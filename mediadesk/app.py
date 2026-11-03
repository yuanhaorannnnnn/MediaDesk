"""MediaDesk desktop application for Ubuntu."""
import os
import json
import math
import subprocess
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import gi
gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio
from .store import Store, youtube_id, identify_url
from .paths import google_config_dir
from . import downloader, sources, bilibili
from .player import Player
from .preview import HoverPreview

CSS=b'''*{font-family:Sans} window,dialog,headerbar{background:#11151a;color:#f2f5f4} list,list row,scrolledwindow,viewport{background:#11151a;color:#f2f5f4} label{color:#f2f5f4} button{background:#263137;color:#f2f5f4;border:1px solid #46575c;border-radius:6px;padding:7px} button:hover{background:#35434a} button:focus{outline:2px solid #7dd6d0;outline-offset:-2px} button.suggested-action{background:#7dd6d0;color:#102426;border:0} button.suggested-action label{color:#102426} entry,combobox,treeview{background:#1d242b;color:#f2f5f4} .sidebar{background:#171c22;border-right:1px solid #303b42} .sidebar button{background:transparent;border-color:transparent;padding:9px} .sidebar button:hover{background:#28323b} .sidebar button.selected{background:#2b3d41;border-left:3px solid #7dd6d0} .sidebar .nav-title{font-size:12px;color:#9eafb2;font-weight:bold} .muted{color:#b7c5c8} .title{font-size:25px;font-weight:bold} .section{font-size:18px;font-weight:bold} .card{background:#1d242b;padding:20px;border-radius:8px} button.media-card{background:#1d242b;border-color:#303b42;padding:0} button.media-card:hover{background:#28323b;border-color:#7dd6d0} .status{color:#b7c5c8;font-size:12px} label.media-title{font-size:15px;font-weight:600} .media-art{background:#263137;color:#9eafb2;border-radius:4px} scale.player-seek trough highlight{background-image:none;background-color:#7dd6d0;border-color:#7dd6d0;box-shadow:none} progressbar.job-progress progress{background-image:none;background-color:#7dd6d0;border-color:#7dd6d0;box-shadow:none} label.job-failed{color:#ffa6a0}'''

LIGHT_CSS=b'''*{font-family:Sans} window,dialog,headerbar{background:#f6f8f7;color:#192c30} list,list row,scrolledwindow,viewport{background:#f6f8f7;color:#192c30} label{color:#192c30} button{background:#edf2f1;color:#192c30;border:1px solid #c4d2d0;border-radius:6px;padding:7px} button:hover{background:#dce9e7} button:focus{outline:2px solid #187d78;outline-offset:-2px} button.suggested-action{background:#247f78;color:#ffffff;border:0} button.suggested-action label{color:#ffffff} entry,combobox,treeview{background:#ffffff;color:#192c30} .sidebar{background:#eaf0ef;border-right:1px solid #cedbd9} .sidebar button{background:transparent;border-color:transparent;padding:9px} .sidebar button:hover{background:#d8e6e4} .sidebar button.selected{background:#cce4e1;border-left:3px solid #247f78} .sidebar .nav-title{font-size:12px;color:#536e6b;font-weight:bold} .muted{color:#536b6b} .title{font-size:25px;font-weight:bold} .section{font-size:18px;font-weight:bold} .card{background:#ffffff;padding:20px;border-radius:8px} button.media-card{background:#ffffff;border-color:#d3dfdd;padding:0} button.media-card:hover{background:#edf7f5;border-color:#247f78} .status{color:#536b6b;font-size:12px} label.media-title{font-size:15px;font-weight:600} .media-art{background:#e6eeec;color:#536e6b;border-radius:4px} scale.player-seek trough highlight{background-image:none;background-color:#247f78;border-color:#247f78;box-shadow:none} progressbar.job-progress progress{background-image:none;background-color:#247f78;border-color:#247f78;box-shadow:none} label.job-failed{color:#9c3733}'''


def selection_css(accent,foreground):
    return f'''checkbutton check:checked,radiobutton radio:checked{{background-image:none;background-color:{accent};border-color:{accent};color:{foreground}}}'''.encode()


CSS+=selection_css('#7dd6d0','#102426')
LIGHT_CSS+=selection_css('#247f78','#ffffff')


def recolor(css,colors):
    for old,new in colors.items():css=css.replace(old.encode(),new.encode())
    return css


# Art movements inform the component color relationships; artwork remains unchanged.
NABIS_CSS=recolor(CSS,{
    '#11151a':'#1d1c23','#f2f5f4':'#f8f0e8','#263137':'#493949','#46575c':'#725d6e',
    '#35434a':'#5b4958','#7dd6d0':'#eac094','#102426':'#342117','#1d242b':'#2b2932',
    '#171c22':'#302638','#303b42':'#665267','#28323b':'#52435a','#2b3d41':'#5b465d',
    '#9eafb2':'#dfc5bd','#b7c5c8':'#d9c8c9'
})+b''' .sidebar .nav-title{background:#51405c;color:#f2ddc9;padding:4px 7px} .sidebar button.selected{border-left-width:4px} .card,button.media-card{border-radius:2px} button.media-card{border:2px solid #665267;border-bottom:4px solid #a77972} .media-art{border-radius:0}'''
NEO_IMPRESSION_CSS=recolor(LIGHT_CSS,{
    '#f6f8f7':'#f8f3e8','#192c30':'#243a44','#edf2f1':'#e5eee8','#c4d2d0':'#b6c9c5',
    '#dce9e7':'#d5e5da','#187d78':'#315d77','#247f78':'#315d77','#ffffff':'#fffef7',
    '#eaf0ef':'#e1ece4','#cedbd9':'#bdcfc6','#d8e6e4':'#d5e5da','#cce4e1':'#d7e8dc',
    '#536e6b':'#536c73','#536b6b':'#526b72','#d3dfdd':'#cbd7cc','#edf7f5':'#eaf1e6',
    '#e6eeec':'#e0ece5'
})+b''' .sidebar button.selected{background-image:linear-gradient(to right,#d4e6d9 0%,#d4e6d9 38%,#e8ead8 38%,#e8ead8 70%,#efdfd6 70%,#efdfd6 100%)} .sidebar .nav-title{border-bottom:2px solid #a2bcb1;padding-bottom:4px} button.media-card{border-bottom:3px solid #a9bfb6} .card{border:1px solid #cbd7cc}'''

def interaction_css(normal,primary_hover,primary_active,sidebar,card):
    return f'''button{{transition:background-color 120ms ease,border-color 120ms ease,box-shadow 120ms ease}}
    button:active{{background-image:none;background-color:{normal};box-shadow:inset 0 2px 4px rgba(0,0,0,0.20)}}
    button.suggested-action:hover{{background-image:none;background-color:{primary_hover}}}
    button.suggested-action:active{{background-image:none;background-color:{primary_active};box-shadow:inset 0 2px 4px rgba(0,0,0,0.25)}}
    .sidebar button:active,.sidebar button.selected:active{{background-image:none;background-color:{sidebar};box-shadow:inset 0 2px 4px rgba(0,0,0,0.18)}}
    button.media-card:active{{background-image:none;background-color:{card};box-shadow:inset 0 2px 4px rgba(0,0,0,0.20)}}'''.encode()

CSS+=interaction_css('#1a2429','#a9ece6','#54afa9','#3d5558','#35434a')
LIGHT_CSS+=interaction_css('#cadbd8','#2f948b','#1b625e','#b6d6d1','#d4eae6')
NABIS_CSS+=interaction_css('#382938','#f4d4b2','#c3936c','#755b73','#69556c')
NEO_IMPRESSION_CSS+=interaction_css('#c4d9d0','#42738b','#254b61','#bfd8c8','#d5e8dc')
# Let the artwork and typography define the media shelf; reserve outlines for interaction.
def shelf_css(surface,hover,outline,pressed):
    return f'''button.media-card{{background-image:none;background-color:transparent;border:1px solid transparent;border-radius:5px}}
    button.media-card:hover{{background-color:{hover};border-color:transparent}}
    button.media-card:active{{background-color:{pressed}}}
    button.media-card:focus{{outline:2px solid {outline};outline-offset:-2px}}
    .media-art{{background-color:{surface}}}'''.encode()

CSS=recolor(CSS,{'#11151a':'#171a1b','#171c22':'#1d2021','#1d242b':'#252a2a','#263137':'#303736','#303b42':'#39413e'})
LIGHT_CSS=recolor(LIGHT_CSS,{'#f6f8f7':'#f4f3ee','#ffffff':'#fffef9'})
CSS+=shelf_css('#292e30','#232a2a','#7dd6d0','#35434a')
LIGHT_CSS+=shelf_css('#e7ebe7','#e9efeb','#187d78','#d4eae6')
NABIS_CSS+=shelf_css('#4a3945','#473646','#eac094','#69556c')+b''' .sidebar .nav-title{background:transparent;color:#d9c8c9;padding:4px 0} button.media-card{border-bottom-width:1px} '''
NEO_IMPRESSION_CSS+=shelf_css('#e1e9df','#e7eee5','#315d77','#d5e8dc')+b''' .sidebar button.selected{background-image:none;background-color:#d7e8dc} .sidebar .nav-title{border-bottom:0;padding-bottom:0} button.media-card{border-bottom-width:1px} '''
# The library uses the typography and color blocks of a record-sleeve index.
def editorial_css(rail,rail_ink,rail_muted,selected,selected_ink,hover,rule,banner,banner_ink):
    return f''' *{{font-family:'Noto Sans CJK SC',Sans}}
    button{{border-radius:4px}}
    entry{{border-radius:4px}}
    .card{{border:1px solid rgba(128,128,128,0.32);border-radius:4px}}
    .media-art{{border-radius:0}}
    .sidebar{{background:{rail};border:0}}
    .sidebar label,.sidebar image{{color:{rail_ink}}}
    .sidebar .nav-title{{color:{rail_muted};font-size:12px;padding:8px 8px 3px;background:transparent;border:0}}
    .sidebar button{{border-radius:0;padding:9px 8px}}
    .sidebar button:hover{{background-image:none;background-color:{hover}}}
    .sidebar button.selected,.sidebar button.selected:active{{background-image:none;background-color:{selected};border:0}}
    .sidebar button.selected label,.sidebar button.selected image{{color:{selected_ink}}}
    .sidebar button:focus{{outline:2px solid {selected};outline-offset:-2px}}
    .sidebar button.selected:focus{{outline-color:{selected_ink}}}
    tooltip.background{{background-image:none;background-color:{rail};border:1px solid {rule}}}
    tooltip label{{color:{rail_ink}}}
    row.discovery-author{{border-bottom:1px solid rgba(128,128,128,0.38);padding:3px 0}}
    row.discovery-author:hover{{background:{hover}}}
    row.discovery-author:focus{{outline:2px solid {rule};outline-offset:-2px}}
    menu.media-context{{background-image:none;background-color:{rail};border:1px solid {rule};padding:4px}}
    menu.media-context menuitem{{color:{rail_ink};padding:5px 12px}}
    menu.media-context menuitem label{{color:{rail_ink}}}
    menu.media-context menuitem:hover,menu.media-context menuitem:selected{{background-color:{hover}}}
    .editorial-heading{{background:{banner};padding:10px 16px}}
    .editorial-heading > label{{color:{banner_ink}}}
    button.library-filter{{padding:5px 12px;border-radius:0}}
    button.library-filter:checked{{background-image:none;background-color:{selected};color:{selected_ink};border-color:{selected}}}
    button.library-filter:checked label{{color:{selected_ink}}}
    button.sort-heading{{background:transparent;border:0;padding:4px 0}}
    button.sort-heading:focus{{outline:2px solid {rule};outline-offset:-2px}}
    button.view-mode{{background-image:none;background-color:transparent;color:{banner_ink};border:1px solid {banner_ink};border-radius:0;padding:6px}}
    button.view-mode image{{color:{banner_ink}}}
    button.view-mode:hover{{background-color:rgba(0,0,0,0.18)}}
    button.view-mode:checked{{background-image:none;background-color:{banner_ink};color:{banner};border-color:{banner_ink}}}
    button.view-mode .detail-glyph{{color:{banner_ink};font-size:12px;font-weight:bold}}
    button.view-mode:checked image,button.view-mode:checked .detail-glyph{{color:{banner}}}
    button.view-mode:focus{{outline:2px solid {banner_ink};outline-offset:-2px}}
    button.view-mode:checked:focus{{outline-color:{banner}}}
    .title{{font-family:'Noto Serif CJK SC',serif;font-size:30px;font-weight:700}}
    .editorial-heading .title{{font-size:27px;font-weight:700}}
    separator.media-rule{{background:{rule};min-height:3px;margin-top:2px}}
    label.media-title{{font-family:'Noto Sans CJK SC',Sans;font-size:15px;font-weight:700}}
    .media-art.has-cover{{background:#171a1b}}
    button.media-card{{border-radius:0}}
    button.media-card:focus{{outline:2px solid {rule};outline-offset:-2px}}'''.encode()

CSS+=editorial_css('#232933','#f9f4e9','#c7d1db','#f1d867','#192a4a','#354356','#eecf60','#163677','#f9f4e9')
LIGHT_CSS+=editorial_css('#e9e3d8','#202b37','#526178','#24498d','#fffaf0','#d5d9db','#1e3973','#24498d','#fffaf0')
NABIS_CSS+=editorial_css('#342c3b','#fff1e4','#e2c9be','#efc486','#422331','#514052','#e6ad72','#863f52','#fff1e4')
NEO_IMPRESSION_CSS+=editorial_css('#cadfd7','#243a44','#4d6269','#a34735','#fff9ef','#b6d2c8','#a34735','#205f69','#f9f7eb')
def editorial_actions_css(accent,ink,hover,pressed):
    return f'''button.suggested-action{{background-image:none;background-color:{accent};color:{ink}}}
    button.suggested-action label,button.suggested-action image{{color:{ink}}}
    button.suggested-action:hover{{background-color:{hover}}}
    button.suggested-action:active{{background-color:{pressed}}}
    checkbutton check:checked,radiobutton radio:checked{{background-color:{accent};border-color:{accent};color:{ink}}}
    scale.player-seek trough highlight,progressbar.job-progress progress{{background-color:{accent};border-color:{accent}}}'''.encode()

CSS+=editorial_actions_css('#f1d867','#192a4a','#f8e89b','#d5b94f')
LIGHT_CSS+=editorial_actions_css('#24498d','#fffaf0','#315ca6','#18376d')
NABIS_CSS+=editorial_actions_css('#efc486','#422331','#f8d9ac','#c99365')
NEO_IMPRESSION_CSS+=editorial_actions_css('#205f69','#f9f7eb','#317783','#174851')
def media_row_css(line):
    return f'''button.media-card.media-row{{border-bottom:1px solid {line}}}'''.encode()

CSS+=media_row_css('#495051')
LIGHT_CSS+=media_row_css('#c8cecb')
NABIS_CSS+=media_row_css('#584957')
NEO_IMPRESSION_CSS+=media_row_css('#b9cec4')
# Windows GTK may inherit a 9 pt system font; preserve the existing role scale
# while giving body and metadata a readable baseline on that platform.
WINDOWS_TYPE_CSS=b'''*{font-family:'Noto Sans CJK SC','Noto Sans SC','Microsoft YaHei UI',Sans;font-size:15px}
.title{font-family:'Noto Serif CJK SC','Noto Serif SC','Microsoft YaHei UI',serif}
label.media-title{font-family:'Noto Sans CJK SC','Noto Sans SC','Microsoft YaHei UI',Sans;font-size:16px}
.sidebar .nav-title,.status,button.view-mode .detail-glyph{font-size:14px}'''
if os.name=='nt':
    CSS+=WINDOWS_TYPE_CSS;LIGHT_CSS+=WINDOWS_TYPE_CSS;NABIS_CSS+=WINDOWS_TYPE_CSS;NEO_IMPRESSION_CSS+=WINDOWS_TYPE_CSS
THEMES={'dark':('深色',CSS,True),'light':('浅色',LIGHT_CSS,False),
        'nabis':('纳比派',NABIS_CSS,True),'neo-impressionism':('新印象主义',NEO_IMPRESSION_CSS,False)}


def label(text='',css=None):
    w=Gtk.Label(label=text);w.set_xalign(0);w.set_line_wrap(True);w.set_selectable(False)
    if css:w.get_style_context().add_class(css)
    return w

def page_heading(text):
    box=Gtk.Box();box.get_style_context().add_class('editorial-heading');box.pack_start(label(text,'title'),True,True,0);return box

def button(text,cb=None,primary=False):
    b=Gtk.Button(label=text)
    if cb:b.connect('clicked',cb)
    if primary:b.get_style_context().add_class('suggested-action')
    return b

def icon_button(name,title,callback):
    b=Gtk.Button();b.connect('clicked',callback);set_button_icon(b,name,title);return b

def set_button_icon(b,name,title):
    b.set_image(Gtk.Image.new_from_icon_name(name,Gtk.IconSize.BUTTON));b.set_tooltip_text(title);b.get_accessible().set_name(title)

def nav_button(name,icon,action):
    b=Gtk.Button();row=Gtk.Box(spacing=10);row.pack_start(Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.MENU),False,False,0);row.pack_start(label(name),True,True,0);b.add(row);b.connect('clicked',action);return b

def async_call(fn,done,fail):
    def work():
        try:
            result=fn(); GLib.idle_add(done,result)
        except Exception as exc:GLib.idle_add(fail,str(exc))
    threading.Thread(target=work,daemon=True).start()


def safe_dirs():
    out=[]
    if os.name=='nt':
        for kind in (GLib.UserDirectory.DIRECTORY_VIDEOS,GLib.UserDirectory.DIRECTORY_MUSIC,GLib.UserDirectory.DIRECTORY_DOWNLOAD):
            value=GLib.get_user_special_dir(kind)
            if value:
                path=Path(value)
                if path.is_dir() and path.resolve()!=Path.home().resolve() and path not in out:out.append(path)
        return out
    for typ in ('VIDEOS','MUSIC','DOWNLOAD'):
        p=subprocess.run(['xdg-user-dir',typ],capture_output=True,text=True,check=False)
        if p.returncode or not p.stdout.strip():continue
        path=Path(p.stdout.strip()).expanduser()
        try:path=path.resolve(strict=True)
        except OSError:continue
        if path in (Path('/'),Path.home().resolve()) or not path.is_dir():continue
        if path not in out:out.append(path)
    return out


def scan_dirs(store,paths):
    count=0;exts={'.mp4','.mkv','.webm','.mov','.avi','.mp3','.m4a','.flac','.ogg','.opus','.wav'}
    for root in paths:
        for base,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink()]
            for name in files:
                p=Path(base)/name
                if p.suffix.lower() in exts and not p.is_symlink():
                    try:store.save_local(p);count+=1
                    except OSError:pass
    return count

def local_media_info(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type:stream_disposition=attached_pic:format=duration','-of','json',str(path)],capture_output=True,text=True,timeout=8)
    if p.returncode:raise ValueError('无法读取本地文件资料')
    info=json.loads(p.stdout);streams=info.get('streams',[])
    video=any(s.get('codec_type')=='video' and not (s.get('disposition') or {}).get('attached_pic') for s in streams)
    audio=any(s.get('codec_type')=='audio' for s in streams)
    duration=float((info.get('format') or {}).get('duration') or 0)
    parts=['视频' if video else '音频' if audio else '媒体文件',Path(path).suffix.lstrip('.').upper()]
    if math.isfinite(duration) and duration>0:
        seconds=int(duration);parts.append(f'{seconds//3600}:{seconds%3600//60:02d}:{seconds%60:02d}' if seconds>=3600 else f'{seconds//60:02d}:{seconds%60:02d}')
    return ' · '.join(x for x in parts if x)


class MediaCover(Gtk.Overlay):
    """Fit images to a 16:9 frame without cropping their original proportions."""
    def __init__(self,minimum_width=190):
        super().__init__()
        self.minimum_width=minimum_width;self.pixbuf=None;self.cover_height=round(minimum_width*9/16);self.image_size=None
        self.frame=Gtk.Box();self.frame.set_size_request(minimum_width,self.cover_height)
        self.frame.get_style_context().add_class('media-art')
        self.frame.connect('size-allocate',self.resize_cover);self.add(self.frame)
        self.image=Gtk.Image.new_from_icon_name('video-x-generic-symbolic',Gtk.IconSize.DIALOG)
        self.image.get_style_context().add_class('muted');self.image.set_halign(Gtk.Align.CENTER);self.image.set_valign(Gtk.Align.CENTER)
        self.add_overlay(self.image);self.set_overlay_pass_through(self.image,True)

    def resize_cover(self,widget,allocation):
        height=max(round(self.minimum_width*9/16),round(allocation.width*9/16))
        if height!=self.cover_height:
            self.cover_height=height;GLib.idle_add(self.update_height)
        if self.pixbuf:
            scale=min(allocation.width/self.pixbuf.get_width(),height/self.pixbuf.get_height())
            size=(max(1,round(self.pixbuf.get_width()*scale)),max(1,round(self.pixbuf.get_height()*scale)))
            if size!=self.image_size:
                self.image_size=size;self.image.set_from_pixbuf(self.pixbuf.scale_simple(*size,GdkPixbuf.InterpType.BILINEAR))

    def update_height(self):
        self.set_size_request(self.minimum_width,self.cover_height);self.frame.set_size_request(self.minimum_width,self.cover_height)
        return False

    def set_cover(self,path):
        self.pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,480,270,True);self.frame.get_style_context().add_class('has-cover');self.image_size=None
        self.resize_cover(self.frame,self.frame.get_allocation())



class App(Gtk.Window):
    def __init__(self,store=None):
        super().__init__(title='MediaDesk');self.set_default_size(1180,760);self.connect('delete-event',self.on_close);self.connect('destroy',self.on_destroy);self.connect('key-press-event',self.on_key);self.connect('key-release-event',self.on_key_release);self.connect('focus-out-event',self.reset_shortcut)
        self.shortcut_pressed=False;self.shortcut_release_source=0
        self.set_wmclass('mediadesk','MediaDesk')
        try:self.set_icon_from_file(str(Path(__file__).parent/'assets'/'mediadesk.svg'))
        except GLib.Error:pass
        self.store=store or Store();self.downloader=downloader.Downloads(self.store,lambda jid:GLib.idle_add(self.download_update,jid));self.thumb_workers=ThreadPoolExecutor(max_workers=6);self.player=None;self.player_open=False;self.play_request=0;self.playing_online=False;self.fullscreened=False;self.theater=False;self.rows=[];self.row_index=0;self.source_kind='library';self.view_generation=0;self.setup_step=0;self.setup_authenticated=False;self.account_checks={'youtube':0,'bilibili':0};self.account_cache={};self.account_inflight={};self.account_views={};self.youtube_auth_generation=0
        self.hover_preview=HoverPreview(self.store)
        self.library_source='all';self.sort_column=None;self.sort_descending=False
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0);self.add(root)
        head=Gtk.HeaderBar(title='MediaDesk');head.set_show_close_button(True);self.set_titlebar(head);self.header=head
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);root.pack_start(self.body,True,True,0)
        footer=Gtk.Box(spacing=12);footer.set_size_request(-1,40);footer.set_margin_start(16);footer.set_margin_end(16);footer.set_margin_bottom(8);root.pack_end(footer,False,False,0);self.footer=footer
        self.download_status=Gtk.Button();self.download_status.set_no_show_all(True);self.download_status.connect('clicked',lambda *_:(self.select_nav('jobs'),self.show_jobs()));self.download_status.set_tooltip_text('查看下载任务')
        status_box=Gtk.Box(spacing=8);self.download_label=Gtk.Label();self.download_label.set_ellipsize(3);self.download_label.set_max_width_chars(55);status_box.pack_start(self.download_label,False,False,0)
        self.download_progress=Gtk.ProgressBar();self.download_progress.set_size_request(100,-1);self.download_progress.set_valign(Gtk.Align.CENTER);self.download_progress.set_no_show_all(True);status_box.pack_start(self.download_progress,False,False,0);self.download_status.add(status_box);status_box.show_all();footer.pack_start(self.download_status,False,False,0)
        self.status=Gtk.Label(label='');self.status.set_xalign(0);self.status.set_ellipsize(3);self.status.get_style_context().add_class('status');footer.pack_start(self.status,True,True,0)
        self.retry_action=None;self.retry_button=button('重试',lambda *_:self.retry_pending());self.retry_button.set_no_show_all(True);footer.pack_start(self.retry_button,False,False,0)
        self.provider=Gtk.CssProvider();Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);self.apply_theme(self.store.setting('theme','dark'))
        if self.store.setting('setup_done',False):self.workspace()
        else:self.setup()
        self.show_all()

    def replace(self,widget):
        for ch in self.body.get_children():self.body.remove(ch)
        self.body.pack_start(widget,True,True,0);self.body.show_all()

    def apply_theme(self,theme):
        _,css,dark=THEMES.get(theme,THEMES['dark']);Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);self.provider.load_from_data(css)

    def message(self,text):
        self.retry_action=None;self.retry_button.hide();self.status.set_text(str(text));self.status.set_tooltip_text(str(text));return False
    def fail(self,text):self.message(text);return False

    def retry_pending(self):
        action=self.retry_action;self.retry_action=None;self.retry_button.hide()
        if action:action()

    def retry_message(self,text,action):
        self.message(text);self.retry_action=action;self.retry_button.show();return False

    def setup(self):
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);outer.set_border_width(25);outer.set_hexpand(True);outer.set_vexpand(True)
        shell=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);shell.get_style_context().add_class('card');shell.set_size_request(480,-1);shell.set_halign(Gtk.Align.CENTER);outer.pack_start(shell,True,True,0)
        card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.ALWAYS);scroll.set_vexpand(True);scroll.add(card);shell.pack_start(scroll,True,True,0)
        titles=['选择内容来源','连接账号','发现本地媒体','选择下载偏好','准备完成'];s=self.setup_step
        card.pack_start(label(f'{s+1} / 5  ·  首次设置','muted'),False,False,0);card.pack_start(label(titles[s],'title'),False,False,0)
        if s==0:card.pack_start(label('连接 YouTube 或 B 站账号，或直接添加视频链接。'),False,False,0)
        if s==1:
            card.pack_start(label('扫码会向 B 站请求二维码；账号连接可跳过，也可稍后设置。'),False,False,0)
            qr=button('扫码连接 B 站',self.connect_bilibili_qr);qr.set_halign(Gtk.Align.START);card.pack_start(qr,False,False,0)
            self.account_status_widgets={}
            for source,title,description in [('youtube','YouTube','使用 Google 只读授权读取订阅、喜欢的视频和播放列表，请求会发送给 Google。'),('bilibili','B 站','用 B 站手机客户端扫码连接，读取关注和收藏；也可选择读取 Chrome 登录状态。')]:
                card.pack_start(label(title,'section'),False,False,0);card.pack_start(label(description,'muted'),False,False,0)
                state=label(self.account_text(source));self.account_status_widgets[source]=state;card.pack_start(state,False,False,0)
                if source=='youtube':
                    self.youtube_connect_button=button('连接 Google 账号',self.authorize);self.youtube_connect_button.set_halign(Gtk.Align.START);card.pack_start(self.youtube_connect_button,False,False,0)
                    self.youtube_disconnect_button=button('断开连接',self.disconnect_youtube);self.youtube_disconnect_button.set_halign(Gtk.Align.START);self.youtube_disconnect_button.set_no_show_all(True);card.pack_start(self.youtube_disconnect_button,False,False,0)
                    self.youtube_import_button=button('导入 Google 客户端配置',self.import_google_client);self.youtube_import_button.set_halign(Gtk.Align.START);self.youtube_import_button.set_no_show_all(True);card.pack_start(self.youtube_import_button,False,False,0)
                else:
                    self.bilibili_connect_button=button('使用 Chrome 连接',self.toggle_bilibili_account);self.bilibili_connect_button.set_halign(Gtk.Align.START);card.pack_start(self.bilibili_connect_button,False,False,0)
            self.cookie_check=Gtk.CheckButton(label='允许解析、播放和下载时读取 Chrome 登录状态（Cookie）');self.cookie_check.set_active(self.store.setting('cookies',False));self.cookie_check.connect('toggled',lambda w:self.store.set_setting('cookies',w.get_active()));card.pack_start(self.cookie_check,False,False,0)
        if s==2:
            dirs=safe_dirs();card.pack_start(label('扫描所选目录及子目录，媒体文件路径会保存到本地库；不移动或重命名文件。'),False,False,0)
            self.dir_checks=[];dirsbox=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);card.pack_start(dirsbox,False,False,0)
            for path in dirs:
                cb=Gtk.CheckButton(label=str(path));cb.set_active(True);dirsbox.pack_start(cb,False,False,0);self.dir_checks.append((cb,path))
            if not dirs:card.pack_start(label('未发现可安全扫描的默认目录。'),False,False,0)
            card.pack_start(button('选择其他目录',lambda *_:self.choose_scan_dir(dirsbox)),False,False,0)
            card.pack_start(button('扫描选中目录',self.scan),False,False,0)
        if s==3:
            card.pack_start(label('自动选择默认下载格式；需要时可查看其他格式。'),False,False,0)
            group=None
            for key,title,desc in [('quality','画质优先','尽量选择更高画质'),('size','文件大小优先','倾向较小文件'),('balance','均衡','优先选择接近 1080p')]:
                rb=Gtk.RadioButton.new_with_label_from_widget(group,f'{title} — {desc}')
                if group is None:group=rb
                rb.set_active(self.store.setting('preference','quality')==key)
                rb.connect('toggled',lambda w,k=key:self.store.set_setting('preference',k) if w.get_active() else None);card.pack_start(rb,False,False,0)
        if s==4:card.pack_start(label('现在可以进入媒体库；跳过的步骤可以稍后再设置。'),False,False,0)
        row=Gtk.Box(spacing=8)
        if s:row.pack_start(button('上一步',lambda *_:self.setup_move(-1)),False,False,0)
        row.pack_end(button('进入媒体库' if s==4 else '继续',self.setup_next,True),False,False,0)
        if s<4:row.pack_end(button('跳过',self.setup_next),False,False,0)
        shell.pack_start(row,False,False,0);self.replace(outer)

    def setup_move(self,n):self.setup_step+=n;self.setup()
    def setup_next(self,*_):
        if self.setup_step==4:
            self.store.set_setting('setup_done',True);self.workspace()
            if self.setup_authenticated:self.load_source('likes')
        else:self.setup_step+=1;self.setup()

    def authorize(self,*_):
        self.message('正在检查 Google 授权…')
        if self.account_surface_active():self.account_view_status('youtube','checking')
        self.youtube_auth_generation+=1;request=self.youtube_auth_generation
        def done(_):
            if request!=self.youtube_auth_generation:return False
            self.store.set_setting('youtube_account_enabled',True);self.account_cache.pop('youtube',None)
            self.setup_authenticated=True;self.message('正在验证 Google 账号…')
            if self.account_surface_active():self.check_account('youtube')
            return False
        def failed(error):
            if request==self.youtube_auth_generation:
                self.fail(error)
                if self.account_surface_active():self.account_view_status('youtube','unknown',error)
            return False
        async_call(lambda:sources.list_youtube('auth'),done,failed)

    def import_google_client(self,*_):
        dialog=Gtk.FileChooserDialog(title='选择 Google OAuth 客户端配置文件',transient_for=self,action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'导入',Gtk.ResponseType.OK);response=dialog.run();path=dialog.get_filename();dialog.destroy()
        if response!=Gtk.ResponseType.OK or not path:return
        try:
            from .oauth_config import import_client
            import_client(path)
        except (ValueError,OSError) as exc:
            self.account_status_widgets['youtube'].set_text('导入失败：'+str(exc)+'。请选择正确的配置文件后重试。');return
        self.account_status_widgets['youtube'].set_text('配置已导入，请连接 Google 账号。');self.youtube_import_button.hide();self.youtube_connect_button.show()

    def choose_scan_dir(self, container):
        d=Gtk.FileChooserDialog(title='选择媒体目录',transient_for=self,action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'选择',Gtk.ResponseType.OK);result=d.run();chosen=d.get_filename();d.destroy()
        if result==Gtk.ResponseType.OK and chosen:
            path=Path(chosen).resolve()
            if path in (Path('/'),Path.home().resolve()):self.fail('请指定更具体的目录');return
            if any(path==p for _,p in self.dir_checks):return
            cb=Gtk.CheckButton(label=str(path));cb.set_active(True);container.pack_start(cb,False,False,0);self.dir_checks.append((cb,path));container.show_all()

    def scan(self,*_):
        paths=[p for cb,p in self.dir_checks if cb.get_active()];self.message('正在后台扫描所选目录…')
        async_call(lambda:scan_dirs(self.store,paths),lambda n:self.message(f'扫描完成：找到 {n} 个文件'),self.fail)

    def workspace(self):
        if self.player:self.player.close();self.player=None
        box=Gtk.Box(spacing=0);side=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);side.set_border_width(12);side.get_style_context().add_class('sidebar');side_scroll=Gtk.ScrolledWindow();side_scroll.set_size_request(210,-1);side_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);side_scroll.add(side);box.pack_start(side_scroll,False,False,0);self.side=side_scroll;self.nav_buttons={}
        side.pack_start(label('媒体库','nav-title'),False,False,0)
        def add_nav(key,title,icon,action):
            b=nav_button(title,icon,lambda *_:(self.select_nav(key),action()));self.nav_buttons[key]=b;side.pack_start(b,False,False,0)
        add_nav('library','全部内容','view-grid-symbolic',lambda:self.show_library())
        add_nav('jobs','下载任务','folder-download-symbolic',self.show_jobs)
        side.pack_start(nav_button('添加链接','list-add-symbolic',self.add_url),False,False,0)
        side.pack_start(label('我的列表','nav-title'),False,False,0)
        self.collection_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=2);side.pack_start(self.collection_box,False,False,0);self.refresh_collections()
        side.pack_start(nav_button('新建列表','folder-new-symbolic',self.new_collection),False,False,0)
        side.pack_start(label('发现','nav-title'),False,False,0)
        add_nav('podcasts','播客','audio-x-generic-symbolic',self.show_podcasts)
        add_nav('discover-follow','关注','avatar-default-symbolic',lambda:self.show_discovery('follow'))
        add_nav('discover-collections','收藏与播放列表','user-bookmarks-symbolic',lambda:self.show_discovery('collections'))
        side.pack_start(label('平台','nav-title'),False,False,0)
        add_nav('platform-youtube','YouTube','video-x-generic-symbolic',lambda:self.show_settings())
        add_nav('platform-bilibili','B 站','video-x-generic-symbolic',lambda:self.show_settings())
        self.platform_status('youtube');self.platform_status('bilibili')
        add_nav('settings','设置','emblem-system-symbolic',self.show_settings)
        self.content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);self.content.set_border_width(25);box.pack_start(self.content,True,True,0);self.replace(box);self.show_library()

    def select_nav(self,key):
        self.active_nav=key
        for k,b in self.nav_buttons.items():
            context=b.get_style_context();context.add_class('selected') if k==key else context.remove_class('selected')

    def refresh_collections(self):
        for ch in self.collection_box.get_children():self.collection_box.remove(ch)
        self.nav_buttons={k:v for k,v in self.nav_buttons.items() if not k.startswith('collection:')}
        for c in self.store.collections():
            key='collection:'+str(c['id']);b=nav_button(c['name'],'folder-symbolic',lambda _,cid=c['id'],k=key:(self.select_nav(k),self.show_library(cid)));self.nav_buttons[key]=b;self.collection_box.pack_start(b,False,False,0)
        self.collection_box.show_all()

    def clear_content(self):
        self.hover_preview.stop()
        self.view_generation+=1;self.play_request+=1
        if self.player:self.player.close();self.player=None
        self.jobs_visible=False
        for ch in self.content.get_children():self.content.remove(ch)
    def set_content(self,*widgets):
        self.clear_content()
        for w in widgets:self.content.pack_start(w,False,False,0)
        self.content.show_all()

    def show_library(self,cid=None,query=''):
        self.source_kind='library';self.select_nav('collection:'+str(cid) if cid else 'library');self.rows=self.store.media(cid)
        name=next((c['name'] for c in self.store.collections() if c['id']==cid),'我的列表') if cid else '全部内容';self.display_rows(name,self.rows,query=query)

    def display_rows(self,title,rows,loading=False,query=''):
        self.rows=rows;self.rows_title=title;self.rows_query=query;self.clear_content()
        snapshot=getattr(self,'collection_discovery_snapshot',None)
        context=getattr(self,'xiaoyuzhou_context',None)
        if context and self.source_kind=='playlist-items':
            self.content.pack_start(button(self.imported_program_back_label(context),lambda *_:self.return_imported_programs(context)),False,False,0)
        elif snapshot and self.source_kind in ('likes','playlist-items','bili-favorites'):
            back=button('← 返回收藏与播放列表',lambda *_:self.show_discovery('collections',snapshot));self.content.pack_start(back,False,False,0)
        heading=Gtk.Box(spacing=12);heading.get_style_context().add_class('editorial-heading');heading.pack_start(label(title,'title'),True,True,0);self.rows_count=label(f'{len(rows)} 项'+(' · 正在读取…' if loading else ''),'muted');heading.pack_end(self.rows_count,False,False,0);self.content.pack_start(heading,False,False,0)
        if not rows and not loading:
            empty=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);empty.set_valign(Gtk.Align.START);empty.set_halign(Gtk.Align.START);empty.set_margin_top(48)
            empty.pack_start(label('这里还没有内容','title'),False,False,0);empty.pack_start(label('读取 YouTube 内容，或添加 YouTube、B 站视频链接。','muted'),False,False,0)
            actions=Gtk.Box(spacing=8);actions.pack_start(button('收藏与播放列表',lambda *_:self.show_discovery('collections')),False,False,0);actions.pack_start(button('添加链接',self.add_url,True),False,False,0);empty.pack_start(actions,False,False,0);self.content.pack_start(empty,True,True,0);self.content.show_all();return
        self.media_view=self.store.setting('media_view','grid')
        if self.media_view not in ('grid','list','details'):self.media_view='grid'
        view=Gtk.Box(spacing=0);self.view_buttons={};group=None
        for key,title,icon in [('grid','网格视图','view-grid-symbolic'),('list','列表视图','view-list-bullet-symbolic'),('details','详细视图',None)]:
            control=Gtk.RadioButton.new_from_widget(group);control.set_mode(False)
            if icon:image=Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.BUTTON)
            else:
                image=Gtk.Box(spacing=0);image.set_size_request(16,16)
                for _ in range(2):
                    glyph=Gtk.Label(label='≡');glyph.get_style_context().add_class('detail-glyph');image.pack_start(glyph,True,True,0)
            control.add(image);control.get_style_context().add_class('view-mode')
            control.set_tooltip_text(title);control.get_accessible().set_name(title);view.pack_start(control,False,False,0);self.view_buttons[key]=control
            if group is None:group=control
        self.view_buttons[self.media_view].set_active(True);heading.pack_end(view,False,False,0)
        search=Gtk.SearchEntry();search.set_placeholder_text('搜索当前列表的标题或频道');self.content.pack_start(search,False,False,0)
        library_filter=getattr(self,'active_nav','')=='library'
        if library_filter:
            filters=Gtk.Box(spacing=0);self.source_buttons={};group=None
            for key,text in [('all','全部'),('youtube','YouTube'),('bilibili','B 站'),('local','本地')]:
                control=Gtk.RadioButton.new_from_widget(group);control.set_mode(False);control.add(Gtk.Label(label=text));control.get_style_context().add_class('library-filter');filters.pack_start(control,False,False,0);self.source_buttons[key]=control
                if group is None:group=control
            self.source_buttons[self.library_source].set_active(True);self.content.pack_start(filters,False,False,0)
        no_results=label('没有匹配的内容。','muted');no_results.set_no_show_all(True);self.content.pack_start(no_results,False,False,0)
        columns=Gtk.Box(spacing=12);columns.set_margin_start(12);columns.set_margin_end(12);columns.set_no_show_all(True)
        self.sort_buttons={};self.detail_column_groups={key:Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL) for key in ('source','duration','state')}
        for key,text,width in [('title','标题',None),('source','来源 / 频道',110),('duration','时长',55),('state','状态',72)]:
            control=Gtk.Button();control.get_style_context().add_class('sort-heading');control.set_halign(Gtk.Align.FILL);control.set_tooltip_text('按'+text+'排序');control.get_accessible().set_name('按'+text+'排序');child=Gtk.Label();child.set_xalign(0);control.add(child)
            if width:control.set_size_request(width,-1);self.detail_column_groups[key].add_widget(control)
            columns.pack_start(control,width is None,width is None,0);control.show_all();self.sort_buttons[key]=(control,text,child)
        def update_sort_labels():
            for key,(control,text,child) in self.sort_buttons.items():
                active=key==self.sort_column;arrow=(' ↓' if self.sort_descending else ' ↑') if active else ' ↕'
                child.set_text(text+arrow);control.get_accessible().set_name('按'+text+'排序'+(('，降序' if self.sort_descending else '，升序') if active else ''))
        update_sort_labels()
        self.content.pack_start(columns,False,False,0)
        box=Gtk.FlowBox();self.rows_box=box;box.set_selection_mode(Gtk.SelectionMode.NONE);box.set_homogeneous(True);box.set_min_children_per_line(1);box.set_max_children_per_line(4 if self.media_view=='grid' else 1);box.set_column_spacing(12);box.set_row_spacing(12 if self.media_view=='grid' else 2);box.set_valign(Gtk.Align.START)
        box.set_filter_func(lambda child:search.get_text().strip().casefold() in child.search_text and (not library_filter or self.library_source=='all' or child.media_item.get('source')==self.library_source))
        def sort_value(child):
            item=child.media_item
            if self.sort_column=='title':return (str(item.get('title') or '').casefold(),)
            if self.sort_column=='source':return (str(item.get('source') or '').casefold(),str(item.get('channel') or '').casefold())
            if self.sort_column=='duration':
                d=item.get('duration');return (d,) if isinstance(d,(int,float)) and math.isfinite(d) and d>0 else None
            if self.sort_column=='state':return (child.sort_state,)
            return None
        def compare(a,b,*_):
            if not self.sort_column:return (a.row_index>b.row_index)-(a.row_index<b.row_index)
            x,y=sort_value(a),sort_value(b)
            if x is None or y is None:return (x is None)-(y is None)
            result=(x>y)-(x<y)
            return -result if self.sort_descending else result
        box.set_sort_func(compare)
        def filter_rows(*_):
            self.rows_query=search.get_text().strip();box.invalidate_filter();no_results.set_visible(not any(child.get_child_visible() for child in box.get_children()) and (bool(self.rows_query) or (library_filter and self.library_source!='all')))
        def search_changed(*_):self.hover_preview.stop();filter_rows()
        self.refresh_rows_filter=filter_rows;search.connect('search-changed',search_changed);search.set_text(query)
        if library_filter:
            def change_source(control,source):
                if control.get_active():self.hover_preview.stop();self.library_source=source;filter_rows()
            for key,control in self.source_buttons.items():control.connect('toggled',change_source,key)
        def change_sort(_,key):
            self.hover_preview.stop()
            if self.sort_column==key:self.sort_descending=not self.sort_descending
            else:self.sort_column=key;self.sort_descending=False
            update_sort_labels();box.invalidate_sort()
        for key,(control,_,_) in self.sort_buttons.items():control.connect('clicked',change_sort,key)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.content.pack_start(scroll,True,True,0);self.detail_source_chars=8
        def set_grid_columns(width):
            if self.media_view=='grid':box.set_max_children_per_line(max(4,width//500))
            return False
        def resize_grid(_,allocation):
            if self.media_view=='grid' and box.get_max_children_per_line()!=max(4,allocation.width//500):
                GLib.idle_add(set_grid_columns,allocation.width)
            if self.media_view=='details':
                cap=max(8,min(24,8+max(0,allocation.width-450)//45))
                if cap!=self.detail_source_chars:
                    self.detail_source_chars=cap
                    def resize_sources():
                        if self.rows_box is box and self.media_view=='details':
                            for row in box.get_children():row.get_child().get_child().get_children()[1].set_max_width_chars(self.detail_source_chars)
                        return False
                    GLib.idle_add(resize_sources)
        scroll.connect('size-allocate',resize_grid)
        def change_view(control,selected):
            if not control.get_active() or selected==self.media_view:return
            self.media_view=selected;self.store.set_setting('media_view',selected)
            box.set_max_children_per_line(max(4,scroll.get_allocated_width()//500) if selected=='grid' else 1);box.set_row_spacing(12 if selected=='grid' else 2)
            columns.set_visible(selected=='details')
            self.hover_preview.stop()
            for child in box.get_children():box.remove(child)
            self.append_cards(self.rows,0)
        for key,control in self.view_buttons.items():control.connect('toggled',change_view,key)
        self.append_cards(rows,0);self.content.show_all();columns.set_visible(self.media_view=='details')

    def append_cards(self,rows,start):
        box=self.rows_box
        for i,item in enumerate(rows,start):
            origin={'local':'本地文件','youtube':'YouTube','bilibili':'B 站','podcast':'播客'}.get(item.get('source'),'其他来源');channel=item.get('channel');state=('本地可用' if Path(item['path']).is_file() else '文件缺失') if item.get('path') else '未下载'
            if item.get('unavailable'):state='来源已失效'+(' · 本地可用' if item.get('path') and Path(item['path']).is_file() else '')
            if self.media_view=='grid':
                card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7);card.set_border_width(6);card.set_size_request(210,-1)
                artwork=MediaCover(190);card.pack_start(artwork,False,False,0)
                if item.get('thumbnail') and item.get('source')!='podcast':
                    if self.source_kind=='creator-local':self.load_cached_art(artwork,item['thumbnail'])
                    else:self.load_art(artwork,item['thumbnail'])
                details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);card.pack_start(details,False,False,0)
                rule=Gtk.Separator();rule.get_style_context().add_class('media-rule');details.pack_start(rule,False,False,0)
                t=label(item.get('title') or '未命名','media-title');t.set_max_width_chars(28);t.set_lines(2);t.set_ellipsize(3);t.set_tooltip_text(item.get('title') or '未命名');details.pack_start(t,False,False,0)
                if channel:
                    creator=label(channel,'muted');creator.set_max_width_chars(24);creator.set_ellipsize(3);creator.set_tooltip_text(channel);details.pack_start(creator,False,False,0)
                desc=label(' · '.join((origin,state)),'muted');desc.set_max_width_chars(24);desc.set_ellipsize(3);desc.set_tooltip_text(desc.get_text());details.pack_start(desc,False,False,0)
            else:
                card=Gtk.Box(spacing=12);card.set_border_width(8)
                title_text=item.get('title') or '未命名';t=label(title_text,'media-title');t.set_line_wrap(False);t.set_ellipsize(3);t.set_tooltip_text(title_text);card.pack_start(t,True,True,0)
                if self.media_view=='details':
                    duration=item.get('duration');duration_text='—'
                    if isinstance(duration,(int,float)) and math.isfinite(duration) and duration>0:
                        seconds=int(duration);duration_text=f'{seconds//3600}:{seconds%3600//60:02d}:{seconds%60:02d}' if seconds>=3600 else f'{seconds//60}:{seconds%60:02d}'
                    for key,value,width in [('source',' · '.join(x for x in (origin,channel) if x),110),('duration',duration_text,55),('state',state,72)]:
                        field=label(value,'muted');field.set_line_wrap(False);field.set_ellipsize(3);field.set_max_width_chars(self.detail_source_chars if key=='source' else 8);field.set_tooltip_text(value);field.set_size_request(width,-1);self.detail_column_groups[key].add_widget(field);card.pack_start(field,False,False,0)
                else:
                    summary_text=' · '.join(x for x in (channel,origin,state) if x);summary=label(summary_text,'muted');summary.set_line_wrap(False);summary.set_ellipsize(3);summary.set_max_width_chars(24);summary.set_tooltip_text(summary_text);card.pack_start(summary,False,False,0)
            b=Gtk.Button();b.get_style_context().add_class('media-card');b.connect('clicked',lambda _,idx=i:self.open_row(idx));b.add(card)
            if self.media_view!='grid':b.get_style_context().add_class('media-row')
            b.get_accessible().set_description('右键或 Shift+F10 打开作品操作')
            def context_press(widget,event,idx=i):
                if event.button==3:self.show_media_menu(widget,idx,event);return True
                return False
            b.connect('button-press-event',context_press)
            b.connect('popup-menu',lambda widget,idx=i:self.show_media_menu(widget,idx))
            local_preview=bool(item.get('path') and Path(item['path']).is_file())
            if self.media_view=='grid' and (self.source_kind!='creator-local' or local_preview) and (item.get('source')!='podcast' or local_preview):self.hover_preview.track(b,artwork,item)
            child=Gtk.FlowBoxChild();child.row_index=i;child.media_item=item;child.sort_state=3 if item.get('unavailable') else {'本地可用':0,'未下载':1,'文件缺失':2}[state];child.search_text=(str(item.get('title') or '')+' '+str(item.get('channel') or '')).casefold();child.add(b);box.add(child)
        box.show_all();self.refresh_rows_filter()

    def show_media_menu(self,widget,idx,event=None):
        if not 0<=idx<len(self.rows):return True
        self.hover_preview.stop()
        item=self.rows[idx];fresh=self.store.get(item['id']) if item.get('id') else None
        if fresh:item={**item,**fresh}
        local=bool(item.get('path') and Path(item['path']).is_file())
        online=bool(item.get('url') and not item.get('unavailable'))
        menu=Gtk.Menu();menu.get_style_context().add_class('media-context');self.media_context_menu=menu
        def add(text,action):
            option=Gtk.MenuItem(label=text);option.connect('activate',lambda *_:action());menu.append(option)
        def play():
            self.start_button=None;self.open_row(idx)
            if self.start_button:self.start_button.clicked()
        if local or online:add('播放',play)
        add('查看详情',lambda:self.open_row(idx))
        if online:
            add('下载',lambda:self.prepare_download(item))
            add('选择下载格式',lambda:self.inspect_and_download(item['url'],True))
        if item.get('id'):add('管理所属列表',lambda:self.choose_collection(item))
        if local:add('打开所在文件夹',lambda:self.open_local(Path(item['path']).parent))
        if item.get('url'):
            add('复制来源链接',lambda:Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(item['url'],-1))
        menu.connect('deactivate',lambda menu:GLib.idle_add(menu.destroy))
        menu.show_all()
        if event:menu.popup_at_pointer(event)
        else:menu.popup_at_widget(widget,Gdk.Gravity.SOUTH_WEST,Gdk.Gravity.NORTH_WEST,Gtk.get_current_event())
        return True

    def show_art(self,widget,path):
        if path:
            try:
                path=str(path)
                if isinstance(widget,MediaCover):widget.set_cover(path)
                else:widget.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path,190,107,True))
            except GLib.Error:pass
        return False

    def load_cached_art(self,widget,url):
        import hashlib
        from urllib.parse import urlparse
        parsed=urlparse(url)
        if parsed.scheme=='http' and (parsed.hostname or '').lower().endswith('.hdslb.com') and not parsed.username and not parsed.password:url=parsed._replace(scheme='https').geturl()
        path=self.store.root/'thumbnails'/(hashlib.sha256(url.encode()).hexdigest()+'.img')
        if path.is_file():self.show_art(widget,path)

    def load_art(self,widget,url):
        future=self.thumb_workers.submit(sources.thumbnail,self.store,url)
        def done(result):
            try:GLib.idle_add(self.show_art,widget,result.result())
            except Exception:pass
        future.add_done_callback(done)

    def load_source(self,kind,playlist_id='',program=None):
        if not self.store.setting('youtube_account_enabled',True):
            self.show_settings();self.message('YouTube 已断开，请先连接账号');return
        self.xiaoyuzhou_context=program
        self.source_kind=kind;self.select_nav('discover-follow' if kind=='subscriptions' else 'discover-collections')
        title={'likes':'喜欢的视频','playlists':'播放列表','subscriptions':'订阅频道','playlist-items':'播放列表内容'}[kind]
        if program:title=program['title']+' · YouTube 作品';self.select_nav('podcasts')
        if kind in ('likes','playlist-items'):
            self.display_rows(title,[],loading=True);generation=self.view_generation;self.message('正在后台读取 YouTube…');count=[0]
            def page(raw):
                items=[]
                for value in raw:
                    item={**sources.normalize(value,kind),'source':'youtube'}
                    try:
                        if item['url']:youtube_id(item['url']);items.append(item)
                    except ValueError:continue
                saved=self.store.save_youtube_batch(items);count[0]+=len(saved)
                def show():
                    if generation==self.view_generation:
                        start=len(self.rows);self.rows.extend(saved);self.append_cards(saved,start);self.rows_count.set_text(f'{len(self.rows)} 项 · 正在读取…')
                    return False
                GLib.idle_add(show)
            def done(_):
                current=generation==self.view_generation
                if current:
                    if self.rows:self.rows_count.set_text(f'{len(self.rows)} 项')
                    else:self.display_rows(title,[])
                self.message(f'读取完成：{count[0]} 项'+('；重新打开全部内容查看' if not current else ''));return False
            def failed(error):
                if generation==self.view_generation:
                    self.rows_count.set_text(f'{len(self.rows)} 项 · 读取未完成');retry=button('重新读取',lambda *_:self.load_source(kind,playlist_id,program=program));self.content.pack_start(retry,False,False,0);retry.set_halign(Gtk.Align.START);retry.show();self.message('读取未完成：'+error)
                else:self.fail(error)
                return False
            async_call(lambda:sources.stream_youtube(kind,page,playlist_id),done,failed);return
        self.set_content(label(title,'title'),label('正在读取 YouTube 内容…','muted'));generation=self.view_generation;self.message('正在后台读取 YouTube…')
        def fetch():
            return sources.list_youtube(kind,playlist_id)
        def done(items):
            if generation!=self.view_generation:
                self.message(f'YouTube 后台读取完成：{len(items)} 项；重新打开全部内容查看');return False
            self.rows=items;self.display_source(kind,items)
            self.message(f'读取完成：{len(items)} 项');return False
        def failed(error):
            if generation==self.view_generation:self.set_content(label(title,'title'),label('读取失败：'+error,'muted'),button('重试',lambda *_:self.load_source(kind,playlist_id,program=program)))
            self.fail(error);return False
        async_call(fetch,done,failed)

    def display_source(self,kind,items):
        box=Gtk.ListBox();box.set_selection_mode(Gtk.SelectionMode.NONE)
        for item in items:
            sn=item.get('snippet') or {};r=Gtk.ListBoxRow();row=Gtk.Box(spacing=10);row.set_border_width(10);row.pack_start(label(sn.get('title','未命名')),True,True,0)
            if kind=='playlists':row.pack_end(button('查看',lambda _,i=item:self.load_source('playlist-items',i['id'])),False,False,0)
            r.add(row);box.add(r)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.clear_content();self.content.pack_start(label('YouTube 播放列表' if kind=='playlists' else 'YouTube 订阅','title'),False,False,0);self.content.pack_start(scroll,True,True,0);self.content.show_all()

    def show_discovery(self,category,snapshot=None):
        self.select_nav('discover-follow' if category=='follow' else 'discover-collections')
        title='关注' if category=='follow' else '收藏与播放列表';self.clear_content();generation=self.view_generation
        heading=Gtk.Box(spacing=12);heading.get_style_context().add_class('editorial-heading');heading.pack_start(label(title,'title'),True,True,0)
        choice=Gtk.ComboBoxText();choice.append('all','全部平台');choice.append('youtube','YouTube');choice.append('bilibili','B 站');choice.set_active_id(snapshot['filter'] if snapshot else 'all');heading.pack_end(choice,False,False,0)
        self.content.pack_start(heading,False,False,0);status=label('正在读取…','muted');self.content.pack_start(status,False,False,0)
        box=Gtk.ListBox();box.set_selection_mode(Gtk.SelectionMode.NONE)
        def activate_discovery(_,row):
            if getattr(row,'creator_data',None):self.open_creator(*row.creator_data)
            elif getattr(row,'discovery_action',None):self.collection_discovery_snapshot=self.snapshot_discovery('collections');row.discovery_action(row)
        box.connect('row-activated',activate_discovery)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.content.pack_start(scroll,True,True,0);self.content.show_all()
        self.discovery_choice=choice;self.discovery_box=box;self.discovery_status=status
        entries=list(snapshot['entries']) if snapshot else [];states=dict(snapshot['states']) if snapshot else {'youtube':'正在读取','bilibili':'正在读取'};received={'youtube':0,'bilibili':0}
        self.discovery_snapshot={'category':category,'entries':entries,'states':states,'choice':choice,'generation':generation}
        def render(*_):
            if generation!=self.view_generation:return False
            for child in box.get_children():box.remove(child)
            selected=choice.get_active_id();shown=[x for x in entries if selected in ('all',x['source'])]
            for item in shown:
                line=Gtk.Box(spacing=10);line.set_border_width(10);line.pack_start(label(item['name']),True,True,0);line.pack_start(label('YouTube' if item['source']=='youtube' else 'B 站','muted'),False,False,0)
                row=Gtk.ListBoxRow();row.add(line)
                if category=='follow' and item.get('creator_id'):
                    row.get_style_context().add_class('discovery-author');row.set_can_focus(True);row.set_activatable(True)
                    row.set_tooltip_text('查看 '+item['name']+' 的视频');row.get_accessible().set_name(item['name']+'，查看视频')
                    line.pack_end(Gtk.Image.new_from_icon_name('go-next-symbolic',Gtk.IconSize.MENU),False,False,0)
                    row.creator_data=(item['source'],item['creator_id'],item['name'])
                elif category=='collections' and item.get('action') and not item.get('placeholder'):
                    row.get_style_context().add_class('discovery-author');row.set_can_focus(True);row.set_activatable(True)
                    row.set_tooltip_text('打开 '+item['name']);row.get_accessible().set_name(item['name']+'，查看内容')
                    line.pack_end(Gtk.Image.new_from_icon_name('go-next-symbolic',Gtk.IconSize.MENU),False,False,0)
                    row.discovery_action=item['action']
                else:
                    row.set_activatable(False)
                    if item.get('action'):line.pack_end(button('查看',item['action']),False,False,0)
                    elif item.get('url'):line.pack_end(Gtk.LinkButton.new_with_label(item['url'],'查看主页'),False,False,0)
                box.add(row)
            box.show_all();visible=('youtube','bilibili') if selected=='all' else (selected,)
            count=sum(not item.get('placeholder') for item in shown)
            status.set_text(f'{count} 项  ·  '+'  ·  '.join(('YouTube' if x=='youtube' else 'B 站')+'：'+states[x] for x in visible));return False
        choice.connect('changed',render)
        def accept(source,items):
            received[source]+=sum(not item.get('placeholder') and not item.get('static') for item in items)
            def show():
                if generation==self.view_generation:entries.extend(items);render()
                return False
            GLib.idle_add(show)
        def finish(source,error=''):
            def update():
                if generation==self.view_generation:states[source]=error or '读取完成';render()
                return False
            GLib.idle_add(update)
        def youtube():
            if not self.store.setting('youtube_account_enabled',True):finish('youtube','未连接');return
            if category=='collections':accept('youtube',[{'source':'youtube','name':'喜欢的视频','static':True,'action':lambda *_:self.load_source('likes')}])
            try:
                raw=sources.list_youtube('subscriptions' if category=='follow' else 'playlists');items=[]
                for value in raw:
                    sn=value.get('snippet') or {};item={'source':'youtube','name':sn.get('title') or '未命名'}
                    if category=='collections':item['action']=lambda _,i=value:self.load_source('playlist-items',i['id'])
                    else:
                        cid=(sn.get('resourceId') or {}).get('channelId') or ''
                        if cid and all(c.isalnum() or c in '_-' for c in cid):item['creator_id']=cid
                    items.append(item)
                accept('youtube',items);finish('youtube')
            except Exception as exc:finish('youtube',('读取未完成：' if received['youtube'] else '读取失败：')+str(exc))
        def bili():
            if not self.store.setting('bilibili_cookies',False):
                accept('bilibili',[{'source':'bilibili','name':'需要允许读取 B 站登录状态','placeholder':True,'action':lambda *_:self.load_bilibili('followings' if category=='follow' else 'folders')}]);finish('bilibili','未授权');return
            try:
                def page(raw):
                    items=[]
                    for value in raw:
                        if category=='follow':
                            mid=value.get('mid');item={'source':'bilibili','name':value.get('uname') or '未知 UP 主'}
                            if isinstance(mid,int) and not isinstance(mid,bool) and mid>0:item['creator_id']=str(mid)
                        else:
                            name=value.get('title') or '未命名收藏夹';item={'source':'bilibili','name':name,'action':lambda _,i=value,n=name:self.load_bilibili('favorites',str(i['id']),n)}
                        items.append(item)
                    accept('bilibili',items)
                self.bilibili_stream('followings' if category=='follow' else 'folders',page);finish('bilibili')
            except Exception as exc:finish('bilibili',('读取未完成：' if received['bilibili'] else '读取失败：')+str(exc))
        if snapshot:render()
        else:threading.Thread(target=youtube,daemon=True).start();threading.Thread(target=bili,daemon=True).start()

    def load_bilibili(self,kind,fid='',title=''):
        if not self.store.setting('bilibili_cookies',False):
            dialog=Gtk.MessageDialog(transient_for=self,flags=Gtk.DialogFlags.MODAL,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,text='连接 B 站账号')
            dialog.format_secondary_text('允许 MediaDesk 读取 Chrome 的 B 站登录状态，用于只读获取关注和收藏。可在设置中关闭。')
            dialog.add_button('取消',Gtk.ResponseType.CANCEL);dialog.add_button('允许并读取',Gtk.ResponseType.OK)
            response=dialog.run();dialog.destroy()
            if response!=Gtk.ResponseType.OK:return
            self.store.set_setting('bilibili_cookies',True)
        self.select_nav('discover-follow' if kind=='followings' else 'discover-collections')
        self.source_kind='bili-'+kind;title=title or {'followings':'B 站关注','folders':'B 站收藏夹','favorites':'收藏内容'}[kind]
        if kind=='favorites':
            self.display_rows(title,[],loading=True);generation=self.view_generation;count=[0]
            def page(raw):
                rows=[]
                for value in raw:
                    item=bilibili.normalize(value)
                    if item['unavailable']:
                        if item['url']:
                            ident=identify_url(item['url']);mid='bilibili:'+ident['id'];saved=self.store.get(mid)
                            if saved:item['id']=mid;item['path']=saved.get('path')
                    else:
                        mid=self.store.save_source(item);item={**item,**self.store.get(mid)}
                    rows.append(item)
                count[0]+=len(rows)
                def show():
                    if generation==self.view_generation:
                        start=len(self.rows);self.rows.extend(rows);self.append_cards(rows,start);self.rows_count.set_text(f'{len(self.rows)} 项 · 正在读取…')
                    return False
                GLib.idle_add(show)
            def fetch():self.bilibili_stream('favorites',page,fid)
            def done(_):
                if generation==self.view_generation:
                    if self.rows:self.rows_count.set_text(f'{len(self.rows)} 项')
                    else:self.display_rows(title,[])
                self.message(f'B 站收藏读取完成：{count[0]} 项');return False
            def failed(error):
                if generation==self.view_generation:
                    self.rows_count.set_text(f'{len(self.rows)} 项 · 读取未完成');retry=button('重新读取',lambda *_:self.load_bilibili(kind,fid,title));self.content.pack_start(retry,False,False,0);retry.show()
                self.fail('B 站读取未完成：'+error);return False
            self.message('正在读取 B 站收藏…');async_call(fetch,done,failed);return
        box=Gtk.ListBox();box.set_selection_mode(Gtk.SelectionMode.NONE);scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box)
        heading=label(title,'title');status=label('正在读取…','muted');self.clear_content();self.content.pack_start(heading,False,False,0);self.content.pack_start(status,False,False,0);self.content.pack_start(scroll,True,True,0);self.content.show_all();generation=self.view_generation;count=[0]
        def page(items):
            count[0]+=len(items)
            def show():
                if generation!=self.view_generation:return False
                for item in items:
                    row=Gtk.Box(spacing=10);row.set_border_width(10)
                    if kind=='folders':
                        name=item.get('title') or '未命名收藏夹';row.pack_start(label(name),True,True,0);row.pack_start(label(str(item.get('media_count',0))+' 项','muted'),False,False,0)
                        row.pack_end(button('查看',lambda _,i=item,n=name:self.load_bilibili('favorites',str(i['id']),n)),False,False,0)
                    else:
                        row.pack_start(label(item.get('uname') or '未知 UP 主'),True,True,0);mid=item.get('mid')
                        if isinstance(mid,int) and mid>0:row.pack_end(Gtk.LinkButton.new_with_label(f'https://space.bilibili.com/{mid}','查看主页'),False,False,0)
                    entry=Gtk.ListBoxRow();entry.add(row);box.add(entry)
                box.show_all();status.set_text(f'{count[0]} 项 · 正在读取…');return False
            GLib.idle_add(show)
        def fetch():self.bilibili_stream(kind,page,fid)
        def done(_):
            if generation==self.view_generation:status.set_text(f'{count[0]} 项')
            self.message(f'B 站读取完成：{count[0]} 项');return False
        def failed(error):
            if generation==self.view_generation:
                status.set_text(f'{count[0]} 项 · 读取未完成：{error}');retry=button('重新读取',lambda *_:self.load_bilibili(kind,fid,title));self.content.pack_start(retry,False,False,0);retry.show()
            self.fail('B 站读取未完成：'+error);return False
        self.message('正在读取 B 站账号…');async_call(fetch,done,failed)

    def snapshot_discovery(self,category):
        previous=getattr(self,'discovery_snapshot',None)
        if not previous or previous['category']!=category or previous['generation']!=self.view_generation:return None
        states={key:('读取未完成' if value=='正在读取' else value) for key,value in previous['states'].items()}
        return {'entries':list(previous['entries']),'states':states,'filter':previous['choice'].get_active_id()}

    def open_creator(self,source,creator_id,name,query=''):
        if source not in ('youtube','bilibili') or not str(creator_id).strip() or not str(name).strip():
            self.message('作者资料不完整，无法查找');return
        snapshot=self.snapshot_discovery('follow')
        if snapshot is not None:self.creator_follow_snapshot=snapshot
        self.source_kind='creator-local';self.creator_ref=(source,str(creator_id),str(name))
        rows=[];name_matches=0
        for item in self.store.media():
            if item.get('source')!=source:continue
            try:
                metadata=item.get('metadata') or {}
                if isinstance(metadata,str):metadata=json.loads(metadata)
                if not isinstance(metadata,dict):metadata={}
            except (ValueError,TypeError):metadata={}
            known=metadata.get('creator_id')
            if known is not None and str(known).strip():
                if str(known)!=str(creator_id):continue
            elif str(item.get('channel') or '').strip().casefold()==str(name).strip().casefold():name_matches+=1
            else:continue
            rows.append(item)
        title=str(name)+' · 媒体库';self.display_rows(title,rows,loading=True,query=query)
        self.rows_count.set_text(f'{len(rows)} 项')
        back=button('← 返回关注',lambda *_:self.show_discovery('follow',getattr(self,'creator_follow_snapshot',None)));self.content.pack_start(back,False,False,0);self.content.reorder_child(back,0);back.show()
        note=label('仅显示本机媒体库内容（含未下载的条目）。'+('其中 '+str(name_matches)+' 项按名称匹配，可能包含同名作者。' if name_matches else ''),'muted')
        note.set_line_wrap(True);self.content.pack_start(note,False,False,0);self.content.reorder_child(note,2);note.show()
        if not rows:
            empty=label('媒体库中暂无匹配的内容。','muted');empty.set_halign(Gtk.Align.START);self.content.pack_start(empty,False,False,0);empty.show()

    def open_row(self,idx):
        if self.player:self.player.close();self.player=None
        self.theater=False;self.row_index=idx;item=self.rows[idx];mid=item.get('id');self.detail_media_id=mid;fresh=self.store.get(mid) if mid else None
        if fresh:item={**item,**fresh}
        if getattr(self,'rows_box',None) and self.rows_box.get_toplevel() is self:
            self.navigation_matches=[child.row_index for child in self.rows_box.get_children() if child.get_child_visible()]
        matches=getattr(self,'navigation_matches',list(range(len(self.rows))));position=matches.index(idx) if idx in matches else -1
        self.clear_content();nav=Gtk.Box(spacing=8);self.detail_nav=nav;nav.pack_start(button('← 返回列表',lambda *_:self.return_rows()),False,False,0)
        prev=icon_button('go-previous-symbolic','上一条',lambda *_:self.open_row(matches[position-1]));prev.set_sensitive(position>0);nxt=icon_button('go-next-symbolic','下一条',lambda *_:self.open_row(matches[position+1]));nxt.set_sensitive(0<=position<len(matches)-1);nav.pack_end(nxt,False,False,0);nav.pack_end(prev,False,False,0);self.content.pack_start(nav,False,False,0)
        content=Gtk.Box(spacing=20);left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);content.pack_start(left,True,True,0)
        if item.get('source')=='podcast' and item.get('url'):
            from urllib.parse import urlparse
            try:host=urlparse(item['url']).hostname or '未知'
            except ValueError:host='未知'
            left.pack_start(label('媒体来源：'+host,'muted'),False,False,0)
        self.player_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);self.player_box.set_size_request(360,270);self.player_box.get_style_context().add_class('card');self.placeholder=MediaCover();self.player_box.pack_start(self.placeholder,True,True,0);
        if item.get('thumbnail') and item.get('source')!='podcast':
            if self.source_kind=='creator-local':self.load_cached_art(self.placeholder,item['thumbnail'])
            else:self.load_art(self.placeholder,item['thumbnail'])
        left.pack_start(self.player_box,False,False,0)
        row=Gtk.Box(spacing=7)
        local=bool(item.get('path') and Path(item['path']).is_file())
        if local or (item.get('url') and not item.get('unavailable')):
            self.start_button=Gtk.Button();self.start_button.set_image(Gtk.Image.new_from_icon_name('media-playback-start-symbolic',Gtk.IconSize.BUTTON));hint='播放本地文件' if local else '在线播放';self.start_button.set_tooltip_text(hint);self.start_button.get_accessible().set_name(hint);self.start_button.get_style_context().add_class('suggested-action');self.start_button.connect('clicked',lambda b:self.open_preferred(item,b));row.pack_start(self.start_button,False,False,0)
            if local and item.get('unavailable'):row.pack_start(label('来源已失效','muted'),False,False,0)
        else:row.pack_start(label('来源视频已失效，无法在线播放或下载' if item.get('unavailable') else '本地文件尚未下载或暂不可用','muted'),False,False,0)
        self.theater_button=icon_button('video-display-symbolic','影院模式',self.toggle_theater);self.fullscreen_button=icon_button('view-fullscreen-symbolic','全屏',self.toggle_fullscreen);row.pack_end(self.fullscreen_button,False,False,0);row.pack_end(self.theater_button,False,False,0);self.mode_row=row;self.control_row=Gtk.EventBox();self.control_row.add(row);self.player_box.pack_start(self.control_row,False,False,0)
        self.detail_left=left
        origin={'local':'本地文件','youtube':'YouTube','bilibili':'B 站','podcast':'播客'}.get(item.get('source'),'其他来源');left.pack_start(label(item.get('title',''),'title'),False,False,0);left.pack_start(label(' · '.join(x for x in (item.get('channel'),origin) if x),'muted'),False,False,0);meta=label(' · '.join(str(x) for x in (item.get('published'),f"{int(item['duration']//60)}:{int(item['duration']%60):02d}" if item.get('duration') else None) if x) or '时间和时长暂无资料','muted');left.pack_start(meta,False,False,0);left.pack_start(label(item.get('description') or '没有可用的原始简介。'),False,False,0)
        if item.get('url'):
            source=Gtk.LinkButton.new_with_label(item['url'],'查看来源');source.set_halign(Gtk.Align.START);left.pack_start(source,False,False,0)
        right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);self.detail_right=right;right.set_size_request(160,-1);right.pack_start(label('内容操作','section'),False,False,0)
        if item.get('url') and not item.get('unavailable'):
            right.pack_start(button('下载',lambda *_:self.prepare_download(item),True),False,False,0)
            right.pack_start(button('更多格式',lambda *_:self.inspect_and_download(item['url'],True)),False,False,0)
            if local:right.pack_start(button('在线播放',lambda b:self.open_online(item,b)),False,False,0)
        if item.get('path') and Path(item['path']).is_file():right.pack_start(button('打开所在目录',lambda *_:self.open_local(Path(item['path']).parent)),False,False,0)
        if mid:right.pack_start(button('管理所属列表',lambda *_:self.choose_collection(item)),False,False,0)
        content.pack_start(right,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(content);self.content.pack_start(scroll,True,True,0)
        def adapt_detail(_,allocation):
            orientation=Gtk.Orientation.VERTICAL if allocation.width<680 else Gtk.Orientation.HORIZONTAL
            if content.get_orientation()!=orientation:
                GLib.idle_add(lambda:(content.set_orientation(orientation),False)[1])
        scroll.connect('size-allocate',adapt_detail);self.content.show_all()
        if item.get('path') and Path(item['path']).is_file():
            generation=self.view_generation
            def show_info(info):
                if generation==self.view_generation:meta.set_text(' · '.join(x for x in (item.get('published'),info) if x))
                return False
            async_call(lambda:local_media_info(item['path']),show_info,lambda _:False)

    def return_rows(self):
        if self.source_kind=='xiaoyuzhou-video':self.return_imported_programs(getattr(self,'xiaoyuzhou_context',None))
        elif self.source_kind=='creator-local':self.open_creator(*self.creator_ref,query=self.rows_query)
        elif getattr(self,'active_nav','').startswith('collection:'):self.show_library(int(self.active_nav.split(':',1)[1]),self.rows_query)
        elif getattr(self,'active_nav','')=='library':self.show_library(query=self.rows_query)
        else:self.display_rows(self.rows_title,self.rows,query=self.rows_query)

    def open_player(self,path,stream=None):
        try:
            self.play_request+=1;self.playing_online=stream is not None
            if not self.player:
                focus_playback=self.get_focus() is self.start_button
                player=Player(self.store.setting('volume',100),lambda value:self.store.set_setting('volume',value),self.player_state);player.toggle.get_style_context().add_class('suggested-action');self.player_box.remove(self.placeholder)
                self.mode_row.remove(self.theater_button);self.mode_row.remove(self.fullscreen_button)
                player.controls.pack_start(self.theater_button,False,False,0);player.controls.pack_start(self.fullscreen_button,False,False,0)
                self.player_box.remove(self.control_row);self.player=player;self.player_box.pack_start(player,True,True,0);self.player_box.show_all()
                if focus_playback:player.toggle.grab_focus()
            if stream:self.online_resolution=str(stream.get('resolution') or '')[:40];self.player.open_stream(stream['url'],stream['user_agent'],stream.get('audio_url',''),stream.get('referer',''));self.message('正在缓冲在线播放…')
            else:self.player.open(path);self.message('播放中')
        except Exception as e:self.fail(str(e))

    def open_preferred(self,item,control):
        try:fresh=self.store.get(item['id']) if item.get('id') else None
        except Exception:self.fail('无法读取媒体库状态');return
        if fresh:item={**item,**fresh}
        path=item.get('path')
        if path and Path(path).is_file():self.open_player(path)
        elif item.get('url') and not item.get('unavailable'):self.open_online(item,control)
        else:self.fail('本地文件不可用，来源也无法播放')

    def playback_cookies(self,url):
        if self.store.setting('bilibili_cookies',False) and self.store.setting('bilibili_auth_source','chrome')=='qr':
            try:
                if identify_url(url).get('source')=='bilibili':return 'bilibili_qr'
            except ValueError:pass
        return self.store.setting('cookies',False)

    def open_online(self,item,control):
        self.play_request+=1;request=self.play_request;generation=self.view_generation;control.set_sensitive(False);self.message('正在获取在线播放地址…')
        def done(stream):
            if generation==self.view_generation:
                control.set_sensitive(True)
                if request==self.play_request:self.open_player(None,stream)
            return False
        def failed(error):
            if generation==self.view_generation:
                control.set_sensitive(True)
                if request==self.play_request:self.fail('在线播放失败：'+error)
            return False
        async_call(lambda:downloader.online_stream(item['url'],self.playback_cookies(item['url'])),done,failed)

    def player_state(self,state):
        if not self.playing_online:return
        if state in (1,2):self.message('正在缓冲在线播放…')
        elif state==3:self.message('在线播放中'+(' · '+self.online_resolution if self.online_resolution else ''))
        elif state==4:self.message('在线播放已暂停')
        elif state==6:self.message('播放完成')
        elif state==7:
            generation=self.view_generation;idx=self.row_index
            def reset():
                if generation==self.view_generation:self.open_row(idx);self.fail('在线播放失败，可重试或打开来源网站')
                return False
            GLib.idle_add(reset)

    def toggle_theater(self,*_):
        self.theater=not self.theater;self.side.set_visible(not self.theater and not self.fullscreened);self.detail_right.set_visible(not self.theater and not self.fullscreened);set_button_icon(self.theater_button,'video-display-symbolic','退出影院模式' if self.theater else '影院模式');self.player_box.set_size_request(360,450 if self.theater else 270)

    def toggle_fullscreen(self,*_):
        self.fullscreened=not self.fullscreened
        set_button_icon(self.fullscreen_button,'view-restore-symbolic' if self.fullscreened else 'view-fullscreen-symbolic','退出全屏' if self.fullscreened else '全屏')
        show=not self.fullscreened
        self.side.set_visible(show and not self.theater);self.detail_right.set_visible(show and not self.theater);self.detail_nav.set_visible(show);self.header.set_visible(show);self.footer.set_visible(show)
        for child in self.detail_left.get_children():
            if child not in (self.player_box,self.control_row):child.set_visible(show)
        self.detail_left.set_child_packing(self.player_box,self.fullscreened,self.fullscreened,0,Gtk.PackType.START)
        if self.fullscreened:self.fullscreen()
        else:self.unfullscreen()

    def on_key(self,_,event):
        if event.keyval==Gdk.KEY_Escape and self.fullscreened:self.toggle_fullscreen();return True
        key=self.store.setting('playback_shortcut','space')
        keyval={'space':Gdk.KEY_space,'k':Gdk.KEY_k}.get(key)
        if not keyval or Gdk.keyval_to_lower(event.keyval)!=keyval:return False
        if event.state & (Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.MOD1_MASK|Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.SHIFT_MASK):return False
        if not self.player or self.player.closed:return False
        focused=self.get_focus()
        if isinstance(focused,(Gtk.Editable,Gtk.TextView,Gtk.ComboBox,Gtk.Range)) or (isinstance(focused,Gtk.Button) and focused is not self.player.toggle):return False
        if self.shortcut_release_source:GLib.source_remove(self.shortcut_release_source);self.shortcut_release_source=0
        if not self.shortcut_pressed:self.shortcut_pressed=True;self.player.toggle.clicked()
        return True

    def on_key_release(self,_,event):
        key=self.store.setting('playback_shortcut','space')
        if self.shortcut_pressed and Gdk.keyval_to_lower(event.keyval)=={'space':Gdk.KEY_space,'k':Gdk.KEY_k}.get(key):
            if self.shortcut_release_source:GLib.source_remove(self.shortcut_release_source)
            self.shortcut_release_source=GLib.timeout_add(100,self.shortcut_released)
            return True
        return False

    def shortcut_released(self):
        self.shortcut_release_source=0;return self.reset_shortcut()

    def reset_shortcut(self,*_):
        if self.shortcut_release_source:GLib.source_remove(self.shortcut_release_source);self.shortcut_release_source=0
        self.shortcut_pressed=False
        return False

    def prompt(self,title,placeholder='',value=''):
        dialog=Gtk.Dialog(title=title,transient_for=self,flags=Gtk.DialogFlags.MODAL);dialog.add_button('取消',Gtk.ResponseType.CANCEL);dialog.add_button('确定',Gtk.ResponseType.OK);entry=Gtk.Entry();entry.set_placeholder_text(placeholder);entry.set_text(value);dialog.get_content_area().pack_start(entry,False,False,15);dialog.show_all();response=dialog.run();value=entry.get_text();dialog.destroy();return value if response==Gtk.ResponseType.OK else None

    def new_collection(self,*_):
        value=self.prompt('新建主题列表','例如：羽毛球')
        if value is not None:
            try:self.store.add_collection(value);self.refresh_collections();self.message('列表已创建')
            except Exception as e:self.fail(str(e))

    def choose_collection(self,item):
        mid=item.get('id');collections=self.store.collections()
        if not mid:self.fail('请先保存内容');return
        if not collections:self.fail('请先创建主题列表');return
        d=Gtk.Dialog(title='管理所属列表',transient_for=self,flags=Gtk.DialogFlags.MODAL);d.add_button('取消',Gtk.ResponseType.CANCEL);d.add_button('保存',Gtk.ResponseType.OK);area=d.get_content_area();area.set_border_width(16);area.set_spacing(8);area.pack_start(label('勾选要加入的列表；取消勾选可移出。','muted'),False,False,0)
        selected=self.store.media_collections(mid);checks=[]
        for x in collections:
            cb=Gtk.CheckButton(label=x['name']);cb.set_active(x['id'] in selected);area.pack_start(cb,False,False,0);checks.append((cb,x['id']))
        d.show_all();res=d.run();chosen=[cid for cb,cid in checks if cb.get_active()];d.destroy()
        if res==Gtk.ResponseType.OK:
            try:self.store.set_media_collections(mid,chosen);self.message('所属列表已更新')
            except ValueError as exc:self.fail(str(exc))

    def show_podcasts(self):
        self.clear_content();self.content.pack_start(page_heading('播客'),False,False,0)
        self.content.pack_start(button('小宇宙 OPML 导入与 YouTube 匹配',lambda *_:self.show_xiaoyuzhou()),False,False,0)
        self.content.pack_start(button('Apple Podcasts 文件导入与 YouTube 匹配',lambda *_:self.show_apple_podcasts()),False,False,0)
        self.content.pack_start(label('搜索 Apple 公开节目，或粘贴 Apple 节目链接 / RSS 地址。查询会连接对应服务。'),False,False,0)
        row=Gtk.Box(spacing=8);entry=Gtk.Entry();entry.set_placeholder_text('节目名称、Apple 节目链接或 RSS 地址');entry.set_hexpand(True);row.pack_start(entry,True,True,0)
        row.pack_start(button('搜索或打开',lambda *_:self.podcast_query(entry.get_text().strip()),True),False,False,0);entry.connect('activate',lambda *_:self.podcast_query(entry.get_text().strip()));self.content.pack_start(row,False,False,0)
        self.podcast_status=label('输入节目名称搜索，或打开公开订阅地址。');self.content.pack_start(self.podcast_status,False,False,0)
        self.podcast_notice=label('','muted');self.content.pack_start(self.podcast_notice,False,False,0)
        self.podcast_results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(self.podcast_results);self.content.pack_start(scroll,True,True,0);self.content.show_all();self.podcast_entry=entry

    def xiaoyuzhou_programs(self):
        values=self.store.setting('xiaoyuzhou_programs',[])
        if not isinstance(values,list) or any(not isinstance(x,dict) or not isinstance(x.get('feed_url'),str) or not isinstance(x.get('title'),str) for x in values):
            raise ValueError('本地小宇宙节目数据损坏，未覆盖；请先备份设置并检查')
        return values

    @staticmethod
    def imported_program_key(program):
        return program.get('program_id') or program.get('feed_url')

    def imported_programs(self):
        if getattr(self,'import_source','xiaoyuzhou')!='apple-podcasts':return self.xiaoyuzhou_programs()
        values=self.store.setting('apple_podcast_programs',[])
        if not isinstance(values,list) or any(not isinstance(x,dict) or not isinstance(x.get('program_id'),str) or not x.get('program_id') or not isinstance(x.get('title'),str) for x in values):
            raise ValueError('本地 Apple Podcasts 节目数据损坏，未覆盖；请先备份设置并检查')
        return values

    def save_imported_programs(self,programs):
        self.store.set_setting('apple_podcast_programs' if getattr(self,'import_source','xiaoyuzhou')=='apple-podcasts' else 'xiaoyuzhou_programs',programs)

    @staticmethod
    def imported_program_back_label(program):
        return '← 返回 Apple Podcasts 节目列表' if program and program.get('source')=='apple-podcasts' else '← 返回小宇宙节目列表'

    def return_imported_programs(self,program):
        if program and program.get('source')=='apple-podcasts':self.show_apple_podcasts()
        else:self.show_xiaoyuzhou()

    def show_apple_podcasts(self):
        self.show_xiaoyuzhou('apple-podcasts')

    def choose_apple_podcast_file(self):
        self.choose_xiaoyuzhou_opml(apple=True)

    def import_apple_podcast_file(self,path):
        from . import apple_podcast_import
        generation=self.view_generation;self.apple_import_request=getattr(self,'apple_import_request',0)+1;request=self.apple_import_request
        self.xiaoyuzhou_status.get_style_context().remove_class('job-failed')
        self.xiaoyuzhou_status.set_text('正在本机读取订阅文件…')
        def failed(error):
            if generation==self.view_generation and request==self.apple_import_request:
                self.xiaoyuzhou_status.get_style_context().add_class('job-failed')
                self.xiaoyuzhou_status.set_text('导入失败：'+error+'；原有节目保留。')
            return False
        def done(result):
            if request!=self.apple_import_request:return False
            try:
                # Persist to Apple storage even if the user left this page while reading.
                existing=self.store.setting('apple_podcast_programs',[])
                if not isinstance(existing,list) or any(not isinstance(x,dict) or not isinstance(x.get('program_id'),str) or not x.get('program_id') or not isinstance(x.get('title'),str) for x in existing):raise ValueError('本地 Apple Podcasts 节目数据损坏，未覆盖')
                by_id={x['program_id']:x for x in existing}
                conflicts=0
                for entry in result['entries']:
                    identity=entry['program_id'];previous=by_id.get(identity,{})
                    same_name=[x for x in existing if not x.get('feed_url') and x['title']==entry['title']]
                    if not entry.get('feed_url') and same_name:
                        # A title/ordinal cannot prove which subscription owns an old match.
                        conflicts+=1;suffix=1;base=identity
                        while identity in by_id:identity=base+':import-'+str(suffix);suffix+=1
                        entry={**entry,'program_id':identity,'name_conflict':True,'identity_ambiguous':True};previous={}
                    by_id[identity]={**previous,**entry,'source':'apple-podcasts'}
                programs=list(by_id.values());self.store.set_setting('apple_podcast_programs',programs)
                text=f"导入完成：本机共 {len(programs)} 个 Apple Podcasts 节目；已确认匹配和缺席节目已保留。跳过 {result.get('skipped',0)} 项，重复 {result.get('duplicates',0)} 项。"
                if result.get('issues'):text+=' 部分条目无效或身份冲突，请检查导出文件。'
                if conflicts:text+=' 无地址同名条目无法核实身份：旧记录保留，新记录需重新确认匹配。'
                if generation==self.view_generation:self.render_xiaoyuzhou(programs);self.xiaoyuzhou_status.set_text(text)
                self.message(text)
            except Exception as exc:failed(str(exc))
            return False
        def read_local():
            try:return apple_podcast_import.read_import(path)
            except OSError:raise ValueError('文件不存在或无法读取，请重新选择') from None
            except ValueError as exc:
                if str(exc)=='无法解析 OPML 文件':raise ValueError('文件格式无法解析；可重新导出并检查节目名或地址中的特殊字符') from None
                raise
        async_call(read_local,done,failed)

    def show_xiaoyuzhou(self,source='xiaoyuzhou'):
        self.import_source=source;apple=source=='apple-podcasts'
        self.clear_content();self.xiaoyuzhou_context=None;self.source_kind=source;self.select_nav('podcasts')
        self.content.pack_start(page_heading('Apple Podcasts' if apple else '小宇宙'),False,False,0)
        guidance=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10) if apple else self.content
        guidance.pack_start(label('在 iPhone 用快捷指令导出 OPML，再传到本机选择；快捷指令可能随 iOS 版本变化，可能缺失无 RSS 节目，请核对节目数量。手动再次导入更新，缺席节目不会删除；无 RSS 的同名记录会另存为待核对条目，避免复用错误匹配。文件仅在本机读取，不连接 Apple 账号。' if apple else '从小宇宙导出 OPML 后选择文件；订阅更新需手动再次导入；导出可能不完整，缺席节目不会删除。文件仅在本机读取。','muted'),False,False,0)
        if apple:
            shortcut=Gtk.LinkButton.new_with_label('https://www.icloud.com/shortcuts/5e49239698c44e92baf94399df86b3f9','查看第三方导出快捷指令');shortcut.set_halign(Gtk.Align.START);guidance.pack_start(shortcut,False,False,0)
            guidance.pack_start(label('在 iPhone 打开后可先查看操作再添加；运行时选择“保存到文件”，再把 OPML 传到本机。当前 iOS 实测待验证。','muted'),False,False,0)
        guidance.pack_start(label('点击查找才会把该节目名称发送给 YouTube。候选需要你确认，不会自动匹配或自动同步。','muted'),False,False,0)
        row=Gtk.Box(spacing=8);row.pack_start(button('选择 OPML 文件',lambda *_:self.choose_apple_podcast_file() if apple else self.choose_xiaoyuzhou_opml(),True),False,False,0);row.pack_start(button('返回播客',lambda *_:self.show_podcasts()),False,False,0);self.content.pack_start(row,False,False,0)
        self.xiaoyuzhou_status=label('正在读取本机节目…','muted');self.content.pack_start(self.xiaoyuzhou_status,False,False,0)
        self.xiaoyuzhou_results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        if apple:
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);body.pack_start(guidance,False,False,0);body.pack_start(self.xiaoyuzhou_results,False,False,0);scroll.add(body)
        else:scroll.add(self.xiaoyuzhou_results)
        self.xiaoyuzhou_scroll=scroll;self.content.pack_start(scroll,True,True,0)
        try:self.render_xiaoyuzhou(self.imported_programs())
        except ValueError as exc:self.xiaoyuzhou_status.set_text(str(exc))
        self.content.show_all()
        generation=self.view_generation
        def restore_scroll():
            if generation==self.view_generation:self.xiaoyuzhou_scroll.get_vadjustment().set_value(getattr(self,'xiaoyuzhou_scroll_value',0))
            return False
        GLib.idle_add(restore_scroll)

    def choose_xiaoyuzhou_opml(self,apple=False):
        dialog=Gtk.FileChooserDialog(title='选择 Apple Podcasts OPML 文件' if apple else '选择小宇宙 OPML 文件',transient_for=self,action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'导入',Gtk.ResponseType.OK)
        dialog.set_name('xiaoyuzhou-opml-chooser')
        selection=label('尚未选择文件','muted');selection.set_max_width_chars(55);dialog.set_extra_widget(selection)
        selection.show();dialog.set_response_sensitive(Gtk.ResponseType.OK,False)
        def selected(chooser):
            path=chooser.get_filename();valid=bool(path and Path(path).is_file())
            selection.set_text('已选文件：'+Path(path).name if valid else '尚未选择文件')
            chooser.set_response_sensitive(Gtk.ResponseType.OK,valid)
        dialog.connect('selection-changed',selected)
        provider=Gtk.CssProvider();provider.load_from_data(b'#xiaoyuzhou-opml-chooser treeview:selected, #xiaoyuzhou-opml-chooser treeview:selected:focus {background-color:#247f78;color:#ffffff;}')
        Gtk.StyleContext.add_provider_for_screen(dialog.get_screen(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        file_filter=Gtk.FileFilter();file_filter.set_name('OPML 文件');file_filter.add_pattern('*.opml');file_filter.add_pattern('*.xml');dialog.add_filter(file_filter)
        response=dialog.run();path=dialog.get_filename();dialog.destroy();Gtk.StyleContext.remove_provider_for_screen(self.get_screen(),provider)
        if response==Gtk.ResponseType.OK and path:
            if apple:self.import_apple_podcast_file(path)
            else:self.import_xiaoyuzhou_opml(path)

    def import_xiaoyuzhou_opml(self,path):
        from . import xiaoyuzhou_import
        generation=self.view_generation;self.xiaoyuzhou_import_request=getattr(self,'xiaoyuzhou_import_request',0)+1;request=self.xiaoyuzhou_import_request
        self.xiaoyuzhou_status.set_text('正在本机读取 OPML…')
        def done(result):
            if request!=self.xiaoyuzhou_import_request:return False
            try:
                existing=self.xiaoyuzhou_programs();by_url={x['feed_url']:x for x in existing}
                for entry in result['entries']:
                    previous=by_url.get(entry['feed_url'],{});by_url[entry['feed_url']]={**previous,**entry}
                programs=list(by_url.values());self.store.set_setting('xiaoyuzhou_programs',programs)
                text=f"导入完成：本机共 {len(programs)} 个节目；已确认选择已保留。跳过 {result.get('skipped',0)} 项，重复 {result.get('duplicates',0)} 项。"
                if result.get('issues'):text+=' 部分条目无效，请检查导出文件。'
                if generation==self.view_generation:self.render_xiaoyuzhou(programs);self.xiaoyuzhou_status.set_text(text)
                self.message(text)
            except Exception as exc:failed(str(exc))
            return False
        def failed(error):
            if generation==self.view_generation and request==self.xiaoyuzhou_import_request:self.xiaoyuzhou_status.set_text('导入失败：'+error+'；原有节目保留。')
            return False
        def read_local():
            try:return xiaoyuzhou_import.read_opml(path)
            except OSError:raise ValueError('文件不存在或无法读取，请重新选择') from None
        async_call(read_local,done,failed)

    def render_xiaoyuzhou(self,programs):
        self.xiaoyuzhou_cards={}
        for child in self.xiaoyuzhou_results.get_children():self.xiaoyuzhou_results.remove(child)
        self.xiaoyuzhou_status.get_style_context().remove_class('job-failed')
        self.xiaoyuzhou_status.set_text(f'本机 {len(programs)} 个节目' if programs else '尚未导入节目。')
        for local_index,program in enumerate(programs,1):
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);card.get_style_context().add_class('card')
            title_button=button(program['title'],lambda _,p=program:self.open_xiaoyuzhou_program(p))
            title_button.get_child().set_line_wrap(True);title_button.get_child().set_max_width_chars(45);title_button.set_tooltip_text(program['title']);title_button.get_accessible().set_name('查看节目：'+program['title'])
            card.pack_start(title_button,False,False,0)
            match=program.get('match');status=label(('来源：Apple Podcasts · '+(f'本地条目 #{local_index}（非节目身份） · ' if not program.get('feed_url') else '')+('同名身份无法核实 · ' if program.get('name_conflict') else '无 RSS，仅按名称记录 · ' if program.get('identity_ambiguous') else '') if program.get('source')=='apple-podcasts' else '')+('已确认：'+match.get('title','') if isinstance(match,dict) and match.get('confirmed') else '尚未确认 YouTube 匹配'),'muted');card.pack_start(status,False,False,0)
            actions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);actions.set_halign(Gtk.Align.START);search=button('查找 YouTube 候选',lambda _,p=program:self.search_xiaoyuzhou(p));actions.pack_start(search,False,False,0)
            if isinstance(match,dict):actions.pack_start(button('在浏览器打开已确认结果',lambda _,m=match:self.open_xiaoyuzhou_match(m)),False,False,0)
            if isinstance(match,dict) and match.get('confirmed'):actions.pack_start(button('在 MediaDesk 查看',lambda _,p=program:self.open_xiaoyuzhou_program(p),True),False,False,0)
            card.pack_start(actions,False,False,0);self.xiaoyuzhou_results.pack_start(card,False,False,0);self.xiaoyuzhou_cards[self.imported_program_key(program)]=card
        self.xiaoyuzhou_results.show_all()

    def search_xiaoyuzhou(self,program):
        self.xiaoyuzhou_open_request=getattr(self,'xiaoyuzhou_open_request',0)+1
        from . import xiaoyuzhou_import
        if not self.store.setting('youtube_account_enabled',True):
            self.xiaoyuzhou_status.set_text('YouTube 已断开，请在设置中连接账号后再查找。');return
        generation=self.view_generation;self.xiaoyuzhou_search_request=getattr(self,'xiaoyuzhou_search_request',0)+1;request=self.xiaoyuzhou_search_request
        self.xiaoyuzhou_status.set_text('正在 YouTube 查找：'+program['title'])
        def done(result):
            if generation!=self.view_generation or request!=self.xiaoyuzhou_search_request:return False
            candidates=result['candidates']
            self.render_xiaoyuzhou(self.imported_programs());self.xiaoyuzhou_status.set_text(f"{program['title']}：{len(candidates)} 个候选，请核对后确认。" if candidates else '未找到候选；可重试或保留未匹配状态。')
            owner=self.xiaoyuzhou_cards.get(self.imported_program_key(program))
            if owner is None:return False
            owner.pack_start(label('候选所属节目：'+program['title'],'section'),False,False,0)
            for candidate in candidates:
                row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);row.get_style_context().add_class('card')
                row.pack_start(label(candidate.get('title') or '未命名候选'),False,False,0);row.pack_start(label({'channel':'频道','playlist':'播放列表','video':'单集 / 视频'}.get(candidate.get('kind'),'候选')+' · '+candidate.get('channel','')+' · 官方归属未验证','muted'),False,False,0)
                row.pack_start(label(candidate['url'],'muted'),False,False,0);actions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);actions.set_halign(Gtk.Align.START)
                actions.pack_start(button('浏览器预览',lambda _,c=candidate:self.open_xiaoyuzhou_match(c)),False,False,0)
                actions.pack_start(button('确认此匹配',lambda _,c=candidate:self.confirm_xiaoyuzhou_match(program,c)),False,False,0);row.pack_start(actions,False,False,0);owner.pack_start(row,False,False,0)
            self.xiaoyuzhou_results.show_all();return False
        def failed(error):
            if generation==self.view_generation and request==self.xiaoyuzhou_search_request:self.xiaoyuzhou_status.set_text('查找失败：'+error+'；可重试，已确认选择保留。')
            return False
        async_call(lambda:xiaoyuzhou_import.search_youtube_candidates(program['title'],user_triggered=True),done,failed)

    def confirm_xiaoyuzhou_match(self,program,candidate):
        try:
            programs=self.imported_programs();entry=next(x for x in programs if self.imported_program_key(x)==self.imported_program_key(program));entry['match']={**candidate,'confirmed':True};self.save_imported_programs(programs)
            self.render_xiaoyuzhou(programs);self.xiaoyuzhou_status.set_text('已确认：'+candidate.get('title','')+'；可在 MediaDesk 查看、播放或下载。')
        except Exception as exc:self.xiaoyuzhou_status.set_text('保存匹配失败：'+str(exc))

    def open_xiaoyuzhou_program(self,program):
        match=program.get('match')
        if not isinstance(match,dict) or not match.get('confirmed'):
            self.search_xiaoyuzhou(program);return
        self.xiaoyuzhou_scroll_value=self.xiaoyuzhou_scroll.get_vadjustment().get_value()
        self.use_xiaoyuzhou_match(match,program)

    def use_xiaoyuzhou_match(self,candidate,program=None):
        if not candidate.get('confirmed'):return
        self.xiaoyuzhou_open_request=getattr(self,'xiaoyuzhou_open_request',0)+1;request=self.xiaoyuzhou_open_request
        if candidate.get('kind')=='video':
            if program is None:
                self.podcast_add({'title':candidate.get('title') or 'YouTube 视频','channel':candidate.get('channel',''),'url':candidate['url'],'source':'youtube','source_id':candidate.get('source_id','')});return
            try:
                mid=self.store.save_source({'title':candidate.get('title') or program['title'],'channel':candidate.get('channel',''),'url':candidate['url'],'source':'youtube','source_id':candidate.get('source_id','')})
                self.xiaoyuzhou_context=program;self.source_kind='xiaoyuzhou-video';self.rows=[self.store.get(mid)];self.rows_title=program['title']+' · YouTube 单集';self.rows_query='';self.navigation_matches=[0];self.open_row(0)
                self.detail_nav.get_children()[0].set_label(self.imported_program_back_label(program))
                heading=label(program['title']+' · YouTube 单集','section');heading.set_max_width_chars(55);self.content.pack_start(heading,False,False,0);self.content.reorder_child(heading,1);heading.show()
            except Exception as exc:self.xiaoyuzhou_status.set_text('读取单集失败：'+str(exc))
            return
        if not self.store.setting('youtube_account_enabled',True):
            self.xiaoyuzhou_status.set_text('YouTube 已断开，请在设置中连接账号后再查看。');return
        if candidate.get('kind')=='playlist':self.load_source('playlist-items',candidate['source_id'],**({'program':program} if program else {}));return
        if candidate.get('kind')!='channel':return
        from . import xiaoyuzhou_import
        generation=self.view_generation;self.xiaoyuzhou_status.set_text('正在读取已确认频道的上传列表…')
        def done(playlist_id):
            if generation==self.view_generation and request==self.xiaoyuzhou_open_request:self.load_source('playlist-items',playlist_id,**({'program':program} if program else {}))
            return False
        def failed(error):
            if generation==self.view_generation and request==self.xiaoyuzhou_open_request:self.xiaoyuzhou_status.set_text('读取频道失败：'+error+'；可重试。')
            return False
        async_call(lambda:xiaoyuzhou_import.resolve_channel_uploads(candidate['source_id'],user_triggered=True),done,failed)

    def open_xiaoyuzhou_match(self,candidate):
        from urllib.parse import urlparse
        url=candidate.get('url','');parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.hostname not in ('www.youtube.com','youtube.com','youtu.be') or parsed.username or parsed.password:
            self.xiaoyuzhou_status.set_text('无法打开：不是有效的 YouTube HTTPS 地址。');return
        try:Gio.AppInfo.launch_default_for_uri(url,None);self.xiaoyuzhou_status.set_text('已交给浏览器打开 YouTube；频道、播放列表或单集均在浏览器查看。')
        except Exception as exc:self.xiaoyuzhou_status.set_text('打开失败：'+str(exc))

    def podcast_query(self,query):
        if not query:self.podcast_status.set_text('请输入节目名称或链接。');return
        generation=self.view_generation;self.podcast_request=getattr(self,'podcast_request',0)+1;request=self.podcast_request
        for child in self.podcast_results.get_children():self.podcast_results.remove(child)
        self.podcast_status.set_text('正在读取…');self.podcast_notice.set_text('')
        def fetch():
            from . import podcasts
            return podcasts.read_feed(query) if query.startswith(('http://','https://')) else podcasts.search(query)
        def done(result):
            if generation!=self.view_generation or request!=self.podcast_request:return False
            if isinstance(result,dict):
                episodes=result.get('episodes',[]);notice=result.get('notice') or ''
                self.podcast_status.set_text(f"{result.get('title') or '节目'} · {len(episodes)} 集");self.podcast_notice.set_text(notice)
                for episode in episodes:
                    row=Gtk.Box(spacing=10);row.set_margin_top(6);row.set_margin_bottom(6);title=label(episode.get('title') or '未命名单集');title.set_max_width_chars(60);row.pack_start(title,True,True,0)
                    row.pack_end(button('加入并查看',lambda _,item=episode:self.podcast_add(item)),False,False,0);self.podcast_results.pack_start(row,False,False,0);self.podcast_results.pack_start(Gtk.Separator(),False,False,0)
                if not episodes:self.podcast_status.set_text(self.podcast_status.get_text()+' · 暂无可用单集')
            else:
                self.podcast_status.set_text(f'找到 {len(result)} 个节目' if result else '没有找到节目，请尝试其他名称。')
                for item in result:
                    row=Gtk.Box(spacing=10);row.set_margin_top(6);row.set_margin_bottom(6);description=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3);description.pack_start(label(item.get('title') or '未命名节目'),False,False,0);description.pack_start(label(item.get('channel') or '','muted'),False,False,0);row.pack_start(description,True,True,0)
                    row.pack_end(button('查看单集',lambda _,i=item:self.podcast_query(i.get('feed_url') or i.get('url') or '')),False,False,0);self.podcast_results.pack_start(row,False,False,0);self.podcast_results.pack_start(Gtk.Separator(),False,False,0)
            self.podcast_results.show_all();return False
        def failed(error):
            if generation==self.view_generation and request==self.podcast_request:self.podcast_status.set_text('读取失败：'+error+'。请检查地址或网络后重试。')
            return False
        async_call(fetch,done,failed)

    def podcast_add(self,item):
        try:mid=self.store.save_source(item)
        except Exception as exc:self.podcast_status.set_text('加入失败：'+str(exc));return
        self.show_library();idx=next((i for i,row in enumerate(self.rows) if row['id']==mid),None)
        if idx is not None:self.open_row(idx);self.message('已加入媒体库，可播放或下载')
        else:self.message('已加入媒体库')

    def add_url(self,*_):
        d=Gtk.Dialog(title='添加视频链接',transient_for=self,flags=Gtk.DialogFlags.MODAL);d.add_button('取消',Gtk.ResponseType.CANCEL);d.add_button('仅加入媒体库',Gtk.ResponseType.APPLY);d.add_button('在线播放',Gtk.ResponseType.YES);d.add_button('下载',Gtk.ResponseType.OK)
        area=d.get_content_area();area.set_border_width(16);entry=Gtk.Entry();entry.set_width_chars(48);entry.set_placeholder_text('粘贴 YouTube 或 B 站 BV 视频链接');entry.set_activates_default(True);area.pack_start(entry,False,False,0);d.set_default_response(Gtk.ResponseType.YES);d.show_all();response=d.run();url=entry.get_text().strip();d.destroy()
        if response not in (Gtk.ResponseType.APPLY,Gtk.ResponseType.YES,Gtk.ResponseType.OK) or not url:return
        try:identify_url(url)
        except ValueError as exc:self.fail(str(exc));return
        if response==Gtk.ResponseType.OK:self.inspect_and_download(url);return
        generation=self.view_generation;online=response==Gtk.ResponseType.YES;self.message('正在获取在线播放地址…' if online else '正在获取视频资料…')
        def fetch():
            stream=downloader.online_stream(url,self.playback_cookies(url)) if online else None
            item=stream['item'] if stream else downloader.inspect(url,self.playback_cookies(url))
            return self.store.save_source(item),stream
        def done(result):
            mid,stream=result
            if generation!=self.view_generation:self.message('视频已加入媒体库；请返回全部内容查看');return False
            self.show_library();idx=next((i for i,row in enumerate(self.rows) if row['id']==mid),None)
            if idx is not None and stream:self.open_row(idx);self.open_player(None,stream)
            else:self.message('视频已加入媒体库')
            return False
        async_call(fetch,done,lambda e:self.fail(('在线播放失败：' if online else '添加失败：')+e))

    def inspect_and_download(self,url,choose=False):
        self.message('正在获取视频资料与格式…')
        def ready(item):
            if choose:return self.format_dialog(item)
            try:
                self.downloader.start(item,self.store.setting('preference','quality'),self.playback_cookies(item['url']));self.message('已按下载偏好加入任务')
            except Exception as e:self.fail(str(e))
            return False
        async_call(lambda:downloader.inspect(url,self.playback_cookies(url)),ready,lambda error:self.retry_message('获取视频资料失败：'+error,lambda:self.inspect_and_download(url,choose)))

    def prepare_download(self,item):self.inspect_and_download(item['url'])

    def format_dialog(self,item):
        d=Gtk.Dialog(title='下载视频',transient_for=self,flags=Gtk.DialogFlags.MODAL);d.add_button('取消',Gtk.ResponseType.CANCEL);d.add_button('下载',Gtk.ResponseType.OK);area=d.get_content_area();area.set_border_width(15);area.set_spacing(8);area.pack_start(label(item['title'],'section'),False,False,0)
        pref=self.store.setting('preference','quality');area.pack_start(label('默认偏好：'+{'quality':'画质优先','size':'文件大小优先','balance':'均衡'}[pref]+'。可展开格式并选择。'),False,False,0)
        exp=Gtk.Expander(label='更多格式');controls=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);combo=Gtk.ComboBoxText();audio=Gtk.ComboBoxText();combo.append('','自动选择');audio.append('','选择音频')
        for f in item['formats']:
            fid=f['format_id'];size=f.get('filesize') or f.get('filesize_approx');estimate='约 ' if not f.get('filesize') and size else '';text=f"{f.get('resolution') or f.get('format_note') or '未知'} · {f.get('ext')} · {f.get('vcodec')} / {f.get('acodec')} · "+(f'{estimate}{size/1048576:.1f} MB' if size else '大小未知')
            combo.append(fid,text)
            if f.get('vcodec') in (None,'none') and f.get('acodec') not in (None,'none'):audio.append(fid,text)
        combo.set_active(0);audio.set_active(0);controls.pack_start(label('视频或音频格式'),False,False,0);controls.pack_start(combo,False,False,0);controls.pack_start(label('仅画面时，选择音频以合并'),False,False,0);controls.pack_start(audio,False,False,0);exp.add(controls);area.pack_start(exp,False,False,0);d.show_all();response=d.run();fmt=combo.get_active_id();aid=audio.get_active_id();d.destroy()
        if response==Gtk.ResponseType.OK:
            try:
                audio_only=False
                if fmt:
                    selected=next(f for f in item['formats'] if f['format_id']==fmt)
                    audio_only=selected.get('vcodec') in (None,'none')
                    if not audio_only and selected.get('acodec') in (None,'none'):
                        if not aid:raise ValueError('仅画面格式需要选择音频进行合并')
                        fmt+='+'+aid
                self.downloader.start(item,pref,self.playback_cookies(item['url']),fmt or None,audio_only);self.message('下载已加入任务')
            except Exception as e:self.fail(str(e))
        return False

    def download_update(self,jid):
        try:
            if not self.downloader.reconcile():raise ValueError('无法保存下载状态，请检查磁盘空间和权限后重新打开下载任务')
            jobs=self.store.jobs()
        except Exception:
            self.download_status.hide();self.fail('无法读取或保存下载状态，请检查磁盘空间和权限');return False
        active=[j for j in jobs if j['state'] in ('等待','下载中')]
        item=next((j for j in active if j['id']==jid),None) or (active[0] if active else next((j for j in jobs if j['id']==jid),None))
        if item:
            state=item['state'];percent=downloader.progress_percent(item['detail']) if state=='下载中' else None
            stage=item['detail'] if item['detail'] in ('正在获取下载地址','等待下载数据','正在合并音视频','正在检验文件','正在严格检查') else '准备中'
            suffix=f' · 当前文件 {percent:g}%' if percent is not None else (' · '+stage if state=='下载中' else '')
            prefix=f'{len(active)} 个任务 · ' if len(active)>1 else ''
            event=next((j for j in jobs if j['id']==jid),None);alert=' · 有任务失败' if active and event and event['state']=='失败' else ''
            text=f"{prefix}{state}{suffix} · {item['title']}{alert}";self.download_label.set_text(text);self.download_label.set_tooltip_text(text)
            self.download_progress.set_visible(percent is not None)
            if percent is not None:self.download_progress.set_fraction(percent/100)
            self.download_status.show()
        else:self.download_status.hide()
        event=next((j for j in jobs if j['id']==jid),None)
        start=getattr(self,'start_button',None)
        if event and event['state']=='完成' and event['media_id']==getattr(self,'detail_media_id',None) and start and start.get_toplevel() is self:
            try:media=self.store.get(event['media_id'])
            except Exception:self.fail('无法读取媒体库状态');return False
            path=media.get('path') if media else None
            if path and Path(path).is_file():start.set_tooltip_text('播放本地文件');start.get_accessible().set_name('播放本地文件')
        if getattr(self,'jobs_visible',False):self.show_jobs()
        return False
    def show_jobs(self):
        offset=self.jobs_scroll.get_vadjustment().get_value() if getattr(self,'jobs_visible',False) else 0
        try:
            if not self.downloader.reconcile():raise ValueError('无法保存下载状态')
            rows=self.store.jobs()
        except Exception:
            self.fail('无法读取或保存下载状态，请检查磁盘空间和权限');return
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        for item in rows:
            row=Gtk.Box(spacing=10);row.get_style_context().add_class('card');details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);title=label(item['title'],'media-title');title.set_ellipsize(3);title.set_max_width_chars(40);title.set_tooltip_text(item['title']);details.pack_start(title,False,False,0)
            percent=downloader.progress_percent(item['detail']) if item['state'] in ('下载中','暂停') else None
            detail=f'当前文件 {percent:g}%' if percent is not None else ('已保存到媒体库' if item['state']=='完成' else item['detail'])
            status=label(item['state']+(' · '+detail if detail else ''),'job-failed' if item['state']=='失败' else 'muted');details.pack_start(status,False,False,0)
            if percent is not None:
                progress=Gtk.ProgressBar();progress.get_style_context().add_class('job-progress');progress.set_fraction(percent/100);progress.set_hexpand(True);progress.get_accessible().set_name(f'当前文件 {percent:g}%');details.pack_start(progress,False,False,0)
            row.pack_start(details,True,True,0)
            actions=Gtk.Box(spacing=5);jid=item['id'];media=self.store.get(item['media_id'])
            if item['state'] in ('等待','下载中'):actions.pack_start(icon_button('media-playback-pause-symbolic','暂停',lambda _,j=jid:self.job_action(self.downloader.pause,j)),False,False,0)
            if item['state'] in ('暂停','中断','失败'):actions.pack_start(icon_button('media-playback-start-symbolic','继续' if item['state']!='失败' else '重新尝试',lambda _,j=jid:self.job_action(self.downloader.resume,j)),False,False,0)
            actions.pack_start(icon_button('document-edit-symbolic','编辑任务名称',lambda _,j=jid,t=item['title']:self.rename_job(j,t)),False,False,0)
            if media and media.get('path') and Path(media['path']).is_file():actions.pack_start(icon_button('document-open-symbolic','打开本地文件',lambda _,p=media['path']:self.open_local(p)),False,False,0)
            actions.pack_start(icon_button('folder-open-symbolic','打开下载目录',lambda *_:self.open_local(self.store.media_dir)),False,False,0)
            actions.pack_start(icon_button('user-trash-symbolic','删除任务',lambda _,j=jid:self.delete_job(j)),False,False,0);row.pack_end(actions,False,False,0)
            box.pack_start(row,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.clear_content();self.content.pack_start(page_heading('下载任务'),False,False,0)
        if not rows:self.content.pack_start(label('还没有下载任务。可以从视频详情或添加链接开始下载。','muted'),False,False,0)
        self.content.pack_start(scroll,True,True,0);self.content.show_all();self.jobs_scroll=scroll;self.jobs_visible=True;GLib.idle_add(lambda:(scroll.get_vadjustment().set_value(offset),False)[1])

    def job_action(self,action,jid):
        try:action(jid)
        except Exception as exc:self.fail(str(exc))

    def rename_job(self,jid,title):
        name=self.prompt('编辑任务名称','任务名称',title)
        if name is not None:
            try:self.store.rename_job(jid,name);self.download_update(jid);self.message('任务名称已更新；本地文件名称不变')
            except ValueError as exc:self.fail(str(exc))

    def delete_job(self,jid):
        dialog=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,text='删除这条下载任务？')
        dialog.format_secondary_text('正在下载的任务会停止。默认保留文件。');check=Gtk.CheckButton(label='同时永久删除此视频在下载目录中的媒体文件和未完成文件');check.get_child().set_line_wrap(True);dialog.get_message_area().pack_start(check,False,False,8)
        job=next((x for x in self.store.jobs() if x['id']==jid),None);uncertain=bool(job and job['state']=='停止未确认')
        if uncertain:check.set_sensitive(False)
        note=label('无法确认后台进程已停止，请先检查；此时只能保留文件删除任务。' if uncertain else '同一视频的其他任务和媒体库可能共用这些文件；目录外的文件不会删除。','muted');dialog.get_message_area().pack_start(note,False,False,0)
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'删除任务',Gtk.ResponseType.OK);dialog.show_all();response=dialog.run();remove_files=check.get_active();dialog.destroy()
        if response==Gtk.ResponseType.OK:
            self.message('正在停止并删除任务…')
            async_call(lambda:self.downloader.delete(jid,remove_files),lambda _:self.message('任务和找到的相关文件已删除' if remove_files else '任务已删除，文件已保留'),self.fail)

    def open_local(self,path):
        try:Gio.AppInfo.launch_default_for_uri(Path(path).resolve().as_uri(),None)
        except (GLib.Error,OSError) as exc:self.fail('无法打开本地文件或目录：'+str(exc))

    def account_surface_active(self):
        return bool(getattr(self,'account_status_widgets',None)) and ((not self.store.setting('setup_done',False) and self.setup_step==1) or getattr(self,'active_nav','') in ('settings','platform-youtube','platform-bilibili'))

    def account_text(self,source,state=None,error=''):
        if source=='youtube' and not self.store.setting('youtube_account_enabled',True) and state not in ('checking','unknown'):return '已断开'
        if source=='bilibili' and not self.store.setting('bilibili_cookies',False):return '未授权读取 Chrome 登录状态'
        previous=self.store.setting('account_'+source,{}) or {};when=previous.get('verified_at');name=previous.get('name')
        suffix=(' · '+name if name else '')+(' · 上次验证 '+when if when else '')
        if state=='checking':return '正在验证…'+suffix
        if state=='connected':return '已连接'+suffix
        if state=='unconnected':return '未连接 · 请连接 Google 账号'
        if state=='expired':return '需要重新连接 · 请重新授权'+suffix
        if state=='unknown':
            if source=='youtube' and '缺少 Google OAuth 客户端配置' in error:return '连接失败：缺少 Google OAuth 客户端配置。请选择配置文件，或跳过并稍后连接。'
            return '暂时无法验证'+(' · '+error if error else '')+'。请检查网络或登录状态后重试。'+suffix
        return ('上次验证成功'+suffix) if when else '尚未验证'

    def platform_status(self,source,state=None,error=''):
        b=getattr(self,'nav_buttons',{}).get('platform-'+source)
        if not b or not b.get_child():return
        title='YouTube' if source=='youtube' else 'B 站';text=self.account_text(source,state,error)
        short={'checking':'验证中','connected':'已连接','unconnected':'未连接','expired':'需重连','unknown':'无法验证'}.get(state,'未验证')
        if source=='youtube' and not self.store.setting('youtube_account_enabled',True):short='已断开'
        if source=='bilibili' and not self.store.setting('bilibili_cookies',False):short='未授权'
        b.get_child().get_children()[1].set_text(title+' · '+short)
        b.set_tooltip_text(text);b.get_accessible().set_name(title+' · '+text)

    def account_view_status(self,source,state=None,error=''):
        self.account_status_widgets[source].set_text(self.account_text(source,state,error))
        if source=='bilibili':
            enabled=self.store.setting('bilibili_cookies',False)
            self.bilibili_connect_button.set_label('断开连接' if enabled else '使用 Chrome 连接')
        if source=='youtube':
            self.youtube_connect_button.set_label('尝试连接 Google 账号' if state=='expired' else '连接 Google 账号')
            enabled=self.store.setting('youtube_account_enabled',True)
            self.youtube_import_button.set_visible(state=='unknown' and '缺少 Google OAuth 客户端配置' in error)
            self.youtube_connect_button.set_visible(not enabled or state in ('unconnected','expired') or (state=='unknown' and '缺少 Google OAuth 客户端配置' in error))
            self.youtube_disconnect_button.set_visible(enabled and state!='unconnected' and not (state=='unknown' and '缺少 Google OAuth 客户端配置' in error))

    def check_account(self,source,force=True):
        if source=='youtube' and not self.store.setting('youtube_account_enabled',True):
            self.account_checks[source]+=1;self.account_inflight.pop(source,None);self.account_cache.pop(source,None);self.account_view_status(source,'unconnected');self.platform_status(source,'unconnected');return
        if source=='bilibili' and not self.store.setting('bilibili_cookies',False):
            self.account_checks[source]+=1;self.account_inflight.pop(source,None);self.account_cache.pop(source,None);self.account_view_status(source,'unconnected');self.platform_status(source);return
        self.account_views[source]=self.view_generation
        cached=self.account_cache.get(source)
        if not force and cached and time.monotonic()-cached[0]<300:
            _,state,error=cached;self.account_view_status(source,state,error);self.platform_status(source,state,error);return
        if not force and source in self.account_inflight:
            self.account_view_status(source,'checking');self.platform_status(source,'checking');return
        self.account_checks[source]+=1;request=self.account_checks[source];self.account_inflight[source]=request
        self.account_view_status(source,'checking')
        self.platform_status(source,'checking')
        def fetch():
            if source=='youtube':
                values=sources.list_youtube('channel');return ((values[0].get('snippet') or {}).get('title') or '') if values else ''
            values=[];self.bilibili_stream('status',values.extend);return values[0].get('name','') if values else ''
        def done(name):
            if request!=self.account_checks[source]:return False
            self.account_inflight.pop(source,None);self.account_cache[source]=(time.monotonic(),'connected','')
            self.store.set_setting('account_'+source,{'name':name,'verified_at':datetime.now().strftime('%Y-%m-%d %H:%M')})
            self.platform_status(source,'connected')
            if self.account_views.get(source)==self.view_generation:self.account_view_status(source,'connected')
            return False
        def failed(error):
            if request!=self.account_checks[source]:return False
            self.account_inflight.pop(source,None)
            state='unknown'
            if source=='youtube' and '需要连接 YouTube' in error:
                config=google_config_dir()
                state='expired' if (config/'token.json').exists() else 'unconnected'
            elif source=='youtube' and 'HTTP 401' in error:state='expired'
            error=error if state=='unknown' else '';self.account_cache[source]=(time.monotonic(),state,error)
            self.platform_status(source,state,error)
            if self.account_views.get(source)==self.view_generation:self.account_view_status(source,state,error)
            return False
        async_call(fetch,done,failed)

    def bilibili_stream(self,kind,on_page,fid=''):
        if self.store.setting('bilibili_auth_source','chrome')=='qr':return bilibili.stream(kind,on_page,fid,auth_source='qr')
        return bilibili.stream(kind,on_page,fid) if fid else bilibili.stream(kind,on_page)

    def connect_bilibili_qr(self,*_):
        if getattr(self,'bilibili_qr_dialog',None):return
        if self.store.setting('bilibili_cookies',False):
            old=self.store.setting('bilibili_auth_source','chrome')
            confirm=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,text='切换 B 站账号连接方式？')
            confirm.format_secondary_text('扫码成功后将改用扫码账号；Chrome 登录状态不会改变。' if old=='chrome' else '扫码成功后将替换当前保存的 B 站扫码账号。')
            confirm.add_buttons('取消',Gtk.ResponseType.CANCEL,'继续扫码',Gtk.ResponseType.OK);response=confirm.run();confirm.destroy()
            if response!=Gtk.ResponseType.OK:return
        from .bilibili_login import QRLogin
        login=QRLogin();cancelled=threading.Event()
        dialog=Gtk.Dialog(title='扫码连接 B 站',transient_for=self,flags=Gtk.DialogFlags.MODAL)
        dialog.set_default_size(360,420);dialog.add_button('取消',Gtk.ResponseType.CANCEL)
        area=dialog.get_content_area();area.set_border_width(20);area.set_spacing(12)
        area.pack_start(label('打开 B 站手机客户端扫码并确认。账号用于读取关注和收藏，以及你选择的 B 站播放和下载；登录信息保存在本机。'),False,False,0)
        drawing=Gtk.Image();drawing.set_size_request(240,240);drawing.set_halign(Gtk.Align.CENTER);area.pack_start(drawing,False,False,0)
        state=label('正在获取二维码…');area.pack_start(state,False,False,0)
        def close(*_):
            cancelled.set();login.cancel()
            if getattr(self,'bilibili_qr_dialog',None) is dialog:self.bilibili_qr_dialog=None
        dialog.connect('response',lambda d,_:d.destroy());dialog.connect('destroy',close)
        self.bilibili_qr_dialog=dialog;dialog.show_all()
        def update(result):
            if cancelled.is_set():return False
            status=result.get('state')
            text={'waiting_scan':'等待扫码','waiting_confirm':'已扫码，请在手机上确认','expired':'二维码已过期，请关闭后重新扫码','cancelled':'已取消扫码','error':'连接失败，请检查网络后重试','success':'已收到授权，正在验证账号…'}.get(status,'连接失败，请关闭后重试')
            state.set_text(text)
            if status in ('expired','cancelled','error'):
                dialog.get_widget_for_response(Gtk.ResponseType.CANCEL).set_label('关闭')
            if status=='success':
                self.store.set_setting('bilibili_auth_source','qr');self.store.set_setting('bilibili_cookies',True);self.account_cache.pop('bilibili',None)
                if self.account_surface_active():self.check_account('bilibili')
                else:self.message('B 站授权已保存，可在设置中验证账号')
                dialog.destroy()
            return False
        def ready(data):
            if cancelled.is_set():return False
            size=len(data);cell=max(1,240//size);width=size*cell
            pixels=b''.join((b''.join((b'\x00\x00\x00' if value else b'\xff\xff\xff')*cell for value in row))*cell for row in data)
            drawing.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(pixels),GdkPixbuf.Colorspace.RGB,False,8,width,width,width*3));state.set_text('等待扫码');return False
        def work():
            try:
                import qrcode
                result=login.start()
                if cancelled.is_set():return
                if result.get('state')!='waiting_scan':GLib.idle_add(update,result);return
                code=qrcode.QRCode(border=4,box_size=1);code.add_data(result['qr_url']);code.make(fit=True)
                GLib.idle_add(ready,code.get_matrix())
                while not cancelled.wait(2):
                    result=login.poll()
                    if cancelled.is_set():return
                    GLib.idle_add(update,result)
                    if result.get('state') not in ('waiting_scan','waiting_confirm'):return
            except ImportError:
                if not cancelled.is_set():GLib.idle_add(lambda:(state.set_text('二维码组件不可用，请联系发布者或使用 Chrome 连接。'),False)[1])
            except Exception:
                if not cancelled.is_set():GLib.idle_add(update,{'state':'error'})
        threading.Thread(target=work,daemon=True).start()

    def toggle_bilibili_account(self,*_):
        enabled=self.store.setting('bilibili_cookies',False)
        dialog=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,text='断开 B 站账号？' if enabled else '连接 B 站账号？')
        dialog.format_secondary_text(('删除本机保存的 B 站扫码登录信息，停止读取账号；已开始的读取可能继续。Chrome 登录、本地媒体和下载文件会保留。' if self.store.setting('bilibili_auth_source','chrome')=='qr' else '停止读取关注和收藏；已开始的读取可能继续。Chrome 登录、本地媒体和下载文件会保留；播放和下载 Cookie 设置不变。') if enabled else '允许 MediaDesk 读取 Chrome 中的 B 站登录状态，用于获取关注和收藏。')
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'断开' if enabled else '允许并连接',Gtk.ResponseType.OK);response=dialog.run();dialog.destroy()
        if response!=Gtk.ResponseType.OK:return
        if not enabled:self.store.set_setting('bilibili_auth_source','chrome')
        elif self.store.setting('bilibili_auth_source','chrome')=='qr':
            from .bilibili_login import QRLogin
            QRLogin().clear_credentials()
        self.store.set_setting('bilibili_cookies',not enabled)
        if enabled:self.store.set_setting('account_bilibili',{})
        self.check_account('bilibili');self.message('B 站已断开' if enabled else '正在验证 B 站账号…')

    def disconnect_youtube(self,*_):
        dialog=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,text='断开 YouTube 账号？')
        dialog.format_secondary_text('MediaDesk 将停止读取账号；已开始的读取可能继续。本地媒体和共享的 Google 授权令牌会保留，不影响其他应用。')
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'断开',Gtk.ResponseType.OK);response=dialog.run();dialog.destroy()
        if response!=Gtk.ResponseType.OK:return
        self.youtube_auth_generation+=1
        self.store.set_setting('youtube_account_enabled',False);self.store.set_setting('account_youtube',{})
        self.setup_authenticated=False;self.check_account('youtube');self.message('YouTube 已断开')

    def show_settings(self):
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);content.set_border_width(4)
        content.pack_start(label('外观','section'),False,False,0);themes=Gtk.ComboBoxText()
        for key,(name,_,_) in THEMES.items():themes.append(key,name)
        themes.set_active_id(self.store.setting('theme','dark'));themes.set_halign(Gtk.Align.START)
        def change_theme(control):
            theme=control.get_active_id()
            if theme:self.store.set_setting('theme',theme);self.apply_theme(theme)
        themes.connect('changed',change_theme);content.pack_start(themes,False,False,0);content.pack_start(Gtk.Separator(),False,False,4)
        content.pack_start(label('账号与连接','section'),False,False,0);content.pack_start(label('账号读取及播放、下载会向对应平台发送必要请求。','muted'),False,False,0);self.account_status_widgets={}
        for source,title in [('youtube','YouTube'),('bilibili','B 站')]:
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);card.get_style_context().add_class('card');card.pack_start(label(title,'section'),False,False,0)
            state=label(self.account_text(source));self.account_status_widgets[source]=state;card.pack_start(state,False,False,0)
            actions=Gtk.Box(spacing=8)
            if source=='youtube':
                self.youtube_connect_button=button('连接 Google 账号',self.authorize)
                self.youtube_connect_button.set_no_show_all(True)
                actions.pack_start(self.youtube_connect_button,False,False,0)
                self.youtube_disconnect_button=button('断开连接',self.disconnect_youtube)
                self.youtube_disconnect_button.set_no_show_all(True);actions.pack_start(self.youtube_disconnect_button,False,False,0)
                self.youtube_import_button=button('导入 Google 客户端配置',self.import_google_client);self.youtube_import_button.set_no_show_all(True);actions.pack_start(self.youtube_import_button,False,False,0)
            else:
                actions.pack_start(button('扫码连接 B 站',self.connect_bilibili_qr),False,False,0)
                self.bilibili_connect_button=button('使用 Chrome 连接',self.toggle_bilibili_account)
                actions.pack_start(self.bilibili_connect_button,False,False,0)
            actions.pack_start(button('刷新状态',lambda _,s=source:self.check_account(s)),False,False,0);card.pack_start(actions,False,False,0);content.pack_start(card,False,False,0)
        content.pack_start(Gtk.Separator(),False,False,4);content.pack_start(label('下载与播放','section'),False,False,0)
        check=Gtk.CheckButton(label='允许解析、播放和下载时读取 Chrome 登录状态（Cookie）');check.set_active(self.store.setting('cookies',False));check.connect('toggled',lambda w:self.store.set_setting('cookies',w.get_active()));content.pack_start(check,False,False,0)
        content.pack_start(label('播放 / 暂停快捷键','section'),False,False,0)
        shortcut=Gtk.ComboBoxText()
        for key,title in [('space','空格'),('k','K'),('off','关闭')]:shortcut.append(key,title)
        shortcut.set_active_id(self.store.setting('playback_shortcut','space'))
        if shortcut.get_active_id() is None:shortcut.set_active_id('space')
        shortcut.set_halign(Gtk.Align.START);shortcut.connect('changed',lambda w:self.store.set_setting('playback_shortcut',w.get_active_id()));content.pack_start(shortcut,False,False,0)
        content.pack_start(label('播放页面可用；输入或操作控件时保留原有键盘操作。','muted'),False,False,0)
        content.pack_start(label('有下载任务时关闭窗口','section'),False,False,0)
        close_choice=Gtk.ComboBoxText()
        for key,title in [('ask','每次询问'),('minimize','最小化窗口'),('exit','退出并中断下载')]:close_choice.append(key,title)
        close_choice.set_active_id(self.store.setting('close_behavior','ask'))
        if close_choice.get_active_id() is None:close_choice.set_active_id('ask')
        close_choice.connect('changed',lambda w:self.store.set_setting('close_behavior',w.get_active_id()));content.pack_start(close_choice,False,False,0)
        content.pack_start(label('最小化后下载继续，暂停的任务仍需手动继续。','muted'),False,False,0)
        content.pack_start(Gtk.Separator(),False,False,4);content.pack_start(label('下载偏好','section'),False,False,0);group=None
        for key,title in [('quality','画质优先'),('size','文件大小优先'),('balance','均衡')]:
            rb=Gtk.RadioButton.new_with_label_from_widget(group,title)
            if group is None:group=rb
            rb.set_active(self.store.setting('preference','quality')==key);rb.connect('toggled',lambda w,k=key:self.store.set_setting('preference',k) if w.get_active() else None);content.pack_start(rb,False,False,0)
        content.pack_start(Gtk.Separator(),False,False,4);content.pack_start(label('本地媒体','section'),False,False,0);content.pack_start(label('扫描选中目录及子目录，媒体文件路径保存到本地库；不移动或重命名文件。','muted'),False,False,0)
        self.dir_checks=[];dirsbox=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);content.pack_start(dirsbox,False,False,0)
        for path in safe_dirs():
            cb=Gtk.CheckButton(label=str(path));cb.set_active(True);dirsbox.pack_start(cb,False,False,0);self.dir_checks.append((cb,path))
        actions=Gtk.Box(spacing=8);actions.pack_start(button('选择目录',lambda *_:self.choose_scan_dir(dirsbox)),False,False,0);actions.pack_start(button('扫描选中目录',self.scan),False,False,0);content.pack_start(actions,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(content);self.clear_content();self.content.pack_start(page_heading('设置'),False,False,0);self.content.pack_start(scroll,True,True,0);self.content.show_all()
        self.check_account('youtube',force=False);self.check_account('bilibili',force=False)
    def on_close(self,*_):
        try:
            states={job['state'] for job in self.store.jobs()}
            if not states.intersection(('等待','下载中','暂停')):return False
            behavior=self.store.setting('close_behavior','ask')
            if behavior=='minimize':self.iconify();return True
            if behavior=='exit':return False
            detail='退出将中断下载；已下载的部分会保留，下次可尝试继续。'
            if '暂停' in states:detail+=' 最小化后已暂停的任务仍需手动继续。'
        except Exception:
            detail='无法读取下载状态。退出可能中断下载；已下载的部分会保留。'
        dialog=Gtk.MessageDialog(transient_for=self,flags=Gtk.DialogFlags.MODAL,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,text='关闭 MediaDesk')
        dialog.format_secondary_text(detail)
        dialog.add_button('取消',Gtk.ResponseType.CANCEL)
        dialog.add_button('最小化',Gtk.ResponseType.ACCEPT)
        dialog.add_button('退出并中断',Gtk.ResponseType.YES)
        response=dialog.run();dialog.destroy()
        if response==Gtk.ResponseType.ACCEPT:self.iconify()
        return response!=Gtk.ResponseType.YES

    def on_destroy(self,*_):
        self.view_generation+=1
        if getattr(self,'bilibili_qr_dialog',None):self.bilibili_qr_dialog.destroy()
        self.hover_preview.stop()
        self.reset_shortcut()
        if self.player:self.player.close()
        self.thumb_workers.shutdown(wait=False,cancel_futures=True)
        self.downloader.stop_all()
        if Gtk.main_level():Gtk.main_quit()

def main():
    from .instance import acquire
    from .store import data_dir
    root=data_dir();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        fd=acquire(root/'application.lock')
    except BlockingIOError:
        d=Gtk.MessageDialog(message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.OK,text='MediaDesk 已在运行');d.run();d.destroy();return
    try:
        win=App();win.show_all();Gtk.main()
    finally:os.close(fd)
