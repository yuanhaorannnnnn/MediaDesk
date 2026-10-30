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
from . import downloader, sources, bilibili
from .player import Player

CSS=b'''*{font-family:Sans} window,dialog,headerbar{background:#11151a;color:#f2f5f4} list,list row,scrolledwindow,viewport{background:#11151a;color:#f2f5f4} label{color:#f2f5f4} button{background:#263137;color:#f2f5f4;border:1px solid #46575c;border-radius:6px;padding:7px} button:hover{background:#35434a} button:focus{outline:2px solid #7dd6d0;outline-offset:-2px} button.suggested-action{background:#7dd6d0;color:#102426;border:0} button.suggested-action label{color:#102426} entry,combobox,treeview{background:#1d242b;color:#f2f5f4} .sidebar{background:#171c22;border-right:1px solid #303b42} .sidebar button{background:transparent;border-color:transparent;padding:9px} .sidebar button:hover{background:#28323b} .sidebar button.selected{background:#2b3d41;border-left:3px solid #7dd6d0} .sidebar .nav-title{font-size:12px;color:#9eafb2;font-weight:bold} .muted{color:#b7c5c8} .title{font-size:25px;font-weight:bold} .section{font-size:18px;font-weight:bold} .card{background:#1d242b;padding:20px;border-radius:8px} button.media-card{background:#1d242b;border-color:#303b42;padding:0} button.media-card:hover{background:#28323b;border-color:#7dd6d0} .status{color:#b7c5c8;font-size:12px} label.media-title{font-size:15px;font-weight:600} .media-art{background:#263137;color:#9eafb2;border-radius:4px} scale.player-seek trough highlight{background-image:none;background-color:#7dd6d0;border-color:#7dd6d0;box-shadow:none} progressbar.job-progress progress{background-image:none;background-color:#7dd6d0;border-color:#7dd6d0;box-shadow:none} label.job-failed{color:#ffa6a0}'''

LIGHT_CSS=b'''*{font-family:Sans} window,dialog,headerbar{background:#f6f8f7;color:#192c30} list,list row,scrolledwindow,viewport{background:#f6f8f7;color:#192c30} label{color:#192c30} button{background:#edf2f1;color:#192c30;border:1px solid #c4d2d0;border-radius:6px;padding:7px} button:hover{background:#dce9e7} button:focus{outline:2px solid #187d78;outline-offset:-2px} button.suggested-action{background:#247f78;color:#ffffff;border:0} button.suggested-action label{color:#ffffff} entry,combobox,treeview{background:#ffffff;color:#192c30} .sidebar{background:#eaf0ef;border-right:1px solid #cedbd9} .sidebar button{background:transparent;border-color:transparent;padding:9px} .sidebar button:hover{background:#d8e6e4} .sidebar button.selected{background:#cce4e1;border-left:3px solid #247f78} .sidebar .nav-title{font-size:12px;color:#536e6b;font-weight:bold} .muted{color:#536b6b} .title{font-size:25px;font-weight:bold} .section{font-size:18px;font-weight:bold} .card{background:#ffffff;padding:20px;border-radius:8px} button.media-card{background:#ffffff;border-color:#d3dfdd;padding:0} button.media-card:hover{background:#edf7f5;border-color:#247f78} .status{color:#536b6b;font-size:12px} label.media-title{font-size:15px;font-weight:600} .media-art{background:#e6eeec;color:#536e6b;border-radius:4px} scale.player-seek trough highlight{background-image:none;background-color:#247f78;border-color:#247f78;box-shadow:none} progressbar.job-progress progress{background-image:none;background-color:#247f78;border-color:#247f78;box-shadow:none} label.job-failed{color:#9c3733}'''


def recolor(css,colors):
    for old,new in colors.items():css=css.replace(old.encode(),new.encode())
    return css


# Art movements inform the component color relationships; artwork remains unchanged.
NABIS_CSS=recolor(CSS,{
    '#11151a':'#241d2b','#f2f5f4':'#f8f0e8','#263137':'#493949','#46575c':'#725d6e',
    '#35434a':'#5b4958','#7dd6d0':'#eac094','#102426':'#342117','#1d242b':'#382c3e',
    '#171c22':'#302638','#303b42':'#665267','#28323b':'#52435a','#2b3d41':'#5b465d',
    '#9eafb2':'#dfc5bd','#b7c5c8':'#d9c8c9'
})+b''' .sidebar .nav-title{background:#51405c;color:#f2ddc9;padding:4px 7px} .sidebar button.selected{border-left-width:4px} .card,button.media-card{border-radius:2px} button.media-card{border:2px solid #665267;border-bottom:4px solid #a77972} .media-art{border-radius:0}'''
NEO_IMPRESSION_CSS=recolor(LIGHT_CSS,{
    '#f6f8f7':'#f3f5ec','#192c30':'#243a44','#edf2f1':'#e5eee8','#c4d2d0':'#b6c9c5',
    '#dce9e7':'#d5e5da','#187d78':'#315d77','#247f78':'#315d77','#ffffff':'#fffef7',
    '#eaf0ef':'#e1ece4','#cedbd9':'#bdcfc6','#d8e6e4':'#d5e5da','#cce4e1':'#d7e8dc',
    '#536e6b':'#536c73','#536b6b':'#526b72','#d3dfdd':'#cbd7cc','#edf7f5':'#eaf1e6',
    '#e6eeec':'#e0ece5'
})+b''' .sidebar button.selected{background-image:linear-gradient(to right,#d4e6d9 0%,#d4e6d9 38%,#e8ead8 38%,#e8ead8 70%,#efdfd6 70%,#efdfd6 100%)} .sidebar .nav-title{border-bottom:2px solid #a2bcb1;padding-bottom:4px} button.media-card{border-bottom:3px solid #a9bfb6} .card{border:1px solid #cbd7cc}'''
THEMES={'dark':('深色',CSS,True),'light':('浅色',LIGHT_CSS,False),
        'nabis':('纳比派 · 深色',NABIS_CSS,True),'neo-impressionism':('新印象主义 · 浅色',NEO_IMPRESSION_CSS,False)}


def label(text='',css=None):
    w=Gtk.Label(label=text);w.set_xalign(0);w.set_line_wrap(True);w.set_selectable(False)
    if css:w.get_style_context().add_class(css)
    return w

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
    def __init__(self):
        super().__init__()
        self.pixbuf=None;self.cover_height=107;self.image_size=None
        self.frame=Gtk.Box();self.frame.set_size_request(190,self.cover_height)
        self.frame.get_style_context().add_class('media-art')
        self.frame.connect('size-allocate',self.resize_cover);self.add(self.frame)
        self.image=Gtk.Image.new_from_icon_name('video-x-generic-symbolic',Gtk.IconSize.DIALOG)
        self.image.get_style_context().add_class('muted');self.image.set_halign(Gtk.Align.CENTER);self.image.set_valign(Gtk.Align.CENTER)
        self.add_overlay(self.image)

    def resize_cover(self,widget,allocation):
        height=max(107,round(allocation.width*9/16))
        if height!=self.cover_height:
            self.cover_height=height;widget.set_size_request(190,height)
        if self.pixbuf:
            scale=min(allocation.width/self.pixbuf.get_width(),height/self.pixbuf.get_height())
            size=(max(1,round(self.pixbuf.get_width()*scale)),max(1,round(self.pixbuf.get_height()*scale)))
            if size!=self.image_size:
                self.image_size=size;self.image.set_from_pixbuf(self.pixbuf.scale_simple(*size,GdkPixbuf.InterpType.BILINEAR))

    def set_cover(self,path):
        self.pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,480,270,True);self.image_size=None
        self.resize_cover(self.frame,self.frame.get_allocation())



class App(Gtk.Window):
    def __init__(self,store=None):
        super().__init__(title='MediaDesk');self.set_default_size(1180,760);self.connect('destroy',self.on_destroy);self.connect('key-press-event',self.on_key)
        self.set_wmclass('mediadesk','MediaDesk')
        try:self.set_icon_from_file(str(Path(__file__).parent/'assets'/'mediadesk.svg'))
        except GLib.Error:pass
        self.store=store or Store();self.downloader=downloader.Downloads(self.store,lambda jid:GLib.idle_add(self.download_update,jid));self.thumb_workers=ThreadPoolExecutor(max_workers=6);self.player=None;self.player_open=False;self.play_request=0;self.playing_online=False;self.fullscreened=False;self.theater=False;self.rows=[];self.row_index=0;self.source_kind='library';self.view_generation=0;self.setup_step=0;self.setup_authenticated=False;self.account_checks={'youtube':0,'bilibili':0};self.account_cache={};self.account_inflight={};self.account_views={}
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
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);outer.set_border_width(55);outer.set_hexpand(True);outer.set_vexpand(True)
        card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);card.get_style_context().add_class('card');card.set_size_request(520,-1);card.set_halign(Gtk.Align.CENTER);card.set_valign(Gtk.Align.CENTER);outer.pack_start(card,True,True,0)
        titles=['选择内容来源','连接 YouTube 账号','发现本地媒体','选择下载偏好','准备完成'];s=self.setup_step
        card.pack_start(label(f'{s+1} / 5  ·  首次设置','muted'),False,False,0);card.pack_start(label(titles[s],'title'),False,False,0)
        if s==0:card.pack_start(label('连接 YouTube 账号，或添加 YouTube 和 B 站视频链接。'),False,False,0)
        if s==1:
            card.pack_start(label('使用 Google 只读授权读取订阅、喜欢的视频与播放列表；请求会发送给 Google。可以跳过，之后再连接。'),False,False,0)
            card.pack_start(button('连接 Google 账号',self.authorize,True),False,False,0)
            self.cookie_check=Gtk.CheckButton(label='允许解析、播放和下载时读取 Chrome 登录状态（Cookie）');self.cookie_check.set_active(self.store.setting('cookies',False));self.cookie_check.connect('toggled',lambda w:self.store.set_setting('cookies',w.get_active()));card.pack_start(self.cookie_check,False,False,0)
        if s==2:
            dirs=safe_dirs();card.pack_start(label('扫描所选目录及子目录，媒体文件路径会保存到本地库；不移动或重命名文件。'),False,False,0)
            self.dir_checks=[]
            for path in dirs:
                cb=Gtk.CheckButton(label=str(path));cb.set_active(True);card.pack_start(cb,False,False,0);self.dir_checks.append((cb,path))
            if not dirs:card.pack_start(label('未发现可安全扫描的默认目录。'),False,False,0)
            card.pack_start(button('选择其他目录',lambda *_:self.choose_scan_dir(card)),False,False,0)
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
        card.pack_start(Gtk.Box(),True,True,0);row=Gtk.Box(spacing=8)
        if s:row.pack_start(button('上一步',lambda *_:self.setup_move(-1)),False,False,0)
        row.pack_end(button('进入媒体库' if s==4 else '继续',self.setup_next,True),False,False,0)
        if s<4:row.pack_end(button('跳过',self.setup_next),False,False,0)
        card.pack_start(row,False,False,0);self.replace(outer)

    def setup_move(self,n):self.setup_step+=n;self.setup()
    def setup_next(self,*_):
        if self.setup_step==4:
            self.store.set_setting('setup_done',True);self.workspace()
            if self.setup_authenticated:self.load_source('likes')
        else:self.setup_step+=1;self.setup()

    def authorize(self,*_):
        self.message('正在打开 Google 授权页面…')
        def done(_):
            self.setup_authenticated=True;self.message('Google 授权完成，正在验证账号')
            if getattr(self,'account_status_widgets',None) and getattr(self,'active_nav','') in ('settings','platform-youtube','platform-bilibili'):self.check_account('youtube')
            return False
        async_call(lambda:sources.list_youtube('auth'),done,self.fail)

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
        add_nav('discover-follow','关注','avatar-default-symbolic',lambda:self.show_discovery('follow'))
        add_nav('discover-collections','收藏与播放列表','emblem-favorite-symbolic',lambda:self.show_discovery('collections'))
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
        heading=Gtk.Box(spacing=12);heading.pack_start(label(title,'title'),True,True,0);self.rows_count=label(f'{len(rows)} 项'+(' · 正在读取…' if loading else ''),'muted');heading.pack_end(self.rows_count,False,False,0);self.content.pack_start(heading,False,False,0)
        if not rows and not loading:
            empty=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);empty.set_valign(Gtk.Align.CENTER);empty.set_halign(Gtk.Align.CENTER)
            empty.pack_start(Gtk.Image.new_from_icon_name('folder-videos-symbolic',Gtk.IconSize.DIALOG),False,False,0);empty.pack_start(label('这里还没有内容','section'),False,False,0);empty.pack_start(label('读取 YouTube 内容，或添加 YouTube、B 站视频链接。','muted'),False,False,0)
            actions=Gtk.Box(spacing=8);actions.pack_start(button('收藏与播放列表',lambda *_:self.show_discovery('collections')),False,False,0);actions.pack_start(button('添加链接',self.add_url,True),False,False,0);empty.pack_start(actions,False,False,0);self.content.pack_start(empty,True,True,0);self.content.show_all();return
        search=Gtk.SearchEntry();search.set_placeholder_text('搜索当前列表的标题或频道');self.content.pack_start(search,False,False,0)
        no_results=label('没有匹配的内容。','muted');no_results.set_no_show_all(True);self.content.pack_start(no_results,False,False,0)
        box=Gtk.FlowBox();self.rows_box=box;box.set_selection_mode(Gtk.SelectionMode.NONE);box.set_homogeneous(True);box.set_min_children_per_line(1);box.set_max_children_per_line(4);box.set_column_spacing(12);box.set_row_spacing(12);box.set_valign(Gtk.Align.START)
        box.set_filter_func(lambda child:search.get_text().strip().casefold() in child.search_text)
        def filter_rows(*_):
            self.rows_query=search.get_text().strip();box.invalidate_filter();no_results.set_visible(bool(search.get_text().strip()) and not any(child.get_child_visible() for child in box.get_children()))
        self.refresh_rows_filter=filter_rows;search.connect('search-changed',filter_rows);search.set_text(query)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.content.pack_start(scroll,True,True,0);self.append_cards(rows,0);self.content.show_all()

    def append_cards(self,rows,start):
        box=self.rows_box
        for i,item in enumerate(rows,start):
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);card.set_border_width(9);card.set_size_request(190,-1)
            artwork=MediaCover();card.pack_start(artwork,False,False,0)
            if item.get('thumbnail'):self.load_art(artwork,item['thumbnail'])
            t=label(item.get('title') or '未命名','media-title');t.set_max_width_chars(24);t.set_lines(2);t.set_ellipsize(3);t.set_tooltip_text(item.get('title') or '未命名');card.pack_start(t,False,False,0)
            origin={'local':'本地文件','youtube':'YouTube','bilibili':'B 站'}.get(item.get('source'),'其他来源');channel=item.get('channel');state=('本地可用' if Path(item['path']).is_file() else '文件缺失') if item.get('path') else '未下载'
            if item.get('unavailable'):state='来源已失效'+(' · 本地可用' if item.get('path') and Path(item['path']).is_file() else '')
            if channel:
                creator=label(channel,'muted');creator.set_max_width_chars(24);creator.set_ellipsize(3);creator.set_tooltip_text(channel);card.pack_start(creator,False,False,0)
            desc=label(' · '.join((origin,state)),'muted');desc.set_max_width_chars(24);desc.set_ellipsize(3);desc.set_tooltip_text(desc.get_text());card.pack_start(desc,False,False,0)
            b=Gtk.Button();b.get_style_context().add_class('media-card');b.connect('clicked',lambda _,idx=i:self.open_row(idx));b.add(card)
            child=Gtk.FlowBoxChild();child.search_text=(str(item.get('title') or '')+' '+str(item.get('channel') or '')).casefold();child.add(b);box.add(child)
        box.show_all();self.refresh_rows_filter()

    def show_art(self,widget,path):
        if path:
            try:
                if isinstance(widget,MediaCover):widget.set_cover(path)
                else:widget.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path,190,107,True))
            except GLib.Error:pass
        return False

    def load_art(self,widget,url):
        future=self.thumb_workers.submit(sources.thumbnail,self.store,url)
        def done(result):
            try:GLib.idle_add(self.show_art,widget,result.result())
            except Exception:pass
        future.add_done_callback(done)

    def load_source(self,kind,playlist_id=''):
        self.source_kind=kind;self.select_nav('discover-follow' if kind=='subscriptions' else 'discover-collections')
        title={'likes':'喜欢的视频','playlists':'播放列表','subscriptions':'订阅频道','playlist-items':'播放列表内容'}[kind]
        if kind in ('likes','playlist-items'):
            self.display_rows(title,[],loading=True);generation=self.view_generation;self.message('正在后台读取 YouTube…');count=[0]
            def page(raw):
                items=[]
                for value in raw:
                    item=sources.normalize(value,kind)
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
                    self.rows_count.set_text(f'{len(self.rows)} 项 · 读取未完成');retry=button('重新读取',lambda *_:self.load_source(kind,playlist_id));self.content.pack_start(retry,False,False,0);retry.set_halign(Gtk.Align.START);retry.show();self.message('读取未完成：'+error)
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
            if generation==self.view_generation:self.set_content(label(title,'title'),label('读取失败：'+error,'muted'),button('重试',lambda *_:self.load_source(kind,playlist_id)))
            self.fail(error);return False
        async_call(fetch,done,failed)

    def display_source(self,kind,items):
        box=Gtk.ListBox();box.set_selection_mode(Gtk.SelectionMode.NONE)
        for item in items:
            sn=item.get('snippet') or {};r=Gtk.ListBoxRow();row=Gtk.Box(spacing=10);row.set_border_width(10);row.pack_start(label(sn.get('title','未命名')),True,True,0)
            if kind=='playlists':row.pack_end(button('查看',lambda _,i=item:self.load_source('playlist-items',i['id'])),False,False,0)
            r.add(row);box.add(r)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.clear_content();self.content.pack_start(label('YouTube 播放列表' if kind=='playlists' else 'YouTube 订阅','title'),False,False,0);self.content.pack_start(scroll,True,True,0);self.content.show_all()

    def show_discovery(self,category):
        self.select_nav('discover-follow' if category=='follow' else 'discover-collections')
        title='关注' if category=='follow' else '收藏与播放列表';self.clear_content();generation=self.view_generation
        heading=Gtk.Box(spacing=12);heading.pack_start(label(title,'title'),True,True,0)
        choice=Gtk.ComboBoxText();choice.append('all','全部平台');choice.append('youtube','YouTube');choice.append('bilibili','B 站');choice.set_active_id('all');heading.pack_end(choice,False,False,0)
        self.content.pack_start(heading,False,False,0);status=label('正在读取…','muted');self.content.pack_start(status,False,False,0)
        box=Gtk.ListBox();box.set_selection_mode(Gtk.SelectionMode.NONE);scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.content.pack_start(scroll,True,True,0);self.content.show_all()
        self.discovery_choice=choice;self.discovery_box=box;self.discovery_status=status
        entries=[];states={'youtube':'正在读取','bilibili':'正在读取'};received={'youtube':0,'bilibili':0}
        def render(*_):
            if generation!=self.view_generation:return False
            for child in box.get_children():box.remove(child)
            selected=choice.get_active_id();shown=[x for x in entries if selected in ('all',x['source'])]
            for item in shown:
                line=Gtk.Box(spacing=10);line.set_border_width(10);line.pack_start(label(item['name']),True,True,0);line.pack_start(label('YouTube' if item['source']=='youtube' else 'B 站','muted'),False,False,0)
                if item.get('action'):line.pack_end(button('查看',item['action']),False,False,0)
                elif item.get('url'):line.pack_end(Gtk.LinkButton.new_with_label(item['url'],'查看主页'),False,False,0)
                row=Gtk.ListBoxRow();row.add(line);box.add(row)
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
            if category=='collections':accept('youtube',[{'source':'youtube','name':'喜欢的视频','static':True,'action':lambda *_:self.load_source('likes')}])
            try:
                raw=sources.list_youtube('subscriptions' if category=='follow' else 'playlists');items=[]
                for value in raw:
                    sn=value.get('snippet') or {};item={'source':'youtube','name':sn.get('title') or '未命名'}
                    if category=='collections':item['action']=lambda _,i=value:self.load_source('playlist-items',i['id'])
                    else:
                        cid=(sn.get('resourceId') or {}).get('channelId') or ''
                        if cid and all(c.isalnum() or c in '_-' for c in cid):item['url']='https://www.youtube.com/channel/'+cid
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
                            if isinstance(mid,int) and mid>0:item['url']=f'https://space.bilibili.com/{mid}'
                        else:
                            name=value.get('title') or '未命名收藏夹';item={'source':'bilibili','name':name,'action':lambda _,i=value,n=name:self.load_bilibili('favorites',str(i['id']),n)}
                        items.append(item)
                    accept('bilibili',items)
                bilibili.stream('followings' if category=='follow' else 'folders',page);finish('bilibili')
            except Exception as exc:finish('bilibili',('读取未完成：' if received['bilibili'] else '读取失败：')+str(exc))
        threading.Thread(target=youtube,daemon=True).start();threading.Thread(target=bili,daemon=True).start()

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
            def fetch():bilibili.stream('favorites',page,fid)
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
        def fetch():bilibili.stream(kind,page,fid)
        def done(_):
            if generation==self.view_generation:status.set_text(f'{count[0]} 项')
            self.message(f'B 站读取完成：{count[0]} 项');return False
        def failed(error):
            if generation==self.view_generation:
                status.set_text(f'{count[0]} 项 · 读取未完成：{error}');retry=button('重新读取',lambda *_:self.load_bilibili(kind,fid,title));self.content.pack_start(retry,False,False,0);retry.show()
            self.fail('B 站读取未完成：'+error);return False
        self.message('正在读取 B 站账号…');async_call(fetch,done,failed)

    def open_row(self,idx):
        if self.player:self.player.close();self.player=None
        self.theater=False;self.row_index=idx;item=self.rows[idx];mid=item.get('id');fresh=self.store.get(mid) if mid else None
        if fresh:item={**item,**fresh}
        self.clear_content();nav=Gtk.Box(spacing=8);self.detail_nav=nav;nav.pack_start(button('← 返回列表',lambda *_:self.return_rows()),False,False,0)
        matches=[i for i,row in enumerate(self.rows) if self.rows_query.casefold() in (str(row.get('title') or '')+' '+str(row.get('channel') or '')).casefold()];position=matches.index(idx) if idx in matches else -1
        prev=icon_button('go-previous-symbolic','上一条',lambda *_:self.open_row(matches[position-1]));prev.set_sensitive(position>0);nxt=icon_button('go-next-symbolic','下一条',lambda *_:self.open_row(matches[position+1]));nxt.set_sensitive(0<=position<len(matches)-1);nav.pack_end(nxt,False,False,0);nav.pack_end(prev,False,False,0);self.content.pack_start(nav,False,False,0)
        content=Gtk.Box(spacing=20);left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);content.pack_start(left,True,True,0)
        self.player_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);self.player_box.set_size_request(360,270);self.player_box.get_style_context().add_class('card');self.placeholder=MediaCover();self.player_box.pack_start(self.placeholder,True,True,0);
        if item.get('thumbnail'):self.load_art(self.placeholder,item['thumbnail'])
        left.pack_start(self.player_box,False,False,0)
        row=Gtk.Box(spacing=7)
        local=bool(item.get('path') and Path(item['path']).is_file())
        if local or (item.get('url') and not item.get('unavailable')):
            self.start_button=Gtk.Button();self.start_button.set_image(Gtk.Image.new_from_icon_name('media-playback-start-symbolic',Gtk.IconSize.BUTTON));hint='播放本地文件' if local else '在线播放';self.start_button.set_tooltip_text(hint);self.start_button.get_accessible().set_name(hint);self.start_button.get_style_context().add_class('suggested-action');self.start_button.connect('clicked',lambda b:self.open_player(item['path']) if local else self.open_online(item,b));row.pack_start(self.start_button,False,False,0)
            if not local:row.pack_start(label('在线播放，无需下载','muted'),False,False,0)
            else:row.pack_start(label('来源已失效，播放本地文件' if item.get('unavailable') else '播放本地文件','muted'),False,False,0)
        else:row.pack_start(label('来源视频已失效，无法在线播放或下载' if item.get('unavailable') else '本地文件尚未下载或暂不可用','muted'),False,False,0)
        self.theater_button=icon_button('video-display-symbolic','影院模式',self.toggle_theater);self.fullscreen_button=icon_button('view-fullscreen-symbolic','全屏',self.toggle_fullscreen);row.pack_end(self.fullscreen_button,False,False,0);row.pack_end(self.theater_button,False,False,0);self.mode_row=row;self.control_row=Gtk.EventBox();self.control_row.add(row);self.player_box.pack_start(self.control_row,False,False,0)
        self.detail_left=left
        origin={'local':'本地文件','youtube':'YouTube','bilibili':'B 站'}.get(item.get('source'),'其他来源');left.pack_start(label(item.get('title',''),'title'),False,False,0);left.pack_start(label(' · '.join(x for x in (item.get('channel'),origin) if x),'muted'),False,False,0);meta=label(' · '.join(str(x) for x in (item.get('published'),f"{int(item['duration']//60)}:{int(item['duration']%60):02d}" if item.get('duration') else None) if x) or '时间和时长暂无资料','muted');left.pack_start(meta,False,False,0);left.pack_start(label(item.get('description') or '没有可用的原始简介。'),False,False,0)
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
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(content);self.content.pack_start(scroll,True,True,0);self.content.show_all()
        if item.get('path') and Path(item['path']).is_file():
            generation=self.view_generation
            def show_info(info):
                if generation==self.view_generation:meta.set_text(' · '.join(x for x in (item.get('published'),info) if x))
                return False
            async_call(lambda:local_media_info(item['path']),show_info,lambda _:False)

    def return_rows(self):
        if getattr(self,'active_nav','').startswith('collection:'):self.show_library(int(self.active_nav.split(':',1)[1]),self.rows_query)
        elif getattr(self,'active_nav','')=='library':self.show_library(query=self.rows_query)
        else:self.display_rows(self.rows_title,self.rows,query=self.rows_query)

    def open_player(self,path,stream=None):
        try:
            self.play_request+=1;self.playing_online=stream is not None
            if not self.player:
                player=Player(self.store.setting('volume',100),lambda value:self.store.set_setting('volume',value),self.player_state);self.player_box.remove(self.placeholder)
                self.mode_row.remove(self.theater_button);self.mode_row.remove(self.fullscreen_button)
                player.controls.pack_start(self.theater_button,False,False,0);player.controls.pack_start(self.fullscreen_button,False,False,0)
                self.player_box.remove(self.control_row);self.player=player;self.player_box.pack_start(player,True,True,0);self.player_box.show_all()
            if stream:self.online_resolution=str(stream.get('resolution') or '')[:40];self.player.open_stream(stream['url'],stream['user_agent'],stream.get('audio_url',''),stream.get('referer',''));self.message('正在缓冲在线播放…')
            else:self.player.open(path);self.message('播放中')
        except Exception as e:self.fail(str(e))

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
        async_call(lambda:downloader.online_stream(item['url'],self.store.setting('cookies',False)),done,failed)

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

    def add_url(self,*_):
        d=Gtk.Dialog(title='添加视频链接',transient_for=self,flags=Gtk.DialogFlags.MODAL);d.add_button('取消',Gtk.ResponseType.CANCEL);d.add_button('仅加入媒体库',Gtk.ResponseType.APPLY);d.add_button('在线播放',Gtk.ResponseType.YES);d.add_button('下载',Gtk.ResponseType.OK)
        area=d.get_content_area();area.set_border_width(16);entry=Gtk.Entry();entry.set_width_chars(48);entry.set_placeholder_text('粘贴 YouTube 或 B 站 BV 视频链接');entry.set_activates_default(True);area.pack_start(entry,False,False,0);d.set_default_response(Gtk.ResponseType.YES);d.show_all();response=d.run();url=entry.get_text().strip();d.destroy()
        if response not in (Gtk.ResponseType.APPLY,Gtk.ResponseType.YES,Gtk.ResponseType.OK) or not url:return
        try:identify_url(url)
        except ValueError as exc:self.fail(str(exc));return
        if response==Gtk.ResponseType.OK:self.inspect_and_download(url);return
        generation=self.view_generation;online=response==Gtk.ResponseType.YES;self.message('正在获取在线播放地址…' if online else '正在获取视频资料…')
        def fetch():
            stream=downloader.online_stream(url,self.store.setting('cookies',False)) if online else None
            item=stream['item'] if stream else downloader.inspect(url,self.store.setting('cookies',False))
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
                self.downloader.start(item,self.store.setting('preference','quality'),self.store.setting('cookies',False));self.message('已按下载偏好加入任务')
            except Exception as e:self.fail(str(e))
            return False
        async_call(lambda:downloader.inspect(url,self.store.setting('cookies',False)),ready,lambda error:self.retry_message('获取视频资料失败：'+error,lambda:self.inspect_and_download(url,choose)))

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
                self.downloader.start(item,pref,self.store.setting('cookies',False),fmt or None,audio_only);self.message('下载已加入任务')
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
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(box);self.clear_content();self.content.pack_start(label('下载任务','title'),False,False,0)
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

    def account_text(self,source,state=None,error=''):
        if source=='bilibili' and not self.store.setting('bilibili_cookies',False):return '未授权读取 Chrome 登录状态'
        previous=self.store.setting('account_'+source,{}) or {};when=previous.get('verified_at');name=previous.get('name')
        suffix=(' · '+name if name else '')+(' · 上次验证 '+when if when else '')
        if state=='checking':return '正在验证…'+suffix
        if state=='connected':return '已连接'+suffix
        if state=='unconnected':return '未连接 · 请连接 Google 账号'
        if state=='expired':return '需要重新连接 · 请重新授权'+suffix
        if state=='unknown':return '暂时无法验证'+(' · '+error if error else '')+suffix
        return ('上次验证成功'+suffix) if when else '尚未验证'

    def platform_status(self,source,state=None,error=''):
        b=self.nav_buttons.get('platform-'+source)
        if not b or not b.get_child():return
        title='YouTube' if source=='youtube' else 'B 站';text=self.account_text(source,state,error)
        b.get_child().get_children()[1].set_text(title+('  ●' if state=='connected' else '  ○'))
        b.set_tooltip_text(text);b.get_accessible().set_name(title+' · '+text)

    def check_account(self,source,force=True):
        if source=='bilibili' and not self.store.setting('bilibili_cookies',False):
            self.account_checks[source]+=1;self.account_inflight.pop(source,None);self.account_cache.pop(source,None);self.account_status_widgets[source].set_text(self.account_text(source));self.platform_status(source);return
        self.account_views[source]=self.view_generation
        cached=self.account_cache.get(source)
        if not force and cached and time.monotonic()-cached[0]<300:
            _,state,error=cached;self.account_status_widgets[source].set_text(self.account_text(source,state,error));self.platform_status(source,state,error);return
        if not force and source in self.account_inflight:
            self.account_status_widgets[source].set_text(self.account_text(source,'checking'));self.platform_status(source,'checking');return
        self.account_checks[source]+=1;request=self.account_checks[source];self.account_inflight[source]=request
        self.account_status_widgets[source].set_text(self.account_text(source,'checking'))
        self.platform_status(source,'checking')
        def fetch():
            if source=='youtube':
                values=sources.list_youtube('channel');return ((values[0].get('snippet') or {}).get('title') or '') if values else ''
            values=[];bilibili.stream('status',values.extend);return values[0].get('name','') if values else ''
        def done(name):
            if request!=self.account_checks[source]:return False
            self.account_inflight.pop(source,None);self.account_cache[source]=(time.monotonic(),'connected','')
            self.store.set_setting('account_'+source,{'name':name,'verified_at':datetime.now().strftime('%Y-%m-%d %H:%M')})
            self.platform_status(source,'connected')
            if self.account_views.get(source)==self.view_generation:self.account_status_widgets[source].set_text(self.account_text(source,'connected'))
            return False
        def failed(error):
            if request!=self.account_checks[source]:return False
            self.account_inflight.pop(source,None)
            state='unknown'
            if source=='youtube' and '需要连接 YouTube' in error:
                config=Path(os.environ.get('MEDIADESK_GOOGLE_CONFIG',str(Path.home()/'.config/youtube-readonly')))
                state='expired' if (config/'token.json').exists() else 'unconnected'
            elif source=='youtube' and 'HTTP 401' in error:state='expired'
            error=error if state=='unknown' else '';self.account_cache[source]=(time.monotonic(),state,error)
            self.platform_status(source,state,error)
            if self.account_views.get(source)==self.view_generation:self.account_status_widgets[source].set_text(self.account_text(source,state,error))
            return False
        async_call(fetch,done,failed)

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
            state=label(self.account_text(source),'muted');self.account_status_widgets[source]=state;card.pack_start(state,False,False,0)
            actions=Gtk.Box(spacing=8)
            if source=='youtube':actions.pack_start(button('连接 Google 账号',self.authorize),False,False,0)
            else:
                bili=Gtk.CheckButton(label='允许读取 Chrome 登录状态以获取关注和收藏');bili.set_active(self.store.setting('bilibili_cookies',False))
                def change_bili(w):
                    self.store.set_setting('bilibili_cookies',w.get_active());self.check_account('bilibili')
                bili.connect('toggled',change_bili);card.pack_start(bili,False,False,0)
                card.pack_start(label('关闭后已开始的读取可能继续；已保存的数据仍保留。','muted'),False,False,0)
            actions.pack_start(button('刷新状态',lambda _,s=source:self.check_account(s)),False,False,0);card.pack_start(actions,False,False,0);content.pack_start(card,False,False,0)
        content.pack_start(Gtk.Separator(),False,False,4);content.pack_start(label('下载与播放','section'),False,False,0)
        check=Gtk.CheckButton(label='允许解析、播放和下载时读取 Chrome 登录状态（Cookie）');check.set_active(self.store.setting('cookies',False));check.connect('toggled',lambda w:self.store.set_setting('cookies',w.get_active()));content.pack_start(check,False,False,0)
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
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.add(content);self.clear_content();self.content.pack_start(label('设置','title'),False,False,0);self.content.pack_start(scroll,True,True,0);self.content.show_all()
        self.check_account('youtube',force=False);self.check_account('bilibili',force=False)
    def on_destroy(self,*_):
        if self.player:self.player.close()
        self.thumb_workers.shutdown(wait=False,cancel_futures=True)
        self.downloader.stop_all()
        if Gtk.main_level():Gtk.main_quit()

def main():
    import fcntl
    from .store import data_dir
    root=data_dir();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(root/'application.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        d=Gtk.MessageDialog(message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.OK,text='MediaDesk 已在运行');d.run();d.destroy();os.close(fd);return
    try:
        win=App();win.show_all();Gtk.main()
    finally:os.close(fd)
