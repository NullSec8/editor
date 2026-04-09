import tkinter as tk
import socket
import threading
import json

class LiveShareClient:
    def __init__(self, text_widget):
        self.text = text_widget

        self.sock = None
        self.connected = False

        self.last_sent = ""
        self._job = None
        self._recv_buffer = ""

        self.text.bind("<KeyRelease>", self.schedule_send)

        self.connect()
        self.reconnect_loop()

    # ---------------- CONNECT ----------------
    def connect(self):
        new_sock = None
        try:
            self._safe_close_socket()
            new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_sock.connect(("127.0.0.1", 9999))
            self.sock = new_sock
            self._recv_buffer = ""
            self.connected = True

            print("Connected to server")

            threading.Thread(target=self.listen, args=(new_sock,), daemon=True).start()

        except Exception:
            self.connected = False
            if new_sock:
                self._close_socket(new_sock)
            if self.sock is new_sock:
                self.sock = None
            print("Connection failed")

    # ---------------- AUTO RECONNECT (SAFE) ----------------
    def reconnect_loop(self):
        if not self.connected:
            self.connect()

        self.text.after(2000, self.reconnect_loop)

    # ---------------- LISTEN ----------------
    def listen(self, listen_sock):
        while self.connected:
            try:
                data = listen_sock.recv(8192)
                if not data:
                    break

                self._recv_buffer += data.decode("utf-8")

                while "\n" in self._recv_buffer:
                    line, self._recv_buffer = self._recv_buffer.split("\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if msg.get("type") == "sync":
                        # Tkinter UI updates must happen on the main thread.
                        self.text.after(0, self.apply_text, msg.get("text", ""))

            except Exception:
                break

        if self.sock is listen_sock:
            self.connected = False
            self.sock = None
        self._close_socket(listen_sock)
        print("Disconnected")

    # ---------------- DEBOUNCED SEND ----------------
    def schedule_send(self, event=None):
        if self._job:
            self.text.after_cancel(self._job)

        self._job = self.text.after(300, self.send)

    def send(self):
        if not self.connected:
            return

        sock = self.sock
        if not sock:
            self.connected = False
            return

        content = self.text.get("1.0", "end-1c")

        if content == self.last_sent:
            return

        self.last_sent = content

        try:
            msg = {
                "type": "sync",
                "text": content
            }

            sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))

        except Exception:
            if self.sock is sock:
                self.connected = False
                self._safe_close_socket()
            print("Send failed (disconnect)")

    # ---------------- APPLY REMOTE TEXT ----------------
    def apply_text(self, text):
        current = self.text.get("1.0", "end-1c")

        if current != text:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", text)

    def _close_socket(self, sock):
        if sock:
            try:
                sock.close()
            except OSError:
                pass

    def _safe_close_socket(self):
        if self.sock:
            self._close_socket(self.sock)
            self.sock = None


# ---------------- SIMPLE UI ----------------

root = tk.Tk()
root.title("LiveShare Stable")

text = tk.Text(root, font=("Consolas", 12))
text.pack(fill=tk.BOTH, expand=True)

client = LiveShareClient(text)

root.mainloop()