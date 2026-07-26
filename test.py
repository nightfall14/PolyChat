#!/usr/bin/env python
import socket
import struct

HOST = "127.0.0.1"  # The server's hostname or IP address
PORT = 9034 # The port used by the server
MSG_CHAT = 1
MSG_JOIN = 2

def send_frame(soc: socket.socket, msg_type: int, payload: bytes) -> None:
   header = struct.pack("!BI", msg_type, len(payload))
   soc.sendall(header + payload)

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        usr = "nightfall"
        content = """Step 3 is done.
               You now have a working real-time chat app with usernames, join/leave notifications, and proper binary framing. That's a genuinely solid foundation.
               Where you are
               Step 1 — framing — done. Step 2 — Python threaded client — done. Step 3 — usernames and client state — done. Step 4 — file transfer — next. Step 5 — epoll upgrade — after that.
               Before moving to file transfer
               Do one quick thing — run your rapid fire test. Write a small Python script that connects, sends a username, then sends 10 messages with zero delay. Verify the server handles all 10 correctly without crashing or merging. This confirms your framing is solid under real load before you add file transfer complexity on top of it.
               If that passes cleanly, we start file transfer. Ready?"""
        send_frame(s, MSG_JOIN, usr.encode('utf-8'))
        for i in range(10):
           send_frame(s, MSG_CHAT, (content+str(i)).encode('utf-8')) 

if __name__ == "__main__":
    main()
