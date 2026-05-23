"""
NST ULTIMATE CONSOLE - Desktop GUI (Redesigned + Task Engine)
===============================================================
GUI modern dengan CustomTkinter - Sidebar navigation, collapsible console,
dashboard, task engine, background service, notifikasi toast, dan status center.

ARSITEKTUR:
- UI Layer: nst_gui.py (hanya tampilan)
- Task Engine: core/task_manager.py (background thread)
- Event System: core/event_bus.py (pub/sub antar komponen)
- Background: core/background_service.py (auto device detection)
- Notifikasi: ui/notification.py (toast non-blocking)
- Status Monitor: ui/status_center.py (floating task monitor)

NOTE: Fungsi CLI yang memanggil input() (seperti 'Tekan Enter...')
akan 'hang' di mode GUI karena stdin tidak di-redirect.
Gunakan CLI mode (python main.py) untuk fungsi yang interaktif.
"""

from core.background_service import BackgroundService
from ui.status_center import StatusCenter
from ui.notification import ToastNotifications
from core.task_manager import TaskManager, task_manager, Task
from core.event_bus import EventBus, event_bus
from config import APP_NAME, VERSION, SUBVERSION, AUTHOR
from core.logger import log, Colors
import os
import sys
import re
from core.smart_scanner import run_smart_scan
import threading
import io
import time
from typing import Dict, List, Optional

# Pastikan path project root ada di sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import CustomTkinter
try:
    import customtkinter as ctk
except ImportError:
    ctk = None


# ── New Architecture Imports ──


# =============================================================================
# KONFIGURASI TEMA & WARNA
# =============================================================================

COLORS = {
    "primary_glow": "#38bdf8",
    "neon_blue": "#0ea5e9",
    "neon_green": "#22c55e",
    "neon_red": "#ef4444",
    "surface": "#0f172a",

    "sidebar_bg": "#1a1a2e",
    "sidebar_button": "transparent",
    "sidebar_hover": "#16213e",
    "sidebar_active": "#0f3460",
    "sidebar_text": "#a0a0b8",
    "sidebar_text_active": "#e0e0ff",
    "accent_blue": "#4fc3f7",
    "accent_green": "#4caf50",
    "accent_orange": "#ff9800",
    "accent_red": "#f44336",
    "accent_purple": "#ab47bc",
    "accent_cyan": "#26c6da",
    "safe_green": "#2e7d32",
    "warning_orange": "#e65100",
    "danger_red": "#c62828",
    "card_bg": "#1e1e2f",
    "header_bg": "#16162a",
    "divider": "#2a2a40",
}

SIDEBAR_ITEMS = [
    ("  🏠  Dashboard", "dashboard", COLORS["accent_blue"]),
    ("  📱  Android", "android", COLORS["accent_green"]),
    ("  🍎  iPhone", "iphone", COLORS["accent_cyan"]),
    ("  🔧  Flashing", "flashing", COLORS["accent_orange"]),
    ("  🛡  Safety", "safety", COLORS["accent_purple"]),
    ("  🚑  Emergency", "emergency", COLORS["accent_red"]),
    ("  📊  Reports", "reports", COLORS["accent_blue"]),
    ("  ⚙  Settings", "settings", "#888888"),
]

BUTTON_COLORS = {
    "primary_glow": "#38bdf8",
    "neon_blue": "#0ea5e9",
    "neon_green": "#22c55e",
    "neon_red": "#ef4444",
    "surface": "#0f172a",

    "safe": {"fg": COLORS["safe_green"], "hover": "#1b5e20", "text": "white"},
    "warning": {"fg": COLORS["warning_orange"], "hover": "#bf360c", "text": "white"},
    "danger": {"fg": COLORS["danger_red"], "hover": "#b71c1c", "text": "white"},
    "primary": {"fg": "#1565c0", "hover": "#0d47a1", "text": "white"},
    "default": {"fg": "#2c2c3e", "hover": "#3a3a50", "text": "#cccccc"},
}

DEVICE_STATUS_COLORS = {
    "primary_glow": "#38bdf8",
    "neon_blue": "#0ea5e9",
    "neon_green": "#22c55e",
    "neon_red": "#ef4444",
    "surface": "#0f172a",

    "android": COLORS["accent_green"],
    "iphone": COLORS["accent_cyan"],
    "stm32": COLORS["accent_orange"],
    "none": "#666666",
}

DEVICE_STATUS_LABELS = {
    "android": "Android",
    "iphone": "iPhone",
    "stm32": "STM32",
    "none": "No Device",
}

DEVICE_STATUS_ICONS = {
    "android": "📱",
    "iphone": "🍎",
    "stm32": "🔧",
    "none": "○",
}

# =============================================================================
# HELPER: Thread-safe stdout redirect ke GUI Text widget
# =============================================================================


class TextRedirector(io.StringIO):
    """Redirect stdout/stderr ke CTkTextbox secara thread-safe"""

    def __init__(self, text_widget, tag="info"):
        super().__init__()
        self.text_widget = text_widget
        self.tag = tag

    def write(self, string):
        string = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", str(string))
        if string.strip():
            self.text_widget.after(0, self._append, string)

    def _append(self, string):
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", string, self.tag)
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        except Exception:
            pass

    def flush(self):
        pass


# =============================================================================
# CUSTOM TKINTER GUI APP
# =============================================================================


class NSTGUI:
    """Main GUI Application dengan Task Engine + Background Service"""

    def __init__(self):
        if ctk is None:
            print("CustomTkinter tidak terinstall! Jalankan: pip install customtkinter")
            return

        # Theme & appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} v{VERSION} - {SUBVERSION}")
        self.root.geometry("1280x800")
        self.root.minsize(1024, 600)

        # Icon (jika ada)
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        # ── Variables ──
        self.current_thread = None
        self.is_running = False
        self.status_var = ctk.StringVar(value="Siap")
        self.console_visible = True
        self.active_page = None
        self.pages = {}
        self.sidebar_buttons = {}

        # Live device status
        self.device_status: Dict = {
            "type": "none",
            "devices": [],
            "adb": False,
            "fastboot": False,
            "usb": False,
        }
        self._dashboard_status_labels: Dict[str, ctk.CTkLabel] = {}
        self._dashboard_model_label = None
        self._dashboard_battery_label = None

        # ── Initialize Architecture Components ──
        # EventBus & TaskManager are singletons — auto-initialized on import

        # Background Service (auto device detection)
        self.background_service = BackgroundService(ui_callback=self)

        # Toast notification system (created after UI built)
        self.toast_notifier = None

        # Status center (created after UI built)
        self.status_center = None

        # ── Build UI ──
        self._build_ui()

        # Show default page
        self._show_page("dashboard")

        # ── Register event listeners ──
        self._register_event_listeners()

        # ── Start background services ──
        self.background_service.start()

        # ── Bind close event ──
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Sentinel
        self._setup_sentinel()

    def _setup_sentinel(self):
        """Setup crash sentinel untuk GUI"""
        try:
            from core.crash_handler import setup_crash_handling, cleanup_crash_handling

            was_crash = setup_crash_handling()
            self._sentinel_cleanup = cleanup_crash_handling
            if was_crash:
                self.log_message(
                    "⚠  Program sebelumnya crash! Periksa logs/crashes/ untuk detail.",
                    "warning",
                )
        except Exception:
            self._sentinel_cleanup = None

    # =========================================================================
    # EVENT BUS LISTENERS
    # =========================================================================

    def _register_event_listeners(self):
        """Register listeners for event bus events"""
        # ── Task events → Notifications ──
        event_bus.on(EventBus.TASK_COMPLETED, self._on_task_completed)
        event_bus.on(EventBus.TASK_FAILED, self._on_task_failed)
        event_bus.on(EventBus.TASK_CREATED, self._on_task_created)

        # ── Device events → Notifications ──
        event_bus.on(EventBus.DEVICE_CONNECTED, self._on_device_connected)
        event_bus.on(EventBus.DEVICE_DISCONNECTED, self._on_device_disconnected)

        # ── UI events ──
        event_bus.on(EventBus.UI_CONSOLE_LOG, self._on_console_log)

    def _on_task_created(self, task: Task):
        """Task created — update status bar"""
        self.root.after(0, lambda: self.status_var.set(f"⏳ {task.name}..."))

    def _on_task_completed(self, task: Task):
        """Task completed — show success toast & reset status"""
        self.root.after(0, lambda: self._handle_task_complete(task))

    def _handle_task_complete(self, task: Task):
        """Handle task completion on main thread"""
        if self.toast_notifier:
            duration = f" ({task.duration})" if task.duration else ""
            self.toast_notifier.show_success(f"{task.name} selesai!{duration}")
        self.status_var.set(f"✅ {task.name} selesai")
        self.is_running = False

    def _on_task_failed(self, task: Task):
        """Task failed — show error toast & reset status"""
        self.root.after(0, lambda: self._handle_task_fail(task))

    def _handle_task_fail(self, task: Task):
        """Handle task failure on main thread"""
        if self.toast_notifier:
            error_msg = task.error or "Unknown error"
            self.toast_notifier.show_error(f"{task.name} gagal: {error_msg[:60]}")
        self.status_var.set(f"❌ {task.name} gagal")
        self.is_running = False

    def _on_device_connected(self, data: Dict):
        """Device connected — show success toast"""
        name = data.get("status", {}).get("name", "Device")
        dev_type = data.get("status", {}).get("type", "unknown")
        self.root.after(
            0, lambda: self._show_device_notification("connected", dev_type, name)
        )

    def _on_device_disconnected(self, data: Dict):
        """Device disconnected — show warning toast"""
        self.root.after(
            0, lambda: self._show_device_notification("disconnected", "none", "Device")
        )

    def _show_device_notification(self, action: str, dev_type: str, name: str):
        """Show toast for device connection change"""
        if self.toast_notifier:
            if action == "connected":
                icon = DEVICE_STATUS_ICONS.get(dev_type, "📱")
                self.toast_notifier.show_success(f"{icon} {name} terhubung!")
            else:
                self.toast_notifier.show_warning(f"Device terputus!")

    def _on_console_log(self, message: str, tag: str = "info"):
        """Log message to console via event bus"""
        self.log_message(message, tag)

    # =========================================================================
    # LIVE DEVICE STATUS (via BackgroundService)
    # =========================================================================

    def _update_device_ui(self, status: Dict):
        """
        Update all UI elements with latest device status.
        Called from BackgroundService background thread.
        ALL widget manipulation is wrapped in root.after() for thread safety.
        """
        # Schedule UI update on main thread
        self.root.after(0, self._apply_device_ui, status)

        # Store status for quick action routing (safe — primitive assignment,
        # no UI)
        self.device_status = status

    def _apply_device_ui(self, status: Dict):
        """Apply device status to UI widgets on main thread"""
        dev_type = status.get("type", "none")

        # --- Update header badge ---
        icon = DEVICE_STATUS_ICONS.get(dev_type, "○")
        label = DEVICE_STATUS_LABELS.get(dev_type, "Unknown")
        color = DEVICE_STATUS_COLORS.get(dev_type, "#666666")

        if dev_type == "none":
            self.device_status_dot.configure(text="○", text_color="#9ca3af")
            self.device_status_label.configure(text="No Device", text_color=color)
        else:
            mode_str = (
                f" [{status.get('mode', '').upper()}]"
                if status.get("mode") and status["mode"] != "unknown"
                else ""
            )
            name_str = (
                f" {status.get('name', '')}"
                if status.get("name")
                else ""
            )
            self.device_status_dot.configure(text=icon, text_color=color)
            self.device_status_label.configure(
                text=f"{label}{mode_str}{name_str}",
                text_color=color,
            )
        # --- Update dashboard status cards ---
        if self._dashboard_status_labels:
            labels = self._dashboard_status_labels

            usb_ok = status["adb"] or status["fastboot"] or status["usb_connected"]
            labels["usb"].configure(
                text="✅ Connected" if usb_ok else "❌ Disconnected",
                text_color=COLORS["accent_green"] if usb_ok else COLORS["accent_red"],
            )

            if status["adb"]:
                labels["adb"].configure(
                    text="✅ Active", text_color=COLORS["accent_green"]
                )
            elif status["type"] == "android":
                labels["adb"].configure(
                    text="⚠ Waiting...", text_color=COLORS["accent_orange"]
                )
            else:
                labels["adb"].configure(text="—", text_color=COLORS["sidebar_text"])

            if status["fastboot"]:
                labels["fastboot"].configure(
                    text="✅ Ready", text_color=COLORS["accent_green"]
                )
            else:
                labels["fastboot"].configure(
                    text="—", text_color=COLORS["sidebar_text"]
                )

            if status["type"] != "none":
                mode_name = status.get("mode", "unknown").upper()
                labels["mode"].configure(text=mode_name, text_color=color)
            else:
                labels["mode"].configure(text="—", text_color=COLORS["sidebar_text"])

        # --- Update dashboard extra info ---
        if self._dashboard_model_label:
            if status["type"] != "none" and status.get("model"):
                self._dashboard_model_label.configure(
                    text=f"Model: {status['model']}", text_color="#aaaaaa"
                )
            elif status["type"] != "none" and status.get("name"):
                self._dashboard_model_label.configure(
                    text=f"Device: {status['name']}", text_color="#aaaaaa"
                )
            else:
                self._dashboard_model_label.configure(
                    text="Tidak ada device terdeteksi", text_color="#9ca3af"
                )

        if self._dashboard_battery_label:
            if status.get("battery") is not None:
                bat = status["battery"]
                bat_color = (
                    COLORS["accent_green"]
                    if bat > 50
                    else COLORS["accent_orange"] if bat > 20 else COLORS["accent_red"]
                )
                self._dashboard_battery_label.configure(
                    text=f"Battery: {bat}%", text_color=bat_color
                )
            else:
                self._dashboard_battery_label.configure(text="", text_color="#9ca3af")

    def _detect_device_type_sync(self) -> str:
        """Quick synchronous device type detection for action routing"""
        if self.device_status and self.device_status.get("type", "none") != "none":
            return self.device_status.get("type", "none")
        return "none"

    # =========================================================================
    # BUILD UI
    # =========================================================================

    def _make_sidebar_button(self, parent, text, page_name, accent_color):
        """Buat tombol sidebar dengan gaya yang konsisten"""
        container = ctk.CTkFrame(parent, fg_color="transparent", height=40)
        container.grid_columnconfigure(0, weight=0)
        container.grid_columnconfigure(1, weight=1)

        # Accent bar (hidden by default)
        accent_bar = ctk.CTkFrame(container, width=3, corner_radius=0)
        accent_bar.grid(row=0, column=0, sticky="ns", padx=(0, 2))
        accent_bar.grid_propagate(False)

        btn = ctk.CTkButton(
            container,
            text=text,
            command=lambda p=page_name: self._show_page(p),
            font=ctk.CTkFont(size=14),
            anchor="w",
            fg_color=COLORS["sidebar_button"],
            text_color=COLORS["sidebar_text"],
            hover_color=COLORS["sidebar_hover"],
            height=38,
            corner_radius=6,
            border_width=0,
        )
        btn.grid(row=0, column=1, sticky="nsew", padx=(0, 5))

        self.sidebar_buttons[page_name] = {
            "button": btn,
            "accent_bar": accent_bar,
            "accent_color": accent_color,
        }
        return container

    def _build_ui(self):
        """Build complete UI layout"""
        # Main grid
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        # ===== HEADER =====
        header_frame = ctk.CTkFrame(
            self.root, height=48, corner_radius=0, fg_color=COLORS["header_bg"]
        )
        header_frame.pack(fill="x")
        header_frame.grid_columnconfigure(1, weight=1)

        # App title
        title_label = ctk.CTkLabel(
            header_frame,
            text=f"  {APP_NAME}",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent_blue"],
        )
        title_label.pack(
            padx=(15, 0),
            pady=10,
            side="left"
        )

        # Version subtitle
        ctk.CTkLabel(
            header_frame,
            text=f"v{VERSION}",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
        ).pack(
            padx=(5, 0),
            pady=10,
            side="left"
        )

        # Device status indicator (live)
        self.device_status_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.device_status_frame.pack(
            padx=10,
            pady=10,
            side="right"
        )

        self.device_status_dot = ctk.CTkLabel(
            self.device_status_frame,
            text="○",
            font=ctk.CTkFont(size=13),
            text_color="#9ca3af",
        )
        self.device_status_dot.pack(side="left", padx=(0, 5))

        self.device_status_label = ctk.CTkLabel(
            self.device_status_frame,
            text="No Device",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        )
        self.device_status_label.pack(side="left")

        # ===== MAIN CONTENT =====
        main_container = ctk.CTkFrame(self.root, corner_radius=0)
        main_container.pack(fill="both", expand=True)
        main_container.grid_rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(0, weight=0, minsize=220)
        main_container.grid_columnconfigure(1, weight=1)

        # ===== SIDEBAR =====
        sidebar_frame = ctk.CTkFrame(
            main_container, corner_radius=0, fg_color=COLORS["sidebar_bg"]
        )
        sidebar_frame.grid(row=0, column=0, sticky="nsew")
        sidebar_frame.grid_columnconfigure(0, weight=1)

        # Sidebar title
        title_lbl = ctk.CTkLabel(
            sidebar_frame,
            text="  NAVIGASI",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
            anchor="w",
        )
        title_lbl.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        # Sidebar separator
        sep = ctk.CTkFrame(sidebar_frame, height=1, fg_color=COLORS["divider"])
        sep.grid(row=1, column=0, sticky="ew")

        # Sidebar buttons
        self.sidebar_button_frames = {}
        for i, (label, page, accent) in enumerate(SIDEBAR_ITEMS):
            container = self._make_sidebar_button(sidebar_frame, label, page, accent)
            container.grid(row=2+i, column=0, padx=10, pady=2, sticky="ew")
            self.sidebar_button_frames[page] = container

        # Spacer
        sidebar_frame.grid_rowconfigure(2 + len(SIDEBAR_ITEMS), weight=1)

        # Sidebar footer (version)
        footer_lbl = ctk.CTkLabel(
            sidebar_frame,
            text=f"v{VERSION} - {SUBVERSION}",
            font=ctk.CTkFont(size=10),
            text_color="#444444",
        )
        footer_lbl.grid(row=3 + len(SIDEBAR_ITEMS), column=0, padx=15, pady=(0, 10))

        # ===== RIGHT PANEL (Pages + Console + Status Center) =====
        right_panel = ctk.CTkFrame(main_container, corner_radius=0)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        # === Status Center (active tasks monitor) — fixed di atas ===
        self.status_center = StatusCenter(right_panel, width=300)

        # === Console (collapsible) — fixed di tengah ===
        self._build_console(right_panel)

        # === Page container — mengambil sisa ruang ===
        self.page_container = ctk.CTkFrame(right_panel, corner_radius=0)
        self.page_container.pack(fill="both", expand=True)

        # === Toast Notification System (overlay on root) ===
        self.toast_notifier = ToastNotifications(self.root)

        # ===== STATUS BAR =====
        status_frame = ctk.CTkFrame(self.root, height=26, corner_radius=0)
        status_frame.pack(fill="x")
        status_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status_frame,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.status_label.pack(padx=10, side="left")

        ctk.CTkLabel(
            status_frame,
            text=f"{AUTHOR} | Task Engine | Build {VERSION}",
            font=ctk.CTkFont(size=10),
            text_color="gray50",
        ).pack(padx=10, side="right")

    # =========================================================================
    # COLLAPSIBLE CONSOLE
    # =========================================================================

    def _build_console(self, parent):
        """Console output area - collapsible, placed below status center"""
        self.console_frame = ctk.CTkFrame(
            parent,
            corner_radius=12,
            height=140,
            fg_color="#020617",
            border_width=1,
            border_color="#334155",
        )
        self.console_frame.pack(padx=10, pady=(0, 8), fill="x")
        self.console_frame.grid_columnconfigure(0, weight=1)
        self.console_frame.grid_propagate(False)

        # Console header bar
        console_header = ctk.CTkFrame(
            self.console_frame,
            height=28,
            fg_color="#0f172a",
            corner_radius=14,
        )
        console_header.pack(padx=12, pady=(3, 0), fill="x")
        console_header.grid_columnconfigure(0, weight=1)

        self.toggle_btn = ctk.CTkButton(
            console_header,
            text="▼  Console Output • Live Logs",
            command=self._toggle_console,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="transparent",
            text_color="#888888",
            hover_color="#2a2a3e",
            width=140,
            height=22,
            corner_radius=4,
        )
        self.toggle_btn.pack(side="left")

        # Copy button
        ctk.CTkButton(
            console_header,
            text="Copy",
            command=self._copy_console,
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            text_color="#9ca3af",
            hover_color="#2a2a3e",
            width=60,
            height=22,
            corner_radius=4,
        ).pack(side="right", padx=(5, 0))

        # Clear console button
        ctk.CTkButton(
            console_header,
            text="Clear",
            command=self._clear_console,
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            text_color="#9ca3af",
            hover_color="#2a2a3e",
            width=60,
            height=22,
            corner_radius=4,
        ).pack(side="right")

        # Console text widget
        self.output_text = ctk.CTkTextbox(
            self.console_frame,
            wrap="word",
            font=ctk.CTkFont(family="JetBrains Mono", size=12),
            state="disabled",
            height=110,
            fg_color="#020617",
            border_width=1,
            border_color="#334155",
            corner_radius=10,
            text_color="#e2e8f0",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        self.output_text.pack(padx=8, pady=(2, 4), fill="both", expand=True)
        self.console_frame.grid_rowconfigure(1, weight=1)

        # Text tags for colors
        self.output_text.tag_config("info", foreground="#cbd5e1")
        self.output_text.tag_config("success", foreground="#22c55e")
        self.output_text.tag_config("warning", foreground="#f59e0b")
        self.output_text.tag_config("error", foreground="#ef4444")
        self.output_text.tag_config("header", foreground="#38bdf8")
        self.output_text.tag_config("dim", foreground="#64748b")
        self.output_text.tag_config("bold")

    def _toggle_console(self):
        """Toggle console visibility"""
        self.console_visible = not self.console_visible
        if self.console_visible:
            self.output_text.pack(padx=8, pady=(2, 4), fill="both", expand=True)
            self.console_frame.configure(height=140)
            self.toggle_btn.configure(text="▼  Console Output • Live Logs")
        else:
            self.output_text.pack_forget()
            self.console_frame.configure(height=28)
            self.toggle_btn.configure(text="▶  Console Output")

    def _clear_console(self):
        """Clear console output"""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

    def _copy_console(self):
        """Copy console content to clipboard"""
        try:
            content = self.output_text.get("1.0", "end-1c")
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("Console copied to clipboard")
        except Exception:
            pass

    # =========================================================================
    # PAGE SYSTEM
    # =========================================================================

    def _show_page(self, page_name):
        """Switch to a page"""
        if self.active_page == page_name:
            return

        # Create page if it doesn't exist
        if page_name not in self.pages:
            self.pages[page_name] = ctk.CTkScrollableFrame(
                self.page_container, corner_radius=0, fg_color="transparent"
            )
            build_method = getattr(self, f"_build_{page_name}_page", None)
            if build_method:
                build_method(self.pages[page_name])

        # Hide current page
        if self.active_page and self.active_page in self.pages:
            self.pages[self.active_page].pack_forget()

        # Show new page
        self.pages[page_name].pack(fill="both", expand=True, padx=6, pady=4)
        self.active_page = page_name

        # Emit event
        event_bus.emit(EventBus.UI_PAGE_CHANGED, page_name)

        # Update sidebar active state with accent bar
        for name, data in self.sidebar_buttons.items():
            btn = data["button"]
            bar = data["accent_bar"]
            accent = data["accent_color"]

            if name == page_name:
                btn.configure(
                    fg_color=COLORS["sidebar_active"],
                    text_color=COLORS["sidebar_text_active"],
                )
                bar.configure(fg_color=accent)
            else:
                btn.configure(
                    fg_color=COLORS["sidebar_button"], text_color=COLORS["sidebar_text"]
                )
                bar.configure(fg_color="transparent")

        # Update status
        page_label = page_name.capitalize()
        for label, key, _ in SIDEBAR_ITEMS:
            if key == page_name:
                page_label = label.strip()
                break
        self.status_var.set(f"📍 {page_label}")

    # =========================================================================
    # PAGE: DASHBOARD (sama seperti sebelumnya)
    # =========================================================================

    def _build_dashboard_page(self, parent):
        """Dashboard utama - informasi device + quick actions"""
        # Title
        ctk.CTkLabel(
            parent,
            text="🏠  Dashboard",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["accent_blue"],
        ).pack(anchor="w", pady=(0, 15))

        # --- Device Status Card ---
        status_card = ctk.CTkFrame(parent, corner_radius=12, fg_color="#0f172a")
        status_card.pack(fill="x", pady=(0, 15))

        header_row = ctk.CTkFrame(status_card)
        header_row.pack(fill="x", padx=20, pady=(15, 5))

        ctk.CTkLabel(
            header_row,
            text="📡  Device Status",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent_blue"],
        ).pack(side="left")

        # Model/Name label
        self._dashboard_model_label = ctk.CTkLabel(
            header_row,
            text="Tidak ada device terdeteksi",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
        )
        self._dashboard_model_label.pack(side="right")

        # Separator
        ctk.CTkFrame(status_card, height=1, fg_color=COLORS["divider"]).pack()

        status_grid = ctk.CTkFrame(status_card)
        status_grid.pack(fill="x", padx=20, pady=(0, 15))
        status_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

        status_items = [
            ("usb", "USB Connection", "❌ Disconnected", COLORS["accent_red"]),
            ("adb", "ADB Status", "—", COLORS["sidebar_text"]),
            ("fastboot", "Fastboot", "—", COLORS["sidebar_text"]),
            ("mode", "Device Mode", "—", COLORS["sidebar_text"]),
        ]

        for col_idx, (key, label, value, color) in enumerate(status_items):
            item_frame = ctk.CTkFrame(status_grid)
            item_frame.grid(row=0, column=col_idx, sticky="nsew", padx=5)

            ctk.CTkLabel(
                item_frame,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color="#9ca3af",
            ).pack(anchor="w")

            val_label = ctk.CTkLabel(
                item_frame,
                text=value,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=color,
            )
            val_label.pack(anchor="w")
            self._dashboard_status_labels[key] = val_label

        # Battery label
        self._dashboard_battery_label = ctk.CTkLabel(
            status_card, text="", font=ctk.CTkFont(size=11), text_color="#9ca3af"
        )
        self._dashboard_battery_label.pack(anchor="w", padx=20, pady=(0, 10))

        # --- Quick Actions ---
        ctk.CTkLabel(
            parent,
            text="⚡  Quick Actions",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent_blue"],
        ).pack(anchor="w", pady=(0, 10))

        quick_grid = ctk.CTkFrame(parent)
        quick_grid.pack(fill="x", pady=(0, 15))
        quick_grid.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        quick_actions = [
            (
                "🔎  Smart Deep Scan",
                self._run_smart_scan,
                COLORS["accent_blue"],
                "#0d47a1",
                "Identifikasi HWID & cari firmware",
            ),
            (
                "🔍  Scan Device",
                self._run_scan_device,
                COLORS["safe_green"],
                "#1b5e20",
                "Deteksi device terhubung",
            ),
            (
                "🩺  Diagnostic",
                self._run_diagnostic,
                COLORS["safe_green"],
                "#1b5e20",
                "Analisa hardware & software",
            ),
            (
                "⚡  Flash Firmware",
                self._run_flash_firmware,
                COLORS["warning_orange"],
                "#bf360c",
                "Flash firmware device",
            ),
            (
                "🚑  Emergency",
                self._run_emergency,
                COLORS["danger_red"],
                "#b71c1c",
                "Kill ADB + restart USB + clean",
            ),
        ]

        for i, (text, cmd, color, hover, desc) in enumerate(quick_actions):
            frame = ctk.CTkFrame(
                quick_grid, corner_radius=14, fg_color="#0f172a"
            )
            frame.grid(row=0, column=i, sticky="nsew", padx=5, pady=5)

            btn = ctk.CTkButton(
                frame,
                text=text,
                command=cmd,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color=color,
                hover_color=hover,
                height=60,
                corner_radius=14,
            )
            btn.pack(fill="x", padx=15, pady=(15, 5))

            ctk.CTkLabel(
                frame,
                text=desc,
                font=ctk.CTkFont(size=11),
                text_color="#888888",
            ).pack(anchor="w", padx=15, pady=(0, 15))

        # --- Recent Activity ---
        ctk.CTkFrame(parent, height=1, fg_color=COLORS["divider"]).pack()

        ctk.CTkLabel(
            parent,
            text="📋  Recent Activity",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent_blue"],
        ).pack(anchor="w", pady=(0, 10))

        recent_container = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color="#0f172a",
            border_width=1,
            border_color="#1f2937",
        )
        recent_container.pack(fill="both", expand=True, pady=(0, 10))

        # Header info
        header = ctk.CTkFrame(recent_container, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 5))

        ctk.CTkLabel(
            header,
            text="10 aktivitas terakhir",
            font=ctk.CTkFont(size=11),
            text_color="#7dd3fc",
        ).pack(side="left")

        # Scrollable activity area
        recent_frame = ctk.CTkScrollableFrame(
            recent_container,
            fg_color="transparent",
            corner_radius=14,
            height=160,
        )
        recent_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Load recent history
        self._load_recent_activity(recent_frame)

    def _load_recent_activity(self, parent):
        """Load recent activity from action_history.json"""
        try:
            history_path = os.path.join("logs", "action_history.json")
            if os.path.exists(history_path):
                import json

                with open(history_path, "r") as f:
                    history = json.load(f)
                items = history[-10:] if len(history) > 10 else history
                for entry in reversed(items):
                    ts = entry.get("timestamp", "—")
                    action = entry.get("action", "—")
                    status = entry.get("status", "—")
                    detail = entry.get("detail", "")
                    row = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=14)
                    row.pack(fill="x", padx=12, pady=6)

                    ctk.CTkLabel(
                        row,
                        text=ts,
                        font=ctk.CTkFont(size=10),
                        text_color="#94a3b8",
                        width=80,
                    ).pack(side="left")

                    status_color = (
                        COLORS["accent_green"]
                        if status == "SUCCESS"
                        else (
                            COLORS["accent_orange"]
                            if "WARN" in str(status)
                            else (
                                COLORS["accent_red"]
                                if "ERROR" in str(status) or "FAIL" in str(status)
                                else COLORS["accent_blue"]
                            )
                        )
                    )

                    ctk.CTkLabel(
                        row,
                        text=f"[{status}]",
                        font=ctk.CTkFont(size=10, weight="bold"),
                        text_color=status_color,
                        width=80,
                    ).pack(side="left")

                    ctk.CTkLabel(
                        row,
                        text=action,
                        font=ctk.CTkFont(size=11),
                        text_color="#f3f4f6",
                    ).pack(side="left", padx=(5, 0))

                    if detail:
                        ctk.CTkLabel(
                            row,
                            text=f"— {detail}",
                            font=ctk.CTkFont(size=10),
                            text_color="#9ca3af",
                        ).pack(side="left", padx=(5, 0))
            else:
                ctk.CTkLabel(
                    parent,
                    text="  Belum ada aktivitas. Mulai dengan scan device!",
                    font=ctk.CTkFont(size=12),
                    text_color="#9ca3af",
                ).pack(anchor="w", padx=15, pady=15)
        except Exception:
            ctk.CTkLabel(
                parent,
                text="  Gagal memuat riwayat aktivitas.",
                font=ctk.CTkFont(size=12),
                text_color="#888888",
            ).pack(anchor="w", padx=15, pady=15)

    # =========================================================================
    # ALL PAGES (Android, iPhone, Flashing, Safety, Emergency, Reports, Settings)
    # =========================================================================

    def _build_android_page(self, parent):
        """Android toolkit page - categorized actions"""
        self._build_page_header(
            parent,
            "📱  Android Toolkit",
            "Tools untuk service & repair Android",
            COLORS["accent_green"],
        )

        sections = [
            (
                "📱  Device Info",
                [
                    (
                        "🔍  Scan Device",
                        self._run_android_scan,
                        "safe",
                        "Baca info lengkap via ADB/fastboot",
                    ),
                    (
                        "✅  Root Checker",
                        self._run_android_root_check,
                        "safe",
                        "Cek status root device",
                    ),
                ],
            ),
            (
                "🔧  Repair",
                [
                    (
                        "🩺  Smart Diagnostic",
                        self._run_android_diagnostic,
                        "safe",
                        "Analisa hardware & software",
                    ),
                    (
                        "🧹  Clean Cache",
                        self._run_android_clean_cache,
                        "safe",
                        "Bersihkan sampah (+ deep clean)",
                    ),
                    (
                        "🔄  Factory Reset",
                        self._run_android_reset,
                        "danger",
                        "Reset aman + backup otomatis",
                    ),
                ],
            ),
            (
                "⚡  Flashing",
                [
                    (
                        "⚡  Flash Firmware",
                        self._run_android_flash,
                        "warning",
                        "Flash firmware Android",
                    ),
                    (
                        "🔓  Unlock Bootloader",
                        self._run_android_unlock,
                        "warning",
                        "Buka bootloader via fastboot",
                    ),
                    (
                        "🛠  Root Android",
                        self._run_android_root,
                        "warning",
                        "Root device (Magisk/TWRP)",
                    ),
                ],
            ),
            (
                "🔐  Security",
                [
                    (
                        "🔑  FRP Bypass",
                        self._run_android_frp,
                        "warning",
                        "5 metode FRP bypass",
                    ),
                ],
            ),
        ]

        self._build_sectioned_grid(parent, sections, columns=3)

    def _build_iphone_page(self, parent):
        """iPhone toolkit page"""
        self._build_page_header(
            parent,
            "🍎  iPhone Toolkit",
            "Tools untuk service & repair iPhone",
            COLORS["accent_cyan"],
        )

        sections = [
            (
                "📋  Scanner",
                [
                    (
                        "🔍  Apple Full Scan",
                        self._run_iphone_full_scan,
                        "safe",
                        "Ecosystem scan (driver, USB, services)",
                    ),
                    (
                        "⚡  Quick Driver Check",
                        self._run_iphone_driver_check,
                        "safe",
                        "Cepat cek Apple driver registry",
                    ),
                    (
                        "🔌  Port Verification",
                        self._run_iphone_port_verify,
                        "safe",
                        "Cek port komunikasi Apple/MTK/QC",
                    ),
                ],
            ),
            (
                "📖  Guides",
                [
                    (
                        "📲  Mode Guide",
                        self._run_iphone_mode_guide,
                        "safe",
                        "Panduan Recovery/DFU mode",
                    ),
                    (
                        "🔋  Battery Guide",
                        self._run_iphone_battery_guide,
                        "safe",
                        "Cek cycle count & health",
                    ),
                    (
                        "🔐  Activation Check",
                        self._run_iphone_activation_check,
                        "safe",
                        "Cek iCloud lock",
                    ),
                    (
                        "📥  Install Driver",
                        self._run_iphone_install_guide,
                        "safe",
                        "Panduan install driver Apple",
                    ),
                ],
            ),
        ]

        self._build_sectioned_grid(parent, sections, columns=3)

    def _build_flashing_page(self, parent):
        """STM32 Flashing page"""
        self._build_page_header(
            parent,
            "🔧  STM32 Flasher",
            "Flash & recovery untuk chip STM32",
            COLORS["accent_orange"],
        )

        sections = [
            (
                "⚡  Flashing",
                [
                    (
                        "⚡  Flash STM32",
                        self._run_stm32_flash,
                        "warning",
                        "Flash firmware via UART/DFU/ST-Link",
                    ),
                    (
                        "🩺  Diagnostic STM32",
                        self._run_stm32_diagnostic,
                        "safe",
                        "Deteksi chip, test koneksi, read flash",
                    ),
                ],
            ),
            (
                "🛡  Recovery",
                [
                    (
                        "🛡  Anti-Brick STM32",
                        self._run_stm32_anti_brick,
                        "danger",
                        "Recovery & unbrick (5 metode)",
                    ),
                    (
                        "🔌  Driver Doctor",
                        self._run_stm32_driver_doctor,
                        "safe",
                        "Scan & install driver STM32 + Apple",
                    ),
                ],
            ),
        ]

        self._build_sectioned_grid(parent, sections, columns=3)

    def _build_safety_page(self, parent):
        """Safety & Backup page"""
        self._build_page_header(
            parent,
            "🛡  Safety & Backup",
            "Backup, restore, dan verifikasi firmware",
            COLORS["accent_purple"],
        )

        sections = [
            (
                "💾  Backup",
                [
                    (
                        "💾  Backup Now",
                        self._run_backup_now,
                        "safe",
                        "Backup full semua partisi + data",
                    ),
                    (
                        "📂  Restore Backup",
                        self._run_restore_backup,
                        "warning",
                        "Pulihkan device dari backup",
                    ),
                ],
            ),
            (
                "✅  Verification",
                [
                    (
                        "✅  Firmware Verify",
                        self._run_firmware_verify,
                        "safe",
                        "MD5/struktur firmware sebelum flash",
                    ),
                    (
                        "📋  Safety History",
                        self._run_safety_history,
                        "safe",
                        "Riwayat aksi & backup manager",
                    ),
                ],
            ),
            (
                "📌  Utilities",
                [
                    (
                        "📌  Create Shortcut",
                        self._run_create_shortcut,
                        "safe",
                        "Buat Near Cell System di desktop",
                    ),
                ],
            ),
        ]

        self._build_sectioned_grid(parent, sections, columns=3)

    def _build_emergency_page(self, parent):
        """Emergency Recovery page"""
        self._build_page_header(
            parent,
            "🚑  Emergency Recovery",
            "Pulihkan device dari keadaan darurat",
            COLORS["accent_red"],
        )

        sections = [
            (
                "🚨  Emergency",
                [
                    (
                        "🚑  Emergency Recovery",
                        self._run_emergency,
                        "danger",
                        "Full: Kill ADB, restart USB, clean temp",
                    ),
                ],
            ),
            (
                "🔧  ADB Tools",
                [
                    (
                        "💀  Kill ADB Zombie",
                        self._run_kill_adb,
                        "warning",
                        "Matikan proses ADB yang hang",
                    ),
                    (
                        "🔄  Restart ADB",
                        self._run_restart_adb,
                        "safe",
                        "Restart ADB server dari awal",
                    ),
                ],
            ),
            (
                "🧹  System Cleanup",
                [
                    (
                        "🧹  Clean Temp",
                        self._run_clean_temp,
                        "safe",
                        "Bersihkan file temporary",
                    ),
                ],
            ),
        ]

        self._build_sectioned_grid(parent, sections, columns=3)

    def _build_reports_page(self, parent):
        """Reports & System Tools page"""
        self._build_page_header(
            parent,
            "📊  Reports & Tools",
            "Laporan, scan device, dan monitoring",
            COLORS["accent_blue"],
        )

        sections = [
            (
                "📋  Reports",
                [
                    (
                        "📄  Report Manager",
                        self._run_report_manager,
                        "safe",
                        "Lihat, buka, hapus report",
                    ),
                    (
                        "📜  Safety History",
                        self._run_safety_history,
                        "safe",
                        "Riwayat aksi & backup manager",
                    ),
                ],
            ),
            (
                "🔍  Device Scanner",
                [
                    (
                        "🔍  Device Scan",
                        self._run_device_scan,
                        "safe",
                        "Deteksi semua perangkat terhubung",
                    ),
                    (
                        "ℹ️  Device Detail",
                        self._run_device_detail,
                        "safe",
                        "Info detail perangkat terdeteksi",
                    ),
                    (
                        "📡  Device Monitor",
                        self._run_device_monitor,
                        "safe",
                        "Pantau koneksi real-time",
                    ),
                ],
            ),
        ]

        self._build_sectioned_grid(parent, sections, columns=3)

    def _build_settings_page(self, parent):
        """Settings & About page"""
        # Title
        title_frame = ctk.CTkFrame(parent)
        title_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            title_frame,
            text="⚙  Settings & Tools",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#888888",
        ).pack(side="left")        
        # System section
        sys_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color="#0f172a")
        sys_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            sys_frame,
            text="🛠  System Tools",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#888888",
        ).pack(anchor="w", padx=20, pady=(15, 10))

        # Separator
        ctk.CTkFrame(sys_frame, height=1, fg_color=COLORS["divider"]).pack()

        sys_grid = ctk.CTkFrame(sys_frame)
        sys_grid.pack(fill="x", padx=20, pady=(0, 15))
        sys_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

        sys_tools = [
            ("🔧  Check Tools", self._run_env_check, "Cek dependencies"),
            ("📦  Install Deps", self._run_env_install, "Install yang hilang"),
            ("💻  System Info", self._run_env_sysinfo, "Info OS & hardware"),
            ("🔄  Check Update", self._run_check_update, "Cek versi terbaru"),
        ]

        for i, (text, cmd, desc) in enumerate(sys_tools):
            frame = ctk.CTkFrame(sys_grid, corner_radius=14, fg_color="#252538")
            frame.grid(row=0, column=i, sticky="nsew", padx=5)

            ctk.CTkButton(
                frame,
                text=text,
                command=cmd,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#2c2c3e",
                hover_color="#3a3a50",
                height=50,
                corner_radius=6,
            ).pack(fill="x", padx=10, pady=(10, 2))

            ctk.CTkLabel(
                frame,
                text=desc,
                font=ctk.CTkFont(size=10),
                text_color="#9ca3af",
            ).pack(anchor="w", padx=12, pady=(0, 10))

        # --- About Section ---
        about_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color="#0f172a")
        about_frame.pack(fill="x")

        ctk.CTkLabel(
            about_frame,
            text="ℹ️  About",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#888888",
        ).pack(anchor="w", padx=20, pady=(15, 10))

        # Separator
        ctk.CTkFrame(about_frame, height=1, fg_color=COLORS["divider"]).pack()

        info_items = [
            ("Nama Aplikasi", f"{APP_NAME} v{VERSION} - {SUBVERSION}"),
            ("Author", AUTHOR),
            ("Platform", f"Python {sys.version.split()[0]} | OS: {os.name}"),
            ("Total Fitur", "56 fitur siap pakai + GUI Desktop"),
            ("Task Engine", "✓ Active (Task Manager + Background Service)"),
            ("Event System", "✓ Active (Event Bus pub/sub)"),
            ("Notifications", "✓ Active (Toast + Status Center)"),
        ]

        for label, value in info_items:
            row = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=14)
            row.pack(fill="x", padx=20, pady=1)

            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=ctk.CTkFont(size=12, weight="bold"),
                width=120,
                anchor="w",
                text_color="#aaaaaa",
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=value,
                font=ctk.CTkFont(size=12),
                anchor="w",
                text_color="#f3f4f6",
            ).pack(side="left", padx=(5, 0))

        ctk.CTkLabel(about_frame, text="").pack(pady=5)

        ctk.CTkLabel(
            about_frame,
            text=f"(c) 2024-2025 {AUTHOR}. All rights reserved.",
            font=ctk.CTkFont(size=10),
            text_color="gray50",
        ).pack(anchor="w", padx=20, pady=(0, 15))

        # Plugin System info
        plugin_frame = ctk.CTkFrame(
            parent, corner_radius=10, fg_color="#0f172a"
        )
        plugin_frame.pack(fill="x", pady=(15, 0))

        ctk.CTkLabel(
            plugin_frame,
            text="🔌  Plugin System",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#888888",
        ).pack(anchor="w", padx=20, pady=(15, 10))

        # Separator
        ctk.CTkFrame(plugin_frame, height=1, fg_color=COLORS["divider"]).pack()

        plugin_grid = ctk.CTkFrame(plugin_frame)
        plugin_grid.pack(fill="x", padx=20, pady=(0, 15))
        plugin_grid.grid_columnconfigure((0, 1, 2), weight=1)

        plugin_actions = [
            ("📦  Plugin Manager", self._run_plugin_manager, "Status & kelola plugin"),
            (
                "🔍  Plugin Scan",
                self._run_plugin_scan,
                "Deteksi device dari semua plugin",
            ),
            ("🔄  Plugin Reload", self._run_plugin_reload, "Hot-reload semua plugin"),
        ]

        for i, (text, cmd, desc) in enumerate(plugin_actions):
            frame = ctk.CTkFrame(plugin_grid, corner_radius=14, fg_color="#252538")
            frame.grid(row=0, column=i, sticky="nsew", padx=5)

            ctk.CTkButton(
                frame,
                text=text,
                command=cmd,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="#2c2c3e",
                hover_color="#3a3a50",
                height=50,
                corner_radius=6,
            ).pack(fill="x", padx=10, pady=(10, 2))

            ctk.CTkLabel(
                frame,
                text=desc,
                font=ctk.CTkFont(size=10),
                text_color="#9ca3af",
            ).pack(anchor="w", padx=12, pady=(0, 10))

        # Separator for bottom spacing
        ctk.CTkLabel(parent, text="").pack(pady=(15, 0))

    # =========================================================================
    # HELPERS: BUILD PAGE ELEMENTS
    # =========================================================================

    def _build_page_header(self, parent, title, subtitle, accent_color):
        """Page title with accent color"""
        header_frame = ctk.CTkFrame(parent)
        header_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            header_frame,
            text=title,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=accent_color,
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_frame,
            text=subtitle,
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af",
        ).pack(anchor="w")

    def _build_sectioned_grid(self, parent, sections, columns=3):
        """Build categorized button grid from sections list"""
        for section_idx, (section_title, buttons) in enumerate(sections):
            # Section header
            header_frame = ctk.CTkFrame(parent)
            header_frame.pack(fill="x", pady=(15, 8))

            ctk.CTkLabel(
                header_frame,
                text=section_title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#aaaaaa",
            ).pack(side="left")

            # Section count badge
            ctk.CTkLabel(
                header_frame,
                text=f"  {len(buttons)} tools",
                font=ctk.CTkFont(size=10),
                text_color="#94a3b8",
            ).pack(side="left", padx=(8, 0))

            # Separator line under header
            ctk.CTkFrame(parent, height=1, fg_color=COLORS["divider"]).pack()

            # Button grid
            grid = ctk.CTkFrame(parent)
            grid.pack(fill="x", pady=(0, 5))

            for i, col in enumerate(range(columns)):
                grid.grid_columnconfigure(i, weight=1)

            for i, (text, command, color_key, desc) in enumerate(buttons):
                color_cfg = BUTTON_COLORS.get(color_key, BUTTON_COLORS["default"])

                frame = ctk.CTkFrame(grid, corner_radius=14, fg_color="#0f172a")
                frame.pack(padx=5, pady=5)

                is_primary = color_key in ("safe", "warning", "danger")
                btn_height = 52 if is_primary else 44

                btn = ctk.CTkButton(
                    frame,
                    text=text,
                    command=command,
                    font=ctk.CTkFont(
                        size=13, weight="bold" if is_primary else "normal"
                    ),
                    fg_color=color_cfg["fg"],
                    hover_color=color_cfg["hover"],
                    text_color=color_cfg["text"],
                    height=btn_height,
                    corner_radius=6,
                )
                btn.pack(fill="x", padx=12, pady=(10, 2))

                ctk.CTkLabel(
                    frame,
                    text=desc,
                    font=ctk.CTkFont(size=10),
                    text_color="#9ca3af",
                    wraplength=250,
                ).pack(anchor="w", padx=14, pady=(0, 10))

    # =========================================================================
    # CLI FUNCTION DISPATCHER (via Task Manager)
    # =========================================================================

    def _get_func(self, func_name):
        """Dapatkan fungsi CLI berdasarkan nama"""
        func_map = {
            # STM32
            "run_flasher": lambda: __import__(
                "main", fromlist=["run_flasher"]
            ).run_flasher(),
            "run_diagnostic": lambda: __import__(
                "main", fromlist=["run_diagnostic"]
            ).run_diagnostic(),
            "run_anti_brick": lambda: __import__(
                "main", fromlist=["run_anti_brick"]
            ).run_anti_brick(),
            "run_driver_doctor": lambda: __import__(
                "main", fromlist=["run_driver_doctor"]
            ).run_driver_doctor(),
            # Android
            "run_android_diagnostic": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_1_smart_diagnostic(),
            "run_android_clean_cache": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_2_clean_cache(),
            "run_android_flash": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_3_flash_firmware(),
            "run_android_unlock": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_4_unlock_bootloader(),
            "run_android_root": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_5_root(),
            "run_android_frp": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_6_frp_bypass(),
            "run_android_reset": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_7_factory_reset(),
            "run_android_scan": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_8_scan_device(),
            "run_android_root_check": lambda: __import__(
                "core.nst_android", fromlist=["AndroidToolkit"]
            )
            .AndroidToolkit()
            .fitur_9_root_checker(),
            # iPhone
            "run_iphone_full_scan": lambda: __import__(
                "core.nst_iphone", fromlist=["NSTiPhone"]
            )
            .NSTiPhone()
            .scan_apple_drivers(),
            "run_iphone_driver_check": lambda: __import__(
                "core.nst_iphone", fromlist=["NSTiPhone"]
            )
            .NSTiPhone()
            .quick_driver_check(),
            "run_iphone_mode_guide": lambda: __import__(
                "core.nst_iphone", fromlist=["NSTiPhone"]
            )
            .NSTiPhone()
            .show_mode_guide(),
            "run_iphone_battery_guide": lambda: __import__(
                "core.nst_iphone", fromlist=["NSTiPhone"]
            )
            .NSTiPhone()
            .show_battery_guide(),
            "run_iphone_activation_check": lambda: __import__(
                "core.nst_iphone", fromlist=["NSTiPhone"]
            )
            .NSTiPhone()
            .activation_check_guide(),
            "run_iphone_install_guide": lambda: __import__(
                "core.nst_iphone", fromlist=["NSTiPhone"]
            )
            .NSTiPhone()
            .show_install_guide(),
            "run_iphone_port_verify": lambda: __import__(
                "core.nst_iphone", fromlist=["NSTiPhone"]
            )
            .NSTiPhone()
            .verifikasi_port_komunikasi(),
            # Device
            "run_device_scan": lambda: __import__(
                "core.device_detector", fromlist=["DeviceDetector"]
            )
            .DeviceDetector()
            .scan_all(),
            "run_device_detail": lambda: __import__(
                "core.device_detector", fromlist=["DeviceDetector"]
            )
            .DeviceDetector()
            .show_device_info(),
            "run_device_monitor": lambda: __import__(
                "core.device_detector", fromlist=["DeviceDetector"]
            )
            .DeviceDetector()
            .monitor_mode(),
            # Environment
            "run_env_check": lambda: __import__(
                "core.environment", fromlist=["EnvironmentChecker"]
            )
            .EnvironmentChecker()
            .check_all(),
            "run_env_install": lambda: __import__(
                "core.environment", fromlist=["EnvironmentChecker"]
            )
            .EnvironmentChecker()
            .install_missing(),
            "run_env_sysinfo": lambda: __import__(
                "core.environment", fromlist=["EnvironmentChecker"]
            )
            .EnvironmentChecker()
            .show_system_info(),
            # Reports & Safety
            "run_report_manager": lambda: __import__(
                "core.reporter", fromlist=["ReportGenerator"]
            ).ReportGenerator.show_reports(),
            "show_safety_history": lambda: __import__(
                "main", fromlist=["show_safety_history"]
            ).show_safety_history(),
            "run_restore_backup": lambda: __import__(
                "main", fromlist=["run_restore_backup"]
            ).run_restore_backup(),
            "run_backup_now": lambda: __import__(
                "main", fromlist=["run_backup_now"]
            ).run_backup_now(),
            "run_firmware_verify": lambda: __import__(
                "core.firmware_verify", fromlist=["run"]
            ).run(),
            "run_create_shortcut": lambda: __import__(
                "main", fromlist=["run_create_shortcut"]
            ).run_create_shortcut(),
            # Emergency
            "run_emergency_recovery": lambda: __import__(
                "core.emergency", fromlist=["EmergencyRecovery"]
            )
            .EmergencyRecovery()
            .run_full_emergency(),
            "_emergency_kill_adb": lambda: __import__(
                "core.emergency", fromlist=["EmergencyRecovery"]
            )
            .EmergencyRecovery()
            .kill_adb_zombie(),
            "_emergency_restart_adb": lambda: __import__(
                "core.emergency", fromlist=["EmergencyRecovery"]
            )
            .EmergencyRecovery()
            .restart_adb_service(),
            "_emergency_clean_temp": lambda: __import__(
                "core.emergency", fromlist=["EmergencyRecovery"]
            )
            .EmergencyRecovery()
            .clean_temp_files(),
            "run_check_update": lambda: __import__(
                "core.update_checker", fromlist=["UpdateInstaller"]
            )
            .UpdateInstaller()
            .run_update_flow(),
            # Plugin
            "run_plugin_manager": lambda: __import__(
                "main", fromlist=["run_plugin_manager"]
            ).run_plugin_manager(),
            "run_plugin_scan": lambda: __import__(
                "main", fromlist=["run_plugin_scan"]
            ).run_plugin_scan(),
            "run_plugin_reload": lambda: __import__(
                "main", fromlist=["run_plugin_reload"]
            ).run_plugin_reload(),
        }

        return func_map.get(func_name)

    # ── Daftar fungsi berbahaya yang butuh validasi Protection Layer ──
    _DANGEROUS_FUNCS = {
        "run_flasher",  # STM32 Flash
        "run_anti_brick",  # STM32 Anti-Brick
        "run_android_flash",  # Android Flash
        "run_android_unlock",  # Unlock Bootloader
        "run_android_root",  # Root Android
        "run_android_frp",  # FRP Bypass
        "run_android_reset",  # Factory Reset
        "run_emergency_recovery",  # Emergency Recovery
        "run_restore_backup",  # Restore Backup
        "run_firmware_verify",  # Firmware Verify
        "run_diagnostic",  # STM32 Diagnostic (bisa tulis flash)
    }

    def _run_cli(self, func_name):
        """Jalankan fungsi CLI via Task Manager (background thread aman)"""
        if self.is_running:
            self.log_message(
                "⏳ Ada operasi sedang berjalan! Tunggu selesai.", "warning"
            )
            return

        func = self._get_func(func_name)
        if func is None:
            self.log_message(f"Fungsi '{func_name}' tidak dikenal!", "error")
            return

        # Clear output
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

        # Ensure console is visible
        if not self.console_visible:
            self._toggle_console()

        # Start via Task Manager
        self.is_running = True
        task_name = func_name.replace("_", " ").title()
        self.status_var.set(f"⏳ {task_name}...")

        # Log start
        self.log_message(f"\n{'=' * 60}", "info")
        self.log_message(f"  {task_name}", "header")
        self.log_message(f"{'=' * 60}\n", "info")

        # Determine if this task needs Protection Layer validation
        needs_protection = func_name in self._DANGEROUS_FUNCS
        if needs_protection:
            self.log_message(
                "🛡  Protection Layer aktif — memvalidasi environment...", "warning"
            )

        # Run via TaskManager (handles threading, events, status, protection)
        # NOTE: 'cli_func' passed via kwargs to avoid duplicate 'func' keyword
        task_manager.run(
            name=task_name,
            func=self._task_runner,
            func_name=func_name,
            cli_func=func,
            requires_protection=needs_protection,
        )

    def _gui_input_handler(self, prompt=""):
        """Thread-safe input handler to replace builtins.input during tasks"""
        import threading
        event = threading.Event()
        result = {"value": ""}
        print(prompt, end="", flush=True)
        self.root.after(0, self._show_input_dialog, prompt, result, event)
        event.wait()
        print(f" {result['value']}")
        return result["value"]

    def _show_input_dialog(self, prompt, result_dict, event):
        """Runs on main thread: shows dialog and sets event"""
        dialog = ctk.CTkInputDialog(text=prompt, title="NST Ultimate - Input Required")
        answer = dialog.get_input()
        result_dict["value"] = answer if answer is not None else ""
        event.set()

    def _task_runner(self, func_name: str, cli_func):
        """Internal: jalankan fungsi dengan stdout redirection dan input patching"""
        import builtins
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_input = builtins.input
        redirector = TextRedirector(self.output_text)

        try:
            sys.stdout = redirector
            sys.stderr = redirector
            builtins.input = self._gui_input_handler

            # Jalankan fungsi
            cli_func()

            print(f"\n{'=' * 60}")
            print("  SELESAI ✓")
            print(f"{'=' * 60}\n")

        except Exception as e:
            import traceback

            error_msg = f"ERROR: {e}\n{traceback.format_exc()}"
            self.output_text.after(0, self._append_error, error_msg)

            # If task_manager catches this too, it will emit TASK_FAILED
            # But we re-raise so TaskManager can properly track status
            raise

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            builtins.input = old_input

    def _append_error(self, msg):
        """Append error message to output"""
        try:
            self.output_text.configure(state="normal")
            self.output_text.insert("end", f"\n⚠  {msg}\n", "error")
            self.output_text.see("end")
            self.output_text.configure(state="disabled")
        except Exception:
            pass

    def log_message(self, message, tag="info"):
        """Log message ke output text"""
        try:
            self.output_text.configure(state="normal")
            self.output_text.insert("end", f"{message}\n", tag)
            self.output_text.see("end")
            self.output_text.configure(state="disabled")
        except Exception:
            pass

    # =========================================================================
    # QUICK ACTION WRAPPERS (Dashboard & Pages)
    # =========================================================================

    def _run_smart_scan(self):
        if not self.console_visible:
            self._toggle_console()
            
        task_manager.run_progress(
            "Smart Deep Scan",
            run_smart_scan,
            resource=None
        )

    def _run_scan_device(self):
        self._run_cli("run_device_scan")

    def _run_diagnostic(self):
        """Device-aware diagnostic: route based on detected device type"""
        dev_type = self._detect_device_type_sync()
        if dev_type == "android":
            self._run_android_diagnostic()
        elif dev_type == "iphone":
            self._run_iphone_full_scan()
        elif dev_type == "stm32":
            self._run_stm32_diagnostic()
        else:
            self._run_cli("run_device_scan")

    def _run_flash_firmware(self):
        """Device-aware flash: route based on detected device type"""
        dev_type = self._detect_device_type_sync()
        if dev_type == "android":
            self._run_android_flash()
        elif dev_type == "stm32":
            self._run_stm32_flash()
        elif dev_type == "iphone":
            self._run_iphone_full_scan()
        else:
            self._run_android_flash()

    def _run_emergency(self):
        self._run_cli("run_emergency_recovery")

    def _run_android_scan(self):
        self._run_cli("run_android_scan")

    def _run_android_root_check(self):
        self._run_cli("run_android_root_check")

    def _run_android_diagnostic(self):
        self._run_cli("run_android_diagnostic")

    def _run_android_clean_cache(self):
        self._run_cli("run_android_clean_cache")

    def _run_android_reset(self):
        self._run_cli("run_android_reset")

    def _run_android_flash(self):
        self._run_cli("run_android_flash")

    def _run_android_unlock(self):
        self._run_cli("run_android_unlock")

    def _run_android_root(self):
        self._run_cli("run_android_root")

    def _run_android_frp(self):
        self._run_cli("run_android_frp")

    def _run_iphone_full_scan(self):
        self._run_cli("run_iphone_full_scan")

    def _run_iphone_driver_check(self):
        self._run_cli("run_iphone_driver_check")

    def _run_iphone_mode_guide(self):
        self._run_cli("run_iphone_mode_guide")

    def _run_iphone_battery_guide(self):
        self._run_cli("run_iphone_battery_guide")

    def _run_iphone_activation_check(self):
        self._run_cli("run_iphone_activation_check")

    def _run_iphone_install_guide(self):
        self._run_cli("run_iphone_install_guide")

    def _run_iphone_port_verify(self):
        self._run_cli("run_iphone_port_verify")

    def _run_stm32_flash(self):
        self._run_cli("run_flasher")

    def _run_stm32_diagnostic(self):
        self._run_cli("run_diagnostic")

    def _run_stm32_anti_brick(self):
        self._run_cli("run_anti_brick")

    def _run_stm32_driver_doctor(self):
        self._run_cli("run_driver_doctor")

    def _run_backup_now(self):
        self._run_cli("run_backup_now")

    def _run_restore_backup(self):
        self._run_cli("run_restore_backup")

    def _run_firmware_verify(self):
        self._run_cli("run_firmware_verify")

    def _run_safety_history(self):
        self._run_cli("show_safety_history")

    def _run_create_shortcut(self):
        self._run_cli("run_create_shortcut")

    def _run_kill_adb(self):
        self._run_cli("_emergency_kill_adb")

    def _run_restart_adb(self):
        self._run_cli("_emergency_restart_adb")

    def _run_clean_temp(self):
        self._run_cli("_emergency_clean_temp")

    def _run_device_scan(self):
        self._run_cli("run_device_scan")

    def _run_device_detail(self):
        self._run_cli("run_device_detail")

    def _run_device_monitor(self):
        self._run_cli("run_device_monitor")

    def _run_report_manager(self):
        self._run_cli("run_report_manager")

    def _run_env_check(self):
        self._run_cli("run_env_check")

    def _run_env_install(self):
        self._run_cli("run_env_install")

    def _run_env_sysinfo(self):
        self._run_cli("run_env_sysinfo")

    def _run_check_update(self):
        self._run_cli("run_check_update")

    def _run_plugin_manager(self):
        self._run_cli("run_plugin_manager")

    def _run_plugin_scan(self):
        self._run_cli("run_plugin_scan")

    def _run_plugin_reload(self):
        self._run_cli("run_plugin_reload")

    # =========================================================================
    # WINDOW CLOSE HANDLER
    # =========================================================================

    def _on_close(self):
        """Handle window close event — stop all services gracefully"""
        if self.is_running:
            self.log_message(
                "⏳ Operasi masih berjalan... Tunggu sampai selesai.", "warning"
            )
            return

        # Stop background services
        self.background_service.stop()

        # Emit shutdown event
        event_bus.emit(EventBus.SYSTEM_SHUTDOWN)

        # Cleanup UI widgets
        if self.toast_notifier:
            try:
                self.toast_notifier.destroy()
            except Exception:
                pass

        if self.status_center:
            try:
                self.status_center.destroy()
            except Exception:
                pass

        # Cleanup sentinel
        if self._sentinel_cleanup:
            try:
                self._sentinel_cleanup()
            except Exception:
                pass

        self.root.destroy()

    # =========================================================================
    # RUN
    # =========================================================================

    def run(self):
        """Start GUI main loop"""
        if ctk is None:
            print("CustomTkinter tidak terinstall! Jalankan: pip install customtkinter")
            return
        self.root.mainloop()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def main():
    """Launch GUI"""
    gui = NSTGUI()
    gui.run()


if __name__ == "__main__":
    main()


