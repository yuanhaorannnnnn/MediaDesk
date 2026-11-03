"""Google read-only authorization helper, isolated from the GUI runtime."""
import json
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google_auth_oauthlib import flow as google_flow
from oauthlib.oauth2.rfc6749 import errors as oauth_errors
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError, TransportError
import requests

if __package__:
    from .paths import google_config_dir
    from .oauth_config import read_client
else:
    from paths import google_config_dir
    from oauth_config import read_client
CONFIG=google_config_dir()
SCOPE='https://www.googleapis.com/auth/youtube.readonly'

class SafeOAuthError(ValueError):
    """Only application-authored messages may cross the helper boundary."""

def error_message(exc):
    seen=set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc,SafeOAuthError):return str(exc)
        if isinstance(exc,oauth_errors.AccessDeniedError):return '未获得 Google 授权；请重新连接并在浏览器确认所需权限'
        if isinstance(exc,oauth_errors.MismatchingStateError):return '授权回应与本次连接不匹配；请关闭旧授权页，只完成最新一次连接'
        if isinstance(exc,getattr(google_flow,'WSGITimeoutError',())):return '5 分钟内未收到浏览器授权回应；请检查浏览器是否完成授权或显示错误，再重新连接'
        if isinstance(exc,(oauth_errors.InvalidClientError,oauth_errors.InvalidClientIdError,oauth_errors.UnauthorizedClientError)):
            return 'Google 拒绝了客户端配置；请检查桌面应用客户端是否有效、已启用且允许此授权方式'
        if isinstance(exc,oauth_errors.InvalidGrantError):return 'Google 拒绝了本次授权凭据；请关闭旧授权页后重新连接'
        if isinstance(exc,requests.exceptions.ProxyError):return '无法通过代理连接 Google；请检查当前代理设置和连接后重试'
        if isinstance(exc,(requests.exceptions.ConnectionError,requests.exceptions.Timeout,TransportError)):
            return '无法完成与 Google 的网络通信；请检查 Google 服务连接、代理和系统时间后重试'
        exc=exc.__cause__ or exc.__context__
    return 'Google 授权或请求未完成，原因暂未识别；请查看浏览器错误代码后重新连接'


BROWSER_ERROR='无法启动系统默认浏览器；请先在 Windows 设置中选择可用的默认浏览器，再重新连接 Google'

class CheckedBrowser:
    def __init__(self,controller):self.controller=controller
    def open(self,url,new=0,autoraise=True):
        try:opened=self.controller.open(url,new=new,autoraise=autoraise)
        except (OSError,webbrowser.Error):raise SafeOAuthError(BROWSER_ERROR) from None
        if not opened:raise SafeOAuthError(BROWSER_ERROR)
        return True

def run_authorization(flow):
    options={}
    if os.name=='nt':
        try:controller=webbrowser.get()
        except (OSError,webbrowser.Error):raise SafeOAuthError(BROWSER_ERROR) from None
        # The SDK ignores open(False); make launch failure stop before waiting for a callback.
        webbrowser.register('mediadesk-google-auth',None,CheckedBrowser(controller))
        options['browser']='mediadesk-google-auth'
    return flow.run_local_server(host='localhost',port=0,open_browser=True,authorization_prompt_message='',timeout_seconds=300,**options)

def credentials(interactive=False):
    CONFIG.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=CONFIG/'token.json';cred=Credentials.from_authorized_user_file(str(token),[SCOPE]) if token.exists() else None
    if cred and not cred.valid and cred.refresh_token:
        try:cred.refresh(Request())
        except RefreshError:cred=None
        except TransportError:raise SafeOAuthError('网络不可用，无法刷新 YouTube 授权') from None
    if cred and cred.valid:return cred
    if not cred or not cred.valid:
        if not interactive:raise SafeOAuthError('需要连接 YouTube 账号')
        if not (CONFIG/'client.json').exists():raise SafeOAuthError('缺少 Google OAuth 客户端配置：请先导入 Google 桌面应用客户端 JSON，再连接账号')
        if os.name!='nt':os.environ.setdefault('BROWSER','google-chrome')
        try:read_client(CONFIG/'client.json')
        except ValueError as exc:raise SafeOAuthError(str(exc)) from None
        flow=InstalledAppFlow.from_client_secrets_file(str(CONFIG/'client.json'),[SCOPE])
        cred=run_authorization(flow)
    fd,tmp=tempfile.mkstemp(prefix='.token-',dir=CONFIG)
    try:
        if hasattr(cred,'to_json'):data=cred.to_json()
        else:data=json.dumps({'token':cred.token,'refresh_token':cred.refresh_token,'token_uri':cred.token_uri,'client_id':cred.client_id,'client_secret':cred.client_secret,'scopes':list(cred.scopes or [SCOPE]),'expiry':cred.expiry.isoformat()+'Z' if cred.expiry else None})
        with os.fdopen(fd,'w') as out:out.write(data)
        os.replace(tmp,token)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return cred

def main():
    kind=sys.argv[1];cred=credentials(kind=='auth')
    if kind=='auth':print('{}');return
    mapping={'channel':('channels',{'mine':'true'}),'subscriptions':('subscriptions',{'mine':'true'}),'likes':('videos',{'myRating':'like'}),'playlists':('playlists',{'mine':'true'}),'playlist-items':('playlistItems',{'playlistId':sys.argv[2] if len(sys.argv)>2 else ''})}
    streaming='--stream' in sys.argv[2:];endpoint,params=mapping[kind];params.update(part='snippet,contentDetails',maxResults=50);out=[]
    for _ in range(100):
        r=requests.get('https://www.googleapis.com/youtube/v3/'+endpoint,params=params,headers={'Authorization':'Bearer '+cred.token},timeout=30)
        if not r.ok:raise SafeOAuthError(f'YouTube API 返回 HTTP {r.status_code}')
        body=r.json();items=body.get('items',[])
        if streaming:print(json.dumps(items,ensure_ascii=False),flush=True)
        else:out.extend(items)
        page=body.get('nextPageToken')
        if not page:break
        params['pageToken']=page
    else:raise SafeOAuthError('列表过大，未能完整读取')
    if not streaming:print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:print(error_message(e),file=sys.stderr);sys.exit(1)
