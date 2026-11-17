"""只审阅已观察的详情入口，不把候选记录当作已完成的业务。"""

def review_entries(entries):
    coverage = {}
    for entry in entries:
        detail = entry['detail_fact']
        coverage.setdefault(detail['region'], []).append({'marker': detail['visible_store'],
             'directory_store': detail['catalog_store'], 'source': entry['source'],
             'region_complete': detail['map_complete'] == 'true', 'brand_status': 'not_observed'})
    return coverage
