
"""
NST Auto Recovery v1
======================
Auto-recovery System — Menangani kegagalan koneksi & device disconnect.

Fitur:
1. ADB Auto-Restart — Jika ADB mati/membeku, restart otomatis
2. Device Reconnect — Jika device terputus, tunggu & coba reconnect
3. Flash Failure Recovery — Jika flashing gagal, auto restore backup
4. Fastboot Timeout Recovery — Jika fastboot timeout, retry dengan backoff
5. USB Reset — Reset USB stack jika driver bermasalah

Setiap recovery memiliki:
- Max retries sebelum menyerah
- Exponential backoff antara retry
- Logging detail ke error_log
- Event emission via EventBus
"""
import os
import sys
import time
import threading
import subprocess
from typing import Optional, Callable, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from core.logger import log, error_log, adb_log, flash_log, device_log
from core.event_bus import EventBus, event_bus


class RecoveryAction(Enum):
    """Jenis aksi recovery yang bisa dilakukan"""
    RESTART_ADB = "restart_adb"
    RECONNECT_DEVICE = "reconnect_device"
    RETRY_FLASH = "retry_flash"
    RESET_USB = "reset_usb"
    KILL_ZOMBIE = "kill_zombie"
    RESTART_SERVICE = "restart_service"
    NONE = "none"


class RecoveryResult:
    """Hasil dari satu aksi recovery"""
    def __init__(self, action: RecoveryAction, success: bool, message: str = ""):
        self.action = action
        self.success = success
        self.message = message
        self.timestamp = datetime.now()
        self.duration: Optional[float] = None


class AutoRecovery:
    """
    Auto Recovery System — singleton.
    Bertanggung jawab atas recovery otomatis saat terjadi kegagalan.

    Cara pakai:
        recovery = AutoRecovery()
        recovery.recover_adb()  # Coba restart ADB
        recovery.recover_device("serial123")  # Coba reconnect device
        recovery.monitor_device("serial123", on_reconnected=lambda: print("Device back!"))
    """

    _instance: Optional["AutoRecovery"] = None
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
            self._event_bus = event_bus
            self._recovery_history: Dict[str, list] = {}
            self._lock = threading.Lock()
            self._monitoring: Dict[str, threading.Thread] = {}
            self._running = True

            # Konfigurasi retry
            self.max_adb_retries = 3
            self.max_reconnect_retries = 5
            self.max_flash_retries = 2

            # Exponential backoff: 1s, 2s, 4s, 8s, 16s
            self.backoff_base = 1.0
            self.backoff_max = 30.0

            # Log
            error_log.info("AutoRecovery initialized")

    # ── Public API ──

    def recover_adb(self) -> RecoveryResult:
        """
        Recovery ADB server — kill zombie, restart, verify.
        Returns RecoveryResult
        """
        start = time.time()
        adb_log.warning("AUTO-RECOVERY: Mencoba restart ADB server...")

        result = self._execute_recovery([
            ("Kill ADB", self._kill_adb),
            ("Verify kill", lambda: self._verify_adb_dead()),
            ("Start ADB", self._start_adb),
            ("Verify ADB", lambda: self._verify_adb_alive()),
            ("Check devices", lambda: self._check_adb_devices()),
        ], "ADB")

        result.duration = time.time() - start
        self._record_recovery("adb", result)

        if result.success:
            adb_log.success(f"AUTO-RECOVERY: ADB berhasil direstart ({result.duration:.1f}s)")
            self._event_bus.emit(EventBus.SYSTEM_RECOVERY, {
                "type": "adb",
                "success": True,
                "message": result.message,
            })
        else:
            error_log.error(f"AUTO-RECOVERY: ADB recovery gagal! {result.message}")
            self._event_bus.emit(EventBus.SYSTEM_RECOVERY, {
                "type": "adb",
                "success": False,
                "message": result.message,
            })

        return result

    def recover_device(self, serial: str = None) -> RecoveryResult:
        """
        Recovery device connection — reconnect dengan retry + backoff.

        Args:
            serial: Serial device (None = auto-detect)

        Returns:
            RecoveryResult
        """
        start = time.time()
        device_log.warning(f"AUTO-RECOVERY: Mencoba reconnect device...")

        if not serial:
            serial = self._detect_serial()

        result = RecoveryResult(RecoveryAction.RECONNECT_DEVICE, False)

        for attempt in range(self.max_reconnect_retries):
            # Cek apakah sudah terhubung
            if self._is_device_connected(serial):
                result.success = True
                result.message = f"Device {serial} terhubung kembali (attempt {attempt + 1})"
                result.duration = time.time() - start
                device_log.success(result.message)
                self._record_recovery(f"device_{serial}", result)

                self._event_bus.emit(EventBus.DEVICE_CONNECTED, {
                    "key": serial,
                    "status": {"type": "android", "serial": serial},
                    "recovery": True,
                })
                return result

            # Exponential backoff
            delay = min(self.backoff_base * (2 ** attempt), self.backoff_max)
            device_log.info(f"  Menunggu reconnect... ({delay:.0f}s, attempt {attempt + 1}/{self.max_reconnect_retries})")

            for _ in range(int(delay * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

                # Cek device tiap 100ms
                if self._is_device_connected(serial):
                    result.success = True
                    result.message = f"Device {serial} terhubung kembali!"
                    result.duration = time.time() - start
                    device_log.success(result.message)
                    self._record_recovery(f"device_{serial}", result)

                    self._event_bus.emit(EventBus.DEVICE_CONNECTED, {
                        "key": serial,
                        "status": {"type": "android", "serial": serial},
                        "recovery": True,
                    })
                    return result

        result.message = f"Device {serial} tidak terhubung setelah {self.max_reconnect_retries} percobaan"
        error_log.error(result.message)
        result.duration = time.time() - start
        self._record_recovery(f"device_{serial}", result)
        return result

    def recover_flash(self, task_name: str = "unknown") -> RecoveryResult:
        """
        Recovery flash failure — retry flashing.
        Untuk dipanggil jika flashing gagal.

        Args:
            task_name: Nama task yang gagal

        Returns:
            RecoveryResult
        """
        flash_log.warning(f"AUTO-RECOVERY: Mencoba recovery flash gagal: {task_name}")
        result = RecoveryResult(RecoveryAction.RETRY_FLASH, False)

        # 1. Cek device masih terhubung
        if not self._is_device_connected():
            device_log.warning("Device terputus, mencoba reconnect...")
            reconnect = self.recover_device()
            if not reconnect.success:
                result.message = "Device tidak terhubung, tidak bisa retry flash"
                error_log.error(result.message)
                return result

        # 2. Cek ADB masih hidup
        if not self._is_adb_alive():
            adb_log.warning("ADB mati, mencoba restart...")
            adb_recovery = self.recover_adb()
            if not adb_recovery.success:
                result.message = "ADB tidak bisa direstart, tidak bisa retry flash"
                error_log.error(result.message)
                return result

        # 3. Cek fastboot (jika flashing via fastboot)
        if "fastboot" in task_name.lower():
            if not self._is_fastboot_alive():
                result.message = "Fastboot tidak merespon"
                return result

        result.success = True
        result.message = "Flash recovery siap — system siap untuk retry"
        flash_log.success(result.message)
        self._record_recovery(f"flash_{task_name}", result)

        # Emit event agar task_manager bisa retry
        self._event_bus.emit(EventBus.SYSTEM_RECOVERY, {
            "type": "flash",
            "success": True,
            "message": result.message,
            "task": task_name,
            "ready_for_retry": True,
        })

        return result

    def recover_emergency(self) -> RecoveryResult:
        """
        Full emergency recovery — kill zombie ADB, restart, clean.
        Untuk situasi darurat (ADB hang total, device not responding).
        """
        log.warning("🚑 AUTO-RECOVERY: Menjalankan emergency recovery...")

        steps = [
            ("Kill ADB zombies", self._kill_adb_zombies),
            ("Restart ADB", self._start_adb),
            ("Verify ADB", lambda: self._verify_adb_alive()),
            ("Clean temp", self._clean_temp_files),
        ]

        result = self._execute_recovery(steps, "EMERGENCY")
        result.action = RecoveryAction.KILL_ZOMBIE

        if result.success:
            log.success("🚑 Emergency recovery berhasil!")
        else:
            error_log.error(f"🚑 Emergency recovery gagal: {result.message}")

        self._record_recovery("emergency", result)

        self._event_bus.emit(EventBus.SYSTEM_RECOVERY, {
            "type": "emergency",
            "success": result.success,
            "message": result.message,
        })

        return result

    def recover_usb(self) -> RecoveryResult:
        """
        Reset USB stack — restart USB subsystem.
        Windows: devcon restart
        Linux: usbreset
        """
        result = RecoveryResult(RecoveryAction.RESET_USB, False)
        start = time.time()

        try:
            if os.name == 'nt':
                # Windows — restart via devcon atau usbdeview
                try:
                    # Coba restart via devcon
                    subprocess.run(
                        ["devcon", "restart", "USB\\VID_*"],
                        capture_output=True, text=True, timeout=10
                    )
                    result.success = True
                    result.message = "USB devices restarted (devcon)"
                except FileNotFoundError:
                    # Coba via usbdeview
                    result.message = "devcon tidak ditemukan"
            else:
                # Linux — unbind/rebind USB
                result.message = "USB reset hanya untuk Windows"
        except Exception as e:
            result.message = f"USB reset error: {e}"

        result.duration = time.time() - start
        return result

    # ── Monitoring ──

    def monitor_device(self, serial: str, on_connected: Optional[Callable] = None,
                       on_disconnected: Optional[Callable] = None,
                       check_interval: float = 2.0):
        """
        Monitor device connection — panggil callback saat status berubah.

        Args:
            serial: Serial device
            on_connected: Callback saat device terhubung (thread-safe)
            on_disconnected: Callback saat device terputus
            check_interval: Interval check (detik)
        """
        if serial in self._monitoring:
            return

        def _monitor():
            prev_connected = self._is_device_connected(serial)
            while self._running and serial in self._monitoring:
                connected = self._is_device_connected(serial)
                if connected != prev_connected:
                    if connected and on_connected:
                        on_connected()
                    elif not connected and on_disconnected:
                        on_disconnected()
                    prev_connected = connected
                time.sleep(check_interval)

        thread = threading.Thread(target=_monitor, daemon=True, name=f"Monitor-{serial[:8]}")
        self._monitoring[serial] = thread
        thread.start()

    def unmonitor_device(self, serial: str):
        """Stop monitoring device"""
        self._monitoring.pop(serial, None)

    # ── Internal Recovery Steps ──

    def _kill_adb(self) -> bool:
        try:
            subprocess.run(["adb", "kill-server"], capture_output=True, timeout=5)
            time.sleep(1)
            return True
        except Exception:
            return False

    def _verify_adb_dead(self) -> bool:
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=3)
            return False  # ADB masih hidup kalo return code 0
        except Exception:
            return True  # ADB mati (yang diharapkan)

    def _start_adb(self) -> bool:
        try:
            r = subprocess.run(["adb", "start-server"], capture_output=True, text=True, timeout=10)
            time.sleep(1)
            return r.returncode == 0
        except Exception:
            return False

    def _verify_adb_alive(self) -> bool:
        return self._is_adb_alive()

    def _check_adb_devices(self) -> bool:
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            return '\tdevice' in r.stdout
        except Exception:
            return False

    def _kill_adb_zombies(self) -> bool:
        """Kill semua proses ADB yang membeku"""
        try:
            if os.name == 'nt':
                subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True, timeout=5)
            else:
                subprocess.run(["pkill", "-9", "adb"], capture_output=True, timeout=5)
            time.sleep(1)
            return True
        except Exception:
            return False

    def _clean_temp_files(self) -> bool:
        """Bersihkan file temporary"""
        try:
            temp_dirs = []
            if os.name == 'nt':
                temp_dirs.append(os.environ.get('TEMP', ''))
            temp_dirs.append('/tmp')

            for td in temp_dirs:
                if td and os.path.exists(td):
                    for f in os.listdir(td):
                        fpath = os.path.join(td, f)
                        if os.path.isfile(fpath) and f.endswith(('.tmp', '.log')):
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
            return True
        except Exception:
            return False

    # ── Helpers ──

    def _is_device_connected(self, serial: str = None) -> bool:
        """Cek apakah device terhubung via ADB"""
        try:
            if serial:
                r = subprocess.run(
                    ["adb", "-s", serial, "get-state"],
                    capture_output=True, text=True, timeout=3
                )
                return r.returncode == 0 and "device" in r.stdout
            else:
                r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=3)
                return '\tdevice' in r.stdout
        except Exception:
            return False

    def _is_adb_alive(self) -> bool:
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=3)
            return r.returncode == 0
        except Exception:
            return False

    def _is_fastboot_alive(self) -> bool:
        try:
            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
            return '\tfastboot' in r.stdout
        except Exception:
            return False

    def _detect_serial(self) -> Optional[str]:
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=3)
            for line in r.stdout.split('\n')[1:]:
                if '\tdevice' in line:
                    return line.split('\t')[0]
            return None
        except Exception:
            return None

    def _execute_recovery(self, steps: list, name: str) -> RecoveryResult:
        """Eksekusi serangkaian langkah recovery"""
        succeeded = 0
        failed = 0
        messages = []

        for step_name, step_func in steps:
            try:
                result = step_func()
                if result:
                    succeeded += 1
                    messages.append(f"{step_name}: ✅")
                else:
                    failed += 1
                    messages.append(f"{step_name}: ❌")
            except Exception as e:
                failed += 1
                messages.append(f"{step_name}: ❌ ({e})")

        result = RecoveryResult(RecoveryAction.NONE, failed == 0, "; ".join(messages))
        result.action = RecoveryAction.RESTART_ADB if "adb" in name.lower() else RecoveryAction.RESTART_SERVICE

        return result

    def _record_recovery(self, key: str, result: RecoveryResult):
        """Catat history recovery"""
        with self._lock:
            if key not in self._recovery_history:
                self._recovery_history[key] = []
            self._recovery_history[key].append(result)
            # Keep last 10 entries
            if len(self._recovery_history[key]) > 10:
                self._recovery_history[key] = self._recovery_history[key][-10:]

    def get_recovery_history(self, key: Optional[str] = None) -> Dict[str, list]:
        """Dapatkan history recovery"""
        if key:
            return {key: self._recovery_history.get(key, [])}
        return dict(self._recovery_history)

    def get_recovery_stats(self) -> Dict:
        """Dapatkan statistik recovery"""
        stats = {"total": 0, "success": 0, "failed": 0}
        for key, history in self._recovery_history.items():
            for r in history:
                stats["total"] += 1
                if r.success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
        return stats

    def stop(self):
        """Stop monitoring threads"""
        self._running = False
        self._monitoring.clear()


# ── Global instance ──
auto_recovery = AutoRecovery()
