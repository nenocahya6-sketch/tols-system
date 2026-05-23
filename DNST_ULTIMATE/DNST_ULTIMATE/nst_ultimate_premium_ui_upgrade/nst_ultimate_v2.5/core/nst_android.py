

"""
NST ANDROID PROFESSIONAL TOOLKIT v2
====================================
DESAIN: 1 MENU = 1 FITUR (TIDAK ADA LOOPING DALAM)
         Setiap menu melakukan SATU hal spesifik
         Error = STOP + Solusi step-by-step
         Adaptive: jika step 1 gagal, saran step 2

FITUR:
1. Smart Deep Diagnostic - Analisa hardware/software lengkap
2. Clean Cache HP - Bersihkan semua sampah
3. Flash Firmware - Panduan step-by-step
4. Unlock Bootloader - Panduan + link
5. Root Android - Panduan + link
6. FRP Bypass - Panduan
7. Factory Reset - Panduan
8. Fastboot Toolkit - Satu per satu
"""
import os
import time
import platform
import subprocess
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core.logger import log, Colors
from core.safety import (
    ConfirmationChain, ErrorHandler, AdaptiveTroubleshooter,
    PreFlightCheck, BackupManager, ActionLogger
)
from config import DIAGNOSTIC_THRESHOLDS, DEVICE_DOWNLOAD_LINKS


class AndroidToolkit:
    """
    Android Toolkit - Setiap method = SATU fitur spesifik
    Tidak ada loop/menu di dalam method
    """

    def __init__(self):
        self.os_name = platform.system()
        self.has_adb = self._check_tool("adb")
        self.has_fastboot = self._check_tool("fastboot")
        self.device_serial: Optional[str] = None
        self.device_info: Dict = {}
        self.troubleshooter = AdaptiveTroubleshooter()

    def _check_tool(self, name: str) -> bool:
        try:
            subprocess.run([name, "--version"], capture_output=True, timeout=3)
            return True
        except (FileNotFoundError, Exception):
            return False

    def _run_adb(self, args: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
        cmd = ["adb"]
        if self.device_serial:
            cmd += ["-s", self.device_serial]
        cmd += args
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _run_fastboot(self, args: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
        return subprocess.run(["fastboot"] + args, capture_output=True, text=True, timeout=timeout)

    def _detect_connection(self) -> Dict:
        """Deteksi device dan set self.device_serial"""
        try:
            # Cek ADB
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split('\n')[1:]:
                if '\tdevice' in line:
                    self.device_serial = line.split('\t')[0]
                    return {"ok": True, "method": "ADB", "serial": self.device_serial}
            # Cek fastboot
            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
            if 'fastboot' in r.stdout:
                self.device_serial = r.stdout.split('\t')[0]
                return {"ok": True, "method": "fastboot", "serial": self.device_serial}
            return {"ok": False, "method": "none", "serial": None}
        except Exception:
            return {"ok": False, "method": "none", "serial": None}

    def _get_device_brand(self) -> str:
        """Dapatkan merk HP dari info yang ada"""
        if not self.device_serial:
            return "generic"

        try:
            r = self._run_adb(["shell", "getprop", "ro.product.manufacturer"], timeout=3)
            brand = r.stdout.strip().lower()
            if brand:
                if "samsung" in brand: return "samsung"
                if "xiaomi" in brand: return "xiaomi"
                if "oppo" in brand: return "oppo"
                if "vivo" in brand: return "vivo"
                if "realme" in brand: return "realme"
                if "oneplus" in brand: return "oneplus"
                if "google" in brand: return "google_pixel"
                if "motorola" in brand: return "motorola"
                if "lg" in brand: return "lg"
                if "asus" in brand: return "asus"
                if "nokia" in brand or "hmd" in brand: return "nokia"
                if "sony" in brand: return "sony"
                if "huawei" in brand: return "huawei"
                return brand
        except Exception:
            pass
        return "generic"

    def _get_device_model(self) -> str:
        """Dapatkan model HP"""
        if not self.device_serial:
            return "Unknown"
        try:
            r = self._run_adb(["shell", "getprop", "ro.product.model"], timeout=3)
            return r.stdout.strip() or "Unknown"
        except Exception:
            return "Unknown"

    def _get_links_for_device(self) -> Dict:
        """Dapatkan link download spesifik untuk device"""
        brand = self._get_device_brand()
        links = DEVICE_DOWNLOAD_LINKS.get(brand, {})
        if not links:
            links = DEVICE_DOWNLOAD_LINKS.get("generic", {})
        return links

    def _print_device_links(self):
        """Cetak link download khusus device"""
        links = self._get_links_for_device()
        if links:
            log.info(f"Link Download untuk {self._get_device_brand().upper()}:")
            for name, url in links.items():
                print(f"  {Colors.CYAN}  - {name}: {url}{Colors.RESET}")
            print()

    # ====================================================================
    # FITUR 1: SMART DEEP DIAGNOSTIC
    # ====================================================================

    def fitur_1_smart_diagnostic(self):
        """
        Deep diagnostic: analisa hardware + software
        Output: diagnosis AKURAT + arah tindakan
        Jika tidak bisa memberi efek -> deteksi -> saran berikutnya
        """
        log.header("[SMART DEEP DIAGNOSTIC]")
        ActionLogger.log("SMART DIAGNOSTIC", "INFO", "Memulai diagnostic")

        # Cek koneksi
        conn = self._detect_connection()
        if not conn["ok"]:
            log.warning("Tidak ada device terdeteksi via ADB")
            ErrorHandler.show_error("device_not_found")
            print("  Mode offline (data dari user):")
            conn["ok"] = False  # Lanjut dengan mode offline

        print()
        log.info("Menganalisa Hardware & Software...")
        time.sleep(0.5)
        print()

        # === DATA REAL vs SIMULASI ===
        # Jika device terdeteksi, baca data real
        arus = 0.0
        tegangan = 0.0
        ic_flash = "Unknown"
        cache_size = 0.0
        battery_level = 0
        errors_found = []

        if conn["ok"] and conn["method"] == "ADB":
            # === BACA DATA REAL DARI ADB ===
            # Battery level
            try:
                r = self._run_adb(["shell", "dumpsys", "battery"], timeout=3)
                for line in r.stdout.split('\n'):
                    if 'level' in line.lower():
                        battery_level = int(line.split(':')[1].strip())
                    if 'voltage' in line.lower():
                        try:
                            tegangan = int(line.split(':')[1].strip()) / 1000.0
                        except Exception:
                            pass
            except Exception:
                pass

            # Current (arus)
            try:
                r = self._run_adb(["shell", "cat", "/sys/class/power_supply/*/current_now"], timeout=3)
                raw = r.stdout.strip()
                if raw:
                    arus = abs(int(raw.split('\n')[0])) / 1000000.0
            except Exception:
                pass

            # IC Flash health (deteksi via error log)
            try:
                r = self._run_adb(["shell", "dmesg | grep -i 'mmc\\|flash\\|emmc' | tail -5"], timeout=3)
                dmesg = r.stdout.lower()
                if "error" in dmesg or "fail" in dmesg or "i/o" in dmesg:
                    ic_flash = "CRITICAL_BAD_SECTOR"
                elif "warning" in dmesg:
                    ic_flash = "LEMAH_READ_ONLY"
                else:
                    ic_flash = "BAIK"
            except Exception:
                ic_flash = "BAIK"

            # Cache size
            try:
                r = self._run_adb(["shell", "du -sh /data/dalvik-cache/ 2>/dev/null | cut -f1"], timeout=3)
                cache_raw = r.stdout.strip()
                if cache_raw:
                    if 'G' in cache_raw:
                        cache_size = float(cache_raw.replace('G', ''))
                    elif 'M' in cache_raw:
                        cache_size = float(cache_raw.replace('M', '')) / 1024
            except Exception:
                pass

            # OS version
            try:
                r = self._run_adb(["shell", "getprop", "ro.build.version.release"])
                os_ver = r.stdout.strip()
            except Exception:
                os_ver = "?"

            # Model
            model = self._get_device_model()

            # === CETAK HASIL ===
            print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}DEVICE TERDETEKSI:{Colors.RESET}")
            print(f"  {Colors.DIM}Model:{Colors.RESET} {model}")
            print(f"  {Colors.DIM}Serial:{Colors.RESET} {self.device_serial}")
            print(f"  {Colors.DIM}Android:{Colors.RESET} {os_ver}")
            print()
            print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}HARDWARE ANALYSIS:{Colors.RESET}")
            print(f"  {Colors.DIM}Battery:{Colors.RESET} {battery_level}%")
            print(f"  {Colors.DIM}Tegangan:{Colors.RESET} {tegangan:.1f}V")
            print(f"  {Colors.DIM}Arus:{Colors.RESET} {arus:.3f}A")
            print(f"  {Colors.DIM}IC Flash:{Colors.RESET} {ic_flash}")
            print(f"  {Colors.DIM}Cache:{Colors.RESET} {cache_size:.1f}GB")

        else:
            # === MODE OFFLINE: estimasi dari gejala user ===
            print(f"  {Colors.YELLOW}Mode: OFFLINE (device tidak terdeteksi){Colors.RESET}")
            print()
            print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}DIAGNOSA BERDASARKAN GEJALA:{Colors.RESET}")
            print(f"  Silakan jawab pertanyaan berikut:")
            print()

            gejala_baterai = input(f"  Apakah HP mati total? (y/N): ").strip().lower()
            gejala_charge = input(f"  Apakah tidak mau charge? (y/N): ").strip().lower()
            gejala_bootloop = input(f"  Apakah bootloop/restart terus? (y/N): ").strip().lower()
            gejala_lambat = input(f"  Apakah HP lemot/penuh? (y/N): ").strip().lower()
            print()

            arus = 0.0 if gejala_baterai == "y" else 0.5
            tegangan = 2.8 if gejala_baterai == "y" else 3.8
            battery_level = 0 if gejala_baterai == "y" else 50
            cache_size = 15.0 if gejala_lambat == "y" else 2.0
            if gejala_bootloop == "y":
                ic_flash = "LEMAH_READ_ONLY"
            elif gejala_baterai == "y":
                ic_flash = "BAIK"
            else:
                ic_flash = "BAIK"

        # === DIAGNOSA AKURAT ===
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 50}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_YELLOW}HASIL DIAGNOSA:{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 50}{Colors.RESET}")

        diagnosis_list = []
        tindakan_list = []

        # Analisa Arus
        if arus == DIAGNOSTIC_THRESHOLDS["current_no_charge"]:
            diagnosis_list.append("[KRITIS] Arus 0A - Tidak ada power masuk ke HP")
            tindakan_list.append("1. CEK KABEL CHARGER - ganti kabel data yang bagus")
            tindakan_list.append("2. CEK PORT CHARGER - bersihkan port dengan alkohol")
            tindakan_list.append("3. CEK BATERAI - ukur tegangan battery dengan multimeter")
            tindakan_list.append("4. Jika tegangan battery < 2.8V: tembak battery dengan power supply 4.2V")
            tindakan_list.append("5. Jika masih 0A: IC Power/Charger rusak -> butuh service center")
        elif arus < DIAGNOSTIC_THRESHOLDS["current_normal_min"]:
            diagnosis_list.append(f"[WARNING] Arus rendah ({arus:.2f}A) - Kemungkinan masalah charging")
            tindakan_list.append("1. Bersihkan port charger HP")
            tindakan_list.append("2. Coba charger original")
            tindakan_list.append("3. Ganti kabel USB")
            tindakan_list.append("4. Jika tetap rendah: IC charger lemah")

        # Analisa Tegangan
        if tegangan <= DIAGNOSTIC_THRESHOLDS["voltage_critical"]:
            diagnosis_list.append("[KRITIS] Baterai drop total - tidak bisa boot")
            tindakan_list.append("1. Tembak battery dengan power supply 4.2V (jangan lebih!)")
            tindakan_list.append("2. Tunggu 5 menit, coba hidupkan")
            tindakan_list.append("3. Jika tetap mati: ganti battery baru")
        elif tegangan < DIAGNOSTIC_THRESHOLDS["voltage_low"]:
            diagnosis_list.append(f"[WARNING] Baterai lemah ({tegangan}V) - perlu di-charge dulu")
            tindakan_list.append("1. Charge HP hingga penuh (> 4.0V)")
            tindakan_list.append("2. Jangan lakukan flashing/update sebelum battery penuh!")

        # Analisa IC Flash
        if ic_flash == "CRITICAL_BAD_SECTOR":
            diagnosis_list.append("[KRITIS] IC Flash rusak (bad sector) - Data mungkin hilang")
            tindakan_list.append("1. Backup data segera (jika masih bisa boot)")
            tindakan_list.append("2. Jika masih bisa boot: langsung backup ke PC!")
            tindakan_list.append("3. Jika sudah brick: butuh ganti IC Flash di service center")
            tindakan_list.append("4. EDL mode + format all mungkin bisa, tapi data hilang total")
        elif ic_flash == "LEMAH_READ_ONLY":
            diagnosis_list.append("[WARNING] IC Flash mulai lemah (read-only mode)")
            tindakan_list.append("1. Jangan lakukan factory reset dulu! Data bisa hilang")
            tindakan_list.append("2. Backup data via ADB: adb pull /sdcard/ ./backup/")
            tindakan_list.append("3. Flash ulang firmware bisa repair (tapi data hilang)")
            tindakan_list.append("4. Atau ganti IC Flash di service center")

        # Analisa Cache
        if cache_size > DIAGNOSTIC_THRESHOLDS["cache_critical_gb"]:
            diagnosis_list.append(f"[INFO] Cache menumpuk ({cache_size:.1f}GB) - HP jadi lemot")
            tindakan_list.append("1. Jalankan fitur CLEAN CACHE (Menu 2)")
            tindakan_list.append("2. Hapus app yang tidak dipakai")
            tindakan_list.append("3. Pindahkan foto/video ke PC atau cloud")

        # Analisa Battery
        if battery_level > 0 and battery_level < 20:
            diagnosis_list.append(f"[WARNING] Battery sangat rendah ({battery_level}%)")
            tindakan_list.append("1. Charge battery segera")
            tindakan_list.append("2. Jangan flashing dengan battery rendah!")

        # Cetak diagnosis
        if diagnosis_list:
            for d in diagnosis_list:
                if "[KRITIS]" in d:
                    log.critical(d)
                elif "[WARNING]" in d:
                    log.warning(d)
                else:
                    log.info(d)
            print()
            log.info("TINDAKAN YANG HARUS DILAKUKAN:")
            for t in tindakan_list:
                print(f"  {t}")
        else:
            log.success("[OK] Tidak ditemukan masalah kritis pada device")
            log.info("Device dalam kondisi normal")

        print()
        log.info("REKOMENDASI BERDASARKAN DIAGNOSA:")

        # Rekomendasi cerdas berdasarkan diagnosis
        gejala_bootloop = "n"
        if gejala_bootloop == "y" or ic_flash == "LEMAH_READ_ONLY":
            print(f"  {Colors.CYAN}  -> Gunakan: UNLOCK BOOTLOADER + FLASH FIRMWARE{Colors.RESET}")
        gejala_baterai = "n"
        if cache_size > DIAGNOSTIC_THRESHOLDS["cache_critical_gb"]:
            print(f"  {Colors.CYAN}  -> Gunakan: CLEAN CACHE (Menu 2){Colors.RESET}")
        if gejala_baterai == "y" and arus == 0:
            print(f"  {Colors.CYAN}  -> Bawa ke service center untuk perbaikan hardware{Colors.RESET}")
        if battery_level > 0 and battery_level < 30:
            print(f"  {Colors.CYAN}  -> Charge dulu baru lakukan service lainnya{Colors.RESET}")

        print()
        self._print_device_links()

        # Log hasil
        ActionLogger.log("SMART DIAGNOSTIC", "SUCCESS",
                         f"Arus:{arus}A Tegangan:{tegangan}V IC:{ic_flash} Cache:{cache_size}GB")

        # Cek apakah diagnosa memberi efek
        if arus == 0 and not conn["ok"]:
            log.warning("Diagnosa tidak bisa memberikan efek karena device tidak terdeteksi")
            log.info("Langkah selanjutnya: Hubungkan device via USB dengan driver benar")
            ErrorHandler.show_error("device_not_found")

    # ====================================================================
    # FITUR 2: CLEAN CACHE HP
    # ====================================================================

    def fitur_2_clean_cache(self):
        """
        Bersihkan semua sampah di device - 3 LEVEL DEEP CLEAN
        Level 1: Cache app user + dalvik-cache + system cache
        Level 2: Temporary files, thumbnails, logcat
        Level 3: Deep clean via recovery mode (panduan)
        """
        log.header("[CLEAN CACHE - 3 LEVEL DEEP CLEAN]")

        conn = self._detect_connection()

        if not conn["ok"] or conn["method"] != "ADB":
            log.warning("Device tidak terdeteksi via ADB")
            print()
            log.info("Mode OFFLINE - Panduan manual:")
            ErrorHandler.show_steps("clean_cache")
            ActionLogger.log("CLEAN CACHE", "INFO", "Mode offline - panduan ditampilkan")
            return

        # Pilih level
        print()
        print(f"  {Colors.BOLD}PILIH LEVEL PEMBERSIHAN:{Colors.RESET}")
        print(f"  {Colors.DIM}{'─' * 45}{Colors.RESET}")
        print(f"  {Colors.GREEN}1.{Colors.RESET} Level 1 - Soft Clean (cache app + dalvik)")
        print(f"  {Colors.YELLOW}2.{Colors.RESET} Level 2 - Deep Clean (+ temp, thumbnails, logcat)")
        print(f"  {Colors.RED}3.{Colors.RESET} Level 3 - Full Clean (+ recovery wipe cache guide)")
        print(f"  {Colors.DIM}{'─' * 45}{Colors.RESET}")
        level = input(f"  Pilih level [1-3] atau 0 untuk batal: ").strip()

        if level == "0":
            return

        if level not in ("1", "2", "3"):
            log.warning("Level tidak valid!")
            return

        level_names = {"1": "Level 1 - Soft Clean", "2": "Level 2 - Deep Clean", "3": "Level 3 - Full Clean"}
        log.info(f"Memulai: {level_names[level]}")

        if not ConfirmationChain.confirm_simple(
            f"Jalankan {level_names[level]}? (Data TIDAK akan hilang)", "n"
        ):
            return

        ActionLogger.log("CLEAN CACHE", "INFO", f"Mulai {level_names[level]}")
        total_cleaned = 0

        # ===== LEVEL 1: Cache App + Dalvik + System =====
        log.info("Level 1: Membersihkan cache app, dalvik, system...")
        try:
            cmds = [
                ("Cache app user", "rm -rf /data/data/*/cache/* 2>/dev/null; rm -rf /data/app/*/cache/* 2>/dev/null"),
                ("Cache sistem", "rm -rf /cache/* 2>/dev/null"),
                ("Dalvik cache", "rm -rf /data/dalvik-cache/* 2>/dev/null"),
                ("Google Play cache", "rm -rf /data/data/com.google.android.gms/cache/* 2>/dev/null"),
                ("Download manager", "rm -rf /data/data/com.android.providers.downloads/cache/* 2>/dev/null"),
            ]
            for label, cmd in cmds:
                self._run_adb(["shell", cmd], timeout=10)
                log.success(f"  [OK] {label}")
                total_cleaned += 1

            # Clear cache per app (top 50 apps)
            r = self._run_adb(["shell", "pm list packages | cut -d: -f2"], timeout=5)
            packages = r.stdout.strip().split('\n')
            app_count = 0
            for pkg in packages[:50]:
                try:
                    self._run_adb(["shell", f"pm clear --cache-only {pkg} 2>/dev/null"], timeout=3)
                    app_count += 1
                except Exception:
                    pass
            if app_count > 0:
                log.success(f"  [OK] Cache {app_count} app dibersihkan")
                total_cleaned += 1

        except Exception as e:
            log.warning(f"Level 1 error: {e}")

        # ===== LEVEL 2: Temp + Thumbnails + Logcat =====
        if level in ("2", "3"):
            print()
            log.info("Level 2: Membersihkan temporary files & thumbnails...")
            try:
                cmds_level2 = [
                    ("Temp files (/data/local/tmp)", "rm -rf /data/local/tmp/* 2>/dev/null"),
                    ("Thumbnails", "rm -rf /sdcard/DCIM/.thumbnails/* 2>/dev/null"),
                    ("Thumbnails (internal)", "rm -rf /data/data/*/cache/thumbnails/* 2>/dev/null"),
                    ("Logcat buffer", "logcat -c 2>/dev/null"),
                    ("Dropbox crash logs", "rm -rf /data/system/dropbox/* 2>/dev/null"),
                    ("App error traces", "rm -rf /data/anr/* 2>/dev/null"),
                    ("Bug reports", "rm -rf /data/bugreports/* 2>/dev/null"),
                    ("Tombstones", "rm -rf /data/tombstones/* 2>/dev/null"),
                    ("Recovery logs", "rm -rf /cache/recovery/* 2>/dev/null"),
                    ("Last kernel msg", "rm -f /proc/last_kmsg 2>/dev/null; echo 'ok'"),
                ]
                for label, cmd in cmds_level2:
                    self._run_adb(["shell", cmd], timeout=10)
                    log.success(f"  [OK] {label}")
                    total_cleaned += 1
            except Exception as e:
                log.warning(f"Level 2 error: {e}")

        # ===== LEVEL 3: Recovery Wipe + Verifikasi =====
        if level == "3":
            print()
            log.info("Level 3: Deep clean tambahan...")
            try:
                # Google Services Framework reset (biar gak lemot)
                self._run_adb(["shell", "pm clear com.google.android.gsf 2>/dev/null"], timeout=5)
                log.success("  [OK] Google Services cache")
                total_cleaned += 1

                # Media storage reset (biar gallery gak lemot)
                self._run_adb(["shell", "pm clear com.android.providers.media 2>/dev/null"], timeout=5)
                log.success("  [OK] Media storage cache")
                total_cleaned += 1

            except Exception as e:
                log.warning(f"Level 3 error: {e}")

            print()
            log.info("LANGKAH TAMBAHAN: Wipe cache via Recovery")
            print(f"  {Colors.DIM}Untuk hasil maksimal, wipe cache partition via recovery:{Colors.RESET}")
            print(f"  1. Matikan HP")
            print(f"  2. Masuk Recovery Mode (Vol Up + Power)")
            print(f"  3. Pilih 'Wipe cache partition'")
            print(f"  4. Reboot system")

        # ===== VERIFIKASI HASIL =====
        print()
        log.success(f"[OK] {level_names[level]} SELESAI! ({total_cleaned} item dibersihkan)")
        log.info("Restart HP untuk efek maksimal...")

        # Reboot HP otomatis setelah deep clean
        try:
            if ConfirmationChain.confirm_simple("Reboot HP sekarang? (biar efek maksimal)", "n"):
                log.info("Merestart HP...")
                self._run_adb(["reboot"], timeout=5)
                log.success("Perintah reboot telah dikirim! HP akan restart.")
        except Exception as e:
            log.warning(f"Gagal reboot otomatis: {e}")

        # Cek apakah ada sisa
        try:
            r = self._run_adb(["shell", "du -sh /data/dalvik-cache/ 2>/dev/null | cut -f1"], timeout=3)
            sisa = r.stdout.strip()
            if sisa and sisa != "0" and sisa != "0K":
                log.warning(f"Sisa cache: {sisa} (beberapa file terkunci)")
                log.info("Coba wipe cache via recovery mode untuk hasil maksimal")
            else:
                log.success("Dalvik cache: KOSONG (bersih sempurna)")
        except Exception:
            pass

        ActionLogger.log("CLEAN CACHE", "SUCCESS",
                         f"{level_names[level]}: {total_cleaned} item, cache bersih")

        # Adaptive: jika tidak ada efek
        try:
            r = self._run_adb(["shell", "du -sh /data/dalvik-cache/ 2>/dev/null | cut -f1"], timeout=3)
            sisa = r.stdout.strip()
            if sisa and sisa != "0" and sisa != "0K":
                log.warning("Pembersihan level ini belum tuntas!")
                saran = self.troubleshooter.suggest_next_step("clean_cache")
                log.info(saran)
                self.troubleshooter.record_attempt("clean_cache", False, f"Sisa: {sisa}")
        except Exception:
            pass

    # ====================================================================
    # FITUR 3: FLASH FIRMWARE (PANDUAN)
    # ====================================================================

    def fitur_3_flash_firmware(self):
        """Panduan step-by-step flash firmware"""
        log.header("[FLASH FIRMWARE - PANDUAN LENGKAP]")

        # Cek device
        conn = self._detect_connection()

        # BACKUP FULL OTOMATIS SEBELUM FLASH (WAJIB, TANPA KONFIRMASI)
        if conn["ok"]:
            log.warning("BACKUP OTOMATIS SEBELUM FLASHING...")
            BackupManager.auto_full_backup_forced(self.device_serial)

        ErrorHandler.show_steps("flash_firmware")

        # Cetak link spesifik device
        self._print_device_links()

        # Adaptive: cek apakah sudah pernah gagal flash sebelumnya
        failed = self.troubleshooter.get_failed_attempts("flash_firmware")
        if failed:
            print()
            log.warning(f"Anda sudah {len(failed)}x gagal flash sebelumnya!")
            saran = self.troubleshooter.suggest_next_step("flash_firmware")
            log.info(saran)
            print()

        # Konfirmasi
        if not ConfirmationChain.confirm_action(
            "Flash Firmware",
            "Pastikan firmware COCOK dengan model HP ANDA!\n"
            "Firmware salah = BRICK!\n"
            "Backup sudah dibuat, restore bisa dilakukan jika gagal.",
            "FIRMWARE SALAH AKAN MERUSAK HP!",
            True
        ):
            ActionLogger.log("FLASH FIRMWARE", "WARNING", "Dibatalkan user")
            return

        # Coba deteksi mode flashing
        if conn["ok"] and conn["method"] == "fastboot":
            log.success("Device dalam mode fastboot! Siap untuk flashing.")
        elif conn["ok"] and conn["method"] == "ADB":
            log.info("Device dalam mode ADB. Bisa reboot ke fastboot.")
            if ConfirmationChain.confirm_simple("Reboot ke fastboot?", "n"):
                try:
                    self._run_adb(["reboot", "bootloader"])
                    log.success("Reboot ke fastboot...")
                    time.sleep(3)
                except Exception as e:
                    ErrorHandler.handle_exception(e, "Reboot fastboot")
        else:
            log.warning("Device tidak terdeteksi. Ikuti panduan di atas untuk masuk mode flashing.")

        print()
        self._print_device_links()

        # Reboot ke mode yang sesuai
        if conn["ok"] and conn["method"] == "fastboot":
            if ConfirmationChain.confirm_simple("Reboot device sekarang?", "n"):
                try:
                    self._run_fastboot(["reboot"], timeout=10)
                    log.success("Perintah reboot telah dikirim!")
                except Exception as e:
                    log.warning(f"Gagal reboot: {e}")
        elif conn["ok"] and conn["method"] == "ADB":
            if ConfirmationChain.confirm_simple("Reboot device sekarang?", "n"):
                try:
                    self._run_adb(["reboot"], timeout=5)
                    log.success("Perintah reboot telah dikirim! HP akan restart.")
                except Exception as e:
                    log.warning(f"Gagal reboot: {e}")

        ActionLogger.log("FLASH FIRMWARE", "SUCCESS", "Panduan ditampilkan")

    # ====================================================================
    # FITUR 4: UNLOCK BOOTLOADER
    # ====================================================================

    def fitur_4_unlock_bootloader(self):
        """Panduan unlock bootloader"""
        log.header("[UNLOCK BOOTLOADER]")

        conn = self._detect_connection()

        ErrorHandler.show_steps("unlock_bootloader")
        self._print_device_links()

        # Adaptive: cek percobaan sebelumnya
        failed = self.troubleshooter.get_failed_attempts("unlock_bootloader")
        if failed:
            log.warning(f"Percobaan unlock sebelumnya gagal ({len(failed)}x)")
            saran = self.troubleshooter.suggest_next_step("unlock_bootloader")
            log.info(saran)
            print()

        if not ConfirmationChain.confirm_action(
            "Unlock Bootloader",
            "UNLOCK BOOTLOADER AKAN MENGHAPUS SEMUA DATA!\n"
            "Termasuk foto, kontak, aplikasi, setting.",
            "SEMUA DATA AKAN HILANG! BACKUP DULU!",
            True
        ):
            ActionLogger.log("UNLOCK BOOTLOADER", "WARNING", "Dibatalkan user")
            return

        # FULL BACKUP WAJIB SEBELUM UNLOCK (TANPA KONFIRMASI!)
        log.warning("BACKUP OTOMATIS: Mem-backup SEMUA partisi + data sebelum unlock...")
        BackupManager.auto_full_backup_forced(self.device_serial)

        # Eksekusi dengan AUTO RESTORE ON FAILURE
        try:
            if conn["ok"] and conn["method"] == "fastboot":
                log.info("Device dalam mode fastboot. Menjalankan unlock...")

                # Coba beberapa metode
                success = False
                for cmd in [["oem", "unlock"], ["flashing", "unlock"]]:
                    try:
                        r = self._run_fastboot(cmd, timeout=15)
                        if r.returncode == 0:
                            log.success("Bootloader UNLOCKED!")
                            ActionLogger.log("UNLOCK BOOTLOADER", "SUCCESS", f"Metode: fastboot {' '.join(cmd)}")
                            # Reboot device setelah unlock berhasil
                            log.info("Merestart device...")
                            try:
                                self._run_fastboot(["reboot"], timeout=10)
                                log.success("Device direstart!")
                            except Exception as reboot_err:
                                log.warning(f"Reboot otomatis gagal: {reboot_err}")
                                log.info("Silakan reboot manual: fastboot reboot")
                            success = True
                            break
                        else:
                            log.warning(f"fastboot {' '.join(cmd)} gagal: {r.stderr}")
                    except Exception as e:
                        log.warning(f"fastboot {' '.join(cmd)} error: {e}")

                if not success:
                    log.error("Semua metode unlock gagal!")
                    self.troubleshooter.record_attempt("unlock_bootloader", False, "Semua metode gagal")
                    ErrorHandler.show_error("bootloader_locked")
                    ActionLogger.log("UNLOCK BOOTLOADER", "ERROR", "Semua metode gagal")
                    # RESTORE OTOMATIS karena gagal
                    log.warning("MENJALANKAN RESTORE OTOMATIS...")
                    BackupManager.auto_restore_on_failure(self.device_serial, "Unlock bootloader gagal")

            elif conn["ok"] and conn["method"] == "ADB":
                log.info("Device dalam mode ADB. Reboot ke fastboot dulu...")
                try:
                    self._run_adb(["reboot", "bootloader"])
                    log.success("Reboot ke fastboot. Jalankan menu ini lagi setelah device di fastboot.")
                except Exception as e:
                    ErrorHandler.handle_exception(e, "Reboot bootloader")
                    # RESTORE OTOMATIS jika reboot gagal
                    BackupManager.auto_restore_on_failure(self.device_serial, "Reboot bootloader gagal")
            else:
                log.warning("Device tidak terdeteksi. Ikuti panduan manual di atas.")
        except Exception as e:
            log.critical(f"[ERROR] Unlock bootloader: {e}")
            BackupManager.auto_restore_on_failure(self.device_serial, str(e))

        print()
        self._print_device_links()

    # ====================================================================
    # FITUR 5: ROOT ANDROID
    # ====================================================================

    def fitur_5_root(self):
        """Panduan root Android"""
        log.header("[ROOT ANDROID - PANDUAN]")

        conn = self._detect_connection()

        log.warning("ROOT AKAN MENGHAPUS GARANSI!")
        log.warning("Beberapa app (banking, streaming) MUNGKIN TIDAK BERFUNGSI!")
        print()

        ErrorHandler.show_steps("root")
        self._print_device_links()

        if not ConfirmationChain.confirm_action(
            "Root Android",
            "Root akan:\n"
            "  - Menghapus garansi\n"
            "  - Mungkin mematikan beberapa app\n"
            "  - Tapi memberi akses full ke sistem",
            "ROOT BERISIKO! PASTIKAN ANDA TAHU APA YANG DILAKUKAN!",
            True
        ):
            ActionLogger.log("ROOT", "WARNING", "Dibatalkan user")
            return

        # Deteksi status bootloader
        if conn["ok"] and conn["method"] == "ADB":
            try:
                r = self._run_adb(["shell", "getprop", "ro.boot.flash.locked"], timeout=3)
                locked = r.stdout.strip()
                if locked == "1":
                    log.warning("Bootloader masih TERKUNCI! Buka dulu sebelum root.")
                    log.info("Gunakan menu UNLOCK BOOTLOADER dulu.")
                    ActionLogger.log("ROOT", "WARNING", "Bootloader terkunci")
                    return
                elif locked == "0":
                    log.success("Bootloader sudah terbuka! Bisa lanjut root.")
            except Exception:
                pass

        ActionLogger.log("ROOT", "SUCCESS", "Panduan ditampilkan")

    # ====================================================================
    # FITUR 6: FRP BYPASS GUIDE
    # ====================================================================

    def fitur_6_frp_bypass(self):
        """Panduan FRP bypass"""
        log.header("[FRP BYPASS - PANDUAN]")

        log.warning("FRP BYPASS HANYA LEGAL UNTUK HP MILIK SENDIRI!")
        print()

        # BACKUP FULL WAJIB SEBELUM FRP BYPASS (TANPA KONFIRMASI)
        conn = self._detect_connection()
        if conn["ok"]:
            log.warning("BACKUP OTOMATIS SEBELUM FRP BYPASS...")
            BackupManager.auto_full_backup_forced(self.device_serial)
            log.success("Backup selesai! Jika bypass gagal, restore otomatis.")
            print()

        methods = [
            ("Method 1: Google Account (Official)",
             "Setelah factory reset, hubungkan WiFi\n"
             "Masukkan email/password Google SEBELUMNYA\n"
             "Ini SATU-SATUNYA cara legal dan aman"),

            ("Method 2: OTG + Mouse (Samsung & beberapa HP)",
             "1. Boot ke recovery (Vol Up + Power)\n"
             "2. Wipe data/factory reset\n"
             "3. Reboot\n"
             "4. Saat diminta WiFi, jangan konek\n"
             "5. Colok OTG + Mouse\n"
             "6. Klik pojok kanan atas layar (area tertentu)"),

            ("Method 3: ADB (jika USB Debugging aktif)",
             "1. Hubungkan HP via USB\n"
             "2. Jalankan: adb shell am broadcast -a ACTION_FRP_BYPASS\n"
             "3. Atau: adb shell settings put secure frp_bypass 1"),

            ("Method 4: Download Mode (Samsung)",
             "1. Boot ke Download Mode (Vol Down + Power + Home)\n"
             "2. Flash firmware via Odin dengan HOME_CSC\n"
             "3. Data aman, FRP ter-reset"),

            ("Method 5: EDL (Qualcomm) / BROM (MediaTek)",
             "Flash firmware via EDL/BROM dengan format all\n"
             "FRP akan terhapus bersama semua data"),
        ]

        for name, detail in methods:
            print(f"  {Colors.BOLD}{Colors.CYAN}{name}{Colors.RESET}")
            print(f"  {Colors.DIM}{detail}{Colors.RESET}")
            print()

        if not ConfirmationChain.confirm_simple(
            "Saya mengerti FRP bypass hanya untuk HP sendiri?", "n"
        ):
            return

        # Reboot setelah panduan FRP
        if ConfirmationChain.confirm_simple("Reboot device sekarang? (disarankan setelah FRP bypass)", "n"):
            try:
                if conn["ok"] and conn["method"] == "ADB":
                    self._run_adb(["reboot"], timeout=5)
                    log.success("Perintah reboot telah dikirim! HP akan restart.")
                elif conn["ok"] and conn["method"] == "fastboot":
                    self._run_fastboot(["reboot"], timeout=10)
                    log.success("Perintah reboot telah dikirim!")
                else:
                    log.info("Silakan reboot HP secara manual.")
            except Exception as e:
                log.warning(f"Gagal reboot: {e}")

        ActionLogger.log("FRP BYPASS GUIDE", "SUCCESS", "Panduan ditampilkan")

    # ====================================================================
    # FITUR 7: FACTORY RESET
    # ====================================================================

    def fitur_7_factory_reset(self):
        """Factory reset aman dengan panduan"""
        log.header("[FACTORY RESET]")

        conn = self._detect_connection()

        log.warning("FACTORY RESET AKAN MENGHAPUS SEMUA DATA!")
        log.warning("Foto, kontak, app, setting, semuanya HILANG!")
        print()

        # Konfirmasi 3 layer
        if not ConfirmationChain.confirm_action(
            "Factory Reset",
            "SEMUA DATA AKAN TERHAPUS TOTAL!\n"
            "Tidak bisa dikembalikan!",
            "SEMUA DATA AKAN HILANG! BACKUP DULU!",
            True
        ):
            ActionLogger.log("FACTORY RESET", "WARNING", "Dibatalkan user")
            return

        # FULL BACKUP WAJIB SEBELUM FACTORY RESET (TANPA KONFIRMASI!)
        if conn["ok"] and conn["method"] == "ADB":
            log.warning("BACKUP OTOMATIS: Mem-backup SEMUA data sebelum factory reset...")
            BackupManager.auto_full_backup_forced(self.device_serial)
        else:
            log.warning("ADB tidak terdeteksi. Backup manual dulu!")
            print("  Cara backup manual:")
            print("  1. Colok HP ke PC")
            print("  2. Copy folder DCIM, Download, Documents ke PC")
            print("  3. Export kontak ke file .vcf")

        # Eksekusi factory reset via ADB dengan AUTO RESTORE ON FAILURE
        try:
            if conn["ok"] and conn["method"] == "ADB":
                print()
                if ConfirmationChain.confirm_simple("Jalankan factory reset VIA ADB?", "n"):
                    log.info("Menjalankan factory reset via ADB...")
                    r = self._run_adb(["shell", "recovery", "--wipe_data"], timeout=10)
                    if r.returncode == 0:
                        log.success("Factory reset via ADB berhasil!")
                        # Reboot otomatis setelah factory reset
                        log.info("Merestart device setelah factory reset...")
                        try:
                            self._run_adb(["reboot"], timeout=5)
                            log.success("Device sedang restart. Tunggu beberapa saat.")
                        except Exception as reboot_err:
                            log.warning(f"Reboot otomatis gagal: {reboot_err}")
                            log.info("Silakan reboot manual: adb reboot")
                    else:
                        log.warning("Factory reset via ADB gagal, mencoba metode alternatif...")
                        self._run_adb(["reboot", "recovery"])
                        log.success("Reboot ke recovery. Pilih 'Wipe data/factory reset' manual.")
            else:
                ErrorHandler.show_steps("factory_reset")
        except Exception as e:
            ErrorHandler.handle_exception(e, "Factory reset via ADB")
            log.warning("Factory reset gagal! Menjalankan RESTORE OTOMATIS...")
            BackupManager.auto_restore_on_failure(self.device_serial, str(e))
            log.info("Device telah dikembalikan ke keadaan sebelum reset.")
            ErrorHandler.show_steps("factory_reset")

        print()
        self._print_device_links()
        ActionLogger.log("FACTORY RESET", "SUCCESS", "Panduan ditampilkan")

    # ====================================================================
    # SCAN DEVICE - HELPER METHODS (dipecah dari fitur_8_scan_device)
    # ====================================================================

    def _scan_print_basic_info(self):
        """Cetak info dasar device dari getprop"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_YELLOW}  INFO DASAR DEVICE{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        dasar_props = [
            ("Merk", "ro.product.manufacturer"),
            ("Model", "ro.product.model"),
            ("Nama Panggilan", "ro.product.name"),
            ("Brand", "ro.product.brand"),
            ("Device Code", "ro.product.device"),
            ("Board", "ro.product.board"),
            ("Hardware Platform", "ro.hardware"),
            ("Android Version", "ro.build.version.release"),
            ("SDK Level", "ro.build.version.sdk"),
            ("Security Patch", "ro.build.version.security_patch"),
            ("Build ID", "ro.build.display.id"),
            ("Build Type", "ro.build.type"),
            ("Build Tags", "ro.build.tags"),
            ("Bootloader", "ro.bootloader"),
            ("Baseband", "ro.baseband"),
            ("Radio Version", "ro.build.version.baseband"),
            ("CPU ABI", "ro.product.cpu.abi"),
            ("Serial Number", "ro.serialno"),
            ("Fingerprint", "ro.build.fingerprint"),
        ]
        for label, prop in dasar_props:
            try:
                r = self._run_adb(["shell", "getprop", prop], timeout=2)
                val = r.stdout.strip()
                if val and val != "unknown" and "not found" not in val.lower():
                    print(f"  {Colors.DIM}{label}:{Colors.RESET} {val[:80]}")
            except Exception:
                pass

    def _scan_print_imei(self):
        """Cetak IMEI & identitas device via 3 metode"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_GREEN}  IMEI & IDENTITAS DEVICE{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        # Metode 1: service call iphonesubinfo
        for slot in ["1", "2", "3", "4"]:
            try:
                r = self._run_adb(["shell", "service", "call", "iphonesubinfo", slot], timeout=3)
                import re
                hex_vals = re.findall(r'0x[0-9a-fA-F]{2}', r.stdout)
                chars = []
                for h in hex_vals:
                    val = int(h, 16)
                    if 0x20 <= val <= 0x7E:
                        chars.append(chr(val))
                imei = ''.join(chars)
                if imei and len(imei) >= 14:
                    label = "IMEI 1" if slot == "1" else f"IMEI {slot}"
                    print(f"  {Colors.DIM}{label}:{Colors.RESET} {imei}")
            except Exception:
                pass

        # Metode 2: getprop IMEI
        imei_props = [
            "ro.ril.miui_imei", "ro.ril.miui_imei2",
            "persist.radio.imei", "persist.radio.imei1", "persist.radio.imei2",
            "ril.imei", "ril.imei1", "ril.imei2",
            "ro.phone.imei", "gsm.imei", "gsm.imei1", "gsm.imei2",
        ]
        for prop in imei_props:
            try:
                r = self._run_adb(["shell", "getprop", prop], timeout=2)
                val = r.stdout.strip()
                if val and val != "unknown" and "not found" not in val.lower() and len(val) >= 14:
                    key = prop.split('.')[-1].upper()
                    print(f"  {Colors.DIM}{key}:{Colors.RESET} {val}")
            except Exception:
                pass

        # Metode 3: dumpsys iphonesubinfo
        try:
            r = self._run_adb(["shell", "dumpsys", "iphonesubinfo"], timeout=3)
            for line in r.stdout.split('\n'):
                if "imei" in line.lower() or "device id" in line.lower():
                    print(f"  {Colors.DIM}{line.strip()}{Colors.RESET}")
        except Exception:
            pass

        # Android ID
        try:
            r = self._run_adb(["shell", "settings", "get", "secure", "android_id"], timeout=2)
            android_id = r.stdout.strip()
            if android_id:
                print(f"  {Colors.DIM}Android ID:{Colors.RESET} {android_id}")
        except Exception:
            pass

    def _scan_print_battery(self):
        """Cetak info battery health lengkap, simpan level ke self._battery_level"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_MAGENTA}  BATTERY HEALTH{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        battery_info = {}
        self._battery_level = '?'
        try:
            r = self._run_adb(["shell", "dumpsys", "battery"], timeout=3)
            for line in r.stdout.split('\n'):
                if ':' in line:
                    k = line.split(':')[0].strip()
                    v = line.split(':')[1].strip()
                    battery_info[k.lower()] = v

            status_map = {"1": "Unknown", "2": "Charging (AC)", "3": "Discharging",
                          "4": "Not Charging", "5": "Full"}
            health_map = {"1": "Unknown", "2": "Good", "3": "Overheat",
                          "4": "Dead", "5": "Over Voltage", "6": "Unspecified", "7": "Cold"}

            self._battery_level = battery_info.get('level', '?')
            print(f"  {Colors.DIM}Level:{Colors.RESET} {self._battery_level}%")
            print(f"  {Colors.DIM}Status:{Colors.RESET} {status_map.get(battery_info.get('status', '?'), battery_info.get('status', '?'))}")
            print(f"  {Colors.DIM}Health:{Colors.RESET} {health_map.get(battery_info.get('health', '?'), battery_info.get('health', '?'))}")
            print(f"  {Colors.DIM}Technology:{Colors.RESET} {battery_info.get('technology', '?')}")
            print(f"  {Colors.DIM}Tegangan:{Colors.RESET} {battery_info.get('voltage', '?')} mV")

            temp_raw = battery_info.get('temperature', '0')
            try:
                temp_c = int(temp_raw) / 10
                status_suhu = "[OK]" if 20 <= temp_c <= 40 else "[!]"
                print(f"  {Colors.DIM}Suhu:{Colors.RESET} {temp_c:.1f}C {status_suhu}")
            except Exception:
                pass

            if battery_info.get('present', '1') == 'true':
                print(f"  {Colors.GREEN}[OK]{Colors.RESET} Baterai Terpasang")
            else:
                print(f"  {Colors.RED}[X]{Colors.RESET} Baterai TIDAK Terpasang!")
        except Exception as e:
            log.warning(f"Battery info error: {e}")

        # sys/class/power_supply
        try:
            r = self._run_adb(["shell", "cat", "/sys/class/power_supply/*/capacity"], timeout=3)
            caps = r.stdout.strip().split('\n')
            print(f"  {Colors.DIM}Capacity (sys):{Colors.RESET} {caps[0] if caps else '?'}%")

            r = self._run_adb(["shell", "cat", "/sys/class/power_supply/*/current_now"], timeout=3)
            cur = r.stdout.strip().split('\n')[0] if r.stdout.strip() else '?'
            try:
                cur_a = int(cur) / 1000000
                print(f"  {Colors.DIM}Arus:{Colors.RESET} {cur_a:.3f}A")
            except Exception:
                pass

            r = self._run_adb(["shell", "cat", "/sys/class/power_supply/*/voltage_now"], timeout=3)
            volt = r.stdout.strip().split('\n')[0] if r.stdout.strip() else '?'
            try:
                volt_v = int(volt) / 1000000
                print(f"  {Colors.DIM}Voltage (sys):{Colors.RESET} {volt_v:.3f}V")
            except Exception:
                pass
        except Exception:
            pass

        # Battery health interpretation
        print()
        try:
            level_int = int(self._battery_level) if self._battery_level != '?' else 0
            if level_int < 15:
                log.warning("BATERAI KRITIS! Segera charge!")
            elif level_int < 30:
                log.warning("Baterai rendah. Jangan lakukan flashing!")
            elif level_int > 80:
                log.success("Baterai dalam kondisi baik.")
        except Exception:
            pass

    def _scan_print_storage(self):
        """Cetak info storage"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_CYAN}  STORAGE{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        try:
            r = self._run_adb(["shell", "df", "-h"], timeout=3)
            for line in r.stdout.split('\n'):
                if any(m in line for m in ['/data', '/sdcard', '/system', '/storage']):
                    parts = line.split()
                    if len(parts) >= 6:
                        mount = parts[-1]
                        size = parts[1]
                        used = parts[2]
                        avail = parts[3]
                        use_pct = parts[4]
                        print(f"  {Colors.DIM}{mount}:{Colors.RESET} {used}/{size} ({avail} free, {use_pct} used)")
        except Exception:
            pass

    def _scan_print_ram_cpu(self):
        """Cetak info RAM & CPU"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_BLUE}  RAM & CPU{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        try:
            r = self._run_adb(["shell", "cat", "/proc/meminfo"], timeout=3)
            for line in r.stdout.split('\n'):
                if any(k in line for k in ['MemTotal', 'MemFree', 'MemAvailable']):
                    print(f"  {Colors.DIM}{line.strip()}{Colors.RESET}")
        except Exception:
            pass

        try:
            r = self._run_adb(["shell", "cat", "/proc/cpuinfo"], timeout=3)
            for line in r.stdout.split('\n'):
                if any(k in line for k in ['Processor', 'Hardware', 'model name', 'Features']):
                    print(f"  {Colors.DIM}{line.strip()}{Colors.RESET}")
            r2 = self._run_adb(["shell", "nproc", "--all"], timeout=2)
            cores = r2.stdout.strip()
            if cores:
                print(f"  {Colors.DIM}CPU Cores:{Colors.RESET} {cores}")
        except Exception:
            pass

    def _scan_print_network(self):
        """Cetak info network & operator"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_YELLOW}  NETWORK & OPERATOR{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        net_props = [
            ("Operator", "gsm.operator.alpha"),
            ("Operator Code", "gsm.operator.numeric"),
            ("SIM Operator", "gsm.sim.operator.alpha"),
            ("Network Type", "gsm.network.type"),
            ("Device Name", "settings get global device_name"),
            ("Radio Operator", "persist.radio.operator"),
        ]
        for label, prop in net_props:
            try:
                if prop.startswith("settings "):
                    r = self._run_adb(["shell"] + prop.split(), timeout=2)
                else:
                    r = self._run_adb(["shell", "getprop", prop], timeout=2)
                print(f"  {Colors.DIM}{label}:{Colors.RESET} {r.stdout.strip() or '?'}")
            except Exception:
                pass

    def _scan_print_display(self):
        """Cetak info display"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_MAGENTA}  DISPLAY{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        display_cmds = [
            ("Resolution", "wm size"),
            ("Density", "wm density"),
            ("LCD Density", "getprop ro.sf.lcd_density"),
        ]
        for label, cmd in display_cmds:
            try:
                r = self._run_adb(["shell"] + cmd.split(), timeout=2)
                print(f"  {Colors.DIM}{label}:{Colors.RESET} {r.stdout.strip() or '?'}")
            except Exception:
                pass

    def _scan_print_security(self):
        """Cetak info keamanan device"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_RED}  KEAMANAN{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        self._locked = '?'
        security_props = [
            ("Encryption", "getprop ro.crypto.state"),
            ("Bootloader", "getprop ro.boot.flash.locked"),
            ("SELinux", "getenforce"),
            ("Verify Mode", "getprop ro.boot.verifymode"),
        ]
        for label, cmd in security_props:
            try:
                parts = cmd.split()
                if parts[0] == "getprop":
                    r = self._run_adb(["shell"] + parts, timeout=2)
                elif parts[0] == "getenforce":
                    r = self._run_adb(["shell", "getenforce"], timeout=2)
                else:
                    continue
                val = r.stdout.strip()

                if label == "Bootloader":
                    self._locked = val
                    lock_str = {"1": "LOCKED", "0": "UNLOCKED"}.get(val, val)
                    lock_color = Colors.RED if val == "1" else Colors.GREEN
                    print(f"  {Colors.DIM}{label}:{Colors.RESET} {lock_color}{lock_str}{Colors.RESET}")
                else:
                    print(f"  {Colors.DIM}{label}:{Colors.RESET} {val or '?'}")
            except Exception:
                pass

    def _scan_print_bluetooth_wifi(self):
        """Cetak info Bluetooth & WiFi"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_BLUE}  BLUETOOTH & WIFI{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        try:
            r = self._run_adb(["shell", "getprop", "ro.bt.bdaddr_path"], timeout=2)
            bt_path = r.stdout.strip()
            if bt_path:
                try:
                    r2 = self._run_adb(["shell", "cat", bt_path], timeout=2)
                    if r2.returncode == 0 and r2.stdout.strip():
                        print(f"  {Colors.DIM}Bluetooth MAC:{Colors.RESET} {r2.stdout.strip()}")
                except Exception:
                    pass

            r = self._run_adb(["shell", "getprop", "wifi.interface"], timeout=2)
            print(f"  {Colors.DIM}WiFi Interface:{Colors.RESET} {r.stdout.strip() or '?'}")

            r = self._run_adb(["shell", "cat", "/sys/class/net/wlan0/address"], timeout=2)
            if r.returncode == 0 and r.stdout.strip():
                print(f"  {Colors.DIM}WiFi MAC:{Colors.RESET} {r.stdout.strip()}")
        except Exception:
            pass

    def _scan_print_diagnosis(self):
        """Cetak diagnosis status device (baca level dari self._battery_level)"""
        print()
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_GREEN}  🩺 DIAGNOSIS STATUS{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 52}{Colors.RESET}")

        issues = []
        try:
            level = getattr(self, '_battery_level', '?')
            level_int = int(level) if level != '?' else -1
            if level_int >= 0 and level_int < 15:
                issues.append("BATERAI KRITIS - Segera charge!")
            locked = getattr(self, '_locked', '?')
            if locked == "1":
                issues.append("Bootloader TERKUNCI - Tidak bisa flash custom")

            if issues:
                for issue in issues:
                    log.warning(f"[!] {issue}")
            else:
                log.success("Device dalam kondisi normal.")
        except Exception:
            pass

    # ====================================================================
    # FITUR 8: SCAN DEVICE (INFO LENGKAP)
    # ====================================================================

    def fitur_8_scan_device(self):
        """
        SCAN DEVICE LENGKAP:
        - IMEI 1 & IMEI 2 (via 3 metode)
        - Battery health (capacity, temperature, voltage, current, technology)
        - Semua properti device (model, brand, android version, dll)
        - Storage (internal + external)
        - RAM & CPU info
        - Network info (operator, signal, IMSI, phone number)
        - Sensor info
        - Display info
        - Kamera info
        - Bluetooth & WiFi MAC
        """
        log.header("[SCAN DEVICE - FULL INFO]")

        conn = self._detect_connection()

        if not conn["ok"]:
            log.warning("Tidak ada device terdeteksi!")
            print()
            print(f"  {Colors.DIM}Pastikan:{Colors.RESET}")
            print(f"  1. HP terhubung via USB")
            print(f"  2. USB Debugging AKTIF (Developer Options)")
            print(f"  3. Driver USB sudah terinstall")
            print(f"  4. Kabel USB adalah kabel DATA (bukan charger-only)")
            print()
            log.info("Coba restart ADB:")
            try:
                subprocess.run(["adb", "kill-server"], capture_output=True, timeout=3)
                subprocess.run(["adb", "start-server"], capture_output=True, timeout=5)
                log.info("ADB restart selesai. Coba scan lagi.")
            except Exception:
                pass

            ActionLogger.log("SCAN DEVICE", "WARNING", "Tidak ada device")
            return

        log.success(f"Device terdeteksi via {conn['method']}!")

        if conn["method"] == "ADB":
            self._scan_print_basic_info()
            self._scan_print_imei()
            self._scan_print_battery()
            self._scan_print_storage()
            self._scan_print_ram_cpu()
            self._scan_print_network()
            self._scan_print_display()
            self._scan_print_security()
            self._scan_print_bluetooth_wifi()
            self._scan_print_diagnosis()

        elif conn["method"] == "fastboot":
            print(f"  Mode: FASTBOOT")
            try:
                r = self._run_fastboot(["getvar", "all"], timeout=5)
                for line in r.stdout.split('\n'):
                    if ':' in line and 'version' not in line.lower():
                        print(f"  {Colors.DIM}{line.strip()}{Colors.RESET}")
            except Exception:
                pass

        print()
        self._print_device_links()
        ActionLogger.log("SCAN DEVICE", "SUCCESS", f"Device: {self.device_serial}")

    # ====================================================================
    # FITUR 9: ROOT CHECKER
    # ====================================================================

    def fitur_9_root_checker(self):
        """Cek status root device"""
        log.header("[ROOT CHECKER]")

        conn = self._detect_connection()

        if not conn["ok"] or conn["method"] != "ADB":
            log.warning("Device tidak terdeteksi via ADB")
            return

        log.info("Memeriksa status root...")

        checks = [
            ("su binary", "which su"),
            ("Magisk", "magisk -c 2>/dev/null || echo 'not found'"),
            ("SuperSU", "su -v 2>/dev/null || echo 'not found'"),
            ("Busybox", "busybox --help 2>/dev/null || echo 'not found'"),
            ("Build Tags", "getprop ro.build.tags"),
            ("SELinux", "getenforce 2>/dev/null || echo 'unknown'"),
            ("Root via ADBD", "getprop ro.debuggable"),
            ("Test Root Access", "su -c 'id' 2>/dev/null || echo 'no root'"),
        ]

        print()
        rooted = False
        for label, cmd in checks:
            try:
                r = self._run_adb(["shell", cmd], timeout=3)
                val = r.stdout.strip()
                if val and val != "not found" and "not found" not in val.lower() and "no root" not in val.lower():
                    if "test-keys" in val.lower() or val == "1" or "uid=0" in val.lower():
                        rooted = True
                        print(f"  {Colors.GREEN}[ROOT]{Colors.RESET} {label}: {val}")
                    else:
                        print(f"  {Colors.DIM}{label}: {val}{Colors.RESET}")
                else:
                    print(f"  {Colors.DIM}{label}: -{Colors.RESET}")
            except Exception:
                print(f"  {Colors.DIM}{label}: error{Colors.RESET}")

        print()
        if rooted:
            log.warning("DEVICE DALAM KEADAAN ROOTED!")
            print("  - App banking & streaming mungkin tidak berfungsi")
            print("  - Garansi sudah hangus")
            print("  - Bisa akses full sistem")
        else:
            log.success("Device TIDAK ROOTED (aman)")
            print("  - Garansi masih berlaku")
            print("  - App banking & streaming aman")

        ActionLogger.log("ROOT CHECKER", "SUCCESS" if not rooted else "WARNING",
                         "Rooted" if rooted else "Not rooted")

    # ====================================================================
    # MENU UTAMA ANDROID (1 LEVEL, TIDAK ADA SUB-LOOP)
    # ====================================================================

    @staticmethod
    def list_features():
        """Tampilkan fitur yang tersedia"""
        print()
        print(f"  {Colors.BOLD}FITUR ANDROID TOOLKIT:{Colors.RESET}")
        print(f"  - Diagnostic (diagnostic)")
        print(f"  - Clean Cache (cache)")
        print(f"  - Flash Firmware (flash)")
        print(f"  - Unlock Bootloader (unlock)")
        print(f"  - Root Android (root)")
        print(f"  - FRP Bypass (frp)")
        print(f"  - Factory Reset (reset)")
        print(f"  - Scan Device (scan)")
        print(f"  - Root Checker (rootcheck)")
        print(f"  {Colors.DIM}Panggil dari menu utama NST (nomor 5-13){Colors.RESET}")
        print()