"""
NST Plugin Architecture v1.0
============================
Sistem plugin universal untuk mendukung multi-chipset dan multi-device.

Struktur:
    plugins/
    ├── __init__.py      # BasePlugin, PluginRegistry, DeviceMode
    ├── loader.py        # Auto-discovery + hot-reload
    ├── stm32/           # Plugin STM32
    ├── apple/           # Plugin iPhone/iPad
    ├── qualcomm/        # Plugin Qualcomm (EDL, Sahara, Firehose)
    ├── mediatek/        # Plugin MediaTek (BROM, DA, Preloader)
    ├── samsung/         # Plugin Samsung/Exynos (Download Mode, Heimdall)
    ├── unisoc/          # Plugin Unisoc (FDL, ResearchDownload)
    └── kirin/           # Plugin Kirin/HiSilicon
"""


import os
import sys
import json
import time
import logging
import inspect
import importlib
import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any, Callable, Type

# ---------------------------------------------------------------------------
# DeviceMode — semua mode device yang didukung
# ---------------------------------------------------------------------------

class DeviceMode(Enum):
    """Mode operasi device — universal untuk semua chipset/platform."""

    # ── Android Universal ──
    ADB            = auto()  # Android Normal (ADB)
    FASTBOOT       = auto()  # Bootloader (Fastboot)
    RECOVERY       = auto()  # Custom Recovery (TWRP, OrangeFox)
    SIDELOAD       = auto()  # ADB Sideload

    # ── Qualcomm ──
    EDL            = auto()  # Emergency Download (Qualcomm 9008)
    SAHARA         = auto()  # Sahara Protocol (Qualcomm)
    FIREHOSE       = auto()  # Firehose Protocol (Qualcomm)
    QDL            = auto()  # Qualcomm Download Mode
    HSUSB          = auto()  # Qualcomm HS-USB (Diagnostic)

    # ── MediaTek ──
    BROM           = auto()  # BootROM (MediaTek — USB VCOM)
    PRELOADER      = auto()  # Preloader (MediaTek)
    DA             = auto()  # Download Agent (MediaTek)
    META           = auto()  # META Mode (MediaTek RF)
    ATF            = auto()  # Advanced Telephony Feature

    # ── Samsung / Exynos ──
    DOWNLOAD       = auto()  # Download Mode (Samsung Odin)
    HEIMDALL       = auto()  # Heimdall Protocol
    DLOAD          = auto()  # Exynos DLOAD
    XMIT           = auto()  # Exynos XMIT (Odin protocol)
    IBL            = auto()  # Exynos IBL (First Bootloader)
    PBL            = auto()  # Exynos PBL (Primary Bootloader)

    # ── Unisoc / Spreadtrum ──
    FDL            = auto()  # Fast Download Loader (Unisoc)
    RESEARCH       = auto()  # ResearchDownload Mode
    UART_DOWNLOAD  = auto()  # UART Download Mode (Unisoc)
    BOOTROM_SPRD   = auto()  # Spreadtrum BootROM

    # ── Kirin / HiSilicon ──
    HISILICON_USB  = auto()  # HiSilicon USB Download
    FASTBOOT_HISI  = auto()  # HiSilicon Fastboot
    BURN_MODE      = auto()  # Kirin Burn Mode
    DL_MODE_HISI   = auto()  # Hisilicon Download Mode

    # ── Apple / iPhone ──
    NORMAL_APPLE   = auto()  # iOS Normal
    RECOVERY_APPLE = auto()  # Recovery Mode
    DFU_APPLE      = auto()  # DFU Mode
    PWNED_DFU      = auto()  # Pwned DFU (checkm8)
    IBOOT          = auto()  # iBoot
    PURPLE_MODE    = auto()  # Purple Mode (diagnostic)

    # ── STM32 ──
    STLINK         = auto()  # ST-Link Debug Probe
    DFU_STM32      = auto()  # DFU (USB DFU Class)
    UART_BOOT      = auto()  # UART Bootloader
    SWD            = auto()  # Serial Wire Debug
    DFU_BOOT       = auto()  # DFU Bootloader (system memory)
    ROM_BOOT       = auto()  # ROM Bootloader

    # ── Generic ──
    UNKNOWN        = auto()  # Unknown / Not detected
    SERIAL         = auto()  # Generic Serial Port
    USB_DEBUG      = auto()  # USB Debug Mode

    # ── Modem / RF ──
    DIAG           = auto()  # Qualcomm Diag Port
    MODEM          = auto()  # Modem Mode
    DOWNLOAD_MODEM = auto()  # Modem Download

    @property
    def category(self) -> str:
        """Kategori mode."""
        categories = {
            "ADB": "android", "FASTBOOT": "android", "RECOVERY": "android", "SIDELOAD": "android",
            "EDL": "qualcomm", "SAHARA": "qualcomm", "FIREHOSE": "qualcomm", "QDL": "qualcomm", "HSUSB": "qualcomm",
            "BROM": "mediatek", "PRELOADER": "mediatek", "DA": "mediatek", "META": "mediatek", "ATF": "mediatek",
            "DOWNLOAD": "samsung", "HEIMDALL": "samsung", "DLOAD": "samsung", "XMIT": "samsung", "IBL": "samsung", "PBL": "samsung",
            "FDL": "unisoc", "RESEARCH": "unisoc", "UART_DOWNLOAD": "unisoc", "BOOTROM_SPRD": "unisoc",
            "HISILICON_USB": "kirin", "FASTBOOT_HISI": "kirin", "BURN_MODE": "kirin", "DL_MODE_HISI": "kirin",
            "NORMAL_APPLE": "apple", "RECOVERY_APPLE": "apple", "DFU_APPLE": "apple", "PWNED_DFU": "apple", "IBOOT": "apple", "PURPLE_MODE": "apple",
            "STLINK": "stm32", "DFU_STM32": "stm32", "UART_BOOT": "stm32", "SWD": "stm32", "DFU_BOOT": "stm32", "ROM_BOOT": "stm32",
        }
        return categories.get(self.name, "other")

    def __str__(self) -> str:
        return self.name.replace("_", " ").title()


# ---------------------------------------------------------------------------
# USB Vendor/Product ID helpers
# ---------------------------------------------------------------------------

@dataclass
class USB_ID:
    """USB Vendor/Product ID pair."""
    vid: int
    pid: int
    description: str = ""

    def __hash__(self):
        return hash((self.vid, self.pid))

    def __eq__(self, other):
        if isinstance(other, USB_ID):
            return self.vid == other.vid and self.pid == other.pid
        return False


@dataclass
class DeviceInfo:
    """Informasi device terdeteksi."""
    serial: str = ""
    model: str = ""
    brand: str = ""
    chipset: str = ""
    platform: str = ""
    mode: DeviceMode = DeviceMode.UNKNOWN
    vid: int = 0
    pid: int = 0
    usb_ids: List[USB_ID] = field(default_factory=list)
    description: str = ""
    battery: int = -1
    android_version: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"[{self.mode}]"]
        if self.model: parts.append(self.model)
        if self.serial: parts.append(f"({self.serial})")
        if self.chipset: parts.append(f"Chip: {self.chipset}")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# BasePlugin — abstract base class untuk semua plugin
# ---------------------------------------------------------------------------

class BasePlugin(ABC):
    """
    Base class untuk semua plugin device.

    Setiap plugin mewakili SATU chipset/platform (Qualcomm, MediaTek, dll.)
    dan bisa handle MULTIPLE device modes.
    """

    # Metadata — diisi oleh subclass
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = "NST Team"
    homepage: str = ""
    dependencies: List[str] = []

    def __init__(self):
        self._log = logging.getLogger(f"nst.plugin.{self.name}")

    # ── Abstract methods ──

    @abstractmethod
    def detect(self) -> List[DeviceInfo]:
        """
        Deteksi semua device yang kompatibel dengan plugin ini.
        Returns list DeviceInfo dengan mode terdeteksi.
        """
        ...

    @abstractmethod
    def supported_modes(self) -> List[DeviceMode]:
        """Return daftar mode yang didukung plugin ini."""
        ...

    # ── Optional methods (default = tidak didukung) ──

    def flash(self, device: DeviceInfo, firmware_path: str, **kwargs) -> bool:
        """Flash firmware ke device. Return True jika sukses."""
        raise NotImplementedError(f"{self.name} tidak mendukung flashing")

    def backup(self, device: DeviceInfo, backup_path: str, **kwargs) -> bool:
        """Backup device. Return True jika sukses."""
        raise NotImplementedError(f"{self.name} tidak mendukung backup")

    def restore(self, device: DeviceInfo, backup_path: str, **kwargs) -> bool:
        """Restore device dari backup. Return True jika sukses."""
        raise NotImplementedError(f"{self.name} tidak mendukung restore")

    def emergency_recovery(self, device: DeviceInfo, **kwargs) -> bool:
        """Emergency recovery untuk bricked device. Return True jika sukses."""
        raise NotImplementedError(f"{self.name} tidak mendukung emergency recovery")

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        """Dapatkan informasi detail device. Return dict properties."""
        return {}

    def enter_mode(self, device: DeviceInfo, target_mode: DeviceMode) -> bool:
        """Reboot device ke mode tertentu. Return True jika sukses."""
        raise NotImplementedError(f"{self.name} tidak mendukung mode switching")

    def verify_firmware(self, firmware_path: str, device: Optional[DeviceInfo] = None) -> Dict[str, Any]:
        """
        Verifikasi firmware compatibility.
        Return dict: {'valid': bool, 'messages': [...], 'hash_match': bool, ...}
        """
        return {"valid": True, "messages": [], "hash_match": True}

    # ── Utility methods ──

    def log_info(self, msg: str):
        self._log.info(f"[{self.name}] {msg}")

    def log_warn(self, msg: str):
        self._log.warning(f"[{self.name}] {msg}")

    def log_error(self, msg: str):
        self._log.error(f"[{self.name}] {msg}")

    def log_debug(self, msg: str):
        self._log.debug(f"[{self.name}] {msg}")

    def __repr__(self) -> str:
        return f"<Plugin {self.name} v{self.version}>"


# ---------------------------------------------------------------------------
# PluginRegistry — central registry + discovery
# ---------------------------------------------------------------------------

class PluginRegistry:
    """
    Central registry untuk semua plugin.
    
    - Auto-discover plugin dari plugins/ directory
    - Maintain mapping: plugin_name -> plugin_instance
    - Support query: plugin by chipset, mode, vendor ID
    """

    _instance: Optional["PluginRegistry"] = None
    _plugins: Dict[str, BasePlugin] = {}
    _mode_map: Dict[DeviceMode, List[str]] = {}  # mode -> [plugin_names]
    _chipset_map: Dict[str, List[str]] = {}       # chipset -> [plugin_names]
    _detect_cache: List[DeviceInfo] = []
    _cache_time: float = 0
    CACHE_TTL: float = 2.0  # detik sebelum re-detect

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── Plugin Management ──

    @classmethod
    def register(cls, plugin: BasePlugin) -> bool:
        """Daftarkan plugin instance. Return False jika duplikat."""
        if plugin.name in cls._plugins:
            return False
        cls._plugins[plugin.name] = plugin
        
        # Index by supported modes
        for mode in plugin.supported_modes():
            if mode not in cls._mode_map:
                cls._mode_map[mode] = []
            cls._mode_map[mode].append(plugin.name)
        
        return True

    @classmethod
    def unregister(cls, name: str) -> bool:
        """Hapus plugin dari registry."""
        if name not in cls._plugins:
            return False
        plugin = cls._plugins.pop(name)
        
        # Clean mode map
        for mode in plugin.supported_modes():
            if mode in cls._mode_map and name in cls._mode_map[mode]:
                cls._mode_map[mode].remove(name)
        return True

    @classmethod
    def get_plugin(cls, name: str) -> Optional[BasePlugin]:
        return cls._plugins.get(name)

    @classmethod
    def get_all_plugins(cls) -> List[BasePlugin]:
        return list(cls._plugins.values())

    @classmethod
    def get_plugins_by_mode(cls, mode: DeviceMode) -> List[BasePlugin]:
        """Cari plugin yang support mode tertentu."""
        names = cls._mode_map.get(mode, [])
        return [cls._plugins[n] for n in names if n in cls._plugins]

    @classmethod
    def get_plugins_by_category(cls, category: str) -> List[BasePlugin]:
        """Cari plugin berdasarkan kategori (android, qualcomm, mediatek, dll)."""
        result = []
        for plugin in cls._plugins.values():
            modes = plugin.supported_modes()
            if any(m.category == category for m in modes):
                result.append(plugin)
        return result

    @classmethod
    def get_plugin_for_device(cls, device: DeviceInfo) -> Optional[BasePlugin]:
        """Cari plugin terbaik untuk device tertentu berdasarkan mode."""
        return cls.get_plugins_by_mode(device.mode)[0] if cls.get_plugins_by_mode(device.mode) else None

    # ── Detection ──

    @classmethod
    def detect_all(cls, force: bool = False) -> List[DeviceInfo]:
        """
        Jalankan detect() di SEMUA plugin.
        Results ter-cache selama CACHE_TTL detik.
        """
        now = time.time()
        if not force and (now - cls._cache_time) < cls.CACHE_TTL:
            return cls._detect_cache

        all_devices: List[DeviceInfo] = []
        for plugin in cls._plugins.values():
            try:
                devices = plugin.detect()
                all_devices.extend(devices)
            except Exception as e:
                cls._log_warn(f"Plugin {plugin.name}.detect() error: {e}")

        cls._detect_cache = all_devices
        cls._cache_time = now
        return all_devices

    @classmethod
    def detect_plugins(cls) -> Dict[str, List[DeviceInfo]]:
        """Detect per-plugin. Return dict {plugin_name: [devices]}."""
        result = {}
        for name, plugin in cls._plugins.items():
            try:
                devices = plugin.detect()
                if devices:
                    result[name] = devices
            except Exception as e:
                cls._log_warn(f"Plugin {name}.detect() error: {e}")
        return result

    # ── Action helpers ──

    @classmethod
    def execute_on_device(cls, device: DeviceInfo, action: str, **kwargs) -> Any:
        """
        Execute action pada device tertentu.
        action: 'flash', 'backup', 'restore', 'emergency_recovery', 'get_device_info'
        """
        plugin = cls.get_plugin_for_device(device)
        if not plugin:
            raise ValueError(f"Tidak ada plugin untuk mode {device.mode}")

        method = getattr(plugin, action, None)
        if not method:
            raise NotImplementedError(f"Plugin {plugin.name} tidak support action '{action}'")

        return method(device, **kwargs)

    @classmethod
    def summary(cls) -> str:
        """Return ringkasan semua plugin terdaftar."""
        lines = [f"  Plugin Registry: {len(cls._plugins)} plugin(s) terdaftar"]
        for name, plugin in cls._plugins.items():
            modes = ", ".join(str(m) for m in plugin.supported_modes()[:5])
            extra = "..." if len(plugin.supported_modes()) > 5 else ""
            lines.append(f"    ├─ {name} v{plugin.version} — modes: {modes}{extra}")
        return "\n".join(lines)

    @classmethod
    def _log_warn(cls, msg: str):
        logging.getLogger("nst.plugin").warning(msg)


# ---------------------------------------------------------------------------
# Plugin base class short-name
# ---------------------------------------------------------------------------

Plugin = BasePlugin  # alias


# ===========================================================================
# Quick test
# ===========================================================================

if __name__ == "__main__":
    # Test DeviceMode
    print("=== Device Modes ===")
    for mode in DeviceMode:
        print(f"  {mode.name:20s} -> {mode.category:15s} | {mode}")

    print("\n=== Plugin Registry (kosong) ===")
    print(PluginRegistry.summary())