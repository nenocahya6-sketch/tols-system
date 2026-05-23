

"""
Plugin Samsung / Exynos — Download Mode, Heimdall, Odin protocol.

Dukungan mode:
- Download Mode (Odin/Heimdall) — Samsung stock firmware flashing
- Exynos IBL/PBL — Low-level boot chain
- DLOAD/XMIT — Exynos download protocol
- Qualcomm-based Samsung — delegated ke plugin Qualcomm

TO DO:
- Heimdall protocol implementation (pit parsing, partition flash)
- Odin protocol reverse engineering
- PIT file parser
"""


import os
import sys
from typing import Dict, List, Optional, Any

from plugins import BasePlugin, DeviceMode, DeviceInfo, USB_ID
from core.mode_scanner import ModeScanner
from core.external_tools import ToolManager, ToolStatus


# ── Samsung USB IDs ──
SAMSUNG_VID = 0x04E8

SAMSUNG_USB_IDS = [
    # Download Mode (Odin/Heimdall)
    USB_ID(0x04E8, 0x6601, "Samsung Download Mode (Exynos)"),
    USB_ID(0x04E8, 0x6610, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6611, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6612, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6613, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6614, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6615, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6616, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6620, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6621, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6622, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6630, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6640, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6650, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6660, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6670, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6680, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6690, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6700, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6710, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6720, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6730, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6740, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6750, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6760, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6770, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6780, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6790, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6800, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6810, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6820, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6830, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6840, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6850, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6860, "Samsung Download Mode (USB)"),
    USB_ID(0x04E8, 0x6870, "Samsung Download Mode (USB)"),
    # Exynos-specific
    USB_ID(0x04E8, 0x6920, "Samsung Exynos IBL Mode"),
    USB_ID(0x04E8, 0x6930, "Samsung Exynos PBL Mode"),
    USB_ID(0x04E8, 0x6940, "Samsung Exynos DLOAD Mode"),
    USB_ID(0x04E8, 0x6950, "Samsung Exynos XMIT Mode"),
    # Qualcomm Samsung (EDL)
    USB_ID(0x04E8, 0x685D, "Samsung Qualcomm EDL"),
    USB_ID(0x04E8, 0x685E, "Samsung Qualcomm EDL"),
    USB_ID(0x04E8, 0x6860, "Samsung Qualcomm Download"),
    # ADB Mode
    USB_ID(0x04E8, 0x6866, "Samsung ADB Normal Mode"),
    USB_ID(0x04E8, 0x6875, "Samsung ADB (Android)"),
    USB_ID(0x04E8, 0x68C0, "Samsung ADB Mode"),
    # Recovery
    USB_ID(0x04E8, 0x68C1, "Samsung Recovery Mode"),
]

SAMSUNG_MODE_MAP = {}
for pid in range(0x6601, 0x6880):
    SAMSUNG_MODE_MAP[pid] = DeviceMode.DOWNLOAD
SAMSUNG_MODE_MAP.update({
    0x6920: DeviceMode.IBL,
    0x6930: DeviceMode.PBL,
    0x6940: DeviceMode.DLOAD,
    0x6950: DeviceMode.XMIT,
    0x685D: DeviceMode.EDL,
    0x685E: DeviceMode.EDL,
    0x6860: DeviceMode.EDL,
    0x6866: DeviceMode.ADB,
    0x6875: DeviceMode.ADB,
    0x68C0: DeviceMode.ADB,
    0x68C1: DeviceMode.RECOVERY,
})


# Mode set untuk Samsung
SAMSUNG_MODES = {DeviceMode.DOWNLOAD, DeviceMode.HEIMDALL, DeviceMode.DLOAD,
                 DeviceMode.XMIT, DeviceMode.IBL, DeviceMode.PBL}


class SamsungPlugin(BasePlugin):
    """Plugin untuk Samsung/Exynos device — Download Mode, Heimdall, Odin."""

    name = "samsung"
    version = "1.0.0"
    description = "Samsung Exynos: Download Mode, Odin/Heimdall protocol — firmware flashing & recovery"
    author = "NST Team"
    dependencies = ["heimdall"]

    def supported_modes(self) -> List[DeviceMode]:
        return list(SAMSUNG_MODES)

    def detect(self) -> List[DeviceInfo]:
        """Deteksi Samsung device via ModeScanner (Download/Exynos modes)."""
        scanner = ModeScanner()
        devices = []
        seen_pids = set()

        all_usb = scanner.scan_usb()
        for dev in all_usb:
            if dev.mode in SAMSUNG_MODES and dev.pid not in seen_pids:
                seen_pids.add(dev.pid)
                dev.chipset = "Exynos/Samsung"
                dev.platform = "Samsung"
                if not dev.model:
                    dev.model = dev.description
                devices.append(dev)

        return devices

    def enter_mode(self, device: DeviceInfo, target_mode: DeviceMode) -> bool:
        """Reboot Samsung ke Download Mode via ADB."""
        import subprocess
        try:
            if target_mode == DeviceMode.DOWNLOAD:
                result = subprocess.run(
                    ["adb", "reboot", "download"],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
            return False
        except Exception:
            return False

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        info = {
            "platform": "Samsung",
            "mode": str(device.mode),
            "description": device.description,
        }

        # Cek heimdall availability via ToolManager
        try:
            tm = ToolManager()
            if tm.heimdall.is_available():
                info["heimdall"] = tm.heimdall.get_version()
                # Coba print PIT info jika di Download Mode
                if device.mode == DeviceMode.DOWNLOAD:
                    try:
                        pit_result = tm.heimdall.print_pit()
                        if pit_result.success:
                            info["pit"] = "Readable"
                    except Exception:
                        pass
            else:
                info["heimdall"] = "Not installed — install from https://glassechidna.com.au/heimdall/"
        except Exception:
            info["heimdall"] = "Error checking"

        return info


# ── Export ──
__plugin__ = SamsungPlugin()