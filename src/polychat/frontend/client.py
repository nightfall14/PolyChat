#!/usr/bin/env python
import argparse
import subprocess
import sys
import hashlib
from polychat.backend.network import Client
import time
from enum import IntEnum
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.message import Message
from textual.events import Key
from textual.widgets import TextArea
from textual.binding import Binding
from pathlib import Path
from textual.screen import Screen
from textual.validation import Length, Regex
from textual.containers import Vertical, Horizontal

# from textual.worker import Worker
from textual import work, on
from textual.widgets import (
    RichLog,
    Button,
    Input,
    Header,
    ListView,
    ListItem,
    Footer,
    Label,
    ProgressBar,
    DirectoryTree,
)

# HOST = "20.2.196.123"  # The server's hostname or IP address
# HOME = Path.home()
# storage_path = f"{HOME}/chat/downloads"


class MsgTyp(IntEnum):
    MSG_CHAT = 1
    MSG_JOIN = 2
    MSG_FILE_START = 5
    MSG_FILE_CHUNK = 6
    MSG_FILE_END = 7


class ChatReceived(Message):
    def __init__(self, username: str, text: str) -> None:
        super().__init__()
        self.username = username
        self.text = text


class FileReceived(Message):
    def __init__(self, status_msg: str) -> None:
        super().__init__()
        self.status_msg = status_msg


class Notification(Message):
    def __init__(self, body: str, severity: str) -> None:
        super().__init__()
        self.body = body
        self.severity = severity


class FilePickerModal(Screen):
    """A modal screen to pick a file."""

    BINDINGS = [("escape", "quit", "Quit Application")]

    def compose(self) -> ComposeResult:
        yield DirectoryTree("~/")

    @on(DirectoryTree.FileSelected)
    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        # 1. Stop if we already successfully picked a file
        if getattr(self, "_dismissed", False):
            return

        # 2. Expand the '~' to the real path
        clean_path = Path(event.path).expanduser().resolve()

        # 3. ONLY react if it's an actual file.
        # If it's a folder (or a ghost Enter key), do absolutely nothing!
        if clean_path.is_file():
            self._dismissed = True
            self.dismiss(str(clean_path))

    def action_quit(self) -> None:
        self.dismiss(None)


class LoginScreen(Screen[str | None]):
    """A centered, modern login card for username authentication."""

    CSS_PATH = "loginScreen.tcss"

    def compose(self) -> ComposeResult:
        with Vertical(id="login-card"):
            yield Label("POLYCHAT", id="title")
            yield Label("Enter a username to join the network", id="subtitle")
            yield Input(
                placeholder="Username (e.g. Alice_99)",
                id="usrnm",
                max_length=39,
                validators=[
                    Length(
                        minimum=1,
                        failure_description="Username cannot be empty!",
                    ),
                    Regex(
                        regex=r"^[a-zA-Z0-9_-]*$",
                        failure_description="Allowed characters: a-z, A-Z, 0-9, _, -",
                    ),
                ],
            )
            yield Label("", id="error-label")
            yield Button("Connect", variant="success", id="submit-btn")

    def _submit(self) -> None:
        inp = self.query_one("#usrnm", Input)
        error_lbl = self.query_one("#error-label", Label)
        res = inp.validate(inp.value)

        if res and res.is_valid:
            error_lbl.display = False
            self.dismiss(inp.value.strip())
        elif res and res.failures:
            error_lbl.update(res.failures[0].description)
            error_lbl.display = True

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit-btn":
            self._submit()


class ChatInput(TextArea):
    """A multiline text area tailored for chat applications."""

    # We keep these bindings so they display nicely in your Footer UI
    BINDINGS = [
        Binding("enter", "submit_message", "Send", show=True),
        Binding("shift+enter", "insert_newline", "New Line", show=True),
    ]

    class Submitted(Message):
        """Posted when the user presses Enter."""

        def __init__(self, input_control: "ChatInput", text: str) -> None:
            super().__init__()
            self._control = input_control
            self.text = text

        @property
        def control(self) -> "ChatInput":
            return self._control

    def _on_key(self, event: Key) -> None:
        """Intercept raw key presses before TextArea consumes them."""
        if event.key == "enter":
            self.action_submit_message()
            event.prevent_default()  # Stops the TextArea from writing a newline

        elif event.key == "shift+enter":
            self.action_insert_newline()
            event.prevent_default()

        else:
            # Let TextArea handle all other normal typing (letters, backspace, etc.)
            super()._on_key(event)

    def action_submit_message(self) -> None:
        """Triggered when Enter is pressed."""
        msg = self.text.strip()
        if msg:
            self.post_message(self.Submitted(self, msg))

        self.text = ""

    def action_insert_newline(self) -> None:
        """Triggered when Shift+Enter is pressed."""
        self.insert("\n")


DISCORD_PALETTE = [
    "#5865F2",  # Blurple
    "#57F287",  # Green
    "#FEE75C",  # Yellow
    "#EB459E",  # Fuchsia
    "#ED4245",  # Red
    "#00B0F4",  # Cyan
    "#9B59B6",  # Purple
    "#E67E22",  # Orange
    "#1ABC9C",  # Teal
]


def get_user_color(username: str) -> str:
    """Returns a deterministic hex color for a given username."""
    hash_val = int(hashlib.md5(username.encode("utf-8")).hexdigest(), 16)
    return DISCORD_PALETTE[hash_val % len(DISCORD_PALETTE)]


def add_discord_message(
    chat_log: RichLog,
    username: str,
    text: str,
    is_self: bool = False,
    badge: str | None = None,
) -> None:
    """Write a Discord-style message with crisp dark contrast and separated badges."""

    timestamp = time.strftime("%I:%M %p")
    user_color = get_user_color(username)
    initial = username[0].upper() if username else "?"

    # 1. AVATAR: Dark text (#111827) on user_color background removes the harsh white glare
    avatar = f"[bold #111827 on {user_color}] {initial} [/bold #111827 on {user_color}]"

    # 2. USERNAME: Bold colored text matching the user's avatar color
    username_markup = f"[bold {user_color}]{username}[/bold {user_color}]"

    # 3. BADGE: Anchored strictly AFTER username (never next to avatar)
    badge_markup = ""
    if badge:
        badge_markup = f" [bold #111827 on #3BA55D] {badge} [/bold #111827 on #3BA55D]"
    elif is_self:
        badge_markup = " [bold #111827 on #FEE75C] YOU [/bold #111827 on #FEE75C]"

    # 4. TIMESTAMP: Soft slate gray (#9CA3AF) instead of glaring white
    time_markup = f"[#9CA3AF]{timestamp}[/#9CA3AF]"

    # Header Assembly: [AVATAR]  Username [BADGE]  Timestamp
    header = f"{avatar}  {username_markup}{badge_markup}  {time_markup}"

    # Indented body aligns text cleanly under the username
    indented_body = "\n".join(f"      {line}" for line in text.split("\n"))

    chat_log.write(f"{header}\n{indented_body}\n")


class PolyChat(App):
    # This tells Textual to handle Ctrl+C cleanly
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("ctrl+q", "quit", "Quit App"),
        ("ctrl+f", "file_picker", "Open file picker"),
    ]

    CSS_PATH = "chat.tcss"

    def __init__(self, host, port) -> None:
        self.host = host
        self.port = port
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="room-body"):
            # Sidebar
            with Vertical(id="sidebar"):

                yield Label("ONLINE USERS", id="sidebar-title")
                yield ListView(
                    ListItem(Label("🟢 [bold]Alice[/bold]", classes="online-user")),
                    ListItem(Label("🟢 [bold]Bob[/bold]", classes="online-user")),
                    ListItem(Label("🟢 [bold]You[/bold]", classes="online-user")),
                    id="user-list",
                )

            # Chat Panel
            with Vertical(id="chat-main"):
                yield RichLog(id="chat-log", markup=True)
                yield ProgressBar(id="file-progress", total=100, show_eta=False)
                yield ChatInput(id="chat-input", show_line_numbers=False)
        yield Footer()

    def action_file_picker(self) -> None:
        self.trigger_file_trans()

    @work
    async def on_mount(self) -> None:
        # ---> NEW: Hide the progress bar initially <---
        try:
            self.query_one(ProgressBar).display = False
        except NoMatches:
            pass

        # 1. Initialize the network engine and pass the callback handler
        self.usrnm = await self.push_screen_wait(LoginScreen())

        if self.usrnm is None:
            self.exit()
            return

        # If we made it here, they provided a valid string!
        self.notify(f"Welcome, {self.usrnm}!")
        self.client = Client(
            self.host, self.port, self.handle_network_event, self.handle_progress_update
        )

        try:
            self.client.connect(self.usrnm)
        except ConnectionRefusedError:
            # 1. Notify the user visually
            self.notify("Server not yet started!", severity="error", timeout=10)

            # 2. Disable the chat input widget so they cannot type
            chat_box = self.query_one("#chat-input")
            chat_box.disabled = True
            chat_box.placeholder = "Disconnected."
            return

        # 2. Start the background listening thread
        self.run_network_worker()

    def on_unmount(self) -> None:
        # 1. Safely check if the client was ever created
        if hasattr(self, "client") and self.client is not None:
            # 2. Call disconnect() with the correct spelling
            self.client.disconnect()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )

    @work(exclusive=True, thread=True)
    def run_network_worker(self):
        self.client.listen()

    def handle_network_event(self, msg_type, data: str):
        """This acts as the bridge. The network calls this when data arrives."""
        try:
            match msg_type:
                case MsgTyp.MSG_CHAT:
                    usrname, text = data.split(":", 1)
                    self.post_message(ChatReceived(usrname, text))

                case MsgTyp.MSG_JOIN | MsgTyp.MSG_FILE_START:
                    if data.startswith("Error:"):
                        self.notify(data, timeout=10, severity="error")
                    else:
                        self.notify(data, timeout=10)

                case MsgTyp.MSG_FILE_END:
                    # Check if the backend sent us an error string!
                    if data.startswith("Error:"):
                        self.notify(data, timeout=10, severity="error")
                    else:
                        self.post_message(FileReceived(data))
        except Exception as e:
            # ---> NEW: If the worker crashes, print the error to the screen! <---
            self.notify(f"UI Error: {str(e)}", timeout=10, severity="error")

    def handle_progress_update(self, pct: float) -> None:
        def safe_update():
            try:
                # Find the progress bar and update its percentage (0 to 100)
                pb = self.query_one(ProgressBar)
                pb.update(progress=pct, total=100)
            except NoMatches:
                pass

        self.call_from_thread(safe_update)

    # ---> 1. Put the UI helpers here, as normal class methods <---
    def start_transfer_ui(self):
        try:
            pb = self.query_one(ProgressBar)
            pb.update(progress=0.0, total=100)
            pb.display = True
        except NoMatches:
            pass

    def end_transfer_ui(self):
        try:
            self.query_one(ProgressBar).display = False
        except NoMatches:
            pass

    # ---> 2. The UI Flow (Main Thread) <---
    @work
    async def trigger_file_trans(self):
        # Await the screen directly. DO NOT use call_from_thread here!
        fpath = await self.push_screen_wait(FilePickerModal())

        if not fpath:
            self.notify("File selection canceled", severity="warning")
            return

        # Await the screen directly. DO NOT use call_from_thread here!
        recipient = await self.push_screen_wait(LoginScreen())

        if not recipient:
            self.notify("File transfer canceled", severity="warning")
            return

        # Hand off the heavy lifting to the background thread!
        self.run_background_transfer(fpath, recipient)

    # ---> 3. The Network Flow (Background Thread) <---
    @work(exclusive=True, thread=True)
    def run_background_transfer(self, fpath: str, recipient: str):
        # 1. Show the bar (Must call back to the main thread to touch UI)
        self.app.call_from_thread(self.start_transfer_ui)

        # 2. Block and send the file over the network
        self.client.send_file(fpath, recipient)

        # 3. Hide the bar when finished
        self.app.call_from_thread(self.end_transfer_ui)
        self.app.call_from_thread(
            self.notify, f"File {Path(fpath).stem} transferred successfully!"
        )

    @work(exclusive=True, thread=True)
    def send(self, msg) -> None:
        match msg:
            case "/ex":
                self.call_from_thread(self.exit)
            case "/file":
                self.trigger_file_trans()
            # Send to the server
            case _:
                self.client.send_message(msg)

    @on(ChatInput.Submitted, "#chat-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        msg = event.text.strip()
        if not msg:
            return
        self.send(msg)
        chat_log = self.query_one(RichLog)
        add_discord_message(chat_log, self.usrnm, msg, is_self=True)

    # These also go INSIDE your Textual App class
    @on(ChatReceived)
    def on_chat_received(self, event: ChatReceived) -> None:
        chat_log = self.query_one(RichLog)
        add_discord_message(chat_log, event.username, event.text.strip(), is_self=False)

    @on(Notification)
    def on_join_notification(self, event: Notification) -> None:
        chat_log = self.query_one(RichLog)
        # Using Rich text markup to make system notifications dim and italic
        chat_log.write(f"[dim italic]{event.body}[/dim italic]")

    @on(FileReceived)
    def on_file_received(self, event: FileReceived) -> None:
        self.notify(event.status_msg, timeout=10)


def update_repository():
    """Checks for updates, pulls if necessary, and syncs dependencies."""
    print("🔍 Checking for updates...")
    try:
        # 1. Fetch the latest metadata from the remote repository (silent output)
        subprocess.run(["git", "fetch"], check=True, capture_output=True)

        # 2. Get the commit hashes for the local branch and the remote branch
        local_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()

        remote_hash = subprocess.run(
            ["git", "rev-parse", "@{u}"], check=True, capture_output=True, text=True
        ).stdout.strip()

        # 3. Compare them!
        if local_hash == remote_hash:
            print("✨ You are already on the latest version!")
            sys.exit(0)

        # 4. If they don't match, proceed with the update
        print("📥 New version found! Pulling changes...")
        subprocess.run(["git", "pull"], check=True)

        print("📦 Syncing dependencies with uv...")
        subprocess.run(["uv", "sync"], check=True)

        print("✅ Update complete! Please run the client again to use the new version.")
        sys.exit(0)

    except subprocess.CalledProcessError:
        print(
            "❌ Failed to check for updates. Make sure you are connected to the internet and inside a valid git repository.",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Launch the PolyChat terminal client.")

    # 1. Add the update flag (action="store_true" means it's a boolean True/False flag)
    parser.add_argument(
        "-U",
        "--update",
        action="store_true",
        help="Update PolyChat to the latest version from the repository",
    )

    # 2. Make host and port accept zero or one arguments (nargs="?")
    # This prevents argparse from crashing if the user ONLY types '-U'
    parser.add_argument(
        "host", nargs="?", help="The server IP address (e.g., 127.0.0.1)"
    )
    parser.add_argument(
        "port", nargs="?", type=int, help="The server port (e.g., 9034)"
    )

    args = parser.parse_args()

    # 3. Intercept the update command before doing anything else
    if args.update:
        update_repository()

    # 4. If we aren't updating, enforce that host and port MUST be provided
    if not args.host or not args.port:
        parser.error("The following arguments are required to connect: host, port")

    # 5. Proceed with normal execution
    HOST = args.host
    PORT = args.port

    app = PolyChat(HOST, PORT)  # Pass HOST and PORT if needed
    exit_msg = app.run()
    if exit_msg:
        print(exit_msg)


if __name__ == "__main__":
    main()
