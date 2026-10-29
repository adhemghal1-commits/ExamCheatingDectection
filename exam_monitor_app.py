import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from datetime import timedelta

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2
from PIL import Image, ImageDraw, ImageTk

import settings as cfg
from alert_store import IncidentDatabaseManager, AlertDB
from cloud_backup import CloudSyncService, FirebaseSync
from video_processor import ExamVideoProcessor, Pipeline


# ---------------------------------------------------------
# Visual Styling & Palette Constants
# ---------------------------------------------------------
THEME = {
    "bg_root": "#0b0f19",        # Very dark navy/slate
    "bg_card": "#151d30",        # Card surface
    "bg_card_alt": "#1c2742",    # Secondary card surface
    "bg_panel": "#101726",       # Sidebar / panel surface
    "border": "#273553",         # Border color
    "border_light": "#3b4f7a",   # Border highlight
    "text_primary": "#f8fafc",   # Crisp white
    "text_secondary": "#94a3b8", # Muted slate
    "text_muted": "#64748b",     # Darker muted
    "accent_blue": "#3b82f6",    # Electric Blue
    "accent_blue_hover": "#2563eb",
    "accent_cyan": "#06b6d4",
    "accent_red": "#ef4444",     # Alert Red
    "accent_red_hover": "#dc2626",
    "accent_green": "#10b981",   # Success
    "accent_amber": "#f59e0b",   # Warning
    "tree_odd": "#151d30",
    "tree_even": "#182239",
    "tree_select": "#2563eb",
}


def create_icon(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Modern rounded shield
    d.rounded_rectangle((10, 10, size - 10, size - 10), radius=56, fill=(15, 23, 42, 255), outline=(59, 130, 246, 255), width=6)
    cx, cy = size // 2, size // 2
    # Eye contour
    d.ellipse((cx - 86, cy - 54, cx + 86, cy + 54), outline=(248, 250, 252, 255), width=12)
    # Pupil / Lens
    d.ellipse((cx - 36, cy - 36, cx + 36, cy + 36), fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=4)
    # Reflection dot
    d.ellipse((cx - 14, cy - 18, cx - 4, cy - 8), fill=(255, 255, 255, 255))
    return img


def build_notification(alert):
    title = "CHEATING ALERT DETECTED"
    body = (
        f"Behavior: {alert['behavior']}\n"
        f"Student ID: #{alert['student_id']}\n"
        f"Time: {alert['display_time']}\n"
        f"Confidence: {alert.get('confidence', 0.0):.0%}\n"
        f"Evidence snapshot saved."
    )
    return title, body


class ExamProctorApp(tk.Tk):
    """
    Modern Tkinter desktop application for automated exam proctoring
    and real-time cheating detection.
    """
    def __init__(self):
        super().__init__()
        self.title("Exam Guard AI — Intelligent Proctoring System")
        self.geometry("1280x820")
        self.minsize(1040, 700)
        self.configure(bg=THEME["bg_root"])

        self._setup_icon()
        self._init_theme_styles()

        # Core Services
        self.db = IncidentDatabaseManager(cfg.DB_PATH)
        self.cloud = CloudSyncService(self.db)
        self.pipeline = None

        # State management
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.alert_count = 0
        self.active_video_name = ""
        self._photo = None

        # Build Modern UI
        self._build_ui()
        self.refresh_history()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(30, self._poll)

    def _setup_icon(self):
        try:
            icon = create_icon()
            icon.save(cfg.ICON_PNG)
            icon.save(cfg.ICON_ICO, sizes=[(256, 256), (64, 64), (32, 32)])
            self._icon_img = ImageTk.PhotoImage(icon.resize((64, 64)))
            self.iconphoto(True, self._icon_img)
            self.iconbitmap(str(cfg.ICON_ICO))
        except Exception:
            pass

    def _init_theme_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Frame styles
        style.configure("Root.TFrame", background=THEME["bg_root"])
        style.configure("Card.TFrame", background=THEME["bg_card"], relief="flat")
        style.configure("Panel.TFrame", background=THEME["bg_panel"])

        # Notebook (Tabs) styling
        style.configure(
            "TNotebook",
            background=THEME["bg_root"],
            borderwidth=0,
            tabmargins=[6, 0, 6, 0]
        )
        style.configure(
            "TNotebook.Tab",
            background=THEME["bg_panel"],
            foreground=THEME["text_secondary"],
            padding=[18, 10],
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            focuscolor=THEME["bg_root"]
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", THEME["bg_card"]), ("active", THEME["bg_card_alt"])],
            foreground=[("selected", THEME["text_primary"]), ("active", THEME["text_primary"])],
        )

        # Buttons
        style.configure(
            "Primary.TButton",
            background=THEME["accent_blue"],
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            padding=[16, 7],
            borderwidth=0,
            focuscolor="none"
        )
        style.map(
            "Primary.TButton",
            background=[("active", THEME["accent_blue_hover"]), ("disabled", THEME["border"])],
            foreground=[("disabled", THEME["text_muted"])],
        )

        style.configure(
            "Danger.TButton",
            background=THEME["accent_red"],
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            padding=[14, 7],
            borderwidth=0,
            focuscolor="none"
        )
        style.map(
            "Danger.TButton",
            background=[("active", THEME["accent_red_hover"]), ("disabled", THEME["border"])],
            foreground=[("disabled", THEME["text_muted"])],
        )

        style.configure(
            "Secondary.TButton",
            background=THEME["bg_card_alt"],
            foreground=THEME["text_primary"],
            font=("Segoe UI", 9, "bold"),
            padding=[12, 6],
            borderwidth=1,
            bordercolor=THEME["border"],
            focuscolor="none"
        )
        style.map(
            "Secondary.TButton",
            background=[("active", THEME["border_light"]), ("disabled", THEME["bg_card"])],
            foreground=[("disabled", THEME["text_muted"])],
        )

        # Treeview styling
        style.configure(
            "Treeview",
            background=THEME["bg_card"],
            foreground=THEME["text_primary"],
            fieldbackground=THEME["bg_card"],
            rowheight=32,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=THEME["bg_panel"],
            foreground=THEME["text_secondary"],
            font=("Segoe UI", 9, "bold"),
            padding=[8, 8],
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "Treeview.Heading",
            background=[("active", THEME["bg_card_alt"])],
            foreground=[("active", THEME["text_primary"])]
        )
        style.map(
            "Treeview",
            background=[("selected", THEME["tree_select"])],
            foreground=[("selected", "#ffffff")]
        )

        # Progressbar
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=THEME["bg_panel"],
            background=THEME["accent_blue"],
            borderwidth=0,
            thickness=6
        )

    def _build_ui(self):
        # ---------------- Top Navigation Bar ----------------
        top_bar = tk.Frame(self, bg=THEME["bg_panel"], height=70, padx=18, pady=10)
        top_bar.pack(fill="x", side="top")

        # Brand / Title info
        brand_frame = tk.Frame(top_bar, bg=THEME["bg_panel"])
        brand_frame.pack(side="left")

        title_lbl = tk.Label(
            brand_frame,
            text="EXAM GUARD AI",
            font=("Segoe UI", 15, "bold"),
            fg=THEME["text_primary"],
            bg=THEME["bg_panel"]
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            brand_frame,
            text="Intelligent Proctoring & Behavioral Analysis",
            font=("Segoe UI", 9),
            fg=THEME["accent_cyan"],
            bg=THEME["bg_panel"]
        )
        subtitle_lbl.pack(anchor="w")

        # Top Action Buttons
        actions_frame = tk.Frame(top_bar, bg=THEME["bg_panel"])
        actions_frame.pack(side="right")

        self.btn_upload = ttk.Button(
            actions_frame, text="▶ Upload Exam Video", style="Primary.TButton", command=self.upload_video
        )
        self.btn_upload.pack(side="left", padx=6)

        self.btn_stop = ttk.Button(
            actions_frame, text="⏹ Stop", style="Danger.TButton", command=self.stop, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=6)

        self.btn_folder = ttk.Button(
            actions_frame, text="📂 Screenshots", style="Secondary.TButton", command=self.open_folder
        )
        self.btn_folder.pack(side="left", padx=6)

        # ---------------- KPI Metric Cards ----------------
        kpi_bar = tk.Frame(self, bg=THEME["bg_root"], padx=16, pady=8)
        kpi_bar.pack(fill="x")

        # Card 1: Alert Count
        self.kpi_alerts_val = tk.StringVar(value="0")
        self._create_metric_card(kpi_bar, "SESSION ALERTS", self.kpi_alerts_val, THEME["accent_red"], "🚨")

        # Card 2: Current Status
        self.kpi_status_val = tk.StringVar(value="IDLE (READY)")
        self._create_metric_card(kpi_bar, "PROCTOR STATUS", self.kpi_status_val, THEME["accent_green"], "🛡️")

        # Card 3: Active Video File
        self.kpi_video_val = tk.StringVar(value="None Selected")
        self._create_metric_card(kpi_bar, "MONITORED VIDEO", self.kpi_video_val, THEME["accent_blue"], "🎥")

        # Card 4: Database Incidents
        self.kpi_db_val = tk.StringVar(value="0 Records")
        self._create_metric_card(kpi_bar, "DATABASE LOG", self.kpi_db_val, THEME["accent_amber"], "💾")

        # ---------------- Main Tabbed Views ----------------
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        # Tab 1: Live Monitor
        self.live_tab = tk.Frame(self.tabs, bg=THEME["bg_root"])
        self.tabs.add(self.live_tab, text="  Live Monitor  ")
        self._build_live_tab()

        # Tab 2: Alert History
        self.hist_tab = tk.Frame(self.tabs, bg=THEME["bg_root"])
        self.tabs.add(self.hist_tab, text="  Alert History & Evidence  ")
        self._build_history_tab()

        # ---------------- Bottom Status Bar ----------------
        bottom_bar = tk.Frame(self, bg=THEME["bg_panel"], padx=16, pady=6)
        bottom_bar.pack(fill="x", side="bottom")

        self.progress = ttk.Progressbar(
            bottom_bar, style="Accent.Horizontal.TProgressbar", mode="determinate", maximum=100
        )
        self.progress.pack(fill="x", pady=(0, 4))

        status_sub = tk.Frame(bottom_bar, bg=THEME["bg_panel"])
        status_sub.pack(fill="x")

        self.status_var = tk.StringVar(value="System Ready. Upload an exam video to start detection.")
        tk.Label(
            status_sub, textvariable=self.status_var, bg=THEME["bg_panel"],
            fg=THEME["text_secondary"], font=("Segoe UI", 9)
        ).pack(side="left")

        self.pct_var = tk.StringVar(value="0%")
        tk.Label(
            status_sub, textvariable=self.pct_var, bg=THEME["bg_panel"],
            fg=THEME["accent_cyan"], font=("Segoe UI", 9, "bold")
        ).pack(side="right")

    def _create_metric_card(self, parent, label_text, var, accent_color, icon=""):
        card = tk.Frame(parent, bg=THEME["bg_card"], padx=14, pady=10, relief="flat", highlightbackground=THEME["border"], highlightthickness=1)
        card.pack(side="left", fill="x", expand=True, padx=5)

        header_frame = tk.Frame(card, bg=THEME["bg_card"])
        header_frame.pack(fill="x")

        tk.Label(
            header_frame, text=f"{icon} {label_text}", font=("Segoe UI", 8, "bold"),
            fg=THEME["text_muted"], bg=THEME["bg_card"]
        ).pack(side="left")

        tk.Label(
            card, textvariable=var, font=("Segoe UI", 13, "bold"),
            fg=accent_color, bg=THEME["bg_card"]
        ).pack(anchor="w", pady=(3, 0))

    def _build_live_tab(self):
        container = tk.Frame(self.live_tab, bg=THEME["bg_root"])
        container.pack(fill="both", expand=True, pady=6)

        # Left: Video stream frame
        self.video_container = tk.Frame(
            container, bg=THEME["bg_card"], highlightbackground=THEME["border"], highlightthickness=1
        )
        self.video_container.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.video_container.pack_propagate(False)

        # Placeholder inside video frame
        self.video_label = tk.Label(
            self.video_container,
            bg="#060911",
            fg=THEME["text_secondary"],
            text="VIDEO STREAM OFFLINE\n\nClick 'Upload Exam Video' above to load a session\nAI will automatically detect students, phones, head-turns and gaze direction.",
            font=("Segoe UI", 12),
            justify="center"
        )
        self.video_label.pack(fill="both", expand=True)

        # Right: Real-time Incident Feed Panel
        side_panel = tk.Frame(
            container, bg=THEME["bg_card"], width=380, highlightbackground=THEME["border"], highlightthickness=1, padx=12, pady=12
        )
        side_panel.pack(side="right", fill="y")
        side_panel.pack_propagate(False)

        side_header = tk.Frame(side_panel, bg=THEME["bg_card"])
        side_header.pack(fill="x", pady=(0, 8))

        tk.Label(
            side_header, text="🚨 Live Cheating Feed", font=("Segoe UI", 11, "bold"),
            fg=THEME["text_primary"], bg=THEME["bg_card"]
        ).pack(side="left")

        btn_clear = ttk.Button(
            side_header, text="Clear List", style="Secondary.TButton",
            command=lambda: self.live_list.delete(0, "end")
        )
        btn_clear.pack(side="right")

        # Feed Listbox
        list_frame = tk.Frame(side_panel, bg=THEME["bg_card"])
        list_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self.live_list = tk.Listbox(
            list_frame,
            bg=THEME["bg_panel"],
            fg=THEME["text_primary"],
            selectbackground=THEME["tree_select"],
            selectforeground="#ffffff",
            font=("Consolas", 10),
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=THEME["border"],
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.live_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.live_list.pack(side="left", fill="both", expand=True)

        # Help badge at bottom of side panel
        tip_frame = tk.Frame(side_panel, bg=THEME["bg_card_alt"], padx=8, pady=6, highlightbackground=THEME["border"], highlightthickness=1)
        tip_frame.pack(fill="x", pady=(8, 0))
        tk.Label(
            tip_frame,
            text="🟢 Green Box = Normal   |   🔴 Red Box = Suspect Flagged",
            font=("Segoe UI", 8, "bold"),
            fg=THEME["text_secondary"],
            bg=THEME["bg_card_alt"]
        ).pack()

    def _build_history_tab(self):
        container = tk.Frame(self.hist_tab, bg=THEME["bg_root"], pady=6)
        container.pack(fill="both", expand=True)

        # Top Search & Action Bar
        toolbar = tk.Frame(
            container, bg=THEME["bg_card"], padx=12, pady=10,
            highlightbackground=THEME["border"], highlightthickness=1
        )
        toolbar.pack(fill="x", pady=(0, 8))

        # Search field
        tk.Label(
            toolbar, text="🔍 Search:", font=("Segoe UI", 10, "bold"),
            fg=THEME["text_secondary"], bg=THEME["bg_card"]
        ).pack(side="left", padx=(0, 6))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._filter_history())
        search_entry = tk.Entry(
            toolbar, textvariable=self.search_var, bg=THEME["bg_panel"],
            fg=THEME["text_primary"], insertbackground=THEME["text_primary"],
            font=("Segoe UI", 10), width=28, borderwidth=1, relief="solid"
        )
        search_entry.pack(side="left", padx=(0, 14))

        # Action Buttons
        ttk.Button(toolbar, text="🖼️ View Evidence", style="Primary.TButton", command=self.view_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="📊 Export CSV", style="Secondary.TButton", command=self.export_csv).pack(side="left", padx=4)
        ttk.Button(toolbar, text="🗑️ Delete Selected", style="Danger.TButton", command=self.delete_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="🔄 Refresh", style="Secondary.TButton", command=self.refresh_history).pack(side="left", padx=4)

        # Treeview Table
        tree_frame = tk.Frame(
            container, bg=THEME["bg_card"], highlightbackground=THEME["border"], highlightthickness=1
        )
        tree_frame.pack(fill="both", expand=True)

        cols = ("id", "time", "student", "behavior", "confidence", "location")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")

        heads = {
            "id": ("# ID", 65, "center"),
            "time": ("Timestamp", 160, "w"),
            "student": ("Student ID", 100, "center"),
            "behavior": ("Detected Cheating Behavior", 220, "w"),
            "confidence": ("Confidence", 100, "center"),
            "location": ("Screenshot Evidence / Cloud Storage Path", 460, "w"),
        }
        for k, (txt, w, anch) in heads.items():
            self.tree.heading(k, text=txt, anchor=anch)
            self.tree.column(k, width=w, anchor=anch)

        # Alternating row colors
        self.tree.tag_configure("odd", background=THEME["tree_odd"])
        self.tree.tag_configure("even", background=THEME["tree_even"])

        sb_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        sb_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        self.tree.pack(side="left", fill="both", expand=True)
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")

        self.tree.bind("<Double-1>", lambda e: self.view_selected())

    # ---------------- Video Processing Operations ----------------
    def upload_video(self):
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("System Busy", "An exam video is currently being analyzed.")
            return

        path = filedialog.askopenfilename(
            title="Select Exam Surveillance Video",
            filetypes=[
                ("Video Files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv"),
                ("All Files", "*.*")
            ],
        )
        if not path:
            return

        self.stop_event.clear()
        self.alert_count = 0
        self.active_video_name = Path(path).name
        self.kpi_alerts_val.set("0")
        self.kpi_status_val.set("ANALYZING...")
        self.kpi_video_val.set(self.active_video_name)
        self.live_list.delete(0, "end")
        self.progress["value"] = 0
        self.pct_var.set("0%")

        self.btn_upload.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set(f"Initializing AI detection for: {self.active_video_name}")

        self.worker = threading.Thread(target=self._worker, args=(path,), daemon=True)
        self.worker.start()

    def _worker(self, path):
        try:
            if self.pipeline is None:
                self.pipeline = ExamVideoProcessor(self.db, self.cloud)

            self.pipeline.load(status=lambda m: self.q.put(("status", m)))
            self.q.put(("status", f"Processing: {Path(path).name}"))

            def on_frame(f):
                if self.q.qsize() < 3:
                    self.q.put(("frame", f))

            n = self.pipeline.run(
                path,
                on_frame=on_frame,
                on_alert=lambda a: self.q.put(("alert", a)),
                on_progress=lambda i, t: self.q.put(("progress", (i, t))),
                stop_event=self.stop_event,
            )
            self.q.put(("done", n))
        except Exception as e:
            traceback.print_exc()
            self.q.put(("error", str(e)))

    def stop(self):
        self.stop_event.set()
        self.status_var.set("Stopping proctoring analysis...")
        self.kpi_status_val.set("STOPPING...")

    def _poll(self):
        latest = None
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "frame":
                    latest = data
                elif kind == "alert":
                    self._on_alert(data)
                elif kind == "status":
                    self.status_var.set(data)
                elif kind == "progress":
                    i, total = data
                    pct = 100.0 * i / max(total, 1)
                    self.progress["value"] = pct
                    self.pct_var.set(f"{pct:.1f}%")
                elif kind == "done":
                    self._finish(f"Completed analysis. Total incidents flagged: {data}")
                elif kind == "error":
                    self._finish(f"Error encountered: {data}")
                    messagebox.showerror("Detection Error", data)
        except queue.Empty:
            pass

        if latest is not None:
            self._show_frame(latest)
        self.after(30, self._poll)

    def _finish(self, msg):
        self.btn_upload.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.status_var.set(msg)
        self.kpi_status_val.set("IDLE (READY)")
        self.refresh_history()

    def _show_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        w = max(self.video_container.winfo_width(), 320)
        h = max(self.video_container.winfo_height(), 240)
        img.thumbnail((w, h))
        self._photo = ImageTk.PhotoImage(img)
        self.video_label.configure(image=self._photo, text="")

    def _on_alert(self, alert):
        self.alert_count += 1
        self.kpi_alerts_val.set(str(self.alert_count))

        # Pretty badge entry in live list
        badge_text = f"[{alert['display_time']}] Student #{alert['student_id']:<2} ➜ {alert['behavior']}"
        self.live_list.insert(0, badge_text)

        title, body = build_notification(alert)
        self.toast(title, body)
        self.refresh_history()

    # ---------------- Alert Toast Window ----------------
    def toast(self, title, msg, ms=5000):
        t = tk.Toplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)

        box = tk.Frame(
            t, bg=THEME["bg_card"],
            highlightbackground=THEME["accent_red"], highlightthickness=2,
            padx=16, pady=12
        )
        box.pack()

        head_frame = tk.Frame(box, bg=THEME["bg_card"])
        head_frame.pack(fill="x", pady=(0, 4))

        tk.Label(
            head_frame, text=f"🚨 {title}", bg=THEME["bg_card"],
            fg=THEME["accent_red"], font=("Segoe UI", 11, "bold")
        ).pack(side="left")

        tk.Label(
            box, text=msg, bg=THEME["bg_card"], fg=THEME["text_primary"],
            justify="left", font=("Segoe UI", 9)
        ).pack(anchor="w")

        self.update_idletasks()
        x = self.winfo_x() + self.winfo_width() - t.winfo_reqwidth() - 30
        y = self.winfo_y() + 100
        t.geometry(f"+{x}+{y}")
        self._beep()
        t.after(ms, t.destroy)

    def _beep(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception:
            self.bell()

    # ---------------- Alert History Table ----------------
    def refresh_history(self):
        records = self.db.all()
        self.kpi_db_val.set(f"{len(records)} Incidents")
        self._render_history_rows(records)

    def _filter_history(self):
        query = self.search_var.get().strip().lower()
        records = self.db.all()
        if not query:
            self._render_history_rows(records)
            return

        filtered = []
        for r in records:
            # r: (id, created_at, behavior, confidence, student_id, screenshot_path, firebase_url, video_name, video_time)
            txt_repr = f"{r[0]} {r[1]} {r[2]} {r[4]} {r[7]}".lower()
            if query in txt_repr:
                filtered.append(r)
        self._render_history_rows(filtered)

    def _render_history_rows(self, records):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, r in enumerate(records):
            location = r[5] or r[6] or ""
            tag = "even" if idx % 2 == 0 else "odd"
            conf_str = f"{r[3]:.0%}" if isinstance(r[3], (int, float)) else str(r[3])
            self.tree.insert(
                "", "end", iid=str(r[0]),
                values=(r[0], r[1], f"#{r[4]}", r[2], conf_str, location),
                tags=(tag,)
            )

    def view_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select an Alert", "Please select an incident from the table first.")
            return
        row = self.db.get(int(sel[0]))
        if row:
            self.open_screenshot(row[5], row[6], details=row)

    def open_screenshot(self, path, url="", details=None):
        if path and Path(path).exists():
            win = tk.Toplevel(self)
            win.title(f"Evidence Viewer — {Path(path).name}")
            win.configure(bg=THEME["bg_root"])
            win.geometry("900x680")

            if details:
                meta = tk.Frame(win, bg=THEME["bg_card"], padx=16, pady=10)
                meta.pack(fill="x")
                info_txt = f"Student ID: #{details[4]}   |   Behavior: {details[2]}   |   Date: {details[1]}"
                tk.Label(meta, text=info_txt, font=("Segoe UI", 10, "bold"), fg=THEME["accent_cyan"], bg=THEME["bg_card"]).pack(side="left")

            img = Image.open(path)
            img.thumbnail((880, 560))
            photo = ImageTk.PhotoImage(img)

            img_frame = tk.Frame(win, bg=THEME["bg_root"])
            img_frame.pack(fill="both", expand=True, padx=12, pady=12)

            lbl = tk.Label(img_frame, image=photo, bg=THEME["bg_root"])
            lbl.image = photo
            lbl.pack(expand=True)

            btn_frame = tk.Frame(win, bg=THEME["bg_panel"], padx=12, pady=8)
            btn_frame.pack(fill="x", side="bottom")

            ttk.Button(btn_frame, text="Close", style="Secondary.TButton", command=win.destroy).pack(side="right", padx=6)
            ttk.Button(btn_frame, text="Open in System Viewer", style="Primary.TButton", command=lambda: os.startfile(str(path)) if os.name == "nt" else None).pack(side="right", padx=6)
        elif url:
            webbrowser.open(url)
        else:
            messagebox.showwarning("File Missing", "Screenshot file is missing on disk and no cloud URL is found.")

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv")],
            initialfile="exam_incidents_report.csv"
        )
        if not path:
            return
        try:
            n = self.db.export_csv(path)
            messagebox.showinfo("Export Successful", f"Successfully exported {n} incident records to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Records", "Please select one or more incidents to delete.")
            return

        ans = messagebox.askyesnocancel(
            "Confirm Deletion",
            f"Are you sure you want to delete {len(sel)} incident record(s)?\n\n"
            "• Yes: Delete both database records and screenshot evidence files\n"
            "• No: Delete database records only\n"
            "• Cancel: Keep everything"
        )
        if ans is None:
            return
        if ans:
            for iid in sel:
                row = self.db.get(int(iid))
                if row and row[5]:
                    try:
                        Path(row[5]).unlink()
                    except OSError:
                        pass
        self.db.delete([int(i) for i in sel])
        self.refresh_history()

    def open_folder(self):
        folder = str(cfg.SCREENSHOT_DIR.resolve())
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("Cannot Open Folder", str(e))

    def _on_close(self):
        self.stop_event.set()
        self.destroy()


# Backward-compatible alias
ExamApp = ExamProctorApp


if __name__ == "__main__":
    os.chdir(str(cfg.BASE_DIR))
    ExamProctorApp().mainloop()
