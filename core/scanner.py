"""
Scanner — Confronta driver installati con il database delle versioni recenti
=============================================================================
"""

import os
import json
import re
from typing import List, Dict, Optional, Tuple
from packaging.version import Version
from datetime import datetime, timedelta

from .detector import get_detector, DeviceInfo


# Cache del database driver
_db_cache = None
_db_last_load = None
DB_CACHE_TTL = 3600  # 1 ora

DRIVER_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'driver_db.json')


def _load_driver_db() -> Dict:
    """Carica il database dei driver."""
    global _db_cache, _db_last_load
    
    now = datetime.now()
    if _db_cache and _db_last_load and (now - _db_last_load).seconds < DB_CACHE_TTL:
        return _db_cache

    db_path = DRIVER_DB_PATH
    if not os.path.exists(db_path):
        # Crea database vuoto se non esiste
        _db_cache = {'drivers': {}, 'version': '1.0', 'updated': now.isoformat()}
        _save_driver_db(_db_cache)
        return _db_cache

    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            _db_cache = json.load(f)
        _db_last_load = now
    except Exception:
        _db_cache = {'drivers': {}, 'version': '1.0', 'updated': now.isoformat()}
    
    return _db_cache


def _save_driver_db(db: Dict):
    """Salva il database dei driver."""
    try:
        os.makedirs(os.path.dirname(DRIVER_DB_PATH), exist_ok=True)
        with open(DRIVER_DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2, default=str)
    except Exception:
        pass


def _parse_version(version_str: str) -> Optional[Version]:
    """Tenta di parsare una stringa di versione."""
    if not version_str:
        return None
    try:
        # Pulisci la stringa
        v = version_str.strip()
        # Rimuovi prefissi non numerici
        v = re.sub(r'^[^\d.]+', '', v)
        # Prendi solo la parte iniziale numerica con punti
        v = re.match(r'[\d.]+', v)
        if v:
            return Version(v.group())
    except Exception:
        pass
    return None


def _is_newer(current: str, suggested: str) -> bool:
    """Determina se suggested è più recente di current."""
    cur_v = _parse_version(current)
    sug_v = _parse_version(suggested)
    if cur_v is None or sug_v is None:
        return False
    return sug_v > cur_v


def compare_with_database(devices: List[DeviceInfo]) -> List[DeviceInfo]:
    """Confronta i dispositivi con il database e marca quelli obsoleti."""
    db = _load_driver_db()
    driver_map = db.get('drivers', {})
    
    for dev in devices:
        # Cerca match per hardware_id
        hw_id = dev.hardware_id or dev.pnp_id
        best_match = None
        
        # Cerca per hardware_id esatto
        if hw_id in driver_map:
            best_match = driver_map[hw_id]
        else:
            # Cerca per nome dispositivo (match parziale)
            dev_name = dev.device_name.lower()
            for db_key, db_entry in driver_map.items():
                db_name = db_entry.get('name', '').lower()
                if dev_name and db_name and (
                    db_name in dev_name or dev_name in db_name
                ):
                    best_match = db_entry
                    break
        
        if best_match:
            suggested_version = best_match.get('latest_version', '')
            suggested_url = best_match.get('download_url', '')
            
            if suggested_version and _is_newer(dev.driver_version, suggested_version):
                dev.status = 'OUTDATED'
                dev.suggested_version = suggested_version
                dev.suggested_url = suggested_url
            elif dev.driver_version:
                dev.status = 'CURRENT'
                dev.suggested_version = suggested_version
            else:
                dev.status = 'UNKNOWN'
        else:
            # Dispositivo non nel database — segna come sconosciuto
            dev.status = 'UNKNOWN'
    
    return devices


def fetch_online_updates() -> bool:
    """
    Aggiorna il database driver da fonti online.
    Questo metodo verra' chiamato periodicamente dalla telemetria.
    """
    # TODO: implementare scraping da fonti ufficiali
    # Per ora, restituisce True per segnalare che il meccanismo e' pronto
    return True


def scan_drivers() -> List[DeviceInfo]:
    """Esegue una scansione completa e restituisce risultati."""
    detector = get_detector()
    devices = detector.get_all_devices(force_refresh=True)
    results = compare_with_database(devices)
    return results


def get_update_summary(results: List[DeviceInfo]) -> Dict:
    """Restituisce un sommario dei risultati scansione."""
    total = len(results)
    outdated = sum(1 for r in results if r.status == 'OUTDATED')
    current = sum(1 for r in results if r.status == 'CURRENT')
    unknown = sum(1 for r in results if r.status == 'UNKNOWN')
    
    return {
        'total': total,
        'outdated': outdated,
        'current': current,
        'unknown': unknown,
        'outdated_devices': [
            {
                'name': r.device_name,
                'current': r.driver_version,
                'suggested': r.suggested_version,
                'url': r.suggested_url,
            }
            for r in results if r.status == 'OUTDATED'
        ]
    }


# ============================================================
# Quick test
# ============================================================
if __name__ == "__main__":
    results = scan_drivers()
    summary = get_update_summary(results)
    print(f"\nScan risultati:")
    print(f"  Totali: {summary['total']}")
    print(f"  Correnti: {summary['current']}")
    print(f"  Obsoleti: {summary['outdated']}")
    print(f"  Sconosciuti: {summary['unknown']}")
    if summary['outdated_devices']:
        print(f"\nDriver obsoleti:")
        for d in summary['outdated_devices']:
            print(f"  - {d['name']}: {d['current']} -> {d['suggested']}")
            if d['url']:
                print(f"    Scarica: {d['url']}")
