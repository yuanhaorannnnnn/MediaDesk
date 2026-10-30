"""yt-dlp jobs; user-selected formats and credentials remain local."""
import json
import errno
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse
from .store import youtube_id


def executable():
    explicit=os.environ.get('MEDIADESK_YTDLP')
    preferred=Path.home()/'.local/share/youtube-download/bin/yt-dlp'
    candidate=explicit or (str(preferred) if preferred.is_file() else shutil.which('yt-dlp'))
    if not candidate: raise ValueError('未找到 yt-dlp；请安装后重试')
    return candidate


def command(cookies=False):
    args=[executable(),'--ignore-config','--no-playlist']
    if shutil.which('node'): args+=['--js-runtimes','node']
    if cookies: args+=['--cookies-from-browser','chrome+gnomekeyring']
    return args


def environment():
    env=os.environ.copy(); sock=Path(f'/run/user/{os.getuid()}/bus')
    if sock.exists():
        env.setdefault('DBUS_SESSION_BUS_ADDRESS',f'unix:path={sock}');env.setdefault('XDG_RUNTIME_DIR',str(sock.parent))
    return env


def error_message(text):
    for line in text.splitlines():
        if 'ERROR:' in line:
            message=line.split('ERROR:',1)[1].strip()
            lower=message.lower()
            if any(x in lower for x in ('sign in','login required','authentication required','confirm you’re not a bot',"confirm you're not a bot")):return '需要账号登录或验证；请检查账号状态和下载设置'
            if 'requested format is not available' in lower:return '所选格式已不可用，请选择其他格式后重试'
            if any(x in lower for x in ('http error 429','too many requests')):return '请求过于频繁，请稍后重试'
            if any(x in lower for x in ('http error 403','http error 401')):return '来源拒绝访问；请检查账号权限和登录状态'
            if any(x in lower for x in ('network is unreachable','connection timed out','name or service not known','temporary failure in name resolution')):return '网络连接失败，请检查网络后重试'
            if 'no space left on device' in lower:return '磁盘空间不足，请释放空间后重试'
            if 'ffmpeg' in lower and ('not found' in lower or 'not installed' in lower):return '缺少 FFmpeg，无法合并音视频'
            return re.sub(r'https?://\S+', '[链接已隐藏]', message)[:300]
    return '无法完成下载；请检查网络、登录状态或 yt-dlp 版本'

def progress_percent(detail):
    match=re.search(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%',detail)
    if not match:return None
    value=float(match.group(1))
    return value if 0<=value<=100 else None


def inspect(url, cookies=False):
    sid=youtube_id(url);url='https://www.youtube.com/watch?v='+sid
    p=subprocess.run(command(cookies)+['--dump-single-json','--skip-download','--',url],capture_output=True,text=True,timeout=120,env=environment())
    if p.returncode: raise ValueError(error_message(p.stderr))
    raw=json.loads(p.stdout); fs=[]
    for f in raw.get('formats') or []:
        fid=str(f.get('format_id') or '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',fid): continue
        if (f.get('vcodec') or 'none')=='none' and (f.get('acodec') or 'none')=='none': continue
        fs.append({k:f.get(k) for k in ('format_id','ext','format_note','resolution','height','vcodec','acodec','filesize','filesize_approx')})
    return {'url':url,'title':raw.get('title') or sid,'channel':raw.get('channel') or raw.get('uploader') or '', 'description':raw.get('description') or '', 'thumbnail':raw.get('thumbnail') or '', 'duration':raw.get('duration'), 'published':raw.get('upload_date'), 'formats':fs}

def online_stream(url,cookies=False):
    sid=youtube_id(url);source='https://www.youtube.com/watch?v='+sid
    args=command(cookies)+['-f','best[protocol=https]/best[protocol=m3u8_native]','--dump-single-json','--skip-download','--',source]
    try:p=subprocess.run(args,capture_output=True,text=True,timeout=120,env=environment())
    except subprocess.TimeoutExpired:raise ValueError('获取播放地址超时，请检查网络后重试') from None
    if p.returncode:
        error=error_message(p.stderr)
        raise ValueError('没有可同时播放画面和声音的格式；可尝试下载或查看来源' if '所选格式已不可用' in error else error)
    raw=json.loads(p.stdout);stream=raw.get('url') or '';parsed=urlparse(stream);host=(parsed.hostname or '').lower()
    if parsed.scheme!='https' or parsed.username or parsed.password or not (host=='googlevideo.com' or host.endswith('.googlevideo.com') or host=='youtube.com' or host.endswith('.youtube.com')):
        raise ValueError('未找到可用的 YouTube 播放地址')
    if raw.get('vcodec') in (None,'none') or raw.get('acodec') in (None,'none'):
        raise ValueError('未找到同时包含画面和声音的在线播放格式')
    headers=raw.get('http_headers') or {};agent=headers.get('User-Agent','')
    if not isinstance(agent,str) or len(agent)>1024 or '\n' in agent or '\r' in agent:agent=''
    return {'url':stream,'user_agent':agent,'resolution':raw.get('resolution') or '', 'item':{'url':source,'title':raw.get('title') or sid,'channel':raw.get('channel') or raw.get('uploader') or '', 'description':raw.get('description') or '', 'thumbnail':raw.get('thumbnail') or '', 'duration':raw.get('duration'), 'published':raw.get('upload_date')}}


class Downloads:
    def __init__(self,store,notify):
        self.store=store;self.notify=notify;self.processes={};self.workers={};self.active=set();self.deleting=set();self.paused=set();self.cancelled=set();self.lock=threading.Lock();self.stopping=False

    def start(self,item,preference='quality',cookies=False,fmt=None,audio_only=False,job_id=None):
        if fmt and not re.fullmatch(r'[A-Za-z0-9_.-]+(?:\+[A-Za-z0-9_.-]+)?',fmt):raise ValueError('格式无效')
        mid=self.store.save_youtube(item);jid=job_id or uuid.uuid4().hex
        with self.lock:
            if self.stopping:raise ValueError('应用正在关闭')
            if mid in self.active or mid in self.deleting:raise ValueError('该视频正在下载或正在停止')
            self.active.add(mid)
            finished=threading.Event();self.workers[jid]=finished
            self.store.job(jid,mid,'等待','等待下载')
            self.store.job_options(jid,{'preference':preference,'cookies':cookies,'fmt':fmt,'audio_only':audio_only})
        self.notify(jid)
        def update(state,detail=''):
            with self.lock:
                if jid in self.cancelled or (state=='下载中' and jid in self.paused):return False
                self.store.job(jid,mid,state,detail)
            self.notify(jid);return True
        def run():
            try:
                if not update('下载中','准备下载'):return
                if item.get('thumbnail'):
                    try:
                        from .sources import thumbnail
                        thumbnail(self.store,item['thumbnail'])
                    except Exception:pass
                args=command(cookies)+['--no-overwrites','--continue','--newline','--progress','--print','after_move:filepath','-P',str(self.store.media_dir),'-o','%(title).180B [%(id)s].%(ext)s']
                if fmt:args+=['-f',fmt]
                elif preference=='size':args+=['-S','+size,+br,+res']
                elif preference=='balance':args+=['-S','res:1080']
                args+=['--',item['url']]
                with self.lock:
                    if jid in self.cancelled or self.stopping:return
                    proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=environment(),start_new_session=True)
                    self.processes[jid]=proc
                tail=[];last_update=0
                import time
                for line in proc.stdout:
                    line=line.strip();tail.append(line);tail=tail[-100:]
                    if line.startswith('[download]') and '%' in line and time.monotonic()-last_update>1:
                        update('下载中',line[:180]);last_update=time.monotonic()
                    elif line.startswith('[youtube]') and ('Extracting URL' in line or 'Downloading webpage' in line):update('下载中','正在获取下载地址')
                    elif line.startswith('[info]') and 'Downloading' in line:update('下载中','等待下载数据')
                    elif line.startswith('[Merger]'):update('下载中','正在合并音视频')
                proc.stdout.close();code=proc.wait()
                with self.lock:
                    if jid in self.cancelled:return
                if code:raise ValueError(error_message('\n'.join(tail)))
                candidates=[Path(x).resolve() for x in tail if x.startswith(str(self.store.media_dir))]
                path=candidates[-1] if candidates else None
                if not path or not path.is_relative_to(self.store.media_dir.resolve()) or not path.is_file():raise ValueError('下载结束，但未找到最终文件')
                update('下载中','正在检验文件')
                probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(path)],capture_output=True,text=True,timeout=60)
                streams={v.get('codec_type') for v in json.loads(probe.stdout).get('streams',[])} if not probe.returncode else set()
                required={'audio'} if audio_only else {'audio','video'}
                if not required.issubset(streams):raise ValueError('文件已保存，但音视频流检查失败')
                with self.lock:
                    if jid not in self.cancelled and not self.stopping:
                        self.store.set_path(mid,path);self.store.job(jid,mid,'完成',path.name)
            except Exception as exc:
                detail=('磁盘空间不足，请释放空间后重试' if isinstance(exc,OSError) and exc.errno==errno.ENOSPC else '找不到下载器或相关程序' if isinstance(exc,FileNotFoundError) else str(exc) if isinstance(exc,ValueError) else '下载失败，请检查网络和本机依赖')
                update('中断' if self.stopping else '失败','应用关闭，下载可继续' if self.stopping else detail)
            finally:
                with self.lock:
                    self.processes.pop(jid,None);self.workers.pop(jid,None);self.active.discard(mid);self.paused.discard(jid);self.cancelled.discard(jid);finished.set()
                self.notify(jid)
        threading.Thread(target=run,daemon=True).start();return jid

    def pause(self,jid):
        import signal
        with self.lock:
            proc=self.processes.get(jid)
            if not proc or proc.poll() is not None:raise ValueError('任务正在准备或处理，请稍后再试')
            try:os.killpg(proc.pid,signal.SIGSTOP)
            except ProcessLookupError:raise ValueError('任务已结束，请刷新任务列表') from None
            self.paused.add(jid)
            job=next((j for j in self.store.jobs() if j['id']==jid),None)
            if job:self.store.job(jid,job['media_id'],'暂停',job['detail'])
        self.notify(jid)

    def resume(self,jid):
        import signal
        with self.lock:
            proc=self.processes.get(jid)
            if jid in self.paused and proc and proc.poll() is None:
                try:os.killpg(proc.pid,signal.SIGCONT)
                except ProcessLookupError:raise ValueError('任务已结束，请刷新任务列表') from None
                self.paused.discard(jid)
                job=next((j for j in self.store.jobs() if j['id']==jid),None)
                if job:self.store.job(jid,job['media_id'],'下载中',job['detail'])
                continuing=True
            else:continuing=False
        if continuing:self.notify(jid);return
        job=next((j for j in self.store.jobs() if j['id']==jid),None)
        if not job or job['state'] not in ('中断','失败','暂停'):raise ValueError('任务当前无法继续')
        media=self.store.get(job['media_id'])
        if not media or not media.get('url'):raise ValueError('找不到视频来源')
        try:opts=json.loads(job.get('options') or '{}')
        except (ValueError,TypeError):opts={}
        item={k:media[k] for k in ('url','title','channel','description','thumbnail','duration','published')}
        self.start(item,opts.get('preference',self.store.setting('preference','quality')),opts.get('cookies',self.store.setting('cookies',False)),opts.get('fmt'),opts.get('audio_only',False),job_id=jid)

    def delete(self,jid,delete_files=False):
        import signal
        with self.lock:
            job=next((j for j in self.store.jobs() if j['id']==jid),None)
            if not job:raise ValueError('任务已不存在')
            mid=job['media_id'];proc=self.processes.get(jid);finished=self.workers.get(jid)
            if mid in self.deleting:raise ValueError('该视频的任务正在删除')
            if delete_files and mid in self.active and not finished:raise ValueError('该视频有其他下载任务正在运行，请先停止它')
            self.deleting.add(mid);self.cancelled.add(jid)
            if proc and proc.poll() is None:
                try:
                    if jid in self.paused:os.killpg(proc.pid,signal.SIGCONT)
                    os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            if finished:self.store.job(jid,mid,'中断','正在停止任务')
        try:
            if finished and not finished.wait(25):raise ValueError('任务未能及时停止，任务和文件未删除；请稍后重试')
            if delete_files:
                media=self.store.get(mid)
                if not media or not media.get('url'):raise ValueError('找不到视频来源，无法安全确定文件')
                sid=youtube_id(media['url']);root=self.store.media_dir.resolve()
                pattern=re.compile(r'\['+re.escape(sid)+r'\]\.(?:[A-Za-z0-9_-]+\.)*(?:mp4|mkv|webm|mov|avi|m4a|mp3|flac|ogg|opus|wav|aac|m4v|part|ytdl)(?:-Frag\d+)?$',re.IGNORECASE)
                for path in root.iterdir():
                    if path.is_symlink() or not path.is_file() or not pattern.search(path.name):continue
                    path.unlink();self.store.clear_path_if_matches(mid,path)
            self.store.delete_job(jid)
        except OSError as exc:
            raise ValueError('部分文件可能未删除，任务记录已保留：'+str(exc)) from exc
        finally:
            with self.lock:
                self.deleting.discard(mid)
                if not finished or finished.is_set():self.cancelled.discard(jid)
            self.notify(jid)

    def stop_all(self):
        import signal
        with self.lock:
            self.stopping=True
            for jid,proc in self.processes.items():
                if proc.poll() is None:
                    try:
                        if jid in self.paused:os.killpg(proc.pid,signal.SIGCONT)
                        os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
            for job in self.store.jobs():
                if job['state'] in ('等待','下载中','暂停'):
                    self.store.job(job['id'],job['media_id'],'中断','应用关闭，下载可继续')
