
"""
NST Environment Checker v2
===========================
- Cek kelengkapan tools (ADB, fastboot, python modules)
- AUTO-DOWNLOAD ADB & Fastboot dari official source
- Auto-detect driver + install guide
- System information
- Multi-language support (Indonesia + English)
"""
import os
import sys
import platform
import subprocess
import urllib.request
import zipfile
import tarfile
import shutil
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from core.logger import log, Colors


# ========== LANGUAGE ==========
LANG_EN = "en"
LANG_ID = "id"

_current_lang = LANG_ID  # Default: Indonesia

STRINGS = {
    LANG_ID: {
        "title": "NST ENVIRONMENT CHECK",
        "os": "Sistem Operasi",
        "python": "Python Version",
        "arch": "Architecture",
        "tools_ok": "Tools: OK",
        "tools_missing": "Tools: Tidak ditemukan",
        "dep_ok": "Dependencies: OK",
        "dep_missing": "Dependencies: Tidak terinstall",
        "all_ok": "Semua kebutuhan terpenuhi!",
        "need_install": "Beberapa tools perlu diinstall. Lihat panduan di atas.",
        "install_prompt": "Install dependencies yang hilang?",
        "installing": "Menginstall...",
        "install_ok": "Installasi selesai!",
        "install_fail": "Install gagal. Install manual.",
        "download_start": "Mendownload",
        "download_done": "Download selesai!",
        "extracting": "Mengextract",
        "extract_done": "Extract selesai!",
        "added_to_path": "Ditambahkan ke PATH",
        "download_confirm": "Download dan install ADB & Fastboot otomatis?",
        "driver_confirm": "Install driver USB otomatis?",
        "no_adb_fastboot": "ADB & Fastboot tidak ditemukan",
        "yes_auto": "y - Download otomatis + extract + add PATH",
    },
    LANG_EN: {
        "title": "SYSTEM ENVIRONMENT CHECK",
        "os": "Operating System",
        "python": "Python Version",
        "arch": "Architecture",
        "tools_ok": "Tools: Available",
        "tools_missing": "Tools: Not Found",
        "dep_ok": "Dependencies: OK",
        "dep_missing": "Dependencies: Not Installed",
        "all_ok": "All requirements met!",
        "need_install": "Some tools need to be installed. See guide above.",
        "install_prompt": "Install missing dependencies?",
        "installing": "Installing...",
        "install_ok": "Installation complete!",
        "install_fail": "Installation failed. Install manually.",
        "download_start": "Downloading",
        "download_done": "Download complete!",
        "extracting": "Extracting",
        "extract_done": "Extract complete!",
        "added_to_path": "Added to PATH",
        "download_confirm": "Download and install ADB & Fastboot automatically?",
        "driver_confirm": "Install USB driver automatically?",
        "no_adb_fastboot": "ADB & Fastboot not found",
        "yes_auto": "y - Auto download + extract + add PATH",
    }
}


def _(key: str) -> str:
    """Get localized string"""
    return STRINGS.get(_current_lang, STRINGS[LANG_ID]).get(key, key)


def set_language(lang: str):
    """Set bahasa"""
    global _current_lang
    if lang in [LANG_ID, LANG_EN]:
        _current_lang = lang


@dataclass
class ToolInfo:
    """Informasi satu tool"""
    name: str
    cmd: str
    check_args: List[str] = None
    install_url: str = ""
    install_cmd: str = ""
    optional: bool = False


class AutoDownloader:
    """Download tools otomatis dari official source"""

    # Official download URLs
    PLATFORM_TOOLS_WIN = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    PLATFORM_TOOLS_MAC = "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
    PLATFORM_TOOLS_LINUX = "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"

    # Driver URLs
    SAMSUNG_USB_DRIVER = "https://developer.samsung.com/android-usb-driver"
    GOOGLE_USB_DRIVER = "https://developer.android.com/studio/run/win-usb"
    APPLE_MOBILE_DEVICE = "https://support.apple.com/downloads"
    QUALCOMM_DRIVER = "https://qpsttool.com/"
    MEDIATEK_DRIVER = "https://spflashtool.com/"
    ZADIG_TOOL = "https://zadig.akeo.ie/"

    def __init__(self):
        self.os_name = platform.system()
        self.tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
        os.makedirs(self.tools_dir, exist_ok=True)

    def _download_file(self, url: str, dest: str, desc: str = "") -> bool:
        """Download file dengan progress bar sederhana + timeout 120 detik"""
        try:
            import socket
            socket.setdefaulttimeout(120)  # Timeout total 2 menit
            log.info(f"{_('download_start')} {desc or url.split('/')[-1]}...")
            
            def report(block_count, block_size, total_size):
                downloaded = block_count * block_size / (1024 * 1024)
                total_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                if total_mb > 0:
                    percent = min(100, int(downloaded / total_mb * 100))
                    bar = "#" * (percent // 5) + "." * (20 - percent // 5)
                    print(f"\r  [{bar}] {percent}% ({downloaded:.1f}/{total_mb:.1f} MB)", end="")
                else:
                    print(f"\r  Downloaded: {downloaded:.1f} MB", end="")

            urllib.request.urlretrieve(url, dest, report)
            print()
            socket.setdefaulttimeout(None)  # Reset timeout
            log.success(f"{_('download_done')}: {os.path.basename(dest)}")
            return True
        except (socket.timeout, Exception) as e:
            log.error(f"Download gagal: {e}")
            return False

    def _extract_zip(self, zip_path: str, extract_to: str) -> bool:
        """Extract zip file"""
        try:
            log.info(f"{_('extracting')} {os.path.basename(zip_path)}...")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_to)
            log.success(f"{_('extract_done')}")
            return True
        except Exception as e:
            log.error(f"Extract gagal: {e}")
            return False

    def download_platform_tools(self) -> Optional[str]:
        """
        Download platform-tools (ADB + Fastboot) dari official Google source.
        Returns path ke folder platform-tools, atau None jika gagal.
        """
        log.header("[AUTO DOWNLOAD PLATFORM-TOOLS]")
        log.info(f"Mendownload ADB & Fastboot dari Google...")
        print()

        # Pilih URL sesuai OS
        url_map = {
            "Windows": self.PLATFORM_TOOLS_WIN,
            "Darwin": self.PLATFORM_TOOLS_MAC,
            "Linux": self.PLATFORM_TOOLS_LINUX,
        }
        url = url_map.get(self.os_name)
        if not url:
            log.error(f"OS tidak didukung: {self.os_name}")
            return None

        # Download
        zip_name = f"platform-tools-{self.os_name.lower()}.zip"
        zip_path = os.path.join(self.tools_dir, zip_name)

        if not self._download_file(url, zip_path, "platform-tools"):
            return None

        # Extract
        extract_dir = os.path.join(self.tools_dir, "platform-tools")
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)

        if not self._extract_zip(zip_path, extract_dir):
            return None

        # Cari folder platform-tools yang sebenarnya (mungkin ada subfolder)
        actual_dir = extract_dir
        for item in os.listdir(extract_dir):
            item_path = os.path.join(extract_dir, item)
            if os.path.isdir(item_path) and "platform-tools" in item.lower():
                # Pindahkan konten ke extract_dir
                for f in os.listdir(item_path):
                    shutil.move(os.path.join(item_path, f), os.path.join(extract_dir, f))
                shutil.rmtree(item_path)
                break

        # Verifikasi ADB & Fastboot
        adb_path = os.path.join(extract_dir, "adb.exe" if self.os_name == "Windows" else "adb")
        fastboot_path = os.path.join(extract_dir, "fastboot.exe" if self.os_name == "Windows" else "fastboot")

        if os.path.exists(adb_path) and os.path.exists(fastboot_path):
            log.success(f"ADB: {adb_path}")
            log.success(f"Fastboot: {fastboot_path}")
            log.success("Download & extract BERHASIL!")
            print()

            # Tambahkan ke PATH environment variable
            self._add_to_path(extract_dir)

            return extract_dir
        else:
            log.error("File ADB/Fastboot tidak ditemukan setelah extract!")
            return None

    def _add_to_path(self, dir_path: str):
        """Tambahkan folder ke PATH (user-level, persistent) - No Duplicates"""
        try:
            if self.os_name == "Windows":
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    "Environment",
                    0,
                    winreg.KEY_READ | winreg.KEY_WRITE
                )
                current_path, _ = winreg.QueryValueEx(key, "PATH")
                # Cek duplikasi
                existing = current_path.split(";")
                if dir_path not in existing:
                    new_path = current_path + ";" + dir_path
                    winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                    winreg.CloseKey(key)
                    log.success(f"{_('added_to_path')}: {dir_path}")
                    log.info("PATH akan aktif setelah restart terminal/komputer.")
                else:
                    log.info(f"Sudah ada di PATH: {dir_path}")
            else:
                # Linux/Mac: tambahkan ke .bashrc atau .zshrc (cek duplikasi)
                rc_file = os.path.expanduser("~/.bashrc")
                if os.path.exists(os.path.expanduser("~/.zshrc")):
                    rc_file = os.path.expanduser("~/.zshrc")

                # Baca file dulu, cek apakah sudah ada
                if os.path.exists(rc_file):
                    with open(rc_file, 'r') as f:
                        content = f.read()
                    if dir_path in content:
                        log.info(f"Sudah ada di {rc_file}: {dir_path}")
                        return

                with open(rc_file, 'a') as f:
                    f.write(f'\n# Added by NST Ultimate Console\nexport PATH="$PATH:{dir_path}"\n')
                log.success(f"{_('added_to_path')}: {dir_path}")
                log.info(f"Jalankan: source {rc_file}")
        except Exception as e:
            log.warning(f"Gagal tambah PATH otomatis: {e}")
            log.info(f"Tambahkan manual ke PATH: {dir_path}")

    def detect_and_download_adb(self) -> bool:
        """
        Deteksi ADB, jika tidak ada auto-download.
        Returns True jika sukses.
        """
        # Cek ADB dulu
        adb_found = shutil.which("adb") is not None
        fastboot_found = shutil.which("fastboot") is not None

        if adb_found and fastboot_found:
            log.success("ADB & Fastboot sudah terinstall di PATH")
            return True

        print()
        log.warning(f"{_('no_adb_fastboot')}")
        print()

        if not ConfirmationChain.confirm_simple(_("download_confirm"), "n"):
            log.info("Skip auto-download. Install manual.")
            return False

        result = self.download_platform_tools()
        return result is not None

    def show_driver_links(self):
        """Tampilkan link download driver untuk berbagai brand"""
        log.header("[DRIVER DOWNLOAD LINKS]")
        log.info("Link download driver USB:")
        print()
        drivers = [
            ("Samsung USB Driver", self.SAMSUNG_USB_DRIVER, "Untuk Samsung Android"),
            ("Google USB Driver", self.GOOGLE_USB_DRIVER, "Untuk Pixel/Generic Android"),
            ("Apple Mobile Device", self.APPLE_MOBILE_DEVICE, "Untuk iPhone/iPad"),
            ("Qualcomm Driver (QDLoader)", self.QUALCOMM_DRIVER, "Untuk Qualcomm EDL mode"),
            ("MediaTek USB VCOM", self.MEDIATEK_DRIVER, "Untuk MediaTek BROM mode"),
            ("Zadig (WinUSB Driver)", self.ZADIG_TOOL, "Untuk STM32/DFU mode"),
        ]
        for name, url, desc in drivers:
            print(f"  {Colors.CYAN}  {name}{Colors.RESET}")
            print(f"         {Colors.DIM}{desc}{Colors.RESET}")
            print(f"         {Colors.UNDERLINE}{url}{Colors.RESET}")
            print()

    def open_driver_url(self, brand: str):
        """Buka link driver di browser"""
        import webbrowser
        url_map = {
            "samsung": self.SAMSUNG_USB_DRIVER,
            "google": self.GOOGLE_USB_DRIVER,
            "apple": self.APPLE_MOBILE_DEVICE,
            "qualcomm": self.QUALCOMM_DRIVER,
            "mediatek": self.MEDIATEK_DRIVER,
            "zadig": self.ZADIG_TOOL,
        }
        url = url_map.get(brand.lower())
        if url:
            webbrowser.open(url)
            log.info(f"Membuka: {url}")
        else:
            log.warning(f"Brand '{brand}' tidak dikenal")


class EnvironmentChecker:
    """Cek environment dan tools"""

    REQUIRED_TOOLS = [
        ToolInfo("ADB (Android Debug Bridge)", "adb", ["version"],
                 "https://developer.android.com/tools/releases/platform-tools",
                 "Download platform-tools and add to PATH"),
        ToolInfo("Fastboot", "fastboot", ["--version"],
                 "https://developer.android.com/tools/releases/platform-tools",
                 "Included with platform-tools"),
    ]

    OPTIONAL_TOOLS = [
        ToolInfo("Python pip", "pip", ["--version"]),
        ToolInfo("pyserial", "python", ["-c", "import serial; print(serial.__version__)"],
                 "", "pip install pyserial"),
        ToolInfo("dfu-util", "dfu-util", ["--version"],
                 "http://dfu-util.sourceforge.net/", "apt install dfu-util / brew install dfu-util"),
        ToolInfo("OpenOCD", "openocd", ["--version"],
                 "https://openocd.org/", "apt install openocd / brew install openocd"),
        ToolInfo("st-flash", "st-flash", ["--version"],
                 "https://github.com/stlink-org/stlink", "apt install stlink-tools / brew install stlink"),
        ToolInfo("lsusb (Linux/Mac)", "lsusb", [], "", "apt install usbutils", optional=True),
        ToolInfo("WinUSB (Windows)", "where", ["Zadig"], optional=True),
        # External Tools (chipset-specific)
        ToolInfo("mtkclient (MediaTek)", "mtk", ["--version"],
                 "https://github.com/bkerler/mtkclient",
                 "pip install mtkclient / git clone https://github.com/bkerler/mtkclient", optional=True),
        ToolInfo("heimdall (Samsung)", "heimdall", ["version"],
                 "https://glassechidna.com.au/heimdall/",
                 "apt install heimdall-flash / brew install heimdall", optional=True),
        ToolInfo("libimobiledevice (Apple)", "idevice_id", ["-l"],
                 "https://libimobiledevice.org/",
                 "apt install libimobiledevice-utils / brew install libimobiledevice", optional=True),
        ToolInfo("irecovery (Apple DFU)", "irecovery", ["-i"],
                 "https://github.com/libimobiledevice/libirecovery",
                 "apt install libirecovery-utils / brew install libirecovery", optional=True),
        ToolInfo("edl (Qualcomm EDL)", "edl", ["--help"],
                 "https://github.com/bkerler/edl",
                 "pip install edl", optional=True),
        ToolInfo("idevicerestore (Apple Restore)", "idevicerestore", ["--help"],
                 "https://github.com/libimobiledevice/idevicerestore", optional=True),
    ]

    def __init__(self):
        self.os_name = platform.system()
        self.results: Dict[str, bool] = {}
        self.auto_downloader = AutoDownloader()

    def check_tool(self, tool: ToolInfo) -> Tuple[bool, str]:
        """Cek apakah tool tersedia"""
        try:
            if tool.check_args:
                result = subprocess.run(
                    [tool.cmd] + tool.check_args,
                    capture_output=True, text=True, timeout=5
                )
                ok = result.returncode == 0
            else:
                # Cek via `which` atau `where`
                if self.os_name == "Windows":
                    result = subprocess.run(["where", tool.cmd], capture_output=True, text=True, timeout=3)
                else:
                    result = subprocess.run(["which", tool.cmd], capture_output=True, text=True, timeout=3)
                ok = result.returncode == 0

            if ok:
                return True, _(f"tools_ok").replace(": OK", f": {tool.name} OK")
            return False, f"{tool.name}: {_('tools_missing')}"

        except FileNotFoundError:
            return False, f"{tool.name}: {_('tools_missing')}"
        except Exception as e:
            return False, f"{tool.name}: Error ({e})"

    def check_all(self) -> Dict:
        """Cek semua tools"""
        log.header(_("title"))
        log.info(f"{_('os')}: {self.os_name} {platform.release()}")
        log.info(f"{_('python')}: {sys.version.split()[0]}")
        log.info(f"{_('arch')}: {platform.machine()}")
        print()

        results = {"os": self.os_name, "python": sys.version, "tools": {}, "missing": []}

        # Cek required tools
        log.info("Required Tools:")
        for tool in self.REQUIRED_TOOLS:
            ok, msg = self.check_tool(tool)
            results["tools"][tool.name] = ok
            if ok:
                log.success(f"  {msg}")
            else:
                log.warning(f"  X {msg}")
                results["missing"].append(tool)

        print()
        log.info("Optional Tools:")
        for tool in self.OPTIONAL_TOOLS:
            ok, msg = self.check_tool(tool)
            results["tools"][tool.name] = ok
            if ok:
                log.success(f"  {msg}")
            elif not tool.optional:
                log.warning(f"  {msg}")
                results["missing"].append(tool)

        # Cek python modules
        print()
        log.info("Python Modules:")
        modules = ["serial", "json", "struct"]
        for mod in modules:
            try:
                __import__(mod)
                log.success(f"  {mod}: OK")
            except ImportError:
                log.warning(f"  X {mod}: Not installed")
                if mod == "serial":
                    results["missing"].append(
                        ToolInfo("pyserial", "pip", install_cmd="pip install pyserial")
                    )

        print()
        if not results["missing"]:
            log.success(_("all_ok"))
        else:
            log.warning(_("need_install"))

        return results

    def install_missing(self, tools: List[ToolInfo] = None):
        """Install dependencies yang hilang"""
        if tools is None:
            results = self.check_all()
            tools = results.get("missing", [])

        if not tools:
            log.info("Tidak ada yang perlu diinstall")
            return

        log.header("[INSTALL DEPENDENCIES]")

        # Deteksi jika ADB/Fastboot tidak ada - tawarkan auto-download
        missing_adb = any("adb" in t.name.lower() or "fastboot" in t.name.lower() for t in tools)
        if missing_adb:
            print()
            log.warning(f"  {_('no_adb_fastboot')}")
            log.info(f"  {_('yes_auto')}")
            print()
            if ConfirmationChain.confirm_simple("Download ADB & Fastboot otomatis dari Google?", "n"):
                self.auto_downloader.download_platform_tools()
                # Setelah download, cek ulang tools
                tools = [t for t in tools if "adb" not in t.name.lower() and "fastboot" not in t.name.lower()]
                if not tools:
                    log.success("Semua tools terinstall!")
                    return
                print()

        # Tampilkan sisa tools yang perlu diinstall manual
        log.info("Tools yang masih perlu diinstall:")
        print()
        for tool in tools:
            print(f"  {Colors.YELLOW}[{tool.name}]{Colors.RESET}")
            if tool.install_cmd:
                print(f"  Run: {Colors.CYAN}{tool.install_cmd}{Colors.RESET}")
            if tool.install_url:
                print(f"  Download: {Colors.CYAN}{tool.install_url}{Colors.RESET}")
            print()

        # Auto-install pyserial via pip
        for tool in tools:
            if "pip install" in tool.install_cmd:
                confirm = input(f"  Install {tool.name} via pip? (y/N): ").strip().lower()
                if confirm == "y":
                    log.info(f"{_('installing')} {tool.name}...")
                    try:
                        result = subprocess.run(
                            tool.install_cmd.split(),
                            capture_output=True, text=True, timeout=30
                        )
                        if result.returncode == 0:
                            log.success(f"{tool.name}: {_('install_ok')}")
                        else:
                            log.error(f"{_('install_fail')} {tool.name}: {result.stderr}")
                    except Exception as e:
                        log.error(f"{tool.name}: {e}")

        # Tampilkan driver links
        print()
        if ConfirmationChain.confirm_simple("Tampilkan link download driver?", "n"):
            self.auto_downloader.show_driver_links()

        print()
        log.info("Untuk tools lain, install manual sesuai panduan di atas.")

    def show_system_info(self):
        """Tampilkan info sistem lengkap"""
        log.header("[SYSTEM INFORMATION]")
        info = {
            "OS": f"{self.os_name} {platform.release()}",
            "OS Version": platform.version(),
            "Architecture": platform.machine(),
            "Processor": platform.processor() or "N/A",
            "Python": sys.version.split()[0],
            "Python Path": sys.executable,
            "Hostname": platform.node(),
            "Current Dir": os.getcwd(),
        }

        for key, val in info.items():
            print(f"  {Colors.DIM}{key}:{Colors.RESET} {val}")

        # Cek PATH
        print()
        log.info("System PATH (first 5):")
        path = os.environ.get("PATH", "")
        for i, p in enumerate(path.split(os.pathsep)[:5], 1):
            print(f"  {Colors.DIM}{i}.{Colors.RESET} {p}")

        if len(path.split(os.pathsep)) > 5:
            print(f"  {Colors.DIM}... and {len(path.split(os.pathsep)) - 5} more{Colors.RESET}")

    def check_driver(self) -> Dict:
        """Cek status driver USB"""
        log.header("[DRIVER CHECK]")
        results = {"drivers": {}, "ok": True}

        if self.os_name == "Windows":
            try:
                # Cek driver via PowerShell
                log.info("Checking USB drivers...")
                cmd = [
                    "powershell", "-Command",
                    "Get-PnpDevice -Class USB | Where-Object {$_.Status -eq 'OK'} | "
                    "Select-Object FriendlyName, Status, Class | ConvertTo-Json"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0 and clean_console_output(result.stdout).strip():
                    import json
                    try:
                        devices = json.loads(clean_console_output(result.stdout))
                        if isinstance(devices, dict):
                            devices = [devices]
                        for dev in devices:
                            name = dev.get("FriendlyName", "Unknown")
                            status = dev.get("Status", "?")
                            results["drivers"][name] = status
                            if "ADB" in name or "Android" in name:
                                log.success(f"  [OK] {name}")
                            elif "Apple" in name or "iPhone" in name:
                                log.success(f"  [OK] {name}")
                            else:
                                log.info(f"  [i] {name}")
                    except (json.JSONDecodeError, Exception):
                        pass
                print()
                log.success("Driver check selesai.")
            except Exception as e:
                log.warning(f"Driver check error: {e}")
        else:
            # Linux/Mac
            try:
                result = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in clean_console_output(result.stdout).strip().split('\n')[:20]:
                        print(f"  {line}")
            except Exception:
                pass

        return results


# Import disini untuk menghindari circular import
from core.safety import ConfirmationChain


def run():
    """Jalankan Environment Checker - check all tools"""
    checker = EnvironmentChecker()
    checker.check_all()
