
"""
Flasher - Flash firmware ke STM32
Mendukung UART (ROM Bootloader), DFU, dan ST-Link
"""
import os
import time
import struct
import platform
from typing import Optional, Dict, List, Callable
from datetime import datetime

from config import (
    FIRMWARE_DIR, DEFAULT_BAUDRATE, DEFAULT_TIMEOUT,
    DEFAULT_PROTOCOL, BOOTLOADER_CMD, FLASH_PROTOCOLS,
    STM32_MODELS, DEFAULT_MODEL
)
from core.logger import log


class Flasher:
    """Flash firmware ke STM32"""

    def __init__(self):
        self.port: Optional[str] = None
        self.baudrate: int = DEFAULT_BAUDRATE
        self.protocol: str = DEFAULT_PROTOCOL
        self.connected: bool = False
        self.serial_conn = None
        self.chip_id: Optional[int] = None
        self.bootloader_version: Optional[str] = None
        self.progress_callback: Optional[Callable] = None
        self.selected_model: str = DEFAULT_MODEL

    def connect(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> bool:
        """Konek ke STM32 via UART bootloader"""
        log.header(f"[KONEK KE {port} @ {baudrate} baud]")

        try:
            import serial
            self.serial_conn = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=DEFAULT_TIMEOUT
            )

            self.port = port
            self.baudrate = baudrate

            # Handshake bootloader
            if self._bootloader_handshake():
                self.connected = True

                # Read bootloader version
                self._get_bootloader_version()

                # Read chip ID
                self._get_chip_id()

                log.success(f"✅ Terhubung ke {port} @ {baudrate} baud")
                return True
            else:
                log.error("Gagal handshake dengan bootloader")
                self.disconnect()
                return False

        except ImportError:
            log.error("Module 'pyserial' tidak terinstall")
            log.info("Install: pip install pyserial")
            return False
        except Exception as e:
            log.error(f"Gagal konek: {e}")
            return False

    def _bootloader_handshake(self) -> bool:
        """Handshake dengan STM32 ROM bootloader"""
        try:
            # Kirim 0x7F
            self.serial_conn.write(b'\x7f')
            time.sleep(0.1)

            if self.serial_conn.in_waiting:
                resp = self.serial_conn.read(self.serial_conn.in_waiting)
                return resp == b'\x79'  # ACK
            return False
        except Exception:
            return False

    def _get_bootloader_version(self) -> Optional[str]:
        """Baca versi bootloader"""
        try:
            # Command: GET (0x00)
            self.serial_conn.write(bytes([BOOTLOADER_CMD["GET"]]))
            self.serial_conn.write(bytes([0xFF ^ BOOTLOADER_CMD["GET"]]))  # XOR checksum
            time.sleep(0.05)

            if self.serial_conn.in_waiting:
                resp = self.serial_conn.read(self.serial_conn.in_waiting)
                if resp and len(resp) >= 2 and resp[0] == 0x79:  # ACK
                    ver = resp[1]
                    self.bootloader_version = f"{ver >> 4}.{ver & 0x0F}"
                    log.info(f"Bootloader version: {self.bootloader_version}")
                    return self.bootloader_version
        except Exception:
            pass
        return None

    def _get_chip_id(self) -> Optional[int]:
        """Baca ID chip"""
        try:
            # Command: GET_ID (0x02)
            cmd = BOOTLOADER_CMD["GET_ID"]
            self.serial_conn.write(bytes([cmd]))
            self.serial_conn.write(bytes([0xFF ^ cmd]))
            time.sleep(0.05)

            if self.serial_conn.in_waiting:
                resp = self.serial_conn.read(self.serial_conn.in_waiting)
                if resp and len(resp) >= 3 and resp[0] == 0x79:  # ACK
                    # 2 byte chip ID
                    self.chip_id = (resp[1] << 8) | resp[2]
                    from core.diagnostic import STM32Diagnostic
                    diag = STM32Diagnostic()
                    chip_name = diag.get_chip_info_from_id(self.chip_id)
                    if chip_name:
                        log.success(f"Chip terdeteksi: {chip_name} (ID: 0x{self.chip_id:04X})")
                    else:
                        log.info(f"Chip ID: 0x{self.chip_id:04X} (unknown)")
                    return self.chip_id
        except Exception:
            pass
        return None

    def disconnect(self):
        """Putus koneksi"""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.connected = False
        self.serial_conn = None
        self.chip_id = None
        log.info("Koneksi diputus")

    def flash_firmware(self, firmware_path: str, address: int = 0x08000000) -> bool:
        """Flash firmware ke STM32"""
        log.header("[FLASH FIRMWARE]")

        if not self.connected:
            log.error("Tidak terhubung! Konek dulu ke perangkat.")
            return False

        if not os.path.exists(firmware_path):
            log.error(f"File tidak ditemukan: {firmware_path}")
            return False

        # Baca file firmware
        try:
            with open(firmware_path, 'rb') as f:
                firmware_data = f.read()
        except Exception as e:
            log.error(f"Gagal baca file: {e}")
            return False

        file_size = len(firmware_data)
        log.info(f"File: {os.path.basename(firmware_path)}")
        log.info(f"Ukuran: {self._format_size(file_size)}")
        log.info(f"Address: 0x{address:08X}")
        log.info(f"Protocol: {FLASH_PROTOCOLS.get(self.protocol, self.protocol)}")
        print()

        # Konfirmasi
        confirm = input(f"  Flash {os.path.basename(firmware_path)}? (y/N): ").strip().lower()
        if confirm != 'y':
            log.warning("Dibatalkan")
            return False

        # Proses flashing
        if self.protocol == "uart":
            success = self._flash_uart(firmware_data, address)
        elif self.protocol == "dfu":
            success = self._flash_dfu(firmware_path)
        elif self.protocol == "stlink":
            success = self._flash_stlink(firmware_path)
        else:
            log.error(f"Protocol tidak didukung: {self.protocol}")
            return False

        if success:
            log.success("Firmware berhasil di-flash!")
            self._verify_flash(firmware_data, address)
        else:
            log.error("Flash gagal!")

        return success

    def _flash_uart(self, data: bytes, address: int) -> bool:
        """Flash via UART bootloader"""
        try:
            # Erase flash dulu
            log.info("Erase flash...")
            if not self._erase_flash():
                log.error("Gagal erase flash")
                return False
            log.success("Flash erased!")

            # Write memory
            log.info(f"Menulis {self._format_size(len(data))}...")
            chunk_size = 256  # Max per command

            for i in range(0, len(data), chunk_size):
                chunk = data[i:i + chunk_size]
                
                # Write Memory command
                cmd = BOOTLOADER_CMD["WRITE_MEMORY"]
                self.serial_conn.write(bytes([cmd]))
                self.serial_conn.write(bytes([0xFF ^ cmd]))
                time.sleep(0.01)

                if not self._wait_ack():
                    log.error(f"Error di offset 0x{i:08X}")
                    return False

                # Address (4 bytes) + checksum
                addr = address + i
                addr_bytes = struct.pack('>I', addr)
                addr_checksum = 0xFF & (addr_bytes[0] ^ addr_bytes[1] ^ addr_bytes[2] ^ addr_bytes[3])
                self.serial_conn.write(addr_bytes + bytes([addr_checksum]))
                time.sleep(0.01)

                if not self._wait_ack():
                    log.error(f"Address NACK di 0x{addr:08X}")
                    return False

                # Data: length (N-1) + data + checksum
                n = len(chunk)
                checksum = 0xFF ^ n
                for b in chunk:
                    checksum ^= b
                
                self.serial_conn.write(bytes([0xFF & (n - 1)]) + chunk + bytes([0xFF & checksum]))
                time.sleep(0.01)

                if not self._wait_ack():
                    log.error(f"Data NACK di offset 0x{i:08X}")
                    return False

                # Progress
                if self.progress_callback:
                    self.progress_callback(i + len(chunk), len(data))
                log.progress_bar(i + len(chunk), len(data), "Flashing:")

            print()
            log.success("✅ Flash selesai!")
            return True

        except Exception as e:
            log.error(f"Error flash: {e}")
            return False

    def _erase_flash(self) -> bool:
        """Erase flash memory"""
        try:
            # Extended Erase (0x44)
            cmd = BOOTLOADER_CMD["EXTENDED_ERASE"]
            self.serial_conn.write(bytes([cmd]))
            self.serial_conn.write(bytes([0xFF ^ cmd]))
            time.sleep(0.05)

            if not self._wait_ack():
                # Try regular erase
                return self._erase_flash_legacy()

            # Global erase (0xFFFE = special, 0xFFFF = global)
            self.serial_conn.write(b'\xff\xff\x00')  # Global erase
            time.sleep(0.1)

            return self._wait_ack()

        except Exception:
            return False

    def _erase_flash_legacy(self) -> bool:
        """Legacy erase (0x43)"""
        try:
            cmd = BOOTLOADER_CMD["ERASE_MEMORY"]
            self.serial_conn.write(bytes([cmd]))
            self.serial_conn.write(bytes([0xFF ^ cmd]))
            time.sleep(0.05)

            if not self._wait_ack():
                return False

            # Global erase
            self.serial_conn.write(b'\xff\xff')  # 0xFFFF = all pages
            time.sleep(0.1)

            return True

        except Exception:
            return False

    def _wait_ack(self, timeout: float = 2.0) -> bool:
        """Tunggu ACK (0x79) dari perangkat"""
        start = time.time()
        while time.time() - start < timeout:
            if self.serial_conn.in_waiting:
                resp = self.serial_conn.read(1)
                if resp == b'\x79':  # ACK
                    return True
                elif resp == b'\x1f':  # NACK
                    return False
            time.sleep(0.01)
        return False

    def _flash_dfu(self, firmware_path: str) -> bool:
        """Flash via DFU mode menggunakan dfu-util"""
        try:
            import subprocess
            cmd = [
                "dfu-util",
                "-a", "0",
                "-s", "0x08000000:leave",
                "-D", firmware_path,
            ]
            log.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                log.success("DFU flash berhasil!")
                return True
            else:
                log.error(f"DFU error: {result.stderr}")
                return False

        except FileNotFoundError:
            log.error("dfu-util tidak ditemukan. Install: dnf install dfu-util / brew install dfu-util")
            return False
        except Exception as e:
            log.error(f"DFU error: {e}")
            return False

    def _flash_stlink(self, firmware_path: str) -> bool:
        """Flash via ST-Link menggunakan st-flash"""
        try:
            import subprocess
            cmd = [
                "st-flash",
                "--reset",
                "write", firmware_path,
                "0x08000000",
            ]
            log.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                log.success("ST-Link flash berhasil!")
                return True
            else:
                log.error(f"ST-Link error: {result.stderr}")
                return False

        except FileNotFoundError:
            log.error("st-flash tidak ditemukan. Install: brew install stlink / dnf install stlink")
            return False
        except Exception as e:
            log.error(f"ST-Link error: {e}")
            return False

    def _verify_flash(self, data: bytes, address: int) -> bool:
        """Verifikasi hasil flash"""
        log.info("Verifikasi flash...")
        
        if not self.connected:
            log.warning("Tidak bisa verifikasi (tidak terhubung)")
            return False

        try:
            verify_size = min(len(data), 1024)  # Verify first 1KB
            # Read back and compare
            for i in range(0, verify_size, 256):
                chunk = data[i:i + 256]
                # Read Memory command
                cmd = BOOTLOADER_CMD["READ_MEMORY"]
                self.serial_conn.write(bytes([cmd]))
                self.serial_conn.write(bytes([0xFF ^ cmd]))
                time.sleep(0.01)
                self._wait_ack()

                addr = address + i
                addr_bytes = struct.pack('>I', addr)
                addr_checksum = 0xFF & (addr_bytes[0] ^ addr_bytes[1] ^ addr_bytes[2] ^ addr_bytes[3])
                self.serial_conn.write(addr_bytes + bytes([addr_checksum]))
                time.sleep(0.01)
                self._wait_ack()

                n = len(chunk) - 1
                self.serial_conn.write(bytes([n]))
                time.sleep(0.05)

                if self.serial_conn.in_waiting:
                    read_data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if read_data != chunk[:len(read_data)]:
                        log.warning(f"Verifikasi gagal di offset 0x{addr:08X}")
                        return False

            log.success("Verifikasi berhasil!")
            return True

        except Exception as e:
            log.warning(f"Verifikasi gagal: {e}")
            return False

    def read_flash(self, address: int = 0x08000000, size: int = 1024) -> Optional[bytes]:
        """Baca isi flash"""
        if not self.connected:
            log.error("Tidak terhubung!")
            return None

        log.info(f"Membaca flash dari 0x{address:08X} ({self._format_size(size)})...")
        data = bytearray()

        try:
            for i in range(0, size, 256):
                chunk_size = min(256, size - i)
                
                # Read Memory command
                cmd = BOOTLOADER_CMD["READ_MEMORY"]
                self.serial_conn.write(bytes([cmd]))
                self.serial_conn.write(bytes([0xFF ^ cmd]))
                time.sleep(0.01)
                self._wait_ack()

                # Address
                addr = address + i
                addr_bytes = struct.pack('>I', addr)
                addr_checksum = 0xFF & (addr_bytes[0] ^ addr_bytes[1] ^ addr_bytes[2] ^ addr_bytes[3])
                self.serial_conn.write(addr_bytes + bytes([addr_checksum]))
                time.sleep(0.01)
                self._wait_ack()

                # Read request
                self.serial_conn.write(bytes([chunk_size - 1]))
                time.sleep(0.05)

                if self.serial_conn.in_waiting:
                    chunk = self.serial_conn.read(self.serial_conn.in_waiting)
                    data.extend(chunk)

                log.progress_bar(i + chunk_size, size, "Reading:")

            print()
            log.success(f"✅ Read selesai ({self._format_size(len(data))})")
            return bytes(data)

        except Exception as e:
            log.error(f"Error read: {e}")
            return None

    def read_flash_to_file(self, filepath: str, address: int = 0x08000000, size: int = 65536) -> bool:
        """Baca flash dan simpan ke file"""
        data = self.read_flash(address, size)
        if data:
            try:
                with open(filepath, 'wb') as f:
                    f.write(data)
                log.success(f"Flash tersimpan: {filepath}")
                return True
            except Exception as e:
                log.error(f"Gagal simpan: {e}")
        return False

    def set_protocol(self, protocol: str):
        """Set protocol flashing"""
        if protocol in FLASH_PROTOCOLS:
            self.protocol = protocol
            log.info(f"Protocol: {FLASH_PROTOCOLS[protocol]}")

    def select_firmware(self) -> Optional[str]:
        """Pilih file firmware dari direktori"""
        log.header("[PILIH FIRMWARE]")

        # List firmware files
        if not os.path.exists(FIRMWARE_DIR):
            os.makedirs(FIRMWARE_DIR, exist_ok=True)

        firmware_files = [
            f for f in os.listdir(FIRMWARE_DIR)
            if f.endswith(('.bin', '.hex', '.elf'))
        ]

        if not firmware_files:
            log.warning(f"Tidak ada file firmware di folder: {FIRMWARE_DIR}")
            log.info("Letakkan file .bin/.hex/.elf di folder 'firmware/'")
            path = "".strip()
            if path and os.path.exists(path):
                return path
            return None

        print()
        log.info("File firmware tersedia:")
        for i, f in enumerate(firmware_files, 1):
            fpath = os.path.join(FIRMWARE_DIR, f)
            size = os.path.getsize(fpath)
            print(f"  {i}. {f} ({self._format_size(size)})")

        print()
        choice = input(f"  Pilih file [1-{len(firmware_files)}] atau 0 untuk manual: ").strip()

        if choice == "0":
            path = "".strip()
            return path if os.path.exists(path) else None
        elif choice.isdigit() and 1 <= int(choice) <= len(firmware_files):
            return os.path.join(FIRMWARE_DIR, firmware_files[int(choice) - 1])

        log.warning("Pilihan tidak valid")
        return None

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024*1024):.1f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes} bytes"

    def show_connection_status(self):
        """Tampilkan status koneksi"""
        log.header("[STATUS KONEKSI]")
        if self.connected:
            log.success(f"✅ Terhubung ke {self.port}")
            log.info(f"   Baudrate: {self.baudrate}")
            log.info(f"   Protocol: {FLASH_PROTOCOLS.get(self.protocol, self.protocol)}")
            if self.chip_id:
                log.info(f"   Chip ID: 0x{self.chip_id:04X}")
            if self.bootloader_version:
                log.info(f"   🔓 Bootloader : v{self.bootloader_version}")
            log.info(f"   Model: {self.selected_model}")
        else:
            log.warning("Tidak terhubung")
        log.separator()

    def select_model(self) -> str:
        """Pilih model STM32"""
        log.header("[PILIH MODEL STM32]")
        models = list(STM32_MODELS.keys())
        for i, key in enumerate(models, 1):
            model = STM32_MODELS[key]
            print(f"  {i}. {key} - {model['name']}")
            print(f"     Flash: {model['flash_size']}, RAM: {model['ram_size']}")
        print()
        choice = input(f"  Pilih model [1-{len(models)}] atau Enter untuk default: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            self.selected_model = models[int(choice) - 1]
            log.success(f"Model: {self.selected_model}")
        return self.selected_model


def run():
    """Jalankan Flasher secara interaktif"""
    flasher = Flasher()

    while True:
        log.header("[FLASHER]")
        flasher.show_connection_status()
        print("  1. Connect / Ganti Port")
        print("  2. Flash Firmware")
        print("  3. Read Flash")
        print("  4. Pilih Model STM32")
        print("  5. Ganti Protocol")
        print("  6. Disconnect")
        print("  0. Kembali ke Menu Utama")
        print()

        choice = input("  Pilih [0-6]: ").strip()

        if choice == "1":
            port = input("  Port (COMx): ").strip()
            baud_input = input(f"  Baudrate [{DEFAULT_BAUDRATE}]: ").strip()
            baud = int(baud_input) if baud_input else DEFAULT_BAUDRATE
            flasher.connect(port, baud)

        elif choice == "2":
            if not flasher.connected:
                log.warning("Belum terhubung! Connect dulu.")
            else:
                fw = flasher.select_firmware()
                if fw:
                    flasher.flash_firmware(fw)

        elif choice == "3":
            if not flasher.connected:
                log.warning("Belum terhubung!")
            else:
                default_file = os.path.join(FIRMWARE_DIR, "flash_dump.bin")
                addr_input = input("  Address [0x08000000]: ").strip()
                addr = int(addr_input, 16) if addr_input else 0x08000000
                size_input = input("  Size [65536]: ").strip()
                size = int(size_input) if size_input else 65536
                filepath = input(f"  Output file [{default_file}]: ").strip()
                flasher.read_flash_to_file(filepath or default_file, addr, size)

        elif choice == "4":
            flasher.select_model()

        elif choice == "5":
            log.header("[GANTI PROTOCOL]")
            protocols = list(FLASH_PROTOCOLS.items())
            for i, (key, desc) in enumerate(protocols, 1):
                marker = "*" if flasher.protocol == key else " "
                print(f"  [{marker}] {i}. {desc}")
            print()
            pchoice = input(f"  Pilih protocol [1-{len(protocols)}]: ").strip()
            if pchoice.isdigit() and 1 <= int(pchoice) <= len(protocols):
                flasher.set_protocol(protocols[int(pchoice) - 1][0])

        elif choice == "6":
            if flasher.connected:
                flasher.disconnect()
            else:
                log.info("Sudah disconnect")

        elif choice == "0":
            if flasher.connected:
                flasher.disconnect()
            break
        else:
            log.warning("Pilihan tidak valid!")

        if choice != "0":
            ""

