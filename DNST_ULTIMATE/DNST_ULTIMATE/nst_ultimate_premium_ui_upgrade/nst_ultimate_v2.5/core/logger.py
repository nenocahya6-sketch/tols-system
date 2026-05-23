
"""
NST Logging System v3 - Per-module loggers + Rotating Files
============================================================
- Output berwarna ke console
- Log ke file dengan ROTATION otomatis per module
- Per-module log files: logs/adb.log, logs/flash.log, logs/error.log, logs/app.log
- Otomatis deteksi dukungan UTF-8/Unicode
- RotatingFileHandler: max 5MB, 5 backup files
- Log levels: DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL

Module Loggers:
    app_log      → logs/app.log          (general aplikasi)
    adb_log      → logs/adb.log          (ADB operations)
    flash_log    → logs/flash.log        (Flashing operations)
    error_log    → logs/error.log        (Hanya ERROR level ke atas)
    device_log   → logs/device.log       (Device connection history)
    recovery_log → logs/recovery.log     (Recovery operations)
    cleanup_log  → logs/cleanup.log      (Process cleanup operations)
"""
import os
import re
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict

# ========== ANSI CLEANER ==========
_ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])|(?:\[[0-9;]*[A-Za-z])')


def clean_console_output(text):
    """Remove ANSI escape sequences and normalize output text."""
    if text is None:
        return ""
    text = str(text)
    text = _ANSI_ESCAPE.sub('', text)
    text = re.sub(r'\[\d+m', '', text)
    text = re.sub(r'\[[0-9;]*m', '', text)
    text = text.replace('==================================================', '\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ========== UTF-8 DETECTION ==========
_USE_UTF8 = False
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        _USE_UTF8 = True
except Exception:
    pass
if not _USE_UTF8:
    try:
        enc = sys.stdout.encoding or ''
        _USE_UTF8 = 'utf' in enc.lower() or 'UTF' in enc
    except Exception:
        pass


def _icon(utf8_char: str, fallback: str) -> str:
    """Pilih icon: UTF-8 jika support, fallback ASCII jika tidak"""
    return utf8_char if _USE_UTF8 else fallback


# ========== ANSI COLORS ==========
class Colors:
    """Kode warna ANSI untuk terminal"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"

    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_DARK_GRAY = "\033[100m"

    @staticmethod
    def supports_color() -> bool:
        """Cek apakah terminal mendukung warna"""
        if not sys.stdout.isatty():
            return False
        if os.name == 'nt':  # Windows
            return True  # ANSI support via Virtual Terminal
        return True


# ========== CUSTOM LOGGER ==========
class ColoredFormatter(logging.Formatter):
    """Formatter dengan warna untuk logging"""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.BRIGHT_BLACK,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BG_RED + Colors.WHITE + Colors.BOLD,
    }

    LEVEL_ICONS = {
        logging.DEBUG: _icon("# ", "# "),
        logging.INFO: _icon("i ", "i "),
        logging.WARNING: _icon("! ", "! "),
        logging.ERROR: _icon("x ", "x "),
        logging.CRITICAL: _icon("!! ", "!! "),
    }

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        color = self.LEVEL_COLORS.get(record.levelno, "")
        icon = self.LEVEL_ICONS.get(record.levelno, "")
        level_name = record.levelname.ljust(8)

        if Colors.supports_color():
            log_msg = (
                f"{Colors.DIM}{timestamp}{Colors.RESET} "
                f"{color}{icon}{level_name}{Colors.RESET} "
                f"{Colors.BRIGHT_WHITE}{record.getMessage()}{Colors.RESET}"
            )
        else:
            log_msg = f"[{timestamp}] [{level_name.strip()}] {record.getMessage()}"

        return log_msg


class PlainFileFormatter(logging.Formatter):
    """Formatter untuk file log - tanpa warna, dengan detail lengkap"""

    def format(self, record):
        return (
            f"[{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}] "
            f"[{record.levelname}] "
            f"[{record.name}] "
            f"{record.getMessage()}"
        )


# ========== LOGGER REGISTRY ==========
_logger_cache: Dict[str, logging.Logger] = {}
_log_dir: Optional[str] = None


def get_logger(name: str) -> logging.Logger:
    """
    Dapatkan per-module logger dengan file handler sendiri.

    Module yang tersedia:
        app     → logs/app.log
        adb     → logs/adb.log
        flash   → logs/flash.log
        error   → logs/error.log (only ERROR+)
        device  → logs/device.log
        recovery → logs/recovery.log
        cleanup  → logs/cleanup.log

    Args:
        name: Nama module logger

    Returns:
        logging.Logger instance
    """
    global _log_dir

    if name in _logger_cache:
        return _logger_cache[name]

    # Tentukan file path
    log_file = None
    if _log_dir:
        # Module khusus
        module_map = {
            "app": "app.log",
            "adb": "adb.log",
            "flash": "flash.log",
            "device": "device.log",
            "error": "error.log",  # Only ERROR+ level
            "recovery": "recovery.log",
            "cleanup": "cleanup.log",
        }
        fname = module_map.get(name, f"{name}.log")
        log_file = os.path.join(_log_dir, fname)

    # Buat logger
    logger = logging.getLogger(f"NST.{name}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # Console handler (berwarna)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    # File handler dengan ROTATION
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            level = logging.ERROR if name == "error" else logging.DEBUG

            file_handler = RotatingFileHandler(
                log_file,
                mode='a',
                maxBytes=5 * 1024 * 1024,  # 5MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(PlainFileFormatter())
            logger.addHandler(file_handler)
        except Exception:
            pass

    _logger_cache[name] = logger
    return logger


def set_log_directory(log_dir: str):
    """Set direktori untuk log files (dipanggil saat init)"""
    global _log_dir
    _log_dir = log_dir
    os.makedirs(log_dir, exist_ok=True)


# ========== LEGACY LOGGER (compatibility) ==========
class Logger:
    """Logger utama aplikasi - backward compatible dengan kode lama"""

    def __init__(self, name: str = "NST_Console", log_file: Optional[str] = None,
                 max_bytes: int = 5 * 1024 * 1024, backup_count: int = 5):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        self.name = name

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(ColoredFormatter())
        self.logger.addHandler(console_handler)

        # File handler
        if log_file:
            try:
                log_dir = os.path.dirname(log_file)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                file_handler = RotatingFileHandler(
                    log_file, mode='a',
                    maxBytes=max_bytes, backupCount=backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(PlainFileFormatter())
                self.logger.addHandler(file_handler)

                # Error-only log file
                error_log = log_file.replace('.log', '_error.log')
                error_handler = RotatingFileHandler(
                    error_log, mode='a',
                    maxBytes=max_bytes, backupCount=3,
                    encoding='utf-8'
                )
                error_handler.setLevel(logging.ERROR)
                error_handler.setFormatter(PlainFileFormatter())
                self.logger.addHandler(error_handler)

            except Exception as e:
                self.warning(f"Tidak bisa membuat log file: {log_file} - {e}")

    def print_banner(self):
        """Cetak ASCII banner NST"""
        if Colors.supports_color():
            banner = f"""
  {Colors.BOLD}{Colors.BRIGHT_CYAN}███╗   ██╗███████╗████████╗{Colors.RESET}
  {Colors.BOLD}{Colors.BRIGHT_BLUE}████╗  ██║██╔════╝╚══██╔══╝{Colors.RESET}
  {Colors.BOLD}{Colors.BRIGHT_CYAN}██╔██╗ ██║███████╗   ██║   {Colors.RESET}
  {Colors.BOLD}{Colors.BRIGHT_BLUE}██║╚██╗██║╚════██║   ██║   {Colors.RESET}
  {Colors.BOLD}{Colors.BRIGHT_CYAN}██║ ╚████║███████║   ██║   {Colors.RESET}
  {Colors.BOLD}{Colors.BRIGHT_BLUE}╚═╝  ╚═══╝╚══════╝   ╚═╝   {Colors.RESET}
  {Colors.DIM}U L T I M A T E   C O N S O L E{Colors.RESET}
"""
            print(banner)
        else:
            print("""
  NST ULTIMATE CONSOLE
  ====================""")

    def debug(self, msg: str): self.logger.debug(msg)
    def info(self, msg: str): self.logger.info(msg)

    def success(self, msg: str):
        check = _icon("[OK]", "[OK]")
        if Colors.supports_color():
            self.logger.info(f"{Colors.BRIGHT_GREEN}{check} {msg}{Colors.RESET}")
        else:
            self.logger.info(f"{check} {msg}")

    def warning(self, msg: str): self.logger.warning(msg)
    def error(self, msg: str): self.logger.error(msg)
    def critical(self, msg: str): self.logger.critical(msg)

    def header(self, title: str):
        width = 60
        h_line = "=" * width
        if Colors.supports_color():
            print(f"\n{Colors.BOLD}{Colors.CYAN}{h_line}{Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.CYAN}  {Colors.RESET}{Colors.BRIGHT_WHITE}{title}{Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.CYAN}{h_line}{Colors.RESET}\n")
        else:
            print(f"\n{h_line}\n  {title}\n{h_line}\n")

    def separator(self, char: str = "=", length: int = 60):
        line = char * length
        if Colors.supports_color():
            print(f"{Colors.DIM}{line}{Colors.RESET}")
        else:
            print(line)

    def section(self, title: str):
        if Colors.supports_color():
            print(f"\n  {Colors.BOLD}{Colors.CYAN}>> {title}{Colors.RESET}")
            print(f"  {Colors.DIM}{'-' * 50}{Colors.RESET}")
        else:
            print(f"\n  >> {title}\n  {'-' * 50}")

    def progress_bar(self, current: int, total: int, prefix: str = "", suffix: str = "", length: int = 30):
        percent = current / total if total > 0 else 0
        filled = int(length * percent)
        bar = "#" * filled + "." * (length - filled)
        if Colors.supports_color():
            print(f"\r{Colors.CYAN}{prefix}{Colors.RESET} |{Colors.GREEN}{bar}{Colors.RESET}| {Colors.BRIGHT_WHITE}{percent:.1%}{Colors.RESET} {suffix}", end="")
        else:
            print(f"\r{prefix} |{bar}| {percent:.1%} {suffix}", end="")
        if current >= total:
            print()

    def device_log(self, device_serial: str, action: str, status: str, detail: str = ""):
        """Log aktivitas perangkat - menggunakan per-module logger"""
        adb = get_logger("adb")
        msg = f"[{device_serial}] [{action}] {status}"
        if detail:
            msg += f" - {detail}"
        adb.info(msg)

    def log_csv(self, device_serial: str, action: str, status: str, imei: str = "", model: str = "", note: str = ""):
        """Log ke CSV untuk analisis"""
        try:
            from config import LOG_DIR
            csv_path = os.path.join(LOG_DIR, "device_history.csv")
            import csv
            file_exists = os.path.exists(csv_path)
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Timestamp", "Serial", "Action", "Status", "IMEI", "Model", "Note"])
                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), device_serial, action, status, imei, model, note])
        except Exception:
            pass


# ========== GLOBAL INSTANCE ==========
from config import LOG_FILE, LOG_MAX_SIZE, LOG_BACKUP_COUNT, VERSION, AUTHOR, LOG_DIR

# Set log directory for per-module loggers
set_log_directory(LOG_DIR)

# Legacy global instance (backward compatible)
log = Logger(log_file=LOG_FILE, max_bytes=LOG_MAX_SIZE, backup_count=LOG_BACKUP_COUNT)

# Per-module loggers (NEW!)
adb_log = get_logger("adb")
flash_log = get_logger("flash")
error_log = get_logger("error")
device_log = get_logger("device")
app_log = get_logger("app")
recovery_log = get_logger("recovery")
cleanup_log = get_logger("cleanup")
