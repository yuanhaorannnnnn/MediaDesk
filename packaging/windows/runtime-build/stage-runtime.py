"""Stage a reviewable portable runtime, retaining dynamically loaded DLLs.
Build-time only: run with the validated MSYS2 UCRT64 interpreter.
"""
import argparse, collections, hashlib, json, pathlib, shutil
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--target',type=pathlib.Path,required=True);a=p.parse_args()
if a.target.exists(): raise SystemExit('Target exists; use a fresh isolated target')
skip_dirs={'__pycache__','test','tests','idlelib','tkinter','ensurepip'}
# Headers/static link archives/GIR XML are build inputs. Keep all runtime DLLs,
# typelibs, loaders, schemas, themes, translations and license files.
share_skip={'gir-1.0','gtk-doc','doc','man','info','aclocal','cmake','pkgconfig','vala'}
files=[];sizes=collections.Counter()
for src in a.source.rglob('*'):
 if not src.is_file(): continue
 rel=src.relative_to(a.source);parts=rel.parts
 if parts[0]=='bin': keep=src.suffix.lower()=='.dll' or src.name in ('python.exe','pythonw.exe','gdk-pixbuf-query-loaders.exe','glib-compile-schemas.exe')
 elif parts[0]=='lib':
  keep=src.suffix.lower()=='.dll' or (parts[1].startswith('python') and not any(x in skip_dirs for x in parts) and src.suffix.lower() not in ('.a','.pyc')) or parts[1] in ('girepository-1.0','gdk-pixbuf-2.0','gtk-3.0')
 elif parts[0]=='share': keep=len(parts)>1 and parts[1] not in share_skip
 elif parts[0]=='etc': keep=True
 else: keep=False
 if not keep: continue
 dst=a.target/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 size=dst.stat().st_size;sizes[parts[0]]+=size
 files.append({'path':str(rel),'bytes':size,'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()})
(a.target/'runtime-files.json').write_text(json.dumps({'source':str(a.source),'bytes':sum(sizes.values()),'groups':sizes,'files':files},indent=2),encoding='utf-8')
print(json.dumps({'target':str(a.target),'files':len(files),'bytes':sum(sizes.values()),'groups':sizes},indent=2))
