"""
Online Search — Cerca informazioni driver per hardware ID sconosciuti
====================================================================
Fallback quando un dispositivo non e' nel database locale.
Usa DeviceHunt + Windows Update API + link per ricerca manuale.

NON bloccante: timeout breve, non crasha mai.
Funziona su qualsiasi Windows 10/11.
"""
import re
import os
import json
import time
import subprocess
from typing import Optional, Dict
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

# Cache
_CACHE = {}
_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'db', 'search_cache.json')
_CACHE_TTL = 86400 * 30  # 30 giorni

# Headers per sembrare un browser
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
    """Cerca il nome del dispositivo su DeviceHunt.
    Funziona per PCI e USB. Non richiede API key.
    """
    ven, dev = _extract_vendor_device(hw_id)
    if not ven or not dev:
        return None

    # Determina se è PCI o USB
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

        # Cerca il nome del dispositivo nell'HTML
        # Pattern: "Device Name" o titolo della pagina
        patterns = [
            # DeviceHunt mette il nome nel titolo: "NOME — PCI VEN:DEV — DeviceHunt"
            r'<title>(.+?)\s*[—–-]\s*(?:PCI|USB)\s+\w+:\w+\s*[—–-]\s*DeviceHunt</title>',
            # O nel tag h1
            r'<h1[^>]*>(.+?)</h1>',
            # O in un div con classe device-name
            r'class="[^"]*device-name[^"]*"[^>]*>(.+?)</',
            r'class="[^"]*device[^"]*"[^>]*>(.+?)</',
        ]
        device_name = ''
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                name = match.group(1).strip()
                # Pulisci da tag HTML
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

        # Fallback: nessun nome trovato
        return {
            'name': f'Vendor {ven} Device {dev}',
            'vendor_id': ven,
            'device_id': dev,
            'source': 'devicehunt_fallback',
        }

    except Exception:
        return None


def search_windows_update(hw_id: str, timeout: int = 15) -> Optional[Dict]:
    """Cerca driver tramite Windows Update API (PowerShell).
    Restituisce {version, title} o None se non disponibile.
    """
    # Script PowerShell robusto
    ps_script = f'''
try {{
    `$Session = New-Object -ComObject Microsoft.Update.Session
    `$Searcher = `$Session.CreateUpdateSearcher()
    `$searchString = "Type='Driver' and DriverHardwareID='{hw_id}'"
    `$result = `$Searcher.Search(`$searchString)
    if (`$result.Updates.Count -gt 0) {{
        `$u = `$result.Updates | Sort-Object LastDeploymentChangeTime -Descending | Select-Object -First 1
        `$ver = ""
        `$title = `$u.Title
        `$m = [regex]::Match(`$title, '(\\d+\\.\\d+\\.\\d+\\.\\d+)')
        if (`$m.Success) {{ `$ver = `$m.Groups[1].Value }}
        Write-Output ("VERSION:" + `$ver)
        Write-Output ("TITLE:" + `$title)
        exit 0
    }}
}} catch {{
    Write-Output ("ERROR:" + `$_.Exception.Message)
}}
exit 1
'''
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        lines = result.stdout.strip().split('\n')
        version = ''
        title = ''
        for line in lines:
            line = line.strip()
            if line.startswith('VERSION:'):
                version = line[8:].strip()
            elif line.startswith('TITLE:'):
                title = line[6:].strip()
            elif line.startswith('ERROR:'):
                return None

        if version:
            return {
                'latest_version': version,
                'title': title,
                'source': 'windows_update',
            }
        return None

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def search_online(hw_id: str, device_name: str = '') -> Dict:
    """
    Cerca informazioni per un hardware ID sconosciuto.
    Restituisce SEMPRE un dict, mai None:
    - name: nome del dispositivo (trovato o derivato)
    - version: versione driver (se trovata)
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
    cache_key = hw_id.replace('&', '_').replace('\\', '_')
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
        if time.time() - cached.get('_ts', 0) < _CACHE_TTL:
            return cached.get('data', result)

    # 1) Cerca nome su DeviceHunt
    dh = search_devicehunt(hw_id)
    if dh and dh.get('name'):
        result['name'] = dh['name']
        result['source'] = dh['source']

    # 2) Cerca versione su Windows Update
    wu = search_windows_update(hw_id)
    if wu:
        result['latest_version'] = wu.get('latest_version', '')
        result['source'] = 'windows_update'

    # 3) Genera URL per ricerca manuale
    if hw_id.startswith('PCI\\') or hw_id.startswith('USB\\'):
        # Microsoft Update Catalog search
        encoded = hw_id.replace('\\', '%5C').replace('&', '%26')
        result['search_url'] = (f'https://www.catalog.update.microsoft.com/'
                                f'Search.aspx?q={encoded}')

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
        print(f'  URL ricerca: {result.get("search_url", "?")[:60]}')
