import json
import os
import socket
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

MAX_RECENT_FILES = 10
SETTINGS_FILE = "settings.json"


def resolve_ui_bg(color):
    return "#1e1e1e" if color in ("black", "#000000") else color


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
    path = editor_tab.file_path or "Untitled"
    room = editor_tab.liveshare_room if editor_tab.liveshare_active else "-"
    modified = "modified" if editor_tab.modified else "saved"
    wrap = "wrap" if word_wrap_enabled else "nowrap"
    status_var.set(f"{path} | Ln {line}, Col {int(col) + 1} | {modified} | {wrap} | room: {room}")


def refresh_tab_title(editor_tab):
    try:
        idx = notebook.index(editor_tab.frame)
    except tk.TclError:
        return
    notebook.tab(idx, text=safe_tab_title(editor_tab))
    update_status_bar()


def apply_text_area_theme(editor_tab):
    editor_tab.text_area.config(
        bg=bg_color,
        fg=text_color,
        insertbackground=text_color,
        font=("Courier New", current_font_size),
        wrap=tk.WORD if word_wrap_enabled else tk.NONE,
    )
    editor_tab.line_numbers_canvas.config(bg=bg_color)
    editor_tab.scrollbar.config(troughcolor=bg_color)
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
            settings.get("text_color", "green"),
            settings.get("bg_color", "black"),
            settings.get("font_size", 12),
            settings.get("project_root"),
            settings.get("recent_files", []),
            settings.get("word_wrap", True),
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return "green", "black", 12, None, [], True


def apply_ui_theme():
    ui_bg = resolve_ui_bg(bg_color)
    root.configure(bg=bg_color)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=ui_bg, foreground=text_color)
    style.configure("TFrame", background=ui_bg)
    style.configure("TLabel", background=ui_bg, foreground=text_color)
    style.configure("TNotebook", background=ui_bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=ui_bg, foreground=text_color, padding=(10, 4))
    style.configure("TEntry", fieldbackground=ui_bg, foreground=text_color)
    style.configure("TButton", background="#2a2a2a", foreground=text_color)
    style.configure("Treeview", background=ui_bg, foreground=text_color, fieldbackground=ui_bg)
    style.configure("Treeview.Heading", background="#2a2a2a", foreground=text_color)
    style.map("TNotebook.Tab", background=[("selected", "#2a2a2a"), ("active", "#1f1f1f")], foreground=[("selected", text_color), ("active", text_color)])


def save_settings():
    settings = {
        "text_color": text_color,
        "bg_color": bg_color,
        "font_size": current_font_size,
        "project_root": project_root,
        "recent_files": recent_files,
        "word_wrap": word_wrap_enabled,
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

        editor_frame = tk.Frame(self.frame, bg=bg_color_value)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        self.line_numbers_canvas = tk.Canvas(editor_frame, width=54, bg=bg_color_value, bd=0, highlightthickness=0)
        self.line_numbers_canvas.pack(side=tk.LEFT, fill=tk.Y)

        self.text_area = tk.Text(
            editor_frame,
            wrap=tk.WORD,
            width=80,
            height=20,
            font=("Courier New", font_size_value),
            bg=bg_color_value,
            fg=text_color_value,
            insertbackground=text_color_value,
            undo=True,
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollbar = tk.Scrollbar(
            editor_frame,
            command=self.on_scroll,
            bg="#2a2a2a",
            activebackground="#3a3a3a",
            troughcolor=bg_color_value,
            highlightthickness=0,
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


root = tk.Tk()
root.title("Nullsec8 Editor")

text_color, bg_color, current_font_size, settings_project_root, settings_recent_files, settings_word_wrap = load_colors()
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
root.option_add("*Menu.ActiveBackground", "#2a2a2a")
root.option_add("*Menu.ActiveForeground", text_color)
root.option_add("*Button.Background", "#2a2a2a")
root.option_add("*Button.Foreground", text_color)
root.option_add("*Toplevel.Background", option_bg)

project_root = settings_project_root
recent_files = settings_recent_files[:MAX_RECENT_FILES] if isinstance(settings_recent_files, list) else []
word_wrap_enabled = bool(settings_word_wrap)
status_var = tk.StringVar(value="Ready")
project_label_var = tk.StringVar(value="Project: (none)")
tabs = {}
next_tab_id = 1
open_recent_menu = None
wrap_var = tk.BooleanVar(value=word_wrap_enabled)

main_pane = tk.PanedWindow(root, orient=tk.HORIZONTAL, bg=option_bg, sashwidth=5)
main_pane.pack(fill=tk.BOTH, expand=True)

left_sidebar = tk.Frame(main_pane, bg=option_bg, width=240)
main_pane.add(left_sidebar, minsize=180)

right_panel = tk.Frame(main_pane, bg=bg_color)
main_pane.add(right_panel, stretch="always")

project_header = tk.Label(left_sidebar, textvariable=project_label_var, bg=option_bg, fg=text_color, anchor="w")
project_header.pack(fill=tk.X, padx=6, pady=(6, 2))

file_tree = ttk.Treeview(left_sidebar, columns=("path",), show="tree")
file_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
file_tree.bind("<<TreeviewOpen>>", on_tree_open)
file_tree.bind("<Double-1>", on_tree_double_click)

notebook = ttk.Notebook(right_panel)
notebook.pack(fill=tk.BOTH, expand=True)

status_bar = tk.Label(root, textvariable=status_var, bg="#2a2a2a", fg=text_color, anchor="w")
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

view_menu = tk.Menu(menu, tearoff=0, bg=option_bg, fg=text_color, activebackground="#2a2a2a", activeforeground=text_color)
menu.add_cascade(label="View", menu=view_menu)
view_menu.add_command(label="Zoom In", command=zoom_in, accelerator="Ctrl++")
view_menu.add_command(label="Zoom Out", command=zoom_out, accelerator="Ctrl+-")
view_menu.add_checkbutton(label="Word Wrap", variable=wrap_var, command=toggle_word_wrap, accelerator="Ctrl+Shift+W")

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
root.bind("<Control-Shift-L>", disconnect_liveshare)
root.bind("<Control-Shift-l>", disconnect_liveshare)
root.bind("<Control-Shift-W>", lambda e: (wrap_var.set(not wrap_var.get()), toggle_word_wrap()))
root.bind("<Control-Shift-w>", lambda e: (wrap_var.set(not wrap_var.get()), toggle_word_wrap()))
root.bind("<Control-q>", on_app_exit)
root.bind("<Control-plus>", zoom_in)
root.bind("<Control-minus>", zoom_out)
root.bind("<Control-z>", undo)
root.bind("<Control-y>", redo)
notebook.bind("<<NotebookTabChanged>>", update_status_bar)
root.protocol("WM_DELETE_WINDOW", on_app_exit)

create_new_tab()
if project_root and os.path.isdir(project_root):
    set_project_root(project_root)
rebuild_recent_files_menu()
autosave()
update_status_bar()
root.mainloop()
