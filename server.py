import socket
import threading
import json

clients = set()

def broadcast(msg, sender=None):
    dead = set()

    for c in clients:
        if c == sender:
            continue
        try:
            c.sendall(json.dumps(msg).encode("utf-8"))
        except:
            dead.add(c)

    for d in dead:
        clients.discard(d)
        try:
            d.close()
        except:
            pass

def handle_client(conn):
    clients.add(conn)
    print("Client connected:", conn.getpeername())

    while True:
        try:
            data = conn.recv(8192)
            if not data:
                break

            msg = json.loads(data.decode("utf-8"))
            broadcast(msg, conn)

        except:
            break

    clients.discard(conn)
    try:
        conn.close()
    except:
        pass

    print("Client disconnected")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", 9999))
server.listen()

print("LiveShare server running on port 9999")

while True:
    conn, addr = server.accept()
    threading.Thread(target=handle_client, args=(conn,), daemon=True).start()