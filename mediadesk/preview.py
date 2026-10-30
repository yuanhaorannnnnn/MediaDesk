"""Silent, bounded hover previews without adding an input window over the card."""
import os
import signal
import subprocess
import threading
from pathlib import Path

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from . import downloader

PREVIEW_WALL_SECONDS = 15


class PreviewCancellation(threading.Event):
    def __init__(self):
        super().__init__();self._lock=threading.Lock();self._process=None

    def bind(self,proc):
        with self._lock:
            self._process=proc
            if self.is_set():self._kill()

    def finish(self,proc):
        with self._lock:
            try:
                if self._process is proc:self._kill()
                return downloader.finish_process(proc)
            finally:
                if self._process is proc:self._process=None

    def _kill(self):
        if self._process:
            try:os.killpg(self._process.pid,signal.SIGKILL)
            except ProcessLookupError:pass

    def set(self):
        with self._lock:
            super().set();self._kill()


class HoverPreview:
    def __init__(self, store):
        self.store = store
        self.cover = self.item = None
        self.timer = 0
        self.serial = 0
        self.resolving = False
        self.resolve_cancel = None
        self.pending = None
        self.process = None
        self.lock = threading.Lock()

    def track(self, button, cover, item):
        button.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        def motion(_, event):
            top = cover.get_toplevel()
            if not isinstance(top, Gtk.Window) or not top.get_window(): return False
            pos = cover.translate_coordinates(top, 0, 0)
            if not pos: return False
            origin = top.get_window().get_origin()[-2:]
            x, y = event.x_root-origin[0]-pos[0], event.y_root-origin[1]-pos[1]
            alloc = cover.get_allocation()
            if 0 <= x < alloc.width and 0 <= y < alloc.height:
                if self.cover is not cover:
                    self.stop(); self.cover = cover; self.item = item
                    self.timer = GLib.timeout_add(650, self.start, self.serial)
            elif self.cover is cover: self.stop()
            return False
        button.connect('motion-notify-event', motion)
        button.connect('enter-notify-event', motion)
        button.connect('leave-notify-event', motion)
        button.connect('destroy', lambda *_: self.stop() if self.cover is cover else None)

    def start(self, serial):
        self.timer = 0
        if serial != self.serial or not self.cover: return False
        item = self.item
        try: fresh = self.store.get(item['id']) if item.get('id') else None
        except Exception: self.stop(); return False
        if fresh: item = {**item, **fresh}
        if item.get('path') and Path(item['path']).is_file():
            self.play(serial, {'path': item['path']})
        elif item.get('url') and not item.get('unavailable'):
            self.pending = (serial, item['url'])
            self.resolve_next()
        return False

    def resolve_next(self):
        if self.resolving or not self.pending: return
        serial, url = self.pending; self.pending = None; self.resolving = True
        cookies = self.store.setting('cookies', False)
        cancel = PreviewCancellation(); self.resolve_cancel = cancel
        def run():
            try: stream = downloader.online_stream(url, cookies, cancel)
            except Exception: stream = None
            GLib.idle_add(self.resolved, serial, stream, cancel)
        threading.Thread(target=run, daemon=True).start()

    def resolved(self, serial, stream, cancel):
        self.resolving = False
        if self.resolve_cancel is cancel: self.resolve_cancel = None
        if stream and serial == self.serial and self.cover: self.play(serial, stream)
        self.resolve_next()
        return False

    def play(self, serial, stream):
        if serial != self.serial or not self.cover: return
        args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-re']
        if stream.get('user_agent'): args += ['-user_agent', stream['user_agent']]
        if stream.get('referer'): args += ['-referer', stream['referer']]
        args += ['-i', stream.get('path') or stream['url'], '-an', '-t', '10', '-vf', 'fps=5,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
        def decode():
            try:
                proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                with self.lock:
                    if serial != self.serial: proc.kill()
                    else: self.process = proc
                def timeout():
                    with self.lock:
                        if self.process is proc and proc.poll() is None:
                            try: proc.kill()
                            except ProcessLookupError: pass
                watchdog = threading.Timer(PREVIEW_WALL_SECONDS, timeout); watchdog.daemon = True; watchdog.start()
                size = 320*180*3
                while True:
                    data = bytearray()
                    while len(data) < size:
                        chunk = proc.stdout.read(size-len(data))
                        if not chunk: break
                        data.extend(chunk)
                    if len(data) != size: break
                    GLib.idle_add(self.frame, serial, bytes(data))
                proc.stdout.close(); proc.wait(); watchdog.cancel()
                with self.lock:
                    if self.process is proc: self.process = None
            except (OSError, ValueError): pass
            GLib.idle_add(self.finish, serial)
        threading.Thread(target=decode, daemon=True).start()

    def frame(self, serial, data):
        if serial != self.serial or not self.cover: return False
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, False, 8, 320, 180, 320*3)
        width = max(1, self.cover.frame.get_allocated_width())
        self.cover.image.set_from_pixbuf(pixbuf.scale_simple(width, max(1, round(width*9/16)), GdkPixbuf.InterpType.BILINEAR))
        return False

    def finish(self, serial):
        if serial == self.serial: self.stop()
        return False

    def stop(self):
        with self.lock:
            self.serial += 1
            proc = self.process; self.process = None
            if proc and proc.poll() is None:
                try: proc.kill()
                except ProcessLookupError: pass
        self.pending = None
        if self.resolve_cancel: self.resolve_cancel.set()
        if self.timer: GLib.source_remove(self.timer); self.timer = 0
        if self.cover:
            if self.cover.pixbuf:
                self.cover.image_size = None
                self.cover.resize_cover(self.cover.frame, self.cover.frame.get_allocation())
            else: self.cover.image.set_from_icon_name('video-x-generic-symbolic', Gtk.IconSize.DIALOG)
        self.cover = self.item = None
        return False
