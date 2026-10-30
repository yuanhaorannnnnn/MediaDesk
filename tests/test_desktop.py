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

    def test_search_navigation_and_return_preserve_filter(self):
        for url, title in [('https://youtu.be/jNQXAC9IVRw', '搜索 样例一'), ('https://youtu.be/dQw4w9WgXcQ', '其他内容'), ('https://youtu.be/9bZkp7q19f0', '搜索 样例二')]:
            self.store.save_youtube({'url': url, 'title': title})
        self.window.show_library()
        search = next(w for w in self.window.content.get_children() if isinstance(w, Gtk.SearchEntry))
        search.set_text('搜索')
        self.assertTrue(spin_until(lambda: sum(child.get_child_visible() for child in self.window.rows_box.get_children()) == 2))
        indices = [i for i, row in enumerate(self.window.rows) if '搜索' in row['title']]
        self.window.open_row(indices[0])
        next_button = next(w for w in self.window.detail_nav.get_children() if w.get_tooltip_text() == '下一条')
        self.assertTrue(next_button.get_sensitive())
        next_button.clicked()
        self.assertEqual(self.window.row_index, indices[1])
        self.window.return_rows()
        restored = next(w for w in self.window.content.get_children() if isinstance(w, Gtk.SearchEntry))
        self.assertEqual(restored.get_text(), '搜索')
        self.assertTrue(spin_until(lambda: sum(child.get_child_visible() for child in self.window.rows_box.get_children()) == 2))

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

    def test_download_metadata_failure_can_retry_without_reentering_url(self):
        url='https://youtu.be/jNQXAC9IVRw';item={'url':url,'title':'sample'}
        with mock.patch('mediadesk.app.downloader.inspect',side_effect=[ValueError('网络连接失败'),item]) as inspect, mock.patch.object(self.window.downloader,'start') as start:
            self.window.inspect_and_download(url)
            self.assertTrue(spin_until(lambda:self.window.retry_button.get_visible()))
            self.assertIn('网络连接失败',self.window.status.get_text())
            self.window.retry_button.clicked()
            self.assertTrue(spin_until(lambda:start.called))
            self.assertEqual(inspect.call_count,2);self.assertEqual(start.call_args.args[0],item)
            self.assertFalse(self.window.retry_button.get_visible())

    def test_download_state_save_failure_is_visible(self):
        with mock.patch.object(self.window.downloader,'reconcile',return_value=False):
            self.window.download_update('missing')
            self.assertIn('无法读取或保存下载状态',self.window.status.get_text())
            self.window.show_jobs();self.assertIn('无法读取或保存下载状态',self.window.status.get_text())

    def test_download_strict_check_stage_is_visible(self):
        mid=self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw','title':'sample'})
        self.store.job('strict-job',mid,'下载中','正在严格检查');self.window.download_update('strict-job')
        self.assertIn('正在严格检查',self.window.download_label.get_text())

    def test_bilibili_pages_and_unavailable_video(self):
        self.store.set_setting('bilibili_cookies',True)
        def pages(kind,on_page,fid=''):
            self.assertEqual(kind,'favorites')
            on_page([{'id':1,'type':2,'title':'可播放','bv_id':'BV1bK411W797'}])
            on_page([{'id':2,'type':2,'title':'已失效视频','bv_id':'BV1PL4y1h7yd','attr':1}])
        with mock.patch('mediadesk.app.bilibili.stream',side_effect=pages):
            self.window.load_bilibili('favorites','42','测试收藏')
            self.assertTrue(spin_until(lambda: len(self.window.rows)==2))
            self.assertTrue(spin_until(lambda: self.window.rows_count.get_text()=='2 项'))
            self.assertFalse(self.window.rows[0]['unavailable']);self.assertTrue(self.window.rows[1]['unavailable'])
            search = next(w for w in self.window.content.get_children() if isinstance(w, Gtk.SearchEntry))
            search.set_text('失效')
            self.assertTrue(spin_until(lambda: sum(child.get_child_visible() for child in self.window.rows_box.get_children()) == 1))
            self.window.open_row(1)
            self.assertFalse(next(w for w in self.window.detail_nav.get_children() if w.get_tooltip_text() == '上一条').get_sensitive())
            self.assertTrue(any(isinstance(x,Gtk.Label) and '已失效' in x.get_text() for x in self.window.mode_row.get_children()))
            self.assertFalse(any(isinstance(x,Gtk.Button) and x.get_label()=='下载' for x in self.window.detail_right.get_children()))
            self.assertEqual(len(self.store.media()),1)
            self.window.return_rows()
            self.assertEqual(next(w for w in self.window.content.get_children() if isinstance(w, Gtk.SearchEntry)).get_text(), '失效')

    def test_account_status_requires_verification_and_keeps_last_success(self):
        self.store.set_setting('bilibili_cookies',True)
        def bili(kind,on_page,fid=''):
            self.assertEqual(kind,'status');on_page([{'name':'测试账号'}])
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[{'snippet':{'title':'YouTube 测试'}}]),mock.patch('mediadesk.app.bilibili.stream',side_effect=bili):
            self.window.select_nav('settings');self.window.show_settings()
            self.assertTrue(spin_until(lambda: self.window.account_status_widgets['bilibili'].get_text().startswith('已连接')))
            self.assertTrue(spin_until(lambda: self.window.account_status_widgets['youtube'].get_text().startswith('已连接')))
            self.assertIn('测试账号',self.window.account_status_widgets['bilibili'].get_text())
            self.assertIn('●',self.window.nav_buttons['platform-bilibili'].get_child().get_children()[1].get_text())
        with mock.patch('mediadesk.app.bilibili.stream',side_effect=ValueError('网络不可用')):
            self.window.check_account('bilibili')
            self.assertTrue(spin_until(lambda:self.window.account_status_widgets['bilibili'].get_text().startswith('暂时无法验证')))
            self.assertIn('上次验证',self.window.account_status_widgets['bilibili'].get_text())
            self.assertIn('○',self.window.nav_buttons['platform-bilibili'].get_child().get_children()[1].get_text())
        self.store.set_setting('bilibili_cookies',False);self.window.check_account('bilibili')
        self.assertIn('未授权',self.window.account_status_widgets['bilibili'].get_text())

    def test_discovery_filters_and_folder_navigation(self):
        self.store.set_setting('bilibili_cookies',True)
        def bili(kind,on_page,fid=''):
            self.assertEqual(kind,'folders');on_page([{'id':7,'title':'B 站收藏'}])
        youtube=[{'id':'playlist-id','snippet':{'title':'YouTube 播放列表'}}]
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=youtube),mock.patch('mediadesk.app.bilibili.stream',side_effect=bili):
            self.window.show_discovery('collections')
            self.assertTrue(spin_until(lambda:len(self.window.discovery_box.get_children())==3))
            self.window.discovery_choice.set_active_id('bilibili')
            self.assertEqual(len(self.window.discovery_box.get_children()),1)
            row=self.window.discovery_box.get_children()[0].get_child()
            with mock.patch.object(self.window,'load_bilibili') as open_folder:
                next(w for w in row.get_children() if isinstance(w,Gtk.Button)).clicked()
                open_folder.assert_called_once_with('favorites','7','B 站收藏')
            self.window.discovery_choice.set_active_id('youtube');self.assertEqual(len(self.window.discovery_box.get_children()),2)

    def test_revoking_permission_discards_inflight_account_result(self):
        self.store.set_setting('bilibili_cookies',True);entered=threading.Event();release=threading.Event()
        def bili(kind,on_page,fid=''):
            entered.set();release.wait(3);on_page([{'name':'不应显示'}])
        try:
            with mock.patch('mediadesk.app.sources.list_youtube',side_effect=ValueError('需要连接 YouTube 账号')),mock.patch('mediadesk.app.bilibili.stream',side_effect=bili):
                self.window.select_nav('settings');self.window.show_settings();self.assertTrue(entered.wait(2))
                self.store.set_setting('bilibili_cookies',False);self.window.check_account('bilibili');release.set()
                spin_until(lambda:not Gtk.events_pending(),.2)
                self.assertIn('未授权',self.window.account_status_widgets['bilibili'].get_text())
                self.assertIsNone(self.store.setting('account_bilibili'))
        finally:release.set()

    def test_discovery_permission_prompt_is_not_counted_as_content(self):
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[]):
            self.window.show_discovery('collections')
            self.assertTrue(spin_until(lambda:'未授权' in self.window.discovery_status.get_text()))
            self.assertEqual(len(self.window.discovery_box.get_children()),2)
            self.assertTrue(self.window.discovery_status.get_text().startswith('1 项'))

    def test_art_themes_are_selectable_and_persisted(self):
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[]):
            self.window.show_settings()
            scroll=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.ScrolledWindow))
            content=scroll.get_child().get_child()
            combo=next(w for w in content.get_children() if isinstance(w,Gtk.ComboBoxText))
            for theme,dark in [('nabis',True),('neo-impressionism',False),('dark',True),('light',False)]:
                combo.set_active_id(theme);self.assertEqual(self.store.setting('theme'),theme)
                self.assertEqual(Gtk.Settings.get_default().get_property('gtk-application-prefer-dark-theme'),dark)
            self.assertEqual(Store(self.temp.name).setting('theme'),'light')


if __name__ == '__main__':
    unittest.main()
