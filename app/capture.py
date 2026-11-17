"""使用真实 Chromium 浏览本地演练门户，逐范围留下可核对的观察。

采集只记录页面当时可见的内容：目录卡片、视口选择、地图范围、门店浮层、
品牌详情。不把未访问或未加载的区域解释为没有门店，也不在不同来源冲突时选择真值。

地图行为约束（见 docs/portal.md）：
- 平移会复用同一个标记节点，因此每次点击标记后要重新读取它当前的身份和地址；
- 缩放可能只加载部分区域，隐藏标记不等于门店不存在；
- 同品牌多店地址相似，观察以门店键（store-*）而不是名称或地址归并。
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import sync_playwright

from .domain import (NO_ABSENCE_INFERENCE, SCOPES, interpret_card, interpret_entry,
                     parse_address, parse_status, summary_claims)

_STATE_JS = """() => {
  const marker = document.querySelector('.marker');
  const viewport = document.querySelector('#viewport');
  const scope = document.querySelector('#map-scope');
  const complete = viewport ? viewport.dataset.complete : undefined;
  const choice = document.querySelector('#choice');
  return {
    url: location.href,
    page_identity: document.querySelector('main') ? document.querySelector('main').dataset.key : null,
    summary: document.querySelector('#summary') ? document.querySelector('#summary').textContent : null,
    region: viewport ? viewport.dataset.region : null,
    scope_loaded: complete === 'false' ? false : (complete === 'true' ? true : null),
    scope_visited: scope ? scope.dataset.visited : null,
    scope_text: scope ? scope.textContent : null,
    marker_present: !!marker,
    marker_hidden: marker ? !!marker.hidden : null,
    marker_store: marker ? marker.dataset.store : null,
    marker_text: marker ? marker.textContent : null,
    popover: document.querySelector('#store-popover') ? document.querySelector('#store-popover').textContent : null,
    brand_state: document.querySelector('#brand-state') ? document.querySelector('#brand-state').textContent : null,
    brand_address: document.querySelector('#brand-address') ? document.querySelector('#brand-address').textContent : null,
    panel: document.querySelector('#panel') ? document.querySelector('#panel').textContent : null,
    result: document.querySelector('#result') ? document.querySelector('#result').textContent : null,
    selection: choice ? choice.value : null,
    choices: choice ? Array.from(choice.options).map(option => ({value: option.value, label: option.textContent})) : [],
    controls: {
      pan: !!document.querySelector('#pan'),
      zoom: !!document.querySelector('#zoom'),
      brand: !!document.querySelector('#brand'),
      details: !!document.querySelector('#details'),
      preview: !!document.querySelector('#preview'),
      marker: !!marker,
    },
  };
}"""


def _check_origin(origin):
    parts = urlsplit(origin)
    if parts.hostname not in ('127.0.0.1', 'localhost') or parts.scheme != 'http':
        raise ValueError('只允许本地演练来源')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def _read_state(page):
    return page.evaluate(_STATE_JS)


def _click(page, selector):
    locator = page.locator(selector)
    if not locator.count():
        return False
    locator.click()
    page.wait_for_timeout(60)  # 详情与浮层是分步出现的可见内容
    return True


def _wait_for_text(page, selector, attempts=25, delay=20):
    """等待分步内容从“读取中/核对中”落定；返回当前文字。"""
    text = ''
    for _ in range(attempts):
        locator = page.locator(selector)
        text = locator.inner_text() if locator.count() else ''
        if text and text not in ('读取中', '核对中'):
            return text
        page.wait_for_timeout(delay)
    return text


def _wait_for_marker(page, expected_store=None, attempts=25, delay=25):
    """点击标记后等它自己被复用为新的门店；不把旧状态当成新观察。"""
    for _ in range(attempts):
        state = _read_state(page)
        if expected_store is None:
            if state['marker_present'] and not state['marker_hidden']:
                return state
        elif state['marker_store'] == expected_store:
            return state
        page.wait_for_timeout(delay)
    return _read_state(page)


def _claim(subject, basis, field, raw, value):
    return {'subject': subject, 'subject_basis': basis, 'field': field,
            'raw': raw, 'value': value}


def read_catalog(origin):
    _check_origin(origin)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(origin, wait_until='domcontentloaded')
            if not page.locator('main').count():
                raise ValueError('来源目录未加载')
            items = page.locator('.card').evaluate_all('(nodes) => nodes.map(n => ({id:n.dataset.key,name:n.querySelector("h2").textContent,summary:n.querySelector("p").textContent,href:n.querySelector("a").getAttribute("href")}))')
            return [{'source': page.url, **item, 'catalog_fact': interpret_card(item)} for item in items]
        finally:
            browser.close()


def read_detail_entry(origin, item_id, selection=None):
    _check_origin(origin)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(origin, wait_until='domcontentloaded')
            card = page.locator(f'.card[data-key="{item_id}"]')
            if card.count() != 1:
                raise ValueError('card identity is not unique')
            catalog = {'id': item_id, 'summary': card.locator('p').inner_text()}
            card.locator('a').click()
            if page.locator('main').get_attribute('data-key') != item_id:
                raise ValueError('detail identity differs from catalog')
            if selection is not None:
                if selection == '东区':
                    page.locator('#pan').click()
            catalog_fact = interpret_card(catalog)
            entry_signal = {'region': page.locator('#viewport').get_attribute('data-region'), 'store': page.locator('.marker').get_attribute('data-store'), 'map_complete': page.locator('#viewport').get_attribute('data-complete')}
            return {'id': item_id, 'source': page.url, 'catalog_fact': catalog_fact,
                    'opening_summary': page.locator('#summary').inner_text(),
                    'detail_fact': interpret_entry(catalog_fact, entry_signal)}
        finally:
            browser.close()


def _observation(kind, state, session_id, sequence, store=None, claims=None, **extra):
    observation = {
        'kind': kind,
        'session_id': session_id,
        'sequence': sequence,
        'observed_at': _now(),
        'source': state.get('url'),
        'item_id': state.get('page_identity'),
        'region': state.get('region'),
        'scope_visited': state.get('scope_visited'),
        'scope_text': state.get('scope_text'),
        'scope_loaded': state.get('scope_loaded'),
        'selection': state.get('selection'),
        'store': store,
        'marker_present': state.get('marker_present'),
        'marker_hidden': state.get('marker_hidden'),
        'marker_store': state.get('marker_store'),
        'marker_text': state.get('marker_text'),
        'claims': list(claims or ()),
    }
    observation.update(extra)
    return observation


def _checkpoint_payload(session_id, item_id, observations, status, completed_scopes,
                        unvisited_scopes, error=None):
    return {
        'session_id': session_id,
        'item_id': item_id,
        'status': status,
        'complete': status == 'complete',
        'started_at': observations[0]['observed_at'] if observations else _now(),
        'updated_at': _now(),
        'completed_scopes': list(completed_scopes),
        'unvisited_scopes': list(unvisited_scopes),
        'observations': copy.deepcopy(observations),
        'error': error,
        'notes': [NO_ABSENCE_INFERENCE],
    }


def capture_observations(origin, item_id, checkpoint=None, session_id=None):
    """逐范围巡查一个详情页，返回只含可见观察的会话记录。

    checkpoint(payload) 在每个观察后以及完成/中断时被调用；payload 可被保存为
    未完成会话，其中 unvisited_scopes 明确列出尚未访问的范围。会话记录只描述
    “观察到什么”，不包含“某范围没有门店”的结论。
    """
    _check_origin(origin)
    session_id = session_id or uuid4().hex
    observations = []
    completed_scopes = []
    known_scopes = list(SCOPES)
    status = 'running'

    def unvisited():
        return [scope for scope in known_scopes if scope not in completed_scopes]

    def save(status_value, failure=None):
        payload = _checkpoint_payload(
            session_id, item_id, observations, status_value, completed_scopes,
            unvisited(), failure)
        if checkpoint is not None:
            checkpoint(copy.deepcopy(payload))
        return payload

    def record(kind, state, **kwargs):
        observation = _observation(kind, state, session_id, len(observations) + 1, **kwargs)
        observations.append(observation)
        save('running')
        return observation

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(origin, wait_until='domcontentloaded')
            card = page.locator(f'.card[data-key="{item_id}"]')
            if card.count() != 1:
                raise ValueError('card identity is not unique')
            catalog_url = page.url
            summary = card.locator('p').inner_text()
            card.locator('a').click()
            page.wait_for_load_state('domcontentloaded')

            state = _read_state(page)
            if state['page_identity'] != item_id:
                raise ValueError('detail identity differs from catalog')

            # 目录卡片是独立来源，先原样留下它的时间与状态（来源是目录页）。
            catalog_state = {'url': catalog_url, 'page_identity': item_id,
                             'region': None, 'scope_visited': None, 'scope_text': None,
                             'scope_loaded': None, 'marker_present': None,
                             'marker_hidden': None, 'marker_store': None,
                             'marker_text': None, 'selection': None}
            record('catalog_card', catalog_state, claims=summary_claims(item_id, summary),
                   page_summary=summary)

            # “视口”选择会改变当前页面状态；逐项打开地图浮层与品牌详情。
            choices = state['choices']
            for choice in choices:
                page.select_option('#choice', choice['value'])
                page.wait_for_timeout(30)
                state = _read_state(page)
                if state['controls']['details']:
                    _click(page, '#details')
                    panel = _wait_for_text(page, '#panel')
                    state = _read_state(page)
                    record('map_overlay', state,
                           claims=[
                               _claim(f'store:{item_id}', 'page_item_selection', 'overlay_text',
                                      panel, panel or None),
                               _claim(f'store:{item_id}', 'page_item_selection', 'status',
                                      panel, parse_status(panel)),
                           ], panel=panel, choice=choice['value'])
                if state['controls']['preview']:
                    _click(page, '#preview')
                    result = _wait_for_text(page, '#result')
                    state = _read_state(page)
                    record('brand_detail_panel', state,
                           claims=[
                               _claim(f'store:{item_id}', 'brand_detail_panel', 'detail_text',
                                      result, result or None),
                               _claim(f'store:{item_id}', 'brand_detail_panel', 'status',
                                      result, parse_status(result)),
                           ], result=result, choice=choice['value'])

            # 逐个可见地图范围：每次平移后重新读取被复用的标记，再打开浮层与品牌页。
            queue = [state['region']]
            pan_attempts = 0
            while queue:
                target = queue.pop(0)
                if target in completed_scopes:
                    continue
                state = _read_state(page)
                while state['region'] != target and state['controls']['pan'] and pan_attempts < 12:
                    _click(page, '#pan')
                    state = _read_state(page)
                    pan_attempts += 1
                pan_attempts = 0
                if state['region'] != target:
                    # 无法进入目标范围：它保持未访问，绝不当成“没有门店”。
                    continue
                if target not in known_scopes:
                    known_scopes.append(target)

                record('map_scope', state, scanned_region=target,
                       claims=[_claim(f'map:{target}', 'map_scope', 'scope_text',
                                      state['scope_text'], state['scope_text'])])

                if state['marker_present'] and not state['marker_hidden']:
                    _click(page, '.marker')
                    state = _wait_for_marker(page)
                    store = state['marker_store']
                    if state['marker_present'] and not state['marker_hidden'] and store:
                        record('map_marker', state, store=store,
                               claims=[
                                   _claim(f'store:{store}', 'visible_marker', 'address',
                                          state['popover'], parse_address(state['popover'])),
                                   _claim(f'store:{store}', 'visible_marker', 'status',
                                          state['popover'], parse_status(state['popover'])),
                                   _claim(f'store:{store}', 'visible_marker', 'marker_text',
                                          state['marker_text'], state['marker_text']),
                               ], popover=state['popover'])
                        if _click(page, '#brand'):
                            state = _read_state(page)
                            record('brand_page', state, store=store,
                                   claims=[
                                       _claim(f'store:{store}', 'brand_detail', 'status',
                                              state['brand_state'], parse_status(state['brand_state'])),
                                       _claim(f'store:{store}', 'brand_detail', 'address',
                                              state['brand_address'], parse_address(state['brand_address'])),
                                   ], brand_state=state['brand_state'],
                                   brand_address=state['brand_address'])
                else:
                    record('map_zoom', state,
                           note='标记被隐藏或该范围暂无可交互标记；这不表示该范围没有门店。')

                if target not in completed_scopes:
                    completed_scopes.append(target)

                # 平移可能暴露新范围；只把页面实际切换到的范围排入队列。
                if state['controls']['pan']:
                    before = state['region']
                    _click(page, '#pan')
                    state = _read_state(page)
                    if state['region'] != before:
                        if state['region'] not in known_scopes:
                            known_scopes.append(state['region'])
                        if state['region'] not in completed_scopes and state['region'] not in queue:
                            queue.append(state['region'])

            # 缩放只加载部分区域：记录这次裁剪，不用隐藏标记推断缺店。
            if state['controls']['zoom']:
                _click(page, '#zoom')
                state = _read_state(page)
                record('map_zoom', state,
                       note='缩放后区域可能只加载一部分；隐藏的标记不解释为没有门店。')

            return save('complete')
        except BaseException as exc:
            save('interrupted', f'{type(exc).__name__}: {exc}')
            raise
        finally:
            browser.close()
