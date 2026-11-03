"""Local OPML preview and explicitly requested YouTube candidates; never binds sources."""
import html
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .podcasts import public_url

MAX_OPML = 4 * 1024 * 1024
MAX_ENTRIES = 2000
NOTICE = '候选仅来自 YouTube 公开搜索；同名、串台或单集不代表官方节目，请确认后关联。'


def _feed_key(url):
    p = urlsplit(public_url(url))
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))


def parse_opml(data, existing_urls=()):
    """Return a preview only; RSS URLs are validated syntactically, never fetched."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    if len(data) > MAX_OPML:
        raise ValueError('OPML 文件超过 4 MiB')
    # Removing NULs also detects UTF-16/32 declarations before ElementTree sees them.
    guard = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in guard or b'<!ENTITY' in guard:
        raise ValueError('OPML 不允许 DTD 或 XML 实体')
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError):
        raise ValueError('无法解析 OPML 文件') from None
    if root.tag != 'opml' or root.find('body') is None:
        raise ValueError('文件不是包含 body 的 OPML')
    seen = set()
    for url in existing_urls:
        try:
            seen.add(_feed_key(url))
        except ValueError:
            pass
    result = {'entries': [], 'skipped': 0, 'duplicates': 0, 'issues': []}
    outlines = list(root.find('body').iter('outline'))
    if len(outlines) > MAX_ENTRIES:
        raise ValueError('OPML 条目超过 2000 条，请拆分文件')
    for index, node in enumerate(outlines, 1):
        raw_url = (node.get('xmlUrl') or node.get('xmlurl') or '').strip()
        if not raw_url and len(node):
            continue  # Folder outlines are not subscriptions.
        title = (node.get('title') or '').strip()
        # Xiaoyuzhou uses text for description, unlike many generic OPML exporters.
        description = (node.get('description') or node.get('text') or '').strip()
        try:
            key = _feed_key(raw_url)
            if not title:
                raise ValueError('缺少节目名称 title')
        except ValueError:
            result['skipped'] += 1
            result['issues'].append({'index': index, 'reason': '缺少节目名称或有效公开 HTTPS RSS 地址'})
            continue
        if key in seen:
            result['duplicates'] += 1
            continue
        seen.add(key)
        result['entries'].append({'title': title, 'description': description,
                                  'feed_url': key, 'source_url': key})
    return result


def read_opml(path, existing_urls=()):
    """Read only the file selected by the caller; no discovery or account access."""
    with Path(path).open('rb') as source:
        return parse_opml(source.read(MAX_OPML + 1), existing_urls)


def _search_api(params, endpoint="search"):
    from . import sources
    command = [sources.helper_python(), '-m', 'mediadesk.xiaoyuzhou_import', '--' + endpoint, json.dumps(params)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                              env=sources.environment(), cwd=str(Path(__file__).resolve().parent.parent), timeout=60,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('YouTube 搜索失败：请检查已连接账号、网络或 API 配额') from None
    if proc.returncode:
        raise ValueError('YouTube 搜索失败：请检查已连接账号、网络或 API 配额')
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise ValueError('YouTube 搜索返回无效数据') from None


def search_youtube_candidates(title, *, user_triggered=False, limit=5, api_request=None):
    """One search request, no pagination/retries. UI must disclose title transmission."""
    if user_triggered is not True:
        raise ValueError('请明确点击搜索；节目名称将发送到 YouTube')
    title = title.strip()
    if not title or len(title) > 300:
        raise ValueError('节目名称为空或过长')
    limit = max(1, min(int(limit), 10))
    params = {'part': 'snippet', 'q': title, 'type': 'channel,playlist,video', 'maxResults': limit}
    body = (api_request or _search_api)(params)
    if not isinstance(body, dict):
        raise ValueError('YouTube 搜索返回无效数据')
    if body.get('error'):
        raise ValueError('YouTube 搜索失败：请检查授权、网络或 API 配额；不会自动重试')
    candidates = []
    seen = set()
    items = body.get('items') or []
    if not isinstance(items, list):
        raise ValueError('YouTube 搜索返回无效数据')
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        identity, snippet = item.get('id') or {}, item.get('snippet') or {}
        if not isinstance(identity, dict) or not isinstance(snippet, dict):
            continue
        for kind, field, prefix in [('channel', 'channelId', 'https://www.youtube.com/channel/'),
                                    ('playlist', 'playlistId', 'https://www.youtube.com/playlist?list='),
                                    ('video', 'videoId', 'https://www.youtube.com/watch?v=')]:
            identifier = identity.get(field)
            if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
                continue
            url = prefix + identifier
            if url not in seen:
                candidates.append({'kind': kind, 'source_id': identifier, 'url': url, 'source_url': url,
                                   'title': html.unescape(snippet.get('title') or ''),
                                   'channel': html.unescape(snippet.get('channelTitle') or ''),
                                   'description': html.unescape(snippet.get('description') or ''),
                                   'provider': 'youtube', 'query': title, 'confirmed': False})
                seen.add(url)
            break
    return {'candidates': candidates, 'query': title, 'notice': NOTICE, 'limited': True}


def resolve_channel_uploads(channel_id, *, user_triggered=False, api_request=None):
    """Resolve a confirmed channel to its uploads playlist, only on explicit action."""
    if user_triggered is not True:
        raise ValueError('请确认频道后点击查看作品')
    if not isinstance(channel_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', channel_id):
        raise ValueError('无效的 YouTube 频道 ID')
    params = {'part': 'contentDetails', 'id': channel_id}
    try:
        body = api_request(params) if api_request else _search_api(params, 'channels')
    except Exception:
        raise ValueError('YouTube 频道读取失败：请检查已连接账号、网络或 API 配额') from None
    if not isinstance(body, dict) or body.get('error'):
        raise ValueError('YouTube 频道读取失败：请检查已连接账号、网络或 API 配额')
    items = body.get('items')
    if not isinstance(items, list):
        raise ValueError('YouTube 频道返回无效数据')
    for item in items:
        if not isinstance(item, dict) or item.get('id') != channel_id:
            continue
        details = item.get('contentDetails') or {}
        related = details.get('relatedPlaylists') if isinstance(details, dict) else None
        uploads = related.get('uploads') if isinstance(related, dict) else None
        if isinstance(uploads, str) and re.fullmatch(r'[A-Za-z0-9_-]+', uploads):
            return uploads
    raise ValueError('该频道没有可用的上传作品列表')


def _main():
    # Reuse the existing credential owner in its helper Python, outside the GTK process.
    from .oauth_bridge import credentials
    import requests
    params = json.loads(sys.argv[2])
    endpoint = sys.argv[1][2:]
    response = requests.get('https://www.googleapis.com/youtube/v3/' + endpoint, params=params,
                            headers={'Authorization': 'Bearer ' + credentials(False).token}, timeout=30)
    if not response.ok:
        raise ValueError('YouTube 搜索请求失败')
    print(json.dumps(response.json(), ensure_ascii=False))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('--search', '--channels'):
            raise ValueError('不支持的调用')
        _main()
    except Exception:
        print('YouTube 搜索失败：请检查授权、网络或 API 配额', file=sys.stderr)
        sys.exit(1)
