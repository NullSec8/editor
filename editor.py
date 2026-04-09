import tkinter as tk
from tkinter import filedialog, colorchooser, messagebox, ttk
from ttkthemes import ThemedTk
import json
import socket
import threading

def start_liveshare_with_custom_server(editor_tab):
    def connect():
        server_host = host_entry.get()
        server_port = int(port_entry.get())
        connect_window.destroy()
        start_liveshare_client(editor_tab, server_host, server_port)
    
    connect_window = tk.Toplevel(root)
    connect_window.title("Connect to LiveShare Server")
    
    tk.Label(connect_window, text="Server Host:").grid(row=0, column=0, padx=5, pady=5)
    host_entry = tk.Entry(connect_window)
    host_entry.insert(0, "localhost")
    host_entry.grid(row=0, column=1, padx=5, pady=5)
    
    tk.Label(connect_window, text="Server Port:").grid(row=1, column=0, padx=5, pady=5)
    port_entry = tk.Entry(connect_window)
    port_entry.insert(0, "9999")
    port_entry.grid(row=1, column=1, padx=5, pady=5)
    
    connect_button = tk.Button(connect_window, text="Connect", command=connect)
    connect_button.grid(row=2, column=0, columnspan=2, pady=10)

def start_liveshare_client(editor_tab, server_host='localhost', server_port=9999):
    def receive_updates(sock):
        while True:
            try:
                data = sock.recv(4096).decode('utf-8')
                if data:
                    # Zëvendëson përmbajtjen vetëm nëse është ndryshe
                    current_text = editor_tab.text_area.get("1.0", tk.END).strip()
                    if data.strip() != current_text:
                        editor_tab.text_area.delete("1.0", tk.END)
                        editor_tab.text_area.insert(tk.END, data)
            except Exception as e:
                print(f"Gabim në lidhje: {e}")
                break

    def on_key_release(event=None):
        try:
            text = editor_tab.text_area.get("1.0", tk.END)
            sock.sendall(text.encode('utf-8'))
        except Exception as e:
            print(f"Gabim në dërgim: {e}")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # Timeout prej 5 sekondash
        sock.connect((server_host, server_port))
        threading.Thread(target=receive_updates, args=(sock,), daemon=True).start()
        editor_tab.text_area.bind("<KeyRelease>", on_key_release)
        messagebox.showinfo("LiveShare", f"U lidh me serverin {server_host}:{server_port}")
    except socket.timeout:
        messagebox.showerror("LiveShare", f"Timeout - Serveri nuk u gjet në {server_host}:{server_port}")
    except ConnectionRefusedError:
        messagebox.showerror("LiveShare", f"Lidhja u refuzua - Sigurohuni që serveri është duke xhiruar në {server_host}:{server_port}")
    except Exception as e:
        messagebox.showerror("LiveShare", f"Nuk u lidh: {e}")

# Funksioni Per Autosave
def autosave():
    for editor_tab in tabs.values():
        if editor_tab.modified and editor_tab.file_path:
            try:
                with open(editor_tab.file_path, 'w', encoding='utf-8') as file:
                    file.write(editor_tab.text_area.get("1.0", "end-1c"))
                editor_tab.modified = False

                # Përditëso titullin duke hequr "*" nëse ekziston
                tab_index = notebook.index(editor_tab.frame)
                current_text = notebook.tab(tab_index, "text")
                if current_text.endswith("*"):
                    notebook.tab(tab_index, text=current_text.rstrip("*"))

            except Exception as e:
                print(f"Gabim gjatë autoruajtjes: {e}")
    
    # Rikrijo thirrjen pas 2 minutash (120000 ms)
    root.after(120000, autosave)





# Funksioni per te lexuar konfigurimin e ngjyrave nga nje skedar
def load_colors():
    try:
        with open('settings.json', 'r') as file:
            settings = json.load(file)
        return (settings.get('text_color', 'green'), 
                settings.get('bg_color', 'black'), 
                settings.get('font_size', 12))
    except (FileNotFoundError, json.JSONDecodeError):
        return 'green', 'black', 12  # Ngjyrat dhe madhesia default

# Funksioni per te ruajtur konfigurimin e ngjyrave ne nje skedar
def save_colors(text_color, bg_color, font_size):
    settings = {
        'text_color': text_color,
        'bg_color': bg_color,
        'font_size': font_size
    }
    with open('settings.json', 'w') as file:
        json.dump(settings, file)

# Klasa per Ã§do tab te editorit
class EditorTab:
    def __init__(self, parent, text_color, bg_color, font_size):
        self.frame = ttk.Frame(parent)
        self.text_color = text_color
        self.bg_color = bg_color
        self.font_size = font_size
        self.file_path = None  # Rruga e skedarit
        self.modified = False  # Nese ka ndryshime te paruajtura
        self.liveshare_sock = None
        self.liveshare_active = False
        
        # Krijojme Frame per te mbajtur canvas dhe scrollbar
        editor_frame = tk.Frame(self.frame)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas per numrat e linjave
        self.line_numbers_canvas = tk.Canvas(
            editor_frame, 
            width=54, 
            bg=bg_color, 
            bd=0, 
            highlightthickness=0
        )
        self.line_numbers_canvas.pack(side=tk.LEFT, fill=tk.Y)
        
        # Zona e tekstit
        self.text_area = tk.Text(
            editor_frame, 
            wrap=tk.WORD, 
            width=80, 
            height=20, 
            font=("Courier New", font_size),
            bg=bg_color, 
            fg=text_color, 
            insertbackground=text_color, 
            undo=True
        )
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Scrollbar
        self.scrollbar = tk.Scrollbar(
            editor_frame, 
            command=self.on_scroll
        )
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.text_area.config(yscrollcommand=self.on_text_scroll)
        
        # Lidh eventet per update te numrave te linjave
        self.text_area.bind("<KeyRelease>", self.update_line_numbers)
        self.text_area.bind("<MouseWheel>", self.update_line_numbers)
        self.text_area.bind("<Button-1>", self.update_line_numbers)
        self.text_area.bind("<Configure>", self.update_line_numbers)
        
        # Lidh eventin per ndryshime
        self.text_area.bind("<<Modified>>", self.on_text_modified)
    
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
        i = self.text_area.index("@0,0")  # index i pare qe shfaqet ne fillim te view
        
        while True:
            dline = self.text_area.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            line_number = str(i).split(".")[0]
            self.line_numbers_canvas.create_text(
                5, y, anchor="nw", text=line_number, 
                fill="gray", font=("Courier New", self.font_size)
            )
            i = self.text_area.index(f"{i}+1line")
    
    def on_text_modified(self, event=None):
        if self.text_area.edit_modified():
            self.modified = True
            # Perditeso titullin e tabit per te treguar se ka ndryshime
            tab_index = notebook.index(self.frame)
            current_text = notebook.tab(tab_index, "text")
            if not current_text.endswith("*"):
                notebook.tab(tab_index, text=current_text + "*")
            self.text_area.edit_modified(False)

# Krijo dritaren kryesore
root = tk.Tk()
root.title("Nullsec8 Editor")

# Perdor ngjyrat e ruajtura nga skedari
text_color, bg_color, current_font_size = load_colors()

# Ndrysho fontin dhe ngjyrat per te krijuar atmosferen e nje terminali
root.config(bg=bg_color)

# Notebook per tabs
notebook = ttk.Notebook(root)
notebook.pack(fill=tk.BOTH, expand=True)

# Dictionary per te mbajtur te dhenat e tabave
tabs = {}

# Funksioni per te krijuar nje tab te ri
def create_new_tab(title="New File"):
    tab_id = len(tabs) + 1
    editor_tab = EditorTab(notebook, text_color, bg_color, current_font_size)
    tabs[tab_id] = editor_tab
    notebook.add(editor_tab.frame, text=title)
    notebook.select(editor_tab.frame)
    return editor_tab

# Funksioni per te marre tabin aktual
def get_current_tab():
    current_tab_id = notebook.index(notebook.select())
    if current_tab_id >= 0:
        return list(tabs.values())[current_tab_id]
    return None

# Funksioni per te hapur nje skedar
def hap_skedar(event=None):
    try:
        file_path = filedialog.askopenfilename(
            defaultextension=".txt", 
            filetypes=[("All Files", "*.*"), ("Text files", "*.txt")]
        )
        if file_path:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Krijo nje tab te ri
            tab_title = file_path.split("/")[-1]  # Merr emrin e skedarit
            editor_tab = create_new_tab(tab_title)
            editor_tab.text_area.delete(1.0, tk.END)
            editor_tab.text_area.insert(tk.END, content)
            editor_tab.file_path = file_path
            editor_tab.modified = False
            editor_tab.update_line_numbers()
    except Exception as e:
        messagebox.showerror("Error", f"Gabim gjate hapjes se skedarit: {e}")

# Funksioni per te ruajtur nje skedar
def ruaj_skedar(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    
    try:
        # Nese skedari nuk ekziston, pyet per vendndodhjen e ruajtjes
        if not editor_tab.file_path:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt", 
                filetypes=[("All Files", "*.*"), ("Text files", "*.txt")]
            )
            if not file_path:
                return
            editor_tab.file_path = file_path
        
        with open(editor_tab.file_path, 'w', encoding='utf-8') as file:
            file.write(editor_tab.text_area.get(1.0, tk.END))
        
        editor_tab.modified = False
        # Largo * nga titulli i tabit
        tab_index = notebook.index(editor_tab.frame)
        current_text = notebook.tab(tab_index, "text")
        if current_text.endswith("*"):
            notebook.tab(tab_index, text=current_text.rstrip("*"))
        
    except Exception as e:
        messagebox.showerror("Error", f"Gabim gjate ruajtjes se skedarit: {e}")

# Funksioni per ruajtje si
def ruaj_si_skedar(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    
    try:
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt", 
            filetypes=[("All Files", "*.*"), ("Text files", "*.txt")]
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(editor_tab.text_area.get(1.0, tk.END))
            
            editor_tab.file_path = file_path
            editor_tab.modified = False
            
            # Perditeso titullin e tabit
            tab_title = file_path.split("/")[-1]
            tab_index = notebook.index(editor_tab.frame)
            notebook.tab(tab_index, text=tab_title)
            
    except Exception as e:
        messagebox.showerror("Error", f"Gabim gjate ruajtjes se skedarit: {e}")

# Funksioni per te ndryshuar ngjyren e tekstit
def ndrysho_ngjyren_tekstit(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    
    ngjyra = colorchooser.askcolor()[1]  # Merr ngjyren nga color picker
    if ngjyra:
        editor_tab.text_area.config(fg=ngjyra)
        editor_tab.text_area.config(insertbackground=ngjyra)
        editor_tab.text_color = ngjyra
        
        # Ruaj ne cilesimet globale
        global text_color
        text_color = ngjyra
        save_colors(text_color, bg_color, current_font_size)

# Funksioni per te ndryshuar ngjyren e fonit
def ndrysho_ngjyren_fonit(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    
    ngjyra = colorchooser.askcolor()[1]  # Merr ngjyren nga color picker
    if ngjyra:
        editor_tab.text_area.config(bg=ngjyra)
        editor_tab.line_numbers_canvas.config(bg=ngjyra)
        editor_tab.bg_color = ngjyra
        
        # Ruaj ne cilesimet globale
        global bg_color
        bg_color = ngjyra
        save_colors(text_color, bg_color, current_font_size)

# Funksioni per te hapur dritaren e ndihmes
def shfaq_help():
    help_text = (
        "Shortcuts:\n"
        "Ctrl+N - New file\n"
        "Ctrl+O - Open file\n"
        "Ctrl+S - Save file\n"
        "Ctrl+Shift+S - Save as\n"
        "Ctrl+W - Close tab\n"
        "Ctrl+T - Change text color\n"
        "Ctrl+B - Change background color\n"
        "Ctrl+F - Find text\n"
        "Ctrl++ - Zoom in\n"
        "Ctrl+- - Zoom out\n"   
        "Ctrl+Q - Exit\n"
    )
    messagebox.showinfo("Help", help_text)

# Funksioni per kerkimin ne tekst
def find_text(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    
    # Krijo nje dritare per kerkim
    find_window = tk.Toplevel(root)
    find_window.title("Find Text")
    find_window.transient(root)
    find_window.resizable(False, False)
    
    tk.Label(find_window, text="Find:").grid(row=0, column=0, padx=10, pady=5, sticky='e')
    search_entry = tk.Entry(find_window, width=40)
    search_entry.grid(row=0, column=1, padx=10, pady=5)
    search_entry.focus_set()
    
    def search():
        text_to_find = search_entry.get()
        if text_to_find:
            start_pos = editor_tab.text_area.search(text_to_find, "1.0", stopindex=tk.END)
            if start_pos:
                end_pos = f"{start_pos}+{len(text_to_find)}c"
                editor_tab.text_area.tag_remove("highlight", "1.0", tk.END)
                editor_tab.text_area.tag_add("highlight", start_pos, end_pos)
                editor_tab.text_area.tag_configure("highlight", background="yellow")
                editor_tab.text_area.mark_set("insert", end_pos)  # Vendos kursorin tek perputhja e pare
                editor_tab.text_area.see(start_pos)  # Shiko perputhjen
            else:
                messagebox.showinfo("Info", "Text not found.")
    
    tk.Button(find_window, text="Find", command=search).grid(row=1, column=0, columnspan=2, pady=5)

# Funksioni per zmadhimin e tekstit (zoom in)
def zoom_in(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    
    global current_font_size
    current_font_size += 1
    editor_tab.text_area.config(font=("Courier New", current_font_size))
    editor_tab.font_size = current_font_size
    editor_tab.update_line_numbers()
    save_colors(text_color, bg_color, current_font_size)

# Funksioni per zvogelimin e tekstit (zoom out)
def zoom_out(event=None):
    editor_tab = get_current_tab()
    if not editor_tab:
        return
    
    global current_font_size
    if current_font_size > 1:  # Sigurohemi qe madhesia te mos behet negative
        current_font_size -= 1
        editor_tab.text_area.config(font=("Courier New", current_font_size))
        editor_tab.font_size = current_font_size
        editor_tab.update_line_numbers()
        save_colors(text_color, bg_color, current_font_size)

# Funksioni per te krijuar nje skedar te ri
def new_file(event=None):
    create_new_tab()

# Funksioni per te mbyllur tabin aktual
def close_tab(event=None):
    current_tab = get_current_tab()
    if current_tab is None:
        return
    
    # Nëse ka lidhje liveshare, mbylle atë
    if hasattr(current_tab, 'liveshare_sock') and current_tab.liveshare_sock:
        try:
            current_tab.liveshare_sock.close()
        except Exception as e:
            print(f"Gabim gjatë mbylljes së liveshare socket: {e}")

    # Mbyll tab-in normalisht (kjo pjesë mund të jetë edhe më poshtë në funksionin origjinal)
    if current_tab.modified:
        result = messagebox.askyesnocancel(
            "Save Changes", 
            "Do you want to save changes before closing?"
        )
        if result is None:  # Cancel
            return
        if result:  # Yes
            ruaj_skedar()
    
    tab_index = notebook.index(notebook.select())
    notebook.forget(tab_index)
    
    # Largo nga dictionary
    tab_id = list(tabs.keys())[tab_index]
    del tabs[tab_id]


    # Kontrollo nese ka ndryshime te paruajtura
    if current_tab.modified:
        result = messagebox.askyesnocancel(
            "Save Changes", 
            "Do you want to save changes before closing?"
        )
        if result is None:  # Cancel
            return
        if result:  # Yes
            ruaj_skedar()
    
    # Gjej indeksin e tabit dhe fshije
    tab_index = notebook.index(notebook.select())
    notebook.forget(tab_index)
    
    # Largo nga dictionary
    tab_id = list(tabs.keys())[tab_index]
    del tabs[tab_id]

# Shto support per Undo/Redo
def undo(event=None):
    editor_tab = get_current_tab()
    if editor_tab:
        try:
            editor_tab.text_area.edit_undo()
        except tk.TclError:
            pass

def redo(event=None):
    editor_tab = get_current_tab()
    if editor_tab:
        try:
            editor_tab.text_area.edit_redo()
        except tk.TclError:
            pass

# Krijo nje menu
menu = tk.Menu(root)
root.config(menu=menu)

# Shto opsionet e menu-se
file_menu = tk.Menu(menu, tearoff=0)
menu.add_cascade(label="File", menu=file_menu)
file_menu.add_command(label="New", command=new_file, accelerator="Ctrl+N")
file_menu.add_command(label="Open", command=hap_skedar, accelerator="Ctrl+O")
file_menu.add_command(label="Save", command=ruaj_skedar, accelerator="Ctrl+S")
file_menu.add_command(label="Save As", command=ruaj_si_skedar, accelerator="Ctrl+Shift+S")
file_menu.add_separator()
file_menu.add_command(label="Close Tab", command=close_tab, accelerator="Ctrl+W")
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit, accelerator="Ctrl+Q")
file_menu.add_separator()
file_menu.add_command(label="Start LiveShare", command=lambda: start_liveshare_with_custom_server(get_current_tab()))

# Shto opsione per ngjyra
edit_menu = tk.Menu(menu, tearoff=0)
menu.add_cascade(label="Edit", menu=edit_menu)
edit_menu.add_command(label="Change Text Color", command=ndrysho_ngjyren_tekstit, accelerator="Ctrl+T")
edit_menu.add_command(label="Change Background Color", command=ndrysho_ngjyren_fonit, accelerator="Ctrl+B")
edit_menu.add_separator()
edit_menu.add_command(label="Undo", command=undo, accelerator="Ctrl+Z")
edit_menu.add_command(label="Redo", command=redo, accelerator="Ctrl+Y")
edit_menu.add_separator()
edit_menu.add_command(label="Find", command=find_text, accelerator="Ctrl+F")

# Shto opsione per zoom
view_menu = tk.Menu(menu, tearoff=0)
menu.add_cascade(label="View", menu=view_menu)
view_menu.add_command(label="Zoom In", command=zoom_in, accelerator="Ctrl++")
view_menu.add_command(label="Zoom Out", command=zoom_out, accelerator="Ctrl+-")

# Shto opsionin Help
help_menu = tk.Menu(menu, tearoff=0)
menu.add_cascade(label="Help", menu=help_menu)
help_menu.add_command(label="Help", command=shfaq_help)

# Perdorimi i shkurtesave te tastieres
root.bind("<Control-n>", new_file)  # Ctrl+N per skedar te ri
root.bind("<Control-o>", hap_skedar)  # Ctrl+O per te hapur nje skedar
root.bind("<Control-s>", ruaj_skedar)  # Ctrl+S per te ruajtur nje skedar
root.bind("<Control-Shift-S>", ruaj_si_skedar)  # Ctrl+Shift+S per Save As
root.bind("<Control-w>", close_tab)  # Ctrl+W per te mbyllur tabin
root.bind("<Control-t>", ndrysho_ngjyren_tekstit)  # Ctrl+T per te ndryshuar ngjyren e tekstit
root.bind("<Control-b>", ndrysho_ngjyren_fonit)  # Ctrl+B per te ndryshuar ngjyren e fonit
root.bind("<Control-f>", find_text)  # Ctrl+F per te hapur dritaren e kerkimit
root.bind("<Control-q>", lambda e: root.quit())  # Ctrl+Q per te mbyllur aplikacionin
root.bind("<Control-plus>", zoom_in)  # Ctrl++ per zmadhim
root.bind("<Control-minus>", zoom_out)  # Ctrl+- per zvogelim
root.bind("<Control-z>", undo)  # Ctrl+Z per Undo
root.bind("<Control-y>", redo)  # Ctrl+Y per Redo

# Starto aplikacionin me nje tab te zbrazet
create_new_tab()
autosave()
root.mainloop()