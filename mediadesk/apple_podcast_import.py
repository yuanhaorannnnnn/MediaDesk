"""Local subscription previews; importing never resolves URLs or changes sources."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit, urlunsplit

from .xiaoyuzhou_import import (
    MAX_OPML, MAX_ENTRIES, search_youtube_candidates,
    resolve_channel_uploads,
)


def _feed_key(url):
    """Local identity only: never authorizes fetching this URL."""
    try:
        parts = urlsplit(url)
        if (parts.scheme.lower() not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None
                or any(ord(char) < 33 for char in url)):
            raise ValueError
        port = parts.port
        host = parts.hostname.lower()
        if ':' in host:
            host = '[' + host + ']'
        if port is not None and port != (443 if parts.scheme.lower() == 'https' else 80):
            host += ':' + str(port)
        return urlunsplit((parts.scheme.lower(), host, parts.path or '/', parts.query, ''))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('RSS 地址必须是无账号凭据的 HTTP 或 HTTPS URL') from None


def _preview(rows, existing_urls=(), existing_titles=()):
    seen_urls = set()
    for url in existing_urls:
        try:
            seen_urls.add(_feed_key(url))
        except ValueError:
            pass
    seen_titles = {title.strip().casefold() for title in existing_titles if isinstance(title, str)}
    occurrences = {}
    name_counts = Counter(row['title'].strip().casefold() for row in rows)
    result = {'entries': [], 'skipped': 0, 'duplicates': 0, 'issues': []}
    for index, row in enumerate(rows, 1):
        title = row['title'].strip()
        raw_url = row.get('feed_url', '').strip()
        try:
            if not title or len(title) > 300:
                raise ValueError('节目名称为空或超过 300 字符')
            feed = _feed_key(raw_url) if raw_url else ''
        except ValueError as error:
            result['skipped'] += 1
            result['issues'].append({'index': index, 'reason': str(error)})
            continue
        key = title.casefold()
        if feed and feed in seen_urls:
            result['duplicates'] += 1
            continue
        if feed:
            seen_urls.add(feed)
        identity = feed or json.dumps([key, row.get('description', '').strip()], ensure_ascii=False)
        occurrences[identity] = occurrences.get(identity, 0) + 1
        program_id = hashlib.sha256((identity + '\0' + str(occurrences[identity])).encode()).hexdigest()[:32]
        result['entries'].append({'title': title, 'description': row.get('description', '').strip(),
                                  'feed_url': feed, 'source_url': feed, 'index': index,
                                  'name_conflict': key in seen_titles or name_counts[key] > 1,
                                  'identity_ambiguous': not bool(feed), 'source': 'apple-podcasts',
                                  'program_id': program_id})
        seen_titles.add(key)
    return result


def parse_opml(data, existing_urls=(), existing_titles=()):
    """Generic OPML: text is a title fallback, unlike Xiaoyuzhou's description."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    if len(data) > MAX_OPML:
        raise ValueError('导入文件超过 4 MiB')
    guard = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in guard or b'<!ENTITY' in guard:
        raise ValueError('OPML 不允许 DTD 或 XML 实体')
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError):
        raise ValueError('无法解析 OPML 文件') from None
    body = root.find('body')
    if root.tag != 'opml' or body is None:
        raise ValueError('文件不是包含 body 的 OPML')
    nodes = list(body.iter('outline'))
    if len(nodes) > MAX_ENTRIES:
        raise ValueError('导入条目超过 2000 条，请拆分文件')
    rows = []
    for node in nodes:
        feed = (node.get('xmlUrl') or node.get('xmlurl') or '').strip()
        if not feed and len(node):
            continue
        rows.append({'title': (node.get('title') or '').strip() or node.get('text') or '',
                     'description': node.get('description') or '', 'feed_url': feed})
    return _preview(rows, existing_urls, existing_titles)


def read_import(path, existing_urls=(), existing_titles=()):
    """Read only the selected local file, with a bounded allocation."""
    with Path(path).open('rb') as source:
        return parse_import(source.read(MAX_OPML + 1), existing_urls, existing_titles)


def parse_import(data, existing_urls=(), existing_titles=()):
    return parse_opml(data, existing_urls, existing_titles)
