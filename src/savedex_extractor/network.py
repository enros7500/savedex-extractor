import socket,ssl,http.client,ipaddress,re,json
from urllib.parse import urlsplit,urljoin,parse_qs

def normalize_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):raise ValueError('Only public HTTPS platform URLs are supported')
    host=(p.hostname or '').lower()
    if host in ['instagram.com','www.instagram.com','m.instagram.com']:
        m=re.fullmatch(r'/(?:p|reel|reels)/([A-Za-z0-9_-]{11})/?',p.path)
        if not m:raise ValueError('An individual Instagram post is required')
        code=m[1];return 'instagram',code,'https://www.instagram.com/p/'+code+'/'
    if host in ['youtube.com','www.youtube.com','m.youtube.com','youtu.be','www.youtu.be']:
        code=p.path.strip('/') if host.endswith('youtu.be') else (parse_qs(p.query).get('v',[''])[0] if p.path=='/watch' else (p.path.split('/')[2] if re.fullmatch(r'/shorts/[A-Za-z0-9_-]{11}/?',p.path) else ''))
        if not re.fullmatch('[A-Za-z0-9_-]{11}',code):raise ValueError('An individual YouTube video is required')
        return 'youtube',code,'https://www.youtube.com/watch?v='+code
    raise ValueError('Platform host is not supported')
def check_public_addresses(addresses):
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('Private or non-public destination prohibited')
def allowed(host,suffixes):return any(host==suffix or host.endswith('.'+suffix) for suffix in suffixes)
def check_media_url(url,platform):
    p=urlsplit(url)
    suffixes=['cdninstagram.com','fbcdn.net','instagram.com'] if platform=='instagram' else ['googlevideo.com','ytimg.com','youtube.com','googleusercontent.com']
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not allowed(p.hostname or '',suffixes):raise ValueError('Media destination not allowed')
    return p
class PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses=socket.getaddrinfo(self.host,self.port,type=socket.SOCK_STREAM)
        check_public_addresses([x[4][0] for x in addresses])
        last=None
        for family,kind,proto,_,address in addresses:
            raw=socket.socket(family,kind,proto);raw.settimeout(self.timeout)
            try:
                raw.connect(address);self.sock=self._context.wrap_socket(raw,server_hostname=self.host);return
            except OSError as e:last=e;raw.close()
        raise last or OSError('No public address available')
def fetch(url,platform,max_bytes=3_000_000,timeout=25,destination=None):
    for _ in range(5):
        p=check_media_url(url,platform)
        conn=PinnedHTTPS(p.hostname,port=443,timeout=timeout,context=ssl.create_default_context())
        try:
            conn.request('GET',p.path+('?' +p.query if p.query else ''),headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise OSError('Redirect without location')
                url=urljoin(url,location);continue
            if response.status!=200:raise OSError('Platform returned HTTP '+str(response.status))
            size=int(response.getheader('Content-Length') or 0)
            if size>max_bytes:raise ValueError('Resource byte limit exceeded')
            content=bytearray();size=0
            handle=open(destination,'wb') if destination else None
            try:
                while chunk:=response.read(128*1024):
                    size+=len(chunk)
                    if size>max_bytes:raise ValueError('Resource byte limit exceeded')
                    if handle:handle.write(chunk)
                    else:content.extend(chunk)
            finally:
                if handle:handle.close()
            return bytes(content) if not destination else size
        finally:conn.close()
    raise OSError('Too many redirects')
