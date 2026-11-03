"""Build-only assembly from verified inputs; never download or mutate a source tree."""
import argparse,collections,hashlib,json,pathlib,shutil,subprocess,sys
p=argparse.ArgumentParser()
for name in ('ucrt','python-overlay','vlc','node','ffmpeg','target'):p.add_argument('--'+name,type=pathlib.Path,required=True)
p.add_argument('--qr-wheels',type=pathlib.Path,required=True)
a=p.parse_args()
if not (a.python_overlay/'bin/yt-dlp.exe').is_file():raise SystemExit('Missing signed yt-dlp launcher in package extraction')
subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('stage-runtime.py')),'--source',str(a.ucrt),'--target',str(a.target)],check=True)
def copytree(source,target):
 shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','tests','test'))
shutil.copy2(a.python_overlay/'bin/yt-dlp.exe',a.target/'bin/yt-dlp.exe')
copytree(a.python_overlay/'lib/python3.14/site-packages',a.target/'lib/python3.14/site-packages')
copytree(a.python_overlay/'share/licenses',a.target/'share/licenses')
subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('stage-qr-dependencies.py')),'--wheel-dir',str(a.qr_wheels),'--target',str(a.target)],check=True)
for child in a.vlc.iterdir():
 if child.name in ('sdk','msi','.mediadesk-complete'):continue
 target=a.target/'vlc'/child.name
 if child.is_dir():copytree(child,target)
 else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(child,target)
node=a.target/'tools/node';node.mkdir(parents=True)
for name in ('node.exe','LICENSE'):shutil.copy2(a.node/name,node/name)
ff=a.target/'tools/ffmpeg';(ff/'bin').mkdir(parents=True)
for child in (a.ffmpeg/'bin').iterdir():
 if child.suffix.lower()=='.dll' or child.name in ('ffmpeg.exe','ffprobe.exe'):shutil.copy2(child,ff/'bin'/child.name)
for child in a.ffmpeg.iterdir():
 if child.is_file():shutil.copy2(child,ff/child.name)
files=[];groups=collections.Counter()
for child in a.target.rglob('*'):
 if child.is_file() and child.name!='runtime-files.json':
  rel=child.relative_to(a.target);size=child.stat().st_size
  group='/'.join(rel.parts[:2]) if rel.parts[0]=='tools' else rel.parts[0]
  groups[group]+=size;files.append({'path':str(rel),'bytes':size,'sha256':hashlib.sha256(child.read_bytes()).hexdigest()})
manifest={'schema':1,'groups':groups,'bytes':sum(groups.values()),'files':files,'inputs':{key:str(value) for key,value in vars(a).items() if key!='target'}}
(a.target/'runtime-files.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'target':str(a.target),'bytes':manifest['bytes'],'groups':groups,'files':len(files)},indent=2))
