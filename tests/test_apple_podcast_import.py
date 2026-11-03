import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mediadesk import apple_podcast_import as importer
from mediadesk import xiaoyuzhou_import


def opml(outlines):
    return '<opml version="2.0"><body>' + outlines + '</body></opml>'


class ApplePodcastImport(unittest.TestCase):
    def test_standard_title_text_and_names_only(self):
        data = opml('<outline text="Folder"><outline text="Text Show" xmlUrl="https://EXAMPLE.com/rss"/></outline>'
                    '<outline title="Title Show" text="Other label" description="Description"/>'
                    '<outline text="Name only"/>')
        with patch.object(socket, 'getaddrinfo', side_effect=AssertionError('network')):
            result = importer.parse_import(data)
        self.assertEqual([r['title'] for r in result['entries']], ['Text Show', 'Title Show', 'Name only'])
        self.assertEqual(result['entries'][0]['description'], '')
        self.assertEqual(result['entries'][0]['feed_url'], 'https://example.com/rss')
        self.assertEqual(result['entries'][1]['description'], 'Description')
        self.assertEqual(result['entries'][1]['source_url'], '')

    def test_duplicate_urls_but_preserve_same_names(self):
        data = opml('<outline text="Same"/><outline text="Same"/>'
                    '<outline text="Same" xmlUrl="https://example.com/new"/>'
                    '<outline text="Other" xmlUrl="https://EXAMPLE.com/old"/>'
                    '<outline text="Again" xmlUrl="https://example.com/new"/>')
        result = importer.parse_import(data, ['https://example.com/old'], ['Same'])
        self.assertEqual(len(result['entries']), 3)
        self.assertEqual(result['duplicates'], 2)
        self.assertTrue(all(r['name_conflict'] for r in result['entries']))
        self.assertEqual([r['index'] for r in result['entries']], [1, 2, 3])

    def test_ids_survive_reordering_and_distinguish_same_names(self):
        first = importer.parse_opml(opml('<outline text="Same"/><outline text="Same"/>'
                                        '<outline text="Other"/>'))['entries']
        second = importer.parse_opml(opml('<outline text="Other"/><outline text="Same"/>'
                                         '<outline text="Same"/>'))['entries']
        self.assertEqual({r['program_id'] for r in first}, {r['program_id'] for r in second})
        self.assertEqual(len({r['program_id'] for r in first}), 3)
        self.assertTrue(all(r['source'] == 'apple-podcasts' for r in first))

    def test_invalid_rows_and_unsafe_urls_are_visible(self):
        result = importer.parse_opml(opml('<outline/><outline text="Private" xmlUrl="https://user:secret@127.0.0.1/rss"/>'
                                          '<outline text="HTTP" xmlUrl="file:///example.com/rss"/>'))
        self.assertEqual(result['entries'], [])
        self.assertEqual(result['skipped'], 3)
        self.assertEqual(len(result['issues']), 3)

    def test_http_local_identity_and_credentials_redacted(self):
        with patch.object(socket, 'getaddrinfo', side_effect=AssertionError('network')):
            result = importer.parse_opml(opml('<outline text="HTTP" xmlUrl="http://EXAMPLE.com:80/rss"/>'
                                              '<outline text="Secret" xmlUrl="http://user:secret@127.0.0.1/rss"/>'))
        self.assertEqual(result['entries'][0]['feed_url'], 'http://example.com/rss')
        self.assertFalse(result['entries'][0]['identity_ambiguous'])
        self.assertEqual(result['skipped'], 1)
        self.assertNotIn('secret', str(result))
        self.assertNotIn('127.0.0.1', str(result))
        self.assertEqual(importer.parse_opml(opml('<outline text="HTTP" xmlUrl="http://example.com/rss"/>'),
                         ['http://EXAMPLE.com:80/rss'])['duplicates'], 1)

    def test_xml_safety_and_limits(self):
        for data in ['<!DOCTYPE opml><opml/>', '<!DOCTYPE opml><opml/>'.encode('utf-16'),
                     '<rss/>', '<broken', ' ' * (importer.MAX_OPML + 1),
                     opml('<outline/>' * (importer.MAX_ENTRIES + 1))]:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                importer.parse_import(data)

    def test_shortcut_opml_escaped_names_and_invalid_xml(self):
        data = opml('<outline title="A &amp; B &quot;show&quot;" text="A &amp; B &quot;show&quot;" '
                    'xmlUrl="https://example.com/rss?a=1&amp;b=2"/>'
                    '<outline title="No RSS &lt;show&gt;" text="No RSS &lt;show&gt;"/>')
        result = importer.parse_import(data)
        self.assertEqual(result['entries'][0]['title'], 'A & B "show"')
        self.assertEqual(result['entries'][0]['feed_url'], 'https://example.com/rss?a=1&b=2')
        self.assertEqual(result['entries'][1]['title'], 'No RSS <show>')
        broken = opml('<outline title="A & B"/>')
        with self.assertRaisesRegex(ValueError, '无法解析 OPML'):
            importer.parse_import(broken)
        self.assertIn('A & B', broken)

    def test_only_reads_selected_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'selected.opml'
            path.write_text(opml('<outline text="Show"/>'))
            self.assertEqual(importer.read_import(path)['entries'][0]['title'], 'Show')
            self.assertEqual(path.read_text(), opml('<outline text="Show"/>'))

    def test_search_reuses_existing_explicit_action_boundary(self):
        self.assertIs(importer.search_youtube_candidates, xiaoyuzhou_import.search_youtube_candidates)
        self.assertIs(importer.resolve_channel_uploads, xiaoyuzhou_import.resolve_channel_uploads)
        with self.assertRaises(ValueError):
            importer.search_youtube_candidates('Show')


if __name__ == '__main__':
    unittest.main()
