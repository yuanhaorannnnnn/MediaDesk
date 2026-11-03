"""Synthetic local import tests: no Apple account, export or network."""
import tempfile
import unittest
from unittest import mock
import gi
gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0')
from gi.repository import Gtk,Gdk
from mediadesk.app import App
from mediadesk.store import Store
from tests.test_desktop import spin_until

@unittest.skipUnless(Gdk.Display.get_default(),'需要 X11 或 Xvfb')
class AppleImportUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.store.set_setting('setup_done',True);self.w=App(self.store);self.w.show_apple_podcasts()
    def tearDown(self):
        self.w.destroy();spin_until(lambda:not Gtk.events_pending(),.2);self.tmp.cleanup()
    def program(self,identity='one',title='合成节目'):
        return {'program_id':identity,'title':title,'feed_url':'','source':'apple-podcasts'}
    def test_reimport_preserves_matches_missing_entries_and_other_source(self):
        match={'title':'候选','kind':'playlist','source_id':'PLtest','confirmed':True}
        self.store.set_setting('apple_podcast_programs',[{**self.program(),'feed_url':'https://example.org/feed','match':match},self.program('absent')]);xiaoyu=[{'title':'小宇宙','feed_url':'https://example.org/feed'}];self.store.set_setting('xiaoyuzhou_programs',xiaoyu)
        with mock.patch('mediadesk.apple_podcast_import.read_import',return_value={'entries':[{**self.program(title='新名称'),'feed_url':'https://example.org/feed'}]}):
            self.w.import_apple_podcast_file('synthetic');self.assertTrue(spin_until(lambda:'导入完成' in self.w.xiaoyuzhou_status.get_text(),3))
        values=self.store.setting('apple_podcast_programs');self.assertEqual(len(values),2);self.assertEqual(values[0]['match'],match);self.assertEqual(values[0]['title'],'新名称');self.assertEqual(self.w.xiaoyuzhou_programs(),xiaoyu)
    def test_title_only_search_and_confirmation_use_apple_collection(self):
        program=self.program();self.store.set_setting('apple_podcast_programs',[program]);candidate={'kind':'playlist','source_id':'PLtest','title':'候选','url':'https://www.youtube.com/playlist?list=PLtest'}
        with mock.patch('mediadesk.xiaoyuzhou_import.search_youtube_candidates',return_value={'candidates':[candidate]}) as search:
            self.w.show_apple_podcasts();search.assert_not_called();self.w.search_xiaoyuzhou(program);self.assertTrue(spin_until(lambda:'1 个候选' in self.w.xiaoyuzhou_status.get_text(),3));search.assert_called_once_with('合成节目',user_triggered=True)
            self.w.confirm_xiaoyuzhou_match(program,candidate)
        self.assertTrue(self.store.setting('apple_podcast_programs')[0]['match']['confirmed']);self.assertEqual(self.w.xiaoyuzhou_programs(),[])
        with mock.patch.object(self.w,'load_source') as load:self.w.open_xiaoyuzhou_program(self.store.setting('apple_podcast_programs')[0]);load.assert_called_once_with('playlist-items','PLtest',program=self.store.setting('apple_podcast_programs')[0])
    def test_video_returns_to_apple_page(self):
        program={**self.program(),'match':{'kind':'video','source_id':'abcdefghijk','title':'合成视频','url':'https://www.youtube.com/watch?v=abcdefghijk','confirmed':True}}
        self.store.set_setting('apple_podcast_programs',[program]);self.w.open_xiaoyuzhou_program(program);self.assertEqual(self.w.rows[0]['source'],'youtube');self.w.return_rows();self.assertEqual(self.w.source_kind,'apple-podcasts')
    def test_bad_file_preserves_unmatched_program(self):
        self.store.set_setting('apple_podcast_programs',[self.program()])
        with mock.patch('mediadesk.apple_podcast_import.read_import',side_effect=ValueError('合成错误')):
            self.w.import_apple_podcast_file('synthetic');self.assertTrue(spin_until(lambda:'导入失败' in self.w.xiaoyuzhou_status.get_text(),3))
        self.assertNotIn('match',self.store.setting('apple_podcast_programs')[0]);self.assertTrue(self.w.xiaoyuzhou_status.get_style_context().has_class('job-failed'))
        self.w.show_apple_podcasts();self.assertFalse(self.w.xiaoyuzhou_status.get_style_context().has_class('job-failed'))
    def test_same_title_entries_keep_separate_confirmations(self):
        programs=[{**self.program('one'),'name_conflict':True},{**self.program('two'),'name_conflict':True}];self.store.set_setting('apple_podcast_programs',programs);self.w.show_apple_podcasts()
        self.assertEqual(len(self.w.xiaoyuzhou_cards),2)
        card=self.w.xiaoyuzhou_cards['one'];self.assertIn('同名身份无法核实',card.get_children()[1].get_text());self.assertIn('本地条目 #1（非节目身份）',card.get_children()[1].get_text());self.assertIn('本地条目 #2（非节目身份）',self.w.xiaoyuzhou_cards['two'].get_children()[1].get_text())
        self.w.confirm_xiaoyuzhou_match(programs[1],{'title':'候选','kind':'playlist','source_id':'PLtwo'})
        values=self.store.setting('apple_podcast_programs');self.assertNotIn('match',values[0]);self.assertTrue(values[1]['match']['confirmed'])
    def test_title_only_reexport_never_assigns_old_match_to_new_occurrence(self):
        old=[{**self.program('one'),'name_conflict':True,'match':{'title':'旧关联','confirmed':True}},self.program('two')]
        self.store.set_setting('apple_podcast_programs',old)
        for entries in ([self.program('one')],[self.program('two'),self.program('one')]):
            with mock.patch('mediadesk.apple_podcast_import.read_import',return_value={'entries':entries}):
                self.w.import_apple_podcast_file('synthetic');self.assertTrue(spin_until(lambda:'导入完成' in self.w.xiaoyuzhou_status.get_text(),3))
            values=self.store.setting('apple_podcast_programs');self.assertEqual(values[0]['match']['title'],'旧关联')
            for item in values[2:]:self.assertNotIn('match',item);self.assertTrue(item['name_conflict'])
    def test_third_party_shortcut_link_is_visible_without_network_access(self):
        def descendants(widget):
            yield widget
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():yield from descendants(child)
        children=list(descendants(self.w.content))
        links=[child for child in children if isinstance(child,Gtk.LinkButton)]
        self.assertEqual(len(links),1);self.assertEqual(links[0].get_uri(),'https://www.icloud.com/shortcuts/5e49239698c44e92baf94399df86b3f9');self.assertIn('第三方',links[0].get_label());self.assertTrue(links[0].get_visible())
        text=' '.join(child.get_text() for child in children if isinstance(child,Gtk.Label))
        for expected in ('查看操作再添加','保存到文件','当前 iOS 实测待验证'):self.assertIn(expected,text)
    def test_invalid_xml_has_export_guidance_and_keeps_data(self):
        self.store.set_setting('apple_podcast_programs',[self.program()])
        with mock.patch('mediadesk.apple_podcast_import.read_import',side_effect=ValueError('无法解析 OPML 文件')):
            self.w.import_apple_podcast_file('synthetic');self.assertTrue(spin_until(lambda:'导入失败' in self.w.xiaoyuzhou_status.get_text(),3))
        self.assertIn('文件格式无法解析；可重新导出并检查节目名或地址中的特殊字符',self.w.xiaoyuzhou_status.get_text());self.assertEqual(len(self.store.setting('apple_podcast_programs')),1)
    def test_apple_guidance_scrolls_without_forcing_taller_window(self):
        self.store.set_setting('apple_podcast_programs',[self.program(str(index)) for index in range(5)]);self.w.show_apple_podcasts()
        self.w.resize(720,674);self.w.show_all();spin_until(lambda:False,.15)
        width,height=self.w.get_size();self.assertLessEqual(width,720);self.assertLessEqual(height,674)
        scroll=self.w.xiaoyuzhou_scroll;adjustment=scroll.get_vadjustment();self.assertGreater(adjustment.get_upper(),adjustment.get_page_size())
        content=self.w.content.get_children();actions=next(child for child in content if isinstance(child,Gtk.Box) and any(isinstance(button,Gtk.Button) and button.get_label()=='选择 OPML 文件' for button in child.get_children()))
        for child in actions.get_children():self.assertTrue(child.get_mapped());self.assertGreater(child.get_allocated_height(),0)
        self.assertGreater(scroll.get_allocated_height(),100)
