"""
Database Updater — Mantiene il database driver sempre aggiornato
================================================================
Scraping da fonti ufficiali: NVIDIA, AMD, Intel, Realtek.
Restituisce le ultime versioni disponibili per ogni produttore.
"""

import re
import json
import time
import hashlib
import ssl
import urllib.request
import urllib.error
import os
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from pathlib import Path

# Costanti
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'driver_db.json')
CACHE_TTL = 86400  # 24 ore tra aggiornamenti
REQUEST_TIMEOUT = 15

# Headers per sembrare un browser
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/125.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


class DriverDBUpdater:
    """
    Aggiorna il database driver da fonti ufficiali.
    Supporta: NVIDIA, AMD, Intel Graphics, Realtek.
    """

    def __init__(self):
        self._cache = {}
        self._last_fetch = 0

    def fetch_nvidia_version(self) -> Optional[Dict]:
        """Recupera ultima versione driver NVIDIA (Game Ready)."""
        # Tentativo 1: NVIDIA API ufficiale
        api_urls = [
            'https://api.nvidiagrid.net/v1/drivers/geforce',
            'https://gfwsl.geforce.com/services_toolkit/services/v3/driver/versions',
            'https://api.nvidia.com/drivers/v1/versions/geforce',
        ]
        
        for api_url in api_urls:
            try:
                req = urllib.request.Request(api_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode())
                
                # Formato 1: lista diretta
                if isinstance(data, list) and len(data) > 0:
                    latest = data[0]
                    version = latest.get('versionNumber') or latest.get('version') or ''
                    download_url = latest.get('downloadUrl') or latest.get('url') or ''
                    if version:
                        return {
                            'latest_version': version,
                            'download_url': download_url,
                            'source': 'nvidia_api',
                            'fetched': datetime.now().isoformat(),
                        }
                
                # Formato 2: annidato in 'drivers'
                if isinstance(data, dict) and 'drivers' in data:
                    drivers = data['drivers']
                    if drivers and len(drivers) > 0:
                        latest = drivers[0]
                        version = latest.get('versionNumber') or latest.get('version') or ''
                        download_url = latest.get('downloadUrl') or latest.get('url') or ''
                        if version:
                            return {
                                'latest_version': version,
                                'download_url': download_url,
                                'source': 'nvidia_api',
                                'fetched': datetime.now().isoformat(),
                            }
            except Exception:
                continue

        # Tentativo 2: NVIDIA download page scraping
        try:
            url = 'https://www.nvidia.com/en-us/geforce/drivers/'
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                html = resp.read().decode('utf-8', errors='ignore')

            patterns = [
                r'Version:\s*(\d+[\d.]*\d+)',
                r'(\d{3}\.\d{2})',  # 560.94
            ]
            versions_found = set()
            for pattern in patterns:
                for match in re.finditer(pattern, html):
                    ver = match.group(1)
                    if len(ver) > 3 and ver.count('.') >= 1:
                        versions_found.add(ver)
            
            if versions_found:
                # Prendi la versione piu' alta
                sorted_versions = sorted(versions_found, key=lambda v: [int(x) for x in v.split('.')], reverse=True)
                return {
                    'latest_version': sorted_versions[0],
                    'download_url': '',
                    'source': 'nvidia_html',
                    'fetched': datetime.now().isoformat(),
                }
        except Exception as e:
            print(f'[DB_UPDATER] NVIDIA HTML fallback error: {e}')

        return None

    def fetch_amd_version(self) -> Optional[Dict]:
        """Recupera ultima versione driver AMD Adrenalin."""
        try:
            url = ('https://www.amd.com/en/support/kb/release-notes/'
                   'amd-software-adrenalin-edition')
            req = urllib.request.Request(url, headers=HEADERS)
            
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                html = resp.read().decode('utf-8', errors='ignore')

            # Cerca versione
            patterns = [
                r'Adrenalin\s*Edition\s*(\d+[\d.]*\d+)',
                r'version\s*(\d+\.\d+\.\d+)',
                r'(\d{2}\.\d{1,2}\.\d{1,2}\.\d{1,4})',  # 25.5.1.xxx
                r'(\d{2}\.\d{1,2}\.\d{1,2})',  # 25.5.1
            ]
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    ver = match.group(1)
                    return {
                        'latest_version': ver,
                        'download_url': '',
                        'source': 'amd',
                        'fetched': datetime.now().isoformat(),
                    }
        except Exception as e:
            print(f'[DB_UPDATER] AMD fetch error: {e}')

        return None

    def fetch_intel_graphics_version(self) -> Optional[Dict]:
        """Recupera ultima versione driver Intel Graphics."""
        # Crea contesto SSL che accetta certificati (alcuni server Intel hanno chain issues)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # URL alternativi per driver Intel
        urls = [
            'https://www.intel.com/content/www/us/en/support/articles/000090744/graphics.html',
            'https://www.intel.com/content/www/us/en/download/19351/intel-graphics-driver-for-windows.html',
            'https://downloadcenter.intel.com/product/80939/Intel-Graphics-Driver',
        ]

        for url in urls:
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                    html = resp.read().decode('utf-8', errors='ignore')

                patterns = [
                    r'version\s*(\d+\.\d+\.\d+\.\d+)',
                    r'(\d{2}\.\d{1,3}\.\d{1,4}\.\d{1,4})',
                    r'Version:\s*(\d+[\d.]*\d+)',
                ]
                for pattern in patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        ver = match.group(1)
                        # Verifica che sia una versione valida
                        parts = [p for p in ver.split('.') if p.isdigit()]
                        if len(parts) >= 3:
                            return {
                                'latest_version': ver,
                                'download_url': url,
                                'source': 'intel',
                                'fetched': datetime.now().isoformat(),
                            }
            except Exception:
                continue

        return None

    def fetch_realtek_audio_version(self) -> Optional[Dict]:
        """Recupera ultima versione driver Realtek Audio."""
        try:
            url = ('https://www.realtek.com/en/component/zoo/category/'
                   'pc-audio-codecs-high-definition-audio-codecs-software')
            req = urllib.request.Request(url, headers=HEADERS)
            
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                html = resp.read().decode('utf-8', errors='ignore')

            patterns = [
                r'(\d+\.\d+\.\d+\.\d+)',
                r'Version\s*(\d+[\d.]*\d+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    ver = match.group(1)
                    if len(ver.split('.')) >= 4:
                        return {
                            'latest_version': ver,
                            'download_url': url,
                            'source': 'realtek',
                            'fetched': datetime.now().isoformat(),
                        }
        except Exception as e:
            print(f'[DB_UPDATER] Realtek fetch error: {e}')

        return None

    def fetch_all(self) -> Dict[str, Optional[Dict]]:
        """Recupera versioni da TUTTE le fonti."""
        results = {
            'nvidia': self.fetch_nvidia_version(),
            'amd': self.fetch_amd_version(),
            'intel_graphics': self.fetch_intel_graphics_version(),
            'realtek_audio': self.fetch_realtek_audio_version(),
            'fetched_at': datetime.now().isoformat(),
        }
        return results

    def update_database(self, force: bool = False) -> Tuple[bool, str]:
        """
        Aggiorna il database JSON con le ultime versioni dalle fonti ufficiali.
        Restituisce (successo, messaggio).
        """
        now = time.time()

        # Check cache
        if not force and (now - self._last_fetch) < CACHE_TTL:
            return True, 'Database già aggiornato (cache valida)'

        if not os.path.exists(DB_PATH):
            return False, f'Database non trovato: {DB_PATH}'

        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                db = json.load(f)
        except Exception as e:
            return False, f'Errore lettura database: {e}'

        # Fetch versioni online
        results = self.fetch_all()
        updated = 0

        # Mappa risultati a entry del database
        mappings = {
            'nvidia': {
                'hw_ids': ['PCI\\VEN_10DE', 'PCI\\VEN_10DE&DEV_1E84',
                          'PCI\\VEN_10DE&DEV_1F08', 'PCI\\VEN_10DE&DEV_2684'],
                'version_field': 'latest_version',
                'url_field': 'download_url',
            },
            'amd': {
                'hw_ids': ['PCI\\VEN_1002', 'PCI\\VEN_1002&DEV_73DF',
                          'PCI\\VEN_1002&DEV_73BF'],
                'version_field': 'latest_version',
                'url_field': 'download_url',
            },
            'intel_graphics': {
                'hw_ids': ['PCI\\VEN_8086', 'PCI\\VEN_8086&DEV_9A49',
                          'PCI\\VEN_8086&DEV_A780'],
                'version_field': 'latest_version',
                'url_field': 'download_url',
            },
            'realtek_audio': {
                'hw_ids': ['HDAUDIO\\FUNC_01&VEN_10EC', 'HDAUDIO\\FUNC_01&VEN_10EC&DEV_0900',
                          'HDAUDIO\\FUNC_01&VEN_10EC&DEV_0899', 'HDAUDIO\\FUNC_01&VEN_10EC&DEV_0892'],
                'version_field': 'latest_version',
                'url_field': 'download_url',
            },
        }

        for source_name, source_result in results.items():
            if source_name == 'fetched_at' or not source_result:
                continue

            mapping = mappings.get(source_name)
            if not mapping:
                continue

            version = source_result.get('latest_version', '')
            url = source_result.get('download_url', '')

            if not version:
                continue

            # Aggiorna tutte le entry corrispondenti
            for hw_id in mapping['hw_ids']:
                if hw_id in db.get('drivers', {}):
                    entry = db['drivers'][hw_id]
                    if entry.get('latest_version') != version:
                        entry['latest_version'] = version
                        if url:
                            entry['download_url'] = url
                        entry['_auto_updated'] = datetime.now().isoformat()
                        updated += 1

        if updated > 0:
            db['updated'] = datetime.now().isoformat()
            db['last_auto_update'] = datetime.now().isoformat()
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(db, f, indent=2, ensure_ascii=False)
            self._last_fetch = now
            return True, f'Database aggiornato: {updated} entry modificate'
        else:
            self._last_fetch = now
            return True, 'Database gia\' alla versione piu\' recente'

    def get_driver_news(self) -> List[Dict]:
        """
        Restituisce le ultime novita' driver (per notifiche all'utente).
        """
        news = []
        results = self.fetch_all()
        
        for source, data in results.items():
            if source == 'fetched_at' or not data:
                continue
            news.append({
                'source': source.replace('_', ' ').title(),
                'version': data.get('latest_version', ''),
                'fetched': data.get('fetched', ''),
            })
        
        return news


# Singleton
_updater_instance = None

def get_db_updater() -> DriverDBUpdater:
    global _updater_instance
    if _updater_instance is None:
        _updater_instance = DriverDBUpdater()
    return _updater_instance


if __name__ == '__main__':
    updater = get_db_updater()
    print('=== Driver DB Updater ===')
    print('Fetching latest versions...')
    results = updater.fetch_all()
    for source, data in results.items():
        if source == 'fetched_at':
            continue
        if data:
            print(f'  {source}: {data.get("latest_version", "?")}')
        else:
            print(f'  {source}: FAILED')
    
    print('\nUpdating database...')
    ok, msg = updater.update_database(force=True)
    print(f'  {msg}')
