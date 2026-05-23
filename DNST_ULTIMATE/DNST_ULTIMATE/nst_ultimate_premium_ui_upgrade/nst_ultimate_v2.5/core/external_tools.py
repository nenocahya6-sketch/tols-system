

"""
NST External Tools Integration v1.0
====================================
Manager untuk integrasi tool eksternal: mtkclient, heimdall, libimobiledevice, qpst/qfil.

Setiap tool di-wrap dalam class sendiri dengan method:
- check() -> bool       : Cek apakah tool tersedia
- get_version() -> str  : Dapatkan versi tool
- get_help() -> str     : Dapatkan panduan singkat

Setiap tool juga memiliki method operasi spesifik (flash, backup, detect, dll.)
"""
from core import clean_console_output



import os
import sys
import json
import time
import shutil
import platform
import subprocess
import threading
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


# ===========================================================================
# Tool Status & Result Types
# ===========================================================================

class ToolStatus(Enum):
    """Status ketersediaan tool."""
    AVAILABLE = auto()       # Tool tersedia dan berfungsi
    NOT_FOUND = auto()       # Tool tidak ditemukan di PATH
    WRONG_VERSION = auto()   # Versi terlalu tua
    ERROR = auto()           # Error saat pengecekan
    NOT_INSTALLED = auto()   # Belum diinstall


@dataclass
class ToolResult:
    """Hasil eksekusi tool."""
    success: bool = False
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    data: Any = None
    error_message: str = ""

    @property
    def output(self) -> str:
        """Gabungan stdout + stderr."""
        out = self.stdout or ""
        if self.stderr:
            out += "\n" + self.stderr
        return out.strip()


# ===========================================================================
# BASE TOOL WRAPPER
# ===========================================================================

class BaseTool:
    """Base class untuk semua wrapper tool eksternal."""

    name: str = ""
    binary: str = ""                    # Nama binary di PATH
    description: str = ""
    install_url: str = ""
    install_guide: str = ""
    min_version: Optional[str] = None
    _cached_path: Optional[str] = None
    _cached_status: Optional[ToolStatus] = None
    _os_name: str = platform.system()

    def __init__(self):
        self._lock = threading.Lock()

    # ── Detection ──

    def find_binary(self) -> Optional[str]:
        """Cari binary tool di PATH. Cache hasilnya."""
        if self._cached_path:
            return self._cached_path

        # Cek PATH biasa
        path = shutil.which(self.binary)
        if path:
            self._cached_path = path
            return path

        # Cek di folder tools/ project
        project_tools = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"
        )
        tool_path = os.path.join(project_tools, self.binary)
        if self._os_name == "Windows":
            tool_path += ".exe"
        if os.path.isfile(tool_path):
            self._cached_path = tool_path
            return tool_path

        # Cek di subfolder (misal: tools/mtkclient/)
        if os.path.isdir(project_tools):
            for root, dirs, files in os.walk(project_tools):
                for f in files:
                    if f.lower() == self.binary.lower() or f.lower() == f"{self.binary}.exe".lower():
                        full = os.path.join(root, f)
                        self._cached_path = full
                        return full

        return None

    def check(self) -> ToolStatus:
        """Cek apakah tool tersedia dan berfungsi."""
        if self._cached_status:
            return self._cached_status

        binary = self.find_binary()
        if not binary:
            self._cached_status = ToolStatus.NOT_FOUND
            return self._cached_status

        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self._cached_status = ToolStatus.AVAILABLE
            else:
                self._cached_status = ToolStatus.ERROR
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            self._cached_status = ToolStatus.ERROR

        return self._cached_status

    def is_available(self) -> bool:
        """Cepat cek apakah tool tersedia."""
        return self.check() == ToolStatus.AVAILABLE

    def get_version(self) -> str:
        """Dapatkan versi tool. Return 'unknown' jika gagal."""
        binary = self.find_binary()
        if not binary:
            return "not installed"

        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return clean_console_output(result.stdout).strip().split('\n')[0][:80]
            return "error"
        except Exception:
            return "error"

    # ── Execution ──

    def run(self, args: List[str], timeout: int = 30,
            capture_output: bool = True, check: bool = True) -> ToolResult:
        """
        Jalankan tool dengan arguments.

        Args:
            args: Arguments untuk tool (tanpa binary name)
            timeout: Timeout dalam detik
            capture_output: True = capture stdout/stderr
            check: True = raise exception jika returncode != 0

        Returns:
            ToolResult object
        """
        binary = self.find_binary()
        if not binary:
            return ToolResult(
                success=False,
                error_message=f"{self.name} tidak ditemukan. Install: {self.install_url}"
            )

        try:
            result = subprocess.run(
                [binary] + args,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            return ToolResult(
                success=result.returncode == 0,
                stdout=clean_console_output(result.stdout),
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error_message=f"{self.name} timeout setelah {timeout}s"
            )
        except FileNotFoundError:
            self._cached_path = None
            self._cached_status = ToolStatus.NOT_FOUND
            return ToolResult(
                success=False,
                error_message=f"{self.name} tidak ditemukan"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error_message=str(e)
            )

    def run_piped(self, args: List[str], input_data: Optional[str] = None,
                  timeout: int = 30) -> ToolResult:
        """Jalankan tool dengan input pipe."""
        binary = self.find_binary()
        if not binary:
            return ToolResult(success=False, error_message=f"{self.name} tidak ditemukan")

        try:
            result = subprocess.run(
                [binary] + args,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return ToolResult(
                success=result.returncode == 0,
                stdout=clean_console_output(result.stdout),
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except Exception as e:
            return ToolResult(success=False, error_message=str(e))

    def reset_cache(self):
        """Reset cache status & path."""
        self._cached_path = None
        self._cached_status = None

    def get_install_guide(self) -> str:
        """Return panduan install tool."""
        lines = [f"=== {self.name} ==="]
        lines.append(f"  Deskripsi: {self.description}")
        lines.append(f"  Binary: {self.binary}")
        lines.append(f"  Download: {self.install_url}")
        if self.install_guide:
            lines.append(f"  Panduan: {self.install_guide}")
        lines.append("")
        return "\n".join(lines)


# ===========================================================================
# M T K C L I E N T   W R A P P E R
# ===========================================================================

class MTKClientTool(BaseTool):
    """
    Wrapper untuk mtkclient — MediaTek BROM/Preloader/DA operations.

    mtkclient adalah tool open-source untuk berkomunikasi dengan chipset MediaTek
    via BROM (BootROM) mode. Supports: read/write flash, bypass auth, format, dll.

    GitHub: https://github.com/bkerler/mtkclient
    """

    name = "mtkclient"
    binary = "mtk"
    description = "MediaTek BROM/Preloader/DA client — flash, unlock, bypass auth"
    install_url = "https://github.com/bkerler/mtkclient"
    install_guide = """
    Install:
      1. git clone https://github.com/bkerler/mtkclient
      2. cd mtkclient
      3. pip install -r requirements.txt
      4. python setup.py install
      5. Atau langsung jalankan: python mtk_gui.py

    Untuk Windows:
      - Download dari releases GitHub
      - Atau jalankan via WSL/Linux VM

    Pastikan driver VCOM MediaTek terinstall:
      - Gunakan Zadig: https://zadig.akeo.ie/
      - Install driver WinUSB untuk device MediaTek VCOM (VID 0x0E8D)
    """

    def __init__(self):
        super().__init__()
        self._da_loaded = False

    # ── Preloader / BROM Operations ──

    def detect(self) -> ToolResult:
        """Deteksi device MediaTek di BROM/Preloader mode."""
        return self.run(["printgpt"], timeout=15)

    def printgpt(self) -> ToolResult:
        """Baca partition table (GPT) dari device."""
        return self.run(["printgpt"], timeout=15)

    def read_flash(self, partition: str = "", output: str = "",
                   start: int = 0, length: int = 0) -> ToolResult:
        """Baca flash/partition dari device MediaTek."""
        args = ["r", partition] if partition else ["r"]
        if output:
            args += [output]
        if start and length:
            args += [hex(start), hex(length)]
        return self.run(args, timeout=120)

    def write_flash(self, partition: str, filepath: str) -> ToolResult:
        """Write file ke partition MediaTek."""
        return self.run(["w", partition, filepath], timeout=120)

    def format_flash(self, partition: str = "") -> ToolResult:
        """Format partition atau seluruh flash."""
        args = ["format"] if not partition else ["format", partition]
        return self.run(args, timeout=60)

    def da(self) -> ToolResult:
        """Load Download Agent ke device."""
        result = self.run(["da"], timeout=30)
        if result.success:
            self._da_loaded = True
        return result

    def bypass_auth(self) -> ToolResult:
        """Bypass authentication (untuk device dengan auth)."""
        return self.run(["bypass"], timeout=30)

    def payload(self, payload_file: str) -> ToolResult:
        """Kirim custom payload ke device."""
        return self.run(["payload", payload_file], timeout=30)

    def reset(self) -> ToolResult:
        """Reset device."""
        return self.run(["reset"], timeout=15)

    def info(self) -> ToolResult:
        """Dapatkan info device (chip, HW, SW, dll)."""
        result = self.run(["info"], timeout=15)
        return result

    def get_chip(self) -> Optional[str]:
        """Dapatkan nama chipset MediaTek."""
        result = self.info()
        if result.success:
            for line in clean_console_output(result.stdout).split('\n'):
                if "chip" in line.lower() or "hw" in line.lower():
                    return line.strip()
        return None

    def dump_brom(self, output: str = "brom_dump.bin") -> ToolResult:
        """Dump BROM dari device."""
        return self.run(["dump", "brom", output], timeout=60)

    # ── High-level operations ──

    def flash_firmware(self, scatter_file: str, firmwares_dir: str) -> ToolResult:
        """
        Flash firmware lengkap dari scatter.txt + folder firmware.

        Args:
            scatter_file: Path ke scatter.txt
            firmwares_dir: Folder berisi file firmware (*.img, *.bin)
        """
        return self.run(["--load", scatter_file, firmwares_dir], timeout=300)

    def auto_flash(self, scatter_file: str) -> bool:
        """
        Auto flash: da -> bypass (jika perlu) -> flash from scatter.

        Returns True jika sukses.
        """
        # Step 1: Load DA
        da_result = self.da()
        if not da_result.success:
            return False
        time.sleep(1)

        # Step 2: Bypass auth
        self.bypass_auth()
        time.sleep(1)

        # Step 3: Flash from scatter
        result = self.flash_firmware(scatter_file, os.path.dirname(scatter_file))
        return result.success


# ===========================================================================
# H E I M D A L L   W R A P P E R
# ===========================================================================

class HeimdallTool(BaseTool):
    """
    Wrapper untuk heimdall — Samsung Odin protocol flashing tool.

    Heimdall adalah cross-platform open-source tool untuk flash firmware
    Samsung via Download Mode (Odin protocol).

    GitHub: https://github.com/Benjamin-Dobell/Heimdall
    """

    name = "heimdall"
    binary = "heimdall"
    description = "Samsung Odin protocol flasher — flash firmware, PIT operations"
    install_url = "https://github.com/Benjamin-Dobell/Heimdall"
    install_guide = """
    Install:
      Windows:
        - Download installer dari https://glassechidna.com.au/heimdall/
        - Atau via Scoop: scoop install heimdall

      Linux:
        - sudo apt install heimdall-flash (Debian/Ubuntu)
        - sudo dnf install heimdall (Fedora)

      Mac:
        - brew install heimdall

    Driver:
      Windows: Install Samsung USB Driver
        https://developer.samsung.com/android-usb-driver
    """

    def __init__(self):
        super().__init__()
        # Heimdall di beberapa distro bernama 'heimdall-flash'
        if self._os_name != "Windows":
            alt = shutil.which("heimdall-flash")
            if alt and not shutil.which("heimdall"):
                self.binary = "heimdall-flash"

    # ── Detection ──

    def detect(self) -> ToolResult:
        """Deteksi Samsung device di Download Mode."""
        return self.run(["detect"], timeout=10)

    def print_pit(self) -> ToolResult:
        """Baca dan tampilkan PIT (Partition Information Table)."""
        return self.run(["print-pit"], timeout=15)

    def download_pit(self, output: str = "samsung.pit") -> ToolResult:
        """Download PIT dari device ke file."""
        return self.run(["download-pit", "--output", output], timeout=15)

    # ── Flash Operations ──

    def flash(self, partition: str, filepath: str) -> ToolResult:
        """
        Flash file ke partition tertentu.

        Example:
            flash("SYSTEM", "system.img")
            flash("BOOT", "boot.img")
        """
        return self.run(["flash", f"--{partition}", filepath, "--no-reboot"], timeout=120)

    def flash_all(self, files: Dict[str, str]) -> List[ToolResult]:
        """
        Flash multiple partitions sekaligus.

        Args:
            files: Dict {partition_name: file_path}
                   Example: {"SYSTEM": "system.img", "BOOT": "boot.img"}

        Returns: List of ToolResult untuk setiap flash
        """
        results = []
        for partition, filepath in files.items():
            result = self.flash(partition, filepath)
            results.append(result)
            if not result.success:
                break
        return results

    def flash_firmware_from_dir(self, firmware_dir: str) -> ToolResult:
        """Flash semua file firmware dari folder."""
        if not os.path.isdir(firmware_dir):
            return ToolResult(success=False, error_message=f"Folder tidak ditemukan: {firmware_dir}")

        # Cari file-file firmware umum
        args = []
        for f in sorted(os.listdir(firmware_dir)):
            f_lower = f.lower()
            if f_lower.endswith('.img') or f_lower.endswith('.bin') or f_lower.endswith('.elf'):
                partition = os.path.splitext(f)[0].upper()
                args += [f"--{partition}", os.path.join(firmware_dir, f)]

        if not args:
            return ToolResult(success=False, error_message="Tidak ada file .img/.bin/.elf di folder")

        args.append("--no-reboot")
        return self.run(["flash"] + args, timeout=300)

    def close_pc_screen(self) -> ToolResult:
        """Close PC screen (untuk device Samsung tertentu)."""
        return self.run(["close-pc-screen"], timeout=10)

    def info(self) -> ToolResult:
        """Info device."""
        return self.run(["info"], timeout=10)


# ===========================================================================
# L I B I M O B I L E D E V I C E   W R A P P E R
# ===========================================================================

class LibIMobileDeviceTool(BaseTool):
    """
    Wrapper untuk libimobiledevice — Apple iPhone/iDevice tools.

    libimobiledevice adalah library cross-platform untuk berkomunikasi
    dengan device Apple (iPhone, iPad, iPod) tanpa iTunes.

    Website: https://libimobiledevice.org/
    GitHub: https://github.com/libimobiledevice/libimobiledevice
    """

    name = "libimobiledevice"
    binary = "idevice_id"
    description = "Apple device tools — backup, restore, activation, file access"
    install_url = "https://libimobiledevice.org/"
    install_guide = """
    Install:
      Windows:
        - Download dari https://github.com/libimobiledevice-win32/imobiledevice-net/releases
        - Atau via: pip install pyimg4

      Linux:
        - sudo apt install libimobiledevice-utils libusbmuxd-tools
        - sudo dnf install libimobiledevice-utils

      Mac:
        - brew install libimobiledevice
        - brew install usbmuxd

    Tools yang disediakan:
      idevice_id        - List device UDID
      ideviceinfo       - Dapatkan info device
      idevicebackup     - Backup device
      idevicebackup2    - Backup (encrypted)
      idevicerestore    - Restore firmware
      ideviceenterrecovery - Masuk Recovery mode
      idevicepair       - Pair dengan device
      idevicesyslog     - Baca system log
      ideviceprovision  - Manage provision profiles
      irecovery         - Low-level recovery/DFU operations
    """

    def __init__(self):
        super().__init__()
        self._paired = False

    # ── Device Detection ──

    def list_devices(self) -> ToolResult:
        """List semua device Apple yang terhubung (return UDIDs)."""
        return self.run(["-l"], timeout=5)

    def get_info(self, key: str = "") -> ToolResult:
        """
        Dapatkan info device dari key tertentu.

        Args:
            key: Key info (ProductType, ProductVersion, DeviceName, SerialNumber, dll.)
                 Kosongkan untuk semua info.
        """
        if key:
            return self.run(["ideviceinfo", "-k", key], timeout=10)
        return self.run(["ideviceinfo"], timeout=10)

    def get_udid(self) -> Optional[str]:
        """Dapatkan UDID device pertama yang terhubung."""
        result = self.list_devices()
        if result.success and clean_console_output(result.stdout).strip():
            return clean_console_output(result.stdout).strip().split('\n')[0].strip()
        return None

    # ── Backup & Restore ──

    def backup(self, output_dir: str, full: bool = False) -> ToolResult:
        """
        Backup iPhone/iPad.

        Args:
            output_dir: Folder tujuan backup
            full: True = full backup (all apps + data)
        """
        args = ["idevicebackup2", "backup", output_dir]
        if not full:
            args.append("--partial")
        return self.run(args, timeout=600)

    def backup_encrypted(self, output_dir: str) -> ToolResult:
        """
        Backup terenkripsi.

        Args:
            output_dir: Folder tujuan backup
        """
        return self.run(["idevicebackup2", "backup", "--encrypted", output_dir], timeout=600)

    def restore_backup(self, backup_dir: str) -> ToolResult:
        """Restore device dari backup."""
        return self.run(["idevicebackup2", "restore", backup_dir], timeout=600)

    # ── Recovery / DFU Operations ──

    def enter_recovery(self) -> ToolResult:
        """Reboot device ke Recovery Mode."""
        return self.run(["ideviceenterrecovery"], timeout=15)

    def exit_recovery(self) -> ToolResult:
        """Keluar dari Recovery Mode."""
        # Gunakan irecovery untuk exit recovery
        result = self.run_irecovery(["-n"], timeout=15)
        return result

    def get_recovery_info(self) -> ToolResult:
        """Dapatkan info dari device di Recovery mode."""
        # irecovery -i -> device info di recovery
        result = self.run_irecovery(["-i"], timeout=10)
        return result

    def send_iboot_command(self, cmd: str) -> ToolResult:
        """
        Kirim command iBoot ke device (di DFU/Recovery).
        Contoh: "go", "reset", "setenv auto-boot true", "saveenv"
        """
        return self.run_irecovery(["-c", cmd], timeout=15)

    # ── Pairing ──

    def pair(self) -> ToolResult:
        """Pair dengan device (wajib untuk backup/restore)."""
        result = self.run(["idevicepair", "pair"], timeout=15)
        if result.success:
            self._paired = True
        return result

    def unpair(self) -> ToolResult:
        """Unpair device."""
        result = self.run(["idevicepair", "unpair"], timeout=10)
        self._paired = False
        return result

    def is_paired(self) -> bool:
        """Cek apakah device sudah paired."""
        result = self.run(["idevicepair", "validate"], timeout=10)
        return result.success

    # ── File Operations (AFC) ──

    def list_files(self, path: str = "/") -> ToolResult:
        """List file di device via AFC."""
        return self.run(["idevicefs", "ls", path], timeout=10)

    def pull_file(self, remote_path: str, local_path: str) -> ToolResult:
        """Copy file dari device ke PC."""
        return self.run(["idevicefs", "pull", remote_path, local_path], timeout=60)

    def push_file(self, local_path: str, remote_path: str) -> ToolResult:
        """Copy file dari PC ke device."""
        return self.run(["idevicefs", "push", local_path, remote_path], timeout=60)

    # ── System Operations ──

    def get_syslog(self, lines: int = 50) -> ToolResult:
        """Baca system log device."""
        return self.run(["idevicesyslog"], timeout=10)

    def get_crashreport(self) -> ToolResult:
        """Dapatkan crash report."""
        return self.run(["idevicecrashreport", "-e", "."], timeout=30)

    # ── Activation ──

    def get_activation_state(self) -> ToolResult:
        """Cek status activation lock."""
        return self.run(["ideviceactivation", "info"], timeout=10)

    # ── irecovery wrapper ──

    def run_irecovery(self, args: List[str], timeout: int = 30) -> ToolResult:
        """Jalankan irecovery command."""
        irecovery_bin = shutil.which("irecovery")
        if not irecovery_bin:
            # Cek di tools folder
            tools_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"
            )
            irecovery_bin = os.path.join(tools_dir, "irecovery")
            if not os.path.isfile(irecovery_bin):
                return ToolResult(
                    success=False,
                    error_message="irecovery tidak ditemukan. Install libimobiledevice."
                )

        try:
            result = subprocess.run(
                [irecovery_bin] + args,
                capture_output=True, text=True, timeout=timeout
            )
            return ToolResult(
                success=result.returncode == 0,
                stdout=clean_console_output(result.stdout),
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except Exception as e:
            return ToolResult(success=False, error_message=str(e))

    # ── Restore IPSW ──

    def restore_ipsw(self, ipsw_path: str) -> ToolResult:
        """
        Restore firmware IPSW ke device (via idevicerestore).

        Args:
            ipsw_path: Path ke file IPSW (iOS firmware)
        """
        idevicerestore = shutil.which("idevicerestore")
        if not idevicerestore:
            return ToolResult(
                success=False,
                error_message="idevicerestore tidak ditemukan. Install dari https://github.com/libimobiledevice/idevicerestore"
            )
        try:
            result = subprocess.run(
                [idevicerestore, "-e", "-y", ipsw_path],
                capture_output=True, text=True, timeout=600
            )
            return ToolResult(
                success=result.returncode == 0,
                stdout=clean_console_output(result.stdout),
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except Exception as e:
            return ToolResult(success=False, error_message=str(e))


# ===========================================================================
# Q P S T / Q F I L   W R A P P E R
# ===========================================================================

class QPSTTool(BaseTool):
    """
    Wrapper untuk QPST/QFIL — Qualcomm EDL flashing tool.

    QPST (Qualcomm Product Support Tools) adalah tool oficial Qualcomm
    untuk flash firmware via EDL (Emergency Download) mode.

    QFIL adalah GUI wrapper untuk QPST yang support Firehose programmer.

    Download: https://qpsttool.com/
    """

    name = "qpst"
    binary = "QFIL"  # QFIL.exe di Windows
    description = "Qualcomm EDL flasher — flash via Sahara/Firehose protocol"
    install_url = "https://qpsttool.com/"
    install_guide = """
    Install:
      Windows (hanya Windows):
        1. Download QPST dari https://qpsttool.com/
        2. Jalankan installer sebagai Administrator
        3. QFIL.exe ada di: C:\\Program Files (x86)\\Qualcomm\\QPST\\bin\\
        4. Install Qualcomm USB Driver:
           - QDLoader 9008 driver (VID 0x05C6, PID 0x9008)
           - Gunakan Zadig jika perlu

      Linux/Mac:
        QPST hanya tersedia untuk Windows.
        Alternatif: gunakan edl (python tool):
          pip install edl
          https://github.com/bkerler/edl
    """

    def __init__(self):
        super().__init__()
        # Cek alternatif: edl (open-source Python)
        self._edl = None

    def get_edl(self) -> Optional[BaseTool]:
        """Dapatkan EDL tool (open-source alternative)."""
        if self._edl is None:
            edl_bin = shutil.which("edl")
            if edl_bin:
                self._edl = BaseTool()
                self._edl.name = "edl"
                self._edl.binary = "edl"
                self._edl.description = "Qualcomm EDL client (open-source)"
                self._edl.install_url = "https://github.com/bkerler/edl"
        return self._edl

    def check(self) -> ToolStatus:
        """Cek QPST atau EDL tool."""
        # Cek EDL dulu (open-source, cross-platform)
        edl = self.get_edl()
        if edl and edl.is_available():
            self._cached_status = ToolStatus.AVAILABLE
            return self._cached_status

        # Cek QFIL (Windows only)
        if self._os_name == "Windows":
            # Coba cari QFIL di PATH atau default location
            qfil_paths = [
                r"C:\Program Files (x86)\Qualcomm\QPST\bin\QFIL.exe",
                r"C:\Program Files\Qualcomm\QPST\bin\QFIL.exe",
            ]
            for p in qfil_paths:
                if os.path.isfile(p):
                    self._cached_path = p
                    self._cached_status = ToolStatus.AVAILABLE
                    return self._cached_status

        return ToolStatus.NOT_FOUND

    def check_edl(self) -> bool:
        """Cek apakah EDL tool tersedia."""
        edl = self.get_edl()
        return edl is not None and edl.is_available()

    # ── EDL Operations (via edl tool) ──

    def edl_run(self, args: List[str], timeout: int = 60) -> ToolResult:
        """Jalankan EDL command."""
        edl = self.get_edl()
        if not edl:
            return ToolResult(
                success=False,
                error_message="EDL tool tidak ditemukan. Install: pip install edl"
            )
        return edl.run(args, timeout=timeout)

    def edl_detect(self) -> ToolResult:
        """Deteksi Qualcomm device di EDL mode."""
        return self.edl_run(["--edl"], timeout=10)

    def edl_read_flash(self, partition: str, output: str) -> ToolResult:
        """Baca partition dari device Qualcomm di EDL."""
        return self.edl_run(["r", partition, output], timeout=120)

    def edl_write_flash(self, partition: str, filepath: str) -> ToolResult:
        """Write file ke partition Qualcomm."""
        return self.edl_run(["w", partition, filepath], timeout=120)

    def edl_erase(self, partition: str) -> ToolResult:
        """Erase partition."""
        return self.edl_run(["e", partition], timeout=30)

    def edl_reset(self) -> ToolResult:
        """Reset device dari EDL."""
        return self.edl_run(["reset"], timeout=15)

    def edl_printgpt(self) -> ToolResult:
        """Baca partition table Qualcomm."""
        return self.edl_run(["printgpt"], timeout=15)

    def edl_qfil(self, programmer: str, rawprogram: str, patch: str = "") -> ToolResult:
        """
        Flash via EDL menggunakan Firehose programmer.

        Args:
            programmer: Path ke firehose programmer .elf/.mbn
            rawprogram: Path ke rawprogram0.xml
            patch: Path ke patch0.xml (opsional)
        """
        args = ["qfil", "--programmer", programmer, "--rawprogram", rawprogram]
        if patch:
            args += ["--patch", patch]
        return self.edl_run(args, timeout=300)

    # ── QFIL Operations (Windows only) ──

    def qfil_flash(self, programmer_path: str, rawprogram_path: str,
                   patch_path: str = "", contents_dir: str = "") -> ToolResult:
        """
        Flash via QFIL (Windows only).

        Args:
            programmer_path: Path ke prog_ufs_firehose_*.elf
            rawprogram_path: Path ke rawprogram0.xml
            patch_path: Path ke patch0.xml
            contents_dir: Folder berisi file firmware
        """
        if self._os_name != "Windows":
            return ToolResult(success=False, error_message="QFIL hanya untuk Windows")

        qfil_path = self.find_binary()
        if not qfil_path:
            return ToolResult(success=False, error_message="QFIL tidak ditemukan")

        args = [
            "-p", f"COM{self._detect_edl_port()}",
            "-f", programmer_path,
            "-s", rawprogram_path,
        ]
        if patch_path:
            args += ["-v", patch_path]
        if contents_dir:
            args += ["-c", contents_dir]

        return self.run(args, timeout=300)

    def _detect_edl_port(self) -> str:
        """Deteksi port COM untuk EDL device."""
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-WmiObject Win32_SerialPort | Where-Object {$_.Description -like "*Qualcomm*" -or $_.Description -like "*QDLoader*"} | Select-Object -ExpandProperty DeviceID'],
                capture_output=True, text=True, timeout=5
            )
            if clean_console_output(result.stdout).strip():
                port = clean_console_output(result.stdout).strip().split('\n')[0]
                return port.replace("COM", "")
        except Exception:
            pass
        return "3"  # Default fallback


# ===========================================================================
# T O O L   M A N A G E R   —   M A S T E R   C O N T R O L L E R
# ===========================================================================

class ToolManager:
    """
    Master controller untuk semua external tools.

    Singleton — satu instance untuk seluruh aplikasi.
    Menyediakan akses terpusat ke semua tool wrapper + caching status.

    Usage:
        tm = ToolManager()
        if tm.mtkclient.is_available():
            result = tm.mtkclient.detect()

        if tm.heimdall.is_available():
            result = tm.heimdall.print_pit()

        if tm.libimobile.is_available():
            result = tm.libimobile.get_udid()
    """

    _instance: Optional["ToolManager"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Tool instances
        self.mtkclient = MTKClientTool()
        self.heimdall = HeimdallTool()
        self.libimobile = LibIMobileDeviceTool()
        self.qpst = QPSTTool()

        # Map nama tool (dari scan_all keys) -> attribute name
        self._ATTR_MAP = {
            "mtkclient": "mtkclient",
            "heimdall": "heimdall",
            "libimobiledevice": "libimobile",
            "qpst/edl": "qpst",
        }

        # Cache untuk hasil scan
        self._scan_cache: Dict[str, ToolStatus] = {}
        self._scan_time: float = 0
        self.SCAN_CACHE_TTL: float = 10.0  # detik

    def _get_tool(self, name: str):
        """Dapatkan tool object dari nama scan key."""
        attr_name = self._ATTR_MAP.get(name, name.replace("/", "_").replace("-", "_").lower())
        return getattr(self, attr_name, None)

    def scan_all(self, force: bool = False) -> Dict[str, ToolStatus]:
        """
        Scan SEMUA external tools dan return status masing-masing.

        Results di-cache selama SCAN_CACHE_TTL detik.
        """
        now = time.time()
        if not force and (now - self._scan_time) < self.SCAN_CACHE_TTL and self._scan_cache:
            return self._scan_cache

        results = {
            "mtkclient": self.mtkclient.check(),
            "heimdall": self.heimdall.check(),
            "libimobiledevice": self.libimobile.check(),
            "qpst/edl": self.qpst.check(),
        }

        self._scan_cache = results
        self._scan_time = now
        return results

    def get_available_tools(self) -> Dict[str, str]:
        """Return dict {tool_name: version} untuk tool yang tersedia."""
        results = self.scan_all()
        available = {}
        for name, status in results.items():
            if status == ToolStatus.AVAILABLE:
                tool = self._get_tool(name)
                if tool:
                    available[name] = tool.get_version()
                else:
                    available[name] = "available"
        return available

    def get_missing_tools(self) -> List[str]:
        """Return list nama tool yang tidak ditemukan."""
        results = self.scan_all()
        return [name for name, status in results.items() if status != ToolStatus.AVAILABLE]

    def reset_cache(self):
        """Reset semua cache tool."""
        self._scan_cache = {}
        self._scan_time = 0
        self.mtkclient.reset_cache()
        self.heimdall.reset_cache()
        self.libimobile.reset_cache()
        self.qpst.reset_cache()

    def get_install_guides(self) -> str:
        """Return gabungan panduan install untuk semua tool yang hilang."""
        missing = self.get_missing_tools()
        if not missing:
            return "Semua external tools tersedia!\n"

        guides = []
        for name in missing:
            tool = self._get_tool(name)
            if tool and hasattr(tool, 'get_install_guide'):
                guides.append(tool.get_install_guide())

        return "\n".join(guides)

    def get_summary(self) -> str:
        """Return ringkasan status semua tool."""
        status = self.scan_all()
        lines = ["=== EXTERNAL TOOLS STATUS ==="]
        icons = {
            ToolStatus.AVAILABLE: "✅",
            ToolStatus.NOT_FOUND: "❌",
            ToolStatus.ERROR: "⚠️",
            ToolStatus.WRONG_VERSION: "⚠️",
            ToolStatus.NOT_INSTALLED: "❌",
        }
        for name, s in status.items():
            icon = icons.get(s, "?")
            tool = self._get_tool(name)
            version = f" ({tool.get_version()})" if tool and s == ToolStatus.AVAILABLE else ""
            lines.append(f"  {icon} {name}{version}")
        return "\n".join(lines)


# ===========================================================================
# QUICK TEST
# ===========================================================================

if __name__ == "__main__":
    print("=== EXTERNAL TOOLS TEST ===\n")
    tm = ToolManager()

    print("Scanning all tools...")
    status = tm.scan_all(force=True)

    for name, s in status.items():
        icon = {
            ToolStatus.AVAILABLE: "✅",
            ToolStatus.NOT_FOUND: "❌",
            ToolStatus.ERROR: "⚠️",
        }.get(s, "?")
        print(f"  {icon} {name}: {s.name}")

    print("\nAvailable tools:")
    for name, ver in tm.get_available_tools().items():
        print(f"  - {name}: {ver}")

    if tm.get_missing_tools():
        print(f"\nMissing tools: {', '.join(tm.get_missing_tools())}")
        print("\nInstall guides:")
        print(tm.get_install_guides())