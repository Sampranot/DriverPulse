"""
Installer — Download e installazione driver
=============================================
Il cuore di DriverPulse: aggiorna i driver obsoleti in modo sicuro.

Flusso:
  1. Crea punto di ripristino
  2. Backup driver corrente (pnputil /export-driver)
  3. Download nuovo driver
  4. Installazione silenziosa
  5. Verifica installazione
  6. Rollback se necessario
"""
import os
import re
import sys
import json
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from typing import Optional, Tuple, List, Dict
from datetime import datetime
from pathlib import Path

# Timeout download (secondi)
DOWNLOAD_TIMEOUT = 300  # 5 minuti
INSTALL_TIMEOUT = 120   # 2 minuti

# Directory per backup driver
try:
    from .paths import get_backup_dir
    BACKUP_DIR = get_backup_dir()
except ImportError:
    # Fallback per esecuzione diretta
    import os
    BACKUP_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                              'DriverPulse', 'backups')

# Headers per download
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _run_as_admin() -> bool:
    """Verifica se il processo ha privilegi di amministratore."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _require_admin() -> Tuple[bool, str]:
    """Richiede privilegi di amministratore."""
    if not _run_as_admin():
        return False, "Servono privilegi di amministratore per installare driver."
    return True, ""


def create_restore_point(description: str = "DriverPulse - Driver Update") -> Tuple[bool, str]:
    """Crea un punto di ripristino di sistema."""
    try:
        # PowerShell per creare restore point
        ps_script = f'''
Checkpoint-Computer -Description "{description}" -RestorePointType MODIFY_SETTINGS
'''
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return True, "Punto di ripristino creato"
        return False, f"Punto di ripristino: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Errore restore point: {e}"


def backup_driver(hardware_id: str, driver_version: str) -> Tuple[bool, str, str]:
    """
    Backup del driver corrente via pnputil.
    Restituisce (successo, messaggio, percorso_backup).
    """
    # Crea directory backup con timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = re.sub(r'[\\/&]', '_', hardware_id)[:50]
    backup_path = os.path.join(BACKUP_DIR, f'{safe_name}_{timestamp}')

    try:
        os.makedirs(backup_path, exist_ok=True)

        # Trova il driver con pnputil
        result = subprocess.run(
            ['pnputil', '/enum-drivers'],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode != 0:
            return False, "pnputil non disponibile", ""

        # Cerca l'original name (file .inf) per l'hardware
        # Formato output pnputil:
        #   Driver originale: oemXX.inf
        #   Nome provider: ...
        #   Classe: ...
        #   Hardware ID: ...
        current_oem = None
        lines = result.stdout.split('\n')
        for i, line in enumerate(lines):
            if hardware_id.split('&')[0] in line and 'Hardware ID' in line:
                # Risali per trovare "Driver originale"
                for j in range(i - 1, max(0, i - 5), -1):
                    m = re.search(r'Driver originale:\s*(oem\d+\.inf)', lines[j], re.IGNORECASE)
                    if m:
                        current_oem = m.group(1)
                        break

        if not current_oem:
            return False, f"Driver non trovato per {hardware_id[:40]}", ""

        # Esporta driver
        result = subprocess.run(
            ['pnputil', '/export-driver', current_oem, backup_path],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode == 0:
            # Scrivi info backup
            info = {
                'hardware_id': hardware_id,
                'driver_version': driver_version,
                'oem_file': current_oem,
                'backup_date': datetime.now().isoformat(),
                'files': os.listdir(backup_path),
            }
            with open(os.path.join(backup_path, 'backup_info.json'), 'w') as f:
                json.dump(info, f, indent=2)
            return True, f"Backup driver in {backup_path}", backup_path

        return False, f"Export fallito: {result.stderr.strip()}", ""

    except Exception as e:
        return False, f"Errore backup: {e}", ""


def download_driver(download_url: str, dest_path: str) -> Tuple[bool, str]:
    """Scarica un file driver con progress indicator."""
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        req = urllib.request.Request(download_url, headers=_HEADERS)

        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
            total = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 8192

            with open(dest_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = (downloaded / total) * 100
                        print(f"\r  Download: {pct:.0f}% ({downloaded//1024//1024}MB/{total//1024//1024}MB)", end="")

        print()
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        return True, f"Scaricato {size_mb:.0f}MB in {dest_path}"

    except urllib.error.HTTPError as e:
        return False, f"Errore HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Errore di rete: {e.reason}"
    except Exception as e:
        return False, f"Errore download: {e}"


def install_driver_silent(driver_path: str) -> Tuple[bool, str]:
    """
    Installazione silenziosa del driver.
    Supporta formati: .exe (vari produttori), .inf (via pnputil).
    """
    if not os.path.exists(driver_path):
        return False, f"File non trovato: {driver_path}"

    ext = os.path.splitext(driver_path)[1].lower()

    try:
        if ext == '.inf':
            # Installazione via pnputil
            result = subprocess.run(
                ['pnputil', '/add-driver', driver_path, '/install'],
                capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                return True, "Driver installato via pnputil"
            return False, result.stderr.strip()

        elif ext == '.exe':
            # Tentativi di installazione silenziosa per vari produttori
            silent_flags = [
                ['/S', '/quiet'],           # NVIDIA, Intel, generico
                ['-s', '-quiet'],           # Alcuni Intel
                ['/verysilent'],            # InnoSetup
                ['/s', '/v"/qn"'],          # MSI wrapper
                ['--silent'],               # Universale
            ]

            for flags in silent_flags:
                try:
                    result = subprocess.run(
                        [driver_path] + flags,
                        capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    if result.returncode == 0:
                        return True, f"Installato con flag: {' '.join(flags)}"
                except Exception:
                    continue

            # Ultimo tentativo: esecuzione senza flag (mostra UI)
            return False, "Installazione silenziosa non supportata per questo driver."

        elif ext == '.zip':
            # Driver zippato: estrai e installa via .inf
            import zipfile
            extract_dir = tempfile.mkdtemp(prefix='dp_driver_')
            try:
                with zipfile.ZipFile(driver_path, 'r') as zf:
                    zf.extractall(extract_dir)

                # Cerca .inf nella directory estratta
                for root, dirs, files in os.walk(extract_dir):
                    for f in files:
                        if f.endswith('.inf'):
                            inf_path = os.path.join(root, f)
                            return install_driver_silent(inf_path)

                return False, "Nessun file .inf trovato nel ZIP"
            finally:
                shutil.rmtree(extract_dir, ignore_errors=True)

        else:
            return False, f"Formato non supportato: {ext}"

    except Exception as e:
        return False, f"Errore installazione: {e}"


def rollback_driver(backup_path: str) -> Tuple[bool, str]:
    """Ripristina un driver dal backup."""
    if not os.path.exists(backup_path):
        return False, f"Backup non trovato: {backup_path}"

    try:
        # Leggi info backup
        info_path = os.path.join(backup_path, 'backup_info.json')
        if os.path.exists(info_path):
            with open(info_path) as f:
                info = json.load(f)

        # Re-installa i driver dal backup
        # pnputil /add-driver *.inf /install
        installed = 0
        for f in os.listdir(backup_path):
            if f.endswith('.inf') and f != 'backup_info.json':
                fp = os.path.join(backup_path, f)
                result = subprocess.run(
                    ['pnputil', '/add-driver', fp, '/install'],
                    capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    installed += 1

        if installed > 0:
            return True, f"Rollback completato: {installed} driver reinstallati"
        return False, "Nessun driver ripristinato dal backup"

    except Exception as e:
        return False, f"Errore rollback: {e}"


def get_available_backups() -> List[Dict]:
    """Restituisce lista dei backup disponibili."""
    backups = []
    if not os.path.exists(BACKUP_DIR):
        return backups

    for entry in os.listdir(BACKUP_DIR):
        entry_path = os.path.join(BACKUP_DIR, entry)
        info_path = os.path.join(entry_path, 'backup_info.json')
        if os.path.isdir(entry_path) and os.path.exists(info_path):
            try:
                with open(info_path) as f:
                    info = json.load(f)
                backups.append(info)
            except Exception:
                pass

    return sorted(backups, key=lambda x: x.get('backup_date', ''), reverse=True)


def update_single_driver(device_info) -> Tuple[bool, str]:
    """
    Flusso completo di aggiornamento per un singolo dispositivo.
    device_info: oggetto DeviceInfo con status OUTDATED.
    """
    if not _run_as_admin():
        return False, "Servono privilegi di amministratore."

    hw_id = device_info.hardware_id or device_info.pnp_id or ''
    current_ver = device_info.driver_version or '0'
    new_ver = device_info.suggested_version or ''
    dl_url = device_info.suggested_url or ''

    if not new_ver:
        return False, "Nessuna versione suggerita."
    if not dl_url:
        return False, "Nessun URL di download."

    print(f"\n{'='*60}")
    print(f"Aggiornamento: {device_info.device_name}")
    print(f"  Versione corrente: {current_ver}")
    print(f"  Nuova versione:    {new_ver}")
    print(f"{'='*60}")

    # 1) Punto di ripristino
    print("\n[1/5] Creazione punto di ripristino...")
    ok, msg = create_restore_point()
    print(f"  {msg}")

    # 2) Backup
    print("\n[2/5] Backup driver corrente...")
    ok, msg, backup_path = backup_driver(hw_id, current_ver)
    print(f"  {msg}")
    if not ok:
        print("  ⚠ Continuo senza backup.")

    # 3) Download
    print(f"\n[3/5] Download nuovo driver...")
    temp_dir = tempfile.mkdtemp(prefix='dp_dl_')
    safe_name = re.sub(r'[^\w.]', '_', device_info.device_name)[:30]
    dl_path = os.path.join(temp_dir, f'{safe_name}.exe')

    ok, msg = download_driver(dl_url, dl_path)
    print(f"  {msg}")
    if not ok:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, f"Download fallito: {msg}"

    # 4) Installazione
    print(f"\n[4/5] Installazione driver...")
    ok, msg = install_driver_silent(dl_path)
    print(f"  {msg}")

    # 5) Verifica
    print(f"\n[5/5] Verifica installazione...")
    if ok:
        print(f"  ✅ Driver {device_info.device_name} aggiornato a {new_ver}")
        # Pulisci
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        return True, f"Aggiornato a {new_ver}"
    else:
        # Rollback
        print(f"  ❌ Installazione fallita.")
        if backup_path:
            print(f"  Avvio rollback...")
            ok_rb, msg_rb = rollback_driver(backup_path)
            print(f"  Rollback: {msg_rb}")
        return False, f"Installazione fallita: {msg}"


def update_all_outdated(devices: list) -> List[Dict]:
    """Aggiorna tutti i driver obsoleti."""
    if not _run_as_admin():
        return [{'device': 'SYSTEM', 'success': False, 'message': 'Admin required'}]

    results = []
    outdated = [d for d in devices if d.status == 'OUTDATED']

    if not outdated:
        return [{'device': 'NONE', 'success': True, 'message': 'Nessun driver obsoleto'}]

    print(f"Trovati {len(outdated)} driver obsoleti.")
    for i, dev in enumerate(outdated, 1):
        print(f"\n--- [{i}/{len(outdated)}] {dev.device_name} ---")
        success, msg = update_single_driver(dev)
        results.append({
            'device': dev.device_name,
            'success': success,
            'message': msg,
            'old_version': dev.driver_version,
            'new_version': dev.suggested_version,
        })

    return results


if __name__ == '__main__':
    # Test: mostra backup disponibili
    print("=== DriverPulse Installer ===")
    print(f"Admin: {_run_as_admin()}")
    print(f"Backup dir: {BACKUP_DIR}")

    backups = get_available_backups()
    if backups:
        print(f"\nBackup disponibili: {len(backups)}")
        for b in backups[:5]:
            print(f"  {b.get('backup_date', '?')} - {b.get('hardware_id', '?')[:40]}")
    else:
        print("\nNessun backup disponibile.")
