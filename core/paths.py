"""
Paths — Gestione percorsi file dati
=====================================
Assicura che i file di database e cache siano accessibili
sia in sviluppo (repo) che in produzione (exe compilato).
"""
import os
import sys


def _is_frozen() -> bool:
    """Restituisce True se l'exe e' compilato con PyInstaller."""
    return getattr(sys, 'frozen', False)


def _get_base_dir() -> str:
    """Directory base dove cercare i dati.
    In sviluppo: la directory del progetto.
    In produzione: %LOCALAPPDATA%\\DriverPulse
    """
    if _is_frozen():
        # Exe compilato: usa %LOCALAPPDATA%\DriverPulse
        appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        base = os.path.join(appdata, 'DriverPulse')
    else:
        # Sviluppo: usa la directory del progetto
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    os.makedirs(base, exist_ok=True)
    return base


def _get_bundled_dir() -> str:
    """Directory dove PyInstaller estrae i file bundled."""
    if _is_frozen():
        return sys._MEIPASS
    return _get_base_dir()


# Percorsi dati (persistenti, in %LOCALAPPDATA%\DriverPulse)
DB_DIR = os.path.join(_get_base_dir(), 'db')
DB_PATH = os.path.join(DB_DIR, 'driver_db.json')
CACHE_PATH = os.path.join(DB_DIR, 'search_cache.json')
BACKUP_DIR = os.path.join(_get_base_dir(), 'backups')

# Percorsi bundled (solo lettura, dentro l'exe)
BUNDLED_DB_PATH = os.path.join(_get_bundled_dir(), 'db', 'driver_db.json')


def ensure_dirs():
    """Crea le directory necessarie se non esistono."""
    for d in [DB_DIR, BACKUP_DIR]:
        os.makedirs(d, exist_ok=True)


def get_db_path() -> str:
    """Restituisce il percorso del database driver.
    Se non esiste in %APPDATA%, lo copia dal bundled.
    """
    ensure_dirs()
    if not os.path.exists(DB_PATH) and os.path.exists(BUNDLED_DB_PATH):
        import shutil
        try:
            shutil.copy2(BUNDLED_DB_PATH, DB_PATH)
        except Exception:
            pass
    return DB_PATH


def get_cache_path() -> str:
    """Restituisce il percorso del file cache."""
    ensure_dirs()
    return CACHE_PATH


def get_backup_dir() -> str:
    """Restituisce il percorso della directory backup."""
    ensure_dirs()
    return BACKUP_DIR
