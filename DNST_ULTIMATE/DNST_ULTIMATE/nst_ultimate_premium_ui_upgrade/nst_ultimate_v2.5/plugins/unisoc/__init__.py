

"""
Plugin Unisoc / Spreadtrum — FDL, ResearchDownload, UART Download Mode.

Dukungan mode:
- FDL (Fast Download Loader) — Unisoc flashing protocol
- ResearchDownload Mode — Factory flash tool mode
- UART Download — Serial-based download
- BootROM — Low-level USB mode

TO DO:
- FDL protocol implementation
- ResearchDownload USB handshake
- UART download mode support
"""


import os
import sys
from typing import Dict, List, Optional, Any

from plugins import BasePlugin, DeviceMode, DeviceInfo, USB_ID
from core.mode_scanner import ModeScanner


# ── Unisoc / Spreadtrum USB IDs ──
UNISOC_VID = 0x1782

UNISOC_USB_IDS = [
    # Spreadtrum BootROM
    USB_ID(0x1782, 0x4000, "Spreadtrum BootROM"),
    USB_ID(0x1782, 0x4001, "Spreadtrum BootROM (USB)"),
    USB_ID(0x1782, 0x4005, "Spreadtrum BootROM (SC9850)"),
    USB_ID(0x1782, 0x4006, "Spreadtrum (SC9832)"),
    USB_ID(0x1782, 0x4008, "Spreadtrum BootROM (SC7731)"),
    USB_ID(0x1782, 0x4009, "Spreadtrum BootROM (SC9820)"),
    USB_ID(0x1782, 0x400A, "Spreadtrum BootROM (SC9863)"),
    USB_ID(0x1782, 0x400B, "Spreadtrum BootROM"),
    USB_ID(0x1782, 0x400C, "Spreadtrum BootROM (Tiger)"),
    USB_ID(0x1782, 0x400D, "Spreadtrum BootROM (Shark)"),
    USB_ID(0x1782, 0x400E, "Spreadtrum BootROM"),
    USB_ID(0x1782, 0x400F, "Spreadtrum BootROM"),
    # FDL Mode
    USB_ID(0x1782, 0x5000, "Unisoc FDL Mode"),
    USB_ID(0x1782, 0x5001, "Unisoc FDL (USB)"),
    USB_ID(0x1782, 0x5002, "Unisoc FDL VCOM"),
    USB_ID(0x1782, 0x5005, "Unisoc FDL Mode"),
    USB_ID(0x1782, 0x5006, "Unisoc FDL (SC9850)"),
    USB_ID(0x1782, 0x5008, "Unisoc FDL Mode"),
    USB_ID(0x1782, 0x5009, "Unisoc FDL"),
    USB_ID(0x1782, 0x500A, "Unisoc FDL Mode"),
    # ResearchDownload
    USB_ID(0x1782, 0x6000, "Unisoc ResearchDownload"),
    USB_ID(0x1782, 0x6001, "Unisoc ResearchDownload Mode"),
    USB_ID(0x1782, 0x6002, "Unisoc RD (USB)"),
    USB_ID(0x1782, 0x6003, "Unisoc ResearchDownload"),
    USB_ID(0x1782, 0x6004, "Unisoc ResearchDownload (SC9850)"),
    USB_ID(0x1782, 0x6005, "Unisoc ResearchDownload Mode"),
    # Normal / ADB
    USB_ID(0x1782, 0x3000, "Unisoc Device (Normal)"),
    USB_ID(0x1782, 0x3001, "Unisoc ADB"),
    USB_ID(0x1782, 0x3002, "Unisoc Device"),
    # OEM (Xiaomi, Realme etc)
    USB_ID(0x2717, 0x5008, "Xiaomi Unisoc FDL"),
    USB_ID(0x2717, 0x6008, "Xiaomi Unisoc ResearchDownload"),
    USB_ID(0x0BB4, 0x5008, "Nokia Unisoc FDL"),
]

UNISOC_MODE_MAP = {
    0x4000: DeviceMode.BOOTROM_SPRD,
    0x4001: DeviceMode.BOOTROM_SPRD,
    0x4005: DeviceMode.BOOTROM_SPRD,
    0x4006: DeviceMode.BOOTROM_SPRD,
    0x4008: DeviceMode.BOOTROM_SPRD,
    0x4009: DeviceMode.BOOTROM_SPRD,
    0x400A: DeviceMode.BOOTROM_SPRD,
    0x400B: DeviceMode.BOOTROM_SPRD,
    0x400C: DeviceMode.BOOTROM_SPRD,
    0x400D: DeviceMode.BOOTROM_SPRD,
    0x400E: DeviceMode.BOOTROM_SPRD,
    0x400F: DeviceMode.BOOTROM_SPRD,
    0x5000: DeviceMode.FDL,
    0x5001: DeviceMode.FDL,
    0x5002: DeviceMode.FDL,
    0x5005: DeviceMode.FDL,
    0x5006: DeviceMode.FDL,
    0x5008: DeviceMode.FDL,
    0x5009: DeviceMode.FDL,
    0x500A: DeviceMode.FDL,
    0x6000: DeviceMode.RESEARCH,
    0x6001: DeviceMode.RESEARCH,
    0x6002: DeviceMode.RESEARCH,
    0x6003: DeviceMode.RESEARCH,
    0x6004: DeviceMode.RESEARCH,
    0x6005: DeviceMode.RESEARCH,
}

UNISOC_CHIPSETS = [
    "SC9820", "SC9832", "SC9836", "SC9850", "SC9853",
    "SC9863", "SC7715", "SC7731", "SC7727", "SC8810",
    "Tiger T310", "Tiger T610", "Tiger T612", "Tiger T616", "Tiger T618",
    "Tiger T710", "Tiger T740", "Tiger T7510", "Tiger T760", "Tiger T770",
    "Shark S86", "Shark T7510",
    "UIS7862", "UIS7881", "UIS8142", "UIS8581",
    "UMS9117", "UMS9230", "UMS9620",
]


# Mode set untuk Unisoc
UNISOC_MODES = {DeviceMode.FDL, DeviceMode.RESEARCH, DeviceMode.BOOTROM_SPRD, DeviceMode.UART_DOWNLOAD}


class UnisocPlugin(BasePlugin):
    """Plugin untuk Unisoc/Spreadtrum chipset — FDL, ResearchDownload, BootROM."""

    name = "unisoc"
    version = "1.0.0"
    description = "Unisoc/Spreadtrum: FDL, ResearchDownload Mode, BootROM — flash & unbrick"
    author = "NST Team"
    dependencies = ["research_download", "fdl_tools"]

    def supported_modes(self) -> List[DeviceMode]:
        return list(UNISOC_MODES)

    def detect(self) -> List[DeviceInfo]:
        """Deteksi Unisoc device via ModeScanner (FDL/BootROM/ResearchDownload)."""
        scanner = ModeScanner()
        devices = []
        seen_pids = set()

        all_usb = scanner.scan_usb()
        for dev in all_usb:
            if dev.mode in UNISOC_MODES and dev.pid not in seen_pids:
                seen_pids.add(dev.pid)
                dev.chipset = "Unisoc"
                dev.platform = "Unisoc"
                dev.model = dev.description
                devices.append(dev)

        return devices

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        return {
            "platform": "Unisoc",
            "mode": str(device.mode),
            "description": device.description,
            "status": "dev — implementasi menyusul (ResearchDownload integration planned)",
        }


# ── Export ──
__plugin__ = UnisocPlugin()