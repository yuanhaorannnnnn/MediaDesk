"""YouTube adapter: use OAuth-backed plugin on the current machine."""
import json
import importlib.util
import shutil
import sys
import os
import subprocess
from pathlib import Path

# Existing plugin already owns the user's credential lifecycle. A packaged app
# can override both paths without importing a second Python runtime into GTK.
SCRIPT = Path(os.environ.get('MEDIADESK_YOUTUBE_SCRIPT', str(Path(__file__).with_name('oauth_bridge.py'))))
def helper_python():
    explicit=os.environ.get('MEDIADESK_YOUTUBE_PYTHON')
    if explicit:return explicit
    try:
        if importlib.util.find_spec('google.auth') and importlib.util.find_spec('google_auth_oauthlib'):return sys.executable
    except ModuleNotFoundError:pass
    return shutil.which('python3') or sys.executable

PYTHON=helper_python()


def list_youtube(kind, playlist_id=''):
    if kind not in ('auth','channel','subscriptions','likes','playlists','playlist-items'): raise ValueError('不支持的 YouTube 列表')
    if not SCRIPT.is_file() or not Path(PYTHON).is_file(): raise ValueError('YouTube 连接组件不可用，请检查设置')
    args=[PYTHON,str(SCRIPT),kind]
    if kind=='playlist-items': args+=[playlist_id]
    p=subprocess.run(args,capture_output=True,text=True,timeout=330 if kind=='auth' else 120)
    if p.returncode: raise ValueError((p.stderr.strip().splitlines()[-1] if p.stderr.strip() else '读取 YouTube 失败：请检查账号授权、网络或 API 配额')[:220])
    return json.loads(p.stdout)

def stream_youtube(kind,on_page,playlist_id=''):
    if kind not in ('likes','playlist-items'):raise ValueError('不支持分批读取此列表')
    if not SCRIPT.is_file() or not Path(PYTHON).is_file():raise ValueError('YouTube 连接组件不可用，请检查设置')
    args=[PYTHON,str(SCRIPT),kind]
    if kind=='playlist-items':args.append(playlist_id)
    args.append('--stream')
    with subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as proc:
        try:
            for line in proc.stdout:
                page=json.loads(line)
                if not isinstance(page,list):raise ValueError('YouTube 返回了无效的列表')
                on_page(page)
        except Exception:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            raise
        error=proc.stderr.read();code=proc.wait()
        if code:raise ValueError((error.strip().splitlines()[-1] if error.strip() else '读取 YouTube 失败：请检查账号授权、网络或 API 配额')[:220])


def duration_seconds(value):
    import re
    match=re.fullmatch(r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',value or '')
    if not match:return None
    days,hours,minutes,seconds=(int(x or 0) for x in match.groups())
    return days*86400+hours*3600+minutes*60+seconds


def normalize(item, kind):
    sn=item.get('snippet') or {}; details=item.get('contentDetails') or {}
    vid=(details.get('videoId') or (sn.get('resourceId') or {}).get('videoId')) if kind=='playlist-items' else item.get('id')
    return {'title':sn.get('title') or '未命名','channel':sn.get('videoOwnerChannelTitle') or sn.get('channelTitle') or '', 'description':sn.get('description') or '', 'thumbnail':((sn.get('thumbnails') or {}).get('high') or (sn.get('thumbnails') or {}).get('medium') or {}).get('url') or '', 'published':sn.get('publishedAt'), 'duration':duration_seconds(details.get('duration')), 'url':'https://www.youtube.com/watch?v='+vid if isinstance(vid,str) and kind in ('likes','playlist-items') else '', 'source_id':vid}


def thumbnail(store, url):
    """Cache source artwork privately; restrict hosts and redirects."""
    import hashlib
    from urllib.parse import urlparse
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    allowed={'i.ytimg.com','img.youtube.com','yt3.ggpht.com','yt3.googleusercontent.com'}
    def valid(value):
        p=urlparse(value);host=(p.hostname or '').lower();return p.scheme=='https' and not p.username and not p.password and (host in allowed or host.endswith('.hdslb.com'))
    parsed=urlparse(url)
    if parsed.scheme=='http' and (parsed.hostname or '').lower().endswith('.hdslb.com') and not parsed.username and not parsed.password:
        url=parsed._replace(scheme='https').geturl()
    if not valid(url):return None
    folder=store.root/'thumbnails';folder.mkdir(mode=0o700,exist_ok=True)
    path=folder/(hashlib.sha256(url.encode()).hexdigest()+'.img')
    if path.is_file():return str(path)
    class SafeRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not valid(newurl): raise ValueError('图片重定向不受支持')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    response=build_opener(SafeRedirect).open(Request(url,headers={'User-Agent':'MediaDesk/1'}),timeout=15)
    if response.headers.get_content_type() not in ('image/jpeg','image/png','image/webp'):return None
    data=response.read(4*1024*1024+1)
    if len(data)>4*1024*1024:return None
    import tempfile
    fd,tmp=tempfile.mkstemp(dir=folder,prefix='.image-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return str(path)
