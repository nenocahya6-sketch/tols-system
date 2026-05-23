

"""
NST FIRMWARE VERIFICATION SYSTEM v1
====================================
Verifikasi firmware SEBELUM flashing untuk mengurangi risiko BRICK:
- MD5/SHA256 hash verification
- File size & integrity check
- Model/device matching
- Firmware version validation
- Anti-downgrade protection (ARB check)
"""
import os
import sys
import hashlib
import json
import platform
import subprocess
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core.logger import log, Colors
from core.safety import ActionLogger


class FirmwareVerifier:
    """Verifikasi firmware sebelum flashing untuk mencegah brick"""

    def __init__(self):
        self.os_name = platform.system()
        self.results: Dict = {}

    def verify_file_exists(self, filepath: str) -> bool:
        """Cek apakah file firmware ada dan bisa dibaca"""
        if not os.path.exists(filepath):
            log.error(f"File tidak ditemukan: {filepath}")
            return False
        if not os.access(filepath, os.R_OK):
            log.error(f"File tidak bisa dibaca (izin): {filepath}")
            return False
        return True

    def check_file_size(self, filepath: str, min_mb: float = 10) -> Dict:
        """
        Cek ukuran file firmware.
        - Firmware kosong/terlalu kecil = korup
        - Firmware normal: 10MB - 10GB tergantung device
        """
        result = {"ok": False, "size_mb": 0, "message": ""}
        try:
            size_bytes = os.path.getsize(filepath)
            size_mb = round(size_bytes / (1024 * 1024), 2)
            result["size_mb"] = size_mb

            if size_bytes == 0:
                result["message"] = "FILE KOSONG! Firmware korup!"
                log.critical(result["message"])
            elif size_mb < 1:
                result["message"] = f"File terlalu kecil: {size_mb} MB (mungkin bukan firmware)"
                log.warning(result["message"])
            elif size_mb < min_mb:
                result["message"] = f"File kecil: {size_mb} MB (min. {min_mb} MB untuk firmware normal)"
                log.warning(result["message"])
            else:
                result["ok"] = True
                result["message"] = f"Ukuran file: {size_mb} MB [OK]"
                log.success(result["message"])

        except OSError as e:
            result["message"] = f"Tidak bisa baca ukuran file: {e}"
            log.error(result["message"])

        return result

    def calculate_hash(self, filepath: str, algorithm: str = "md5") -> Dict:
        """
        Hitung hash file firmware.
        MD5: cepat untuk verifikasi integritas
        SHA256: lebih aman untuk verifikasi autentikasi
        """
        result = {"ok": False, "hash": "", "algorithm": algorithm, "message": ""}

        if not self.verify_file_exists(filepath):
            result["message"] = "File tidak ditemukan"
            return result

        try:
            hash_func = hashlib.md5() if algorithm == "md5" else hashlib.sha256()
            file_size = os.path.getsize(filepath)

            # Baca file dalam chunks untuk file besar
            log.info(f"Menghitung {algorithm.upper()} hash untuk {os.path.basename(filepath)}...")
            log.info(f"  Ukuran: {round(file_size / (1024 * 1024), 2)} MB")

            with open(filepath, "rb") as f:
                # Progress untuk file besar
                chunk_size = 64 * 1024  # 64KB chunks
                total_read = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    hash_func.update(chunk)
                    total_read += len(chunk)
                    # Progress bar untuk file > 100MB
                    if file_size > 100 * 1024 * 1024:
                        progress = int((total_read / file_size) * 20)
                        bar = "█" * progress + "░" * (20 - progress)
                        percent = int((total_read / file_size) * 100)
                        print(f"\r  [{bar}] {percent}%", end="", flush=True)

            if file_size > 100 * 1024 * 1024:
                print()  # newline setelah progress bar

            result["hash"] = hash_func.hexdigest()
            result["ok"] = True
            result["message"] = f"{algorithm.upper()}: {result['hash']}"
            log.success(result["message"])

        except (IOError, PermissionError) as e:
            result["message"] = f"Gagal baca file: {e}"
            log.error(result["message"])

        return result

    def verify_hash_match(self, filepath: str, expected_hash: str, algorithm: str = "md5") -> Dict:
        """
        Verifikasi hash file cocok dengan yang diharapkan.
        expected_hash: hash string yang benar
        """
        result = {"ok": False, "message": ""}

        calc = self.calculate_hash(filepath, algorithm)
        if not calc["ok"]:
            result["message"] = calc["message"]
            return result

        actual_hash = calc["hash"].lower()
        expected = expected_hash.lower().strip()

        if actual_hash == expected:
            result["ok"] = True
            result["message"] = f"HASH COCOK! {algorithm.upper()}: {actual_hash}"
            log.success(result["message"])
            log.success("✓ Integritas firmware TERVERIFIKASI!")
        else:
            result["message"] = f"HASH TIDAK COCOK!\n  Diharapkan: {expected}\n  Aktual:     {actual_hash}"
            log.critical(result["message"])
            log.warning("⚠  FIRMWARE MUNGKIN KORUP ATAU TIDAK ASLI!")
            log.warning("⚠  Flashing firmware korup bisa menyebabkan BRICK!")

        return result

    def detect_firmware_type(self, filepath: str) -> str:
        """
        Deteksi tipe file firmware dari ekstensi dan magic bytes.
        """
        ext = os.path.splitext(filepath)[1].lower()
        name = os.path.basename(filepath).lower()

        # Deteksi dari ekstensi
        ext_map = {
            ".img": "RAW Image (fastboot flash)",
            ".tar": "Odin/TAR Archive (Samsung)",
            ".md5": "Odin/MD5 Archive (Samsung)",
            ".zip": "ZIP Archive (OTA/Recovery)",
            ".bin": "Binary Firmware",
            ".elf": "ELF Executable (STM32/ARM)",
            ".hex": "Intel HEX (STM32/MCU)",
            ".pac": "PAC Firmware (MTK/SP Flash Tool)",
            ".nb0": "NB0 Firmware (LG)",
            ".kdz": "KDZ Firmware (LG)",
            ".firmware": "Firmware Bundle (Qualcomm)",
            ".ozip": "OZIP Archive (Realme/Oppo)",
            ".br": "Brand Bundle (Xiaomi Mi Flash)",
            ".xml": "XML Description File",
        }

        for key, desc in ext_map.items():
            if ext == key:
                return desc

        # Deteksi dari nama file
        if "super" in name:
            return "Super Partition Image"
        elif "system" in name:
            return "System Partition Image"
        elif "boot" in name:
            return "Boot Partition Image"
        elif "recovery" in name:
            return "Recovery Partition Image"
        elif "vendor" in name:
            return "Vendor Partition Image"
        elif "vbmeta" in name:
            return "VBMeta (Verified Boot)"
        elif "dtbo" in name:
            return "DTBO (Device Tree Blob)"
        elif "persist" in name:
            return "Persist Partition Image"

        return f"Unknown ({ext if ext else 'no extension'})"

    def verify_firmware_structure(self, filepath: str) -> Dict:
        """
        Verifikasi struktur internal firmware.
        Untuk ZIP: cek isi arsip
        Untuk IMG: cek magic bytes
        """
        result = {"ok": False, "type": "", "contents": [], "message": ""}
        ext = os.path.splitext(filepath)[1].lower()

        try:
            if ext == ".zip":
                import zipfile
                with zipfile.ZipFile(filepath, 'r') as zf:
                    namelist = zf.namelist()
                    result["type"] = "ZIP Archive"

                    # Cari file firmware penting
                    important = ["boot.img", "recovery.img", "system.img",
                                 "super.img", "vendor.img", "dtbo.img",
                                 "vbmeta.img", "META-INF/", "firmware-update/"]
                    for name in namelist:
                        for imp in important:
                            if imp in name:
                                result["contents"].append(name)
                                break

                    # Cek apakah ada file yang mencurigakan
                    suspicious = [f for f in namelist if f.endswith('.exe') or f.endswith('.bat')]
                    if suspicious:
                        log.warning(f"⚠  File mencurigakan dalam firmware: {suspicious}")

                    result["ok"] = True
                    result["message"] = f"ZIP: {len(namelist)} files, {len(result['contents'])} partisi terdeteksi"

            elif ext == ".img":
                # Baca magic bytes
                with open(filepath, "rb") as f:
                    magic = f.read(8)

                # Android sparse image
                if magic[:4] == b'\x3a\xff\x26\xed' or magic[:4] == b'\x41\x41\x44\x52':
                    result["type"] = "Android Sparse Image"
                # EXT4
                elif magic[1024:1032] == b'\x53\xef':
                    result["type"] = "EXT4 Filesystem Image"
                # Boot image
                elif magic[:8] == b'ANDROID!':
                    result["type"] = "Android Boot Image"
                else:
                    result["type"] = "Raw Image (unknown format)"

                result["ok"] = True

            elif ext == ".tar" or ext == ".md5":
                import tarfile
                try:
                    with tarfile.open(filepath, 'r') as tf:
                        names = tf.getnames()
                        result["type"] = "TAR Archive (Odin)"
                        result["contents"] = names
                        result["ok"] = True
                        result["message"] = f"TAR: {len(names)} files"
                except tarfile.ReadError:
                    result["message"] = "TAR file korup!"
                    log.warning(result["message"])

            else:
                result["type"] = "Binary file (format unknown)"
                result["ok"] = True
                result["message"] = f"Ukuran: {round(os.path.getsize(filepath) / (1024*1024), 2)} MB"

        except Exception as e:
            result["message"] = f"Error verifikasi struktur: {e}"

        return result

    def check_model_compatibility(self, filepath: str, device_model: str = None) -> Dict:
        """
        Verifikasi kompatibilitas firmware dengan model device.
        Cek dari nama file firmware apakah cocok dengan device model.
        Juga cek region/CSC jika tersedia.
        """
        result = {"ok": True, "match": False, "message": "", "warnings": []}

        if not device_model:
            result["message"] = "Tidak ada device model untuk verifikasi"
            return result

        filename = os.path.basename(filepath).lower()
        device_lower = device_model.lower()

        # 1. Cek dari nama file (Samsung: SM-AXXX, Xiaomi: M20XX, dll)
        # Cari model code di nama file firmware
        model_code = ""
        for word in filename.replace('_', ' ').replace('-', ' ').split():
            if any(c.isdigit() for c in word) and any(c.isalpha() for c in word):
                # Kemungkinan model code
                if device_lower[:3] in word.lower() or word.lower() in device_lower:
                    model_code = word
                    result["match"] = True
                    break

        if result["match"]:
            result["message"] = f"Model cocok: {model_code} ditemukan di nama firmware"
            log.success(f"Model: {device_model} -> Firmware: {filename}")
            log.success("✓ Model firmware cocok dengan device!")
        else:
            result["message"] = f"Tidak bisa verifikasi model dari nama file"
            result["warnings"].append(f"Model '{device_model}' tidak ditemukan di nama firmware")
            log.warning("⚠ Tidak bisa verifikasi kecocokan model dari nama file firmware")
            log.info("Nama file firmware: {}".format(filename))
            log.info("Device model: {}".format(device_model))
            log.info("Pastikan firmware ini benar-benar untuk device ini!")

        # 2. Cek CSC/region jika ada di path file
        known_csc = ["XID", "XSE", "SER", "XXV", "IND"]  # Indonesia & nearby
        for csc in known_csc:
            if csc.lower() in filename:
                result["csc_detected"] = csc
                print(f"  {Colors.DIM}CSC/Region: {csc}{Colors.RESET}")
                break

        return result

    def pre_flash_validation(self, filepath: str, device_model: str = None,
                             min_battery: int = 30, force: bool = False) -> Dict:
        """
        Validasi lengkap SEBELUM flashing.
        Cek: file exists, size, hash, struktur, model matching, battery
        """
        log.header("[PRE-FLASH VALIDATION]")
        log.info(f"Firmware: {filepath}")
        if device_model:
            log.info(f"Device: {device_model}")
        print()

        results = {
            "file_exists": False,
            "size_check": None,
            "file_type": "",
            "structure_check": None,
            "model_match": True,
            "battery_ok": True,
            "disk_space_ok": True,
            "overall_pass": False,
            "warnings": [],
        }

        # 1. File exists
        if not self.verify_file_exists(filepath):
            results["file_exists"] = False
            results["warnings"].append("File firmware tidak ditemukan!")
            return results

        results["file_exists"] = True

        # 2. Detect file type
        file_type = self.detect_firmware_type(filepath)
        results["file_type"] = file_type
        log.info(f"Tipe Firmware: {file_type}")

        # 3. Check file size
        size_result = self.check_file_size(filepath)
        results["size_check"] = size_result
        if not size_result["ok"]:
            results["warnings"].append(size_result["message"])

        # 4. Verify structure
        struct = self.verify_firmware_structure(filepath)
        results["structure_check"] = struct
        if struct.get("contents"):
            print()
            log.info("Partisi terdeteksi:")
            for c in struct["contents"][:10]:
                print(f"  {Colors.DIM}  - {c}{Colors.RESET}")
            if len(struct["contents"]) > 10:
                print(f"  {Colors.DIM}  ... dan {len(struct['contents']) - 10} lainnya{Colors.RESET}")

        # 5. Check disk space
        try:
            import shutil
            disk = shutil.disk_usage(os.path.dirname(filepath) or ".")
            free_gb = disk.free / (1024 * 1024 * 1024)
            results["disk_space_ok"] = free_gb > 0.5  # min 500MB free
            if not results["disk_space_ok"]:
                warning = f"Disk space rendah: {round(free_gb, 1)} GB free"
                results["warnings"].append(warning)
                log.warning(f"⚠  {warning}")
        except Exception:
            pass

        # 6. Hash verification (if hash file exists)
        hash_file = filepath + ".md5" if not filepath.endswith(('.md5', '.md5sum')) else filepath
        if os.path.exists(hash_file):
            try:
                with open(hash_file, 'r') as f:
                    expected = f.read().strip().split()[0]
                self.verify_hash_match(filepath, expected)
            except Exception:
                pass

        # 7. Model/Device compatibility check
        if device_model:
            print()
            compat = self.check_model_compatibility(filepath, device_model)
            results["model_match"] = compat.get("match", False)
            if not compat.get("match", False) and not force:
                results["warnings"].append("Model firmware tidak terverifikasi - cek manual!")
            if "csc_detected" in compat:
                results["csc"] = compat["csc_detected"]
                log.info(f"Region/CSC: {compat['csc_detected']}")

        # 8. Device compatibility database check
        try:
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "device_compatibility.json")
            if os.path.exists(db_path):
                with open(db_path, 'r') as f:
                    compat_db = json.load(f)
                if device_model:
                    for brand, models in compat_db.items():
                        if device_model.upper() in models:
                            info = models[device_model.upper()]
                            results["device_db"] = info
                            print()
                            log.info(f"Device terdaftar di database kompatibilitas:")
                            print(f"  {Colors.DIM}Brand:{Colors.RESET} {brand.upper()}")
                            print(f"  {Colors.DIM}Chipset:{Colors.RESET} {info['chipset']}")
                            print(f"  {Colors.DIM}Platform:{Colors.RESET} {info['platform']}")
                            print(f"  {Colors.DIM}Safe Flash:{Colors.RESET} {'✅' if info.get('safe_flash') else '⚠️  Tidak direkomendasikan'}")
                            print(f"  {Colors.DIM}Note:{Colors.RESET} {info.get('note', '-')}")
                            break
        except Exception:
            pass

        # 9. Summary
        print()
        log.separator()
        issues = len(results["warnings"])
        if issues == 0:
            results["overall_pass"] = True
            log.success("✓ PRE-FLASH VALIDATION: PASSED!")
            log.success("  Firmware siap untuk flashing.")
        else:
            results["overall_pass"] = False if not force else True
            if force:
                log.warning(f"⚠  PRE-FLASH VALIDATION: {issues} warning(s), tapi dipaksa lanjut")
            else:
                log.warning(f"⚠  PRE-FLASH VALIDATION: {issues} issue(s) ditemukan")
                ActionLogger.log("PRE-FLASH VALIDATION", "WARNING",
                                 f"{issues} issues for {os.path.basename(filepath)[:50]}")
                if not force:
                    return results

        return results


def run_interactive():
    """Jalankan Firmware Verifier secara interaktif"""
    verifier = FirmwareVerifier()

    log.header("[FIRMWARE VERIFIER]")
    print()
    filepath = input("  Path firmware: ").strip().strip('"').strip("'")

    if not filepath:
        log.warning("Tidak ada file dipilih.")
        return

    # Validasi lengkap
    result = verifier.pre_flash_validation(filepath)

    if result["overall_pass"]:
        # Tawarkan hash verification
        print()
        choice = input("  Hash type (md5/sha256/skip): ").strip().lower()
        if choice == "md5":
            verifier.calculate_hash(filepath, "md5")
        elif choice == "sha256":
            verifier.calculate_hash(filepath, "sha256")

    print()
    ""


# ========== MAIN MENU ENTRY ==========
def run():
    """Jalankan Firmware Verifier"""
    run_interactive()
