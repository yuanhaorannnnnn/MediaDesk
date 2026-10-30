"""Offline GTK smoke tests; run under Xvfb on CI."""
import tempfile
import threading
import time
import unittest
from unittest import mock

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk

from mediadesk.app import App
from mediadesk.store import Store


def spin_until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        if predicate():
            return True
        time.sleep(.01)
    return False


@unittest.skipUnless(Gdk.Display.get_default(), '需要 X11 或 Xvfb')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.store.set_setting('setup_done', True)
        self.window = App(self.store)

    def tearDown(self):
        self.window.destroy()
        spin_until(lambda: not Gtk.events_pending(), .3)
        self.temp.cleanup()

    def test_first_page_appears_before_remaining_pages(self):
        first, release = threading.Event(), threading.Event()

        def pages(kind, on_page, playlist_id=''):
            on_page([{'id': 'jNQXAC9IVRw', 'snippet': {'title': 'first'}}])
            first.set()
            release.wait(3)
            on_page([{'id': 'dQw4w9WgXcQ', 'snippet': {'title': 'second'}}])

        try:
            with mock.patch('mediadesk.app.sources.stream_youtube', side_effect=pages):
                self.window.load_source('likes')
                self.assertTrue(first.wait(2))
                self.assertTrue(spin_until(lambda: len(self.window.rows) == 1))
                self.assertIn('正在读取', self.window.rows_count.get_text())
                release.set()
                self.assertTrue(spin_until(lambda: len(self.window.rows) == 2))
                self.assertTrue(spin_until(lambda: self.window.rows_count.get_text() == '2 项'))
                self.assertEqual(len(self.store.media()), 2)
        finally:
            release.set()

    def test_online_playback_does_not_create_download(self):
        self.store.save_youtube({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': 'sample'})
        self.window.show_library()
        self.window.open_row(0)
        self.assertEqual(self.window.start_button.get_tooltip_text(), '在线播放')
        stream = {'url': 'https://r1.googlevideo.com/file?token=example', 'user_agent': 'test', 'resolution': '640x360'}
        with mock.patch('mediadesk.app.downloader.online_stream', return_value=stream), mock.patch('mediadesk.app.Player.open_stream') as play:
            self.window.start_button.clicked()
            self.assertTrue(spin_until(lambda: play.called))
        self.assertEqual(self.store.jobs(), [])
        self.assertFalse(list(self.store.media_dir.iterdir()))
        self.assertNotIn(b'token=example', self.store.dbpath.read_bytes())


if __name__ == '__main__':
    unittest.main()
