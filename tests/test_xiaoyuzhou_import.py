import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from mediadesk import xiaoyuzhou_import as importer


def opml(outlines):
    return ('<opml version="2.0"><body>' + outlines + '</body></opml>').encode()


class XiaoyuzhouImport(unittest.TestCase):
    def test_local_preview_fields_folders_and_duplicates(self):
        data = opml('<outline text="Folder"><outline title="Show" text="Description" xmlUrl="https://EXAMPLE.com/rss"/></outline>'
                    '<outline title="Again" xmlUrl="https://example.com/rss"/>'
                    '<outline text="Description only" xmlUrl="https://example.com/other"/>'
                    '<outline title="Private" xmlUrl="https://127.0.0.1/rss"/>')
        with patch.object(importer, '_search_api', side_effect=AssertionError('network')):
            result = importer.parse_opml(data)
        self.assertEqual(result['entries'], [{'title': 'Show', 'description': 'Description',
                         'feed_url': 'https://example.com/rss', 'source_url': 'https://example.com/rss'}])
        self.assertEqual(result['duplicates'], 1)
        self.assertEqual(result['skipped'], 2)
        self.assertEqual(importer.parse_opml(data, ['https://example.com/rss'])['entries'], [])

    def test_safe_xml_and_limits(self):
        for data in [b'<!DOCTYPE opml [<!ENTITY x "bad">]><opml/>',
                     '<!DOCTYPE opml><opml/>'.encode('utf-16'), b'<broken', b'<rss/>',
                     b' ' * (importer.MAX_OPML + 1), opml('<outline/>' * 2001)]:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                importer.parse_opml(data)

    def test_read_explicit_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'selected.opml'
            path.write_bytes(opml('<outline title="Show" xmlUrl="https://example.com/rss"/>'))
            self.assertEqual(importer.read_opml(path)['entries'][0]['title'], 'Show')

    def test_explicit_search_one_request_no_binding(self):
        request = Mock(return_value={'items': [
            {'id': {'channelId': 'UC_123'}, 'snippet': {'title': 'A &amp; B', 'channelTitle': 'Show'}},
            {'id': {'playlistId': 'PL123'}, 'snippet': {'title': 'Playlist'}},
            {'id': {'videoId': 'abc123'}, 'snippet': {'title': 'Guest appearance'}},
            {'id': {'videoId': '../bad'}, 'snippet': {}}]})
        with self.assertRaises(ValueError):
            importer.search_youtube_candidates('Show', api_request=request)
        request.assert_not_called()
        result = importer.search_youtube_candidates('Show', user_triggered=True, api_request=request)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0]['maxResults'], 5)
        self.assertEqual([c['kind'] for c in result['candidates']], ['channel', 'playlist', 'video'])
        self.assertTrue(all(not c['confirmed'] for c in result['candidates']))
        self.assertEqual(result['candidates'][0]['title'], 'A & B')

    def test_resolve_channel_requires_action_and_returns_uploads(self):
        request = Mock(return_value={'items': [{'id': 'UC123', 'contentDetails':
                        {'relatedPlaylists': {'uploads': 'UU123'}}}]})
        with self.assertRaises(ValueError):
            importer.resolve_channel_uploads('UC123', api_request=request)
        request.assert_not_called()
        self.assertEqual(importer.resolve_channel_uploads('UC123', user_triggered=True,
                         api_request=request), 'UU123')
        request.assert_called_once_with({'part': 'contentDetails', 'id': 'UC123'})

    def test_resolve_channel_rejects_invalid_missing_and_error(self):
        request = Mock()
        with self.assertRaises(ValueError):
            importer.resolve_channel_uploads('../bad', user_triggered=True, api_request=request)
        request.assert_not_called()
        for body in [None, {'error': {'message': 'secret token'}}, {'items': []},
                     {'items': [{'id': 'other', 'contentDetails': {'relatedPlaylists': {'uploads': 'UU123'}}}]},
                     {'items': [{'id': 'UC123', 'contentDetails': {'relatedPlaylists': {'uploads': '../bad'}}}]}]:
            with self.subTest(body=body), self.assertRaises(ValueError) as error:
                importer.resolve_channel_uploads('UC123', user_triggered=True,
                                                api_request=Mock(return_value=body))
            self.assertNotIn('secret', str(error.exception))
        request = Mock(side_effect=RuntimeError('secret token'))
        with self.assertRaises(ValueError) as error:
            importer.resolve_channel_uploads('UC123', user_triggered=True, api_request=request)
        self.assertNotIn('secret', str(error.exception))
        request.assert_called_once()

    def test_resolve_channel_uses_channels_endpoint(self):
        with patch.object(importer, '_search_api', return_value={'items': [
                {'id': 'UC123', 'contentDetails': {'relatedPlaylists': {'uploads': 'UU123'}}}]}) as api:
            self.assertEqual(importer.resolve_channel_uploads('UC123', user_triggered=True), 'UU123')
        api.assert_called_once_with({'part': 'contentDetails', 'id': 'UC123'}, 'channels')

    def test_quota_no_retry(self):
        request = Mock(return_value={'error': {'code': 403, 'message': 'quotaExceeded'}})
        with self.assertRaisesRegex(ValueError, '配额'):
            importer.search_youtube_candidates('Show', user_triggered=True, api_request=request)
        request.assert_called_once()

    def test_helper_timeout_is_safe(self):
        import subprocess
        with patch('mediadesk.sources.helper_python', return_value='/usr/bin/python3'), \
             patch.object(importer.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['secret'], 60)):
            with self.assertRaises(ValueError) as error:
                importer.search_youtube_candidates('Show', user_triggered=True)
        self.assertNotIn('secret', str(error.exception))

    def test_helper_errors_do_not_expose_credentials(self):
        with patch('mediadesk.sources.helper_python', return_value='/usr/bin/python3'), \
             patch.object(importer.subprocess, 'run', return_value=Mock(returncode=1, stderr='secret token')):
            with self.assertRaisesRegex(ValueError, '配额') as error:
                importer.search_youtube_candidates('Show', user_triggered=True)
        self.assertNotIn('secret', str(error.exception))


if __name__ == '__main__':
    unittest.main()
