"""User-initiated Bilibili web QR login; this is not OAuth.

Only Set-Cookie credentials are retained, until their server-provided expiry. Refresh tokens
and the SSO response URL are deliberately ignored.
"""
import ctypes
import http.cookiejar
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

from .paths import data_dir


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('登录接口重定向被拒绝')


def _protect(data, decrypt=False):
    if os.name != 'nt':
        return data
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    crypt = ctypes.windll.crypt32
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError('无法保护本机登录凭证')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


class CredentialStore:
    def __init__(self, path=None, clock=time.time):
        self.path = Path(path) if path else data_dir() / 'bilibili-session' / 'credentials'
        self.clock = clock

    def save(self, jar):
        cookies = [dict(name=c.name, value=c.value, domain=c.domain, path=c.path,
                        secure=c.secure, expires=c.expires) for c in jar
                   if c.domain.lstrip('.') in ('bilibili.com', 'passport.bilibili.com', 'api.bilibili.com')]
        if not any(c['name'] == 'SESSDATA' and c['value'] for c in cookies):
            raise ValueError('未收到 B 站会话凭证，请重试')
        expiry = next(c['expires'] for c in cookies if c['name'] == 'SESSDATA')
        payload = _protect(json.dumps({'until': expiry or self.clock()+86400, 'cookies': cookies}).encode())
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.is_symlink():
            raise ValueError('登录凭证目录无效')
        if os.name != 'nt':
            os.chmod(self.path.parent, 0o700)
        temporary = self.path.with_name('.session-' + secrets.token_hex(12))
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(payload)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self):
        self.path.unlink(missing_ok=True)

    def load(self):
        try:
            if self.path.is_symlink():
                raise ValueError()
            if os.name != 'nt' and self.path.stat().st_mode & 0o077:
                raise ValueError()
            data = json.loads(_protect(self.path.read_bytes(), decrypt=True))
            if data['until'] <= self.clock():
                self.clear()
                raise ValueError()
            jar = http.cookiejar.CookieJar()
            for c in data['cookies']:
                if c['domain'].lstrip('.') not in ('bilibili.com', 'passport.bilibili.com', 'api.bilibili.com'):
                    raise ValueError()
                jar.set_cookie(http.cookiejar.Cookie(0,c['name'],c['value'],None,False,c['domain'],True,c['domain'].startswith('.'),c['path'],True,c['secure'],c['expires'],False,None,None,{}))
            return jar
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('扫码登录已失效，请重新连接') from None


class QRLogin:
    def __init__(self, store=None, clock=time.monotonic, transport=None):
        self.store = store or CredentialStore()
        self.clock = clock
        self.jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar), NoRedirect())
        self.transport = transport or self._request
        self._lock = threading.Lock()
        self._generation = 0
        self._key = None
        self.state = 'idle'
        self._busy = False

    def _request(self, action, key=None):
        url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/' + action
        if key:
            url += '?' + urlencode({'qrcode_key':key})
        with self.opener.open(Request(url, headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.bilibili.com/', 'Origin':'https://www.bilibili.com'}), timeout=10) as response:
            result = json.load(response)
        if result.get('code') != 0 or not isinstance(result.get('data'), dict):
            raise ValueError()
        return result['data']

    def start(self):
        with self._lock:
            if self._busy:
                return {'state':self.state}
            self._generation += 1
            generation = self._generation
            self._busy = True
            self.state = 'generating'
            self.jar.clear()
        try:
            data = self.transport('generate')
            parsed = urlparse(data['url'])
            if parsed.scheme != 'https' or parsed.hostname not in ('passport.bilibili.com', 'account.bilibili.com') or parsed.username or parsed.password:
                raise ValueError()
            if not isinstance(data['qrcode_key'], str) or not data['qrcode_key']:
                raise ValueError()
            with self._lock:
                if generation != self._generation:
                    return {'state':self.state}
                self._key = data['qrcode_key']
                self._deadline = self.clock()+180
                self.state = 'waiting_scan'
                return {'state':self.state, 'qr_url':data['url'], 'expires_in':180}
        except Exception as exc:
            with self._lock:
                if generation == self._generation:
                    self.state = 'error'
                message = 'B 站暂时拒绝扫码请求，请稍后重试' if isinstance(exc, HTTPError) and exc.code == 412 else '无法生成二维码，请检查网络后重试'
                return {'state':self.state, 'message':message}
        finally:
            with self._lock:
                self._busy = False

    def poll(self):
        with self._lock:
            if self.state not in ('waiting_scan', 'waiting_confirm') or self._busy:
                return {'state':self.state}
            if self.clock() >= self._deadline:
                self.state = 'expired'
                self._key = None
                return {'state':self.state}
            generation, key = self._generation, self._key
            self._busy = True
        try:
            data = self.transport('poll', key)
            with self._lock:
                if generation != self._generation:
                    return {'state':self.state}
                self.state = {86101:'waiting_scan',86090:'waiting_confirm',86038:'expired',0:'success'}.get(data.get('code'), 'error')
                if self.state == 'success':
                    self.store.save(self.jar)
                if self.state not in ('waiting_scan','waiting_confirm'):
                    self._key = None
                    self.jar.clear()
                return {'state':self.state}
        except Exception:
            with self._lock:
                if generation == self._generation:
                    self.state = 'error'
                    self._key = None
                    self.jar.clear()
                return {'state':self.state, 'message':'登录未完成，请重新生成二维码'}
        finally:
            with self._lock:
                self._busy = False

    def cancel(self):
        with self._lock:
            self._generation += 1
            self.state = 'cancelled'
            self._key = None
            self.jar.clear()
        return {'state':'cancelled'}

    def clear_credentials(self):
        self.cancel()
        self.store.clear()


def ytdlp_main():
    """Pass credentials directly in memory, never through argv or a cookie file."""
    import yt_dlp
    original = yt_dlp.YoutubeDL
    class SessionYoutubeDL(original):
        @property
        def cookiejar(self):
            if not hasattr(self, '_bilibili_jar'):
                self._bilibili_jar = CredentialStore().load()
            return self._bilibili_jar
        def save_cookies(self):
            pass
    yt_dlp.YoutubeDL = SessionYoutubeDL
    yt_dlp.main()


if __name__ == '__main__':
    ytdlp_main()
