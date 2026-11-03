"""No browser is opened; exercise Windows SDK callback with synthetic URLs."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import webbrowser
from mediadesk import oauth_bridge as bridge

PRIVATE='http://localhost/?code=PRIVATE&state=PRIVATE'

class BrowserLaunch(unittest.TestCase):
    def test_failed_controller_is_actionable_and_private(self):
        for outcome in (False,OSError(PRIVATE),webbrowser.Error(PRIVATE)):
            controller=Mock()
            if isinstance(outcome,Exception):controller.open.side_effect=outcome
            else:controller.open.return_value=outcome
            with self.subTest(outcome=type(outcome).__name__),self.assertRaises(bridge.SafeOAuthError) as caught:
                bridge.CheckedBrowser(controller).open(PRIVATE,new=1,autoraise=True)
            message=bridge.error_message(caught.exception)
            self.assertIn('默认浏览器',message);self.assertNotIn('PRIVATE',message);self.assertNotIn('localhost',message)

    def test_success_forwards_url_without_printing(self):
        controller=Mock();controller.open.return_value=True
        self.assertTrue(bridge.CheckedBrowser(controller).open(PRIVATE,new=1,autoraise=True))
        controller.open.assert_called_once_with(PRIVATE,new=1,autoraise=True)

    def test_windows_sdk_false_launch_stops_instead_of_waiting(self):
        controller=Mock();controller.open.return_value=False;controllers={}
        def register(name,klass,instance):controllers[name]=instance
        def sdk(**kwargs):
            controllers[kwargs['browser']].open(PRIVATE,new=1,autoraise=True)
            self.fail('SDK should never reach callback waiting')
        flow=Mock();flow.run_local_server.side_effect=sdk
        with patch.object(bridge,'os',SimpleNamespace(name='nt')),patch.object(bridge.webbrowser,'get',return_value=controller),patch.object(bridge.webbrowser,'register',side_effect=register):
            with self.assertRaises(bridge.SafeOAuthError):bridge.run_authorization(flow)
        controller.open.assert_called_once()

    def test_no_default_browser_stops_before_sdk(self):
        flow=Mock()
        with patch.object(bridge,'os',SimpleNamespace(name='nt')),patch.object(bridge.webbrowser,'get',side_effect=webbrowser.Error(PRIVATE)):
            with self.assertRaisesRegex(bridge.SafeOAuthError,'默认浏览器'):bridge.run_authorization(flow)
        flow.run_local_server.assert_not_called()

    def test_non_windows_retains_existing_call(self):
        flow=Mock()
        with patch.object(bridge,'os',SimpleNamespace(name='posix')):
            self.assertIs(bridge.run_authorization(flow),flow.run_local_server.return_value)
        self.assertNotIn('browser',flow.run_local_server.call_args.kwargs)

if __name__=='__main__':unittest.main()
