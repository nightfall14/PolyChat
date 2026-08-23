import socket
from .protocol import MsgTyp, send_frame, recv_frame
import hashlib
from pathlib import Path
import struct
import os


class Client:
    def __init__(self, host, port, on_event_callback) -> None:
        self.host = host
        self.port = port
        self.on_event = on_event_callback
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, username: str):
        self.s.connect((self.host, self.port))
        send_frame(self.s, MsgTyp.MSG_JOIN, username.encode("utf-8"))

    def disconnect(self):
        try:
            # Instantly breaks the blocking soc.recv() in your worker thread
            self.s.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Ignore errors if the server already disconnected
            pass
        finally:
            self.s.close()

    def send_message(self, text: str):
        send_frame(self.s, MsgTyp.MSG_CHAT, text.encode("utf-8"))

    def listen(self):
        storage_path = str(Path.home() / "chat/downloads/") + "/"
        current_file = None
        current_hasher = None
        f_name = ""

        while True:
            try:
                msg_type, data = recv_frame(self.s)

                match msg_type:
                    case MsgTyp.MSG_CHAT | MsgTyp.MSG_JOIN:
                        # Standard text messages get passed directly to the UI
                        self.on_event(msg_type, data.decode("utf-8"))

                    case MsgTyp.MSG_FILE_START:
                        f_name = data[48:].decode("utf-8")
                        full_path = storage_path + f_name
                        os.makedirs(storage_path, exist_ok=True)
                        current_file = open(full_path, "wb")
                        current_hasher = hashlib.sha256()

                        # Optional: Tell the UI a file is incoming
                        self.on_event(MsgTyp.MSG_FILE_START, f"Downloading {f_name}...")

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

                                # Tell the UI the file finished successfully!
                                success_msg = f"File {f_name} received successfully!"
                                self.on_event(MsgTyp.MSG_FILE_END, success_msg)
                            else:
                                error_msg = f"Error: File {f_name} corrupted."
                                self.on_event(MsgTyp.MSG_FILE_END, error_msg)

            except (ConnectionError, OSError):
                self.on_event(MsgTyp.MSG_JOIN, "Error: Disconnected from server.")
                break

    def send_file(self, fpath, recipient):
        fpath = Path(fpath)
        self.current_f_name = os.path.basename(fpath)
        f_size = os.stat(fpath).st_size

        recipient_in_bytes = recipient.encode("utf-8").ljust(40, b"\x00")
        filename_in_bytes = self.current_f_name.encode("utf-8")
        payload = struct.pack("!Q", f_size) + recipient_in_bytes + filename_in_bytes
        send_frame(self.s, MsgTyp.MSG_FILE_START, payload)

        chunk_size = 65536
        self.current_hasher = hashlib.sha256()

        with open(fpath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                self.current_hasher.update(chunk)
                send_frame(self.s, MsgTyp.MSG_FILE_CHUNK, chunk)

        checksum = self.current_hasher.hexdigest()
        send_frame(self.s, MsgTyp.MSG_FILE_END, checksum.encode("utf-8"))
