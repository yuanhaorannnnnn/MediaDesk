"""GTK native libVLC player on X11 and Windows."""
import ctypes as C
from pathlib import Path
import os

import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib
if os.name!='nt':
    gi.require_version('GdkX11','3.0')
    from gi.repository import GdkX11

_dll_handles=[]
if os.name=='nt':
    candidates=[os.environ.get('MEDIADESK_VLC_DIR')]
    candidates += [str(Path(os.environ.get(key,''))/'VideoLAN/VLC') for key in ('ProgramW6432','ProgramFiles','ProgramFiles(x86)') if os.environ.get(key)]
    directory=next((Path(p) for p in candidates if p and (Path(p)/'libvlc.dll').is_file()),None)
    if directory is None:raise RuntimeError('未找到 VLC；请安装同架构 VLC 或设置 MEDIADESK_VLC_DIR')
    _dll_handles.append(os.add_dll_directory(str(directory)))
    os.environ.setdefault('VLC_PLUGIN_PATH',str(directory/'plugins'))
    lib=C.CDLL(str(directory/'libvlc.dll'))
else:lib=C.CDLL('libvlc.so.5')
PTR=C.c_void_p

def api(name, result, args):
    f=getattr(lib,name);f.restype=result;f.argtypes=args;return f

_new=api('libvlc_new',PTR,[C.c_int,C.POINTER(C.c_char_p)])
_release=api('libvlc_release',None,[PTR])
_new_media=api('libvlc_media_new_path',PTR,[PTR,C.c_char_p])
_new_location=api('libvlc_media_new_location',PTR,[PTR,C.c_char_p])
_media_option=api('libvlc_media_add_option',None,[PTR,C.c_char_p])
_media_slave=api('libvlc_media_slaves_add',C.c_int,[PTR,C.c_int,C.c_uint,C.c_char_p])
_release_media=api('libvlc_media_release',None,[PTR])
_new_player=api('libvlc_media_player_new',PTR,[PTR])
_release_player=api('libvlc_media_player_release',None,[PTR])
_set_media=api('libvlc_media_player_set_media',None,[PTR,PTR])
if os.name=='nt':
    _set_hwnd=api('libvlc_media_player_set_hwnd',None,[PTR,PTR])
    _gdk=C.CDLL('libgdk-3-0.dll')
    _win_handle=_gdk.gdk_win32_window_get_handle;_win_handle.restype=PTR;_win_handle.argtypes=[PTR]
    _capsule=C.pythonapi.PyCapsule_GetPointer;_capsule.restype=PTR;_capsule.argtypes=[C.py_object,C.c_char_p]
else:_set_xwindow=api('libvlc_media_player_set_xwindow',None,[PTR,C.c_uint32])
_play=api('libvlc_media_player_play',C.c_int,[PTR]);_pause=api('libvlc_media_player_pause',None,[PTR]);_stop=api('libvlc_media_player_stop',None,[PTR]);_time=api('libvlc_media_player_get_time',C.c_int64,[PTR]);_length=api('libvlc_media_player_get_length',C.c_int64,[PTR]);_seek=api('libvlc_media_player_set_time',None,[PTR,C.c_int64]);_state=api('libvlc_media_player_get_state',C.c_int,[PTR])
_seekable=api('libvlc_media_player_is_seekable',C.c_int,[PTR])
_volume=api('libvlc_audio_set_volume',C.c_int,[PTR,C.c_int]);_mute=api('libvlc_audio_set_mute',None,[PTR,C.c_int])


class Player(Gtk.Box):
    def __init__(self,volume=100,on_volume=None,on_state=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        # VLC 3.x's avcodec/VDPAU path can stall AV1; native dav1d handles it.
        options=(C.c_char_p*1)(b'--codec=dav1d,any')
        self.instance=_new(0,None) if os.name=='nt' else _new(1,options)
        if not self.instance: raise RuntimeError('无法初始化 libVLC')
        self.player=_new_player(self.instance)
        if not self.player: _release(self.instance);raise RuntimeError('无法创建播放器')
        self.closed=False
        self.area=Gtk.DrawingArea();self.area.set_size_request(360,270);self.area.set_hexpand(True);self.area.set_vexpand(True);self.area.connect('realize',self._realize);self.area.connect('size-allocate',self._schedule_area_resize)
        # VLC owns an opaque native surface; CSD's RGBA visual leaks through compositing.
        if os.name!='nt':self.area.set_visual(self.area.get_screen().get_system_visual())
        self.area_height=270;self.area_resize_source=0;self.window_resize_handler=0;self.resize_window=None
        self.pack_start(self.area,True,True,0)
        controls=Gtk.Box(spacing=6);self.controls=controls;self.toggle=Gtk.Button();self.toggle.connect('clicked',lambda *_:_pause(self.player) if _state(self.player)==3 else _play(self.player));controls.pack_start(self.toggle,False,False,0)
        self._set_play_icon(False)
        self.scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,1000,1);self.scale.get_style_context().add_class('player-seek');self.scale.set_draw_value(False);self.scale.set_hexpand(True);self.scrubbing=False;self.scale.connect('button-press-event',self._on_press);self.scale.connect('button-release-event',self._on_seek);self.scale.connect('change-value',self._on_change);controls.pack_start(self.scale,True,True,0)
        self.label=Gtk.Label(label='00:00 / 00:00');controls.pack_start(self.label,False,False,0)
        self.on_volume=on_volume;self.on_state=on_state;self.last_state=None;self.volume_button=Gtk.VolumeButton();self.volume_button.set_tooltip_text('音量（设为零可静音）');self.volume_button.get_accessible().set_name('音量');self.volume_button.set_value(max(0,min(100,int(volume)))/100);self.volume_button.connect('value-changed',self._change_volume);controls.pack_start(self.volume_button,False,False,0)
        self.volume_pending=True
        control_window=Gtk.EventBox();control_window.add(controls);self.pack_start(control_window,False,False,0)
        self.source=GLib.timeout_add(500,self._tick)

    def _realize(self, area):
        window=area.get_window()
        if os.name=='nt':
            window.ensure_native()
            handle=_win_handle(_capsule(window.__gpointer__,None))
            if not handle:raise RuntimeError('无法获得 Windows 窗口句柄')
            _set_hwnd(self.player,handle)
        else:
            if not isinstance(window,GdkX11.X11Window):raise RuntimeError('当前会话不是 X11；请通过启动器使用 XWayland')
            _set_xwindow(self.player,window.get_xid())
        top=area.get_toplevel()
        if self.window_resize_handler and self.resize_window:self.resize_window.disconnect(self.window_resize_handler);self.window_resize_handler=0
        if isinstance(top,Gtk.Window):self.resize_window=top;self.window_resize_handler=top.connect('size-allocate',self._schedule_area_resize)

    def _schedule_area_resize(self,*_):
        if not self.closed and not self.area_resize_source:self.area_resize_source=GLib.idle_add(self._resize_area)

    def _resize_area(self):
        self.area_resize_source=0
        if self.closed:return False
        top=self.get_toplevel();window_height=top.get_allocated_height() if isinstance(top,Gtk.Window) else 0
        cap=max(270,round(window_height*.65));height=max(270,min(round(self.area.get_allocated_width()*9/16),cap))
        if height!=self.area_height:self.area_height=height;self.area.set_size_request(360,height)
        return False

    def open(self,path):
        p=Path(path)
        if not p.is_file(): raise ValueError('本地文件不存在')
        m=_new_media(self.instance,str(p).encode())
        if not m: raise RuntimeError('无法打开文件')
        _set_media(self.player,m);_release_media(m)
        if _play(self.player)!=0: raise RuntimeError('无法开始播放')
        self.volume_pending=True

    def open_stream(self,url,user_agent='',audio_url='',referer=''):
        m=_new_location(self.instance,url.encode())
        if not m:raise RuntimeError('无法打开在线播放地址')
        if user_agent:_media_option(m,(':http-user-agent='+user_agent).encode())
        if referer:_media_option(m,(':http-referrer='+referer).encode())
        if audio_url and _media_slave(m,1,4,audio_url.encode())!=0:
            _release_media(m);raise RuntimeError('无法加载在线播放音频')
        _set_media(self.player,m);_release_media(m)
        if _play(self.player)!=0:raise RuntimeError('无法开始在线播放')
        self.last_state=None;self.volume_pending=True

    def _on_press(self,*_):
        self.scrubbing=True;return False

    def _change_volume(self,button,value):
        value=round(value*100);self.volume_pending=True;self._apply_volume()
        if self.on_volume:self.on_volume(value)

    def _apply_volume(self):
        value=round(self.volume_button.get_value()*100)
        if _volume(self.player,value)==0:
            _mute(self.player,1 if value==0 else 0);self.volume_pending=False

    def _on_change(self,_,scroll,value):
        length=_length(self.player)
        if not self.scrubbing and length>0:_seek(self.player,int(length*value/1000))
        return False

    def _on_seek(self,*_):
        length=_length(self.player)
        if length>0:_seek(self.player,int(length*self.scale.get_value()/1000))
        self.scrubbing=False;return False

    @staticmethod
    def stamp(ms):
        sec=max(0,ms)//1000;return f'{sec//60:02d}:{sec%60:02d}'

    def _set_play_icon(self,playing):
        name='media-playback-pause-symbolic' if playing else 'media-playback-start-symbolic'
        if getattr(self,'icon_name',None)!=name:
            self.toggle.set_image(Gtk.Image.new_from_icon_name(name,Gtk.IconSize.BUTTON));self.icon_name=name
            title='暂停' if playing else '播放';self.toggle.set_tooltip_text(title);self.toggle.get_accessible().set_name(title)

    def _tick(self):
        if self.closed:return False
        t,l=_time(self.player),_length(self.player)
        self.scale.set_sensitive(bool(_seekable(self.player)))
        state=_state(self.player)
        if self.volume_pending and state==3:self._apply_volume()
        self._set_play_icon(state==3)
        reported=2 if state==3 and t<=0 else state
        if self.on_state and reported!=self.last_state:self.last_state=reported;self.on_state(reported)
        self.label.set_text(f'{self.stamp(t)} / {self.stamp(l)}')
        if l>0 and not self.scrubbing:self.scale.set_value(max(0,t)*1000/l)
        return True

    def close(self):
        if self.closed:return
        self.closed=True;GLib.source_remove(self.source)
        if self.area_resize_source:GLib.source_remove(self.area_resize_source);self.area_resize_source=0
        if self.window_resize_handler and self.resize_window:self.resize_window.disconnect(self.window_resize_handler);self.window_resize_handler=0;self.resize_window=None
        _stop(self.player);_release_player(self.player);_release(self.instance)
