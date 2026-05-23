
""" 
NST EMERGENCY RECOVERY SYSTEM v1
=================================
Fitur darurat untuk menangani masalah koneksi device:
- Kill ADB zombie processes
- Restart ADB/Fastboot services
- Clean temp files
- Reinstall device drivers
- Force reboot device (ADB/Fastboot/Recovery/EDL)
- Force kill semua proses Apple/Android yang hang
"""

import os
import time
import platform
import subprocess
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

from core.logger import log, Colors
from core.safety import ActionLogger


class EmergencyRecovery:
    """Emergency Recovery System"""

    def __init__(self) -> None:
        self.os_name = platform.system()
        self.results: Dict[str, bool] = {}

    def kill_adb_zombie(self) -> bool:
        """Kill semua proses ADB yang zombie/hang"""
        log.info("Mematikan proses ADB zombie...")
        success = False

        try:
            if self.os_name == "Windows":
                # Hentikan ADB server dulu
                subprocess.run(["adb", "kill-server"], capture_output=True, timeout=5)
                time.sleep(0.5)

                # Kill task ADB via taskkill
                for proc in ["adb.exe", "adb"]:
                    r = subprocess.run(
                        ["taskkill", "/F", "/IM", proc],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if r.returncode == 0:
                        log.success(f"  [OK] {proc} dimatikan")
                        success = True

                # Kill juga proses terkait
                for proc in ["fastboot.exe", "fastboot"]:
                    subprocess.run(
                        ["taskkill", "/F", "/IM", proc],
                        capture_output=True,
                        timeout=3,
                    )

            elif self.os_name == "Linux":
                subprocess.run(["pkill", "-9", "adb"], capture_output=True, timeout=5)
                subprocess.run(
                    ["pkill", "-9", "fastboot"], capture_output=True, timeout=5
                )
                success = True
            else:  # Mac
                subprocess.run(["pkill", "-9", "adb"], capture_output=True, timeout=5)
                subprocess.run(
                    ["pkill", "-9", "fastboot"], capture_output=True, timeout=5
                )
                success = True

            # Bersihkan file lock
            lock_file = os.path.expanduser("~/.android/adb.lock")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    log.success("  [OK] ADB lock file dibersihkan")
                except Exception:
                    pass

            time.sleep(1)
            log.success("ADB zombie berhasil dibersihkan!")

        except Exception as e:
            log.warning(f"Gagal kill ADB: {e}")

        return success

    def restart_adb_service(self) -> bool:
        """Restart ADB server dari awal"""
        log.info("Merestart ADB server...")

        try:
            # Kill dulu
            subprocess.run(["adb", "kill-server"], capture_output=True, timeout=5)
            time.sleep(1)

            # Start server baru
            r = subprocess.run(
                ["adb", "start-server"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            time.sleep(1)

            if r.returncode == 0:
                log.success("ADB server berhasil direstart!")

                # Verifikasi
                r2 = subprocess.run(
                    ["adb", "devices"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                devices = [
                    l for l in r2.stdout.split("\n") if "\tdevice" in l
                ]
                if devices:
                    log.success(f"Device terdeteksi: {len(devices)} perangkat")
                else:
                    log.info("Tidak ada device, tapi ADB server sudah jalan.")

                return True

            log.warning(f"Gagal restart ADB: {r.stderr}")
            return False

        except FileNotFoundError:
            log.warning("ADB tidak terinstall!")
            return False
        except Exception as e:
            log.warning(f"Error restart ADB: {e}")
            return False

    def clean_temp_files(self) -> Dict[str, Any]:
        """Bersihkan file temporary yang bisa mengganggu koneksi"""
        log.info("Membersihkan file temporary...")
        results = {"cleaned": [], "failed": [], "total_size_mb": 0}

        # Folder yang perlu dibersihkan
        temp_dirs = []

        if self.os_name == "Windows":
            temp_dirs = [
                os.environ.get("TEMP", ""),
                os.environ.get("TMP", ""),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp"),
            ]
        elif self.os_name == "Linux":
            temp_dirs = ["/tmp"]
        else:  # Mac
            temp_dirs = ["/tmp", os.path.expanduser("~/Library/Caches")]

        for temp_dir in temp_dirs:
            if not temp_dir or not os.path.exists(temp_dir):
                continue
            try:
                total_size = 0
                count = 0
                for root, dirs, files in os.walk(temp_dir):
                    for f in files:
                        fpath = os.path.join(root, f)
                        try:
                            size = os.path.getsize(fpath)
                            os.remove(fpath)
                            total_size += size
                            count += 1
                        except (PermissionError, OSError):
                            results["failed"].append(fpath)

                    # Hapus folder kosong
                    for d in dirs:
                        try:
                            dpath = os.path.join(root, d)
                            if os.path.isdir(dpath) and not os.listdir(dpath):
                                os.rmdir(dpath)
                        except Exception:
                            pass

                size_mb = round(total_size / (1024 * 1024), 1)
                if count > 0:
                    results["cleaned"].append(
                        f"{temp_dir}: {count} files, {size_mb} MB"
                    )
                    results["total_size_mb"] += size_mb
                    log.success(f"  [OK] {temp_dir}: {count} files ({size_mb} MB)")

            except Exception as e:
                log.warning(f"  [X] {temp_dir}: {e}")

        return results

    def force_reboot_device(self, mode: str = "normal") -> bool:
        """Force reboot device ke mode tertentu."""
        log.info(f"Force reboot device ke mode: {mode.upper()}...")

        if mode == "normal":
            commands = [
                (["adb", "reboot"], "Reboot normal via ADB"),
                (["fastboot", "reboot"], "Reboot via Fastboot"),
            ]
        elif mode == "recovery":
            commands = [
                (["adb", "reboot", "recovery"], "Reboot ke Recovery via ADB"),
            ]
        elif mode == "bootloader":
            commands = [
                (["adb", "reboot", "bootloader"], "Reboot ke Bootloader via ADB"),
            ]
        elif mode == "edl":
            commands = [
                (["adb", "reboot", "edl"], "Reboot ke EDL via ADB"),
                (["fastboot", "oem", "edl"], "EDL via Fastboot"),
            ]
        elif mode == "download":
            commands = [
                (["adb", "reboot", "download"], "Reboot ke Download Mode via ADB"),
            ]
        else:
            log.warning(f"Mode '{mode}' tidak dikenal!")
            return False

        for cmd, desc in commands:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    log.success(f"  [OK] {desc}")
                    ActionLogger.log("EMERGENCY REBOOT", "SUCCESS", f"Mode: {mode}")
                    return True
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                log.warning(f"  [X] {desc} - timeout")
                continue
            except Exception as e:
                log.warning(f"  [X] {desc} - {e}")
                continue

        log.warning(f"Gagal reboot ke mode {mode}")
        ActionLogger.log("EMERGENCY REBOOT", "ERROR", f"Mode: {mode} - gagal")
        return False

    def kill_apple_processes(self) -> bool:
        """Kill proses Apple yang hang (iTunes, MobileDevice, dll)"""
        if self.os_name != "Windows":
            return False

        log.info("Mematikan proses Apple yang hang...")
        apple_procs = [
            "iTunes.exe",
            "iTunesHelper.exe",
            "AppleMobileDeviceService.exe",
            "AppleMobileBackup.exe",
            "APSDaemon.exe",
            "ApplePush.exe",
        ]

        success = False
        for proc in apple_procs:
            try:
                r = subprocess.run(
                    ["taskkill", "/F", "/IM", proc],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if r.returncode == 0:
                    log.success(f"  [OK] {proc} dimatikan")
                    success = True
            except Exception:
                pass

        return success

    def reset_usb_ports(self) -> bool:
        """Reset port USB via devcon / PowerShell"""
        if self.os_name != "Windows":
            log.info("Linux/Mac: Cabut dan colok kembali USB device.")
            return False

        log.info("Merestart port USB...")
        try:
            # Coba restart via devcon jika ada
            devcon_paths = [
                r"C:\\Program Files (x86)\\Windows Kits\\10\\Tools\\x64\\devcon.exe",
                r"C:\\Program Files\\Windows Kits\\10\\Tools\\x64\\devcon.exe",
            ]
            for dp in devcon_paths:
                if os.path.exists(dp):
                    r = subprocess.run(
                        [dp, "restart", "USB\\*"],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    if r.returncode == 0:
                        log.success("USB ports berhasil direstart!")
                        return True
        except Exception:
            pass

        # Fallback: PowerShell restart USB
        try:
            ps_cmd = '''
            Get-PnpDevice -PresentOnly | Where-Object {$_.Class -eq "USB"} | 
            ForEach-Object { Disable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false; 
                             Enable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false }
            '''
            r = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                log.success("USB controllers berhasil di-restart!")
                return True
        except Exception:
            pass

        log.warning("Tidak bisa restart USB otomatis.")
        log.info("Cabut dan colok kembali USB device secara manual.")
        return False

    def run_full_emergency(self) -> Dict[str, Any]:
        """Jalankan semua langkah emergency secara berurutan"""
        log.header("[EMERGENCY RECOVERY - FULL]")
        log.warning("Menjalankan semua langkah pemulihan darurat...")
        print()

        results: Dict[str, object] = {}

        # Step 1: Kill ADB zombie
        log.info("Step 1/6: Membunuh proses ADB/Fastboot zombie...")
        r1 = self.kill_adb_zombie()
        results["kill_adb"] = r1
        print()

        # Step 2: Kill Apple processes
        log.info("Step 2/6: Mematikan proses Apple yang hang...")
        r2 = self.kill_apple_processes()
        results["kill_apple"] = r2
        print()

        # Step 3: Restart ADB server
        log.info("Step 3/6: Merestart ADB server...")
        r3 = self.restart_adb_service()
        results["restart_adb"] = r3
        print()

        # Step 4: Clean temp files
        log.info("Step 4/6: Membersihkan file temporary...")
        r4 = self.clean_temp_files()
        results["clean_temp"] = r4.get("total_size_mb", 0) > 0
        if r4.get("total_size_mb", 0) > 0:
            log.success(f"  {r4['total_size_mb']} MB dibersihkan")
        print()

        # Step 5: Reset USB ports
        log.info("Step 5/6: Mereset port USB...")
        r5 = self.reset_usb_ports()
        results["reset_usb"] = r5
        print()

        # Step 6: Scan devices
        log.info("Step 6/6: Scanning perangkat...")
        try:
            from core.device_detector import DeviceDetector
            devices = DeviceDetector().scan_all()
            results["devices_found"] = len(devices) if devices else 0
            if devices:
                log.success(f"{len(devices)} perangkat terdeteksi!")
            else:
                log.warning("Tidak ada perangkat terdeteksi.")
                log.info("Coba: 1. Ganti kabel USB | 2. Ganti port | 3. Restart PC")
        except Exception as e:
            log.warning(f"Scan device error: {e}")
            results["devices_found"] = 0
        print()

        # Optional: Reboot detected device
        if results.get("devices_found", 0) > 0:
            log.info("🔄 Ingin reboot perangkat yang terdeteksi?")
            try:
                confirm = input(f"  {Colors.YELLOW}Reboot device sekarang? (y/N): {Colors.RESET}").strip().lower()
                if confirm == "y":
                    self.force_reboot_device("normal")
                    results["reboot"] = True
                else:
                    results["reboot"] = False
            except Exception:
                results["reboot"] = False
            print()

        # Summary
        success_count = sum(1 for v in results.values() if isinstance(v, bool) and v)
        log.separator()
        log.info("RINGKASAN EMERGENCY RECOVERY:")
        log.success(f"  {success_count} dari {len(results)} langkah berhasil")
        if results.get("devices_found", 0) > 0:
            log.success(f"  Device terdeteksi: {results['devices_found']}")
        else:
            log.warning("  Device TIDAK terdeteksi. Coba langkah manual.")
            print()
            log.info("Langkah manual selanjutnya:")
            print("  1. Restart PC")
            print("  2. Ganti kabel USB (pakai kabel DATA, bukan charger-only)")
            print("  3. Install ulang driver device")
            print("  4. Coba di PC lain untuk memastikan")

        ActionLogger.log("EMERGENCY FULL", "SUCCESS" if success_count > 3 else "WARNING",
                         f"{success_count}/{len(results)} steps OK")

        return results


# ========== RETRY HANDLER ==========

class RetryHandler:
    """
    Retry otomatis dengan exponential backoff untuk operasi yang gagal.
    - Maksimal N kali percobaan
    - Delay bertambah exponensial (2^attempt detik)
    - Max delay 60 detik
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.attempt = 0

    def execute(self, func: Callable, *args, context: str = "", **kwargs) -> Any:
        """Eksekusi fungsi dengan retry logic"""
        last_error = None

        while self.attempt < self.max_retries:
            try:
                if self.attempt > 0:
                    delay = min(self.base_delay * (2 ** (self.attempt - 1)), self.max_delay)
                    log.info(f"  Retry ke-{self.attempt + 1} dalam {delay:.0f} detik...")
                    time.sleep(delay)

                result = func(*args, **kwargs)
                if self.attempt > 0:
                    log.success(f"  Berhasil setelah retry ke-{self.attempt + 1}!")
                self.attempt = 0  # Reset untuk penggunaan berikutnya
                return result

            except Exception as e:
                last_error = e
                self.attempt += 1
                log.warning(f"  [{context or func.__name__}] Percobaan {self.attempt}/{self.max_retries} gagal: {e}")

                if self.attempt >= self.max_retries:
                    log.error(f"  Semua {self.max_retries} percobaan gagal untuk '{context or func.__name__}'")
                    raise last_error

        return None

    def reset(self) -> None:
        """Reset counter attempt"""
        self.attempt = 0


class RecoveryCheckpoint:
    """
    Checkpoint system untuk operasi multi-step.
    Jika salah satu step gagal, bisa rollback ke checkpoint terakhir.
    """

    def __init__(self) -> None:
        self.checkpoints: List[Dict[str, str]] = []

    def begin(self, operation: str) -> None:
        """Mulai operasi baru"""
        self.checkpoints = []
        log.info(f">>> Mulai operasi: {operation}")
        self._save_checkpoint(operation, "BEGIN")

    def checkpoint(self, step_name: str) -> None:
        """Simpan checkpoint setelah step berhasil"""
        self._save_checkpoint(step_name, "CHECKPOINT")
        log.success(f"  Checkpoint: {step_name}")

    def _save_checkpoint(self, step: str, status: str) -> None:
        """Simpan checkpoint ke internal list"""
        self.checkpoints.append({
            "step": step,
            "status": status,
            "timestamp": datetime.now().isoformat(),
        })

    def undo_last(self, rollback_func: Optional[Callable] = None) -> Optional[str]:
        """
        Rollback ke checkpoint terakhir.
        Jika ada rollback_func, panggil dengan nama step.
        Returns nama step yang di-rollback, atau None.
        """
        if not self.checkpoints:
            log.warning("Tidak ada checkpoint untuk di-rollback")
            return None

        # Hapus checkpoint terakhir (yang gagal)
        self.checkpoints.pop()

        if self.checkpoints:
            # Dapatkan checkpoint terakhir yang berhasil
            last_good = self.checkpoints[-1]
            step_name = last_good["step"]

            log.warning(f"Rollback ke checkpoint: {step_name}...")

            if rollback_func:
                try:
                    rollback_func(step_name)
                    log.success(f"  Rollback ke '{step_name}' berhasil")
                except Exception as e:
                    log.warning(f"  Rollback function error: {e}")

            return step_name
        else:
            log.warning("Checkpoint pertama gagal. Tidak ada yang bisa di-rollback.")
            return None

    def rollback_all(self, rollback_func: Optional[Callable] = None) -> None:
        """Rollback semua checkpoint dari yang terakhir"""
        log.warning("Rollback SEMUA checkpoint...")
        while self.checkpoints:
            self.undo_last(rollback_func)
        log.info("Rollback selesai.")

    def get_progress(self) -> str:
        """Dapatkan progress dalam format string"""
        total = len(self.checkpoints)
        completed = sum(1 for c in self.checkpoints if c["status"] == "CHECKPOINT")
        if total == 0:
            return "0/0"
        return f"{completed}/{total - 1}"  # -1 untuk BEGIN

    def get_last_step(self) -> Optional[str]:
        """Dapatkan step terakhir yang berhasil"""
        for c in reversed(self.checkpoints):
            if c["status"] == "CHECKPOINT":
                return c["step"]
        return None



# ========== MAIN MENU ENTRY ==========
#
# ARSITEKTUR: 1 MENU = 1 FITUR
# Setiap fungsi di bawah adalah SATU aksi spesifik, dipanggil langsung dari main.py
# TIDAK ADA SUB-MENU atau input loop di dalam fungsi-fungsi ini!
#

# Emergency Action Wrappers — dipanggil dari main.py sebagai menu individual

def run_full_emergency() -> None:
    """
    Aksi: Jalankan FULL EMERGENCY RECOVERY (semua langkah otomatis)
    Menu: 32 (Emergency Recovery)
    """
    EmergencyRecovery().run_full_emergency()


def run_kill_adb_zombie() -> None:
    """
    Aksi: Matikan proses ADB yang hang/zombie
    """
    log.header("[KILL ADB ZOMBIE]")
    EmergencyRecovery().kill_adb_zombie()


def run_restart_adb() -> None:
    """
    Aksi: Restart ADB server dari awal
    """
    log.header("[RESTART ADB SERVER]")
    EmergencyRecovery().restart_adb_service()


def run_clean_temp() -> None:
    """
    Aksi: Bersihkan file temporary yang bisa mengganggu koneksi
    """
    log.header("[CLEAN TEMP FILES]")
    results = EmergencyRecovery().clean_temp_files()
    if results['total_size_mb'] > 0:
        log.success(f"Total: {results['total_size_mb']} MB dibersihkan")


def run_reset_usb() -> None:
    """
    Aksi: Reset/restart port USB
    """
    log.header("[RESET USB PORTS]")
    EmergencyRecovery().reset_usb_ports()


def run_kill_apple() -> None:
    """
    Aksi: Matikan proses Apple yang hang (iTunes, MobileDevice, dll)
    """
    log.header("[KILL APPLE PROCESSES]")
    EmergencyRecovery().kill_apple_processes()


def run() -> None:
    """
    [DEPRECATED] Panggil run_full_emergency langsung.
    Fungsi ini dipertahankan untuk backward compatibility.
    """
    run_full_emergency()
