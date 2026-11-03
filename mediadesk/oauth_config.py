"""Validate and import user-supplied Google Desktop OAuth configuration."""
import json
import os
from pathlib import Path
import tempfile
if __package__:
    from .paths import google_config_dir
else:
    from paths import google_config_dir


def read_client(path):
    try:
        raw=Path(path).read_bytes()
        if len(raw)>65536:raise ValueError('OAuth 配置文件过大，请选择 Google 下载的桌面客户端 JSON')
        data=json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError('无法读取 OAuth 配置，请选择 Google 下载的桌面客户端 JSON') from None
    installed=data.get('installed') if isinstance(data,dict) else None
    if not isinstance(installed,dict):raise ValueError('需要 Google 桌面应用客户端配置（installed），不支持 Web 客户端或服务账号')
    if any(not isinstance(installed.get(key),str) or not installed[key].strip() for key in ('client_id','client_secret')):
        raise ValueError('OAuth 配置缺少 client_id 或 client_secret，请重新下载桌面客户端 JSON')
    if installed.get('auth_uri') not in ('https://accounts.google.com/o/oauth2/auth','https://accounts.google.com/o/oauth2/v2/auth') or installed.get('token_uri') not in ('https://oauth2.googleapis.com/token','https://accounts.google.com/o/oauth2/token'):
        raise ValueError('OAuth 配置的授权地址不是受支持的 Google 地址，请重新下载桌面客户端 JSON')
    return data


def import_client(source, config=None):
    """Return destination Path. Never overwrite different client settings or tokens."""
    data=read_client(source);root=Path(config) if config is not None else google_config_dir();target=root/'client.json'
    if target.exists():
        if read_client(target)==data:return target
        raise ValueError('已有不同的 OAuth 客户端配置；为保留现有授权，未替换。请使用独立的 Google 配置目录')
    if (root/'token.json').exists():raise ValueError('已有授权令牌但缺少客户端配置；请恢复原客户端配置或使用独立的 Google 配置目录')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temp=tempfile.mkstemp(prefix='.client-',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(data,out,ensure_ascii=False)
        # Exclusive creation keeps concurrent imports from replacing each other.
        os.link(temp,target)
    except FileExistsError:
        raise ValueError('OAuth 客户端配置已被其他操作创建，请重新检查') from None
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return target
