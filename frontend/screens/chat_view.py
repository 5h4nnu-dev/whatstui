import logging
from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Input, Label, Static, ListView, ListItem, Footer
from textual.binding import Binding
from textual import work


logger = logging.getLogger(__name__)


class ChatItem(ListItem):
    def __init__(self, chat_data: dict) -> None:
        super().__init__()
        self.chat_data = chat_data

    def compose(self) -> ComposeResult:
        name = escape(self.chat_data.get("name", "Unknown"))
        last_msg = escape(self.chat_data.get("lastMessage", "")[:50])
        unread = self.chat_data.get("unreadCount", 0)

        unread_badge = f" [{unread}]" if unread else ""
        yield Label(f"[bold]{name}[/bold]{unread_badge}", classes="chat-name")
        yield Label(f"  {last_msg}", classes="chat-last-msg")


class MessageBubble(Static):
    def __init__(self, msg_data: dict) -> None:
        super().__init__()
        self.msg_data = msg_data

    def render(self) -> str:
        body = escape(self.msg_data.get("body", ""))
        ts = self.msg_data.get("timestamp", 0)
        from_me = self.msg_data.get("fromMe", False)
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
        prefix = "You:" if from_me else "Them:"
        return f"{prefix} {body}  [dim]{time_str}[/dim]"

    def on_mount(self) -> None:
        border_style = "green" if self.msg_data.get("fromMe") else "white"
        self.styles.border = ("rounded", border_style)
        self.styles.margin = (0, 0, 0, 0)
        self.styles.padding = (0, 1)
        self.styles.width = "80%"
        if self.msg_data.get("fromMe"):
            self.add_class("outgoing")


class ChatViewScreen(Screen):
    CSS = """
    ChatViewScreen {
        background: #0b141a;
    }

    #sidebar {
        width: 30;
        border-right: solid #1f2c33;
        background: #0b141a;
    }

    #sidebar-title {
        color: #aebac1;
        text-style: bold;
        padding: 1 2;
        height: 3;
    }

    #chat-list {
        height: 1fr;
    }

    ChatItem {
        padding: 1 2;
        border-bottom: solid #1f2c33;
        height: 3;
    }

    ChatItem:hover {
        background: #1f2c33;
    }

    ChatItem > Label.chat-name {
        color: #e9edef;
    }

    ChatItem > Label.chat-last-msg {
        color: #8696a0;
    }

    #chat-area {
        height: 1fr;
    }

    #no-chat-selected {
        height: 100%;
        content-align: center middle;
        color: #8696a0;
    }

    #message-container {
        height: 1fr;
        padding: 1;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #input-area {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: #111b21;
    }

    #message-input {
        width: 1fr;
    }

    Input {
        background: #1f2c33;
        color: #e9edef;
        border: none;
    }

    Input:focus {
        border: none;
    }

    MessageBubble.outgoing {
        margin-left: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "focus_chat_list", "Chats"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Chats", id="sidebar-title")
                yield ListView(id="chat-list")
            with Vertical(id="chat-area"):
                yield Static("Select a chat to start messaging", id="no-chat-selected")
                yield ScrollableContainer(id="message-container")
                with Horizontal(id="input-area"):
                    yield Input(placeholder="Type a message...", id="message-input")
        yield Footer()

    def on_mount(self) -> None:
        self.load_chats()

    @work
    async def load_chats(self) -> None:
        try:
            chats = await self.app.wa.get_chats()
            chat_list = self.query_one("#chat-list", ListView)
            await chat_list.clear()
            await chat_list.extend(ChatItem(chat) for chat in chats)
        except Exception:
            logger.exception("Failed to load chats")
            self.notify("Could not load chats - see log", severity="error")

    def on_list_view_selected(self, event) -> None:
        item = event.item
        if isinstance(item, ChatItem):
            chat_id = item.chat_data.get("id") or item.chat_data.get("name")
            if chat_id:
                self.load_messages(chat_id)

    @work
    async def load_messages(self, chat_id: str) -> None:
        self.app.active_chat_id = chat_id
        messages = await self.app.wa.get_messages(chat_id)
        msg_container = self.query_one("#message-container", ScrollableContainer)
        await msg_container.remove_children()
        self.query_one("#no-chat-selected", Static).display = False
        if messages:
            await msg_container.mount(*(MessageBubble(msg) for msg in messages))
        msg_container.scroll_end(animate=False)
        self.query_one("#message-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value
        self.query_one("#message-input", Input).value = ""
        self._send_message(message)

    @work
    async def _send_message(self, msg: str) -> None:
        msg = msg.strip()
        chat_id = self.app.active_chat_id
        if not msg or not chat_id:
            return
        sent = await self.app.wa.send_message(chat_id, msg)
        if not sent:
            self.notify("Message was not sent - see log", severity="error")
            return
        msg_data = {
            "body": msg,
            "fromMe": True,
            "timestamp": int(datetime.now().timestamp()),
        }
        msg_container = self.query_one("#message-container", ScrollableContainer)
        await msg_container.mount(MessageBubble(msg_data))
        msg_container.scroll_end(animate=False)

    def action_focus_chat_list(self) -> None:
        self.query_one("#chat-list", ListView).focus()

    def on_new_message(self, msg_data: dict) -> None:
        try:
            chat_id = msg_data.get("chatId", "")
            if chat_id != self.app.active_chat_id:
                return
            msg_container = self.query_one("#message-container", ScrollableContainer)
            self.query_one("#no-chat-selected", Static).display = False
            msg_container.mount(MessageBubble(msg_data))
            self.call_later(msg_container.scroll_end, animate=False)
        except Exception:
            logger.exception("Failed to display incoming message")
