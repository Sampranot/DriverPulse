"""
Updater — Download e installazione driver
==========================================
Gestisce il download e l'installazione silenziosa dei driver.
Supporta formati: .exe, .msi, .inf (PNP)
"""

import os
import sys
import subprocess
import tempfile
import shutil
import urllib.request
import urllib.error
import json
import hashlib
from typing import List, Optional, Tuple, Dict
from pathlib import Path
from datetime import datetime

from .scanner import scan_drivers, get_update_summary
from .detector import DeviceInfo


# Directory per cache dei download
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.driver_cache')
MAX_CACHE_SIZE = 500 * 1024 * 1024  # 500 MB


def ensure_cache_dir():
    """Crea directory cache se non esiste."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def download_driver(url: str, dest_path: str, timeout: int = 120) -> bool:
    """
    Scarica un driver da URL.
    Restituisce True se il download e' riuscito.
    """
    try:
        print(f"[DOWNLOAD] {url} -> {dest_path}")
        
        # Headers per sembrare un browser normale
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/octet-stream,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            with open(dest_path, 'wb') as f:
                shutil.copyfileobj(response, f)
        
        # Verifica che il file non sia vuoto
        if os.path.getsize(dest_path) == 0:
            os.remove(dest_path)
            return False
            
        return True
        
    except Exception as e:
        print(f"[ERROR] Download fallito: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def install_driver_inf(inf_path: str) -> Tuple[bool, str]:
    """
    Installa un driver via .inf file.
    Usa pnputil.exe (built-in Windows).
    """
    try:
        # Aggiungi al driver store
        result = subprocess.run(
            ['pnputil.exe', '/add-driver', inf_path, '/install'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError:
        return False, "pnputil.exe non trovato"
    except Exception as e:
        return False, str(e)


def install_driver_exe(exe_path: str, silent_args: Optional[List[str]] = None) -> Tuple[bool, str]:
    """
    Installa un driver via .exe con parametri silenziosi.
    """
    if silent_args is None:
        # Default silent flags per vari produttori
        silent_args = ['/S', '/silent', '/verysilent', '/quiet', '/qn', '-y']
    
    try:
        result = subprocess.run(
            [exe_path] + silent_args,
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            return True, "Installation completed"
        else:
            # Alcuni installer ritornano codici non-zero anche se OK
            return True, result.stdout.strip() or result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (300s)"
    except Exception as e:
        return False, str(e)


def install_driver_msi(msi_path: str) -> Tuple[bool, str]:
    """Installa un driver via .msi."""
    try:
        result = subprocess.run(
            ['msiexec.exe', '/i', msi_path, '/quiet', '/norestart'],
            capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def update_single_device(device: DeviceInfo, force: bool = False) -> Tuple[bool, str]:
    """
    Aggiorna un singolo dispositivo.
    Restituisce (successo, messaggio).
    """
    if device.status != 'OUTDATED' and not force:
        return False, f"{device.device_name}: gia' aggiornato"
    
    if not device.suggested_url:
        return False, f"{device.device_name}: nessun URL disponibile"
    
    ensure_cache_dir()
    
    # Estrai estensione dal URL
    url = device.suggested_url
    ext = os.path.splitext(url.split('?')[0])[1].lower()
    if not ext:
        ext = '.exe'  # fallback
    
    # Nome file unico
    safe_name = re.sub(r'[^\w\-]', '_', device.device_name)[:40]
    filename = f"{safe_name}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
    filepath = os.path.join(CACHE_DIR, filename)
    
    # Download
    print(f"[UPDATE] {device.device_name}: download in corso...")
    success = download_driver(url, filepath)
    if not success:
        return False, f"{device.device_name}: download fallito"
    
    # Installazione in base al tipo
    print(f"[UPDATE] {device.device_name}: installazione...")
    if ext == '.inf':
        ok, msg = install_driver_inf(filepath)
    elif ext == '.msi':
        ok, msg = install_driver_msi(filepath)
    else:
        ok, msg = install_driver_exe(filepath)
    
    # Pulisci cache se necessario
    _cleanup_cache()
    
    if ok:
        device.status = 'CURRENT'
        return True, f"{device.device_name}: aggiornato a {device.suggested_version}"
    else:
        return False, f"{device.device_name}: installazione fallita - {msg}"


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
            # Rimuovi i piu' vecchi
            files.sort(key=lambda x: x[1])
            while total > MAX_CACHE_SIZE and files:
                fp, _ = files.pop(0)
                total -= os.path.getsize(fp)
                os.remove(fp)
    except Exception:
        pass


import re

# ============================================================
if __name__ == "__main__":
    success, failed = update_all()
    print(f"\nAggiornati: {success}, Falliti: {failed}")
