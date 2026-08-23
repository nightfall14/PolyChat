from enum import IntEnum
import socket
import struct


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
