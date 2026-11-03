"""Report unresolved regular and delayed PE imports; dynamic loads need smoke tests."""
import argparse,json,os,pathlib,struct
p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);a=p.parse_args()
def imports(path):
 b=path.read_bytes()
 if b[:2]!=b'MZ':return []
 pe=struct.unpack_from('<I',b,0x3c)[0];n=struct.unpack_from('<H',b,pe+6)[0];optlen=struct.unpack_from('<H',b,pe+20)[0];opt=pe+24
 magic=struct.unpack_from('<H',b,opt)[0];dirs=opt+(112 if magic==0x20b else 96);sections=[]
 for i in range(n):
  off=opt+optlen+40*i;vs,va,rs,raw=struct.unpack_from('<IIII',b,off+8);sections.append((va,max(vs,rs),raw))
 def offset(rva):
  for va,size,raw in sections:
   if va<=rva<va+size:return raw+rva-va
  return rva
 def string(rva):
  start=offset(rva);return b[start:b.index(b'\0',start)].decode('ascii')
 names=[]
 for index,width,nameoff in [(1,20,12),(13,32,4)]:
  rva,size=struct.unpack_from('<II',b,dirs+8*index)
  if not rva:continue
  pos=offset(rva)
  while any(b[pos:pos+width]):
   name=struct.unpack_from('<I',b,pos+nameoff)[0]
   if name:names.append(string(name))
   pos+=width
 return names
all_files=[p for p in a.root.rglob('*') if p.is_file()]
known={p.name.lower() for p in all_files};system=pathlib.Path(os.environ['SystemRoot'])/'System32';missing=[];count=0
for path in all_files:
 if path.suffix.lower() not in ('.dll','.pyd','.exe'):continue
 count+=1
 for name in imports(path):
  if name.lower() not in known and not (system/name).exists() and not name.lower().startswith(('api-ms-win-','ext-ms-win-')):missing.append({'file':str(path.relative_to(a.root)),'import':name})
print(json.dumps({'pe_files':count,'unresolved':missing,'scope':'regular and delayed PE imports; runtime LoadLibrary/typelib/plugin loads require separate tests'},indent=2))
raise SystemExit(bool(missing))
