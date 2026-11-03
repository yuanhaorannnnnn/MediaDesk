import tempfile
import unittest
from unittest.mock import patch
from mediadesk import podcasts, downloader
from mediadesk.store import Store, identify_url

RSS=b'''<rss><channel><title>Example</title><item><title>Audio</title><guid>a</guid><enclosure url="https://cdn.example.com/a.mp3" type="audio/mpeg"/></item><item><title>Video</title><enclosure url="https://cdn.example.com/v.mp4" type="video/mp4"/></item><item><title>Paid</title></item></channel></rss>'''
class Podcasts(unittest.TestCase):
    def setUp(self):
        resolver=patch.object(podcasts.socket,'getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))])
        resolver.start();self.addCleanup(resolver.stop)
    def test_artwork(self):
        xml=RSS.replace(b'<channel>',b'<channel xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><image><url>https://img.example.com/show.jpg</url></image>').replace(b'<title>Audio</title>',b'<title>Audio</title><itunes:image href="https://img.example.com/episode.jpg"/>')
        with patch.object(podcasts,'_read',return_value=(xml,'https://example.com/feed')):
            feed=podcasts.read_feed('https://example.com/feed')
        self.assertEqual(feed['thumbnail'],'https://img.example.com/show.jpg')
        self.assertEqual(feed['episodes'][0]['thumbnail'],'https://img.example.com/episode.jpg')
        self.assertEqual(feed['episodes'][1]['thumbnail'],feed['thumbnail'])
    def test_dns_and_tun_boundary(self):
        with patch.object(podcasts,'getproxies',return_value={}):
            self.assertEqual(podcasts.network_boundary('https://example.com/feed'),'public_dns_preflight')
            with patch.object(podcasts.socket,'getaddrinfo',return_value=[(2,1,6,'',('198.18.0.1',443))]):
                self.assertEqual(podcasts.network_boundary('https://example.com/feed'),'fake_ip_unverified')
        for address in ('127.0.0.1','10.0.0.1','169.254.169.254','::1','fd00::1'):
            with self.subTest(address=address),patch.object(podcasts.socket,'getaddrinfo',return_value=[(2,1,6,'',(address,443))]),self.assertRaises(ValueError):
                podcasts.network_boundary('https://example.com/feed')
        with patch.object(podcasts,'getproxies',return_value={'https':'http://proxy.invalid:8080'}):
            self.assertEqual(podcasts.network_boundary('https://example.com/feed'),'proxy_unverified')
        with patch.object(podcasts.socket,'getaddrinfo',side_effect=OSError),self.assertRaises(ValueError):podcasts.network_boundary('https://example.com/feed')
    def test_feed_limit_and_media(self):
        with patch.object(podcasts,'_read',return_value=(RSS,'https://example.com/feed')):
            feed=podcasts.read_feed('https://example.com/feed',1)
        self.assertEqual(feed['available'],2);self.assertTrue(feed['limited']);self.assertEqual(feed['skipped'],1)
        self.assertIn('不代表完整历史',feed['notice'])
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);mid=store.save_source(feed['episodes'][0])
            self.assertTrue(mid.startswith('podcast:'));self.assertEqual(store.get(mid)['source'],'podcast')
            store.save_source(feed['episodes'][0]);self.assertEqual(len(store.media()),1)
        self.assertEqual(downloader.online_stream(feed['episodes'][0]['url'],True)['audio_url'],'')
    def test_untrusted_sources(self):
        for url in ['file:///a.mp3','http://example.com/a.mp3','https://user:secret@example.com/a.mp3','https://127.0.0.1/a.mp3','https://[::1]/a.mp3','https://localhost/a.mp3','https://example.com/a.html']:
            with self.subTest(url=url),self.assertRaises(ValueError):identify_url(url)
        with patch.object(podcasts,'_read',return_value=(b'<!DOCTYPE rss><rss/>','https://example.com/feed')),self.assertRaises(ValueError):podcasts.read_feed('https://example.com/feed')
    def test_apple_lookup(self):
        with patch.object(podcasts,'_read',return_value=(b'{"results":[{"feedUrl":"https://example.com/feed"}]}','')) as read:
            self.assertEqual(podcasts.resolve_feed('https://podcasts.apple.com/cn/podcast/example/id123?i=45'),'https://example.com/feed')
            self.assertIn('id=123',read.call_args.args[0])
    def test_private_cookies_disabled_for_inspect(self):
        import subprocess
        with patch.object(downloader,'command',return_value=['yt-dlp']) as command,patch.object(downloader.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"title":"Audio","formats":[]}', '')):
            downloader.inspect('https://example.com/a.mp3',True)
        command.assert_called_once_with(False)
class PodcastDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        if os.name=='nt':
            from test_windows_downloads import WindowsDownloads
            cls.helper_class=WindowsDownloads
        else:
            from test_download_reliability import DownloadIntegrationTests
            cls.helper_class=DownloadIntegrationTests
        cls.helper_class.setUpClass()
    @classmethod
    def tearDownClass(cls):cls.helper_class.tearDownClass()
    def setUp(self):
        boundary=patch.object(podcasts,'network_boundary',return_value='public_dns_preflight')
        boundary.start();self.addCleanup(boundary.stop)
        self.case=self.helper_class();self.case.setUp()
    def tearDown(self):self.case.tearDown()
    def test_audio_download_no_browser_cookies(self):
        import json
        case=self.case;case.data=case.audio_only
        with patch('mediadesk.sources.thumbnail') as thumbnail:
            worker=case.worker();worker.start({'url':'https://cdn.example.com/a.m4a?required_token=retained','thumbnail':'https://i.ytimg.com/vi/example/default.jpg'},cookies=True)
            self.assertTrue(case.wait_for(lambda:case.store.jobs()[0]['state'] in ('完成','失败')))
            job=case.store.jobs()[0];self.assertEqual(job['state'],'完成',job['detail'])
            options=json.loads(job['options']);self.assertTrue(options['audio_only']);self.assertFalse(options['cookies'])
            downloader.command.assert_called_once_with(False)
            thumbnail.assert_not_called()
    def test_video_without_audio_download(self):
        import subprocess
        from pathlib import Path
        case=self.case;path=case.root/'silent.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10','-t','1','-an','-c:v','mpeg4',str(path)],check=True)
        case.data=path.read_bytes();worker=case.worker();worker.start({'url':'https://cdn.example.com/v.mp4'})
        self.assertTrue(case.wait_for(lambda:case.store.jobs()[0]['state'] in ('完成','失败')))
        job=case.store.jobs()[0];self.assertEqual(job['state'],'完成',job['detail'])
if __name__=='__main__':unittest.main()
