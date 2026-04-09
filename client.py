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

        self.text.bind("<KeyRelease>", self.schedule_send)

        self.connect()
        self.reconnect_loop()

    # ---------------- CONNECT ----------------
    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(("127.0.0.1", 9999))
            self.connected = True

            print("Connected to server")

            threading.Thread(target=self.listen, daemon=True).start()

        except:
            self.connected = False
            print("Connection failed")

    # ---------------- AUTO RECONNECT (SAFE) ----------------
    def reconnect_loop(self):
        if not self.connected:
            self.connect()

        self.text.after(2000, self.reconnect_loop)

    # ---------------- LISTEN ----------------
    def listen(self):
        while self.connected:
            try:
                data = self.sock.recv(8192)
                if not data:
                    break

                msg = json.loads(data.decode("utf-8"))

                if msg["type"] == "sync":
                    self.apply_text(msg["text"])

            except:
                break

        self.connected = False
        print("Disconnected")

    # ---------------- DEBOUNCED SEND ----------------
    def schedule_send(self, event=None):
        if self._job:
            self.text.after_cancel(self._job)

        self._job = self.text.after(300, self.send)

    def send(self):
        if not self.connected:
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

            self.sock.sendall(json.dumps(msg).encode("utf-8"))

        except:
            self.connected = False
            print("Send failed (disconnect)")

    # ---------------- APPLY REMOTE TEXT ----------------
    def apply_text(self, text):
        current = self.text.get("1.0", "end-1c")

        if current != text:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", text)


# ---------------- SIMPLE UI ----------------

root = tk.Tk()
root.title("LiveShare Stable")

text = tk.Text(root, font=("Consolas", 12))
text.pack(fill=tk.BOTH, expand=True)

client = LiveShareClient(text)

root.mainloop()