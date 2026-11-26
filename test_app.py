import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'frontend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'frontend', 'screens'))

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestQRScreen(unittest.TestCase):
    def test_generate_qr_styled(self):
        from qr_screen import generate_qr_styled
        result = generate_qr_styled("https://example.com/test")
        self.assertIsNotNone(result)
        result_str = str(result)
        self.assertIn("▄", result_str)
        self.assertIn("█", result_str)

    def test_generate_qr_styled_empty(self):
        from qr_screen import generate_qr_styled
        result = generate_qr_styled("")
        self.assertIsNotNone(result)

    def test_generate_qr_styled_long_url(self):
        from qr_screen import generate_qr_styled
        url = "https://wa.me/settings/linked_devices#2@test123"
        result = generate_qr_styled(url)
        self.assertIsNotNone(result)

    def test_generate_qr_styled_keeps_colour_spans(self):
        from rich.text import Text
        from qr_screen import generate_qr_styled
        result = generate_qr_styled("2@test-ref")
        self.assertIsInstance(result, Text)
        self.assertTrue(result.spans)
        self.assertIn("█", result.plain)

    def test_qr_display_watch_text(self):
        from qr_screen import QRDisplay
        display = QRDisplay()
        display.watch_qr_text("")

    def test_qr_display_watch_text_with_data(self):
        from qr_screen import QRDisplay
        display = QRDisplay()
        display.watch_qr_text("test-data")

    def test_qr_screen_has_show_qr(self):
        from qr_screen import QRScreen
        screen = QRScreen()
        self.assertTrue(hasattr(screen, 'show_qr'))

    def test_qr_screen_has_show_status(self):
        from qr_screen import QRScreen
        screen = QRScreen()
        self.assertTrue(hasattr(screen, 'show_status'))


class TestChatView(unittest.TestCase):
    def test_chat_item_creation(self):
        from chat_view import ChatItem
        chat = ChatItem({
            'name': 'Test User',
            'lastMessage': 'Hello!',
            'unreadCount': 2,
            'timestamp': int(datetime.now().timestamp()),
        })
        self.assertEqual(chat.chat_data['name'], 'Test User')

    def test_chat_item_no_timestamp(self):
        from chat_view import ChatItem
        chat = ChatItem({
            'name': 'User',
            'lastMessage': 'Hi',
        })
        self.assertIsNotNone(chat)

    def test_message_bubble_render(self):
        from chat_view import MessageBubble
        msg = MessageBubble({
            'body': 'Test message',
            'fromMe': True,
            'timestamp': int(datetime.now().timestamp()),
        })
        rendered = msg.render()
        self.assertIn('Test message', str(rendered))
        self.assertIn('You:', str(rendered))

    def test_message_bubble_incoming(self):
        from chat_view import MessageBubble
        msg = MessageBubble({
            'body': 'Incoming',
            'fromMe': False,
            'timestamp': int(datetime.now().timestamp()),
        })
        rendered = msg.render()
        self.assertIn('Them:', str(rendered))

    def test_message_bubble_escapes_markup(self):
        from chat_view import MessageBubble
        msg = MessageBubble({
            'body': '[bold]not markup[/bold]',
            'fromMe': True,
            'timestamp': 0,
        })
        rendered = str(msg.render())
        self.assertTrue(rendered.startswith('You: \\[bold]not markup'))
        self.assertTrue(rendered.endswith('\\[/bold]  [dim][/dim]'))


class TestWhatsAppClient(unittest.TestCase):
    def test_client_import(self):
        from client import WhatsAppClient
        client = WhatsAppClient()
        self.assertIsNotNone(client)
        self.assertFalse(client.ready)
        self.assertTrue(hasattr(client, 'start'))
        self.assertTrue(hasattr(client, 'stop'))
        self.assertTrue(hasattr(client, 'get_chats'))
        self.assertTrue(hasattr(client, 'get_messages'))
        self.assertTrue(hasattr(client, 'send_message'))


class TestApp(unittest.TestCase):
    def test_app_import(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'app',
            os.path.join(os.path.dirname(__file__), 'frontend', 'app.py')
        )
        self.assertIsNotNone(spec)


if __name__ == '__main__':
    unittest.main()
