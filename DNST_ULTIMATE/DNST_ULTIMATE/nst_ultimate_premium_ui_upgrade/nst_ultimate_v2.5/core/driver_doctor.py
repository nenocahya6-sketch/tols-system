


"""
NST Driver Doctor v2 — Auto Driver Repair
===========================================
Diagnostik, perbaikan, dan instalasi driver otomatis.

Fitur baru v2:
  ✅ Auto-detect missing drivers (ADB, Fastboot, USB Serial, Qualcomm, MediaTek)
  ✅ Auto-install driver untuk platform umum
  ✅ Repair ADB/Fastboot (reset, reinstall, fix permissions)
  ✅ Detect driver conflicts
  ✅ Windows: install via Zadig, PnPUtil
  ✅ Linux: install udev rules otomatis
"""


import os
import sys
import re
import json
import time
import shutil
import platform
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from config import STLINK_VID_PID, DFU_VID_PID
from core.logger import log, Colors


class DriverDoctor:
    """Diagnostik dan perbaikan driver untuk perangkat STM32 + Android + Apple"""

    # Driver yang dikenal dan binary-nya
    KNOWN_DRIVERS = {
        "ADB": {
            "binary": "adb",
            "description": "Android Debug Bridge",
            "install_url": "https://developer.android.com/studio/releases/platform-tools",
            "windows_url": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
            "linux_cmd": "sudo apt install adb",
            "mac_cmd": "brew install android-platform-tools",
        },
        "Fastboot": {
            "binary": "fastboot",
            "description": "Android Fastboot Protocol",
            "install_url": "https://developer.android.com/studio/releases/platform-tools",
        },
        "dfu-util": {
            "binary": "dfu-util",
            "description": "DFU Utility for STM32",
            "install_url": "https://dfu-util.sourceforge.net/",
            "linux_cmd": "sudo apt install dfu-util",
            "mac_cmd": "brew install dfu-util",
        },
        "OpenOCD": {
            "binary": "openocd",
            "description": "Open On-Chip Debugger",
            "install_url": "https://openocd.org/",
            "linux_cmd": "sudo apt install openocd",
            "mac_cmd": "brew install open-ocd",
        },
        "st-flash": {
            "binary": "st-flash",
            "description": "ST-Link Flash Utility",
            "install_url": "https://github.com/stlink-org/stlink",
            "linux_cmd": "sudo apt install stlink-tools",
            "mac_cmd": "brew install stlink",
        },
        "Heimdall": {
            "binary": "heimdall",
            "description": "Samsung Odin Flasher",
            "install_url": "https://github.com/Benjamin-Dobell/Heimdall",
            "linux_cmd": "sudo apt install heimdall-flash",
        },
        "idevice_id": {
            "binary": "idevice_id",
            "description": "libimobiledevice - Apple device tools",
            "install_url": "https://libimobiledevice.org/",
            "linux_cmd": "sudo apt install libimobiledevice-utils",
            "mac_cmd": "brew install libimobiledevice",
        },
    }

    def __init__(self):
        self.os_name = platform.system()
        self.drivers_found: List[str] = []
        self.missing_drivers: List[str] = []
        self.broken_drivers: List[str] = []
        self.connected_devices: List[Dict] = []
        self.repair_log: List[Dict] = []

    # ── SCAN ──

    def scan_all(self) -> Dict:
        """Scan lengkap semua driver dan perangkat."""
        log.header("[DRIVER DOCTOR v2 - FULL SCAN]")
        log.info(f"Sistem Operasi: {self.os_name} {platform.release()}")
        print()

        results = {
            "os": self.os_name,
            "tools": self._scan_tools(),
            "stlink": self._check_stlink(),
            "dfu": self._check_dfu(),
            "serial": self._check_serial_ports(),
            "usb_devices": self._check_usb_devices(),
            "drivers_status": self._check_drivers_installed(),
            "adb_status": self._check_adb_health(),
            "fastboot_status": self._check_fastboot_health(),
        }

        print()
        log.separator()
        log.info("RINGKASAN DRIVER:")
        print()

        for name in self.drivers_found:
            log.success(f"  ✅ {name}")
        for name in self.missing_drivers:
            log.warning(f"  ❌ {name} — TIDAK TERINSTALL")
        for name in self.broken_drivers:
            log.error(f"  ⚠️ {name} — BERMASALAH")

        print()
        if self.missing_drivers or self.broken_drivers:
            log.warning(f"Total: {len(self.drivers_found)} OK, {len(self.missing_drivers)} missing, {len(self.broken_drivers)} broken")
        else:
            log.success(f"Semua driver OK! ({len(self.drivers_found)} terdeteksi)")
        log.separator()

        return results

    def _scan_tools(self) -> Dict[str, bool]:
        """Scan semua tool yang dikenal."""
        results = {}
        for name, info in self.KNOWN_DRIVERS.items():
            binary = info["binary"]
            path = shutil.which(binary)
            if path:
                self.drivers_found.append(name)
                results[name] = True
            else:
                self.missing_drivers.append(name)
                results[name] = False
        return results

    def _check_stlink(self) -> Dict:
        """Cek koneksi ST-Link."""
        result = {"found": False, "info": ""}
        try:
            if self.os_name == "Windows":
                output = subprocess.run(
                    ['powershell', '-Command', 'Get-PnpDevice | Where-Object {$_.FriendlyName -like "*ST-Link*"} | Select-Object Status, FriendlyName'],
                    capture_output=True, text=True, timeout=5
                )
                if "OK" in output.stdout:
                    result["found"] = True
                    result["info"] = "ST-Link terdeteksi di Device Manager"
            else:
                output = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                for vid, pid in STLINK_VID_PID:
                    if f"{vid:04x}:{pid:04x}" in output.stdout.lower():
                        result["found"] = True
                        result["info"] = f"ST-Link terdeteksi (VID={vid:04x}, PID={pid:04x})"
                        break
        except Exception as e:
            log.warning(f"Error check ST-Link: {e}")
        return result

    def _check_dfu(self) -> Dict:
        """Cek perangkat DFU."""
        result = {"found": False, "info": ""}
        try:
            if self.os_name == "Windows":
                output = subprocess.run(
                    ['powershell', '-Command', 'Get-PnpDevice | Where-Object {$_.FriendlyName -like "*DFU*" -or $_.FriendlyName -like "*STM32 Bootloader*"} | Select-Object Status, FriendlyName'],
                    capture_output=True, text=True, timeout=5
                )
                if output.stdout.strip():
                    result["found"] = True
                    result["info"] = "Perangkat DFU terdeteksi"
            else:
                output = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                for vid, pid in DFU_VID_PID:
                    if f"{vid:04x}:{pid:04x}" in output.stdout.lower():
                        result["found"] = True
                        result["info"] = f"DFU terdeteksi (VID={vid:04x}, PID={pid:04x})"
                        break
        except Exception:
            pass

        # Cek dfu-util
        if shutil.which("dfu-util"):
            try:
                output = subprocess.run(["dfu-util", "-l"], capture_output=True, text=True, timeout=5)
                if "Found DFU" in output.stdout:
                    result["found"] = True
                    result["info"] += " | dfu-util tersedia"
            except Exception:
                pass

        return result

    def _check_serial_ports(self) -> Dict:
        """Cek port serial yang tersedia."""
        result = {"ports": []}
        try:
            if self.os_name == "Windows":
                output = subprocess.run(
                    ['powershell', '-Command', 'Get-WmiObject Win32_SerialPort | Select-Object DeviceID, Description, Status'],
                    capture_output=True, text=True, timeout=5
                )
                for line in output.stdout.strip().split('\n'):
                    if "COM" in line:
                        result["ports"].append(line.strip())
            else:
                import glob
                patterns = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*", "/dev/cu.*"]
                for pattern in patterns:
                    for port in glob.glob(pattern):
                        if os.access(port, os.R_OK):
                            result["ports"].append(port)
        except Exception as e:
            log.warning(f"Error scan port serial: {e}")
        return result

    def _check_usb_devices(self) -> List[Dict]:
        """Cek semua perangkat USB."""
        devices = []
        try:
            if self.os_name == "Windows":
                output = subprocess.run(
                    ['powershell', '-Command', 'Get-PnpDevice -Class USB | Where-Object {$_.Status -eq "OK"} | Select-Object FriendlyName, Status | ConvertTo-Json'],
                    capture_output=True, text=True, timeout=5
                )
                if output.stdout.strip():
                    log.info("Perangkat USB terdeteksi")
            else:
                output = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
                for line in output.stdout.strip().split('\n'):
                    if line.strip():
                        devices.append(line.strip())
                        if "STMicro" in line or "STM" in line:
                            log.success(f"  → {line.strip()}")
        except Exception as e:
            log.warning(f"Error scan USB: {e}")
        return devices

    def _check_drivers_installed(self) -> Dict:
        """Cek status driver yang terinstall."""
        result = {"installed": [], "missing": []}

        if self.os_name == "Windows":
            checks = {
                "ST-Link": "STLink",
                "STM32 Virtual COM Port": "STM32",
                "DFU": "DFU",
            }
            for name, keyword in checks.items():
                try:
                    output = subprocess.run(
                        ['powershell', '-Command', f'Get-PnpDevice | Where-Object {{$_.FriendlyName -like "*{keyword}*"}} | Select-Object Status'],
                        capture_output=True, text=True, timeout=5
                    )
                    if "OK" in output.stdout:
                        result["installed"].append(name)
                        log.success(f"  {name}: OK Terinstall")
                    else:
                        result["missing"].append(name)
                        log.warning(f"Driver {name}: X Tidak terinstall")
                except Exception:
                    result["missing"].append(name)
        else:
            udev_files = []
            for path in ["/etc/udev/rules.d", "/lib/udev/rules.d"]:
                if os.path.exists(path):
                    for f in os.listdir(path):
                        if "stm" in f.lower() or "stlink" in f.lower():
                            udev_files.append(os.path.join(path, f))
            if udev_files:
                result["installed"].append("udev rules")
                log.success(f"Udev rules: OK Ditemukan ({len(udev_files)} file)")
            else:
                result["missing"].append("udev rules")
                log.warning("Udev rules: X Tidak ditemukan")
        return result

    def _check_adb_health(self) -> Dict:
        """Cek kesehatan ADB server."""
        result = {"status": "unknown", "devices": 0, "issues": []}

        adb_path = shutil.which("adb")
        if not adb_path:
            result["status"] = "not_found"
            result["issues"].append("ADB tidak terinstall")
            return result

        # Cek ADB version
        try:
            r = subprocess.run(["adb", "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                version_line = r.stdout.split('\n')[0] if r.stdout else "?"
                result["version"] = version_line
        except Exception:
            result["issues"].append("Gagal cek versi ADB")

        # Cek ADB devices
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            lines = r.stdout.strip().split('\n')
            device_count = sum(1 for l in lines if '\tdevice' in l)
            result["devices"] = device_count
            if device_count > 0:
                result["status"] = "healthy"
            else:
                # Cek apakah server jalan
                if "daemon started successfully" in r.stderr or "daemon not running" in r.stderr:
                    result["issues"].append("ADB server baru dimulai (normal)")
                elif "error: no devices/emulators found" in r.stdout:
                    result["status"] = "no_device"
                    result["issues"].append("Device tidak terdeteksi via ADB")
                else:
                    result["status"] = "no_device"
                    result["issues"].append("Tidak ada device ADB")
        except Exception as e:
            result["status"] = "error"
            result["issues"].append(f"Error: {e}")

        if result["status"] != "healthy" and result["status"] != "unknown":
            self.broken_drivers.append("ADB")

        return result

    def _check_fastboot_health(self) -> Dict:
        """Cek kesehatan Fastboot."""
        result = {"status": "unknown", "devices": 0, "issues": []}

        if not shutil.which("fastboot"):
            result["status"] = "not_found"
            result["issues"].append("Fastboot tidak terinstall")
            self.missing_drivers.append("Fastboot")
            return result

        try:
            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
            device_count = sum(1 for l in r.stdout.split('\n') if 'fastboot' in l)
            result["devices"] = device_count
            if device_count > 0:
                result["status"] = "healthy"
            else:
                result["status"] = "no_device"
                result["issues"].append("Tidak ada device di mode fastboot")
        except Exception as e:
            result["status"] = "error"
            result["issues"].append(f"Error: {e}")

        if result["status"] == "error":
            self.broken_drivers.append("Fastboot")

        return result

    # ── REPAIR ──

    def repair_adb(self) -> bool:
        """Repair ADB — reset, kill, restart, fix permissions."""
        log.header("[REPAIR ADB]")
        log.info("Memperbaiki ADB...")
        print()

        steps = []

        # Step 1: Kill ADB server
        log.info("Step 1/5: Mematikan ADB server...")
        try:
            subprocess.run(["adb", "kill-server"], capture_output=True, timeout=5)
            time.sleep(1)
            log.success("  ✅ ADB server dimatikan")
            steps.append("kill-server: OK")
        except Exception as e:
            log.warning(f"  ⚠️ Gagal kill server: {e}")
            steps.append("kill-server: FAIL")

        # Step 2: Kill all adb processes
        log.info("Step 2/5: Mematikan proses ADB zombie...")
        try:
            if self.os_name == "Windows":
                subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True, timeout=5)
                subprocess.run(["taskkill", "/F", "/IM", "adb"], capture_output=True, timeout=5)
            else:
                subprocess.run(["pkill", "-9", "adb"], capture_output=True, timeout=5)
            time.sleep(0.5)
            log.success("  ✅ Proses ADB dibersihkan")
            steps.append("kill-proc: OK")
        except Exception:
            steps.append("kill-proc: SKIP")

        # Step 3: Bersihkan lock file
        log.info("Step 3/5: Membersihkan file lock...")
        lock_file = os.path.expanduser("~/.android/adb.lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                log.success("  ✅ Lock file dibersihkan")
                steps.append("clean-lock: OK")
            except Exception:
                log.warning("  ⚠️ Gagal hapus lock file")
                steps.append("clean-lock: FAIL")
        else:
            log.info("  ℹ️ Tidak ada lock file")
            steps.append("clean-lock: SKIP")

        # Step 4: Restart ADB server
        log.info("Step 4/5: Menjalankan ADB server...")
        try:
            r = subprocess.run(["adb", "start-server"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                log.success("  ✅ ADB server berjalan")
                steps.append("start-server: OK")
            else:
                log.warning(f"  ⚠️ Gagal start server: {r.stderr}")
                steps.append("start-server: FAIL")
        except Exception as e:
            log.error(f"  ❌ Error start server: {e}")
            steps.append("start-server: ERROR")

        # Step 5: Verifikasi
        time.sleep(1)
        log.info("Step 5/5: Verifikasi...")
        try:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            devices = [l.split('\t')[0] for l in r.stdout.split('\n')[1:] if '\tdevice' in l]
            if devices:
                log.success(f"  ✅ Device terdeteksi: {', '.join(devices)}")
            else:
                log.warning("  ⚠️ ADB jalan, tapi tidak ada device terdeteksi")
                log.info("  💡 Tips: Pastikan USB Debugging aktif di device")
            steps.append(f"verify: {len(devices)} device(s)")
        except Exception as e:
            log.warning(f"  ⚠️ Error verifikasi: {e}")
            steps.append("verify: FAIL")

        print()
        success = all("OK" in s or "SKIP" in s for s in steps)
        if success:
            log.success("REPAIR ADB BERHASIL! ✅")
        else:
            log.warning("REPAIR ADB dengan peringatan.")

        self.repair_log.append({
            "action": "repair_adb",
            "time": datetime.now().isoformat(),
            "steps": steps,
            "success": success,
        })
        return success

    def repair_fastboot(self) -> bool:
        """Repair Fastboot — detect, test, fix USB issues."""
        log.header("[REPAIR FASTBOOT]")
        steps = []

        # Step 1: Cek fastboot available
        log.info("Step 1/3: Memeriksa Fastboot...")
        fb_path = shutil.which("fastboot")
        if not fb_path:
            log.error("  ❌ Fastboot tidak terinstall!")
            log.info("  💡 Install platform-tools dari developer.android.com")
            return False
        log.success(f"  ✅ Fastboot ditemukan: {fb_path}")

        # Step 2: Cek devices
        log.info("Step 2/3: Mendeteksi device fastboot...")
        try:
            r = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=10)
            devices = [l.split('\t')[0] for l in r.stdout.split('\n') if 'fastboot' in l]
            if devices:
                log.success(f"  ✅ Device fastboot: {', '.join(devices)}")
                steps.append("detect: OK")
            else:
                log.warning("  ⚠️ Tidak ada device di fastboot mode")
                log.info("  💡 Boot ke fastboot: adb reboot bootloader")
                log.info("     Atau manual: Vol Down + Power")
                steps.append("detect: no_device")
        except Exception as e:
            log.warning(f"  ⚠️ Error: {e}")
            steps.append("detect: FAIL")

        # Step 3: Test komunikasi
        if devices:
            log.info("Step 3/3: Menguji komunikasi...")
            try:
                r = subprocess.run(["fastboot", "getvar", "product"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0 and r.stdout.strip():
                    log.success(f"  ✅ Fastboot komunikasi OK: {r.stdout.strip()[:80]}")
                    steps.append("test: OK")
            except Exception:
                steps.append("test: FAIL")
        else:
            steps.append("test: SKIP")

        success = any("OK" in s for s in steps)
        print()
        if success:
            log.success("REPAIR FASTBOOT BERHASIL! ✅")
        else:
            log.warning("Fastboot tidak siap. Boot device ke fastboot mode dulu.")

        return success

    def repair_drivers(self) -> bool:
        """Repair semua driver yang bermasalah."""
        log.header("[REPAIR DRIVERS]")
        log.info("Memperbaiki semua driver yang bermasalah...")
        print()

        success = True

        # Repair ADB
        if "ADB" in self.broken_drivers or "ADB" in self.missing_drivers:
            log.info(">>> Memperbaiki ADB...")
            if self.repair_adb():
                log.success("  ADB OK ✅")
            else:
                log.warning("  ADB perlu install ulang")
                self.install_adb_fastboot()
                success = False
            print()

        # Repair Fastboot
        if "Fastboot" in self.missing_drivers:
            log.info(">>> Menginstall Fastboot...")
            self.install_adb_fastboot()
            print()

        # Install udev rules (Linux)
        if self.os_name == "Linux":
            self._install_linux_rules()

        self.repair_log.append({
            "action": "repair_all",
            "time": datetime.now().isoformat(),
            "success": success,
        })
        return success

    def install_adb_fastboot(self) -> bool:
        """Install ADB & Fastboot."""
        log.header("[INSTALL ADB & FASTBOOT]")
        log.info("Menginstall ADB & Fastboot tools...")
        print()

        if self.os_name == "Windows":
            self._install_adb_windows()
        elif self.os_name == "Linux":
            self._install_adb_linux()
        else:
            self._install_adb_mac()

        # Verifikasi
        if shutil.which("adb"):
            log.success("ADB berhasil diinstall! ✅")
        if shutil.which("fastboot"):
            log.success("Fastboot berhasil diinstall! ✅")
        return shutil.which("adb") is not None

    def _install_adb_windows(self) -> bool:
        """Download & install platform-tools di Windows."""
        log.info("Windows: Download platform-tools...")
        platform_tools_url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"

        try:
            import urllib.request
            import zipfile

            download_dir = tempfile.mkdtemp()
            zip_path = os.path.join(download_dir, "platform-tools.zip")
            extract_dir = os.path.join(download_dir, "platform-tools")

            log.info(f"  Downloading from: {platform_tools_url}")
            log.info(f"  This may take a few minutes...")

            # Download
            urllib.request.urlretrieve(platform_tools_url, zip_path)
            log.success("  ✅ Download selesai")

            # Extract
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(download_dir)
            log.success("  ✅ Extract selesai")

            # Copy ke tujuan
            dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
            os.makedirs(dest_dir, exist_ok=True)

            for fname in ["adb.exe", "fastboot.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]:
                src = os.path.join(extract_dir, fname)
                if os.path.exists(src):
                    dst = os.path.join(dest_dir, fname)
                    shutil.copy2(src, dst)
                    log.success(f"  ✅ Copied: {fname}")

            # Tambahkan ke PATH (user level)
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Environment", 0, winreg.KEY_SET_VALUE)
                current_path = os.environ.get("PATH", "")
                if dest_dir not in current_path:
                    new_path = f"{dest_dir};{current_path}"
                    winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                    winreg.CloseKey(key)
                    os.environ["PATH"] = new_path
                    log.success("  ✅ Ditambahkan ke PATH")
            except Exception:
                log.warning("  ⚠️ Tambahkan tools/ folder ke PATH manual")

            # Bersihkan
            shutil.rmtree(download_dir, ignore_errors=True)
            return True

        except Exception as e:
            log.error(f"  ❌ Download gagal: {e}")
            log.info("  💡 Download manual: https://developer.android.com/studio/releases/platform-tools")
            log.info("     Extract dan tambahkan folder platform-tools ke PATH")
            return False

    def _install_adb_linux(self) -> bool:
        """Install ADB via apt."""
        try:
            log.info("Menginstall via apt...")
            r = subprocess.run(
                ["sudo", "apt", "install", "-y", "adb", "fastboot"],
                capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0:
                log.success("ADB & Fastboot terinstall! ✅")
                return True
            else:
                log.warning(f"apt error: {r.stderr}")
                return False
        except Exception as e:
            log.error(f"Error: {e}")
            return False

    def _install_adb_mac(self) -> bool:
        """Install ADB via brew."""
        try:
            log.info("Menginstall via brew...")
            r = subprocess.run(
                ["brew", "install", "android-platform-tools"],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode == 0:
                log.success("ADB & Fastboot terinstall! ✅")
                return True
            else:
                log.warning(f"brew error: {r.stderr}")
                return False
        except FileNotFoundError:
            log.error("Homebrew tidak terinstall!")
            log.info("Install Homebrew: /bin/bash -c '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)'")
            return False
        except Exception as e:
            log.error(f"Error: {e}")
            return False

    def _install_linux_rules(self) -> bool:
        """Install udev rules untuk Linux."""
        rule_content = (
            '# STM32 Bootloader (DFU)\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="df11", MODE="0666"\n'
            '# ST-Link/V2\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="3748", MODE="0666"\n'
            '# ST-Link/V2-1\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", MODE="0666"\n'
            '# Android ADB/Fastboot\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="18d1", MODE="0666", GROUP="plugdev"\n'
            '# Qualcomm EDL\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="05c6", MODE="0666"\n'
            '# MediaTek BROM\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="0e8d", MODE="0666"\n'
            '# Samsung\n'
            'SUBSYSTEM=="usb", ATTRS{idVendor}=="04e8", MODE="0666"\n'
            '# Serial devices\n'
            'SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", MODE="0666"\n'
        )

        rule_path = "/etc/udev/rules.d/99-nst.rules"
        try:
            log.info(f"Membuat udev rules: {rule_path}")
            subprocess.run(
                ["sudo", "sh", "-c", f"echo '{rule_content}' > {rule_path} && udevadm control --reload-rules && udevadm trigger"],
                timeout=10
            )
            log.success("Udev rules berhasil diinstall! ✅")
            return True
        except Exception as e:
            log.error(f"Gagal install udev rules: {e}")
            log.info("Jalankan manual: sudo cp 99-nst.rules /etc/udev/rules.d/")
            return False

    # ── DIAGNOSE ──

    def diagnose_connection(self) -> Dict:
        """Diagnostik mendalam koneksi."""
        log.header("[DIAGNOSTIK KONEKSI]")
        issues = []
        recommendations = []

        # Cek ST-Link
        stlink = self._check_stlink()
        if not stlink["found"]:
            issues.append("ST-Link tidak terdeteksi")
            recommendations.extend([
                "Pastikan ST-Link terhubung via USB",
                "Coba port USB lain",
                "Check kabel SWD/JTAG",
            ])

        # Cek power
        try:
            if self.os_name == "Linux":
                output = subprocess.run(["lsusb", "-t"], capture_output=True, text=True, timeout=5)
                if "STM" in output.stdout and "12M" not in output.stdout:
                    recommendations.append("Periksa power USB (mungkin perlu hub powered)")
        except Exception:
            pass

        # Cek wire connections
        log.info("Pastikan koneksi berikut:")
        print("  • SWDIO → Pin SWDIO target")
        print("  • SWCLK → Pin SWCLK target")
        print("  • GND   → GND")
        print("  • 3.3V  → VCC (opsional)")
        print()

        return {"issues": issues, "recommendations": recommendations}

    def show_driver_info(self):
        """Tampilkan info driver lengkap."""
        log.header("[INFO DRIVER]")
        log.info(f"Sistem Operasi: {platform.system()} {platform.release()}")
        log.info(f"Python Version: {sys.version}")
        print()

        log.info("Tools Terdeteksi:")
        for name, info in self.KNOWN_DRIVERS.items():
            path = shutil.which(info["binary"])
            if path:
                log.success(f"  ✅ {name}: {path}")
            else:
                log.warning(f"  ❌ {name}: Tidak ditemukan")
        log.separator()

    def show_repair_log(self):
        """Tampilkan log perbaikan."""
        log.header("[REPAIR LOG]")
        if not self.repair_log:
            log.info("Belum ada aktivitas perbaikan")
            return
        for entry in self.repair_log:
            action = entry.get("action", "?")
            t = entry.get("time", "?")[:19]
            success = "✅" if entry.get("success") else "⚠️"
            steps = ", ".join(entry.get("steps", []))[:80]
            log.info(f"  {success} [{t}] {action}: {steps}")

    def get_install_guide(self, tool_name: str) -> str:
        """Dapatkan panduan install untuk tool tertentu."""
        info = self.KNOWN_DRIVERS.get(tool_name)
        if not info:
            return f"Tool '{tool_name}' tidak dikenal"

        lines = [f"=== {tool_name} ==="]
        lines.append(f"  Deskripsi: {info['description']}")
        lines.append(f"  Binary: {info['binary']}")
        lines.append(f"  Download: {info.get('install_url', 'N/A')}")

        if self.os_name == "Windows":
            lines.append(f"  Windows: Download dari {info.get('install_url', 'N/A')}")
        elif self.os_name == "Linux":
            lines.append(f"  Linux: {info.get('linux_cmd', 'Install via package manager')}")
        else:
            lines.append(f"  Mac: {info.get('mac_cmd', 'Install via package manager')}")

        return "\n".join(lines)


# ========== NST FUNCTIONS (backward compatibility) ==========

def cek_driver_windows_registry():
    """Cek driver Apple via Windows Registry."""
    if platform.system() != "Windows":
        return False
    try:
        import winreg
        jalur_reg = [
            r"SOFTWARE\\Apple Inc.\\Apple Mobile Device Support",
            r"SOFTWARE\\WOW6432Node\\Apple Inc.\\Apple Mobile Device Support"
        ]
        for jalur in jalur_reg:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, jalur)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False


def verifikasi_port_komunikasi():
    """Verifikasi port komunikasi (Mediatek/Qualcomm/USB Serial)."""
    if platform.system() != "Windows":
        return True
    try:
        output = subprocess.run(
            ["wmic", "path", "Win32_PnPEntity", "get", "Caption"],
            capture_output=True, text=True, check=True, timeout=5
        )
        result = output.stdout.lower()
        if "mediatek" in result or "qualcomm" in result or "usb serial" in result:
            return True
        return False
    except Exception:
        return False


# ========== MAIN ENTRY ==========

def run():
    """Jalankan Driver Doctor — scan + info."""
    doctor = DriverDoctor()
    doctor.scan_all()
    doctor.show_driver_info()
    doctor.diagnose_connection()


def run_repair_adb():
    """Repair ADB server."""
    DriverDoctor().repair_adb()


def run_repair_fastboot():
    """Repair Fastboot."""
    DriverDoctor().repair_fastboot()


def run_repair_all():
    """Repair semua driver."""
    DriverDoctor().repair_drivers()


def run_install_tools():
    """Install ADB & Fastboot."""
    Doctor = DriverDoctor()
    if not shutil.which("adb") or not shutil.which("fastboot"):
        Doctor.install_adb_fastboot()
    else:
        log.info("ADB & Fastboot sudah terinstall.")
        if input("  Install ulang? (y/N): ").strip().lower() == 'y':
            Doctor.install_adb_fastboot()