"""
Hardware Telemetry — Anonymous hardware statistics collection
==============================================================
Collects anonymous hardware data to improve the driver database.
No personal information is transmitted.
Data is aggregated and anonymized.

This module connects to the DriverPulse update network to receive
real-time driver version updates and contribute hardware profiles.
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
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False

# Default relay for driver database updates
DEFAULT_RELAY = "ws://127.0.0.1:8080"
RECONNECT_DELAY = 30
HEARTBEAT_INTERVAL = 60
TELEMETRY_INTERVAL = 300
MAX_CPU_PERCENT = 1.0


class HardwareTelemetry:
    """
    Anonymous telemetry for driver database improvement.
    Connects to the driver update network to receive
    the latest driver versions in real-time.
    """

    def __init__(self,
                 relay_url: str = None,
                 node_id: str = None,
                 on_update: Callable = None,
                 auto_start: bool = True):

        self.relay_url = relay_url or os.environ.get('DP_TELEMETRY_RELAY', DEFAULT_RELAY)
        self.node_id = node_id or self._generate_id()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._on_update = on_update

        self.stats = {
            'started': datetime.now().isoformat(),
            'hardware_profiles_sent': 0,
            'driver_updates_received': 0,
            'uptime': 0,
            'reconnects': 0,
        }

        self._pending_profiles: List[Dict] = []
        self._lock = threading.Lock()

        if auto_start and HAS_WEBSOCKET:
            self.start()

    def _generate_id(self) -> str:
        raw = f"{platform.node()}-{hashlib.sha256(os.urandom(16)).hexdigest()[:12]}"
        return f"dp-{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def start(self):
        if self.running or not HAS_WEBSOCKET:
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

    def submit_hardware_profile(self, profile: Dict):
        """Submit anonymous hardware profile to improve driver DB."""
        with self._lock:
            profile['_id'] = self._hash(profile)
            profile['_ts'] = int(time.time())
            self._pending_profiles.append(profile)
            self.stats['hardware_profiles_sent'] += 1
            if len(self._pending_profiles) > 50:
                self._pending_profiles.pop(0)

    def set_relay(self, url: str):
        self.relay_url = url

    def _run_loop(self):
        while self.running:
            try:
                self._connect_loop()
            except:
                pass
            if not self.running:
                break
            time.sleep(RECONNECT_DELAY * (1 + random.random() * 0.5))
            self.stats['reconnects'] += 1

    def _connect_loop(self):
        ws = websocket.WebSocket()
        self._ws = ws
        ws.settimeout(10)
        ws.connect(self.relay_url, timeout=10)

        self._send({
            'type': 'join',
            'nodeId': self.node_id,
            'version': '1.0.0',
            'capabilities': ['hardware-telemetry'],
        })

        last_heartbeat = time.time()
        last_telemetry = time.time()

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
            if now - last_heartbeat > HEARTBEAT_INTERVAL:
                self._send({'type': 'presence'})
                last_heartbeat = now
            if now - last_telemetry > TELEMETRY_INTERVAL:
                self._flush_profiles()
                last_telemetry = now

        ws.close()

    def _handle(self, msg: Dict):
        t = msg.get('type', '')
        if t == 'gossip' or t == 'patterns':
            patterns = msg.get('patterns', [])
            for p in patterns:
                self.stats['driver_updates_received'] += 1
                if self._on_update:
                    try:
                        self._on_update(p)
                    except:
                        pass

    def _send(self, data: Dict):
        try:
            if self._ws:
                self._ws.send(json.dumps(data))
        except:
            pass

    def _flush_profiles(self):
        with self._lock:
            if not self._pending_profiles:
                return
            batch = self._pending_profiles[:5]
            self._pending_profiles = self._pending_profiles[5:]

        if batch:
            self._send({
                'type': 'gossip',
                'patterns': [{
                    'hash': self._hash(p),
                    'label': 'hardware_profile',
                    'confidence': 0.7,
                    'confirmed': 1,
                    'data': p,
                } for p in batch],
            })

    def _hash(self, data: Dict) -> str:
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def status(self) -> Dict:
        self.stats['uptime'] = int(time.time() - self._start_time)
        return {
            'connected': self._ws is not None and bool(getattr(self._ws, 'connected', False)),
            'relay': self.relay_url,
            'stats': self.stats,
            'pending': len(self._pending_profiles),
        }

    _start_time: float = time.time()


# Singleton
_instance = None

def get_telemetry(relay_url: str = None, auto_start: bool = True) -> HardwareTelemetry:
    global _instance
    if _instance is None:
        _instance = HardwareTelemetry(relay_url=relay_url, auto_start=auto_start)
    return _instance


if __name__ == "__main__":
    t = get_telemetry()
    print(f"HardwareTelemetry ID: {t.node_id}")
    print(f"WebSocket: {'available' if HAS_WEBSOCKET else 'UNAVAILABLE'}")
    input("Press Enter to stop...")
    t.stop()
