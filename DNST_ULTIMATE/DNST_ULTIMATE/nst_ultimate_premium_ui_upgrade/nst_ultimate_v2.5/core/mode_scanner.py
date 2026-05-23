


"""
NST Universal Mode Scanner
==========================
Deteksi mode device secara universal via USB VID/PID + tool scan.

Fitur:
- Consolidated USB ID database dari SEMUA chipset (STM32, Apple, Qualcomm, MediaTek,
  Samsung/Exynos, Unisoc, Kirin, generic Android)
- Satu-pass scan USB (tidak perlu tiap plugin scan sendiri)
- Tool-based detection: ADB, Fastboot, idevice, dfu-util, st-info
- Detection cache dengan TTL
- Output DeviceInfo objects (compatible dengan plugin system)
- Real-time device monitor

Cara pakai:
    scanner = ModeScanner()
    devices = scanner.scan_all()          # Full scan USB + tools
    devices = scanner.fast_scan()         # Cepat: USB only
    scanner.monitor(interval=2.0)         # Monitor real-time
"""


import os
import sys
import time
import json
import platform
import subprocess
import threading
import logging
from typing import Dict, List, Optional, Tuple, Set, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

# ── Pastikan project root ada di path ──
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from plugins import DeviceMode, DeviceInfo, USB_ID
    from core.logger import log, Colors
    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False
    # Fallback classes
    from enum import Enum, auto
    class DeviceMode(Enum):
        UNKNOWN = auto(); ADB = auto(); FASTBOOT = auto(); RECOVERY = auto()
        EDL = auto(); BROM = auto(); PRELOADER = auto(); DA = auto()
        DOWNLOAD = auto(); DFU_APPLE = auto(); RECOVERY_APPLE = auto()
        NORMAL_APPLE = auto()
        STLINK = auto(); DFU_STM32 = auto(); UART_BOOT = auto()
        FDL = auto(); RESEARCH = auto(); BOOTROM_SPRD = auto()
        HISILICON_USB = auto(); FASTBOOT_HISI = auto()
        # Mode tambahan yang direferensi di CONSOLIDATED_USB_DB
        PURPLE_MODE = auto(); SWD = auto(); HSUSB = auto()
        DIAG = auto(); QDL = auto(); META = auto(); ATF = auto()
        IBL = auto(); PBL = auto(); DLOAD = auto(); XMIT = auto()
        BURN_MODE = auto(); SERIAL = auto()
        def __str__(self): return self.name.replace("_", " ").title()

    @dataclass
    class DeviceInfo:
        serial: str = ""; model: str = ""; brand: str = ""
        chipset: str = ""; platform: str = ""
        mode: Any = DeviceMode.UNKNOWN
        vid: int = 0; pid: int = 0
        usb_ids: List = field(default_factory=list)
        description: str = ""; battery: int = -1
        android_version: str = ""
        properties: Dict = field(default_factory=dict)

        def __str__(self):
            parts = [f"[{self.mode}]"]
            if self.model: parts.append(self.model)
            if self.serial: parts.append(f"({self.serial})")
            if self.chipset: parts.append(f"Chip: {self.chipset}")
            return " ".join(parts)

    @dataclass
    class USB_ID:
        vid: int; pid: int; description: str = ""
        def __hash__(self): return hash((self.vid, self.pid))
        def __eq__(self, other):
            if isinstance(other, USB_ID):
                return self.vid == other.vid and self.pid == other.pid
            return False


# ===========================================================================
# CONSOLIDATED USB ID DATABASE — dari SEMUA chipset
# ===========================================================================

# Setiap entry: (vid, pid, mode, description)
# Sumber: plugins/stm32, apple, qualcomm, mediatek, samsung, unisoc, kirin
CONSOLIDATED_USB_DB: List[Tuple[int, int, DeviceMode, str]] = [
    # ── STMicroelectronics / STM32 ──
    (0x0483, 0x3748, DeviceMode.STLINK,    "ST-Link/V2"),
    (0x0483, 0x374B, DeviceMode.STLINK,    "ST-Link/V2-1"),
    (0x0483, 0x3752, DeviceMode.STLINK,    "ST-Link/V2-1 (mass storage)"),
    (0x0483, 0x3753, DeviceMode.STLINK,    "ST-Link/V2-1 (bridge)"),
    (0x0483, 0xDF11, DeviceMode.DFU_STM32, "STM32 DFU Bootloader (system memory)"),
    (0x0483, 0x5720, DeviceMode.DFU_STM32, "STM32 Mass Storage (DFU)"),
    (0x0483, 0x5721, DeviceMode.DFU_STM32, "STM32 Mass Storage (read-only)"),
    (0x0483, 0x5740, DeviceMode.UART_BOOT, "STM32 Virtual COM Port (bootloader)"),
    (0x0483, 0x5741, DeviceMode.UART_BOOT, "STM32 VCP + Debug"),
    (0x1EAF, 0x0003, DeviceMode.STLINK,    "Maple Mini (STM32)"),
    (0x1EAF, 0x0004, DeviceMode.STLINK,    "Maple (STM32)"),
    (0x1D50, 0x6018, DeviceMode.SWD,       "Black Magic Probe (STM32)"),
    (0x0D28, 0x0204, DeviceMode.SWD,       "DAPLink (STM32)"),

    # ── Apple / iPhone ──
    (0x05AC, 0x12A0, DeviceMode.NORMAL_APPLE,   "iPhone 5/5C (Normal)"),
    (0x05AC, 0x12A8, DeviceMode.NORMAL_APPLE,   "iPhone 6/6S/SE (Normal)"),
    (0x05AC, 0x12AA, DeviceMode.NORMAL_APPLE,   "iPhone 7 (Normal)"),
    (0x05AC, 0x12AB, DeviceMode.NORMAL_APPLE,   "iPhone 7+ (Normal)"),
    (0x05AC, 0x1210, DeviceMode.RECOVERY_APPLE, "iPhone/iPad Recovery Mode"),
    (0x05AC, 0x1211, DeviceMode.RECOVERY_APPLE, "iPhone Recovery (old)"),
    (0x05AC, 0x1281, DeviceMode.RECOVERY_APPLE, "iPhone iBoot Recovery"),
    (0x05AC, 0x1291, DeviceMode.RECOVERY_APPLE, "iPhone 5/5C Recovery"),
    (0x05AC, 0x12A1, DeviceMode.RECOVERY_APPLE, "iPhone 5S Recovery"),
    (0x05AC, 0x12A9, DeviceMode.RECOVERY_APPLE, "iPhone 6/6+ Recovery"),
    (0x05AC, 0x1220, DeviceMode.DFU_APPLE,      "iPhone/iPad DFU Mode"),
    (0x05AC, 0x1222, DeviceMode.DFU_APPLE,      "iPhone DFU (old)"),
    (0x05AC, 0x1227, DeviceMode.DFU_APPLE,      "iPhone/iPad DFU (newer)"),
    (0x05AC, 0x1280, DeviceMode.DFU_APPLE,      "iPhone iBoot DFU"),
    (0x05AC, 0x1290, DeviceMode.DFU_APPLE,      "iPhone 5/5C DFU"),
    (0x05AC, 0x12A2, DeviceMode.DFU_APPLE,      "iPhone 6/6+ DFU"),
    (0x05AC, 0x1292, DeviceMode.PURPLE_MODE,    "iPhone Purple Mode"),

    # ── Qualcomm ──
    (0x05C6, 0x9008, DeviceMode.EDL,    "Qualcomm HS-USB QDLoader 9008 (EDL)"),
    (0x05C6, 0x900E, DeviceMode.HSUSB,  "Qualcomm Diagnostics 900E"),
    (0x05C6, 0x9003, DeviceMode.HSUSB,  "Qualcomm HS-USB 9003"),
    (0x05C6, 0x9025, DeviceMode.EDL,    "Qualcomm HS-USB 9025 (EDL)"),
    (0x05C6, 0x9200, DeviceMode.HSUSB,  "Qualcomm HS-USB 9200"),
    (0x05C6, 0x9201, DeviceMode.HSUSB,  "Qualcomm HS-USB 9201"),
    (0x05C6, 0x920D, DeviceMode.DIAG,   "Qualcomm Diag 920D"),
    (0x05C6, 0x920B, DeviceMode.EDL,    "Qualcomm EDL 920B"),
    (0x05C6, 0x9215, DeviceMode.EDL,    "Qualcomm EDL 9215"),
    (0x05C6, 0x9001, DeviceMode.EDL,    "Qualcomm QDLoader 9001"),
    (0x05C6, 0x9002, DeviceMode.QDL,    "Qualcomm QDLoader 9002"),
    (0x18D1, 0xD00D, DeviceMode.EDL,    "Google EDL (Qualcomm)"),
    (0x18D1, 0x4EE0, DeviceMode.EDL,    "Google Pixel EDL"),
    (0x0955, 0xCF00, DeviceMode.EDL,    "NVIDIA EDL (Tegra/QC)"),
    (0x0489, 0xE000, DeviceMode.EDL,    "Foxconn Qualcomm EDL"),
    (0x04E8, 0x685D, DeviceMode.EDL,    "Samsung Qualcomm EDL"),
    (0x04E8, 0x685E, DeviceMode.EDL,    "Samsung Qualcomm EDL"),
    (0x2717, 0x9046, DeviceMode.EDL,    "Xiaomi Qualcomm EDL"),
    (0x2717, 0x9048, DeviceMode.EDL,    "Xiaomi Qualcomm EDL"),
    (0x2717, 0x9050, DeviceMode.EDL,    "Xiaomi Qualcomm EDL"),

    # ── MediaTek ──
    (0x0E8D, 0x0003, DeviceMode.BROM,      "MediaTek USB VCOM (BROM)"),
    (0x0E8D, 0x2000, DeviceMode.PRELOADER, "MediaTek Preloader VCOM"),
    (0x0E8D, 0x2001, DeviceMode.PRELOADER, "MediaTek Preloader (MT65xx)"),
    (0x0E8D, 0x2002, DeviceMode.PRELOADER, "MediaTek Preloader VCOM"),
    (0x0E8D, 0x2003, DeviceMode.PRELOADER, "MediaTek Preloader (MT67xx)"),
    (0x0E8D, 0x2004, DeviceMode.PRELOADER, "MediaTek Preloader VCOM"),
    (0x0E8D, 0x2005, DeviceMode.PRELOADER, "MediaTek Preloader"),
    (0x0E8D, 0x2006, DeviceMode.PRELOADER, "MediaTek Preloader (MT68xx)"),
    (0x0E8D, 0x2008, DeviceMode.PRELOADER, "MediaTek Preloader (MT8167)"),
    (0x0E8D, 0x3000, DeviceMode.DA,        "MediaTek Download Agent"),
    (0x0E8D, 0x3001, DeviceMode.DA,        "MediaTek DA (MT65xx)"),
    (0x0E8D, 0x3002, DeviceMode.DA,        "MediaTek DA VCOM"),
    (0x0E8D, 0x3003, DeviceMode.DA,        "MediaTek DA (MT67xx)"),
    (0x0E8D, 0x3005, DeviceMode.DA,        "MediaTek DA Protocol"),
    (0x0E8D, 0x4000, DeviceMode.META,      "MediaTek META Mode"),
    (0x0E8D, 0x4001, DeviceMode.META,      "MediaTek META (USB)"),
    (0x0E8D, 0x5000, DeviceMode.ATF,       "MediaTek ATF Mode"),
    (0x0E8D, 0x1000, DeviceMode.ADB,       "MediaTek Device (Normal)"),
    (0x2717, 0x2008, DeviceMode.PRELOADER, "Xiaomi MTK Preloader"),
    (0x04E8, 0x2008, DeviceMode.PRELOADER, "Samsung MTK Preloader"),

    # ── Samsung / Exynos ──
    (0x04E8, 0x6601, DeviceMode.DOWNLOAD, "Samsung Download Mode"),
    (0x04E8, 0x685D, DeviceMode.EDL,      "Samsung Qualcomm EDL"),
    (0x04E8, 0x685E, DeviceMode.EDL,      "Samsung Qualcomm EDL"),
    (0x04E8, 0x6860, DeviceMode.EDL,      "Samsung Qualcomm Download"),
    (0x04E8, 0x6866, DeviceMode.ADB,      "Samsung ADB Normal"),
    (0x04E8, 0x68C0, DeviceMode.ADB,      "Samsung ADB Mode"),
    (0x04E8, 0x68C1, DeviceMode.RECOVERY, "Samsung Recovery Mode"),
    (0x04E8, 0x6920, DeviceMode.IBL,      "Samsung Exynos IBL"),
    (0x04E8, 0x6930, DeviceMode.PBL,      "Samsung Exynos PBL"),
    (0x04E8, 0x6940, DeviceMode.DLOAD,    "Samsung Exynos DLOAD"),
    (0x04E8, 0x6950, DeviceMode.XMIT,     "Samsung Exynos XMIT"),

    # ── Unisoc / Spreadtrum ──
    (0x1782, 0x4000, DeviceMode.BOOTROM_SPRD, "Spreadtrum BootROM"),
    (0x1782, 0x4005, DeviceMode.BOOTROM_SPRD, "Spreadtrum BootROM (SC9850)"),
    (0x1782, 0x4008, DeviceMode.BOOTROM_SPRD, "Spreadtrum BootROM (SC7731)"),
    (0x1782, 0x400A, DeviceMode.BOOTROM_SPRD, "Spreadtrum BootROM (SC9863)"),
    (0x1782, 0x5000, DeviceMode.FDL,          "Unisoc FDL Mode"),
    (0x1782, 0x5001, DeviceMode.FDL,          "Unisoc FDL (USB)"),
    (0x1782, 0x5005, DeviceMode.FDL,          "Unisoc FDL (SC9850)"),
    (0x1782, 0x6000, DeviceMode.RESEARCH,     "Unisoc ResearchDownload"),
    (0x1782, 0x6001, DeviceMode.RESEARCH,     "Unisoc RD Mode"),
    (0x1782, 0x3000, DeviceMode.ADB,          "Unisoc Device (Normal)"),
    (0x1782, 0x3001, DeviceMode.ADB,          "Unisoc ADB"),
    (0x2717, 0x5008, DeviceMode.FDL,          "Xiaomi Unisoc FDL"),

    # ── Kirin / HiSilicon ──
    (0x12D1, 0x3600, DeviceMode.HISILICON_USB, "HiSilicon USB Download (Kirin)"),
    (0x12D1, 0x3605, DeviceMode.HISILICON_USB, "HiSilicon USB Download"),
    (0x12D1, 0x3607, DeviceMode.HISILICON_USB, "HiSilicon USB Download"),
    (0x12D1, 0x360D, DeviceMode.FASTBOOT_HISI, "HiSilicon Fastboot"),
    (0x12D1, 0x360E, DeviceMode.FASTBOOT_HISI, "HiSilicon Fastboot"),
    (0x12D1, 0x360F, DeviceMode.FASTBOOT_HISI, "HiSilicon Fastboot"),
    (0x12D1, 0x1077, DeviceMode.ADB,           "HiSilicon Android ADB"),
    (0x12D1, 0x1079, DeviceMode.ADB,           "HiSilicon Android Phone"),
    (0x12D1, 0x3700, DeviceMode.BURN_MODE,     "HiSilicon Burn Mode"),
    (0x18D1, 0x4EE2, DeviceMode.HISILICON_USB, "Huawei HiSilicon Download"),
    (0x18D1, 0x4EE3, DeviceMode.FASTBOOT_HISI, "Huawei HiSilicon Fastboot"),

    # ── Generic Android ──
    (0x18D1, 0xD00D, DeviceMode.FASTBOOT, "Android Fastboot (Google)"),
    (0x18D1, 0x4EE7, DeviceMode.ADB,      "Android ADB (Nexus/Pixel)"),
    (0x18D1, 0x4EE0, DeviceMode.ADB,      "Android ADB (old)"),
    (0x2B4A, 0x0001, DeviceMode.ADB,      "Generic Android ADB"),
    (0x2717, 0xFF40, DeviceMode.ADB,      "Xiaomi ADB/Fastboot"),
    (0x2D95, 0x6006, DeviceMode.EDL,      "OnePlus EDL Mode"),
    (0x2D95, 0x6007, DeviceMode.EDL,      "OnePlus EDL (variant)"),
    (0x22B8, 0x0001, DeviceMode.ADB,      "Motorola ADB"),
    (0x413C, 0x0001, DeviceMode.ADB,      "Dell ADB"),
]

# Build lookup maps sekali di module level
_USB_VID_MAP: Dict[int, List[Tuple[int, DeviceMode, str]]] = {}
for vid, pid, mode, desc in CONSOLIDATED_USB_DB:
    if vid not in _USB_VID_MAP:
        _USB_VID_MAP[vid] = []
    _USB_VID_MAP[vid].append((pid, mode, desc))


# ===========================================================================
# MODE SCANNER
# ===========================================================================

class ModeScanner:
    """
    Universal mode scanner — deteksi semua mode device dalam satu pass.

    Method utama:
        scan_all()        -> List[DeviceInfo]  # USB + tool scan (lengkap)
        fast_scan()       -> List[DeviceInfo]  # USB only (cepat)
        scan_usb()        -> List[DeviceInfo]  # USB VID/PID only
        scan_tools()      -> List[DeviceInfo]  # ADB, Fastboot, idevice, etc.
        detect_mode(vid, pid) -> DeviceMode    # Cari mode dari VID/PID
        monitor(interval) -> None              # Real-time monitor
    """

    # Cache
    _cache: List[DeviceInfo] = []
    _cache_time: float = 0
    _cache_ttl: float = 5.0  # detik

    # Singleton instance
    _instance: Optional["ModeScanner"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._os_name = platform.system()
            self._log = logging.getLogger("nst.mode_scanner")
            self._scan_lock = threading.Lock()

    # ── Public API ──

    def scan_all(self, force: bool = False) -> List[DeviceInfo]:
        """
        Full scan: USB VID/PID + tool-based detection (ADB, fastboot, dll).
        Results di-cache selama cache_ttl.
        """
        now = time.time()
        if not force and (now - self._cache_time) < self._cache_ttl and self._cache:
            return self._cache

        with self._scan_lock:
            all_devices: List[DeviceInfo] = []
            seen_keys: Set[str] = set()  # cegah duplikat

            # 1. USB scan (VID/PID database)
            usb_devices = self._scan_usb_once()
            for dev in usb_devices:
                key = f"{dev.vid:04X}:{dev.pid:04X}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_devices.append(dev)

            # 2. Tool scan (ADB, Fastboot, idevice, dfu-util, st-info)
            tool_devices = self._scan_tools_once()
            for dev in tool_devices:
                key = dev.serial or f"{dev.description}:{dev.mode}"
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    all_devices.append(dev)

            # 3. Serial ports (STM32 bootloader, generic)
            serial_devices = self._scan_serial_once()
            for dev in serial_devices:
                key = f"serial:{dev.serial or dev.description}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_devices.append(dev)

            self._cache = all_devices
            self._cache_time = now
            return all_devices

    def fast_scan(self, force: bool = False) -> List[DeviceInfo]:
        """
        Fast scan: USB VID/PID only (tanpa tool scan).
        Lebih cepat tapi kurang akurat untuk mode ADB/Fastboot.
        """
        now = time.time()
        if not force and (now - self._cache_time) < self._cache_ttl and self._cache:
            return [d for d in self._cache if d.mode != DeviceMode.UNKNOWN]

        usb_devices = self._scan_usb_once()
        self._cache = usb_devices
        self._cache_time = now
        return usb_devices

    def scan_usb(self) -> List[DeviceInfo]:
        """Scan USB VID/PID saja — deteksi mode dari database."""
        return self._scan_usb_once()

    def scan_tools(self) -> List[DeviceInfo]:
        """Scan via external tools: ADB, Fastboot, idevice, dfu-util, st-info."""
        return self._scan_tools_once()

    def detect_mode(self, vid: int, pid: int) -> DeviceMode:
        """Cari DeviceMode dari VID/PID."""
        entries = _USB_VID_MAP.get(vid, [])
        for p, mode, _ in entries:
            if p == pid:
                return mode
        return DeviceMode.UNKNOWN

    def get_description(self, vid: int, pid: int) -> str:
        """Dapatkan deskripsi device dari VID/PID."""
        entries = _USB_VID_MAP.get(vid, [])
        for p, _, desc in entries:
            if p == pid:
                return desc
        return f"Unknown Device (VID={vid:04X}, PID={pid:04X})"

    def get_chipset(self, vid: int, pid: int) -> str:
        """Dapatkan nama chipset dari VID."""
        chipset_map = {
            0x0483: "STM32", 0x05AC: "Apple", 0x05C6: "Snapdragon",
            0x0E8D: "MediaTek", 0x04E8: "Exynos/Samsung", 0x1782: "Unisoc",
            0x12D1: "Kirin/HiSilicon", 0x18D1: "Google/Android",
            0x2717: "Xiaomi", 0x2D95: "OnePlus/Oppo",
        }
        return chipset_map.get(vid, "Generic")

    def get_platform(self, vid: int, pid: int) -> str:
        """Dapatkan platform dari mode."""
        mode = self.detect_mode(vid, pid)
        return mode.category if hasattr(mode, 'category') else "unknown"

    def clear_cache(self):
        """Hapus cache."""
        self._cache = []
        self._cache_time = 0

    def set_cache_ttl(self, ttl: float):
        """Set cache TTL dalam detik."""
        self._cache_ttl = ttl

    # ── USB Scan ──

    def _scan_usb_once(self) -> List[DeviceInfo]:
        """Scan USB device — panggil OS-specific method."""
        try:
            if self._os_name == "Windows":
                return self._scan_usb_windows()
            else:
                return self._scan_usb_linux()
        except Exception as e:
            self._log.warning(f"USB scan error: {e}")
            return []

    def _scan_usb_windows(self) -> List[DeviceInfo]:
        """Scan USB via PowerShell WMI pada Windows."""
        devices = []
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-PnpDevice -PresentOnly | Where-Object {$_.Class -eq "USB" -or $_.Class -eq "Ports"} | '
                 'Select-Object FriendlyName, DeviceID, Status, Class | ConvertTo-Json -Compress'],
                capture_output=True, text=True, timeout=15
            )
            if not clean_console_output(result.stdout).strip() or clean_console_output(result.stdout).strip() == 'null':
                return devices

            try:
                data = json.loads(clean_console_output(result.stdout))
                if isinstance(data, dict):
                    data = [data]

                for item in data:
                    device_id = item.get('DeviceID', '') or ''
                    status = item.get('Status', '') or ''
                    friendly = item.get('FriendlyName', '') or ''

                    if status != 'OK':
                        continue

                    # Cari VID/PID
                    import re
                    match = re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', device_id, re.I)
                    if match:
                        vid = int(match.group(1), 16)
                        pid = int(match.group(2), 16)
                        mode = self.detect_mode(vid, pid)
                        desc = self.get_description(vid, pid)

                        dev = DeviceInfo(
                            mode=mode,
                            vid=vid,
                            pid=pid,
                            description=desc or friendly,
                            chipset=self.get_chipset(vid, pid),
                            platform=self.get_platform(vid, pid),
                        )
                        # Tambah detail dari friendly name
                        if not desc:
                            dev.description = friendly
                        devices.append(dev)
            except (json.JSONDecodeError, Exception):
                pass

            # Fallback: WMI Win32_USBControllerDevice
            if not devices:
                result2 = subprocess.run(
                    ['powershell', '-Command',
                     'Get-WmiObject Win32_USBControllerDevice | % {[wmi]$_.Dependent} | '
                     'Select-Object DeviceID, Description | ConvertTo-Json -Compress'],
                    capture_output=True, text=True, timeout=10
                )
                if result2.stdout.strip() and result2.stdout.strip() != 'null':
                    try:
                        data2 = json.loads(result2.stdout)
                        if isinstance(data2, dict):
                            data2 = [data2]
                        for item in data2:
                            device_id = item.get('DeviceID', '') or ''
                            desc2 = item.get('Description', '') or ''
                            match = re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', device_id, re.I)
                            if match:
                                vid = int(match.group(1), 16)
                                pid = int(match.group(2), 16)
                                mode = self.detect_mode(vid, pid)
                                dev = DeviceInfo(
                                    mode=mode, vid=vid, pid=pid,
                                    description=desc2,
                                    chipset=self.get_chipset(vid, pid),
                                    platform=self.get_platform(vid, pid),
                                )
                                devices.append(dev)
                    except (json.JSONDecodeError, Exception):
                        pass

        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            self._log.warning(f"Windows USB scan error: {e}")

        return devices

    def _scan_usb_linux(self) -> List[DeviceInfo]:
        """Scan USB via lsusb pada Linux/Mac."""
        devices = []
        try:
            result = subprocess.run(
                ["lsusb"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return devices

            for line in clean_console_output(result.stdout).split('\n'):
                match = re.search(r'ID ([0-9a-f]{4}):([0-9a-f]{4})', line, re.I)
                if match:
                    vid = int(match.group(1), 16)
                    pid = int(match.group(2), 16)
                    mode = self.detect_mode(vid, pid)

                    # Ekstrak nama vendor dari lsusb output
                    desc = line.split(':', 2)[-1].strip() if ':' in line else self.get_description(vid, pid)

                    dev = DeviceInfo(
                        mode=mode, vid=vid, pid=pid,
                        description=desc,
                        chipset=self.get_chipset(vid, pid),
                        platform=self.get_platform(vid, pid),
                    )
                    devices.append(dev)

        except FileNotFoundError:
            pass
        except Exception as e:
            self._log.warning(f"Linux USB scan error: {e}")

        return devices

    # ── Tool-based Detection ──

    def _scan_tools_once(self) -> List[DeviceInfo]:
        """Scan via external tools — detect ADB, Fastboot, idevice, dfu-util."""
        devices = []
        seen_serials: Set[str] = set()

        # 1. ADB devices
        for dev in self._scan_adb():
            if dev.serial and dev.serial not in seen_serials:
                seen_serials.add(dev.serial)
                devices.append(dev)

        # 2. Fastboot devices
        for dev in self._scan_fastboot():
            key = dev.serial or "fastboot"
            if key not in seen_serials:
                seen_serials.add(key)
                devices.append(dev)

        # 3. Apple devices (libimobiledevice)
        if self._os_name != "Windows":  # libimobiledevice lebih stabil di Linux/Mac
            for dev in self._scan_idevice():
                if dev.serial and dev.serial not in seen_serials:
                    seen_serials.add(dev.serial)
                    devices.append(dev)

        # 4. DFU devices (dfu-util)
        for dev in self._scan_dfu_util():
            key = f"dfu:{dev.serial or 'unknown'}"
            if key not in seen_serials:
                seen_serials.add(key)
                devices.append(dev)

        # 5. ST-Link (st-info)
        for dev in self._scan_stlink():
            key = f"stlink:{dev.serial or 'unknown'}"
            if key not in seen_serials:
                seen_serials.add(key)
                devices.append(dev)

        return devices

    def _scan_adb(self) -> List[DeviceInfo]:
        """Deteksi device via ADB."""
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return []

            devices = []
            for line in clean_console_output(result.stdout).split('\n')[1:]:
                if '\tdevice' in line:
                    parts = line.split()
                    serial = parts[0]
                    dev = DeviceInfo(
                        mode=DeviceMode.ADB,
                        serial=serial,
                        description=f"Device via ADB ({serial})",
                        chipset="Android",
                        platform="Android",
                        properties={},
                    )

                    # Parse -l output: model, product, manufacturer
                    for p in parts[2:]:
                        if ':' in p:
                            k, v = p.split(':', 1)
                            dev.properties[k] = v
                            if k == 'model':
                                dev.model = v

                    # Baca info tambahan dari ADB
                    self._adb_enrich(dev)
                    devices.append(dev)
            return devices
        except FileNotFoundError:
            return []
        except subprocess.TimeoutExpired:
            return []
        except Exception:
            return []

    def _adb_enrich(self, dev: DeviceInfo):
        """Baca info tambahan device via ADB (OS version, battery, model)."""
        if not dev.serial:
            return
        try:
            # OS version
            r = subprocess.run(
                ["adb", "-s", dev.serial, "shell", "getprop ro.build.version.release"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                dev.android_version = r.stdout.strip()
                dev.properties["os_version"] = dev.android_version

            # Model (fallback)
            if not dev.model:
                r = subprocess.run(
                    ["adb", "-s", dev.serial, "shell", "getprop ro.product.model"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0:
                    dev.model = r.stdout.strip()

            # Battery
            r = subprocess.run(
                ["adb", "-s", dev.serial, "shell", "dumpsys battery | grep level"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0 and ':' in r.stdout:
                try:
                    dev.battery = int(r.stdout.split(':')[1].strip())
                except ValueError:
                    pass

            # Brand
            r = subprocess.run(
                ["adb", "-s", dev.serial, "shell", "getprop ro.product.brand"],
                capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                dev.brand = r.stdout.strip()
        except Exception:
            pass

    def _scan_fastboot(self) -> List[DeviceInfo]:
        """Deteksi device via Fastboot."""
        try:
            result = subprocess.run(
                ["fastboot", "devices"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0 or not clean_console_output(result.stdout).strip():
                return []

            devices = []
            for line in clean_console_output(result.stdout).split('\n'):
                if '\tfastboot' in line:
                    serial = line.split('\t')[0]
                    dev = DeviceInfo(
                        mode=DeviceMode.FASTBOOT,
                        serial=serial,
                        description=f"Device via Fastboot ({serial})",
                        chipset="Android",
                        platform="Android",
                    )
                    devices.append(dev)
            return devices
        except FileNotFoundError:
            return []
        except Exception:
            return []

    def _scan_idevice(self) -> List[DeviceInfo]:
        """Deteksi Apple device via libimobiledevice."""
        try:
            result = subprocess.run(
                ["idevice_id", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and clean_console_output(result.stdout).strip():
                serials = [s.strip() for s in clean_console_output(result.stdout).strip().split('\n') if s.strip()]
                devices = []
                for serial in serials:
                    dev = DeviceInfo(
                        mode=DeviceMode.NORMAL_APPLE,
                        serial=serial,
                        description=f"iPhone via libimobiledevice ({serial[:12]}...)",
                        chipset="Apple",
                        platform="Apple",
                    )
                    # Coba dapatkan info tambahan
                    try:
                        r = subprocess.run(
                            ["ideviceinfo", "-k", "ProductType"],
                            capture_output=True, text=True, timeout=3
                        )
                        if r.returncode == 0:
                            dev.model = r.stdout.strip()
                    except Exception:
                        pass
                    devices.append(dev)
                return devices
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return []

    def _scan_dfu_util(self) -> List[DeviceInfo]:
        """Deteksi DFU device via dfu-util."""
        try:
            result = subprocess.run(
                ["dfu-util", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and "Found DFU" in clean_console_output(result.stdout):
                # Parse DFU devices
                devices = []
                for line in clean_console_output(result.stdout).split('\n'):
                    if "Found DFU" in line:
                        # Found DFU: [0483:df11] ver=0200, devnum=1, cfg=1, ...
                        match = re.search(r'\[([0-9a-f]{4}):([0-9a-f]{4})\]', line, re.I)
                        if match:
                            vid = int(match.group(1), 16)
                            pid = int(match.group(2), 16)
                            dev = DeviceInfo(
                                mode=DeviceMode.DFU_STM32,
                                vid=vid, pid=pid,
                                description=f"DFU device: [{vid:04X}:{pid:04X}]",
                                chipset="STM32",
                                platform="STM32",
                            )
                            # Cari serial dari baris berikutnya
                            serial_match = re.search(r'serial="?([0-9A-F]+)"?', clean_console_output(result.stdout))
                            if serial_match:
                                dev.serial = serial_match.group(1)
                            devices.append(dev)
                return devices
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return []

    def _scan_stlink(self) -> List[DeviceInfo]:
        """Deteksi ST-Link device via st-info."""
        try:
            result = subprocess.run(
                ["st-info", "--probe"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and ("ST-Link" in clean_console_output(result.stdout) or "stlink" in clean_console_output(result.stdout).lower()):
                dev = DeviceInfo(
                    mode=DeviceMode.STLINK,
                    description="ST-Link detected via st-info",
                    chipset="STM32",
                    platform="STM32",
                )
                # Coba dapatkan serial
                try:
                    r = subprocess.run(
                        ["st-info", "--serial"],
                        capture_output=True, text=True, timeout=3
                    )
                    if r.returncode == 0:
                        dev.serial = r.stdout.strip()
                except Exception:
                    pass
                return [dev]
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return []

    def _scan_serial_once(self) -> List[DeviceInfo]:
        """Scan serial port untuk STM32 bootloader dan generic device."""
        devices = []
        try:
            if self._os_name == "Windows":
                result = subprocess.run(
                    ['powershell',
                     'Get-WmiObject Win32_SerialPort | Select-Object DeviceID, Description, Name | ConvertTo-Json -Compress'],
                    capture_output=True, text=True, timeout=5
                )
                if clean_console_output(result.stdout).strip() and clean_console_output(result.stdout).strip() != 'null':
                    try:
                        data = json.loads(clean_console_output(result.stdout))
                        if isinstance(data, dict):
                            data = [data]
                        for item in data:
                            desc = (item.get('Description', '') or '').lower()
                            name = item.get('Name', '') or ''
                            device_id = item.get('DeviceID', '') or ''
                            if 'stm32' in desc or 'stlink' in desc:
                                devices.append(DeviceInfo(
                                    mode=DeviceMode.UART_BOOT,
                                    serial=device_id,
                                    description=f"STM32 Serial: {name}",
                                    chipset="STM32",
                                    platform="STM32",
                                ))
                            elif 'com' in device_id.lower() and not devices:
                                # Generic serial port
                                pass
                    except (json.JSONDecodeError, Exception):
                        pass
            else:
                # Linux/Mac: scan ttyUSB, ttyACM
                import glob
                for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
                    for port in glob.glob(pattern):
                        if os.access(port, os.R_OK):
                            devices.append(DeviceInfo(
                                mode=DeviceMode.SERIAL,
                                serial=port,
                                description=f"Serial port: {port}",
                                chipset="Generic",
                                platform="Serial",
                            ))
        except Exception:
            pass
        return devices

    # ── Monitor Mode ──

    def monitor(self, interval: float = 2.0, callback: Optional[Callable] = None):
        """
        Monitor koneksi device real-time.

        Args:
            interval: Waktu antar scan (detik)
            callback: Fungsi yang dipanggil setiap ada perubahan device.
                      Signature: callback(connected: List[DeviceInfo], disconnected: List[DeviceInfo])
        """
        if PLUGINS_AVAILABLE:
            log.header("[MODE SCANNER — MONITOR REAL-TIME]")
            log.info("Memantau device connection... (CTRL+C untuk stop)")
            print(f"  {Colors.DIM}Interval: {interval}s | Cache TTL: {self._cache_ttl}s{Colors.RESET}")
            print()

        previous: List[DeviceInfo] = []
        try:
            while True:
                time.sleep(2)
                current = self.scan_all(force=True)

                # Deteksi perubahan
                prev_keys = set(d.serial or f"{d.vid:04X}:{d.pid:04X}" for d in previous)
                curr_keys = set(d.serial or f"{d.vid:04X}:{d.pid:04X}" for d in current)

                new_devices = [d for d in current if (d.serial or f"{d.vid:04X}:{d.pid:04X}") not in prev_keys]
                removed = [d for d in previous if (d.serial or f"{d.vid:04X}:{d.pid:04X}") not in curr_keys]

                if new_devices and PLUGINS_AVAILABLE:
                    print(f"\n  {Colors.GREEN}[CONNECTED]{Colors.RESET}")
                    for d in new_devices:
                        print(f"    + {d}")
                        log.success(f"Device terhubung: {d}")
                elif new_devices:
                    for d in new_devices:
                        print(f"  + {d}")

                if removed and PLUGINS_AVAILABLE:
                    print(f"\n  {Colors.RED}[DISCONNECTED]{Colors.RESET}")
                    for d in removed:
                        print(f"    - {d}")
                        log.warning(f"Device terputus: {d}")
                elif removed:
                    for d in removed:
                        print(f"  - {d}")

                # Panggil callback jika ada
                if callback and (new_devices or removed):
                    callback(new_devices, removed)

                if not current:
                    if PLUGINS_AVAILABLE:
                        print(f"\r  {Colors.DIM}Menunggu device...{Colors.RESET}", end="")
                    else:
                        print(f"\r  Menunggu device...", end="")

                previous = current
                time.sleep(interval)

        except KeyboardInterrupt:
            if PLUGINS_AVAILABLE:
                print()
                log.info("Monitor dihentikan")

    # ── Display ──

    def show_results(self, devices: Optional[List[DeviceInfo]] = None):
        """Tampilkan hasil scan.""" ""
        if not PLUGINS_AVAILABLE:
            for d in (devices or []):
                print(f"  {d}")
            return

        display = devices if devices is not None else self._cache

        if not display:
            print(f"  {Colors.DIM}Tidak ada device terdeteksi.{Colors.RESET}")
            return

        # Group by platform
        from collections import defaultdict
        by_platform = defaultdict(list)
        for d in display:
            by_platform[d.platform or d.chipset or "Unknown"].append(d)

        total = len(display)
        print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
        print(f"  {Colors.BOLD}Total: {total} device terdeteksi{Colors.RESET}")
        print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")

        for platform_name, platform_devices in by_platform.items():
            platform_color = {
                "Android": Colors.YELLOW,
                "Qualcomm": Colors.RED,
                "MediaTek": Colors.MAGENTA,
                "Samsung": Colors.BLUE,
                "Apple": Colors.CYAN,
                "STM32": Colors.GREEN,
                "Unisoc": Colors.BRIGHT_YELLOW,
                "HiSilicon": Colors.BRIGHT_CYAN,
            }.get(platform_name, Colors.WHITE)

            print(f"\n  {platform_color}{Colors.BOLD}[{platform_name}]{Colors.RESET} ({len(platform_devices)} device)")
            for dev in platform_devices:
                mode_str = str(dev.mode) if hasattr(dev.mode, 'name') else str(dev.mode)
                print(f"  {Colors.DIM}    ├─ {mode_str:20s}{Colors.RESET} {dev.description[:50]}")
                if dev.serial:
                    print(f"  {Colors.DIM}    │  Serial: {dev.serial[:20]}{Colors.RESET}")
                if dev.model:
                    print(f"  {Colors.DIM}    │  Model:  {dev.model[:30]}{Colors.RESET}")
                if dev.android_version:
                    print(f"  {Colors.DIM}    │  OS:     {dev.android_version}{Colors.RESET}")
                if dev.battery >= 0:
                    print(f"  {Colors.DIM}    │  Bat:    {dev.battery}%{Colors.RESET}")

        print()


# ===========================================================================
# FUNGSI UTILITY — untuk dipanggil dari main.py langsung
# ===========================================================================

def run_mode_scan():
    """Scan semua device — tampilkan hasil lengkap."""
    if PLUGINS_AVAILABLE:
        log.header("[MODE SCANNER — FULL SCAN]")
        log.info("Memindai semua port USB + tools...")
        print()

    scanner = ModeScanner()
    devices = scanner.scan_all(force=True)

    if PLUGINS_AVAILABLE:
        scanner.show_results(devices)
        if devices:
            log.success(f"{len(devices)} device terdeteksi!")
        else:
            log.warning("Tidak ada device terdeteksi")
    else:
        print(f"\n{len(devices)} device terdeteksi")
        for d in devices:
            print(f"  {d}")


def run_mode_fast():
    """Quick scan — USB VID/PID only."""
    if PLUGINS_AVAILABLE:
        log.header("[MODE SCANNER — FAST SCAN]")
        log.info("USB VID/PID scan (cepat)...")
        print()

    scanner = ModeScanner()
    devices = scanner.fast_scan(force=True)

    if PLUGINS_AVAILABLE:
        scanner.show_results(devices)
        if devices:
            log.success(f"{len(devices)} device via USB")
        else:
            log.warning("Tidak ada USB device terdeteksi")


def run_mode_monitor():
    """Real-time device monitor."""
    if PLUGINS_AVAILABLE:
        log.header("[MODE SCANNER — MONITOR]")
    ModeScanner().monitor(interval=2.0)


def run_mode_info():
    """Tampilkan info mode scanner — database stats."""
    if not PLUGINS_AVAILABLE:
        print("Mode Scanner — Consolidated USB Database")
        print(f"  Total entries: {len(CONSOLIDATED_USB_DB)}")
        return

    from core.logger import Colors as C

    # Hitung statistik
    by_chipset: Dict[str, int] = {}
    by_mode: Dict[str, int] = {}
    for vid, pid, mode, desc in CONSOLIDATED_USB_DB:
        chipset = ModeScanner().get_chipset(vid, pid)
        by_chipset[chipset] = by_chipset.get(chipset, 0) + 1
        mode_name = mode.name if hasattr(mode, 'name') else str(mode)
        by_mode[mode_name] = by_mode.get(mode_name, 0) + 1

    print(f"  {C.BOLD}{C.DIM}{'─' * 56}{C.RESET}")
    print(f"  {C.BOLD}MODE SCANNER — INFO DATABASE{C.RESET}")
    print(f"  {C.DIM}{'─' * 56}{C.RESET}")
    print(f"  Total USB entries: {C.BOLD}{len(CONSOLIDATED_USB_DB)}{C.RESET}")
    print(f"  Unique vendors:    {C.BOLD}{len(by_chipset)}{C.RESET}")
    print(f"  Unique modes:      {C.BOLD}{len(by_mode)}{C.RESET}")
    print()
    print(f"  {C.BOLD}Per Chipset:{C.RESET}")
    for chipset, count in sorted(by_chipset.items(), key=lambda x: -x[1]):
        print(f"    {C.DIM}  {chipset:25s}{C.RESET} {count} USB IDs")

    print()
    print(f"  {C.BOLD}Per Mode:{C.RESET}")
    for mode_name, count in sorted(by_mode.items(), key=lambda x: -x[1]):
        print(f"    {C.DIM}  {mode_name:25s}{C.RESET} {count} entries")

    # Tools
    print()
    print(f"  {C.BOLD}External Tools:{C.RESET}")
    tools = {
        "ADB": "adb", "Fastboot": "fastboot", "libimobiledevice": "idevice_id",
        "dfu-util": "dfu-util", "st-info": "st-info",
    }
    for name, cmd in tools.items():
        found = subprocess.run(["where", cmd] if platform.system() == "Windows" else ["which", cmd],
                               capture_output=True, text=True, timeout=2).returncode == 0
        status = f"{C.GREEN}OK{C.RESET}" if found else f"{C.RED}Not Found{C.RESET}"
        print(f"    {C.DIM}  {name:25s}{C.RESET} {status}")


# ===========================================================================
# Quick test
# ===========================================================================

if __name__ == "__main__":
    print("=== MODE SCANNER TEST ===")
    scanner = ModeScanner()

    print("\n1. Statistik Database:")
    print(f"   Total USB entries: {len(CONSOLIDATED_USB_DB)}")
    print(f"   Unique vendors: {len(_USB_VID_MAP)}")

    print("\n2. Fast Scan (USB only):")
    devices = scanner.fast_scan(force=True)
    print(f"   Found: {len(devices)} USB device(s)")
    for d in devices:
        print(f"     {d}")

    print("\n3. Full Scan (USB + Tools):")
    devices = scanner.scan_all(force=True)
    print(f"   Found: {len(devices)} device(s)")
    for d in devices:
        print(f"     {d}")

    print("\n4. Mode Detection Test:")
    test_cases = [
        (0x0483, 0xDF11), (0x05AC, 0x1220), (0x05C6, 0x9008),
        (0x0E8D, 0x0003), (0x04E8, 0x6601), (0x1782, 0x5000),
        (0x12D1, 0x3600), (0x18D1, 0xD00D),
    ]
    for vid, pid in test_cases:
        mode = scanner.detect_mode(vid, pid)
        desc = scanner.get_description(vid, pid)
        chipset = scanner.get_chipset(vid, pid)
        print(f"     {vid:04X}:{pid:04X} -> {mode:25s} | {chipset:20s} | {desc}")

