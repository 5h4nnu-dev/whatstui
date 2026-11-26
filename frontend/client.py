import asyncio
import logging
import os
from pathlib import Path

from playwright.async_api import async_playwright


logger = logging.getLogger(__name__)

USER_DATA_DIR = str(
    Path(
        os.environ.get(
            "WHATSAPP_TUI_PROFILE", "~/.local/share/whatsapp-tui/chrome-profile"
        )
    ).expanduser()
)

TEXTBOX_SELECTOR = "div[role='textbox'][contenteditable='true']"


class WhatsAppClient:
    def __init__(self):
        self.browser = None
        self.page = None
        self.ready = False
        self.event_queue = asyncio.Queue()
        self._running = False
        self._known_messages = {}
        self._playwright = None
        self._tasks = set()
        self._message_poll_task = None
        self._last_qr = None
        self._last_two_fa = False

    def has_session(self) -> bool:
        """Best-effort check for an existing WhatsApp Web login."""
        leveldb = Path(USER_DATA_DIR) / "Default" / "Local Storage" / "leveldb"
        if not leveldb.is_dir():
            return False
        # A logged-in profile always has a leveldb database; one file alone
        # (e.g. just CURRENT) is not enough evidence.
        return len(list(leveldb.iterdir())) > 1

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)

        try:
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--window-size=1920,1080",
                ],
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                bypass_csp=True,
                ignore_https_errors=True,
            )

            self.page = (
                self.browser.pages[0]
                if self.browser.pages
                else await self.browser.new_page()
            )

            await self.page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'platform', { get: () => 'Linux' });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                """
            )

            await self.page.goto(
                "https://web.whatsapp.com",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            logger.info("Opened WhatsApp Web")
            self._spawn(self._poll_auth())
        except Exception:
            logger.exception("Failed to start Playwright/WhatsApp Web")
            self._running = False
            await self.event_queue.put(
                ("status", "Failed to open WhatsApp Web - see log")
            )
            raise

    async def _poll_auth(self) -> None:
        while self._running:
            try:
                if self.page is None or self.page.is_closed():
                    break

                auth_state = await self.page.evaluate(
                    r"""() => {
                        const refEl = document.querySelector('[data-ref]');
                        const qrRef = refEl ? (refEl.getAttribute('data-ref') || '') : '';
                        const hasTwoFa = !!document.querySelector(
                            '[data-testid="code-confirm-pin"], [data-testid="enter-pin"], [data-testid="confirm-pin"]'
                        );
                        let chatRows = 0;
                        for (const row of document.querySelectorAll('div[role="row"]')) {
                            if (row.querySelector('[data-testid="cell-frame-container"]')) {
                                chatRows++;
                            }
                        }
                        const chatPane = document.querySelector('[data-testid="chat-list"], #pane-side');
                        return {
                            qrRef,
                            hasTwoFa,
                            isLoggedIn: chatRows > 0 || !!chatPane,
                        };
                    }"""
                )

                if auth_state.get("isLoggedIn"):
                    if not self.ready:
                        self.ready = True
                        # Avoid treating the current chat list as new messages.
                        await self.get_chats()
                        await self.event_queue.put(("ready", {}))
                        logger.info("WhatsApp Web is ready")
                    self._last_qr = None
                    self._last_two_fa = False
                    await asyncio.sleep(2)
                    continue

                # Logged out / session expired: return to QR flow.
                if self.ready:
                    self.ready = False
                    self._known_messages.clear()
                    self._last_qr = None
                    await self.event_queue.put(
                        ("status", "Session expired - scan the QR code again")
                    )
                    logger.warning("WhatsApp session expired")

                has_two_fa = bool(auth_state.get("hasTwoFa"))
                if has_two_fa and not self._last_two_fa:
                    await self.event_queue.put(
                        ("status", "Two-factor code required - enter it in the browser")
                    )
                self._last_two_fa = has_two_fa

                qr_ref = auth_state.get("qrRef") or ""
                if qr_ref and qr_ref != self._last_qr:
                    self._last_qr = qr_ref
                    await self.event_queue.put(("qr", qr_ref))
            except Exception:
                if self._running:
                    logger.exception("Error while polling authentication state")
            await asyncio.sleep(1)

    async def _poll_messages(self) -> None:
        while self._running and self.ready:
            try:
                if self.page and not self.page.is_closed():
                    await self._check_new_messages()
            except Exception:
                logger.exception("Error while polling messages")
            await asyncio.sleep(2)

    async def _check_new_messages(self) -> None:
        chats = await self.get_chats()
        for chat in chats:
            chat_id = chat["id"]
            current = chat.get("lastMessage", "")
            known = self._known_messages.get(chat_id)
            if known and current and current != known["lastMessage"]:
                await self.event_queue.put(
                    (
                        "wa_message",
                        {
                            "chatId": chat_id,
                            "body": current,
                            "fromMe": chat.get("lastMessageFromMe", False),
                            "timestamp": chat.get("timestamp", 0),
                        },
                    )
                )
            self._known_messages[chat_id] = {
                "lastMessage": current,
                "lastMessageFromMe": chat.get("lastMessageFromMe", False),
            }

    async def get_chats(self) -> list:
        if not self.ready or self.page is None:
            return []
        try:
            return (
                await self.page.evaluate(
                    r"""() => {
                        const chats = [];
                        const seen = new Set();
                        for (const row of document.querySelectorAll('div[role="row"]')) {
                            const container = row.querySelector('[data-testid="cell-frame-container"]');
                            if (!container) continue;
                            const titleEl = container.querySelector('span[title]');
                            const name = titleEl ? titleEl.getAttribute('title') : null;
                            if (!name || seen.has(name)) continue;
                            seen.add(name);

                            const msgEl = container.querySelector('span.selectable-text');
                            const lastMsg = msgEl ? msgEl.textContent.trim() : '';

                            const timeEl = container.querySelector('[data-testid="last-msg-time"]') ||
                                container.querySelector('[data-pre-plain-text]');
                            let ts = Math.floor(Date.now() / 1000);
                            if (timeEl) {
                                const pre = timeEl.getAttribute('data-pre-plain-text') || timeEl.textContent || '';
                                const match = pre.match(/\b(\d{1,2}):(\d{2})\b/);
                                if (match) {
                                    const d = new Date();
                                    d.setHours(parseInt(match[1], 10), parseInt(match[2], 10), 0, 0);
                                    ts = Math.floor(d.getTime() / 1000);
                                }
                            }

                            const unreadEl = container.querySelector('[data-testid="icon-unread-count"]') ||
                                container.querySelector('[data-testid="pills-unread-count"]');
                            let unread = 0;
                            if (unreadEl) {
                                const val = parseInt(unreadEl.textContent, 10);
                                if (!isNaN(val)) unread = val;
                            }

                            const fromMe = !!container.querySelector(
                                '[data-testid="msg-dblcheck"], [data-testid="msg-check"], [data-testid="msg-dblcheck-ack"]'
                            );
                            const dataId = row.getAttribute('data-id') || container.getAttribute('data-id') || '';
                            chats.push({
                                id: dataId || name,
                                name: name,
                                lastMessage: lastMsg,
                                unreadCount: unread,
                                timestamp: ts,
                                lastMessageFromMe: fromMe,
                            });
                        }
                        return chats.slice(0, 50);
                    }"""
                )
                or []
            )
        except Exception:
            logger.exception("Failed to read chat list")
            return []

    async def open_chat(self, chat_id: str) -> bool:
        if not self.ready or self.page is None:
            return False
        try:
            clicked = await self.page.evaluate(
                """(value) => {
                    for (const row of document.querySelectorAll('div[role="row"]')) {
                        const container = row.querySelector('[data-testid="cell-frame-container"]');
                        if (!container) continue;
                        const titleEl = container.querySelector('span[title]');
                        const name = titleEl ? titleEl.getAttribute('title') : null;
                        const dataId = row.getAttribute('data-id') || container.getAttribute('data-id') || '';
                        if (name === value || dataId === value) {
                            container.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                chat_id,
            )
            if clicked:
                await self.page.locator(TEXTBOX_SELECTOR).first.wait_for(
                    state="visible", timeout=5000
                )
            return bool(clicked)
        except Exception:
            logger.exception("Failed to open chat %r", chat_id)
            return False

    async def get_messages(self, chat_id: str, limit: int = 50) -> list:
        if not self.ready or self.page is None:
            return []
        try:
            if not await self.open_chat(chat_id):
                return []
            messages = (
                await self.page.evaluate(
                    r"""(lim) => {
                        const selectors = [
                            'div.message-in, div.message-out',
                            '[data-testid="conversation-panel"] div[role="row"]',
                            'div.copyable-text',
                            '[data-testid="msg-container"]',
                        ];
                        let allMsgs = [];
                        for (const selector of selectors) {
                            const found = document.querySelectorAll(selector);
                            if (found.length) {
                                allMsgs = Array.from(found);
                                break;
                            }
                        }

                        return allMsgs.slice(-lim).map(el => {
                            const bodyEl = el.querySelector('span.selectable-text') ||
                                el.querySelector('span[dir="auto"]');
                            const body = bodyEl ? bodyEl.textContent.trim() : (el.textContent || '').trim();
                            const isOut = el.classList.contains('message-out') ||
                                el.closest('.message-out') !== null ||
                                (el.getAttribute('data-testid') || '').includes('msg-out');

                            const preText = el.getAttribute('data-pre-plain-text') || '';
                            let ts = Math.floor(Date.now() / 1000);
                            const full = preText.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4}),?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?/);
                            if (full) {
                                let year = parseInt(full[3], 10);
                                if (year < 100) year += 2000;
                                const d = new Date(
                                    year, parseInt(full[1], 10) - 1, parseInt(full[2], 10),
                                    parseInt(full[4], 10), parseInt(full[5], 10),
                                    full[6] ? parseInt(full[6], 10) : 0
                                );
                                ts = Math.floor(d.getTime() / 1000);
                            } else {
                                const hm = preText.match(/\b(\d{1,2}):(\d{2})\b/);
                                if (hm) {
                                    const d = new Date();
                                    d.setHours(parseInt(hm[1], 10), parseInt(hm[2], 10), 0, 0);
                                    ts = Math.floor(d.getTime() / 1000);
                                }
                            }
                            return { body, fromMe: !!isOut, timestamp: ts };
                        });
                    }""",
                    limit,
                )
                or []
            )
            return messages
        except Exception:
            logger.exception("Failed to read messages for %r", chat_id)
            return []

    async def send_message(self, chat_id: str, message: str) -> bool:
        if not self.ready or self.page is None:
            return False
        try:
            if not await self.open_chat(chat_id):
                return False
            textbox = self.page.locator(TEXTBOX_SELECTOR).first
            if not await textbox.count():
                return False
            await textbox.click()
            await textbox.press_sequentially(message, delay=10)
            await textbox.press("Enter")
            await textbox.wait_for(state="visible", timeout=5000)
            return True
        except Exception:
            logger.exception("Failed to send message to %r", chat_id)
            return False

    async def start_message_polling(self) -> None:
        if self._message_poll_task is None or self._message_poll_task.done():
            self._message_poll_task = self._spawn(self._poll_messages())

    async def stop(self) -> None:
        self._running = False
        self.ready = False

        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                logger.exception("Error closing browser context")
            self.browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                logger.exception("Error stopping Playwright")
            self._playwright = None
        self.page = None
        logger.info("WhatsApp client stopped")
