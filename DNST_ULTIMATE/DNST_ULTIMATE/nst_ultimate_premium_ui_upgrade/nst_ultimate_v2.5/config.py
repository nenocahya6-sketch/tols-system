
"""
NST Ultimate Console v3.2 - Master Configuration
Gabungan STM32 Flasher + NST Android/iPhone Service Tools

FITUR:
- Config via config.json (persistent, bisa diedit user)
- .env support untuk API keys & secrets
- Environment variable override
- Multi-platform path handling
"""
import os
import json
import platform
from typing import Dict, List, Optional, Tuple, Any


# ========== BASE DIRECTORIES ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_json_config() -> Dict[str, Any]:
    """Load config dari config.json jika ada"""
    json_path = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"[WARNING] Gagal load config.json: {e}")
    return {}


def _load_env_file() -> Dict[str, str]:
    """Load .env file jika ada (API keys, secrets)"""
    env_path = os.path.join(BASE_DIR, ".env")
    env_vars = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        env_vars[key.strip()] = value.strip().strip('"').strip("'")
        except Exception as e:
            print(f"[WARNING] Gagal load .env: {e}")
    return env_vars


# Load konfigurasi tambahan
_JSON_CFG = _load_json_config()
_ENV_VARS = _load_env_file()


def get_env(key: str, default: Any = None) -> Any:
    """
    Get config dari multiple sources (priority: env var > .env > config.json > default)
    """
    # 1. Environment variable (highest priority)
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val

    # 2. .env file
    if key in _ENV_VARS:
        return _ENV_VARS[key]

    # 3. config.json
    if key in _JSON_CFG:
        return _JSON_CFG[key]

    return default


# ========== VERSION ==========
APP_NAME = get_env("APP_NAME", "NST Ultimate Console")
VERSION = get_env("VERSION", "3.2")
SUBVERSION = get_env("SUBVERSION", "Professional Edition")
AUTHOR = get_env("AUTHOR", "NST")

# ========== LANGUAGE ==========
AVAILABLE_LANGUAGES = ["id", "en"]
DEFAULT_LANGUAGE = "id"

# ========== SERIAL CONFIG ==========
BAUDRATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 5
DEFAULT_PORT = "auto"  # 'auto' untuk mendeteksi otomatis

# ========== STM32 CONFIG ==========
STM32_MODELS: Dict[str, Dict] = {
    "STM32F0": {
        "name": "STM32F0 Series",
        "flash_start": 0x08000000,
        "flash_size": "16K - 256K",
        "ram_size": "4K - 32K",
    },
    "STM32F1": {
        "name": "STM32F1 Series (Performance)",
        "flash_start": 0x08000000,
        "flash_size": "32K - 512K",
        "ram_size": "6K - 64K",
    },
    "STM32F2": {
        "name": "STM32F2 Series (High Performance Connectivity)",
        "flash_start": 0x08000000,
        "flash_size": "128K - 1M",
        "ram_size": "64K - 128K",
    },
    "STM32F3": {
        "name": "STM32F3 Series (DSP & FPU)",
        "flash_start": 0x08000000,
        "flash_size": "16K - 256K",
        "ram_size": "8K - 40K",
    },
    "STM32F4": {
        "name": "STM32F4 Series (High Performance)",
        "flash_start": 0x08000000,
        "flash_size": "64K - 2M",
        "ram_size": "32K - 384K",
    },
    "STM32F7": {
        "name": "STM32F7 Series (Ultra High Perf)",
        "flash_start": 0x08000000,
        "flash_size": "256K - 2M",
        "ram_size": "64K - 512K",
    },
    "STM32G0": {
        "name": "STM32G0 Series (Entry Level)",
        "flash_start": 0x08000000,
        "flash_size": "16K - 512K",
        "ram_size": "8K - 144K",
    },
    "STM32G4": {
        "name": "STM32G4 Series (Mixed Signal)",
        "flash_start": 0x08000000,
        "flash_size": "64K - 512K",
        "ram_size": "32K - 128K",
    },
    "STM32H7": {
        "name": "STM32H7 Series (High Perf Cortex-M7)",
        "flash_start": 0x08000000,
        "flash_size": "128K - 2M",
        "ram_size": "64K - 1M",
    },
    "STM32L0": {
        "name": "STM32L0 Series (Ultra Low Power)",
        "flash_start": 0x08000000,
        "flash_size": "8K - 192K",
        "ram_size": "2K - 20K",
    },
    "STM32L4": {
        "name": "STM32L4 Series (Ultra Low Power)",
        "flash_start": 0x08000000,
        "flash_size": "64K - 1M",
        "ram_size": "32K - 320K",
    },
    "STM32WB": {
        "name": "STM32WB Series (Wireless)",
        "flash_start": 0x08000000,
        "flash_size": "256K - 1M",
        "ram_size": "32K - 256K",
    },
    "STM32MP1": {
        "name": "STM32MP1 Series (MPU)",
        "flash_start": 0x08000000,
        "flash_size": "Up to 1M",
        "ram_size": "Up to 512K",
    },
}

DEFAULT_MODEL = "STM32F4"

# ========== FLASHING CONFIG ==========
FLASH_PROTOCOLS: Dict[str, str] = {
    "uart": "UART (Serial) - STM32 ROM Bootloader",
    "dfu": "DFU (USB) - Device Firmware Update",
    "stlink": "ST-Link (SWD/JTAG) - ST-Link Debugger",
    "swd": "SWD (Serial Wire Debug)",
}

DEFAULT_PROTOCOL = "uart"

# ========== FIRMWARE PATHS ==========
FIRMWARE_DIR = os.path.join(BASE_DIR, "firmware")
os.makedirs(FIRMWARE_DIR, exist_ok=True)

# ========== LOGGING ==========
LOG_DIR = get_env("LOG_DIR", os.path.join(BASE_DIR, "logs"))
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "flasher.log")
LOG_MAX_SIZE = get_env("LOG_MAX_SIZE", 5 * 1024 * 1024)  # 5 MB
LOG_BACKUP_COUNT = get_env("LOG_BACKUP_COUNT", 5)  # Simpan 5 backup files

# ========== CHIP DETECTION ==========
CHIP_ID_REGISTRY: Dict[int, str] = {
    0x440: "STM32F030x4/x6/x8/xC",
    0x444: "STM32F030x4/x6/x8/xC (Rev 2)",
    0x412: "STM32F103x4/x6",
    0x410: "STM32F103x8/xB",
    0x414: "STM32F103xE/xG",
    0x430: "STM32F303x4/x6/x8",
    0x438: "STM32F303xB/xC/xD/xE",
    0x446: "STM32F303x6/x8",
    0x419: "STM32F407xE/xG",
    0x413: "STM32F405/415/407/417",
    0x423: "STM32F401xB/xC",
    0x431: "STM32F411xE",
    0x441: "STM32F412xG",
    0x421: "STM32F446xE/xG",
    0x434: "STM32F469/479",
    0x458: "STM32L053x6/x8",
    0x447: "STM32L073x8/xB",
    0x462: "STM32L476xx",
    0x415: "STM32L4R5/S5",
    0x449: "STM32L4R7/S7",
    0x457: "STM32L4R9/S9",
    0x468: "STM32G0B0/GB0",
    0x466: "STM32G031/041",
    0x461: "STM32G431/441",
    0x470: "STM32G471/473/483/491",
    0x480: "STM32G4A1",
    0x450: "STM32H743/753",
    0x483: "STM32H7A3/7B3",
    0x451: "STM32L496/4A6",
    0x482: "STM32WB55xx",
}

DEFAULT_CHIP_ID = 0x414  # STM32F103xE/xG

# ========== BOOTLOADER COMMANDS ==========
BOOTLOADER_CMD = {
    "INIT": 0x7F,
    "GET": 0x00,
    "GET_VERSION": 0x01,
    "GET_ID": 0x02,
    "READ_MEMORY": 0x11,
    "GO": 0x21,
    "WRITE_MEMORY": 0x31,
    "ERASE_MEMORY": 0x43,
    "EXTENDED_ERASE": 0x44,
    "WRITE_PROTECT": 0x63,
    "WRITE_UNPROTECT": 0x73,
    "READOUT_PROTECT": 0x82,
    "READOUT_UNPROTECT": 0x92,
    "SPEED": 0x04,
}

# ========== DFU CONFIG ==========
DFU_VID_PID: List[tuple] = [
    (0x0483, 0xDF11),  # STM32 DFU
    (0x0483, 0x3748),  # STM32 DFU (some variants)
    (0x0483, 0x374B),  # STM32L DFU
]

# ========== ST-LINK CONFIG ==========
STLINK_VID_PID: List[tuple] = [
    (0x0483, 0x3748),  # ST-Link/V2
    (0x0483, 0x374B),  # ST-Link/V2-1
    (0x0483, 0x3752),  # ST-Link/V3
]

# ========== RECOVERY ==========
RECOVERY_METHODS: List[str] = [
    "Force Bootloader (BOOT0=HIGH)",
    "DFU Mode (USB)",
    "ST-Link Unbrick",
    "Erase All Flash",
    "Low-Level Recovery",
]

# ========== NST ANDROID CONFIG ==========
ANDROID_PARTITIONS = ["boot", "recovery", "system", "vendor", "product", "dtbo", "vbmeta", "efs", "persist", "cache"]
FASTBOOT_PARTITIONS = ["boot", "recovery", "system", "vendor", "product", "dtbo"]

# ========== NST IPHONE CONFIG ==========
APPLE_VID = 0x05AC
IPHONE_MODEL_DATABASE = {
    "iPhone1,1": "iPhone (Original)",
    "iPhone2,1": "iPhone 3G",
    "iPhone3,1": "iPhone 4",
    "iPhone4,1": "iPhone 4S",
    "iPhone5,1": "iPhone 5",
    "iPhone6,1": "iPhone 5S",
    "iPhone7,2": "iPhone 6",
    "iPhone8,1": "iPhone 6S",
    "iPhone8,2": "iPhone 6S Plus",
    "iPhone9,1": "iPhone 7",
    "iPhone9,3": "iPhone 7",
    "iPhone10,1": "iPhone 8",
    "iPhone10,3": "iPhone X",
    "iPhone10,6": "iPhone X (Global)",
    "iPhone11,8": "iPhone XR",
    "iPhone12,1": "iPhone 11",
    "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max",
    "iPhone13,1": "iPhone SE (2nd gen)",
    "iPhone13,2": "iPhone 12",
    "iPhone13,3": "iPhone 12 Pro",
    "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,2": "iPhone 13 Pro",
    "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,4": "iPhone 13 Mini",
    "iPhone14,5": "iPhone 13",
    "iPhone14,6": "iPhone SE (3rd gen)",
    "iPhone15,2": "iPhone 14 Pro",
    "iPhone15,3": "iPhone 14 Pro Max",
    # iPhone 15 Series
    "iPhone15,4": "iPhone 15",
    "iPhone15,5": "iPhone 15 Plus",
    "iPhone16,1": "iPhone 15 Pro",
    "iPhone16,2": "iPhone 15 Pro Max",
    # iPhone 16 Series
    "iPhone17,1": "iPhone 16",
    "iPhone17,2": "iPhone 16 Plus",
    "iPhone17,3": "iPhone 16 Pro",
    "iPhone17,4": "iPhone 16 Pro Max",
    "iPhone17,5": "iPhone 16e",
}

# ========== DEVICE COMPATIBILITY DATABASE ==========
COMPATIBILITY_DB_PATH = get_env("COMPATIBILITY_DB_PATH", os.path.join(BASE_DIR, "device_compatibility.json"))

# ========== REPORT CONFIG ==========
REPORT_DIR = get_env("REPORT_DIR", os.path.join(BASE_DIR, "reports"))
os.makedirs(REPORT_DIR, exist_ok=True)
REPORT_DAYS_TO_KEEP = get_env("REPORT_DAYS_TO_KEEP", 30)  # Auto-delete reports older than N days

# ========== BACKUP CONFIG ==========
BACKUP_DIR = get_env("BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
os.makedirs(BACKUP_DIR, exist_ok=True)
MAX_BACKUPS_KEEP = get_env("MAX_BACKUPS_KEEP", 10)  # Max number of backups to keep


# ========== DEVICE-SPECIFIC DOWNLOAD LINKS ==========
# Database link download berdasarkan merk/model device
DEVICE_DOWNLOAD_LINKS = {
    "samsung": {
        "firmware": "https://samfw.com/",
        "odin": "https://odindownload.com/",
        "driver": "https://developer.samsung.com/android-usb-driver",
        "pit": "https://samfw.com/pit",
        "frp_tool": "https://samfw.com/frp-tool",
    },
    "xiaomi": {
        "firmware": "https://xiaomifirmwareupdater.com/",
        "mi_flash": "https://xiaomifirmwareupdater.com/tools/",
        "driver": "https://developer.xiaomi.com/",
        "unlock_tool": "https://en.miui.com/unlock/",
        "frp_tool": "https://xiaomitools.com/",
    },
    "oppo": {
        "firmware": "https://oppofirmware.com/",
        "driver": "https://www.oppo.com/en/support/",
    },
    "vivo": {
        "firmware": "https://vivofirmware.com/",
        "driver": "https://www.vivo.com/en/support",
    },
    "realme": {
        "firmware": "https://realmeupdater.com/",
        "driver": "https://www.realme.com/support/",
    },
    "oneplus": {
        "firmware": "https://onepluscommunity.com/",
        "driver": "https://www.oneplus.com/support/",
        "unlock_tool": "https://oneplus.com/unlock_bootloader",
    },
    "google_pixel": {
        "firmware": "https://developers.google.com/android/images",
        "driver": "https://developer.android.com/studio/run/win-usb",
    },
    "motorola": {
        "firmware": "https://motostockrom.com/",
        "driver": "https://en-us.support.motorola.com/",
    },
    "lg": {
        "firmware": "https://lg-firmwares.com/",
        "driver": "https://www.lg.com/us/support/",
    },
    "asus": {
        "firmware": "https://asus-zenfone.com/",
        "driver": "https://www.asus.com/support/",
    },
    "nokia": {
        "firmware": "https://nokiafirmware.com/",
        "driver": "https://www.nokia.com/phones/support/",
    },
    "sony": {
        "firmware": "https://xpericheck.com/",
        "driver": "https://www.sony.com/electronics/support/",
    },
    "huawei": {
        "firmware": "https://huaweifirmware.com/",
        "driver": "https://consumer.huawei.com/en/support/",
    },
    "mediatek": {
        "driver": "https://spflashtool.com/",
        "sp_flash_tool": "https://spflashtool.com/",
    },
    "qualcomm": {
        "driver": "https://qpsttool.com/",
        "qpst": "https://qpsttool.com/",
    },
    "apple": {
        "itunes": "https://www.apple.com/itunes/download/",
        "driver": "https://support.apple.com/downloads/",
        "firmware": "https://ipsw.me/",
        "3utools": "https://www.3u.com/",
        "idevice": "https://libimobiledevice.org/",
    },
}

# ========== ERROR SOLUTION DATABASE ==========
# Solusi untuk setiap error yang mungkin terjadi
ERROR_SOLUTIONS = {
    "device_not_found": {
        "error": "Device tidak terdeteksi",
        "solutions": [
            "1. Pastikan kabel USB berfungsi (ganti kabel jika perlu)",
            "2. Install driver USB yang sesuai:",
            "   - Android: developer.android.com/studio/run/win-usb",
            "   - Samsung: developer.samsung.com/android-usb-driver",
            "   - iPhone: www.apple.com/itunes/download/",
            "3. Aktifkan USB Debugging di Developer Options (Android)",
            "4. Coba port USB lain di komputer",
            "5. Restart ADB: adb kill-server && adb start-server",
            "6. Ganti kabel USB (kabel data, bukan charger-only)",
        ]
    },
    "adb_not_found": {
        "error": "ADB tidak terinstall/tidak ditemukan",
        "solutions": [
            "1. Download platform-tools: developer.android.com/tools/releases/platform-tools",
            "2. Extract ke folder, tambahkan ke PATH",
            "3. Atau jalankan dari folder platform-tools",
            "4. Install via: sudo apt install adb (Linux)",
            "5. Install via: brew install android-platform-tools (Mac)",
        ]
    },
    "fastboot_not_found": {
        "error": "Fastboot tidak terinstall",
        "solutions": [
            "1. Download platform-tools (sudah include fastboot)",
            "2. Link: developer.android.com/tools/releases/platform-tools",
        ]
    },
    "flash_failed": {
        "error": "Proses flashing gagal",
        "solutions": [
            "1. Periksa koneksi USB (jangan goyang-goyang selama flash)",
            "2. Pastikan battery > 30%",
            "3. Coba ulang proses dari awal",
            "4. Gunakan mode fastboot/EDL yang berbeda",
            "5. Coba firmware versi lain",
            "6. Jika terus gagal, mungkin IC flash rusak fisik",
        ]
    },
    "bootloader_locked": {
        "error": "Bootloader terkunci - tidak bisa flash partisi sistem",
        "solutions": [
            "1. Buka bootloader dulu (akan hapus semua data!)",
            "2. Samsung: Buka OEM Unlock di Developer Options",
            "3. Xiaomi: Minta unlock code di en.miui.com/unlock/",
            "4. Google Pixel: fastboot flashing unlock",
            "5. HTC/OnePlus: fastboot oem unlock",
        ]
    },
    "battery_low": {
        "error": "Battery terlalu rendah untuk flashing",
        "solutions": [
            "1. Charge battery hingga > 50%",
            "2. Gunakan power supply eksternal",
            "3. Jangan flash dengan battery < 20% - risiko brick!",
        ]
    },
    "device_bricked": {
        "error": "Device dalam keadaan brick (mati total)",
        "solutions": [
            "1. Coba force restart: Vol Up + Power 15 detik",
            "2. Coba masuk Recovery: Vol Up + Power + Home",
            "3. Coba Download Mode (Samsung): Vol Down + Power + Home",
            "4. Coba EDL Mode (Qualcomm): Test Point + USB",
            "5. Coba BROM (MediaTek): Colok USB tanpa battery",
            "6. Jika semua gagal: butuh programmer/repair fisik",
        ]
    },
    "permission_denied": {
        "error": "Izin ditolak (Linux/Mac)",
        "solutions": [
            "1. Jalankan dengan sudo: sudo python main.py",
            "2. Atau tambahkan udev rules untuk akses USB",
        ]
    },
}

# ========== STEP-BY-STEP GUIDE DATABASE ==========
STEP_BY_STEP_GUIDES = {
    "unlock_bootloader": {
        "title": "PANDUAN UNLOCK BOOTLOADER",
        "warning": "UNLOCK BOOTLOADER AKAN MENGHAPUS SEMUA DATA!\nBuat backup dulu!",
        "steps": [
            "LANGKAH 1: Backup semua data penting",
            "  - Foto, kontak, pesan, dokumen",
            "  - Catat IMEI: Dial *#06#",
            "",
            "LANGKAH 2: Aktifkan Developer Options",
            "  - Settings > About Phone > Tap 'Build Number' 7x",
            "  - Settings > Developer Options > OEM Unlock = ON",
            "  - Settings > Developer Options > USB Debugging = ON",
            "",
            "LANGKAH 3: Boot ke Fastboot/Bootloader",
            "  - Hubungkan HP ke PC via USB",
            "  - Jalankan: adb reboot bootloader",
            "  - Atau manual: matikan HP, tekan Vol Down + Power",
            "",
            "LANGKAH 4: Eksekusi Unlock",
            "  - fastboot oem unlock  (untuk HTC/OnePlus/Motorola)",
            "  - fastboot flashing unlock  (untuk Google/Pixel)",
            "  - fastboot oem unlock [kode]  (Samsung perlu kode)",
            "",
            "LANGKAH 5: Konfirmasi di HP",
            "  - Tekan Volume Up untuk confirm",
            "  - HP akan restart dan factory reset",
            "",
            "LANGKAH 6: Verifikasi",
            "  - Setelah boot, cek: fastboot oem device-info",
            "  - Atau: adb shell getprop ro.boot.flash.locked",
        ],
        "links": [
            "Link unlock Xiaomi: en.miui.com/unlock/",
            "Tool Samsung: odindownload.com",
        ]
    },
    "flash_firmware": {
        "title": "PANDUAN FLASH FIRMWARE",
        "warning": "FLASHING SALAH BISA BRICK! Pastikan firmware cocok dengan device!",
        "steps": [
            "LANGKAH 1: Backup data penting",
            "  - Semua data akan terhapus saat flashing",
            "  - Backup ke PC atau cloud dulu",
            "",
            "LANGKAH 2: Download firmware yang tepat",
            "  - Cari firmware sesuai model HP ANDA",
            "  - Cek build number di Settings > About Phone",
            "  - Jangan download firmware untuk model berbeda!",
            "",
            "LANGKAH 3: Siapkan tools",
            "  - Samsung: Odin3 (odindownload.com)",
            "  - Xiaomi: Mi Flash Tool (xiaomifirmwareupdater.com)",
            "  - Generic: fastboot flash",
            "",
            "LANGKAH 4: Boot ke mode flashing",
            "  - Samsung: Vol Down + Power + Home (Download Mode)",
            "  - Xiaomi: Vol Down + Power (Fastboot)",
            "  - Google: adb reboot bootloader",
            "",
            "LANGKAH 5: Flash firmware",
            "  - Samsung: Buka Odin, load firmware, klik Start",
            "  - Xiaomi: Buka Mi Flash, pilih folder, klik Flash",
            "  - Fastboot: fastboot flash system system.img (dll)",
            "",
            "LANGKAH 6: Tunggu selesai",
            "  - Jangan cabut USB selama proses!",
            "  - HP akan restart otomatis",
            "  - First boot mungkin 5-15 menit",
        ],
        "links": []
    },
    "factory_reset": {
        "title": "PANDUAN FACTORY RESET",
        "warning": "SEMUA DATA AKAN TERHAPUS! Backup dulu!",
        "steps": [
            "LANGKAH 1: Backup data penting",
            "  - Foto, kontak, chat, dokumen",
            "  - Catat password akun Google/Apple",
            "",
            "LANGKAH 2: Method via Settings (jika HP masih nyala)",
            "  - Settings > System > Reset > Factory Reset",
            "  - Atau Settings > General Management > Reset",
            "  - Konfirmasi dengan PIN/password",
            "",
            "LANGKAH 3: Method via Recovery (jika HP error)",
            "  - Matikan HP",
            "  - Tekan: Vol Up + Power (atau kombinasi brand)",
            "  - Pilih 'Wipe data/factory reset'",
            "  - Pilih 'Yes - delete all user data'",
            "  - Reboot system now",
            "",
            "LANGKAH 4: Via ADB (jika USB Debugging aktif)",
            "  - adb reboot recovery",
            "  - Atau: adb shell recovery --wipe_data",
            "",
            "LANGKAH 5: Setelah reset",
            "  - HP akan restart dan masuk setup wizard",
            "  - Login dengan akun Google FRP",
            "  - Jangan lupa restore backup",
        ],
        "links": []
    },
    "clean_cache": {
        "title": "PANDUAN BERSIHKAN CACHE",
        "steps": [
            "Method 1: Via Recovery",
            "  1. Matikan HP",
            "  2. Masuk Recovery Mode (Vol Up + Power)",
            "  3. Pilih 'Wipe cache partition'",
            "  4. Reboot system",
            "",
            "Method 2: Via ADB (Deep Clean)",
            "  1. Hubungkan HP via USB (USB Debugging ON)",
            "  2. adb shell",
            "  3. su (jika rooted)",
            "  4. rm -rf /cache/*",
            "  5. rm -rf /data/dalvik-cache/*",
            "  6. rm -rf /data/app/*/cache/*",
            "  7. reboot",
            "",
            "Method 3: Via Settings (soft clean)",
            "  1. Settings > Storage > Cached data",
            "  2. Tap 'Clear cached data'",
            "",
            "Method 4: Clean Cache per App",
            "  1. Settings > Apps > [Pilih App]",
            "  2. Storage > Clear Cache",
            "  (Lakukan untuk app besar: Chrome, IG, WA, FB)",
        ],
        "links": []
    },
    "root": {
        "title": "PANDUAN ROOT ANDROID",
        "warning": "ROOT AKAN: Menghapus garansi, Mematikan beberapa app (banking)!",
        "steps": [
            "LANGKAH 1: Unlock Bootloader dulu",
            "  - Buka OEM Unlock di Developer Options",
            "  - fastboot flashing unlock",
            "  - (Semua data akan terhapus!)",
            "",
            "LANGKAH 2: Download file root",
            "  - Magisk: github.com/topjohnwu/Magisk/releases",
            "  - Atau TWRP: twrp.me/Devices/",
            "",
            "LANGKAH 3: Flash via fastboot (metode Magisk)",
            "  - adb push magisk.apk /sdcard/",
            "  - adb reboot recovery",
            "  - Install via TWRP atau boot patched boot.img",
            "",
            "LANGKAH 4: Install Magisk Manager",
            "  - Buka Magisk app",
            "  - Cek: Install > Direct Install",
            "  - Reboot",
            "",
            "LANGKAH 5: Verifikasi root",
            "  - Buka Magisk: harus ada 'Installed'",
            "  - Buka app root checker",
        ],
        "links": [
            "Magisk: github.com/topjohnwu/Magisk",
            "TWRP: twrp.me",
        ]
    },
}

# ========== EMERGENCY RECOVERY CONFIG ==========
EMERGENCY_CONFIG = {
    "auto_kill_adb": True,
    "auto_restart_adb": True,
    "clean_temp": True,
    "reset_usb": False,  # Hati-hati: bisa reset semua USB
    "timeout_seconds": 30,
}

# ========== FIRMWARE VERIFY CONFIG ==========
FIRMWARE_VERIFY_CONFIG = {
    "min_size_mb": 10,
    "check_md5": True,
    "check_structure": True,
    "check_disk_space": True,
    "allowed_extensions": [".img", ".tar", ".md5", ".zip", ".bin", ".elf", ".hex", ".pac", ".kdz", ".nb0"],
}

# ========== PLUGIN SYSTEM CONFIG ==========
PLUGIN_DIR = get_env("PLUGIN_DIR", os.path.join(BASE_DIR, "plugins"))
PLUGIN_AUTO_LOAD = get_env("PLUGIN_AUTO_LOAD", True)  # Auto-load plugins on startup
PLUGIN_ENABLE_HOT_RELOAD = get_env("PLUGIN_ENABLE_HOT_RELOAD", False)

# Daftar plugin yang di-disable (tidak di-load)
PLUGIN_BLACKLIST: List[str] = []

# ========== EXTERNAL TOOLS CONFIG ==========
EXTERNAL_TOOLS_PATH = get_env("EXTERNAL_TOOLS_PATH", os.path.join(BASE_DIR, "tools"))
os.makedirs(EXTERNAL_TOOLS_PATH, exist_ok=True)

# Tool binary names (dicari di PATH dan di tools/ folder)
EXTERNAL_TOOL_BINARIES = {
    "mtkclient": "mtk",
    "heimdall": "heimdall",
    "libimobiledevice": "idevice_id",
    "edl": "edl",  # open-source Qualcomm EDL tool
    "idevicerestore": "idevicerestore",
    "irecovery": "irecovery",
    "ideviceinfo": "ideviceinfo",
    "idevicebackup": "idevicebackup2",
    "ideviceenterrecovery": "ideviceenterrecovery",
    "usbmuxd": "usbmuxd",
}

# QPST paths (Windows only)
QPST_PATHS = [
    r"C:\Program Files (x86)\Qualcomm\QPST\bin\QFIL.exe",
    r"C:\Program Files\Qualcomm\QPST\bin\QFIL.exe",
]

# Tool timeout konfigurasi (detik)
TOOL_TIMEOUTS = {
    "default": 30,
    "flash": 300,
    "backup": 600,
    "restore": 600,
    "detect": 15,
    "info": 10,
    "list": 5,
}

# ========== DEVICE MODE SCANNER CONFIG ==========
MODE_SCAN_TIMEOUT = get_env("MODE_SCAN_TIMEOUT", 3)  # detik per mode scan
MODE_DETECT_INTERVAL = get_env("MODE_DETECT_INTERVAL", 2.0)  # detik auto-detect interval
MODE_CACHE_TTL = get_env("MODE_CACHE_TTL", 5.0)  # detik cache detection results

# ========== QUEUE / BUSY CONFIG ==========
BUSY_FLAG = False  # Global flag untuk mencegah command tabrakan
COMMAND_QUEUE = []  # Queue untuk command berurutan

# ========== DEEP DIAGNOSTIC THRESHOLDS ==========
DIAGNOSTIC_THRESHOLDS = {
    "current_no_charge": 0.00,  # Ampere 0 = no power
    "current_low": 0.10,  # Ampere < 0.1A = power issue
    "current_normal_min": 0.30,  # Normal charging min
    "current_normal_max": 1.50,  # Normal charging max
    "voltage_dead": 0.0,  # Battery truly dead
    "voltage_critical": 3.2,  # Critical low voltage
    "voltage_low": 3.4,  # Low voltage
    "voltage_normal_min": 3.7,  # Normal voltage
    "voltage_full": 4.2,  # Full charge
    "cache_critical_gb": 5.0,  # > 5GB cache = perlu bersihkan
    "battery_flash_min": 30,  # Min battery % for flashing
    "disk_space_min_mb": 200,  # Min disk space
}
