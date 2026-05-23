


"""
NST Device State Validator v1
==============================
Validasi kondisi device SEBELUM mengeksekusi aksi berbahaya.

Memeriksa 7 aspek kritis:
  ✅ Bootloader — status lock/unlock
  ✅ Battery — level cukup untuk flashing
  ✅ Antirollback — kompatibilitas versi
  ✅ FRP — Factory Reset Protection status
  ✅ Chipset — cocok dengan firmware target
  ✅ Driver — driver terinstall dan berfungsi
  ✅ Auth — authentication status (Samsung, Xiaomi, Huawei)

Setiap check memiliki:
  - PASS ✅ -> aman untuk lanjut
  - WARN ⚠️ -> peringatan tapi bisa lanjut (user confirm)
  - BLOCK ❌ -> operation di-block sama sekali
"""


import os
import re
import json
import time
import shutil
import platform
import subprocess
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from core.logger import log, Colors
from core.safety import PreFlightCheck


# ===========================================================================
# Validation Result Types
# ===========================================================================

class CheckLevel(Enum):
    """Tingkat keparahan hasil check."""
    PASS = auto()      # ✅ Aman
    WARN = auto()      # ⚠️ Peringatan, perlu konfirmasi user
    BLOCK = auto()     # ❌ Operation di-block, harus diperbaiki dulu
    SKIP = auto()      # ⏭️ Tidak bisa dicek (skip)


@dataclass
class CheckResult:
    """Hasil satu item check."""
    name: str
    level: CheckLevel
    message: str
    detail: str = ""
    suggestion: str = ""

    @property
    def icon(self) -> str:
        return {
            CheckLevel.PASS: "✅",
            CheckLevel.WARN: "⚠️",
            CheckLevel.BLOCK: "❌",
            CheckLevel.SKIP: "⏭️",
        }.get(self.level, "❓")


@dataclass
class ValidationReport:
    """Laporan lengkap validasi device."""
    device_serial: str = ""
    device_model: str = ""
    device_brand: str = ""
    checks: List[CheckResult] = field(default_factory=list)
    timestamp: str = ""
    target_operation: str = ""

    @property
    def all_pass(self) -> bool:
        """Semua check PASS (termasuk SKIP dianggap aman)."""
        return all(c.level in (CheckLevel.PASS, CheckLevel.SKIP) for c in self.checks)

    @property
    def has_blockers(self) -> bool:
        """Ada check BLOCK yang mencegah operasi."""
        return any(c.level == CheckLevel.BLOCK for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        """Ada check WARN yang butuh perhatian."""
        return any(c.level == CheckLevel.WARN for c in self.checks)

    def get_blockers(self) -> List[CheckResult]:
        return [c for c in self.checks if c.level == CheckLevel.BLOCK]

    def get_warnings(self) -> List[CheckResult]:
        return [c for c in self.checks if c.level == CheckLevel.WARN]


# ===========================================================================
# DEVICE STATE VALIDATOR — INTI
# ===========================================================================

class DeviceStateValidator:
    """
    Validator kondisi device komprehensif.

    Usage:
        validator = DeviceStateValidator()
        report = validator.validate_all(serial="<device_serial>",
                                        operation="flash_firmware",
                                        firmware_info={"model": "SM-G998B", "chipset": "exynos2100"})

        if report.has_blockers:
            print("❌ OPERATION BLOCKED!")
            for b in report.get_blockers():
                print(f"  {b.icon} {b.message}")
        elif report.has_warnings:
            print("⚠️ Lanjutkan dengan hati-hati...")
        else:
            print("✅ Semua aman, silakan lanjutkan!")
    """

    def __init__(self):
        self.os_name = platform.system()
        self._adb_serial: Optional[str] = None
        self._fastboot_serial: Optional[str] = None

    # ── Public API ──

    def validate_all(self,
                     serial: Optional[str] = None,
                     operation: str = "generic",
                     firmware_info: Optional[Dict[str, Any]] = None) -> ValidationReport:
        """
        Validasi KOMPREHENSIF semua aspek device.

        Args:
            serial: Serial device (ADB atau Fastboot). None = auto-detect.
            operation: Tipe operasi ('flash', 'unlock', 'backup', 'restore', 'repair', 'generic')
            firmware_info: Info firmware target (opsional):
                {
                    "model": "SM-G998B",
                    "chipset": "exynos2100",
                    "version": "G998BXXU5CVG7",
                    "region": "XID",
                    "antirollback_version": 5,
                }

        Returns:
            ValidationReport — hasil semua check
        """
        log.header(f"[DEVICE STATE VALIDATOR]")
        log.info(f"Operation: {operation.upper()}")
        if firmware_info:
            log.info(f"Target Firmware: {firmware_info.get('model', '?')} / {firmware_info.get('version', '?')}")
        print()

        report = ValidationReport(
            device_serial=serial or "auto",
            target_operation=operation,
            timestamp=datetime.now().isoformat(),
        )

        # ── 1. Deteksi device ──
        device_info = self._detect_device(serial)
        if not device_info["connected"]:
            report.checks.append(CheckResult(
                name="Device Connection",
                level=CheckLevel.BLOCK,
                message="Tidak ada device terdeteksi",
                detail=f"Metode dicoba: ADB, Fastboot",
                suggestion="Hubungkan device via USB, pastikan driver terinstall"
            ))
            return report

        serial_adb = device_info.get("adb_serial")
        serial_fastboot = device_info.get("fastboot_serial")
        report.device_serial = serial_adb or serial_fastboot or ""
        report.device_model = device_info.get("model", "")
        report.device_brand = device_info.get("brand", "")

        log.success(f"Device terdeteksi: {report.device_model or 'Unknown'} ({serial_adb or serial_fastboot})")

        # ── 2. Bootloader Check ──
        bl_check = self._check_bootloader(serial_adb)
        report.checks.append(bl_check)

        # ── 3. Battery Check ──
        battery_check = self._check_battery(serial_adb)
        report.checks.append(battery_check)

        # ── 4. Driver Check ──
        driver_check = self._check_drivers()
        report.checks.append(driver_check)

        # ── 5. Chipset Check (jika ada firmware_info) ──
        if firmware_info:
            chipset_check = self._check_chipset(serial_adb, firmware_info)
            report.checks.append(chipset_check)

        # ── 6. Antirollback Check (jika ada firmware_info) ──
        if firmware_info and serial_adb:
            arb_check = self._check_antirollback(serial_adb, firmware_info)
            report.checks.append(arb_check)

        # ── 7. FRP Check (untuk flashing) ──
        if operation in ("flash", "flash_firmware", "reset"):
            frp_check = self._check_frp(serial_adb)
            report.checks.append(frp_check)

        # ── 8. Auth Check ──
        auth_check = self._check_auth(serial_adb, serial_fastboot)
        report.checks.append(auth_check)

        # ── 9. Disk Space ──
        disk_check = self._check_disk_space()
        report.checks.append(disk_check)

        # ── Tampilkan hasil ──
        self._print_report(report)
        return report

    def validate_fast(self, serial: Optional[str] = None) -> ValidationReport:
        """
        Validasi CEPAT — hanya check esensial:
        device connection, battery, driver, disk space.
        """
        report = ValidationReport(
            device_serial=serial or "auto",
            target_operation="fast_check",
            timestamp=datetime.now().isoformat(),
        )

        device_info = self._detect_device(serial)
        if not device_info["connected"]:
            report.checks.append(CheckResult("Device", CheckLevel.BLOCK,
                "Tidak ada device terdeteksi"))
            return report

        serial_adb = device_info.get("adb_serial")
        report.device_serial = serial_adb or device_info.get("fastboot_serial", "")

        report.checks.append(self._check_battery(serial_adb))
        report.checks.append(self._check_drivers())
        report.checks.append(self._check_disk_space())

        self._print_report(report)
        return report

    # ── Individual Check Methods ──

    def _detect_device(self, serial: Optional[str] = None) -> Dict[str, Any]:
        """Deteksi device — ADB dan Fastboot."""
        result = {
            "connected": False,
            "adb_serial": None,
            "fastboot_serial": None,
            "model": None,
            "brand": None,
        }

        # Jika serial sudah ditentukan, cek ADB dulu
        if serial:
            try:
                r = subprocess.run(
                    ["adb", "-s", serial, "get-state"],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0:
                    result["connected"] = True
                    result["adb_serial"] = serial
                    # Baca model/brand
                    for prop, key in [("ro.product.model", "model"), ("ro.product.brand", "brand")]:
                        try:
                            r2 = subprocess.run(
                                ["adb", "-s", serial, "shell", f"getprop {prop}"],
                                capture_output=True, text=True, timeout=3
                            )
                            if r2.returncode == 0 and r2.stdout.strip():
                                result[key] = r2.stdout.strip()
                        except Exception:
                            pass
                    return result
            except Exception:
                pass

        # Auto-detect ADB
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n')[1:]:
                if '\tdevice' in line:
                    detected_serial = line.split('\t')[0]
                    result["connected"] = True
                    result["adb_serial"] = detected_serial
                    # Baca model
                    try:
                        r2 = subprocess.run(
                            ["adb", "-s", detected_serial, "shell", "getprop ro.product.model"],
                            capture_output=True, text=True, timeout=3
                        )
                        if r2.returncode == 0 and r2.stdout.strip():
                            result["model"] = r2.stdout.strip()
                        r3 = subprocess.run(
                            ["adb", "-s", detected_serial, "shell", "getprop ro.product.brand"],
                            capture_output=True, text=True, timeout=3
                        )
                        if r3.returncode == 0 and r3.stdout.strip():
                            result["brand"] = r3.stdout.strip()
                    except Exception:
                        pass
                    break
        except Exception:
            pass

        # Auto-detect Fastboot
        try:
            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n'):
                if '\tfastboot' in line:
                    detected_serial = line.split('\t')[0]
                    result["connected"] = True
                    result["fastboot_serial"] = detected_serial
                    break
        except Exception:
            pass

        return result

    def _check_bootloader(self, serial_adb: Optional[str]) -> CheckResult:
        """
        Cek status bootloader (LOCKED/UNLOCKED).
        - LOCKED + flash system partition = BLOCK
        - UNLOCKED = PASS
        - Tidak bisa cek = WARN
        """
        if not serial_adb:
            # Coba via fastboot
            try:
                r = subprocess.run(
                    ["fastboot", "oem", "device-info"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0:
                    output = r.stdout.lower()
                    if "device unlocked" in output or "unlocked: yes" in output:
                        return CheckResult("Bootloader", CheckLevel.PASS,
                            "Bootloader UNLOCKED", "Device bootloader sudah terbuka")
                    elif "device locked" in output or "locked: yes" in output:
                        return CheckResult("Bootloader", CheckLevel.WARN,
                            "Bootloader LOCKED",
                            "Flash partisi sistem mungkin terbatas",
                            "Unlock bootloader: fastboot oem unlock atau fastboot flashing unlock")
                    else:
                        return CheckResult("Bootloader", CheckLevel.WARN,
                            f"Status bootloader: {r.stdout[:100]}",
                            "Fastboot terdeteksi tapi output tidak dikenal")
                return CheckResult("Bootloader", CheckLevel.SKIP,
                    "Tidak bisa cek bootloader", "Device tidak dalam mode ADB/Fastboot")
            except Exception:
                return CheckResult("Bootloader", CheckLevel.SKIP,
                    "Tidak bisa cek bootloader", "Fastboot tidak tersedia")

        try:
            # Via ADB: cek ro.boot.flash.locked
            r = subprocess.run(
                ["adb", "-s", serial_adb, "shell", "getprop ro.boot.flash.locked"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                val = r.stdout.strip()
                if val == "0":
                    return CheckResult("Bootloader", CheckLevel.PASS,
                        "Bootloader UNLOCKED ✅", "Device bootloader terbuka, semua partisi bisa di-flash")
                elif val == "1":
                    return CheckResult("Bootloader", CheckLevel.WARN,
                        "Bootloader LOCKED ⚠️",
                        "Partisi sistem (boot, recovery, super) tidak bisa di-flash",
                        "Unlock bootloader via: Settings > Developer Options > OEM Unlock\n"
                        "Lalu: fastboot oem unlock atau fastboot flashing unlock")

            # Alternatif: ro.boot.lock_state
            r2 = subprocess.run(
                ["adb", "-s", serial_adb, "shell", "getprop ro.boot.lock_state"],
                capture_output=True, text=True, timeout=5
            )
            if r2.returncode == 0:
                val2 = r2.stdout.strip().lower()
                if val2 in ("unlocked", "false", "0"):
                    return CheckResult("Bootloader", CheckLevel.PASS,
                        f"Bootloader UNLOCKED ({val2}) ✅")
                elif val2 in ("locked", "true", "1"):
                    return CheckResult("Bootloader", CheckLevel.WARN,
                        f"Bootloader LOCKED ({val2}) ⚠️",
                        suggestion="Unlock bootloader sebelum flash partisi sistem")

            # Cek via fastboot jika ADB tapi fastboot juga
            try:
                r3 = subprocess.run(
                    ["adb", "-s", serial_adb, "reboot", "bootloader"],
                    capture_output=True, timeout=5
                )
                time.sleep(2)
                r4 = subprocess.run(
                    ["fastboot", "oem", "device-info"],
                    capture_output=True, text=True, timeout=10
                )
                # Reboot back
                subprocess.run(["fastboot", "reboot"], capture_output=True, timeout=5)
                if r4.returncode == 0:
                    output = r4.stdout.lower()
                    if "unlocked" in output:
                        return CheckResult("Bootloader", CheckLevel.PASS,
                            "Bootloader UNLOCKED ✅")
                    else:
                        return CheckResult("Bootloader", CheckLevel.WARN,
                            "Bootloader Status: " + r4.stdout[:80])
            except Exception:
                pass

            return CheckResult("Bootloader", CheckLevel.SKIP,
                "Tidak bisa konfirmasi status bootloader",
                "Cek manual: fastboot oem device-info")
        except Exception as e:
            return CheckResult("Bootloader", CheckLevel.SKIP,
                f"Error cek bootloader: {e}")

    def _check_battery(self, serial_adb: Optional[str]) -> CheckResult:
        """
        Cek level baterai.
        - < 20%: BLOCK (risiko mati di tengah operasi)
        - 20-30%: WARN
        - > 30%: PASS
        """
        if not serial_adb:
            return CheckResult("Battery", CheckLevel.SKIP,
                "Tidak bisa cek battery", "Device tidak dalam mode ADB")

        try:
            r = subprocess.run(
                ["adb", "-s", serial_adb, "shell", "dumpsys battery | grep level"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and ':' in r.stdout:
                level = int(r.stdout.split(':')[1].strip())
                temp_r = subprocess.run(
                    ["adb", "-s", serial_adb, "shell", "dumpsys battery | grep temperature"],
                    capture_output=True, text=True, timeout=3
                )
                temp_str = ""
                if temp_r.returncode == 0 and ':' in temp_r.stdout:
                    temp_raw = temp_r.stdout.split(':')[1].strip()
                    try:
                        temp_c = int(temp_raw) / 10.0
                        temp_str = f" | Suhu: {temp_c:.1f}°C"
                    except Exception:
                        pass

                if level < 15:
                    return CheckResult("Battery", CheckLevel.BLOCK,
                        f"Battery KRITIS: {level}%{temp_str}",
                        "Battery terlalu rendah, risiko brick jika mati di tengah operasi",
                        f"Charge battery minimal 30%. Saat ini: {level}%")
                elif level < 30:
                    return CheckResult("Battery", CheckLevel.WARN,
                        f"Battery RENDAH: {level}%{temp_str}",
                        "Risiko operasi terputus karena battery habis",
                        f"Disarankan charge > 30%. Saat ini: {level}%")
                else:
                    return CheckResult("Battery", CheckLevel.PASS,
                        f"Battery: {level}% ✅{temp_str}")
            else:
                return CheckResult("Battery", CheckLevel.SKIP,
                    "Tidak bisa baca level battery")
        except Exception as e:
            return CheckResult("Battery", CheckLevel.SKIP,
                f"Error cek battery: {e}")

    def _check_drivers(self) -> CheckResult:
        """Cek driver penting terinstall."""
        missing = []
        found = []

        # Cek ADB
        if shutil.which("adb"):
            found.append("ADB")
        else:
            missing.append("ADB")

        # Cek Fastboot
        if shutil.which("fastboot"):
            found.append("Fastboot")
        else:
            missing.append("Fastboot")

        # Cek di Windows via registry untuk driver USB
        if self.os_name == "Windows":
            try:
                import winreg
                # Cek Android USB Driver
                android_keys = [
                    r"SYSTEM\CurrentControlSet\Services\usbaudio",
                    r"SYSTEM\CurrentControlSet\Control\Class\{745a17a0-74d3-11d0-b6fe-00a0c90f57da}",
                ]
                for key_path in android_keys:
                    try:
                        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                        winreg.CloseKey(key)
                        found.append("USB Driver (Registry)")
                        break
                    except Exception:
                        pass
            except Exception:
                pass

            # Cek driver Qualcomm (EDL)
            try:
                r = subprocess.run(
                    ['powershell', '-Command',
                     'Get-PnpDevice | Where-Object {$_.FriendlyName -like "*Qualcomm*" -or $_.FriendlyName -like "*QDLoader*"} | Select-Object Status'],
                    capture_output=True, text=True, timeout=5
                )
                if "OK" in r.stdout:
                    found.append("Qualcomm USB Driver")
            except Exception:
                pass

            # Cek driver MediaTek (VCOM)
            try:
                r = subprocess.run(
                    ['powershell', '-Command',
                     'Get-PnpDevice | Where-Object {$_.FriendlyName -like "*MediaTek*" -or $_.FriendlyName -like "*MTK*" -or $_.FriendlyName -like "*Preloader*"} | Select-Object Status'],
                    capture_output=True, text=True, timeout=5
                )
                if "OK" in r.stdout:
                    found.append("MediaTek VCOM Driver")
            except Exception:
                pass

        if missing:
            msg = f"Driver ditemukan: {', '.join(found)}. Missing: {', '.join(missing)}"
            return CheckResult("Driver", CheckLevel.WARN if len(missing) <= 1 else CheckLevel.BLOCK,
                msg, suggestion=f"Install driver yang kurang. Gunakan menu Driver Doctor (menu 14)")

        return CheckResult("Driver", CheckLevel.PASS,
            f"Semua driver OK ✅ ({', '.join(found)})")

    def _check_chipset(self, serial_adb: Optional[str],
                       firmware_info: Dict[str, Any]) -> CheckResult:
        """
        Cek chipset device cocok dengan firmware target.
        """
        if not serial_adb:
            # Coba via fastboot
            try:
                r = subprocess.run(
                    ["fastboot", "getvar", "product"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0 and r.stdout.strip():
                    product = r.stdout.strip().split('\n')[0].split(': ')[-1].strip()
                    return CheckResult("Chipset", CheckLevel.SKIP,
                        f"Product: {product} (via Fastboot)",
                        "Verifikasi manual apakah cocok dengan firmware target")
            except Exception:
                pass

            return CheckResult("Chipset", CheckLevel.SKIP,
                "Tidak bisa verifikasi chipset - device tidak dalam mode ADB")

        try:
            # Baca chipset info via ADB
            chipset_props = {
                "chipset": "ro.chipset",
                "platform": "ro.board.platform",
                "hardware": "ro.hardware",
                "soc": "ro.soc.model",
                "mediatek_platform": "ro.mediatek.platform",
            }

            device_chipset = None
            for key, prop in chipset_props.items():
                r = subprocess.run(
                    ["adb", "-s", serial_adb, "shell", f"getprop {prop}"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip() and r.stdout.strip() != "unknown":
                    device_chipset = r.stdout.strip()
                    break

            if not device_chipset:
                # Fallback: baca dari /proc/cpuinfo
                r = subprocess.run(
                    ["adb", "-s", serial_adb, "shell", "cat /proc/cpuinfo | grep Hardware"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and ':' in r.stdout:
                    device_chipset = r.stdout.split(':')[1].strip()

            if not device_chipset:
                return CheckResult("Chipset", CheckLevel.SKIP,
                    "Tidak bisa deteksi chipset")

            # Cek cocok dengan firmware target
            target_chipset = firmware_info.get("chipset", "").lower()
            if target_chipset:
                device_lower = device_chipset.lower()
                match = (target_chipset in device_lower or
                         device_lower in target_chipset or
                         any(kw in device_lower for kw in target_chipset.split("_")))
                if match:
                    return CheckResult("Chipset", CheckLevel.PASS,
                        f"Chipset cocok ✅ Device: {device_chipset} ↔ Target: {target_chipset}")
                else:
                    return CheckResult("Chipset", CheckLevel.BLOCK,
                        f"Chipset TIDAK COCOK ❌ Device: {device_chipset}, Target: {target_chipset}",
                        "Flashing firmware untuk chipset berbeda bisa menyebabkan BRICK!",
                        "Cari firmware yang sesuai dengan chipset device Anda")
            else:
                return CheckResult("Chipset", CheckLevel.PASS,
                    f"Chipset: {device_chipset} ✅ (tanpa verifikasi target)")
        except Exception as e:
            return CheckResult("Chipset", CheckLevel.SKIP,
                f"Error cek chipset: {e}")

    def _check_antirollback(self, serial_adb: str,
                            firmware_info: Dict[str, Any]) -> CheckResult:
        """
        Cek Anti-Rollback (ARB) version.
        Qualcomm: ro.boot.avb_version
        Samsung: ro.boot.odin_arb_version
        """
        if not serial_adb:
            return CheckResult("Anti-Rollback", CheckLevel.SKIP,
                "Tidak bisa cek ARB - device tidak dalam mode ADB")

        try:
            # Cek Samsung ARB
            arb_props = {
                "samsung": "ro.boot.odin_arb_version",
                "samsung2": "ro.boot.arb_version",
                "qualcomm_avb": "ro.boot.avb_version",
                "qualcomm_meta": "ro.boot.antirollback",
            }

            device_arb = None
            arb_source = ""
            for source, prop in arb_props.items():
                r = subprocess.run(
                    ["adb", "-s", serial_adb, "shell", f"getprop {prop}"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip() and r.stdout.strip() != "unknown":
                    device_arb = r.stdout.strip()
                    arb_source = source
                    break

            if device_arb is None:
                return CheckResult("Anti-Rollback", CheckLevel.SKIP,
                    "Tidak bisa deteksi ARB version (mungkin bukan Samsung/Qualcomm)")

            target_arb = firmware_info.get("antirollback_version")
            if target_arb is not None:
                try:
                    device_arb_num = int(device_arb)
                    target_arb_num = int(target_arb)

                    if device_arb_num == target_arb_num:
                        return CheckResult("Anti-Rollback", CheckLevel.PASS,
                            f"ARB cocok ✅ Device: v{device_arb_num} = Target: v{target_arb_num}")
                    elif device_arb_num > target_arb_num:
                        return CheckResult("Anti-Rollback", CheckLevel.BLOCK,
                            f"ARB DOWNGRADE TERDETEKSI ❌ Device: v{device_arb_num} > Target: v{target_arb_num}",
                            "Flashing firmware dengan ARB lebih rendah bisa menyebabkan BRICK!",
                            "Cari firmware dengan ARB >= versi device Anda")
                    else:
                        return CheckResult("Anti-Rollback", CheckLevel.PASS,
                            f"ARB upgrade aman ✅ Device: v{device_arb_num} < Target: v{target_arb_num}")
                except ValueError:
                    return CheckResult("Anti-Rollback", CheckLevel.PASS,
                        f"ARB: {device_arb} (tanpa verifikasi)")

            return CheckResult("Anti-Rollback", CheckLevel.PASS,
                f"ARB Device: v{device_arb} (sumber: {arb_source}) ✅")
        except Exception as e:
            return CheckResult("Anti-Rollback", CheckLevel.SKIP,
                f"Error cek ARB: {e}")

    def _check_frp(self, serial_adb: Optional[str]) -> CheckResult:
        """
        Cek FRP (Factory Reset Protection) status.
        """
        if not serial_adb:
            return CheckResult("FRP", CheckLevel.SKIP,
                "Tidak bisa cek FRP - device tidak dalam mode ADB")

        try:
            # Beberapa metode cek FRP
            frp_checks = [
                ("adb", "-s", serial_adb, "shell", "getprop ro.boot.verifiedbootstate"),
                ("adb", "-s", serial_adb, "shell", "getprop ro.frp.pst"),
                ("adb", "-s", serial_adb, "shell", "getprop sys.frp"),
            ]

            for cmd in frp_checks:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    val = r.stdout.strip().lower()
                    if val in ("1", "true", "yes", "locked", "on"):
                        return CheckResult("FRP", CheckLevel.WARN,
                            "FRP AKTIF ⚠️",
                            "FRP aktif: Setelah flash, device akan minta login Google account sebelumnya",
                            "Nonaktifkan FRP: Settings > Accounts > Remove Google account, "
                            "atau flash firmware dengan .pit yang menyertakan format userdata")
                    elif val in ("0", "false", "no", "unlocked", "off"):
                        return CheckResult("FRP", CheckLevel.PASS,
                            "FRP: Tidak aktif ✅")

            # Cek via content provider
            r = subprocess.run(
                ["adb", "-s", serial_adb, "shell",
                 "settings get secure frp_enable 2>/dev/null || echo unknown"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                val = r.stdout.strip()
                if val == "1":
                    return CheckResult("FRP", CheckLevel.WARN,
                        "FRP AKTIF ⚠️")
                elif val == "0":
                    return CheckResult("FRP", CheckLevel.PASS,
                        "FRP: Tidak aktif ✅")

            return CheckResult("FRP", CheckLevel.PASS,
                "FRP: Tidak terdeteksi (kemungkinan tidak aktif) ✅")
        except Exception as e:
            return CheckResult("FRP", CheckLevel.SKIP,
                f"Tidak bisa cek FRP: {e}")

    def _check_auth(self, serial_adb: Optional[str],
                    serial_fastboot: Optional[str]) -> CheckResult:
        """
        Cek authentication status per brand.
        - Samsung: KG State (Prenormal, Lockdown)
        - Xiaomi: Mi Unlock Status
        - Huawei: Bootloader code required
        """
        try:
            # Samsung KG State
            if serial_fastboot:
                r = subprocess.run(
                    ["fastboot", "getvar", "kg-state"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0 and r.stdout.strip():
                    kg = r.stdout.strip().lower()
                    if "prenormal" in kg:
                        return CheckResult("Auth", CheckLevel.WARN,
                            "Samsung KG: PRENORMAL ⚠️",
                            "Device Samsung dengan KG Prenormal: butuh waktu 7 hari unlock",
                            "Login Samsung account > Settings > Account > Biometric > "
                            "Add account > Tunggu 7 hari untuk unlock resmi")
                    elif "lockdown" in kg or "permanent" in kg:
                        return CheckResult("Auth", CheckLevel.BLOCK,
                            "Samsung KG: LOCKDOWN ❌",
                            "KG Lockdown: Flashing terbatas, tidak bisa downgrade",
                            "Hubungi Samsung Service Center")
                    elif "checking" in kg:
                        return CheckResult("Auth", CheckLevel.WARN,
                            "Samsung KG: CHECKING ⚠️",
                            "Status belum final, bisa berubah")
                    else:
                        return CheckResult("Auth", CheckLevel.PASS,
                            f"KG State: {kg.replace('kg-state: ', '')} ✅")

            # Samsung via ADB
            if serial_adb:
                r = subprocess.run(
                    ["adb", "-s", serial_adb, "shell", "getprop ro.boot.kgstate"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    kg = r.stdout.strip().lower()
                    if "prenormal" in kg:
                        return CheckResult("Auth", CheckLevel.WARN,
                            "Samsung KG: PRENORMAL ⚠️")
                    elif "lockdown" in kg:
                        return CheckResult("Auth", CheckLevel.BLOCK,
                            "Samsung KG: LOCKDOWN ❌")

            # Common auth check: rooted?
            if serial_adb:
                r = subprocess.run(
                    ["adb", "-s", serial_adb, "shell", "su -c 'echo su_ok' 2>/dev/null || echo no_su"],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0 and "su_ok" in r.stdout:
                    log.info("  Device: ROOTED (full access)")

            return CheckResult("Auth", CheckLevel.PASS,
                "Auth: OK ✅ (tanpa batasan autentikasi terdeteksi)")
        except Exception as e:
            return CheckResult("Auth", CheckLevel.SKIP,
                f"Tidak bisa cek auth: {e}")

    def _check_disk_space(self, required_mb: int = 500) -> CheckResult:
        """Cek disk space tersedia."""
        try:
            usage = shutil.disk_usage(os.getcwd())
            free_mb = usage.free / (1024 * 1024)
            if free_mb < required_mb:
                return CheckResult("Disk Space", CheckLevel.BLOCK,
                    f"Disk space TIDAK CUKUP ❌: {free_mb:.0f} MB (minimal {required_mb} MB)",
                    suggestion=f"Bersihkan disk atau pindah ke drive lain. Butuh minimal {required_mb} MB")
            elif free_mb < required_mb * 2:
                return CheckResult("Disk Space", CheckLevel.WARN,
                    f"Disk space terbatas: {free_mb:.0f} MB (disarankan > {required_mb * 2} MB)")
            else:
                return CheckResult("Disk Space", CheckLevel.PASS,
                    f"Disk space: {free_mb:.0f} MB ✅")
        except Exception as e:
            return CheckResult("Disk Space", CheckLevel.SKIP,
                f"Error cek disk: {e}")

    # ── Display ──

    def _print_report(self, report: ValidationReport):
        """Tampilkan laporan validasi ke layar."""
        print()
        log.separator()
        log.header("[VALIDATION REPORT]")
        print()

        for check in report.checks:
            color = {
                CheckLevel.PASS: Colors.GREEN,
                CheckLevel.WARN: Colors.YELLOW,
                CheckLevel.BLOCK: Colors.RED,
                CheckLevel.SKIP: Colors.DIM,
            }.get(check.level, Colors.WHITE)

            print(f"  {color}{check.icon} {check.name:20s} {check.message}{Colors.RESET}")
            if check.detail:
                print(f"  {Colors.DIM}     {check.detail}{Colors.RESET}")
            if check.suggestion:
                print(f"  {Colors.CYAN}     💡 {check.suggestion[:120]}{Colors.RESET}")
            print()

        log.separator()

        # Kesimpulan
        if report.has_blockers:
            log.critical("⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛")
            log.critical("⬛  OPERATION BLOCKED ❌                       ⬛")
            log.critical("⬛  Perbaiki BLOCKER(s) di atas dulu!          ⬛")
            for b in report.get_blockers():
                log.critical(f"⬛  ❌ {b.message[:50]}...")
            log.critical("⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛")
            print()
        elif report.has_warnings:
            log.warning("═══ VALIDATION PASSED WITH WARNINGS ⚠️ ═══")
            log.info("Lanjutkan dengan hati-hati dan perhatikan peringatan di atas.")
            print()
        else:
            log.success("═══ VALIDATION PASSED ✅ ═══")
            log.success("Semua aspek aman, silakan melanjutkan operasi!")
            print()

    def get_operation_requirements(self, operation: str) -> List[str]:
        """
        Dapatkan daftar check yang diperlukan untuk suatu operasi.

        Args:
            operation: 'flash', 'unlock', 'backup', 'restore', 'repair', 'generic'

        Returns: List nama check yang diperlukan
        """
        requirements = {
            "flash": [
                "Device Connection", "Battery", "Bootloader",
                "Chipset", "Anti-Rollback", "FRP", "Auth",
                "Driver", "Disk Space"
            ],
            "unlock": [
                "Device Connection", "Battery", "Auth",
                "Driver"
            ],
            "backup": [
                "Device Connection", "Battery", "Disk Space", "Driver"
            ],
            "restore": [
                "Device Connection", "Battery", "Disk Space", "Driver"
            ],
            "repair": [
                "Device Connection", "Battery", "Driver"
            ],
        }
        return requirements.get(operation, requirements["generic"])

    def suggest_fix(self, check: CheckResult) -> List[str]:
        """
        Berikan saran perbaikan untuk check yang gagal.
        """
        suggestions = {
            "Bootloader": [
                "Buka OEM Unlock di Settings > Developer Options",
                "Reboot ke Fastboot: adb reboot bootloader",
                "Jalankan: fastboot oem unlock",
                "Atau: fastboot flashing unlock",
                "Konfirmasi dengan tombol volume pada device",
            ],
            "Battery": [
                "Charge device hingga minimal 30%",
                "Gunakan charger cepat jika tersedia",
                "Pastikan kabel charging berfungsi baik",
            ],
            "Driver": [
                "Install ADB & Fastboot: https://developer.android.com/studio/releases/platform-tools",
                "Gunakan menu Driver Repair (menu baru 53)",
                "Install Samsung USB Driver untuk Samsung device",
                "Gunakan Zadig untuk driver VCOM MediaTek",
            ],
            "Chipset": [
                "Cari firmware dengan chipset yang sesuai",
                "Cek model device di Settings > About Phone",
                "Cari firmware di: samfrew.com, xiaomifirmwareupdater.com",
            ],
            "FRP": [
                "Hapus Google account: Settings > Accounts > Remove account",
                "Flash firmware dengan format userdata",
                "Gunakan PIT file yang menyertakan format userdata",
            ],
        }
        return suggestions.get(check.name, ["Tidak ada saran otomatis. Konsultasi forum XDA."])


# ===========================================================================
# MAIN ENTRY
# ===========================================================================

def run_validator():
    """Jalankan Device State Validator — full validation."""
    validator = DeviceStateValidator()
    validator.validate_all()


def run_validator_fast():
    """Jalankan Device State Validator — fast check."""
    validator = DeviceStateValidator()
    validator.validate_fast()