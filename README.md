# whatsapp-tui

A terminal WhatsApp client built with [Textual](https://textual.textualize.io/). It drives WhatsApp Web through a headless Chromium instance via Playwright, renders the login QR code directly in the terminal, and lets you browse chats, read recent messages, and send replies without leaving the keyboard.

> **Note:** This is an unofficial client. It reads WhatsApp Web's DOM, so UI changes on WhatsApp's side can break it. It is not affiliated with or endorsed by WhatsApp.

## Features

- QR-code login rendered in the terminal (half-block characters, WhatsApp green)
- Persistent browser profile, so you normally only scan the QR code once
- Chat list with unread counts and last-message previews
- Recent message history for the selected chat
- Send messages with Enter; incoming messages appear live in the open chat
- Session-expiry detection that returns to the QR screen

## Requirements

- Python 3 (the test environment uses 3.14)
- Chromium, installed through Playwright

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/playwright install chromium
```

## Run

```bash
./run.sh
```

`run.sh` activates the local `venv` and starts `frontend/app.py`. On first launch, scan the QR code shown in the terminal with WhatsApp on your phone.

## Keybindings

| Key | Action |
| --- | --- |
| `q` | Quit |
| `r` | Refresh the chat list |
| `Esc` | Focus the chat list |
| `Enter` | Send the typed message |

## Configuration

Both settings are optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WHATSAPP_TUI_PROFILE` | `~/.local/share/whatsapp-tui/chrome-profile` | Chromium profile directory holding the login session |
| `WHATSAPP_TUI_LOG` | `~/.local/state/whatsapp-tui/app.log` | Log file (kept out of the terminal so it doesn't corrupt the UI) |

## Tests

```bash
venv/bin/python test_app.py
```

## Project layout

```text
frontend/app.py              Textual app, screens, keybindings, event loop
frontend/client.py           Playwright/WhatsApp Web client
frontend/screens/qr_screen.py    QR-code login screen
frontend/screens/chat_view.py    Chat list and conversation view
test_app.py                  Unit tests
run.sh                       Launcher
requirements.txt             Python dependencies
```
