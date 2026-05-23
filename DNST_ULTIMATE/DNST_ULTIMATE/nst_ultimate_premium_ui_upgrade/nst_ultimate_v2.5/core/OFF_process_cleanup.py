
"""
NST Process Cleanup System v1 — Anti-Zombie & Subprocess Guardian
==================================================================
Fitur:
1. Subprocess Tracking — catat semua subprocess yang dibuat
2. Process Watchdog — background thread untuk periodic cleanup
3. Zombie Killer — kill adb.exe, fastboot.exe, dan zombie lain
4. Graceful Shutdown — cleanup otomatis saat program exit
5. Orphan Detection — deteksi subprocess yang lupa di-terminate

Arsitektur:
    ProcessCleanup (singleton)
    ├── register(pid, name)     — Catat subprocess baru
    ├── unregister(pid)         — Hapus dari tracking
    ├── cleanup_adb()           — Kill zombie ADB
    ├── cleanup_fastboot()      — Kill zombie Fastboot
    ├── cleanup_all()           — Kill semua tracked + zombie
    └── get_stats()             — Statistik proses

    ProcessWatchdog (background thread)
    ├── Periodik cleanup tiap 30 detik
    ├── Deteksi zombie berlebih
    └── Auto-cleanup jika threshold terlampaui
"""
import os
import sys
import time
import signal
import atexit
import subprocess
import threading
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from core.logger import log, error_log, cleanup_log


# ========== DATA CLASSES ==========

@dataclass
class TrackedProcess:
    """Informasi satu subprocess yang dilacak"""
    pid: int
    name: str
    command: str
    created_at: datetime
    process: Optional[subprocess.Popen] = None
    killed: bool = False

    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def is_zombie(self) -> bool:
        """Cek apakah process sudah mati tapi belum di-unregister"""
        if self.killed:
            return True
        if self.process and self.process.poll() is not None:
            return True
        return False


@dataclass
class CleanupStats:
    """Statistik hasil cleanup"""
    total_cleaned: int = 0
    total_failed: int = 0
    adb_killed: int = 0
    fastboot_killed: int = 0
    apple_killed: int = 0
    orphaned_killed: int = 0
    total_memory_freed_mb: float = 0.0
    last_cleanup: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)


# ========== PROCESS CLEANUP ==========

class ProcessCleanup:
    """
    Process Cleanup System — singleton.
    Melacak dan membersihkan semua subprocess yang dibuat.

    Cara pakai:
        pc = ProcessCleanup()
        proc = subprocess.Popen([...])
        pc.register(proc.pid, "adb devices", proc)
        # ... nanti ...
        pc.cleanup_all()  # Kill semua tracked processes
    """

    _instance: Optional["ProcessCleanup"] = None
    _singleton_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._tracked: Dict[int, TrackedProcess] = {}
            self._lock = threading.Lock()
            self._stats = CleanupStats()
            self._watchdog: Optional["ProcessWatchdog"] = None

            # Konfigurasi
            self.max_process_age_minutes = 30  # Auto-kill jika > 30 menit
            self.zombie_threshold = 5  # Jika > 5 zombie, trigger cleanup

            # Daftar binary yang dianggap aman untuk di-kill
            self._known_binaries = {
                "adb.exe", "adb",
                "fastboot.exe", "fastboot",
                "iTunes.exe", "iTunesHelper.exe",
                "AppleMobileDeviceService.exe",
                "idevice_id.exe", "idevice_id",
                "irecovery.exe", "irecovery",
                "idevicerestore.exe", "idevicerestore",
                "mtk.exe", "mtk",
                "heimdall.exe", "heimdall",
                "edl.exe", "edl",
            }

            # Daftar proses yang dilarang di-kill
            self._protected_pids: Set[int] = set()

            # Daftar subprocess yang harus di-kill dengan SIGKILL (9)
            self._force_kill_binaries = {
                "adb.exe", "adb",
                "fastboot.exe", "fastboot",
            }

            # Register cleanup at exit
            atexit.register(self.cleanup_all)

            cleanup_log.info("ProcessCleanup initialized")

    # ── Public API: Registration ──

    def register(self, pid: int, name: str = "", process: subprocess.Popen = None) -> bool:
        """
        Daftarkan subprocess untuk dilacak.

        Args:
            pid: Process ID
            name: Nama/deskripsi proses
            process: Optional subprocess.Popen object

        Returns:
            True jika berhasil didaftarkan
        """
        if pid <= 0:
            return False

        with self._lock:
            if pid in self._tracked:
                return False

            cmd = ""
            if process and hasattr(process, 'args'):
                try:
                    cmd = ' '.join(process.args) if isinstance(process.args, (list, tuple)) else str(process.args)
                except Exception:
                    cmd = str(process.pid)

            self._tracked[pid] = TrackedProcess(
                pid=pid,
                name=name or f"Process-{pid}",
                command=cmd[:200],
                created_at=datetime.now(),
                process=process,
            )
            cleanup_log.debug(f"Registered: PID {pid} ({name})")
            return True

    def unregister(self, pid: int) -> bool:
        """
        Hapus subprocess dari tracking (setelah selesai).

        Args:
            pid: Process ID

        Returns:
            True jika berhasil dihapus
        """
        with self._lock:
            if pid in self._tracked:
                del self._tracked[pid]
                return True
            return False

    def protect(self, pid: int):
        """Lindungi process agar tidak di-kill otomatis"""
        with self._lock:
            self._protected_pids.add(pid)

    def unprotect(self, pid: int):
        """Hapus perlindungan process"""
        with self._lock:
            self._protected_pids.discard(pid)

    def is_tracked(self, pid: int) -> bool:
        """Cek apakah process sedang dilacak"""
        with self._lock:
            return pid in self._tracked

    def get_tracked_count(self) -> int:
        """Dapatkan jumlah process yang sedang dilacak"""
        with self._lock:
            return len(self._tracked)

    # ── Public API: Cleanup Operations ──

    def cleanup_adb(self) -> int:
        """
        Kill semua proses ADB yang zombie/hang.

        Returns:
            Jumlah proses yang berhasil di-kill
        """
        cleanup_log.warning("CLEANUP: Membersihkan proses ADB...")
        count = 0

        try:
            if os.name == 'nt':  # Windows
                for proc in ["adb.exe", "adb"]:
                    try:
                        r = subprocess.run(
                            ["taskkill", "/F", "/IM", proc],
                            capture_output=True, text=True, timeout=5
                        )
                        if r.returncode == 0:
                            # Hitung dari output "SUCCESS: sent termination signal"
                            lines = [l for l in r.stdout.split('\n') if 'SUCCESS' in l or 'success' in l.lower()]
                            count += len(lines) if lines else 1
                            cleanup_log.debug(f"  Killed: {proc}")
                    except Exception:
                        pass

                # Hapus juga lock file ADB
                lock_file = os.path.expanduser("~/.android/adb.lock")
                if os.path.exists(lock_file):
                    try:
                        os.remove(lock_file)
                        cleanup_log.debug("  ADB lock file removed")
                    except Exception:
                        pass
            else:  # Linux / Mac
                try:
                    r = subprocess.run(
                        ["pkill", "-9", "adb"],
                        capture_output=True, text=True, timeout=5
                    )
                    if r.returncode == 0:
                        count = 1
                except Exception:
                    pass
                try:
                    subprocess.run(
                        ["pkill", "-9", "adb"],
                        capture_output=True, timeout=5
                    )
                except Exception:
                    pass

            # Bersihkan dari tracked processes
            with self._lock:
                zombie_pids = [
                    pid for pid, tp in self._tracked.items()
                    if "adb" in tp.name.lower() or "adb" in tp.command.lower()
                ]
                for pid in zombie_pids:
                    del self._tracked[pid]

            self._stats.adb_killed += count
            self._stats.total_cleaned += count

            if count > 0:
                log.success(f"CLEANUP: {count} proses ADB dibersihkan")
            else:
                cleanup_log.info("CLEANUP: Tidak ada proses ADB yang perlu dibersihkan")

        except Exception as e:
            cleanup_log.error(f"CLEANUP: Error cleanup ADB: {e}")
            self._stats.errors.append(f"cleanup_adb: {e}")

        return count

    def cleanup_fastboot(self) -> int:
        """
        Kill semua proses Fastboot yang zombie/hang.

        Returns:
            Jumlah proses yang berhasil di-kill
        """
        cleanup_log.warning("CLEANUP: Membersihkan proses Fastboot...")
        count = 0

        try:
            if os.name == 'nt':
                for proc in ["fastboot.exe", "fastboot"]:
                    try:
                        r = subprocess.run(
                            ["taskkill", "/F", "/IM", proc],
                            capture_output=True, text=True, timeout=5
                        )
                        if r.returncode == 0:
                            count += 1
                            cleanup_log.debug(f"  Killed: {proc}")
                    except Exception:
                        pass
            else:
                try:
                    subprocess.run(
                        ["pkill", "-9", "fastboot"],
                        capture_output=True, timeout=5
                    )
                    count = 1
                except Exception:
                    pass

            # Bersihkan dari tracked
            with self._lock:
                zombie_pids = [
                    pid for pid, tp in self._tracked.items()
                    if "fastboot" in tp.name.lower() or "fastboot" in tp.command.lower()
                ]
                for pid in zombie_pids:
                    del self._tracked[pid]

            self._stats.fastboot_killed += count
            self._stats.total_cleaned += count

            if count > 0:
                log.success(f"CLEANUP: {count} proses Fastboot dibersihkan")
            else:
                cleanup_log.info("CLEANUP: Tidak ada proses Fastboot yang perlu dibersihkan")

        except Exception as e:
            cleanup_log.error(f"CLEANUP: Error cleanup Fastboot: {e}")
            self._stats.errors.append(f"cleanup_fastboot: {e}")

        return count

    def cleanup_apple(self) -> int:
        """
        Kill proses Apple yang hang (Windows hanya).

        Returns:
            Jumlah proses yang berhasil di-kill
        """
        if os.name != 'nt':
            return 0

        cleanup_log.warning("CLEANUP: Membersihkan proses Apple...")
        count = 0

        apple_procs = [
            "iTunes.exe", "iTunesHelper.exe",
            "AppleMobileDeviceService.exe",
            "AppleMobileBackup.exe",
            "APSDaemon.exe", "ApplePush.exe",
        ]

        for proc in apple_procs:
            try:
                r = subprocess.run(
                    ["taskkill", "/F", "/IM", proc],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode == 0:
                    count += 1
                    cleanup_log.debug(f"  Killed: {proc}")
            except Exception:
                pass

        self._stats.apple_killed += count
        self._stats.total_cleaned += count

        if count > 0:
            log.success(f"CLEANUP: {count} proses Apple dibersihkan")

        return count

    def cleanup_orphans(self) -> int:
        """
        Kill semua subprocess yang masih running tapi sudah tidak diperlukan.

        Returns:
            Jumlah proses yang berhasil di-kill
        """
        cleanup_log.warning("CLEANUP: Membersihkan orphan processes...")
        count = 0

        with self._lock:
            tracked_copy = dict(self._tracked)

        for pid, tp in tracked_copy.items():
            if pid in self._protected_pids:
                continue

            if tp.is_zombie:
                # Sudah mati, cukup hapus dari tracking
                with self._lock:
                    self._tracked.pop(pid, None)
                cleanup_log.debug(f"  Removed zombie: PID {pid} ({tp.name})")
                continue

            # Cek apakah process sudah terlalu tua
            if tp.age_seconds > self.max_process_age_minutes * 60:
                cleanup_log.warning(
                    f"  Killing old process: PID {pid} ({tp.name}) "
                    f"- age: {tp.age_seconds:.0f}s > {self.max_process_age_minutes}m limit"
                )
                try:
                    if os.name == 'nt':
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=5
                        )
                    else:
                        os.kill(pid, signal.SIGKILL)
                    tp.killed = True
                    count += 1
                except Exception as e:
                    cleanup_log.debug(f"  Failed to kill PID {pid}: {e}")

        with self._lock:
            self._tracked = {
                pid: tp for pid, tp in self._tracked.items()
                if not tp.killed and pid in self._protected_pids
            }

        self._stats.orphaned_killed += count
        self._stats.total_cleaned += count

        if count > 0:
            log.success(f"CLEANUP: {count} orphan processes dibersihkan")

        return count

    def cleanup_all(self):
        """
        FULL CLEANUP — Kill SEMUA zombie + orphan processes.
        Dipanggil otomatis saat program exit via atexit.
        """
        cleanup_log.info("=" * 50)
        cleanup_log.info("FULL CLEANUP: Memulai pembersihan total...")
        cleanup_log.info("=" * 50)

        total = 0

        # 1. Kill ADB zombie
        total += self.cleanup_adb()

        # 2. Kill Fastboot zombie
        total += self.cleanup_fastboot()

        # 3. Kill Apple processes
        total += self.cleanup_apple()

        # 4. Kill orphan processes
        total += self.cleanup_orphans()

        # 5. Final: kill tracked processes yang tersisa
        with self._lock:
            remaining = list(self._tracked.items())

        for pid, tp in remaining:
            if pid in self._protected_pids:
                continue
            try:
                if os.name == 'nt':
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, timeout=5
                    )
                else:
                    os.kill(pid, signal.SIGKILL)
                total += 1
            except Exception:
                pass

        # Bersihkan tracking
        with self._lock:
            self._tracked.clear()

        # Update stats
        self._stats.last_cleanup = datetime.now()
        self._stats.total_cleaned += total

        if total > 0:
            log.success(f"FULL CLEANUP: {total} total proses dibersihkan ✅")
        else:
            cleanup_log.info("FULL CLEANUP: Tidak ada proses yang perlu dibersihkan")

        cleanup_log.info("=" * 50)
        return total

    def cleanup_by_name(self, name_pattern: str) -> int:
        """
        Kill semua tracked process yang namanya mengandung pattern.

        Args:
            name_pattern: String pattern untuk mencocokkan nama process

        Returns:
            Jumlah proses yang di-kill
        """
        count = 0
        with self._lock:
            to_kill = [
                (pid, tp) for pid, tp in self._tracked.items()
                if name_pattern.lower() in tp.name.lower()
                or name_pattern.lower() in tp.command.lower()
            ]

        for pid, tp in to_kill:
            try:
                if os.name == 'nt':
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, timeout=5
                    )
                else:
                    os.kill(pid, signal.SIGKILL)
                count += 1
            except Exception:
                pass

        with self._lock:
            for pid, _ in to_kill:
                self._tracked.pop(pid, None)

        if count > 0:
            cleanup_log.info(f"CLEANUP: {count} proses '{name_pattern}' dibersihkan")

        return count

    # ── Public API: Status & Stats ──

    def get_stats(self) -> dict:
        """Dapatkan statistik cleanup"""
        with self._lock:
            return {
                "total_cleaned": self._stats.total_cleaned,
                "total_failed": self._stats.total_failed,
                "adb_killed": self._stats.adb_killed,
                "fastboot_killed": self._stats.fastboot_killed,
                "apple_killed": self._stats.apple_killed,
                "orphaned_killed": self._stats.orphaned_killed,
                "currently_tracked": len(self._tracked),
                "protected_count": len(self._protected_pids),
                "last_cleanup": self._stats.last_cleanup.isoformat() if self._stats.last_cleanup else None,
                "errors": self._stats.errors[-5:],  # Last 5 errors
            }

    def get_tracked_processes(self) -> List[dict]:
        """Dapatkan daftar semua process yang sedang dilacak"""
        with self._lock:
            return [
                {
                    "pid": tp.pid,
                    "name": tp.name,
                    "command": tp.command[:100],
                    "age_seconds": tp.age_seconds,
                    "killed": tp.killed,
                    "protected": tp.pid in self._protected_pids,
                }
                for tp in self._tracked.values()
            ]

    def print_status(self):
        """Tampilkan status process tracking ke console"""
        from core.logger import Colors as C

        with self._lock:
            if not self._tracked:
                log.info(f"  {C.DIM}Tidak ada process yang sedang dilacak.{C.RESET}")
                return

            log.info(f"  {C.BOLD}Process Tracking:{C.RESET}")
            for tp in sorted(self._tracked.values(), key=lambda x: x.created_at):
                protected = "🔒" if tp.pid in self._protected_pids else " "
                zombie = "💀" if tp.is_zombie else " "
                age_str = f"{tp.age_seconds:.0f}s"
                print(f"  {protected}{zombie} PID {C.CYAN}{tp.pid}{C.RESET} "
                      f"{C.DIM}{tp.name[:40]}{C.RESET} ({age_str})")

    # ── Watchdog ──

    def start_watchdog(self, interval: float = 30.0):
        """
        Mulai ProcessWatchdog untuk periodic cleanup.

        Args:
            interval: Interval cleanup dalam detik (default: 30)
        """
        if self._watchdog and self._watchdog.is_running():
            return

        self._watchdog = ProcessWatchdog(self, interval)
        self._watchdog.start()
        cleanup_log.info(f"ProcessWatchdog started (interval: {interval}s)")

    def stop_watchdog(self):
        """Stop ProcessWatchdog"""
        if self._watchdog:
            self._watchdog.stop()
            self._watchdog = None
            cleanup_log.info("ProcessWatchdog stopped")

    def is_watchdog_running(self) -> bool:
        return self._watchdog is not None and self._watchdog.is_running()


# ========== PROCESS WATCHDOG ==========

class ProcessWatchdog:
    """
    Background thread untuk periodic process cleanup.
    Berjalan di thread terpisah, ngecek tiap N detik.

    Args:
        cleanup: ProcessCleanup instance
        interval: Interval detik antar cleanup
    """

    def __init__(self, cleanup: ProcessCleanup, interval: float = 30.0):
        self._cleanup = cleanup
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cycle_count = 0

    def start(self):
        """Start watchdog thread"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="ProcessWatchdog",
        )
        self._thread.start()

    def stop(self):
        """Stop watchdog"""
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def _run_loop(self):
        """Watchdog main loop"""
        while self._running:
            try:
                self._cycle_count += 1
                self._watchdog_cycle()
            except Exception as e:
                cleanup_log.error(f"Watchdog cycle error: {e}")

            # Sleep dengan early exit check
            for _ in range(int(self._interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _watchdog_cycle(self):
        """Satu siklus watchdog — cek dan cleanup jika perlu"""
        # Cek zombie count
        tracked = self._cleanup.get_tracked_processes()
        zombie_count = sum(1 for tp in tracked if tp["killed"])
        active_old = sum(1 for tp in tracked if tp["age_seconds"] > 300 and not tp["killed"])

        # Log status periodik
        if self._cycle_count % 10 == 0:  # Every 10 cycles (~5 minutes)
            cleanup_log.debug(
                f"Watchdog: {len(tracked)} tracked, "
                f"{zombie_count} zombies, {active_old} old processes"
            )

        # Trigger cleanup jika zombie berlebih
        if zombie_count > self._cleanup.zombie_threshold:
            cleanup_log.warning(
                f"Watchdog: {zombie_count} zombie processes detected "
                f"(threshold: {self._cleanup.zombie_threshold}). Running cleanup..."
            )
            self._cleanup.cleanup_orphans()

        # Trigger cleanup jika ada process terlalu tua
        if active_old > 0:
            cleanup_log.info(
                f"Watchdog: {active_old} processes older than 5 minutes. Cleanup..."
            )
            self._cleanup.cleanup_orphans()


# ========== CONVENIENCE WRAPPER ==========

def cleanup_adb_zombies() -> int:
    """Convenience: Kill ADB zombie processes"""
    return ProcessCleanup().cleanup_adb()


def cleanup_fastboot_zombies() -> int:
    """Convenience: Kill Fastboot zombie processes"""
    return ProcessCleanup().cleanup_fastboot()


def cleanup_all_processes() -> int:
    """Convenience: Full cleanup semua proses"""
    return ProcessCleanup().cleanup_all()


def start_cleanup_watchdog(interval: float = 30.0):
    """Convenience: Start process watchdog"""
    pc = ProcessCleanup()
    pc.start_watchdog(interval)
    return pc


# ========== GLOBAL INSTANCE ==========
process_cleanup = ProcessCleanup()
