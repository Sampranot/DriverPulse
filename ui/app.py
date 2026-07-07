"""
DriverPulse UI — Interfaccia utente
====================================
GUI minimale con tray icon per aggiornamenti silenziosi.
Supporta: scansione, aggiornamento, monitoraggio.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime
from typing import Optional, List

# Core modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.scanner import scan_drivers, get_update_summary
from core.detector import get_detector, DeviceInfo

# Vendor catalog sync (background driver database update)
from core.manufacturer_lookup import get_catalog_sync


class DriverPulseApp:
    """Applicazione GUI principale."""

    def __init__(self, tray_mode: bool = False, silent: bool = False):
        self.tray_mode = tray_mode
        self.silent = silent
        self.root: Optional[tk.Tk] = None
        self._scan_results: List[DeviceInfo] = []
        self._scanning = False
        self._updating = False
        
        # Avvia sincronizzazione catalogo driver in background
        self._catalog_sync = get_catalog_sync(auto_start=True)
        
        if not silent:
            self._build_ui()
    
    def _build_ui(self):
        """Costruisce l'interfaccia."""
        self.root = tk.Tk()
        self.root.title("DriverPulse")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Icona (se disponibile)
        try:
            self.root.iconbitmap(os.path.join(
                os.path.dirname(__file__), '..', 'assets', 'icon.ico'
            ))
        except:
            pass
        
        # Style
        style = ttk.Style()
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        
        # Frame principale
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header, text="DriverPulse", 
                  font=('Segoe UI', 18, 'bold')).pack(side=tk.LEFT)
        
        ttk.Label(header, text="v1.0.0", 
                  font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=(10, 0))
        
        # Barra azioni
        actions = ttk.Frame(main_frame)
        actions.pack(fill=tk.X, pady=(0, 10))
        
        self.scan_btn = ttk.Button(actions, text="Scansiona driver", 
                                    command=self._on_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.update_btn = ttk.Button(actions, text="Aggiorna tutto", 
                                      command=self._on_update_all)
        self.update_btn.pack(side=tk.LEFT, padx=5)
        self.update_btn.config(state=tk.DISABLED)
        
        self.status_label = ttk.Label(actions, text="Pronto", font=('Segoe UI', 9))
        self.status_label.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Separatore
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=5)
        
        # Notebook (tab)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab: Risultati
        self._build_results_tab(notebook)
        
        # Tab: Sistema
        self._build_system_tab(notebook)
        
        # Tab: Info
        self._build_info_tab(notebook)
        
        # Barra stato
        self.bottom_bar = ttk.Label(main_frame, text="Inattivo", 
                                      font=('Segoe UI', 8), foreground='gray')
        self.bottom_bar.pack(fill=tk.X, pady=(5, 0))
        
        # Timer per aggiornamento
        self._update_status()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        if self.tray_mode:
            self.root.withdraw()
        
        self.root.mainloop()
    
    def _build_results_tab(self, notebook: ttk.Notebook):
        """Tab risultati scansione."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Risultati")
        
        # Treeview
        columns = ('device', 'current', 'suggested', 'status')
        self.tree = ttk.Treeview(tab, columns=columns, show='headings', 
                                  height=15)
        
        self.tree.heading('device', text='Dispositivo')
        self.tree.heading('current', text='Versione attuale')
        self.tree.heading('suggested', text='Versione suggerita')
        self.tree.heading('status', text='Stato')
        
        self.tree.column('device', width=300)
        self.tree.column('current', width=150)
        self.tree.column('suggested', width=150)
        self.tree.column('status', width=80)
        
        # Scrollbar
        vscroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tags per colori
        self.tree.tag_configure('outdated', foreground='red')
        self.tree.tag_configure('current', foreground='green')
        self.tree.tag_configure('unknown', foreground='gray')
    
    def _build_system_tab(self, notebook: ttk.Notebook):
        """Tab informazioni di sistema."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Sistema")
        
        text = scrolledtext.ScrolledText(tab, wrap=tk.WORD, font=('Consolas', 9))
        text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        det = get_detector()
        summary = det.get_system_summary()
        
        text.insert(tk.END, "=== INFORMAZIONI SISTEMA ===\n\n")
        text.insert(tk.END, f"OS: {summary['os_info'].get('name', 'N/A')}\n")
        text.insert(tk.END, f"Versione: {summary['os_info'].get('version', 'N/A')}\n")
        text.insert(tk.END, f"Build: {summary['os_info'].get('build', 'N/A')}\n")
        text.insert(tk.END, f"Architettura: {summary['os_info'].get('arch', 'N/A')}\n")
        text.insert(tk.END, f"Computer: {summary['computer_info'].get('manufacturer', 'N/A')} "
                           f"{summary['computer_info'].get('model', 'N/A')}\n")
        text.insert(tk.END, f"RAM: {summary['computer_info'].get('total_ram_gb', 'N/A')} GB\n\n")
        text.insert(tk.END, "=== DISPOSITIVI PER CATEGORIA ===\n\n")
        
        for cat, info in summary.get('by_category', {}).items():
            text.insert(tk.END, f"[{cat.upper()}] {info['count']} dispositivi\n")
            for d in info['devices'][:10]:
                text.insert(tk.END, f"  - {d['name'][:50]:50s} "
                                   f"Driver: {d['driver'][:30]:30s}\n")
            if len(info['devices']) > 10:
                text.insert(tk.END, f"  ... e altri {len(info['devices'])-10}\n")
            text.insert(tk.END, "\n")
        
        text.config(state=tk.DISABLED)
    
    def _build_info_tab(self, notebook: ttk.Notebook):
        """Tab informazioni app."""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Info")
        
        text = scrolledtext.ScrolledText(tab, wrap=tk.WORD, font=('Segoe UI', 10))
        text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        text.insert(tk.END, "DriverPulse v1.0.0\n\n")
        text.insert(tk.END, "Mantiene i driver del PC sempre aggiornati.\n")
        text.insert(tk.END, "Niente popup, niente toolbar, niente pubblicita'.\n\n")
        text.insert(tk.END, "Caratteristiche:\n")
        text.insert(tk.END, "  - Scansione hardware completa\n")
        text.insert(tk.END, "  - Database driver aggiornato\n")
        text.insert(tk.END, "  - Download e installazione automatica\n")
        text.insert(tk.END, "  - Aggiornamento database in tempo reale\n")
        text.insert(tk.END, "  - Funziona in background (system tray)\n\n")
        text.insert(tk.END, "Catalogo driver:\n")
        text.insert(tk.END, "  Sincronizzazione periodica con i database\n")
        text.insert(tk.END, "  dei produttori per avere sempre i driver\n")
        text.insert(tk.END, "  piu' recenti. Connessione solo quando necessario.\n\n")
        text.insert(tk.END, "https://github.com/driverpulse/driverpulse\n")
        
        text.config(state=tk.DISABLED)
    
    def _on_scan(self):
        """Avvia scansione in thread separato."""
        if self._scanning:
            return
        
        self._scanning = True
        self.scan_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Scansione in corso...")
        self.bottom_bar.config(text="Analisi hardware in corso...")
        
        # Pulisci tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        thread = threading.Thread(target=self._do_scan, daemon=True)
        thread.start()
    
    def _do_scan(self):
        """Esegue scansione (nel thread)."""
        try:
            results = scan_drivers()
            self._scan_results = results
            
            # Aggiorna UI nel thread principale
            if self.root:
                self.root.after(0, self._display_results, results)
        except Exception as e:
            if self.root:
                self.root.after(0, self._scan_error, str(e))
    
    def _display_results(self, results: List[DeviceInfo]):
        """Mostra risultati nella treeview."""
        self.tree.delete(*self.tree.get_children())
        
        outdated = 0
        for r in results:
            tag = 'unknown'
            if r.status == 'OUTDATED':
                tag = 'outdated'
                outdated += 1
            elif r.status == 'CURRENT':
                tag = 'current'
            
            self.tree.insert('', tk.END, values=(
                r.device_name[:50],
                r.driver_version[:25] if r.driver_version else 'N/A',
                r.suggested_version[:25] if r.suggested_version else '-',
                r.status
            ), tags=(tag,))
        
        # Statistiche
        total = len(results)
        current = sum(1 for r in results if r.status == 'CURRENT')
        unknown = sum(1 for r in results if r.status == 'UNKNOWN')
        
        summary = f"Totale: {total} | Obsoleti: {outdated} | Correnti: {current} | Sconosciuti: {unknown}"
        self.bottom_bar.config(text=summary)
        
        self.update_btn.config(state=tk.NORMAL if outdated > 0 else tk.DISABLED)
        self.status_label.config(text=f"Scansione completata ({total} dispositivi)")
        self.scan_btn.config(state=tk.NORMAL)
        self._scanning = False
    
    def _scan_error(self, error: str):
        """Mostra errore scansione."""
        messagebox.showerror("Errore scansione", 
                             f"Impossibile completare la scansione:\n{error}")
        self.status_label.config(text="Errore scansione")
        self.scan_btn.config(state=tk.NORMAL)
        self.bottom_bar.config(text="Errore")
        self._scanning = False
    
    def _on_update_all(self):
        """Avvia aggiornamento di tutti i driver obsoleti."""
        if self._updating or not self._scan_results:
            return
        
        outdated = [r for r in self._scan_results if r.status == 'OUTDATED']
        if not outdated:
            return
        
        if not messagebox.askyesno(
            "Conferma",
            f"Aggiornare {len(outdated)} driver obsoleti?\n\n"
            "Il sistema potrebbe riavviarsi dopo l'installazione."
        ):
            return
        
        self._updating = True
        self.update_btn.config(state=tk.DISABLED)
        self.scan_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Aggiornamento in corso...")
        
        thread = threading.Thread(target=self._do_update, args=(outdated,), daemon=True)
        thread.start()
    
    def _do_update(self, outdated: List[DeviceInfo]):
        """Esegue aggiornamento (nel thread)."""
        from core.updater import update_single_device
        
        success = 0
        failed = 0
        
        for dev in outdated:
            try:
                ok, msg = update_single_device(dev)
                if ok:
                    success += 1
                else:
                    failed += 1
                
                if self.root:
                    self.root.after(0, self._update_status_msg, 
                                    f"{'OK' if ok else 'FAIL'}: {dev.device_name[:40]} - {msg[:60]}")
            except Exception as e:
                failed += 1
                if self.root:
                    self.root.after(0, self._update_status_msg,
                                    f"ERR: {dev.device_name[:40]} - {e}")
        
        if self.root:
            self.root.after(0, self._update_done, success, failed)
    
    def _update_status_msg(self, msg: str):
        """Aggiorna messaggio di stato."""
        self.bottom_bar.config(text=msg)
    
    def _update_done(self, success: int, failed: int):
        """Completato aggiornamento."""
        messagebox.showinfo(
            "Aggiornamento completato",
            f"Driver aggiornati: {success}\n"
            f"Falliti: {failed}\n\n"
            "Alcuni aggiornamenti potrebbero richiedere un riavvio."
        )
        self.status_label.config(text="Aggiornamento completato")
        self.update_btn.config(state=tk.NORMAL)
        self.scan_btn.config(state=tk.NORMAL)
        self._updating = False
    
    def _update_status(self):
        """Aggiornamento periodico della status bar."""
        if self._catalog_sync:
            c_status = self._catalog_sync.status()
            self.root.after(5000, self._update_status)
    
    def _on_close(self):
        """Chiusura applicazione."""
        if self._catalog_sync:
            self._catalog_sync.stop()
        self.root.destroy()


def run_app(tray_mode: bool = False, silent: bool = False):
    """Entry point per avviare l'app."""
    app = DriverPulseApp(tray_mode=tray_mode, silent=silent)


if __name__ == "__main__":
    run_app()
