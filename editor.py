import json
import keyword
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
import importlib
import shutil


REQUIRED_PIP_MODULES = {}


def _run_command(cmd):
    try:
        return subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except Exception:
        return False


def _install_missing_pip_modules():
    for module_name, pip_name in REQUIRED_PIP_MODULES.items():
        try:
            importlib.import_module(module_name)
            continue
        except ModuleNotFoundError:
            pass
        print(f"Missing module '{module_name}'. Installing '{pip_name}'...")
        _run_command([sys.executable, "-m", "pip", "install", pip_name])


def _try_install_tkinter_linux():
    pkg_managers = [
        (["apt-get", "update"], ["apt-get", "install", "-y", "python3-tk"], "sudo apt-get install -y python3-tk"),
        (["dnf", "install", "-y", "python3-tkinter"], None, "sudo dnf install -y python3-tkinter"),
        (["yum", "install", "-y", "python3-tkinter"], None, "sudo yum install -y python3-tkinter"),
        (["pacman", "-Sy", "--noconfirm", "tk"], None, "sudo pacman -Sy --noconfirm tk"),
    ]
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    for pre_cmd, install_cmd, hint in pkg_managers:
        if not shutil.which(pre_cmd[0]):
            continue
        if is_root:
            if _run_command(pre_cmd) and (install_cmd is None or _run_command(install_cmd)):
                return True, hint
        elif shutil.which("sudo"):
            sudo_pre = ["sudo", "-n"] + pre_cmd
            sudo_install = ["sudo", "-n"] + install_cmd if install_cmd else None
            if _run_command(sudo_pre) and (sudo_install is None or _run_command(sudo_install)):
                return True, hint
        return False, hint
    return False, "Install Tk for your Linux distro (example: sudo apt-get install -y python3-tk)"


def _ensure_tkinter():
    try:
        import tkinter as tkinter_module
        return tkinter_module
    except ModuleNotFoundError:
        pass

    print("tkinter is missing. Attempting automatic installation...")
    system_name = platform.system().lower()
    hint = "Install Tkinter for your platform and run the editor again."

    if system_name == "linux":
        installed, hint = _try_install_tkinter_linux()
        if installed:
            try:
                import tkinter as tkinter_module
                print("tkinter installed successfully.")
                return tkinter_module
            except ModuleNotFoundError:
                pass
    elif system_name == "darwin":
        hint = "Install Python with Tk support (for Homebrew Python, reinstall Python and tkinter support)."
    elif system_name == "windows":
        hint = "Reinstall Python from python.org and ensure Tcl/Tk is selected in the installer."

    print("Automatic tkinter installation failed.")
    print(f"Manual fix: {hint}")
    raise ModuleNotFoundError("No module named 'tkinter'")


_install_missing_pip_modules()
tk = _ensure_tkinter()
from tkinter import colorchooser, filedialog, messagebox, ttk

MAX_RECENT_FILES = 10
SETTINGS_FILE = "settings.json"
APP_START_TIME = time.time()
DEFAULT_TEXT_COLOR = "#d7dde7"
DEFAULT_BG_COLOR = "#121417"
UI_BG = "#111318"
UI_PANEL_BG = "#171a1f"
UI_ELEVATED_BG = "#1d2330"
UI_BORDER_COLOR = "#2a3242"
UI_MUTED_TEXT = "#9aa4b2"
DEFAULT_SHOW_SIDEBAR = False
DEFAULT_SHOW_LINE_NUMBERS = False

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
}

LANGUAGE_KEYWORDS = {
    "python": sorted(set(keyword.kwlist)),
    "javascript": [
        "break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete",
        "do", "else", "export", "extends", "false", "finally", "for", "function", "if", "import",
        "in", "instanceof", "let", "new", "null", "return", "super", "switch", "this", "throw",
        "true", "try", "typeof", "var", "void", "while", "with", "yield",
    ],
    "json": ["true", "false", "null"],
    "markdown": ["#", "##", "###", "- ", "* ", "1. ", "```"],
}

PAIR_CHARS = {
    "(": ")",
    "[": "]",
    "{": "}",
    "\"": "\"",
    "'": "'",
}


def format_elapsed(seconds):
    total = int(max(0, seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_language_for_path(file_path):
    if not file_path:
        return "plaintext"
    _, ext = os.path.splitext(file_path.lower())
    return LANGUAGE_EXTENSIONS.get(ext, "plaintext")


def to_index(char_pos):
    return f"1.0+{char_pos}c"


def get_keyword_candidates(language, prefix):
    if not prefix:
        return []
    words = LANGUAGE_KEYWORDS.get(language, [])
    return [w for w in words if w.startswith(prefix)]


def short_display_path(path, max_len=56):
    if not path:
        return "Untitled"
    path = os.path.abspath(path)
    if len(path) <= max_len:
        return path
    keep = max_len - 3
    return f"...{path[-keep:]}"


def resolve_ui_bg(color):
    return UI_PANEL_BG if color in ("black", "#000000") else color


def file_name_from_path(path):
    return os.path.basename(path) if path else "New File"


def safe_tab_title(editor_tab):
    title = file_name_from_path(editor_tab.file_path)
    if editor_tab.modified:
        return f"{title}*"
    return title


def update_status_bar(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        status_var.set("No tab selected")
        return

    insert_idx = editor_tab.text_area.index("insert")
    line, col = insert_idx.split(".")
    path = short_display_path(editor_tab.file_path)
    modified_mark = "*" if editor_tab.modified else ""
    elapsed = format_elapsed(time.time() - APP_START_TIME)
    parts = [path, f"{line}:{int(col) + 1}{modified_mark}", elapsed]
    if editor_tab.liveshare_active and editor_tab.liveshare_room:
        parts.append(f"live:{editor_tab.liveshare_room}")
    status_var.set("  ".join(parts))


def refresh_tab_title(editor_tab):
    try:
        idx = notebook.index(editor_tab.frame)
    except tk.TclError:
        return
    notebook.tab(idx, text=safe_tab_title(editor_tab))
    editor_tab.language = get_language_for_path(editor_tab.file_path)
    editor_tab.run_highlight()
    update_status_bar()


def apply_text_area_theme(editor_tab):
    editor_tab.text_area.config(
        bg=bg_color,
        fg=text_color,
        insertbackground=text_color,
        font=("Consolas", current_font_size),
        wrap=tk.WORD if word_wrap_enabled else tk.NONE,
    )
    if line_numbers_enabled:
        editor_tab.line_numbers_canvas.config(bg=UI_PANEL_BG, width=46)
        if not editor_tab.line_numbers_canvas.winfo_ismapped():
            editor_tab.line_numbers_canvas.pack(side=tk.LEFT, fill=tk.Y, before=editor_tab.text_area)
    else:
        if editor_tab.line_numbers_canvas.winfo_ismapped():
            editor_tab.line_numbers_canvas.pack_forget()
    editor_tab.scrollbar.config(bg=UI_PANEL_BG, activebackground=UI_ELEVATED_BG, troughcolor=UI_PANEL_BG)
    editor_tab.update_line_numbers()


def add_recent_file(file_path):
    global recent_files
    if not file_path:
        return
    abs_path = os.path.abspath(file_path)
    recent_files = [p for p in recent_files if p != abs_path]
    recent_files.insert(0, abs_path)
    recent_files = recent_files[:MAX_RECENT_FILES]
    rebuild_recent_files_menu()


def rebuild_recent_files_menu():
    if open_recent_menu is None:
        return
    open_recent_menu.delete(0, tk.END)
    if not recent_files:
        open_recent_menu.add_command(label="(empty)", state=tk.DISABLED)
        return
    for path in recent_files:
        open_recent_menu.add_command(label=path, command=lambda p=path: open_recent_file(p))


def open_recent_file(path):
    global recent_files
    if not os.path.exists(path):
        messagebox.showwarning("Open Recent", f"File not found:\n{path}")
        if path in recent_files:
            recent_files.remove(path)
            rebuild_recent_files_menu()
            save_settings()
        return
    open_file_in_new_tab(path)


def restore_session_tabs():
    restored = 0
    for path in session_open_tabs:
        if path and os.path.isfile(path):
            if open_file_in_new_tab(path):
                restored += 1
    return restored


def update_status_timer():
    update_status_bar()
    root.after(1000, update_status_timer)


def set_project_root(selected_dir):
    global project_root
    project_root = selected_dir
    project_label_var.set(f"Project: {project_root}")
    for item in file_tree.get_children():
        file_tree.delete(item)
    root_item = file_tree.insert("", "end", text=os.path.basename(project_root) or project_root, open=True, values=(project_root,))
    populate_tree_node(root_item, project_root)


def populate_tree_node(parent_item, abs_dir):
    try:
        entries = sorted(os.listdir(abs_dir), key=lambda name: (not os.path.isdir(os.path.join(abs_dir, name)), name.lower()))
    except OSError:
        return

    for name in entries:
        full_path = os.path.join(abs_dir, name)
        item = file_tree.insert(parent_item, "end", text=name, open=False, values=(full_path,))
        if os.path.isdir(full_path):
            file_tree.insert(item, "end", text="__dummy__")


def on_tree_open(event=None):
    selected = file_tree.focus()
    if not selected:
        return
    values = file_tree.item(selected, "values")
    if not values:
        return
    path = values[0]
    if not os.path.isdir(path):
        return

    children = file_tree.get_children(selected)
    if len(children) == 1 and file_tree.item(children[0], "text") == "__dummy__":
        file_tree.delete(children[0])
        populate_tree_node(selected, path)


def open_file_in_new_tab(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
    except Exception as e:
        messagebox.showerror("Error", f"Gabim gjate hapjes se skedarit: {e}")
        return None

    editor_tab = create_new_tab(file_name_from_path(file_path))
    editor_tab.text_area.delete("1.0", tk.END)
    editor_tab.text_area.insert("1.0", content)
    editor_tab.file_path = file_path
    editor_tab.modified = False
    editor_tab.update_line_numbers()
    add_recent_file(file_path)
    refresh_tab_title(editor_tab)
    return editor_tab


def on_tree_double_click(event=None):
    selected = file_tree.focus()
    if not selected:
        return
    values = file_tree.item(selected, "values")
    if not values:
        return
    path = values[0]
    if os.path.isfile(path):
        open_file_in_new_tab(path)


def open_project_folder(event=None):
    selected_dir = filedialog.askdirectory()
    if not selected_dir:
        return
    set_project_root(selected_dir)
    save_settings()


def start_liveshare_with_custom_server(editor_tab):
    if editor_tab is None:
        messagebox.showwarning("LiveShare", "No active tab to share.")
        return

    def connect():
        server_host = host_entry.get()
        room_name = room_entry.get().strip() or "default"
        try:
            server_port = int(port_entry.get())
            if server_port <= 0 or server_port > 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("LiveShare", "Port must be a number between 1 and 65535.")
            return
        connect_window.destroy()
        start_liveshare_client(editor_tab, server_host, server_port, room_name)

    connect_window = tk.Toplevel(root)
    connect_window.title("Connect to LiveShare Server")
    ui_bg = resolve_ui_bg(bg_color)
    connect_window.configure(bg=ui_bg)

    tk.Label(connect_window, text="Server Host:", bg=ui_bg, fg=text_color).grid(row=0, column=0, padx=5, pady=5)
    host_entry = tk.Entry(connect_window, bg=ui_bg, fg=text_color, insertbackground=text_color)
    host_entry.insert(0, "localhost")
    host_entry.grid(row=0, column=1, padx=5, pady=5)

    tk.Label(connect_window, text="Server Port:", bg=ui_bg, fg=text_color).grid(row=1, column=0, padx=5, pady=5)
    port_entry = tk.Entry(connect_window, bg=ui_bg, fg=text_color, insertbackground=text_color)
    port_entry.insert(0, "9999")
    port_entry.grid(row=1, column=1, padx=5, pady=5)

    tk.Label(connect_window, text="Room:", bg=ui_bg, fg=text_color).grid(row=2, column=0, padx=5, pady=5)
    room_entry = tk.Entry(connect_window, bg=ui_bg, fg=text_color, insertbackground=text_color)
    room_entry.insert(0, editor_tab.liveshare_room or "default")
    room_entry.grid(row=2, column=1, padx=5, pady=5)

    tk.Button(
        connect_window,
        text="Connect",
        command=connect,
        bg="#2a2a2a",
        fg=text_color,
        activebackground="#3a3a3a",
        activeforeground=text_color,
    ).grid(row=3, column=0, columnspan=2, pady=10)


def stop_liveshare(editor_tab):
    if not editor_tab:
        return
    if editor_tab.liveshare_handler_id is not None:
        try:
            editor_tab.text_area.unbind("<KeyRelease>", editor_tab.liveshare_handler_id)
        except Exception:
            pass
        editor_tab.liveshare_handler_id = None
    if editor_tab.liveshare_sock:
        try:
            editor_tab.liveshare_sock.close()
        except OSError:
            pass
    editor_tab.liveshare_sock = None
    editor_tab.liveshare_active = False
    editor_tab.liveshare_room = None
    update_status_bar()


def _schedule_stop_liveshare(editor_tab):
    root.after(0, stop_liveshare, editor_tab)


def start_liveshare_client(editor_tab, server_host="localhost", server_port=9999, room_name="default"):
    stop_liveshare(editor_tab)

    def receive_updates(sock):
        recv_buffer = ""
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                recv_buffer += data.decode("utf-8")

                while "\n" in recv_buffer:
                    line, recv_buffer = recv_buffer.split("\n", 1)
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if message.get("type") != "sync":
                        continue
                    if message.get("room") != editor_tab.liveshare_room:
                        continue
                    remote_text = message.get("text", "")
                    root.after(0, apply_remote_text, remote_text)
            except Exception:
                break
        if editor_tab.liveshare_sock is sock:
            _schedule_stop_liveshare(editor_tab)

    def apply_remote_text(remote_text):
        current_text = editor_tab.text_area.get("1.0", "end-1c")
        if remote_text != current_text:
            editor_tab.text_area.delete("1.0", tk.END)
            editor_tab.text_area.insert("1.0", remote_text)

    def on_key_release(event=None):
        if not editor_tab.liveshare_sock:
            return
        try:
            text = editor_tab.text_area.get("1.0", "end-1c")
            payload = json.dumps({"type": "sync", "room": editor_tab.liveshare_room, "text": text}) + "\n"
            editor_tab.liveshare_sock.sendall(payload.encode("utf-8"))
        except Exception:
            stop_liveshare(editor_tab)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((server_host, server_port))
        sock.settimeout(None)
        editor_tab.liveshare_sock = sock
        editor_tab.liveshare_active = True
        editor_tab.liveshare_room = room_name
        join_payload = json.dumps({"type": "join", "room": room_name}) + "\n"
        editor_tab.liveshare_sock.sendall(join_payload.encode("utf-8"))
        threading.Thread(target=receive_updates, args=(sock,), daemon=True).start()
        editor_tab.liveshare_handler_id = editor_tab.text_area.bind("<KeyRelease>", on_key_release, add="+")
        on_key_release()
        update_status_bar()
        messagebox.showinfo("LiveShare", f"Connected to {server_host}:{server_port} (room: {room_name})")
    except socket.timeout:
        stop_liveshare(editor_tab)
        messagebox.showerror("LiveShare", f"Timeout - Serveri nuk u gjet në {server_host}:{server_port}")
    except ConnectionRefusedError:
        stop_liveshare(editor_tab)
        messagebox.showerror("LiveShare", f"Lidhja u refuzua - Sigurohuni që serveri është duke xhiruar në {server_host}:{server_port}")
    except Exception as e:
        stop_liveshare(editor_tab)
        messagebox.showerror("LiveShare", f"Nuk u lidh: {e}")


def autosave():
    for editor_tab in tabs.values():
        if editor_tab.modified and editor_tab.file_path:
            try:
                with open(editor_tab.file_path, "w", encoding="utf-8") as file:
                    file.write(editor_tab.text_area.get("1.0", "end-1c"))
                editor_tab.modified = False
                refresh_tab_title(editor_tab)
            except Exception as e:
                print(f"Gabim gjatë autoruajtjes: {e}")
    root.after(120000, autosave)


def load_colors():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            settings = json.load(file)
        return (
            settings.get("text_color", DEFAULT_TEXT_COLOR),
            settings.get("bg_color", DEFAULT_BG_COLOR),
            settings.get("font_size", 12),
            settings.get("project_root"),
            settings.get("recent_files", []),
            settings.get("word_wrap", True),
            settings.get("open_tabs", []),
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_TEXT_COLOR, DEFAULT_BG_COLOR, 12, None, [], True, []


def apply_ui_theme():
    ui_bg = resolve_ui_bg(bg_color)
    root.configure(bg=ui_bg)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=ui_bg, foreground=text_color)
    style.configure("TFrame", background=ui_bg)
    style.configure("TLabel", background=ui_bg, foreground=UI_MUTED_TEXT)
    style.configure("TNotebook", background=ui_bg, borderwidth=0, tabmargins=(2, 2, 2, 0))
    style.configure(
        "TNotebook.Tab",
        background=UI_PANEL_BG,
        foreground=UI_MUTED_TEXT,
        borderwidth=0,
        padding=(10, 4),
    )
    style.map("TNotebook.Tab", background=[("selected", UI_ELEVATED_BG)], foreground=[("selected", text_color)])
    style.configure(
        "TEntry",
        fieldbackground=UI_ELEVATED_BG,
        foreground=text_color,
        insertcolor=text_color,
        borderwidth=0,
        relief="flat",
    )
    style.configure("TButton", background=UI_ELEVATED_BG, foreground=text_color, borderwidth=0, relief="flat")
    style.map("TButton", background=[("active", UI_ELEVATED_BG), ("pressed", UI_ELEVATED_BG)], foreground=[("active", text_color)])
    style.configure("Treeview", background=UI_PANEL_BG, foreground=text_color, fieldbackground=UI_PANEL_BG, rowheight=20, borderwidth=0)
    style.configure("Treeview.Heading", background=UI_ELEVATED_BG, foreground=UI_MUTED_TEXT, relief="flat", borderwidth=0)
    style.map("Treeview", background=[("selected", UI_ELEVATED_BG)], foreground=[("selected", text_color)])
    root.option_add("*Menu.Background", UI_PANEL_BG)
    root.option_add("*Menu.Foreground", text_color)
    root.option_add("*Menu.ActiveBackground", UI_ELEVATED_BG)
    root.option_add("*Menu.ActiveForeground", text_color)
    file_tree.tag_configure("dir", foreground=UI_MUTED_TEXT)
    file_tree.tag_configure("file", foreground=text_color)


def save_settings():
    settings = {
        "text_color": text_color,
        "bg_color": bg_color,
        "font_size": current_font_size,
        "project_root": project_root,
        "recent_files": recent_files,
        "word_wrap": word_wrap_enabled,
        "open_tabs": [tab.file_path for tab in tabs.values() if tab.file_path],
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file)


def save_colors(text_color_value, bg_color_value, font_size_value):
    global text_color, bg_color, current_font_size
    text_color = text_color_value
    bg_color = bg_color_value
    current_font_size = font_size_value
    save_settings()


def save_current_tab(editor_tab, force_choose_path=False):
    if not editor_tab:
        return False
    try:
        if force_choose_path or not editor_tab.file_path:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("All Files", "*.*"), ("Text files", "*.txt")],
            )
            if not file_path:
                return False
            editor_tab.file_path = file_path

        with open(editor_tab.file_path, "w", encoding="utf-8") as file:
            file.write(editor_tab.text_area.get("1.0", "end-1c"))

        editor_tab.modified = False
        add_recent_file(editor_tab.file_path)
        refresh_tab_title(editor_tab)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Gabim gjate ruajtjes se skedarit: {e}")
        return False


class EditorTab:
    def __init__(self, parent, text_color_value, bg_color_value, font_size_value):
        self.frame = ttk.Frame(parent)
        self.text_color = text_color_value
        self.bg_color = bg_color_value
        self.font_size = font_size_value
        self.file_path = None
        self.modified = False
        self.liveshare_sock = None
        self.liveshare_active = False
        self.liveshare_handler_id = None
        self.liveshare_room = None
        self.language = "plaintext"
        self.syntax_timer = None
        self.completion_popup = None

        editor_frame = tk.Frame(self.frame, bg=UI_BG)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        self.line_numbers_canvas = tk.Canvas(editor_frame, width=44, bg=UI_BG, bd=0, highlightthickness=0)
        self.line_numbers_canvas.pack_forget()

        self.text_area = tk.Text(
            editor_frame,
            wrap=tk.WORD,
            width=80,
            height=20,
            font=("Consolas", font_size_value),
            bg=bg_color_value,
            fg=text_color_value,
            insertbackground=text_color_value,
            undo=True,
            bd=0,
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(
            editor_frame,
            command=self.on_scroll,
            bg=UI_PANEL_BG,
            activebackground=UI_ELEVATED_BG,
            troughcolor=UI_PANEL_BG,
            highlightthickness=0,
            bd=0,
        )
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_area.config(yscrollcommand=self.on_text_scroll)
        self.text_area.bind("<KeyRelease>", self.update_line_numbers)
        self.text_area.bind("<MouseWheel>", self.update_line_numbers)
        self.text_area.bind("<Button-1>", self.update_line_numbers)
        self.text_area.bind("<Configure>", self.update_line_numbers)
        self.text_area.bind("<<Modified>>", self.on_text_modified)
        self.text_area.bind("<KeyRelease>", update_status_bar, add="+")
        self.text_area.bind("<ButtonRelease-1>", update_status_bar, add="+")
        self.text_area.bind("<KeyPress>", self.on_text_key_press, add="+")
        self.text_area.bind("<KeyRelease>", self.on_text_key_release, add="+")
        self.setup_syntax_tags()
        self.run_highlight()

    def on_scroll(self, *args):
        self.text_area.yview(*args)
        self.line_numbers_canvas.yview_moveto(args[0])
        self.update_line_numbers()

    def on_text_scroll(self, *args):
        self.scrollbar.set(*args)
        self.line_numbers_canvas.yview_moveto(args[0])
        self.update_line_numbers()

    def update_line_numbers(self, event=None):
        self.line_numbers_canvas.delete("all")
        idx = self.text_area.index("@0,0")
        while True:
            dline = self.text_area.dlineinfo(idx)
            if dline is None:
                break
            y = dline[1]
            line_number = str(idx).split(".")[0]
            self.line_numbers_canvas.create_text(5, y, anchor="nw", text=line_number, fill="gray", font=("Courier New", self.font_size))
            idx = self.text_area.index(f"{idx}+1line")

    def on_text_modified(self, event=None):
        if self.text_area.edit_modified():
            self.modified = True
            refresh_tab_title(self)
            self.text_area.edit_modified(False)

    def setup_syntax_tags(self):
        self.text_area.tag_configure("syn_keyword", foreground="#c586c0")
        self.text_area.tag_configure("syn_string", foreground="#ce9178")
        self.text_area.tag_configure("syn_comment", foreground="#6a9955")
        self.text_area.tag_configure("syn_number", foreground="#b5cea8")
        self.text_area.tag_configure("syn_heading", foreground="#4fc1ff")

    def clear_syntax_tags(self):
        for tag in ("syn_keyword", "syn_string", "syn_comment", "syn_number", "syn_heading"):
            self.text_area.tag_remove(tag, "1.0", "end")

    def run_highlight(self):
        if self.syntax_timer:
            self.text_area.after_cancel(self.syntax_timer)
        self.syntax_timer = self.text_area.after(120, self.apply_syntax_highlighting)

    def apply_syntax_highlighting(self):
        self.clear_syntax_tags()
        content = self.text_area.get("1.0", "end-1c")
        if not content:
            return

        if self.language == "markdown":
            for match in re.finditer(r"(?m)^#{1,6} .*$", content):
                self._tag_span("syn_heading", match.start(), match.end())
            return

        comment_patterns = {
            "python": r"(?m)#.*$",
            "javascript": r"(?m)//.*$",
            "json": None,
        }
        pattern = comment_patterns.get(self.language)
        if pattern:
            for match in re.finditer(pattern, content):
                self._tag_span("syn_comment", match.start(), match.end())

        string_pattern = r"(?s)(\"([^\"\\\\]|\\\\.)*\"|'([^'\\\\]|\\\\.)*')"
        for match in re.finditer(string_pattern, content):
            self._tag_span("syn_string", match.start(), match.end())

        for match in re.finditer(r"(?<!\w)\d+(?:\.\d+)?(?!\w)", content):
            self._tag_span("syn_number", match.start(), match.end())

        for kw in LANGUAGE_KEYWORDS.get(self.language, []):
            for match in re.finditer(rf"(?<!\w){re.escape(kw)}(?!\w)", content):
                self._tag_span("syn_keyword", match.start(), match.end())

    def _tag_span(self, tag, start_off, end_off):
        start = f"1.0+{start_off}c"
        end = f"1.0+{end_off}c"
        self.text_area.tag_add(tag, start, end)

    def _insert_paired(self, left, right):
        widget = self.text_area
        if widget.tag_ranges(tk.SEL):
            start = widget.index(tk.SEL_FIRST)
            end = widget.index(tk.SEL_LAST)
            selection = widget.get(start, end)
            widget.delete(start, end)
            widget.insert(start, left + selection + right)
            widget.mark_set("insert", f"{start}+{len(left + selection + right)}c")
            return "break"
        widget.insert("insert", left + right)
        widget.mark_set("insert", "insert-1c")
        return "break"

    def _autocomplete_current_word(self):
        word = self.text_area.get("insert wordstart", "insert")
        if not word or len(word) < 2:
            if self.completion_popup:
                self.completion_popup.destroy()
                self.completion_popup = None
            return
        candidates = [kw for kw in LANGUAGE_KEYWORDS.get(self.language, []) if kw.startswith(word) and kw != word]
        if not candidates:
            if self.completion_popup:
                self.completion_popup.destroy()
                self.completion_popup = None
            return
        candidates = candidates[:8]

        if self.completion_popup:
            self.completion_popup.destroy()
        self.completion_popup = tk.Toplevel(self.text_area)
        self.completion_popup.overrideredirect(True)
        self.completion_popup.configure(bg=resolve_ui_bg(bg_color))
        x, y, _, h = self.text_area.bbox("insert") or (0, 0, 0, 0)
        abs_x = self.text_area.winfo_rootx() + x
        abs_y = self.text_area.winfo_rooty() + y + h
        self.completion_popup.geometry(f"+{abs_x}+{abs_y}")

        lb = tk.Listbox(self.completion_popup, height=min(len(candidates), 6), bg=resolve_ui_bg(bg_color), fg=text_color)
        for c in candidates:
            lb.insert(tk.END, c)
        lb.pack()
        lb.selection_set(0)

        def accept(event=None):
            if not lb.curselection():
                return "break"
            choice = lb.get(lb.curselection()[0])
            self.text_area.delete("insert wordstart", "insert")
            self.text_area.insert("insert", choice)
            self.completion_popup.destroy()
            self.completion_popup = None
            self.run_highlight()
            return "break"

        lb.bind("<Return>", accept)
        lb.bind("<Double-Button-1>", accept)
        lb.focus_set()

    def on_text_key_press(self, event):
        pairs = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
        if event.char in pairs:
            return self._insert_paired(event.char, pairs[event.char])
        if event.keysym == "Tab":
            self.text_area.insert("insert", "    ")
            return "break"
        return None

    def on_text_key_release(self, event=None):
        self.run_highlight()
        if event is not None and event.keysym.isalpha():
            self._autocomplete_current_word()


root = tk.Tk()
root.title("Nullsec8 Editor")

text_color, bg_color, current_font_size, settings_project_root, settings_recent_files, settings_word_wrap, settings_open_tabs = load_colors()
option_bg = resolve_ui_bg(bg_color)
root.config(bg=bg_color)
root.option_add("*Background", option_bg)
root.option_add("*Foreground", text_color)
root.option_add("*Entry.Background", option_bg)
root.option_add("*Entry.Foreground", text_color)
root.option_add("*Entry.InsertBackground", text_color)
root.option_add("*Text.Background", option_bg)
root.option_add("*Text.Foreground", text_color)
root.option_add("*Text.InsertBackground", text_color)
root.option_add("*Menu.Background", option_bg)
root.option_add("*Menu.Foreground", text_color)
root.option_add("*Menu.ActiveBackground", UI_ELEVATED_BG)
root.option_add("*Menu.ActiveForeground", text_color)
root.option_add("*Button.Background", UI_ELEVATED_BG)
root.option_add("*Button.Foreground", text_color)
root.option_add("*Toplevel.Background", option_bg)

project_root = settings_project_root
recent_files = settings_recent_files[:MAX_RECENT_FILES] if isinstance(settings_recent_files, list) else []
word_wrap_enabled = bool(settings_word_wrap)
session_open_tabs = settings_open_tabs if isinstance(settings_open_tabs, list) else []
status_var = tk.StringVar(value="Ready")
project_label_var = tk.StringVar(value="Project: (none)")
tabs = {}
next_tab_id = 1
open_recent_menu = None
wrap_var = tk.BooleanVar(value=word_wrap_enabled)
line_numbers_enabled = DEFAULT_SHOW_LINE_NUMBERS
sidebar_visible = DEFAULT_SHOW_SIDEBAR
ui_font = ("Segoe UI", 10)

main_pane = tk.PanedWindow(root, orient=tk.HORIZONTAL, bg=UI_BG, sashwidth=3, sashrelief=tk.FLAT)
main_pane.pack(fill=tk.BOTH, expand=True)

left_sidebar = tk.Frame(main_pane, bg=UI_PANEL_BG, width=220, padx=8, pady=8)
if DEFAULT_SHOW_SIDEBAR:
    main_pane.add(left_sidebar, minsize=150)

right_panel = tk.Frame(main_pane, bg=UI_BG, padx=4, pady=4)
main_pane.add(right_panel, stretch="always")

project_header = tk.Label(
    left_sidebar,
    textvariable=project_label_var,
    bg=UI_PANEL_BG,
    fg=UI_MUTED_TEXT,
    anchor="w",
    font=ui_font,
)
project_header.pack(fill=tk.X, padx=2, pady=(0, 8))

file_tree = ttk.Treeview(left_sidebar, columns=("path",), show="tree")
file_tree.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
file_tree.bind("<<TreeviewOpen>>", on_tree_open)
file_tree.bind("<Double-1>", on_tree_double_click)

notebook = ttk.Notebook(right_panel)
notebook.pack(fill=tk.BOTH, expand=True)

status_bar = tk.Label(
    root,
    textvariable=status_var,
    bg=UI_PANEL_BG,
    fg=UI_MUTED_TEXT,
    anchor="w",
    padx=10,
    pady=6,
    font=ui_font,
)
status_bar.pack(fill=tk.X, side=tk.BOTTOM)

apply_ui_theme()


def create_new_tab(title="New File"):
    global next_tab_id
    tab_id = next_tab_id
    next_tab_id += 1
    editor_tab = EditorTab(notebook, text_color, bg_color, current_font_size)
    tabs[tab_id] = editor_tab
    notebook.add(editor_tab.frame, text=title)
    notebook.select(editor_tab.frame)
    refresh_tab_title(editor_tab)
    return editor_tab


def get_current_tab():
    selected_tab = notebook.select()
    for editor_tab in tabs.values():
        if str(editor_tab.frame) == selected_tab:
            return editor_tab
    return None


def hap_skedar(event=None):
    file_path = filedialog.askopenfilename(defaultextension=".txt", filetypes=[("All Files", "*.*"), ("Text files", "*.txt")])
    if file_path:
        open_file_in_new_tab(file_path)


def ruaj_skedar(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    try:
        if not editor_tab.file_path:
            file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("All Files", "*.*"), ("Text files", "*.txt")])
            if not file_path:
                return
            editor_tab.file_path = file_path

        with open(editor_tab.file_path, "w", encoding="utf-8") as file:
            file.write(editor_tab.text_area.get("1.0", "end-1c"))

        editor_tab.modified = False
        refresh_tab_title(editor_tab)
    except Exception as e:
        messagebox.showerror("Error", f"Gabim gjate ruajtjes se skedarit: {e}")


def ruaj_si_skedar(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    try:
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("All Files", "*.*"), ("Text files", "*.txt")])
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(editor_tab.text_area.get("1.0", "end-1c"))
        editor_tab.file_path = file_path
        editor_tab.modified = False
        refresh_tab_title(editor_tab)
    except Exception as e:
        messagebox.showerror("Error", f"Gabim gjate ruajtjes se skedarit: {e}")


def ndrysho_ngjyren_tekstit(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    ngjyra = colorchooser.askcolor()[1]
    if not ngjyra:
        return
    global text_color
    text_color = ngjyra
    for tab in tabs.values():
        tab.text_color = ngjyra
        apply_text_area_theme(tab)
    apply_ui_theme()
    update_status_bar()
    save_colors(text_color, bg_color, current_font_size)


def ndrysho_ngjyren_fonit(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    ngjyra = colorchooser.askcolor()[1]
    if not ngjyra:
        return
    global bg_color, option_bg
    bg_color = ngjyra
    option_bg = resolve_ui_bg(bg_color)
    for tab in tabs.values():
        tab.bg_color = ngjyra
        apply_text_area_theme(tab)
    apply_ui_theme()
    update_status_bar()
    save_colors(text_color, bg_color, current_font_size)


def shfaq_help():
    help_text = (
        "Shortcuts:\n"
        "Ctrl+N - New file\n"
        "Ctrl+O - Open file\n"
        "Ctrl+Shift+O - Open folder\n"
        "Ctrl+S - Save file\n"
        "Ctrl+Shift+S - Save as\n"
        "Ctrl+W - Close tab\n"
        "Ctrl+F - Find text\n"
        "Ctrl+H - Find/Replace\n"
    )
    messagebox.showinfo("Help", help_text)


def find_text(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    needle = simple_text_prompt("Find", "Find text:")
    if not needle:
        return
    editor_tab.text_area.tag_remove("highlight", "1.0", tk.END)
    pos = editor_tab.text_area.search(needle, "1.0", stopindex=tk.END)
    if not pos:
        messagebox.showinfo("Info", "Text not found.")
        return
    end = f"{pos}+{len(needle)}c"
    editor_tab.text_area.tag_add("highlight", pos, end)
    editor_tab.text_area.tag_configure("highlight", background="yellow")
    editor_tab.text_area.mark_set("insert", end)
    editor_tab.text_area.see(pos)
    update_status_bar()


def simple_text_prompt(title, label_text):
    prompt = tk.Toplevel(root)
    prompt.title(title)
    prompt.configure(bg=option_bg)
    prompt.transient(root)
    prompt.grab_set()
    tk.Label(prompt, text=label_text, bg=option_bg, fg=text_color).pack(padx=10, pady=(10, 4))
    value_var = tk.StringVar()
    entry = tk.Entry(prompt, textvariable=value_var, width=40, bg=option_bg, fg=text_color, insertbackground=text_color)
    entry.pack(padx=10, pady=4)
    entry.focus_set()
    done = {"ok": False}

    def ok():
        done["ok"] = True
        prompt.destroy()

    def cancel():
        prompt.destroy()

    buttons = tk.Frame(prompt, bg=option_bg)
    buttons.pack(pady=(4, 10))
    tk.Button(buttons, text="OK", command=ok, bg="#2a2a2a", fg=text_color).pack(side=tk.LEFT, padx=4)
    tk.Button(buttons, text="Cancel", command=cancel, bg="#2a2a2a", fg=text_color).pack(side=tk.LEFT, padx=4)
    prompt.bind("<Return>", lambda e: ok())
    prompt.bind("<Escape>", lambda e: cancel())
    prompt.wait_window()
    if done["ok"]:
        return value_var.get()
    return None


def show_find_replace(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return

    win = tk.Toplevel(root)
    win.title("Find / Replace")
    win.configure(bg=option_bg)
    win.transient(root)

    tk.Label(win, text="Find:", bg=option_bg, fg=text_color).grid(row=0, column=0, padx=8, pady=6, sticky="e")
    tk.Label(win, text="Replace:", bg=option_bg, fg=text_color).grid(row=1, column=0, padx=8, pady=6, sticky="e")

    find_var = tk.StringVar()
    replace_var = tk.StringVar()
    find_entry = tk.Entry(win, textvariable=find_var, width=36, bg=option_bg, fg=text_color, insertbackground=text_color)
    replace_entry = tk.Entry(win, textvariable=replace_var, width=36, bg=option_bg, fg=text_color, insertbackground=text_color)
    find_entry.grid(row=0, column=1, padx=8, pady=6)
    replace_entry.grid(row=1, column=1, padx=8, pady=6)
    find_entry.focus_set()

    def do_find_next():
        needle = find_var.get()
        if not needle:
            return
        text_widget = editor_tab.text_area
        start = text_widget.index("insert")
        pos = text_widget.search(needle, start, stopindex=tk.END)
        if not pos:
            pos = text_widget.search(needle, "1.0", stopindex=start)
        text_widget.tag_remove("highlight", "1.0", tk.END)
        if not pos:
            messagebox.showinfo("Find/Replace", "Text not found.")
            return
        end = f"{pos}+{len(needle)}c"
        text_widget.tag_add("highlight", pos, end)
        text_widget.tag_configure("highlight", background="yellow")
        text_widget.mark_set("insert", end)
        text_widget.see(pos)
        update_status_bar()

    def do_replace():
        needle = find_var.get()
        repl = replace_var.get()
        if not needle:
            return
        text_widget = editor_tab.text_area
        sel_start = text_widget.tag_ranges(tk.SEL)
        if sel_start:
            start = text_widget.index(tk.SEL_FIRST)
            end = text_widget.index(tk.SEL_LAST)
            if text_widget.get(start, end) == needle:
                text_widget.delete(start, end)
                text_widget.insert(start, repl)
                editor_tab.modified = True
                refresh_tab_title(editor_tab)
        do_find_next()

    def do_replace_all():
        needle = find_var.get()
        repl = replace_var.get()
        if not needle:
            return
        text_widget = editor_tab.text_area
        content = text_widget.get("1.0", "end-1c")
        count = content.count(needle)
        if count == 0:
            messagebox.showinfo("Find/Replace", "No matches found.")
            return
        content = content.replace(needle, repl)
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", content)
        editor_tab.modified = True
        refresh_tab_title(editor_tab)
        messagebox.showinfo("Find/Replace", f"Replaced {count} matches.")

    button_row = tk.Frame(win, bg=option_bg)
    button_row.grid(row=2, column=0, columnspan=2, pady=(6, 10))
    tk.Button(button_row, text="Find Next", command=do_find_next, bg="#2a2a2a", fg=text_color).pack(side=tk.LEFT, padx=4)
    tk.Button(button_row, text="Replace", command=do_replace, bg="#2a2a2a", fg=text_color).pack(side=tk.LEFT, padx=4)
    tk.Button(button_row, text="Replace All", command=do_replace_all, bg="#2a2a2a", fg=text_color).pack(side=tk.LEFT, padx=4)


def go_to_line(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    line_raw = simple_text_prompt("Go to Line", "Line number:")
    if not line_raw:
        return
    try:
        line_num = int(line_raw)
        if line_num <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Go to Line", "Please enter a valid positive number.")
        return

    last_line = int(editor_tab.text_area.index("end-1c").split(".")[0])
    line_num = min(line_num, last_line)
    idx = f"{line_num}.0"
    editor_tab.text_area.mark_set("insert", idx)
    editor_tab.text_area.see(idx)
    editor_tab.text_area.focus_set()
    update_status_bar()


def toggle_word_wrap(event=None):
    global word_wrap_enabled
    word_wrap_enabled = wrap_var.get()
    for tab in tabs.values():
        apply_text_area_theme(tab)
    update_status_bar()
    save_settings()


def toggle_sidebar(event=None):
    global sidebar_visible
    if sidebar_visible:
        main_pane.forget(left_sidebar)
        sidebar_visible = False
    else:
        main_pane.add(left_sidebar, before=right_panel, minsize=150)
        sidebar_visible = True
    update_status_bar()
    return "break"


def toggle_line_numbers(event=None):
    global line_numbers_enabled
    line_numbers_enabled = not line_numbers_enabled
    for tab in tabs.values():
        apply_text_area_theme(tab)
    update_status_bar()
    return "break"


def disconnect_liveshare(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    if editor_tab.liveshare_active:
        stop_liveshare(editor_tab)
        messagebox.showinfo("LiveShare", "Disconnected.")


def zoom_in(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    global current_font_size
    current_font_size += 1
    for tab in tabs.values():
        tab.font_size = current_font_size
        apply_text_area_theme(tab)
    save_colors(text_color, bg_color, current_font_size)
    update_status_bar()


def zoom_out(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    global current_font_size
    if current_font_size > 1:
        current_font_size -= 1
        for tab in tabs.values():
            tab.font_size = current_font_size
            apply_text_area_theme(tab)
        save_colors(text_color, bg_color, current_font_size)
        update_status_bar()


def new_file(event=None):
    create_new_tab()


def close_tab(event=None):
    current_tab = get_current_tab()
    if current_tab is None:
        return
    stop_liveshare(current_tab)
    if current_tab.modified:
        result = messagebox.askyesnocancel("Save Changes", "Do you want to save changes before closing?")
        if result is None:
            return
        if result:
            ruaj_skedar()

    tab_index = notebook.index(notebook.select())
    notebook.forget(tab_index)

    for tab_id, editor_tab in list(tabs.items()):
        if editor_tab is current_tab:
            del tabs[tab_id]
            break
    update_status_bar()


def close_tab_by_obj(current_tab):
    if current_tab is None:
        return True

    stop_liveshare(current_tab)
    if current_tab.modified:
        result = messagebox.askyesnocancel("Save Changes", "Do you want to save changes before closing?")
        if result is None:
            return False
        if result and not save_current_tab(current_tab, force_choose_path=False):
            return False

    try:
        notebook.forget(current_tab.frame)
    except tk.TclError:
        pass

    for tab_id, editor_tab in list(tabs.items()):
        if editor_tab is current_tab:
            del tabs[tab_id]
            break
    update_status_bar()
    return True


def undo(event=None):
    editor_tab = get_current_tab()
    if editor_tab:
        try:
            editor_tab.text_area.edit_undo()
        except tk.TclError:
            pass
    update_status_bar()


def redo(event=None):
    editor_tab = get_current_tab()
    if editor_tab:
        try:
            editor_tab.text_area.edit_redo()
        except tk.TclError:
            pass
    update_status_bar()


def check_unsaved_tabs():
    unsaved = [tab for tab in tabs.values() if tab.modified]
    if not unsaved:
        return True

    answer = messagebox.askyesnocancel(
        "Unsaved Changes",
        "You have unsaved tabs. Save all before exit?",
    )
    if answer is None:
        return False
    if answer:
        for tab in list(unsaved):
            if not save_current_tab(tab, force_choose_path=False):
                return False
    return True


def on_app_exit(event=None):
    if not check_unsaved_tabs():
        return "break"

    for tab in list(tabs.values()):
        stop_liveshare(tab)
    save_settings()
    root.destroy()
    return "break"


def search_in_project_worker(query, use_regex):
    if not project_root or not os.path.isdir(project_root):
        return []
    results = []
    for current_root, _, files in os.walk(project_root):
        for filename in files:
            path = os.path.join(current_root, filename)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, start=1):
                        if use_regex:
                            if re.search(query, line):
                                results.append((path, line_no, line.rstrip()))
                        else:
                            if query.lower() in line.lower():
                                results.append((path, line_no, line.rstrip()))
            except Exception:
                continue
    return results


def open_search_result(tree):
    selected = tree.focus()
    if not selected:
        return
    vals = tree.item(selected, "values")
    if len(vals) < 2:
        return
    path = vals[0]
    try:
        line_no = int(vals[1])
    except ValueError:
        return
    tab = open_file_in_new_tab(path)
    if not tab:
        return
    idx = f"{line_no}.0"
    tab.text_area.mark_set("insert", idx)
    tab.text_area.see(idx)
    tab.text_area.focus_set()
    update_status_bar()


def find_in_project(event=None):
    if not project_root or not os.path.isdir(project_root):
        messagebox.showinfo("Find in Project", "Open a project folder first.")
        return

    win = tk.Toplevel(root)
    win.title("Find in Project")
    win.configure(bg=option_bg)
    win.transient(root)
    win.geometry("900x450")

    top = tk.Frame(win, bg=option_bg)
    top.pack(fill=tk.X, padx=8, pady=8)
    tk.Label(top, text="Query:", bg=option_bg, fg=text_color).pack(side=tk.LEFT, padx=(0, 6))
    query_var = tk.StringVar()
    query_entry = tk.Entry(top, textvariable=query_var, width=40, bg=option_bg, fg=text_color, insertbackground=text_color)
    query_entry.pack(side=tk.LEFT, padx=(0, 8))
    query_entry.focus_set()
    regex_var = tk.BooleanVar(value=False)
    tk.Checkbutton(top, text="Regex", variable=regex_var, bg=option_bg, fg=text_color, selectcolor="#2a2a2a").pack(side=tk.LEFT)

    columns = ("path", "line", "text")
    tree = ttk.Treeview(win, columns=columns, show="headings")
    tree.heading("path", text="File")
    tree.heading("line", text="Line")
    tree.heading("text", text="Text")
    tree.column("path", width=320, anchor="w")
    tree.column("line", width=70, anchor="center")
    tree.column("text", width=480, anchor="w")
    tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    status = tk.Label(win, text="Ready", bg=option_bg, fg=text_color, anchor="w")
    status.pack(fill=tk.X, padx=8, pady=(0, 8))

    def run_search():
        query = query_var.get().strip()
        if not query:
            return
        for item in tree.get_children():
            tree.delete(item)
        try:
            matches = search_in_project_worker(query, regex_var.get())
        except re.error as exc:
            messagebox.showerror("Find in Project", f"Invalid regex: {exc}")
            return
        for path, line_no, text in matches:
            tree.insert("", "end", values=(path, line_no, text))
        status.config(text=f"Found {len(matches)} matches")

    tk.Button(top, text="Search", command=run_search, bg="#2a2a2a", fg=text_color).pack(side=tk.LEFT, padx=8)
    query_entry.bind("<Return>", lambda e: run_search())
    tree.bind("<Double-1>", lambda e: open_search_result(tree))


menu = tk.Menu(root, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
root.config(menu=menu)

file_menu = tk.Menu(menu, tearoff=0, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
menu.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="New", command=new_file, accelerator="Ctrl+N")
file_menu.add_command(label="Open", command=hap_skedar, accelerator="Ctrl+O")
file_menu.add_command(label="Open Folder", command=open_project_folder, accelerator="Ctrl+Shift+O")
open_recent_menu = tk.Menu(file_menu, tearoff=0, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
file_menu.add_cascade(label="Open Recent", menu=open_recent_menu)
file_menu.add_command(label="Save", command=ruaj_skedar, accelerator="Ctrl+S")
file_menu.add_command(label="Save As", command=ruaj_si_skedar, accelerator="Ctrl+Shift+S")
file_menu.add_separator()
file_menu.add_command(label="Close Tab", command=close_tab, accelerator="Ctrl+W")
file_menu.add_separator()
file_menu.add_command(label="Exit", command=on_app_exit, accelerator="Ctrl+Q")
file_menu.add_separator()
file_menu.add_command(label="Start LiveShare", command=lambda: start_liveshare_with_custom_server(get_current_tab()))
file_menu.add_command(label="Disconnect LiveShare", command=disconnect_liveshare, accelerator="Ctrl+Shift+L")

edit_menu = tk.Menu(menu, tearoff=0, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
menu.add_cascade(label="Edit", menu=edit_menu)
edit_menu.add_command(label="Change Text Color", command=ndrysho_ngjyren_tekstit, accelerator="Ctrl+T")
edit_menu.add_command(label="Change Background Color", command=ndrysho_ngjyren_fonit, accelerator="Ctrl+B")
edit_menu.add_separator()
edit_menu.add_command(label="Undo", command=undo, accelerator="Ctrl+Z")
edit_menu.add_command(label="Redo", command=redo, accelerator="Ctrl+Y")
edit_menu.add_separator()
edit_menu.add_command(label="Find", command=find_text, accelerator="Ctrl+F")
edit_menu.add_command(label="Find / Replace", command=show_find_replace, accelerator="Ctrl+H")
edit_menu.add_command(label="Go to Line", command=go_to_line, accelerator="Ctrl+L")

search_menu = tk.Menu(menu, tearoff=0, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
menu.add_cascade(label="Search", menu=search_menu)
search_menu.add_command(label="Find in Project", command=find_in_project, accelerator="Ctrl+Shift+F")

view_menu = tk.Menu(menu, tearoff=0, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
menu.add_cascade(label="View", menu=view_menu)
view_menu.add_command(label="Zoom In", command=zoom_in, accelerator="Ctrl++")
view_menu.add_command(label="Zoom Out", command=zoom_out, accelerator="Ctrl+-")
view_menu.add_checkbutton(label="Word Wrap", variable=wrap_var, command=toggle_word_wrap, accelerator="Ctrl+Shift+W")
view_menu.add_command(label="Toggle Sidebar", command=toggle_sidebar, accelerator="Ctrl+\\")
view_menu.add_command(label="Toggle Line Numbers", command=toggle_line_numbers, accelerator="Ctrl+Shift+N")

help_menu = tk.Menu(menu, tearoff=0, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
menu.add_cascade(label="Help", menu=help_menu)
help_menu.add_command(label="Help", command=shfaq_help)

root.bind("<Control-n>", new_file)
root.bind("<Control-o>", hap_skedar)
root.bind("<Control-O>", open_project_folder)
root.bind("<Control-Shift-O>", open_project_folder)
root.bind("<Control-s>", ruaj_skedar)
root.bind("<Control-Shift-S>", ruaj_si_skedar)
root.bind("<Control-Shift-s>", ruaj_si_skedar)
root.bind("<Control-w>", close_tab)
root.bind("<Control-t>", ndrysho_ngjyren_tekstit)
root.bind("<Control-b>", ndrysho_ngjyren_fonit)
root.bind("<Control-f>", find_text)
root.bind("<Control-h>", show_find_replace)
root.bind("<Control-l>", go_to_line)
root.bind("<Control-Shift-F>", find_in_project)
root.bind("<Control-Shift-f>", find_in_project)
root.bind("<Control-Shift-L>", disconnect_liveshare)
root.bind("<Control-Shift-l>", disconnect_liveshare)
root.bind("<Control-Shift-W>", lambda e: (wrap_var.set(not wrap_var.get()), toggle_word_wrap()))
root.bind("<Control-Shift-w>", lambda e: (wrap_var.set(not wrap_var.get()), toggle_word_wrap()))
root.bind("<Control-q>", on_app_exit)
root.bind("<Control-plus>", zoom_in)
root.bind("<Control-minus>", zoom_out)
root.bind("<Control-backslash>", toggle_sidebar)
root.bind("<Control-Shift-N>", toggle_line_numbers)
root.bind("<Control-Shift-n>", toggle_line_numbers)
root.bind("<Control-z>", undo)
root.bind("<Control-y>", redo)
notebook.bind("<<NotebookTabChanged>>", update_status_bar)
root.protocol("WM_DELETE_WINDOW", on_app_exit)

if restore_session_tabs() == 0:
    create_new_tab()
if project_root and os.path.isdir(project_root):
    set_project_root(project_root)
rebuild_recent_files_menu()
autosave()
update_status_bar()
update_status_timer()

# Start in a balanced clean layout.
root.update_idletasks()
try:
    total_width = max(root.winfo_width(), 980)
    main_pane.sash_place(0, int(total_width * 0.24), 0)
except tk.TclError:
    pass

root.mainloop()
