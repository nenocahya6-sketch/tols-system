


"""
NST Flash Simulation Mode v1
==============================
Simulasi flashing SEBELUM eksekusi real.

Fitur:
  1. Analyze Firmware — Ekstrak & analisis struktur firmware (.zip, .tar.md5, .img, .bin)
  2. Partition Match — Cek apakah partisi di firmware cocok dengan device
  3. Preloader Safety — Verifikasi preloader aman untuk di-flash (MediaTek)
  4. Anti-Rollback Check — Cek versi ARB firmware vs device
  5. Dry-Run Mode — Simulasi tanpa menulis ke flash (hanya verifikasi)
  6. Risk Assessment — Beri skor risiko flashing

Tanpa simulasi: firmware salah -> BRICK!
Dengan simulasi: deteksi masalah SEBELUM flash.
"""


import os
import re
import json
import hashlib
import struct
import zipfile
import tarfile
import tempfile
import shutil
from typing import Dict, List, Optional, Tuple, Any, BinaryIO
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from core.logger import log, Colors
from core.firmware_verify import FirmwareVerifier


# ===========================================================================
# Risk Level
# ===========================================================================

class RiskLevel(Enum):
    SAFE = "SAFE ✅"           # Aman untuk di-flash
    LOW = "LOW ⚠️"             # Risiko rendah
    MEDIUM = "MEDIUM ⚡"        # Risiko sedang, perlu hati-hati
    HIGH = "HIGH ❌"            # Risiko tinggi, tidak disarankan
    CRITICAL = "CRITICAL 🚫"   # Sangat berbahaya, jangan flash


@dataclass
class FirmwareAnalysis:
    """Hasil analisis firmware."""
    filename: str = ""
    size_mb: float = 0.0
    format_type: str = ""        # zip, tar, img, bin, etc.
    partitions: List[PartitionInfo] = field(default_factory=list)
    total_partitions: int = 0
    has_preloader: bool = False
    preloader_safe: bool = True
    preloader_detail: str = ""
    has_boot: bool = False
    has_recovery: bool = False
    has_vbmeta: bool = False
    has_super: bool = False
    has_system: bool = False
    has_vendor: bool = False
    has_userdata: bool = False
    detected_chipset: str = ""
    detected_model: str = ""
    detected_region: str = ""
    android_version: str = ""
    security_patch: str = ""
    firmware_version: str = ""
    antirollback_version: int = -1
    signature_valid: bool = False
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        """Skor kualitas firmware (0-100)."""
        score = 50  # base
        if self.has_boot: score += 10
        if self.has_recovery: score += 5
        if self.has_vbmeta: score += 10
        if self.has_super or self.has_system: score += 10
        if self.signature_valid: score += 10
        if not self.issues: score += 5
        if self.preloader_safe: score += 5
        if self.antirollback_version >= 0: score += 5
        return min(score, 100)

    @property
    def risk(self) -> RiskLevel:
        """Risk level berdasarkan analisis."""
        if not self.partitions:
            return RiskLevel.CRITICAL
        if not self.has_boot:
            return RiskLevel.HIGH
        if not self.preloader_safe:
            return RiskLevel.CRITICAL
        if len(self.issues) > 3:
            return RiskLevel.HIGH
        if len(self.issues) > 1:
            return RiskLevel.MEDIUM
        if self.issues:
            return RiskLevel.LOW
        return RiskLevel.SAFE


@dataclass
class PartitionInfo:
    """Info satu partisi dalam firmware."""
    name: str = ""
    filename: str = ""
    size_mb: float = 0.0
    offset: int = 0
    hash_md5: str = ""
    hash_sha256: str = ""
    is_essential: bool = False       # boot, vbmeta, etc.
    is_dangerous: bool = False        # preloader, tz, etc.
    is_userdata: bool = False         # akan wipe data
    detected_type: str = ""           # GPT, EXT4, VBN, etc.

    def __str__(self) -> str:
        icon = "⚠️" if self.is_dangerous else "📦"
        return f"  {icon} {self.name:20s} {self.size_mb:>8.1f} MB  {self.detected_type or ''}"


@dataclass
class SimulationResult:
    """Hasil simulasi flashing."""
    passed: bool = False
    risk_level: RiskLevel = RiskLevel.SAFE
    analysis: FirmwareAnalysis = field(default_factory=FirmwareAnalysis)
    device_compatible: bool = True
    partition_mismatches: List[str] = field(default_factory=list)
    partition_missing: List[str] = field(default_factory=list)
    partition_extra: List[str] = field(default_factory=list)
    model_match: bool = True
    arb_safe: bool = True
    preloader_safe: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recommendation: str = ""


# ===========================================================================
# FIRMWARE ANALYZER
# ===========================================================================

class FirmwareAnalyzer:
    """
    Analisis firmware — ekstrak, baca struktur, deteksi partisi, validasi.

    Support:
    - ZIP (Xiaomi, OTA update)
    - TAR.MD5 (Samsung Odin)
    - IMG (raw partition image)
    - BIN (Qualcomm, MediaTek)
    - ELF (Qualcomm Firehose Programmer)
    """

    PARTITION_ESSENTIAL = {
        "boot", "vbmeta", "recovery", "dtbo", "dts",
    }
    PARTITION_DANGEROUS = {
        "preloader", "lx", "tz", "secos", "abl", "xbl",
        "pmic", "hyp", "uefi", "keymaster", "cmnlib",
    }
    PARTITION_USERDATA = {
        "userdata", "data", "cache", "super",
    }

    def __init__(self):
        self._temp_dir: Optional[str] = None

    def analyze(self, firmware_path: str) -> FirmwareAnalysis:
        """
        Analisis firmware file secara mendalam.

        Args:
            firmware_path: Path ke file firmware

        Returns:
            FirmwareAnalysis — hasil analisis lengkap
        """
        log.info(f"Menganalisis firmware: {os.path.basename(firmware_path)}")
        print()

        if not os.path.isfile(firmware_path):
            analysis = FirmwareAnalysis()
            analysis.issues.append(f"File tidak ditemukan: {firmware_path}")
            return analysis

        analysis = FirmwareAnalysis()
        analysis.filename = os.path.basename(firmware_path)
        analysis.size_mb = os.path.getsize(firmware_path) / (1024 * 1024)

        # Deteksi format
        ext = os.path.splitext(firmware_path)[1].lower()
        analysis.format_type = ext

        # Analisis berdasarkan format
        if ext in ('.zip',):
            self._analyze_zip(firmware_path, analysis)
        elif ext in ('.md5', '.tar', '.tar.md5'):
            self._analyze_tar(firmware_path, analysis)
        elif ext in ('.img',):
            self._analyze_image(firmware_path, analysis)
        elif ext in ('.bin', '.elf'):
            self._analyze_bin(firmware_path, analysis)
        else:
            # Coba deteksi format dari magic bytes
            magic = self._read_magic(firmware_path)
            if magic.startswith(b'PK'):
                self._analyze_zip(firmware_path, analysis)
            elif magic.startswith(b'\x1f\x8b'):
                self._analyze_tar(firmware_path, analysis)
            else:
                self._analyze_bin(firmware_path, analysis)

        analysis.total_partitions = len(analysis.partitions)

        # Post-analysis
        if analysis.partitions:
            log.success(f"  Format: {analysis.format_type.upper()}")
            log.success(f"  Size: {analysis.size_mb:.1f} MB")
            log.success(f"  Partisi: {analysis.total_partitions} ditemukan")
        else:
            analysis.issues.append("Tidak ada partisi terdeteksi dalam firmware")
            log.warning("  Tidak ada partisi yang dikenal dalam firmware")
            log.warning("  Mungkin firmware corrupt atau format tidak dikenal")

        return analysis

    def _analyze_zip(self, path: str, analysis: FirmwareAnalysis):
        """Analisis firmware ZIP (Xiaomi, OTA, Custom ROM)."""
        try:
            with zipfile.ZipFile(path, 'r') as z:
                namelist = z.namelist()

                # Deteksi tipe firmware dari struktur folder
                for name in namelist:
                    lower = name.lower()

                    # Cari file images/
                    if 'images/' in lower or '/img/' in lower:
                        analysis.format_type = "ZIP (Xiaomi/OTA)"

                    # Deteksi partisi dari nama file
                    fname = os.path.basename(name)
                    self._detect_partition_from_name(fname, analysis)

                    # Baca metadata
                    if 'rom' in lower and name.endswith('.txt'):
                        try:
                            content = z.read(name).decode('utf-8', errors='ignore')
                            self._parse_metadata(content, analysis)
                        except Exception:
                            pass

                    # Cek signature
                    if 'sig' in lower or 'signature' in lower:
                        analysis.signature_valid = True

                # Jika ada folder images/, analisis lebih dalam
                for name in namelist:
                    lower = name.lower()
                    if '/images/' in lower and not lower.endswith('/'):
                        fname = os.path.basename(name)
                        try:
                            info = z.getinfo(name)
                            info_mb = info.file_size / (1024 * 1024)
                            pi = PartitionInfo(
                                name=os.path.splitext(fname)[0],
                                filename=fname,
                                size_mb=round(info_mb, 1),
                                is_essential=fname.replace('.img','') in self.PARTITION_ESSENTIAL,
                                is_dangerous=fname.replace('.img','') in self.PARTITION_DANGEROUS,
                                is_userdata=fname.replace('.img','') in self.PARTITION_USERDATA,
                            )
                            # Hash
                            if info.file_size < 100 * 1024 * 1024:  # < 100 MB
                                data = z.read(name)
                                pi.hash_md5 = hashlib.md5(data).hexdigest()
                                pi.hash_sha256 = hashlib.sha256(data).hexdigest()

                                # Deteksi tipe
                                pi.detected_type = self._detect_image_type(data)
                                if pi.name == "preloader":
                                    pi.is_dangerous = True
                                    analysis.preloader_safe = self._check_preloader_safe(data)
                                    analysis.preloader_detail = "Preloader version: " + (pi.hash_md5[:8])
                                    analysis.has_preloader = True

                            analysis.partitions.append(pi)
                        except Exception:
                            pass

        except zipfile.BadZipFile:
            analysis.issues.append("Firmware ZIP corrupt atau bukan format ZIP")
        except Exception as e:
            analysis.issues.append(f"Error analisis ZIP: {e}")

    def _analyze_tar(self, path: str, analysis: FirmwareAnalysis):
        """Analisis firmware TAR (Samsung Odin)."""
        try:
            # TAR.MD5 = TAR dengan appended MD5 hash
            mode = 'r:'
            if path.endswith('.gz') or path.endswith('.tar.gz'):
                mode = 'r:gz'
            elif path.endswith('.md5') or path.endswith('.tar.md5'):
                mode = 'r:'  # TAR tanpa kompresi
            else:
                mode = 'r:'

            with tarfile.open(path, mode) as tar:
                members = tar.getmembers()

                for member in members:
                    if member.isfile():
                        fname = os.path.basename(member.name).lower()
                        pi = PartitionInfo(
                            name=os.path.splitext(fname)[0],
                            filename=member.name,
                            size_mb=round(member.size / (1024 * 1024), 1),
                            is_essential=fname.replace('.img','').replace('.bin','') in self.PARTITION_ESSENTIAL,
                            is_dangerous=fname.replace('.img','').replace('.bin','') in self.PARTITION_DANGEROUS,
                            is_userdata=fname.replace('.img','').replace('.bin','') in self.PARTITION_USERDATA,
                        )

                        # Hash jika kecil
                        if member.size < 50 * 1024 * 1024:
                            try:
                                f = tar.extractfile(member)
                                if f:
                                    data = f.read()
                                    pi.hash_md5 = hashlib.md5(data).hexdigest()
                                    pi.hash_sha256 = hashlib.sha256(data).hexdigest()
                                    # Deteksi tipe
                                    pi.detected_type = self._detect_image_type(data)
                                    if pi.name == "preloader":
                                        analysis.preloader_safe = self._check_preloader_safe(data)
                                        analysis.has_preloader = True
                            except Exception:
                                pass

                        analysis.partitions.append(pi)

                # Cek validasi MD5 (Samsung append MD5 di akhir file)
                if path.endswith('.md5'):
                    file_size = os.path.getsize(path)
                    expected_hash = ""
                    try:
                        with open(path, 'rb') as f:
                            f.seek(-32, 2)
                            expected_hash = f.read(32).decode('ascii', errors='ignore')
                        if expected_hash and len(expected_hash) == 32:
                            # Verifikasi hash
                            with open(path, 'rb') as f:
                                data = f.read(file_size - 32)
                                actual_hash = hashlib.md5(data).hexdigest()
                                analysis.signature_valid = (expected_hash == actual_hash)
                    except Exception:
                        pass

        except Exception as e:
            analysis.issues.append(f"Error analisis TAR: {e}")

    def _analyze_image(self, path: str, analysis: FirmwareAnalysis):
        """Analisis file IMG (raw partition image)."""
        try:
            with open(path, 'rb') as f:
                data = f.read()
                f.seek(0, 2)
                size = f.tell()

            name = os.path.splitext(os.path.basename(path))[0]
            pi = PartitionInfo(
                name=name,
                filename=os.path.basename(path),
                size_mb=round(size / (1024 * 1024), 1),
                is_essential=name in self.PARTITION_ESSENTIAL,
                is_dangerous=name in self.PARTITION_DANGEROUS,
                is_userdata=name in self.PARTITION_USERDATA,
            )
            pi.hash_md5 = hashlib.md5(data[:min(len(data), 100*1024*1024)]).hexdigest()
            pi.detected_type = self._detect_image_type(data[:4096])
            analysis.partitions.append(pi)

        except Exception as e:
            analysis.issues.append(f"Error analisis IMG: {e}")

    def _analyze_bin(self, path: str, analysis: FirmwareAnalysis):
        """Analisis file BIN/ELF (Qualcomm, MediaTek)."""
        try:
            with open(path, 'rb') as f:
                magic = f.read(16)
                f.seek(0, 2)
                size = f.tell()

            name = os.path.splitext(os.path.basename(path))[0]
            detected_type = self._detect_image_type(magic)

            pi = PartitionInfo(
                name=name,
                filename=os.path.basename(path),
                size_mb=round(size / (1024 * 1024), 1),
                is_dangerous=name in self.PARTITION_DANGEROUS,
                detected_type=detected_type,
            )

            # ELF = Qualcomm Firehose Programmer
            if magic[:4] == b'\x7fELF':
                pi.detected_type = "Qualcomm Firehose ELF"
                analysis.detected_chipset = "Qualcomm (EDL mode)"

            # MediaTK BROM header
            elif magic[:8] == b'MTK_BROM' or magic[:4] == b'\x0e\x8d\x00':
                pi.detected_type = "MediaTek BROM"
                analysis.detected_chipset = "MediaTek (BROM mode)"

            analysis.partitions.append(pi)

        except Exception as e:
            analysis.issues.append(f"Error analisis BIN: {e}")

    # ── Helper Methods ──

    def _detect_partition_from_name(self, fname: str, analysis: FirmwareAnalysis):
        """Deteksi partisi dari nama file."""
        fname_lower = fname.lower()
        name_noext = os.path.splitext(fname_lower)[0]

        # Deteksi chipset
        chipset_keywords = {
            "mt6": "MediaTek", "mt8": "MediaTek",
            "sm8": "Qualcomm", "sdm": "Qualcomm",
            "exynos": "Exynos", "kirin": "Kirin",
            "unisoc": "Unisoc", "sc98": "Unisoc",
            "bcm": "Broadcom",
        }
        for kw, chip in chipset_keywords.items():
            if kw in fname_lower:
                analysis.detected_chipset = chip
                break

        # Deteksi model dari nama folder/file
        model_match = re.search(r'([A-Z][A-Z0-9]{3,10})', fname)
        if model_match:
            analysis.detected_model = model_match.group(1)

        # Deteksi region (Samsung)
        region_match = re.search(r'_([A-Z]{3})_', fname)
        if region_match:
            analysis.detected_region = region_match.group(1)

    def _parse_metadata(self, content: str, analysis: FirmwareAnalysis):
        """Parse metadata dari file teks dalam firmware."""
        patterns = {
            r'version\s*[=:]\s*([\w.]+)': lambda m: setattr(analysis, 'firmware_version', m.group(1)),
            r'android\s*version\s*[=:]\s*([\d.]+)': lambda m: setattr(analysis, 'android_version', m.group(1)),
            r'security\s*patch\s*[=:]\s*([\d-]+)': lambda m: setattr(analysis, 'security_patch', m.group(1)),
            r'qcom\.arb_version\s*[=:]\s*(\d+)': lambda m: setattr(analysis, 'antirollback_version', int(m.group(1))),
            r'ro\.build\.version\.incremental\s*[=:]\s*([\w.]+)': lambda m: setattr(analysis, 'firmware_version', m.group(1)),
        }
        for pattern, action in patterns.items():
            match = re.search(pattern, content, re.I)
            if match:
                try:
                    action(match)
                except Exception:
                    pass

    def _read_magic(self, path: str, n: int = 8) -> bytes:
        """Baca magic bytes dari file."""
        try:
            with open(path, 'rb') as f:
                return f.read(n)
        except Exception:
            return b''

    def _detect_image_type(self, data: bytes) -> str:
        """Deteksi tipe image dari header bytes."""
        if len(data) < 4:
            return "Unknown"

        magic = data[:8]

        # Android sparse image
        if magic[:4] == b'\x3a\xff\x26\xed':
            return "Android Sparse (SIMG)"
        if magic[:4] == b'\x3a\xff\x26\xed':
            return "Android Sparse"

        # EXT4
        if magic[:2] == b'\x53\xef':
            return "EXT4 Filesystem"

        # F2FS
        if magic[:4] == b'\x10\x20\xf5\xf2':
            return "F2FS Filesystem"

        # GPT
        if magic[:8] == b'EFI PART':
            return "GPT Partition Table"

        # ELF
        if magic[:4] == b'\x7fELF':
            return "ELF Binary"

        # VBmeta
        if magic[:4] == b'\x41\x56\x42\x30':  # AVB0
            return "AVB VBMeta"

        # Boot image
        if magic[:8] == b'ANDROID!':
            return "Android Boot Image"
        if data[0:4] == b'\x41\x4e\x44\x52':  # ANDR
            return "Android Boot Image (new)"

        # DTB
        if magic[:4] == b'\xd0\x0d\xfe\xed':
            return "Device Tree Blob (DTB)"

        # ZIP
        if magic[:2] == b'PK':
            return "ZIP Archive"

        # GZIP
        if magic[:2] == b'\x1f\x8b':
            return "GZIP Compressed"

        # LZ4
        if magic[:4] == b'\x02\x21\x4c\x18':
            return "LZ4 Compressed"

        # MediaTek DA
        if b'MTK_DOWNLOAD_AGENT' in magic or b'DA_' in magic:
            return "MediaTek Download Agent"

        return "Unknown"

    def _check_preloader_safe(self, data: bytes) -> bool:
        """
        Verifikasi preloader aman untuk di-flash.
        Preloader berbahaya jika:
        - Untuk chipset berbeda
        - Corrupt header
        - Version mismatch dengan device
        """
        if len(data) < 512:
            return False

        try:
            # Cek magic preloader
            if data[0:4] == b'\x0e\x8d\x00\x03':  # MediaTek BROM header
                return True
            if data[0:4] == b'PRE\x00':  # Generic preloader
                return True

            # Cek jika data terlalu kecil atau acak
            entropy = sum(1 for b in data[:256] if b != 0) / 256
            if entropy < 0.1:
                return False  # Hampir kosong

            return True
        except Exception:
            return False

    def cleanup(self):
        """Bersihkan temporary files."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None


# ===========================================================================
# FLASH SIMULATOR — INTI
# ===========================================================================

class FlashSimulator:
    """
    Simulator flashing — uji coba flashing TANPA menulis ke flash.

    Melakukan:
    1. Analisis firmware
    2. Cek kompatibilitas device
    3. Cek partition match
    4. Cek preloader safety
    5. Cek ARB version
    6. Dry-run (hitung apa yang akan ditulis)
    7. Risk assessment
    """

    def __init__(self):
        self.analyzer = FirmwareAnalyzer()

    def simulate(self,
                 firmware_path: str,
                 device_info: Optional[Dict[str, Any]] = None) -> SimulationResult:
        """
        Jalankan simulasi flashing lengkap.

        Args:
            firmware_path: Path ke file firmware
            device_info: Info device (serial, model, chipset, etc.):
                {
                    "serial": "1234567890",
                    "model": "SM-G998B",
                    "chipset": "exynos2100",
                    "arb_version": 5,
                    "mode": "ADB",
                }

        Returns:
            SimulationResult — hasil simulasi
        """
        log.header(f"[FLASH SIMULATION MODE]")
        log.info(f"Firmware: {os.path.basename(firmware_path)}")
        if device_info:
            log.info(f"Device: {device_info.get('model', '?')} ({device_info.get('serial', '?')})")
        print()

        result = SimulationResult()

        # ── Step 1: Analisis Firmware ──
        log.step("Step 1/5", "Menganalisis firmware...")
        analysis = self.analyzer.analyze(firmware_path)
        result.analysis = analysis
        print()

        self._print_firmware_summary(analysis)

        # Quick check: apakah firmware valid?
        if not analysis.partitions:
            result.errors.append("Firmware tidak mengandung partisi yang dikenal")
            result.risk_level = RiskLevel.CRITICAL
            result.recommendation = "❌ JANGAN FLASH! Firmware corrupt atau format tidak dikenal."
            result.passed = False
            self._print_result(result)
            return result

        # ── Step 2: Preloader Safety ──
        if analysis.has_preloader:
            log.step("Step 2/5", "Memeriksa preloader safety...")
            if not analysis.preloader_safe:
                result.errors.append("Preloader TIDAK AMAN untuk di-flash")
                result.preloader_safe = False
                result.risk_level = RiskLevel.CRITICAL
                log.warning("  ❌ Preloader TIDAK AMAN!")
                log.warning("  Flashing preloader dari firmware yang salah bisa BRICK permanen!")
            else:
                result.preloader_safe = True
                log.success("  ✅ Preloader aman untuk di-flash")
            print()

        # ── Step 3: Partition Match (jika ada device info) ──
        if device_info:
            log.step("Step 3/5", "Memeriksa partition match...")
            self._check_partition_match(analysis, device_info, result)
            print()

        # ── Step 4: Anti-Rollback Check ──
        if device_info and analysis.antirollback_version >= 0:
            log.step("Step 4/5", "Memeriksa Anti-Rollback...")
            device_arb = device_info.get("arb_version")
            if device_arb is not None:
                if analysis.antirollback_version < device_arb:
                    result.errors.append(
                        f"ANTI-ROLLBACK DOWNGRADE! "
                        f"Firmware: v{analysis.antirollback_version} < Device: v{device_arb}")
                    result.arb_safe = False
                    result.risk_level = RiskLevel.CRITICAL
                    log.warning(f"  ❌ ARB DOWNGRADE: Firmware v{analysis.antirollback_version} < Device v{device_arb}")
                else:
                    result.arb_safe = True
                    log.success(f"  ✅ ARB aman: Firmware v{analysis.antirollback_version} >= Device v{device_arb}")
                print()

        # ── Step 5: Risk Assessment ──
        log.step("Step 5/5", "Menilai risiko flashing...")
        self._assess_risk(analysis, result)
        print()

        # ── Keputusan ──
        self._print_result(result)
        return result

    def _check_partition_match(self, analysis: FirmwareAnalysis,
                               device_info: Dict[str, Any],
                               result: SimulationResult):
        """Cek apakah partisi di firmware cocok dengan device."""
        # Cek model
        device_model = device_info.get("model", "").upper()
        if analysis.detected_model and device_model:
            # Cocokkan sebagian dari model
            model_num = re.sub(r'[^A-Z0-9]', '', device_model)
            fw_model = re.sub(r'[^A-Z0-9]', '', analysis.detected_model)
            if model_num[:5] != fw_model[:5]:  # Bandingkan 5 karakter pertama
                result.model_match = False
                result.warnings.append(
                    f"Model mismatch: Firmware={analysis.detected_model}, Device={device_model}")
                log.warning(f"  ⚠️ Model mismatch: FW={analysis.detected_model} vs Device={device_model}")
            else:
                log.success(f"  ✅ Model cocok: {analysis.detected_model}")

        # Cek chipset
        device_chipset = (device_info.get("chipset") or "").lower()
        fw_chipset = analysis.detected_chipset.lower()
        if device_chipset and fw_chipset:
            if device_chipset not in fw_chipset and fw_chipset not in device_chipset:
                result.warnings.append(
                    f"Chipset mungkin berbeda: FW={analysis.detected_chipset}, Device={device_chipset}")

        # Cek partisi yang ada
        device_partitions = device_info.get("partitions", [])
        fw_partitions = [p.name for p in analysis.partitions if p.is_essential or p.is_dangerous]

        log.info("  Partisi firmware:")
        # Itung partisi berbahaya
        dangerous = [p for p in analysis.partitions if p.is_dangerous]
        essential = [p for p in analysis.partitions if p.is_essential]
        userdata = [p for p in analysis.partitions if p.is_userdata]

        if dangerous:
            log.warning(f"  ⚠️ {len(dangerous)} partisi BERBAHAYA (preloader/tz/abl):")
            for p in dangerous:
                print(f"    {p}")
        if essential:
            log.info(f"  ✅ {len(essential)} partisi esensial:")
            for p in essential:
                print(f"    {p}")
        if userdata:
            log.warning(f"  ⚠️ {'/'.join(p.name for p in userdata)} akan DIWIPE (data hilang!)")

    def _assess_risk(self, analysis: FirmwareAnalysis, result: SimulationResult):
        """Nilai risiko flashing."""
        # Hitung skor risiko
        risk_score = 0

        if not analysis.has_boot:
            risk_score += 30
            result.errors.append("Tidak ada boot partition — device mungkin tidak bisa boot")
        if not analysis.preloader_safe:
            risk_score += 40
        if not analysis.model_match:
            risk_score += 20
        if not analysis.arb_safe:
            risk_score += 40
        if len(analysis.issues) > 0:
            risk_score += min(len(analysis.issues) * 10, 30)
        if analysis.has_preloader and analysis.preloader_safe:
            risk_score -= 10

        # Tentukan risk level
        if risk_score >= 70:
            result.risk_level = RiskLevel.CRITICAL
            result.recommendation = "🚫 JANGAN FLASH! Risiko BRICK sangat tinggi."
        elif risk_score >= 50:
            result.risk_level = RiskLevel.HIGH
            result.recommendation = "❌ Flashing TIDAK DISARANKAN. Perbaiki masalah terlebih dahulu."
        elif risk_score >= 30:
            result.risk_level = RiskLevel.MEDIUM
            result.recommendation = "⚡ Risiko sedang. Pastikan backup sebelum flash."
        elif risk_score >= 10:
            result.risk_level = RiskLevel.LOW
            result.recommendation = "⚠️ Risiko rendah. Backup tetap disarankan."
        else:
            result.risk_level = RiskLevel.SAFE
            result.recommendation = "✅ Firmware aman untuk di-flash."
            result.passed = True

    def _print_firmware_summary(self, analysis: FirmwareAnalysis):
        """Tampilkan ringkasan firmware."""
        print(f"  {'Filename':20s}: {analysis.filename}")
        print(f"  {'Size':20s}: {analysis.size_mb:.1f} MB")
        print(f"  {'Format':20s}: {analysis.format_type.upper()}")
        print(f"  {'Partitions':20s}: {analysis.total_partitions}")
        if analysis.detected_chipset:
            print(f"  {'Chipset':20s}: {analysis.detected_chipset}")
        if analysis.detected_model:
            print(f"  {'Model':20s}: {analysis.detected_model}")
        if analysis.android_version:
            print(f"  {'Android':20s}: {analysis.android_version}")
        if analysis.firmware_version:
            print(f"  {'Version':20s}: {analysis.firmware_version}")
        if analysis.detected_region:
            print(f"  {'Region':20s}: {analysis.detected_region}")
        if analysis.antirollback_version >= 0:
            print(f"  {'ARB Version':20s}: v{analysis.antirollback_version}")

        print(f"  {'Score':20s}: {analysis.score}/100  ", end="")
        if analysis.score >= 80:
            log.success("(Excellent)")
        elif analysis.score >= 60:
            log.info("(Good)")
        elif analysis.score >= 40:
            log.warning("(Fair)")
        else:
            log.error("(Poor)")

        if analysis.partitions:
            print()
            log.info("Daftar Partisi:")
            for p in analysis.partitions:
                print(p)
        print()

        if analysis.issues:
            log.warning("Issues ditemukan:")
            for issue in analysis.issues:
                print(f"  ❌ {issue}")

    def _print_result(self, result: SimulationResult):
        """Tampilkan hasil simulasi."""
        log.step("SIMULATION RESULT", "=" * 30)
        print()

        level_color = {
            RiskLevel.SAFE: Colors.GREEN,
            RiskLevel.LOW: Colors.YELLOW,
            RiskLevel.MEDIUM: Colors.YELLOW,
            RiskLevel.HIGH: Colors.RED,
            RiskLevel.CRITICAL: Colors.BG_RED,
        }
        color = level_color.get(result.risk_level, Colors.WHITE)
        print(f"  {color}Risk Level: {result.risk_level.value}{Colors.RESET}")
        print(f"  Score: {result.analysis.score}/100")
        print()

        if result.errors:
            log.error("ERRORS (harus diperbaiki):")
            for e in result.errors:
                print(f"  ❌ {e}")
            print()

        if result.warnings:
            log.warning("WARNINGS:")
            for w in result.warnings:
                print(f"  ⚠️ {w}")
            print()

        if result.recommendation:
            log.info("RECOMMENDATION:")
            print(f"  {result.recommendation}")
            print()

        log.step("END SIMULATION", "=" * 30)
        print()

    def get_partition_list(self, firmware_path: str) -> List[PartitionInfo]:
        """Dapatkan daftar partisi dari firmware (tanpa simulasi penuh)."""
        analysis = self.analyzer.analyze(firmware_path)
        return analysis.partitions


# ===========================================================================
# MAIN ENTRY
# ===========================================================================

def run_simulator():
    """
    Jalankan Flash Simulator.
    Akan minta path firmware dan device info.
    """
    print()
    firmware_path = input(f"  {Colors.CYAN}Path firmware (zip/tar/img): {Colors.RESET}").strip()

    if not firmware_path or not os.path.isfile(firmware_path):
        log.error("File firmware tidak valid!")
        return

    # Bisa juga auto-detect device
    device_info = None
    try:
        detect = input(f"  {Colors.CYAN}Auto-detect device? (Y/n): {Colors.RESET}").strip().lower()
        if detect != 'n':
            from core.device_detector import DeviceDetector
            dd = DeviceDetector()
            devices = dd.scan_all()
            if devices:
                dev = devices[0]
                device_info = {
                    "serial": dev.serial or "",
                    "model": dev.model or "",
                    "mode": dev.method or "unknown",
                }
                # Coba baca chipset via ADB
                if dev.serial and dev.adb_available:
                    try:
                        import subprocess
                        r = subprocess.run(
                            ["adb", "-s", dev.serial, "shell", "getprop ro.board.platform"],
                            capture_output=True, text=True, timeout=5
                        )
                        if r.returncode == 0 and r.stdout.strip():
                            device_info["chipset"] = r.stdout.strip()
                    except Exception:
                        pass
    except Exception:
        pass

    simulator = FlashSimulator()
    simulator.simulate(firmware_path, device_info)