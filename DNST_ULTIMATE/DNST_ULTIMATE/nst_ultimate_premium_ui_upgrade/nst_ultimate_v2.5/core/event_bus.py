
"""
NST Event Bus — Simple pub/sub event system
=============================================
Komunikasi antar komponen tanpa dependensi langsung.
Thread-safe, singleton pattern.

Contoh:
    bus = EventBus()
    bus.on("device:connected", my_callback)
    bus.emit("device:connected", device_info)
"""
import threading
from typing import Callable, Dict, List, Any, Optional


class EventBus:
    """Singleton event bus — publish/subscribe pattern"""

    _instance: Optional["EventBus"] = None
    _singleton_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._listeners: Dict[str, List[Callable]] = {}
            self._lock = threading.Lock()

    # ── Public API ──

    def on(self, event: str, callback: Callable):
        """Daftarkan listener untuk suatu event"""
        with self._lock:
            if event not in self._listeners:
                self._listeners[event] = []
            if callback not in self._listeners[event]:
                self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable):
        """Hapus listener dari event"""
        with self._lock:
            if event in self._listeners:
                self._listeners[event] = [
                    cb for cb in self._listeners[event] if cb != callback
                ]

    def emit(self, event: str, *args, **kwargs):
        """Kirim event — panggil semua listener yang terdaftar"""
        listeners = []
        with self._lock:
            listeners = list(self._listeners.get(event, []))

        for callback in listeners:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"[EventBus] Error in '{event}' handler: {e}")

    def once(self, event: str, callback: Callable):
        """Daftarkan listener yang hanya dipanggil sekali"""
        def wrapper(*args, **kwargs):
            self.off(event, wrapper)
            callback(*args, **kwargs)
        self.on(event, wrapper)

    def has_listeners(self, event: str) -> bool:
        """Cek apakah suatu event memiliki listener"""
        with self._lock:
            return bool(self._listeners.get(event))

    def listener_count(self, event: str) -> int:
        """Hitung jumlah listener untuk suatu event"""
        with self._lock:
            return len(self._listeners.get(event, []))

    def clear(self):
        """Hapus semua listener"""
        with self._lock:
            self._listeners.clear()

    def get_events(self) -> List[str]:
        """Dapatkan daftar semua event yang memiliki listener"""
        with self._lock:
            return list(self._listeners.keys())

    # ── Events yang digunakan sistem ──

    # Device events
    DEVICE_CONNECTED = "device:connected"
    DEVICE_DISCONNECTED = "device:disconnected"
    DEVICE_STATUS_CHANGED = "device:status_changed"
    DEVICE_SCANNED = "device:scanned"

    # Task events
    TASK_CREATED = "task:created"
    TASK_STARTED = "task:started"
    TASK_PROGRESS = "task:progress"
    TASK_COMPLETED = "task:completed"
    TASK_FAILED = "task:failed"
    TASK_CANCELLED = "task:cancelled"
    TASK_UPDATED = "task:updated"

    # UI events
    UI_PAGE_CHANGED = "ui:page_changed"
    UI_NOTIFICATION = "ui:notification"
    UI_STATUS_MESSAGE = "ui:status_message"
    UI_CONSOLE_LOG = "ui:console_log"

    # System events
    SYSTEM_SHUTDOWN = "system:shutdown"
    SYSTEM_READY = "system:ready"
    SYSTEM_ERROR = "system:error"


# ── Global instance ──
event_bus = EventBus()
