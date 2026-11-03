"""Account helpers must not create Windows console windows; no real accounts are read."""
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from mediadesk import sources, bilibili


class AccountProcesses(unittest.TestCase):
    def options(self, module, windows):
        return patch.object(module, 'os', SimpleNamespace(name='nt' if windows else 'posix', pathsep=';'))

    def test_youtube_auth_console_flag(self):
        for windows in (False, True):
            with self.subTest(windows=windows), self.options(sources, windows), patch.object(sources.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True), patch.object(sources.subprocess, 'run', return_value=Mock(returncode=0, stdout='{}')) as run:
                self.assertEqual(sources.list_youtube('auth'), {})
                self.assertEqual(run.call_args.kwargs['creationflags'], 0x08000000 if windows else 0)

    def test_stream_helpers_console_flag(self):
        for module, call in ((sources, lambda: sources.stream_youtube('likes', lambda page: None)), (bilibili, lambda: bilibili.stream('status', lambda page: None))):
            for windows in (False, True):
                proc=Mock(stdout=io.StringIO('[]\n'), stderr=io.StringIO(''))
                proc.wait.return_value=0
                manager=Mock();manager.__enter__=Mock(return_value=proc);manager.__exit__=Mock(return_value=False)
                with self.subTest(module=module.__name__, windows=windows), self.options(module, windows), patch.object(module.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True), patch.object(module.subprocess, 'Popen', return_value=manager) as popen:
                    call()
                    self.assertEqual(popen.call_args.kwargs['creationflags'], 0x08000000 if windows else 0)


if __name__=='__main__':unittest.main()
