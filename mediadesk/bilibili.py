"""Read the user's Bilibili lists with their explicitly permitted Chrome session."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

from .downloader import environment, executable


def cookie_error(exc):
    if os.name!='nt':return '无法读取 Chrome 登录状态，请检查浏览器和系统密钥环'
    chain=[];seen=set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc));chain.append(exc);exc=exc.__cause__ or exc.__context__
    text='\n'.join(str(error).lower() for error in chain)
    if 'could not find chrome cookies database' in text:
        return '未发现 Chrome 登录数据，请在同一 Windows 用户的 Chrome 中登录 B 站后重试'
    if any(isinstance(error,PermissionError) for error in chain) or 'could not copy chrome cookie database' in text:
        return '无法读取 Chrome 登录数据库，请完全退出 Chrome 后刷新；若仍失败，请检查当前用户的读取权限'
    if 'failed to decrypt with dpapi' in text or any(term in text for term in ('app-bound encryption','application-bound encryption','app bound encryption')):
        return '当前环境无法解密 Chrome 的受保护登录状态；可先跳过 B 站账号连接'
    return '无法读取 Chrome 登录状态，请在同一 Windows 用户的 Chrome 中登录 B 站，完全退出 Chrome 后刷新；若仍失败，可先跳过账号连接'


class Client:
    def __init__(self, auth_source="chrome"):
        import yt_dlp
        for key in ('DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR'):
            value=environment().get(key)
            if value:os.environ.setdefault(key,value)
        try:
            if auth_source == 'qr':
                from .bilibili_login import CredentialStore
                jar = CredentialStore().load()
            elif auth_source != 'chrome':
                raise ValueError('不支持的登录方式')
            else:
                self.ydl=yt_dlp.YoutubeDL({'quiet':True,'no_warnings':True,'cookiesfrombrowser':('chrome',None,None if os.name=='nt' else 'GNOMEKEYRING')})
                jar=self.ydl.cookiejar
        except Exception as exc:
            raise ValueError(cookie_error(exc)) from None
        class SafeRedirect(HTTPRedirectHandler):
            def redirect_request(self,req,fp,code,msg,headers,newurl):
                p=urlparse(newurl)
                if p.scheme!='https' or p.hostname!='api.bilibili.com' or p.username or p.password:
                    raise ValueError('B 站接口重定向地址不受支持')
                return super().redirect_request(req,fp,code,msg,headers,newurl)
        self.opener=build_opener(HTTPCookieProcessor(jar),SafeRedirect)
        nav=self.get('/x/web-interface/nav')
        if not nav.get('isLogin') or not nav.get('mid'):raise ValueError('未检测到 B 站登录，请先在 Chrome 登录')
        self.mid=int(nav['mid']);self.name=str(nav.get('uname') or '')

    def get(self,path,**params):
        url='https://api.bilibili.com'+path+('?' + urlencode(params) if params else '')
        request=Request(url,headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36','Referer':'https://www.bilibili.com/'})
        try:
            with self.opener.open(request,timeout=25) as response:
                data=json.load(response)
        except Exception as exc:raise ValueError('无法连接 B 站，请检查网络后重试') from exc
        code=data.get('code')
        if code==-101:raise ValueError('无法识别 B 站登录，请检查 Chrome 登录状态或更新 yt-dlp')
        if code!=0:raise ValueError(f'B 站读取失败（代码 {code}），请检查登录状态或稍后重试')
        if not isinstance(data.get('data'),dict):raise ValueError('B 站返回了无效的数据')
        return data['data']

    def followings(self,on_page):
        page=1;seen=set()
        while True:
            data=self.get('/x/relation/followings',vmid=self.mid,pn=page,ps=50)
            items=data.get('list');total=data.get('total')
            if not isinstance(items,list) or not isinstance(total,int):raise ValueError('B 站关注列表数据不完整')
            if not items:
                if len(seen)<total:raise ValueError('关注列表未读完，请重试')
                break
            fresh=[x for x in items if x.get('mid') not in seen]
            if not fresh:raise ValueError('关注列表分页重复，请稍后重试')
            seen.update(x.get('mid') for x in fresh);on_page(fresh)
            if len(seen)>=total:break
            page+=1
            if page>1000:raise ValueError('关注列表页数异常，请稍后重试')

    def folders(self):
        data=self.get('/x/v3/fav/folder/created/list-all',up_mid=self.mid)
        items=data.get('list') or []
        if not isinstance(items,list):raise ValueError('B 站收藏夹数据不完整')
        return items

    def favorites(self,fid,on_page):
        if not re.fullmatch(r'[0-9]+',str(fid)):raise ValueError('收藏夹编号无效')
        page=1;seen=set()
        while True:
            data=self.get('/x/v3/fav/resource/list',media_id=fid,pn=page,ps=20)
            items=data.get('medias') or [];more=data.get('has_more')
            if not isinstance(items,list) or not isinstance(more,bool):raise ValueError('B 站收藏内容数据不完整')
            fresh=[]
            for item in items:
                key=(item.get('type'),item.get('id'))
                if key not in seen:seen.add(key);fresh.append(item)
            if more and not fresh:raise ValueError('收藏列表分页中断，请稍后重试')
            if fresh:on_page(fresh)
            if not more:break
            page+=1
            if page>1000:raise ValueError('收藏列表页数异常，请稍后重试')


def normalize(item):
    bv=item.get('bvid') or item.get('bv_id') or ''
    url=f'https://www.bilibili.com/video/{bv}' if re.fullmatch(r'BV[0-9A-Za-z]{10}',bv) else ''
    attr=item.get('attr',0);unavailable=item.get('title')=='已失效视频' or (isinstance(attr,int) and bool(attr&1))
    return {'title':item.get('title') or '已失效或不可用内容','channel':(item.get('upper') or {}).get('name') or '',
            'thumbnail':item.get('cover') or '', 'description':item.get('intro') or '', 'duration':item.get('duration'),
            'url':url,'source':'bilibili','unavailable':unavailable or not url}


def stream(kind,on_page,fid='',auth_source='chrome'):
    if kind not in ('followings','folders','favorites','status'):raise ValueError('不支持的 B 站列表')
    interpreter=sys.executable
    try:
        with open(executable(),'rb') as f:line=f.readline(512).decode('utf-8').strip()
        if line.startswith('#!'):
            candidate=line[2:].strip()
            if candidate.startswith('/') and ' ' not in candidate and Path(candidate).is_file():interpreter=candidate
    except (OSError,UnicodeError):pass
    env=environment();root=str(Path(__file__).resolve().parent.parent)
    env['PYTHONPATH']=root+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    with subprocess.Popen([interpreter,'-m','mediadesk.bilibili',kind,str(fid),auth_source],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8' if os.name=='nt' else None,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0) as proc:
        try:
            for line in proc.stdout:
                data=json.loads(line)
                if not isinstance(data,list):raise ValueError('B 站返回了无效的列表')
                on_page(data)
        except Exception:
            proc.terminate();proc.wait();raise
        error=proc.stderr.read();code=proc.wait()
        if code:raise ValueError(error.strip().splitlines()[-1][:220] if error.strip() else 'B 站读取失败，请检查登录状态')


def main():
    def page(items):print(json.dumps(items,ensure_ascii=False),flush=True)
    try:
        client=Client(sys.argv[3] if len(sys.argv)>3 else 'chrome');kind=sys.argv[1]
        if kind=='status':page([{'name':client.name}])
        elif kind=='folders':page(client.folders())
        elif kind=='followings':client.followings(page)
        elif kind=='favorites':client.favorites(sys.argv[2],page)
        else:raise ValueError('不支持的 B 站列表')
    except Exception as exc:
        print(str(exc) if isinstance(exc,ValueError) else 'B 站读取失败，请检查登录状态和 yt-dlp 版本',file=sys.stderr);sys.exit(1)


if __name__=='__main__':main()
