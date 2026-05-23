"""
NST ULTIMATE CONSOLE v3.2 - Main Entry Point
"""
import os
import sys
import platform

# Pastikan working directory = folder project
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from config import APP_NAME, VERSION, SUBVERSION, AUTHOR, BUSY_FLAG, COMMAND_QUEUE
from core.logger import log, Colors
from core.safety import ActionLogger


def _check_admin_windows():
    if platform.system() != "Windows":
        return True
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not is_admin:
            print(f"\n  {Colors.BG_RED}{Colors.BOLD}  PERINGATAN: Jalankan sebagai ADMINISTRATOR!  {Colors.RESET}")
            print(f"  {Colors.YELLOW}Beberapa fitur butuh admin rights.{Colors.RESET}\n")
        return is_admin
    except Exception:
        return True


def print_header():
    log.print_banner()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 56}{Colors.RESET}")
    print(f"  {Colors.BOLD}{Colors.BRIGHT_CYAN}  {APP_NAME} v{VERSION} - {SUBVERSION}{Colors.RESET}")
    print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 56}{Colors.RESET}")
    print(f"  {Colors.DIM}  Author: {AUTHOR} | Safety berlapis | Plugin system{Colors.RESET}")
    print(f"  {Colors.BOLD}{Colors.BRIGHT_WHITE}{'=' * 56}{Colors.RESET}")


def print_main_menu():
    print_header()

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_GREEN}[STM32 FLASHER SUITE]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.GREEN} 1.{Colors.RESET}  Flash STM32          Flash firmware via UART/DFU/ST-Link")
    print(f"  {Colors.GREEN} 2.{Colors.RESET}  Diagnostic STM32     Deteksi chip, test koneksi, read flash")
    print(f"  {Colors.GREEN} 3.{Colors.RESET}  Anti-Brick STM32     Recovery & unbrick (5 metode)")
    print(f"  {Colors.GREEN} 4.{Colors.RESET}  Driver Doctor        Scan & install driver STM32 + Apple")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_YELLOW}[NST ANDROID SUITE]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.YELLOW} 5.{Colors.RESET}  Smart Diagnostic     Analisa hardware & software mendalam")
    print(f"  {Colors.YELLOW} 6.{Colors.RESET}  Clean Cache          Bersihkan semua sampah (+ deep clean)")
    print(f"  {Colors.YELLOW} 7.{Colors.RESET}  Flash Firmware       Panduan step-by-step + link download")
    print(f"  {Colors.YELLOW} 8.{Colors.RESET}  Unlock Bootloader    Panduan + eksekusi via fastboot")
    print(f"  {Colors.YELLOW} 9.{Colors.RESET}  Root Android         Panduan root + link download")
    print(f"  {Colors.YELLOW}10.{Colors.RESET}  FRP Bypass Guide     5 metode FRP bypass")
    print(f"  {Colors.YELLOW}11.{Colors.RESET}  Factory Reset        Reset aman + backup otomatis")
    print(f"  {Colors.YELLOW}12.{Colors.RESET}  Scan Device Info     Baca info lengkap via ADB/fastboot")
    print(f"  {Colors.YELLOW}13.{Colors.RESET}  Root Checker         Cek status root device")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_CYAN}[NST IPHONE SUITE]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.CYAN}14.{Colors.RESET}  Apple Full Scan       Ecosystem scan (driver, USB, services)")
    print(f"  {Colors.CYAN}15.{Colors.RESET}  Quick Driver Check    Cepat cek Apple driver registry")
    print(f"  {Colors.CYAN}16.{Colors.RESET}  Mode Guide            Panduan Recovery/DFU mode")
    print(f"  {Colors.CYAN}17.{Colors.RESET}  Battery Guide         Cek cycle count & health")
    print(f"  {Colors.CYAN}18.{Colors.RESET}  Activation Lock       Panduan cek iCloud lock")
    print(f"  {Colors.CYAN}19.{Colors.RESET}  Install Driver        Panduan install driver Apple")
    print(f"  {Colors.CYAN}20.{Colors.RESET}  Port Verification     Cek port komunikasi Apple/MTK/QC")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_BLUE}[SYSTEM TOOLS]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.BLUE}21.{Colors.RESET}  Device Scan           Deteksi semua perangkat terhubung")
    print(f"  {Colors.BLUE}22.{Colors.RESET}  Device Detail         Info detail perangkat terdeteksi")
    print(f"  {Colors.BLUE}23.{Colors.RESET}  Device Monitor        Pantau koneksi real-time (CTRL+C)")
    print(f"  {Colors.BLUE}24.{Colors.RESET}  Check Tools           Cek ADB, fastboot, dependencies")
    print(f"  {Colors.BLUE}25.{Colors.RESET}  Install Deps          Install dependencies yang hilang")
    print(f"  {Colors.BLUE}26.{Colors.RESET}  System Info           OS, Python, PATH, hardware")
    print(f"  {Colors.BLUE}27.{Colors.RESET}  Report Manager        Lihat, buka, hapus report")
    print(f"  {Colors.BLUE}28.{Colors.RESET}  Safety History        Riwayat aksi & backup manager")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_RED}[SAFETY & RECOVERY]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.RED}29.{Colors.RESET}  Restore from Backup  Pulihkan device dari backup")
    print(f"  {Colors.RED}30.{Colors.RESET}  Backup Now           Backup full semua partisi + data")
    print(f"  {Colors.RED}31.{Colors.RESET}  Create Shortcut      Buat Near Cell System di desktop")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_RED}[EMERGENCY & TOOLS]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.RED}32.{Colors.RESET}  Emergency Recovery  Full: Kill ADB, USB, temp, scan")
    print(f"  {Colors.RED}33.{Colors.RESET}  Kill ADB Zombie     Matikan proses ADB/Fastboot yang hang")
    print(f"  {Colors.RED}34.{Colors.RESET}  Restart ADB Server  Restart ADB server dari awal")
    print(f"  {Colors.RED}35.{Colors.RESET}  Clean Temp Files    Bersihkan file temporary sistem")
    print(f"  {Colors.RED}36.{Colors.RESET}  Reset USB Ports     Reset port USB via devcon/PowerShell")
    print(f"  {Colors.RED}37.{Colors.RESET}  Kill Apple Procs    Matikan proses Apple yang hang")
    print(f"  {Colors.RED}38.{Colors.RESET}  Firmware Verify     MD5/struktur firmware sebelum flash")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_MAGENTA}[PLUGIN SYSTEM]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.MAGENTA}39.{Colors.RESET}  Plugin Manager      Lihat status & kelola plugin terpasang")
    print(f"  {Colors.MAGENTA}40.{Colors.RESET}  Plugin Scan         Deteksi device dari SEMUA plugin")
    print(f"  {Colors.MAGENTA}41.{Colors.RESET}  Plugin Reload       Hot-reload semua plugin")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_YELLOW}[MODE SCANNER]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.YELLOW}42.{Colors.RESET}  Mode Scan (Full)    USB + tools — deteksi SEMUA mode device")
    print(f"  {Colors.YELLOW}43.{Colors.RESET}  Mode Scan (Fast)    USB VID/PID only — cepat")
    print(f"  {Colors.YELLOW}44.{Colors.RESET}  Mode Monitor        Pantau device connection real-time")
    print(f"  {Colors.YELLOW}45.{Colors.RESET}  Mode Info           Info database mode scanner + tools")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_CYAN}[EXTERNAL TOOLS]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.CYAN}46.{Colors.RESET}  External Tools Status  Cek mtkclient, heimdall, libimobiledevice")
    print(f"  {Colors.CYAN}47.{Colors.RESET}  External Tools Guide   Panduan install semua external tools")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_RED}[VALIDATION & SIMULATION]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.RED}51.{Colors.RESET}  Device Validator      Validasi 7 aspek device sebelum flash")
    print(f"  {Colors.RED}52.{Colors.RESET}  Flash Simulation      Simulasi flashing (analisis + risk)")
    print(f"  {Colors.RED}53.{Colors.RESET}  Auto Driver Repair    Repair ADB, Fastboot, USB drivers")
    print(f"  {Colors.RED}54.{Colors.RESET}  Smart Anti-Brick      Diagnosa brick + auto recovery")

    print()
    print(f"  {Colors.BOLD}{Colors.BRIGHT_CYAN}[DEVICE DATABASE]{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.CYAN}55.{Colors.RESET}  Device Profile DB     Cari device, partition, auth, test point")
    print(f"  {Colors.CYAN}56.{Colors.RESET}  DB Statistics         Statistik database device")

    print()
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  {Colors.CYAN}48.{Colors.RESET}  About                Info aplikasi, kredit, changelog")
    print(f"  {Colors.BRIGHT_GREEN}49.{Colors.RESET}  Launch GUI Desktop  Buka antarmuka grafis modern")
    print(f"  {Colors.BRIGHT_GREEN}50.{Colors.RESET}  Check Update        Cek versi terbaru dari GitHub")
    print(f"  {Colors.RED} 0.{Colors.RESET}  Exit                 Keluar program")
    print(f"  {Colors.DIM}{'=' * 56}{Colors.RESET}")


# =====================================================================
# FUNGSI EKSEKUSI — STM32 Suite
# =====================================================================
def run_flasher():
    from core.flasher import run
    run()

def run_diagnostic():
    from core.diagnostic import run
    run()

def run_anti_brick():
    from core.anti_brick import run
    run()

def run_driver_doctor():
    from core.driver_doctor import run
    run()

# =====================================================================
# FUNGSI EKSEKUSI — Android Suite
# =====================================================================
def run_android_diagnostic():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_1_smart_diagnostic()

def run_android_clean_cache():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_2_clean_cache()

def run_android_flash():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_3_flash_firmware()

def run_android_unlock():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_4_unlock_bootloader()

def run_android_root():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_5_root()

def run_android_frp():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_6_frp_bypass()

def run_android_reset():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_7_factory_reset()

def run_android_scan():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_8_scan_device()

def run_android_root_check():
    from core.nst_android import AndroidToolkit
    AndroidToolkit().fitur_9_root_checker()

# =====================================================================
# FUNGSI EKSEKUSI — iPhone Suite
# =====================================================================
def run_iphone_full_scan():
    from core.nst_iphone import NSTiPhone
    NSTiPhone().scan_apple_drivers()

def run_iphone_driver_check():
    from core.nst_iphone import NSTiPhone
    NSTiPhone().quick_driver_check()

def run_iphone_mode_guide():
    from core.nst_iphone import NSTiPhone
    NSTiPhone().show_mode_guide()

def run_iphone_battery_guide():
    from core.nst_iphone import NSTiPhone
    NSTiPhone().show_battery_guide()

def run_iphone_activation_check():
    from core.nst_iphone import NSTiPhone
    NSTiPhone().activation_check_guide()

def run_iphone_install_guide():
    from core.nst_iphone import NSTiPhone
    NSTiPhone().show_install_guide()

def run_iphone_port_verify():
    from core.nst_iphone import NSTiPhone
    log.header("[PORT VERIFICATION]")
    if NSTiPhone().verifikasi_port_komunikasi():
        log.success("Port komunikasi: OK (Apple/MTK/QC/USB Serial terdeteksi)")
    else:
        log.warning("Port komunikasi: Tidak terdeteksi")

# =====================================================================
# FUNGSI EKSEKUSI — Device Detector
# =====================================================================
def run_device_scan():
    from core.device_detector import DeviceDetector
    DeviceDetector().scan_all()

def run_device_detail():
    from core.device_detector import DeviceDetector
    DeviceDetector().show_device_info()

def run_device_monitor():
    from core.device_detector import DeviceDetector
    DeviceDetector().monitor_mode()

# =====================================================================
# FUNGSI EKSEKUSI — Environment
# =====================================================================
def run_env_check():
    from core.environment import EnvironmentChecker
    EnvironmentChecker().check_all()

def run_env_install():
    from core.environment import EnvironmentChecker
    EnvironmentChecker().install_missing()

def run_env_sysinfo():
    from core.environment import EnvironmentChecker
    EnvironmentChecker().show_system_info()

# =====================================================================
# FUNGSI EKSEKUSI — Report & Safety
# =====================================================================
def run_report_manager():
    from core.reporter import ReportGenerator
    ReportGenerator.show_reports()

def show_safety_history():
    from core.safety import ActionLogger, BackupManager
    print()
    ActionLogger.show_history(limit=15)
    print()
    log.info("Backup Manager:")
    backups = BackupManager.list_backups()
    if backups:
        for b in backups[:5]:
            print(f"  {Colors.DIM}- {b['name']}{Colors.RESET} ({b['size_mb']} MB, {b['modified']})")
    else:
        print(f"  {Colors.DIM}Belum ada backup{Colors.RESET}")

def run_restore_backup():
    from core.safety import BackupManager, ConfirmationChain, ActionLogger, PreFlightCheck
    import json
    log.header("[RESTORE FROM BACKUP]")
    backup_manifest = BackupManager.find_latest_backup()
    if not backup_manifest:
        log.warning("Tidak ada backup yang tersedia!")
        log.info("Lakukan backup dulu via menu Backup Now.")
        return
    try:
        with open(backup_manifest, 'r') as f:
            data = json.load(f)
        log.info(f"Backup ditemukan: {os.path.basename(backup_manifest)}")
        log.info(f"Waktu backup: {data.get('timestamp', 'unknown')}")
    except Exception:
        pass
    print()
    log.warning("RESTORE AKAN MENGEMBALIKAN DEVICE KE KEADAAN SEBELUMNYA!")
    if not ConfirmationChain.confirm_action(
        "Restore Device",
        "Restore akan mengembalikan backup partisi.",
        "RESTORE INI AKAN MENGEMBALIKAN DEVICE!",
        True
    ):
        return
    device = PreFlightCheck.check_device_connection()
    serial = device.get("serial") if device.get("ok") else None
    if not serial:
        log.warning("Device tidak terdeteksi. Restore butuh ADB.")
        return
    log.info(f"Memulai restore untuk device: {serial}")
    BackupManager.auto_restore(serial, backup_manifest)
    ActionLogger.log("RESTORE BACKUP", "SUCCESS", f"From: {backup_manifest}")

def run_backup_now():
    from core.safety import BackupManager, ConfirmationChain, PreFlightCheck, ActionLogger
    log.header("[BACKUP FULL OTOMATIS]")
    device = PreFlightCheck.check_device_connection()
    serial = device.get("serial") if device.get("ok") else None
    if not serial:
        log.warning("Device tidak terdeteksi!")
        log.info("Hubungkan HP via USB dengan USB Debugging ON.")
        return
    log.info(f"Device terdeteksi: {serial}")
    if not ConfirmationChain.confirm_simple("Mulai backup FULL semua partisi + data?", "n"):
        return
    BackupManager.auto_full_backup(serial)
    ActionLogger.log("BACKUP NOW", "SUCCESS", f"Device: {serial}")

def run_create_shortcut():
    log.header("[CREATE DESKTOP SHORTCUT]")
    try:
        from create_desktop_shortcut import create_windows_shortcut, create_near_cell_icon, create_linux_shortcut
        create_near_cell_icon()
        if platform.system() == "Windows":
            path = create_windows_shortcut()
        elif platform.system() == "Linux":
            path = create_linux_shortcut()
        else:
            log.warning("Mac OS: Buat shortcut manual via Automator")
            path = None
        if path:
            log.success(f"Shortcut dibuat: {path}")
        ActionLogger.log("CREATE SHORTCUT", "SUCCESS", "Near Cell System")
    except Exception as e:
        log.warning(f"Gagal buat shortcut: {e}")

# =====================================================================
# FUNGSI EKSEKUSI — Emergency
# =====================================================================
def run_emergency_recovery():
    from core.emergency import run_full_emergency
    run_full_emergency()

def run_kill_adb_zombie():
    from core.emergency import run_kill_adb_zombie as _fn
    _fn()

def run_restart_adb():
    from core.emergency import run_restart_adb as _fn
    _fn()

def run_clean_temp():
    from core.emergency import run_clean_temp as _fn
    _fn()

def run_reset_usb():
    from core.emergency import run_reset_usb as _fn
    _fn()

def run_kill_apple():
    from core.emergency import run_kill_apple as _fn
    _fn()

def run_firmware_verify():
    from core.firmware_verify import run
    run()

# =====================================================================
# FUNGSI EKSEKUSI — External Tools
# =====================================================================
def run_external_tools_status():
    log.header("[EXTERNAL TOOLS STATUS]")
    try:
        from core.external_tools import ToolManager, ToolStatus
        tm = ToolManager()
        status = tm.scan_all(force=True)
        icons = {
            ToolStatus.AVAILABLE: f"{Colors.GREEN}[OK]{Colors.RESET}",
            ToolStatus.NOT_FOUND: f"{Colors.RED}[X]{Colors.RESET}",
            ToolStatus.ERROR: f"{Colors.YELLOW}[!]{Colors.RESET}",
            ToolStatus.WRONG_VERSION: f"{Colors.YELLOW}[!]{Colors.RESET}",
            ToolStatus.NOT_INSTALLED: f"{Colors.RED}[X]{Colors.RESET}",
        }
        tool_names = {
            "mtkclient": "mtkclient (MediaTek BROM/DA)",
            "heimdall": "heimdall (Samsung Odin protocol)",
            "libimobiledevice": "libimobiledevice (Apple iPhone tools)",
            "qpst/edl": "EDL/Qualcomm (Flash tool for Snapdragon)",
        }
        print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
        for name, s in status.items():
            icon = icons.get(s, f"{Colors.DIM}?{Colors.RESET}")
            display_name = tool_names.get(name, name)
            print(f"  {icon} {display_name}")
        print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
        missing = [name for name, s in status.items() if s != ToolStatus.AVAILABLE]
        if missing:
            log.warning(f"Belum terinstall: {', '.join(missing)}")
            log.info("Gunakan menu 'External Tools Guide' untuk panduan install.")
    except Exception as e:
        log.warning(f"Gagal cek external tools: {e}")

def run_external_tools_guide():
    log.header("[EXTERNAL TOOLS GUIDE]")
    try:
        from core.external_tools import ToolManager
        tm = ToolManager()
        guide = tm.get_install_guides()
        print(f"  {guide}")
    except Exception as e:
        log.warning(f"Error: {e}")
        print(f"""
  {Colors.CYAN}1. mtkclient{Colors.RESET}: pip install mtkclient
  {Colors.CYAN}2. heimdall{Colors.RESET}: https://glassechidna.com.au/heimdall/
  {Colors.CYAN}3. libimobiledevice{Colors.RESET}: sudo apt install libimobiledevice-utils
  {Colors.CYAN}4. edl{Colors.RESET}: pip install edl
""")

def show_about():
    log.header(f"TENTANG {APP_NAME}")
    print(f"  {Colors.BOLD}{Colors.CYAN}{APP_NAME} v{VERSION} - {SUBVERSION}{Colors.RESET}")
    print(f"  {Colors.DIM}Author: {AUTHOR}{Colors.RESET}")
    print(f"  56 fitur | Plugin system | Safety berlapis | GUI + CLI")

def run_launch_gui():
    log.header("[LAUNCH GUI DESKTOP]")
    try:
        import importlib.util
        spec = importlib.util.find_spec("customtkinter")
        if spec is None:
            log.warning("CustomTkinter belum terinstall!")
            log.info("Install: pip install customtkinter")
            return
        import threading as _th
        from nst_gui import NSTGUI
        gui_thread = _th.Thread(target=lambda: NSTGUI().run(), daemon=True)
        gui_thread.start()
        log.success("GUI Desktop berhasil diluncurkan!")
    except Exception as e:
        log.warning(f"Gagal launch GUI: {e}")
        log.info("Install dulu: pip install customtkinter")

def run_check_update():
    log.header("[CHECK UPDATE]")
    try:
        from core.update_checker import UpdateInstaller
        installer = UpdateInstaller()
        installer.run_update_flow()
    except Exception as e:
        log.warning(f"Gagal cek update: {e}")

# =====================================================================
# FUNGSI EKSEKUSI — Plugin System
# =====================================================================
def run_plugin_manager():
    log.header("[PLUGIN MANAGER]")
    try:
        from plugins import PluginRegistry
        plugins = PluginRegistry.get_all_plugins()
        if not plugins:
            log.warning("Tidak ada plugin terdaftar.")
            log.info("Gunakan menu Plugin Reload untuk load plugin.")
            return
        print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
        print(f"  {Colors.BOLD}Total Plugin: {len(plugins)} terdaftar{Colors.RESET}")
        for p in plugins:
            print(f"  {Colors.MAGENTA}  {p.name}{Colors.RESET} v{p.version}")
            print(f"  {Colors.DIM}     {p.description[:80]}{Colors.RESET}")
        log.info(PluginRegistry.summary())
    except Exception as e:
        log.warning(f"Gagal load plugin: {e}")

def run_plugin_scan():
    log.header("[PLUGIN SCAN]")
    try:
        from plugins import PluginRegistry
        results = PluginRegistry.detect_plugins()
        total_devices = 0
        for plugin_name, devices in results.items():
            count = len(devices)
            color = Colors.GREEN if devices else Colors.YELLOW
            print(f"  {color}  [{plugin_name}]{Colors.RESET} {count} device terdeteksi")
            for dev in devices:
                print(f"  {Colors.DIM}    - {dev}{Colors.RESET}")
            total_devices += count
        log.success(f"Total: {total_devices} device terdeteksi dari {len(results)} plugin")
    except Exception as e:
        log.warning(f"Gagal scan plugin: {e}")

def run_plugin_reload():
    log.header("[PLUGIN RELOAD]")
    try:
        from plugins import PluginRegistry
        from plugins.loader import load_all_plugins
        PluginRegistry._plugins.clear()
        PluginRegistry._mode_map.clear()
        count = load_all_plugins()
        log.success(f"{count} plugin berhasil di-load!")
    except Exception as e:
        log.warning(f"Gagal reload plugin: {e}")

# =====================================================================
# FUNGSI EKSEKUSI — Mode Scanner
# =====================================================================
def run_mode_scan():
    from core.mode_scanner import run_mode_scan as _scan
    _scan()

def run_mode_fast():
    from core.mode_scanner import run_mode_fast as _fast
    _fast()

def run_mode_monitor():
    from core.mode_scanner import run_mode_monitor as _monitor
    _monitor()

def run_mode_info():
    from core.mode_scanner import run_mode_info as _info
    _info()

# =====================================================================
# FUNGSI EKSEKUSI — Validation & Simulation
# =====================================================================
def run_device_validator():
    from core.device_validator import DeviceStateValidator
    DeviceStateValidator().validate_all()

def run_flash_simulator():
    from core.flash_simulator import run_simulator
    run_simulator()

def run_auto_driver_repair():
    from core.driver_doctor import DriverDoctor
    from core.safety import ConfirmationChain
    doctor = DriverDoctor()
    doctor.scan_all()
    print()
    if doctor.missing_drivers or doctor.broken_drivers:
        if ConfirmationChain.confirm_simple("Mulai repair semua driver bermasalah?", "n"):
            doctor.repair_drivers()
    else:
        log.info("Semua driver dalam kondisi baik.")

def run_smart_anti_brick():
    from core.anti_brick import SmartAntiBrick
    from core.safety import ConfirmationChain
    sab = SmartAntiBrick()
    diagnosis = sab.diagnose()
    if diagnosis.detected:
        print()
        if ConfirmationChain.confirm_simple("Jalankan auto-recovery?", "n"):
            sab.auto_recover(diagnosis)

def run_device_profile():
    from core.device_database import run
    run()

def run_db_statistics():
    from core.device_database import run_stats
    run_stats()


# =====================================================================
# DISPATCH TABLE — semua menu 1-56
# =====================================================================
MENU_ACTIONS = {
    "1":  ("Flash STM32", run_flasher),
    "2":  ("Diagnostic STM32", run_diagnostic),
    "3":  ("Anti-Brick STM32", run_anti_brick),
    "4":  ("Driver Doctor", run_driver_doctor),
    "5":  ("Smart Diagnostic", run_android_diagnostic),
    "6":  ("Clean Cache", run_android_clean_cache),
    "7":  ("Flash Firmware", run_android_flash),
    "8":  ("Unlock Bootloader", run_android_unlock),
    "9":  ("Root Android", run_android_root),
    "10": ("FRP Bypass", run_android_frp),
    "11": ("Factory Reset", run_android_reset),
    "12": ("Scan Device", run_android_scan),
    "13": ("Root Checker", run_android_root_check),
    "14": ("Apple Full Scan", run_iphone_full_scan),
    "15": ("Quick Driver Check", run_iphone_driver_check),
    "16": ("Mode Guide", run_iphone_mode_guide),
    "17": ("Battery Guide", run_iphone_battery_guide),
    "18": ("Activation Check", run_iphone_activation_check),
    "19": ("Install Guide", run_iphone_install_guide),
    "20": ("Port Verification", run_iphone_port_verify),
    "21": ("Device Scan", run_device_scan),
    "22": ("Device Detail", run_device_detail),
    "23": ("Device Monitor", run_device_monitor),
    "24": ("Check Tools", run_env_check),
    "25": ("Install Deps", run_env_install),
    "26": ("System Info", run_env_sysinfo),
    "27": ("Report Manager", run_report_manager),
    "28": ("Safety History", show_safety_history),
    "29": ("Restore from Backup", run_restore_backup),
    "30": ("Backup Now", run_backup_now),
    "31": ("Create Shortcut", run_create_shortcut),
    "32": ("Emergency Recovery", run_emergency_recovery),
    "33": ("Kill ADB Zombie", run_kill_adb_zombie),
    "34": ("Restart ADB Server", run_restart_adb),
    "35": ("Clean Temp Files", run_clean_temp),
    "36": ("Reset USB Ports", run_reset_usb),
    "37": ("Kill Apple Processes", run_kill_apple),
    "38": ("Firmware Verify", run_firmware_verify),
    "39": ("Plugin Manager", run_plugin_manager),
    "40": ("Plugin Scan", run_plugin_scan),
    "41": ("Plugin Reload", run_plugin_reload),
    "42": ("Mode Scan Full", run_mode_scan),
    "43": ("Mode Scan Fast", run_mode_fast),
    "44": ("Mode Monitor", run_mode_monitor),
    "45": ("Mode Info", run_mode_info),
    "46": ("External Tools Status", run_external_tools_status),
    "47": ("External Tools Guide", run_external_tools_guide),
    "48": ("About", show_about),
    "49": ("Launch GUI Desktop", run_launch_gui),
    "50": ("Check Update", run_check_update),
    "51": ("Device State Validator", run_device_validator),
    "52": ("Flash Simulation", run_flash_simulator),
    "53": ("Auto Driver Repair", run_auto_driver_repair),
    "54": ("Smart Anti-Brick", run_smart_anti_brick),
    "55": ("Device Profile DB", run_device_profile),
    "56": ("DB Statistics", run_db_statistics),
}


from contextlib import contextmanager

@contextmanager
def _set_busy_flag():
    import config as _cfg
    _cfg.BUSY_FLAG = True
    try:
        yield
    finally:
        _cfg.BUSY_FLAG = False


def main():
    """Main entry point CLI — 56 menu, 1 level, no sub-loops"""
    import config as _cfg

    # Auto-load plugin system
    try:
        from plugins.loader import load_all_plugins
        loaded = load_all_plugins()
        if loaded > 0:
            log.debug(f"{loaded} plugin(s) loaded")
    except Exception:
        pass

    try:
        while True:
            if _cfg.BUSY_FLAG:
                log.warning("Ada command yang sedang berjalan! Tunggu selesai.")
                input(f"  {Colors.DIM}Tekan Enter untuk melanjutkan...{Colors.RESET}")
                continue

            print_main_menu()
            print()
            choice = input(f"  {Colors.BRIGHT_WHITE}Pilih menu [0-56]{Colors.RESET}: ").strip()
            print()

            if choice == "0":
                log.info("Terima kasih telah menggunakan NST Ultimate Console!")
                ActionLogger.log("EXIT", "INFO", "Program ditutup user")
                break

            if choice in MENU_ACTIONS:
                name, func = MENU_ACTIONS[choice]
                log.header(f"[{name.upper()}]")
                ActionLogger.log(name, "INFO", "Memulai")
                try:
                    with _set_busy_flag():
                        func()
                except KeyboardInterrupt:
                    print()
                    log.warning(f"{name} dibatalkan user (Ctrl+C)")
                    ActionLogger.log(name, "WARNING", "KeyboardInterrupt")
                except Exception as e:
                    log.critical(f"[ERROR] {name}: {e}")
                    from core.safety import ErrorHandler
                    ErrorHandler.handle_exception(e, name)
                    ActionLogger.log(name, "ERROR", str(e))

                input(f"\n  {Colors.DIM}Tekan Enter untuk kembali ke menu utama...{Colors.RESET}")
                print()
            else:
                log.warning(f"Pilihan '{choice}' tidak valid! Pilih angka 0-56.")

    except KeyboardInterrupt:
        print()
        log.info("Program dihentikan oleh user (Ctrl+C)")
        try:
            ActionLogger.log("EXIT", "INFO", "KeyboardInterrupt")
        except Exception:
            pass


if __name__ == "__main__":
    _check_admin_windows()

    try:
        from core.crash_handler import setup_crash_handling, cleanup_crash_handling
        was_crash = setup_crash_handling()
        if was_crash:
            log.warning("Terdeteksi crash sebelumnya! Memulai dengan mode aman.")
    except Exception:
        pass

    try:
        main()
    except Exception as e:
        print(f"\n  {Colors.BG_RED}{Colors.BOLD}  FATAL ERROR  {Colors.RESET}")
        print(f"  {Colors.RED}{e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        ""
        sys.exit(1)
    finally:
        try:
            from core.crash_handler import cleanup_crash_handling
            cleanup_crash_handling()
        except Exception:
            pass
