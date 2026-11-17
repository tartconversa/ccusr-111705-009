"""只审阅已观察的来源，不把候选记录当作已完成的业务。

审阅输出并列各来源的时间与状态：每条观察都能回到具体门店、页面和地图范围。
未访问或未加载的区域只标记为未观察，不产出“没有门店”的结论；冲突也不选真值。
"""
from .domain import compare_observations, review_observations

# 旧的详情入口收据仍可审阅，但只说明“未观察品牌状态”，不推断业务资格。
def review_entries(entries):
    coverage = {}
    for entry in entries:
        detail = entry['detail_fact']
        coverage.setdefault(detail['region'], []).append({'marker': detail['visible_store'],
             'directory_store': detail['catalog_store'], 'source': entry['source'],
             'region_complete': detail['map_complete'] == 'true', 'brand_status': 'not_observed'})
    return coverage


def _citation(observation):
    """把一条并列观察压缩成可核对的一句话。"""
    page = observation.get('source') or '未知页面'
    store = observation.get('store') or observation.get('item_id') or '未知门店'
    scope = observation.get('region') or '未记录范围'
    visited = observation.get('scope_visited')
    scope_text = f'{scope}（visited={visited}）' if visited else scope
    return {
        'store': store,
        'page': page,
        'page_item': observation.get('item_id'),
        'map_scope': scope_text,
        'observed_at': observation.get('observed_at'),
        'source_kind': observation.get('kind'),
        'subject_basis': observation.get('subject_basis'),
        'raw': observation.get('raw'),
    }


def explain_conflicts(observations, fields=None):
    """逐条冲突列出各来源的取值与出处，便于人工核对。"""
    explained = []
    for conflict in compare_observations(observations, fields=fields):
        explained.append({
            'subject': conflict['subject'],
            'field': conflict['field'],
            'values': conflict['values'],
            'sources': [_citation(item) for item in conflict['observations']],
            'note': conflict['note'],
        })
    return explained


def build_report(observations, sessions=None):
    """完整核对报告；sessions 用于区分已完成与未访问的地图范围。"""
    report = review_observations(observations, sessions=sessions)
    report['conflict_explanations'] = explain_conflicts(observations)
    return report
