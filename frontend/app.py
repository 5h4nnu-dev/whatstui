import asyncio
import logging
import os
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.binding import Binding

from client import WhatsAppClient
from screens.qr_screen import QRScreen
from screens.chat_view import ChatViewScreen


logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Log to a file so log output never corrupts the Textual display."""
    log_path = Path(
        os.environ.get("WHATSAPP_TUI_LOG", "~/.local/state/whatsapp-tui/app.log")
    ).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class WhatsAppTUI(App):
    CSS = """
    Screen {
        background: #0b141a;
    }

    Header {
        background: #0b141a;
        color: #00a884;
    }

    Footer {
        background: #0b141a;
        color: #8696a0;
    }

    FooterKey .footer-key--key {
        color: #00a884;
    }

    FooterKey .footer-key--description {
        color: #8696a0;
    }
    """

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self):
        super().__init__()
        self.wa = WhatsAppClient()
        self.active_chat_id = None
        self._chat_screen = None
        self._qr_screen = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    async def on_mount(self) -> None:
        if not self.wa.has_session():
            await self.push_screen(self._qr_screen_or_create())
        self.set_interval(0.25, self._poll_events, name="wa-event-poll")
        self._start_client()

    def _qr_screen_or_create(self) -> QRScreen:
        if self._qr_screen is None:
            self._qr_screen = QRScreen()
        return self._qr_screen

    @work
    async def _start_client(self) -> None:
        try:
            await self.wa.start()
        except Exception:
            logger.exception("Failed to start WhatsApp client")
            self.notify("Could not start WhatsApp client - see log", severity="error")

    async def _poll_events(self) -> None:
        while True:
            try:
                event, data = self.wa.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                if event == "qr":
                    self._show_qr(data)
                elif event == "ready":
                    self._on_wa_ready()
                elif event == "status":
                    self._show_status(data)
                elif event == "wa_message":
                    self._on_wa_message(data)
                else:
                    logger.warning("Unknown client event: %r", event)
            except Exception:
                logger.exception("Error handling WhatsApp event %r", event)

    def _show_qr(self, qr_data: str) -> None:
        try:
            if not isinstance(self.screen, QRScreen):
                # Session expired while the chat screen was visible.
                self.switch_screen(self._qr_screen_or_create())
            screen = self.screen
            if hasattr(screen, "show_qr"):
                screen.show_qr(qr_data)
        except Exception:
            logger.exception("Failed to display QR code")
            self.notify("Could not display QR code - see log", severity="error")

    def _show_status(self, msg: str) -> None:
        try:
            screen = self.screen
            if hasattr(screen, "show_status"):
                screen.show_status(msg)
            else:
                self.notify(msg)
        except Exception:
            logger.exception("Failed to display status")
            self.notify(str(msg), severity="warning")

    def _on_wa_ready(self) -> None:
        try:
            if not hasattr(self.screen, "load_chats"):
                self._chat_screen = ChatViewScreen()
                self.switch_screen(self._chat_screen)
            self.wa.start_message_polling()
        except Exception:
            logger.exception("Failed to switch to chat view")
            self.notify("Could not load chats - see log", severity="error")

    def _on_wa_message(self, msg_data: dict) -> None:
        try:
            current = self.screen
            if hasattr(current, "on_new_message"):
                current.on_new_message(msg_data)
        except Exception:
            logger.exception("Failed to display new message")

    def action_refresh(self) -> None:
        try:
            current = self.screen
            if hasattr(current, "load_chats"):
                current.load_chats()
        except Exception:
            logger.exception("Refresh failed")
            self.notify("Refresh failed - see log", severity="error")

    def action_quit_app(self) -> None:
        # Cleanup runs in on_unmount, so all shutdown paths are covered.
        self.exit()

    async def on_unmount(self) -> None:
        try:
            await self.wa.stop()
        except Exception:
            logger.exception("Error while stopping WhatsApp client")


def main():
    setup_logging()
    app = WhatsAppTUI()
    app.run()


if __name__ == "__main__":
    main()
