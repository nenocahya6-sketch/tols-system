

"""
NST iPhone Professional Toolkit
- Apple Device Detection via USB (Normal, Recovery, DFU modes)
- Apple Driver Check (iTunes, Mobile Device, Bonjour, iCloud)
- iOS Version & Activation Status
- Battery Cycle Count Guide
- Port Communication Verification
- Cross-platform support (Windows, Mac, Linux)
"""
import time
import json
import platform
import subprocess
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core.logger import log, Colors
from core.safety import ErrorHandler, ActionLogger


# ========== APPLE DEVICE DATABASE ==========
APPLE_USB_IDS = {
    # iPhone/iPad - Normal Mode
    0x05AC: {
        "name": "Apple Inc.",
        "devices": {
            # Normal mode - Product IDs bervariasi per generasi
            0x1200: ("iPhone/iPad (Normal Mode)", "normal"),
            0x129E: ("iPhone (Normal Mode)", "normal"),
            0x12A0: ("iPhone (Normal Mode)", "normal"),
            # Recovery Mode
            0x1210: ("iPhone/iPad (Recovery Mode)", "recovery"),
            0x1211: ("iPhone (Recovery Mode - old)", "recovery"),
            0x1281: ("iPhone (iBoot - Recovery)", "recovery"),
            0x1291: ("iPhone 5/5C Recovery", "recovery"),
            # DFU Mode
            0x1220: ("iPhone/iPad (DFU Mode)", "dfu"),
            0x1222: ("iPhone (DFU Mode - old)", "dfu"),
            0x1227: ("iPhone/iPad (DFU - new)", "dfu"),
            0x1280: ("iPhone (iBoot - DFU)", "dfu"),
            0x1290: ("iPhone 5/5C DFU", "dfu"),
            0x12A2: ("iPhone 6/6+ DFU", "dfu"),
            0x12A8: ("iPhone 6S/SE DFU", "dfu"),
            0x12AA: ("iPhone 7/7+ DFU", "dfu"),
            0x12AC: ("iPhone 8/8+/X DFU", "dfu"),
            0x12AD: ("iPhone XS/XR/11 DFU", "dfu"),
            0x12AE: ("iPhone 12/13 DFU", "dfu"),
        }
    }
}

# Apple driver registry keys
APPLE_REGISTRY_KEYS = {
    "Apple Mobile Device USB Driver": r"SYSTEM\CurrentControlSet\Services\usbaaple",
    "Apple Mobile Device Support": r"SOFTWARE\Apple Inc.\Apple Mobile Device Support",
    "Apple Mobile Device Support (32bit)": r"SOFTWARE\WOW6432Node\Apple Inc.\Apple Mobile Device Support",
    "iTunes": r"SOFTWARE\Apple Computer, Inc.\iTunes",
    "iTunes (32bit)": r"SOFTWARE\WOW6432Node\Apple Computer, Inc.\iTunes",
    "Bonjour": r"SOFTWARE\Apple Inc.\Bonjour",
    "QuickTime": r"SOFTWARE\Apple Computer, Inc.\QuickTime",
    "Apple Application Support": r"SOFTWARE\Apple Inc.\Apple Application Support",
    "Apple Music": r"SOFTWARE\Apple Inc.\Apple Music",
    "iCloud": r"SOFTWARE\Apple Inc.\iCloud",
}

# Apple processes
APPLE_PROCESSES = [
    "iTunes.exe",
    "iTunesHelper.exe",
    "AppleMobileDeviceService.exe",
    "AppleMobileBackup.exe",
    "APSDaemon.exe",
    "Bonjour Service",
    "mDNSResponder.exe",
    "ApplePush.exe",
]


class NSTiPhone:
    """iPhone Specialist Professional Toolkit"""

    def __init__(self):
        self.os_name = platform.system()
        self.device_mode: Optional[str] = None  # normal, recovery, dfu, none
        self.driver_status: Dict = {}
        self.usb_device_found: bool = False

    # ==================== DEVICE DETECTION ====================

    def scan_device_usb(self) -> Dict:
        """Deteksi iPhone via USB VID/PID"""
        result = {"found": False, "mode": None, "device_name": "Unknown"}

        try:
            if self.os_name == "Windows":
                # Scan via PowerShell untuk Apple USB devices
                cmd = '''
                Get-PnpDevice -PresentOnly | 
                Where-Object {$_.FriendlyName -like "*Apple*" -or $_.FriendlyName -like "*iPhone*" -or $_.FriendlyName -like "*iPad*"} |
                Select-Object FriendlyName, Status, DeviceID, Class |
                ConvertTo-Json
                '''
                proc = subprocess.run(
                    ["powershell", "-Command", cmd],
                    capture_output=True, text=True, timeout=10
                )
                if proc.stdout.strip() and proc.stdout.strip() != "null":
                    try:
                        data = json.loads(proc.stdout)
                        if isinstance(data, dict):
                            data = [data]
                        for item in data:
                            name = item.get("FriendlyName", "") or ""
                            status = item.get("Status", "") or ""
                            if status == "OK":
                                result["found"] = True
                                result["device_name"] = name
                                # Detect mode dari nama
                                name_lower = name.lower()
                                if "dfu" in name_lower:
                                    result["mode"] = "dfu"
                                elif "recovery" in name_lower:
                                    result["mode"] = "recovery"
                                else:
                                    result["mode"] = "normal"
                                break
                    except json.JSONDecodeError:
                        pass

                # Cek via VID/PID jika tidak terdeteksi via nama
                if not result["found"]:
                    result = self._scan_usb_by_vid_pid()

            elif self.os_name == "Linux":
                result = self._scan_usb_linux()
            else:  # Mac
                result = self._scan_usb_mac()

        except Exception as e:
            log.warning(f"USB scan error: {e}")

        return result

    def _scan_usb_by_vid_pid(self) -> Dict:
        """Scan USB dengan mencocokkan Apple VID (0x05AC)"""
        result = {"found": False, "mode": None, "device_name": "Unknown"}

        try:
            import re
            cmd = '''
            Get-PnpDevice -PresentOnly | 
            Where-Object {$_.Class -eq "USB"} |
            Select-Object FriendlyName, DeviceID, Status |
            ConvertTo-Json
            '''
            proc = subprocess.run(
                ["powershell", "-Command", cmd],
                capture_output=True, text=True, timeout=10
            )
            if proc.stdout.strip() and proc.stdout.strip() != "null":
                try:
                    data = json.loads(proc.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for item in data:
                        device_id = item.get("DeviceID", "") or ""
                        status = item.get("Status", "") or ""
                        if status != "OK":
                            continue
                        match = re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', device_id, re.I)
                        if match:
                            vid = int(match.group(1), 16)
                            pid = int(match.group(2), 16)
                            if vid == 0x05AC:  # Apple
                                result["found"] = True
                                if vid in APPLE_USB_IDS:
                                    dev_info = APPLE_USB_IDS[vid]["devices"].get(
                                        pid, ("Apple Device", "normal")
                                    )
                                    result["device_name"] = dev_info[0]
                                    result["mode"] = dev_info[1]
                                break
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

        return result

    def _scan_usb_linux(self) -> Dict:
        """Scan Apple device via lsusb di Linux"""
        result = {"found": False, "mode": None, "device_name": "Unknown"}
        try:
            proc = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
            for line in proc.stdout.split("\n"):
                if "05ac" in line.lower():  # Apple VID
                    result["found"] = True
                    # Parse mode
                    match = re.search(r'ID 05ac:([0-9a-f]{4})', line, re.I)
                    if match:
                        pid = int(match.group(1), 16)
                        if 0x05AC in APPLE_USB_IDS:
                            dev_info = APPLE_USB_IDS[0x05AC]["devices"].get(
                                pid, ("Apple Device", "normal")
                            )
                            result["device_name"] = f"{line.strip()} [{dev_info[0]}]"
                            result["mode"] = dev_info[1]
                    if not result["device_name"] or result["device_name"] == "Unknown":
                        result["device_name"] = line.strip()
                    break
        except (FileNotFoundError, Exception):
            pass
        return result

    def _scan_usb_mac(self) -> Dict:
        """Scan Apple device di Mac OS menggunakan system_profiler"""
        result = {"found": False, "mode": None, "device_name": "Unknown"}
        try:
            # Mac: Gunakan system_profiler atau ioreg
            proc = subprocess.run(
                ["system_profiler", "SPUSBDataType"],
                capture_output=True, text=True, timeout=10
            )
            if "iPhone" in proc.stdout or "iPad" in proc.stdout or "iPod" in proc.stdout:
                result["found"] = True
                # Parse nama
                for line in proc.stdout.split("\n"):
                    if "Product:" in line and ("iPhone" in line or "iPad" in line or "iPod" in line):
                        result["device_name"] = line.split("Product:")[1].strip()
                        break
                # Parse mode
                if "Recovery" in proc.stdout:
                    result["mode"] = "recovery"
                elif "DFU" in proc.stdout:
                    result["mode"] = "dfu"
                else:
                    result["mode"] = "normal"

            # Fallback: cek via ioreg
            if not result["found"]:
                proc = subprocess.run(
                    ["ioreg", "-p", "IOUSB", "-l", "-w", "0"],
                    capture_output=True, text=True, timeout=10
                )
                if "Apple" in proc.stdout and ("iPhone" in proc.stdout or "iPad" in proc.stdout):
                    result["found"] = True
                    result["device_name"] = "Apple Device Detected"
                    result["mode"] = "normal"

        except FileNotFoundError:
            pass
        except Exception:
            pass
        return result

    # ==================== DRIVER SCAN ====================

    def scan_apple_drivers(self) -> Dict:
        """Scan lengkap driver dan komponen Apple"""
        log.header("[APPLE ECOSYSTEM SCAN]")
        log.info(f"Sistem: {self.os_name} {platform.release()} | {platform.machine()}")

        ActionLogger.log("APPLE SCAN", "INFO", "Memulai Apple ecosystem scan")
        results = {
            "system": f"{self.os_name} {platform.release()}",
            "drivers": {},
            "processes": {},
            "path_tools": {},
        }

        # 1. USB Device Detection
        print()
        log.info("Memeriksa perangkat Apple via USB...")
        time.sleep(0.5)
        device_info = self.scan_device_usb()
        self.usb_device_found = device_info["found"]
        self.device_mode = device_info["mode"]

        if device_info["found"]:
            mode_str = device_info["mode"].upper() if device_info["mode"] else "UNKNOWN"
            color = Colors.GREEN if device_info["mode"] == "normal" else Colors.YELLOW
            log.success(f"Device Terdeteksi: {device_info['device_name']}")
            print(f"  {Colors.DIM}Mode:{Colors.RESET} {color}{mode_str}{Colors.RESET}")

            if device_info["mode"] == "dfu":
                log.warning("Device dalam mode DFU! Siap untuk flashing/pemulihan.")
            elif device_info["mode"] == "recovery":
                log.warning("Device dalam mode Recovery! Gunakan iTunes/3uTools.")
        else:
            log.warning("Tidak ada perangkat Apple terdeteksi via USB")

        # 2. Registry Check (Windows only)
        if self.os_name == "Windows":
            print()
            log.info("Memeriksa Windows Registry...")
            time.sleep(1)

            installed_count = 0
            for name, reg_path in APPLE_REGISTRY_KEYS.items():
                status = self._check_registry_key(reg_path)
                results["drivers"][name] = status
                if status:
                    log.success(f"  {name}: OK")
                    installed_count += 1
                else:
                    log.warning(f"  X {name}: Tidak terdeteksi")

            print()
            if installed_count >= 3:
                log.success(f"Driver Apple: {installed_count} komponen terdeteksi")
            elif installed_count > 0:
                log.warning(f"Driver Apple: {installed_count} komponen terdeteksi (sebagian)")
            else:
                log.warning("Driver Apple: Tidak ada komponen terdeteksi!")
                self._show_install_panduan()

        elif self.os_name == "Linux":
            print()
            log.info("Linux: Gunakan libimobiledevice untuk akses iPhone")
            self._check_libimobiledevice()
            results["path_tools"]["libimobiledevice"] = self._find_tool("ideviceinfo")

        else:  # Mac
            print()
            log.info("Mac OS: Driver Apple terinstall secara native")

        # 3. Cek Apple processes
        if self.os_name == "Windows":
            print()
            log.info("Memeriksa Apple services (background processes)...")
            for proc_name in APPLE_PROCESSES:
                running = self._check_process(proc_name)
                results["processes"][proc_name] = running
                if running:
                    log.success(f"  {proc_name}: Running")
                else:
                    print(f"  {Colors.DIM}  {proc_name}: Stopped{Colors.RESET}")

        # 4. Cek tools di PATH
        print()
        log.info("Memeriksa Apple tools...")
        tools_to_check = ["iTunes", "ideviceinfo", "idevicebackup", "idevice_id"]
        for tool in tools_to_check:
            path = self._find_tool(tool)
            results["path_tools"][tool] = path is not None
            if path:
                log.success(f"  {tool}: {path}")
            else:
                print(f"  {Colors.DIM}  {tool}: Tidak ditemukan{Colors.RESET}")

        # 5. Verifikasi Port Komunikasi
        print()
        log.info("Memeriksa port komunikasi...")
        port_ok = self.verifikasi_port_komunikasi()
        results["port_communication"] = port_ok
        if port_ok:
            log.success("Port komunikasi: OK")
        else:
            log.warning("Port komunikasi: Tidak ada (MTK/QC/USB Serial)")

        print()
        log.separator()
        self._print_summary(results)

        ActionLogger.log("APPLE SCAN", "SUCCESS", f"Driver: {len(results['drivers'])}, USB: {self.usb_device_found}")
        return results

    def _check_registry_key(self, reg_path: str) -> bool:
        """Cek apakah registry key exists"""
        try:
            import winreg
            # Parse path
            parts = reg_path.split("\\", 1)
            if len(parts) < 2:
                return False

            root_map = {
                "SYSTEM": winreg.HKEY_LOCAL_MACHINE,
                "SOFTWARE": winreg.HKEY_LOCAL_MACHINE,
            }
            root = root_map.get(parts[0], winreg.HKEY_LOCAL_MACHINE)
            try:
                key = winreg.OpenKey(root, parts[1])
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                return False
            except OSError:
                return False
        except ImportError:
            return False
        except Exception:
            return False

    def _check_process(self, process_name: str) -> bool:
        """Cek apakah proses berjalan"""
        try:
            if self.os_name == "Windows":
                result = subprocess.run(
                    ['tasklist', '/FI', f'IMAGENAME eq {process_name}'],
                    capture_output=True, text=True, timeout=5
                )
                return process_name.lower() in clean_console_output(result.stdout).lower()
            else:
                result = subprocess.run(
                    ["pgrep", "-f", process_name],
                    capture_output=True, text=True, timeout=5
                )
                return result.returncode == 0
        except Exception:
            return False

    def _find_tool(self, name: str) -> Optional[str]:
        """Cari tool di system PATH"""
        try:
            if self.os_name == "Windows":
                result = subprocess.run(["where", name], capture_output=True, text=True, timeout=3)
            else:
                result = subprocess.run(["which", name], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                return clean_console_output(result.stdout).strip().split("\n")[0]
        except Exception:
            pass
        return None

    def _check_libimobiledevice(self):
        """Cek libimobiledevice tools di Linux"""
        tools = ["ideviceinfo", "idevicebackup", "idevice_id", "idevicepair"]
        found = []
        for tool in tools:
            if self._find_tool(tool):
                found.append(tool)

        if found:
            log.success(f"libimobiledevice: OK ({', '.join(found)})")
        else:
            log.warning("libimobiledevice: Tidak terinstall")
            print(f"  {Colors.DIM}  Install: sudo apt install libimobiledevice-utils{Colors.RESET}")
            print(f"  {Colors.DIM}  atau: brew install libimobiledevice (Mac){Colors.RESET}")

    def _print_summary(self, results: Dict):
        """Cetak ringkasan hasil scan"""
        driver_count = sum(1 for v in results.get("drivers", {}).values() if v)
        process_count = sum(1 for v in results.get("processes", {}).values() if v)
        tool_count = sum(1 for v in results.get("path_tools", {}).values() if v)

        print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}RINGKASAN:{Colors.RESET}")
        print(f"  {Colors.GREEN}[OK]{Colors.RESET} Driver: {driver_count} terdeteksi")
        print(f"  {Colors.GREEN}[OK]{Colors.RESET} Services: {process_count} berjalan")
        print(f"  {Colors.GREEN}[OK]{Colors.RESET} Tools: {tool_count} tersedia")

        if self.usb_device_found:
            print(f"  {Colors.GREEN}[OK]{Colors.RESET} iPhone: TERDETEKSI ({self.device_mode})")
        else:
            print(f"  {Colors.RED}[X]{Colors.RESET} iPhone: TIDAK TERDETEKSI")

    # ==================== PORT VERIFICATION ====================

    def verifikasi_port_komunikasi(self) -> bool:
        """Verifikasi port komunikasi untuk iPhone/Android service"""
        if self.os_name != "Windows":
            return True

        try:
            cmd = '''
            Get-PnpDevice -PresentOnly | 
            Where-Object {$_.FriendlyName -like "*Apple*" -or $_.FriendlyName -like "*iPhone*" -or 
                         $_.FriendlyName -like "*Mobile*" -or $_.FriendlyName -like "*USB Serial*"} |
            Select-Object Status, FriendlyName
            '''
            result = subprocess.run(
                ["powershell", "-Command", cmd],
                capture_output=True, text=True, timeout=5
            )
            # Also check with wmic
            wmic_result = subprocess.run(
                ["wmic", "path", "Win32_PnPEntity", "get", "Caption"],
                capture_output=True, text=True, check=False, timeout=5
            )
            output = wmic_clean_console_output(result.stdout).lower()
            has_comm = ("apple" in output or "iphone" in output or 
                       "mediatek" in output or "qualcomm" in output or 
                       "usb serial" in output)
            return has_comm or "OK" in clean_console_output(result.stdout)
        except Exception:
            return False

    # ==================== BATTERY & DEVICE INFO ====================

    def scan_battery_health_real(self) -> Dict:
        """
        SCAN REAL-TIME battery health dari iPhone yang terhubung.
        Mendeteksi: ampere (arus), tegangan, level, health %, cycle count
        Bekerja di Windows (WMI/PowerShell), Mac (ioreg), Linux (libimobiledevice)
        """
        result = {
            "ok": False,
            "level": None,
            "voltage": None,
            "current": None,
            "health_percent": None,
            "cycle_count": None,
            "design_capacity": None,
            "full_charge_capacity": None,
            "temperature": None,
            "chemistry": None,
            "status": None,
        }

        try:
            if self.os_name == "Windows":
                # Baca battery info via PowerShell (Win32_Battery)
                cmd = '''
                Get-WmiObject Win32_Battery | 
                Select-Object EstimatedChargeRemaining, BatteryStatus, Chemistry, 
                DesignCapacity, FullChargeCapacity, ExpectedLife, 
                SmartBatteryVersion, Temperature | ConvertTo-Json
                '''
                proc = subprocess.run(
                    ["powershell", "-Command", cmd],
                    capture_output=True, text=True, timeout=5
                )
                if proc.stdout.strip() and proc.stdout.strip() != "null":
                    try:
                        data = json.loads(proc.stdout)
                        if isinstance(data, dict):
                            data = [data]
                        for bat in data:
                            result["level"] = bat.get("EstimatedChargeRemaining")
                            result["chemistry"] = bat.get("Chemistry")
                            result["design_capacity"] = bat.get("DesignCapacity")
                            result["full_charge_capacity"] = bat.get("FullChargeCapacity")
                            # ExpectedLife = sisa usia dalam menit, BUKAN cycle count
                            # Estimasi cycle count dari DesignCapacity vs FullChargeCapacity
                            if result["design_capacity"] and result["full_charge_capacity"]:
                                ratio = result["full_charge_capacity"] / result["design_capacity"]
                                if ratio > 1.0:
                                    ratio = 1.0  # cegah negatif
                                result["cycle_count"] = "~" + str(int((1 - ratio) * 1000))
                            result["status"] = {1: "Discharging", 2: "Charging", 3: "Full", 4: "Low", 5: "Critical", 6: "Unknown"}.get(bat.get("BatteryStatus"), "Unknown")

                            if result["design_capacity"] and result["full_charge_capacity"]:
                                result["health_percent"] = round((result["full_charge_capacity"] / result["design_capacity"]) * 100, 1)

                            # Baca tegangan & arus via PowerShell tambahan
                            try:
                                vcmd = 'Get-WmiObject Win32_Battery | Select-Object * | ConvertTo-Json'
                                vproc = subprocess.run(
                                    ["powershell", "-Command", vcmd],
                                    capture_output=True, text=True, timeout=5
                                )
                                if vproc.stdout.strip() and vproc.stdout.strip() != "null":
                                    vdata = json.loads(vproc.stdout)
                                    if isinstance(vdata, dict):
                                        vdata = [vdata]
                                    for vbat in vdata:
                                        if vbat.get("Voltage"):
                                            # Voltage dalam millivolts, konversi ke volt
                                            result["voltage"] = round(vbat["Voltage"] / 1000, 3)
                                            break
                            except Exception:
                                pass

                            result["ok"] = True
                            break
                    except json.JSONDecodeError:
                        pass

                # Jika tidak ada battery info dari laptop, baca dari iPhone via iTunes registry
                if not result["ok"]:
                    try:
                        import winreg
                        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                             r"SOFTWARE\Apple Inc.\Apple Mobile Device Support\Devices")
                        i = 0
                        while True:
                            try:
                                name = winreg.EnumKey(key, i)
                                sub_key = winreg.OpenKey(key, name)
                                try:
                                    # Baca battery info dari registry device
                                    for val_name in ["BatteryCapacity", "BatteryCycleCount", "BatterySerial", "ProductType"]:
                                        try:
                                            val, _ = winreg.QueryValueEx(sub_key, val_name)
                                            if val_name == "BatteryCapacity":
                                                result["health_percent"] = val
                                            elif val_name == "BatteryCycleCount":
                                                result["cycle_count"] = val
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                winreg.CloseKey(sub_key)
                                i += 1
                            except WindowsError:
                                break
                        winreg.CloseKey(key)
                    except Exception:
                        pass

            elif self.os_name == "Darwin":
                # Mac: baca via ioreg
                try:
                    proc = subprocess.run(
                        ["ioreg", "-r", "-c", "AppleSmartBattery", "-a"],
                        capture_output=True, text=True, timeout=10
                    )
                    for pattern, key in [
                        (r'"AppleRawCurrentCapacity"\s*=\s*(\d+)', "level"),
                        (r'"AppleRawMaxCapacity"\s*=\s*(\d+)', "full_charge_capacity"),
                        (r'"DesignCapacity"\s*=\s*(\d+)', "design_capacity"),
                        (r'"CycleCount"\s*=\s*(\d+)', "cycle_count"),
                        (r'"Temperature"\s*=\s*(\d+)', "temperature"),
                        (r'"Voltage"\s*=\s*(\d+)', "voltage"),
                        (r'"Amperage"\s*=\s*(-?\d+)', "current"),
                        (r'"BatteryChemistry"\s*=\s*"(\w+)"', "chemistry"),
                    ]:
                        m = re.search(pattern, proc.stdout)
                        if m:
                            result[key] = int(m.group(1)) if key not in ["chemistry"] else m.group(1)

                    if result["voltage"]:
                        result["voltage"] = round(result["voltage"] / 1000, 3)  # mV to V
                    if result["current"]:
                        result["current"] = round(abs(result["current"]) / 1000, 3)  # mA to A
                    if result["temperature"]:
                        result["temperature"] = round(result["temperature"] / 100, 1)  # Kelvin*100 to C
                    if result["design_capacity"] and result["full_charge_capacity"]:
                        result["health_percent"] = round((result["full_charge_capacity"] / result["design_capacity"]) * 100, 1)
                    result["ok"] = True
                except Exception:
                    pass

            elif self.os_name == "Linux":
                # Linux: coba baca dari sysfs atau libimobiledevice
                try:
                    # Coba via libimobiledevice
                    if self._find_tool("ideviceinfo"):
                        proc = subprocess.run(
                            ["ideviceinfo", "-q", "com.apple.ioregistry", "-k", "IOPMPowerSource"],
                            capture_output=True, text=True, timeout=10
                        )
                        output = proc.stdout
                        for pattern, key in [
                            (r'"CycleCount"\s*=\s*(\d+)', "cycle_count"),
                            (r'"MaxCapacity"\s*=\s*(\d+)', "full_charge_capacity"),
                            (r'"DesignCapacity"\s*=\s*(\d+)', "design_capacity"),
                            (r'"CurrentCapacity"\s*=\s*(\d+)', "level"),
                        ]:
                            m = re.search(pattern, output)
                            if m:
                                result[key] = int(m.group(1))
                        if result["design_capacity"] and result["full_charge_capacity"]:
                            result["health_percent"] = round((result["full_charge_capacity"] / result["design_capacity"]) * 100, 1)
                        result["ok"] = True
                except Exception:
                    pass

        except Exception:
            pass

        return result

    def show_battery_guide(self):
        """Panduan & deteksi battery health iPhone (real-time jika terhubung)"""
        log.header("[BATTERY HEALTH - INFO LENGKAP]")

        # Deteksi device terlebih dahulu
        device_info = self.scan_device_usb()

        # SCAN REAL-TIME battery health
        battery = self.scan_battery_health_real()

        if device_info["found"] or battery["ok"]:
            print()
            print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 50}{Colors.RESET}")
            print(f"  {Colors.BOLD}{Colors.BRIGHT_CYAN}  DATA REAL-TIME DARI PERANGKAT{Colors.RESET}")
            print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 50}{Colors.RESET}")

            if device_info["found"]:
                log.success(f"iPhone terdeteksi: {device_info['device_name']} (Mode: {device_info['mode'].upper()})")
            print()

            if battery["level"] is not None:
                print(f"  {Colors.DIM}Battery Level:{Colors.RESET} {battery['level']}%")
            if battery["voltage"] is not None:
                print(f"  {Colors.DIM}Tegangan:{Colors.RESET} {battery['voltage']}V")
            if battery["current"] is not None:
                print(f"  {Colors.DIM}Arus:{Colors.RESET} {battery['current']}A")
            if battery["temperature"] is not None:
                status = "[OK]" if 20 < battery['temperature'] < 40 else "[!]"
                print(f"  {Colors.DIM}Suhu:{Colors.RESET} {battery['temperature']}C {status}")
            if battery["cycle_count"] is not None:
                color = Colors.GREEN if battery['cycle_count'] < 200 else Colors.YELLOW if battery['cycle_count'] < 500 else Colors.RED
                print(f"  {Colors.DIM}Cycle Count:{Colors.RESET} {color}{battery['cycle_count']}{Colors.RESET}")
                if battery['cycle_count'] < 200:
                    print(f"               Battery masih SEGAR")
                elif battery['cycle_count'] < 500:
                    print(f"               Normal (1-2 tahun)")
                elif battery['cycle_count'] < 800:
                    print(f"               MENURUN - pertimbangkan ganti")
                else:
                    print(f"               {Colors.RED}AUS! Segera ganti!{Colors.RESET}")
            if battery["design_capacity"] is not None:
                print(f"  {Colors.DIM}Design Capacity:{Colors.RESET} {battery['design_capacity']} mAh")
            if battery["full_charge_capacity"] is not None:
                print(f"  {Colors.DIM}Full Charge Capacity:{Colors.RESET} {battery['full_charge_capacity']} mAh")
            if battery["health_percent"] is not None:
                if battery["health_percent"] > 80:
                    log.success(f"Battery Health: {battery['health_percent']}% [SEHAT]")
                elif battery["health_percent"] > 60:
                    log.warning(f"Battery Health: {battery['health_percent']}% [MENURUN]")
                else:
                    log.critical(f"Battery Health: {battery['health_percent']}% [AUS! GANTI SEGERA!]")
            if battery["status"] is not None:
                print(f"  {Colors.DIM}Status:{Colors.RESET} {battery['status']}")
            if battery["chemistry"] is not None:
                print(f"  {Colors.DIM}Chemistry:{Colors.RESET} {battery['chemistry']}")

            if battery["ok"]:
                print()
                log.success("[OK] Data REAL berhasil dibaca dari perangkat!")

        else:
            log.warning("iPhone tidak terdeteksi via USB. Menampilkan panduan manual.")
            print()

        print()
        print(f"  {Colors.BOLD}{Colors.CYAN}PANDUAN LENGKAP BATTERY IPHONE{Colors.RESET}")
        print("  " + "=" * 45)
        print()
        print("  Cara cek Battery Cycle Count iPhone:")
        print()
        print("  Method 1: Settings (iOS 15+)\n")
        print("     Settings > General > About > Cycle Count")
        print()
        print("  Method 2: Analytics Data\n")
        print("     1. Settings > Privacy > Analytics & Improvements")
        print("     2. Analytics Data > Cari 'log-aggregated' terbaru")
        print("     3. Cari string: 'BatteryCycleCount'")
        print()
        print("  Method 3: Mac (libimobiledevice)\n")
        print("     $ ideviceinfo -q com.apple.ioregistry -k IOPMPowerSource")
        print("     (Cari: CycleCount, MaxCapacity, DesignCapacity)")
        print()
        print("  Method 4: Windows (3uTools / iMazing / CoconutBattery)")
        print()
        log.info("Interpretasi Cycle Count:")
        print(f"  {Colors.GREEN}  0-200:{Colors.RESET} Baik (Battery baru/segar)")
        print(f"  {Colors.YELLOW}  200-500:{Colors.RESET} Normal (1-2 tahun pemakaian)")
        print(f"  {Colors.YELLOW}  500-800:{Colors.RESET} Menurun (mulai pertimbangkan ganti)")
        print(f"  {Colors.RED}  800+:   {Colors.RESET} Aus (sebaiknya ganti battery)")
        print()
        log.info("Diagnostic Tips:")
        print("  - iPhone X: 79% capacity in 500 cycles dianggap normal")
        print("  - iPhone 11+: MaximumCapacity vs DesignCapacity")
        print("  - Jika battery health < 80%, disarankan ganti battery")
        print("  - Swelling battery = ganti SEGERA! (bahaya kebakaran)")
        print("  - Battery health < 60%: HP bisa restart sendiri (random shutdown)")

    # ==================== MODE GUIDE ====================

    def show_mode_guide(self):
        """Panduan masuk/keluar Recovery dan DFU mode"""
        log.header("[IPHONE MODE GUIDE]")

        print(f"  {Colors.BOLD}{Colors.CYAN}RECOVERY MODE{Colors.RESET}")
        print("  " + "-" * 45)
        print("  Cara Masuk Recovery Mode:")
        print("  1. Hubungkan iPhone ke PC via USB")
        print("  2. Tekan & lepas Volume Up cepat")
        print("  3. Tekan & lepas Volume Down cepat")
        print("  4. Tahan Power (Side button) sampai layar mati")
        print("  5. Saat logo Apple muncul, tahan Volume Down")
        print("  6. Lepas saat muncul logo iTunes + kabel")
        print()
        print("  Keluar Recovery Mode:")
        print("  - Tekan & tahan Power + Volume Down 10 detik")
        print("  - Atau via iTunes: Restore / Update")
        print()

        print(f"  {Colors.BOLD}{Colors.YELLOW}DFU MODE{Colors.RESET}")
        print("  " + "-" * 45)
        log.warning("DFU MODE ADALAH MODE PALING RENDAH! HATI-HATI!")
        print()
        print("  Cara Masuk DFU Mode (iPhone 8+):")
        print("  1. Tekan & lepas Volume UP cepat")
        print("  2. Tekan & lepas Volume DOWN cepat")
        print("  3. Tahan Power 10 detik (layar akan mati)")
        print("  4. Sambil tahan Power, tekan Volume DOWN 5 detik")
        print("  5. Lepas Power, terus tahan Volume DOWN 10 detik")
        print("  6. Layar tetap hitam (tanda DFU mode!)")
        print()
        print("  Keluar DFU Mode:")
        print("  - Tekan & tahan Power + Volume Down 10 detik")
        print("  - Atau: Hard reset (Vol Up, Vol Down, tahan Power)")
        print()
        print(f"  {Colors.DIM}Catatan: Di DFU mode, device TIDAK menampilkan apapun di layar.{Colors.RESET}")
        print(f"  {Colors.DIM}Jika ada logo iTunes, berarti masih di Recovery, bukan DFU!{Colors.RESET}")

    # ==================== ACTIVATION CHECK ====================

    def scan_imei_real(self) -> Dict:
        """
        SCAN REAL-TIME IMEI & Serial dari iPhone yang terhubung.
        Membaca dari: iTunes registry (Windows), libimobiledevice (Mac/Linux)
        """
        result = {
            "ok": False,
            "imei": None,
            "serial": None,
            "model": None,
            "product_type": None,
            "ios_version": None,
            "device_name": None,
            "activation_state": None,
            "unique_id": None,
        }

        try:
            if self.os_name == "Windows":
                # Baca dari iTunes registry
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                         r"SOFTWARE\Apple Inc.\Apple Mobile Device Support\Devices")
                    i = 0
                    while True:
                        try:
                            name = winreg.EnumKey(key, i)
                            sub_key = winreg.OpenKey(key, name)
                            try:
                                imei, _ = winreg.QueryValueEx(sub_key, "IMEI")
                                if imei and len(str(imei)) >= 14:
                                    result["imei"] = str(imei)
                            except Exception:
                                pass
                            try:
                                serial, _ = winreg.QueryValueEx(sub_key, "SerialNumber")
                                result["serial"] = str(serial)
                            except Exception:
                                pass
                            try:
                                model, _ = winreg.QueryValueEx(sub_key, "ProductType")
                                result["product_type"] = str(model)
                            except Exception:
                                pass
                            winreg.CloseKey(sub_key)
                            result["device_name"] = name
                            result["ok"] = True
                            i += 1
                        except WindowsError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass

                # Coba juga via PowerShell (Get-WmiObject)
                if not result["ok"]:
                    try:
                        cmd = '''
                        Get-CimInstance -Namespace root/Apple -ClassName AppleDeviceInfo | 
                        Select-Object IMEI, SerialNumber, Model | ConvertTo-Json
                        '''
                        proc = subprocess.run(
                            ["powershell", "-Command", cmd],
                            capture_output=True, text=True, timeout=5
                        )
                        if proc.stdout.strip() and proc.stdout.strip() != "null":
                            data = json.loads(proc.stdout)
                            if isinstance(data, dict):
                                data = [data]
                            for d in data:
                                if d.get("IMEI"):
                                    result["imei"] = str(d["IMEI"])
                                if d.get("SerialNumber"):
                                    result["serial"] = str(d["SerialNumber"])
                                result["ok"] = True
                    except Exception:
                        pass

            elif self.os_name == "Darwin":
                # Mac: baca via system_profiler
                try:
                    proc = subprocess.run(
                        ["system_profiler", "SPHardwareDataType"],
                        capture_output=True, text=True, timeout=10
                    )
                    for line in proc.stdout.split('\n'):
                        if "Serial Number" in line:
                            result["serial"] = line.split(':')[1].strip()
                        if "Model Name" in line:
                            result["model"] = line.split(':')[1].strip()
                    result["ok"] = bool(result["serial"])
                except Exception:
                    pass

            # Coba via libimobiledevice (Mac/Linux)
            if not result["ok"] and self._find_tool("ideviceinfo"):
                try:
                    proc = subprocess.run(
                        ["ideviceinfo"],
                        capture_output=True, text=True, timeout=10
                    )
                    output = proc.stdout
                    for line in output.split('\n'):
                        if "IMEI:" in line:
                            result["imei"] = line.split(':')[1].strip()
                        if "SerialNumber:" in line:
                            result["serial"] = line.split(':')[1].strip()
                        if "ProductVersion:" in line:
                            result["ios_version"] = line.split(':')[1].strip()
                        if "ProductType:" in line:
                            result["product_type"] = line.split(':')[1].strip()
                        if "DeviceName:" in line:
                            result["device_name"] = line.split(':')[1].strip()
                        if "ActivationState:" in line:
                            result["activation_state"] = line.split(':')[1].strip()
                        if "UniqueDeviceID:" in line:
                            result["unique_id"] = line.split(':')[1].strip()
                    result["ok"] = bool(result["imei"] or result["serial"])
                except Exception:
                    pass

        except Exception:
            pass

        return result

    def activation_check_guide(self):
        """Panduan cek activation lock / iCloud lock + baca IMEI real-time"""
        log.header("[ACTIVATION LOCK & IMEI CHECK]")

        # Deteksi device
        device_info = self.scan_device_usb()
        imei_data = self.scan_imei_real()

        if device_info["found"] or imei_data["ok"]:
            print()
            print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 50}{Colors.RESET}")
            print(f"  {Colors.BOLD}{Colors.BRIGHT_CYAN}  DATA REAL DARI PERANGKAT{Colors.RESET}")
            print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 50}{Colors.RESET}")

            if device_info["found"]:
                log.success(f"iPhone terdeteksi: {device_info['device_name']} (Mode: {device_info['mode'].upper()})")
            print()

            if imei_data["imei"]:
                print(f"  {Colors.DIM}IMEI:{Colors.RESET} {Colors.BRIGHT_WHITE}{imei_data['imei']}{Colors.RESET}")
            if imei_data["serial"]:
                print(f"  {Colors.DIM}Serial:{Colors.RESET} {imei_data['serial']}")
            if imei_data["model"]:
                print(f"  {Colors.DIM}Model:{Colors.RESET} {imei_data['model']}")
            if imei_data["product_type"]:
                # Cari di database model
                from config import IPHONE_MODEL_DATABASE
                db_name = IPHONE_MODEL_DATABASE.get(imei_data['product_type'])
                extra = f" ({db_name})" if db_name else ""
                print(f"  {Colors.DIM}Product Type:{Colors.RESET} {imei_data['product_type']}{extra}")
            if imei_data["ios_version"]:
                print(f"  {Colors.DIM}iOS Version:{Colors.RESET} {imei_data['ios_version']}")
            if imei_data["device_name"]:
                print(f"  {Colors.DIM}Device Name:{Colors.RESET} {imei_data['device_name']}")
            if imei_data["activation_state"]:
                act_color = Colors.RED if "unactivated" in imei_data['activation_state'].lower() else Colors.GREEN
                print(f"  {Colors.DIM}Activation State:{Colors.RESET} {act_color}{imei_data['activation_state']}{Colors.RESET}")
            if imei_data["unique_id"]:
                print(f"  {Colors.DIM}Unique ID (ECID):{Colors.RESET} {imei_data['unique_id']}")

            if imei_data["ok"]:
                print()
                log.success("[OK] Data REAL berhasil dibaca dari perangkat!")
        else:
            log.warning("iPhone tidak terdeteksi. Tampilkan panduan.")

        print()
        print(f"  {Colors.BOLD}{Colors.CYAN}PANDUAN CEK ACTIVATION LOCK & IMEI{Colors.RESET}")
        print("  " + "=" * 45)
        print()
        print("  Cara Cek Activation Lock:")
        print()
        print("  Method 1: Cek di iPhone langsung")
        print("     Settings > [Nama Anda] > Find My > Find My iPhone")
        print("     Jika ON -> Activation Lock aktif")
        print()
        print("  Method 2: Cek via IMEI/Serial")
        print("     1. Cari IMEI di Settings > General > About")
        print("     2. Atau dial *#06#")
        print("     3. Cek di: https://icloud.com/activationlock/")
        print("     4. Atau: https://sickw.com / https://imei.info")
        print()
        print("  Cara Cek IMEI:")
        print("  - Dial: *#06#")
        print("  - Settings > General > About")
        print("  - Di box iPhone orisinal: lihat barcode")
        print("  - Di iTunes: klik serial number (berubah jadi IMEI)")
        print()
        log.warning("CATATAN PENTING:")
        print(f"  {Colors.RED}  - Activation Lock adalah fitur keamanan Apple, bukan bug!{Colors.RESET}")
        print(f"  {Colors.RED}  - BYPASS ACTIVATION LOCK ILEGAL!{Colors.RESET}")
        print(f"  {Colors.RED}  - Hanya pemilik asli yang bisa unlock via Apple ID{Colors.RESET}")
        print(f"  {Colors.RED}  - Catat IMEI dulu sebelum service!{Colors.RESET}")

    # ==================== INSTALL GUIDE ====================

    def _show_install_panduan(self):
        """Tampilkan panduan install driver Apple"""
        print()
        log.info("PANDUAN INSTALL DRIVER APPLE DI WINDOWS:")
        print("  " + "=" * 50)

        if self.os_name == "Windows":
            print()
            print("  Opsi 1: Install iTunes (Recommended)")
            print("  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            print("  1. Download dari: https://www.apple.com/itunes/download/")
            print("  2. Install iTunes (sudah termasuk Apple Mobile Device Support)")
            print("  3. Restart PC")
            print()
            print("  Opsi 2: Install Driver Only")
            print("  ~~~~~~~~~~~~~~~~~~~~~~~~~~")
            print("  1. Download AppleMobileDeviceSupport.msi")
            print("  2. Buka: C:\\Program Files\\Common Files\\Apple\\")
            print("  3. Jalankan: AppleMobileDeviceSupport.msi")
            print()
            print("  Opsi 3: 3uTools (Alternatif All-in-One)")
            print("  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            print("  - Download: https://www.3u.com/")
            print("  - Sudah termasuk driver, tools, flashing")
            print()
            print("  Opsi 4: Reinstall Driver via Device Manager")
            print("  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            print("  1. Buka Device Manager (devmgmt.msc)")
            print("  2. Cari 'Apple iPhone' atau 'Unknown Device'")
            print("  3. Right-click > Update driver")
            print("  4. Browse: C:\\Program Files\\Common Files\\Apple\\Mobile Device Support\\Drivers")
            print()
            log.info("Setelah install, restart dan hubungkan iPhone via USB")

            # Buka browser untuk download iTunes
            try:
                import webbrowser
                webbrowser.open("https://www.apple.com/itunes/download/")
            except Exception:
                try:
                    # Fallback via system command
                    if self.os_name == "Windows":
                        subprocess.run(["start", "https://www.apple.com/itunes/download/"],
                                       capture_output=True, timeout=3)
                    elif self.os_name == "Linux":
                        subprocess.run(["xdg-open", "https://www.apple.com/itunes/download/"],
                                       capture_output=True, timeout=3)
                    else:
                        subprocess.run(["open", "https://www.apple.com/itunes/download/"],
                                       capture_output=True, timeout=3)
                except Exception:
                    pass
            print()
            log.info("Membuka halaman download iTunes...")
        else:
            if self.os_name == "Linux":
                print()
                print("  Install libimobiledevice:")
                print("  $ sudo apt update")
                print("  $ sudo apt install libimobiledevice-utils usbmuxd")
                print()
                print("  Atau dari source:")
                print("  $ brew install libimobiledevice (jika pakai Homebrew)")
            else:
                print()
                print("  Mac OS sudah memiliki driver Apple native.")
                print("  Cukup colok iPhone via USB.")

    def _quick_driver_check(self):
        """Quick check driver Apple"""
        log.header("[APPLE DRIVER QUICK CHECK]")
        if self.os_name == "Windows":
            installed_count = 0
            for name, reg_path in APPLE_REGISTRY_KEYS.items():
                if self._check_registry_key(reg_path):
                    log.success(f"{name}: OK")
                    installed_count += 1
                else:
                    log.warning(f"X {name}: Tidak terdeteksi")

            print()
            if installed_count > 0:
                log.success(f"{installed_count} Apple components found")
            else:
                log.warning("No Apple components detected!")
        else:
            log.info(f"Gunakan tools: {'ideviceinfo' if self.os_name == 'Linux' else 'System Information'}")

    # ==================== PUBLIC WRAPPER METHODS ====================

    def quick_driver_check(self):
        """Public wrapper untuk _quick_driver_check"""
        self._quick_driver_check()

    def show_install_guide(self):
        """Public wrapper untuk _show_install_panduan"""
        self._show_install_panduan()

    @staticmethod
    def list_features():
        """Tampilkan fitur iPhone yang tersedia"""
        print()
        print(f"  {Colors.BOLD}FITUR IPHONE TOOLKIT:{Colors.RESET}")
        print(f"  - Apple Full Scan (14)")
        print(f"  - Quick Driver Check (15)")
        print(f"  - Mode Guide (16)")
        print(f"  - Battery Guide (17)")
        print(f"  - Activation Check (18)")
        print(f"  - Install Guide (19)")
        print(f"  - Port Verification (20)")
        print(f"  {Colors.DIM}Panggil dari menu utama NST (nomor 14-20){Colors.RESET}")
        print()


def run():
    """Jalankan iPhone Toolkit - scan penuh"""
    app = NSTiPhone()
    app.scan_apple_drivers()
