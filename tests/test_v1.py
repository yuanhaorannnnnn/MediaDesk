import json
import contextlib
import io
import sqlite3
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from mediadesk.store import Store, youtube_id, identify_url
from mediadesk import downloader, sources, bilibili

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_metadata_upsert_and_collection_preserve_file(self):
        item={'url':'https://www.youtube.com/watch?v=jNQXAC9IVRw','title':'标题','description':'原始说明','thumbnail':'https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg'}
        mid=self.store.save_youtube(item);self.store.set_path(mid,'/media/example.mp4');cid=self.store.add_collection('羽毛球');self.store.add_to_collection(cid,mid)
        self.store.save_youtube({'url':item['url'],'title':'更新标题'})
        row=self.store.media(cid)[0];self.assertEqual(row['description'],'原始说明');self.assertEqual(row['path'],'/media/example.mp4');self.assertEqual(row['title'],'更新标题')
        backup=Path(self.tmp.name)/'backup.sqlite';self.store.backup(backup);self.assertTrue(backup.exists())

    def test_manage_multiple_collections_without_deleting_media(self):
        mid=self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw'});a=self.store.add_collection('羽毛球');b=self.store.add_collection('运动')
        self.store.set_media_collections(mid,[a,b]);self.assertEqual(self.store.media_collections(mid),{a,b})
        self.store.set_media_collections(mid,[b]);self.assertEqual(self.store.media_collections(mid),{b});self.assertIsNotNone(self.store.get(mid))
        with self.assertRaises(ValueError):self.store.set_media_collections(mid,[999])
        self.assertEqual(self.store.media_collections(mid),{b})

    def test_batch_import_preserves_downloaded_path_and_is_atomic(self):
        one={'url':'https://youtu.be/jNQXAC9IVRw','title':'first'};mid=self.store.save_youtube(one);self.store.set_path(mid,'/media/example.mp4')
        saved=self.store.save_youtube_batch([one,{'url':'https://youtu.be/dQw4w9WgXcQ','title':'second'}])
        self.assertEqual(saved[0]['path'],'/media/example.mp4');self.assertEqual(len(saved),2)
        with self.assertRaises(ValueError):self.store.save_youtube_batch([{'url':'https://youtu.be/aqz-KE-bpKQ'},{'url':'https://evil.invalid/'}])
        self.assertEqual(len(self.store.media()),2)
    def test_job_interruption_is_durable(self):
        mid=self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw'});self.store.job('job',mid,'下载中','进行中')
        reopened=Store(self.tmp.name);self.assertEqual(reopened.jobs()[0]['state'],'中断')
    def test_local_identity_and_invalid_url(self):
        f=Path(self.tmp.name)/'clip.mp4';f.write_bytes(b'x');a=self.store.save_local(f);self.assertEqual(a,self.store.save_local(f))
        with self.assertRaises(ValueError):youtube_id('https://evil.invalid/watch?v=jNQXAC9IVRw')
    def test_bilibili_parts_have_distinct_identity_and_preserve_file(self):
        base='https://www.bilibili.com/video/BV1bK411W797'
        one=self.store.save_source({'url':base,'title':'P1','description':'原简介'})
        self.store.set_path(one,'/tmp/existing.mp4')
        self.assertEqual(one,self.store.save_source({'url':base+'?p=1','title':'P1 update'}))
        two=self.store.save_source({'url':base+'?p=2','title':'P2'})
        self.assertNotEqual(one,two);self.assertEqual(self.store.get(one)['path'],'/tmp/existing.mp4')
        self.assertEqual(self.store.get(one)['description'],'原简介');self.assertEqual(self.store.get(two)['source'],'bilibili')
        for url in (base+'?p=0',base+'?p=2&p=3','https://bilibili.com.evil.invalid/video/BV1bK411W797','http://www.bilibili.com/video/BV1bK411W797'):
            with self.assertRaises(ValueError):identify_url(url)

    def test_bilibili_delete_only_selected_part(self):
        url='https://www.bilibili.com/video/BV1bK411W797?p=2';mid=self.store.save_source({'url':url});self.store.job('b',mid,'完成','')
        target=self.store.media_dir/'视频 [BV1bK411W797_p2].mp4.part';other=self.store.media_dir/'视频 [BV1bK411W797_p1].mp4.part'
        target.write_text('data');other.write_text('data');downloader.Downloads(self.store,lambda _:None).delete('b',True)
        self.assertFalse(target.exists());self.assertTrue(other.exists())
    def test_format_validation_does_not_create_task(self):
        dl=downloader.Downloads(self.store,lambda _:None)
        with self.assertRaises(ValueError):dl.start({'url':'https://youtu.be/jNQXAC9IVRw'},fmt='bad/format')
        self.assertEqual(self.store.jobs(),[])

    def test_interrupted_job_preserves_partial_and_rejects_duplicate(self):
        script=Path(self.tmp.name)/'fake-downloader';partial=Path(self.tmp.name)/'download.part'
        script.write_text('#!/bin/sh\n[ "$2" = "--help" ] && exit 0\nprintf partial > "$MEDIADESK_TEST_PARTIAL"\nprintf "[download] 1%%\\n"\nsleep 30\n');script.chmod(0o700)
        with mock.patch.dict('os.environ',{'MEDIADESK_YTDLP':str(script),'MEDIADESK_TEST_PARTIAL':str(partial)}):
            events=[];worker=downloader.Downloads(self.store,events.append);item={'url':'https://youtu.be/jNQXAC9IVRw'};jid=worker.start(item)
            deadline=time.monotonic()+5
            while not partial.exists() and time.monotonic()<deadline:time.sleep(.03)
            self.assertTrue(partial.exists())
            deadline=time.monotonic()+5
            while downloader.progress_percent(self.store.jobs()[0]['detail']) is None and time.monotonic()<deadline:time.sleep(.03)
            self.assertEqual(downloader.progress_percent(self.store.jobs()[0]['detail']),1)
            self.assertIn(jid,events)
            with self.assertRaises(ValueError):worker.start(item)
            worker.pause(jid);worker.stop_all();deadline=time.monotonic()+5
            while worker.processes and time.monotonic()<deadline:time.sleep(.03)
            self.assertEqual(self.store.jobs()[0]['state'],'中断');self.assertEqual(partial.read_text(),'partial');self.assertFalse(worker.processes)

    def test_pause_resume_delete_keeps_partial_file(self):
        script=Path(self.tmp.name)/'fake-download';partial=Path(self.tmp.name)/'progress.part'
        script.write_text('#!/bin/sh\n[ "$2" = "--help" ] && exit 0\nwhile :; do printf x >> "$MEDIADESK_TEST_PARTIAL"; printf "[download] 23%%\\n"; sleep 0.1; done\n');script.chmod(0o700)
        with mock.patch.dict('os.environ',{'MEDIADESK_YTDLP':str(script),'MEDIADESK_TEST_PARTIAL':str(partial)}):
            worker=downloader.Downloads(self.store,lambda _:None);jid=worker.start({'url':'https://youtu.be/jNQXAC9IVRw'},preference='size',fmt='137+140')
            deadline=time.monotonic()+5
            while (not partial.exists() or jid not in worker.processes) and time.monotonic()<deadline:time.sleep(.03)
            worker.pause(jid);self.assertEqual(self.store.jobs()[0]['state'],'暂停');time.sleep(.2);size=partial.stat().st_size;time.sleep(.3);self.assertEqual(partial.stat().st_size,size)
            worker.resume(jid);deadline=time.monotonic()+3
            while partial.stat().st_size==size and time.monotonic()<deadline:time.sleep(.03)
            self.assertGreater(partial.stat().st_size,size)
            worker.pause(jid);worker.delete(jid);deadline=time.monotonic()+5
            while worker.processes and time.monotonic()<deadline:time.sleep(.03)
            self.assertEqual(self.store.jobs(),[]);self.assertTrue(partial.exists());self.assertFalse(worker.processes)

    def test_task_rename_and_retry_preserve_options(self):
        mid=self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw','title':'原视频'})
        self.store.job('existing',mid,'中断','');self.store.job_options('existing',{'preference':'size','cookies':True,'fmt':'137+140','audio_only':False});self.store.rename_job('existing','新的任务名称')
        self.assertEqual(self.store.jobs()[0]['title'],'新的任务名称');self.assertEqual(self.store.get(mid)['title'],'原视频')
        worker=downloader.Downloads(self.store,lambda _:None)
        with mock.patch.object(worker,'start') as start:
            worker.resume('existing');self.assertEqual(start.call_args.args[1:5],('size',True,'137+140',False));self.assertEqual(start.call_args.kwargs['job_id'],'existing')

    def test_legacy_database_migration_preserves_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/'library.sqlite3'
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE downloads(id TEXT PRIMARY KEY, media_id TEXT NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
                c.execute("INSERT INTO downloads(id,media_id,state,detail) VALUES('legacy','youtube:jNQXAC9IVRw','下载中','[download] 5%')")
            reopened=Store(d)
            with reopened.connection() as c:
                row=c.execute("SELECT * FROM downloads WHERE id='legacy'").fetchone()
                self.assertEqual(row['state'],'中断');self.assertEqual(row['label'],'');self.assertEqual(row['options'],'{}')

    def test_delete_during_preparation_does_not_restart_job(self):
        entered=threading.Event();release=threading.Event()
        def slow_thumbnail(*_):entered.set();release.wait(3)
        worker=downloader.Downloads(self.store,lambda _:None)
        with mock.patch.object(sources,'thumbnail',side_effect=slow_thumbnail),mock.patch.object(downloader.subprocess,'Popen') as popen:
            jid=worker.start({'url':'https://youtu.be/jNQXAC9IVRw','thumbnail':'https://i.ytimg.com/test'})
            self.assertTrue(entered.wait(3));deleting=threading.Thread(target=worker.delete,args=(jid,));deleting.start();release.set();deleting.join(3);self.assertFalse(deleting.is_alive());deadline=time.monotonic()+3
            while worker.active and time.monotonic()<deadline:time.sleep(.03)
            self.assertFalse(worker.active);self.assertEqual(self.store.jobs(),[]);popen.assert_not_called()

    def test_delete_with_files_is_limited_to_managed_video(self):
        mid=self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw'});self.store.job('one',mid,'完成','')
        root=self.store.media_dir;complete=root/'示例 [jNQXAC9IVRw].webm';partial=root/'示例 [jNQXAC9IVRw].f137.mp4.part';state=root/'示例 [jNQXAC9IVRw].mp4.ytdl';note=root/'示例 [jNQXAC9IVRw].txt';other=root/'其他 [dQw4w9WgXcQ].webm';outside=Path(self.tmp.name)/'outside.webm'
        more_media=[root/f'示例 [jNQXAC9IVRw].{ext}' for ext in ('ts','mka','M2TS','m4b','3gp','flv')]
        for f in (complete,partial,state,note,other,outside,*more_media):f.write_text('keep or remove')
        (root/'link [jNQXAC9IVRw].mp4').symlink_to(outside);self.store.set_path(mid,complete)
        downloader.Downloads(self.store,lambda _:None).delete('one',True)
        self.assertEqual(self.store.jobs(),[]);self.assertIsNone(self.store.get(mid)['path'])
        for f in (complete,partial,state,*more_media):self.assertFalse(f.exists())
        for f in (note,other,outside,root/'link [jNQXAC9IVRw].mp4'):self.assertTrue(f.exists())

    def test_delete_failure_keeps_task_and_file(self):
        mid=self.store.save_youtube({'url':'https://youtu.be/jNQXAC9IVRw'});self.store.job('one',mid,'完成','')
        complete=self.store.media_dir/'示例 [jNQXAC9IVRw].webm';complete.write_text('file');self.store.set_path(mid,complete)
        with mock.patch.object(Path,'unlink',side_effect=PermissionError('denied')):
            with self.assertRaises(ValueError):downloader.Downloads(self.store,lambda _:None).delete('one',True)
        self.assertEqual(len(self.store.jobs()),1);self.assertTrue(complete.exists());self.assertEqual(self.store.get(mid)['path'],str(complete))

    def test_delete_files_waits_for_running_process(self):
        script=Path(self.tmp.name)/'fake';partial=self.store.media_dir/'示例 [jNQXAC9IVRw].webm.part'
        script.write_text('#!/bin/sh\n[ "$2" = "--help" ] && exit 0\nwhile :; do printf x >> "$MEDIADESK_TEST_PARTIAL"; sleep 0.1; done\n');script.chmod(0o700)
        with mock.patch.dict('os.environ',{'MEDIADESK_YTDLP':str(script),'MEDIADESK_TEST_PARTIAL':str(partial)}):
            worker=downloader.Downloads(self.store,lambda _:None);jid=worker.start({'url':'https://youtu.be/jNQXAC9IVRw'})
            deadline=time.monotonic()+5
            while not partial.exists() and time.monotonic()<deadline:time.sleep(.03)
            self.assertTrue(partial.exists());worker.delete(jid,True);time.sleep(.25)
            self.assertFalse(partial.exists());self.assertFalse(worker.processes);self.assertEqual(self.store.jobs(),[])

class AdapterTests(unittest.TestCase):
    def test_node_runtime_flag_follows_downloader_capability(self):
        with mock.patch.object(downloader,'executable',return_value='/fake/yt-dlp'),mock.patch.object(downloader.shutil,'which',return_value='/fake/node'),mock.patch.object(downloader.subprocess,'run') as run:
            run.return_value=mock.Mock(returncode=0,stdout='  --js-runtimes RUNTIMES')
            self.assertIn('--js-runtimes',downloader.command())
            run.assert_called_with(['/fake/yt-dlp','--ignore-config','--help'],capture_output=True,text=True,errors='replace',timeout=2)
            run.return_value=mock.Mock(returncode=0,stdout='old version help')
            self.assertNotIn('--js-runtimes',downloader.command())
            run.side_effect=downloader.subprocess.TimeoutExpired('yt-dlp',10)
            self.assertNotIn('--js-runtimes',downloader.command())

    def test_bilibili_pagination_and_invalid_content(self):
        client=bilibili.Client.__new__(bilibili.Client);client.mid=1;pages=[]
        client.get=mock.Mock(side_effect=[{'list':[{'mid':1},{'mid':2}],'total':3},{'list':[{'mid':3}],'total':3}])
        client.followings(pages.extend);self.assertEqual([p['mid'] for p in pages],[1,2,3]);self.assertEqual(client.get.call_args.kwargs['pn'],2)
        pages=[];client.get=mock.Mock(side_effect=[{'medias':[{'id':1,'type':2,'title':'有效','bv_id':'BV1bK411W797'}],'has_more':True},{'medias':[{'id':2,'type':2,'title':'已失效视频','bv_id':'BV1PL4y1h7yd','attr':1}],'has_more':False}])
        client.favorites('9',pages.extend);self.assertEqual(len(pages),2)
        self.assertFalse(bilibili.normalize(pages[0])['unavailable']);self.assertTrue(bilibili.normalize(pages[1])['unavailable'])
        client.get=mock.Mock(return_value={'medias':[],'has_more':True})
        with self.assertRaisesRegex(ValueError,'分页中断'):client.favorites('9',lambda _:None)
        client.get=mock.Mock(return_value={'list':[],'total':3})
        with self.assertRaisesRegex(ValueError,'未读完'):client.followings(lambda _:None)
    def test_bilibili_split_stream_and_untrusted_audio(self):
        response={'requested_formats':[{'url':'https://a.bilivideo.com/video','vcodec':'h264','acodec':'none'},{'url':'https://b.bilivideo.com/audio','vcodec':'none','acodec':'aac'}]}
        def run(data):return mock.patch('mediadesk.downloader.subprocess.run',return_value=mock.Mock(returncode=0,stdout=json.dumps(data),stderr=''))
        with mock.patch('mediadesk.downloader.executable',return_value='/fake'),run(response):
            stream=downloader.online_stream('https://www.bilibili.com/video/BV1bK411W797?p=2')
            self.assertTrue(stream['audio_url']);self.assertEqual(stream['referer'],'https://www.bilibili.com/video/BV1bK411W797?p=2')
        response['requested_formats'][1]['url']='https://bilivideo.com.evil.invalid/audio'
        with mock.patch('mediadesk.downloader.executable',return_value='/fake'),run(response):
            with self.assertRaises(ValueError):downloader.online_stream('https://www.bilibili.com/video/BV1bK411W797?p=2')
    def test_online_stream_validates_origin_and_combined_media(self):
        response={'url':'https://r1.googlevideo.com/videoplayback?token=example','vcodec':'h264','acodec':'aac','resolution':'640x360','http_headers':{'User-Agent':'test agent'}}
        def result(data):return mock.Mock(returncode=0,stdout=json.dumps(data),stderr='')
        with mock.patch('mediadesk.downloader.subprocess.run',return_value=result(response)),mock.patch('mediadesk.downloader.executable',return_value='/fake'):
            stream=downloader.online_stream('https://youtu.be/jNQXAC9IVRw');self.assertEqual(stream['resolution'],'640x360');self.assertEqual(stream['user_agent'],'test agent')
        for bad in ('http://r1.googlevideo.com/file','https://googlevideo.com.evil.invalid/file','https://example.invalid/file','https://user@googlevideo.com/file'):
            with mock.patch('mediadesk.downloader.subprocess.run',return_value=result({**response,'url':bad})),mock.patch('mediadesk.downloader.executable',return_value='/fake'):
                with self.assertRaises(ValueError):downloader.online_stream('https://youtu.be/jNQXAC9IVRw')
        with mock.patch('mediadesk.downloader.subprocess.run',return_value=result({**response,'acodec':'none'})),mock.patch('mediadesk.downloader.executable',return_value='/fake'):
            with self.assertRaisesRegex(ValueError,'画面和声音'):downloader.online_stream('https://youtu.be/jNQXAC9IVRw')
    def test_refresh_token_without_access_token(self):
        from mediadesk import oauth_bridge
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'token.json';path.write_text('unchanged');cred=mock.Mock();cred.valid=False;cred.refresh_token='present'
            def refresh(_):cred.valid=True
            cred.refresh.side_effect=refresh
            with mock.patch.object(oauth_bridge,'CONFIG',Path(d)),mock.patch.object(oauth_bridge.Credentials,'from_authorized_user_file',return_value=cred):
                result=oauth_bridge.credentials()
            self.assertIs(result,cred);cred.refresh.assert_called_once();self.assertEqual(path.read_text(),'unchanged')
    def test_legacy_google_credentials_can_be_saved_after_login(self):
        from mediadesk import oauth_bridge
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'client.json').write_text('{}')
            cred=SimpleNamespace(token='sample',refresh_token='refresh',token_uri='https://example.invalid/token',client_id='sample',client_secret='sample',scopes=[oauth_bridge.SCOPE],expiry=None)
            flow=mock.Mock();flow.run_local_server.return_value=cred
            with mock.patch.object(oauth_bridge,'CONFIG',root),mock.patch.object(oauth_bridge.InstalledAppFlow,'from_client_secrets_file',return_value=flow):
                self.assertIs(oauth_bridge.credentials(True),cred)
            token=root/'token.json';self.assertEqual(json.loads(token.read_text())['refresh_token'],'refresh');self.assertEqual(token.stat().st_mode & 0o777,0o600)
    def test_bridge_emits_each_api_page(self):
        from mediadesk import oauth_bridge
        responses=[]
        for data in ({'items':[{'id':'first'}],'nextPageToken':'next'},{'items':[{'id':'second'}]}):
            r=mock.Mock();r.ok=True;r.json.return_value=data;responses.append(r)
        output=io.StringIO()
        with mock.patch.object(oauth_bridge,'credentials',return_value=mock.Mock(token='sample')),mock.patch.object(oauth_bridge.requests,'get',side_effect=responses),mock.patch('sys.argv',['oauth_bridge.py','likes','--stream']),contextlib.redirect_stdout(output):oauth_bridge.main()
        self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()],[[{'id':'first'}],[{'id':'second'}]])
    def test_streamed_pages_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as d:
            script=Path(d)/'helper.py';script.write_text('import json,sys\nprint(json.dumps([{\"id\":1}]),flush=True)\nprint(json.dumps([{\"id\":2}]),flush=True)\nprint(\"offline\",file=sys.stderr)\nsys.exit(1)\n');pages=[]
            with mock.patch.object(sources,'SCRIPT',script),mock.patch.object(sources,'PYTHON',__import__('sys').executable):
                with self.assertRaisesRegex(ValueError,'offline'):sources.stream_youtube('likes',pages.append)
            self.assertEqual(pages,[[{'id':1}],[{'id':2}]])
    def test_readable_download_errors(self):
        self.assertIn('格式',downloader.error_message('ERROR: Requested format is not available'))
        self.assertIn('登录',downloader.error_message('ERROR: Sign in to confirm'))
        self.assertIn('磁盘空间',downloader.error_message('ERROR: No space left on device'))
    def test_audio_album_art_does_not_make_it_video(self):
        from mediadesk.app import local_media_info
        probe={'streams':[{'codec_type':'audio'},{'codec_type':'video','disposition':{'attached_pic':1}}],'format':{'duration':'65.2'}}
        with mock.patch('mediadesk.app.subprocess.run',return_value=mock.Mock(returncode=0,stdout=json.dumps(probe))):
            self.assertEqual(local_media_info('/tmp/example.mp3'),'音频 · MP3 · 01:05')
    def test_download_progress_is_current_file_only(self):
        self.assertEqual(downloader.progress_percent('[download]  32.5% of 20.00MiB at 1.00MiB/s'),32.5)
        self.assertEqual(downloader.progress_percent('[download] 100% of 20MiB'),100)
        self.assertIsNone(downloader.progress_percent('准备下载'))
        self.assertIsNone(downloader.progress_percent('[download] 101%'))
    def test_normalize_playlist_item(self):
        item={'snippet':{'title':'one','description':'intro'},'contentDetails':{'videoId':'jNQXAC9IVRw'}}
        got=sources.normalize(item,'playlist-items');self.assertEqual(got['url'],'https://www.youtube.com/watch?v=jNQXAC9IVRw');self.assertEqual(got['description'],'intro')
    def test_untrusted_thumbnail_refused(self):
        with tempfile.TemporaryDirectory() as d:self.assertIsNone(sources.thumbnail(Store(d),'http://127.0.0.1/secret'))

if __name__=='__main__':unittest.main()
