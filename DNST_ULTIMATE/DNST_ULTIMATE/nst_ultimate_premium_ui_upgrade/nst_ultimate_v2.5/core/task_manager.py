
"""
NST Task Manager — Background task execution engine
=====================================================
Task QUEUE, Worker Thread, Resource Locks, Status Tracking.
Semua task berjalan di background thread — UI tetap responsif.

ARSITEKTUR BARU:
- Queue-based: task masuk antrian, worker proses satu per satu (per resource)
- Resource Locks: ADB, Fastboot, Flash — task untuk resource yang SAMA jalan serial
- Resource berbeda bisa jalan PARALEL (contoh: ADB scan + Flash STM32)
- Concurrency control: max N task per resource type
- Process Isolation: subprocess wrapper untuk flashing/repair

Fitur:
- Task creation with UUID
- Queue execution via worker thread pool (1 per resource)
- Progress tracking (0-100%)
- Status: pending → running → completed/failed/cancelled
- Resource-level locking untuk mencegah konflik ADB & fastboot
- Event-driven updates via EventBus
- Active task monitoring
- Recent task history (last 10)
"""
import threading
import uuid
import time
import queue
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta

from core.event_bus import EventBus, event_bus


# ========== PRIORITY SYSTEM ==========

class TaskPriority(Enum):
    """Prioritas task — 0 = tertinggi, 3 = terendah"""
    CRITICAL = 0   # Emergency, recovery — jalan DULUAN
    HIGH = 1       # Flashing, backup — penting
    NORMAL = 2     # Scan, diagnostic — standard
    LOW = 3        # Info, check — bisa nunggu

    def __lt__(self, other):
        if isinstance(other, TaskPriority):
            return self.value < other.value
        return NotImplemented


# Mapping nama task ke prioritas otomatis
TASK_PRIORITY_MAP = {
    "emergency": TaskPriority.CRITICAL,
    "recovery": TaskPriority.CRITICAL,
    "kill": TaskPriority.CRITICAL,
    "restart": TaskPriority.HIGH,
    "flash": TaskPriority.HIGH,
    "unlock": TaskPriority.HIGH,
    "backup": TaskPriority.HIGH,
    "restore": TaskPriority.HIGH,
    "reset": TaskPriority.HIGH,
    "root": TaskPriority.HIGH,
    "frp": TaskPriority.HIGH,
    "scan": TaskPriority.NORMAL,
    "detect": TaskPriority.NORMAL,
    "diagnostic": TaskPriority.NORMAL,
    "check": TaskPriority.LOW,
    "info": TaskPriority.LOW,
    "about": TaskPriority.LOW,
}


def detect_priority(name: str) -> TaskPriority:
    """Deteksi prioritas dari nama task otomatis"""
    name_lower = name.lower()
    for keyword, priority in TASK_PRIORITY_MAP.items():
        if keyword in name_lower:
            return priority
    return TaskPriority.NORMAL


class ResourceType(Enum):
    """Jenis resource — task untuk resource SAMA jalan serial"""
    ADB = "adb"
    FASTBOOT = "fastboot"
    FLASH = "flash"        # STM32/Generic flashing
    DEVICE = "device"      # Device scanning (ringan, bisa paralel)
    SYSTEM = "system"      # System tools, env check
    EMERGENCY = "emergency"
    GENERIC = "generic"


class TaskStatus(Enum):
    """Status lifecycle: pending → running → completed/failed/cancelled"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    VALIDATING = "validating"  # Sedang divalidasi oleh protection layer

    def __str__(self):
        return self.value

    @property
    def is_active(self) -> bool:
        return self in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.VALIDATING)

    @property
    def is_finished(self) -> bool:
        return self in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


@dataclass
class Task:
    """Representasi satu task yang sedang/akan dijalankan"""
    id: str = ""
    name: str = ""
    status: TaskStatus = TaskStatus.PENDING
    resource: ResourceType = ResourceType.GENERIC
    priority: TaskPriority = TaskPriority.NORMAL
    progress: int = 0
    progress_max: int = 100
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    func: Optional[Callable] = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    queued_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 0
    requires_protection: bool = False  # Butuh validasi protection layer?
    depends_on: List[str] = field(default_factory=list)  # Task IDs yang harus selesai dulu
    dependents: List[str] = field(default_factory=list)  # Task IDs yang depend pada task ini
    block_index: int = 0  # Blok eksekusi (task dalam block yang sama jalan serial)

    @property
    def duration(self) -> Optional[str]:
        """Human-readable duration string"""
        if self.started_at:
            end = self.completed_at or datetime.now()
            delta = end - self.started_at
            total_seconds = int(delta.total_seconds())
            if total_seconds < 60:
                return f"{total_seconds}s"
            elif total_seconds < 3600:
                return f"{total_seconds // 60}m {total_seconds % 60}s"
            else:
                return f"{total_seconds // 3600}h {(total_seconds % 3600) // 60}m"
        return None

    @property
    def progress_pct(self) -> int:
        if self.progress_max <= 0:
            return 0
        return min(int((self.progress / self.progress_max) * 100), 100)

    @property
    def status_icon(self) -> str:
        icons = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.QUEUED: "⏳",
            TaskStatus.VALIDATING: "🔍",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫",
        }
        return icons.get(self.status, "❓")

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": str(self.status),
            "resource": self.resource.value,
        "progress": self.progress_pct,
        "message": self.message,
        "duration": self.duration,
        "error": self.error,
        "retry_count": self.retry_count,
        "priority": self.priority.value,
        "priority_label": self.priority.name,
        "depends_on": list(self.depends_on),
        "dependents": list(self.dependents),
    }

    @property
    def resource_label(self) -> str:
        labels = {
            ResourceType.ADB: "ADB",
            ResourceType.FASTBOOT: "Fastboot",
            ResourceType.FLASH: "Flash",
            ResourceType.DEVICE: "Device",
            ResourceType.SYSTEM: "System",
            ResourceType.EMERGENCY: "Emergency",
            ResourceType.GENERIC: "Generic",
        }
        return labels.get(self.resource, "?")


def resource_from_name(name: str) -> ResourceType:
    """Detect resource type from task name"""
    name_lower = name.lower()
    if any(kw in name_lower for kw in ["adb", "fastboot", "flash", "firmware", "stm32"]):
        return ResourceType.FLASH
    if any(kw in name_lower for kw in ["adb"]):
        return ResourceType.ADB
    if any(kw in name_lower for kw in ["fastboot"]):
        return ResourceType.FASTBOOT
    if any(kw in name_lower for kw in ["scan", "detect", "device"]):
        return ResourceType.DEVICE
    if any(kw in name_lower for kw in ["emergency", "recovery"]):
        return ResourceType.EMERGENCY
    if any(kw in name_lower for kw in ["check", "install", "system", "info"]):
        return ResourceType.SYSTEM
    return ResourceType.GENERIC


class TaskManager:
    """
    Task Manager singleton — Queue-based execution dengan resource locking.

    Cara pakai:
        tm = TaskManager()
        task_id = tm.run("Flash Firmware", my_flash_func, arg1, arg2)
        tm.on_event("task:completed", lambda t: print(f"Done: {t.name}"))
    """

    _instance: Optional["TaskManager"] = None
    _singleton_lock = threading.Lock()

    # Resource locks — mencegah konflik
    # Dua task untuk resource SAMA jalan serial
    _resource_locks: Dict[ResourceType, threading.Lock] = {
        ResourceType.ADB: threading.Lock(),
        ResourceType.FASTBOOT: threading.Lock(),
        ResourceType.FLASH: threading.Lock(),
        ResourceType.DEVICE: threading.Lock(),   # Bisa paralel via semaphore
        ResourceType.SYSTEM: threading.Lock(),
        ResourceType.EMERGENCY: threading.Lock(),
        ResourceType.GENERIC: threading.Lock(),
    }

    # Semaphore untuk resource ringan (device scan bisa paralel)
    _resource_semaphores: Dict[ResourceType, threading.Semaphore] = {
        ResourceType.DEVICE: threading.Semaphore(3),  # Max 3 scan paralel
        ResourceType.GENERIC: threading.Semaphore(5),
    }

    def __new__(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._tasks: Dict[str, Task] = {}
            self._lock = threading.Lock()
            self._event_bus = event_bus

            # Queue per resource type — PriorityQueue agar task prioritas tinggi jalan duluan
            self._queues: Dict[ResourceType, "queue.PriorityQueue"] = {
                rt: queue.PriorityQueue() for rt in ResourceType
            }

            # Dependency tracking — task yang menunggu dependensi selesai
            self._pending_deps: Dict[str, Task] = {}  # task_id -> Task (menunggu dependencies)
            self._completed_ids: Set[str] = set()     # task_id yang sudah selesai

            # Workers
            self._workers: Dict[ResourceType, threading.Thread] = {}
            self._running = True

            # Max concurrency
            self._max_concurrent = 5

            # Start worker threads
            self._start_workers()

    def _start_workers(self):
        """Start worker thread untuk setiap resource type"""
        for resource in ResourceType:
            worker = threading.Thread(
                target=self._worker_loop,
                args=(resource,),
                daemon=True,
                name=f"Worker-{resource.value}",
            )
            self._workers[resource] = worker
            worker.start()

    def _worker_loop(self, resource: ResourceType):
        """Worker loop — ambil task dari queue PriorityQueue dan eksekusi"""
        resource_queue = self._queues[resource]
        resource_lock = self._resource_locks[resource]
        semaphore = self._resource_semaphores.get(resource)

        while self._running:
            try:
                # Ambil task dari PriorityQueue (timeout 1 detik)
                # PriorityQueue.get() mengembalikan item dengan prioritas terendah dulu
                # Format item: (priority_value, timestamp, task_id)
                try:
                    priority_val, timestamp, task_id = resource_queue.get(timeout=1)
                except queue.Empty:
                    continue

                # Dapatkan task object
                task = self._get_task(task_id)
                if not task or task.status == TaskStatus.CANCELLED:
                    resource_queue.task_done()
                    continue

                # CEK DEPENDENCIES — jika task memiliki dependensi yang belum selesai,
                # kembalikan ke queue dengan prioritas yang sama
                if not self._check_dependencies(task):
                    # Task belum siap, masukkan ke pending_deps
                    with self._lock:
                        self._pending_deps[task_id] = task
                    resource_queue.task_done()
                    continue

                # Acquire lock untuk resource ini
                if semaphore:
                    semaphore.acquire()
                else:
                    resource_lock.acquire()

                try:
                    # Execute
                    self._execute_task(task)
                finally:
                    # Release lock
                    if semaphore:
                        semaphore.release()
                    else:
                        resource_lock.release()

                resource_queue.task_done()

            except Exception:
                pass

    def _check_dependencies(self, task: Task) -> bool:
        """
        Cek apakah semua dependensi task sudah selesai.

        Args:
            task: Task yang akan dicek

        Returns:
            True jika semua dependensi sudah selesai
        """
        if not task.depends_on:
            return True

        with self._lock:
            for dep_id in task.depends_on:
                if dep_id not in self._completed_ids:
                    # Cek task masih ada — jika sudah dihapus, anggap selesai
                    dep_task = self._tasks.get(dep_id)
                    if dep_task and not dep_task.status.is_finished:
                        return False
            return True

    def _check_pending_dependencies(self):
        """
        Periodik: cek apakah ada task di pending_deps yang dependensinya sudah selesai.
        Jika ya, masukkan kembali ke queue.
        """
        with self._lock:
            ready_ids = [
                tid for tid, task in self._pending_deps.items()
                if self._check_dependencies(task) and not task.status.is_finished
            ]
            for tid in ready_ids:
                task = self._pending_deps.pop(tid)
                if task:
                    # Masukkan ke queue resource dengan prioritas asli
                    now = datetime.now()
                    queue_item = (task.priority.value, now.timestamp(), tid)
                    try:
                        self._queues[task.resource].put(queue_item)
                    except Exception:
                        pass

    # ── Public API ──

    def run(
        self,
        name: str,
        func: Callable,
        *args,
        priority: Optional[TaskPriority] = None,
        resource: Optional[ResourceType] = None,
        requires_protection: bool = False,
        max_retries: int = 0,
        **kwargs
    ) -> str:
        """
        Kirim task ke PriorityQueue — akan dieksekusi oleh worker thread.
        Task dengan prioritas tinggi (CRITICAL) jalan duluan.

        Args:
            name: Nama task (untuk display)
            func: Function yang akan dijalankan
            priority: Prioritas task (auto-detect jika None)
            resource: Resource type (auto-detect jika None)
            requires_protection: Apakah perlu validasi protection layer
            max_retries: Jumlah maksimal retry jika gagal
            *args, **kwargs: Arguments untuk func

        Returns:
            task_id (string)
        """
        if resource is None:
            resource = resource_from_name(name)

        if priority is None:
            priority = detect_priority(name)

        task_id = uuid.uuid4().hex[:12]
        task = Task(
            id=task_id,
            name=name,
            status=TaskStatus.QUEUED,
            resource=resource,
            priority=priority,
            func=func,
            args=args,
            kwargs=kwargs,
            queued_at=datetime.now(),
            max_retries=max_retries,
            requires_protection=requires_protection,
        )

        with self._lock:
            self._tasks[task_id] = task

        self._event_bus.emit(EventBus.TASK_CREATED, task)

        # Masukkan ke PriorityQueue — format: (priority_value, timestamp, task_id)
        # PriorityQueue otomatis mengurutkan: priority 0 (CRITICAL) jalan duluan
        now = datetime.now()
        queue_item = (priority.value, now.timestamp(), task_id)
        self._queues[resource].put(queue_item)

        # Subscribe ke event completed untuk dependency tracking
        def _on_completed(t):
            if t.id == task_id:
                with self._lock:
                    self._completed_ids.add(task_id)
                    # Cek dependents yang menunggu
                    for dep_id in task.dependents:
                        dep_task = self._pending_deps.get(dep_id)
                        if dep_task:
                            self._check_pending_dependencies()
                    self._event_bus.off(EventBus.TASK_COMPLETED, _on_completed)

        if task.dependents:
            self._event_bus.on(EventBus.TASK_COMPLETED, _on_completed)

        # Emit update via EventBus
        self._event_bus.emit(EventBus.TASK_UPDATED, task)

        return task_id

    def run_with_deps(
        self,
        name: str,
        func: Callable,
        *args,
        depends_on: Optional[List[str]] = None,
        priority: Optional[TaskPriority] = None,
        resource: Optional[ResourceType] = None,
        requires_protection: bool = False,
        max_retries: int = 0,
        **kwargs
    ) -> str:
        """
        Kirim task dengan DEPENDENCIES — hanya jalan jika task lain sudah selesai.

        Args:
            name: Nama task
            func: Function yang akan dijalankan
            depends_on: List task_id yang HARUS selesai sebelum task ini jalan
            priority: Prioritas task
            resource: Resource type
            requires_protection: Butuh protection layer?
            max_retries: Max retry
            *args, **kwargs: Args untuk func

        Returns:
            task_id
        """
        task_id = self.run(
            name, func, *args,
            priority=priority,
            resource=resource,
            requires_protection=requires_protection,
            max_retries=max_retries,
            **kwargs
        )

        if depends_on:
            task = self._get_task(task_id)
            if task:
                task.depends_on = list(depends_on)
                # Register dependents di parent tasks
                for dep_id in depends_on:
                    dep_task = self._get_task(dep_id)
                    if dep_task and dep_id not in dep_task.dependents:
                        dep_task.dependents.append(task_id)

        return task_id

    def run_block(
        self,
        tasks: List[Tuple[str, Callable, tuple, dict]],
        resource: Optional[ResourceType] = None,
        priority: Optional[TaskPriority] = None,
    ) -> List[str]:
        """
        Jalankan BLOK task — task dalam block dieksekusi serial berurutan.
        Setiap task depend pada task sebelumnya dalam blok.

        Args:
            tasks: List of (name, func, args, kwargs)
            resource: Resource type untuk semua task
            priority: Prioritas untuk semua task

        Returns:
            List task_id
        """
        task_ids = []
        prev_id = None

        for i, (name, func, args, kwargs) in enumerate(tasks):
            deps = [prev_id] if prev_id else None
            tid = self.run_with_deps(
                name, func, *args,
                depends_on=deps,
                priority=priority,
                resource=resource,
                **kwargs
            )
            task_ids.append(tid)

            # Update task dengan block_index
            task = self._get_task(tid)
            if task:
                task.block_index = i

            prev_id = tid

        return task_ids


    def run_progress(
        self,
        name: str,
        func: Callable,
        progress_callback: Optional[Callable] = None,
        *args,
        priority: Optional[TaskPriority] = None,
        resource: Optional[ResourceType] = None,
        requires_protection: bool = False,
        **kwargs
    ) -> str:
        """
        Jalankan task dengan progress tracking via callback.

        Fungsi akan dipanggil dengan (update_progress, task_id) sebagai arg tambahan.
        Di dalam fungsi, panggil update_progress(percent, message) untuk update.
        """
        if resource is None:
            resource = resource_from_name(name)

        if priority is None:
            priority = detect_priority(name)

        def wrapper(update_fn, task_id, *args, **kwargs):
            try:
                result = func(update_fn, task_id, *args, **kwargs)
                return result
            except Exception:
                raise

        task_id = uuid.uuid4().hex[:12]
        task = Task(
            id=task_id,
            name=name,
            status=TaskStatus.QUEUED,
            resource=resource,
            priority=priority,
            func=wrapper,
            args=((), kwargs),
            kwargs={},
            queued_at=datetime.now(),
            requires_protection=requires_protection,
        )

        with self._lock:
            self._tasks[task_id] = task

        self._event_bus.emit(EventBus.TASK_CREATED, task)

        # Buat wrapper update progress
        def update_progress(progress: int, message: str = ""):
            self.update_progress(task_id, progress, message)

        # Task akan menerima (update_progress, task_id) sebagai arg pertama
        task.args = ((update_progress, task_id), kwargs)

        # Masukkan ke PriorityQueue dengan format yang benar
        now = datetime.now()
        queue_item = (priority.value, now.timestamp(), task_id)
        self._queues[resource].put(queue_item)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Batalkan task — jika masih di queue atau running"""
        task = self._get_task(task_id)
        if task and task.status.is_active:
            task.status = TaskStatus.CANCELLED
            self._event_bus.emit(EventBus.TASK_CANCELLED, task)
            self._event_bus.emit(EventBus.TASK_UPDATED, task)
            return True
        return False

    def update_progress(self, task_id: str, progress: int, message: str = ""):
        """Update progress task (0-100 persen)"""
        task = self._get_task(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.progress = max(0, min(progress, 100))
            if message:
                task.message = message
            self._event_bus.emit(EventBus.TASK_PROGRESS, task)
            self._event_bus.emit(EventBus.TASK_UPDATED, task)

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._get_task(task_id)

    def get_all_tasks(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())

    def get_active_tasks(self) -> List[Task]:
        return [t for t in self.get_all_tasks() if t.status.is_active]

    def get_tasks_by_resource(self, resource: ResourceType) -> List[Task]:
        return [t for t in self.get_all_tasks() if t.resource == resource]

    def get_recent_tasks(self, limit: int = 10) -> List[Task]:
        tasks = self.get_all_tasks()
        tasks.sort(key=lambda t: t.started_at or datetime.min, reverse=True)
        return tasks[:limit]

    def get_completed_tasks(self, limit: int = 5) -> List[Task]:
        tasks = [t for t in self.get_all_tasks() if t.status.is_finished]
        tasks.sort(key=lambda t: t.completed_at or datetime.min, reverse=True)
        return tasks[:limit]

    def clear_completed(self):
        """Hapus task yang sudah selesai dari memory"""
        with self._lock:
            self._tasks = {
                tid: t for tid, t in self._tasks.items()
                if t.status.is_active
            }

    def clear_all(self):
        active = self.get_active_tasks()
        with self._lock:
            self._tasks = {t.id: t for t in active}

    def on_event(self, event: str, callback: Callable):
        self._event_bus.on(event, callback)

    def off_event(self, event: str, callback: Callable):
        self._event_bus.off(event, callback)

    def active_count(self) -> int:
        return len(self.get_active_tasks())

    def has_active_tasks(self) -> bool:
        return self.active_count() > 0

    def get_queue_length(self, resource: Optional[ResourceType] = None) -> int:
        """Dapatkan jumlah task yang mengantri"""
        if resource:
            return self._queues[resource].qsize()
        return sum(q.qsize() for q in self._queues.values())

    def get_resource_status(self) -> Dict[str, Dict]:
        """Dapatkan status semua resource locks"""
        status = {}
        for rt, lock in self._resource_locks.items():
            status[rt.value] = {
                "locked": lock.locked(),
                "queue_size": self._queues[rt].qsize(),
                "active_tasks": len(self.get_tasks_by_resource(rt)),
            }
        return status

    def wait_for_resource(self, resource: ResourceType, timeout: float = 30) -> bool:
        """Tunggu hingga resource tersedia (tidak ada task aktif untuk resource tsb)"""
        start = time.time()
        while time.time() - start < timeout:
            if not self._resource_locks[resource].locked():
                return True
            time.sleep(0.5)
        return False

    def get_queue_position(self, task_id: str) -> Optional[int]:
        """
        Dapatkan perkiraan posisi task di queue.
        PriorityQueue tidak mendukung peek, jadi ini estimasi.

        Returns:
            Perkiraan posisi (0 = next), atau None jika tidak di queue
        """
        task = self._get_task(task_id)
        if not task:
            return None

        resource = task.resource
        queue = self._queues[resource]

        # PriorityQueue.qsize() memberikan jumlah item dalam queue
        # Posisi diperkirakan dari jumlah item dengan prioritas lebih tinggi
        try:
            qsize = queue.qsize()
            if qsize == 0:
                return 0
            return max(0, qsize - 1)
        except Exception:
            return None

    def get_pending_deps(self) -> List[Task]:
        """Dapatkan task yang sedang menunggu dependensi"""
        with self._lock:
            return list(self._pending_deps.values())

    def get_completed_ids(self) -> Set[str]:
        """Dapatkan set task_id yang sudah selesai"""
        with self._lock:
            return set(self._completed_ids)

    def stop(self):
        """Stop semua workers dan clear pending tasks"""
        self._running = False

    # ── Internal ──

    def _execute_task(self, task: Task):
        """Internal: jalankan task dan update status"""
        task_id = task.id

        # Protection layer — validasi sebelum eksekusi
        if task.requires_protection:
            task.status = TaskStatus.VALIDATING
            self._event_bus.emit(EventBus.TASK_UPDATED, task)

            valid, error_msg = self._run_protection_check(task)
            if not valid:
                task.status = TaskStatus.FAILED
                task.error = error_msg or "Gagal validasi protection layer"
                task.completed_at = datetime.now()
                self._event_bus.emit(EventBus.TASK_FAILED, task)
                self._event_bus.emit(EventBus.TASK_UPDATED, task)
                return

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        self._event_bus.emit(EventBus.TASK_STARTED, task)

        for attempt in range(task.max_retries + 1):
            try:
                task.retry_count = attempt

                # Eksekusi function
                if task.args and len(task.args) == 2 and isinstance(task.args[0], tuple) and isinstance(task.args[1], dict):
                    # Dari run_progress
                    actual_args = task.args[0]
                    actual_kwargs = task.args[1]
                    result = task.func(*actual_args, **actual_kwargs)
                else:
                    result = task.func(*task.args, **task.kwargs)

                # Sukses — set completed_at + emit events
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.progress = 100
                task.message = "Selesai"
                task.completed_at = datetime.now()
                self._event_bus.emit(EventBus.TASK_COMPLETED, task)
                self._event_bus.emit(EventBus.TASK_UPDATED, task)
                return

            except Exception as e:
                if attempt < task.max_retries:
                    # Retry dengan exponential backoff — jangan set completed_at
                    time.sleep(1 * (attempt + 1))
                    continue

                # Gagal total — set completed_at + emit events
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now()
                self._event_bus.emit(EventBus.TASK_FAILED, task)
                self._event_bus.emit(EventBus.TASK_UPDATED, task)

    def _run_protection_check(self, task: Task) -> tuple:
        """Jalankan protection layer validation"""
        try:
            from core.protection import ProtectionLayer
            protector = ProtectionLayer()
            result = protector.validate_task(task)
            return result.valid, result.error_message
        except ImportError:
            # Protection layer belum ada — skip
            return True, None
        except Exception as e:
            return False, str(e)

    def _get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)


# ── Global instance ──
task_manager = TaskManager()
