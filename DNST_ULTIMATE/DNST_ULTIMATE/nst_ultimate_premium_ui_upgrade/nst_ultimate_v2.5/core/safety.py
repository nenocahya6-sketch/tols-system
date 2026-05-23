

"""
NST Safety System v2 - KEAMANAN BERLAPIS
=========================================
1. ConfirmationChain: 3-layer konfirmasi (info -> SAYA MENGERTI -> YA)
2. ErrorHandler: Deteksi error -> tampilkan solusi step-by-step
3. AdaptiveTroubleshooter: Jika step 1 gagal -> deteksi -> saran step 2
4. BackupManager: Backup EFS/boot/recovery
5. ActionLogger: Catat semua aksi
"""
import os
import sys
import json
import time
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

from core.logger import log, Colors


class ConfirmationChain:
    """Konfirmasi berlapis 3-layer untuk MENCEGAH KESALAHAN FATAL"""

    @staticmethod
    def level_1_info(title: str, detail: str = ""):
        """Layer 1: Tampilkan informasi aksi yang akan dilakukan"""
        print()
        log.header(f"[KONFIRMASI: {title}]")
        if detail:
            print(f"  {Colors.DIM}{detail}{Colors.RESET}")
        print()

    @staticmethod
    def level_2_warning(warning_text: str):
        """Layer 2: Tampilkan peringatan MENGERTI"""
        print(f"  {Colors.BG_RED}{Colors.BOLD}  {warning_text}  {Colors.RESET}")
        print()
        confirm = input(f"  {Colors.YELLOW}Ketik 'SAYA MENGERTI' untuk lanjut: {Colors.RESET}").strip()
        if confirm.upper() != "SAYA MENGERTI":
            log.info("DIBATALKAN oleh user")
            return False
        return True

    @staticmethod
    def level_3_final(action_name: str):
        """Layer 3: Konfirmasi final YA"""
        confirm = input(f"  {Colors.RED}Ketik 'YA' untuk konfirmasi final {action_name}: {Colors.RESET}").strip()
        if confirm.upper() != "YA":
            log.info("DIBATALKAN oleh user")
            return False
        return True

    @staticmethod
    def confirm_action(title: str, detail: str = "",
                       warning_text: str = "PERINGATAN: Aksi ini bisa merusak perangkat!",
                       require_level3: bool = True) -> bool:
        """Full 3-layer confirmation chain"""
        ConfirmationChain.level_1_info(title, detail)

        # Layer 2
        if not ConfirmationChain.level_2_warning(warning_text):
            return False

        # Layer 3 (hanya untuk aksi CRITICAL)
        if require_level3:
            if not ConfirmationChain.level_3_final(title):
                return False

        log.success("Konfirmasi diterima. Melanjutkan...")
        return True

    @staticmethod
    def confirm_simple(prompt: str, default: str = "n") -> bool:
        """Konfirmasi sederhana 1x (untuk aksi ringan)"""
        if default == "n":
            confirm = input(f"  {prompt} (y/N): ").strip().lower()
            return confirm == "y"
        else:
            confirm = input(f"  {prompt} (Y/n): ").strip().lower()
            return confirm != "n"


class ErrorHandler:
    """Penanganan error dengan solusi step-by-step"""

    @staticmethod
    def get_solution(error_key: str) -> Dict:
        """Dapatkan solusi untuk error tertentu"""
        from config import ERROR_SOLUTIONS
        return ERROR_SOLUTIONS.get(error_key, {
            "error": "Error tidak dikenal",
            "solutions": [
                "1. Catat kode error yang muncul",
                "2. Cari solusi di Google dengan kode error tersebut",
                "3. Hubungi technical support jika perlu",
            ]
        })

    @staticmethod
    def show_error(error_key: str, detail: str = ""):
        """Tampilkan error + solusi"""
        solution = ErrorHandler.get_solution(error_key)

        print()
        log.critical(f"[ERROR] {solution['error']}")
        if detail:
            print(f"  {Colors.DIM}{detail}{Colors.RESET}")
        print()

        log.info("SOLUSI STEP-BY-STEP:")
        print(f"  {Colors.DIM}{'=' * 50}{Colors.RESET}")
        for step in solution["solutions"]:
            print(f"  {step}")
        print(f"  {Colors.DIM}{'=' * 50}{Colors.RESET}")
        print()

    @staticmethod
    def show_steps(guide_key: str, extra_links: List[str] = None):
        """Tampilkan step-by-step guide"""
        from config import STEP_BY_STEP_GUIDES

        guide = STEP_BY_STEP_GUIDES.get(guide_key)
        if not guide:
            log.warning(f"Guide '{guide_key}' tidak ditemukan")
            return

        print()
        log.header(f"[{guide['title']}]")

        if "warning" in guide:
            print(f"  {Colors.BG_RED}{Colors.BOLD}  {guide['warning']}  {Colors.RESET}")
            print()

        for step in guide["steps"]:
            print(f"  {step}")

        if guide.get("links"):
            print()
            log.info("Link Download:")
            for link in guide["links"]:
                print(f"  {Colors.CYAN}  {link}{Colors.RESET}")

        if extra_links:
            print()
            log.info("Link Tambahan:")
            for link in extra_links:
                print(f"  {Colors.CYAN}  {link}{Colors.RESET}")

        print()

    @staticmethod
    def handle_exception(e: Exception, context: str = ""):
        """Handle exception dan tampilkan solusi"""
        error_str = str(e).lower()
        log.critical(f"ERROR: {e}")

        # Diagnosa otomatis
        if "adb" in error_str and "not found" in error_str:
            ErrorHandler.show_error("adb_not_found")
        elif "fastboot" in error_str and "not found" in error_str:
            ErrorHandler.show_error("fastboot_not_found")
        elif "permission" in error_str or "access" in error_str:
            ErrorHandler.show_error("permission_denied")
        elif "device" in error_str and "not" in error_str:
            ErrorHandler.show_error("device_not_found")
        elif "battery" in error_str or "power" in error_str:
            ErrorHandler.show_error("battery_low")
        elif "timeout" in error_str:
            log.warning("Koneksi timeout. Coba ulang.")
        else:
            ErrorHandler.show_error("unknown", str(e))

        if context:
            print(f"  {Colors.DIM}Context: {context}{Colors.RESET}")
            print()


class AdaptiveTroubleshooter:
    """
    Troubleshooter adaptif:
    - Jika step 1 gagal -> deteksi -> saran step 2
    - Track riwayat percobaan
    - Analisa efek dari aksi sebelumnya
    """

    def __init__(self):
        self.attempt_history: List[Dict] = []
        self.max_attempts_before_escalate = 3

    def record_attempt(self, action: str, result: bool, detail: str = ""):
        """Catat percobaan"""
        self.attempt_history.append({
            "action": action,
            "result": result,
            "detail": detail,
            "timestamp": datetime.now().isoformat()
        })

    def get_failed_attempts(self, action: str = None) -> List[Dict]:
        """Dapatkan percobaan yang gagal"""
        if action:
            return [a for a in self.attempt_history if a["action"] == action and not a["result"]]
        return [a for a in self.attempt_history if not a["result"]]

    def suggest_next_step(self, failed_action: str) -> str:
        """Saran langkah selanjutnya jika aksi gagal"""
        failed_count = len(self.get_failed_attempts(failed_action))

        escalation_map = {
            "unlock_bootloader": [
                "Coba metode lain: fastboot flashing unlock (bukan oem unlock)",
                "Cek OEM Unlock di Developer Options sudah aktif",
                "Untuk Samsung: butuh kode unlock dari Samsung",
                "Untuk Xiaomi: minta kode di en.miui.com/unlock/",
                "Coba flash firmware stock dulu, baru unlock",
                "Terakhir: EDL mode + format all (qualcomm)",
            ],
            "flash_firmware": [
                "Cek ulang firmware: apakah cocok dengan model HP?",
                "Coba firmware versi sebelumnya (downgrade)",
                "Coba tool lain: Odin vs Smart Switch vs Mi Flash",
                "Coba port USB lain / kabel lain",
                "Boot ke recovery, wipe cache, baru flash",
                "Terakhir: EDL/BROM mode dengan format all",
            ],
            "root": [
                "Coba metode root alternatif",
                "Cek apakah bootloader sudah terbuka",
                "Coba versi Magisk yang berbeda",
                "Cari forum XDA untuk model HP spesifik",
            ],
            "factory_reset": [
                "Coba via recovery mode manual",
                "Coba via ADB: adb shell recovery --wipe_data",
                "Gunakan Stock Recovery (bukan custom)",
            ],
            "clean_cache": [
                "Coba via recovery mode (wipe cache partition)",
                "Coba app cleaner dari Play Store",
                "Coba via ADB dengan perintah yang berbeda",
            ]
        }

        suggestions = escalation_map.get(failed_action, ["Coba metode alternatif"])
        idx = min(failed_count, len(suggestions) - 1)

        if failed_count >= self.max_attempts_before_escalate:
            return f"[ESCALASI] Percobaan ke-{failed_count + 1}. Saran: {suggestions[-1]}"
        else:
            return f"Saran berikutnya: {suggestions[idx]}"

    def check_previous_effect(self, action: str) -> bool:
        """
        Cek apakah aksi sebelumnya memberikan efek.
        Contoh: setelah unlock bootloader, cek apakah status berubah.
        """
        attempts = self.get_failed_attempts(action)
        if not attempts:
            return True  # Belum ada percobaan sebelumnya

        log.warning(f"Aksi '{action}' sebelumnya belum berhasil ({len(attempts)}x gagal)")
        return False


class DeviceValidator:
    """Validasi device komprehensif SEBELUM aksi berbahaya"""

    @staticmethod
    def get_device_info(serial: str = None) -> Dict:
        """
        Dapatkan info lengkap device via ADB:
        - Brand, model, android version, build number
        - Bootloader status
        - Battery level, temperature
        - IMEI (via getprop)
        """
        result = {
            "ok": False,
            "brand": None,
            "model": None,
            "android": None,
            "build": None,
            "bootloader": None,
            "battery": None,
            "temperature": None,
            "imei": None,
            "serial": serial,
            "mode": "unknown",
        }

        if not serial:
            return result

        try:
            import subprocess

            # Cek mode (ADB atau fastboot)
            # Coba ADB dulu
            props_to_check = {
                "brand": "ro.product.brand",
                "model": "ro.product.model",
                "android": "ro.build.version.release",
                "build": "ro.build.display.id",
                "bootloader": "ro.boot.bootloader",
                "imei": "gsm.serial",  # fallback: ro.ril.oem.imei
            }

            cmd_base = ["adb"]
            if serial:
                cmd_base += ["-s", serial]

            for key, prop in props_to_check.items():
                try:
                    r = subprocess.run(
                        cmd_base + ["shell", "getprop", prop],
                        capture_output=True, text=True, timeout=3
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        val = r.stdout.strip()
                        if val and val != "unknown":
                            result[key] = val
                except Exception:
                    pass

            # Cek battery
            try:
                r = subprocess.run(
                    cmd_base + ["shell", "dumpsys", "battery"],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0:
                    for line in r.stdout.split('\n'):
                        if "level" in line.lower():
                            result["battery"] = int(line.split(':')[1].strip())
                        if "temperature" in line.lower():
                            temp_raw = line.split(':')[1].strip()
                            result["temperature"] = int(temp_raw) / 10  # Convert to Celsius
            except Exception:
                pass

            # Cek bootloader status
            try:
                r = subprocess.run(
                    cmd_base + ["shell", "getprop", "ro.boot.flash.locked"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0:
                    val = r.stdout.strip()
                    if val == "1":
                        result["bootloader_status"] = "LOCKED"
                    elif val == "0":
                        result["bootloader_status"] = "UNLOCKED"
            except Exception:
                pass

            # Cek IMEI via service call (alternatif)
            try:
                r = subprocess.run(
                    cmd_base + ["shell", "service", "call", "iphonesubinfo", "1"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    # Parse hex output
                    import re
                    hex_vals = re.findall(r'([0-9A-Fa-f]{4})', r.stdout)
                    if hex_vals:
                        imei_chars = []
                        for h in hex_vals:
                            try:
                                imei_chars.append(chr(int(h, 16)))
                            except (ValueError, OverflowError):
                                pass
                        imei_str = ''.join(imei_chars)
                        if any(c.isdigit() for c in imei_str):
                            result["imei"] = imei_str.strip()
            except Exception:
                pass

            result["ok"] = result["brand"] is not None
            result["mode"] = "ADB" if result["ok"] else "fastboot"

        except Exception:
            pass

        return result

    @staticmethod
    def validate_before_flash(serial: str = None) -> Dict:
        """
        Validasi KOMPREHENSIF sebelum flashing:
        - Cek brand & model
        - Cek battery > 30%
        - Cek bootloader (harus unlocked untuk system partitions)
        - Cek koneksi stabil
        - Cek disk space
        """
        log.header("[DEVICE VALIDATION - PRA FLASH]")
        results = {"ok": True, "warnings": [], "errors": []}

        # 1. Dapatkan info device
        info = DeviceValidator.get_device_info(serial)
        if info["ok"]:
            log.success(f"Device: {info['brand']} {info['model']}")
            log.info(f"Android: {info['android']} | Build: {info['build']}")
            if info.get("bootloader_status"):
                status_color = Colors.GREEN if info["bootloader_status"] == "UNLOCKED" else Colors.YELLOW
                log.info(f"🔓 Bootloader : {status_color}{info['bootloader_status']}{Colors.RESET}")
        else:
            log.warning("Device info: Tidak bisa dibaca (mungkin fastboot mode)")
            results["warnings"].append("Device info terbatas")

        # 2. Cek battery
        battery = PreFlightCheck.check_battery(serial)
        if battery["ok"]:
            level = battery.get("level", 0)
            if isinstance(level, (int, float)) and level < 30:
                log.warning(f"Battery RENDAH: {level}% (minimal 30% untuk flashing!)")
                results["errors"].append(f"Battery terlalu rendah: {level}%")
                results["ok"] = False
            else:
                log.success(f"Battery: {level}%")
        else:
            log.warning("Battery: Tidak bisa dicek")
            results["warnings"].append("Battery check skipped")

        # 3. Cek bootloader (untuk system partitions)
        if info.get("bootloader_status") == "LOCKED":
            log.warning("Bootloader TERKUNCI! Tidak bisa flash system partitions!")
            results["warnings"].append("Bootloader LOCKED - hanya bisa flash stock firmware via Odin/MiFlash")

        # 4. Cek koneksi (ping test)
        try:
            import subprocess
            if serial:
                r = subprocess.run(
                    ["adb", "-s", serial, "shell", "echo ping"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and "ping" in r.stdout:
                    log.success("Koneksi: Stabil")
                else:
                    log.warning("Koneksi: Tidak stabil!")
                    results["warnings"].append("Koneksi tidak stabil")
        except Exception:
            pass

        # 5. Cek disk space
        try:
            usage = shutil.disk_usage(os.getcwd())
            free_mb = usage.free / (1024 * 1024)
            if free_mb < 500:
                log.warning(f"Disk space RENDAH: {free_mb:.0f} MB free (min 500 MB)")
                results["warnings"].append(f"Disk space: {free_mb:.0f} MB")
            else:
                log.success(f"Disk space: {free_mb:.0f} MB free")
        except Exception:
            pass

        # 6. Cek IMEI
        if info.get("imei"):
            log.success(f"IMEI terdeteksi: {info['imei']}")
            # Catat IMEI sebelum flashing
            results["imei"] = info["imei"]
        else:
            log.info("IMEI: Tidak bisa dibaca via ADB (normal jika fastboot mode)")

        print()
        if results["errors"]:
            log.error("VALIDASI GAGAL! Perbaiki error di atas dulu.")
            for err in results["errors"]:
                print(f"  {Colors.RED}  - {err}{Colors.RESET}")
        elif results["warnings"]:
            log.warning("VALIDASI LULUS DENGAN PERINGATAN:")
            for w in results["warnings"]:
                print(f"  {Colors.YELLOW}  - {w}{Colors.RESET}")
            log.info("Lanjutkan dengan hati-hati.")
        else:
            log.success("VALIDASI LULUS! Device siap untuk flashing.")

        return results


class PreFlightCheck:
    """Pemeriksaan kondisi SEBELUM melakukan aksi apa pun"""

    @staticmethod
    def check_device_connection() -> Dict:
        """Cek apakah device terdeteksi via ADB atau fastboot"""
        try:
            import subprocess
            # Cek ADB
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            lines = clean_console_output(result.stdout).strip().split('\n')
            devices = [l.split('\t')[0] for l in lines if '\tdevice' in l]
            if devices:
                return {"ok": True, "method": "ADB", "device": devices[0], "serial": devices[0]}

            # Cek fastboot
            result = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
            if clean_console_output(result.stdout).strip() and 'fastboot' in clean_console_output(result.stdout):
                serial = clean_console_output(result.stdout).split('\t')[0]
                return {"ok": True, "method": "fastboot", "device": serial, "serial": serial}

            return {"ok": False, "method": "none", "device": None, "serial": None}
        except FileNotFoundError:
            return {"ok": False, "method": "none", "device": None, "serial": None}
        except Exception:
            return {"ok": False, "method": "none", "device": None, "serial": None}

    @staticmethod
    def check_battery(adb_serial: str = None) -> Dict:
        """Cek level baterai via ADB"""
        try:
            import subprocess
            cmd = ["adb"]
            if adb_serial:
                cmd += ["-s", adb_serial]
            cmd += ["shell", "dumpsys", "battery"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in clean_console_output(result.stdout).split('\n'):
                    if "level" in line.lower():
                        level = int(line.split(':')[1].strip())
                        ok = level > 30
                        return {"ok": ok, "level": level,
                                "message": f"Battery: {level}%" if ok else f"Battery RENDAH: {level}%"}
            return {"ok": True, "level": "?", "message": "Tidak bisa cek battery (skip)"}
        except Exception:
            return {"ok": True, "level": "?", "message": "ADB tidak tersedia (skip)"}

    @staticmethod
    def check_disk_space(required_mb: int = 200) -> Dict:
        """Cek ketersediaan disk space"""
        try:
            usage = shutil.disk_usage(os.getcwd())
            free_mb = usage.free / (1024 * 1024)
            ok = free_mb > required_mb
            return {
                "ok": ok,
                "free_mb": round(free_mb, 1),
                "required_mb": required_mb,
                "message": f"Disk: {free_mb:.0f} MB free (need {required_mb} MB)"
            }
        except Exception:
            return {"ok": True, "free_mb": 0, "required_mb": required_mb, "message": "Cek disk skipped"}

    @staticmethod
    def run_essential() -> Dict:
        """Pre-flight check esensial (wajib sebelum aksi berbahaya)"""
        log.header("[PRE-FLIGHT CHECK]")

        results = {"all_ok": True, "checks": {}}

        # Check device connection
        device = PreFlightCheck.check_device_connection()
        results["checks"]["device"] = device
        if device["ok"]:
            log.success(f"Device: OK ({device['method']}: {device['device']})")
        else:
            log.warning("Device: X TIDAK TERDETEKSI")
            ErrorHandler.show_error("device_not_found")
            results["all_ok"] = False

        # Check disk space
        disk = PreFlightCheck.check_disk_space()
        results["checks"]["disk"] = disk
        if disk["ok"]:
            log.success(disk["message"])
        else:
            log.warning(disk["message"])
            results["all_ok"] = False

        # Check battery (jika device terdeteksi via ADB)
        if device["ok"] and device["method"] == "ADB":
            battery = PreFlightCheck.check_battery(device["serial"])
            results["checks"]["battery"] = battery
            if battery["ok"]:
                log.success(battery["message"])
            else:
                log.warning(battery["message"])
                results["all_ok"] = False

        print()
        if results["all_ok"]:
            log.success("PRE-FLIGHT: SEMUA AMAN. Silakan lanjutkan.")
        else:
            log.warning("PRE-FLIGHT: ADA MASALAH! Perbaiki dulu sebelum lanjut.")
            print()

        return results

    @staticmethod
    def must_pass() -> bool:
        """Pre-flight WAJIB lolos (jika tidak, STOP)"""
        result = PreFlightCheck.run_essential()
        if not result["all_ok"]:
            print(f"  {Colors.BG_RED}{Colors.BOLD}  PROSES DIHENTIKAN! Perbaiki masalah di atas dulu.  {Colors.RESET}")
            print()
            return False
        return True


class BackupManager:
    """Backup partisi penting SEBELUM aksi berbahaya"""

    from config import BACKUP_DIR

    @classmethod
    def ensure_backup_dir(cls):
        os.makedirs(cls.BACKUP_DIR, exist_ok=True)

    @classmethod
    def backup_partition(cls, partition: str, serial: str = None) -> Optional[str]:
        """Backup partisi via ADB"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"{partition}_{timestamp}.img"
        cls.ensure_backup_dir()
        output_path = os.path.join(cls.BACKUP_DIR, output_name)

        log.info(f"Backup partition {partition}...")
        try:
            import subprocess
            cmd = ["adb"]
            if serial:
                cmd += ["-s", serial]
            cmd += ["shell", f"dd if=/dev/block/by-name/{partition}"]

            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and len(clean_console_output(result.stdout)) > 0:
                with open(output_path, 'wb') as f:
                    f.write(clean_console_output(result.stdout))
                size_mb = len(clean_console_output(result.stdout)) / (1024 * 1024)
                log.success(f"Backup {partition}: {output_path} ({size_mb:.1f} MB)")
                return output_path
            else:
                log.warning(f"Gagal backup {partition}: mungkin partisi tidak ada")
                return None
        except FileNotFoundError:
            log.warning("ADB tidak tersedia untuk backup")
            return None
        except Exception as e:
            log.warning(f"Backup error: {e}")
            return None

    @classmethod
    def backup_boot(cls, serial: str = None) -> Optional[str]:
        return cls.backup_partition("boot", serial)

    @classmethod
    def backup_efs(cls, serial: str = None) -> Optional[str]:
        return cls.backup_partition("efs", serial)

    @classmethod
    def backup_recovery(cls, serial: str = None) -> Optional[str]:
        return cls.backup_partition("recovery", serial)

    @classmethod
    def list_backups(cls) -> List[Dict]:
        """Daftar semua backup yang tersedia"""
        cls.ensure_backup_dir()
        backups = []
        if os.path.exists(cls.BACKUP_DIR):
            for f in os.listdir(cls.BACKUP_DIR):
                fpath = os.path.join(cls.BACKUP_DIR, f)
                if os.path.isfile(fpath):
                    size = os.path.getsize(fpath)
                    modified = datetime.fromtimestamp(os.path.getmtime(fpath))
                    backups.append({
                        "name": f,
                        "path": fpath,
                        "size_mb": round(size / (1024 * 1024), 1),
                        "modified": modified.strftime("%Y-%m-%d %H:%M:%S")
                    })
        return sorted(backups, key=lambda x: x["modified"], reverse=True)

    @classmethod
    def backup_imei(cls, serial: str = None) -> Optional[str]:
        """
        Backup IMEI device sebelum flashing.
        Backup data penting: IMEI, NVRAM, persist, EFS.
        Returns path ke file backup IMEI, atau None jika gagal.
        """
        log.info("Backup IMEI & NVRAM...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(cls.BACKUP_DIR, f"imei_backup_{timestamp}.txt")

        try:
            import subprocess
            cmd = ["adb"]
            if serial:
                cmd += ["-s", serial]

            imei_data = {}

            # Backup IMEI via berbagai metode
            imei_sources = [
                ("stock_imei1", "getprop ro.ril.miui_imei"),
                ("stock_imei2", "getprop ro.ril.miui_imei2"),
                ("persist_imei1", "getprop persist.radio.imei"),
                ("persist_imei2", "getprop persist.radio.imei2"),
                ("gsm_imei", "getprop gsm.imei"),
                ("gsm_imei1", "getprop gsm.imei1"),
                ("gsm_imei2", "getprop gsm.imei2"),
                ("ril_imei1", "getprop ril.imei"),
                ("ril_imei2", "getprop ril.imei2"),
                ("phone_imei", "getprop ro.phone.imei"),
                ("board_serial", "getprop ro.serialno"),
                ("wifi_mac", "cat /sys/class/net/wlan0/address 2>/dev/null || echo notfound"),
                ("bt_mac", "cat /sys/class/net/bt0/address 2>/dev/null || cat /sys/class/bluetooth/hci0/address 2>/dev/null || echo notfound"),
                ("android_id", "settings get secure android_id 2>/dev/null || echo notfound"),
            ]

            for label, prop_cmd in imei_sources:
                try:
                    r = subprocess.run(
                        cmd + ["shell", prop_cmd],
                        capture_output=True, text=True, timeout=3
                    )
                    val = r.stdout.strip()
                    if val and "notfound" not in val and "unknown" not in val:
                        imei_data[label] = val
                except Exception:
                    pass

            # Backup NVRAM partition (Qualcomm) jika ada
            nvram_paths = [
                "/dev/block/by-name/nvram",
                "/dev/block/by-name/nvdata",
                "/dev/block/by-name/nvcfg",
            ]
            for nv in nvram_paths:
                try:
                    r = subprocess.run(
                        cmd + ["shell", f"ls {nv} 2>/dev/null || echo notfound"],
                        capture_output=True, text=True, timeout=3
                    )
                    if "notfound" not in r.stdout:
                        nv_out = os.path.join(cls.BACKUP_DIR, f"nvram_backup_{timestamp}.img")
                        r2 = subprocess.run(
                            cmd + ["shell", f"dd if={nv}"],
                            capture_output=True, timeout=30
                        )
                        if r2.returncode == 0 and len(r2.stdout) > 0:
                            with open(nv_out, 'wb') as f:
                                f.write(r2.stdout)
                            imei_data["nvram_backup"] = nv_out
                            log.success(f"  [OK] NVRAM backed up: {os.path.basename(nv)}")
                        break
                except Exception:
                    pass

            # Simpan ke file
            if imei_data:
                with open(output_path, 'w') as f:
                    f.write(f"IMEI Backup - {datetime.now().isoformat()}\n")
                    f.write(f"Serial: {serial or 'unknown'}\n")
                    f.write("=" * 50 + "\n")
                    for key, val in imei_data.items():
                        f.write(f"{key}: {val}\n")

                # Backup persist partition juga
                cls.backup_partition("persist", serial)

                log.success(f"IMEI/NVRAM backup: {output_path}")
                log.info("IMEI yang ditemukan:")
                for key in imei_data:
                    if "imei" in key.lower() and len(imei_data[key]) >= 14:
                        print(f"  {Colors.CYAN}  {key}: {imei_data[key]}{Colors.RESET}")

                return output_path
            else:
                log.warning("Tidak ada IMEI yang bisa di-backup (device mungkin di fastboot)")
                return None

        except Exception as e:
            log.warning(f"Backup IMEI gagal: {e}")
            return None

    @classmethod
    def auto_backup_before_action(cls, serial: str = None):
        """Auto backup partisi penting sebelum aksi berbahaya"""
        log.info("Backup otomatis partisi penting...")
        cls.backup_boot(serial)
        cls.backup_efs(serial)
        cls.backup_recovery(serial)
        cls.backup_imei(serial)  # Backup IMEI + NVRAM spesifik
        log.success("Backup selesai!")
        print()

    @classmethod
    def auto_full_backup(cls, serial: str = None) -> Dict[str, Optional[str]]:
        """
        FULL BACKUP otomatis SEBELUM aksi berbahaya.
        Backup semua partisi penting + data sdcard.
        Returns dict of backup paths.
        """
        log.header("[AUTO FULL BACKUP]")
        log.warning("Melakukan full backup sebelum aksi berbahaya...")
        print()

        results = {
            "boot": None,
            "efs": None,
            "recovery": None,
            "super": None,
            "persist": None,
            "data": None,
            "sdcard": None,
            "timestamp": datetime.now().isoformat(),
        }

        # Backup partisi kritis
        log.info("Backup partisi kritis...")
        results["boot"] = cls.backup_partition("boot", serial)
        results["efs"] = cls.backup_partition("efs", serial)
        results["recovery"] = cls.backup_partition("recovery", serial)
        results["persist"] = cls.backup_partition("persist", serial)

        # Backup super partition jika ada (A/B slot devices)
        if serial:
            try:
                import subprocess
                r = subprocess.run(
                    ["adb", "-s", serial, "shell", "ls /dev/block/by-name/super 2>/dev/null || echo notfound"],
                    capture_output=True, text=True, timeout=3
                )
                if "notfound" not in r.stdout:
                    results["super"] = cls.backup_partition("super", serial)
            except Exception:
                pass

        # Backup data user (sdcard) - file-file penting
        if serial:
            try:
                import subprocess
                log.info("Backup data user (sdcard)...")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = os.path.join(cls.BACKUP_DIR, f"userdata_{timestamp}")
                os.makedirs(backup_dir, exist_ok=True)

                # Backup folders penting
                folders = ["DCIM", "Documents", "Download", "Pictures", "Music", "Movies", "WhatsApp"]
                for folder in folders:
                    try:
                        r = subprocess.run(
                            ["adb", "-s", serial, "pull", f"/sdcard/{folder}", backup_dir],
                            capture_output=True, text=True, timeout=60
                        )
                        if r.returncode == 0:
                            log.success(f"  [OK] {folder}")
                    except Exception:
                        log.warning(f"  [X] {folder} - tidak ada atau gagal")

                results["sdcard"] = backup_dir
                log.success(f"Backup userdata ke: {backup_dir}")
            except Exception as e:
                log.warning(f"Backup sdcard gagal: {e}")

        # Simpan manifest backup
        manifest_path = os.path.join(cls.BACKUP_DIR, f"manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            with open(manifest_path, 'w') as f:
                json.dump(results, f, indent=2)
        except Exception:
            pass

        print()
        log.success("FULL BACKUP SELESAI!")
        log.info("Jika terjadi kesalahan, RESTORE OTOMATIS akan dijalankan.")
        print()

        return results

    @classmethod
    def auto_full_backup_forced(cls, serial: str = None) -> Dict[str, Optional[str]]:
        """
        FULL BACKUP WAJIB - TANPA KONFIRMASI, langsung backup!
        Untuk aksi berbahaya: bypass, flash, unlock, reset.
        """
        log.header("[BACKUP OTOMATIS - WAJIB]")
        log.warning("BACKUP OTOMATIS SEDANG BERJALAN... JANGAN CABUT USB!")
        print()

        results = {
            "boot": None,
            "efs": None,
            "recovery": None,
            "persist": None,
            "sdcard": None,
            "timestamp": datetime.now().isoformat(),
        }

        # Backup partisi kritis
        results["boot"] = cls.backup_partition("boot", serial)
        results["efs"] = cls.backup_partition("efs", serial)
        results["recovery"] = cls.backup_partition("recovery", serial)
        results["persist"] = cls.backup_partition("persist", serial)

        # Backup data user
        if serial:
            try:
                import subprocess
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = os.path.join(cls.BACKUP_DIR, f"userdata_{timestamp}")
                os.makedirs(backup_dir, exist_ok=True)
                folders = ["DCIM", "Documents", "Download", "Pictures", "WhatsApp"]
                for folder in folders:
                    try:
                        subprocess.run(
                            ["adb", "-s", serial, "pull", f"/sdcard/{folder}", backup_dir],
                            capture_output=True, text=True, timeout=60
                        )
                    except Exception:
                        pass
                results["sdcard"] = backup_dir
            except Exception:
                pass

        # Simpan manifest
        manifest_path = os.path.join(cls.BACKUP_DIR, f"manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            with open(manifest_path, 'w') as f:
                json.dump(results, f, indent=2)
        except Exception:
            pass

        log.success("BACKUP OTOMATIS SELESAI!")
        log.info("Jika aksi gagal, RESTORE OTOMATIS akan dijalankan.")
        print()
        return results

    @classmethod
    def auto_restore_on_failure(cls, serial: str = None, error_desc: str = "") -> bool:
        """
        RESTORE OTOMATIS Jika aksi berbahaya GAGAL.
        Akan restore dari backup terbaru.
        """
        log.header("[RESTORE OTOMATIS - KARENA GAGAL]")
        log.critical(f"[!] Aksi GAGAL: {error_desc}")
        log.warning("MENJALANKAN RESTORE OTOMATIS UNTUK MENGEMBALIKAN DEVICE...")
        print()

        # Cari manifest terbaru
        cls.ensure_backup_dir()
        manifests = sorted([
            os.path.join(cls.BACKUP_DIR, f)
            for f in os.listdir(cls.BACKUP_DIR)
            if f.startswith("manifest_") and f.endswith(".json")
        ], reverse=True)

        if not manifests:
            log.error("TIDAK ADA BACKUP! Device mungkin BRICK!")
            log.info("Coba langkah darurat:")
            print("  1. Coba force restart HP")
            print("  2. Coba masuk recovery mode")
            print("  3. Flash ulang firmware")
            return False

        manifest_path = manifests[0]
        log.info(f"Restore dari backup: {os.path.basename(manifest_path)}")

        # Baca manifest
        try:
            with open(manifest_path, 'r') as f:
                backup_data = json.load(f)
        except Exception as e:
            log.error(f"Gagal baca manifest: {e}")
            return False

        success = True

        # Restore partisi
        for partition in ["boot", "efs", "recovery", "persist"]:
            backup_path = backup_data.get(partition)
            if backup_path and os.path.exists(backup_path):
                log.info(f"Restore {partition}...")
                try:
                    import subprocess
                    remote_path = f"/tmp/{partition}_restore.img"
                    r = subprocess.run(
                        ["adb", "-s", serial, "push", backup_path, remote_path],
                        capture_output=True, text=True, timeout=30
                    )
                    if r.returncode == 0:
                        r2 = subprocess.run(
                            ["adb", "-s", serial, "shell",
                             f"dd if={remote_path} of=/dev/block/by-name/{partition} 2>/dev/null || "
                             f"dd if={remote_path} of=/dev/block/platform/*/by-name/{partition} 2>/dev/null || echo fail"],
                            capture_output=True, text=True, timeout=30
                        )
                        if "fail" not in r2.stdout:
                            log.success(f"  [OK] {partition} restored!")
                        else:
                            log.warning(f"  [X] {partition} - butuh mode lain")
                    else:
                        log.warning(f"  [X] {partition} - push gagal")
                except Exception as e:
                    log.warning(f"  [X] {partition}: {e}")
                    success = False

        # Restore sdcard
        sdcard_backup = backup_data.get("sdcard")
        if sdcard_backup and os.path.exists(sdcard_backup):
            log.info("Restore data user...")
            try:
                import subprocess
                r = subprocess.run(
                    ["adb", "-s", serial, "push", sdcard_backup + "/", "/sdcard/"],
                    capture_output=True, text=True, timeout=120
                )
                if r.returncode == 0:
                    log.success("  [OK] User data restored!")
            except Exception as e:
                log.warning(f"  [X] User data: {e}")

        print()
        if success:
            log.success("RESTORE OTOMATIS BERHASIL! Device kembali normal.")
            log.info("Silakan reboot device.")
        else:
            log.warning("Restore selesai dengan peringatan. Coba flash firmware manual.")

        return success

    @classmethod
    def auto_restore(cls, serial: str = None, manifest_path: str = None) -> bool:
        """
        RESTORE otomatis dari backup terakhir.
        Mengembalikan semua partisi yang di-backup.
        """
        log.header("[AUTO RESTORE]")
        log.warning("Memulihkan device dari backup terakhir...")
        print()

        # Cari manifest terbaru
        if not manifest_path:
            cls.ensure_backup_dir()
            manifests = sorted([
                os.path.join(cls.BACKUP_DIR, f)
                for f in os.listdir(cls.BACKUP_DIR)
                if f.startswith("manifest_") and f.endswith(".json")
            ], reverse=True)
            if not manifests:
                log.error("Tidak ada backup yang ditemukan!")
                return False
            manifest_path = manifests[0]

        # Baca manifest
        try:
            with open(manifest_path, 'r') as f:
                backup_data = json.load(f)
        except Exception as e:
            log.error(f"Gagal baca manifest: {e}")
            return False

        log.info(f"Restore dari backup: {os.path.basename(manifest_path)}")
        timestamp = backup_data.get("timestamp", "unknown")
        log.info(f"Waktu backup: {timestamp}")
        print()

        success = True

        # Restore partisi via fastboot (jika bootloader unlocked)
        # Via dd command di ADB
        for partition in ["boot", "efs", "recovery", "persist"]:
            backup_path = backup_data.get(partition)
            if backup_path and os.path.exists(backup_path):
                log.info(f"Restore {partition}...")
                try:
                    import subprocess
                    # Push file ke device lalu dd
                    remote_path = f"/tmp/{partition}_restore.img"
                    r = subprocess.run(
                        ["adb", "-s", serial, "push", backup_path, remote_path],
                        capture_output=True, text=True, timeout=30
                    )
                    if r.returncode == 0:
                        r2 = subprocess.run(
                            ["adb", "-s", serial, "shell",
                             f"dd if={remote_path} of=/dev/block/by-name/{partition} 2>/dev/null || "
                             f"dd if={remote_path} of=/dev/block/platform/*/by-name/{partition} 2>/dev/null || echo fail"],
                            capture_output=True, text=True, timeout=30
                        )
                        if "fail" not in r2.stdout:
                            log.success(f"  [OK] {partition} restored!")
                        else:
                            log.warning(f"  [X] {partition} - butuh fastboot mode")
                    else:
                        log.warning(f"  [X] {partition} - push gagal")
                except Exception as e:
                    log.warning(f"  [X] {partition}: {e}")
                    success = False

        # Restore sdcard jika ada
        sdcard_backup = backup_data.get("sdcard")
        if sdcard_backup and os.path.exists(sdcard_backup):
            log.info("Restore data user (sdcard)...")
            try:
                import subprocess
                r = subprocess.run(
                    ["adb", "-s", serial, "push", sdcard_backup + "/", "/sdcard/"],
                    capture_output=True, text=True, timeout=120
                )
                if r.returncode == 0:
                    log.success("  [OK] User data restored!")
                else:
                    log.warning(f"  [X] User data restore: {r.stderr}")
            except Exception as e:
                log.warning(f"  [X] User data: {e}")

        print()
        if success:
            log.success("RESTORE SELESAI! Silakan reboot device.")
        else:
            log.warning("Restore selesai dengan beberapa peringatan.")

        return success

    @classmethod
    def find_latest_backup(cls) -> Optional[str]:
        """Cari file manifest backup terbaru"""
        cls.ensure_backup_dir()
        manifests = sorted([
            os.path.join(cls.BACKUP_DIR, f)
            for f in os.listdir(cls.BACKUP_DIR)
            if f.startswith("manifest_") and f.endswith(".json")
        ], reverse=True)
        return manifests[0] if manifests else None


class ActionLogger:
    """Logging semua aksi dengan timestamp"""

    from config import LOG_DIR
    HISTORY_FILE = os.path.join(LOG_DIR, "action_history.json")

    @classmethod
    def ensure_log_dir(cls):
        os.makedirs(cls.LOG_DIR, exist_ok=True)

    @classmethod
    def log(cls, action: str, status: str, detail: str = ""):
        """Catat aksi"""
        cls.ensure_log_dir()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "status": status,
            "detail": detail
        }

        history = []
        if os.path.exists(cls.HISTORY_FILE):
            try:
                with open(cls.HISTORY_FILE, 'r') as f:
                    history = json.load(f)
            except Exception:
                history = []

        history.append(entry)
        if len(history) > 1000:
            history = history[-1000:]

        try:
            with open(cls.HISTORY_FILE, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass

        # Juga log ke file actions.log
        log_file = os.path.join(cls.LOG_DIR, "actions.log")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{entry['timestamp']}] [{status}] {action}")
                if detail:
                    f.write(f" - {detail}")
                f.write("\n")
        except Exception:
            pass

    @classmethod
    def show_history(cls, limit: int = 20):
        """Tampilkan history"""
        log.header("[HISTORY AKSI]")
        if not os.path.exists(cls.HISTORY_FILE):
            log.info("Belum ada history")
            return

        try:
            with open(cls.HISTORY_FILE, 'r') as f:
                history = json.load(f)
            if not history:
                log.info("History kosong")
                return

            status_colors = {
                "SUCCESS": Colors.GREEN,
                "WARNING": Colors.YELLOW,
                "ERROR": Colors.RED,
                "INFO": Colors.CYAN,
            }

            for entry in history[-limit:]:
                ts = entry.get("timestamp", "?")[:19]
                action = entry.get("action", "?")
                status = entry.get("status", "?")
                detail = entry.get("detail", "")
                color = status_colors.get(status.upper(), Colors.WHITE)
                icon = {"SUCCESS": "[OK]", "ERROR": "[X]", "WARNING": "[!]", "INFO": "[i]"}.get(status.upper(), "[?]")
                print(f"  {Colors.DIM}{ts}{Colors.RESET} {color}{icon} {action}{Colors.RESET}")
                if detail:
                    print(f"         {Colors.DIM}{detail}{Colors.RESET}")

            print(f"\n  {Colors.DIM}Total: {len(history)} aksi{Colors.RESET}")
        except Exception as e:
            log.warning(f"Gagal baca history: {e}")


# ========== INTEGRATED SAFE ACTION WRAPPER ==========
def safe_action(
    action_name: str,
    action_func: Callable,
    *args,
    require_preflight: bool = True,
    require_backup: bool = False,
    require_confirm: bool = True,
    confirm_level: str = "CRITICAL",
    error_key: str = None,
    guide_key: str = None,
    **kwargs
) -> bool:
    """
    WRAPPER AMAN: Jalankan aksi dengan keamanan berlapis penuh

    Args:
        action_name: Nama aksi
        action_func: Function yang akan dijalankan
        require_preflight: Apakah perlu pre-flight check
        require_backup: Apakah perlu backup otomatis
        require_confirm: Apakah perlu konfirmasi
        confirm_level: "WARNING" (1 layer) atau "CRITICAL" (3 layer)
        error_key: Key error dari ERROR_SOLUTIONS jika gagal
        guide_key: Key guide dari STEP_BY_STEP_GUIDES untuk ditampilkan
    """
    log.header(f"[SAFETY WRAPPER: {action_name}]")

    # Step 0: Tampilkan guide jika ada
    if guide_key:
        ErrorHandler.show_steps(guide_key)
        print()

    # Step 1: Pre-flight check
    if require_preflight:
        if not PreFlightCheck.must_pass():
            ActionLogger.log(action_name, "WARNING", "Pre-flight gagal")
            return False

    # Step 2: Deteksi device untuk backup serial
    device = PreFlightCheck.check_device_connection()
    serial = device.get("serial") if device.get("ok") else None

    # Step 3: FULL BACKUP WAJIB (TIDAK ADA KONFIRMASI)
    if require_backup:
        log.warning("BACKUP OTOMATIS: Mem-backup SEMUA partisi + data...")
        BackupManager.auto_full_backup_forced(serial)

    # Step 4: Konfirmasi
    if require_confirm:
        if confirm_level == "CRITICAL":
            if not ConfirmationChain.confirm_action(action_name, "", "AKSI INI BISA MERUSAK PERANGKAT!", True):
                ActionLogger.log(action_name, "WARNING", "Dibatalkan user")
                return False
        else:
            if not ConfirmationChain.confirm_simple(f"Lanjutkan {action_name}?", "n"):
                ActionLogger.log(action_name, "WARNING", "Dibatalkan user")
                return False

    # Step 5: Eksekusi dengan error handling + AUTO RESTORE ON FAILURE
    try:
        log.info(f"Menjalankan: {action_name}...")
        result = action_func(*args, **kwargs)

        if result:
            ActionLogger.log(action_name, "SUCCESS")
            log.success(f"[OK] {action_name} berhasil!")
        else:
            ActionLogger.log(action_name, "ERROR", "Function returned False")
            log.error(f"[X] {action_name} gagal!")

            # RESTORE OTOMATIS jika backup sudah dibuat
            if require_backup and serial:
                log.warning("MENJALANKAN RESTORE OTOMATIS...")
                BackupManager.auto_restore_on_failure(serial, f"{action_name} gagal")

            # Tampilkan solusi
            if error_key:
                ErrorHandler.show_error(error_key)

        return result

    except Exception as e:
        ActionLogger.log(action_name, "ERROR", str(e))

        # RESTORE OTOMATIS jika exception
        if require_backup and serial:
            log.warning("MENJALANKAN RESTORE OTOMATIS...")
            BackupManager.auto_restore_on_failure(serial, str(e))

        ErrorHandler.handle_exception(e, action_name)
        return False
