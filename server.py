import json
import socket
import threading

# Track each client socket and its current room.
clients = {}
clients_lock = threading.Lock()


def _remove_client(conn):
    with clients_lock:
        clients.pop(conn, None)
    try:
        conn.close()
    except OSError:
        pass


def _set_client_room(conn, room):
    with clients_lock:
        if conn in clients:
            clients[conn] = room


def _get_client_room(conn):
    with clients_lock:
        return clients.get(conn, "default")


def broadcast(msg, sender=None):
    room = msg.get("room", "default")
    payload = (json.dumps(msg) + "\n").encode("utf-8")

    with clients_lock:
        recipients = [c for c, c_room in clients.items() if c != sender and c_room == room]

    for c in recipients:
        try:
            c.sendall(payload)
        except OSError:
            _remove_client(c)


def handle_client(conn):
    with clients_lock:
        clients[conn] = "default"
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

                msg_type = msg.get("type")
                if msg_type == "join":
                    room = msg.get("room", "default")
                    _set_client_room(conn, room)
                    continue

                if msg_type != "sync":
                    continue

                if "room" not in msg:
                    msg["room"] = _get_client_room(conn)
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