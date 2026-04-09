import socket
import threading
import json

clients = set()
clients_lock = threading.Lock()


def _remove_client(conn):
    with clients_lock:
        clients.discard(conn)
    try:
        conn.close()
    except OSError:
        pass


def broadcast(msg, sender=None):
    payload = (json.dumps(msg) + "\n").encode("utf-8")

    with clients_lock:
        recipients = [c for c in clients if c != sender]

    for c in recipients:
        try:
            c.sendall(payload)
        except OSError:
            _remove_client(c)


def handle_client(conn):
    with clients_lock:
        clients.add(conn)
    print("Client connected:", conn.getpeername())
    recv_buffer = ""

    while True:
        try:
            data = conn.recv(8192)
            if not data:
                break

            recv_buffer += data.decode("utf-8")

            while "\n" in recv_buffer:
                line, recv_buffer = recv_buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                broadcast(msg, conn)

        except OSError:
            break

    _remove_client(conn)
    print("Client disconnected")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", 9999))
server.listen()

print("LiveShare server running on port 9999")

while True:
    conn, addr = server.accept()
    threading.Thread(target=handle_client, args=(conn,), daemon=True).start()