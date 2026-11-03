"""Clean-PATH GTK smoke and deliberately missing dynamic-library diagnosis."""
import argparse,json,os,pathlib,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);p.add_argument('--probe',action='store_true');a=p.parse_args();root=a.root.resolve()
if a.probe:
 import gi,cairo
 gi.require_version('Gtk','3.0');from gi.repository import Gtk,GdkPixbuf
 ok,_=Gtk.init_check([])
 if not ok:raise RuntimeError('GTK cannot initialize a Windows display')
 window=Gtk.Window();window.set_title('MediaDesk isolated runtime probe');window.show_all()
 while Gtk.events_pending():Gtk.main_iteration_do(False)
 assert window.get_window() is not None
 window.destroy()
 loader=GdkPixbuf.PixbufLoader.new_with_type('svg')
 loader.write(b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="blue"/></svg>');loader.close()
 assert loader.get_pixbuf().get_width()==16
 import ctypes as C
 kernel=C.WinDLL('kernel32');kernel.GetCurrentProcess.restype=C.c_void_p
 kernel.K32EnumProcessModules.argtypes=[C.c_void_p,C.POINTER(C.c_void_p),C.c_ulong,C.POINTER(C.c_ulong)]
 kernel.K32GetModuleFileNameExW.argtypes=[C.c_void_p,C.c_void_p,C.c_wchar_p,C.c_ulong]
 modules=(C.c_void_p*2048)();needed=C.c_ulong();process=kernel.GetCurrentProcess()
 assert kernel.K32EnumProcessModules(process,modules,C.sizeof(modules),C.byref(needed))
 related=[]
 for module in modules[:needed.value//C.sizeof(C.c_void_p)]:
  buffer=C.create_unicode_buffer(32768);kernel.K32GetModuleFileNameExW(process,module,buffer,len(buffer));path=pathlib.Path(buffer.value)
  if path.name.lower().startswith(('libgtk-3','librsvg-2','libpixbufloader-svg')):
   assert str(path).lower().startswith(str(root).lower()+'\\'),str(path)
   related.append(str(path))
 print(json.dumps({'svg_loaded':True,'native_modules':related}))
 subprocess.run([sys.executable,'-I','-B','-c','import json,sys; print(json.dumps({"child_python":sys.executable}))'],check=True)
 print(json.dumps({'gtk':f'{Gtk.get_major_version()}.{Gtk.get_minor_version()}','python':sys.executable,'prefix':sys.prefix,'pixbuf_formats':len(GdkPixbuf.Pixbuf.get_formats())}));raise SystemExit()
env=os.environ.copy()
for key in list(env):
 if key.upper().startswith(('PYTHON','GI_','GTK_','GDK_','XDG_','MSYS')):env.pop(key)
env.update(PATH=str(root/'bin')+';'+str(pathlib.Path(os.environ['SystemRoot'])/'System32'),GI_TYPELIB_PATH=str(root/'lib/girepository-1.0'),XDG_DATA_DIRS=str(root/'share'),GTK_PATH=str(root/'lib/gtk-3.0'),GDK_BACKEND='win32')
cmd=[str(root/'bin/python.exe'),'-I','-B',str(pathlib.Path(__file__).resolve()),str(root),'--probe']
dll=root/'bin/libgtk-3-0.dll';hidden=dll.with_suffix('.probe-hidden')
if hidden.exists():raise SystemExit('Stale missing-library probe artifact; inspect before retry')
dll.rename(hidden)
try:
 missing=subprocess.run(cmd,env=env,capture_output=True,text=True)
 if missing.returncode==0:raise RuntimeError('Missing GTK DLL unexpectedly succeeded: environment contamination')
 print(json.dumps({'missing_gtk_returncode':missing.returncode,'diagnostic':missing.stderr[-4000:]}))
finally:hidden.rename(dll)
complete=subprocess.run(cmd,env=env,capture_output=True,text=True)
print(complete.stdout);print(complete.stderr,file=sys.stderr)
raise SystemExit(complete.returncode)
