

"""
Plugin Apple — iPhone/iPad detection, DFU, Recovery Mode.

Memanfaatkan:
- core/nst_iphone.py   -> iPhone operations
- libimobiledevice     -> idevice tools (jika tersedia)
- USB VID/PID detection untuk mode
"""
from core import clean_console_output



import os
import sys
import subprocess
from typing import Dict, List, Optional, Any

# ── Import core modules (project root sudah di sys.path oleh main.py) ──

try:
    from core.nst_iphone import NSTiPhone as iPhoneHandler
    from core.logger import log
    IPHONE_AVAILABLE = True
except ImportError as e:
    IPHONE_AVAILABLE = False
    _import_error = str(e)

from plugins import BasePlugin, DeviceMode, DeviceInfo, USB_ID
from core.mode_scanner import ModeScanner
from core.external_tools import ToolManager, ToolStatus


# Mode set untuk Apple — digunakan untuk filter hasil ModeScanner
APPLE_MODES = {DeviceMode.NORMAL_APPLE, DeviceMode.RECOVERY_APPLE, DeviceMode.DFU_APPLE,
               DeviceMode.PWNED_DFU, DeviceMode.IBOOT, DeviceMode.PURPLE_MODE}


class ApplePlugin(BasePlugin):
    """Plugin untuk Apple iPhone/iPad."""

    name = "apple"
    version = "1.0.0"
    description = "Apple iPhone/iPad: Normal, Recovery, DFU mode detection + basic operations"
    author = "NST Team"
    dependencies = ["libimobiledevice"]

    def __init__(self):
        super().__init__()
        self._handler = None

    def _get_handler(self) -> Optional[iPhoneHandler]:
        if not IPHONE_AVAILABLE:
            return None
        if self._handler is None:
            self._handler = iPhoneHandler()
        return self._handler

    def supported_modes(self) -> List[DeviceMode]:
        return [
            DeviceMode.NORMAL_APPLE,
            DeviceMode.RECOVERY_APPLE,
            DeviceMode.DFU_APPLE,
            DeviceMode.PWNED_DFU,
            DeviceMode.IBOOT,
            DeviceMode.PURPLE_MODE,
        ]

    def detect(self) -> List[DeviceInfo]:
        """Deteksi iPhone dalam berbagai mode via ModeScanner."""
        devices = []
        seen_serials = set()

        # ── Metode 1: ModeScanner USB (consolidated database) ──
        scanner = ModeScanner()
        all_usb = scanner.scan_usb()
        for dev in all_usb:
            if dev.mode in APPLE_MODES:
                key = dev.serial or f"{dev.vid:04X}:{dev.pid:04X}"
                if key not in seen_serials:
                    seen_serials.add(key)
                    dev.chipset = "Apple"
                    dev.platform = "Apple"
                    
                    # Coba dapatkan info via NSTiPhone handler
                    if IPHONE_AVAILABLE and dev.mode == DeviceMode.NORMAL_APPLE:
                        try:
                            handler = self._get_handler()
                            if handler:
                                imei_info = handler.scan_imei_real()
                                if imei_info:
                                    dev.serial = imei_info.get("serial", "")
                                    dev.model = imei_info.get("product_type", "") or imei_info.get("model", "")
                                bat_info = handler.scan_battery_health_real()
                                if bat_info:
                                    dev.battery = bat_info.get("level", -1)
                        except Exception:
                            pass

                    devices.append(dev)

        # ── Metode 2: libimobiledevice (fallback) ──
        if not devices:
            dev = self._scan_libimobiledevice()
            if dev:
                devices.append(dev)

        return devices

    def _scan_libimobiledevice(self) -> Optional[DeviceInfo]:
        """Scan via idevice_id / ideviceinfo."""
        try:
            result = subprocess.run(
                ["idevice_id", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and clean_console_output(result.stdout).strip():
                serials = clean_console_output(result.stdout).strip().split("\n")
                if serials:
                    return DeviceInfo(
                        mode=DeviceMode.NORMAL_APPLE,
                        serial=serials[0].strip(),
                        description="iPhone via libimobiledevice",
                        chipset="Apple",
                        platform="Apple",
                    )
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        return None

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        """Dapatkan info detail iPhone."""
        info = {
            "platform": "Apple iOS",
            "mode": str(device.mode),
            "serial": device.serial or "N/A",
            "model": device.model or "N/A",
        }

        if IPHONE_AVAILABLE:
            try:
                handler = self._get_handler()
                if handler:
                    # Gunakan scan_imei_real() — existing method di NSTiPhone
                    imei_info = handler.scan_imei_real()
                    if imei_info:
                        info.update(imei_info)
            except Exception:
                pass

        # Cek libimobiledevice tools via ToolManager
        try:
            tm = ToolManager()
            if tm.libimobile.is_available():
                info["libimobiledevice"] = tm.libimobile.get_version()
                
                # Coba baca info device via ToolManager
                if device.mode == DeviceMode.NORMAL_APPLE:
                    for key, label in [("ProductType", "model_id"),
                                       ("ProductVersion", "ios_version"),
                                       ("DeviceName", "device_name")]:
                        try:
                            r = tm.libimobile.get_info(key)
                            if r.success and r.stdout.strip():
                                info[label] = r.stdout.strip()
                        except Exception:
                            pass
                
                # Cek status pairing
                try:
                    paired = tm.libimobile.is_paired()
                    info["paired"] = "Yes" if paired else "No"
                except Exception:
                    pass
            else:
                info["libimobiledevice"] = "Not installed — install from https://libimobiledevice.org/"
        except Exception:
            # Fallback: coba ideviceinfo langsung
            try:
                result = subprocess.run(
                    ["ideviceinfo", "-k", "ProductType"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    info["model_id"] = clean_console_output(result.stdout).strip()
                result = subprocess.run(
                    ["ideviceinfo", "-k", "ProductVersion"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    info["ios_version"] = clean_console_output(result.stdout).strip()
            except FileNotFoundError:
                info["libimobiledevice"] = "Not installed"
            except Exception:
                pass

        return info

    def enter_mode(self, device: DeviceInfo, target_mode: DeviceMode) -> bool:
        """Pindah mode iPhone."""
        try:
            if target_mode == DeviceMode.RECOVERY_APPLE:
                if device.mode == DeviceMode.NORMAL_APPLE:
                    # Normal -> Recovery
                    result = subprocess.run(
                        ["ideviceenterrecovery", device.serial],
                        capture_output=True, text=True, timeout=10
                    )
                    return result.returncode == 0
                return False
            elif target_mode == DeviceMode.DFU_APPLE:
                # Recovery -> DFU (timing-critical)
                self.log_info("Masuk DFU: Power + Home/VolDown 10s, release Power...")
                self.log_info("Gunakan tools eksternal: irecovery + usbmuxd")
                return False  # DFU entry sangat timing-critical
            return False
        except FileNotFoundError:
            self.log_warn("libimobiledevice tools tidak ditemukan")
            return False
        except Exception as e:
            self.log_error(f"Gagal enter mode {target_mode}: {e}")
            return False


# ── Export ──
__plugin__ = ApplePlugin()