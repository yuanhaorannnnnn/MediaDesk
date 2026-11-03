"""Offline integration tests for account onboarding and podcast discovery."""
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

import gi
import mediadesk
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk

from mediadesk.app import App
from mediadesk.store import Store
from tests.test_desktop import spin_until


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from descendants(child)


def button_named(widget, text):
    return next(w for w in descendants(widget)
                if isinstance(w, Gtk.Button) and w.get_label() == text)


@unittest.skipUnless(Gdk.Display.get_default(), '需要 X11 或 Xvfb')
class ProductUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.store.set_setting('setup_done', True)
        self.window = App(self.store)

    def tearDown(self):
        self.window.destroy()
        spin_until(lambda: not Gtk.events_pending(), .3)
        self.temp.cleanup()

    def test_search_feed_and_add_episode(self):
        episode = {'url': 'https://example.test/episode.mp3', 'title': '示例单集'}
        podcast = types.ModuleType('mediadesk.podcasts')
        podcast.search = mock.Mock(return_value=[{'title': '示例节目', 'channel': '示例频道', 'feed_url': 'https://example.test/feed'}])
        podcast.read_feed = mock.Mock(return_value={'title': '示例节目', 'episodes': [episode], 'notice': '展示有限结果'})
        with mock.patch.dict(sys.modules, {'mediadesk.podcasts': podcast}), mock.patch.object(mediadesk, 'podcasts', podcast, create=True):
            self.window.select_nav('podcasts'); self.window.show_podcasts()
            self.window.podcast_entry.set_text('示例'); self.window.podcast_entry.emit('activate')
            self.assertTrue(spin_until(lambda: self.window.podcast_status.get_text() == '找到 1 个节目'))
            button_named(self.window.podcast_results, '查看单集').clicked()
            self.assertTrue(spin_until(lambda: self.window.podcast_status.get_text() == '示例节目 · 1 集'))
            self.assertEqual(self.window.podcast_notice.get_text(), '展示有限结果')
            self.assertTrue(any(isinstance(w, Gtk.Label) and w.get_text() == '示例单集' for w in descendants(self.window.podcast_results)))
            with mock.patch.object(self.store, 'save_source', return_value='episode-id') as save, mock.patch.object(self.window, 'show_library') as library, mock.patch.object(self.window, 'open_row') as opened:
                library.side_effect = lambda: setattr(self.window, 'rows', [{'id': 'episode-id'}])
                button_named(self.window.podcast_results, '加入并查看').clicked()
                save.assert_called_once_with(episode); opened.assert_called_once_with(0)
            podcast.search.assert_called_once_with('示例'); podcast.read_feed.assert_called_once_with('https://example.test/feed')

    def test_stale_podcast_request_and_navigation_do_not_replace_current_view(self):
        entered = threading.Event(); release = threading.Event(); finished = threading.Event()
        podcast = types.ModuleType('mediadesk.podcasts')
        def search(query):
            if query == '旧请求':
                entered.set(); release.wait(3); finished.set()
                return [{'title': '过期节目', 'feed_url': 'https://example.test/old'}]
            return [{'title': '新节目', 'feed_url': 'https://example.test/new'}]
        podcast.search = search
        try:
            with mock.patch.dict(sys.modules, {'mediadesk.podcasts': podcast}), mock.patch.object(mediadesk, 'podcasts', podcast, create=True):
                self.window.select_nav('podcasts'); self.window.show_podcasts()
                self.window.podcast_query('旧请求'); self.assertTrue(entered.wait(2))
                self.window.podcast_query('新请求')
                self.assertTrue(spin_until(lambda: any(isinstance(w, Gtk.Label) and w.get_text() == '新节目' for w in descendants(self.window.podcast_results))))
                release.set(); self.assertTrue(finished.wait(2)); spin_until(lambda: False, .1)
                self.assertFalse(any(isinstance(w, Gtk.Label) and w.get_text() == '过期节目' for w in descendants(self.window.podcast_results)))
                entered.clear(); release.clear(); finished.clear()
                self.window.podcast_query('旧请求'); self.assertTrue(entered.wait(2))
                self.window.show_library(); release.set(); self.assertTrue(finished.wait(2)); spin_until(lambda: False, .1)
                self.assertFalse(any(isinstance(w, Gtk.Label) and w.get_text() == '过期节目' for w in descendants(self.window.content)))
        finally:
            release.set()

    def test_podcast_hover_does_not_fetch_online_but_local_preview_remains(self):
        import os
        local_path = os.path.join(self.temp.name, 'download.mp3')
        with open(local_path, 'wb') as output:
            output.write(b'local example')
        items = [
            {'id': 'remote-podcast', 'source': 'podcast', 'url': 'https://example.test/episode.mp3', 'title': '在线播客'},
            {'id': 'local-podcast', 'source': 'podcast', 'url': 'https://example.test/local.mp3', 'path': local_path, 'title': '本地播客'},
            {'id': 'youtube', 'source': 'youtube', 'url': 'https://youtu.be/jNQXAC9IVRw', 'title': '视频'},
        ]
        self.window.source_kind = 'library'
        with mock.patch.object(self.window.hover_preview, 'track') as track:
            self.window.display_rows('测试', items)
        self.assertEqual([call.args[2]['id'] for call in track.call_args_list], ['local-podcast', 'youtube'])

    def test_podcast_add_and_detail_never_fetch_art_or_online_preview(self):
        episode = {'id': 'podcast:example', 'source': 'podcast', 'url': 'https://example.test/audio.mp3',
                   'title': '示例单集', 'thumbnail': 'https://i.ytimg.com/example.jpg'}
        self.window.select_nav('podcasts'); self.window.show_podcasts()
        with mock.patch.object(self.store, 'save_source', return_value=episode['id']), \
             mock.patch.object(self.store, 'media', return_value=[episode]), \
             mock.patch.object(self.store, 'get', return_value=episode), \
             mock.patch.object(self.window, 'load_art') as art, \
             mock.patch('mediadesk.preview.downloader.online_stream') as online:
            self.window.podcast_add(episode)
            art.assert_not_called()
            preview = self.window.hover_preview
            preview.cover = self.window.placeholder; preview.item = episode
            preview.start(preview.serial)
            self.assertIsNone(preview.pending)
            online.assert_not_called()

    def test_setup_error_import_and_skip(self):
        self.store.set_setting('setup_done', False); self.window.setup_step = 1; self.window.setup()
        oauth = types.ModuleType('mediadesk.oauth_config'); oauth.import_client = mock.Mock()
        with mock.patch('mediadesk.app.sources.list_youtube', side_effect=ValueError('缺少 Google OAuth 客户端配置')) as auth:
            self.window.youtube_connect_button.clicked()
            self.assertTrue(spin_until(lambda: '连接失败' in self.window.account_status_widgets['youtube'].get_text()))
            self.assertTrue(self.window.youtube_import_button.get_visible())
            with mock.patch.dict(sys.modules, {'mediadesk.oauth_config': oauth}), mock.patch('mediadesk.app.Gtk.FileChooserDialog') as dialog:
                dialog.return_value.run.return_value = Gtk.ResponseType.OK
                dialog.return_value.get_filename.return_value = '/example/client.json'
                self.window.youtube_import_button.clicked()
            oauth.import_client.assert_called_once_with('/example/client.json')
            self.assertIn('配置已导入', self.window.account_status_widgets['youtube'].get_text())
            self.assertFalse(self.window.youtube_import_button.get_visible())
            auth.assert_called_once_with('auth')
            button_named(self.window.body, '跳过').clicked()
            self.assertEqual(self.window.setup_step, 2)
            self.assertFalse(self.store.setting('setup_done', False))


if __name__ == '__main__':
    unittest.main()
