"""Synthetic local OPML UI checks; no account, OPML export or network access."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
import gi
gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0')
from gi.repository import Gtk,Gdk
from mediadesk.app import App
from mediadesk.store import Store
from tests.test_desktop import spin_until

@unittest.skipUnless(Gdk.Display.get_default(),'需要 X11 或 Xvfb')
class XiaoyuzhouUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.store.set_setting('setup_done',True);self.w=App(self.store);self.w.show_xiaoyuzhou()
    def tearDown(self):
        self.w.destroy();spin_until(lambda:not Gtk.events_pending(),.2);self.tmp.cleanup()
    def test_reimport_preserves_confirmed_and_absent_entries(self):
        match={'title':'频道','url':'https://www.youtube.com/channel/UCtest','kind':'channel','confirmed':True}
        self.store.set_setting('xiaoyuzhou_programs',[{'title':'旧名称','feed_url':'https://example.org/feed','match':match},{'title':'缺席节目','feed_url':'https://example.org/absent'}])
        path=Path(self.tmp.name)/'synthetic.opml';path.write_text('<opml><body><outline title="新名称" xmlUrl="https://example.org/feed"/></body></opml>')
        self.w.import_xiaoyuzhou_opml(str(path));self.assertTrue(spin_until(lambda:'导入完成' in self.w.xiaoyuzhou_status.get_text(),3))
        programs=self.w.xiaoyuzhou_programs();self.assertEqual(len(programs),2);self.assertEqual(programs[0]['match'],match);self.assertEqual(programs[0]['title'],'新名称')
    def test_search_is_explicit_background_and_confirmation_is_separate(self):
        program={'title':'合成节目','feed_url':'https://example.org/feed'};self.store.set_setting('xiaoyuzhou_programs',[program]);candidate={'title':'合成候选','url':'https://www.youtube.com/playlist?list=PLtest','kind':'playlist','channel':'测试'}
        entered=threading.Event();release=threading.Event()
        def search(title,**kwargs):
            entered.set();release.wait(3);return {'candidates':[candidate]}
        with mock.patch('mediadesk.xiaoyuzhou_import.search_youtube_candidates',side_effect=search) as fetch:
            self.w.show_xiaoyuzhou();fetch.assert_not_called();self.w.search_xiaoyuzhou(program);self.assertTrue(entered.wait(2));self.assertNotIn('match',self.w.xiaoyuzhou_programs()[0]);release.set()
            self.assertTrue(spin_until(lambda:'1 个候选' in self.w.xiaoyuzhou_status.get_text(),3));fetch.assert_called_once_with('合成节目',user_triggered=True)
            self.w.confirm_xiaoyuzhou_match(program,candidate);self.assertTrue(self.w.xiaoyuzhou_programs()[0]['match']['confirmed'])
        with mock.patch('mediadesk.app.Gio.AppInfo.launch_default_for_uri') as launch:
            for url in ('https://www.youtube.com/channel/UCtest','https://www.youtube.com/playlist?list=PLtest','https://www.youtube.com/watch?v=test'):
                self.w.open_xiaoyuzhou_match({'url':url});launch.assert_called_with(url,None)
            self.w.open_xiaoyuzhou_match({'url':'https://evil.test/video'});self.assertEqual(launch.call_count,3)
    def test_disconnected_account_does_not_search(self):
        self.store.set_setting('youtube_account_enabled',False)
        with mock.patch('mediadesk.xiaoyuzhou_import.search_youtube_candidates') as search:
            self.w.search_xiaoyuzhou({'title':'合成','feed_url':'https://example.org/feed'});search.assert_not_called()
        self.assertIn('已断开',self.w.xiaoyuzhou_status.get_text())

    def test_late_search_does_not_replace_another_page(self):
        entered=threading.Event();release=threading.Event()
        def search(*args,**kwargs):
            entered.set();release.wait(3);return {'candidates':[]}
        with mock.patch('mediadesk.xiaoyuzhou_import.search_youtube_candidates',side_effect=search):
            self.w.search_xiaoyuzhou({'title':'合成','feed_url':'https://example.org/feed'});self.assertTrue(entered.wait(2));self.w.show_podcasts();release.set();spin_until(lambda:False,.15)
            self.assertEqual(self.w.podcast_status.get_text(),'输入节目名称搜索，或打开公开订阅地址。')

    def test_confirmed_matches_use_existing_app_playback_paths(self):
        with mock.patch.object(self.w,'load_source') as load, mock.patch.object(self.w,'podcast_add') as add:
            self.w.use_xiaoyuzhou_match({'kind':'playlist','source_id':'PLtest','confirmed':True});load.assert_called_once_with('playlist-items','PLtest')
            self.w.use_xiaoyuzhou_match({'kind':'video','source_id':'vid','url':'https://www.youtube.com/watch?v=vid','title':'单集','confirmed':True});self.assertEqual(add.call_args.args[0]['source'],'youtube')
            with mock.patch('mediadesk.xiaoyuzhou_import.resolve_channel_uploads',return_value='UUtest',create=True) as resolve:
                self.w.use_xiaoyuzhou_match({'kind':'channel','source_id':'UCtest','confirmed':True});self.assertTrue(spin_until(lambda:load.call_count==2,3));resolve.assert_called_once_with('UCtest',user_triggered=True);load.assert_called_with('playlist-items','UUtest')

    def test_candidates_stay_inside_their_program_card(self):
        programs=[{'title':'节目甲','feed_url':'https://example.org/a'},{'title':'节目乙','feed_url':'https://example.org/b'}];self.store.set_setting('xiaoyuzhou_programs',programs);self.w.show_xiaoyuzhou()
        candidate={'title':'甲的候选','url':'https://www.youtube.com/watch?v=test','kind':'video','channel':'测试'}
        with mock.patch('mediadesk.xiaoyuzhou_import.search_youtube_candidates',return_value={'candidates':[candidate]}):
            self.w.search_xiaoyuzhou(programs[0]);self.assertTrue(spin_until(lambda:'1 个候选' in self.w.xiaoyuzhou_status.get_text(),3))
        cards=self.w.xiaoyuzhou_results.get_children();self.assertEqual(len(cards),2)
        labels=[child.get_text() for child in cards[0].get_children() if isinstance(child,Gtk.Label)];self.assertIn('候选所属节目：节目甲',labels)
        self.assertEqual(len(cards[1].get_children()),3);self.assertEqual(len(cards[0].get_children()),5)

    def test_confirmed_actions_fit_narrow_window(self):
        match={'title':'已确认候选','url':'https://www.youtube.com/watch?v=test','kind':'video','source_id':'test','confirmed':True}
        self.store.set_setting('xiaoyuzhou_programs',[{'title':'合成节目','feed_url':'https://example.org/a','match':match}]);self.w.show_xiaoyuzhou();self.w.resize(710,674);self.w.show_all();spin_until(lambda:False,.1)
        card=self.w.xiaoyuzhou_results.get_children()[0];actions=card.get_children()[2];self.assertEqual(actions.get_orientation(),Gtk.Orientation.VERTICAL)
        for control in actions.get_children():
            self.assertLessEqual(control.get_allocated_width(),card.get_allocated_width());self.assertTrue(control.get_visible())

    def test_unreadable_file_does_not_reveal_path(self):
        self.store.set_setting('xiaoyuzhou_programs',[{'title':'保留','feed_url':'https://example.org/feed'}])
        self.w.import_xiaoyuzhou_opml('/private/synthetic-secret-export.opml')
        self.assertTrue(spin_until(lambda:'导入失败' in self.w.xiaoyuzhou_status.get_text(),3))
        text=self.w.xiaoyuzhou_status.get_text();self.assertIn('文件不存在或无法读取，请重新选择',text);self.assertNotIn('/private',text);self.assertNotIn('Errno',text);self.assertEqual(self.w.xiaoyuzhou_programs()[0]['title'],'保留')

    def test_bad_file_keeps_existing_data(self):
        self.store.set_setting('xiaoyuzhou_programs',[{'title':'保留','feed_url':'https://example.org/feed'}]);path=Path(self.tmp.name)/'broken.opml';path.write_text('broken')
        self.w.import_xiaoyuzhou_opml(str(path));self.assertTrue(spin_until(lambda:'导入失败' in self.w.xiaoyuzhou_status.get_text(),3));self.assertEqual(self.w.xiaoyuzhou_programs()[0]['title'],'保留')

    def test_program_playlist_navigation_keeps_youtube_source_and_return(self):
        program={'title':'合成节目'*30,'feed_url':'https://example.org/a','match':{'kind':'playlist','source_id':'PLtest','confirmed':True}}
        self.store.set_setting('xiaoyuzhou_programs',[program]);self.w.show_xiaoyuzhou()
        raw={'id':'entry','snippet':{'title':'合成单集','resourceId':{'videoId':'abcdefghijk'}}}
        def stream(kind,page,playlist):page([raw])
        with mock.patch('mediadesk.sources.stream_youtube',side_effect=stream):
            self.w.xiaoyuzhou_cards[program['feed_url']].get_children()[0].clicked()
            self.assertTrue(spin_until(lambda:len(self.w.rows)==1,3))
        self.assertEqual(self.w.rows[0]['source'],'youtube');self.assertIn(program['title'],self.w.rows_title)
        self.w.content.get_children()[0].clicked();self.assertEqual(self.w.source_kind,'xiaoyuzhou');self.assertTrue(self.w.xiaoyuzhou_programs()[0]['match']['confirmed'])

    def test_program_video_returns_directly_and_deduplicates(self):
        match={'kind':'video','source_id':'abcdefghijk','url':'https://www.youtube.com/watch?v=abcdefghijk','title':'单集','confirmed':True}
        program={'title':'合成节目','feed_url':'https://example.org/a','match':match}
        self.store.set_setting('xiaoyuzhou_programs',[program]);self.w.show_xiaoyuzhou()
        self.w.open_xiaoyuzhou_program(program);self.assertEqual(self.w.rows[0]['source'],'youtube');mid=self.w.rows[0]['id'];self.w.return_rows()
        self.assertEqual(self.w.source_kind,'xiaoyuzhou');self.w.open_xiaoyuzhou_program(program);self.assertEqual(self.w.rows[0]['id'],mid)

    def test_chooser_selection_feedback_and_import_sensitivity(self):
        path=Path(self.tmp.name)/'synthetic.opml';path.write_text('<opml/>')
        def run(dialog):
            self.assertFalse(dialog.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive())
            dialog.set_filename(str(path));self.assertTrue(spin_until(lambda:dialog.get_filename()==str(path),2));dialog.emit('selection-changed')
            self.assertTrue(dialog.get_widget_for_response(Gtk.ResponseType.OK).get_sensitive())
            self.assertEqual(dialog.get_extra_widget().get_text(),'已选文件：synthetic.opml')
            return Gtk.ResponseType.CANCEL
        with mock.patch.object(Gtk.FileChooserDialog,'run',run):self.w.choose_xiaoyuzhou_opml()

    def test_unmatched_program_opens_explicit_search(self):
        program={'title':'未匹配节目','feed_url':'https://example.org/a'}
        with mock.patch.object(self.w,'search_xiaoyuzhou') as search, mock.patch.object(self.w,'load_source') as load:
            self.w.open_xiaoyuzhou_program(program);search.assert_called_once_with(program);load.assert_not_called()

    def test_late_channel_navigation_cannot_override_new_selection(self):
        entered=threading.Event();release=threading.Event()
        def resolve(*args,**kwargs):entered.set();release.wait(3);return 'UUold'
        with mock.patch('mediadesk.xiaoyuzhou_import.resolve_channel_uploads',side_effect=resolve), mock.patch.object(self.w,'load_source') as load:
            self.w.use_xiaoyuzhou_match({'kind':'channel','source_id':'UCold','confirmed':True});self.assertTrue(entered.wait(2))
            self.w.use_xiaoyuzhou_match({'kind':'playlist','source_id':'PLnew','confirmed':True});release.set();spin_until(lambda:False,.15)
            load.assert_called_once_with('playlist-items','PLnew')

    def test_channel_error_keeps_program_and_match(self):
        program={'title':'合成','feed_url':'https://example.org/a','match':{'kind':'channel','source_id':'UCtest','confirmed':True}}
        self.store.set_setting('xiaoyuzhou_programs',[program]);self.w.show_xiaoyuzhou()
        with mock.patch('mediadesk.xiaoyuzhou_import.resolve_channel_uploads',side_effect=ValueError('合成错误')):
            self.w.open_xiaoyuzhou_program(program);self.assertTrue(spin_until(lambda:'读取频道失败' in self.w.xiaoyuzhou_status.get_text(),3))
        self.assertEqual(self.w.source_kind,'xiaoyuzhou');self.assertTrue(self.w.xiaoyuzhou_programs()[0]['match']['confirmed'])
