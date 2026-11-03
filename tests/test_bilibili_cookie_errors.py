"""Synthetic extraction errors only: never open a real browser profile."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mediadesk import bilibili

SECRET='synthetic-token C:/private/profile/Cookies'

class CookieErrors(unittest.TestCase):
    def check(self, underlying, expected):
        wrapped=RuntimeError('failed to load cookies '+SECRET);wrapped.__context__=underlying
        with patch.object(bilibili,'os',SimpleNamespace(name='nt')):
            message=bilibili.cookie_error(wrapped)
        self.assertIn(expected,message);self.assertNotIn(SECRET,message);self.assertNotIn('C:/',message)

    def test_missing_database(self):
        self.check(FileNotFoundError('could not find chrome cookies database in '+SECRET),'未发现 Chrome 登录数据')

    def test_locked_or_inaccessible_database(self):
        self.check(PermissionError(13,SECRET),'完全退出 Chrome')
        self.check(RuntimeError('Could not copy Chrome cookie database '+SECRET),'完全退出 Chrome')

    def test_explicit_decryption_failure(self):
        for text in ('Failed to decrypt with DPAPI','unsupported App-Bound encryption','Application-Bound Encryption failure'):
            with self.subTest(text=text):self.check(RuntimeError(text+' '+SECRET),'无法解密')

    def test_unknown_and_cyclic_chain(self):
        error=RuntimeError(SECRET);error.__cause__=error
        self.check(error,'可先跳过账号连接')

    def test_non_windows_preserves_message(self):
        with patch.object(bilibili,'os',SimpleNamespace(name='posix')):
            self.assertEqual(bilibili.cookie_error(PermissionError(SECRET)),'无法读取 Chrome 登录状态，请检查浏览器和系统密钥环')

    def test_client_returns_only_fixed_message_without_touching_cookiejar(self):
        import yt_dlp
        wrapped=RuntimeError('failed to load cookies '+SECRET)
        wrapped.__cause__=RuntimeError('Failed to decrypt with DPAPI '+SECRET)
        with patch.object(bilibili,'os',SimpleNamespace(name='nt',environ={})),patch.object(yt_dlp,'YoutubeDL',side_effect=wrapped):
            with self.assertRaisesRegex(ValueError,'无法解密') as caught:bilibili.Client()
        self.assertNotIn(SECRET,str(caught.exception));self.assertTrue(caught.exception.__suppress_context__)

if __name__=='__main__':unittest.main()
