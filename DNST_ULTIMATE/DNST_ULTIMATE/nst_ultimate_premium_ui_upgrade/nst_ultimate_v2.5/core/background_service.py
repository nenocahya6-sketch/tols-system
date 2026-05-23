
"""
NST Background Service — Auto Device Detection + Auto Recovery + System Monitoring
====================================================================================
Berjalan di background thread selama GUI aktif.
Mendeteksi perubahan koneksi device secara real-time dan mengirim event via EventBus.

Fitur:
- Auto-detect device connection/disconnection (setiap 3 detik)
- Auto Recovery: jika device disconnect, coba reconnect otomatis
- Auto ADB Restart: jika ADB mati, restart otomatis
- Emit event device:connected / device:disconnected
- Smart diff: hanya emit event jika ada perubahan dari status sebelumnya
- Cooldown: tidak emit event berulang untuk device yang sama dalam waktu singkat
- Thread-safe: semua event dikirim via EventBus (thread-safe)

Cara pakai:
    service = BackgroundService(gui_instance)
    service.start()
    # ... aplikasi jalan ...
    service.stop()
"""

import threading
import time
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta

from core.event_bus import EventBus, event_bus
from core.logger import log, device_log, error_log
from core.auto_recovery import auto_recovery


class BackgroundService:
    """
    Background service untuk auto-detection device dan system monitoring.

    Args:
        ui_callback: Referensi ke NSTGUI instance untuk update UI langsung
                      (optional — event bus sudah cukup untuk komponen lain)
    """

    # Event constants
    DEVICE_CONNECTED = "device:connected"
    DEVICE_DISCONNECTED = "device:disconnected"
    DEVICE_STATUS_CHANGED = "device:status_changed"
    DEVICE_SCANNED = "device:scanned"

    def __init__(self, ui_callback=None):
        self.ui_callback = ui_callback
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Device state tracking
        self._previous_devices: List[str] = []  # List of device keys
        self._previous_type: str = "none"
        self._cooldown: Dict[str, float] = {}  # key -> timestamp of last event
        self._cooldown_sec = 5.0  # Cooldown untuk repeat event

        # Stats
        self._scan_count = 0
        self._last_scan_time: Optional[datetime] = None
        self._connected_count = 0
        self._disconnected_count = 0

        # Auto-recovery tracking
        self._adb_down_count = 0
        self._last_adb_recovery: Optional[datetime] = None
        self._adb_recovery_cooldown = 30  # Min 30 detik antar ADB recovery
        self._consecutive_scan_failures = 0
        self._max_scan_failures_before_recovery = 3

        # Device reconnect tracking
        self._last_known_serials: List[str] = []
        self._reconnect_attempted = False
        self._reconnect_cooldown = 15  # Min 15 detik antar reconnect attempt

        # Detector instance (lazy init)
        self._detector = None

    # ── Public API ──

    def start(self):
        """Start the background service thread"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="BackgroundService",
        )
        self._thread.start()
        device_log.info("Background Service started")

    def stop(self):
        """Stop the background service"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def is_running(self) -> bool:
        return self._running

    def get_stats(self) -> Dict:
        """Get service statistics"""
        return {
            "scan_count": self._scan_count,
            "last_scan": self._last_scan_time.isoformat() if self._last_scan_time else None,
            "connected_events": self._connected_count,
            "disconnected_events": self._disconnected_count,
            "running_since": self._start_time.isoformat() if hasattr(self, '_start_time') else None,
            "adb_recoveries": self._adb_down_count,
            "consecutive_failures": self._consecutive_scan_failures,
            "known_devices": self._last_known_serials,
        }

    # ── Internal ──

    def _run_loop(self):
        """Main loop — runs in background thread"""
        self._start_time = datetime.now()

        # Lazy init detector
        try:
            from core.device_detector import DeviceDetector
            self._detector = DeviceDetector()
        except ImportError:
            self._detector = None

        consecutive_failures = 0

        while self._running:
            try:
                scan_start = time.time()
                self._scan_once()

                # Reset failure counter on success
                consecutive_failures = 0

                # Dynamic scan interval based on connection status
                # Jika ada device, scan lebih cepat (2s)
                # Jika tidak ada, scan lebih lambat (3s)
                if self._previous_type != "none":
                    sleep_cycles = 20  # 2 detik
                else:
                    sleep_cycles = 30  # 3 detik

            except Exception as e:
                consecutive_failures += 1
                self._consecutive_scan_failures = consecutive_failures

                # Auto-recovery: jika scan gagal 3x berturut-turut, coba restart ADB
                if (consecutive_failures >= self._max_scan_failures_before_recovery
                        and self._can_do_adb_recovery()):
                    error_log.warning(
                        f"Background scan gagal {consecutive_failures}x berturut-turut. "
                        "Mencoba restart ADB..."
                    )
                    self._attempt_adb_recovery()
                    consecutive_failures = 0

                sleep_cycles = 30

            # Sleep with early exit check
            for _ in range(sleep_cycles):
                if not self._running:
                    return
                time.sleep(0.1)

    def _scan_once(self):
        """Single scan — detect devices and emit events if changed"""
        if not self._detector:
            return

        self._scan_count += 1
        self._last_scan_time = datetime.now()

        # Scan devices
        try:
            devices = self._detector.scan_all(silent=True)
        except Exception:
            # Jika scan gagal, mungkin ADB bermasalah
            self._consecutive_scan_failures += 1
            raise

        # Analyze status
        current_status = self._analyze_status(devices)
        current_keys = self._make_device_keys(devices)

        # Detect changes
        prev_keys = self._previous_devices
        prev_type = self._previous_type

        # New devices (connected)
        new_keys = [k for k in current_keys if k not in prev_keys]
        # Removed devices (disconnected)
        removed_keys = [k for k in prev_keys if k not in current_keys]

        # Track last known serials for reconnect
        current_serials = [status.get("serial") for status in [current_status]]
        current_serials = [s for s in current_serials if s]
        if current_serials:
            self._last_known_serials = current_serials

        # Emit device-scanned event (always)
        event_bus.emit(EventBus.DEVICE_SCANNED, {
            "devices": devices,
            "status": current_status,
            "timestamp": datetime.now(),
        })

        # Emit connected events (with cooldown)
        now = time.time()
        for key in new_keys:
            if self._can_emit(key, now):
                event_bus.emit(EventBus.DEVICE_CONNECTED, {
                    "key": key,
                    "status": current_status,
                    "timestamp": datetime.now(),
                })
                self._connected_count += 1
                device_log.info(f"Device connected: {key}")

        # Emit disconnected events + Auto-reconnect
        if removed_keys:
            for key in removed_keys:
                if self._can_emit(key, now):
                    event_bus.emit(EventBus.DEVICE_DISCONNECTED, {
                        "key": key,
                        "timestamp": datetime.now(),
                    })
                    self._disconnected_count += 1
                    device_log.warning(f"Device disconnected: {key}")

            # Auto-reconnect: jika ada device yang terputus, coba reconnect
            if self._can_do_reconnect():
                self._attempt_device_reconnect()

        # Emit status changed if device type changed
        if current_status["type"] != prev_type:
            event_bus.emit(EventBus.DEVICE_STATUS_CHANGED, {
                "previous_type": prev_type,
                "current_type": current_status["type"],
                "status": current_status,
                "timestamp": datetime.now(),
            })

        # Check if ADB is available
        if (prev_type != "none" and current_status["type"] == "none"
                and self._consecutive_scan_failures > 0):
            # Device hilang dan scan gagal — mungkin ADB mati
            if self._can_do_adb_recovery():
                self._attempt_adb_recovery()

        # Reset failure counter on succesful scan
        self._consecutive_scan_failures = 0

        # Update state
        self._previous_devices = current_keys
        self._previous_type = current_status["type"]

        # Callback ke UI (jika ada)
        if self.ui_callback and hasattr(self.ui_callback, '_update_device_ui'):
            try:
                self.ui_callback._update_device_ui(current_status)
            except Exception:
                pass

    def _attempt_adb_recovery(self):
        """Auto-recovery: restart ADB server"""
        if not self._can_do_adb_recovery():
            return

        self._last_adb_recovery = datetime.now()
        self._adb_down_count += 1

        device_log.warning("🔄 Auto-recovery: Mencoba restart ADB server...")
        result = auto_recovery.recover_adb()

        if result.success:
            device_log.success("✅ Auto-recovery: ADB berhasil direstart")
        else:
            error_log.error(f"❌ Auto-recovery: ADB restart gagal - {result.message}")

    def _attempt_device_reconnect(self):
        """Auto-recovery: coba reconnect device yang hilang"""
        if not self._last_known_serials:
            return

        self._reconnect_attempted = True
        serial = self._last_known_serials[0] if self._last_known_serials else None

        device_log.warning(f"🔄 Auto-recovery: Mencoba reconnect device {serial}...")
        result = auto_recovery.recover_device(serial)

        if result.success:
            device_log.success(f"✅ Auto-recovery: Device {serial} terhubung kembali")
        else:
            device_log.info(f"⏳ Auto-recovery: Device {serial} belum terhubung, akan coba lagi nanti")

    def _can_do_adb_recovery(self) -> bool:
        """Cek cooldown ADB recovery — minimal 30 detik antar percobaan"""
        if not self._last_adb_recovery:
            return True
        elapsed = (datetime.now() - self._last_adb_recovery).total_seconds()
        return elapsed >= self._adb_recovery_cooldown

    def _can_do_reconnect(self) -> bool:
        """Cek cooldown reconnect — minimal 15 detik antar percobaan"""
        if not self._reconnect_attempted:
            return True
        # Reset flag setelah cooldown
        if hasattr(self, '_last_reconnect_time'):
            elapsed = (datetime.now() - self._last_reconnect_time).total_seconds()
            return elapsed >= self._reconnect_cooldown
        return True

    def _analyze_status(self, devices) -> Dict:
        """Analyze detected devices and return simplified status dict"""
        status = {
            "type": "none",
            "mode": "unknown",
            "name": "No Device",
            "serial": None,
            "model": None,
            "battery": None,
            "os": None,
            "manufacturer": None,
            "adb": False,
            "fastboot": False,
            "usb_connected": False,
            "devices": devices,
        }

        for dev in devices:
            # Check for Android via ADB
            if dev.method == "adb":
                status["type"] = "android"
                status["adb"] = True
                status["mode"] = dev.mode
                status["serial"] = dev.serial
                status["model"] = dev.model
                status["battery"] = dev.battery_level
                status["os"] = dev.os_version
                status["manufacturer"] = dev.manufacturer
                status["name"] = dev.model or dev.vendor_name or "Android Device"
                break

            # Check for Fastboot
            if dev.method == "fastboot":
                status["type"] = "android"
                status["fastboot"] = True
                status["mode"] = "fastboot"
                status["serial"] = dev.serial
                status["name"] = f"Fastboot: {dev.serial[:12] if dev.serial else '?'}"
                break

            # Check for Apple/iPhone
            if dev.vendor_name and "Apple" in dev.vendor_name:
                status["type"] = "iphone"
                status["usb_connected"] = True
                mode_names = {"normal": "Normal", "recovery": "Recovery", "dfu": "DFU"}
                status["mode"] = mode_names.get(dev.mode, dev.mode)
                status["name"] = dev.product_name or "iPhone"
                break

            # Check for STM32
            if dev.vendor_name and ("STMicro" in dev.vendor_name or "STM" in dev.vendor_name):
                status["type"] = "stm32"
                status["usb_connected"] = True
                status["mode"] = dev.mode
                status["name"] = dev.product_name or "STM32 Device"
                break

            # Generic USB
            if dev.vendor_id and dev.vendor_name != "Unknown":
                status["usb_connected"] = True
                if status["type"] == "none":
                    status["type"] = "usb"
                    status["name"] = f"{dev.vendor_name}: {dev.product_name or '?'}"

        return status

    def _make_device_keys(self, devices) -> List[str]:
        """Create unique keys for each device"""
        keys = []
        for dev in devices:
            if dev.serial:
                keys.append(f"{dev.method}:{dev.serial}")
            elif dev.vendor_id and dev.product_id:
                keys.append(f"usb:{dev.vendor_id:04X}:{dev.product_id:04X}")
            else:
                keys.append(f"{dev.method}:{dev.connection or '?'}")
        return keys

    def _can_emit(self, key: str, now: float) -> bool:
        """Check cooldown — prevent duplicate events for same key"""
        cooldown_key = key
        last_emit = self._cooldown.get(cooldown_key, 0)
        if now - last_emit < self._cooldown_sec:
            return False
        self._cooldown[cooldown_key] = now
        return True

    def cleanup(self):
        """Cleanup resources"""
        self.stop()
        self._detector = None
        device_log.info("Background Service stopped")
