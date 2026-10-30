"""Persistent local media index; existing source files are never modified."""
from contextlib import contextmanager
import uuid
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import re


def youtube_id(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.username or p.password or (p.hostname or '').lower() not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        raise ValueError('请输入 YouTube 视频链接')
    import re
    value = p.path.strip('/').split('/')[0] if p.hostname.lower() == 'youtu.be' else parse_qs(p.query).get('v', [''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        raise ValueError('请输入单个 YouTube 视频链接')
    return value


def identify_url(url):
    """Identify a supported single video, including its Bilibili part."""
    p=urlparse(url); host=(p.hostname or '').lower()
    if p.scheme!='https' or p.username or p.password:
        raise ValueError('请输入 YouTube 或 B 站的视频链接')
    if host in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
        sid=youtube_id(url)
        return {'source':'youtube','id':sid,'file_id':sid,'url':'https://www.youtube.com/watch?v='+sid}
    if host in ('bilibili.com','www.bilibili.com','m.bilibili.com'):
        match=re.fullmatch(r'/video/(BV[0-9A-Za-z]{10})/?',p.path)
        parts=parse_qs(p.query,keep_blank_values=True).get('p',['1'])
        if match and len(parts)==1 and re.fullmatch(r'[1-9][0-9]{0,5}',parts[0]):
            bv=match.group(1);part=int(parts[0]);sid=f'{bv}_p{part}'
            return {'source':'bilibili','id':sid,'file_id':sid,'url':f'https://www.bilibili.com/video/{bv}?p={part}'}
    raise ValueError('请输入单个 YouTube 或 B 站 BV 视频链接')


def data_dir():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'mediadesk'


class Store:
    def __init__(self, root=None):
        self.root = Path(root or data_dir()); self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.media_dir = self.root / 'media'; self.media_dir.mkdir(exist_ok=True, mode=0o700)
        self.dbpath = self.root / 'library.sqlite3'
        with self.connection() as c:
            c.executescript('''
              CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT, title TEXT NOT NULL, channel TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', thumbnail TEXT NOT NULL DEFAULT '', url TEXT, path TEXT, duration REAL, published TEXT, metadata TEXT NOT NULL DEFAULT '{}', updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(source, source_id));
              CREATE TABLE IF NOT EXISTS collections(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
              CREATE TABLE IF NOT EXISTS collection_items(collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE, media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE, added_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(collection_id,media_id));
              CREATE TABLE IF NOT EXISTS downloads(id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id), state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            ''')
            columns={row['name'] for row in c.execute('PRAGMA table_info(downloads)')}
            if 'label' not in columns:c.execute("ALTER TABLE downloads ADD COLUMN label TEXT NOT NULL DEFAULT ''")
            if 'options' not in columns:c.execute("ALTER TABLE downloads ADD COLUMN options TEXT NOT NULL DEFAULT '{}'")
            c.execute("UPDATE downloads SET state='中断',detail='应用关闭时下载尚未完成；可继续',updated_at=CURRENT_TIMESTAMP WHERE state IN ('等待','下载中','暂停')")
        os.chmod(self.dbpath, 0o600)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.dbpath, timeout=10); conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def setting(self, key, default=None):
        with self.connection() as c:
            row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connection() as c:
            c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value, ensure_ascii=False)))

    def save_youtube(self, item):
        return self.save_youtube_batch([item])[0]['id']

    def save_source(self,item):
        identity=identify_url(item['url'])
        if identity['source']=='youtube':return self.save_youtube(item)
        sid=identity['id'];mid='bilibili:'+sid
        record=(mid,'bilibili',sid,str(item.get('title') or sid),str(item.get('channel') or ''),str(item.get('description') or ''),str(item.get('thumbnail') or ''),identity['url'],item.get('duration'),item.get('published'),json.dumps(item.get('metadata') or {},ensure_ascii=False))
        with self.connection() as c:
            c.execute('''INSERT INTO media(id,source,source_id,title,channel,description,thumbnail,url,duration,published,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET title=excluded.title,channel=excluded.channel,description=CASE WHEN excluded.description='' THEN media.description ELSE excluded.description END,thumbnail=CASE WHEN excluded.thumbnail='' THEN media.thumbnail ELSE excluded.thumbnail END,duration=COALESCE(excluded.duration,media.duration),published=COALESCE(excluded.published,media.published),metadata=CASE WHEN excluded.metadata='{}' THEN media.metadata ELSE excluded.metadata END,updated_at=CURRENT_TIMESTAMP''',record)
        return mid

    def save_youtube_batch(self,items):
        records=[]
        for item in items:
            sid=youtube_id(item['url']);mid='youtube:'+sid
            records.append((mid,'youtube',sid,str(item.get('title') or sid),str(item.get('channel') or ''),str(item.get('description') or ''),str(item.get('thumbnail') or ''),'https://www.youtube.com/watch?v='+sid,item.get('duration'),item.get('published'),json.dumps(item.get('metadata') or {},ensure_ascii=False)))
        with self.connection() as c:
            c.executemany('''INSERT INTO media(id,source,source_id,title,channel,description,thumbnail,url,duration,published,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET title=excluded.title,channel=excluded.channel,description=CASE WHEN excluded.description='' THEN media.description ELSE excluded.description END,thumbnail=CASE WHEN excluded.thumbnail='' THEN media.thumbnail ELSE excluded.thumbnail END,duration=COALESCE(excluded.duration,media.duration),published=COALESCE(excluded.published,media.published),metadata=CASE WHEN excluded.metadata='{}' THEN media.metadata ELSE excluded.metadata END,updated_at=CURRENT_TIMESTAMP''',records)
            paths={row['id']:row['path'] for row in c.execute('SELECT id,path FROM media WHERE id IN ('+','.join('?' for _ in records)+')',[r[0] for r in records])} if records else {}
        return [{**item,'id':record[0],'path':paths.get(record[0])} for item,record in zip(items,records)]

    def save_local(self, path):
        path = Path(path).resolve(strict=True)
        if not path.is_file(): raise ValueError('不是普通文件')
        with self.connection() as c:
            row=c.execute("SELECT id FROM media WHERE source='local' AND path=?",(str(path),)).fetchone()
            if row:return row['id']
            mid='local:'+uuid.uuid4().hex
            c.execute('INSERT INTO media(id,source,title,path) VALUES(?,?,?,?)',(mid,'local',path.stem,str(path)))
        return mid

    def media(self, collection=None):
        with self.connection() as c:
            if collection:
                rows = c.execute('SELECT m.* FROM media m JOIN collection_items ci ON ci.media_id=m.id WHERE ci.collection_id=? ORDER BY ci.added_at DESC,m.id', (collection,)).fetchall()
            else: rows=c.execute('SELECT * FROM media ORDER BY updated_at DESC,id').fetchall()
        return [dict(r) for r in rows]

    def get(self, mid):
        with self.connection() as c: row=c.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
        return dict(row) if row else None

    def set_path(self, mid, path):
        with self.connection() as c: c.execute('UPDATE media SET path=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(str(path),mid))

    def collections(self):
        with self.connection() as c: return [dict(r) for r in c.execute('SELECT * FROM collections ORDER BY name')]

    def add_collection(self, name):
        name=name.strip()
        if not name or len(name)>80: raise ValueError('列表名称应为 1–80 个字符')
        with self.connection() as c:
            try: return c.execute('INSERT INTO collections(name) VALUES(?)',(name,)).lastrowid
            except sqlite3.IntegrityError: raise ValueError('列表已存在') from None

    def add_to_collection(self, cid, mid):
        with self.connection() as c: c.execute('INSERT OR IGNORE INTO collection_items(collection_id,media_id) VALUES(?,?)',(cid,mid))

    def media_collections(self,mid):
        with self.connection() as c:return {r[0] for r in c.execute('SELECT collection_id FROM collection_items WHERE media_id=?',(mid,))}

    def set_media_collections(self,mid,ids):
        with self.connection() as c:
            valid={r[0] for r in c.execute('SELECT id FROM collections')};selected=set(ids)
            if not selected.issubset(valid):raise ValueError('列表已发生变化，请重试')
            c.execute('DELETE FROM collection_items WHERE media_id=?',(mid,))
            c.executemany('INSERT INTO collection_items(collection_id,media_id) VALUES(?,?)',((cid,mid) for cid in selected))

    def job(self, jobid, mid, state, detail=''):
        with self.connection() as c:
            c.execute('INSERT INTO downloads(id,media_id,state,detail) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP',(jobid,mid,state,detail))

    def jobs(self):
        with self.connection() as c: return [dict(r) for r in c.execute("SELECT d.*,COALESCE(NULLIF(d.label,''),m.title) AS title FROM downloads d JOIN media m ON m.id=d.media_id ORDER BY d.rowid DESC")]

    def job_options(self,jobid,options):
        with self.connection() as c:c.execute('UPDATE downloads SET options=? WHERE id=?',(json.dumps(options),jobid))

    def rename_job(self,jobid,name):
        name=name.strip()
        if not name or len(name)>200:raise ValueError('任务名称应为 1–200 个字符')
        with self.connection() as c:c.execute('UPDATE downloads SET label=? WHERE id=?',(name,jobid))

    def delete_job(self,jobid):
        with self.connection() as c:c.execute('DELETE FROM downloads WHERE id=?',(jobid,))

    def clear_path_if_matches(self,mid,path):
        with self.connection() as c:c.execute('UPDATE media SET path=NULL WHERE id=? AND path=?',(mid,str(path)))

    def backup(self, destination):
        with self.connection() as src, sqlite3.connect(destination) as dst: src.backup(dst)
