"""
Hardware Detector — Rileva dispositivi e driver via WMI
========================================================
Utilizza Windows Management Instrumentation per:
  - Enumerare tutti i dispositivi hardware
  - Leggere versioni driver correnti
  - Identificare produttori e hardware IDs
"""

import wmi
import sys
import re
import json
import subprocess
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class DeviceInfo:
    """Informazioni su un dispositivo hardware e il suo driver."""
    device_id: str = ""
    device_name: str = ""
    hardware_id: str = ""
    manufacturer: str = ""
    driver_provider: str = ""
    driver_version: str = ""
    driver_date: str = ""
    driver_path: str = ""
    class_guid: str = ""
    category: str = "unknown"
    status: str = "unknown"  # current, outdated, missing, unknown
    suggested_version: str = ""
    suggested_url: str = ""
    search_url: str = ""  # URL per ricerca manuale (es. MS Update Catalog)
    pnp_id: str = ""


class HardwareDetector:
    """Rileva hardware e driver tramite WMI + fallback PowerShell."""

    def __init__(self):
        self._cached_devices: Optional[List[DeviceInfo]] = None
        self._conn = None
        try:
            self._conn = wmi.WMI()
        except Exception as e:
            print(f"[WARNING] WMI COM non disponibile: {e}")
            print("[INFO]  Uso fallback PowerShell...")

    def get_all_devices(self, force_refresh: bool = False) -> List[DeviceInfo]:
        """Recupera tutti i dispositivi hardware con i loro driver.
        Usa WMI COM se disponibile, altrimenti fallback PowerShell."""
        if self._cached_devices and not force_refresh:
            return self._cached_devices

        devices = []

        # Fallback PowerShell se WMI COM non disponibile
        if not self._conn:
            devices = self._scan_with_powershell()
            self._cached_devices = devices
            return devices

        try:
            # Carica TUTTI i driver in una batch query (velocissimo)
            driver_map = self._load_all_drivers()

            # Query PnP entities (dispositivi con driver)
            pnp_entities = self._conn.query(
                "SELECT * FROM Win32_PnPEntity WHERE ConfigManagerErrorCode = 0"
            )
            
            for entity in pnp_entities:
                try:
                    pnp_id = getattr(entity, 'PNPDeviceID', '') or ''
                    dev = DeviceInfo(
                        device_id=getattr(entity, 'DeviceID', '') or '',
                        device_name=self._clean_name(getattr(entity, 'Name', '') or 'Unknown Device'),
                        hardware_id=self._get_first_hw_id(entity),
                        manufacturer=getattr(entity, 'Manufacturer', '') or '',
                        driver_provider='',
                        driver_version='',
                        driver_date='',
                        driver_path='',
                        class_guid=getattr(entity, 'ClassGuid', '') or '',
                        category=self._categorize(entity),
                        pnp_id=pnp_id,
                    )

                    # Lookup driver nel batch map (O(1))
                    driver_info = driver_map.get(pnp_id) or driver_map.get(dev.device_id)
                    if driver_info:
                        dev.driver_version = driver_info.get('DriverVersion', '')
                        dev.driver_provider = driver_info.get('DriverProvider', '')
                        dev.driver_date = driver_info.get('DriverDate', '')
                        dev.driver_path = driver_info.get('InfName', '')

                    devices.append(dev)
                except Exception:
                    continue

        except Exception as e:
            print(f"[ERROR] WMI query: {e}")
            print("[INFO]  Fallback a PowerShell...")
            devices = self._scan_with_powershell()

        self._cached_devices = devices
        return devices

    def _scan_with_powershell(self) -> List[DeviceInfo]:
        """Fallback: enumera dispositivi via PowerShell con DriverVersion reale.
        Usa Get-PnpDeviceProperty per DriverVersion (funziona sempre su Win10/11).
        Gestisce correttamente null, errori, e qualsiasi versione di Windows."""
        ps_script = r'''
$devices = @()
try {
    # Pre-carica tutti i dispositivi CIM (veloce)
    $allWmi = Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue
    foreach ($d in $allWmi) {
        # Nome dispositivo (safe)
        $name = ""
        try { $name = [string]$d.Name } catch {}
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        
        # HardwareID (safe)
        $hwId = ""
        if ($d.HardwareID) {
            try { 
                $first = @($d.HardwareID)[0]
                if ($first) { $hwId = [string]$first }
            } catch {}
        }
        
        # Manufacturer (safe)
        $manu = ""
        try { $manu = [string]$d.Manufacturer } catch {}
        
        # DRIVER VERSION - via PnpDeviceProperty (funziona sempre)
        $ver = ""
        try {
            $p = Get-PnpDeviceProperty -InstanceId $d.PNPDeviceID -KeyName "DEVPKEY_Device_DriverVersion" -ErrorAction SilentlyContinue
            if ($null -ne $p -and $null -ne $p.Data) {
                $ver = [string]$p.Data
            }
        } catch {}
        
        # Driver Date (safe)
        $date = ""
        try { $date = [string]$d.DriverDate } catch {}
        
        $dev = [PSCustomObject]@{
            DeviceID   = [string]$d.DeviceID
            Name       = $name
            HardwareID = $hwId
            Manufacturer = $manu
            DriverVersion = $ver
            DriverDate = $date
        }
        $devices += $dev
    }
} catch {
    Write-Output ("PS_ERROR:" + $_.Exception.Message)
}
$devices | ConvertTo-Json -Compress -Depth 2
'''
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
                capture_output=True, text=True, timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            raw = result.stdout.strip()
            print(f"[DEBUG] PS returncode={result.returncode} stdout={len(raw)}B stderr={len(result.stderr)}B")

            if not raw:
                print(f"[DEBUG] PS stdout vuoto. stderr: {result.stderr[:200]}")
                return self._scan_with_wmic()

            if raw.startswith('PS_ERROR'):
                print(f"[DEBUG] PS ERROR: {raw[:200]}")
                return self._scan_with_wmic()

            # Estrai JSON dall'output
            json_start = raw.find('[{')
            if json_start < 0:
                print(f"[DEBUG] Nessun JSON trovato. Output: {raw[:200]}")
                return self._scan_with_wmic()

            raw_json = raw[json_start:]
            json_end = raw_json.rfind('}]')
            if json_end < 0:
                print(f"[DEBUG] JSON non terminato: {raw_json[:200]}")
                return self._scan_with_wmic()
            raw_json = raw_json[:json_end+2]

            ps_devices = json.loads(raw_json)
            print(f"[DEBUG] PS trovati {len(ps_devices)} dispositivi (grezzi)")

            devices = []
            for d in ps_devices:
                name = d.get('Name', '') or ''
                if not name.strip() or name == 'Unknown':
                    continue
                name = self._clean_name(name)
                hw_id = d.get('HardwareID', '') or ''
                version = self._fmt_version(d.get('DriverVersion', '') or '')
                dev = DeviceInfo(
                    device_id=d.get('DeviceID', '') or '',
                    device_name=name,
                    hardware_id=hw_id,
                    manufacturer=d.get('Manufacturer', '') or '',
                    driver_version=version,
                    driver_date=d.get('DriverDate', '') or '',
                    category=self._categorize_from_class('', name),
                    pnp_id=d.get('DeviceID', '') or '',
                )
                devices.append(dev)

            con_versione = sum(1 for d in devices if d.driver_version)
            print(f"[DEBUG] PS finali: {len(devices)} dispositivi, {con_versione} con DriverVersion")
            return devices

        except Exception as e:
            print(f"[WARN] PowerShell scan: {e}")
            return self._scan_with_wmic()

    def _scan_with_wmic(self) -> List[DeviceInfo]:
        """Ultimo fallback: usa wmic.exe (obsoleto ma presente su tutti i Windows)."""
        ps_script = r'''
$devices = @()
try {
    $wmi = Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.ConfigManagerErrorCode -eq 0 }
    foreach ($d in $wmi) {
        $hwId = ""
        if ($d.HardwareID) { $hwId = [string]($d.HardwareID[0]) }
        $dev = [PSCustomObject]@{
            DeviceID   = $d.DeviceID
            Name       = $d.Name
            HardwareID = $hwId
            Class      = "Unknown"
            Manufacturer = $d.Manufacturer
            DriverVersion = $d.DriverVersion
            DriverProvider = ""
            DriverDate = $d.DriverDate
        }
        $devices += $dev
    }
} catch {}
$devices | ConvertTo-Json -Compress -Depth 2
'''
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
                capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if not result.stdout.strip():
                return []

            import json
            raw = result.stdout.strip()
            json_start = raw.find('[{')
            if json_start >= 0:
                raw = raw[json_start:]
            json_end = raw.rfind('}]')
            if json_end >= 0:
                raw = raw[:json_end+2]

            ps_devices = json.loads(raw)
            devices = []
            for d in ps_devices:
                if not d.get('Name') or d.get('Name') == 'Unknown':
                    continue
                name = d.get('Name', 'Unknown Device') or 'Unknown Device'
                name = self._clean_name(name)
                dev = DeviceInfo(
                    device_id=d.get('DeviceID', '') or '',
                    device_name=name,
                    hardware_id=d.get('HardwareID', '') or '',
                    manufacturer=d.get('Manufacturer', '') or '',
                    driver_version=self._fmt_version(d.get('DriverVersion', '') or ''),
                    driver_date=d.get('DriverDate', '') or '',
                    pnp_id=d.get('DeviceID', '') or '',
                )
                devices.append(dev)
            return devices

        except Exception as e:
            print(f"[WARN] WMIC scan fallito: {e}")
            return []

    def _fmt_version(self, v: str) -> str:
        """Formatta versione driver."""
        if not v:
            return ''
        # Già in formato stringa
        return v.strip()

    def _categorize_from_class(self, cls: str, name: str) -> str:
        """Categorizza dispositivo da classe PnP e nome."""
        cls_lower = cls.lower()
        name_lower = name.lower()
        if cls_lower in ('display', 'video'):
            return 'display'
        if cls_lower in ('net', 'network', 'netcard', 'wifi', 'bluetooth'):
            return 'network'
        if cls_lower in ('audio', 'media', 'sound'):
            return 'audio'
        if cls_lower in ('hdc', 'storage', 'diskdrive'):
            return 'storage'
        if cls_lower in ('usb', 'usbhub'):
            return 'usb'
        if cls_lower in ('keyboard', 'mouse', 'hid'):
            return 'input'
        if cls_lower in ('system', 'chipset', 'motherboard'):
            return 'chipset'
        if 'nvidia' in name_lower or 'radeon' in name_lower or 'graphics' in name_lower:
            return 'display'
        if 'audio' in name_lower or 'realtek' in name_lower:
            return 'audio'
        if 'ethernet' in name_lower or 'wifi' in name_lower or 'wireless' in name_lower or 'bluetooth' in name_lower:
            return 'network'
        if 'sata' in name_lower or 'ahci' in name_lower or 'nvme' in name_lower:
            return 'storage'
        if 'intel' in name_lower and 'chipset' in name_lower:
            return 'chipset'
        return 'unknown'

    def get_device_by_category(self, category: str) -> List[DeviceInfo]:
        """Filtra dispositivi per categoria."""
        return [d for d in self.get_all_devices() if d.category == category]

    def get_gpu_info(self) -> List[DeviceInfo]:
        """Recupera informazioni GPU."""
        return self.get_device_by_category('display')

    def get_network_info(self) -> List[DeviceInfo]:
        """Recupera informazioni rete."""
        return self.get_device_by_category('network')

    def get_chipset_info(self) -> List[DeviceInfo]:
        """Recupera informazioni chipset."""
        return self.get_device_by_category('chipset')

    def get_audio_info(self) -> List[DeviceInfo]:
        """Recupera informazioni audio."""
        return self.get_device_by_category('audio')

    def get_storage_info(self) -> List[DeviceInfo]:
        """Recupera informazioni storage."""
        return self.get_device_by_category('storage')

    def get_system_summary(self) -> Dict[str, Any]:
        """Restituisce un sommario del sistema."""
        devices = self.get_all_devices()
        summary = {
            'total_devices': len(devices),
            'by_category': {},
            'os_info': self._get_os_info(),
            'computer_info': self._get_computer_info(),
        }
        for d in devices:
            cat = d.category
            if cat not in summary['by_category']:
                summary['by_category'][cat] = {'count': 0, 'devices': []}
            summary['by_category'][cat]['count'] += 1
            summary['by_category'][cat]['devices'].append({
                'name': d.device_name,
                'driver': d.driver_version,
                'status': d.status,
            })
        return summary

    # ---- Metodi privati ----

    def _clean_name(self, name: str) -> str:
        """Pulisce il nome del dispositivo."""
        name = re.sub(r'\s+', ' ', name).strip()
        # Rimuovi parentesi con informazioni ridondanti
        name = re.sub(r'\s*\([^)]*\)\s*', ' ', name).strip()
        return name

    def _get_first_hw_id(self, entity) -> str:
        """Estrae il primo Hardware ID."""
        try:
            hw_ids = getattr(entity, 'HardwareID', None) or []
            if hw_ids and len(hw_ids) > 0:
                return hw_ids[0]
        except Exception:
            pass
        # Prova da PNPDeviceID
        try:
            pnp = getattr(entity, 'PNPDeviceID', '') or ''
            return pnp
        except Exception:
            return ''

    def _load_all_drivers(self) -> Dict[str, Dict[str, str]]:
        """
        Carica TUTTI i driver in una batch query.
        Restituisce dict {PNP_DeviceID: {DriverVersion, DriverProvider, ...}}
        Questo e' MOLTO piu' veloce che fare query individuali.
        """
        driver_map = {}
        if not self._conn:
            return driver_map
        
        try:
            q = self._conn.query("SELECT * FROM Win32_PnPSignedDriver")
            for driver in q:
                device_id = getattr(driver, 'DeviceID', '') or ''
                if device_id:
                    driver_map[device_id] = {
                        'DriverVersion': getattr(driver, 'DriverVersion', '') or '',
                        'DriverProvider': getattr(driver, 'DriverProviderName', '') or '',
                        'DriverDate': str(getattr(driver, 'DriverDate', '') or ''),
                        'InfName': getattr(driver, 'InfName', '') or '',
                    }
        except Exception as e:
            print(f"[WARNING] Driver batch load: {e}")
        
        return driver_map

    def _categorize(self, entity) -> str:
        """Classifica il dispositivo in base al ClassGuid."""
        cg = (getattr(entity, 'ClassGuid', '') or '').upper()
        
        # Mappa ClassGUID a categorie
        categories = {
            '4D36E968-E325-11CE-BFC1-08002BE10318': 'display',
            '4D36E972-E325-11CE-BFC1-08002BE10318': 'network',
            '4D36E96F-E325-11CE-BFC1-08002BE10318': 'mouse',
            '4D36E96B-E325-11CE-BFC1-08002BE10318': 'keyboard',
            '4D36E96C-E325-11CE-BFC1-08002BE10318': 'audio',
            '4D36E97D-E325-11CE-BFC1-08002BE10318': 'display',
            '4D36E97B-E325-11CE-BFC1-08002BE10318': 'storage',
            '4D36E97E-E325-11CE-BFC1-08002BE10318': 'printer',
            '4D36E980-E325-11CE-BFC1-08002BE10318': 'port',
            '745A17A0-74D3-11D0-B6FE-00A0C90F57DA': 'input',
            '6BDD1FC5-810F-11D0-BEC7-08002BE2092F': 'camera',
            'C166523C-FE0C-4A94-A586-F1A80CFBBF3E': 'bluetooth',
        }

        if cg in categories:
            return categories[cg]

        # Fallback: dal nome
        name = (getattr(entity, 'Name', '') or '').lower()
        if any(g in name for g in ['nvidia', 'amd', 'radeon', 'intel graphics', 'intel hd']):
            return 'display'
        if any(n in name for n in ['realtek', 'intel ethernet', 'qualcomm', 'broadcom']):
            return 'network'
        if any(n in name for n in ['high definition audio', 'realtek audio']):
            return 'audio'
        if any(n in name for n in ['smbus', 'chipset', 'pci bridge', 'lpc']):
            return 'chipset'
        if any(n in name for n in ['sata', 'nvme', 'ahci', 'storage']):
            return 'storage'
        if any(n in name for n in ['bluetooth', 'bt']):
            return 'bluetooth'
        
        return 'other'

    def _get_os_info(self) -> Dict[str, str]:
        """Info sistema operativo."""
        try:
            os_info = self._conn.Win32_OperatingSystem()[0]
            return {
                'name': getattr(os_info, 'Caption', '') or '',
                'version': getattr(os_info, 'Version', '') or '',
                'build': getattr(os_info, 'BuildNumber', '') or '',
                'arch': getattr(os_info, 'OSArchitecture', '') or '',
            }
        except Exception:
            return {'name': platform.system() + ' ' + platform.release()}

    def _get_computer_info(self) -> Dict[str, str]:
        """Info computer."""
        try:
            cs = self._conn.Win32_ComputerSystem()[0]
            return {
                'model': getattr(cs, 'Model', '') or '',
                'manufacturer': getattr(cs, 'Manufacturer', '') or '',
                'total_ram_gb': round(int(getattr(cs, 'TotalPhysicalMemory', 0) or 0) / (1024**3), 1),
            }
        except Exception:
            return {}

    def get_gpu_temperature(self) -> Optional[float]:
        """Tenta di leggere temperatura GPU (solo NVIDIA/AMD recenti)."""
        try:
            # Prova con Win32_PerfFormattedData_GPUPerformanceCounters
            gpu_perf = self._conn.query("SELECT * FROM Win32_PerfFormattedData_GPUPerformanceCounters")
            for g in gpu_perf:
                # Non tutti i GPUs espongono temperatura via WMI
                pass
        except Exception:
            pass
        return None


# Esporta singleton
_detector_instance = None

def get_detector() -> HardwareDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = HardwareDetector()
    return _detector_instance


# Se eseguito direttamente, mostra info
if __name__ == "__main__":
    det = get_detector()
    summary = det.get_system_summary()
    print("\n=== SYSTEM SUMMARY ===")
    print(f"OS: {summary['os_info'].get('name', 'N/A')}")
    print(f"Computer: {summary['computer_info'].get('manufacturer', 'N/A')} "
          f"{summary['computer_info'].get('model', 'N/A')}")
    print(f"RAM: {summary['computer_info'].get('total_ram_gb', 'N/A')} GB")
    print(f"\nDispositivi trovati: {summary['total_devices']}")
    for cat, info in summary['by_category'].items():
        devices_str = ', '.join([d['name'][:30] for d in info['devices'][:5]])
        if len(info['devices']) > 5:
            devices_str += f' ... e altri {len(info["devices"]) - 5}'
        print(f"  {cat}: {info['count']} — {devices_str}")
