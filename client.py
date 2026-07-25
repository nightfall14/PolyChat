#!/usr/bin/env python
import socket
import struct
import threading

HOST = "127.0.0.1"  # The server's hostname or IP address
PORT = 9034 # The port used by the server
MSG_CHAT = 1

def send_frame(soc: socket.socket, msg_type: int, payload: bytes) -> None:
   header = struct.pack("!BI", msg_type, len(payload))
   soc.sendall(header + payload)

def recv_exact(soc: socket.socket, n: int):
    data = bytearray()
    while len(data) < n:
        chunk = soc.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes are recieved")
        data.extend(chunk)
    return bytes(data)

def recv_frame(soc: socket.socket):
    msg_type, length= struct.unpack("!BI", recv_exact(soc, 5))
    return msg_type,recv_exact(soc, length)

def send(soc: socket.socket, ):
    while True:
        msg = input("YOU>")
        if msg == "/ex":
            break
        send_frame(soc, 1, msg.encode('utf-8'))

def recv(s: socket.socket):
    while True:
        try:
            msg_type, data = recv_frame(s)
            print("hello")
            if msg_type == MSG_CHAT:
                print(f"recived: {data.decode('utf-8')}")
        except ConnectionError:
            print("disconnect")
            break


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        send_thread = threading.Thread(target=send, args=(s,), daemon=True)
        recv_thread  = threading.Thread(target=recv, args=(s,), daemon=True)
        threads = [send_thread, recv_thread]
        for t in threads:
            t.start()
        send_thread.join()

if __name__ == "__main__":
    main()
