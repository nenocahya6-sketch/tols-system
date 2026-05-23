
"""
NST Toast Notification — Non-blocking notifications untuk GUI
==============================================================
Fitur:
- Muncul di pojok kanan atas
- Auto-dismiss setelah timeout
- Bisa ditutup manual (klik)
- Stacking (notif baru di atas)
- Color-coded: info, success, warning, error
- Thread-safe (bisa dipanggil dari thread mana pun)

Cara pakai:
    notifier = ToastNotifications(parent_frame)
    notifier.show_success("Flash Completed!")
    notifier.show_error("Device not found", timeout=8000)
"""
import threading
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

import customtkinter as ctk

from core.event_bus import EventBus, event_bus


# ── Konfigurasi warna ──

NOTIF_COLORS = {
    "info": {"bg": "#1565c0", "icon": "ℹ️", "text": "white"},
    "success": {"bg": "#2e7d32", "icon": "✅", "text": "white"},
    "warning": {"bg": "#e65100", "icon": "⚠️", "text": "white"},
    "error": {"bg": "#c62828", "icon": "❌", "text": "white"},
}

NOTIF_SIZE = {"width": 320, "max_height": 80}
NOTIF_TIMEOUT = {"info": 4000, "success": 4000, "warning": 5000, "error": 7000}


class ToastNotifications:
    """
    Overlay notification system — muncul di pojok kanan atas parent widget.

    Args:
        parent: Widget yang menjadi anchor (biasanya root atau right_panel)
        max_visible: Maksimal notif yang terlihat bersamaan
    """

    def __init__(self, parent, max_visible: int = 5):
        self.parent = parent
        self.max_visible = max_visible
        self._notifications: list = []
        self._lock = threading.Lock()

        # Create container frame that overlays the parent
        self._container = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            corner_radius=0,
        )
        self._container.place(relx=1.0, y=5, anchor="ne")
        self._container.lift()

    # ── Public API ──

    def show_info(self, message: str, timeout: Optional[int] = None):
        """Tampilkan notifikasi info"""
        self._show("info", message, timeout)

    def show_success(self, message: str, timeout: Optional[int] = None):
        """Tampilkan notifikasi sukses"""
        self._show("success", message, timeout)

    def show_warning(self, message: str, timeout: Optional[int] = None):
        """Tampilkan notifikasi warning"""
        self._show("warning", message, timeout)

    def show_error(self, message: str, timeout: Optional[int] = None):
        """Tampilkan notifikasi error"""
        self._show("error", message, timeout)

    def clear_all(self):
        """Hapus semua notifikasi yang terlihat"""
        for notif in self._notifications[:]:
            notif["frame"].destroy()
        self._notifications.clear()

    def destroy(self):
        """Destroy semua notifikasi dan container"""
        self.clear_all()
        self._container.destroy()

    # ── Internal ──

    def _show(self, level: str, message: str, timeout: Optional[int] = None):
        """Internal: buat notifikasi baru"""
        if not message:
            return

        colors = NOTIF_COLORS.get(level, NOTIF_COLORS["info"])
        duration = timeout or NOTIF_TIMEOUT.get(level, 4000)

        # Create notification frame - thread-safe via after()
        self.parent.after(0, self._create_notif, level, colors, message, duration)

    def _create_notif(self, level: str, colors: dict, message: str, duration: int):
        """Buat notifikasi widget (panggil dari main thread)"""
        # Limit visible notifications
        if len(self._notifications) >= self.max_visible:
            oldest = self._notifications.pop(0)
            try:
                oldest["frame"].destroy()
            except Exception:
                pass

        # Create notification frame
        frame = ctk.CTkFrame(
            self._container,
            corner_radius=8,
            fg_color=colors["bg"],
            height=40,
        )
        frame.pack(pady=(0, 5), padx=10, fill="x")

        # Icon + message
        label = ctk.CTkLabel(
            frame,
            text=f"{colors['icon']}  {message}",
            font=ctk.CTkFont(size=12),
            text_color=colors["text"],
            anchor="w",
            wraplength=260,
            justify="left",
        )
        label.pack(side="left", padx=(10, 5), pady=8, fill="x", expand=True)

        # Close button
        close_btn = ctk.CTkButton(
            frame,
            text="✕",
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            text_color="white",
            hover_color="rgba(255,255,255,0.2)",
            width=20,
            height=20,
            corner_radius=10,
            command=lambda: self._dismiss(frame),
        )
        close_btn.pack(side="right", padx=(0, 5), pady=5)

        # Store
        notif = {
            "frame": frame,
            "label": label,
            "level": level,
            "created_at": datetime.now(),
            "timer": None,
        }
        self._notifications.append(notif)

        # Auto-dismiss after timeout
        if duration > 0:
            notif["timer"] = self.parent.after(duration, lambda: self._dismiss(frame))

        # Emit event
        event_bus.emit(EventBus.UI_NOTIFICATION, level, message)

    def _dismiss(self, frame):
        """Hapus notifikasi dari tampilan"""
        try:
            frame.destroy()
        except Exception:
            pass

        # Remove from list
        with self._lock:
            self._notifications = [
                n for n in self._notifications if n["frame"] != frame
            ]
