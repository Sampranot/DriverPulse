"""
persistence — Auto-avvio e persistenza DriverPulse
====================================================
Crea Scheduled Task per avvio automatico all'accesso
e scansione periodica dei driver.
"""

import os
import sys
import subprocess
from typing import Tuple

APP_NAME = "DriverPulse"
TASK_NAME = f"{APP_NAME}"


def get_exe_path() -> str:
    if getattr(sys, 'frozen', False):
        return sys.executable
    main_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'main.py')
    if os.path.exists(main_py):
        return f'python "{main_py}"'
    return sys.executable


def install_autostart(args: str = "--tray") -> Tuple[bool, str]:
    exe = get_exe_path()
    cmd = (
        f'schtasks /create /tn "{TASK_NAME}" /tr "{exe} {args}" '
        f'/sc onlogon /rl highest /f /it'
    )
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return True, f"Avvio automatico installato. {APP_NAME} partira' all'accesso."
        else:
            return False, f"Errore: {result.stderr.strip()}"
    except Exception as e:
        return False, str(e)


def install_weekly_scan(args: str = "--scan --silent") -> Tuple[bool, str]:
    """Scansione driver una volta a settimana."""
    exe = get_exe_path()
    task_name = f"{TASK_NAME}_WeeklyScan"
    cmd = (
        f'schtasks /create /tn "{task_name}" /tr "{exe} {args}" '
        f'/sc weekly /d sun /st 10:00 /rl lowest /f /it'
    )
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return True, f"Scansione automatica settimanale attivata (ogni domenica alle 10:00)."
        else:
            return False, f"Errore: {result.stderr.strip()}"
    except Exception as e:
        return False, str(e)


def uninstall_autostart() -> Tuple[bool, str]:
    tasks = [TASK_NAME, f"{TASK_NAME}_WeeklyScan"]
    results = []
    for task in tasks:
        try:
            result = subprocess.run(
                f'schtasks /delete /tn "{task}" /f',
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                results.append(f"{task}: rimosso")
        except:
            results.append(f"{task}: errore rimozione")
    if results:
        return True, " | ".join(results)
    return False, "Nessun task trovato."


def is_installed() -> Tuple[bool, bool]:
    autostart = False
    weekly = False
    try:
        result = subprocess.run(
            f'schtasks /query /tn "{TASK_NAME}"',
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        autostart = result.returncode == 0
    except:
        pass
    try:
        result = subprocess.run(
            f'schtasks /query /tn "{TASK_NAME}_WeeklyScan"',
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        weekly = result.returncode == 0
    except:
        pass
    return autostart, weekly


def status() -> str:
    auto, weekly = is_installed()
    parts = []
    parts.append(f"Avvio automatico: {'✅ ATTIVO' if auto else '❌ NON ATTIVO'}")
    parts.append(f"Scansione settimanale: {'✅ ATTIVA' if weekly else '❌ NON ATTIVA'}")
    return " | ".join(parts)


if __name__ == "__main__":
    print(f"=== {APP_NAME} — Persistenza ===")
    print(status())
    print()
    cmd = input("Cosa fare? [install/uninstall/status]: ").strip().lower()
    if cmd == 'install':
        ok, msg = install_autostart()
        print(msg)
        ok2, msg2 = install_weekly_scan()
        print(msg2)
    elif cmd == 'uninstall':
        ok, msg = uninstall_autostart()
        print(msg)
    else:
        print(status())
