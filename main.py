#!/usr/bin/env python3
"""
DriverPulse — Driver Updater
=============================
Mantiene i driver del PC sempre aggiornati in modo silenzioso.
Niente popup, niente toolbar, niente pubblicita'.

Utilizzo:
    DriverPulse.exe                  Avvia la GUI
    DriverPulse.exe --scan           Scansione rapida da terminale
    DriverPulse.exe --update         Aggiorna tutto automaticamente
    DriverPulse.exe --check-update   Controlla aggiornamenti del programma
    DriverPulse.exe --install        Installa avvio automatico + scansione settimanale
    DriverPulse.exe --uninstall      Rimuovi avvio automatico
    DriverPulse.exe --status         Mostra stato sistema e persistenza
"""

import sys
import os
import platform
import argparse
import ctypes
from datetime import datetime

VERSION = "1.0.0"
APP_NAME = "DriverPulse"

if platform.system() != "Windows":
    print("DriverPulse richiede Windows 10/11.")
    sys.exit(1)


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate_now():
    if is_admin():
        return
    print("=" * 60)
    print("  SERVIZIO AMMINISTRATORE RICHIESTO")
    print("=" * 60)
    print("  Per aggiornare i driver devi eseguire come")
    print("  amministratore.")
    print()
    print("  1. Chiudi questa finestra")
    print("  2. Tasto DESTRO su DriverPulse.exe")
    print("  3. Scegli 'Esegui come amministratore'")
    print("  4. Oppure da terminale gia' admin:")
    print(f"     {os.path.basename(sys.argv[0])} --update")
    print("=" * 60)
    sys.exit(0)


def print_banner():
    print(f"""
{'='*55}
  {APP_NAME} v{VERSION} — Driver sempre aggiornati
{'='*55}
""")


def cmd_scan(silent: bool = False):
    """Scansione driver con report."""
    from core.scanner import scan_drivers
    from core.notifications import notify_scan_complete

    if not silent:
        print_banner()
        print(" Scansione hardware in corso...\n")
        print(f"{'Dispositivo':40s} {'Driver attuale':30s} {'Stato':10s}")
        print("-" * 80)

    start = datetime.now()
    results = scan_drivers()
    elapsed = (datetime.now() - start).total_seconds()

    outdated = 0
    current = 0
    unknown = 0

    for r in results:
        dv = r.device_name[:38] if r.device_name else 'N/A'
        cv = r.driver_version[:28] if r.driver_version else 'N/A'
        st = r.status or 'UNKNOWN'
        if not silent:
            print(f"{dv:40s} {cv:30s} {st:10s}")
        if r.status == 'OUTDATED':
            outdated += 1
        elif r.status == 'CURRENT':
            current += 1
        else:
            unknown += 1

    if not silent:
        print("-" * 80)
        print(f"\n Trovati: {len(results)} dispositivi")
        print(f" Obsoleti: {outdated}")
        print(f" Aggiornati: {current}")
        print(f" Sconosciuti: {unknown}")
        print(f" Tempo: {elapsed:.1f}s")
        if outdated > 0:
            estimated = outdated * 2
            print(f"\n ⏱ Tempo stimato aggiornamento: ~{estimated} minuti")
            print(f" Per aggiornare: {APP_NAME}.exe --update (come amministratore)")
        print()

    notify_scan_complete(len(results), outdated)


def cmd_update(silent: bool = False):
    """Aggiorna tutti i driver obsoleti."""
    if not is_admin():
        if not silent:
            print("❌ Servono privilegi di amministratore per aggiornare i driver.")
            print("   Esegui come amministratore (tasto destro -> Esegui come amministratore).")
        sys.exit(1)

    from core.updater import update_all
    from core.notifications import notify_update_complete

    if not silent:
        print_banner()
        print(" Aggiornamento driver in corso...\n")

    start = datetime.now()
    success, failed = update_all()
    elapsed = (datetime.now() - start).total_seconds()

    if not silent:
        print(f"\n{'='*55}")
        print(f" REPORT AGGIORNAMENTO")
        print(f"{'='*55}")
        print(f" ✅ Aggiornati: {success}")
        if failed > 0:
            print(f" ❌ Falliti: {failed}")
        print(f" ⏱ Tempo: {elapsed:.1f}s")
        if success > 0:
            print(f"\n Alcuni aggiornamenti potrebbero richiedere un riavvio.")
        print(f"{'='*55}")
        print("\nPremi INVIO per chiudere...")
        input()

    notify_update_complete(success, failed)


def cmd_check_update():
    """Controlla aggiornamenti del programma stesso."""
    from core.self_update import check_for_updates, download_update
    from core.notifications import notify_update_available

    print_banner()
    print(" Controllo aggiornamenti...\n")

    ok, msg, data = check_for_updates()
    print(f" {msg}")

    if ok and data:
        print("\n Download in corso...")
        ok2, path = download_update(data)
        if ok2:
            print(f" ✅ Scaricato ({os.path.getsize(path) // 1024} KB)")
            from core.self_update import apply_update
            ok3, msg3 = apply_update(path)
            print(f" {msg3}")
            notify_update_available(
                data.get('tag_name', '?').lstrip('v'),
                VERSION,
                data.get('body', '')
            )
        else:
            print(f" ❌ {path}")
    elif not ok:
        print("\n Riprova piu' tardi.")
    else:
        print(" Sei aggiornato.")


def cmd_install():
    """Installa persistenza."""
    from core.persistence import install_autostart, install_weekly_scan
    from core.notifications import notify_balloon

    print_banner()
    print(" Installazione persistenza...\n")

    ok1, msg1 = install_autostart()
    print(f" {'✅' if ok1 else '❌'} Avvio automatico: {msg1}")

    ok2, msg2 = install_weekly_scan()
    print(f" {'✅' if ok2 else '❌'} Scansione settimanale: {msg2}")

    if ok1 or ok2:
        print(f"\n ✅ {APP_NAME} configurato per manutenzione automatica.")
        notify_balloon(f"{APP_NAME} — Installato",
                       f"Avvio automatico + scansione settimanale attivi.",
                       duration_sec=4)


def cmd_uninstall():
    """Rimuovi persistenza."""
    from core.persistence import uninstall_autostart

    print_banner()
    print(" Rimozione persistenza...\n")
    ok, msg = uninstall_autostart()
    print(f" {msg}")
    print(f"\n Persistenza rimossa.")


def cmd_status():
    """Mostra stato."""
    from core.persistence import status as persistence_status
    from core.detector import get_detector

    print_banner()
    det = get_detector()
    summary = det.get_system_summary()

    print(" SISTEMA:")
    os_info = summary.get('os_info', {})
    print(f"  OS: {os_info.get('name', 'N/A')} {os_info.get('version', 'N/A')}")
    comp = summary.get('computer_info', {})
    print(f"  PC: {comp.get('manufacturer', 'N/A')} {comp.get('model', 'N/A')}")
    print(f"  RAM: {comp.get('total_ram_gb', 'N/A')} GB")
    print(f"  Versione {APP_NAME}: {VERSION}")
    print()

    print(" PERSISTENZA:")
    print(f"  {persistence_status()}")
    print()
    print(f" DriverPulse.exe --install    Installa avvio automatico")
    print(f" DriverPulse.exe --check-update  Controlla aggiornamenti")


def cmd_update_done():
    """Chiamato dopo aggiornamento automatico."""
    from core.notifications import notify_balloon
    notify_balloon(f"{APP_NAME} — Aggiornato",
                   f"{APP_NAME} e' stato aggiornato con successo!", duration_sec=4)
    print(f"{APP_NAME} aggiornato con successo.")


def main():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - Driver Updater",
        epilog=f"Esempio: {APP_NAME}.exe --scan  (scansiona e mostra report)"
    )
    parser.add_argument("--scan", action="store_true", help="Scansiona driver obsoleti con report")
    parser.add_argument("--update", action="store_true", help="Aggiorna tutti i driver obsoleti")
    parser.add_argument("--tray", action="store_true", help="Avvia in system tray")
    parser.add_argument("--noelevate", action="store_true", help="Non auto-elevare (usa admin manuale)")
    parser.add_argument("--silent", action="store_true", help="Esecuzione silenziosa (solo notifiche)")
    parser.add_argument("--check-update", action="store_true", help="Controlla e installa aggiornamenti")
    parser.add_argument("--install", action="store_true", help="Installa avvio automatico + scansione settimanale")
    parser.add_argument("--uninstall", action="store_true", help="Rimuovi avvio automatico")
    parser.add_argument("--status", action="store_true", help="Mostra stato sistema e persistenza")
    parser.add_argument("--update-done", action="store_true", help="[Interno] Notifica aggiornamento completato")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} v{VERSION}")
    args = parser.parse_args()

    # Comandi senza auto-elevazione
    if args.update_done:
        cmd_update_done()
        return

    if args.status:
        cmd_status()
        return

    if args.check_update:
        cmd_check_update()
        return

    if args.install:
        cmd_install()
        return

    if args.uninstall:
        cmd_uninstall()
        return

    # Auto-elevazione per azioni che richiedono admin
    if not args.noelevate:
        needs_admin = (args.update or args.tray)
        if needs_admin and not is_admin():
            elevate_now()

    if args.scan:
        cmd_scan(silent=args.silent)
        return

    if args.update:
        cmd_update(silent=args.silent)
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
