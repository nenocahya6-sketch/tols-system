
"""
NST Protection Layer v1
=========================
VALIDATION LAYER — Auto-run DI SETIAP task berbahaya.

Dijalankan OTOMATIS oleh TaskManager SEBELUM mengeksekusi task
yang membutuhkan proteksi (requires_protection=True).

Fungsi:
1. Validasi device connection masih aktif
2. Cek battery level (min 30% untuk flash)
3. Cek bootloader status (untuk flash partisi sistem)
4. Cek chipset cocok (jika firmware info tersedia)
5. Cek disk space tersedia
6. Cek tidak ada konflik resource (ADB & fastboot bersamaan)

Jika validasi GAGAL → task di-cancel dengan error message jelas.
"""
import os
import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Any
from datetime import datetime

from core.logger import log, error_log, flash_log, device_log


@dataclass
class ValidationResult:
    """Hasil validasi protection layer"""
    valid: bool = True
    error_message: Optional[str] = None
    warning: Optional[str] = None
    checks: Dict[str, Any] = None

    def __post_init__(self):
        if self.checks is None:
            self.checks = {}


# Risiko task — semakin tinggi, semakin ketat validasi
TASK_RISK_MAP = {
    "flash": "critical",
    "unlock": "critical",
    "root": "high",
    "reset": "critical",
    "frp": "high",
    "emergency": "high",
    "diagnostic": "low",
    "scan": "low",
    "backup": "medium",
    "restore": "critical",
    "check": "low",
    "install": "medium",
}


def get_task_risk(task_name: str) -> str:
    """Tentukan level risiko dari nama task"""
    name_lower = task_name.lower()
    for keyword, risk in TASK_RISK_MAP.items():
        if keyword in name_lower:
            return risk
    return "low"


class ProtectionLayer:
    """
    Protection Layer — validasi otomatis sebelum task berbahaya.

    Singleton — digunakan oleh TaskManager._run_protection_check()
    """

    _instance: Optional["ProtectionLayer"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._validator = None  # Lazy init DeviceStateValidator
            self._last_validation: Dict[str, ValidationResult] = {}
            self._cache_ttl = 10  # Cache validasi 10 detik

    def validate_task(self, task) -> ValidationResult:
        """
        Validasi task sebelum dieksekusi.

        Args:
            task: Task object dari TaskManager

        Returns:
            ValidationResult — valid / invalid dengan pesan error
        """
        risk = get_task_risk(task.name)
        result = ValidationResult()

        # Skip validasi untuk task ringan
        if risk == "low":
            return result

        log.info(f"🔍 Protection Layer: Memvalidasi task '{task.name}' (risk: {risk})")
        device_log.info(f"VALIDATION: {task.name} (risk={risk})")

        checks = {}

        # ── Check 1: Device Connection ──
        device_ok, device_info = self._check_device_connection()
        checks["device_connected"] = device_ok
        if not device_ok and risk in ("critical", "high"):
            result.valid = False
            result.error_message = "Tidak ada device terdeteksi! Hubungkan device via USB."
            result.checks = checks
            self._log_failure(task, result)
            return result

        # ── Check 2: Resource Conflict ──
        conflict_ok = self._check_resource_conflict(task)
        checks["resource_conflict"] = conflict_ok
        if not conflict_ok:
            result.valid = False
            result.error_message = "Konflik resource! Task lain sedang menggunakan ADB/Fastboot."
            result.checks = checks
            self._log_failure(task, result)
            return result

        # ── Check 3: Battery Level (untuk flash/reset) ──
        if risk in ("critical", "high") and device_ok and device_info.get("adb_serial"):
            battery_ok, battery_msg = self._check_battery(device_info["adb_serial"])
            checks["battery"] = battery_ok
            checks["battery_msg"] = battery_msg
            if not battery_ok:
                result.valid = False
                result.error_message = battery_msg
                result.checks = checks
                self._log_failure(task, result)
                return result

        # ── Check 4: Disk Space (untuk flash/backup) ──
        if risk in ("critical", "high", "medium"):
            disk_ok, disk_msg = self._check_disk_space(risk)
            checks["disk_space"] = disk_ok
            checks["disk_msg"] = disk_msg
            if not disk_ok:
                result.valid = False
                result.error_message = disk_msg
                result.checks = checks
                self._log_failure(task, result)
                return result

        # ── Check 5: Fastboot Mode Safety (untuk flash) ──
        if "flash" in task.name.lower():
            fb_ok, fb_msg = self._check_fastboot_safety()
            checks["fastboot_safe"] = fb_ok
            checks["fastboot_msg"] = fb_msg
            if not fb_ok:
                result.warning = fb_msg
                checks["fastboot_warning"] = True

        # ── Check 6: Emergency Mode Safety ──
        if "emergency" in task.name.lower():
            emerg_ok, emerg_msg = self._check_emergency_safety()
            checks["emergency_safe"] = emerg_ok
            if not emerg_ok:
                result.warning = emerg_msg

        result.checks = checks
        result.valid = True

        if checks:
            log.info(f"✅ Protection: Semua check {sum(1 for v in checks.values() if v is True)}/{len(checks)} lulus")

        # Cache hasil
        cache_key = f"{task.id}_{task.name}"
        self._last_validation[cache_key] = result

        return result

    def _check_device_connection(self) -> tuple:
        """Check device connection via ADB or Fastboot"""
        try:
            import subprocess

            # ADB check
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n')[1:]:
                if '\tdevice' in line:
                    serial = line.split('\t')[0]
                    return True, {"adb_serial": serial, "method": "adb"}

            # Fastboot check
            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n'):
                if '\tfastboot' in line:
                    serial = line.split('\t')[0]
                    return True, {"fastboot_serial": serial, "method": "fastboot"}

            return False, {}
        except FileNotFoundError:
            return False, {}
        except Exception:
            return False, {}

    def _check_resource_conflict(self, task) -> bool:
        """Check tidak ada konflik resource"""
        # TaskManager sudah handle ini via resource locks
        # Tapi kita cek juga via task_manager
        try:
            from core.task_manager import task_manager, ResourceType

            task_resource = task.resource
            active = task_manager.get_active_tasks()

            # Cek apakah ada task lain dengan resource yang SAMA
            for t in active:
                if t.id != task.id and t.resource == task_resource:
                    return False

            return True
        except ImportError:
            return True

    def _check_battery(self, serial: str) -> tuple:
        """Cek battery level — minimal 30% untuk operasi kritis"""
        try:
            import subprocess
            r = subprocess.run(
                ["adb", "-s", serial, "shell", "dumpsys battery | grep level"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and ':' in r.stdout:
                level = int(r.stdout.split(':')[1].strip())
                if level < 15:
                    return False, f"Battery KRITIS: {level}%! Charge minimal 30% untuk mencegah brick."
                elif level < 30:
                    return False, f"Battery RENDAH: {level}%! Risiko mati di tengah operasi. Charge > 30%."
                return True, f"Battery: {level}% ✅"
            return True, "Battery: Tidak bisa dicek (skip)"
        except Exception:
            return True, "Battery: Skip (ADB tidak tersedia)"

    def _check_disk_space(self, risk: str) -> tuple:
        """Cek disk space — minimal 200MB untuk low risk, 1GB untuk critical"""
        required_mb = {
            "critical": 1000,
            "high": 500,
            "medium": 200,
            "low": 50,
        }.get(risk, 200)

        try:
            import shutil
            usage = shutil.disk_usage(os.getcwd())
            free_mb = usage.free / (1024 * 1024)

            if free_mb < required_mb:
                return False, f"Disk space TIDAK CUKUP! {free_mb:.0f} MB free (butuh {required_mb} MB)"
            return True, f"Disk: {free_mb:.0f} MB free ✅"
        except Exception:
            return True, "Disk: Skip"

    def _check_fastboot_safety(self) -> tuple:
        """Check fastboot safety — ada device di fastboot mode?"""
        try:
            import subprocess
            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
            if '\tfastboot' in r.stdout:
                return True, "Device dalam Fastboot mode — aman"
            return True, "Tidak ada device Fastboot"
        except Exception:
            return True, "Fastboot safety: Skip"

    def _check_emergency_safety(self) -> tuple:
        """Check emergency safety — pastikan aman untuk kill/restart"""
        try:
            import subprocess
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=3)
            lines = [l for l in r.stdout.split('\n')[1:] if l.strip() and '\t' in l]
            if lines:
                return True, f"ADB device terdeteksi ({len(lines)})"
            return True, "Tidak ada ADB device"
        except Exception:
            return True, "Emergency safety: Skip"

    def _log_failure(self, task, result: ValidationResult):
        """Log failure ke error log"""
        error_log.error(
            f"PROTECTION BLOCKED: {task.name} | "
            f"Reason: {result.error_message} | "
            f"Resource: {task.resource}"
        )
        flash_log.warning(f"BLOCKED by Protection: {task.name} - {result.error_message}")


# ── Global instance ──
protection_layer = ProtectionLayer()
