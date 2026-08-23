#!/usr/bin/env python
from ..backend.network import Client
import time
from enum import IntEnum
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.message import Message
from pathlib import Path
from textual.screen import Screen
from textual.validation import Length, Regex

# from textual.worker import Worker
from textual import work, on
from textual.widgets import (
    RichLog,
    Input,
    Header,
    Footer,
    Label,
    ProgressBar,
    DirectoryTree,
)

# HOST = "20.2.196.123"  # The server's hostname or IP address
HOST = "127.0.0.1"
PORT = 9034  # The port used by the server
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


class MsgSend(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
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


class PromptUsername(Screen[str | None]):
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()

    BINDINGS = [("escape", "quit", "Quit Application")]

    CSS = """
    Input {
        margin: 1 1;
    }
    Label {
        margin: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(self.text)
        yield Input(
            placeholder="Enter the username...",
            max_length=39,
            validators=[
                Length(minimum=1, failure_description="Username cannot be empty!"),
                Regex(
                    regex=r"^[a-zA-Z0-9_-]*$",
                    failure_description="Only letters, numbers, dashes, and underscores allowed!",
                ),
            ],
            id="usrnm",
        )

    def action_quit(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#usrnm")
    def handle_input_submitted(self, event: Input.Submitted) -> None:
        if event.validation_result.is_valid and event.validation_result:
            self.dismiss(event.value.strip())
            return

        if event.validation_result and not event.validation_result.is_valid:
            for failure in event.validation_result.failures:
                # This will pop up the specific failure_description we wrote earlier!
                self.post_message(Notification(failure.description, severity="error"))


class DemoApp(App):
    # This tells Textual to handle Ctrl+C cleanly
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("ctrl+q", "quit", "Quit App"),
    ]

    CSS_PATH = "chat.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", markup=True)
        yield ProgressBar(id="file-progess", total=100, show_eta=False)
        yield Input(placeholder="Type a message...", id="chat-input")
        yield Footer()

    @work
    async def on_mount(self) -> None:

        # ---> NEW: Hide the progress bar initially <---
        try:
            self.query_one(ProgressBar).display = False
        except NoMatches:
            pass

        # 1. Initialize the network engine and pass the callback handler
        self.usrnm = await self.push_screen_wait(
            PromptUsername(
                "Enter the username...(Username should be 1-39 characters, and only these characters are allowed a-z, A-Z, 0-9, _,-"
            )
        )

        if self.usrnm is None:
            self.exit()
            return

        # If we made it here, they provided a valid string!
        self.notify(f"Welcome, {self.usrnm}!")
        self.client = Client(
            HOST, PORT, self.handle_network_event, self.handle_progress_update
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
        recipient = await self.push_screen_wait(
            PromptUsername(
                'Enter the username of the person you want to send the file (or type "all"):'
            )
        )

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

    @on(Input.Submitted, "#chat-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return
        self.send(msg)
        event.input.clear()

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
                self.post_message(MsgSend(msg))

    # These also go INSIDE your Textual App class
    @on(ChatReceived)
    def on_chat_received(self, event: ChatReceived) -> None:
        time_now = time.strftime("%H:%M", time.gmtime())
        chat_log = self.query_one(RichLog)
        chat_log.write(
            f"[dim italic][{time_now}][/dim italic] [magenta]{event.username}:[/magenta]{event.text}"
        )

    @on(MsgSend)
    def on_msg_send(self, event: MsgSend) -> None:
        # ---> NEW: Print your own message to the log! <---
        time_now = time.strftime("%H:%M", time.gmtime())
        chat_log = self.query_one(RichLog)
        chat_log.write(
            f"[dim italic][{time_now}][/dim italic] [bold blue]{self.usrnm}(YOU):[/bold blue] {event.text}"
        )

    @on(Notification)
    def on_join_notification(self, event: Notification) -> None:
        chat_log = self.query_one(RichLog)
        # Using Rich text markup to make system notifications dim and italic
        chat_log.write(f"[dim italic]{event.body}[/dim italic]")

    @on(FileReceived)
    def on_file_received(self, event: FileReceived) -> None:
        self.notify(event.status_msg, timeout=10)


def main():
    app = DemoApp()
    exit_msg = app.run()
    if exit_msg:
        print(exit_msg)


if __name__ == "__main__":
    main()
