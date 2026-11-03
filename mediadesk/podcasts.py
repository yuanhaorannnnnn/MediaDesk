"""Anonymous Apple public directory and public RSS enclosures; no account cookies."""
import hashlib
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse, urlencode, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler, getproxies
import xml.etree.ElementTree as ET

MAX_FEED = 32 * 1024 * 1024
MEDIA_EXTENSIONS = {'mp3','mp4','m4a','m4v','ogg','oga','opus','wav','webm','aac','mov'}


def public_url(url):
    p=urlparse(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError('仅支持无账号凭据的公开 HTTPS 来源')
    if p.port not in (None,443):raise ValueError('播客来源仅支持 HTTPS 默认端口')
    host=p.hostname.lower()
    if host=='localhost' or host.endswith(('.localhost','.local')):raise ValueError('不支持本机或私有网络来源')
    try:address=ipaddress.ip_address(host)
    except ValueError:address=None
    if address is not None and not address.is_global:raise ValueError('不支持本机或私有网络来源')
    return url


def network_boundary(url):
    """Reject known private DNS; fake-IP/proxies remain a local trust boundary.

    This is preflight, not DNS pinning: yt-dlp/VLC and the local proxy can resolve
    later redirects independently. Never report it as complete SSRF isolation.
    """
    public_url(url);host=urlparse(url).hostname
    try:addresses={ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
    except (OSError,ValueError):raise ValueError('无法解析播客来源地址，请检查 DNS 或本机代理') from None
    if not addresses:raise ValueError('播客来源没有可用 DNS 地址')
    fake=ipaddress.ip_network('198.18.0.0/15')
    if any(not address.is_global and address not in fake for address in addresses):
        raise ValueError('播客来源 DNS 指向已识别的本机或私有网络，已拒绝请求')
    if any(address in fake for address in addresses):return 'fake_ip_unverified'
    proxies=getproxies()
    if proxies.get('https') or proxies.get('all'):return 'proxy_unverified'
    return 'public_dns_preflight'


def artwork(node, base):
    image=node.find('{http://www.itunes.com/dtds/podcast-1.0.dtd}image')
    value=(image.get('href') if image is not None else '') or node.findtext('image/url') or ''
    if not value:return ''
    try:return public_url(urljoin(base,value))
    except ValueError:return ''


def enclosure_identity(url):
    public_url(url)
    if urlparse(url).path.rsplit('.',1)[-1].lower() not in MEDIA_EXTENSIONS:
        raise ValueError('请输入支持的公开音频或视频文件链接')
    sid=hashlib.sha256(url.encode()).hexdigest()[:32]
    return {'source':'podcast','id':sid,'file_id':sid,'url':url}


def _read(url, limit=MAX_FEED):
    network_boundary(url)
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            network_boundary(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    try:
        with build_opener(Redirect).open(Request(url,headers={'User-Agent':'MediaDesk/1','Accept':'application/rss+xml, application/json, application/xml'}),timeout=25) as response:
            data=response.read(limit+1);final=response.url
    except Exception as exc:raise ValueError('无法读取公开播客来源；请检查网络或代理，Apple 目录失败时可直接使用 RSS') from exc
    if len(data)>limit:raise ValueError('播客来源过大，超过 32 MiB 限制')
    return data,final


def search(term, country='CN', limit=25):
    term=term.strip()
    if not term or len(term)>200:raise ValueError('搜索词应为 1–200 个字符')
    if not re.fullmatch('[A-Za-z]{2}',country):raise ValueError('地区代码无效')
    url='https://itunes.apple.com/search?'+urlencode({'term':term,'country':country.upper(),'media':'podcast','entity':'podcast','limit':min(max(int(limit),1),50)})
    data=json.loads(_read(url)[0])
    return [{'title':r.get('collectionName') or '', 'channel':r.get('artistName') or '', 'url':r.get('collectionViewUrl') or '', 'feed_url':public_url(r['feedUrl'])} for r in data.get('results',[]) if r.get('feedUrl')]


def resolve_feed(url):
    public_url(url);p=urlparse(url)
    if p.hostname.lower() not in ('podcasts.apple.com','itunes.apple.com'):return url
    match=re.search(r'/id([0-9]+)(?:/|$)',p.path)
    if not match:raise ValueError('请输入 Apple Podcasts 节目链接或公开 RSS')
    data=json.loads(_read('https://itunes.apple.com/lookup?'+urlencode({'id':match.group(1),'entity':'podcast'}))[0])
    for row in data.get('results',[]):
        if row.get('feedUrl'):return public_url(row['feedUrl'])
    raise ValueError('此节目没有可用的公开 RSS；付费或 Apple 专有内容暂不支持')


def read_feed(url, limit=100):
    """Return only this RSS response's episodes; never claim a complete archive."""
    feed=resolve_feed(url);data,final=_read(feed)
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('不支持包含 DTD 或实体声明的 RSS')
    try:root=ET.fromstring(data)
    except ET.ParseError:raise ValueError('来源不是有效的 RSS XML') from None
    channel=root.find('channel')
    if channel is None:raise ValueError('仅支持带 enclosure 的 RSS 2.0 节目')
    title=channel.findtext('title') or '未命名播客';episodes=[];seen=set();skipped=0
    cover=artwork(channel,final)
    nodes=channel.findall('item');limit=min(max(int(limit),1),500)
    for node in nodes:
        enc=node.find('enclosure')
        if enc is None:skipped+=1;continue
        media=urljoin(final,enc.get('url') or '')
        try:enclosure_identity(media)
        except ValueError:skipped+=1;continue
        if media in seen:continue
        seen.add(media)
        duration=node.findtext('{http://www.itunes.com/dtds/podcast-1.0.dtd}duration') or ''
        try:
            parts=duration.split(':');seconds=sum(int(v)*60**i for i,v in enumerate(reversed(parts)))
        except ValueError:seconds=None
        episodes.append({'url':media,'title':node.findtext('title') or '未命名单集','channel':title,'description':node.findtext('description') or '', 'duration':seconds if duration else None,'published':node.findtext('pubDate'),'thumbnail':artwork(node,final) or cover,'metadata':{'feed_url':feed,'media_type':enc.get('type') or '', 'episode_guid':node.findtext('guid') or ''}})
    return {'title':title,'thumbnail':cover,'feed_url':feed,'episodes':episodes[:limit],'available':len(episodes),'skipped':skipped,'limited':len(episodes)>limit,'notice':f'此订阅提供 {len(nodes)} 集，最多显示 {limit} 集，不代表完整历史。仅支持公开音视频；付费、加密内容和 Apple 专有视频暂不支持。请只添加你信任的节目或 RSS；播放和下载会访问节目提供的媒体地址，应用无法完全核实其最终去向。'}
