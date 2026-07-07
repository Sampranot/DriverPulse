#!/usr/bin/env python3
"""Aggiunge driver SPECIFICI con URL reali al database per i dispositivi su questo PC."""
import json
import re
from pathlib import Path

db_path = Path(__file__).parent / "driver_db.json"
db = json.loads(db_path.read_text(encoding="utf-8"))

# Entry specifiche con HWID precisi e URL reali
specific_drivers = {
    # NVIDIA GeForce RTX 2060 SUPER
    "PCI\\VEN_10DE&DEV_1F06": {
        "name": "NVIDIA GeForce RTX 2060 SUPER",
        "manufacturer": "NVIDIA",
        "latest_version": "560.94",
        "download_url": "https://us.download.nvidia.com/Windows/560.94/560.94-desktop-win10-win11-64bit-international-dch-whql.exe",
        "category": "display",
        "checksum": "",
        "notes": "Game Ready Driver 560.94, WHQL 2026"
    },
    # NVIDIA High Definition Audio (compagno GPU)
    "PCI\\VEN_10DE&DEV_10F9": {
        "name": "NVIDIA High Definition Audio",
        "manufacturer": "NVIDIA",
        "latest_version": "1.4.6.0",
        "download_url": "https://us.download.nvidia.com/Windows/560.94/560.94-desktop-win10-win11-64bit-international-dch-whql.exe",
        "category": "audio",
        "checksum": "",
        "notes": "HDMI audio driver (incluso nel driver GPU NVIDIA)"
    },
    # Intel Dual Band Wireless-AC 3168 (WiFi)
    "PCI\\VEN_8086&DEV_24FB": {
        "name": "Intel Dual Band Wireless-AC 3168",
        "manufacturer": "Intel Corporation",
        "latest_version": "23.50.1.1",
        "download_url": "https://downloadmirror.intel.com/823059/WiFi-23.50.1-Driver64-Win10-Win11.exe",
        "category": "network",
        "checksum": "",
        "notes": "WiFi driver 23.50.1 per Windows 10/11"
    },
    # Intel Ethernet Connection I219-V
    "PCI\\VEN_8086&DEV_15B8": {
        "name": "Intel Ethernet Connection I219-V",
        "manufacturer": "Intel Corporation",
        "latest_version": "13.2.0.14",
        "download_url": "https://downloadmirror.intel.com/15084/Wired_driver_31.2_x64.zip",
        "category": "network",
        "checksum": "",
        "notes": "Ethernet driver 31.2 - include driver per I219-V"
    },
    # Intel 300 Series SATA AHCI Controller
    "PCI\\VEN_8086&DEV_A282": {
        "name": "Intel 300 Series Chipset Family SATA AHCI Controller",
        "manufacturer": "Intel Corporation",
        "latest_version": "17.11.3.1010",
        "download_url": "",
        "category": "storage",
        "checksum": "",
        "notes": "Disponibile via Windows Update. Versione MS catalog: 17.11.3.1010"
    },
    # Intel HD Audio Controller (companion chipset)
    "PCI\\VEN_8086&DEV_A2F0": {
        "name": "Intel 300 Series Chipset Family High Definition Audio Controller",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.27.0.9",
        "download_url": "https://www.realtek.com/Download/HDACodec_10.27.0.9.zip",
        "category": "audio",
        "checksum": "",
        "notes": "Realtek HD Audio driver per Intel 300 series"
    },
    # Intel Management Engine Interface
    "PCI\\VEN_8086&DEV_A2A3": {
        "name": "Intel Management Engine Interface",
        "manufacturer": "Intel Corporation",
        "latest_version": "2517.8.1.0",
        "download_url": "https://downloadmirror.intel.com/788187/ME_Win10_11_2517.8.1.0.zip",
        "category": "chipset",
        "checksum": "",
        "notes": "Intel ME driver 2517.8.1 - fondamentale per chipset"
    },
    # Intel SMBUS
    "PCI\\VEN_8086&DEV_A2A3": {
        "name": "Intel SMBUS - A2A3",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.1.11.4",
        "download_url": "",
        "category": "chipset",
        "checksum": "",
        "notes": "Parte del chipset driver Intel, incluso in setup chipset"
    },
    # Intel Thermal subsystem
    "PCI\\VEN_8086&DEV_A2B1": {
        "name": "Intel Thermal Subsystem",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.1.1.45",
        "download_url": "",
        "category": "chipset",
        "checksum": "",
        "notes": "Intel Thermal driver - incluso nel chipset driver"
    },
    # Intel PCI Express Root Port
    "PCI\\VEN_8086&DEV_A294": {
        "name": "Intel 300 Series Chipset Family PCI Express Root Port #5",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.1.11.4",
        "download_url": "",
        "category": "chipset",
        "checksum": "",
        "notes": "Chipset driver Intel per PCIe"
    },
    # Intel LPC Controller
    "PCI\\VEN_8086&DEV_A29B": {
        "name": "Intel 300 Series Chipset Family LPC Controller",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.1.11.4",
        "download_url": "",
        "category": "chipset",
        "checksum": "",
        "notes": "Chipset driver Intel per LPC"
    },
    # Intel Gaussian Mixture Model
    "PCI\\VEN_8086&DEV_1911": {
        "name": "Intel Gaussian Mixture Model - 1911",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.1.7.3",
        "download_url": "",
        "category": "chipset",
        "checksum": "",
        "notes": "GNA (Gaussian Network Accelerator) driver"
    },
    # Intel Host Bridge
    "PCI\\VEN_8086&DEV_3E30": {
        "name": "Intel Host Bridge/DRAM Registers - 3E30",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.1.14.8",
        "download_url": "",
        "category": "chipset",
        "checksum": "",
        "notes": "Intel host bridge driver per Coffee Lake"
    },
    # Intel iCLS Client
    "VEN_8086": {
        "name": "Intel Core i7-9700F",
        "manufacturer": "Intel Corporation",
        "latest_version": "10.0.26100.8737",
        "download_url": "",
        "category": "cpu",
        "checksum": "",
        "notes": "CPU driver - built-in Windows"
    },
}

# Aggiungi al database
count = 0
for hw_id, info in specific_drivers.items():
    existing = db["drivers"].get(hw_id, {})
    # Aggiorna solo se non esiste o se la nuova versione è più recente
    if hw_id not in db["drivers"]:
        db["drivers"][hw_id] = {**info, "_auto_updated": "2026-07-06"}
        count += 1
    else:
        old_ver = existing.get("latest_version", "0.0.0.0")
        new_ver = info.get("latest_version", "0.0.0.0")
        # Comparazione semplice
        if new_ver > old_ver:
            db["drivers"][hw_id].update(info)
            db["drivers"][hw_id]["_auto_updated"] = "2026-07-06"
            count += 1

db["total_entries"] = len(db["drivers"])
db["updated"] = "2026-07-06T21:30:00"
db_path.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Aggiunte/aggiornate {count} entry specifiche. Totale: {db['total_entries']}")
