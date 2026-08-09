#!/usr/bin/env python
import socket
import hashlib
import struct
import threading
from pathlib import Path
import os
from enum import IntEnum

# HOST = "20.2.196.123"  # The server's hostname or IP address
HOST = "127.0.0.1"
PORT = 9034  # The port used by the server


class MsgTyp(IntEnum):
    MSG_CHAT = 1
    MSG_JOIN = 2
    MSG_FILE_START = 5
    MSG_FILE_CHUNK = 6
    MSG_FILE_END = 7


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


def recv_frame(soc: socket.socket) -> tuple[int, bytes]:
    msg_type: int
    length: int
    msg_type, length = struct.unpack("!BI", recv_exact(soc, 5))
    return msg_type, recv_exact(soc, length)


def strt_file_trans(soc: socket.socket):
    fpath = Path(input("Enter the file path:\n"))

    if not fpath.exists() or not fpath.is_file():
        print("Path does not exist! Retry!")
        return

    recipient = input(
        'Enter the recipients username(or if you want to send it to all, enter "all"):\n'
    )

    while len(recipient) > 39 or len(recipient) == 0:
        print("USERNAME SHOULD BE 1-39 CHARACTERS!!")
        recipient = input(
            'Enter the recipients username(or if you want to send it to all, enter "all"):\n'
        )

    recipient_in_bytes = recipient.encode("utf-8").ljust(40, b"\x00")
    filename = os.path.basename(fpath)
    filename_in_bytes = filename.encode("utf-8")
    f_size = os.stat(fpath).st_size
    payload = struct.pack("!Q", f_size) + recipient_in_bytes + filename_in_bytes

    send_frame(soc, MsgTyp.MSG_FILE_START, payload)

    chunk_size = 65536
    hasher = hashlib.sha256()

    with open(fpath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            send_frame(soc, MsgTyp.MSG_FILE_CHUNK, chunk)

    checksum = hasher.hexdigest()
    send_frame(soc, MsgTyp.MSG_FILE_END, checksum.encode("utf-8"))


def send(
    soc: socket.socket,
):
    while True:
        msg = input("YOU>")
        if not msg.strip():
            continue
        if msg == "/ex":
            break
        elif msg == "/file":
            strt_file_trans(soc)
            continue
        send_frame(soc, MsgTyp.MSG_CHAT, msg.encode("utf-8"))


def recv(s: socket.socket):
    current_file = None
    current_hasher = None
    home_dir = Path.home()
    f_path = f"{home_dir}/chat/downloads/"

    while True:
        try:
            msg_type, data = recv_frame(s)
            msg_type = MsgTyp(msg_type)
            match msg_type:
                case MsgTyp.MSG_CHAT:
                    print(f"received: {data.decode('utf-8')}")

                case MsgTyp.MSG_JOIN:
                    print(data.decode("utf-8"))

                case MsgTyp.MSG_FILE_START:
                    f_name = data[48:].decode("utf-8")
                    full_path = f_path + f_name
                    os.makedirs(f_path, exist_ok=True)
                    current_file = open(full_path, "wb")
                    current_hasher = hashlib.sha256()

                case MsgTyp.MSG_FILE_CHUNK:
                    if current_file and current_hasher:
                        _ = current_file.write(data)
                        current_hasher.update(data)

                case MsgTyp.MSG_FILE_END:
                    if current_file and current_hasher:
                        if current_hasher.hexdigest() == data.decode("utf-8"):
                            current_file.close()
                            current_file = None
                            current_hasher = None
                            print("File recieved successfully")
                        else:
                            print("File corrupted - checksum mismatch")

        except ConnectionError:
            print("disconnect")
            break


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        send_thread = threading.Thread(target=send, args=(s,), daemon=True)
        recv_thread = threading.Thread(target=recv, args=(s,), daemon=True)
        threads = [send_thread, recv_thread]
        usrname = input("Enter UserName: ")
        while len(usrname) > 39 or len(usrname) == 0:
            print("USERNAME SHOULD BE 1-39 CHARACTERS!!")
            usrname = input("Enter UserName: ")
        send_frame(s, MsgTyp.MSG_JOIN, usrname.encode("utf-8"))
        for t in threads:
            t.start()
        send_thread.join()


if __name__ == "__main__":
    main()
