import json
from pathlib import Path
import tempfile
import unittest
from mediadesk.oauth_config import import_client, read_client

CLIENT={'installed':{'client_id':'test.apps.googleusercontent.com','client_secret':'synthetic-secret','auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token'}}

class OAuthConfig(unittest.TestCase):
    def test_import_and_repeat_preserves_existing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.json';source.write_text(json.dumps(CLIENT));config=root/'config'
            target=import_client(source,config);before=target.read_bytes()
            self.assertEqual(read_client(target),CLIENT)
            self.assertEqual(import_client(source,config),target)
            other=json.loads(json.dumps(CLIENT));other['installed']['client_id']='other'
            source.write_text(json.dumps(other))
            with self.assertRaisesRegex(ValueError,'已有不同'):import_client(source,config)
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(list(config.iterdir()),[target])

    def test_invalid_and_orphan_token_do_not_change_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.json';config=root/'config'
            for data in ({'web':CLIENT['installed']}, {'type':'service_account'}, {'installed':{}}, {'installed':{**CLIENT['installed'],'token_uri':'https://example.invalid/token'}}, []):
                source.write_text(json.dumps(data))
                with self.assertRaises(ValueError) as caught:import_client(source,config)
                self.assertNotIn('synthetic-secret',str(caught.exception));self.assertFalse(config.exists())
            config.mkdir();token=config/'token.json';token.write_text('synthetic-token')
            source.write_text(json.dumps(CLIENT))
            with self.assertRaisesRegex(ValueError,'已有授权令牌'):import_client(source,config)
            self.assertEqual(token.read_text(),'synthetic-token');self.assertFalse((config/'client.json').exists())

    def test_malformed_and_oversized_errors_do_not_echo_input(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.json'
            for content in ('synthetic-secret', 'x'*65537):
                source.write_text(content)
                with self.assertRaises(ValueError) as caught:read_client(source)
                self.assertNotIn('synthetic-secret',str(caught.exception))

if __name__=='__main__':unittest.main()
