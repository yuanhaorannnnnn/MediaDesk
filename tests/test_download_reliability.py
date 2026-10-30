"""Offline integration tests: real yt-dlp against an isolated HTTP source."""
import hashlib
import http.server
import json
import os
import signal
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from mediadesk import downloader
from mediadesk.store import Store


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), '需要 FFmpeg')
class DownloadIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:cls.executable=downloader.executable()
        except ValueError:raise unittest.SkipTest('需要 yt-dlp')
        cls.fixture_dir=tempfile.TemporaryDirectory();fixture=Path(cls.fixture_dir.name)/'sample.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=25',
                        '-f','lavfi','-i','sine=frequency=440','-t','12','-c:v','mpeg4','-q:v','5',
                        '-c:a','aac','-movflags','+faststart',str(fixture)],check=True,timeout=30)
        cls.data=fixture.read_bytes();cls.digest=hashlib.sha256(cls.data).digest()
        audio=Path(cls.fixture_dir.name)/'audio-only.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440',
                        '-t','2','-vn','-c:a','aac',str(audio)],check=True,timeout=30)
        cls.audio_only=audio.read_bytes()

    @classmethod
    def tearDownClass(cls):cls.fixture_dir.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root/'library')
        self.ranges=[];self.reject=False;self.cut_once=False;self.cut_happened=False;case=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_HEAD(self):self.respond(False)
            def do_GET(self):self.respond(True)
            def respond(self,body):
                if case.reject:
                    self.send_response(403);self.send_header('Content-Length','0');self.end_headers();return
                header=self.headers.get('Range');start=int(header[6:].split('-')[0] or 0) if header and header.startswith('bytes=') else 0
                if body:case.ranges.append(start)
                self.send_response(206 if header else 200);self.send_header('Content-Type','video/mp4')
                self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(len(case.data)-start))
                if header:self.send_header('Content-Range',f'bytes {start}-{len(case.data)-1}/{len(case.data)}')
                self.end_headers()
                if body:
                    try:
                        for pos in range(start,len(case.data),16384):
                            self.wfile.write(case.data[pos:pos+16384]);self.wfile.flush();time.sleep(.015)
                            if case.cut_once and pos-start>=200000:
                                case.cut_once=False;case.cut_happened=True;self.connection.shutdown(socket.SHUT_RDWR);break
                    except (BrokenPipeError,ConnectionResetError):pass
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/sample.mp4'
        shim=self.root/'downloader-shim.py'
        shim.write_text('import os,sys\nos.execv(sys.argv[1],[sys.argv[1]]+sys.argv[2:-1]+[os.environ["MEDIADESK_TEST_HTTP_URL"]])\n')
        self.env=mock.patch.dict(os.environ,{'MEDIADESK_TEST_HTTP_URL':self.url});self.env.start()
        self.command=mock.patch.object(downloader,'command',return_value=[sys.executable,str(shim),self.executable,'--ignore-config','--no-playlist']);self.command.start()
        self.workers=[]

    def tearDown(self):
        for worker in self.workers:
            worker.stop_all()
            self.wait_for(lambda:not worker.workers,timeout=10)
        self.command.stop();self.env.stop();self.server.shutdown();self.server.server_close();self.thread.join(3);self.temp.cleanup()

    @staticmethod
    def wait_for(predicate,timeout=20):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return True
            time.sleep(.03)
        return False

    def worker(self):
        value=downloader.Downloads(self.store,lambda _:None);self.workers.append(value);return value

    def check_completed(self,jid):
        self.assertTrue(self.wait_for(lambda:self.store.jobs()[0]['state'] in ('完成','失败')))
        job=self.store.jobs()[0];self.assertEqual(job['id'],jid);self.assertEqual(job['state'],'完成',job['detail'])
        path=Path(self.store.get(job['media_id'])['path']);self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),self.digest)

    def test_stop_and_resume_uses_range_and_preserves_file(self):
        first=self.worker();jid=first.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
        def partial():
            paths=list(self.store.media_dir.glob('*.part'))
            return paths and paths[0].stat().st_size>100000
        self.assertTrue(self.wait_for(partial));first.stop_all();self.assertTrue(self.wait_for(lambda:not first.workers))
        self.assertEqual(self.store.jobs()[0]['state'],'中断');self.assertTrue(partial())
        second=self.worker();second.resume(jid);self.check_completed(jid)
        self.assertTrue(any(offset>0 for offset in self.ranges),'没有观察到 Range 续传')

    def test_access_denied_can_retry_same_task(self):
        self.reject=True;worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
        self.assertTrue(self.wait_for(lambda:self.store.jobs()[0]['state']=='失败'))
        self.assertTrue(self.wait_for(lambda:not worker.workers));job=self.store.jobs()[0]
        self.assertIn('拒绝访问',job['detail']);self.assertNotIn('127.0.0.1',job['detail'])
        self.assertIsNone(self.store.get(job['media_id'])['path'])
        self.reject=False;worker.resume(jid);self.check_completed(jid)

    def test_strict_decode_distinguishes_truncation_with_intact_metadata(self):
        good=self.root/'complete.mp4';bad=self.root/'truncated.mp4'
        good.write_bytes(self.data);original=self.data[:len(self.data)*3//5];bad.write_bytes(original)
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(bad)],capture_output=True,text=True,timeout=20)
        self.assertEqual(probe.returncode,0)
        self.assertTrue({'audio','video'}.issubset({v['codec_type'] for v in json.loads(probe.stdout)['streams']}))
        def strict(path):return subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'],capture_output=True,timeout=25).returncode
        self.assertEqual(strict(good),0);self.assertNotEqual(strict(bad),0)
        self.assertEqual(bad.read_bytes(),original)

    def test_connection_drops_once_and_download_completes_intact(self):
        self.cut_once=True;worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
        self.check_completed(jid);self.assertTrue(self.cut_happened,'未能模拟中途断线')
        self.assertTrue(any(offset>0 for offset in self.ranges),'断线后没有观察到 Range 恢复')
        self.assertTrue(json.loads(self.store.jobs()[0]['options']).get('needs_strict_check'),'中途断线未开启严格检查')

    def test_recovered_download_strictly_checks_and_preserves_truncated_file(self):
        self.data=type(self).data[:len(type(self).data)*3//5];self.cut_once=True
        worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
        self.assertTrue(self.wait_for(lambda:self.store.jobs()[0]['state'] in ('完成','失败')))
        self.assertTrue(self.wait_for(lambda:not worker.workers));job=self.store.jobs()[0]
        self.assertTrue(self.cut_happened);self.assertTrue(any(offset>0 for offset in self.ranges))
        self.assertEqual(job['state'],'失败',job['detail']);self.assertEqual(job['detail'],downloader.STRICT_FAILED)
        self.assertTrue(json.loads(job['options']).get('needs_strict_check'))
        self.assertIsNone(self.store.get(job['media_id'])['path'])
        paths=list(self.store.media_dir.glob('*.mp4'));self.assertEqual(len(paths),1);self.assertEqual(paths[0].read_bytes(),self.data)
        bad=paths[0];bad_bytes=self.data;self.data=type(self).data
        worker.resume(jid);self.check_completed(jid)
        self.assertEqual(bad.read_bytes(),bad_bytes)
        self.assertNotEqual(Path(self.store.get(job['media_id'])['path']),bad)

    def test_strict_check_can_pause_resume_and_delete(self):
        fakebin=self.root/'bin';fakebin.mkdir();counter=self.root/'strict-counter';ffmpeg=fakebin/'ffmpeg'
        ffmpeg.write_text('#!/usr/bin/python3\nimport os,sys,time\nfrom pathlib import Path\nif "-xerror" not in sys.argv:os.execv("/usr/bin/ffmpeg",["/usr/bin/ffmpeg"]+sys.argv[1:])\np=Path(os.environ["MEDIADESK_TEST_COUNTER"])\nwhile True:\n with p.open("a") as f:f.write("x")\n time.sleep(.05)\n')
        ffmpeg.chmod(0o755);worker=self.worker()
        with mock.patch.dict(os.environ,{'PATH':str(fakebin)+os.pathsep+os.environ['PATH'],'MEDIADESK_TEST_COUNTER':str(counter)}):
            self.reject=True;jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
            self.assertTrue(self.wait_for(lambda:self.store.jobs()[0]['state']=='失败'))
            self.assertTrue(self.wait_for(lambda:not worker.workers));self.reject=False;worker.resume(jid)
            self.assertTrue(self.wait_for(lambda:counter.exists() and counter.stat().st_size>3))
            self.assertEqual(self.store.jobs()[0]['detail'],'正在严格检查')
            worker.pause(jid);time.sleep(.2);size=counter.stat().st_size;time.sleep(.2)
            self.assertEqual(counter.stat().st_size,size)
            worker.resume(jid);self.assertTrue(self.wait_for(lambda:counter.stat().st_size>size))
            worker.delete(jid);self.assertTrue(self.wait_for(lambda:not worker.workers))
            self.assertEqual(self.store.jobs(),[]);self.assertEqual(len(list(self.store.media_dir.glob('*.mp4'))),1)

    def test_failed_stream_validation_preserves_original_on_retry(self):
        self.data=self.audio_only;worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
        self.assertTrue(self.wait_for(lambda:self.store.jobs()[0]['state']=='失败'))
        self.assertTrue(self.wait_for(lambda:not worker.workers));before=list(self.store.media_dir.glob('*.mp4'))
        self.assertEqual(len(before),1);bad=before[0];self.assertEqual(bad.read_bytes(),self.audio_only)
        self.assertIsNone(self.store.get(self.store.jobs()[0]['media_id'])['path'])
        self.data=type(self).data;worker.resume(jid)
        def retry_part():
            paths=list(self.store.media_dir.glob('*.part'))
            return paths and paths[0].stat().st_size>100000
        self.assertTrue(self.wait_for(retry_part));worker.stop_all();self.assertTrue(self.wait_for(lambda:not worker.workers))
        self.assertEqual(self.store.jobs()[0]['state'],'中断')
        second=self.worker();second.resume(jid);self.check_completed(jid)
        self.assertTrue(any(offset>0 for offset in self.ranges),'重试任务中断后没有观察到 Range 续传')
        self.assertTrue(bad.is_file());self.assertEqual(bad.read_bytes(),self.audio_only)
        self.assertNotEqual(Path(self.store.get(self.store.jobs()[0]['media_id'])['path']),bad)

    def test_invalid_utf8_output_does_not_orphan_child(self):
        pid_file=self.root/'pid';script=self.root/'invalid-output.py'
        script.write_text('import os,time\nfrom pathlib import Path\nPath(os.environ["MEDIADESK_TEST_PID"]).write_text(str(os.getpid()))\nos.write(1,b"\\xff\\n")\ntime.sleep(30)\n')
        worker=self.worker();pid=None
        try:
            with mock.patch.dict(os.environ,{'MEDIADESK_TEST_PID':str(pid_file)}),mock.patch.object(downloader,'command',return_value=[sys.executable,'-u',str(script)]):
                jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
                self.assertTrue(self.wait_for(pid_file.exists));pid=int(pid_file.read_text());time.sleep(.2)
                self.assertIn(jid,worker.processes,'无效 UTF-8 导致下载进程失去管理')
                worker.delete(jid);self.assertTrue(self.wait_for(lambda:not worker.workers));self.assertEqual(self.store.jobs(),[])
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)
        finally:
            if pid is not None:
                try:os.kill(pid,signal.SIGKILL)
                except ProcessLookupError:pass

    def test_stdout_reader_failure_terminates_child(self):
        original=subprocess.Popen;captured=[]
        class BrokenOutput:
            def __init__(self,stream):self.stream=stream
            def __iter__(self):raise OSError('simulated reader failure')
            def close(self):self.stream.close()
        def spawn(*args,**kwargs):
            proc=original([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
            proc.stdout=BrokenOutput(proc.stdout);captured.append(proc);return proc
        worker=self.worker()
        try:
            with mock.patch.object(downloader.subprocess,'Popen',side_effect=spawn):
                worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
                self.assertTrue(self.wait_for(lambda:self.store.jobs()[0]['state']=='失败'))
                self.assertTrue(self.wait_for(lambda:not worker.workers));self.assertTrue(captured)
                self.assertIsNotNone(captured[0].poll(),'读取错误后子进程仍在运行')
        finally:
            for proc in captured:
                if proc.poll() is None:proc.kill();proc.wait()
                proc.stdout.close()

    def test_failed_verification_with_temporary_db_error_keeps_retry_identity(self):
        self.data=self.audio_only;worker=self.worker();real_job=self.store.job;failed_once=[]
        def job(*args):
            if args[2]=='失败' and args[3]==downloader.VERIFY_FAILED and not failed_once:
                failed_once.append(True);raise sqlite3.OperationalError('simulated full database')
            return real_job(*args)
        with mock.patch.object(self.store,'job',side_effect=job):
            jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
            self.assertTrue(self.wait_for(lambda:not worker.workers));self.assertEqual(failed_once,[True])
            self.assertTrue(worker.reconcile());self.assertEqual(self.store.jobs()[0]['detail'],downloader.VERIFY_FAILED)
            bad=list(self.store.media_dir.glob('*.mp4'));self.assertEqual(len(bad),1);self.assertEqual(bad[0].read_bytes(),self.audio_only)
            self.data=type(self).data;worker.resume(jid);self.check_completed(jid)
            self.assertEqual(bad[0].read_bytes(),self.audio_only)
            self.assertNotEqual(Path(self.store.get(self.store.jobs()[0]['media_id'])['path']),bad[0])

    def test_completion_db_failure_retains_file_and_can_retry(self):
        worker=self.worker();real_job=self.store.job;failed_once=[]
        def job(*args):
            if args[2]=='完成' and not failed_once:
                failed_once.append(True);raise sqlite3.OperationalError('simulated database failure')
            return real_job(*args)
        with mock.patch.object(self.store,'job',side_effect=job):
            jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
            self.assertTrue(self.wait_for(lambda:not worker.workers));self.assertEqual(failed_once,[True])
            job_state=self.store.jobs()[0];self.assertEqual(job_state['state'],'失败')
            self.assertTrue(job_state['detail']);files=list(self.store.media_dir.glob('*.mp4'))
            self.assertEqual(len(files),1);self.assertEqual(hashlib.sha256(files[0].read_bytes()).digest(),self.digest)
            worker.resume(jid);self.check_completed(jid)
            self.assertEqual(hashlib.sha256(files[0].read_bytes()).digest(),self.digest)

    def test_pause_and_resume_db_failure_restore_real_process_state(self):
        counter=self.root/'counter';script=self.root/'counting-download.py'
        script.write_text('import os,time\nfrom pathlib import Path\np=Path(os.environ["MEDIADESK_TEST_COUNTER"])\nwhile True:\n with p.open("a") as f:f.write("x")\n print("[download] 10%",flush=True)\n time.sleep(.05)\n')
        worker=self.worker();real_job=self.store.job
        def fail_state(state):
            def job(*args):
                if args[2]==state:raise sqlite3.OperationalError('simulated full database')
                return real_job(*args)
            return job
        with mock.patch.dict(os.environ,{'MEDIADESK_TEST_COUNTER':str(counter)}),mock.patch.object(downloader,'command',return_value=[sys.executable,'-u',str(script)]):
            jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
            self.assertTrue(self.wait_for(lambda:counter.exists() and counter.stat().st_size>3))
            with mock.patch.object(self.store,'job',side_effect=fail_state('暂停')):
                with self.assertRaises(ValueError):worker.pause(jid)
            size=counter.stat().st_size;self.assertTrue(self.wait_for(lambda:counter.stat().st_size>size))
            self.assertNotEqual(self.store.jobs()[0]['state'],'暂停');worker.pause(jid)
            time.sleep(.15);size=counter.stat().st_size
            with mock.patch.object(self.store,'job',side_effect=fail_state('下载中')):
                with self.assertRaises(ValueError):worker.resume(jid)
            time.sleep(.2);self.assertEqual(counter.stat().st_size,size);self.assertEqual(self.store.jobs()[0]['state'],'暂停')
            worker.resume(jid);self.assertTrue(self.wait_for(lambda:counter.stat().st_size>size));worker.delete(jid)

    @unittest.skipUnless(hasattr(os,'waitid') and hasattr(os,'WNOWAIT'), '需要 Linux waitid')
    def test_delete_reaps_group_when_leader_exits_before_term_resistant_child(self):
        pid_file=self.root/'child-pid';script=self.root/'leader.py';captured=[];reader_ready=threading.Event();release=threading.Event()
        script.write_text('''import os,signal,subprocess,sys,time
child="import os,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); open(sys.argv[1],\\"w\\").write(str(os.getpid())); time.sleep(30)"
subprocess.Popen([sys.executable,"-c",child,sys.argv[1]],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
for i in range(300):
 if os.path.exists(sys.argv[1]):break
 time.sleep(.01)
''')
        original=subprocess.Popen
        class WaitingOutput:
            def __init__(self,stream,proc):self.stream=stream;self.proc=proc
            def __iter__(self):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    result=os.waitid(os.P_PID,self.proc.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                    if result and pid_file.exists():reader_ready.set();break
                    time.sleep(.01)
                if not reader_ready.is_set():raise OSError('leader 未按预期退出')
                release.wait(10);raise OSError('模拟读取失败')
            def close(self):self.stream.close()
        def spawn(*args,**kwargs):
            proc=original([sys.executable,str(script),str(pid_file)],**kwargs)
            proc.stdout=WaitingOutput(proc.stdout,proc);captured.append(proc);return proc
        def stopped(pid):
            try:
                state=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[0]
                return state=='Z'
            except FileNotFoundError:return True
        sentinel=original([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
        worker=self.worker();thread=None;child=None;errors=[]
        try:
            with mock.patch.object(downloader.subprocess,'Popen',side_effect=spawn):
                jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
                self.assertTrue(reader_ready.wait(7),'未能形成 leader 已退出、子进程存活的场景')
                child=int(pid_file.read_text());self.assertFalse(stopped(child))
                def delete():
                    try:worker.delete(jid)
                    except Exception as exc:errors.append(exc)
                thread=threading.Thread(target=delete);thread.start();release.set();thread.join(20)
                self.assertFalse(thread.is_alive(),'删除未完成');self.assertFalse(errors,str(errors))
                self.assertTrue(self.wait_for(lambda:stopped(child),timeout=5),'忽略 SIGTERM 的子进程仍在运行')
                self.assertIsNone(sentinel.poll(),'无关进程组受到影响');self.assertEqual(self.store.jobs(),[])
        finally:
            release.set()
            if thread:thread.join(2)
            if child is not None and not stopped(child):
                try:os.kill(child,signal.SIGKILL)
                except ProcessLookupError:pass
            for proc in captured:
                if proc.poll() is None:proc.kill();proc.wait()
                proc.stdout.close()
            if sentinel.poll() is None:sentinel.kill();sentinel.wait()


if __name__=='__main__':unittest.main()
