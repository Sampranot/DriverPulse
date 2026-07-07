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
from .paths import get_db_path


# Cache del database driver
_db_cache = None
_db_last_load = None
DB_CACHE_TTL = 3600  # 1 ora


def _load_driver_db() -> Dict:
    """Carica il database dei driver."""
    global _db_cache, _db_last_load
    
    now = datetime.now()
    if _db_cache and _db_last_load and (now - _db_last_load).seconds < DB_CACHE_TTL:
        return _db_cache

    db_path = get_db_path()
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
        os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)
        with open(get_db_path(), 'w', encoding='utf-8') as f:
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


# Parole chiave GPU per validare match display
_GPU_KEYWORDS = {'geforce', 'rtx', 'gtx', 'graphics', 'gpu', 'iris', 'arc',
                 'radeon', 'rx ', 'intel graphics', 'nvidia geforce', 'amd radeon'}


def _is_plausible_match(db_entry: dict, dev_category: str, dev_name: str) -> bool:
    """
    Verifica che un match sia plausibile, evitando falsi positivi.
    Un prefix match generico (chiave senza DEV specifico) non deve matchare
    dispositivi di categoria completamente diversa.
    """
    db_cat = db_entry.get('category', '')
    if not db_cat or not dev_name:
        return True
    
    # Per entry generiche di categoria "display", verifica che il device
    # sembri effettivamente una GPU (non un controller USB o audio)
    if db_cat == 'display':
        dev_lower = dev_name.lower()
        # Se il nome del DB è contenuto nel nome del dispositivo, OK
        db_name = db_entry.get('name', '').lower()
        if db_name and (db_name in dev_lower or dev_lower in db_name):
            return True
        # Se il dispositivo ha keyword GPU nel nome, OK
        if any(kw in dev_lower for kw in _GPU_KEYWORDS):
            return True
        # Altrimenti è un falso positivo (es. chipset Intel, controller USB NVIDIA)
        return False
    
    # Per altre categorie: il nome del DB deve essere contenuto
    # nel nome del dispositivo o viceversa
    if db_cat in ('audio', 'network', 'chipset', 'storage', 'bluetooth'):
        db_name = db_entry.get('name', '').lower()
        dev_lower = dev_name.lower()
        if db_name and (db_name in dev_lower or dev_lower in db_name):
            return True
        # Se le categorie WMI coincidono, OK (es. WMI dice "audio" e DB dice "audio")
        if dev_category == db_cat:
            return True
        # Fallback: lascia passare (meglio un falso positivo che un falso negativo,
        # ma per display abbiamo bloccato sopra)
        return True
    
    return True


def _match_driver(driver_map: dict, hw_id: str, dev_name: str,
                  dev_category: str = '') -> Optional[dict]:
    """
    Matcha un dispositivo contro il database driver.
    Cerca: 1) hardware_id esatto, 2) prefix match, 3) nome parziale.
    Restituisce l'entry con il match PIÙ specifico (chiave più lunga), 
    validando la plausibilità del match.
    """
    if not hw_id:
        return None
    
    candidates: list[tuple[int, dict]] = []
    
    # 1) Exact match (sempre valido)
    if hw_id in driver_map:
        candidates.append((10000, driver_map[hw_id]))
    
    # 2) Prefix match: la chiave del database è un prefisso dell'HW ID
    for db_key, db_entry in driver_map.items():
        if db_key in hw_id and db_key != hw_id:
            if _is_plausible_match(db_entry, dev_category, dev_name):
                # Punteggio: lunghezza della chiave (preferiamo match più specifici)
                candidates.append((len(db_key), db_entry))
    
    # 3) Partial name match (solo se non abbiamo già trovato match)
    if not candidates and dev_name:
        dev_name_lower = dev_name.lower()
        for db_key, db_entry in driver_map.items():
            db_name = db_entry.get('name', '').lower()
            if db_name and (db_name in dev_name_lower or dev_name_lower in db_name):
                if _is_plausible_match(db_entry, dev_category, dev_name):
                    candidates.append((len(db_name), db_entry))
    
    if not candidates:
        return None
    
    # Prendi il match con punteggio più alto (chiave più lunga = più specifico)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def compare_with_database(devices: List[DeviceInfo]) -> List[DeviceInfo]:
    """Confronta i dispositivi con il database e marca quelli obsoleti."""
    db = _load_driver_db()
    driver_map = db.get('drivers', {})
    
    for dev in devices:
        hw_id = dev.hardware_id or dev.pnp_id
        dev_name = dev.device_name
        
        best_match = _match_driver(driver_map, hw_id, dev_name, dev.category)
        
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


def online_fallback(devices: List[DeviceInfo]) -> List[DeviceInfo]:
    """
    Cerca online informazioni per dispositivi UNKNOWN.
    Non bloccante: usa timeout breve. Se fallisce, il device resta UNKNOWN.
    Migliora il nome del dispositivo e aggiunge URL di ricerca.
    """
    try:
        from .online_search import search_online
    except ImportError:
        return devices
    
    for dev in devices:
        if dev.status != 'UNKNOWN':
            continue
        
        hw_id = dev.hardware_id or dev.pnp_id
        if not hw_id:
            continue
        
        # Ricerca non bloccante (timeout breve)
        try:
            info = search_online(hw_id, dev.device_name)
            if info.get('name') and info['name'] != dev.device_name:
                dev.device_name = info['name'][:100]  # Arricchisci nome
            if info.get('search_url'):
                dev.search_url = info['search_url']
        except Exception:
            pass
    
    return devices


def scan_drivers(enable_online_fallback: bool = True) -> List[DeviceInfo]:
    """Esegue scansione completa: detect + DB match + online fallback."""
    detector = get_detector()
    devices = detector.get_all_devices(force_refresh=True)
    results = compare_with_database(devices)
    
    if enable_online_fallback:
        try:
            results = online_fallback(results)
        except Exception:
            pass
    
    return results


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
