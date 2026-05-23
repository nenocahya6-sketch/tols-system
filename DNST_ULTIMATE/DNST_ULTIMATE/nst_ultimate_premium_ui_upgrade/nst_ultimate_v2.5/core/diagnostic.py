
"""
Diagnostic - Diagnostik perangkat STM32
Mendeteksi chip, membaca register, dan menguji koneksi
"""
import struct
import time
from typing import Dict, Optional, List, Tuple
from datetime import datetime

from config import STM32_MODELS, CHIP_ID_REGISTRY, DEFAULT_BAUDRATE, DEFAULT_TIMEOUT
from core.logger import log


class STM32Diagnostic:
    """Diagnostik untuk perangkat STM32"""

    def __init__(self):
        self.chip_id: Optional[int] = None
        self.chip_name: Optional[str] = None
        self.flash_size: Optional[int] = None
        self.ram_size: Optional[int] = None
        self.bootloader_version: Optional[str] = None
        self.protection_status: Optional[Dict] = None
        self.serial: Optional[str] = None
        self.voltage: Optional[float] = None

    def detect_chip(self) -> Dict:
        """Deteksi chip STM32 yang terhubung"""
        log.header("[DETEKSI CHIP]")

        # Simulasi deteksi (real implementation would use pyserial)
        detected = {
            "chip_id": None,
            "chip_name": "Tidak terdeteksi",
            "flash_size": "?",
            "ram_size": "?",
        }

        log.info("Mencoba mendeteksi chip STM32...")
        print()
        log.warning("Tidak ada koneksi serial aktif")
        log.info("Silakan hubungkan STM32 via UART/ST-Link terlebih dahulu")
        print()

        # Tampilkan model yang tersedia untuk referensi
        log.info("Model STM32 yang didukung:")
        for key, model in STM32_MODELS.items():
            print(f"  • {key}: {model['name']} ({model['flash_size']} Flash)")

        print()
        log.info("Gunakan menu Flash untuk menghubungkan ke perangkat")

        return detected

    def read_chip_info(self) -> Dict:
        """Baca informasi chip dari register"""
        log.header("[INFO CHIP]")

        info = {
            "chip_id": self.chip_id,
            "chip_name": self.chip_name or "Belum terdeteksi",
            "flash_size": self.flash_size,
            "ram_size": self.ram_size,
            "bootloader_ver": self.bootloader_version,
            "protection": self.protection_status,
            "serial": self.serial,
            "voltage": self.voltage,
        }

        if self.chip_id:
            log.success(f"Chip ID: 0x{self.chip_id:04X} ({self.chip_name})")
            log.info(f"Flash: {self.flash_size if self.flash_size else 'Unknown'}")
            log.info(f"RAM: {self.ram_size if self.ram_size else 'Unknown'}")
            if self.bootloader_version:
                log.info(f"🔓 Bootloader : v{self.bootloader_version}")
        else:
            log.warning("Belum ada chip terdeteksi")
            log.info("Gunakan 'Scan & Connect' dulu untuk mendeteksi chip")

        return info

    def run_full_diagnostic(self) -> Dict:
        """Jalankan diagnostik lengkap"""
        log.header("[DIAGNOSTIK LENGKAP]")

        results = {
            "timestamp": datetime.now().isoformat(),
            "chip": {},
            "memory": {},
            "protection": {},
            "errors": [],
            "warnings": [],
        }

        # 1. Chip detection
        results["chip"] = self.detect_chip()

        # 2. Memory test
        log.info("Memory Test:")
        print("  • Read Check    : ⏳ (memerlukan koneksi)")
        print("  • Write Check   : ⏳ (memerlukan koneksi)")
        print("  • Erase Check   : ⏳ (memerlukan koneksi)")
        print()

        # 3. Protection check
        log.info("Protection Status:")
        print("  • Readout Protection  : ⏳ (memerlukan koneksi)")
        print("  • Write Protection    : ⏳ (memerlukan koneksi)")
        print()

        # 4. Clock test
        log.info("Clock Test:")
        print("  • HSI        : ⏳")
        print("  • HSE        : ⏳")
        print("  • PLL        : ⏳")
        print()

        log.warning("Koneksikan perangkat terlebih dahulu untuk diagnostik penuh")
        log.info("Silakan ke menu Flash → Connect")

        return results

    def test_connection(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> bool:
        """Test koneksi serial ke perangkat"""
        log.info(f"Menguji koneksi ke {port} @ {baudrate} baud...")

        try:
            import serial
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=DEFAULT_TIMEOUT
            )

            # Kirim init byte (0x7F) untuk STM32 bootloader
            ser.write(b'\x7f')
            time.sleep(0.1)

            if ser.in_waiting:
                resp = ser.read(ser.in_waiting)
                if resp == b'\x79':  # ACK
                    log.success(f"Koneksi berhasil ke {port}")
                    ser.close()
                    return True
                elif resp == b'\x1f':  # NACK
                    log.error("Perangkat merespon NACK - mungkin bukan mode bootloader")
                else:
                    log.warning(f"Respon tidak dikenal: {resp.hex()}")

            ser.close()
            log.warning(f"Tidak ada respon dari {port}")
            return False

        except ImportError:
            log.warning("Module 'pyserial' tidak terinstall")
            log.info("Install: pip install pyserial")
            return False
        except Exception as e:
            log.error(f"Error koneksi: {e}")
            return False

    def scan_port(self, port: str) -> bool:
        """Scan port tertentu untuk device STM32"""
        log.info(f"Scanning {port}...")

        for baud in [115200, 57600, 38400, 19200, 9600]:
            try:
                import serial
                ser = serial.Serial(
                    port=port,
                    baudrate=baud,
                    bytesize=8,
                    parity='N',
                    stopbits=1,
                    timeout=1
                )

                # Kirim 0x7F untuk test bootloader
                ser.write(b'\x7f')
                time.sleep(0.05)

                if ser.in_waiting:
                    resp = ser.read(ser.in_waiting)
                    if resp == b'\x79':  # ACK
                        log.success(f"STM32 terdeteksi di {port} @ {baud} baud")
                        ser.close()
                        return True

                ser.close()
            except Exception:
                continue

        return False

    def get_chip_info_from_id(self, chip_id: int) -> Optional[str]:
        """Dapatkan nama chip dari ID"""
        return CHIP_ID_REGISTRY.get(chip_id)

    def format_size(self, size_bytes: int) -> str:
        """Format ukuran bytes ke human readable"""
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024*1024):.1f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes} bytes"


def run():
    """Jalankan Diagnostic secara interaktif"""
    diagnostic = STM32Diagnostic()

    while True:
        time.sleep(1)
        log.header("[DIAGNOSTIC]")
        print("  1. Deteksi Chip")
        print("  2. Info Chip")
        print("  3. Diagnostik Lengkap")
        print("  4. Test Koneksi (Manual)")
        print("  5. Scan Port")
        print("  0. Kembali ke Menu Utama")
        print()

        choice = input("  Pilih [0-5]: ").strip()

        if choice == "1":
            diagnostic.detect_chip()
        elif choice == "2":
            diagnostic.read_chip_info()
        elif choice == "3":
            diagnostic.run_full_diagnostic()
        elif choice == "4":
            port = input("  Port (COMx): ").strip()
            baud = input(f"  Baudrate [{DEFAULT_BAUDRATE}]: ").strip()
            baud = int(baud) if baud else DEFAULT_BAUDRATE
            diagnostic.test_connection(port, baud)
        elif choice == "5":
            log.info("Scan port untuk STM32...")
            import glob
            ports = []
            import platform
            if platform.system() == "Windows":
                # Try common COM ports
                for i in range(1, 21):
                    ports.append(f"COM{i}")
            else:
                for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*"]:
                    ports.extend(glob.glob(pattern))

            found = False
            for port in ports:
                if diagnostic.scan_port(port):
                    found = True
            if not found:
                log.warning("Tidak ada STM32 terdeteksi di port yang discan")
        elif choice == "0":
            break
        else:
            log.warning("Pilihan tidak valid!")

        if choice != "0":
            ""


