"""仅存观察的收据：目录按身份覆盖，观察与会话只追加。

不在这里下业务结论（是否可预约、是否正式营业），也不把未完成巡查写成完成。
"""
import json
import sqlite3
from pathlib import Path

from .domain import compare_observations


def save_catalog(path, items):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS catalog (id TEXT PRIMARY KEY, source TEXT NOT NULL, payload TEXT NOT NULL)')
        for item in items:
            db.execute('INSERT OR REPLACE INTO catalog VALUES (?, ?, ?)', (item['id'], item['source'], json.dumps(item, ensure_ascii=False)))
    return len(items)


def save_detail_entries(path, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS detail_entries (visit_id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, business_key TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL)')
        for entry in entries:
            if entry['catalog_fact']['identity'] != entry['id']:
                raise ValueError('catalog and detail identity mismatch')
            db.execute('INSERT INTO detail_entries (item_id, business_key, source, payload) VALUES (?, ?, ?, ?)',
                       (entry['id'], entry['detail_fact']['business_key'], entry['source'], json.dumps(entry, ensure_ascii=False)))
    return len(entries)


def read_detail_entries(path):
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT payload FROM detail_entries ORDER BY visit_id').fetchall()
    return [json.loads(row[0]) for row in rows]


def _ensure_observation_tables(db):
    db.execute('''CREATE TABLE IF NOT EXISTS observation_sessions (
        session_id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL,
        status TEXT NOT NULL,
        complete INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_scopes TEXT NOT NULL,
        unvisited_scopes TEXT NOT NULL,
        error TEXT,
        payload TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS observations (
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        kind TEXT NOT NULL,
        item_id TEXT,
        region TEXT,
        store TEXT,
        scope_visited TEXT,
        scope_loaded TEXT,
        observed_at TEXT NOT NULL,
        source TEXT,
        conflict_group TEXT,
        payload TEXT NOT NULL,
        PRIMARY KEY (session_id, sequence))''')


def save_observations(path, payload):
    """保存一次巡查会话与它的逐条观察；重复保存同一会话会整体替换该会话。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    session_id = payload['session_id']
    with sqlite3.connect(path) as db:
        _ensure_observation_tables(db)
        db.execute('DELETE FROM observations WHERE session_id = ?', (session_id,))
        db.execute('DELETE FROM observation_sessions WHERE session_id = ?', (session_id,))
        db.execute('INSERT INTO observation_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (
            session_id, payload['item_id'], payload['status'], int(bool(payload['complete'])),
            payload['started_at'], payload['updated_at'],
            json.dumps(payload['completed_scopes'], ensure_ascii=False),
            json.dumps(payload['unvisited_scopes'], ensure_ascii=False),
            payload.get('error'), json.dumps(payload, ensure_ascii=False)))
        for observation in payload['observations']:
            db.execute('INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (
                session_id, observation['sequence'], observation['kind'], observation.get('item_id'),
                observation.get('region'), observation.get('store'), observation.get('scope_visited'),
                json.dumps(observation.get('scope_loaded'), ensure_ascii=False),
                observation['observed_at'], observation.get('source'), None,
                json.dumps(observation, ensure_ascii=False)))
    return len(payload['observations'])


def _row_to_observation(row):
    return json.loads(row[0])


def read_observations(path, item_id=None, session_id=None):
    with sqlite3.connect(path) as db:
        _ensure_observation_tables(db)
        query = 'SELECT payload FROM observations'
        clauses, params = [], []
        if item_id is not None:
            clauses.append('item_id = ?')
            params.append(item_id)
        if session_id is not None:
            clauses.append('session_id = ?')
            params.append(session_id)
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        query += ' ORDER BY session_id, sequence'
        rows = db.execute(query, params).fetchall()
    return [_row_to_observation(row) for row in rows]


def read_sessions(path, session_id=None):
    with sqlite3.connect(path) as db:
        _ensure_observation_tables(db)
        if session_id is None:
            rows = db.execute('SELECT payload FROM observation_sessions ORDER BY started_at').fetchall()
        else:
            rows = db.execute('SELECT payload FROM observation_sessions WHERE session_id = ? ORDER BY started_at', (session_id,)).fetchall()
    return [json.loads(row[0]) for row in rows]


def read_conflicts(path):
    """跨会话并列所有来源观察，返回未取舍的冲突清单。"""
    return compare_observations(read_observations(path))
