"""首店地图的营业状态与预约入口对照：来源解析、并列比较与覆盖范围。

这里不做取舍：各来源（目录卡片、视口选择、地图标记/浮层、品牌详情）各自留下
观察；比较只报告同一主体上同一字段出现了哪些不同取值，以及每条取值来自哪个
门店、哪个页面、哪次地图范围和时间。未访问或未加载的区域不会被解释为没有门店。
"""
from __future__ import annotations

import re

# 门户当前会出现的营业状态词。这里只做词表识别，不判断哪个来源更可信。
STATUS_VALUES = ('临时闭店', '预约制', '暂停营业', '营业中', '试营业')
_STATUS_RE = re.compile('|'.join(re.escape(value) for value in STATUS_VALUES))

# 演练门户已知会出现的可见地图范围。巡查仍以页面实际可见状态为准。
SCOPES = ('中心区', '东区')
_STORE_RE = re.compile(r'store-[A-Za-z0-9_-]+')
_REGION_RE = re.compile(r'[一-鿿A-Za-z0-9_-]{1,32}')

# 这些字段是整段页面文字的转录，用来留证；冲突比较看结构化的状态与地址等字段。
NON_COMPARABLE_FIELDS = frozenset({'overlay_text', 'detail_text', 'marker_text',
                                   'scope_text', 'page_summary'})

NO_ABSENCE_INFERENCE = '未访问或未加载的区域只标记为未观察，不解释为没有门店。'

def interpret_card(item):
    parts = item['summary'].split(' · ', 1)
    if len(parts) != 2:
        raise ValueError('卡片摘要格式无效')
    condition, observation = parts
    found = re.fullmatch(rf"(?P<amount>{_STATUS_RE.pattern})", observation)
    if not found:
        raise ValueError('卡片状态未识别')
    amount = found.group('amount')
    return {'kind': 'opening', 'identity': item['id'], 'condition': condition,
            'opening_state': observation, 'state': amount, 'status': amount}

def parse_status(text):
    """从一段可见文字里取出状态词；没有可识别状态时返回 None，不猜。"""
    if not text:
        return None
    found = _STATUS_RE.search(text)
    return found.group(0) if found else None

def parse_address(text):
    """从「门店 / 地址 / 状态」或「选择：浮层文字」一类文字中取地址段。"""
    if not text:
        return None
    parts = [part.strip() for part in re.split(r' / |：|: ', text) if part and part.strip()]
    if not parts:
        return None
    # 浮层是「store-01 / 武康路 10 号」，品牌地址是「store-01 / 武康路 10 号 / 营业中」。
    if len(parts) >= 2 and _STORE_RE.fullmatch(parts[0]):
        return parts[1]
    # 选择前缀是「武康路 10 号：地图浮层：武康新店」，取最后一段带门牌的文字。
    for part in parts:
        if re.search(r'\d+\s*号', part):
            return part
    return parts[-1]

def summary_claims(item_id, summary):
    """把目录摘要拆成可并列比较的观察值。"""
    condition, _, status = summary.partition(' · ')
    return [
        {'subject': f'store:{item_id}', 'subject_basis': 'page_identity',
         'field': 'address', 'raw': condition, 'value': condition.strip() or None},
        {'subject': f'store:{item_id}', 'subject_basis': 'page_identity',
         'field': 'status', 'raw': status, 'value': parse_status(status)},
    ]

def interpret_entry(catalog_fact, signal):
    region = signal.get('region')
    store = signal.get('store')
    if not region or not _REGION_RE.fullmatch(region):
        raise ValueError('unknown map scope')
    if not store or not _STORE_RE.fullmatch(store):
        raise ValueError('unknown marker')
    return {'business_key': f"{region}:{store}", 'catalog_store': catalog_fact['identity'],
            'visible_store': store, 'region': region, 'map_complete': signal.get('map_complete'),
            'page_identity': catalog_fact['identity'], 'store_identity': store,
            'identity_matches_page': store == catalog_fact['identity'],
            'marker_status': signal.get('marker_status'),
            'marker_address': signal.get('marker_address'),
            'page_status': signal.get('page_status'),
            'scope_complete': signal.get('scope_complete')}

def normalize_observation_value(field, value):
    """同一字段在不同来源里的等价写法归一，便于并列比较；不做取舍。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if field == 'status':
        return parse_status(text) or text
    if field == 'address':
        return parse_address(text) or text
    return text

def compare_observations(observations, fields=None):
    """按「主体 + 字段」并列各次观察；只报冲突，不选出真值。

    fields 缺省时比较所有非整段文字字段（状态、地址、时间等）。每条观察都保留
    source（页面）、item_id（页面身份）、store（门店键）、region / scope_visited
    （地图范围）与 observed_at（观察时间），因此每条冲突都能回到具体来源。
    """
    grouped = {}
    for observation in observations:
        for claim in observation.get('claims', ()):
            field = claim.get('field')
            if field in NON_COMPARABLE_FIELDS:
                continue
            if fields is not None and field not in fields:
                continue
            if claim.get('value') is None:
                continue
            key = (claim['subject'], field)
            grouped.setdefault(key, []).append({
                'value': normalize_observation_value(field, claim['value']),
                'raw': claim.get('raw'),
                'subject_basis': claim.get('subject_basis'),
                'kind': observation.get('kind'),
                'source': observation.get('source'),
                'item_id': observation.get('item_id'),
                'store': observation.get('store'),
                'region': observation.get('region'),
                'scope_visited': observation.get('scope_visited'),
                'scope_loaded': observation.get('scope_loaded'),
                'selection': observation.get('selection'),
                'session_id': observation.get('session_id'),
                'sequence': observation.get('sequence'),
                'observed_at': observation.get('observed_at'),
            })
    conflicts = []
    for (subject, field), entries in sorted(grouped.items()):
        values = []
        for entry in entries:
            if entry['value'] not in values:
                values.append(entry['value'])
        if len(values) < 2:
            continue
        conflicts.append({
            'subject': subject,
            'field': field,
            'values': values,
            'observations': entries,
            'note': '同一主体同一字段的来源取值不一致；已并列保留，未选择真值。',
        })
    return conflicts

def find_identity_mismatches(observations):
    """记录页面身份与所打开标记身份不一致的位置，避免把品牌状态归错门店。

    同一会话、页面、范围、门店只列一条，并记录涉及的来源种类，便于逐条回查。
    """
    grouped = {}
    for observation in observations:
        item_id = observation.get('item_id')
        store = observation.get('store')
        if not item_id or not store or item_id == store:
            continue
        key = (observation.get('session_id'), item_id, observation.get('region'), store)
        entry = grouped.setdefault(key, {
            'page_item': item_id,
            'visible_store': store,
            'region': observation.get('region'),
            'kinds': [],
            'sources': [],
            'scope_visited': observation.get('scope_visited'),
            'scope_loaded': observation.get('scope_loaded'),
            'observed_at': observation.get('observed_at'),
            'note': '品牌状态来自当前可见标记；它与目录页身份不同，不能据此改写目录页门店。',
        })
        if observation.get('kind') not in entry['kinds']:
            entry['kinds'].append(observation.get('kind'))
        if observation.get('source') not in entry['sources']:
            entry['sources'].append(observation.get('source'))
    return list(grouped.values())

def build_coverage(observations, sessions=None):
    """按页面与地图范围汇总实际观察到的内容；不生成“无门店”的结论。

    sessions 是巡查会话（含 completed_scopes / unvisited_scopes）。未访问的范围
    会以 state='unvisited' 出现，absence_claim 恒为 False。
    """
    pages = {}
    known_scopes = set()
    for observation in observations:
        kind = observation.get('kind')
        if kind not in ('map_scope', 'map_marker', 'brand_page', 'map_zoom'):
            continue
        item_id = observation.get('item_id')
        region = observation.get('region')
        if not item_id or not region:
            continue
        known_scopes.add(region)
        page = pages.setdefault(item_id, {'source': observation.get('source'), 'scopes': {}})
        scope = page['scopes'].setdefault(region, {
            'visited': True,
            'loaded_values': [],
            'stores_observed': [],
            'marker_hidden_values': [],
            'observations': [],
        })
        if observation.get('scope_loaded') is not None:
            scope['loaded_values'].append(observation['scope_loaded'])
        if kind in ('map_marker', 'brand_page') and observation.get('store'):
            if observation['store'] not in scope['stores_observed']:
                scope['stores_observed'].append(observation['store'])
        if observation.get('marker_hidden') is not None:
            scope['marker_hidden_values'].append(observation['marker_hidden'])
        scope['observations'].append({
            'kind': kind,
            'source': observation.get('source'),
            'observed_at': observation.get('observed_at'),
            'scope_visited': observation.get('scope_visited'),
            'scope_loaded': observation.get('scope_loaded'),
            'marker_hidden': observation.get('marker_hidden'),
            'selection': observation.get('selection'),
        })

    for session in sessions or ():
        item_id = session.get('item_id')
        if not item_id:
            continue
        page = pages.setdefault(item_id, {'source': None,
                                          'scopes': {}})
        page.setdefault('sessions', [])
        page['sessions'].append({
            'session_id': session.get('session_id'),
            'status': session.get('status'),
            'complete': session.get('complete'),
            'started_at': session.get('started_at'),
            'updated_at': session.get('updated_at'),
            'completed_scopes': list(session.get('completed_scopes') or ()),
            'unvisited_scopes': list(session.get('unvisited_scopes') or ()),
        })
        known_scopes.update(session.get('completed_scopes') or ())
        for region in session.get('unvisited_scopes') or ():
            known_scopes.add(region)
            scope = page['scopes'].setdefault(region, {
                'visited': False,
                'stores_observed': [],
                'observations': [],
            })
            if not scope.get('visited'):
                scope['state'] = 'unvisited'
                scope['note'] = '该范围尚未访问；不能解释为没有门店。'
                scope['absence_claim'] = False

    for page in pages.values():
        page.setdefault('sessions', [])
        for scope in page['scopes'].values():
            values = scope.pop('loaded_values', [])
            hidden = scope.pop('marker_hidden_values', [])
            if not scope.get('visited'):
                continue
            if False in values or (hidden and all(hidden)):
                scope['state'] = 'partial'
                scope['note'] = '部分区域未加载或标记被隐藏；隐藏标记不等同于没有门店。'
            elif values and all(values):
                scope['state'] = 'loaded'
                scope['note'] = '该范围可见内容已观察。'
            else:
                scope['state'] = 'unknown'
                scope['note'] = '页面未给出完整加载信息；只保留已观察内容。'
            scope['marker_was_hidden'] = bool(hidden) and all(hidden)
            scope['absence_claim'] = False
    return {
        'known_scopes': sorted(known_scopes),
        'pages': pages,
        'notes': [NO_ABSENCE_INFERENCE],
    }

def review_observations(observations, sessions=None, fields=None):
    """完整核对结果：来源清单、并列冲突、身份错位与覆盖范围。"""
    sources = []
    for observation in observations:
        item = {
            'kind': observation.get('kind'),
            'source': observation.get('source'),
            'item_id': observation.get('item_id'),
            'region': observation.get('region'),
            'store': observation.get('store'),
            'selection': observation.get('selection'),
            'observed_at': observation.get('observed_at'),
        }
        if item not in sources:
            sources.append(item)
    return {
        'sources': sources,
        'conflicts': compare_observations(observations, fields=fields),
        'identity_mismatches': find_identity_mismatches(observations),
        'coverage': build_coverage(observations, sessions=sessions),
        'notes': [NO_ABSENCE_INFERENCE],
    }
