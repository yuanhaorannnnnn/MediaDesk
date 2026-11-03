"""Windows platform integration uses generated files and synthetic children only."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from mediadesk import downloader, store
from mediadesk.paths import google_config_dir
from mediadesk.instance import acquire


class PlatformPaths(unittest.TestCase):
    def test_data_directory(self):
        with patch.dict(os.environ,{'LOCALAPPDATA':'C:/sample','XDG_DATA_HOME':'/sample'}):
            expected=Path('C:/sample')/'MediaDesk' if os.name=='nt' else Path('/sample')/'mediadesk'
            self.assertEqual(store.data_dir(),expected)

    def test_oauth_config_location(self):
        with patch.dict(os.environ,{'LOCALAPPDATA':'C:/sample'}):
            with patch.dict(os.environ):
                os.environ.pop('MEDIADESK_GOOGLE_CONFIG',None)
                expected=store.data_dir()/'google' if os.name=='nt' else Path.home()/'.config/youtube-readonly'
                self.assertEqual(google_config_dir(),expected)
            with patch.dict(os.environ,{'MEDIADESK_GOOGLE_CONFIG':'custom-oauth'}):
                self.assertEqual(google_config_dir(),Path('custom-oauth'))

    def test_single_instance(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'lock';fd=acquire(path)
            try:
                code='from mediadesk.instance import acquire; import sys; acquire(sys.argv[1])'
                p=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True)
                self.assertNotEqual(p.returncode,0)
                self.assertIn(b'BlockingIOError',p.stderr)
            finally:os.close(fd)
            os.close(acquire(path))


@unittest.skipUnless(os.name=='nt','requires Windows GTK')
class WindowsGtkPaths(unittest.TestCase):
    def load_app(self):
        try:from mediadesk import app
        except ModuleNotFoundError as exc:
            if exc.name=='gi':self.skipTest('requires GTK runtime')
            raise
        return app

    def test_safe_dirs_does_not_run_xdg(self):
        app=self.load_app()
        with tempfile.TemporaryDirectory() as root:
            with patch.object(app.GLib,'get_user_special_dir',return_value=root),patch.object(app.subprocess,'run',side_effect=AssertionError('xdg must not run')):
                self.assertEqual(app.safe_dirs(),[Path(root)])

    def test_gui_uses_shared_oauth_path_for_expired_token(self):
        app=self.load_app()
        with tempfile.TemporaryDirectory() as root:
            config=Path(root)/'oauth';config.mkdir();(config/'token.json').write_text('{}')
            library=store.Store(Path(root)/'library');library.set_setting('setup_done',True)
            window=app.App(library)
            try:
                with patch.object(app,'google_config_dir',return_value=config),patch.object(app.sources,'list_youtube',side_effect=ValueError('需要连接 YouTube 账号')):
                    window.show_settings()
                    deadline=time.monotonic()+3
                    while 'youtube' not in window.account_cache and time.monotonic()<deadline:
                        while app.Gtk.events_pending():app.Gtk.main_iteration()
                        time.sleep(.01)
                    self.assertEqual(window.account_cache['youtube'][1],'expired')
            finally:window.destroy()


@unittest.skipUnless(os.name=='nt','requires Windows Job Objects')
class WindowsProcesses(unittest.TestCase):
    def wait_for(self,fn,timeout=5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if fn():return
            time.sleep(.03)
        self.fail('synthetic child did not reach expected state')

    def test_tree_pause_resume_stop(self):
        with tempfile.TemporaryDirectory() as root:
            counter=Path(root)/'ticks'
            child="import pathlib,time,sys; p=pathlib.Path(sys.argv[1]);\nwhile True:\n p.write_text(str(time.time()));time.sleep(.02)"
            parent="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]);time.sleep(60)"
            proc=downloader.spawn([sys.executable,'-c',parent,child,str(counter)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                self.wait_for(counter.exists);self.wait_for(lambda:len(proc.pids())>=2)
                proc.pause_tree();before=counter.read_text();time.sleep(.25)
                self.assertEqual(counter.read_text(),before)
                proc.resume_tree();self.wait_for(lambda:counter.read_text()!=before)
                proc.pause_tree();self.assertTrue(downloader.stop_process(proc,True))
                self.assertEqual(proc.pids(),[])
                before=counter.read_text();time.sleep(.15);self.assertEqual(counter.read_text(),before)
            finally:
                if proc.job:proc.finish_tree()
                proc.stdout.close();proc.stderr.close()

    def test_finish_kills_descendants_after_leader_exit(self):
        parent="import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])"
        proc=downloader.spawn([sys.executable,'-c',parent])
        try:
            downloader.wait_exited(proc)
            self.assertTrue(downloader.leader_state(proc))
            self.assertEqual(downloader.finish_process(proc),0)
            self.assertEqual(proc.pids(),[])
        finally:
            if proc.job:proc.finish_tree()

    def test_probe_pipe_and_utf8(self):
        proc=downloader.spawn([sys.executable,'-c',"print('中文')"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=downloader.environment())
        try:
            result=downloader.probe_output(proc,lambda:False)
            self.assertEqual(result.decode('utf-8').strip(),'中文')
            downloader.wait_exited(proc);self.assertEqual(downloader.finish_process(proc),0)
        finally:
            if proc.job:proc.finish_tree()
            proc.stdout.close();proc.stderr.close()


if __name__=='__main__':unittest.main()
