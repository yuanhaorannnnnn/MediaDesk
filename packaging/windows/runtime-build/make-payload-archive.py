"""Build one verified ZIP plus immutable receipt; no source files are changed."""
import argparse,hashlib,json,pathlib,shutil,stat,time,zipfile
p=argparse.ArgumentParser();p.add_argument('--payload',type=pathlib.Path,required=True);p.add_argument('--target',type=pathlib.Path,required=True);a=p.parse_args()
if a.target.exists():raise SystemExit('Target exists; use a fresh archive output directory')
a.target.mkdir(parents=True);receipt=a.payload/'runtime-files.json';data=json.loads(receipt.read_text(encoding='utf-8'));archive=a.target/'runtime.zip.partial';start=time.monotonic()
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
 for i,entry in enumerate(data['files']):
  name=entry['path'].replace('\\','/');relative=pathlib.PurePosixPath(name)
  if relative.is_absolute() or '..' in relative.parts or ':' in name:raise RuntimeError('Unsafe build receipt')
  info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16;info._compresslevel=1
  digest=hashlib.sha256();total=0
  with (a.payload/pathlib.Path(*relative.parts)).open('rb') as source,z.open(info,'w') as target:
   while block:=source.read(1024*1024):target.write(block);digest.update(block);total+=len(block)
  if digest.hexdigest().lower()!=entry['sha256'].lower() or total!=entry['bytes']:raise RuntimeError('Source changed: '+name)
  if (i+1)%2000==0:print(f'Archived {i+1}/{len(data["files"])}',flush=True)
archive.rename(a.target/'runtime.zip');archive=a.target/'runtime.zip';shutil.copy2(receipt,a.target/'runtime-files.json')
hashvalue=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
result={'schema':1,'archive':'runtime.zip','sha256':hashvalue,'manifest_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,'uncompressed_bytes':sum(x['bytes'] for x in data['files']),'files':len(data['files'])}
(a.target/'runtime-archive.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(result,seconds=time.monotonic()-start),indent=2))
