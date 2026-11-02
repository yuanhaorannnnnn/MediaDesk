"""Read-only dependency preflight; no account, database, or media access."""
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

result={'platform':sys.platform,'bits':struct.calcsize('P')*8,'python':sys.version.split()[0],'missing':[],'versions':{}}
if sys.platform!='win32':result['missing'].append('Windows Python runtime')
for name in ('gi','cairo','requests','yt_dlp','google.auth','google_auth_oauthlib'):
    try:importlib.import_module(name)
    except (ImportError,OSError) as exc:result['missing'].append(name+': '+str(exc))
plugins=os.environ.get('VLC_PLUGIN_PATH','')
if not plugins or not Path(plugins).is_dir():result['missing'].append('VLC plugin directory')
if 'gi' in sys.modules:
    try:
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk
        result['versions']['gtk']='.'.join(str(v) for v in (Gtk.get_major_version(),Gtk.get_minor_version(),Gtk.get_micro_version()))
    except (ImportError,ValueError,OSError) as exc:result['missing'].append('GTK3: '+str(exc))
for name in ('ffmpeg','ffprobe','yt-dlp'):
    path=os.environ.get('MEDIADESK_YTDLP') if name=='yt-dlp' else shutil.which(name)
    if not path or not Path(path).is_file():result['missing'].append(name);continue
    try:
        args=[path,'--version'] if name=='yt-dlp' else [path,'-version']
        proc=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if proc.returncode:raise OSError('version check returned '+str(proc.returncode))
        result['versions'][name]=proc.stdout.splitlines()[0]
    except (OSError,subprocess.TimeoutExpired,IndexError) as exc:result['missing'].append(name+': '+str(exc))
try:
    from mediadesk import player
    import ctypes
    version=player.api('libvlc_get_version',ctypes.c_char_p,[])
    result['versions']['libvlc']=version().decode('utf-8','replace')
except (ImportError,OSError,RuntimeError) as exc:result['missing'].append('libVLC/GTK native integration: '+str(exc))
for name in ('requests','yt-dlp','google-auth','google-auth-oauthlib'):
    try:result['versions'][name+'_python']=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:pass
result['node_available']=bool(shutil.which('node'))
result['ready']=not result['missing']
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if result['ready'] else 1)
