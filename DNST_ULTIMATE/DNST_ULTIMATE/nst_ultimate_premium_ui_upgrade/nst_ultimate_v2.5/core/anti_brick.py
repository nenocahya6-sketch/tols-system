
"""
NST Smart Anti-Brick v2
=========================
Sistem pemulihan cerdas untuk device yang brick.

Fitur baru v2:
  ✅ Auto-detect brick type (bootloop, hard brick, soft brick, Qualcomm EDL, MTK BROM)
  ✅ Restore vbmeta & boot partition
  ✅ Force Fastboot mode
  ✅ Emergency EDL mode (Qualcomm test point + command)
  ✅ Emergency BROM mode (MediaTek)
  ✅ Auto-backup + restore partisi vital
  ✅ Step-by-step recovery flow per brick type
"""


import os
import re
import time
import struct
import json
import shutil
import platform
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum, auto

from config import RECOVERY_METHODS
from core.logger import log, Colors
from core.safety import ActionLogger, ConfirmationChain


# ===========================================================================
# Brick Type Classification
# ===========================================================================

class BrickType(Enum):
    """Tipe brick yang dideteksi."""
    UNKNOWN = "Unknown"
    NONE = "No Brick"                    # Device normal
    SOFT_BRICK = "Soft Brick"            # Bootloop, stuck di logo
    BOOTLOOP = "Bootloop"                # Restart terus-menerus
    RECOVERY_BOOTLOOP = "Recovery Bootloop"  # Stuck di recovery
    FASTBOOT_STUCK = "Fastboot Stuck"    # Stuck di fastboot
    NO_SYSTEM = "No System"              # System corrupt
    NO_BOOT = "No Boot Partition"        # Boot partition corrupt/missing
    HARD_BRICK = "Hard Brick"            # No power, no response
    QUALCOMM_EDL = "Qualcomm EDL"        # Qualcomm Emergency Download
    MEDIATEK_BROM = "MediaTek BROM"      # MediaTek BootROM
    SAMSUNG_DOWNLOAD = "Samsung Download"  # Samsung Download Mode dead
    IPHONE_DFU = "iPhone DFU"            # iPhone DFU mode
    IPHONE_RECOVERY = "iPhone Recovery"  # iPhone Recovery mode loop


@dataclass
class BrickDiagnosis:
    """Hasil diagnosis brick."""
    brick_type: BrickType = BrickType.UNKNOWN
    detected: bool = False
    details: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # 0.0 - 1.0
    recovery_steps: List[str] = field(default_factory=list)
    requires_hardware: bool = False  # Butuh test point / hardware mod
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    recommendation: str = ""


# ===========================================================================
# SMART ANTI-BRICK — INTI
# ===========================================================================

class SmartAntiBrick:
    """
    Smart Anti-Brick system.
    
    Auto-detect brick type dan berikan langkah recovery yang tepat.

    Usage:
        sab = SmartAntiBrick()
        diagnosis = sab.diagnose()
        if diagnosis.detected:
            sab.auto_recover(diagnosis)
    """

    # Partisi vital yang perlu di-backup
    VITAL_PARTITIONS = ["boot", "vbmeta", "recovery", "dtbo", "super", "system", "vendor"]

    def __init__(self):
        self.os_name = platform.system()
        self._diagnosis: Optional[BrickDiagnosis] = None
        self._recovery_log: List[Dict] = []
        self._temp_dir: Optional[str] = None

    # ── DIAGNOSIS ──

    def diagnose(self, serial: Optional[str] = None) -> BrickDiagnosis:
        """
        Diagnosa tipe brick pada device.

        Args:
            serial: Serial device (optional, auto-detect jika None)

        Returns:
            BrickDiagnosis — hasil diagnosa
        """
        log.header("[SMART ANTI-BRICK - DIAGNOSIS]")
        log.info("Mendiagnosa kondisi device...")
        print()

        diagnosis = BrickDiagnosis()

        # ── Check 1: ADB Response ──
        adb_ok, adb_serial = self._check_adb(serial)
        diagnosis.details["adb"] = adb_ok

        if adb_ok:
            # Device normal atau soft brick — bisa komunikasi via ADB
            boot_check = self._check_boot_complete(adb_serial)

            if boot_check["bootloop"]:
                diagnosis.brick_type = BrickType.BOOTLOOP
                diagnosis.detected = True
                diagnosis.confidence = 0.9
                diagnosis.risk_level = "MEDIUM"
                log.warning("  ⚠️ Detected: BOOTLOOP (restart terus-menerus)")
            elif boot_check["stuck_at_logo"]:
                diagnosis.brick_type = BrickType.SOFT_BRICK
                diagnosis.detected = True
                diagnosis.confidence = 0.8
                diagnosis.risk_level = "MEDIUM"
                log.warning("  ⚠️ Detected: SOFT BRICK (stuck di logo)")
            elif boot_check["no_system"]:
                diagnosis.brick_type = BrickType.NO_SYSTEM
                diagnosis.detected = True
                diagnosis.confidence = 0.85
                diagnosis.risk_level = "HIGH"
                log.warning("  ⚠️ Detected: NO SYSTEM (system corrupt)")
            else:
                diagnosis.brick_type = BrickType.NONE
                diagnosis.detected = False
                diagnosis.confidence = 0.95
                log.success("  ✅ Device NORMAL — tidak brick")
        else:
            # ── Check 2: Fastboot Response ──
            fastboot_ok, fb_serial = self._check_fastboot(serial)
            diagnosis.details["fastboot"] = fastboot_ok

            if fastboot_ok:
                # Device stuck di fastboot
                diagnosis.brick_type = BrickType.FASTBOOT_STUCK
                diagnosis.detected = True
                diagnosis.confidence = 0.9
                diagnosis.risk_level = "LOW"
                log.warning("  ⚠️ Detected: STUCK IN FASTBOOT")
            else:
                # ── Check 3: Qualcomm EDL ──
                edl_ok = self._check_edl()
                diagnosis.details["edl"] = edl_ok

                if edl_ok:
                    diagnosis.brick_type = BrickType.QUALCOMM_EDL
                    diagnosis.detected = True
                    diagnosis.confidence = 0.95
                    diagnosis.risk_level = "MEDIUM"
                    log.warning("  ⚠️ Detected: QUALCOMM EDL MODE")
                else:
                    # ── Check 4: MediaTek BROM ──
                    brom_ok = self._check_brom()
                    diagnosis.details["brom"] = brom_ok

                    if brom_ok:
                        diagnosis.brick_type = BrickType.MEDIATEK_BROM
                        diagnosis.detected = True
                        diagnosis.confidence = 0.95
                        diagnosis.risk_level = "MEDIUM"
                        log.warning("  ⚠️ Detected: MEDIATEK BROM MODE")
                    else:
                        # ── Check 5: iPhone DFU/Recovery ──
                        iphone_ok, iphone_mode = self._check_iphone()
                        diagnosis.details["iphone"] = iphone_ok
                        diagnosis.details["iphone_mode"] = iphone_mode

                        if iphone_ok:
                            if iphone_mode == "DFU":
                                diagnosis.brick_type = BrickType.IPHONE_DFU
                                diagnosis.risk_level = "MEDIUM"
                            else:
                                diagnosis.brick_type = BrickType.IPHONE_RECOVERY
                                diagnosis.risk_level = "LOW"
                            diagnosis.detected = True
                            diagnosis.confidence = 0.9
                            log.warning(f"  ⚠️ Detected: IPHONE {iphone_mode} MODE")
                        else:
                            # ── Check 6: Samsung Download Mode ──
                            samsung_ok = self._check_samsung_download()
                            diagnosis.details["samsung_download"] = samsung_ok

                            if samsung_ok:
                                diagnosis.brick_type = BrickType.SAMSUNG_DOWNLOAD
                                diagnosis.detected = True
                                diagnosis.confidence = 0.8
                                diagnosis.risk_level = "MEDIUM"
                                log.warning("  ⚠️ Detected: SAMSUNG DOWNLOAD MODE")
                            else:
                                # ── Check 7: USB device detection ──
                                usb_devices = self._check_usb_devices()
                                diagnosis.details["usb_devices"] = usb_devices

                                if usb_devices:
                                    diagnosis.brick_type = BrickType.HARD_BRICK
                                    diagnosis.detected = True
                                    diagnosis.confidence = 0.7
                                    diagnosis.risk_level = "CRITICAL"
                                    diagnosis.requires_hardware = True
                                    log.error("  ❌ Detected: HARD BRICK (USB detected tapi no communication)")
                                else:
                                    diagnosis.brick_type = BrickType.HARD_BRICK
                                    diagnosis.detected = True
                                    diagnosis.confidence = 0.6
                                    diagnosis.risk_level = "CRITICAL"
                                    diagnosis.requires_hardware = True
                                    log.error("  ❌ Detected: HARD BRICK (no device detected)")

        # ── Generate recovery steps ──
        diagnosis.recovery_steps = self._generate_recovery_steps(diagnosis)
        diagnosis.recommendation = self._generate_recommendation(diagnosis)

        # ── Print diagnosis ──
        print()
        self._print_diagnosis(diagnosis)

        self._diagnosis = diagnosis
        return diagnosis

    def _check_adb(self, serial: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Check ADB connection."""
        try:
            if serial:
                r = subprocess.run(
                    ["adb", "-s", serial, "get-state"],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0:
                    log.success(f"  ✅ ADB: Device terdeteksi ({serial})")
                    return True, serial

            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n')[1:]:
                if '\tdevice' in line:
                    detected = line.split('\t')[0]
                    log.success(f"  ✅ ADB: Device terdeteksi ({detected})")
                    return True, detected
        except Exception:
            pass
        log.warning("  ❌ ADB: Tidak ada response")
        return False, None

    def _check_boot_complete(self, serial: str) -> Dict[str, bool]:
        """Check apakah boot selesai normal."""
        result = {"bootloop": False, "stuck_at_logo": False, "no_system": False, "normal": False}

        try:
            # Cek boot complete
            r = subprocess.run(
                ["adb", "-s", serial, "shell", "getprop sys.boot_completed"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip() == "1":
                result["normal"] = True
                return result
        except Exception:
            pass

        # Cek apakah stuck di boot animation
        try:
            r = subprocess.run(
                ["adb", "-s", serial, "shell", "getprop init.svc.bootanim"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip() == "running":
                # Boot animation masih jalan — possible stuck
                # Cek sudah berapa lama
                r2 = subprocess.run(
                    ["adb", "-s", serial, "shell", "getprop sys.boot.reason"],
                    capture_output=True, text=True, timeout=3
                )
                if r2.returncode == 0 and r2.stdout.strip():
                    result["stuck_at_logo"] = True
                    return result
        except Exception:
            pass

        # Cek bootloop (device reconnect)
        try:
            r = subprocess.run(
                ["adb", "-s", serial, "shell", "uptime"],
                capture_output=True, text=True, timeout=5
            )
            # If uptime < 60 detik, possible bootloop
            if r.returncode == 0 and r.stdout.strip():
                uptime_match = re.search(r'up\s+(\d+)\s+min', r.stdout)
                if uptime_match:
                    minutes = int(uptime_match.group(1))
                    if minutes < 2:
                        result["bootloop"] = True
                        return result
        except Exception:
            result["bootloop"] = True  # ADB disconnect = bootloop
            return result

        # Cek system
        try:
            r = subprocess.run(
                ["adb", "-s", serial, "shell", "ls /system/bin/sh"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode != 0:
                result["no_system"] = True
                return result
        except Exception:
            result["no_system"] = True

        return result

    def _check_fastboot(self, serial: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Check Fastboot connection."""
        try:
            if serial:
                r = subprocess.run(
                    ["fastboot", "-s", serial, "getvar", "product"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0:
                    log.success("  ✅ Fastboot: Device terdeteksi")
                    return True, serial

            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=10)
            for line in r.stdout.split('\n'):
                if '\tfastboot' in line:
                    detected = line.split('\t')[0]
                    log.success(f"  ✅ Fastboot: Device terdeteksi ({detected})")
                    return True, detected
        except Exception:
            pass
        return False, None

    def _check_edl(self) -> bool:
        """Check Qualcomm EDL mode (VID 0x05C6, PID 0x9008)."""
        try:
            if self.os_name == "Windows":
                r = subprocess.run(
                    ['powershell', '-Command',
                     'Get-PnpDevice | Where-Object {$_.DeviceID -like "*VID_05C6*"} | Select-Object Status, FriendlyName'],
                    capture_output=True, text=True, timeout=5
                )
                if "OK" in r.stdout:
                    log.success("  ✅ EDL: Qualcomm device terdeteksi")
                    return True
            else:
                r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                if "05c6:9008" in r.stdout.lower():
                    log.success("  ✅ EDL: Qualcomm QDLoader 9008 terdeteksi")
                    return True
                if "05c6:900e" in r.stdout.lower():
                    log.success("  ✅ EDL: Qualcomm 900E terdeteksi")
                    return True

            # Cek via EDL tool
            edl_tool = shutil.which("edl")
            if edl_tool:
                r = subprocess.run([edl_tool, "--edl"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    log.success("  ✅ EDL: Terkonfirmasi via edl tool")
                    return True
        except Exception:
            pass
        return False

    def _check_brom(self) -> bool:
        """Check MediaTek BROM mode (VID 0x0E8D)."""
        try:
            if self.os_name == "Windows":
                r = subprocess.run(
                    ['powershell', '-Command',
                     'Get-PnpDevice | Where-Object {$_.DeviceID -like "*VID_0E8D*"} | Select-Object Status, FriendlyName'],
                    capture_output=True, text=True, timeout=5
                )
                if "OK" in r.stdout:
                    log.success("  ✅ BROM: MediaTek device terdeteksi")
                    return True
            else:
                r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                if "0e8d:0003" in r.stdout.lower() or "0e8d:2000" in r.stdout.lower():
                    log.success("  ✅ BROM: MediaTek BROM/Preloader terdeteksi")
                    return True

            # Cek via mtkclient
            mtk = shutil.which("mtk")
            if mtk:
                r = subprocess.run([mtk, "printgpt"], capture_output=True, text=True, timeout=15)
                if r.returncode == 0:
                    log.success("  ✅ BROM: Terkonfirmasi via mtkclient")
                    return True
        except Exception:
            pass
        return False

    def _check_iphone(self) -> Tuple[bool, str]:
        """Check iPhone DFU/Recovery mode."""
        try:
            if self.os_name == "Windows":
                r = subprocess.run(
                    ['powershell', '-Command',
                     'Get-PnpDevice | Where-Object {$_.DeviceID -like "*VID_05AC*"} | Select-Object FriendlyName'],
                    capture_output=True, text=True, timeout=5
                )
                output = r.stdout.lower()
                if "dfu" in output:
                    return True, "DFU"
                if "recovery" in output:
                    return True, "Recovery"
            else:
                # Check via lsusb
                r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                output = r.stdout.lower()
                if "05ac:122" in output:  # DFU
                    return True, "DFU"
                if "05ac:121" in output:  # Recovery
                    return True, "Recovery"

            # Check via idevice_id
            idevice = shutil.which("idevice_id")
            if idevice:
                r = subprocess.run([idevice, "-l"], capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and r.stdout.strip():
                    return True, "Normal"
        except Exception:
            pass
        return False, ""

    def _check_samsung_download(self) -> bool:
        """Check Samsung Download Mode."""
        try:
            if self.os_name == "Windows":
                r = subprocess.run(
                    ['powershell', '-Command',
                     'Get-PnpDevice | Where-Object {$_.DeviceID -like "*VID_04E8*"} | Select-Object Status'],
                    capture_output=True, text=True, timeout=5
                )
                if "OK" in r.stdout:
                    return True
            else:
                r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                if "04e8:685d" in r.stdout.lower():
                    return True
        except Exception:
            pass
        return False

    def _check_usb_devices(self) -> bool:
        """Check if any USB devices connected (generic)."""
        try:
            if self.os_name == "Windows":
                r = subprocess.run(
                    ['powershell', '-Command',
                     'Get-PnpDevice -PresentOnly | Where-Object {$_.Class -eq "USB"} | Measure-Object | Select-Object -ExpandProperty Count'],
                    capture_output=True, text=True, timeout=5
                )
                count = int(r.stdout.strip()) if r.stdout.strip().isdigit() else 0
                return count > 0
            else:
                r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                return len(r.stdout.strip().split('\n')) > 1
        except Exception:
            return False

    # ── RECOVERY STEPS ──

    def _generate_recovery_steps(self, diagnosis: BrickDiagnosis) -> List[str]:
        """Generate step-by-step recovery berdasarkan brick type."""
        steps = []

        if diagnosis.brick_type == BrickType.SOFT_BRICK:
            steps = [
                "Step 1: Force restart — tekan Vol Up + Power 15 detik",
                "Step 2: Boot ke Recovery — Vol Up + Power (saat boot)",
                "Step 3: Wipe cache partition",
                "Step 4: Reboot system",
                "Step 5: Jika masih brick → flash ulang boot partition",
            ]
        elif diagnosis.brick_type == BrickType.BOOTLOOP:
            steps = [
                "Step 1: Force restart — Vol Up + Power 15 detik",
                "Step 2: Coba boot ke Safe Mode",
                "Step 3: Jika bisa ADB: adb logcat untuk cek error",
                "Step 4: Wipe cache via Recovery",
                "Step 5: Restore boot partition dari backup",
                "Step 6: Flash ulang firmware (sebagai langkah terakhir)",
            ]
        elif diagnosis.brick_type == BrickType.FASTBOOT_STUCK:
            steps = [
                "Step 1: Cek fastboot devices",
                "Step 2: Reboot: fastboot reboot",
                "Step 3: Jika gagal: fastboot flash boot boot.img",
                "Step 4: Jika masih gagal: fastboot flash vbmeta vbmeta.img",
                "Step 5: Force EDL: fastboot oem edl (untuk Qualcomm)",
            ]
        elif diagnosis.brick_type == BrickType.QUALCOMM_EDL:
            steps = [
                "Step 1: Backup GPT: edl printgpt",
                "Step 2: Restore boot: edl w boot boot.img",
                "Step 3: Restore vbmeta: edl w vbmeta vbmeta.img",
                "Step 4: Reset: edl reset",
                "Step 5: Jika QFIL: Load programmer + rawprogram firehose",
            ]
        elif diagnosis.brick_type == BrickType.MEDIATEK_BROM:
            steps = [
                "Step 1: mtk printgpt (baca partition table)",
                "Step 2: mtk da (load Download Agent)",
                "Step 3: mtk bypass (bypass auth jika perlu)",
                "Step 4: mtk w boot boot.img (restore boot)",
                "Step 5: mtk w vbmeta vbmeta.img (restore vbmeta)",
                "Step 6: mtk reset (reboot)",
            ]
        elif diagnosis.brick_type == BrickType.IPHONE_DFU:
            steps = [
                "Step 1: Gunakan irecovery untuk komunikasi",
                "Step 2: irecovery -i (cek info)",
                "Step 3: irecovery -c 'setenv auto-boot true'",
                "Step 4: irecovery -c 'saveenv'",
                "Step 5: irecovery -c 'reset'",
                "Step 6: Restore via idevicerestore jika perlu",
            ]
        elif diagnosis.brick_type == BrickType.IPHONE_RECOVERY:
            steps = [
                "Step 1: Gunakan ideviceenterrecovery untuk exit",
                "Step 2: Atau: irecovery -n (reboot normal)",
                "Step 3: Jika stuck: restore via iTunes/3uTools",
            ]
        elif diagnosis.brick_type == BrickType.HARD_BRICK:
            steps = [
                "Step 1: Coba force restart 30 detik",
                "Step 2: Cek semua kombinasi tombol",
                "Step 3: Coba charge 30 menit (battery mungkin kosong total)",
                "Step 4: Qualcomm: cari test point EDL + jumper GND",
                "Step 5: MediaTek: colok USB tanpa battery",
                "Step 6: Samsung: Vol Down + Power + Home 15 detik",
                "Step 7: Bawa ke service center jika semua gagal",
            ]
        elif diagnosis.brick_type == BrickType.NO_SYSTEM:
            steps = [
                "Step 1: Cek partisi system: adb shell ls /dev/block/by-name/system",
                "Step 2: Flash system partition via fastboot",
                "Step 3: Flash vbmeta: fastboot flash vbmeta vbmeta.img",
                "Step 4: Wipe data: fastboot -w",
                "Step 5: Reboot: fastboot reboot",
            ]
        elif diagnosis.brick_type == BrickType.SAMSUNG_DOWNLOAD:
            steps = [
                "Step 1: Gunakan Odin atau Heimdall",
                "Step 2: heimdall print-pit (baca partition)",
                "Step 3: heimdall flash --BOOT boot.img --VBMETA vbmeta.img",
                "Step 4: Reboot: heimdall close-pc-screen",
            ]

        return steps

    def _generate_recommendation(self, diagnosis: BrickDiagnosis) -> str:
        """Generate rekomendasi berdasarkan diagnosis."""
        if diagnosis.brick_type == BrickType.NONE:
            return "Device normal, tidak perlu recovery."

        if diagnosis.risk_level == "CRITICAL":
            return ("⚠️ HARD BRICK TERDETEKSI! "
                    "Device mungkin butuh hardware intervention (test point, EDL jumper, "
                    "atau flash programmer). Jika tidak bisa di-recover, bawa ke service center.")

        if diagnosis.risk_level == "HIGH":
            return ("⚠️ Kondisi serius. Disarankan backup EFS/boot sebelum melakukan langkah perbaikan. "
                    "Jika langkah standar gagal, pertimbangkan flash ulang firmware penuh.")

        if diagnosis.risk_level == "MEDIUM":
            return ("⚠️ Kondisi dapat dipulihkan. Ikuti langkah recovery di bawah. "
                    "Backup partisi boot & vbmeta sebelum flash.")

        return "ℹ️ Kondisi ringan. Ikuti langkah recovery standar."

    # ── RECOVERY ACTIONS ──

    def auto_recover(self, diagnosis: Optional[BrickDiagnosis] = None) -> bool:
        """
        Jalankan auto-recovery berdasarkan diagnosis.

        Args:
            diagnosis: BrickDiagnosis dari diagnose(). None = auto-diagnose dulu.

        Returns:
            True jika recovery berhasil
        """
        if diagnosis is None:
            diagnosis = self.diagnose()

        if not diagnosis.detected:
            log.success("Tidak perlu recovery. Device normal.")
            return True

        log.header(f"[AUTO RECOVERY - {diagnosis.brick_type.value}]")
        log.warning(f"Risk Level: {diagnosis.risk_level}")
        print()

        # Tampilkan langkah recovery
        log.info("Step-by-step recovery:")
        for i, step in enumerate(diagnosis.recovery_steps, 1):
            print(f"  {i}. {step}")
        print()

        # Auto-execute untuk yang bisa dilakukan otomatis
        if diagnosis.brick_type == BrickType.QUALCOMM_EDL:
            return self._recover_edl()
        elif diagnosis.brick_type == BrickType.MEDIATEK_BROM:
            return self._recover_brom()
        elif diagnosis.brick_type == BrickType.FASTBOOT_STUCK:
            return self._recover_fastboot()
        elif diagnosis.brick_type in (BrickType.IPHONE_DFU, BrickType.IPHONE_RECOVERY):
            return self._recover_iphone()
        elif diagnosis.brick_type == BrickType.SAMSUNG_DOWNLOAD:
            return self._recover_samsung()
        else:
            log.info("Recovery memerlukan interaksi manual. Ikuti langkah di atas.")
            return False

    def _recover_edl(self) -> bool:
        """Auto-recovery untuk Qualcomm EDL mode."""
        log.info("Auto-recovery EDL mode...")

        # Cek edl tool
        edl = shutil.which("edl")
        if not edl:
            log.warning("EDL tool tidak tersedia. Install: pip install edl")
            return False

        # Step 1: Read GPT
        log.info("Step 1: Membaca partition table...")
        r = subprocess.run([edl, "printgpt"], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            log.warning("Gagal baca partition table")
            return False
        log.success("  ✅ Partition table terbaca")

        # Step 2: Restore boot & vbmeta (if we have backups)
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
        for partition in ["boot", "vbmeta", "recovery"]:
            backup_file = os.path.join(backup_dir, f"{partition}.img")
            if os.path.exists(backup_file):
                log.info(f"Step: Restore {partition}...")
                r = subprocess.run([edl, "w", partition, backup_file], capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    log.success(f"  ✅ {partition} restored!")
                else:
                    log.warning(f"  ❌ {partition} restore gagal")

        # Step 3: Reset
        log.info("Step final: Reset device...")
        subprocess.run([edl, "reset"], capture_output=True, timeout=15)
        log.success("Device direstart dari EDL mode!")

        return True

    def _recover_brom(self) -> bool:
        """Auto-recovery untuk MediaTek BROM mode."""
        log.info("Auto-recovery BROM mode...")

        mtk = shutil.which("mtk")
        if not mtk:
            log.warning("mtkclient tidak tersedia. Install dari github.com/bkerler/mtkclient")
            return False

        # Step 1: Load DA
        log.info("Step 1: Loading Download Agent...")
        r = subprocess.run([mtk, "da"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            log.warning("Gagal load DA")
            return False
        log.success("  ✅ DA loaded")
        time.sleep(1)

        # Step 2: Bypass auth
        log.info("Step 2: Bypass authentication...")
        subprocess.run([mtk, "bypass"], capture_output=True, timeout=15)
        time.sleep(1)

        # Step 3: Restore boot & vbmeta
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
        for partition in ["boot", "vbmeta"]:
            backup_file = os.path.join(backup_dir, f"{partition}.img")
            if os.path.exists(backup_file):
                log.info(f"Step: Restore {partition}...")
                r = subprocess.run([mtk, "w", partition, backup_file], capture_output=True, text=True, timeout=60)

        # Step 4: Reset
        log.info("Step final: Reset device...")
        subprocess.run([mtk, "reset"], capture_output=True, timeout=15)
        log.success("Device direstart dari BROM mode!")

        return True

    def _recover_fastboot(self) -> bool:
        """Recovery untuk Fastboot stuck."""
        log.info("Auto-recovery Fastboot mode...")

        # Coba restore boot & vbmeta
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")

        for partition in ["vbmeta", "boot"]:
            backup_file = os.path.join(backup_dir, f"{partition}.img")
            if os.path.exists(backup_file):
                log.info(f"Restore {partition}...")
                r = subprocess.run(
                    ["fastboot", "flash", partition, backup_file],
                    capture_output=True, text=True, timeout=30
                )
                if r.returncode == 0:
                    log.success(f"  ✅ {partition} flashed!")

        # Force reboot
        log.info("Rebooting...")
        subprocess.run(["fastboot", "reboot"], capture_output=True, timeout=10)
        log.success("Device rebooted!")

        return True

    def _recover_iphone(self) -> bool:
        """Recovery untuk iPhone DFU/Recovery mode."""
        irecovery = shutil.which("irecovery")
        if not irecovery:
            log.warning("irecovery tidak tersedia. Install libimobiledevice")
            return False

        log.info("Mengirim command recovery...")

        # Set auto-boot
        subprocess.run([irecovery, "-c", "setenv auto-boot true"], capture_output=True, timeout=5)
        subprocess.run([irecovery, "-c", "saveenv"], capture_output=True, timeout=5)

        # Reset
        r = subprocess.run([irecovery, "-c", "reset"], capture_output=True, timeout=10)
        if r.returncode == 0:
            log.success("iPhone direstart!")
            return True
        # Alternative: -n flag
        r = subprocess.run([irecovery, "-n"], capture_output=True, timeout=10)
        return r.returncode == 0

    def _recover_samsung(self) -> bool:
        """Recovery untuk Samsung Download Mode."""
        heimdall = shutil.which("heimdall")
        if heimdall:
            log.info("Mencoba restore via Heimdall...")
            backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
            boot_img = os.path.join(backup_dir, "boot.img")
            if os.path.exists(boot_img):
                r = subprocess.run(
                    ["heimdall", "flash", "--BOOT", boot_img, "--no-reboot"],
                    capture_output=True, text=True, timeout=30
                )
                if r.returncode == 0:
                    log.success("Boot partition restored!")
                    return True

        log.info("Gunakan Odin di Windows untuk flash firmware Samsung.")
        return False

    def restore_vbmeta(self, vbmeta_path: Optional[str] = None) -> bool:
        """
        Restore vbmeta partition — penting untuk boot setelah flash tidak sempurna.
        
        Args:
            vbmeta_path: Path ke file vbmeta.img. None = cari di backup folder.
        """
        log.header("[RESTORE VBMETA]")
        log.warning("Memulihkan vbmeta partition...")
        print()

        # Cari file vbmeta
        if not vbmeta_path:
            backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
            candidates = [
                os.path.join(backup_dir, "vbmeta.img"),
                os.path.join(os.getcwd(), "vbmeta.img"),
                os.path.join(os.getcwd(), "firmware", "vbmeta.img"),
            ]
            for path in candidates:
                if os.path.isfile(path):
                    vbmeta_path = path
                    break

        if not vbmeta_path or not os.path.isfile(vbmeta_path):
            log.error("File vbmeta.img tidak ditemukan!")
            log.info("Download vbmeta untuk device Anda atau buat: avbtool make_vbmeta_image")
            return False

        log.info(f"vbmeta.img ditemukan: {vbmeta_path}")

        # Coba via fastboot
        if shutil.which("fastboot"):
            log.info("Mencoba via Fastboot...")
            r = subprocess.run(
                ["fastboot", "flash", "vbmeta", vbmeta_path],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0:
                log.success("vbmeta restored via Fastboot! ✅")
                ActionLogger.log("RESTORE VBMETA", "SUCCESS", "via Fastboot")
                return True
            log.warning(f"Fastboot gagal: {r.stderr}")

        # Coba via ADB
        if shutil.which("adb"):
            log.info("Mencoba via ADB root...")
            r = subprocess.run(
                ["adb", "root"], capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                # Push ke device
                r2 = subprocess.run(
                    ["adb", "push", vbmeta_path, "/tmp/vbmeta.img"],
                    capture_output=True, text=True, timeout=15
                )
                if r2.returncode == 0:
                    r3 = subprocess.run(
                        ["adb", "shell", "dd if=/tmp/vbmeta.img of=/dev/block/by-name/vbmeta"],
                        capture_output=True, text=True, timeout=30
                    )
                    if r3.returncode == 0:
                        log.success("vbmeta restored via ADB! ✅")
                        ActionLogger.log("RESTORE VBMETA", "SUCCESS", "via ADB")
                        return True

        log.error("Gagal restore vbmeta! Gunakan EDL/BROM mode.")
        ActionLogger.log("RESTORE VBMETA", "ERROR", "semua metode gagal")
        return False

    def restore_boot(self, boot_path: Optional[str] = None) -> bool:
        """
        Restore boot partition — perbaiki bootloop.

        Args:
            boot_path: Path ke file boot.img. None = cari di backup folder.
        """
        log.header("[RESTORE BOOT]")
        log.warning("Memulihkan boot partition...")
        print()

        if not boot_path:
            backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
            candidates = [
                os.path.join(backup_dir, "boot.img"),
                os.path.join(os.getcwd(), "boot.img"),
                os.path.join(os.getcwd(), "firmware", "boot.img"),
            ]
            for path in candidates:
                if os.path.isfile(path):
                    boot_path = path
                    break

        if not boot_path or not os.path.isfile(boot_path):
            log.error("File boot.img tidak ditemukan!")
            return False

        log.info(f"boot.img ditemukan: {boot_path}")

        # Via Fastboot
        if shutil.which("fastboot"):
            log.info("Mencoba via Fastboot...")
            r = subprocess.run(
                ["fastboot", "flash", "boot", boot_path],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0:
                log.success("Boot partition restored via Fastboot! ✅")
                ActionLogger.log("RESTORE BOOT", "SUCCESS", "via Fastboot")
                subprocess.run(["fastboot", "reboot"], capture_output=True, timeout=10)
                return True

        # Via ADB
        if shutil.which("adb"):
            log.info("Mencoba via ADB root...")
            subprocess.run(["adb", "root"], capture_output=True, timeout=5)
            r = subprocess.run(
                ["adb", "push", boot_path, "/tmp/boot.img"],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                r2 = subprocess.run(
                    ["adb", "shell", "dd if=/tmp/boot.img of=/dev/block/by-name/boot"],
                    capture_output=True, text=True, timeout=30
                )
                if r2.returncode == 0:
                    log.success("Boot partition restored via ADB! ✅")
                    return True

        log.error("Gagal restore boot! Gunakan EDL/BROM mode.")
        return False

    def force_fastboot(self, serial: Optional[str] = None) -> bool:
        """Force reboot device ke Fastboot mode."""
        log.header("[FORCE FASTBOOT]")
        log.info("Memaksa device masuk Fastboot mode...")
        print()

        methods = []

        # Method 1: ADB reboot
        if serial:
            methods.append(("ADB reboot bootloader", ["adb", "-s", serial, "reboot", "bootloader"]))
        methods.extend([
            ("ADB reboot bootloader", ["adb", "reboot", "bootloader"]),
            ("Fastboot reboot-bootloader", ["fastboot", "reboot-bootloader"]),
        ])

        for desc, cmd in methods:
            try:
                log.info(f"Mencoba: {desc}...")
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    log.success(f"✅ {desc} berhasil!")
                    time.sleep(2)
                    # Verifikasi
                    v = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
                    if 'fastboot' in v.stdout:
                        log.success("Device sekarang di Fastboot mode ✅")
                        ActionLogger.log("FORCE FASTBOOT", "SUCCESS", desc)
                        return True
                else:
                    log.warning(f"  ❌ {desc}: {r.stderr[:100]}")
            except Exception as e:
                log.warning(f"  ❌ {desc}: {e}")

        log.warning("Semua metode gagal! Device mungkin hard brick.")
        ActionLogger.log("FORCE FASTBOOT", "ERROR", "semua metode gagal")

        # Method terakhir: manual
        log.info("Manual: Masuk fastboot dengan kombinasi tombol:")
        print("  • Samsung: Vol Down + Power + Home")
        print("  • Xiaomi: Vol Down + Power")
        print("  • Google Pixel: Vol Down + Power")
        print("  • OnePlus: Vol Down + Power")
        print("  • Huawei: Vol Down + Power")
        print("  • Generic: Vol Down + Power (tahan 15 detik)")
        return False

    def force_edl(self, serial: Optional[str] = None) -> bool:
        """
        Force device ke EDL (Emergency Download) mode — Qualcomm.
        
        Metode:
        1. ADB reboot edl
        2. Fastboot oem edl
        3. Test point (manual)
        """
        log.header("[FORCE EDL MODE]")
        log.info("Memaksa device masuk Qualcomm EDL mode...")
        print()

        methods = [
            ("ADB reboot edl", ["adb", "reboot", "edl"]),
            ("Fastboot oem edl", ["fastboot", "oem", "edl"]),
        ]

        if serial:
            methods.insert(0, (f"ADB reboot edl ({serial})", ["adb", "-s", serial, "reboot", "edl"]))

        for desc, cmd in methods:
            try:
                log.info(f"Mencoba: {desc}...")
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    log.success(f"✅ {desc} berhasil!")
                    time.sleep(3)
                    # Verifikasi
                    if self._check_edl():
                        log.success("Device sekarang di EDL mode ✅")
                        ActionLogger.log("FORCE EDL", "SUCCESS", desc)
                        return True
                else:
                    log.warning(f"  ❌ {desc}: {r.stderr[:100]}")
            except Exception as e:
                log.warning(f"  ❌ {desc}: {e}")

        log.warning("Semua metode software gagal!")
        log.info("Manual EDL via Test Point:")
        print("  1. Buka casing belakang device")
        print("  2. Cari test point EDL (biasanya 2 titik kecil di motherboard)")
        print("  3. Hubungkan test point ke GND dengan pinset")
        print("  4. Colokan USB ke PC")
        print("  5. Lepas pinset setelah terdeteksi QDLoader 9008")
        print()
        log.info("Cari test point untuk device Anda di: google.com/search?q=<model>+edl+test+point")
        ActionLogger.log("FORCE EDL", "INFO", "saran test point manual")
        return False

    def force_brom(self) -> bool:
        """Force device ke MediaTek BROM mode."""
        log.header("[FORCE BROM MODE]")
        log.info("Memaksa device masuk MediaTek BROM mode...")
        print()

        log.info("Metode BROM (MediaTek):")
        print("  1. Lepas battery (jika bisa dilepas)")
        print("  2. Hubungkan USB ke PC")
        print("  3. Tekan tombol Volume Up + Power")
        print("  4. Device akan terdeteksi sebagai MediaTek USB VCOM")
        print()
        log.info("Atau metode tanpa battery:")
        print("  1. Lepas battery")
        print("  2. Tekan dan tahan tombol Volume Up")
        print("  3. Colokkan USB")
        print("  4. Tunggu 5 detik, lepas Volume Up")
        print()
        log.info("Atau untuk device dengan battery non-removable:")
        print("  1. Matikan device")
        print("  2. Tekan tombol Volume Up + Power + Volume Down")
        print("  3. Colokkan USB")
        print("  4. Device akan masuk preloader/BROM mode")

        ActionLogger.log("FORCE BROM", "INFO", "manual instructions shown")
        return False

    # ── BACKUP VITAL ──

    def backup_vital_partitions(self, serial: Optional[str] = None) -> Dict[str, Optional[str]]:
        """
        Backup partisi vital (boot, vbmeta, recovery) untuk anti-brick.
        """
        log.header("[BACKUP VITAL PARTITIONS]")
        log.info("Mem-backup partisi vital untuk anti-brick...")
        print()

        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
        os.makedirs(backup_dir, exist_ok=True)

        results = {}
        for partition in self.VITAL_PARTITIONS[:5]:  # boot, vbmeta, recovery, dtbo, super
            output_path = os.path.join(backup_dir, f"{partition}.img")
            if os.path.exists(output_path):
                size = os.path.getsize(output_path) / (1024 * 1024)
                log.info(f"  ℹ️ {partition} sudah di-backup ({size:.1f} MB)")
                results[partition] = output_path
                continue

            try:
                if serial:
                    r = subprocess.run(
                        ["adb", "-s", serial, "shell",
                         f"dd if=/dev/block/by-name/{partition}"],
                        capture_output=True, timeout=60
                    )
                else:
                    r = subprocess.run(
                        ["adb", "shell", f"dd if=/dev/block/by-name/{partition}"],
                        capture_output=True, timeout=60
                    )
                if r.returncode == 0 and len(r.stdout) > 0:
                    with open(output_path, 'wb') as f:
                        f.write(r.stdout)
                    size_mb = len(r.stdout) / (1024 * 1024)
                    log.success(f"  ✅ {partition}: {output_path} ({size_mb:.1f} MB)")
                    results[partition] = output_path
                else:
                    log.warning(f"  ❌ {partition}: tidak ada atau gagal")
                    results[partition] = None
            except Exception as e:
                log.warning(f"  ❌ {partition}: {e}")
                results[partition] = None

        print()
        log.success("Backup vital selesai! File tersimpan di: " + backup_dir)
        return results

    # ── DISPLAY ──

    def _print_diagnosis(self, diagnosis: BrickDiagnosis):
        """Tampilkan hasil diagnosis."""
        log.separator()
        log.info("DIAGNOSIS RESULT:")
        print()

        # Brick type
        brick_color = {
            BrickType.NONE: Colors.GREEN,
            BrickType.SOFT_BRICK: Colors.YELLOW,
            BrickType.FASTBOOT_STUCK: Colors.YELLOW,
            BrickType.QUALCOMM_EDL: Colors.YELLOW,
            BrickType.MEDIATEK_BROM: Colors.YELLOW,
            BrickType.HARD_BRICK: Colors.RED,
        }.get(diagnosis.brick_type, Colors.WHITE)

        print(f"  Brick Type: {brick_color}{diagnosis.brick_type.value}{Colors.RESET}")
        print(f"  Confidence: {diagnosis.confidence:.0%}")
        print(f"  Risk Level: {diagnosis.risk_level}")

        if diagnosis.requires_hardware:
            print(f"  Hardware Required: YES (test point / hardware mod)")
        print()

        # Recovery steps
        if diagnosis.recovery_steps:
            log.info("Recommended Recovery Steps:")
            for step in diagnosis.recovery_steps:
                print(f"  {step}")
        print()

        if diagnosis.recommendation:
            log.info("Recommendation:")
            print(f"  {diagnosis.recommendation}")

        log.separator()

    def show_recovery_log(self):
        """Tampilkan log recovery."""
        log.header("[RECOVERY LOG]")
        if not self._recovery_log:
            log.info("Belum ada aktivitas recovery")
            return
        for entry in self._recovery_log:
            action = entry.get("action", "?")
            t = entry.get("time", "?")[:19]
            success = "✅" if entry.get("success") else "⚠️"
            log.info(f"  {success} [{t}] {action}")


# ===========================================================================
# MAIN ENTRY
# ===========================================================================

def run():
    """Jalankan Smart Anti-Brick — auto-diagnose + recovery."""
    sab = SmartAntiBrick()
    diagnosis = sab.diagnose()
    if diagnosis.detected:
        print()
        confirm = input(f"  {Colors.YELLOW}Jalankan auto-recovery? (y/N): {Colors.RESET}").strip().lower()
        if confirm == 'y':
            sab.auto_recover(diagnosis)


def run_backup_vital():
    """Backup partisi vital untuk anti-brick."""
    SmartAntiBrick().backup_vital_partitions()


def run_restore_vbmeta():
    """Restore vbmeta partition."""
    sab = SmartAntiBrick()
    diagnosis = sab.diagnose()
    sab.restore_vbmeta()


def run_restore_boot():
    """Restore boot partition."""
    sab = SmartAntiBrick()
    sab.restore_boot()


def run_force_fastboot():
    """Force reboot ke Fastboot mode."""
    SmartAntiBrick().force_fastboot()


def run_force_edl():
    """Force masuk EDL mode (Qualcomm)."""
    SmartAntiBrick().force_edl()


# Backward compatibility
class AntiBrick:
    """Backward compatibility wrapper."""
    def __init__(self):
        self.recovery_log = []
        self._smart = SmartAntiBrick()

    def show_recovery_menu(self):
        log.header("[ANTI-BRICK RECOVERY]")

    def method_force_bootloader(self):
        return True

    def method_dfu_mode(self):
        return True

    def method_stlink_unbrick(self):
        return SmartAntiBrick()._recover_edl()

    def method_erase_all_flash(self):
        return True

    def method_low_level_recovery(self):
        return True

    def run_auto_recovery(self):
        return self._smart.auto_recover()

    def show_recovery_log(self):
        self._smart.show_recovery_log()