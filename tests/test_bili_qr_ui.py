"""GTK QR flow with a fake login service, no account or network access."""
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock
import gi
gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0')
from gi.repository import Gtk,Gdk
from mediadesk.app import App
from mediadesk.store import Store
from tests.test_desktop import spin_until

@unittest.skipUnless(Gdk.Display.get_default(), '需要 X11 或 Xvfb')
class QRUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.store.set_setting('setup_done',True);self.w=App(self.store)
    def tearDown(self):
        self.w.destroy();spin_until(lambda:not Gtk.events_pending(),.2);self.tmp.cleanup()
    def module(self,login):
        m=types.ModuleType('mediadesk.bilibili_login');m.QRLogin=lambda:login;return m
    def test_qr_success_uses_qr_credentials_for_bilibili_only(self):
        login=mock.Mock();login.start.return_value={'state':'waiting_scan','qr_url':'https://example.test/fake','expires_in':180};login.poll.return_value={'state':'success'}
        with mock.patch.dict(sys.modules,{'mediadesk.bilibili_login':self.module(login)}),mock.patch.object(self.w,'check_account') as check:
            self.w.select_nav('settings');self.w.show_settings();check.reset_mock();self.w.connect_bilibili_qr()
            self.assertTrue(spin_until(lambda:self.store.setting('bilibili_auth_source')=='qr',4))
            self.assertTrue(self.store.setting('bilibili_cookies',False));check.assert_called_once_with('bilibili')
            self.assertEqual(self.w.playback_cookies('https://www.bilibili.com/video/BV1bK411W797'),'bilibili_qr')
            self.assertFalse(self.w.playback_cookies('https://youtu.be/jNQXAC9IVRw'))
            self.assertFalse(self.w.playback_cookies('https://example.test/test.mp3'))
            self.assertIsNone(self.w.bilibili_qr_dialog);login.cancel.assert_called_once();login.clear_credentials.assert_not_called()
    def test_close_dialog_cancels_inflight_start_and_late_result(self):
        entered=threading.Event();release=threading.Event();login=mock.Mock()
        def start():
            entered.set();release.wait(3);return {'state':'waiting_scan','qr_url':'https://example.test/fake','expires_in':180}
        login.start.side_effect=start
        try:
            with mock.patch.dict(sys.modules,{'mediadesk.bilibili_login':self.module(login)}):
                self.w.connect_bilibili_qr();self.assertTrue(entered.wait(2));self.w.bilibili_qr_dialog.destroy();login.cancel.assert_called_once()
                release.set();spin_until(lambda:False,.15)
                self.assertIsNone(self.w.bilibili_qr_dialog);self.assertFalse(self.store.setting('bilibili_cookies',False));login.poll.assert_not_called()
        finally:release.set()
    def test_scanned_confirmation_then_expiry_is_visible(self):
        login=mock.Mock();login.start.return_value={'state':'waiting_scan','qr_url':'https://example.test/fake','expires_in':180}
        login.poll.side_effect=[{'state':'waiting_confirm'},{'state':'expired'}]
        def texts(widget):
            if isinstance(widget,Gtk.Label):yield widget.get_text()
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():yield from texts(child)
        with mock.patch.dict(sys.modules,{'mediadesk.bilibili_login':self.module(login)}):
            self.w.connect_bilibili_qr();dialog=self.w.bilibili_qr_dialog
            self.assertTrue(spin_until(lambda:'已扫码，请在手机上确认' in list(texts(dialog)),4))
            self.assertTrue(spin_until(lambda:'二维码已过期，请关闭后重新扫码' in list(texts(dialog)),4))
            self.assertFalse(self.store.setting('bilibili_cookies',False));dialog.destroy()

    def test_qr_failure_keeps_dialog_open(self):
        login=mock.Mock();login.start.return_value={'state':'waiting_scan','qr_url':'https://example.test/fake','expires_in':180};login.poll.return_value={'state':'error'}
        def texts(widget):
            if isinstance(widget,Gtk.Label):yield widget.get_text()
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():yield from texts(child)
        with mock.patch.dict(sys.modules,{'mediadesk.bilibili_login':self.module(login)}):
            self.w.connect_bilibili_qr();dialog=self.w.bilibili_qr_dialog
            self.assertTrue(spin_until(lambda:'连接失败，请检查网络后重试' in list(texts(dialog)),4))
            self.assertIs(self.w.bilibili_qr_dialog,dialog);self.assertFalse(self.store.setting('bilibili_cookies',False));dialog.destroy()

    def test_existing_chrome_login_not_replaced_without_confirmation(self):
        self.store.set_setting('bilibili_cookies',True);self.store.set_setting('bilibili_auth_source','chrome')
        with mock.patch('mediadesk.app.Gtk.MessageDialog') as d:
            d.return_value.run.return_value=Gtk.ResponseType.CANCEL;self.w.connect_bilibili_qr()
        self.assertEqual(self.store.setting('bilibili_auth_source'),'chrome');self.assertTrue(self.store.setting('bilibili_cookies'))

if __name__=='__main__':unittest.main()
