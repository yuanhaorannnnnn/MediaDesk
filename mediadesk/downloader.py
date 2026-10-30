"""yt-dlp jobs; user-selected formats and credentials remain local."""
import json
import errno
import hashlib
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse
from .store import identify_url


def executable():
    explicit=os.environ.get('MEDIADESK_YTDLP')
    preferred=Path.home()/'.local/share/youtube-download/bin/yt-dlp'
    candidate=explicit or (str(preferred) if preferred.is_file() else shutil.which('yt-dlp'))
    if not candidate: raise ValueError('未找到 yt-dlp；请安装后重试')
    return candidate


def command(cookies=False):
    args=[executable(),'--ignore-config','--no-playlist']
    if shutil.which('node'):
        try:
            help_text=subprocess.run([args[0],'--ignore-config','--help'],capture_output=True,text=True,errors='replace',timeout=2)
            if help_text.returncode==0 and '--js-runtimes' in help_text.stdout:args+=['--js-runtimes','node']
        except (OSError,subprocess.TimeoutExpired):pass
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
            if any(x in lower for x in ('network is unreachable','connection timed out','timed out','timeout','name or service not known','temporary failure in name resolution','connection reset','connection refused','remote end closed','incomplete read','incompleteread')):return '网络连接中断或超时；请检查网络后重新尝试'
            if 'no space left on device' in lower:return '磁盘空间不足，请释放空间后重试'
            if 'ffmpeg' in lower and ('not found' in lower or 'not installed' in lower):return '缺少 FFmpeg，无法合并音视频'
            return re.sub(r'https?://\S+', '[链接已隐藏]', message)[:300]
    return '无法完成下载；请检查网络、登录状态或 yt-dlp 版本'

def progress_percent(detail):
    match=re.search(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%',detail)
    if not match:return None
    value=float(match.group(1))
    return value if 0<=value<=100 else None


VERIFY_FAILED='文件未通过音视频流检查；已保留原文件，重新尝试将使用新文件'
STRICT_FAILED='文件未通过严格解码检查；已保留原文件，重新尝试将使用新文件'


def reports_download_risk(line):
    text=line.lower()
    return ('warning:' in text or 'error:' in text or text.startswith('[download]')) and any(x in text for x in ('retrying','retry in','timed out','timeout','connection reset','connection aborted','remote end closed','incomplete read','incompleteread','interrupted'))


def leader_state(proc):
    """Check our child without reaping it, preserving the process-group identity."""
    if proc.returncode is not None:raise ChildProcessError('下载进程身份已失效')
    return os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is not None


def finish_process(proc):
    """Wait without reaping, stop descendants, then reap the group leader."""
    import signal
    if proc.returncode is not None:raise ChildProcessError('下载进程身份已失效')
    os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOWAIT)
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    return proc.wait(timeout=3)


def stop_process(proc,paused=False,lock=None):
    """Only signal the group while its unreaped leader anchors the PGID."""
    import signal,time
    lock=lock or threading.Lock()
    with lock:
        try:leader_state(proc)
        except (ChildProcessError,OSError):return False
        try:
            if paused:os.killpg(proc.pid,signal.SIGCONT)
            os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        except OSError:return False
    end=time.monotonic()+3
    while time.monotonic()<end:
        with lock:
            try:
                if leader_state(proc):break
            except (ChildProcessError,OSError):return False
        time.sleep(.05)
    # The leader remains unreaped, so its ID cannot be reassigned here.
    with lock:
        try:leader_state(proc);os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        except (ChildProcessError,OSError):return False
    end=time.monotonic()+3
    while time.monotonic()<end:
        with lock:
            try:
                if leader_state(proc):
                    try:proc.wait(timeout=.1);return True
                    except (subprocess.TimeoutExpired,OSError):return False
            except (ChildProcessError,OSError):return False
        time.sleep(.05)
    return False


def probe_output(proc,is_paused):
    import selectors,time
    output=bytearray();elapsed=0;last=time.monotonic()
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout,selectors.EVENT_READ)
        while True:
            ready=selector.select(.2);now=time.monotonic()
            if not is_paused():elapsed+=now-last
            last=now
            if elapsed>=60:raise ValueError('读取音视频信息超时；文件已保留，请重试')
            if ready:
                chunk=os.read(proc.stdout.fileno(),65536)
                if not chunk:break
                output.extend(chunk)
                if len(output)>1024*1024:raise ValueError('音视频信息异常；文件已保留，请重试')
    return output


def inspect(url, cookies=False):
    identity=identify_url(url);sid=identity['id'];url=identity['url']
    try:p=subprocess.run(command(cookies)+['--dump-single-json','--skip-download','--',url],capture_output=True,text=True,timeout=120,env=environment())
    except subprocess.TimeoutExpired:raise ValueError('获取视频资料超时，请检查网络后重试') from None
    if p.returncode: raise ValueError(error_message(p.stderr))
    raw=json.loads(p.stdout); fs=[]
    for f in raw.get('formats') or []:
        fid=str(f.get('format_id') or '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',fid): continue
        if (f.get('vcodec') or 'none')=='none' and (f.get('acodec') or 'none')=='none': continue
        fs.append({k:f.get(k) for k in ('format_id','ext','format_note','resolution','height','vcodec','acodec','filesize','filesize_approx')})
    return {'url':url,'title':raw.get('title') or sid,'channel':raw.get('channel') or raw.get('uploader') or '', 'description':raw.get('description') or '', 'thumbnail':raw.get('thumbnail') or '', 'duration':raw.get('duration'), 'published':raw.get('upload_date'), 'formats':fs}

def online_stream(url,cookies=False):
    identity=identify_url(url);sid=identity['id'];source=identity['url']
    fmt='best[protocol=https]/best[protocol=m3u8_native]' if identity['source']=='youtube' else 'best[protocol=https]/bestvideo[protocol=https]+bestaudio[protocol=https]'
    args=command(cookies)+['-f',fmt,'--dump-single-json','--skip-download','--',source]
    try:p=subprocess.run(args,capture_output=True,text=True,timeout=120,env=environment())
    except subprocess.TimeoutExpired:raise ValueError('获取播放地址超时，请检查网络后重试') from None
    if p.returncode:
        error=error_message(p.stderr)
        raise ValueError('没有可同时播放画面和声音的格式；可尝试下载或查看来源' if '所选格式已不可用' in error else error)
    raw=json.loads(p.stdout);selected=raw.get('requested_formats') or [raw]
    video=next((f for f in selected if f.get('vcodec') not in (None,'none')),None)
    audio=next((f for f in selected if f.get('acodec') not in (None,'none')),None)
    if not video or not audio:raise ValueError('未找到同时包含画面和声音的在线播放格式')
    domains=('googlevideo.com','youtube.com') if identity['source']=='youtube' else ('bilivideo.com','bilivideo.cn')
    def valid(f):
        parsed=urlparse(f.get('url') or '');host=(parsed.hostname or '').lower()
        return parsed.scheme=='https' and not parsed.username and not parsed.password and any(host==d or host.endswith('.'+d) for d in domains)
    if not valid(video) or not valid(audio):raise ValueError('未找到受支持的在线播放地址')
    stream=video['url'];audio_url=audio['url'] if audio is not video else ''
    headers=video.get('http_headers') or raw.get('http_headers') or {};agent=headers.get('User-Agent','')
    if not isinstance(agent,str) or len(agent)>1024 or '\n' in agent or '\r' in agent:agent=''
    return {'url':stream,'audio_url':audio_url,'referer':source if identity['source']=='bilibili' else '', 'user_agent':agent,'resolution':video.get('resolution') or raw.get('resolution') or '', 'item':{'url':source,'title':raw.get('title') or sid,'channel':raw.get('channel') or raw.get('uploader') or '', 'description':raw.get('description') or '', 'thumbnail':raw.get('thumbnail') or '', 'duration':raw.get('duration'), 'published':raw.get('upload_date')}}


class Downloads:
    def __init__(self,store,notify):
        self.store=store;self.notify=notify;self.processes={};self.workers={};self.active=set();self.deleting=set();self.paused=set();self.cancelled=set();self.pending_states={};self.lock=threading.Lock();self.stopping=False

    def reconcile(self):
        with self.lock:
            for jid,(mid,state,detail) in list(self.pending_states.items()):
                try:self.store.job(jid,mid,state,detail)
                except Exception:return False
                self.pending_states.pop(jid,None)
        return True

    def start(self,item,preference='quality',cookies=False,fmt=None,audio_only=False,job_id=None):
        if fmt and not re.fullmatch(r'[A-Za-z0-9_.-]+(?:\+[A-Za-z0-9_.-]+)?',fmt):raise ValueError('格式无效')
        identity=identify_url(item['url']);mid=self.store.save_source(item);jid=job_id or uuid.uuid4().hex
        with self.lock:
            if self.stopping:raise ValueError('应用正在关闭')
            if mid in self.active or mid in self.deleting:raise ValueError('该视频正在下载或正在停止')
            if any(j['media_id']==mid and j['state']=='停止未确认' for j in self.store.jobs()):raise ValueError('该视频的旧任务未确认停止；请先检查后台进程并保留文件删除旧任务')
            previous=next((j for j in self.store.jobs() if j['id']==jid),None) if job_id else None
            try:oldopts=json.loads(previous.get('options') or '{}') if previous else {}
            except (ValueError,TypeError):oldopts={}
            if not isinstance(oldopts,dict):oldopts={}
            retry_file=oldopts.get('verification_retry',0)
            if not isinstance(retry_file,int) or isinstance(retry_file,bool) or retry_file<0:raise ValueError('无法读取重试记录，请检查任务数据')
            if previous and previous.get('detail') in (VERIFY_FAILED,STRICT_FAILED):retry_file+=1
            strict=bool(oldopts.get('needs_strict_check')) or bool(previous and previous['state'] in ('中断','失败'))
            options={'preference':preference,'cookies':cookies,'fmt':fmt,'audio_only':audio_only,'verification_retry':retry_file,'needs_strict_check':strict}
            # Persist the retry filename before clearing a previous verification failure.
            if previous:self.store.job_options(jid,options)
            self.store.job(jid,mid,'等待','等待下载')
            try:
                if not previous:self.store.job_options(jid,options)
            except Exception:
                try:self.store.job(jid,mid,'失败','无法保存任务设置，请重试')
                except Exception:pass
                raise
            self.active.add(mid);finished=threading.Event();self.workers[jid]=finished
        def update(state,detail=''):
            with self.lock:
                if jid in self.cancelled or (state=='下载中' and jid in self.paused):return False
                self.store.job(jid,mid,state,detail)
                self.pending_states.pop(jid,None)
            self.notify(jid);return True
        def run():
            nonlocal strict
            group_finished=False
            try:
                if not update('下载中','准备下载'):return
                if item.get('thumbnail'):
                    try:
                        from .sources import thumbnail
                        thumbnail(self.store,item['thumbnail'])
                    except Exception:pass
                with self.lock:
                    if jid in self.cancelled or self.stopping:return
                suffix=('.retry-'+hashlib.sha256(jid.encode()).hexdigest()[:16]+'-'+str(retry_file)) if retry_file else ''
                template='%(title).180B ['+(identity['file_id'] if identity['source']=='bilibili' else '%(id)s')+']'+suffix+'.%(ext)s'
                args=command(cookies)+['--socket-timeout','30','--no-overwrites','--continue','--newline','--progress','--print','after_move:filepath','-P',str(self.store.media_dir),'-o',template]
                if fmt:args+=['-f',fmt]
                elif preference=='size':args+=['-S','+size,+br,+res']
                elif preference=='balance':args+=['-S','res:1080']
                args+=['--',item['url']]
                with self.lock:
                    if jid in self.cancelled or self.stopping:return
                    proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',env=environment(),start_new_session=True)
                    self.processes[jid]=proc
                tail=[];last_update=0;last_progress=None;last_speed_known=False
                import time
                for line in proc.stdout:
                    line=line.strip();tail.append(line);tail=tail[-100:]
                    percent=progress_percent(line) if line.startswith('[download]') else None
                    unknown_speed=bool(re.search(r'\bat\s+Unknown\s+B/s\b',line,re.I))
                    known_speed=bool(re.search(r'\bat\s+[\d.]+\s*[KMGT]?i?B/s\b',line,re.I))
                    speed_reset=(percent is not None and percent>0 and last_progress is not None and percent>=last_progress and last_speed_known and unknown_speed)
                    if percent is not None:
                        last_progress=percent
                        if known_speed or unknown_speed:last_speed_known=known_speed
                    if not strict and (reports_download_risk(line) or speed_reset):
                        with self.lock:
                            if jid not in self.cancelled:
                                options['needs_strict_check']=True;self.store.job_options(jid,options);strict=True
                    if line.startswith('[download]') and '%' in line and time.monotonic()-last_update>1:
                        update('下载中',line[:180]);last_update=time.monotonic()
                    elif line.startswith('[youtube]') and ('Extracting URL' in line or 'Downloading webpage' in line):update('下载中','正在获取下载地址')
                    elif line.startswith('[info]') and 'Downloading' in line:update('下载中','等待下载数据')
                    elif line.startswith('[Merger]'):update('下载中','正在合并音视频')
                proc.stdout.close();os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOWAIT)
                with self.lock:code=finish_process(proc);group_finished=True;self.processes.pop(jid,None)
                with self.lock:
                    if jid in self.cancelled:return
                if code:raise ValueError(error_message('\n'.join(tail)))
                candidates=[Path(x).resolve() for x in tail if x.startswith(str(self.store.media_dir))]
                path=candidates[-1] if candidates else None
                if not path or not path.is_relative_to(self.store.media_dir.resolve()) or not path.is_file():raise ValueError('下载结束，但未找到最终文件')
                if not update('下载中','正在检验文件'):return
                with self.lock:
                    if jid in self.cancelled or self.stopping:return
                    self.processes.pop(jid,None)
                    try:proc=subprocess.Popen(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(path)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0,start_new_session=True)
                    except FileNotFoundError:raise ValueError('缺少 FFprobe，无法检查音视频；文件已保留') from None
                    self.processes[jid]=proc;group_finished=False
                def probe_paused():
                    with self.lock:return jid in self.paused
                raw=probe_output(proc,probe_paused);proc.stdout.close();os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOWAIT)
                with self.lock:code=finish_process(proc);group_finished=True;self.processes.pop(jid,None)
                with self.lock:
                    if jid in self.cancelled or self.stopping:return
                streams={v.get('codec_type') for v in json.loads(raw).get('streams',[])} if not code else set()
                required={'audio'} if audio_only else {'audio','video'}
                if not required.issubset(streams):raise ValueError(VERIFY_FAILED)
                if strict:
                    if not update('下载中','正在严格检查'):return
                    with self.lock:
                        if jid in self.cancelled or self.stopping:return
                        self.processes.pop(jid,None)
                        try:
                            proc=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(path),'-map','0:v?','-map','0:a?','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,errors='replace',start_new_session=True)
                        except FileNotFoundError:raise ValueError('缺少 FFmpeg，无法进行严格检查；文件已保留') from None
                        self.processes[jid]=proc;group_finished=False
                    errors=[]
                    for line in proc.stderr:errors.append(line.strip());errors=errors[-25:]
                    proc.stderr.close();os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOWAIT)
                    with self.lock:code=finish_process(proc);group_finished=True;self.processes.pop(jid,None)
                    with self.lock:
                        if jid in self.cancelled or self.stopping:return
                    if code:
                        if code<0:raise ValueError('严格检查意外中断，文件已保留；请重新尝试')
                        error=' '.join(errors).lower()
                        if any(x in error for x in ('decoder not found','unknown decoder','decoder (codec','error while opening decoder')):raise ValueError('缺少解码器或格式不受支持，无法严格检查；文件已保留')
                        raise ValueError(STRICT_FAILED)
                with self.lock:
                    if jid not in self.cancelled and not self.stopping:
                        self.store.set_path(mid,path);self.store.job(jid,mid,'完成',path.name)
                        self.pending_states.pop(jid,None)
            except Exception as exc:
                detail=('磁盘空间不足，请释放空间后重试' if isinstance(exc,OSError) and exc.errno==errno.ENOSPC else '找不到下载器或相关程序' if isinstance(exc,FileNotFoundError) else str(exc) if isinstance(exc,ValueError) else '下载失败，请检查网络和本机依赖')
                state='中断' if self.stopping else '失败';detail='应用关闭，下载可继续' if self.stopping else detail
                try:update(state,detail)
                except Exception:
                    with self.lock:self.pending_states[jid]=(mid,state,detail)
            finally:
                with self.lock:proc=self.processes.get(jid);paused=jid in self.paused
                stopped=group_finished or (stop_process(proc,paused,self.lock) if proc else True)
                if proc:
                    for stream in (proc.stdout,proc.stderr):
                        if stream:
                            try:stream.close()
                            except (OSError,ValueError):pass
                if not stopped:
                    try:update('停止未确认','无法确认后台进程已停止；请先检查进程，再保留文件删除任务并重新添加链接')
                    except Exception:
                        with self.lock:self.pending_states[jid]=(mid,'停止未确认','无法确认后台进程已停止；请先检查进程，再保留文件删除任务并重新添加链接')
                    def reap():
                        import time
                        try:proc.wait()
                        except Exception:return
                        while True:
                            try:os.killpg(proc.pid,0)
                            except ProcessLookupError:break
                            except OSError:return
                            time.sleep(1)
                        with self.lock:
                            self.processes.pop(jid,None);self.workers.pop(jid,None);self.active.discard(mid);self.paused.discard(jid);self.cancelled.discard(jid);finished.set()
                        self.notify(jid)
                    threading.Thread(target=reap,daemon=True).start();return
                with self.lock:
                    self.processes.pop(jid,None);self.workers.pop(jid,None);self.active.discard(mid);self.paused.discard(jid);self.cancelled.discard(jid);finished.set()
                self.notify(jid)
        try:threading.Thread(target=run,daemon=True).start()
        except Exception as exc:
            with self.lock:
                self.workers.pop(jid,None);self.active.discard(mid);finished.set()
                try:self.store.job(jid,mid,'失败','无法启动下载任务，请重试')
                except Exception:pass
            raise ValueError('无法启动下载任务，请重试') from exc
        self.notify(jid);return jid

    def pause(self,jid):
        import signal
        with self.lock:
            proc=self.processes.get(jid)
            if not proc:raise ValueError('任务正在准备或处理，请稍后再试')
            try:
                if leader_state(proc):raise ValueError('任务正在结束，请稍后再试')
            except (ChildProcessError,OSError):raise ValueError('无法确认下载进程状态') from None
            job=next((j for j in self.store.jobs() if j['id']==jid),None)
            try:os.killpg(proc.pid,signal.SIGSTOP)
            except ProcessLookupError:raise ValueError('任务已结束，请刷新任务列表') from None
            self.paused.add(jid)
            try:
                if job:self.store.job(jid,job['media_id'],'暂停',job['detail'])
            except Exception as exc:
                try:os.killpg(proc.pid,signal.SIGCONT);self.paused.discard(jid)
                except OSError:
                    if job:self.pending_states[jid]=(job['media_id'],'暂停',job['detail'])
                raise ValueError('无法保存下载状态，请检查磁盘或权限') from exc
        self.notify(jid)

    def resume(self,jid):
        import signal
        if not self.reconcile():raise ValueError('无法保存下载状态，请检查磁盘或权限')
        with self.lock:
            proc=self.processes.get(jid)
            try:running=bool(proc) and not leader_state(proc)
            except (ChildProcessError,OSError):raise ValueError('无法确认下载进程状态') from None
            if jid in self.paused and running:
                job=next((j for j in self.store.jobs() if j['id']==jid),None)
                try:os.killpg(proc.pid,signal.SIGCONT)
                except ProcessLookupError:raise ValueError('任务已结束，请刷新任务列表') from None
                try:
                    if job:self.store.job(jid,job['media_id'],'下载中',job['detail'])
                except Exception as exc:
                    try:os.killpg(proc.pid,signal.SIGSTOP)
                    except OSError:
                        self.paused.discard(jid)
                        if job:self.pending_states[jid]=(job['media_id'],'下载中',job['detail'])
                    raise ValueError('无法保存下载状态，请检查磁盘或权限') from exc
                self.paused.discard(jid)
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
        if not self.reconcile():raise ValueError('无法保存下载状态，请检查磁盘或权限')
        with self.lock:
            job=next((j for j in self.store.jobs() if j['id']==jid),None)
            if not job:raise ValueError('任务已不存在')
            mid=job['media_id'];proc=self.processes.get(jid);finished=self.workers.get(jid)
            if delete_files and job['state']=='停止未确认':raise ValueError('请先确认后台进程已退出；此任务只能保留文件删除')
            if mid in self.deleting:raise ValueError('该视频的任务正在删除')
            if delete_files and mid in self.active and not finished:raise ValueError('该视频有其他下载任务正在运行，请先停止它')
            self.deleting.add(mid);self.cancelled.add(jid)
            if proc:
                try:
                    leader_state(proc)
                    if jid in self.paused:os.killpg(proc.pid,signal.SIGCONT)
                    os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                except (ChildProcessError,OSError):
                    self.deleting.discard(mid);self.cancelled.discard(jid);raise ValueError('无法确认下载进程状态，任务和文件未删除') from None
        try:
            if finished and not finished.wait(3):
                with self.lock:
                    proc=self.processes.get(jid)
                    if proc:
                        try:leader_state(proc);os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        except (ChildProcessError,OSError):raise ValueError('无法确认下载进程状态，任务和文件未删除') from None
                if not finished.wait(22):raise ValueError('任务未能及时停止，任务和文件未删除；请稍后重试')
            if delete_files:
                media=self.store.get(mid)
                if not media or not media.get('url'):raise ValueError('找不到视频来源，无法安全确定文件')
                sid=identify_url(media['url'])['file_id'];root=self.store.media_dir.resolve()
                retry=r'(?:\.retry-'+hashlib.sha256(jid.encode()).hexdigest()[:16]+r'-\d+)?'
                pattern=re.compile(r'\['+re.escape(sid)+r'\]'+retry+r'\.(?:[A-Za-z0-9_-]+\.)*(?:mp4|mkv|webm|mov|avi|m4a|mp3|flac|ogg|opus|wav|aac|m4v|ts|m2ts|mka|m4b|3gp|3g2|mpeg|mpg|flv|wmv|wma|aif|aiff|part|ytdl)(?:-Frag\d+)?$',re.IGNORECASE)
                for path in root.iterdir():
                    if path.is_symlink() or not path.is_file() or not pattern.search(path.name):continue
                    path.unlink();self.store.clear_path_if_matches(mid,path)
            self.store.delete_job(jid)
            with self.lock:self.pending_states.pop(jid,None)
        except OSError as exc:
            with self.lock:self.pending_states[jid]=(mid,'中断','任务已停止，文件删除未完成；请重试')
            raise ValueError('部分文件可能未删除，任务记录已保留：'+str(exc)) from exc
        except Exception:
            if finished and finished.is_set():
                with self.lock:self.pending_states[jid]=(mid,'中断','任务已停止，但无法保存状态；请检查磁盘或权限')
            raise
        finally:
            with self.lock:
                self.deleting.discard(mid)
                if not finished or finished.is_set():self.cancelled.discard(jid)
            self.notify(jid)

    def stop_all(self):
        import signal,time
        with self.lock:
            self.stopping=True
            workers=dict(self.workers)
            for jid,proc in self.processes.items():
                try:
                    leader_state(proc)
                    if jid in self.paused:os.killpg(proc.pid,signal.SIGCONT)
                    os.killpg(proc.pid,signal.SIGTERM)
                except (ProcessLookupError,ChildProcessError):pass
                except OSError:pass
        deadline=time.monotonic()+3
        for finished in workers.values():finished.wait(max(0,deadline-time.monotonic()))
        with self.lock:
            for proc in self.processes.values():
                try:leader_state(proc);os.killpg(proc.pid,signal.SIGKILL)
                except (ProcessLookupError,ChildProcessError,OSError):pass
        deadline=time.monotonic()+3
        for finished in workers.values():finished.wait(max(0,deadline-time.monotonic()))
        with self.lock:
            try:jobs=self.store.jobs()
            except Exception:jobs=[]
            for job in jobs:
                if job['id'] not in workers or job['state']=='完成':continue
                stopped=workers[job['id']].is_set()
                if stopped and job['state'] not in ('等待','下载中','暂停','中断'):continue
                state='中断' if stopped else '停止未确认'
                detail='应用关闭，下载可继续' if stopped else '无法确认后台进程已停止；请先检查进程，再保留文件删除任务并重新添加链接'
                try:self.store.job(job['id'],job['media_id'],state,detail)
                except Exception:self.pending_states[job['id']]=(job['media_id'],state,detail)
