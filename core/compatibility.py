"""
Compatibility Check — Verifica compatibilità driver prima del download
======================================================================
Prima di scaricare un driver, verifica:
  - Sistema operativo (Windows 10/11, 32/64 bit)
  - Architettura (x64, ARM64)
  - Versione OS minima richiesta
  - Hardware compatibile (tramite hardware ID)
"""

import platform
import sys
import re
import subprocess
from typing import Dict, Tuple, Optional, List
from packaging.version import Version

from .detector import get_detector, DeviceInfo


class CompatibilityChecker:
    """Verifica se un driver e' compatibile col sistema corrente."""

    def __init__(self):
        self._os_info = self._get_os_info()
        self._detector = get_detector()

    def _get_os_info(self) -> Dict[str, str]:
        """Recupera info complete sul sistema operativo."""
        info = {
            'name': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'arch': platform.machine(),
            'is_64bit': sys.maxsize > 2**32,
        }

        # Dettagli aggiuntivi via WMI
        try:
            import wmi
            c = wmi.WMI()
            os_info = c.Win32_OperatingSystem()[0]
            info['caption'] = getattr(os_info, 'Caption', '') or ''
            info['build'] = getattr(os_info, 'BuildNumber', '') or ''
            info['sp'] = getattr(os_info, 'ServicePackMajorVersion', '') or '0'
            info['os_arch'] = getattr(os_info, 'OSArchitecture', '') or ''
        except:
            pass

        return info

    def check_system_requirements(self, 
                                   min_os: str = '10.0',
                                   required_arch: str = 'x64',
                                   min_ram_gb: float = 0) -> Tuple[bool, str]:
        """
        Verifica requisiti minimi di sistema.
        Restituisce (compatibile, messaggio).
        """
        # Verifica architettura
        if required_arch == 'x64' and not self._os_info.get('is_64bit', False):
            return False, 'Sistema a 32 bit non supportato'

        if required_arch == 'arm64' and self._os_info.get('arch', '').lower() not in ['arm64', 'aarch64']:
            return False, 'Richiesto sistema ARM64'

        # Verifica versione OS
        try:
            os_version = Version(self._os_info.get('release', '0'))
            min_version = Version(min_os)
            if os_version < min_version:
                return False, f'Richiesto Windows {min_os}+ (hai {os_version})'
        except:
            pass

        # Verifica RAM
        if min_ram_gb > 0:
            try:
                import wmi
                c = wmi.WMI()
                total_ram = int(getattr(c.Win32_ComputerSystem()[0], 'TotalPhysicalMemory', 0) or 0)
                ram_gb = total_ram / (1024**3)
                if ram_gb < min_ram_gb:
                    return False, f'Richiesti {min_ram_gb}GB RAM (hai {ram_gb:.1f}GB)'
            except:
                pass

        return True, 'Compatibile'

    def is_driver_compatible(self, device: DeviceInfo, 
                              driver_entry: Dict) -> Tuple[bool, str]:
        """
        Verifica se un driver e' compatibile col dispositivo.
        device: dispositivo rilevato
        driver_entry: entry del database driver
        """
        # Verifica che il vendor corrisponda
        device_hw_id = (device.hardware_id or '').upper()
        driver_hw_patterns = driver_entry.get('_hw_patterns', [driver_entry.get('name', '')])

        # Verifica tramite hardware ID
        for pattern in driver_hw_patterns:
            if pattern.upper() in device_hw_id:
                return True, 'Compatibile (HW match)'

        # Fallback: verifica tramite vendor ID
        vendor_ids = {
            'nvidia': '10DE',
            'amd': ['1002', '1022'],
            'intel': '8086',
            'realtek': '10EC',
        }

        driver_name = (driver_entry.get('name', '') + ' ' + 
                      driver_entry.get('manufacturer', '')).lower()

        for vendor, ids in vendor_ids.items():
            if vendor in driver_name:
                if isinstance(ids, list):
                    if any(vid in device_hw_id for vid in ids):
                        return True, f'Compatibile (vendor {vendor})'
                elif ids in device_hw_id:
                    return True, f'Compatibile (vendor {vendor})'

        return False, 'Hardware non corrispondente'

    def get_os_description(self) -> str:
        """Restituisce descrizione leggibile dell'OS."""
        caption = self._os_info.get('caption', '')
        arch = self._os_info.get('os_arch', self._os_info.get('arch', ''))
        build = self._os_info.get('build', '')
        if caption:
            return f'{caption} ({arch})'
        return f'Windows {self._os_info.get("release", "?")} ({arch})'

    def suggest_alternative_drivers(self, device: DeviceInfo) -> List[Dict]:
        """
        Suggerisce driver alternativi per un dispositivo.
        Utile quando il driver principale non e' compatibile.
        """
        suggestions = []
        category = device.category

        # Driver generici Microsoft
        if category == 'network':
            suggestions.append({
                'name': 'Driver generico Microsoft',
                'version': 'Incluso in Windows',
                'url': '',
                'note': 'Driver nativo, meno funzioni ma stabile',
            })
        elif category == 'display':
            suggestions.append({
                'name': 'Driver display base Microsoft',
                'version': 'Incluso in Windows',
                'url': '',
                'note': 'Risoluzione base, nessuna accelerazione 3D',
            })

        # Driver produttore alternativo
        manufacturer = (device.manufacturer or '').lower()
        if 'realtek' in manufacturer:
            suggestions.append({
                'name': 'Driver Realtek via Windows Update',
                'version': 'Aggiornato da Microsoft',
                'url': '',
                'note': 'Versione firmata Microsoft, potrebbe essere meno recente',
            })

        return suggestions


# Singleton
_checker_instance = None

def get_compatibility_checker() -> CompatibilityChecker:
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = CompatibilityChecker()
    return _checker_instance


if __name__ == '__main__':
    checker = get_compatibility_checker()
    print('=== Compatibility Check ===')
    print(f'OS: {checker.get_os_description()}')
    ok, msg = checker.check_system_requirements()
    print(f'Requisiti: {msg}')
