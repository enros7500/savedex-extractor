import json,re,os
from html.parser import HTMLParser
from pathlib import Path
from .network import fetch,normalize_url

class Scripts(HTMLParser):
    def __init__(self):super().__init__();self.active=False;self.buffer=[];self.scripts=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script':self.active=True;self.buffer=[]
    def handle_data(self,data):
        if self.active:self.buffer.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.active:self.scripts.append(''.join(self.buffer));self.active=False
def parse_instagram(page,code):
    parser=Scripts();parser.feed(page);found=[]
    def walk(v):
        if isinstance(v,dict):
            if v.get('shortcode')==code and ('video_url' in v or 'display_url' in v or 'edge_sidecar_to_children' in v):found.append(v)
            for x in v.values():walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
        elif isinstance(v,str) and v.lstrip().startswith(('{','[')):
            try:walk(json.loads(v))
            except ValueError:pass
    decoder=json.JSONDecoder()
    for script in parser.scripts:
        try:walk(json.loads(script))
        except ValueError:pass
        for match in re.finditer(r's\.handle\(',script):
            try:value,_=decoder.raw_decode(script[match.end():]);walk(value)
            except ValueError:pass
    if not found:raise OSError('Public post media unavailable; login may be required')
    node=found[0];children=node.get('edge_sidecar_to_children',{}).get('edges',[])
    nodes=[e['node'] for e in children] if children else [node]
    assets=[]
    for i,a in enumerate(nodes,1):
        is_video=bool(a.get('is_video') or a.get('video_url'))
        assets.append({'id':'asset'+str(i),'index':i,'kind':'video' if is_video else 'image','duration_ms':round(a['video_duration']*1000) if a.get('video_duration') is not None else None,'available':bool(a.get('video_url') if is_video else a.get('display_url')),'processed':False,'media_url':a.get('video_url') if is_video else a.get('display_url')})
    captions=node.get('edge_media_to_caption',{}).get('edges',[])
    return {'author':node.get('owner',{}).get('username'),'description':captions[0]['node']['text'] if captions else '', 'assets':assets,'inventory_complete':True}
def obtain(url,job):
    platform,code,canonical=normalize_url(url)
    if platform=='instagram':
        page=fetch(canonical+'embed/captioned/',platform).decode('utf-8','replace')
        bundle=parse_instagram(page,code)
    else:
        os.environ['YTDLP_NO_PLUGINS']='1'
        import yt_dlp
        from .network import check_media_url
        with yt_dlp.YoutubeDL({'quiet':True,'no_warnings':True,'noplaylist':True,'allowed_extractors':['youtube'],'skip_download':True,'cachedir':False,'proxy':'','cookiefile':None,'cookiesfrombrowser':None,'socket_timeout':20,'format':'bestaudio/best','logger':QuietLogger()}) as dl:
            info=dl.extract_info(canonical,download=False)
        media=info.get('url') or (info.get('requested_downloads') or [{}])[0].get('url')
        if not media:raise OSError('Anonymous YouTube media unavailable')
        check_media_url(media,'youtube')
        bundle={'author':info.get('uploader'),'description':(info.get('description') or '')[:20000],'inventory_complete':True,'assets':[{'id':'asset1','index':1,'kind':'video','duration_ms':round(info['duration']*1000) if info.get('duration') is not None else None,'available':True,'processed':False,'media_url':media}]}
    if len(bundle['assets'])>20:bundle['assets']=bundle['assets'][:20];bundle['inventory_complete']=False
    for a in bundle['assets']:
        if a['duration_ms'] is not None and a['duration_ms']>300000:raise ValueError('Video duration exceeds five minute limit')
    bundle.update(platform=platform,post_id=code,canonical_url=canonical)
    return bundle
class QuietLogger:
    def debug(self,*args):pass
    def warning(self,*args):pass
    def error(self,*args):pass
def download_asset(asset,platform,job,remaining_bytes):
    if not asset['available']:raise OSError('Asset not publicly available')
    path=Path(job)/(asset['id']+('.media' if asset['kind']=='video' else '.image'))
    size=fetch(asset['media_url'],platform,max_bytes=remaining_bytes,timeout=30,destination=path)
    return path,size
