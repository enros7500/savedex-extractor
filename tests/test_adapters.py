import unittest,json,sys,os
from unittest.mock import patch
from types import SimpleNamespace
from savedex_extractor.adapters import parse_instagram

class AdapterTests(unittest.TestCase):
    def test_nested_embed_and_image_inventory(self):
        code='ABCDEFGHIJK'
        node={'shortcode':code,'owner':{'username':'author'},'edge_media_to_caption':{'edges':[{'node':{'text':'Five things'}}]},'edge_sidecar_to_children':{'edges':[{'node':{'display_url':'https://cdninstagram.com/a.jpg'}},{'node':{'is_video':True,'video_url':'https://cdninstagram.com/v.mp4','video_duration':2}}]}}
        embedded=json.dumps({'data':json.dumps({'media':node})})
        page='<script>var s={};s.handle('+embedded+');</script>'
        bundle=parse_instagram(page,code)
        self.assertEqual([a['kind'] for a in bundle['assets']],['image','video'])
        self.assertEqual([a['index'] for a in bundle['assets']],[1,2])
        self.assertEqual(bundle['description'],'Five things')
    def test_login_page_does_not_invent_metadata(self):
        with self.assertRaises(OSError):parse_instagram('<html>Login</html>','ABCDEFGHIJK')
    def test_youtube_disables_plugins_and_browser_credentials(self):
        from savedex_extractor.adapters import obtain
        options={}
        class FakeDL:
            def __init__(self,params):options.update(params)
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def extract_info(self,*args,**kw):return {'url':'https://r.googlevideo.com/media','duration':2,'description':'Demo','uploader':'Example'}
        with patch.dict(sys.modules,{'yt_dlp':SimpleNamespace(YoutubeDL=FakeDL)}),patch.dict(os.environ,{},clear=False):
            obtain('https://www.youtube.com/watch?v=ABCDEFGHIJK','unused')
            self.assertEqual(os.environ.get('YTDLP_NO_PLUGINS'),'1')
            self.assertEqual(options['allowed_extractors'],['youtube'])
            self.assertIsNone(options['cookiefile']);self.assertIsNone(options['cookiesfrombrowser'])

if __name__=='__main__':unittest.main()
