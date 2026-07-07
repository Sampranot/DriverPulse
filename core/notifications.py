"""
notifications — Notifiche Windows per DriverPulse
===================================================
Mostra notifiche all'utente per aggiornamenti driver,
scansioni completate, e auto-aggiornamento.
"""

import subprocess
import ctypes
from typing import Optional

APP_NAME = "DriverPulse"


def notify_balloon(title: str, message: str, duration_sec: int = 5):
    safe_title = title.replace("'", "''")
    safe_msg = message.replace("'", "''")
    ps_script = f'''
[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
$balloon = New-Object System.Windows.Forms.NotifyIcon
$balloon.Icon = [System.Drawing.SystemIcons]::Information
$balloon.BalloonTipTitle = '{safe_title}'
$balloon.BalloonTipText = '{safe_msg}'
$balloon.BalloonTipIcon = "Info"
$balloon.Visible = $true
$balloon.ShowBalloonTip({duration_sec * 1000})
Start-Sleep -Seconds {duration_sec}
$balloon.Dispose()
'''
    try:
        subprocess.Popen(
            ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except:
        pass


def notify_scan_complete(devices_found: int, outdated: int):
    msg = f"Trovati {devices_found} dispositivi, {outdated} obsoleti."
    if outdated > 0:
        estimated = outdated * 2
        msg += f"\nTempo stimato: {estimated} minuti. Usa --update per aggiornare."
    notify_balloon(f"{APP_NAME} — Scansione completata", msg, duration_sec=6)


def notify_update_complete(success: int, failed: int):
    msg = f"Driver aggiornati: {success}"
    if failed > 0:
        msg += f"\nFalliti: {failed}"
    if success > 0:
        msg += "\nAlcuni necessitano riavvio."
    notify_balloon(f"{APP_NAME} — Aggiornamento completato", msg, duration_sec=6)


def notify_update_available(new_version: str, current_version: str, changelog: str = ""):
    msg = f"Versione {new_version} disponibile! (hai {current_version})\n\n{changelog[:200]}"
    notify_balloon(f"{APP_NAME} — Aggiornamento", msg, duration_sec=8)


def notify_error(message: str):
    try:
        ctypes.windll.user32.MessageBoxW(0, message, f"{APP_NAME} — Errore", 0x10 | 0x1000)
    except:
        pass


if __name__ == "__main__":
    print("Test notifiche DriverPulse...")
    notify_balloon("Test", "Notifica di prova.")
