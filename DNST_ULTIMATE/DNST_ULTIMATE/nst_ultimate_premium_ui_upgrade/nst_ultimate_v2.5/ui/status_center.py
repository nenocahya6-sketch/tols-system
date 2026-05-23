
"""
NST Status Center — Floating Mini Monitor Widget
==================================================
Menampilkan task yang sedang aktif di background (flashing, scan, dll).
Tetap terlihat walau user pindah halaman.

Fitur:
- Auto-update via EventBus
- Progress bar untuk setiap task aktif
- Expandable/collapsible
- Tombol cancel task
- Ringkasan: total active, completed today
- Muncul di footer kanan bawah
"""
import threading
from typing import Dict, Optional, List
from datetime import datetime

import customtkinter as ctk

from core.event_bus import EventBus, event_bus
from core.task_manager import TaskManager, Task, TaskStatus, task_manager


class StatusCenter:
    """
    Status center widget — menampilkan task aktif + history.

    Args:
        parent: Parent widget (biasanya right_panel atau root)
        width: Lebar widget
    """

    def __init__(self, parent, width: int = 350):
        self.parent = parent
        self.width = width
        self._task_rows: Dict[str, dict] = {}
        self._expanded = True
        self._lock = threading.Lock()

        # ── Main frame ──
        self.frame = ctk.CTkFrame(parent, corner_radius=8, fg_color="#1a1a2e", height=0)
        self.frame.pack(fill="x", padx=10, pady=(0, 8))
        self.frame.pack_propagate(False)

        # ── Header bar (clickable to expand/collapse) ──
        self._header = ctk.CTkFrame(self.frame, fg_color="transparent", height=24)
        self._header.pack(fill="x", padx=8, pady=(4, 0))
        self._header.pack_propagate(False)

        self._toggle_label = ctk.CTkLabel(
            self._header,
            text="▼  ACTIVE TASKS (0)",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#888888",
        )
        self._toggle_label.pack(side="left")

        self._active_count_label = ctk.CTkLabel(
            self._header,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["accent_green"],
        )
        self._active_count_label.pack(side="right", padx=(0, 5))

        # Click to toggle
        self._header.bind("<Button-1>", lambda e: self._toggle_expand())

        # ── Task list container ──
        self._task_container = ctk.CTkFrame(self.frame, fg_color="transparent")
        self._task_container.pack(fill="both", expand=True, padx=8, pady=(4, 6))

        # ── Register event listeners ──
        self._registered = False
        self._register_events()

        # ── Initial height ──
        self._set_expanded_height()

    # ── Public API ──

    def set_expanded(self, expanded: bool):
        """Set expanded/collapsed state"""
        self._expanded = expanded
        self._set_expanded_height()
        self._update_header_text()

    def is_expanded(self) -> bool:
        return self._expanded

    def destroy(self):
        """Cleanup event listeners and destroy widget"""
        if self._registered:
            event_bus.off(EventBus.TASK_CREATED, self._on_task_created)
            event_bus.off(EventBus.TASK_UPDATED, self._on_task_updated)
            event_bus.off(EventBus.TASK_COMPLETED, self._on_task_completed)
            event_bus.off(EventBus.TASK_FAILED, self._on_task_failed)
        try:
            self.frame.destroy()
        except Exception:
            pass

    # ── Event Handlers ──

    def _register_events(self):
        """Register event bus listeners"""
        self._registered = True
        event_bus.on(EventBus.TASK_CREATED, self._on_task_created)
        event_bus.on(EventBus.TASK_UPDATED, self._on_task_updated)
        event_bus.on(EventBus.TASK_COMPLETED, self._on_task_completed)
        event_bus.on(EventBus.TASK_FAILED, self._on_task_failed)

    def _on_task_created(self, task: Task):
        """Task baru dibuat — tambahkan ke tampilan"""
        self.parent.after(0, self._add_task_row, task)

    def _on_task_updated(self, task: Task):
        """Task diupdate — refresh tampilan"""
        self.parent.after(0, self._update_task_row, task)

    def _on_task_completed(self, task: Task):
        """Task selesai — update status"""
        self.parent.after(0, self._complete_task_row, task)

    def _on_task_failed(self, task: Task):
        """Task gagal — update status"""
        self.parent.after(0, self._fail_task_row, task)

    # ── Task Row Management ──

    def _add_task_row(self, task: Task):
        """Add a task row to the list"""
        if task.id in self._task_rows:
            return

        row = ctk.CTkFrame(self._task_container, fg_color="transparent", height=20)
        row.pack(fill="x", pady=(0, 2), anchor="w")

        # Status icon + name
        name_label = ctk.CTkLabel(
            row,
            text=f"🔄  {task.name}",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#cccccc",
            anchor="w",
        )
        name_label.pack(side="left")

        # Progress percentage
        pct_label = ctk.CTkLabel(
            row,
            text=f"{task.progress_pct}%",
            font=ctk.CTkFont(size=9),
            text_color="#888888",
            width=30,
        )
        pct_label.pack(side="right")

        # Progress bar
        progress = ctk.CTkProgressBar(
            self._task_container,
            height=4,
            corner_radius=2,
            fg_color="#2a2a3e",
            progress_color=COLORS["accent_blue"],
        )
        progress.pack(fill="x", pady=(0, 4))
        progress.set(task.progress_pct / 100.0)

        # Separator
        sep = ctk.CTkFrame(self._task_container, height=1, fg_color="#2a2a40")
        sep.pack(fill="x")

        self._task_rows[task.id] = {
            "row": row,
            "name_label": name_label,
            "pct_label": pct_label,
            "progress": progress,
            "separator": sep,
        }

        # Ensure container is visible
        if not self._expanded:
            self._toggle_expand()

        self._update_header_count()

    def _update_task_row(self, task: Task):
        """Update progress bar and percentage"""
        row_data = self._task_rows.get(task.id)
        if not row_data:
            self._add_task_row(task)
            return

        try:
            row_data["progress"].set(task.progress_pct / 100.0)
            row_data["pct_label"].configure(text=f"{task.progress_pct}%")

            # Update name if message changed
            if task.message:
                row_data["name_label"].configure(text=f"🔄  {task.name} — {task.message}")
        except Exception:
            pass

    def _complete_task_row(self, task: Task):
        """Mark task as completed"""
        row_data = self._task_rows.get(task.id)
        if not row_data:
            return

        try:
            row_data["name_label"].configure(
                text=f"✅  {task.name} — Selesai ({task.duration or '?'})",
                text_color=COLORS["accent_green"],
            )
            row_data["progress"].configure(progress_color=COLORS["accent_green"])
            row_data["progress"].set(1.0)
            row_data["pct_label"].configure(text="100%", text_color=COLORS["accent_green"])

            # Auto-remove after delay
            self.parent.after(5000, lambda: self._remove_task_row(task.id))
        except Exception:
            pass
        self._update_header_count()

    def _fail_task_row(self, task: Task):
        """Mark task as failed"""
        row_data = self._task_rows.get(task.id)
        if not row_data:
            return

        try:
            error_text = f" — {task.error[:40]}" if task.error else ""
            row_data["name_label"].configure(
                text=f"❌  {task.name}{error_text}",
                text_color=COLORS["accent_red"],
            )
            row_data["progress"].configure(progress_color=COLORS["accent_red"])
            row_data["pct_label"].configure(text="FAILED", text_color=COLORS["accent_red"])
        except Exception:
            pass
        self._update_header_count()

    def _remove_task_row(self, task_id: str):
        """Remove a task row (after delay)"""
        row_data = self._task_rows.pop(task_id, None)
        if row_data:
            try:
                row_data["row"].destroy()
                row_data["progress"].destroy()
                row_data["separator"].destroy()
            except Exception:
                pass
        self._update_header_count()

    # ── UI Helpers ──

    def _toggle_expand(self):
        """Toggle expand/collapse"""
        self._expanded = not self._expanded
        self._set_expanded_height()
        self._update_header_text()

    def _set_expanded_height(self):
        """Set frame height based on expand state"""
        if self._expanded:
            num_tasks = len(self._task_rows)
            content_height = max(30, num_tasks * 32 + 10)
            total_height = min(200, 28 + content_height)
            self.frame.configure(height=total_height)
        else:
            self.frame.configure(height=28)

    def _update_header_text(self):
        """Update header toggle label"""
        arrow = "▼" if self._expanded else "▶"
        count = len(self._task_rows)
        self._toggle_label.configure(text=f"{arrow}  ACTIVE TASKS ({count})")

    def _update_header_count(self):
        """Update active count badge"""
        active = len(task_manager.get_active_tasks())
        if active > 0:
            self._active_count_label.configure(
                text=f"{active} running",
                text_color=COLORS["accent_green"],
            )
        else:
            self._active_count_label.configure(text="", text_color=COLORS["accent_green"])

        self._update_header_text()
        self._set_expanded_height()


# ── Warna lokal (copy dari nst_gui.py supaya standalone) ──
COLORS = {
    "sidebar_bg": "#1a1a2e",
    "accent_blue": "#4fc3f7",
    "accent_green": "#4caf50",
    "accent_red": "#f44336",
    "accent_orange": "#ff9800",
    "accent_purple": "#ab47bc",
    "accent_cyan": "#26c6da",
}
