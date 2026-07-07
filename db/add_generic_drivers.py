#!/usr/bin/env python3
"""Aggiunge driver generici al database per fallback per vendor."""
import json
from pathlib import Path

db_path = Path(__file__).parent / "driver_db.json"
db = json.loads(db_path.read_text(encoding="utf-8"))

generics = {
    "PCI\\VEN_10DE": {"name": "NVIDIA GPU (Generic)", "manufacturer": "NVIDIA", "latest_version": "560.94", "download_url": "https://us.download.nvidia.com/Windows/560.94/560.94-desktop-win10-win11-64bit-international-dch-whql.exe", "category": "display", "checksum": "", "notes": "NVIDIA Game Ready Driver"},
    "PCI\\VEN_1002": {"name": "AMD GPU (Generic)", "manufacturer": "AMD", "latest_version": "24.12.1", "download_url": "https://drivers.amd.com/drivers/whql-amd-software-adrenalin-24.12.1-win10-win11-december2024.exe", "category": "display", "checksum": "", "notes": "AMD Adrenalin Driver"},
    "PCI\\VEN_8086": {"name": "Intel Device (Generic)", "manufacturer": "Intel", "latest_version": "10.1.20008.8625", "download_url": "https://downloadmirror.intel.com/787188/setup-chipset.exe", "category": "chipset", "checksum": "", "notes": "Intel Chipset Driver"},
    "PCI\\VEN_1022": {"name": "AMD Chipset (Generic)", "manufacturer": "AMD", "latest_version": "6.10.17.152", "download_url": "https://drivers.amd.com/drivers/amd_chipset_software_6.10.17.152.exe", "category": "chipset", "checksum": "", "notes": "AMD Chipset Driver"},
    "PCI\\VEN_10EC": {"name": "Realtek Device (Generic)", "manufacturer": "Realtek", "latest_version": "10.69.115.2024", "download_url": "https://www.realtek.com/Download/RTLAN_10.69.115.2024.zip", "category": "network", "checksum": "", "notes": "Realtek Driver"},
    "HDAUDIO\\VEN_10EC": {"name": "Realtek Audio (Generic)", "manufacturer": "Realtek", "latest_version": "6.0.9857.1", "download_url": "https://www.realtek.com/Download/HDACodec_6.0.9857.1.zip", "category": "audio", "checksum": "", "notes": "Realtek HD Audio"},
    "PCI\\VEN_144D": {"name": "Samsung NVMe (Generic)", "manufacturer": "Samsung", "latest_version": "5.1.0.0", "download_url": "https://www.samsung.com/semiconductor/minisite/ssd/download/tools/Samsung_NVMe_Driver_5.1.0.0.zip", "category": "storage", "checksum": "", "notes": "Samsung NVMe Driver"},
    "PCI\\VEN_14E4": {"name": "Broadcom Device (Generic)", "manufacturer": "Broadcom", "latest_version": "10.0.26100.1", "download_url": "", "category": "network", "checksum": "", "notes": "Broadcom Driver"},
    "PCI\\VEN_1B21": {"name": "ASMedia Controller (Generic)", "manufacturer": "ASMedia", "latest_version": "1.16.57.1", "download_url": "https://www.asmedia.com/download/usb3.1_v1.16.57.1.zip", "category": "usb", "checksum": "", "notes": "ASMedia USB Driver"},
    "PCI\\VEN_14C3": {"name": "MediaTek Device (Generic)", "manufacturer": "MediaTek", "latest_version": "10.0.26100.1", "download_url": "", "category": "network", "checksum": "", "notes": "MediaTek Driver"},
    "USB\\VID_046D": {"name": "Logitech Device (Generic)", "manufacturer": "Logitech", "latest_version": "10.0.26100.1", "download_url": "", "category": "input", "checksum": "", "notes": "Logitech Driver"},
    "USB\\VID_045E": {"name": "Microsoft Device (Generic)", "manufacturer": "Microsoft", "latest_version": "10.0.26100.1", "download_url": "", "category": "input", "checksum": "", "notes": "Microsoft Driver"},
    "ACPI\\SYN": {"name": "Synaptics Touchpad (Generic)", "manufacturer": "Synaptics", "latest_version": "19.5.31.1", "download_url": "", "category": "input", "checksum": "", "notes": "Synaptics Touchpad"},
}

count = 0
for hw_id, info in generics.items():
    if hw_id not in db["drivers"]:
        db["drivers"][hw_id] = {**info, "_auto_updated": "2026-07-06"}
        count += 1

db["total_entries"] = len(db["drivers"])
db["updated"] = "2026-07-06T20:00:00"
db_path.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Aggiunti {count} driver generici, totale: {db['total_entries']}")
