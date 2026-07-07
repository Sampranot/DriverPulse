"""
Updater — Download e installazione driver
==========================================
Gestisce il download e l'installazione silenziosa dei driver.
Supporta formati: .exe, .msi, .inf, .cab, .zip
Auto-elevazione: se non admin, avvisa prima di tentare installazione.
"""

import os
import sys
import re
import subprocess
import tempfile
import shutil
import zipfile
import urllib.request
import urllib.error
import json
import hashlib
import ctypes
from typing import List, Optional, Tuple, Dict
from pathlib import Path
from datetime import datetime

from .scanner import scan_drivers, get_update_summary
from .detector import DeviceInfo


# Directory per cache dei download
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.driver_cache')
MAX_CACHE_SIZE = 500 * 1024 * 1024  # 500 MB


def is_admin() -> bool:
    """Verifica se il processo ha privilegi di amministratore."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_cache_dir():
    """Crea directory cache se non esiste."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def download_driver(url: str, dest_path: str, timeout: int = 300) -> bool:
    """
    Scarica un driver da URL.
    Restituisce True se il download e' riuscito.
    Supporta redirect HTTP, retry automatico, e referer multipli.
    """
    # Lista di header da provare (alcuni CDN richiedono referer specifico)
    header_sets = [
        {  # Default: sembra browser Chrome
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                      'image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        {  # Intel download center: referer intel.com
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'application/octet-stream,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.intel.com/content/www/us/en/download-center/home.html',
        },
        {  # NVIDIA: referer nvidia.com
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'application/octet-stream,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nvidia.com/download/driverResults.aspx/',
        },
    ]

    # Per URL Intel, dai priorità al referer intel.com
    if 'intel.com' in url or 'downloadmirror' in url:
        header_sets.insert(0, header_sets.pop(1))

    max_retries = 2
    last_error = ""

    for header_set in header_sets:
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    print(f"[RETRY {attempt}/{max_retries}] nuovo tentativo...")

                req = urllib.request.Request(url, headers=header_set)

                with urllib.request.urlopen(req, timeout=timeout) as response:
                    with open(dest_path, 'wb') as f:
                        total_size = int(response.headers.get('Content-Length', 0))
                        downloaded = 0
                        while True:
                            chunk = response.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (512 * 1024) < 8192:
                                pct = min(downloaded * 100 // max(total_size, 1), 100)
                                mb_dl = downloaded // (1024 * 1024)
                                mb_total = total_size // (1024 * 1024)
                                print(f"\r  Download: {pct}% ({mb_dl} MB / {mb_total} MB)", end='')

                if total_size > 0:
                    pct = min(downloaded * 100 // max(total_size, 1), 100)
                    mb_dl = downloaded // (1024 * 1024)
                    mb_total = total_size // (1024 * 1024)
                    print(f"\r  Download: {pct}% ({mb_dl} MB / {mb_total} MB)")

                # Verifica file valido
                if os.path.getsize(dest_path) == 0:
                    os.remove(dest_path)
                    last_error = "File vuoto"
                    continue

                return True

            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                continue
            except Exception as e:
                last_error = str(e)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                continue

        # Se questo header_set ha funzionato, non provare altri
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            return True

    print(f"[ERROR] Download fallito: {last_error}")
    return False


def get_silent_flags_for_vendor(exe_path: str) -> List[str]:
    """Determina i flag di installazione silenziosa in base al nome del file/produttore."""
    name = os.path.basename(exe_path).lower()

    # NVIDIA installer
    if 'nvidia' in name:
        return ['-s', '-noreboot', '/n']
    # Intel installer
    if 'intel' in name or name.startswith('wifi') or name.startswith('bt') or name.startswith('wired'):
        return ['-s', '-norestart', '/quiet', '-quiet']
    # Realtek
    if 'realtek' in name or 'rtl' in name:
        return ['/silent', '/norestart']
    # AMD
    if 'amd' in name or 'radeon' in name:
        return ['-install', '-quiet']
    # Generic
    return ['/S', '/silent', '/verysilent', '/quiet', '/qn', '-y', '-norestart']


def install_driver_inf(inf_path: str) -> Tuple[bool, str]:
    """
    Installa un driver via .inf file.
    Usa pnputil.exe (built-in Windows).
    Richiede privilegi amministratore.
    """
    if not is_admin():
        return False, "Servono privilegi amministratore per installare driver .inf"

    try:
        result = subprocess.run(
            ['pnputil.exe', '/add-driver', inf_path, '/install'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            # pnputil a volte stampa "successo" anche con returncode != 0
            output = (result.stdout + result.stderr).strip()
            if 'successfully' in output.lower() or 'aggiunto' in output.lower():
                return True, output
            return False, output[:200]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (120s)"
    except FileNotFoundError:
        return False, "pnputil.exe non trovato"
    except Exception as e:
        return False, str(e)


def install_driver_exe(exe_path: str) -> Tuple[bool, str]:
    """
    Installa un driver via .exe con parametri silenziosi.
    Prova diversi flag fino a trovare quello che funziona.
    Richiede privilegi amministratore.
    """
    if not is_admin():
        return False, "Servono privilegi amministratore per installare driver .exe"

    silent_flags_list = [
        get_silent_flags_for_vendor(exe_path),
        ['/S', '/verysilent', '/noreboot'],
        ['-s', '-noreboot', '/n'],
        ['--quiet', '--silent'],
        ['/quiet', '/norestart'],
        ['/s', '/v"/qn"'],
    ]

    # Rimuovi duplicati mantenendo l'ordine
    seen = set()
    unique_flags = []
    for flags in silent_flags_list:
        key = tuple(flags)
        if key not in seen:
            seen.add(key)
            unique_flags.append(flags)

    last_error = "Nessun flag silenzioso ha funzionato"
    for flags in unique_flags:
        try:
            result = subprocess.run(
                [exe_path] + flags,
                capture_output=True, text=True, timeout=300
            )
            # Alcuni installer ritornano 0 = OK, altri 3010 = reboot needed
            if result.returncode in (0, 3010, 1641):
                return True, f"Installato (codice={result.returncode})"
            # Alcuni Intel/Realtek ritornano codici strani ma installano
            output = (result.stdout + result.stderr).lower()
            if 'success' in output or 'completed' in output or 'installed' in output:
                return True, f"Installato (returncode={result.returncode})"
            last_error = f"returncode={result.returncode}"
        except subprocess.TimeoutExpired:
            last_error = "TIMEOUT (300s)"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    return False, last_error


def install_driver_msi(msi_path: str) -> Tuple[bool, str]:
    """Installa un driver via .msi. Richiede admin."""
    if not is_admin():
        return False, "Servono privilegi amministratore per installare driver .msi"

    try:
        result = subprocess.run(
            ['msiexec.exe', '/i', msi_path, '/quiet', '/norestart'],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode in (0, 3010, 1641):
            return True, "Installato"
        return False, f"returncode={result.returncode}"
    except Exception as e:
        return False, str(e)


def extract_cab(cab_path: str, extract_dir: str) -> Optional[str]:
    """
    Estrae un file .cab usando expand.exe (built-in Windows).
    Restituisce il percorso della directory di estrazione o None.
    """
    try:
        os.makedirs(extract_dir, exist_ok=True)

        # expand.exe richiede che la directory esista
        result = subprocess.run(
            ['expand.exe', cab_path, '-F:*', extract_dir],
            capture_output=True, text=True, timeout=60
        )

        # Verifica se ha estratto qualcosa
        files = os.listdir(extract_dir)
        if files:
            return extract_dir

        # Fallback: estrai con Python (per .cab semplici)
        # I .cab sono file cabinet, expand.exe è il metodo nativo
        return None

    except Exception as e:
        print(f"  [WARN] Estrazione CAB fallita: {e}")
        return None


def extract_zip(zip_path: str, extract_dir: str) -> Optional[str]:
    """Estrae un file .zip. Restituisce la directory o None."""
    try:
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        files = os.listdir(extract_dir)
        if files:
            return extract_dir

        # Potrebbe essere dentro una sottodirectory
        for root, dirs, _ in os.walk(extract_dir):
            for d in dirs:
                sub_files = os.listdir(os.path.join(root, d))
                if sub_files:
                    return os.path.join(root, d)
        return None

    except Exception as e:
        print(f"  [WARN] Estrazione ZIP fallita: {e}")
        return None


def find_inf_in_dir(directory: str) -> List[str]:
    """Cerca file .inf ricorsivamente in una directory."""
    inf_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.lower().endswith('.inf'):
                # Ignora file .inf non driver (setupapi, etc.)
                if not any(x in f.lower() for x in ['setup', 'layout', 'autorun']):
                    inf_files.append(os.path.join(root, f))
    return inf_files


def find_exe_in_dir(directory: str) -> List[str]:
    """Cerca file .exe di installazione in una directory."""
    exe_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.lower().endswith('.exe'):
                # Filtra setup.exe, installer.exe etc.
                name = f.lower()
                if any(x in name for x in ['setup', 'install', 'driver', 'update']):
                    exe_files.append(os.path.join(root, f))
    return exe_files


def open_download_page(device: DeviceInfo):
    """Apre il browser alla pagina di download del driver."""
    url = device.suggested_url
    if not url:
        # Genera URL di ricerca basato sul nome del dispositivo
        search_url = device.suggested_url or device.search_url
        if not search_url:
            query = f"{device.device_name} driver download"
            import urllib.parse
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        url = search_url

    try:
        import webbrowser
        webbrowser.open(url)
        return True, f"Aperto browser: {url[:80]}..."
    except Exception as e:
        return False, f"Impossibile aprire browser: {e}"


def update_single_device(device: DeviceInfo, force: bool = False,
                         open_browser_if_no_url: bool = True) -> Tuple[bool, str]:
    """
    Aggiorna un singolo dispositivo.
    Supporta: URL diretto, Windows Update fallback, browser fallback.
    Restituisce (successo, messaggio).
    """
    if device.status != 'OUTDATED' and not force:
        return False, f"{device.device_name}: gia' aggiornato"

    url = device.suggested_url

    # Se non c'è URL diretto, prova Windows Update fallback
    if not url:
        ok, msg = _try_windows_update_fallback(device)
        if not ok and open_browser_if_no_url:
            # Apri browser per download manuale
            return open_download_page(device)
        return ok, msg

    # Se l'URL è un placeholder per Windows Update (da online_search)
    if url == 'windows_update':
        ok, msg = _try_windows_update_fallback(device)
        if not ok and open_browser_if_no_url:
            return open_download_page(device)
        return ok, msg

    ensure_cache_dir()

    # Estrai estensione dal URL
    ext = os.path.splitext(url.split('?')[0].split('#')[0])[1].lower()
    if not ext:
        ext = '.exe'  # fallback

    # Nome file unico usando hash dell'URL
    safe_name = re.sub(r'[^\w\-]', '_', device.device_name)[:40]
    filename = f"{safe_name}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
    filepath = os.path.join(CACHE_DIR, filename)

    # Download
    print(f"[UPDATE] {device.device_name}: download in corso...")
    success = download_driver(url, filepath)
    if not success:
        # Se download fallisce, apri browser per download manuale
        if open_browser_if_no_url:
            print(f"  -> Download diretto non disponibile. Apro browser...")
            return open_download_page(device)
        return False, f"{device.device_name}: download fallito"

    # Installazione in base al tipo
    print(f"[UPDATE] {device.device_name}: installazione...")
    ok, msg = _install_file(filepath, device)

    # Pulisci cache se necessario
    _cleanup_cache()

    if ok:
        device.status = 'CURRENT'
        return True, f"{device.device_name}: aggiornato a {device.suggested_version}"
    else:
        return False, f"{device.device_name}: installazione fallita - {msg}"


def _install_file(filepath: str, device: DeviceInfo) -> Tuple[bool, str]:
    """
    Installa un file driver in base all'estensione.
    Supporta .exe, .msi, .inf, .cab, .zip
    """
    ext = os.path.splitext(filepath)[1].lower()

    # .exe diretto
    if ext == '.exe':
        return install_driver_exe(filepath)

    # .msi diretto
    if ext == '.msi':
        return install_driver_msi(filepath)

    # .inf diretto
    if ext == '.inf':
        return install_driver_inf(filepath)

    # .cab: estrai e cerca .inf
    if ext == '.cab':
        print(f"  Estrazione CAB in corso...")
        extract_dir = os.path.join(CACHE_DIR, f"_extracted_{os.path.basename(filepath)}")
        result = extract_cab(filepath, extract_dir)
        if result:
            infs = find_inf_in_dir(result)
            if infs:
                print(f"  Trovato .inf: {os.path.basename(infs[0])}")
                return install_driver_inf(infs[0])
            exes = find_exe_in_dir(result)
            if exes:
                print(f"  Trovato .exe: {os.path.basename(exes[0])}")
                return install_driver_exe(exes[0])
        return False, "Nessun driver trovato nel CAB"

    # .zip: estrai e cerca .inf/.exe
    if ext == '.zip':
        print(f"  Estrazione ZIP in corso...")
        extract_dir = os.path.join(CACHE_DIR, f"_extracted_{os.path.basename(filepath)}")
        result = extract_zip(filepath, extract_dir)
        if result:
            infs = find_inf_in_dir(result)
            if infs:
                print(f"  Trovato .inf: {os.path.basename(infs[0])}")
                return install_driver_inf(infs[0])
            exes = find_exe_in_dir(result)
            if exes:
                print(f"  Trovato .exe: {os.path.basename(exes[0])}")
                return install_driver_exe(exes[0])
        return False, "Nessun driver trovato nello ZIP"

    # .sys (raw driver): prova con pnputil
    if ext == '.sys':
        return False, "Driver .sys richiede installazione manuale con pnputil"

    return False, f"Formato non supportato: {ext}"


def _try_windows_update_fallback(device: DeviceInfo) -> Tuple[bool, str]:
    """
    Prova a cercare e scaricare il driver da Windows Update.
    Usa Microsoft.Update API via PowerShell.
    """
    hw_id = device.hardware_id or device.pnp_id
    if not hw_id:
        return False, f"{device.device_name}: nessun hardware ID"

    print(f"[WU] {device.device_name}: ricerca su Windows Update...")

    # Script PowerShell per cercare e scaricare driver da Windows Update
    ps_script = f'''
param([string]$hwId = "{hw_id}")

$ErrorActionPreference = "SilentlyContinue"
try {{
    $Session = New-Object -ComObject Microsoft.Update.Session
    $Searcher = $Session.CreateUpdateSearcher()
    $searchString = "Type='Driver' and DriverHardwareID='" + $hwId + "'"
    $result = $Searcher.Search($searchString)

    if ($result.Updates.Count -eq 0) {{
        Write-Output "NO_UPDATES"
        exit 1
    }}

    $update = $result.Updates | Sort-Object LastDeploymentChangeTime -Descending | Select-Object -First 1

    # Scarica l'update
    $downloads = New-Object -ComObject Microsoft.Update.Downloader
    $downloads.Updates = New-Object -ComObject Microsoft.Update.UpdateColl
    $downloads.Updates.Add($update) | Out-Null

    $downloadResult = $downloads.Download()

    if ($downloadResult.ResultCode -eq 2) {{  # Downloaded
        # Crea la lista di installazione
        $installations = New-Object -ComObject Microsoft.Update.Installer
        $installations.Updates = New-Object -ComObject Microsoft.Update.UpdateColl
        $installations.Updates.Add($update) | Out-Null

        $installationResult = $installations.Install()

        Write-Output "INSTALL_RESULT:$($installationResult.ResultCode)"
        Write-Output "TITLE:$($update.Title)"
        exit 0
    }} else {{
        Write-Output "DOWNLOAD_FAILED:$($downloadResult.ResultCode)"
        exit 1
    }}
}} catch {{
    Write-Output "ERROR:$($_.Exception.Message)"
    exit 1
}}
'''

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
             '-File', '-'],
            input=ps_script,
            capture_output=True, text=True, timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        lines = result.stdout.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('INSTALL_RESULT:'):
                code = line.split(':', 1)[1].strip()
                if code == '2':  # Installed
                    return True, f"{device.device_name}: aggiornato da Windows Update"
            elif line.startswith('TITLE:'):
                title = line.split(':', 1)[1].strip()
                print(f"  Trovato: {title[:80]}")
            elif line.startswith('NO_UPDATES'):
                return False, f"{device.device_name}: nessun update su Windows Update"
            elif line.startswith('DOWNLOAD_FAILED:'):
                return False, f"{device.device_name}: download WU fallito"
            elif line.startswith('ERROR:'):
                err = line.split(':', 1)[1].strip()
                return False, f"{device.device_name}: Windows Update: {err[:100]}"

        return False, f"{device.device_name}: Windows Update non disponibile"

    except subprocess.TimeoutExpired:
        return False, f"{device.device_name}: Windows Update TIMEOUT (180s)"
    except Exception as e:
        return False, f"{device.device_name}: Windows Update: {e}"


def update_all(devices: Optional[List[DeviceInfo]] = None) -> Tuple[int, int]:
    """
    Aggiorna tutti i driver obsoleti.
    Restituisce (numero_successi, numero_fallimenti).
    """
    if devices is None:
        devices = scan_drivers()

    outdated = [d for d in devices if d.status == 'OUTDATED']

    if not outdated:
        print("[UPDATE] Nessun driver obsoleto trovato.")
        return 0, 0

    # Check admin
    if not is_admin():
        print("[WARNING] Non hai privilegi amministratore.")
        print("          L'installazione dei driver RICHIEDE l'esecuzione come Admin.")
        print("          Usa: DriverPulse.exe --update (si auto-eleva via UAC)")
        # Tentiamo comunque (alcuni driver potrebbero funzionare)
        print("          Tento comunque...")

    success = 0
    failed = 0

    for device in outdated:
        try:
            ok, msg = update_single_device(device)
            if ok:
                success += 1
            else:
                failed += 1
            print(f"  {'OK' if ok else 'FAIL'} {msg}")
        except Exception as e:
            failed += 1
            print(f"  ERR {device.device_name}: {e}")

    return success, failed


def _cleanup_cache():
    """Pulisce la cache dei download se supera il limite."""
    try:
        total = 0
        files = []
        for f in os.listdir(CACHE_DIR):
            fp = os.path.join(CACHE_DIR, f)
            if os.path.isfile(fp):
                size = os.path.getsize(fp)
                total += size
                files.append((fp, os.path.getmtime(fp)))

        if total > MAX_CACHE_SIZE:
            files.sort(key=lambda x: x[1])
            while total > MAX_CACHE_SIZE and files:
                fp, _ = files.pop(0)
                total -= os.path.getsize(fp)
                try:
                    os.remove(fp)
                except Exception:
                    pass
    except Exception:
        pass


# ============================================================
if __name__ == "__main__":
    success, failed = update_all()
    print(f"\nAggiornati: {success}, Falliti: {failed}")
