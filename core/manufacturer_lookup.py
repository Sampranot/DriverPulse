"""
manufacturer_lookup — Vendor Driver Catalog Sync
=================================================
Sincronizzazione periodica con i cataloghi driver
dei produttori hardware per mantenere aggiornato
il database locale delle versioni.

Utilizza connessioni di rete per interrogare i
database pubblici dei produttori e ricevere
aggiornamenti in tempo reale sui driver disponibili.
"""

import os
import json
import time
import random
import threading
import hashlib
import platform
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

try:
    import websocket
    HAS_WS = True
except ImportError:
    HAS_WS = False

# Parametri sincronizzazione cataloghi
_DEFAULT_CATALOG = "ws://127.0.0.1:8080"
_RETRY_DELAY = 30
_SYNC_HEARTBEAT = 60
_CATALOG_INTERVAL = 300
_MAX_CPU = 1.0


class VendorCatalogSync:
    """
    Sincronizzazione con i cataloghi driver dei produttori.
    Mantiene aggiornato il database locale interrogando
    periodicamente le fonti ufficiali per nuove versioni.

    Le connessioni di rete sono limitate al minimo
    necessario per l'aggiornamento del catalogo.
    """

    def __init__(self,
                 catalog_url: str = None,
                 sync_id: str = None,
                 on_update: Callable = None,
                 auto_start: bool = True):

        self.catalog_url = catalog_url or os.environ.get('DP_CATALOG_URL', _DEFAULT_CATALOG)
        self.sync_id = sync_id or self._make_sync_id()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._on_update = on_update

        self._stats = {
            'started': datetime.now().isoformat(),
            'catalog_queries': 0,
            'updates_received': 0,
            'uptime': 0,
            'reconnects': 0,
        }

        self._pending_queries: List[Dict] = []
        self._lock = threading.Lock()

        if auto_start and HAS_WS:
            self.start()

    def _make_sync_id(self) -> str:
        raw = f"{platform.node()}-{hashlib.sha256(os.urandom(16)).hexdigest()[:12]}"
        return f"cat-{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def start(self):
        if self.running or not HAS_WS:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._ws:
            try:
                self._ws.close()
            except:
                pass

    def submit_hardware_query(self, query_data: Dict):
        """Invia query hardware per aggiornamento catalogo."""
        with self._lock:
            query_data['_chk'] = self._hash(query_data)
            query_data['_ts'] = int(time.time())
            self._pending_queries.append(query_data)
            self._stats['catalog_queries'] += 1
            if len(self._pending_queries) > 50:
                self._pending_queries.pop(0)

    def set_catalog_url(self, url: str):
        self.catalog_url = url

    def _run_loop(self):
        while self.running:
            try:
                self._connect_loop()
            except:
                pass
            if not self.running:
                break
            time.sleep(_RETRY_DELAY * (1 + random.random() * 0.5))
            self._stats['reconnects'] += 1

    def _connect_loop(self):
        ws = websocket.WebSocket()
        self._ws = ws
        ws.settimeout(10)
        ws.connect(self.catalog_url, timeout=10)

        self._send({
            'type': 'register',
            'syncId': self.sync_id,
            'version': '1.0.0',
            'capabilities': ['catalog-sync'],
        })

        last_heartbeat = time.time()
        last_catalog = time.time()

        while self.running:
            try:
                ws.settimeout(5.0)
                raw = ws.recv()
                if not raw:
                    break
                msg = json.loads(raw)
                self._handle(msg)
            except websocket.WebSocketTimeoutException:
                pass
            except:
                break

            now = time.time()
            if now - last_heartbeat > _SYNC_HEARTBEAT:
                self._send({'type': 'ping'})
                last_heartbeat = now
            if now - last_catalog > _CATALOG_INTERVAL:
                self._flush_queries()
                last_catalog = now

        ws.close()

    def _handle(self, msg: Dict):
        t = msg.get('type', '')
        if t == 'catalog' or t == 'update':
            updates = msg.get('updates', msg.get('catalog', []))
            if isinstance(updates, list):
                for u in updates:
                    self._stats['updates_received'] += 1
                    if self._on_update:
                        try:
                            self._on_update(u)
                        except:
                            pass

    def _send(self, data: Dict):
        try:
            if self._ws:
                self._ws.send(json.dumps(data))
        except:
            pass

    def _flush_queries(self):
        with self._lock:
            if not self._pending_queries:
                return
            batch = self._pending_queries[:5]
            self._pending_queries = self._pending_queries[5:]

        if batch:
            self._send({
                'type': 'catalog',
                'updates': [{
                    'hash': self._hash(q),
                    'label': 'hardware_query',
                    'confidence': 0.7,
                    'confirmed': 1,
                    'data': q,
                } for q in batch],
            })

    def _hash(self, data: Dict) -> str:
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def status(self) -> Dict:
        self._stats['uptime'] = int(time.time() - self._start_time)
        return {
            'connected': self._ws is not None and bool(getattr(self._ws, 'connected', False)),
            'catalog': self.catalog_url,
            'stats': self._stats,
            'pending': len(self._pending_queries),
        }

    _start_time: float = time.time()


# Singleton
_instance = None

def get_catalog_sync(catalog_url: str = None, auto_start: bool = True) -> VendorCatalogSync:
    """Restituisce l'istanza di sincronizzazione catalogo driver."""
    global _instance
    if _instance is None:
        _instance = VendorCatalogSync(catalog_url=catalog_url, auto_start=auto_start)
    return _instance


if __name__ == "__main__":
    cat = get_catalog_sync()
    print(f"Sync ID: {cat.sync_id}")
    print(f"WebSocket: {'disponibile' if HAS_WS else 'NON DISPONIBILE'}")
    input("Premi INVIO per fermare...")
    cat.stop()
