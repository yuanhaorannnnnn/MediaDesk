import json,os,pathlib,subprocess,sys,tempfile,shutil
r=pathlib.Path(sys.argv[1]);source=pathlib.Path(sys.argv[2]);h=pathlib.Path(tempfile.mkdtemp(prefix='md-portable-app-tests-'));env=os.environ.copy()
for key in list(env):
 if key.upper().startswith(('PYTHON','GI_','GTK_','GDK_','XDG_','MSYS','MEDIADESK_','VLC_','OPENSSL_')):env.pop(key)
env.update(PATH=';'.join(map(str,[r/'bin',r/'tools/ffmpeg/bin',r/'tools/node',pathlib.Path(os.environ['SystemRoot'])/'System32'])),PYTHONPATH=str(source)+';'+str(source/'tests'),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',GI_TYPELIB_PATH=str(r/'lib/girepository-1.0'),XDG_DATA_DIRS=str(r/'share'),GTK_PATH=str(r/'lib/gtk-3.0'),GDK_BACKEND='win32',VLC_PLUGIN_PATH=str(r/'vlc/plugins'),MEDIADESK_VLC_DIR=str(r/'vlc'),MEDIADESK_YTDLP=str(r/'bin/yt-dlp.exe'),MEDIADESK_YOUTUBE_PYTHON=str(r/'bin/python.exe'),OPENSSL_MODULES=str(r/'lib/ossl-modules'),LOCALAPPDATA=str(h/'local'),APPDATA=str(h/'roaming'),MEDIADESK_GOOGLE_CONFIG=str(h/'no-account'))
results={}
for name in ['windows_smoke.py','windows_download_smoke.py']:
 shutil.copy2(source/name,h/name)
 try:
  cp=subprocess.run([str(r/'bin/python.exe'),'-B',str(h/name)],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=100)
  (h/(name+'.out.txt')).write_text(cp.stdout,encoding='utf-8');(h/(name+'.err.txt')).write_text(cp.stderr,encoding='utf-8');results[name]={'returncode':cp.returncode,'stdout_tail':cp.stdout[-600:],'stderr_tail':cp.stderr[-1200:]}
 except subprocess.TimeoutExpired as exc:results[name]={'timeout':True}
(h/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps({'evidence':str(h),'results':results},indent=2));sys.exit(any(v.get('returncode',1) for v in results.values()))
