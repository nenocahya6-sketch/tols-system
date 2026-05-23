

"""
Plugin MediaTek — BROM, Preloader, DA untuk chipset MediaTek (MTK).

Dukungan mode:
- BROM (BootROM) — USB VCOM port, low-level flashing
- Preloader — Intermediate boot stage
- DA (Download Agent) — Full flash access
- META Mode — RF/Modem calibration

TO DO:
- Implementasi BROM handshake via USB VCOM
- Parsing scatter.txt (MTK partition layout)
- Download Agent communication protocol
"""


import os
import sys
from typing import Dict, List, Optional, Any

from plugins import BasePlugin, DeviceMode, DeviceInfo, USB_ID
from core.mode_scanner import ModeScanner
from core.external_tools import ToolManager, ToolStatus


# ── MediaTek USB IDs ──
MTK_VID = 0x0E8D

MTK_USB_IDS = [
    # BROM / Preloader (VCOM port)
    USB_ID(0x0E8D, 0x0003, "MediaTek USB VCOM (BROM)"),
    USB_ID(0x0E8D, 0x2000, "MediaTek Preloader USB VCOM"),
    USB_ID(0x0E8D, 0x2001, "MediaTek Preloader (MT65xx)"),
    USB_ID(0x0E8D, 0x2002, "MediaTek Preloader VCOM"),
    USB_ID(0x0E8D, 0x2003, "MediaTek Preloader (MT67xx)"),
    USB_ID(0x0E8D, 0x2004, "MediaTek Preloader VCOM (MTK)"),
    USB_ID(0x0E8D, 0x2005, "MediaTek Preloader"),
    USB_ID(0x0E8D, 0x2006, "MediaTek Preloader (MT68xx)"),
    USB_ID(0x0E8D, 0x2007, "MediaTek Device"),
    USB_ID(0x0E8D, 0x2008, "MediaTek Preloader (MT8167)"),
    USB_ID(0x0E8D, 0x2009, "MediaTek Preloader VCOM"),
    USB_ID(0x0E8D, 0x200A, "MediaTek Device"),
    USB_ID(0x0E8D, 0x200B, "MediaTek Preloader"),
    USB_ID(0x0E8D, 0x200C, "MediaTek Device"),
    USB_ID(0x0E8D, 0x200D, "MediaTek Preloader"),
    USB_ID(0x0E8D, 0x200E, "MediaTek Device (BROM)"),
    # DA / Download Agent
    USB_ID(0x0E8D, 0x3000, "MediaTek Download Agent"),
    USB_ID(0x0E8D, 0x3001, "MediaTek DA (MT65xx)"),
    USB_ID(0x0E8D, 0x3002, "MediaTek DA VCOM"),
    USB_ID(0x0E8D, 0x3003, "MediaTek DA (MT67xx)"),
    USB_ID(0x0E8D, 0x3004, "MediaTek DA VCOM"),
    USB_ID(0x0E8D, 0x3005, "MediaTek DA Protocol"),
    USB_ID(0x0E8D, 0x3006, "MediaTek DA (USB)"),
    USB_ID(0x0E8D, 0x3007, "MediaTek DA (MT68xx)"),
    USB_ID(0x0E8D, 0x3008, "MediaTek DA"),
    USB_ID(0x0E8D, 0x3009, "MediaTek DA VCOM"),
    # META Mode
    USB_ID(0x0E8D, 0x4000, "MediaTek META Mode"),
    USB_ID(0x0E8D, 0x4001, "MediaTek META (USB)"),
    USB_ID(0x0E8D, 0x4002, "MediaTek META (RF)"),
    USB_ID(0x0E8D, 0x4003, "MediaTek META Mode"),
    # ATF Mode
    USB_ID(0x0E8D, 0x5000, "MediaTek ATF Mode"),
    USB_ID(0x0E8D, 0x5001, "MediaTek ATF (USB)"),
    # Normal Mode (ADB)
    USB_ID(0x0E8D, 0x1000, "MediaTek Device (Normal)"),
    USB_ID(0x0E8D, 0x1001, "MediaTek Android Phone"),
    # OEM-specific
    USB_ID(0x2717, 0x2008, "Xiaomi MTK Preloader"),
    USB_ID(0x2717, 0x3008, "Xiaomi MTK DA"),
    USB_ID(0x04E8, 0x2008, "Samsung MTK Preloader"),
    USB_ID(0x0BB4, 0x2008, "HMD/Nokia MTK Preloader"),
]

MTK_MODE_MAP = {
    0x0003: DeviceMode.BROM,
    0x2000: DeviceMode.PRELOADER,
    0x2001: DeviceMode.PRELOADER,
    0x2002: DeviceMode.PRELOADER,
    0x2003: DeviceMode.PRELOADER,
    0x2004: DeviceMode.PRELOADER,
    0x2005: DeviceMode.PRELOADER,
    0x2006: DeviceMode.PRELOADER,
    0x2007: DeviceMode.PRELOADER,
    0x2008: DeviceMode.PRELOADER,
    0x2009: DeviceMode.PRELOADER,
    0x200A: DeviceMode.PRELOADER,
    0x200B: DeviceMode.PRELOADER,
    0x200C: DeviceMode.PRELOADER,
    0x200D: DeviceMode.PRELOADER,
    0x200E: DeviceMode.PRELOADER,
    0x3000: DeviceMode.DA,
    0x3001: DeviceMode.DA,
    0x3002: DeviceMode.DA,
    0x3003: DeviceMode.DA,
    0x3004: DeviceMode.DA,
    0x3005: DeviceMode.DA,
    0x3006: DeviceMode.DA,
    0x3007: DeviceMode.DA,
    0x3008: DeviceMode.DA,
    0x3009: DeviceMode.DA,
    0x4000: DeviceMode.META,
    0x4001: DeviceMode.META,
    0x4002: DeviceMode.META,
    0x4003: DeviceMode.META,
    0x5000: DeviceMode.ATF,
    0x5001: DeviceMode.ATF,
}

MTK_CHIPSETS = [
    "MT6761 (Helio A22)", "MT6762 (Helio P22)", "MT6765 (Helio P35)",
    "MT6768 (Helio P65)", "MT6771 (Helio P60)", "MT6779 (Helio P90)",
    "MT6781 (Helio G96)", "MT6785 (Helio G90)", "MT6789 (Helio G99)",
    "MT6833 (Dimensity 700)", "MT6835 (Dimensity 6100+)",
    "MT6853 (Dimensity 720)", "MT6855 (Dimensity 6080)",
    "MT6873 (Dimensity 800)", "MT6875 (Dimensity 820)",
    "MT6877 (Dimensity 900)", "MT6879 (Dimensity 810)",
    "MT6883 (Dimensity 1000+)", "MT6885 (Dimensity 1000)",
    "MT6886 (Dimensity 1200)", "MT6889 (Dimensity 1200 Pro)",
    "MT6891 (Dimensity 1100)", "MT6893 (Dimensity 1200)",
    "MT6895 (Dimensity 8100)", "MT6896 (Dimensity 8200)",
    "MT6983 (Dimensity 9000)", "MT6985 (Dimensity 9200)",
    "MT6989 (Dimensity 9300)",
    "MT8167", "MT8173", "MT8176",
    "MT6572", "MT6580", "MT6582", "MT6592", "MT6595",
    "MT6735", "MT6737", "MT6739",
    "MT6750", "MT6753", "MT6755",
    "MT8127", "MT8312", "MT8382",
]


# Mode set untuk MediaTek
MTK_MODES = {DeviceMode.BROM, DeviceMode.PRELOADER, DeviceMode.DA,
             DeviceMode.META, DeviceMode.ATF}


class MediaTekPlugin(BasePlugin):
    """Plugin untuk MediaTek (MTK) chipset — BROM, Preloader, DA, scatter parsing."""

    name = "mediatek"
    version = "1.0.0"
    description = "MediaTek (MTK): BROM mode, Preloader, Download Agent — full system flash"
    author = "NST Team"
    dependencies = ["mtkclient"]

    def supported_modes(self) -> List[DeviceMode]:
        return list(MTK_MODES)

    def detect(self) -> List[DeviceInfo]:
        """Deteksi MediaTek device via ModeScanner (BROM/Preloader/DA)."""
        scanner = ModeScanner()
        devices = []
        seen_pids = set()

        all_usb = scanner.scan_usb()
        for dev in all_usb:
            if dev.mode in MTK_MODES and dev.pid not in seen_pids:
                seen_pids.add(dev.pid)
                dev.chipset = "MediaTek"
                dev.platform = "MediaTek"
                dev.model = dev.description
                devices.append(dev)

        return devices

    def enter_mode(self, device: DeviceInfo, target_mode: DeviceMode) -> bool:
        """Mode switching untuk MediaTek — BROM/Preloader/DA."""
        import subprocess
        try:
            # Boot ke Preloader/BROM via ADB
            if target_mode == DeviceMode.BROM:
                # Metode 1: ADB reboot to preloader
                result = subprocess.run(
                    ["adb", "reboot", "preloader"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return True
                # Metode 2: ADB reboot to bootROM
                result = subprocess.run(
                    ["adb", "reboot", "bootrom"],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
            elif target_mode == DeviceMode.PRELOADER:
                result = subprocess.run(
                    ["adb", "reboot", "preloader"],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
            elif target_mode == DeviceMode.DA:
                # Metode mtkclient jika tersedia
                try:
                    result = subprocess.run(
                        ["mtk", "da"],
                        capture_output=True, text=True, timeout=15
                    )
                    return result.returncode == 0
                except FileNotFoundError:
                    pass
                return False
            return False
        except Exception:
            return False

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        info = {
            "platform": "MediaTek",
            "mode": str(device.mode),
            "description": device.description,
            "vid:pid": f"{device.vid:04X}:{device.pid:04X}" if device.vid else "N/A",
        }

        # Cek mtkclient availability via ToolManager
        try:
            tm = ToolManager()
            if tm.mtkclient.is_available():
                info["mtkclient"] = tm.mtkclient.get_version()
                # Coba detect chipset via mtkclient
                try:
                    chip_info = tm.mtkclient.get_chip()
                    if chip_info:
                        info["chip"] = chip_info
                except Exception:
                    pass
            else:
                info["mtkclient"] = "Not installed — install from https://github.com/bkerler/mtkclient"
        except Exception:
            info["mtkclient"] = "Error checking"

        return info


# ── Export ──
__plugin__ = MediaTekPlugin()