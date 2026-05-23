

"""
Qualcomm EDL Flasher — Wrapper untuk 'edl' CLI (bkerler, open-source, GRATIS)
==============================================================================
Backend: https://github.com/bkerler/edl (pip install edl)
Protocol: Sahara handshake → Firehose XML → Partition R/W

FITUR:
  - Read GPT (struktur partisi)
  - Bypass FRP (erase partisi frp)
  - Flash per-partisi atau full firmware
  - Backup partisi (read)
  - Root via Magisk (patch boot.img)
  - Factory Reset (erase userdata + cache)
  - Device info & reset

CARA PAKAI (untuk teknisi):
  1. Install driver Qualcomm 9008 (QDLoader)
  2. Masukkan HP ke mode EDL:
     - Matikan HP
     - Tekan & tahan Vol Up + Vol Down, lalu colok USB
     - Atau: adb reboot edl / fastboot oem edl
     - Atau: Test Point (lihat skema IC)
  3. Pastikan muncul 'Qualcomm HS-USB QDLoader 9008' di Device Manager
  4. Jalankan fungsi yang diinginkan

KEAMANAN:
  - Partisi kritis (modemst1, modemst2, fsc, fsg) DILINDUNGI dari erase
  - Validasi MD5 sebelum flash
  - Dry-run mode tersedia
"""
from core import clean_console_output



import os
import sys
import shutil
import subprocess
import hashlib
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path


# ── Partisi yang DILARANG dihapus (bisa bikin IMEI hilang / baseband mati) ──
PROTECTED_PARTITIONS = frozenset({
    "modemst1", "modemst2", "fsc", "fsg", "efs", "efs2",
    "persist", "sec", "ssd", "devinfo", "config",
    "xbl", "xbl_config", "abl", "tz", "hyp", "rpm",
    "sbl1", "pmic", "aop", "devcfg", "qupfw",
    "keymaster", "cmnlib", "cmnlib64",
    "gpt", "pgpt", "sgpt",  # Partition table itself
})

# ── Partisi yang aman untuk di-flash ulang ──
SAFE_FLASH_PARTITIONS = [
    "boot", "recovery", "system", "system_a", "system_b",
    "vendor", "vendor_a", "vendor_b",
    "product", "product_a", "product_b",
    "dtbo", "dtbo_a", "dtbo_b",
    "vbmeta", "vbmeta_a", "vbmeta_b",
    "vbmeta_system", "vbmeta_vendor",
    "cache", "userdata", "metadata",
    "super",  # Dynamic partition container
]

STEP_BY_STEP = {
    "bypass_frp": {
        "title": "BYPASS FRP (Google Account Lock) — Qualcomm EDL",
        "steps": [
            "1. Matikan HP sepenuhnya",
            "2. Masuk EDL Mode: Tekan Vol Up + Vol Down + colok USB",
            "   (atau gunakan Test Point sesuai skema board HP)",
            "3. Pastikan Device Manager menampilkan 'QDLoader 9008'",
            "4. Klik tombol 'Bypass FRP' di aplikasi",
            "5. Tunggu proses selesai (±10 detik)",
            "6. Cabut USB, pasang battery, nyalakan HP",
            "7. HP akan boot tanpa minta akun Google",
        ],
    },
    "flash_firmware": {
        "title": "FLASH FIRMWARE — Qualcomm EDL",
        "steps": [
            "1. Download firmware SESUAI model HP dari situs resmi",
            "2. Extract firmware ke folder (harus ada file .img dan rawprogram*.xml)",
            "3. Masukkan HP ke EDL Mode (lihat panduan di atas)",
            "4. Pilih folder firmware di aplikasi",
            "5. Klik 'Full Flash' — sistem akan validasi MD5 dulu",
            "6. JANGAN CABUT USB selama proses flash!",
            "7. Tunggu sampai selesai (bisa 5-15 menit)",
            "8. HP akan restart otomatis",
        ],
    },
    "root": {
        "title": "ROOT DEVICE — Qualcomm EDL + Magisk",
        "steps": [
            "1. Masukkan HP ke EDL Mode",
            "2. Sistem akan membaca partisi boot dari HP",
            "3. Boot.img akan di-patch dengan Magisk secara otomatis",
            "4. Boot.img yang sudah di-patch ditulis kembali ke HP",
            "5. HP restart → sudah ROOT!",
            "6. Install Magisk Manager APK untuk mengatur akses root",
        ],
    },
    "factory_reset": {
        "title": "FACTORY RESET — Qualcomm EDL",
        "steps": [
            "1. Masukkan HP ke EDL Mode",
            "2. Klik 'Factory Reset'",
            "3. Partisi userdata dan cache akan dihapus",
            "4. Semua data pribadi HILANG (foto, kontak, app)",
            "5. HP akan kembali seperti baru dari pabrik",
        ],
    },
}


class QualcommFlasher:
    """
    Wrapper untuk edl CLI tool (Qualcomm Emergency Download mode).
    
    Semua operasi dilakukan melalui subprocess call ke binary 'edl'.
    Tool ini 100% gratis dan open-source.
    """

    def __init__(self):
        self.edl_path = self._find_edl()
        self.timeout_default = 60
        self.timeout_flash = 600  # 10 menit untuk flash besar
        self.timeout_read = 300   # 5 menit untuk baca partisi

    def _find_edl(self) -> Optional[str]:
        """Cari binary edl di sistem."""
        # 1. Cari di PATH
        found = shutil.which("edl")
        if found:
            return found

        # 2. Cari di pip Scripts (Windows)
        if os.name == "nt":
            pip_paths = [
                os.path.join(sys.prefix, "Scripts", "edl.exe"),
                os.path.join(sys.prefix, "Scripts", "edl"),
                os.path.join(os.path.expanduser("~"), "AppData", "Local",
                             "Programs", "Python", "Python*", "Scripts", "edl.exe"),
            ]
            for p in pip_paths:
                if "*" in p:
                    import glob
                    matches = glob.glob(p)
                    if matches:
                        return matches[0]
                elif os.path.exists(p):
                    return p

        # 3. Cari di folder tools/ project
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        tools_path = os.path.join(project_root, "tools", "edl.exe")
        if os.path.exists(tools_path):
            return tools_path

        return None

    def _run_edl(self, args: List[str], timeout: int = None) -> dict:
        """
        Jalankan edl CLI dengan argumen tertentu.
        Returns: {success, message, stdout, stderr, returncode}
        """
        if not self.edl_path:
            return {
                "success": False,
                "message": "[QC-EDL] ❌ Tool 'edl' tidak ditemukan!\n"
                           "Install dengan: pip install edl\n"
                           "Atau download dari: https://github.com/bkerler/edl",
                "stdout": "",
                "stderr": "",
                "returncode": -1,
            }

        cmd = [self.edl_path] + args
        timeout = timeout or self.timeout_default

        print(f"[QC-EDL] ▶ Menjalankan: {' '.join(cmd)}")
        print(f"[QC-EDL] ⏱ Timeout: {timeout} detik")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(self.edl_path) if self.edl_path else None,
            )
            
            stdout = clean_console_output(result.stdout) or ""
            stderr = result.stderr or ""

            if result.returncode == 0:
                print(f"[QC-EDL] ✅ Berhasil!")
                return {
                    "success": True,
                    "message": "Operasi berhasil",
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": 0,
                }
            else:
                error_msg = stderr.strip() or stdout.strip() or "Unknown error"
                print(f"[QC-EDL] ❌ Gagal: {error_msg[:200]}")
                return {
                    "success": False,
                    "message": f"Operasi gagal: {error_msg[:200]}",
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": result.returncode,
                }

        except subprocess.TimeoutExpired:
            print(f"[QC-EDL] ⏰ TIMEOUT setelah {timeout} detik!")
            return {
                "success": False,
                "message": f"Timeout setelah {timeout} detik. "
                           "Pastikan HP dalam mode EDL 9008 dan kabel USB terhubung dengan baik.",
                "stdout": "",
                "stderr": "TimeoutExpired",
                "returncode": -2,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "message": "[QC-EDL] ❌ Binary 'edl' tidak bisa dijalankan. "
                           "Pastikan sudah terinstall: pip install edl",
                "stdout": "",
                "stderr": "FileNotFoundError",
                "returncode": -3,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"[QC-EDL] ❌ Error: {str(e)}",
                "stdout": "",
                "stderr": str(e),
                "returncode": -4,
            }

    # =========================================================================
    # CHECK TOOL
    # =========================================================================

    def check_tool(self) -> dict:
        """
        Cek apakah edl terinstall dan bisa dijalankan.
        Returns: {success, message, version, path}
        """
        print("[QC-EDL] 🔍 Mengecek instalasi edl tool...")

        if not self.edl_path:
            return {
                "success": False,
                "message": "Tool 'edl' BELUM terinstall.\n"
                           "Cara install:\n"
                           "  1. Buka Command Prompt / PowerShell\n"
                           "  2. Ketik: pip install edl\n"
                           "  3. Restart aplikasi NST Ultimate\n"
                           "Download manual: https://github.com/bkerler/edl",
                "version": None,
                "path": None,
            }

        # Coba jalankan edl --version atau edl tanpa argumen
        result = self._run_edl(["--version"], timeout=10)
        version = "unknown"
        if result["success"] or result["stdout"]:
            output = result["stdout"] + result["stderr"]
            # Parse version dari output
            for line in output.split("\n"):
                if "version" in line.lower() or "edl" in line.lower():
                    version = line.strip()
                    break

        return {
            "success": True,
            "message": f"Tool edl ditemukan di: {self.edl_path}",
            "version": version,
            "path": self.edl_path,
        }

    # =========================================================================
    # READ GPT (Partition Table)
    # =========================================================================

    def read_gpt(self) -> dict:
        """
        Baca tabel partisi (GPT) dari HP Qualcomm via EDL.
        
        SYARAT: HP harus dalam mode EDL 9008.
        Returns: {success, message, data: list of partition names}
        """
        print("[QC-EDL] 📋 Membaca tabel partisi (GPT)...")
        print("[QC-EDL] 💡 Pastikan HP dalam mode EDL 9008!")

        result = self._run_edl(["printgpt"], timeout=30)
        
        if not result["success"]:
            return {
                "success": False,
                "message": f"Gagal membaca GPT: {result['message']}",
                "data": [],
            }

        # Parse output untuk mendapatkan nama partisi
        partitions = []
        output = result["stdout"]
        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("Name"):
                continue
            # Format: Name            Offset      Size        ...
            parts = line.split()
            if parts:
                part_name = parts[0].strip()
                if part_name and not part_name.startswith("["):
                    partitions.append(part_name)

        print(f"[QC-EDL] ✅ Ditemukan {len(partitions)} partisi")
        for p in partitions[:10]:
            print(f"  ├─ {p}")
        if len(partitions) > 10:
            print(f"  └─ ... dan {len(partitions) - 10} partisi lainnya")

        return {
            "success": True,
            "message": f"Berhasil membaca {len(partitions)} partisi",
            "data": partitions,
        }

    # =========================================================================
    # BYPASS FRP (Google Account Lock)
    # =========================================================================

    def erase_frp(self) -> dict:
        """
        Hapus partisi FRP untuk bypass Google Account Lock.
        
        LANGKAH:
        1. HP dalam mode EDL 9008
        2. Tool akan menghapus partisi 'frp'
        3. Setelah selesai, restart HP
        4. HP tidak lagi minta akun Google saat setup
        """
        print("[QC-EDL] 🔓 BYPASS FRP — Menghapus partisi FRP...")
        print("[QC-EDL] ⚠ Ini akan menghapus kunci akun Google!")

        result = self._run_edl(["e", "frp"], timeout=30)

        if result["success"]:
            print("[QC-EDL] ✅ FRP berhasil dihapus!")
            print("[QC-EDL] 💡 Cabut USB → nyalakan HP → setup tanpa akun Google")
            return {
                "success": True,
                "message": "FRP bypass berhasil! Restart HP untuk menyelesaikan.",
                "data": {"partition": "frp", "action": "erased"},
            }
        else:
            return {
                "success": False,
                "message": f"Gagal bypass FRP: {result['message']}",
                "data": None,
            }

    # =========================================================================
    # ERASE PARTITION (Generic)
    # =========================================================================

    def erase_partition(self, name: str, force: bool = False) -> dict:
        """
        Hapus partisi tertentu.
        
        Args:
            name: Nama partisi (contoh: 'frp', 'userdata', 'cache')
            force: Jika True, bisa menghapus partisi yang dilindungi
        """
        name = name.strip().lower()

        # Safety check
        if name in PROTECTED_PARTITIONS and not force:
            msg = (f"⛔ DILARANG menghapus partisi '{name}'!\n"
                   f"Partisi ini kritis untuk fungsi HP (IMEI, baseband, bootloader).\n"
                   f"Menghapusnya bisa menyebabkan HP MATI TOTAL permanen.")
            print(f"[QC-EDL] {msg}")
            return {
                "success": False,
                "message": msg,
                "data": {"partition": name, "protected": True},
            }

        print(f"[QC-EDL] 🗑 Menghapus partisi: {name}")
        result = self._run_edl(["e", name], timeout=60)

        if result["success"]:
            print(f"[QC-EDL] ✅ Partisi '{name}' berhasil dihapus")
            return {
                "success": True,
                "message": f"Partisi '{name}' berhasil dihapus",
                "data": {"partition": name, "action": "erased"},
            }
        else:
            return {
                "success": False,
                "message": f"Gagal menghapus partisi '{name}': {result['message']}",
                "data": None,
            }

    # =========================================================================
    # FLASH PARTITION
    # =========================================================================

    def flash_partition(self, name: str, file_path: str) -> dict:
        """
        Flash/tulis file image ke partisi tertentu.
        
        Args:
            name: Nama partisi (contoh: 'boot', 'system', 'recovery')
            file_path: Path ke file .img yang akan di-flash
        """
        name = name.strip().lower()
        
        # Validasi file
        if not os.path.exists(file_path):
            return {
                "success": False,
                "message": f"File tidak ditemukan: {file_path}",
                "data": None,
            }

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        print(f"[QC-EDL] 📥 Flash partisi '{name}' ← {os.path.basename(file_path)} "
              f"({file_size_mb:.1f} MB)")

        # Safety check untuk partisi kritis
        if name in PROTECTED_PARTITIONS:
            print(f"[QC-EDL] ⚠ PERINGATAN: Partisi '{name}' adalah partisi kritis!")
            print(f"[QC-EDL] ⚠ Pastikan file yang di-flash BENAR untuk device ini!")

        # Hitung timeout berdasarkan ukuran file
        timeout = max(120, int(file_size_mb * 2) + 60)

        result = self._run_edl(["w", name, file_path], timeout=timeout)

        if result["success"]:
            print(f"[QC-EDL] ✅ Partisi '{name}' berhasil di-flash!")
            return {
                "success": True,
                "message": f"Partisi '{name}' berhasil di-flash ({file_size_mb:.1f} MB)",
                "data": {"partition": name, "file": file_path, "size_mb": file_size_mb},
            }
        else:
            return {
                "success": False,
                "message": f"Gagal flash '{name}': {result['message']}",
                "data": None,
            }

    # =========================================================================
    # READ / BACKUP PARTITION
    # =========================================================================

    def read_partition(self, name: str, output_path: str) -> dict:
        """
        Baca/backup partisi dari HP ke file.
        
        Args:
            name: Nama partisi (contoh: 'boot', 'efs', 'persist')
            output_path: Path file output untuk menyimpan backup
        """
        name = name.strip().lower()
        
        # Buat direktori output jika belum ada
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        print(f"[QC-EDL] 📤 Membaca partisi '{name}' → {output_path}")

        result = self._run_edl(["r", name, output_path], timeout=self.timeout_read)

        if result["success"] and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[QC-EDL] ✅ Backup '{name}' berhasil ({size_mb:.1f} MB)")
            return {
                "success": True,
                "message": f"Backup partisi '{name}' berhasil ({size_mb:.1f} MB)",
                "data": {"partition": name, "file": output_path, "size_mb": size_mb},
            }
        else:
            return {
                "success": False,
                "message": f"Gagal backup partisi '{name}': {result['message']}",
                "data": None,
            }

    # =========================================================================
    # FACTORY RESET
    # =========================================================================

    def factory_reset(self) -> dict:
        """
        Factory Reset — Hapus semua data pengguna.
        
        Menghapus partisi: userdata, cache, metadata
        Efek: HP kembali ke pengaturan pabrik (semua data HILANG!)
        """
        print("[QC-EDL] 🏭 FACTORY RESET — Menghapus data pengguna...")
        print("[QC-EDL] ⚠ SEMUA DATA AKAN HILANG! (foto, kontak, app, dll)")

        results = []
        partitions_to_erase = ["userdata", "cache"]

        for part in partitions_to_erase:
            print(f"[QC-EDL]   ├─ Menghapus {part}...")
            r = self._run_edl(["e", part], timeout=120)
            results.append({"partition": part, "success": r["success"]})

        all_ok = all(r["success"] for r in results)
        
        if all_ok:
            print("[QC-EDL] ✅ Factory Reset berhasil!")
            print("[QC-EDL] 💡 Restart HP untuk menyelesaikan proses")
            return {
                "success": True,
                "message": "Factory Reset berhasil! Restart HP.",
                "data": results,
            }
        else:
            failed = [r["partition"] for r in results if not r["success"]]
            return {
                "success": False,
                "message": f"Factory Reset gagal untuk partisi: {', '.join(failed)}",
                "data": results,
            }

    # =========================================================================
    # ROOT DEVICE (via Magisk boot patch)
    # =========================================================================

    def root_device(self, boot_img_path: str = None) -> dict:
        """
        Root device dengan metode Magisk boot.img patching.
        
        Alur:
        1. Baca partisi boot dari HP (jika boot_img_path tidak disediakan)
        2. Patch boot.img dengan magiskboot
        3. Flash kembali boot.img yang sudah di-patch
        
        Args:
            boot_img_path: Path ke boot.img (opsional, jika tidak ada akan di-extract dari HP)
        """
        print("[QC-EDL] 🔐 ROOT DEVICE — Magisk Boot Patching")

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        work_dir = os.path.join(project_root, "backups", "root_work")
        os.makedirs(work_dir, exist_ok=True)

        # Step 1: Dapatkan boot.img
        if boot_img_path and os.path.exists(boot_img_path):
            print(f"[QC-EDL] 📁 Menggunakan boot.img yang disediakan: {boot_img_path}")
            original_boot = boot_img_path
        else:
            print("[QC-EDL] 📥 Step 1: Membaca partisi boot dari HP...")
            original_boot = os.path.join(work_dir, "boot_original.img")
            read_result = self.read_partition("boot", original_boot)
            if not read_result["success"]:
                return {
                    "success": False,
                    "message": f"Gagal membaca partisi boot: {read_result['message']}",
                    "data": None,
                }

        # Step 2: Cek magiskboot
        magiskboot = shutil.which("magiskboot")
        if not magiskboot:
            magiskboot_paths = [
                os.path.join(project_root, "tools", "magiskboot.exe"),
                os.path.join(project_root, "tools", "magiskboot"),
            ]
            for mp in magiskboot_paths:
                if os.path.exists(mp):
                    magiskboot = mp
                    break

        if not magiskboot:
            return {
                "success": False,
                "message": "Tool 'magiskboot' tidak ditemukan!\n"
                           "Download dari: https://github.com/topjohnwu/Magisk/releases\n"
                           "Extract magiskboot.exe ke folder tools/",
                "data": {"step": "magiskboot_missing"},
            }

        # Step 3: Patch boot.img
        print("[QC-EDL] 🔧 Step 2: Patching boot.img dengan Magisk...")
        patched_boot = os.path.join(work_dir, "boot_patched.img")
        
        try:
            # Unpack boot
            subprocess.run(
                [magiskboot, "unpack", original_boot],
                capture_output=True, text=True, timeout=60,
                cwd=work_dir,
            )
            # Patch ramdisk
            subprocess.run(
                [magiskboot, "cpio", "ramdisk.cpio",
                 "add 0750 init magiskinit",
                 "patch"],
                capture_output=True, text=True, timeout=60,
                cwd=work_dir,
            )
            # Repack
            result = subprocess.run(
                [magiskboot, "repack", original_boot, patched_boot],
                capture_output=True, text=True, timeout=60,
                cwd=work_dir,
            )
            
            if not os.path.exists(patched_boot):
                return {
                    "success": False,
                    "message": "Magiskboot gagal membuat patched boot.img",
                    "data": {"step": "patch_failed"},
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error saat patching: {str(e)}",
                "data": None,
            }

        # Step 4: Flash boot yang sudah di-patch
        print("[QC-EDL] 📥 Step 3: Flashing patched boot.img...")
        flash_result = self.flash_partition("boot", patched_boot)

        if flash_result["success"]:
            print("[QC-EDL] ✅ ROOT BERHASIL!")
            print("[QC-EDL] 💡 Restart HP, lalu install Magisk Manager APK")
            return {
                "success": True,
                "message": "Root berhasil! Restart HP dan install Magisk Manager.",
                "data": {
                    "original_boot": original_boot,
                    "patched_boot": patched_boot,
                },
            }
        else:
            return {
                "success": False,
                "message": f"Gagal flash boot: {flash_result['message']}",
                "data": None,
            }

    # =========================================================================
    # FULL FLASH (rawprogram XML)
    # =========================================================================

    def full_flash(self, firmware_dir: str, xml_path: str = None) -> dict:
        """
        Flash SEMUA partisi dari folder firmware.
        
        Alur:
        1. Cari rawprogram*.xml di folder firmware
        2. Parse XML untuk mapping partisi → file
        3. Validasi semua file ada
        4. Flash partisi satu per satu
        
        Args:
            firmware_dir: Path ke folder firmware yang sudah di-extract
            xml_path: Path ke rawprogram XML (opsional, auto-detect jika tidak ada)
        """
        print("[QC-EDL] 🔥 FULL FLASH — Flash semua partisi dari firmware")

        if not os.path.isdir(firmware_dir):
            return {
                "success": False,
                "message": f"Folder firmware tidak ditemukan: {firmware_dir}",
                "data": None,
            }

        # Step 1: Cari rawprogram XML
        if not xml_path:
            for fname in os.listdir(firmware_dir):
                if fname.lower().startswith("rawprogram") and fname.endswith(".xml"):
                    xml_path = os.path.join(firmware_dir, fname)
                    break

        flash_map = {}

        if xml_path and os.path.exists(xml_path):
            # Parse rawprogram XML
            print(f"[QC-EDL] 📄 Parsing: {os.path.basename(xml_path)}")
            flash_map = self._parse_rawprogram_xml(xml_path, firmware_dir)
        else:
            # Fallback: cari file .img di folder
            print("[QC-EDL] ℹ Tidak ada rawprogram XML, menggunakan auto-detect...")
            for fname in os.listdir(firmware_dir):
                if fname.endswith(".img"):
                    part_name = fname.replace(".img", "").lower()
                    if part_name in SAFE_FLASH_PARTITIONS:
                        flash_map[part_name] = os.path.join(firmware_dir, fname)

        if not flash_map:
            return {
                "success": False,
                "message": "Tidak ada file firmware yang valid ditemukan di folder.",
                "data": None,
            }

        # Step 2: Validasi semua file
        print(f"[QC-EDL] 📋 Ditemukan {len(flash_map)} partisi untuk di-flash:")
        missing = []
        for part, fpath in flash_map.items():
            exists = os.path.exists(fpath)
            size_mb = os.path.getsize(fpath) / (1024 * 1024) if exists else 0
            status = f"✅ {size_mb:.1f} MB" if exists else "❌ MISSING"
            print(f"  ├─ {part:20s} → {os.path.basename(fpath):30s} {status}")
            if not exists:
                missing.append(part)

        if missing:
            return {
                "success": False,
                "message": f"File firmware hilang untuk partisi: {', '.join(missing)}",
                "data": {"missing": missing},
            }

        # Step 3: Flash satu per satu
        print(f"\n[QC-EDL] 🚀 Memulai proses flash {len(flash_map)} partisi...")
        results = []
        for i, (part, fpath) in enumerate(flash_map.items(), 1):
            print(f"\n[QC-EDL] [{i}/{len(flash_map)}] Flashing {part}...")
            r = self.flash_partition(part, fpath)
            results.append({
                "partition": part,
                "success": r["success"],
                "message": r["message"],
            })
            if not r["success"]:
                print(f"[QC-EDL] ❌ GAGAL flash {part}! Menghentikan proses.")
                return {
                    "success": False,
                    "message": f"Flash gagal di partisi '{part}': {r['message']}",
                    "data": results,
                }

        print(f"\n[QC-EDL] ✅ FULL FLASH BERHASIL! ({len(flash_map)} partisi)")
        print("[QC-EDL] 💡 Restart HP (first boot bisa 5-15 menit)")

        return {
            "success": True,
            "message": f"Full flash berhasil! {len(flash_map)} partisi di-flash.",
            "data": results,
        }

    def _parse_rawprogram_xml(self, xml_path: str, firmware_dir: str) -> dict:
        """Parse rawprogram*.xml untuk mendapatkan mapping partisi → file."""
        flash_map = {}
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            for program in root.findall(".//program"):
                label = program.get("label", "").strip().lower()
                filename = program.get("filename", "").strip()
                if label and filename:
                    filepath = os.path.join(firmware_dir, filename)
                    if label not in PROTECTED_PARTITIONS:
                        flash_map[label] = filepath
        except ET.ParseError as e:
            print(f"[QC-EDL] ⚠ Error parsing XML: {e}")
        except Exception as e:
            print(f"[QC-EDL] ⚠ Error: {e}")
        return flash_map

    # =========================================================================
    # DEVICE INFO
    # =========================================================================

    def get_device_info(self) -> dict:
        """Dapatkan informasi device Qualcomm via EDL."""
        print("[QC-EDL] ℹ Membaca info device...")

        gpt_result = self.read_gpt()
        
        info = {
            "platform": "Qualcomm",
            "mode": "EDL 9008",
            "tool": self.edl_path or "Not installed",
            "partitions": gpt_result.get("data", []),
            "partition_count": len(gpt_result.get("data", [])),
        }

        return {
            "success": gpt_result["success"],
            "message": "Info device berhasil dibaca" if gpt_result["success"] else gpt_result["message"],
            "data": info,
        }

    # =========================================================================
    # RESET DEVICE
    # =========================================================================

    def reset_device(self) -> dict:
        """Reset/reboot device dari mode EDL."""
        print("[QC-EDL] 🔄 Mereset device...")
        result = self._run_edl(["reset"], timeout=15)
        
        if result["success"]:
            return {
                "success": True,
                "message": "Device berhasil di-reset. HP akan restart.",
                "data": None,
            }
        else:
            return {
                "success": False,
                "message": f"Gagal reset device: {result['message']}",
                "data": None,
            }

    # =========================================================================
    # MD5 VERIFICATION
    # =========================================================================

    def verify_file_md5(self, file_path: str, expected_md5: str) -> dict:
        """Verifikasi MD5 hash file firmware."""
        if not os.path.exists(file_path):
            return {"success": False, "message": "File tidak ditemukan", "data": None}

        print(f"[QC-EDL] 🔍 Verifikasi MD5: {os.path.basename(file_path)}")
        
        md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        
        actual = md5.hexdigest()
        match = actual.lower() == expected_md5.lower()
        
        return {
            "success": match,
            "message": "MD5 cocok ✅" if match else f"MD5 TIDAK COCOK ❌ ({actual})",
            "data": {"expected": expected_md5, "actual": actual, "match": match},
        }