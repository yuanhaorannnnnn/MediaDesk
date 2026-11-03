import os
import http.cookiejar
import tempfile
import threading
import unittest
from pathlib import Path
from mediadesk.bilibili_login import QRLogin, CredentialStore


def cookie():
    return http.cookiejar.Cookie(0,'SESSDATA','secret',None,False,'.bilibili.com',True,True,'/',True,True,2000000000,False,None,None,{})


class LoginTests(unittest.TestCase):
    def test_states_store_permissions_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CredentialStore(Path(tmp)/'private/session')
            codes=iter([86101,86090,0])
            login=QRLogin(store=store,transport=lambda action,key=None: {'url':'https://passport.bilibili.com/qrcode?key=private','qrcode_key':'private'} if action=='generate' else {'code':next(codes)})
            self.assertEqual(login.start()['state'],'waiting_scan')
            self.assertEqual(login.poll()['state'],'waiting_scan')
            self.assertEqual(login.poll()['state'],'waiting_confirm')
            login.jar.set_cookie(cookie())
            self.assertEqual(login.poll()['state'],'success')
            self.assertEqual(next(iter(store.load())).value,'secret')
            if os.name == 'nt':
                self.assertNotIn(b'secret',store.path.read_bytes())
            else:
                self.assertEqual(store.path.stat().st_mode & 0o777,0o600)
                self.assertEqual(store.path.parent.stat().st_mode & 0o777,0o700)
            login.cancel();self.assertTrue(store.path.exists())
            login.clear_credentials();self.assertFalse(store.path.exists())

    def test_cancel_concurrent_poll(self):
        entered=threading.Event();release=threading.Event()
        def transport(action,key=None):
            if action=='generate':return {'url':'https://passport.bilibili.com/qr','qrcode_key':'secret'}
            entered.set();release.wait(2);return {'code':0}
        login=QRLogin(transport=transport)
        login.start();thread=threading.Thread(target=login.poll);thread.start();entered.wait(2)
        self.assertEqual(login.poll()['state'],'waiting_scan')
        login.cancel();release.set();thread.join()
        self.assertEqual(login.state,'cancelled')

    def test_timeout_error_and_expiry(self):
        now=[0]
        login=QRLogin(clock=lambda:now[0],transport=lambda *args:{'url':'https://passport.bilibili.com/qr','qrcode_key':'secret'})
        login.start();now[0]=181
        self.assertEqual(login.poll()['state'],'expired')
        login.transport=lambda *args: (_ for _ in ()).throw(RuntimeError('secret-url-token'))
        result=login.start()
        self.assertEqual(result['state'],'error');self.assertNotIn('secret',str(result))
        login.transport=lambda action,key=None:{'url':'https://passport.bilibili.com/qr','qrcode_key':'secret'} if action=='generate' else {'code':86038}
        login.start();self.assertEqual(login.poll()['state'],'expired')

    def test_expired_credentials_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CredentialStore(Path(tmp)/'private/session',clock=lambda:2000000001)
            jar=http.cookiejar.CookieJar();jar.set_cookie(cookie());store.save(jar)
            with self.assertRaisesRegex(ValueError,'已失效'):store.load()
            self.assertFalse(store.path.exists())

class InjectionTests(unittest.TestCase):
    def test_ytdlp_in_memory_injection(self):
        import sys
        import types
        from unittest.mock import patch
        from mediadesk.bilibili_login import ytdlp_main
        class Base:
            pass
        fake=types.SimpleNamespace(YoutubeDL=Base)
        jar=http.cookiejar.CookieJar();jar.set_cookie(cookie())
        def main():
            client=fake.YoutubeDL()
            self.assertIs(client.cookiejar,jar)
            self.assertIs(client.cookiejar,jar)
            client.save_cookies()
        fake.main=main
        with patch.dict(sys.modules,{'yt_dlp':fake}), patch.object(CredentialStore,'load',return_value=jar):
            ytdlp_main()
