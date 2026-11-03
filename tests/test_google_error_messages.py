"""Typed synthetic errors: never start a browser or access a real token."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import requests
from oauthlib.oauth2.rfc6749 import errors
from mediadesk import oauth_bridge as bridge

PRIVATE='https://localhost/callback?code=PRIVATE&state=PRIVATE token=PRIVATE secret=PRIVATE'

class GoogleErrors(unittest.TestCase):
    def test_fixed_typed_errors_do_not_echo_details(self):
        class CallbackTimeout(Exception):pass
        cases=[(errors.AccessDeniedError(description=PRIVATE),'未获得'),(errors.MismatchingStateError(description=PRIVATE),'不匹配'),(CallbackTimeout(PRIVATE),'5 分钟'),(errors.InvalidClientError(description=PRIVATE),'客户端配置'),(errors.InvalidClientIdError(description=PRIVATE),'客户端配置'),(errors.UnauthorizedClientError(description=PRIVATE),'客户端配置'),(errors.InvalidGrantError(description=PRIVATE),'本次授权凭据'),(requests.exceptions.ProxyError(PRIVATE),'代理'),(requests.exceptions.SSLError(PRIVATE),'网络通信'),(requests.exceptions.Timeout(PRIVATE),'网络通信'),(requests.exceptions.HTTPError(PRIVATE),'原因暂未识别'),(ValueError(PRIVATE),'原因暂未识别'),(errors.OAuth2Error(description=PRIVATE),'原因暂未识别')]
        with patch.object(bridge.google_flow,'WSGITimeoutError',CallbackTimeout,create=True):
            for exc,expected in cases:
                with self.subTest(type=type(exc).__name__):
                    message=bridge.error_message(exc)
                    self.assertIn(expected,message)
                    for secret in ('PRIVATE','localhost','code=','state=','token=','secret='):self.assertNotIn(secret,message)

    def test_wrapped_error_and_cycle(self):
        outer=RuntimeError(PRIVATE);outer.__cause__=requests.exceptions.ProxyError(PRIVATE)
        self.assertIn('代理',bridge.error_message(outer))
        outer.__cause__=outer;self.assertIn('原因暂未识别',bridge.error_message(outer))

    def test_missing_configuration_is_actionable_without_browser(self):
        with tempfile.TemporaryDirectory() as root,patch.object(bridge,'CONFIG',Path(root)),patch.object(bridge.InstalledAppFlow,'from_client_secrets_file') as flow:
            with self.assertRaises(bridge.SafeOAuthError) as caught:bridge.credentials(True)
            self.assertIn('先导入',bridge.error_message(caught.exception));flow.assert_not_called()

    def test_corrupt_token_valueerror_is_not_public(self):
        with tempfile.TemporaryDirectory() as root,patch.object(bridge,'CONFIG',Path(root)):
            (Path(root)/'token.json').write_text('{}')
            with patch.object(bridge.Credentials,'from_authorized_user_file',side_effect=ValueError(PRIVATE)):
                with self.assertRaises(ValueError) as caught:bridge.credentials(True)
            self.assertIn('原因暂未识别',bridge.error_message(caught.exception));self.assertNotIn('PRIVATE',bridge.error_message(caught.exception))

if __name__=='__main__':unittest.main()
