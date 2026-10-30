"""Offline GTK smoke tests; run under Xvfb on CI."""
import tempfile
import threading
import time
import unittest
from unittest import mock

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf

from mediadesk.app import App, MediaCover
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

    def test_local_creator_matching_without_network_and_back_navigation(self):
        channel='UC'+'a'*22
        self.store.save_source({'url':'https://youtu.be/jNQXAC9IVRw','title':'id match','channel':'former name','metadata':{'creator_id':channel},'thumbnail':'https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg'})
        self.store.save_source({'url':'https://youtu.be/dQw4w9WgXcQ','title':'name match','channel':'Alice'})
        self.store.save_source({'url':'https://youtu.be/9bZkp7q19f0','title':'same name different id','channel':'Alice','metadata':{'creator_id':'UC'+'b'*22}})
        self.store.save_source({'url':'https://www.bilibili.com/video/BV1bK411W797','title':'other platform','channel':'Alice'})
        with mock.patch('mediadesk.app.sources.thumbnail') as network,mock.patch.object(self.window.hover_preview,'track') as track:
            self.window.open_creator('youtube',channel,'Alice')
            self.assertEqual({x['title'] for x in self.window.rows},{'id match','name match'})
            self.assertTrue(any(isinstance(w,Gtk.Label) and '可能包含同名作者' in w.get_text() for w in self.window.content.get_children()))
            self.window.open_row(0);self.window.return_rows()
            self.assertEqual(len(self.window.rows),2);network.assert_not_called();track.assert_not_called()
            self.assertTrue(any(isinstance(w,Gtk.Button) and w.get_label()=='← 返回关注' for w in self.window.content.get_children()))

    def test_creator_cached_cover_loads_in_list_and_detail(self):
        import hashlib
        url = 'https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg'
        folder = self.store.root / 'thumbnails'; folder.mkdir(exist_ok=True)
        path = folder / (hashlib.sha256(url.encode()).hexdigest() + '.img')
        image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 32, 18)
        image.fill(0x557788ff); image.savev(str(path), 'png', [], [])
        self.store.save_source({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': 'sample', 'channel': 'Alice', 'thumbnail': url})
        with mock.patch('mediadesk.app.sources.thumbnail') as network:
            self.window.open_creator('youtube', 'UC' + 'a' * 22, 'Alice')
            cover = self.window.rows_box.get_children()[0].get_child().get_child().get_children()[0]
            self.assertIsNotNone(cover.pixbuf)
            self.window.open_row(0)
            self.assertIsNotNone(self.window.placeholder.pixbuf)
            plain = Gtk.Image(); self.window.load_cached_art(plain, url)
            self.assertIsNotNone(plain.get_pixbuf())
            network.assert_not_called()

    def test_creator_return_restores_follow_filter_without_new_requests(self):
        youtube=[{'snippet':{'title':'Alice','resourceId':{'channelId':'UC'+'a'*22}}}]
        def bili(kind,on_page,*_):on_page([{'uname':'up','mid':123}])
        self.store.set_setting('bilibili_cookies',True)
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=youtube) as yt,mock.patch('mediadesk.app.bilibili.stream',side_effect=bili) as bs:
            self.window.show_discovery('follow')
            self.assertTrue(spin_until(lambda:'读取完成' in self.window.discovery_status.get_text() and len(self.window.discovery_box.get_children())==2))
            self.window.discovery_choice.set_active_id('youtube');self.assertEqual(len(self.window.discovery_box.get_children()),1)
            self.window.open_creator('youtube','UC'+'a'*22,'Alice')
            back=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.Button) and w.get_label()=='← 返回关注')
            before=(yt.call_count,bs.call_count);back.clicked()
            self.assertEqual((yt.call_count,bs.call_count),before);self.assertEqual(self.window.discovery_choice.get_active_id(),'youtube')
            self.assertEqual(len(self.window.discovery_box.get_children()),1)
            self.window.discovery_choice.set_active_id('all');self.assertEqual(len(self.window.discovery_box.get_children()),2)
            self.window.open_creator('bilibili','123','up')
            back=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.Button) and w.get_label()=='← 返回关注')
            back.clicked();self.assertEqual(self.window.discovery_choice.get_active_id(),'all');self.assertEqual(len(self.window.discovery_box.get_children()),2)

    def test_collection_return_restores_filter_without_reloading(self):
        lists=[{'id':'playlist','snippet':{'title':'list'}}]
        item={'snippet':{'title':'video','resourceId':{'videoId':'jNQXAC9IVRw'}},'contentDetails':{'videoId':'jNQXAC9IVRw'}}
        def stream(kind,callback,playlist_id=''):callback([item])
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=lists) as list_api,mock.patch('mediadesk.app.sources.stream_youtube',side_effect=stream) as video_api:
            self.window.show_discovery('collections')
            self.assertTrue(spin_until(lambda:len(self.window.discovery_box.get_children())>=2))
            self.window.discovery_choice.set_active_id('youtube')
            self.assertEqual(len(self.window.discovery_box.get_children()),2)
            row=next(row for row in self.window.discovery_box.get_children() if 'list' in row.get_accessible().get_name())
            self.window.discovery_box.emit('row-activated',row)
            self.assertTrue(spin_until(lambda:len(self.window.rows)==1))
            previous=(list_api.call_count,video_api.call_count)
            back=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.Button) and w.get_label()=='← 返回收藏与播放列表')
            back.clicked();self.assertEqual((list_api.call_count,video_api.call_count),previous)
            self.assertEqual(self.window.discovery_choice.get_active_id(),'youtube');self.assertEqual(len(self.window.discovery_box.get_children()),2)

    def test_bilibili_collection_return_preserves_snapshot(self):
        self.store.set_setting('bilibili_cookies',True)
        def bili(kind,callback,fid=''):
            if kind=='folders':callback([{'id':12,'title':'fave'}])
            elif kind=='favorites':callback([{'bvid':'BV1bK411W797','title':'item','upper':{'name':'user'}}])
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[]),mock.patch('mediadesk.app.bilibili.stream',side_effect=bili) as api:
            self.window.show_discovery('collections');self.window.discovery_choice.set_active_id('bilibili')
            self.assertTrue(spin_until(lambda:len(self.window.discovery_box.get_children())==1))
            self.window.discovery_box.emit('row-activated',self.window.discovery_box.get_children()[0])
            self.assertTrue(spin_until(lambda:len(self.window.rows)==1));before=api.call_count
            back=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.Button) and w.get_label()=='← 返回收藏与播放列表')
            back.clicked();self.assertEqual(api.call_count,before);self.assertEqual(self.window.discovery_choice.get_active_id(),'bilibili')

    def test_local_creator_empty_is_local_and_does_not_request_network(self):
        with mock.patch('mediadesk.app.sources.list_youtube') as yt,mock.patch('mediadesk.app.bilibili.stream') as bili:
            self.window.open_creator('bilibili','123','Missing')
            self.assertEqual(self.window.rows,[])
            self.assertTrue(any(isinstance(w,Gtk.Label) and '暂无匹配' in w.get_text() for w in self.window.content.get_children()))
            yt.assert_not_called();bili.assert_not_called()

    def test_setup_added_directory_stays_with_other_choices(self):
        from pathlib import Path
        with mock.patch('mediadesk.app.safe_dirs', return_value=[Path('/tmp/default-media')]):
            self.window.setup_step = 2
            self.window.setup()
        existing = self.window.dir_checks[0][0]
        choices = existing.get_parent()
        with mock.patch('mediadesk.app.Gtk.FileChooserDialog') as dialog:
            dialog.return_value.run.return_value = Gtk.ResponseType.OK
            dialog.return_value.get_filename.return_value = '/tmp/extra-media'
            self.window.choose_scan_dir(choices)
        added = self.window.dir_checks[-1][0]
        self.assertIs(added.get_parent(), choices)
        self.assertTrue(added.get_active())
        card = choices.get_parent()
        children = card.get_children()
        choose = next(w for w in children if isinstance(w, Gtk.Button) and w.get_label() == '选择其他目录')
        self.assertLess(children.index(choices), children.index(choose))

    def test_platform_status_shows_specific_connection_state(self):
        self.store.set_setting('bilibili_cookies', True)
        text = lambda: self.window.nav_buttons['platform-bilibili'].get_child().get_children()[1].get_text()
        for state, expected in [('checking', '验证中'), ('connected', '已连接'), ('unknown', '无法验证'), ('expired', '需重连')]:
            self.window.platform_status('bilibili', state)
            self.assertIn(expected, text())
        self.store.set_setting('bilibili_cookies', False)
        self.window.platform_status('bilibili')
        self.assertIn('未授权', text())

    def test_close_behavior_depends_on_download_state_and_preference(self):
        with mock.patch.object(self.store,'jobs',return_value=[]),mock.patch('mediadesk.app.Gtk.MessageDialog') as dialog:
            self.assertFalse(self.window.on_close())
            dialog.assert_not_called()
        with mock.patch.object(self.store,'jobs',return_value=[{'state':'下载中'}]),mock.patch('mediadesk.app.Gtk.MessageDialog') as dialog,mock.patch.object(self.window,'iconify') as iconify:
            dialog.return_value.run.return_value=Gtk.ResponseType.ACCEPT
            self.assertTrue(self.window.on_close());iconify.assert_called_once()
            dialog.return_value.run.return_value=Gtk.ResponseType.CANCEL
            self.assertTrue(self.window.on_close())
            dialog.return_value.run.return_value=Gtk.ResponseType.YES
            self.assertFalse(self.window.on_close())
            self.store.set_setting('close_behavior','minimize');dialog.reset_mock();iconify.reset_mock()
            self.assertTrue(self.window.on_close());iconify.assert_called_once();dialog.assert_not_called()
            self.store.set_setting('close_behavior','exit');iconify.reset_mock()
            self.assertFalse(self.window.on_close());iconify.assert_not_called()

    def test_close_paused_task_and_unavailable_status_are_explained(self):
        with mock.patch.object(self.store,'jobs',return_value=[{'state':'暂停'}]),mock.patch('mediadesk.app.Gtk.MessageDialog') as dialog:
            dialog.return_value.run.return_value=Gtk.ResponseType.CANCEL
            self.assertTrue(self.window.on_close())
            self.assertIn('暂停',dialog.return_value.format_secondary_text.call_args.args[0])
        with mock.patch.object(self.store,'jobs',side_effect=OSError('database unavailable')),mock.patch('mediadesk.app.Gtk.MessageDialog') as dialog:
            dialog.return_value.run.return_value=Gtk.ResponseType.CANCEL
            self.assertTrue(self.window.on_close())
            self.assertIn('无法读取下载状态',dialog.return_value.format_secondary_text.call_args.args[0])

    def test_playback_shortcut_respects_focus_modifiers_and_repeat(self):
        from types import SimpleNamespace
        click = mock.Mock(); player = SimpleNamespace(closed=False, toggle=Gtk.Button(), close=lambda: None)
        player.toggle.connect('clicked', lambda *_: click())
        event = lambda key, state=0: SimpleNamespace(keyval=key, state=state)
        with mock.patch.object(self.window, 'get_focus', return_value=None):
            self.assertFalse(self.window.on_key(None,event(Gdk.KEY_space)))
            self.window.player=player
            self.assertFalse(self.window.on_key(None,event(Gdk.KEY_space,Gdk.ModifierType.CONTROL_MASK)))
            self.assertTrue(self.window.on_key(None,event(Gdk.KEY_space)))
            self.assertTrue(self.window.on_key_release(None,event(Gdk.KEY_space)))
            self.assertTrue(self.window.on_key(None,event(Gdk.KEY_space)))
            click.assert_called_once()
            self.window.on_key_release(None,event(Gdk.KEY_space))
            self.assertTrue(spin_until(lambda: not self.window.shortcut_pressed, .5))
            self.assertTrue(self.window.on_key(None,event(Gdk.KEY_space)))
            self.assertEqual(click.call_count,2)
            self.window.reset_shortcut()
            self.store.set_setting('playback_shortcut','k')
            self.assertFalse(self.window.on_key(None,event(Gdk.KEY_space)))
            self.assertTrue(self.window.on_key(None,event(Gdk.KEY_k)))
            self.window.reset_shortcut();self.store.set_setting('playback_shortcut','off')
            self.assertFalse(self.window.on_key(None,event(Gdk.KEY_space)))
        self.store.set_setting('playback_shortcut','space')
        for focus in (Gtk.Entry(), Gtk.TextView(), Gtk.Button(), Gtk.Scale()):
            with mock.patch.object(self.window,'get_focus',return_value=focus):
                self.assertFalse(self.window.on_key(None,event(Gdk.KEY_space)))
        with mock.patch.object(self.window,'get_focus',return_value=player.toggle):
            self.assertTrue(self.window.on_key(None,event(Gdk.KEY_space)))
        self.window.reset_shortcut()
        self.window.player=None
        with mock.patch.object(self.window,'toggle_fullscreen') as full:
            self.window.fullscreened=True
            self.assertTrue(self.window.on_key(None,event(Gdk.KEY_Escape)))
            full.assert_called_once()

    def test_playback_start_transfers_focus_only_from_start_button(self):
        self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw','title':'test'})
        self.window.show_all();self.window.show_library();self.window.open_row(0)
        self.window.start_button.grab_focus()
        with mock.patch('mediadesk.app.Player.open_stream'):
            self.window.open_player(None,{'url':'https://example.invalid/test','user_agent':''})
        self.assertIs(self.window.get_focus(),self.window.player.toggle)

    def test_shortcut_setting_persists(self):
        self.store.set_setting('playback_shortcut','k')
        with mock.patch.object(self.window,'check_account'):
            self.window.show_settings()
        def descendants(widget):
            yield widget
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children(): yield from descendants(child)
        combo=next(w for w in descendants(self.window) if isinstance(w,Gtk.ComboBoxText) and w.get_active_id()=='k')
        combo.set_active_id('off');self.assertEqual(self.store.setting('playback_shortcut'),'off')
        with mock.patch.object(self.window,'check_account'):self.window.show_settings()
        self.assertTrue(any(isinstance(w,Gtk.ComboBoxText) and w.get_active_id()=='off' for w in descendants(self.window)))

    def test_close_event_and_setting_are_connected(self):
        with mock.patch.object(self.window,'check_account'):
            self.window.show_settings()
        def descendants(widget):
            yield widget
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():yield from descendants(child)
        choices=[w for w in descendants(self.window) if isinstance(w,Gtk.ComboBoxText)]
        close_choice=next(w for w in choices if w.get_active_id()=='ask')
        close_choice.set_active_id('minimize')
        self.assertEqual(self.store.setting('close_behavior'),'minimize')
        with mock.patch.object(self.store,'jobs',return_value=[{'state':'等待'}]),mock.patch.object(self.window,'iconify') as iconify:
            self.assertTrue(self.window.emit('delete-event',Gdk.Event.new(Gdk.EventType.DELETE)))
            iconify.assert_called_once()

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
                self.window.view_buttons['details'].set_active(True)
                release.set()
                self.assertTrue(spin_until(lambda: len(self.window.rows) == 2))
                self.assertTrue(spin_until(lambda: self.window.rows_count.get_text() == '2 项'))
                self.assertEqual(len(self.store.media()), 2)
                self.assertEqual(self.window.media_view, 'details')
                self.assertEqual(len(self.window.rows_box.get_children()), 2)
        finally:
            release.set()

    def test_cover_adapts_and_preserves_image_ratio(self):
        path = self.temp.name + '/cover.png'
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 400, 400)
        pixbuf.fill(0x557788ff)
        pixbuf.savev(path, 'png', [], [])
        cover = MediaCover(); cover.set_cover(path)
        self.assertTrue(cover.get_overlay_pass_through(cover.image))
        self.assertTrue(cover.frame.get_style_context().has_class('has-cover'))
        allocation = Gdk.Rectangle()
        allocation.width, allocation.height = 320, 180
        cover.resize_cover(cover.frame, allocation)
        self.assertTrue(spin_until(lambda: cover.frame.get_size_request().height == 180))
        self.assertEqual(cover.image_size, (180, 180))
        allocation.width = 200
        cover.resize_cover(cover.frame, allocation)
        self.assertTrue(spin_until(lambda: cover.frame.get_size_request().height == 112))
        self.assertEqual(cover.image_size, (112, 112))

    def test_library_cover_allocation_stays_16_9_when_window_resizes(self):
        path = self.temp.name + '/wide-cover.png'
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 640, 360)
        pixbuf.fill(0x557788ff); pixbuf.savev(path, 'png', [], [])
        rows = [{'title': f'测试视频 {i}', 'source': 'youtube', 'thumbnail': 'test'} for i in range(6)]
        self.window.resize(1120, 760)
        with mock.patch.object(self.window, 'load_art', side_effect=lambda widget, _: widget.set_cover(path)):
            self.window.display_rows('测试媒体库', rows)
        def descendants(widget):
            yield widget
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children(): yield from descendants(child)
        covers = [w for w in descendants(self.window.rows_box) if isinstance(w, MediaCover)]
        self.assertEqual(len(covers), 6)
        def fitted():
            allocations = [cover.frame.get_allocation() for cover in covers]
            return all(a.width >= 190 and abs(a.height - round(a.width * 9 / 16)) <= 1 and cover.image_size[0] <= a.width and cover.image_size[1] <= a.height for a, cover in zip(allocations, covers))
        self.assertTrue(spin_until(fitted), '封面实际大小应保持 16:9')
        self.window.resize(700, 760)
        self.assertTrue(spin_until(lambda: self.window.get_allocated_width() < 900 and fitted()), '调整窗口后封面仍应保持 16:9')
        self.window.resize(1120, 760)
        self.assertTrue(spin_until(lambda: self.window.get_allocated_width() >= 1120 and fitted()), '恢复窗口宽度后封面仍应保持 16:9')

    def test_hover_preview_plays_local_frames_and_cleans_up(self):
        import subprocess
        path = self.temp.name + '/preview.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=5', '-t', '4', '-c:v', 'mpeg4', '-y', path], check=True)
        self.window.display_rows('测试', [{'title': '测试', 'source': 'local', 'path': path}])
        button = self.window.rows_box.get_children()[0].get_child()
        cover = button.get_child().get_children()[0]
        preview = self.window.hover_preview
        preview.cover = cover; preview.item = {'path': path}
        preview.start(preview.serial)
        self.assertTrue(spin_until(lambda: cover.image.get_pixbuf() is not None, 5))
        self.assertIsNotNone(preview.process)
        preview.stop()
        self.assertIsNone(preview.process)
        self.assertIsNone(cover.image.get_pixbuf())
        self.assertIsNone(preview.cover)

    def test_hover_preview_discards_stale_online_resolution(self):
        started, release = threading.Event(), threading.Event()
        preview = self.window.hover_preview
        first, second = MediaCover(), MediaCover()
        def resolve(url, cookies, cancel):
            if url.endswith('first'):
                started.set(); release.wait(3)
            return {'url': url}
        try:
            with mock.patch('mediadesk.preview.downloader.online_stream', side_effect=resolve), mock.patch.object(preview, 'play') as play:
                preview.cover = first; preview.item = {'url': 'https://example.test/first'}
                preview.start(preview.serial)
                self.assertTrue(started.wait(2))
                preview.stop(); preview.cover = second; preview.item = {'url': 'https://example.test/second'}
                preview.start(preview.serial); release.set()
                self.assertTrue(spin_until(lambda: play.called))
                self.assertEqual(play.call_count, 1)
                self.assertEqual(play.call_args.args[1]['url'], 'https://example.test/second')
        finally:
            release.set(); preview.stop()

    def test_online_preview_cancel_reaps_resolver(self):
        import os, sys
        from pathlib import Path
        pidfile=Path(self.temp.name)/'resolver.pid';script=Path(self.temp.name)/'resolver.py'
        script.write_text("import os,time\nopen("+repr(str(pidfile))+",'a').write(str(os.getpid())+'\\n')\ntime.sleep(60)\n")
        preview=self.window.hover_preview;preview.cover=MediaCover();preview.item={'url':'https://youtu.be/jNQXAC9IVRw'}
        with mock.patch('mediadesk.downloader.command',return_value=[sys.executable,str(script)]):
            preview.start(preview.serial)
            self.assertTrue(spin_until(pidfile.exists,3))
            first=int(pidfile.read_text().splitlines()[0]);preview.stop()
            preview.cover=MediaCover();preview.item={'url':'https://youtu.be/dQw4w9WgXcQ'};preview.start(preview.serial)
            self.assertTrue(spin_until(lambda:len(pidfile.read_text().splitlines())>=2,3))
            second=int(pidfile.read_text().splitlines()[1])
            with self.assertRaises(ProcessLookupError):os.kill(first,0)
            preview.stop();self.assertTrue(spin_until(lambda:not preview.resolving,3))
            with self.assertRaises(ProcessLookupError):os.kill(second,0)

    def test_preview_cancel_stops_resolver_process_group(self):
        import sys
        from pathlib import Path
        pidfile=Path(self.temp.name)/'group.pid';script=Path(self.temp.name)/'group.py'
        script.write_text("import os,subprocess,sys,time\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\nopen("+repr(str(pidfile))+",'w').write(str(p.pid))\ntime.sleep(60)\n")
        preview=self.window.hover_preview;preview.cover=MediaCover();preview.item={'url':'https://youtu.be/jNQXAC9IVRw'}
        with mock.patch('mediadesk.downloader.command',return_value=[sys.executable,str(script)]):
            preview.start(preview.serial);self.assertTrue(spin_until(pidfile.exists,3))
            child=int(pidfile.read_text());preview.stop()
            self.assertTrue(spin_until(lambda:not preview.resolving,3))
            def child_not_running():
                stat=Path(f'/proc/{child}/stat')
                return not stat.exists() or stat.read_text().split()[2]=='Z'
            self.assertTrue(spin_until(child_not_running,3))

    def test_cancelled_resolution_does_not_spawn_process(self):
        from mediadesk import downloader
        cancel=threading.Event();cancel.set()
        with mock.patch('mediadesk.downloader.subprocess.Popen') as spawn:
            with self.assertRaises(InterruptedError):downloader._run_cancellable(['unused'],cancel,1)
            spawn.assert_not_called()

    def test_resolver_drains_pipes_and_stops_descendant_after_leader_exit(self):
        import sys
        from mediadesk import downloader
        from mediadesk.preview import PreviewCancellation
        script="import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);sys.stdout.write('x'*200000);sys.stderr.write('y'*200000)"
        result=downloader._run_cancellable([sys.executable,'-c',script],PreviewCancellation(),5)
        self.assertEqual(result.returncode,0)
        self.assertEqual(len(result.stdout),200000);self.assertEqual(len(result.stderr),200000)

    def test_cancel_waits_for_reap_and_never_signals_reaped_pid(self):
        import os,sys
        from mediadesk import downloader
        from mediadesk.preview import PreviewCancellation
        cancel=PreviewCancellation();reaped=threading.Event();release=threading.Event();result=[]
        real_finish=downloader.finish_process;real_kill=os.killpg
        def finish(proc):
            value=real_finish(proc);reaped.set();release.wait(3);return value
        def checked_kill(pid,sig):
            if reaped.is_set():raise AssertionError('不得向已回收的进程组发信号')
            return real_kill(pid,sig)
        def run():
            try:result.append(downloader._run_cancellable([sys.executable,'-c','print("done")'],cancel,3))
            except Exception as exc:result.append(exc)
        with mock.patch('mediadesk.downloader.finish_process',side_effect=finish),mock.patch('os.killpg',side_effect=checked_kill):
            worker=threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(reaped.wait(3));late=threading.Thread(target=cancel.set);late.start()
                self.assertTrue(late.is_alive());release.set();late.join(3);worker.join(3)
                self.assertFalse(late.is_alive());self.assertFalse(worker.is_alive())
                self.assertEqual(result[0].stdout.strip(),'done')
            finally:release.set();worker.join(3)

    def test_preview_wall_timeout_kills_stalled_decoder(self):
        import subprocess, sys
        from pathlib import Path
        script=Path(self.temp.name)/'stall.py';script.write_text('import time\ntime.sleep(60)\n')
        real_popen=subprocess.Popen
        preview=self.window.hover_preview;preview.cover=MediaCover()
        with mock.patch('mediadesk.preview.PREVIEW_WALL_SECONDS',.25), mock.patch('mediadesk.preview.subprocess.Popen',side_effect=lambda _args,**kwargs:real_popen([sys.executable,str(script)],**kwargs)):
            preview.play(preview.serial,{'path':'/tmp/example'})
            self.assertTrue(spin_until(lambda:preview.process is not None,2))
            proc=preview.process
            self.assertTrue(spin_until(lambda:preview.process is None,3))
            self.assertIsNotNone(proc.poll())
            self.assertTrue(spin_until(lambda:preview.cover is None,2))

    def test_search_hiding_cover_cancels_hover(self):
        self.window.select_nav('library');self.window.display_rows('全部内容',[{'title':'目标','source':'youtube','url':'https://youtu.be/jNQXAC9IVRw'}])
        cover=self.window.rows_box.get_children()[0].get_child().get_child().get_children()[0]
        preview=self.window.hover_preview;preview.cover=cover;preview.resolve_cancel=threading.Event();cancel=preview.resolve_cancel
        search=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.SearchEntry))
        search.set_text('不匹配')
        self.assertTrue(spin_until(cancel.is_set))
        self.assertIsNone(preview.cover)
        self.assertTrue(spin_until(lambda:not self.window.rows_box.get_children()[0].get_child_visible()))

    def test_detail_actions_reflow_with_window_width(self):
        self.window.resize(700, 760)
        self.window.display_rows('测试', [{'title': '测试视频', 'source': 'youtube', 'url': 'https://youtu.be/jNQXAC9IVRw'}])
        self.window.open_row(0)
        detail = self.window.detail_right.get_parent()
        self.assertTrue(spin_until(lambda: detail.get_orientation() == Gtk.Orientation.VERTICAL))
        self.window.resize(1120, 760)
        self.assertTrue(spin_until(lambda: detail.get_orientation() == Gtk.Orientation.HORIZONTAL))

    def test_library_expands_columns_at_wide_window_sizes(self):
        rows = [{'title': f'媒体测试 {i}：较长的视频标题', 'source': 'youtube'} for i in range(24)]
        self.window.resize(700, 760)
        self.window.display_rows('全部内容', rows)
        def columns():
            children = self.window.rows_box.get_children()
            y = children[0].get_allocation().y
            return sum(child.get_allocation().y == y for child in children)
        self.assertTrue(spin_until(lambda: self.window.get_allocated_width() < 900 and columns() == 1))
        self.window.resize(2560, 760)
        self.assertTrue(spin_until(lambda: self.window.get_allocated_width() >= 2560 and columns() == 4))
        self.window.view_buttons['list'].set_active(True)
        self.assertTrue(spin_until(lambda: columns() == 1))
        self.window.view_buttons['grid'].set_active(True)
        self.assertTrue(spin_until(lambda: columns() == 4))
        self.window.resize(3200, 760)
        self.assertTrue(spin_until(lambda: self.window.get_allocated_width() >= 3200 and columns() > 4))
        self.window.resize(700, 760)
        self.assertTrue(spin_until(lambda: self.window.get_allocated_width() < 900 and columns() == 1))

    def test_media_view_switch_keeps_filter_and_detail_navigation(self):
        for url, title in [('https://youtu.be/jNQXAC9IVRw', '搜索 样例一'), ('https://youtu.be/dQw4w9WgXcQ', '其他内容'), ('https://youtu.be/9bZkp7q19f0', '搜索 样例二')]:
            self.store.save_youtube({'url': url, 'title': title})
        self.window.show_library()
        search = next(w for w in self.window.content.get_children() if isinstance(w, Gtk.SearchEntry))
        search.set_text('搜索')
        self.assertTrue(spin_until(lambda: sum(child.get_child_visible() for child in self.window.rows_box.get_children()) == 2))
        for mode, name in (('list', '列表视图'), ('details', '详细视图'), ('grid', '网格视图')):
            control = self.window.view_buttons[mode]
            self.assertEqual(control.get_tooltip_text(), name)
            self.assertEqual(control.get_accessible().get_name(), name)
            control.clicked()
            self.assertTrue(control.get_active())
            self.assertEqual(self.store.setting('media_view'), mode)
            self.assertEqual(search.get_text(), '搜索')
            self.assertTrue(spin_until(lambda: sum(child.get_child_visible() for child in self.window.rows_box.get_children()) == 2))
        self.window.view_buttons['details'].set_active(True)
        header = self.window.sort_buttons['duration'][0].get_parent()
        self.assertTrue(header.get_visible())
        self.assertTrue(all(child.get_visible() for child in header.get_children()))
        visible = next(child for child in self.window.rows_box.get_children() if child.get_child_visible())
        visible.get_child().clicked()
        self.window.return_rows()
        self.assertEqual(self.window.media_view, 'details')
        self.assertEqual(self.window.rows_query, '搜索')

    def test_library_platform_filter_and_sorted_detail_navigation(self):
        rows = [
            {'title':'Z 视频', 'source':'youtube', 'channel':'测试', 'duration':20},
            {'title':'丙视频', 'source':'bilibili', 'channel':'测试', 'duration':10},
            {'title':'A 视频', 'source':'youtube', 'channel':'测试', 'duration':None},
            {'title':'本地视频', 'source':'local', 'channel':'其他', 'duration':5},
        ]
        self.window.select_nav('library');self.window.display_rows('全部内容', rows)
        self.window.view_buttons['details'].clicked()
        visible=lambda:[c.row_index for c in self.window.rows_box.get_children() if c.get_child_visible()]
        self.window.sort_buttons['source'][0].clicked()
        self.assertEqual(visible(),[1,3,0,2])
        self.window.sort_buttons['duration'][0].clicked()
        self.assertEqual(visible(),[3,1,0,2])
        self.window.sort_buttons['duration'][0].clicked()
        self.assertEqual(visible(),[0,1,3,2])
        self.window.source_buttons['youtube'].clicked()
        self.assertTrue(spin_until(lambda:visible()==[0,2]))
        self.window.sort_buttons['duration'][0].clicked()
        self.assertEqual(visible(),[0,2])
        self.window.sort_buttons['duration'][0].clicked()
        self.assertEqual(visible(),[0,2], '未知时长应始终排在最后')
        self.window.sort_buttons['title'][0].clicked()
        self.assertEqual(visible(),[2,0])
        self.assertIn('升序',self.window.sort_buttons['title'][0].get_accessible().get_name())
        self.window.rows_box.get_children()[0].get_child().clicked()
        self.assertEqual(self.window.row_index,2)
        next_button = next(w for w in self.window.detail_nav.get_children() if w.get_tooltip_text() == '下一条')
        self.assertTrue(next_button.get_sensitive());next_button.clicked()
        self.assertEqual(self.window.row_index,0)
        self.window.display_rows('全部内容', rows)
        self.assertTrue(self.window.source_buttons['youtube'].get_active())
        self.assertEqual(visible(),[2,0])
        search=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.SearchEntry))
        search.set_text('Z 视频')
        self.assertTrue(spin_until(lambda:visible()==[0]))
        self.window.source_buttons['bilibili'].clicked()
        self.assertTrue(spin_until(lambda:visible()==[]))
        self.assertTrue(any(isinstance(w,Gtk.Label) and w.get_text()=='没有匹配的内容。' and w.get_visible() for w in self.window.content.get_children()))

    def test_detail_status_sort_uses_visible_status_order(self):
        from pathlib import Path
        path=Path(self.temp.name)/'present.mp4';path.write_bytes(b'')
        rows=[{'title':'未下载','source':'youtube'}, {'title':'缺失','source':'local','path':self.temp.name+'/missing'}, {'title':'可用','source':'local','path':str(path)}, {'title':'失效','source':'bilibili','unavailable':True}]
        self.window.select_nav('library');self.window.display_rows('全部内容',rows)
        self.window.view_buttons['details'].clicked()
        visible=lambda:[c.row_index for c in self.window.rows_box.get_children() if c.get_child_visible()]
        with mock.patch('mediadesk.app.Path.is_file',side_effect=AssertionError('排序比较不得再次访问磁盘')):
            self.window.sort_buttons['state'][0].clicked();self.assertEqual(visible(),[2,0,1,3])
            self.window.sort_buttons['state'][0].clicked();self.assertEqual(visible(),[3,1,0,2])

    def test_media_context_menu_matches_item_state_and_routes_actions(self):
        from pathlib import Path
        path=Path(self.temp.name)/'present.mp4';path.write_bytes(b'')
        rows=[{'title':'在线','source':'youtube','url':'https://youtu.be/jNQXAC9IVRw'}, {'title':'本地','source':'local','path':str(path)}, {'title':'失效','source':'bilibili','url':'https://www.bilibili.com/video/BV1bK411W797','unavailable':True}]
        self.window.select_nav('library');self.window.display_rows('全部内容',rows);self.window.show_all()
        for view in ('grid','list','details'):
            self.window.view_buttons[view].set_active(True)
            for idx,expected in [(0,['播放','查看详情','下载','选择下载格式','复制来源链接']),(1,['播放','查看详情','打开所在文件夹']),(2,['查看详情','复制来源链接'])]:
                widget=next(c for c in self.window.rows_box.get_children() if c.row_index==idx).get_child()
                self.assertTrue(widget.emit('popup-menu'))
                menu=self.window.media_context_menu;self.assertEqual([x.get_label() for x in menu.get_children()],expected)
                if idx==0:
                    with mock.patch.object(self.window,'prepare_download') as download:
                        next(x for x in menu.get_children() if x.get_label()=='下载').activate()
                        self.assertEqual(download.call_args.args[0]['title'],'在线')
                menu.popdown()

    def test_mouse_context_download_creates_task(self):
        import ctypes
        import ctypes.util
        x11_path, xtst_path = ctypes.util.find_library('X11'), ctypes.util.find_library('Xtst')
        if not x11_path or not xtst_path: self.skipTest('需要 X11 和 XTest')
        x11, xtst = ctypes.CDLL(x11_path), ctypes.CDLL(xtst_path)
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]; x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]; x11.XFlush.argtypes = [ctypes.c_void_p]
        xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        display = x11.XOpenDisplay(None)
        if not display: self.skipTest('无法打开 X11 显示')
        def click(x, y, button):
            xtst.XTestFakeMotionEvent(display, -1, x, y, 0)
            xtst.XTestFakeButtonEvent(display, button, 1, 0)
            xtst.XTestFakeButtonEvent(display, button, 0, 0)
            x11.XFlush(display)
        try:
            url = 'https://youtu.be/jNQXAC9IVRw'
            self.store.save_youtube({'url': url, 'title': '测试视频'})
            item = {'url': url, 'title': '测试视频'}
            with mock.patch('mediadesk.app.downloader.inspect', return_value=item) as inspect, mock.patch.object(self.window.downloader, 'start') as start:
                self.window.show_all(); self.window.show_library()
                self.assertTrue(spin_until(lambda: bool(self.window.rows_box.get_children())))
                card = self.window.rows_box.get_children()[0].get_child()
                self.assertTrue(spin_until(lambda: card.get_allocated_width() > 10))
                x, y = card.translate_coordinates(self.window, 0, 0)
                ox, oy = self.window.get_window().get_origin()[-2:]
                click(ox + x + card.get_allocated_width() // 2, oy + y + card.get_allocated_height() // 2, 3)
                self.assertTrue(spin_until(lambda: getattr(self.window, 'media_context_menu', None) and self.window.media_context_menu.get_visible()))
                menu = self.window.media_context_menu
                download = next(child for child in menu.get_children() if child.get_label() == '下载')
                self.assertTrue(spin_until(lambda: download.get_allocated_height() > 1))
                a = download.get_allocation(); mx, my = menu.get_window().get_origin()[-2:]
                click(mx + a.x + a.width // 2, my + a.y + a.height // 2, 1)
                self.assertTrue(spin_until(lambda: start.called), '鼠标选择下载后应创建任务')
                inspect.assert_called_once(); self.assertIn('加入任务', self.window.status.get_text())
        finally:
            x11.XCloseDisplay(display)

    def test_playback_uses_file_completed_after_detail_opened(self):
        from pathlib import Path
        url = 'https://www.bilibili.com/video/BV1QE411S71h?p=1'
        mid = self.store.save_source({'url': url, 'title': '测试视频'})
        self.window.show_library(); self.window.open_row(0)
        local_path = Path(self.temp.name) / 'video.mp4'; local_path.write_bytes(b'sample')
        self.store.set_path(mid, local_path)
        self.store.job('test-job', mid, '完成', local_path.name)
        self.window.download_update('test-job')
        self.assertEqual(self.window.start_button.get_tooltip_text(), '播放本地文件')
        with mock.patch.object(self.window, 'open_player') as local, mock.patch.object(self.window, 'open_online') as online:
            self.window.start_button.clicked()
            local.assert_called_once_with(str(local_path)); online.assert_not_called()

    def test_preview_uses_file_completed_after_card_rendered(self):
        from pathlib import Path
        mid = self.store.save_youtube({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': '测试视频'})
        item = self.store.get(mid); preview = self.window.hover_preview
        preview.cover = MediaCover(); preview.item = item
        local_path = Path(self.temp.name) / 'video.mp4'; local_path.write_bytes(b'sample')
        self.store.set_path(mid, local_path)
        with mock.patch.object(preview, 'play') as play, mock.patch.object(preview, 'resolve_next') as resolve:
            preview.start(preview.serial)
            play.assert_called_once_with(preview.serial, {'path': str(local_path)}); resolve.assert_not_called()
        preview.stop()

    def test_context_menu_uses_fresh_saved_item_and_direct_play(self):
        self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw','title':'保存的视频'})
        self.window.show_library();widget=self.window.rows_box.get_children()[0].get_child()
        self.assertTrue(widget.emit('popup-menu'))
        menu=self.window.media_context_menu
        self.assertIn('管理所属列表',[x.get_label() for x in menu.get_children()])
        with mock.patch.object(self.window,'open_player'),mock.patch.object(self.window,'open_online') as online:
            next(x for x in menu.get_children() if x.get_label()=='播放').activate()
            self.assertEqual(online.call_args.args[0]['title'],'保存的视频')
        menu.popdown()

    def test_details_columns_align_with_large_text_and_long_channel(self):
        settings=Gtk.Settings.get_default();old_dpi=settings.get_property('gtk-xft-dpi')
        try:
            settings.set_property('gtk-xft-dpi',147456);self.window.resize(700,760)
            self.window.display_rows('测试',[{'title':'中文排版测试：收藏、播放列表与下载任务','source':'youtube','channel':'中文 YouTube 作者频道','duration':321}])
            self.window.view_buttons['details'].set_active(True)
            row=self.window.rows_box.get_children()[0].get_child().get_child();fields=row.get_children()
            headers=[self.window.sort_buttons[k][0] for k in ('title','source','duration','state')]
            self.assertTrue(spin_until(lambda:fields[0].get_allocated_width()>=100))
            self.assertEqual([x.get_allocated_width() for x in fields[1:]],[x.get_allocated_width() for x in headers[1:]])
            self.assertEqual(fields[1].get_tooltip_text(),'YouTube · 中文 YouTube 作者频道')
            narrow_width=fields[1].get_allocated_width();self.window.resize(1500,760)
            self.assertTrue(spin_until(lambda:fields[1].get_allocated_width()>narrow_width))
            self.assertEqual(fields[1].get_allocated_width(),headers[1].get_allocated_width())
        finally:settings.set_property('gtk-xft-dpi',old_dpi)

    def test_media_list_views_show_channel_for_search_matches(self):
        self.store.save_youtube({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': '示例', 'channel': '测试频道'})
        self.window.show_library()
        search = next(w for w in self.window.content.get_children() if isinstance(w, Gtk.SearchEntry))
        search.set_text('测试频道')
        def descendants(widget):
            yield widget
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children(): yield from descendants(child)
        for mode in ('list', 'details'):
            self.window.view_buttons[mode].set_active(True)
            self.assertTrue(spin_until(lambda: any(child.get_child_visible() for child in self.window.rows_box.get_children())))
            labels = [w for w in descendants(self.window.rows_box) if isinstance(w, Gtk.Label)]
            self.assertTrue(any('测试频道' in w.get_text() and w.get_tooltip_text() for w in labels))

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

    def test_download_progress_represents_current_file(self):
        jobs = [
            {'id': 'one', 'media_id': 'a', 'title': '下载样例', 'state': '下载中', 'detail': '42.5%'},
            {'id': 'two', 'media_id': 'b', 'title': '失败样例', 'state': '失败', 'detail': '连接中断'},
            {'id': 'three', 'media_id': 'c', 'title': '完成样例', 'state': '完成', 'detail': ''},
        ]
        with mock.patch.object(self.window.downloader, 'reconcile', return_value=True), mock.patch.object(self.store, 'jobs', return_value=jobs), mock.patch.object(self.store, 'get', return_value=None):
            self.window.show_jobs()
        viewport = self.window.jobs_scroll.get_child()
        entries = viewport.get_child().get_children()
        details = [row.get_children()[0] for row in entries]
        bars = [w for w in details[0].get_children() if isinstance(w, Gtk.ProgressBar)]
        self.assertEqual(len(bars), 1)
        self.assertAlmostEqual(bars[0].get_fraction(), .425)
        self.assertEqual(bars[0].get_accessible().get_name(), '当前文件 42.5%')
        self.assertFalse(any(isinstance(w, Gtk.ProgressBar) for w in details[1].get_children()))
        self.assertFalse(any(isinstance(w, Gtk.ProgressBar) for w in details[2].get_children()))
        self.assertTrue(any(isinstance(w, Gtk.Label) and '连接中断' in w.get_text() for w in details[1].get_children()))
        while Gtk.events_pending(): Gtk.main_iteration()

    def test_local_detail_explains_play_action(self):
        path = self.store.media_dir / 'example.mp4'
        path.write_bytes(b'')
        self.store.save_local(path)
        self.window.show_library()
        self.window.open_row(0)
        self.assertEqual(self.window.start_button.get_tooltip_text(), '播放本地文件')
        self.assertEqual(self.window.start_button.get_accessible().get_name(), '播放本地文件')

    def test_player_toggle_keeps_primary_action_style(self):
        self.store.save_youtube({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': 'sample'})
        self.window.show_library();self.window.open_row(0)
        self.assertTrue(self.window.start_button.get_style_context().has_class('suggested-action'))
        with mock.patch('mediadesk.app.Player.open_stream'):
            self.window.open_player(None, {'url': 'https://example.invalid/test', 'user_agent': ''})
        self.assertTrue(self.window.player.toggle.get_style_context().has_class('suggested-action'))
        self.window.player._set_play_icon(True)
        self.assertTrue(self.window.player.toggle.get_style_context().has_class('suggested-action'))
        self.assertEqual(self.window.player.toggle.get_accessible().get_name(), '暂停')

    def test_player_layout_resizes_across_modes_and_window_sizes(self):
        self.window.resize(1800, 1000)
        self.store.save_youtube({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': 'sample', 'description': '介绍内容\n' * 30})
        self.window.show_library();self.window.open_row(0)
        with mock.patch('mediadesk.app.Player.open_stream'):
            self.window.open_player(None, {'url': 'https://example.invalid/test', 'user_agent': ''})
        area = self.window.player.area
        self.assertTrue(spin_until(lambda: area.get_allocated_width() > 1000 and area.get_allocated_height() > 500))
        normal_width, normal_height = area.get_allocated_width(), area.get_allocated_height()
        self.window.toggle_theater()
        self.assertTrue(spin_until(lambda: area.get_allocated_width() > normal_width))
        theater_height = area.get_allocated_height()
        self.window.toggle_fullscreen()
        self.assertTrue(spin_until(lambda: area.get_allocated_height() > theater_height))
        self.assertTrue(self.window.player.controls.get_visible())
        self.window.toggle_fullscreen();self.window.toggle_theater();self.window.resize(700, 700)
        self.assertTrue(spin_until(lambda: area.get_allocated_width() < normal_width and area.get_allocated_height() < normal_height))
        self.assertGreaterEqual(area.get_allocated_height(), 270)
        self.assertTrue(self.window.player.controls.get_visible())

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
            self.assertIn('已连接',self.window.nav_buttons['platform-bilibili'].get_child().get_children()[1].get_text())
        with mock.patch('mediadesk.app.bilibili.stream',side_effect=ValueError('网络不可用')):
            self.window.check_account('bilibili')
            self.assertTrue(spin_until(lambda:self.window.account_status_widgets['bilibili'].get_text().startswith('暂时无法验证')))
            self.assertIn('上次验证',self.window.account_status_widgets['bilibili'].get_text())
            self.assertIn('无法验证',self.window.nav_buttons['platform-bilibili'].get_child().get_children()[1].get_text())
        self.store.set_setting('bilibili_cookies',False);self.window.check_account('bilibili')
        self.assertIn('未授权',self.window.account_status_widgets['bilibili'].get_text())

    def test_follow_author_rows_open_matching_creator(self):
        self.store.set_setting('bilibili_cookies',True)
        youtube=[{'snippet':{'title':'YouTube 作者','resourceId':{'channelId':'UC_example-1'}}}, {'snippet':{'title':'缺少编号'}}]
        def bili(kind,on_page,fid=''):
            self.assertEqual(kind,'followings');on_page([{'mid':12345,'uname':'B 站作者'}])
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=youtube), mock.patch('mediadesk.app.bilibili.stream',side_effect=bili), mock.patch.object(self.window,'open_creator',create=True) as open_creator:
            self.window.show_discovery('follow')
            self.assertTrue(spin_until(lambda:len(self.window.discovery_box.get_children())==3))
            for platform,creator,name in [('youtube','UC_example-1','YouTube 作者'),('bilibili','12345','B 站作者')]:
                self.window.discovery_choice.set_active_id(platform)
                row=next(row for row in self.window.discovery_box.get_children() if row.get_tooltip_text()==f'查看 {name} 的视频')
                self.assertTrue(row.get_can_focus());self.assertTrue(row.get_activatable())
                self.assertTrue(row.get_style_context().has_class('discovery-author'))
                self.assertEqual(row.get_accessible().get_name(),name+'，查看视频')
                self.window.discovery_box.emit('row-activated',row);open_creator.assert_called_with(platform,creator,name)
            self.window.discovery_choice.set_active_id('youtube')
            unknown=next(row for row in self.window.discovery_box.get_children() if row.get_child().get_children()[0].get_text()=='缺少编号')
            self.assertFalse(unknown.get_activatable())
            self.assertEqual(open_creator.call_count,2)

    def test_follow_row_opens_real_local_creator_and_returns(self):
        self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw','title':'本机视频','channel':'作者 A'})
        youtube=[{'snippet':{'title':'作者 A','resourceId':{'channelId':'UC_A'}}}]
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=youtube):
            self.window.show_discovery('follow')
            self.assertTrue(spin_until(lambda:any(r.get_tooltip_text()=='查看 作者 A 的视频' for r in self.window.discovery_box.get_children())))
            row=next(r for r in self.window.discovery_box.get_children() if r.get_tooltip_text()=='查看 作者 A 的视频')
            self.window.discovery_box.emit('row-activated',row)
            self.assertEqual(self.window.source_kind,'creator-local')
            self.assertEqual([r['title'] for r in self.window.rows],['本机视频'])
            back=next(w for w in self.window.content.get_children() if isinstance(w,Gtk.Button) and w.get_label()=='← 返回关注')
            back.clicked();self.assertEqual(self.window.active_nav,'discover-follow')

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
            row=self.window.discovery_box.get_children()[0]
            with mock.patch.object(self.window,'load_bilibili') as open_folder:
                self.assertTrue(row.get_can_focus());self.assertTrue(row.get_activatable())
                self.window.discovery_box.emit('row-activated',row)
                open_folder.assert_called_once_with('favorites','7','B 站收藏')
            self.window.discovery_choice.set_active_id('youtube');self.assertEqual(len(self.window.discovery_box.get_children()),2)

    def test_settings_reuses_recent_account_status_and_manual_refresh_forces_request(self):
        self.store.set_setting('bilibili_cookies',True)
        def bili(kind,on_page,fid=''):on_page([{'name':'B 站用户'}])
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[{'snippet':{'title':'YouTube 用户'}}]) as yt,mock.patch('mediadesk.app.bilibili.stream',side_effect=bili) as bs:
            self.window.show_settings()
            self.assertTrue(spin_until(lambda: all(self.window.account_status_widgets[x].get_text().startswith('已连接') for x in ('youtube','bilibili'))))
            self.window.show_library();self.window.show_settings()
            self.assertTrue(self.window.account_status_widgets['youtube'].get_text().startswith('已连接'))
            self.assertEqual((yt.call_count,bs.call_count),(1,1))
            self.window.check_account('youtube')
            self.assertTrue(spin_until(lambda:yt.call_count==2))

    def test_disconnect_youtube_preserves_shared_token_and_blocks_account_reads(self):
        from pathlib import Path
        config = Path(self.temp.name) / 'shared'; config.mkdir()
        token = config / 'token.json'; token.write_text('shared-token')
        self.store.save_youtube({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': 'saved'})
        with mock.patch.dict('os.environ', {'MEDIADESK_GOOGLE_CONFIG': str(config)}), mock.patch('mediadesk.app.sources.list_youtube', return_value=[{'snippet': {'title': 'test'}}]) as fetch:
            self.window.show_settings()
            self.assertTrue(spin_until(lambda: self.window.youtube_disconnect_button.get_visible()))
            with mock.patch('mediadesk.app.Gtk.MessageDialog') as dialog:
                dialog.return_value.run.return_value = Gtk.ResponseType.CANCEL
                self.window.disconnect_youtube();self.assertTrue(self.store.setting('youtube_account_enabled', True))
                dialog.return_value.run.return_value = Gtk.ResponseType.OK
                self.window.disconnect_youtube()
            self.assertEqual(token.read_text(), 'shared-token')
            self.assertFalse(self.store.setting('youtube_account_enabled', True))
            self.assertTrue(self.window.youtube_connect_button.get_visible())
            self.assertFalse(self.window.youtube_disconnect_button.get_visible())
            fetch.reset_mock();self.window.check_account('youtube');self.window.load_source('likes')
            self.assertFalse(fetch.called)
            self.assertTrue(any(row['title'] == 'saved' for row in self.store.media()))
            self.window.authorize()
            self.assertTrue(spin_until(lambda: self.store.setting('youtube_account_enabled', False)))

    def test_youtube_disconnect_ignores_late_authorization(self):
        entered = threading.Event();release = threading.Event()
        def fetch(kind,*args):
            if kind == 'auth':entered.set();release.wait(3)
            return [{'snippet': {'title': 'test'}}]
        with mock.patch('mediadesk.app.sources.list_youtube', side_effect=fetch):
            self.window.show_settings();self.assertTrue(spin_until(lambda:self.window.youtube_disconnect_button.get_visible()))
            self.window.authorize();self.assertTrue(entered.wait(2))
            with mock.patch('mediadesk.app.Gtk.MessageDialog') as dialog:
                dialog.return_value.run.return_value=Gtk.ResponseType.OK
                self.window.disconnect_youtube()
            release.set();spin_until(lambda:False,.15)
            self.assertFalse(self.store.setting('youtube_account_enabled',True))
            self.assertEqual(self.window.account_status_widgets['youtube'].get_text(),'已断开')

    def test_bilibili_connect_and_disconnect_preserve_separate_cookie_permission(self):
        self.store.set_setting('cookies',True)
        with mock.patch('mediadesk.app.sources.list_youtube',side_effect=ValueError('需要连接 YouTube 账号')), mock.patch('mediadesk.app.bilibili.stream') as stream:
            self.window.show_settings()
            self.assertEqual(self.window.bilibili_connect_button.get_label(),'连接 B 站')
            with mock.patch('mediadesk.app.Gtk.MessageDialog') as dialog:
                dialog.return_value.run.return_value=Gtk.ResponseType.OK
                self.window.toggle_bilibili_account()
                self.assertTrue(self.store.setting('bilibili_cookies',False))
                self.assertEqual(self.window.bilibili_connect_button.get_label(),'断开连接')
                self.window.toggle_bilibili_account()
            self.assertFalse(self.store.setting('bilibili_cookies',True))
            self.assertTrue(self.store.setting('cookies',False))
            self.assertEqual(self.window.bilibili_connect_button.get_label(),'连接 B 站')

    def test_youtube_connect_action_matches_verified_state(self):
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[{'snippet':{'title':'YouTube 用户'}}]):
            self.window.show_settings()
            self.assertTrue(spin_until(lambda:self.window.account_status_widgets['youtube'].get_text().startswith('已连接')))
            self.assertFalse(self.window.youtube_connect_button.get_visible())
            self.window.show_library();self.window.show_settings()
            self.assertFalse(self.window.youtube_connect_button.get_visible())
        with mock.patch('mediadesk.app.sources.list_youtube',side_effect=ValueError('HTTP 401')):
            self.window.check_account('youtube')
            self.assertTrue(spin_until(lambda:self.window.account_status_widgets['youtube'].get_text().startswith('需要重新连接')))
            self.assertTrue(self.window.youtube_connect_button.get_visible())
            self.assertEqual(self.window.youtube_connect_button.get_label(),'尝试连接 Google 账号')
        with mock.patch('mediadesk.app.sources.list_youtube',side_effect=ValueError('网络不可用')):
            self.window.check_account('youtube')
            self.assertTrue(spin_until(lambda:self.window.account_status_widgets['youtube'].get_text().startswith('暂时无法验证')))
            self.assertFalse(self.window.youtube_connect_button.get_visible())
        with mock.patch.dict('os.environ',{'MEDIADESK_GOOGLE_CONFIG':self.temp.name}),mock.patch('mediadesk.app.sources.list_youtube',side_effect=ValueError('需要连接 YouTube 账号')):
            self.window.check_account('youtube')
            self.assertTrue(spin_until(lambda:self.window.account_status_widgets['youtube'].get_text().startswith('未连接')))
            self.assertTrue(self.window.youtube_connect_button.get_visible())
            self.assertEqual(self.window.youtube_connect_button.get_label(),'连接 Google 账号')

    def test_collection_rows_open_youtube_likes_and_playlist(self):
        youtube=[{'id':'playlist-id','snippet':{'title':'我的播放列表'}}]
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=youtube), mock.patch.object(self.window,'load_source') as load:
            self.window.show_discovery('collections')
            self.assertTrue(spin_until(lambda:len(self.window.discovery_box.get_children())>=2))
            self.window.discovery_choice.set_active_id('youtube')
            rows=self.window.discovery_box.get_children()
            self.assertEqual(len(rows),2)
            for row in rows:
                self.assertTrue(row.get_can_focus());self.assertTrue(row.get_activatable())
                self.assertTrue(row.get_style_context().has_class('discovery-author'))
                self.window.discovery_box.emit('row-activated',row)
            self.assertEqual(load.call_args_list,[mock.call('likes'),mock.call('playlist-items','playlist-id')])

    def test_collection_rows_open_actual_content_in_app(self):
        self.store.set_setting('bilibili_cookies',True)
        def bili(kind,on_page,fid=''):
            if kind=='folders':on_page([{'id':7,'title':'收藏夹'}])
            elif kind=='favorites':
                self.assertEqual(fid,'7');on_page([{'id':1,'type':2,'title':'B 视频','bv_id':'BV1bK411W797'}])
            else:self.fail('unexpected B 站 request')
        def youtube_stream(kind,on_page,playlist_id=''):
            self.assertEqual(kind,'likes');on_page([{'id':'jNQXAC9IVRw','snippet':{'title':'喜欢的视频'}}])
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[]), mock.patch('mediadesk.app.sources.stream_youtube',side_effect=youtube_stream), mock.patch('mediadesk.app.bilibili.stream',side_effect=bili):
            self.window.show_discovery('collections')
            self.assertTrue(spin_until(lambda:len(self.window.discovery_box.get_children())==2))
            self.window.discovery_choice.set_active_id('youtube')
            self.window.discovery_box.emit('row-activated',self.window.discovery_box.get_children()[0])
            self.assertTrue(spin_until(lambda:len(self.window.rows)==1))
            self.assertEqual(self.window.rows_title,'喜欢的视频');self.assertEqual(self.window.rows[0]['title'],'喜欢的视频')
            self.window.show_discovery('collections')
            self.assertTrue(spin_until(lambda:len(self.window.discovery_box.get_children())==2))
            self.window.discovery_choice.set_active_id('bilibili')
            self.window.discovery_box.emit('row-activated',self.window.discovery_box.get_children()[0])
            self.assertTrue(spin_until(lambda:len(self.window.rows)==1 and self.window.rows_title=='收藏夹'))
            self.assertEqual(self.window.rows[0]['title'],'B 视频')

    def test_discovery_shows_partial_results_after_page_failure(self):
        self.store.set_setting('bilibili_cookies',True)
        def bili(kind,on_page,fid=''):
            on_page([{'id':7,'title':'已读取收藏夹'}]);raise ValueError('网络中断')
        with mock.patch('mediadesk.app.sources.list_youtube',return_value=[]),mock.patch('mediadesk.app.bilibili.stream',side_effect=bili):
            self.window.show_discovery('collections')
            self.assertTrue(spin_until(lambda:'读取未完成：网络中断' in self.window.discovery_status.get_text()))
            self.assertEqual(len(self.window.discovery_box.get_children()),2)

    def test_reopening_settings_reuses_inflight_account_check(self):
        entered,release=threading.Event(),threading.Event()
        def youtube(kind):
            entered.set();release.wait(3);return [{'snippet':{'title':'YouTube 用户'}}]
        try:
            with mock.patch('mediadesk.app.sources.list_youtube',side_effect=youtube) as yt:
                self.window.show_settings();self.assertTrue(entered.wait(2))
                self.window.show_library();self.window.show_settings();self.assertEqual(yt.call_count,1)
                release.set()
                self.assertTrue(spin_until(lambda:self.window.account_status_widgets['youtube'].get_text().startswith('已连接')))
        finally:release.set()

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
