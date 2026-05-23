

from core import clean_console_output

"""
NST Universal Device Detector
Mendeteksi perangkat yang terhubung via USB:
- Android: ADB, Fastboot, EDL (Qualcomm), BROM (MediaTek)
- iPhone: Normal, Recovery, DFU
- STM32: UART (bootloader), ST-Link, DFU
- Generic: USB VID/PID identification
"""
import os
import time
import platform
import subprocess
import re
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core.logger import log, Colors


# ========== DEVICE DATABASE ==========
# Format: vendor_id -> { name, devices: { product_id: name } }
USB_DEVICE_DATABASE = {
    # Apple / iPhone
    0x05AC: {
        "name": "Apple Inc.",
        "devices": {
            0x1200: "iPhone/iPad (Normal Mode)",
            0x1210: "iPhone/iPad (Recovery Mode)",
            0x1211: "iPhone (Recovery Mode - old)",
            0x1220: "iPhone/iPad (DFU Mode)",
            0x1222: "iPhone (DFU Mode - old)",
            0x1227: "iPhone/iPad (DFU - newer)",
            0x1280: "iPhone (iBoot - DFU)",
            0x1281: "iPhone (iBoot - Recovery)",
            0x1290: "iPhone 5/5C (DFU)",
            0x1291: "iPhone 5/5C (Recovery)",
            0x12A0: "iPhone 5S (DFU)",
            0x12A2: "iPhone 6/6+ (DFU)",
            0x12A8: "iPhone 6S/SE (DFU)",
            0x12AA: "iPhone 7/7+ (DFU)",
            0x12AC: "iPhone 8/8+/X (DFU)",
        }
    },
    # Qualcomm (EDL mode)
    0x05C6: {
        "name": "Qualcomm Inc.",
        "devices": {
            0x9008: "Qualcomm HS-USB QDLoader 9008 (EDL Mode)",
            0x9006: "Qualcomm HS-USB Diagnostics 9006",
            0x900E: "Qualcomm HS-USB QDLoader 900E",
            0x901D: "Qualcomm HS-USB QDLoader 901D",
        }
    },
    # MediaTek (BROM)
    0x0E8D: {
        "name": "MediaTek Inc.",
        "devices": {
            0x0003: "MediaTek MT65xx Preloader (BROM)",
            0x2000: "MediaTek USB VCOM Port",
            0x2001: "MediaTek USB Modem",
        }
    },
    # Google (Fastboot)
    0x18D1: {
        "name": "Google Inc.",
        "devices": {
            0xD00D: "Android Fastboot",
            0x4EE7: "Android ADB (Nexus/Pixel)",
            0x4EE0: "Android ADB (old)",
        }
    },
    # Samsung
    0x04E8: {
        "name": "Samsung Electronics",
        "devices": {
            0x6601: "Samsung Galaxy (MTP/ADB)",
            0x685D: "Samsung Galaxy (Download Mode/Odin)",
            0x68C3: "Samsung Galaxy S20 (Download Mode)",
            0x68EF: "Samsung Galaxy S22 (Download Mode)",
        }
    },
    # OnePlus / Oppo
    0x2D95: {
        "name": "OnePlus / Oppo",
        "devices": {
            0x6006: "OnePlus (EDL Mode)",
            0x6007: "OnePlus (EDL Mode - variant)",
        }
    },
    # Xiaomi
    0x2717: {
        "name": "Xiaomi Inc.",
        "devices": {
            0xFF40: "Xiaomi (ADB/Fastboot)",
            0xFF48: "Xiaomi (EDL Mode 9008)",
        }
    },
    # STMicroelectronics
    0x0483: {
        "name": "STMicroelectronics",
        "devices": {
            0x3748: "ST-Link/V2",
            0x374B: "ST-Link/V2-1",
            0x3752: "ST-Link/V3",
            0xDF11: "STM32 Bootloader (DFU)",
            0x5740: "STM32 Virtual COM Port",
        }
    },
    # Generic Android ADB
    0x2B4A: {"name": "Generic Android", "devices": {}},
    0x22B8: {"name": "Motorola", "devices": {}},
    0x413C: {"name": "Dell", "devices": {}},
    0x8087: {"name": "Intel", "devices": {}},
}


class DeviceInfo:
    """Informasi satu perangkat yang terdeteksi"""

    def __init__(self):
        self.method: str = "unknown"       # ADB, fastboot, USB, serial
        self.connection: str = "unknown"   # USB, TCP, serial
        self.vendor_id: Optional[int] = None
        self.product_id: Optional[int] = None
        self.vendor_name: str = "Unknown"
        self.product_name: str = "Unknown"
        self.serial: Optional[str] = None
        self.model: Optional[str] = None
        self.mode: str = "normal"           # normal, recovery, dfu, edl, brom, bootloader, fastboot
        self.adb_available: bool = False
        self.fastboot_available: bool = False
        self.os_version: Optional[str] = None
        self.battery_level: Optional[int] = None
        self.manufacturer: Optional[str] = None
        self.device_name: Optional[str] = None
        self.codename: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "method": self.method,
            "connection": self.connection,
            "vendor_id": f"0x{self.vendor_id:04X}" if self.vendor_id else None,
            "product_id": f"0x{self.product_id:04X}" if self.product_id else None,
            "vendor_name": self.vendor_name,
            "product_name": self.product_name,
            "serial": self.serial,
            "model": self.model,
            "mode": self.mode,
            "adb": self.adb_available,
            "fastboot": self.fastboot_available,
            "os": self.os_version,
            "battery": self.battery_level,
            "manufacturer": self.manufacturer,
            "codename": self.codename,
        }

    def __str__(self) -> str:
        parts = [f"[{self.method.upper()}] {self.vendor_name}"]
        if self.product_name != "Unknown":
            parts.append(self.product_name)
        if self.model:
            parts.append(f"({self.model})")
        if self.serial:
            parts.append(f"SN:{self.serial[:12]}")
        if self.mode != "normal":
            parts.append(f"Mode:{self.mode.upper()}")
        return " ".join(parts)


class DeviceDetector:
    """Pendeteksi perangkat universal"""

    def __init__(self):
        self.os_name = platform.system()
        self.detected_devices: List[DeviceInfo] = []
        self.last_scan: Optional[datetime] = None

    def scan_all(self, silent: bool = False) -> List[DeviceInfo]:
        """Scan semua perangkat yang terhubung (MULTI-THREADED - thread-safe)"""
        if not silent:
            log.header("[DEVICE DETECTOR - SCAN]")
            log.info(f"Mendeteksi perangkat...")

        self.detected_devices = []

        def _safe_scan(scan_method):
            """Wrapper thread-safe: jalankan scan method dan tambahkan hasilnya"""
            try:
                scan_method()
            except Exception as e:
                log.debug(f"Scan thread warning: {type(scan_method).__name__}: {e}")

        # Scan dari berbagai sumber secara PARALEL
        threads = []
        scan_methods = [
            self._scan_adb,
            self._scan_fastboot,
            self._scan_usb_devices,
            self._scan_stm32_serial,
        ]

        for method in scan_methods:
            t = threading.Thread(target=_safe_scan, args=(method,), daemon=True)
            t.start()
            threads.append(t)

        # Tunggu semua thread selesai (max 10 detik)
        for t in threads:
            t.join(timeout=10)

        self.last_scan = datetime.now()

        # Tampilkan hasil
        if not silent:
            if self.detected_devices:
                print()
                for i, dev in enumerate(self.detected_devices, 1):
                    print(f"  {Colors.GREEN}{i}.{Colors.RESET} {dev}")
                    if dev.os_version:
                        print(f"     {Colors.DIM}OS: {dev.os_version}{Colors.RESET}")
                    if dev.battery_level is not None:
                        print(f"     {Colors.DIM}Battery: {dev.battery_level}%{Colors.RESET}")
            else:
                print()
                log.warning("Tidak ada perangkat terdeteksi")
                print(f"  {Colors.DIM}Tips: Pastikan device terhubung via USB dengan driver benar{Colors.RESET}")

        return self.detected_devices

    def _scan_adb(self):
        """Deteksi device via ADB"""
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in clean_console_output(result.stdout).split('\n')[1:]:
                    if '\tdevice' in line:
                        parts = line.split()
                        dev = DeviceInfo()
                        dev.method = "adb"
                        dev.connection = "USB"
                        dev.adb_available = True
                        dev.serial = parts[0]

                        # Parse -l output (model:xxx, product:xxx)
                        for p in parts[2:]:
                            if ':' in p:
                                k, v = p.split(':', 1)
                                if k == 'model':
                                    dev.model = v
                                elif k == 'product':
                                    dev.device_name = v
                                elif k == 'manufacturer':
                                    dev.manufacturer = v

                        # Baca info tambahan
                        self._adb_get_props(dev)
                        self.detected_devices.append(dev)

        except FileNotFoundError:
            pass  # ADB tidak terinstall
        except Exception:
            pass

    def _adb_get_props(self, dev: DeviceInfo):
        """Baca properti device via ADB"""
        try:
            # OS version
            result = subprocess.run(
                ["adb", "-s", dev.serial, "shell", "getprop ro.build.version.release"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                dev.os_version = clean_console_output(result.stdout).strip()

            # Battery
            result = subprocess.run(
                ["adb", "-s", dev.serial, "shell", "dumpsys battery | grep level"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and ':' in clean_console_output(result.stdout):
                dev.battery_level = int(clean_console_output(result.stdout).split(':')[1].strip())

            # Model (as fallback)
            if not dev.model:
                result = subprocess.run(
                    ["adb", "-s", dev.serial, "shell", "getprop ro.product.model"],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    dev.model = clean_console_output(result.stdout).strip()

            # HWID / Codename (Deep Scan)
            result = subprocess.run(
                ["adb", "-s", dev.serial, "shell", "getprop ro.product.device"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and clean_console_output(result.stdout).strip():
                dev.codename = clean_console_output(result.stdout).strip().lower()

        except Exception:
            pass

    def _scan_fastboot(self):
        """Deteksi device via fastboot"""
        try:
            result = subprocess.run(
                ["fastboot", "devices"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and clean_console_output(result.stdout).strip():
                for line in clean_console_output(result.stdout).split('\n'):
                    if '\tfastboot' in line:
                        dev = DeviceInfo()
                        dev.method = "fastboot"
                        dev.connection = "USB"
                        dev.fastboot_available = True
                        dev.mode = "fastboot"
                        dev.serial = line.split('\t')[0]
                        
                        # HWID / Codename (Deep Scan via Fastboot)
                        try:
                            res_fb = subprocess.run(
                                ["fastboot", "-s", dev.serial, "getvar", "product"],
                                capture_output=True, text=True, timeout=3
                            )
                            # fastboot outputs getvar to stderr usually! (e.g. "product: sweet")
                            match = re.search(r'product:\s*([^\s]+)', res_fb.stderr)
                            if match:
                                dev.codename = match.group(1).lower()
                            elif res_fb.stdout:
                                match2 = re.search(r'product:\s*([^\s]+)', res_fb.stdout)
                                if match2:
                                    dev.codename = match2.group(1).lower()
                        except Exception:
                            pass
                            
                        self.detected_devices.append(dev)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _scan_usb_devices(self):
        """Deteksi device via USB VID/PID"""
        try:
            if self.os_name == "Windows":
                self._scan_usb_windows()
            elif self.os_name == "Linux":
                self._scan_usb_linux()
            else:
                self._scan_usb_linux()  # Mac also uses similar approach
        except Exception:
            pass

    def _scan_usb_windows(self):
        """Scan USB via PowerShell Windows"""
        try:
            result = subprocess.run(
                ['powershell', '-Command', 
                 'Get-PnpDevice -PresentOnly | Where-Object {$_.Class -eq "USB" -or $_.Class -eq "Ports"} | '
                 'Select-Object FriendlyName, DeviceID, Status | ConvertTo-Json'],
                capture_output=True, text=True, timeout=10
            )
            if clean_console_output(result.stdout).strip() and clean_console_output(result.stdout).strip() != 'null':
                import json
                try:
                    data = json.loads(clean_console_output(result.stdout))
                    if isinstance(data, dict):
                        data = [data]
                    for item in data:
                        friendly = item.get('FriendlyName', '') or ''
                        device_id = item.get('DeviceID', '') or ''
                        status = item.get('Status', '') or ''
                        
                        if status != 'OK':
                            continue

                        # Cari VID/PID dari DeviceID
                        match = re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', device_id, re.I)
                        if match:
                            vid = int(match.group(1), 16)
                            pid = int(match.group(2), 16)

                            # Cek di database
                            if vid in USB_DEVICE_DATABASE:
                                vendor = USB_DEVICE_DATABASE[vid]
                                product = vendor["devices"].get(pid, "Unknown Device")

                                # Skip jika sudah terdeteksi via ADB/fastboot
                                if any(d.vendor_id == vid and d.product_id == pid for d in self.detected_devices):
                                    continue

                                dev = DeviceInfo()
                                dev.method = "usb"
                                dev.connection = "USB"
                                dev.vendor_id = vid
                                dev.product_id = pid
                                dev.vendor_name = vendor["name"]
                                dev.product_name = product
                                dev.mode = self._classify_mode(vid, pid)
                                self.detected_devices.append(dev)

                except (json.JSONDecodeError, Exception):
                    pass
        except Exception:
            pass

    def _scan_usb_linux(self):
        """Scan USB via lsusb Linux/Mac"""
        try:
            result = subprocess.run(
                ["lsusb"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in clean_console_output(result.stdout).split('\n'):
                    match = re.search(r'ID ([0-9a-f]{4}):([0-9a-f]{4})', line, re.I)
                    if match:
                        vid = int(match.group(1), 16)
                        pid = int(match.group(2), 16)

                        if vid in USB_DEVICE_DATABASE:
                            vendor = USB_DEVICE_DATABASE[vid]
                            product = vendor["devices"].get(pid, "Unknown Device")

                            if any(d.vendor_id == vid and d.product_id == pid for d in self.detected_devices):
                                continue

                            dev = DeviceInfo()
                            dev.method = "usb"
                            dev.connection = "USB"
                            dev.vendor_id = vid
                            dev.product_id = pid
                            dev.vendor_name = vendor["name"]
                            dev.product_name = product
                            dev.mode = self._classify_mode(vid, pid)
                            self.detected_devices.append(dev)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _scan_stm32_serial(self):
        """Deteksi STM32 via serial port"""
        try:
            if self.os_name == "Windows":
                result = subprocess.run(
                    ['powershell', 'Get-WmiObject Win32_SerialPort | Select-Object DeviceID, Description | ConvertTo-Json'],
                    capture_output=True, text=True, timeout=5
                )
                if clean_console_output(result.stdout).strip() and clean_console_output(result.stdout).strip() != 'null':
                    import json
                    try:
                        data = json.loads(clean_console_output(result.stdout))
                        if isinstance(data, dict):
                            data = [data]
                        for item in data:
                            desc = (item.get('Description', '') or '').lower()
                            device_id = item.get('DeviceID', '') or ''
                            if 'stm32' in desc or 'stlink' in desc or 'com' in device_id.lower():
                                dev = DeviceInfo()
                                dev.method = "serial"
                                dev.connection = device_id
                                dev.vendor_name = "STMicroelectronics"
                                dev.product_name = item.get('Description', 'Unknown')
                                dev.mode = "bootloader"
                                self.detected_devices.append(dev)
                    except (json.JSONDecodeError, Exception):
                        pass
            else:
                patterns = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*"]
                import glob
                for pattern in patterns:
                    for port in glob.glob(pattern):
                        if os.access(port, os.R_OK):
                            dev = DeviceInfo()
                            dev.method = "serial"
                            dev.connection = port
                            dev.vendor_name = "Serial Device"
                            dev.product_name = port
                            dev.mode = "bootloader"
                            self.detected_devices.append(dev)
        except Exception:
            pass

    def _classify_mode(self, vid: int, pid: int) -> str:
        """Klasifikasikan mode device berdasarkan VID/PID"""
        # iPhone modes
        if vid == 0x05AC:
            if pid in [0x1220, 0x1222, 0x1227, 0x1280, 0x1290, 0x12A0, 0x12A2, 0x12A8, 0x12AA, 0x12AC]:
                return "dfu"
            if pid in [0x1210, 0x1211, 0x1281, 0x1291]:
                return "recovery"

        # Qualcomm EDL
        if vid == 0x05C6 and pid == 0x9008:
            return "edl"

        # MediaTek BROM
        if vid == 0x0E8D and pid in [0x0003, 0x2000]:
            return "brom"

        # STM32 DFU
        if vid == 0x0483 and pid == 0xDF11:
            return "dfu"

        return "normal"

    def monitor_mode(self, interval: float = 2.0):
        """Monitor device connection in real-time"""
        log.header("[DEVICE MONITOR - REAL TIME]")
        log.info("Memantau koneksi device... (CTRL+C untuk stop)")
        print(f"  {Colors.DIM}Interval: {interval}s | Mode: {self.os_name}{Colors.RESET}")
        print()

        previous_devices: List[str] = []
        try:
            while True:
                time.sleep(2)
                current = self.scan_all()
                current_ids = [str(d) for d in current]

                # Deteksi perubahan
                new_devices = [d for d in current_ids if d not in previous_devices]
                removed = [d for d in previous_devices if d not in current_ids]

                if new_devices:
                    print(f"\n  {Colors.GREEN}[CONNECTED]{Colors.RESET}")
                    for d in new_devices:
                        print(f"    + {d}")
                        log.success(f"Device terhubung: {d}")

                if removed:
                    print(f"\n  {Colors.RED}[DISCONNECTED]{Colors.RESET}")
                    for d in removed:
                        print(f"    - {d}")
                        log.warning(f"Device terputus: {d}")

                previous_devices = current_ids

                if not current:
                    print(f"\r  {Colors.DIM}Menunggu device...{Colors.RESET}", end="")

                time.sleep(interval)

        except KeyboardInterrupt:
            print()
            log.info("Monitor dihentikan")

    def get_first_device(self) -> Optional[DeviceInfo]:
        """Dapatkan device pertama yang terdeteksi"""
        if not self.detected_devices:
            self.scan_all()
        return self.detected_devices[0] if self.detected_devices else None

    def show_device_info(self):
        """Tampilkan info device yang terdeteksi"""
        self.scan_all()

        if not self.detected_devices:
            return

        print()
        log.info("Detail Perangkat:")
        for i, dev in enumerate(self.detected_devices, 1):
            print(f"\n  {Colors.BOLD}{Colors.CYAN}=== Device #{i} ==={Colors.RESET}")
            for key, val in dev.to_dict().items():
                if val:
                    label = key.replace('_', ' ').title()
                    print(f"  {Colors.DIM}{label}:{Colors.RESET} {val}")


def run():
    """Jalankan Device Detector - scan all"""
    detector = DeviceDetector()
    detector.scan_all()

def run_detail():
    """Jalankan Device Detector - show detail"""
    detector = DeviceDetector()
    detector.show_device_info()


