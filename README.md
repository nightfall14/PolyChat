# PolyChat
A real-time multi-client chat and file transfer application built from scratch.
C server, Python client, custom binary protocol over TCP.

## What it does

- Real-time chat between multiple clients simultaneously
- File transfer with SHA256 checksum verification
- Username system with join and leave notifications
- Transfers files of any size — tested with a 4.6GB ISO at ~75MB/s over local WiFi
- Deployed on Azure — accessible from anywhere over the internet

## Architecture

```
Python Client  <-->  C Server (epoll)  <-->  Python Client
                         |
                   Custom Binary Protocol
                   5-byte frame header
                   (1 byte type + 4 byte length)

```
The server is single-process, event-driven using Linux epoll. It handles
all clients in one thread with no blocking — epoll notifies the server only
when a client has data ready, achieving O(1) event dispatch regardless of
client count.

## Technical highlights

- **Custom binary framing protocol** — every message is prefixed with a
  5-byte header (1 byte message type + 4 byte payload length in network byte
  order). This solves TCP's stream boundary problem and handles partial reads
  correctly under all network conditions.
- **epoll-based event loop** — upgraded from poll() to epoll() for O(1)
  scalability. Kernel maintains the interest list; only ready file descriptors
  are returned per epoll_wait call.
- **File transfer** — chunked 64KB reads, raw binary over the wire (no base64
  encoding), SHA256 checksum verified on receipt. Successfully transferred a
  4.6GB Kali Linux ISO intact.
- **Dynamic dispatch** — server routes messages by type (MSG_CHAT, MSG_JOIN,
  MSG_FILE_START, MSG_FILE_CHUNK, MSG_FILE_END). File transfers can target a
  specific user or broadcast to all connected clients.
- **Python threading** — two-thread client (send thread blocks on keyboard
  input, recv thread blocks on socket). TCP socket is safe to read and write
  from separate threads simultaneously.

## Message types

| Type           | Value | Description                                          |
|----------------|-------|------------------------------------------------------|
| MSG_CHAT       | 1     | Chat message broadcast                               |
| MSG_JOIN       | 2     | Username registration / join-leave notification      |
| MSG_FILE_START | 5     | File transfer initiation (filename, size, recipient) |
| MSG_FILE_CHUNK | 6     | Raw file bytes (64KB chunks)                         |
| MSG_FILE_END   | 7     | Transfer complete + SHA256 checksum                  |

## How to run
**Git**
```bash
git clone https://github.com/nightfall14/PolyChat
cd PolyChat
```

**Server**
```bash
make run-server
```

**Client**
```bash
make run-client
```

**Test**
```bash
make test //Tests that 10 rapid messages arrive as separate clean frames.
```

**Make commands**
```
make              # builds the server binary
make run-server   # builds and runs the server
make run-client   # runs the Python client
make test         # runs the framing test
make clean        # deletes compiled binary
```

## What I learned building this

- TCP socket programming in C from scratch — socket(), bind(), listen(), accept(), send(), recv().
- Why TCP is a byte stream and not a message protocol — and how to fix it with length-prefix framing.
- Network byte order and htonl/ntohl/be64toh.
- poll() vs epoll() — the O(n) vs O(1) distinction and when it matters.
- Dynamic memory management in C for variable-length network payloads.
- Python threading model — why two threads work for a chat client and what the GIL actually means.
- Python struct module for binary serialization matching a C wire format
- SHA256 checksums for file integrity verification.
- Cloud deployment — Azure VM setup, NSG port rules, SSH key authentication, SCP.

## Deployment

Currently running on Microsoft Azure (East Asia region).
Connect by setting `HOST` in client.py to the server's public IP.

## Known limitations

- Single-threaded server — a client that sends a partial frame header and
  stops will block recv_exact() and freeze the server (DoS vulnerability).
  Fix requires non-blocking sockets with per-client receive buffers.
- Terminal display — input prompt and incoming messages share the same
  terminal line. A proper TUI (Textual) is planned.
- No message history persistence — all messages exist only in memory.
  Adding MySQL for persistence is planned.
