"""Google read-only authorization helper, isolated from the GUI runtime."""
import json
import os
import sys
import tempfile
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError, TransportError
import requests

CONFIG=Path(os.environ.get('MEDIADESK_GOOGLE_CONFIG', str(Path.home()/'.config/youtube-readonly')))
SCOPE='https://www.googleapis.com/auth/youtube.readonly'

def credentials(interactive=False):
    CONFIG.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=CONFIG/'token.json';cred=Credentials.from_authorized_user_file(str(token),[SCOPE]) if token.exists() else None
    if cred and not cred.valid and cred.refresh_token:
        try:cred.refresh(Request())
        except RefreshError:cred=None
        except TransportError:raise ValueError('网络不可用，无法刷新 YouTube 授权') from None
    if cred and cred.valid:return cred
    if not cred or not cred.valid:
        if not interactive:raise ValueError('需要连接 YouTube 账号')
        if not (CONFIG/'client.json').exists():raise ValueError('缺少 Google OAuth 客户端配置')
        os.environ.setdefault('BROWSER','google-chrome')
        flow=InstalledAppFlow.from_client_secrets_file(str(CONFIG/'client.json'),[SCOPE])
        cred=flow.run_local_server(host='localhost',port=0,open_browser=True,authorization_prompt_message='',timeout_seconds=300)
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
        if not r.ok:raise ValueError(f'YouTube API 返回 HTTP {r.status_code}')
        body=r.json();items=body.get('items',[])
        if streaming:print(json.dumps(items,ensure_ascii=False),flush=True)
        else:out.extend(items)
        page=body.get('nextPageToken')
        if not page:break
        params['pageToken']=page
    else:raise ValueError('列表过大，未能完整读取')
    if not streaming:print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e) if isinstance(e,ValueError) else '授权或请求失败，请检查网络及账号',file=sys.stderr);sys.exit(1)
