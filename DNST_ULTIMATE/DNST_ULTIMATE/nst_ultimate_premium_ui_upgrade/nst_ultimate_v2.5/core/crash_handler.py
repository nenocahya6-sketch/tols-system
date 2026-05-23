
"""
NST Crash Handler v1
=====================
Penanganan crash profesional:
1. CrashDump - Auto save traceback + system info + context ke file
2. SentinelFile - Deteksi apakah terakhir crash (clean exit = sentinel dihapus)
3. AutoRestart - Restart program otomatis setelah crash
"""
import os
import sys
import time
import traceback
import platform
import json
import subprocess
from datetime import datetime
from typing import Dict, Optional, Callable

from core.logger import log, Colors


class CrashDump:
    """Auto save crash dump ke file dengan info lengkap"""

    @staticmethod
    def save_dump(exception: Exception, context: str = "", extra: Dict = None) -> Optional[str]:
        """
        Simpan crash dump ke file.
        Includes: traceback, system info, context, environment.
        Returns path ke file dump, atau None jika gagal.
        """
        from config import LOG_DIR

        dump_dir = os.path.join(LOG_DIR, "crashes")
        os.makedirs(dump_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_file = os.path.join(dump_dir, f"crash_{timestamp}.json")

        try:
            # Tangkap traceback
            tb_lines = traceback.format_exception(type(exception), exception, exception.__traceback__)
            tb_str = "".join(tb_lines)

            # Info sistem
            system_info = {
                "os": platform.system(),
                "os_version": platform.version(),
                "os_release": platform.release(),
                "architecture": platform.machine(),
                "processor": platform.processor() or "N/A",
                "python": sys.version,
                "python_path": sys.executable,
                "hostname": platform.node(),
                "cwd": os.getcwd(),
                "argv": sys.argv,
            }

            # Environment variables (tanpa yang sensitif)
            env_vars = {}
            for key, val in sorted(os.environ.items()):
                key_lower = key.lower()
                if any(s in key_lower for s in ["password", "secret", "token", "key", "auth"]):
                    env_vars[key] = "***REDACTED***"
                else:
                    env_vars[key] = val

            # Build dump data
            dump_data = {
                "timestamp": datetime.now().isoformat(),
                "crash_type": type(exception).__name__,
                "crash_message": str(exception),
                "context": context or "",
                "traceback": tb_str,
                "system_info": system_info,
                "env_vars": env_vars,
                "extra": extra or {},
            }

            with open(dump_file, 'w', encoding='utf-8') as f:
                json.dump(dump_data, f, indent=2, default=str)

            # Juga save traceback plain text
            txt_file = os.path.join(dump_dir, f"crash_{timestamp}.txt")
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write(f"NST CRASH DUMP - {datetime.now().isoformat()}\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Context: {context or 'N/A'}\n")
                f.write(f"Exception: {type(exception).__name__}: {exception}\n\n")
                f.write(f"Traceback:\n{tb_str}\n")
                f.write("=" * 60 + "\n")
                f.write("System Info:\n")
                for key, val in system_info.items():
                    f.write(f"  {key}: {val}\n")

            return dump_file

        except Exception as e:
            # Fallback: simpak ke file minimal
            try:
                fallback_path = os.path.join(LOG_DIR, "crash_fallback.log")
                with open(fallback_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now().isoformat()}] CRASH: {exception}\n")
                    f.write(f"  Context: {context}\n")
                    f.write(f"  Dump save failed: {e}\n")
            except Exception:
                pass
            return None


class SentinelFile:
    """
    Sentinel file mechanism.
    - Dibuat saat program START
    - Dihapus saat program EXIT normal
    - Jika masih ada saat start berikutnya -> program sebelumnya CRASH
    """

    SENTINEL_NAME = ".crash_sentinel"

    @staticmethod
    def get_path() -> str:
        from config import BASE_DIR
        return os.path.join(BASE_DIR, SentinelFile.SENTINEL_NAME)

    @staticmethod
    def mark_start() -> bool:
        """Tandai bahwa program sedang berjalan (sentinel file dibuat)"""
        try:
            path = SentinelFile.get_path()
            data = {
                "pid": os.getpid(),
                "start_time": datetime.now().isoformat(),
                "argv": sys.argv,
                "python": sys.executable,
            }
            with open(path, 'w') as f:
                json.dump(data, f)
            log.debug(f"Sentinel file dibuat: {path}")
            return True
        except Exception as e:
            log.warning(f"Gagal buat sentinel: {e}")
            return False

    @staticmethod
    def mark_exit():
        """Tandai program exit NORMAL (sentinel file dihapus)"""
        try:
            path = SentinelFile.get_path()
            if os.path.exists(path):
                os.remove(path)
                log.debug("Sentinel file dihapus (clean exit)")
        except Exception as e:
            log.warning(f"Gagal hapus sentinel: {e}")

    @staticmethod
    def was_previous_crash() -> bool:
        """Cek apakah program sebelumnya crash (sentinel masih ada)"""
        path = SentinelFile.get_path()
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                pid = data.get("pid", "?")
                start = data.get("start_time", "?")
                log.warning(f"⬅  Deteksi crash SEBELUMNYA! (PID: {pid}, start: {start})")
                return True
            except Exception:
                log.warning("⬅  Sentinel file ditemukan! Program sebelumnya crash.")
                return True
        return False

    @staticmethod
    def get_previous_crash_info() -> Dict:
        """Dapatkan info dari sentinel file jika ada"""
        path = SentinelFile.get_path()
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}


class CrashRecovery:
    """
    Recovery otomatis setelah crash:
    - Restart program (dengan opsi safe mode)
    - Bersihkan state yang nyangkut
    """

    @staticmethod
    def attempt_restart(delay_seconds: int = 0) -> bool:
        """
        Restart program secara otomatis.
        Kembali ke main.py dengan argumen yang sama.
        """
        try:
            log.info(f"Restart program dalam {delay_seconds} detik...")
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            # Build command: restart dengan argumen yang sama
            cmd = [sys.executable] + sys.argv

            # Start proses baru
            if platform.system() == "Windows":
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(cmd)

            log.success("Program direstart!")
            return True

        except Exception as e:
            log.warning(f"Gagal restart otomatis: {e}")
            return False

    @staticmethod
    def save_critical_state(state_data: Dict):
        """Simpan state kritis sebelum crash (agar bisa dipulihkan)"""
        from config import LOG_DIR
        try:
            state_file = os.path.join(LOG_DIR, "last_state.json")
            state_data["saved_at"] = datetime.now().isoformat()
            with open(state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def load_critical_state() -> Optional[Dict]:
        """Load state kritis yang disimpan sebelumnya"""
        from config import LOG_DIR
        state_file = os.path.join(LOG_DIR, "last_state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return None


# ========== INTEGRATION WRAPPER ==========

def setup_crash_handling() -> bool:
    """
    Setup crash handling di awal program.
    Returns True jika sebelumnya crash, False jika clean start.
    """
    # Cek sentinel
    was_crash = SentinelFile.was_previous_crash()

    # Buat sentinel baru
    SentinelFile.mark_start()

    return was_crash


def cleanup_crash_handling():
    """Cleanup crash handling di akhir program (exit normal)"""
    SentinelFile.mark_exit()


class SafeExecutor:
    """
    Executor aman yang menangkap crash dan menyimpan dump.
    Gunakan sebagai wrapper untuk fungsi-fungsi kritis.
    """

    @staticmethod
    def execute(func: Callable, *args, context: str = "", **kwargs):
        """
        Eksekusi fungsi dengan safety net:
        - Crash dump otomatis jika exception
        - Tidak menghentikan program
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            CrashDump.save_dump(e, context)
            log.critical(f"[SAFE EXECUTOR] Error di '{context or func.__name__}': {e}")
            return None
