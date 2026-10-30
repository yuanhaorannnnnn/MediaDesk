"""Exercise video pixels through the real GTK/libVLC loopback playback path."""
import ctypes
import functools
import http.server
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk

from mediadesk.app import App
from mediadesk.store import Store
import mediadesk.player as vlc


def spin_until(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        if predicate():
            return True
        time.sleep(.02)
    return False


def has_color_pixels(area):
    allocation = area.get_allocation()
    window = area.get_window()
    if not window or allocation.width < 10 or allocation.height < 10:
        return False
    image = Gdk.pixbuf_get_from_window(window, 0, 0, allocation.width, allocation.height)
    if not image:
        return False
    data, stride, channels = image.get_pixels(), image.get_rowstride(), image.get_n_channels()
    pixels = []
    for y in range(5, allocation.height, 20):
        for x in range(5, allocation.width, 20):
            offset = y * stride + x * channels
            pixel = data[offset:offset + channels]
            # RGB values alone can pass while RGBA output is fully transparent.
            if channels == 4 and pixel[3] < 250:
                return False
            pixels.append(pixel[:3])
    return bool(pixels) and sum(max(rgb) - min(rgb) > 50 for rgb in pixels) / len(pixels) > .2


@unittest.skipUnless(Gdk.Display.get_default() and shutil.which('ffmpeg'), '需要 X11/Xvfb 和 FFmpeg')
class PlayerRenderingTests(unittest.TestCase):
    def test_loopback_video_renders_after_window_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / 'sample.mp4'
            result = subprocess.run([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15',
                '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                '-t', '12', '-c:v', 'libx264', '-preset', 'ultrafast',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart',
                '-shortest', str(video),
            ], capture_output=True, text=True)
            if result.returncode:
                self.skipTest('本机 FFmpeg 无法生成测试媒体')

            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *_):
                    pass

            server = http.server.ThreadingHTTPServer(
                ('127.0.0.1', 0), functools.partial(QuietHandler, directory=temporary))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            store = Store(root / 'data')
            store.set_setting('setup_done', True)
            store.save_youtube({'url': 'https://youtu.be/jNQXAC9IVRw', 'title': '隔离测试'})
            original_new = vlc._new

            def silent_new(_count, _args):
                options = [_args[i] for i in range(_count)] + [b'--aout=dummy']
                args = (ctypes.c_char_p * len(options))(*options)
                return original_new(len(options), args)

            window = None
            try:
                with mock.patch.object(App, 'check_account'), mock.patch.object(vlc, '_new', silent_new):
                    window = App(store)
                    window.resize(1000, 700)
                    window.show_library()
                    window.open_row(0)
                    window.open_player(None, {'url': f'http://127.0.0.1:{server.server_port}/sample.mp4', 'user_agent': ''})
                    self.assertTrue(spin_until(lambda: vlc._time(window.player.player) > 500 and has_color_pixels(window.player.area)), '在线播放应显示视频画面')
                    before = vlc._time(window.player.player)
                    old_area = window.player.area.get_allocation()
                    old_width, old_height = old_area.width, old_area.height
                    self.assertTrue(spin_until(lambda: abs(window.player.area.get_allocation().height - round(old_width * 9 / 16)) <= 1), '普通窗口的视频区域应适应 16:9')
                    window.toggle_theater()
                    window.resize(1500, 950)
                    self.assertTrue(spin_until(lambda: window.player.area.get_allocation().width > old_width and window.player.area.get_allocation().height > old_height and vlc._time(window.player.player) > before + 500 and has_color_pixels(window.player.area)), '调整窗口后视频区域应变大并继续播放')
            finally:
                if window:
                    window.destroy()
                    spin_until(lambda: not Gtk.events_pending(), .5)
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_av1_video_is_visible_in_rgba_toplevel(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / 'av1.mkv'
            result = subprocess.run([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15',
                '-t', '10', '-c:v', 'libaom-av1', '-cpu-used', '8',
                '-pix_fmt', 'yuv420p', str(video),
            ], capture_output=True, text=True)
            if result.returncode:
                self.skipTest('本机 FFmpeg 无法生成 AV1 样本')
            window = Gtk.Window()
            rgba = window.get_screen().get_rgba_visual()
            if rgba is None:
                window.destroy()
                self.skipTest('当前 X11 显示不支持 RGBA visual')
            window.set_visual(rgba)
            window.set_titlebar(Gtk.HeaderBar(title='RGBA playback regression'))
            window.set_accept_focus(False)
            window.set_focus_on_map(False)
            player = vlc.Player(volume=0)
            window.add(player)
            try:
                window.show_all()
                player.open(str(video))
                self.assertTrue(spin_until(lambda: has_color_pixels(player.area)),
                                'AV1 必须有可见且不透明的画面，不能仅有播放时间推进')
            finally:
                player.close()
                window.destroy()


if __name__ == '__main__':
    unittest.main()
