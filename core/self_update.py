"""
self_update — Auto-aggiornamento DriverPulse
==============================================
Controlla su GitHub se c'e' una nuova versione,
scarica il nuovo eseguibile e lo installa.
"""

import os
import sys
import json
import tempfile
import subprocess
from typing import Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError

APP_NAME = "DriverPulse"
CURRENT_VERSION = "1.0.0"
REPO_OWNER = "Sampranot"
REPO_NAME = "DriverPulse"
RELEASE_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
TIMEOUT = 15


def _get_local_version() -> str:
    return CURRENT_VERSION


def _parse_remote_version(release_data: dict) -> Optional[str]:
    tag = release_data.get('tag_name', '')
    if tag.startswith('v'):
        tag = tag[1:]
    return tag if tag else None


def check_for_updates(timeout: int = TIMEOUT) -> Tuple[bool, str, Optional[dict]]:
    try:
        req = Request(RELEASE_API, headers={
            'User-Agent': f'{APP_NAME}/{CURRENT_VERSION}',
            'Accept': 'application/vnd.github.v3+json',
        })
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        remote_ver = _parse_remote_version(data)
        if not remote_ver:
            return False, "Impossibile leggere la versione remota.", None

        local = _get_local_version()
        if remote_ver == local:
            return False, f"Sei gia' all'ultima versione ({local}).", data

        local_parts = [int(x) for x in local.split('.')]
        remote_parts = [int(x) for x in remote_ver.split('.')]
        while len(local_parts) < len(remote_parts):
            local_parts.append(0)
        while len(remote_parts) < len(local_parts):
            remote_parts.append(0)

        if remote_parts > local_parts:
            changelog = (data.get('body', '') or '')[:300]
            return True, f"Nuova versione {remote_ver} disponibile! (hai {local})", data
        else:
            return False, f"Versione locale ({local}) uguale o superiore alla remota ({remote_ver}).", data

    except URLError as e:
        return False, f"Impossibile contattare GitHub: {e.reason}", None
    except Exception as e:
        return False, f"Errore controllo aggiornamenti: {e}", None


def download_update(release_data: dict, timeout: int = 120) -> Tuple[bool, str]:
    assets = release_data.get('assets', [])
    if not assets:
        return False, "Nessun asset disponibile nella release."

    target_asset = None
    for asset in assets:
        name = asset.get('name', '')
        if name.lower().endswith('.exe') and APP_NAME.lower() in name.lower():
            target_asset = asset
            break

    if not target_asset:
        for asset in assets:
            if asset.get('name', '').lower().endswith('.exe'):
                target_asset = asset
                break

    if not target_asset:
        return False, "Nessun file .exe trovato tra gli asset della release."

    download_url = target_asset.get('browser_download_url')
    if not download_url:
        return False, "URL di download non trovato."

    try:
        temp_dir = tempfile.gettempdir()
        temp_exe = os.path.join(temp_dir, f"{APP_NAME}_update.exe")

        req = Request(download_url, headers={
            'User-Agent': f'{APP_NAME}/{CURRENT_VERSION}',
        })
        with urlopen(req, timeout=timeout) as resp:
            with open(temp_exe, 'wb') as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)

        if not os.path.exists(temp_exe) or os.path.getsize(temp_exe) == 0:
            return False, "Download fallito: file vuoto o non trovato."

        return True, temp_exe

    except Exception as e:
        return False, f"Errore durante il download: {e}"


def apply_update(downloaded_exe: str) -> Tuple[bool, str]:
    current_exe = sys.executable if getattr(sys, 'frozen', False) else None

    if not current_exe:
        return False, "Modalita' sviluppo: copia manuale necessaria."

    current_dir = os.path.dirname(current_exe)
    exe_name = os.path.basename(current_exe)
    backup_exe = os.path.join(current_dir, f"{exe_name}.bak")
    new_exe = os.path.join(current_dir, exe_name)

    bat_path = os.path.join(tempfile.gettempdir(), f"_update_{APP_NAME}.bat")
    bat_content = f"""@echo off
chcp 65001 >nul
timeout /t 2 /nobreak >nul
if exist "{backup_exe}" del /f /q "{backup_exe}"
if exist "{new_exe}" move /y "{new_exe}" "{backup_exe}" >nul 2>&1
if exist "{downloaded_exe}" move /y "{downloaded_exe}" "{new_exe}" >nul 2>&1
if exist "{new_exe}" (
    start "" "{new_exe}" --update-done
    del /f /q "%~f0"
)
"""
    try:
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)

        subprocess.Popen(
            ['cmd.exe', '/c', bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return True, "Aggiornamento applicato. Il programma ripartira' automaticamente."

    except Exception as e:
        return False, f"Errore applicazione aggiornamento: {e}"


if __name__ == "__main__":
    print(f"{APP_NAME} — Controllo aggiornamenti...")
    ok, msg, data = check_for_updates()
    print(msg)
    if ok and data:
        print("Download in corso...")
        ok2, path = download_update(data)
        if ok2:
            print(f"Scaricato: {path}")
            print("Applicazione...")
            ok3, msg3 = apply_update(path)
            print(msg3)
        else:
            print(path)
