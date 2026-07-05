#!/usr/bin/env python3
"""
DriverPulse — Driver Updater
=============================
Mantiene i driver del PC sempre aggiornati in modo silenzioso.
Niente popup, niente toolbar, niente pubblicita'.

Utilizzo:
    python main.py              Avvia la GUI
    python main.py --scan       Scansione rapida da terminale
    python main.py --update     Aggiorna tutto automaticamente
    python main.py --tray       Avvia in system tray (minimized)
"""

import sys
import os
import platform
import argparse

VERSION = "1.0.0"
APP_NAME = "DriverPulse"

# Windows only
if platform.system() != "Windows":
    print("DriverPulse richiede Windows 10/11.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="DriverPulse - Driver Updater")
    parser.add_argument("--scan", action="store_true", help="Scansiona driver obsoleti")
    parser.add_argument("--update", action="store_true", help="Aggiorna tutti i driver")
    parser.add_argument("--tray", action="store_true", help="Avvia in system tray")
    parser.add_argument("--silent", action="store_true", help="Esecuzione silenziosa (nessuna GUI)")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} v{VERSION}")
    args = parser.parse_args()

    if args.scan:
        from core.scanner import scan_drivers
        results = scan_drivers()
        print(f"\nDriverPulse — Scan risultati:")
        print(f"{'Dispositivo':40s} {'Driver attuale':30s} {'Stato':10s}")
        print("-" * 80)
        for r in results:
            dv = r.device_name[:38] if r.device_name else 'N/A'
            cv = r.driver_version[:28] if r.driver_version else 'N/A'
            st = r.status or 'UNKNOWN'
            print(f"{dv:40s} {cv:30s} {st:10s}")
        print(f"\nTrovati: {len(results)} dispositivi")
        outdated = sum(1 for r in results if r.status == 'OUTDATED')
        print(f"Obsoleti: {outdated}")
        return

    if args.update:
        from core.updater import update_all
        success, failed = update_all()
        print(f"Aggiornati: {success}, Falliti: {failed}")
        return

    # Avvia GUI (o tray)
    try:
        from ui.app import run_app
        run_app(tray_mode=args.tray, silent=args.silent)
    except ImportError as e:
        print(f"Errore: {e}")
        print("Esegui: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Errore: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
