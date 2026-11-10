import unittest
from content_extractor.network import normalize_url, check_public_addresses, check_media_url

class NetworkTests(unittest.TestCase):
    def test_only_single_supported_posts(self):
        self.assertEqual(normalize_url('https://www.instagram.com/p/DfbNjF_tqQo/?igsh=secret'),('instagram','DfbNjF_tqQo','https://www.instagram.com/p/DfbNjF_tqQo/'))
        for url in ['http://www.instagram.com/p/DfbNjF_tqQo/','https://instagram.com.evil.test/p/DfbNjF_tqQo/','https://a:b@instagram.com/p/DfbNjF_tqQo/','https://instagram.com:444/p/DfbNjF_tqQo/','https://www.instagram.com/travel/','https://youtube.com/playlist?list=x']:
            with self.subTest(url=url),self.assertRaises(ValueError):normalize_url(url)
    def test_private_addresses_and_foreign_media_blocked(self):
        for ip in ['127.0.0.1','169.254.169.254','192.168.0.1','::1']:
            with self.assertRaises(ValueError):check_public_addresses([ip])
        check_public_addresses(['8.8.8.8'])
        with self.assertRaises(ValueError):check_media_url('https://evil.test/video.mp4','instagram')

if __name__=='__main__':unittest.main()
