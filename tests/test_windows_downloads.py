"""Windows downloads always decode completely; Linux keeps its existing health policy."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import unittest
from unittest import mock

import test_download_reliability as reliability
from mediadesk import downloader
from mediadesk.store import Store


@unittest.skipUnless(os.name=='nt' and shutil.which('ffmpeg') and shutil.which('ffprobe'),'requires Windows and FFmpeg')
class WindowsDownloads(reliability.DownloadIntegrationTests):
    def setUp(self):
        super().setUp()
        self.store=Store(self.root/'中文目录')
        shim=self.root/'downloader-shim.py'
        # Windows execv launches a different PID; wait for the executable to finish.
        shim.write_text('import os,sys,subprocess\nsys.exit(subprocess.call([sys.argv[1]]+sys.argv[2:-1]+[os.environ["MEDIADESK_TEST_HTTP_URL"]]))\n')
        self.command.stop()
        self.command=mock.patch.object(downloader,'command',return_value=[sys.executable,str(shim),self.executable,'--proxy','','--ignore-config','--no-playlist','--encoding','utf-8','--replace-in-metadata','title','^.*$','中文标题'])
        self.command.start()

    def known_speed_output(self):
        code='''import os,sys,subprocess,re
p=subprocess.Popen([sys.argv[1]]+sys.argv[2:-1]+[os.environ["MEDIADESK_TEST_HTTP_URL"]],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8")
for line in p.stdout:
 print(re.sub(r"at\\s+(?:[\\d.]+\\s*[KMGT]?i?B/s|Unknown B/s)","at 1.00MiB/s",line),end="",flush=True)
sys.exit(p.wait())
'''
        (self.root/'downloader-shim.py').write_text(code)

    def test_known_speed_retry_rejects_truncated_file(self):
        self.known_speed_output()
        self.test_recovered_download_strictly_checks_and_preserves_truncated_file()

    def test_known_speed_clean_download_still_decodes(self):
        self.known_speed_output()
        with mock.patch.object(downloader,'spawn',wraps=downloader.spawn) as spawn:
            worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
            self.check_completed(jid)
        self.assertTrue(any('-xerror' in call.args[0] for call in spawn.call_args_list))

    def test_inspect_decodes_utf8_title(self):
        item=downloader.inspect('https://www.bilibili.com/video/BV1bK411W797?p=1')
        self.assertEqual(item['title'],'中文标题')

    def blocking_decoder(self):
        counter=self.root/'decode-counter';script=self.root/'blocking-decoder.py'
        script.write_text('import sys,time\nfrom pathlib import Path\np=Path(sys.argv[1])\nwhile True:\n with p.open("a") as out:out.write("x")\n time.sleep(.03)\n')
        original=downloader.spawn
        def spawn(args,**kwargs):
            if '-xerror' in args:return original([sys.executable,str(script),str(counter)],**kwargs)
            return original(args,**kwargs)
        return counter,mock.patch.object(downloader,'spawn',side_effect=spawn)

    def test_strict_pause_resume_cancel_preserves_file(self):
        counter,decoder=self.blocking_decoder()
        with decoder:
            worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
            self.assertTrue(self.wait_for(lambda:counter.exists() and counter.stat().st_size>3))
            self.assertEqual(self.store.jobs()[0]['detail'],'正在严格检查')
            self.assertTrue(json.loads(self.store.jobs()[0]['options'])['needs_strict_check'])
            worker.pause(jid);time.sleep(.15);size=counter.stat().st_size;time.sleep(.15)
            self.assertEqual(counter.stat().st_size,size)
            worker.resume(jid);self.assertTrue(self.wait_for(lambda:counter.stat().st_size>size))
            worker.delete(jid);self.assertTrue(self.wait_for(lambda:not worker.workers))
            self.assertEqual(self.store.jobs(),[])
            self.assertEqual(len(list(self.store.media_dir.glob('*.mp4'))),1)

    def test_strict_stop_and_restart_retains_policy(self):
        counter,decoder=self.blocking_decoder()
        with decoder:
            worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'})
            self.assertTrue(self.wait_for(lambda:counter.exists() and counter.stat().st_size>3))
            worker.stop_all();self.assertTrue(self.wait_for(lambda:not worker.workers))
            self.assertEqual(self.store.jobs()[0]['state'],'中断')
            self.assertTrue(json.loads(self.store.jobs()[0]['options'])['needs_strict_check'])
        self.worker().resume(jid);self.check_completed(jid)

    def test_audio_only_is_fully_decoded(self):
        self.data=self.audio_only
        with mock.patch.object(downloader,'spawn',wraps=downloader.spawn) as spawn:
            worker=self.worker();jid=worker.start({'url':'https://www.bilibili.com/video/BV1bK411W797?p=1'},audio_only=True)
            self.assertTrue(self.wait_for(lambda:self.store.jobs()[0]['state'] in ('完成','失败')))
            self.assertTrue(self.wait_for(lambda:not worker.workers))
        job=self.store.jobs()[0];self.assertEqual(job['state'],'完成',job['detail'])
        self.assertTrue(json.loads(job['options'])['needs_strict_check'])
        self.assertTrue(any('-xerror' in call.args[0] for call in spawn.call_args_list))
        self.assertEqual(Path(self.store.get(job['media_id'])['path']).read_bytes(),self.audio_only)

    def check_completed(self,jid):
        super().check_completed(jid)
        job=next(j for j in self.store.jobs() if j['id']==jid)
        path=Path(self.store.get(job['media_id'])['path'])
        self.assertIn('中文目录',str(path));self.assertIn('中文标题',path.name)
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),self.digest)
        self.assertTrue(json.loads(job['options'])['needs_strict_check'])


def load_tests(loader,tests,pattern):
    names=('test_known_speed_retry_rejects_truncated_file','test_known_speed_clean_download_still_decodes','test_strict_pause_resume_cancel_preserves_file','test_strict_stop_and_restart_retains_policy','test_audio_only_is_fully_decoded','test_inspect_decodes_utf8_title','test_stop_and_resume_uses_range_and_preserves_file','test_connection_drops_once_and_download_completes_intact','test_access_denied_can_retry_same_task','test_recovered_download_strictly_checks_and_preserves_truncated_file','test_pause_and_resume_db_failure_restore_real_process_state')
    return unittest.TestSuite(WindowsDownloads(name) for name in names)
