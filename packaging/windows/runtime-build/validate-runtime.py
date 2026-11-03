"""Synthetic-only validation: clean environment, doctor, codecs and local download."""
import argparse,json,os,pathlib,subprocess,sys,tempfile,threading,http.server,functools,hashlib
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--app',type=pathlib.Path,required=True);p.add_argument('--doctor',type=pathlib.Path,required=True);p.add_argument('--ffmpeg-bin',type=pathlib.Path);p.add_argument('--fixtures-from',type=pathlib.Path);a=p.parse_args();r=a.root.resolve();evidence=pathlib.Path(tempfile.mkdtemp(prefix='md-runtime-evidence-'))
env=os.environ.copy()
for key in list(env):
 if key.upper().startswith(('PYTHON','GI_','GTK_','GDK_','XDG_','MSYS','MEDIADESK_','VLC_','OPENSSL_')):env.pop(key)
f=a.ffmpeg_bin or r/'tools/ffmpeg/bin'
env.update(PATH=';'.join(map(str,[r/'bin',f,r/'tools/node',pathlib.Path(os.environ['SystemRoot'])/'System32'])),PYTHONPATH=str(a.app),PYTHONDONTWRITEBYTECODE='1',GI_TYPELIB_PATH=str(r/'lib/girepository-1.0'),XDG_DATA_DIRS=str(r/'share'),GTK_PATH=str(r/'lib/gtk-3.0'),GDK_BACKEND='win32',VLC_PLUGIN_PATH=str(r/'vlc/plugins'),MEDIADESK_VLC_DIR=str(r/'vlc'),MEDIADESK_YTDLP=str(r/'bin/yt-dlp.exe'),OPENSSL_MODULES=str(r/'lib/ossl-modules'),LOCALAPPDATA=str(evidence/'local'),APPDATA=str(evidence/'roaming'))
results={}
def run(name,args,ok=True):
 cp=subprocess.run(list(map(str,args)),env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
 (evidence/(name+'.out.txt')).write_text(cp.stdout,encoding='utf-8');(evidence/(name+'.err.txt')).write_text(cp.stderr,encoding='utf-8')
 results[name]={'returncode':cp.returncode,'args':list(map(str,args))}
 if ok and cp.returncode:raise RuntimeError(name+': '+cp.stderr[-1800:])
 return cp
try:
 run('doctor',[r/'bin/python.exe','-B',a.doctor])
 for what in ('decoders','encoders','demuxers','protocols') :run(what,[f/'ffmpeg.exe','-hide_banner','-'+what])
 codecs={'h264':('libx264','mp4'),'hevc':('libx265','mp4'),'vp9':('libvpx-vp9','webm'),'av1':('libaom-av1','mkv')}
 for name,(encoder,ext) in codecs.items():
  target=(a.fixtures_from or evidence)/(name+'.'+ext)
  if not a.fixtures_from:run(name+'-encode',[f/'ffmpeg.exe','-v','error','-f','lavfi','-i','testsrc2=size=64x64:rate=5','-t','0.6','-c:v',encoder,'-threads','2','-y',target])
  run(name+'-decode',[f/'ffmpeg.exe','-v','error','-xerror','-err_detect','explode','-i',target,'-f','null','-'])
  run(name+'-probe',[f/'ffprobe.exe','-v','error','-show_entries','stream=codec_name,width,height','-of','json',target])
  run(name+'-cover',[f/'ffmpeg.exe','-v','error','-i',target,'-frames:v','1','-y',evidence/(name+'.jpg')])
  run(name+'-preview',[f/'ffmpeg.exe','-v','error','-ss','0.2','-i',target,'-frames:v','1','-vf','scale=160:-1','-y',evidence/(name+'-preview.jpg')])
 audio=evidence/'audio.m4a';merged=evidence/'merged.mp4'
 run('audio',[f/'ffmpeg.exe','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.6','-c:a','aac','-y',audio])
 run('merge',[f/'ffmpeg.exe','-v','error','-i',(a.fixtures_from or evidence)/'h264.mp4','-i',audio,'-c','copy','-y',merged])
 run('merge-decode',[f/'ffmpeg.exe','-v','error','-xerror','-err_detect','explode','-i',merged,'-f','null','-'])
 truncated=evidence/'truncated.mp4';data=merged.read_bytes();truncated.write_bytes(data[:len(data)//2])
 failed=run('truncated-decode',[f/'ffmpeg.exe','-v','error','-xerror','-err_detect','explode','-i',truncated,'-f','null','-'],ok=False)
 if not failed.returncode:raise RuntimeError('Truncated synthetic MP4 was not rejected')
 handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(evidence));server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  downloaded=evidence/'downloaded.mp4'
  run('download',[r/'bin/yt-dlp.exe','--ignore-config','--proxy','','--no-playlist','-o',downloaded,f'http://127.0.0.1:{server.server_port}/merged.mp4'])
  if downloaded.read_bytes()!=merged.read_bytes():raise RuntimeError('Downloaded bytes differ')
 finally:server.shutdown();server.server_close()
 results['ready']=True
except Exception as exc:results['ready']=False;results['error']=str(exc)
finally:
 (evidence/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps({'evidence':str(evidence),'ready':results['ready'],'checks':len(results)-1,'error':results.get('error')},indent=2))
sys.exit(not results['ready'])
