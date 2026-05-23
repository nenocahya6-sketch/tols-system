

"""
Plugin STM32 — Flash, Backup, Recovery untuk mikrokontroler STM32.

Memanfaatkan:
- core/anti_brick.py  -> STM32 Anti-Brick recovery
- core/flasher.py     -> STM32 Flashing
- core/environment.py -> ST-Link/DFU tool detection
"""
from core import clean_console_output



import os
import sys
import json
import time
import subprocess
from typing import Dict, List, Optional, Any

# ── Pastikan project root ada di path ──
# ── Import core modules (project root sudah di sys.path oleh main.py) ──

# ── Import core modules ──
try:
    from core.flasher import Flasher as STM32Flasher
    from core.anti_brick import AntiBrickRecovery
    from core.environment import EnvironmentChecker
    from core.logger import log
    FLASHER_AVAILABLE = True
except ImportError as e:
    FLASHER_AVAILABLE = False
    _import_error = str(e)

from plugins import BasePlugin, DeviceMode, DeviceInfo, USB_ID


# Mode mapping untuk STM32 (digunakan oleh ModeScanner via CONSOLIDATED_USB_DB)
STM32_MODES = {DeviceMode.STLINK, DeviceMode.DFU_STM32, DeviceMode.UART_BOOT,
               DeviceMode.SWD, DeviceMode.DFU_BOOT, DeviceMode.ROM_BOOT}


class STM32Plugin(BasePlugin):
    """Plugin untuk STM32 microcontroller series."""

    name = "stm32"
    version = "1.0.0"
    description = "STM32 microcontroller: ST-Link, DFU, UART boot — flash, backup, anti-brick recovery"
    author = "NST Team"
    dependencies = ["stm32-flasher", "dfu-util", "stlink-tools"]

    def __init__(self):
        super().__init__()
        self._env_checker = None

    def _get_env(self) -> EnvironmentChecker:
        if self._env_checker is None:
            self._env_checker = EnvironmentChecker()
        return self._env_checker

    def supported_modes(self) -> List[DeviceMode]:
        return [
            DeviceMode.STLINK,
            DeviceMode.DFU_STM32,
            DeviceMode.UART_BOOT,
            DeviceMode.SWD,
            DeviceMode.DFU_BOOT,
            DeviceMode.ROM_BOOT,
        ]

    def detect(self) -> List[DeviceInfo]:
        """Deteksi device STM32 via ModeScanner + tool scan."""
        from core.mode_scanner import ModeScanner
        devices = []
        seen_pids = set()

        # ── Metode 1: ModeScanner (consolidated USB database) ──
        scanner = ModeScanner()
        all_usb = scanner.scan_usb()
        for dev in all_usb:
            if dev.mode in STM32_MODES:
                if dev.pid not in seen_pids:
                    seen_pids.add(dev.pid)
                    dev.chipset = "STM32"
                    dev.platform = "STM32"
                    # Coba dapatkan serial via ST-Link
                    if dev.mode == DeviceMode.STLINK:
                        serial = self._get_stlink_serial()
                        if serial:
                            dev.serial = serial
                            dev.model = f"STM32 via ST-Link ({serial})"
                    elif dev.mode == DeviceMode.DFU_STM32:
                        dev.model = "STM32 DFU Bootloader"
                    devices.append(dev)

        # ── Metode 2: Tool scan (st-flash, dfu-util) — fallback ──
        if not devices:
            stlink = self._scan_stlink()
            if stlink:
                devices.append(stlink)
            dfu = self._scan_dfu()
            if dfu:
                devices.append(dfu)

        return devices

    def _get_stlink_serial(self) -> Optional[str]:
        """Dapatkan serial number ST-Link via ST-Link CLI."""
        try:
            result = subprocess.run(
                ["st-info", "--serial"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return clean_console_output(result.stdout).strip()
        except FileNotFoundError:
            pass
        return None

    def _scan_stlink(self) -> Optional[DeviceInfo]:
        """Scan via st-info."""
        try:
            result = subprocess.run(
                ["st-info", "--probe"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and "ST-Link" in clean_console_output(result.stdout):
                return DeviceInfo(
                    mode=DeviceMode.STLINK,
                    description="ST-Link detected via st-info",
                    chipset="STM32",
                    platform="STM32",
                )
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        return None

    def _scan_dfu(self) -> Optional[DeviceInfo]:
        """Scan via dfu-util."""
        try:
            result = subprocess.run(
                ["dfu-util", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and "Found DFU" in clean_console_output(result.stdout):
                return DeviceInfo(
                    mode=DeviceMode.DFU_STM32,
                    description="DFU device detected via dfu-util",
                    chipset="STM32",
                    platform="STM32",
                )
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        return None

    def flash(self, device: DeviceInfo, firmware_path: str, **kwargs) -> bool:
        """Flash firmware STM32 menggunakan core/flasher.py jika tersedia."""
        if not FLASHER_AVAILABLE:
            self.log_error(f"Flasher tidak tersedia: {_import_error}")
            return False

        try:
            flasher = STM32Flasher()
            port = kwargs.get("port", None)
            method = kwargs.get("method", "auto")
            
            if method == "stlink":
                return flasher.flash_stlink(firmware_path)
            elif method == "dfu":
                return flasher.flash_dfu(firmware_path)
            else:
                return flasher.flash(firmware_path, port=port)
        except Exception as e:
            self.log_error(f"Flash gagal: {e}")
            return False

    def backup(self, device: DeviceInfo, backup_path: str, **kwargs) -> bool:
        """Backup firmware STM32."""
        # Implementasi: read flash via ST-Link + save ke file
        if not FLASHER_AVAILABLE:
            self.log_error(f"Flasher tidak tersedia")
            return False
        try:
            flasher = STM32Flasher()
            # Default read dari STM32 flash
            addr = kwargs.get("address", 0x08000000)
            size = kwargs.get("size", 0x100000)  # 1MB
            data = flasher.read_flash(addr, size)
            if data:
                with open(backup_path, "wb") as f:
                    f.write(data)
                self.log_info(f"Backup saved: {backup_path} ({len(data)} bytes)")
                return True
            return False
        except Exception as e:
            self.log_error(f"Backup gagal: {e}")
            return False

    def emergency_recovery(self, device: DeviceInfo, **kwargs) -> bool:
        """Anti-brick recovery untuk STM32."""
        if not FLASHER_AVAILABLE:
            self.log_error(f"Core modules tidak tersedia")
            return False
        try:
            recovery = AntiBrickRecovery()
            method = kwargs.get("method", None)
            if method == "dfu":
                return recovery.method_dfu_mode()
            elif method == "stlink":
                return recovery.method_stlink_flash()
            elif method == "serial":
                return recovery.method_serial_boot()
            elif method == "mass_erase":
                return recovery.method_mass_erase()
            else:
                # Auto-detect best method
                return recovery.run()  # full recovery menu
        except Exception as e:
            self.log_error(f"Emergency recovery gagal: {e}")
            return False

    def get_device_info(self, device: DeviceInfo) -> Dict[str, Any]:
        """Dapatkan info detail device STM32."""
        info = {
            "chipset": "STM32",
            "platform": "STM32",
            "mode": str(device.mode),
            "serial": device.serial or "N/A",
            "description": device.description,
        }

        # Coba dapatkan info chip via st-info
        try:
            result = subprocess.run(
                ["st-info", "--chipid"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info["chip_id"] = clean_console_output(result.stdout).strip()
            
            result = subprocess.run(
                ["st-info", "--flash"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info["flash_size"] = clean_console_output(result.stdout).strip()
            
            result = subprocess.run(
                ["st-info", "--sram"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info["sram_size"] = clean_console_output(result.stdout).strip()
        except FileNotFoundError:
            info["tool"] = "st-info not found"
        except subprocess.TimeoutExpired:
            pass

        return info

    def verify_firmware(self, firmware_path: str, device: Optional[DeviceInfo] = None) -> Dict[str, Any]:
        """Verifikasi firmware STM32 (.bin/.hex)."""
        import hashlib
        import os

        result = {
            "valid": False,
            "messages": [],
            "hash_match": True,
            "format": "unknown",
            "size": 0,
            "sha256": "",
        }

        if not os.path.isfile(firmware_path):
            result["messages"].append("❌ File tidak ditemukan")
            return result

        ext = os.path.splitext(firmware_path)[1].lower()
        size = os.path.getsize(firmware_path)
        result["size"] = size

        # Cek format
        if ext in (".bin", ".hex", ".elf"):
            result["format"] = ext[1:]
            result["valid"] = True
            result["messages"].append(f"✅ Format: {ext[1:].upper()} ({size} bytes)")
        else:
            result["messages"].append(f"⚠️ Format tidak dikenal: {ext}")

        # Hash
        with open(firmware_path, "rb") as f:
            result["sha256"] = hashlib.sha256(f.read()).hexdigest()

        # Size check
        if size == 0:
            result["valid"] = False
            result["messages"].append("❌ File kosong!")
        elif size > 2 * 1024 * 1024:  # 2MB
            result["messages"].append("⚠️ File > 2MB — mungkin terlalu besar untuk STM32")

        return result


# ── Export ──
__plugin__ = STM32Plugin()