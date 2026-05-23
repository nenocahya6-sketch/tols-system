

"""
Plugin Kirin / HiSilicon — HiSilicon USB Download, Fastboot, Burn Mode.

Dukungan mode:
- HiSilicon USB Download — Factory flashing mode
- Hisilicon Fastboot — Bootloader mode
- Kirin Burn Mode — Low-level flashing
- DL Mode — Download Mode for HiSilicon

TO DO:
- HiSilicon USB download protocol
- Hisilicon Fastboot OEM commands
- Partition table parsing (xml)
"""


import os
import sys
from typing import Dict, List, Optional, Any

from plugins import BasePlugin, DeviceMode, DeviceInfo, USB_ID
from core.mode_scanner import ModeScanner


# ── HiSilicon / Kirin USB IDs ──
HISILICON_VID = 0x12D1

HISILICON_USB_IDS = [
    # HiSilicon USB Download Mode
    USB_ID(0x12D1, 0x3600, "HiSilicon USB Download (Kirin)"),
    USB_ID(0x12D1, 0x3601, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3602, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3603, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3605, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3607, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3609, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3610, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3611, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3613, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3615, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3617, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3619, "HiSilicon USB Download"),
    USB_ID(0x12D1, 0x3620, "HiSilicon USB Download"),
    # Fastboot
    USB_ID(0x12D1, 0x360D, "HiSilicon Fastboot"),
    USB_ID(0x12D1, 0x360E, "HiSilicon Fastboot"),
    USB_ID(0x12D1, 0x360F, "HiSilicon Fastboot"),
    USB_ID(0x12D1, 0x361D, "HiSilicon Fastboot"),
    USB_ID(0x12D1, 0x361F, "HiSilicon Fastboot"),
    # Normal / ADB
    USB_ID(0x12D1, 0x1077, "HiSilicon Android ADB"),
    USB_ID(0x12D1, 0x1079, "HiSilicon Android Phone"),
    USB_ID(0x12D1, 0x107E, "HiSilicon Device"),
    USB_ID(0x12D1, 0x1080, "HiSilicon Device (ADB)"),
    USB_ID(0x12D1, 0x1081, "HiSilicon Device"),
    # Burn Mode
    USB_ID(0x12D1, 0x3700, "HiSilicon Burn Mode"),
    USB_ID(0x12D1, 0x3701, "HiSilicon Burn Mode (USB)"),
    # Huawei-specific
    USB_ID(0x18D1, 0x4EE2, "Huawei HiSilicon Download"),
    USB_ID(0x18D1, 0x4EE3, "Huawei HiSilicon Fastboot"),
    USB_ID(0x18D1, 0x4EE4, "Huawei HiSilicon ADB"),
    USB_ID(0x18D1, 0x4EE5, "Huawei HiSilicon Download"),
    USB_ID(0x18D1, 0x4EE6, "Huawei HiSilicon (USB)"),
]

HISILICON_MODE_MAP = {
    0x3600: DeviceMode.HISILICON_USB,
    0x3601: DeviceMode.HISILICON_USB,
    0x3602: DeviceMode.HISILICON_USB,
    0x3603: DeviceMode.HISILICON_USB,
    0x3605: DeviceMode.HISILICON_USB,
    0x3607: DeviceMode.HISILICON_USB,
    0x3609: DeviceMode.HISILICON_USB,
    0x3610: DeviceMode.HISILICON_USB,
    0x3611: DeviceMode.HISILICON_USB,
    0x3613: DeviceMode.HISILICON_USB,
    0x3615: DeviceMode.HISILICON_USB,
    0x3617: DeviceMode.HISILICON_USB,
    0x3619: DeviceMode.HISILICON_USB,
    0x3620: DeviceMode.HISILICON_USB,
    0x360D: DeviceMode.FASTBOOT_HISI,
    0x360E: DeviceMode.FASTBOOT_HISI,
    0x360F: DeviceMode.FASTBOOT_HISI,
    0x361D: DeviceMode.FASTBOOT_HISI,
    0x361F: DeviceMode.FASTBOOT_HISI,
    0x3700: DeviceMode.BURN_MODE,
    0x3701: DeviceMode.BURN_MODE,
    0x1077: DeviceMode.ADB,
    0x1079: DeviceMode.ADB,
    0x107E: DeviceMode.ADB,
}

HISILICON_CHIPSETS = [
    "Kirin 9000", "Kirin 9000E", "Kirin 9000S",
    "Kirin 990 5G", "Kirin 990E", "Kirin 990",
    "Kirin 985 5G", "Kirin 980",
    "Kirin 820 5G", "Kirin 810",
    "Kirin 710A", "Kirin 710", "Kirin 700",
    "Kirin 659", "Kirin 658", "Kirin 655", "Kirin 650",
    "Kirin 960", "Kirin 955", "Kirin 950",
    "Kirin 935", "Kirin 930", "Kirin 925", "Kirin 920",
    "Kirin 910", "Kirin 620",
    "Kirin 460", "Kirin 450",
    "HiSilicon Balong 5000",
    "Kirin A2",
]


# Mode set untuk Kirin/HiSilicon
HISILICON_MODES = {DeviceMode.HISILICON_USB, DeviceMode.FASTBOOT_HISI,
                   DeviceMode.BURN_MODE, DeviceMode.DL_MODE_HISI}


class KirinPlugin(BasePlugin):
    """Plugin untuk Kirin/HiSilicon chipset — USB Download, Fastboot, Burn Mode."""

    name = "kirin"
    version = "1.0.0"
    description = "Kirin/HiSilicon: USB Download Mode, Fastboot, Burn Mode — flash & unbrick"
    author = "NST Team"
    dependencies = ["hisilicon_tools"]

    def supported_modes(self) -> List[DeviceMode]:
        return list(HISILICON_MODES)

    def detect(self) -> List[DeviceInfo]:
        """Deteksi Kirin/HiSilicon device via ModeScanner."""
        scanner = ModeScanner()
        devices = []
        seen_pids = set()

        all_usb = scanner.scan_usb()
        for dev in all_usb:
            if dev.mode in HISILICON_MODES and dev.pid not in seen_pids:
                seen_pids.add(dev.pid)
                dev.chipset = "Kirin"
                dev.platform = "HiSilicon"
                dev.model = dev.description
                devices.append(dev)

        return devices

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        return {
            "platform": "HiSilicon",
            "chipset": "Kirin",
            "mode": str(device.mode),
            "description": device.description,
            "status": "dev — implementasi menyusul",
        }


# ── Export ──
__plugin__ = KirinPlugin()