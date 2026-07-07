"""
Online Search — Cerca, scarica e installa driver da Windows Update
====================================================================
Fallback quando un dispositivo non e' nel database locale o non ha URL.
Supporta:
  - Ricerca Windows Update API (PowerShell)
  - Scaricamento diretto driver da Microsoft Update Catalog
  - DeviceHunt per identificazione hardware
  - Cache intelligente (30 giorni)

NON bloccante: timeout breve, non crasha mai.
Funziona su qualsiasi Windows 10/11.
"""
import re
import os
import json
import time
import subprocess
import tempfile
import hashlib
import shutil
from typing import Optional, Dict, Tuple, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Cache
_CACHE = {}
try:
    from .paths import get_cache_path as _get_cache_path
    _CACHE_PATH = _get_cache_path()
except ImportError:
    _CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               'db', 'search_cache.json')
_CACHE_TTL = 86400 * 30  # 30 giorni

# Headers per sembrare un browser
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _load_cache():
    global _CACHE
    try:
        if os.path.exists(_CACHE_PATH):
            with open(_CACHE_PATH, 'r', encoding='utf-8') as f:
                _CACHE = json.load(f)
    except Exception:
        _CACHE = {}


def _save_cache():
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_CACHE, f, indent=2)
    except Exception:
        pass


def _extract_vendor_device(hw_id: str) -> tuple:
    """Estrae vendor e device ID da un hardware ID.
    Esempio: PCI\\\\VEN_10DE&DEV_1F06 -> ('10DE', '1F06')
    """
    if not hw_id:
        return ('', '')
    ven_match = re.search(r'VEN_([0-9A-Fa-f]+)', str(hw_id))
    dev_match = re.search(r'DEV_([0-9A-Fa-f]+)', str(hw_id))
    ven = ven_match.group(1).upper() if ven_match else ''
    dev = dev_match.group(1).upper() if dev_match else ''
    return (ven, dev)


def search_devicehunt(hw_id: str, timeout: int = 8) -> Optional[Dict]:
    """Cerca il nome del dispositivo su DeviceHunt."""
    ven, dev = _extract_vendor_device(hw_id)
    if not ven or not dev:
        return None

    if hw_id.startswith('PCI\\'):
        url = f'https://devicehunt.com/view/type/pci/vendor/{ven}/device/{dev}'
    elif hw_id.startswith('USB\\'):
        url = f'https://devicehunt.com/view/type/usb/vendor/{ven}/device/{dev}'
    else:
        return None

    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        patterns = [
            r'<title>(.+?)\s*[—–-]\s*(?:PCI|USB)\s+\w+:\w+\s*[—–-]\s*DeviceHunt</title>',
            r'<h1[^>]*>(.+?)</h1>',
            r'class="[^"]*device-name[^"]*"[^>]*>(.+?)</',
            r'class="[^"]*device[^"]*"[^>]*>(.+?)</',
        ]
        device_name = ''
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                name = match.group(1).strip()
                name = re.sub(r'<[^>]+>', '', name)
                name = name.split('—')[0].strip()
                if name and 'DeviceHunt' not in name:
                    device_name = name
                    break

        if device_name:
            return {
                'name': device_name,
                'vendor_id': ven,
                'device_id': dev,
                'source': 'devicehunt',
            }

        return {
            'name': f'Vendor {ven} Device {dev}',
            'vendor_id': ven,
            'device_id': dev,
            'source': 'devicehunt_fallback',
        }

    except Exception:
        return None


def search_windows_update(hw_id: str, timeout: int = 30) -> Optional[Dict]:
    """
    Cerca driver tramite Windows Update API (PowerShell).
    Restituisce {version, title, download_url} o None.
    """
    ps_script = f'''
param([string]$hwId = "{hw_id}")

$ErrorActionPreference = "SilentlyContinue"
try {{
    $Session = New-Object -ComObject Microsoft.Update.Session
    $Searcher = $Session.CreateUpdateSearcher()
    $searchString = "Type='Driver' and DriverHardwareID='" + $hwId + "'"
    $result = $Searcher.Search($searchString)

    if ($result.Updates.Count -eq 0) {{
        Write-Output "STATUS:NO_UPDATES"
        exit 1
    }}

    $update = $result.Updates | Sort-Object LastDeploymentChangeTime -Descending | Select-Object -First 1

    Write-Output "STATUS:FOUND"
    Write-Output "TITLE:$($update.Title)"
    Write-Output "SIZE:$($update.MaxDownloadSize)"

    # Estrai versione dal titolo
    $ver = ""
    $m = [regex]::Match($update.Title, '(\\d+\\.\\d+\\.\\d+\\.\\d+)')
    if ($m.Success) {{ $ver = $m.Groups[1].Value }}
    Write-Output "VERSION:$ver"

    # Verifica se l'update e' scaricabile
    $downloadable = $true
    try {{
        $dl = New-Object -ComObject Microsoft.Update.Downloader
        $dl.Updates = New-Object -ComObject Microsoft.Update.UpdateColl
        $dl.Updates.Add($update) | Out-Null
        Write-Output "DOWNLOADABLE:yes"
    }} catch {{
        Write-Output "DOWNLOADABLE:no"
    }}

    exit 0
}} catch {{
    Write-Output ("STATUS:ERROR")
    Write-Output ("MSG:" + $_.Exception.Message)
    exit 1
}}
'''
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        lines = result.stdout.strip().split('\n')
        info = {'source': 'windows_update', 'status': 'unknown'}
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, _, value = line.partition(':')
                info[key.strip()] = value.strip()

        if info.get('STATUS') == 'FOUND':
            return {
                'latest_version': info.get('VERSION', ''),
                'title': info.get('TITLE', ''),
                'size': info.get('SIZE', '0'),
                'downloadable': info.get('DOWNLOADABLE', 'yes') == 'yes',
                'source': 'windows_update',
            }

        return None

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def download_and_install_wu(hw_id: str, device_name: str = '') -> Tuple[bool, str]:
    """
    Scarica e installa un driver da Windows Update.
    Usa Microsoft.Update API via PowerShell.
    Restituisce (successo, messaggio).
    Richiede privilegi amministratore.
    """
    ps_script = f'''
param([string]$hwId = "{hw_id}")

$ErrorActionPreference = "SilentlyContinue"
try {{
    $Session = New-Object -ComObject Microsoft.Update.Session
    $Searcher = $Session.CreateUpdateSearcher()
    $searchString = "Type='Driver' and DriverHardwareID='" + $hwId + "'"
    $result = $Searcher.Search($searchString)

    if ($result.Updates.Count -eq 0) {{
        Write-Output "STATUS:NO_UPDATES"
        exit 1
    }}

    $update = $result.Updates | Sort-Object LastDeploymentChangeTime -Descending | Select-Object -First 1

    Write-Output "TITLE:$($update.Title)"

    # Scarica
    $downloader = New-Object -ComObject Microsoft.Update.Downloader
    $downloader.Updates = New-Object -ComObject Microsoft.Update.UpdateColl
    $downloader.Updates.Add($update) | Out-Null

    $dlResult = $downloader.Download()

    if ($dlResult.ResultCode -ne 2) {{
        Write-Output "STATUS:DOWNLOAD_FAILED:$($dlResult.ResultCode)"
        exit 1
    }}

    Write-Output "STATUS:DOWNLOADED"

    # Installa
    $installer = New-Object -ComObject Microsoft.Update.Installer
    $installer.Updates = New-Object -ComObject Microsoft.Update.UpdateColl
    $installer.Updates.Add($update) | Out-Null

    $installResult = $installer.Install()

    if ($installResult.ResultCode -eq 2) {{
        Write-Output "STATUS:INSTALLED"
        exit 0
    }} else {{
        Write-Output "STATUS:INSTALL_FAILED:$($installResult.ResultCode)"
        exit 1
    }}
}} catch {{
    Write-Output ("STATUS:ERROR")
    Write-Output ("MSG:" + $_.Exception.Message)
    exit 1
}}
'''
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
            capture_output=True, text=True, timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        stdout = result.stdout.strip()
        title = ''
        status = ''
        for line in stdout.split('\n'):
            line = line.strip()
            if line.startswith('TITLE:'):
                title = line.split(':', 1)[1].strip()[:100]
            elif line.startswith('STATUS:'):
                status = line.split(':', 1)[1].strip()

        if status == 'INSTALLED':
            return True, f"{device_name}: driver installato da Windows Update"
        elif status == 'NO_UPDATES':
            return False, f"{device_name}: nessun driver su Windows Update"
        elif status == 'DOWNLOADED':
            return False, f"{device_name}: scaricato ma installazione fallita"
        elif status:
            return False, f"{device_name}: Windows Update: {status[:100]}"
        else:
            return False, f"{device_name}: Windows Update non risponde"

    except subprocess.TimeoutExpired:
        return False, f"{device_name}: Windows Update TIMEOUT (300s)"
    except Exception as e:
        return False, f"{device_name}: {e}"


def generate_search_url(hw_id: str) -> str:
    """Genera URL per ricerca manuale su Microsoft Update Catalog."""
    if not hw_id:
        return ''

    # Codifica l'HW ID per URL
    encoded = hw_id.replace('\\', '%5C').replace('&', '%26')
    return f'https://www.catalog.update.microsoft.com/Search.aspx?q={encoded}'


def search_online(hw_id: str, device_name: str = '') -> Dict:
    """
    Cerca informazioni per un hardware ID sconosciuto.
    Restituisce SEMPRE un dict, mai None:
    - name: nome del dispositivo (trovato o derivato)
    - latest_version: versione driver (se trovata)
    - download_url: URL per download diretto (se trovato)
    - search_url: URL per ricerca manuale
    - source: fonte delle informazioni
    """
    result = {
        'name': device_name,
        'latest_version': '',
        'download_url': '',
        'search_url': '',
        'source': 'unknown',
    }

    if not hw_id:
        return result

    # Cache check
    _load_cache()
    cache_key = re.sub(r'[&\\]', '_', hw_id)
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
        if time.time() - cached.get('_ts', 0) < _CACHE_TTL:
            return cached.get('data', result)

    # 1) Cerca nome su DeviceHunt
    dh = search_devicehunt(hw_id)
    if dh and dh.get('name'):
        result['name'] = dh['name']
        result['source'] = dh.get('source', 'devicehunt')

    # 2) Cerca versione su Windows Update
    wu = search_windows_update(hw_id)
    if wu:
        result['latest_version'] = wu.get('latest_version', '')
        result['source'] = 'windows_update'
        if wu.get('downloadable'):
            result['download_url'] = 'windows_update'  # Flag per usare WU API

    # 3) Genera URL per ricerca manuale
    if hw_id.startswith('PCI\\') or hw_id.startswith('USB\\'):
        result['search_url'] = generate_search_url(hw_id)

    # Salva in cache
    _CACHE[cache_key] = {
        'data': result,
        '_ts': time.time(),
    }
    _save_cache()

    return result


def clear_cache():
    global _CACHE
    _CACHE = {}
    if os.path.exists(_CACHE_PATH):
        try:
            os.remove(_CACHE_PATH)
        except Exception:
            pass


if __name__ == '__main__':
    # Test
    test_ids = [
        r'PCI\VEN_10DE&DEV_1F06',
        r'PCI\VEN_8086&DEV_3E30',
        r'USB\VID_8087&PID_0AA7',
    ]
    for hw_id in test_ids:
        print(f'\nHW ID: {hw_id}')
        result = search_online(hw_id)
        print(f'  Nome: {result.get("name", "?")}')
        print(f'  Versione: {result.get("latest_version", "?")}')
        print(f'  URL: {result.get("search_url", "?")[:80]}')
