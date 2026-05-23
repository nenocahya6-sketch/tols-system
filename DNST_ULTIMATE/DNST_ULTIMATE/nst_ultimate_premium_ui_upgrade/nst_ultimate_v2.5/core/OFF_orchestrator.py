
"""
NST Global Task Orchestrator v1
=================================
High-level API untuk mengatur dan mengkoordinasikan semua operasi.
Duduk di atas TaskManager, menyediakan method-method spesifik untuk:

- Device scanning & monitoring
- ADB & Fastboot operations  
- Flashing (STM32, Android)
- Emergency recovery
- Backup & restore
- Plugin operations

Orchestrator memastikan:
1. Task tidak tabrakan (resource conflict avoidance)
2. Prioritas benar (emergency > flash > scan)
3. Dependencies terpenuhi (backup dulu sebelum flash)
4. Error handling terpusat
"""
import threading
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from core.task_manager import (
    TaskManager, TaskPriority, ResourceType, TaskStatus, task_manager
)
from core.event_bus import EventBus, event_bus
from core.logger import log, error_log, recovery_log, app_log, Colors


class GlobalTaskOrchestrator:
    """
    GLOBAL TASK ORCHESTRATOR — Singleton.
    Mengatur SEMUA operasi sistem dari satu titik pusat.

    Cara pakai:
        orch = GlobalTaskOrchestrator()
        orch.schedule_scan()           # Scan device (prioritas NORMAL)
        orch.schedule_emergency()      # Emergency recovery (prioritas CRITICAL)
        orch.schedule_flash(...)       # Flash firmware (prioritas HIGH)
        orch.get_dashboard()           # Status semua task
    """

    _instance: Optional["GlobalTaskOrchestrator"] = None
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
            self._tm = task_manager
            self._event_bus = event_bus
            self._lock = threading.Lock()

            # Task history untuk dashboard
            self._operation_history: List[Dict] = []
            self._max_history = 100

            app_log.info("GlobalTaskOrchestrator initialized")

    # =====================================================================
    # HIGH-LEVEL OPERATIONS
    # =====================================================================

    def schedule_scan(
        self,
        callback: Optional[Callable] = None,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan device scan.

        Args:
            callback: Optional callback saat selesai
            priority: Prioritas (default: NORMAL)

        Returns:
            task_id
        """
        def _scan():
            from core.device_detector import DeviceDetector
            detector = DeviceDetector()
            devices = detector.scan_all()
            if callback:
                callback(devices)
            return devices

        task_id = self._tm.run(
            "Scan Device",
            _scan,
            priority=priority or TaskPriority.NORMAL,
            resource=ResourceType.DEVICE,
        )
        self._record_operation("scan", task_id, "Device scan dimulai")
        return task_id

    def schedule_emergency(
        self,
        full: bool = True,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan EMERGENCY RECOVERY — prioritas TERTINGGI.

        Args:
            full: True = full emergency, False = kill ADB only
            priority: Prioritas (default: CRITICAL)

        Returns:
            task_id
        """
        def _emergency():
            from core.emergency import EmergencyRecovery
            er = EmergencyRecovery()
            if full:
                return er.run_full_emergency()
            else:
                return {"kill_adb": er.kill_adb_zombie()}

        task_id = self._tm.run(
            "Emergency Recovery",
            _emergency,
            priority=priority or TaskPriority.CRITICAL,
            resource=ResourceType.EMERGENCY,
            requires_protection=True,
        )
        recovery_log.warning(f"EMERGENCY TASK SCHEDULED: {task_id}")
        self._record_operation("emergency", task_id, "Emergency recovery dijadwalkan")
        return task_id

    def schedule_flash_stm32(
        self,
        firmware_path: str,
        port: str = "auto",
        baudrate: int = 115200,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan flashing STM32.

        Args:
            firmware_path: Path ke file firmware (.bin/.hex)
            port: COM port (auto = detect)
            baudrate: Baudrate
            priority: Prioritas (default: HIGH)

        Returns:
            task_id
        """
        def _flash():
            from core.flasher import STM32Flasher
            flasher = STM32Flasher(port=port, baudrate=baudrate)
            result = flasher.flash(firmware_path)
            return result

        task_id = self._tm.run(
            f"Flash STM32 - {firmware_path}",
            _flash,
            priority=priority or TaskPriority.HIGH,
            resource=ResourceType.FLASH,
            requires_protection=True,
            max_retries=1,
        )
        self._record_operation("flash_stm32", task_id, f"Flash STM32: {firmware_path}")
        return task_id

    def schedule_backup(
        self,
        serial: Optional[str] = None,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan backup otomatis.

        Args:
            serial: Serial device (None = auto-detect)
            priority: Prioritas (default: HIGH)

        Returns:
            task_id
        """
        def _backup():
            from core.safety import BackupManager, PreFlightCheck
            if not serial:
                device = PreFlightCheck.check_device_connection()
                device_serial = device.get("serial") if device.get("ok") else None
            else:
                device_serial = serial
            return BackupManager.auto_full_backup(device_serial)

        task_id = self._tm.run(
            "Backup Device",
            _backup,
            priority=priority or TaskPriority.HIGH,
            resource=ResourceType.SYSTEM,
            requires_protection=True,
        )
        self._record_operation("backup", task_id, f"Backup: {serial or 'auto'}")
        return task_id

    def schedule_restore(
        self,
        manifest_path: Optional[str] = None,
        serial: Optional[str] = None,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan restore dari backup.

        Args:
            manifest_path: Path ke manifest backup (None = latest)
            serial: Serial device
            priority: Prioritas (default: HIGH)

        Returns:
            task_id
        """
        def _restore():
            from core.safety import BackupManager, PreFlightCheck
            if not serial:
                device = PreFlightCheck.check_device_connection()
                device_serial = device.get("serial") if device.get("ok") else None
            else:
                device_serial = serial
            return BackupManager.auto_restore(device_serial, manifest_path)

        task_id = self._tm.run(
            "Restore Device",
            _restore,
            priority=priority or TaskPriority.HIGH,
            resource=ResourceType.SYSTEM,
            requires_protection=True,
        )
        self._record_operation("restore", task_id, "Restore dijadwalkan")
        return task_id

    def schedule_adb_repair(
        self,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan repair ADB server.

        Args:
            priority: Prioritas (default: CRITICAL)

        Returns:
            task_id
        """
        def _repair():
            from core.emergency import EmergencyRecovery
            er = EmergencyRecovery()
            results = {
                "kill": er.kill_adb_zombie(),
                "restart": er.restart_adb_service(),
            }
            return results

        task_id = self._tm.run(
            "ADB Repair",
            _repair,
            priority=priority or TaskPriority.CRITICAL,
            resource=ResourceType.ADB,
            max_retries=2,
        )
        self._record_operation("adb_repair", task_id, "ADB repair dijadwalkan")
        return task_id

    def schedule_cleanup(
        self,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan process cleanup.

        Args:
            priority: Prioritas (default: HIGH)

        Returns:
            task_id
        """
        def _cleanup():
            from core.process_cleanup import ProcessCleanup
            pc = ProcessCleanup()
            total = pc.cleanup_all()
            return {"total_cleaned": total}

        task_id = self._tm.run(
            "Process Cleanup",
            _cleanup,
            priority=priority or TaskPriority.HIGH,
            resource=ResourceType.SYSTEM,
        )
        self._record_operation("cleanup", task_id, "Process cleanup dijadwalkan")
        return task_id

    def schedule_auto_recovery(
        self,
        priority: Optional[TaskPriority] = None,
    ) -> str:
        """
        Jadwalkan auto-recovery (ADB + device reconnect).

        Args:
            priority: Prioritas (default: CRITICAL)

        Returns:
            task_id
        """
        def _recover():
            from core.auto_recovery import AutoRecovery
            ar = AutoRecovery()
            results = {
                "adb": ar.recover_adb(),
                "device": ar.recover_device(),
            }
            return {k: {"success": v.success, "message": v.message} for k, v in results.items()}

        task_id = self._tm.run(
            "Auto Recovery",
            _recover,
            priority=priority or TaskPriority.CRITICAL,
            resource=ResourceType.EMERGENCY,
        )
        recovery_log.warning(f"AUTO-RECOVERY SCHEDULED: {task_id}")
        self._record_operation("auto_recovery", task_id, "Auto recovery dijadwalkan")
        return task_id

    def schedule_chain(
        self,
        operations: List[Dict],
    ) -> List[str]:
        """
        Jadwalkan RANTAI operasi — setiap operasi jalan setelah yang sebelumnya selesai.

        Args:
            operations: List of operation configs:
                [
                    {"type": "backup", "serial": "xxx"},
                    {"type": "flash_stm32", "firmware_path": "/path/to/fw.bin"},
                    {"type": "cleanup"},
                ]

        Returns:
            List task_id berurutan
        """
        task_ids = []
        prev_id = None

        for op in operations:
            op_type = op.get("type", "")
            task_id = None

            if op_type == "scan":
                task_id = self.schedule_scan(priority=op.get("priority"))
            elif op_type == "emergency":
                task_id = self.schedule_emergency(full=op.get("full", True), priority=op.get("priority"))
            elif op_type == "flash_stm32":
                task_id = self.schedule_flash_stm32(
                    op["firmware_path"],
                    port=op.get("port", "auto"),
                    baudrate=op.get("baudrate", 115200),
                    priority=op.get("priority"),
                )
            elif op_type == "backup":
                task_id = self.schedule_backup(serial=op.get("serial"), priority=op.get("priority"))
            elif op_type == "restore":
                task_id = self.schedule_restore(
                    manifest_path=op.get("manifest_path"),
                    serial=op.get("serial"),
                    priority=op.get("priority"),
                )
            elif op_type == "adb_repair":
                task_id = self.schedule_adb_repair(priority=op.get("priority"))
            elif op_type == "cleanup":
                task_id = self.schedule_cleanup(priority=op.get("priority"))
            elif op_type == "auto_recovery":
                task_id = self.schedule_auto_recovery(priority=op.get("priority"))

            if task_id:
                # Set dependency ke task sebelumnya
                if prev_id:
                    task = self._tm.get_task(task_id)
                    if task:
                        task.depends_on.append(prev_id)
                        prev_task = self._tm.get_task(prev_id)
                        if prev_task:
                            prev_task.dependents.append(task_id)
                task_ids.append(task_id)
                prev_id = task_id

        return task_ids

    # =====================================================================
    # DASHBOARD & STATUS
    # =====================================================================

    def get_dashboard(self) -> Dict[str, Any]:
        """
        Dapatkan status lengkap semua sistem.

        Returns:
            Dict dengan status task manager, resource, process, dll
        """
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "task_manager": {
                "active_tasks": self._tm.active_count(),
                "total_tasks": len(self._tm.get_all_tasks()),
                "queue_size": self._tm.get_queue_length(),
                "recent_tasks": [t.to_dict() for t in self._tm.get_recent_tasks(5)],
                "pending_deps": len(self._tm.get_pending_deps()),
            },
            "resources": self._tm.get_resource_status(),
            "operations": {
                "history": self._operation_history[-10:],
                "total_operations": len(self._operation_history),
            },
        }

        # Coba dapatkan process cleanup stats
        try:
            from core.process_cleanup import ProcessCleanup
            dashboard["process_cleanup"] = ProcessCleanup().get_stats()
        except Exception:
            dashboard["process_cleanup"] = {"error": "Not available"}

        return dashboard

    def print_dashboard(self):
        """Tampilkan dashboard ke console"""
        from core.logger import Colors as C

        print(f"\n  {C.BOLD}{C.BRIGHT_CYAN}GLOBAL TASK ORCHESTRATOR DASHBOARD{C.RESET}")
        print(f"  {C.DIM}{'─' * 56}{C.RESET}")

        # Active tasks
        active = self._tm.get_active_tasks()
        print(f"  {C.CYAN}Active Tasks: {C.RESET}{C.BRIGHT_WHITE}{len(active)}{C.RESET}")
        for t in active[:5]:
            print(f"    {t.status_icon} {t.resource_label:12s} | {t.priority.name:8s} | {t.name[:50]}")
        if len(active) > 5:
            print(f"    {C.DIM}... and {len(active) - 5} more{C.RESET}")

        # Queue status
        print()
        print(f"  {C.CYAN}Resource Queues:{C.RESET}")
        resource_status = self._tm.get_resource_status()
        for rt_name, status in resource_status.items():
            icon = "🔴" if status["locked"] else "🟢"
            print(f"    {icon} {rt_name:12s} | queue: {status['queue_size']} | active: {status['active_tasks']}")

        # Recent operations
        print()
        print(f"  {C.CYAN}Recent Operations:{C.RESET}")
        for op in self._operation_history[-5:]:
            print(f"    {C.DIM}{op['timestamp'][11:19]}{C.RESET} | {op['type']:15s} | {op['description'][:50]}")

        # Process cleanup stats
        try:
            from core.process_cleanup import ProcessCleanup
            stats = ProcessCleanup().get_stats()
            print(f"\n  {C.CYAN}Process Cleanup:{C.RESET}")
            print(f"    Total cleaned: {stats['total_cleaned']}")
            print(f"    ADB killed: {stats['adb_killed']}")
            print(f"    Fastboot killed: {stats['fastboot_killed']}")
        except Exception:
            pass

        print(f"  {C.DIM}{'─' * 56}{C.RESET}")
        print()

    # =====================================================================
    # INTERNAL
    # =====================================================================

    def _record_operation(self, op_type: str, task_id: str, description: str):
        """Catat operasi ke history"""
        entry = {
            "type": op_type,
            "task_id": task_id,
            "description": description,
            "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            self._operation_history.append(entry)
            if len(self._operation_history) > self._max_history:
                self._operation_history = self._operation_history[-self._max_history:]


# ── Global instance ──
orchestrator = GlobalTaskOrchestrator()
