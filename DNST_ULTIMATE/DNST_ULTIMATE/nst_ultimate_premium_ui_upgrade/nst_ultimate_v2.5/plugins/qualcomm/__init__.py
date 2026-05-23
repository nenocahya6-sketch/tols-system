

"""
Plugin Qualcomm — EDL, Sahara, Firehose protocol untuk chipset Qualcomm.

Dukungan mode:
- EDL (Emergency Download Mode) — USB VID 0x05C6, 0x9008
- Sahara Protocol — handshake & image transfer
- Firehose Protocol — raw partition programming
- HS-USB Diagnostic — 900E, 9003, dll.

TO DO:
- Implementasi Sahara protocol handshake
- Implementasi Firehose XML-based programming
- QPST/QFIL integration
"""


import os
import sys
from typing import Dict, List, Optional, Any

from plugins import BasePlugin, DeviceMode, DeviceInfo, USB_ID
from core.mode_scanner import ModeScanner
from core.external_tools import ToolManager, ToolStatus


# ── Qualcomm USB IDs ──
QUALCOMM_VID = 0x05C6

QUALCOMM_USB_IDS = [
    # EDL Mode (Qualcomm 9008)
    USB_ID(0x05C6, 0x9008, "Qualcomm HS-USB QDLoader 9008 (EDL)"),
    USB_ID(0x05C6, 0x900E, "Qualcomm HS-USB Diagnostics 900E"),
    USB_ID(0x05C6, 0x9003, "Qualcomm HS-USB 9003"),
    USB_ID(0x05C6, 0x9025, "Qualcomm HS-USB 9025 (EDL)"),
    USB_ID(0x05C6, 0x9200, "Qualcomm HS-USB 9200"),
    USB_ID(0x05C6, 0x9201, "Qualcomm HS-USB 9201"),
    USB_ID(0x05C6, 0x920D, "Qualcomm HS-USB 920D (Diag)"),
    USB_ID(0x05C6, 0x920B, "Qualcomm HS-USB 920B (EDL)"),
    USB_ID(0x05C6, 0x920C, "Qualcomm HS-USB 920C"),
    USB_ID(0x05C6, 0x9213, "Qualcomm HS-USB 9213"),
    USB_ID(0x05C6, 0x9214, "Qualcomm HS-USB 9214"),
    USB_ID(0x05C6, 0x9215, "Qualcomm HS-USB 9215 (EDL)"),
    USB_ID(0x05C6, 0x9216, "Qualcomm HS-USB 9216"),
    # Generic QDLoader
    USB_ID(0x05C6, 0x9001, "Qualcomm QDLoader 9001"),
    USB_ID(0x05C6, 0x9002, "Qualcomm QDLoader 9002"),
    USB_ID(0x05C6, 0x9004, "Qualcomm QDLoader 9004"),
    USB_ID(0x05C6, 0x9005, "Qualcomm QDLoader 9005"),
    USB_ID(0x05C6, 0x9006, "Qualcomm QDLoader 9006"),
    # Other OEM EDL PIDs
    USB_ID(0x18D1, 0xD00D, "Google EDL (Qualcomm)"),
    USB_ID(0x18D1, 0x4EE0, "Google EDL (Pixel)"),
    USB_ID(0x0955, 0xCF00, "NVIDIA EDL (Tegra/QC)"),
    USB_ID(0x0955, 0xCF01, "NVIDIA EDL (Tegra)"),
    USB_ID(0x0489, 0xE000, "Foxconn/Qualcomm EDL"),
    USB_ID(0x0489, 0xE001, "Foxconn/Qualcomm EDL"),
    # Samsung Qcomm EDL
    USB_ID(0x04E8, 0x685D, "Samsung Qualcomm EDL"),
    USB_ID(0x04E8, 0x685E, "Samsung Qualcomm EDL"),
    USB_ID(0x04E8, 0x6860, "Samsung Qualcomm EDL"),
    # Xiaomi Qcomm EDL
    USB_ID(0x2717, 0x9046, "Xiaomi Qualcomm EDL"),
    USB_ID(0x2717, 0x9048, "Xiaomi Qualcomm EDL"),
    USB_ID(0x2717, 0x9050, "Xiaomi Qualcomm EDL"),
]

QUALCOMM_MODE_MAP = {
    0x9008: DeviceMode.EDL,
    0x9025: DeviceMode.EDL,
    0x920B: DeviceMode.EDL,
    0x9215: DeviceMode.EDL,
    0x900E: DeviceMode.HSUSB,
    0x9003: DeviceMode.HSUSB,
    0x920D: DeviceMode.DIAG,
    0x9001: DeviceMode.EDL,
    0x9002: DeviceMode.EDL,
}

QUALCOMM_CHIPSETS = [
    "Snapdragon 8 Gen 3", "Snapdragon 8 Gen 2", "Snapdragon 8 Gen 1",
    "Snapdragon 888", "Snapdragon 870", "Snapdragon 865",
    "Snapdragon 780G", "Snapdragon 778G", "Snapdragon 765G",
    "Snapdragon 750G", "Snapdragon 732G", "Snapdragon 720G",
    "Snapdragon 695", "Snapdragon 690", "Snapdragon 680",
    "Snapdragon 662", "Snapdragon 460",
    "Snapdragon 8cx Gen 3", "Snapdragon 8cx Gen 2", "Snapdragon 8cx",
    "Snapdragon 7c+ Gen 3", "Snapdragon 7c Gen 2", "Snapdragon 7c",
    "Snapdragon 6 Gen 1",
    "Snapdragon 4 Gen 1",
    "Snapdragon 210", "Snapdragon 212", "Snapdragon 425", "Snapdragon 435",
    "Snapdragon 450", "Snapdragon 625", "Snapdragon 630", "Snapdragon 636",
    "Snapdragon 652", "Snapdragon 653", "Snapdragon 660", "Snapdragon 665",
    "Snapdragon 670", "Snapdragon 675", "Snapdragon 710", "Snapdragon 712",
    "Snapdragon 720G", "Snapdragon 730G", "Snapdragon 732G",
    "Snapdragon 835", "Snapdragon 845", "Snapdragon 855", "Snapdragon 860",
    "Snapdragon 821", "Snapdragon 820",
    "Snapdragon 805", "Snapdragon 801", "Snapdragon 800",
    "Snapdragon S4 Pro",
]


# Mode set untuk Qualcomm
QUALCOMM_MODES = {DeviceMode.EDL, DeviceMode.SAHARA, DeviceMode.FIREHOSE,
                  DeviceMode.QDL, DeviceMode.HSUSB, DeviceMode.DIAG}


class QualcommPlugin(BasePlugin):
    """Plugin untuk Qualcomm Snapdragon chipset — EDL, Sahara, Firehose."""

    name = "qualcomm"
    version = "1.0.0"
    description = "Qualcomm Snapdragon: EDL mode, Sahara/Firehose protocol — flashing & unbrick"
    author = "NST Team"
    dependencies = ["qsahara_server", "firehose_programmer", "QPST"]

    def supported_modes(self) -> List[DeviceMode]:
        return list(QUALCOMM_MODES)

    def detect(self) -> List[DeviceInfo]:
        """Deteksi Qualcomm device via ModeScanner (EDL/Diag/HSUDB)."""
        from core.mode_scanner import ModeScanner
        scanner = ModeScanner()
        devices = []
        seen_pids = set()

        all_usb = scanner.scan_usb()
        for dev in all_usb:
            if dev.mode in QUALCOMM_MODES and dev.pid not in seen_pids:
                seen_pids.add(dev.pid)
                dev.chipset = "Snapdragon"
                dev.platform = "Qualcomm"
                dev.model = dev.description
                devices.append(dev)

        return devices

    def enter_mode(self, device: DeviceInfo, target_mode: DeviceMode) -> bool:
        """Reboot Qualcomm device ke mode tertentu."""
        import subprocess
        try:
            if target_mode == DeviceMode.EDL:
                # Metode: adb reboot edl
                result = subprocess.run(
                    ["adb", "reboot", "edl"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return True
                # Metode: fastboot oem edl
                result = subprocess.run(
                    ["fastboot", "oem", "edl"],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
            return False
        except Exception:
            return False

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        info = {
            "platform": "Qualcomm",
            "chipset": "Snapdragon",
            "mode": str(device.mode),
            "description": device.description,
            "vid:pid": f"{device.vid:04X}:{device.pid:04X}" if device.vid else "N/A",
        }

        # Cek EDL/Qualcomm tools via ToolManager
        try:
            tm = ToolManager()
            
            # Cek EDL tool (open-source)
            if tm.qpst.check_edl():
                info["edl_tool"] = "Available (pip edl)"
            else:
                info["edl_tool"] = "Not installed — install: pip install edl"

            # Cek QPST/QFIL (Windows)
            qpst_status = tm.qpst.check()
            if qpst_status == ToolStatus.AVAILABLE:
                info["qpst"] = "Available"
            
            # Jika di EDL mode, coba baca info
            if device.mode == DeviceMode.EDL and tm.qpst.check_edl():
                try:
                    gpt_result = tm.qpst.edl_printgpt()
                    if gpt_result.success:
                        info["gpt"] = "Readable"
                except Exception:
                    pass

        except Exception:
            info["edl_tool"] = "Error checking"

        return info


# ── Export ──
__plugin__ = QualcommPlugin()