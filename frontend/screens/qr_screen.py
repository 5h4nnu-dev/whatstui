import logging

import qrcode
from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, Static
from textual.reactive import reactive


logger = logging.getLogger(__name__)


def generate_qr_styled(data: str) -> Text:
    """Render a QR code as a Rich Text object so its colours survive."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make()

    border = 1
    modcount = qr.modules_count
    size = modcount + 2 * border
    dark = "#00a884"
    light = "#0b141a"
    text = Text(no_wrap=True, end="")

    def is_dark(row: int, col: int) -> bool:
        module_row, module_col = row - border, col - border
        if (
            module_row < 0
            or module_row >= modcount
            or module_col < 0
            or module_col >= modcount
        ):
            return False
        return bool(qr.modules[module_row][module_col])

    for row in range(0, size, 2):
        line = Text()
        for col in range(size):
            top = is_dark(row, col)
            bottom = is_dark(row + 1, col)
            if top and bottom:
                line.append("█", style=f"{dark} on {dark}")
            elif top and not bottom:
                line.append("▀", style=f"{dark} on {light}")
            elif not top and bottom:
                line.append("▄", style=f"{dark} on {light}")
            else:
                line.append(" ", style=f"on {light}")
        text.append(line)
        if row + 2 < size:
            text.append("\n")
    return text


class QRDisplay(Static):
    qr_text = reactive("")

    def watch_qr_text(self, value: str) -> None:
        if not value:
            self.update("Waiting for QR code...")
            return
        try:
            rendered = generate_qr_styled(value)
            try:
                self.update(rendered)
            except Exception:
                # Outside a running App, Textual cannot convert Rich Text
                # (no console). Keep the plain block rendering in that case.
                logger.debug("Falling back to plain QR text", exc_info=True)
                self.update(rendered.plain)
        except Exception:
            logger.exception("Could not render QR code")
            self.update(f"Could not render QR: {escape(value[:80])}")


class QRScreen(Screen):
    CSS = """
    QRScreen {
        align: center middle;
    }

    #qr-container {
        width: 100;
        height: 100;
        border: solid #00a884;
        background: #0b141a;
    }

    #qr-title {
        text-align: center;
        color: #00a884;
        text-style: bold;
    }

    #qr-subtitle {
        text-align: center;
        color: #8696a0;
    }

    QRDisplay {
        text-align: center;
        color: #00a884;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="qr-container"):
            yield Label("WhatsApp TUI", id="qr-title")
            yield Label("Scan the QR code with WhatsApp", id="qr-subtitle")
            yield QRDisplay()

    def show_qr(self, qr_text: str) -> None:
        try:
            self.query_one(QRDisplay).qr_text = qr_text
        except Exception:
            logger.exception("QR display is not available")

    def show_status(self, msg: str) -> None:
        try:
            self.query_one("#qr-subtitle", Label).update(escape(msg))
        except Exception:
            logger.exception("QR status label is not available")
