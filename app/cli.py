"""本地演练：启动门户，逐个详情页巡查并输出可核对的来源观察。

不访问外部来源，不操作真实用户、订单或商户；只在本机环回地址演练。
"""
import argparse
import json
import threading

from .capture import capture_observations, read_catalog
from .review import build_report
from .records import save_observations
from .site import start_server


def patrol(origin, item_ids, checkpoint=None, database=None):
    """巡查多个目录项；返回逐项会话记录，冲突由调用方并列审阅。

    每个观察都会写一次收据（含进行中的会话），这样巡查中途退出时，已观察的
    范围仍可核对，未访问范围仍明确列为未访问。
    """
    results = []
    for item_id in item_ids:
        def per_item(payload, item_id=item_id):
            if checkpoint is not None:
                checkpoint(item_id, payload)
            if database is not None:
                save_observations(database, payload)

        payload = capture_observations(origin, item_id, checkpoint=per_item)
        results.append(payload)
    return results


def main():
    parser = argparse.ArgumentParser(description='首店地图本地演练：目录、店铺浮层与品牌详情的营业状态并列观察。')
    parser.add_argument('--origin', default=None, help='本地演练来源；缺省时自动启动演练站点')
    parser.add_argument('--item', action='append', help='只巡查指定目录项（可重复）')
    parser.add_argument('--database', default='portal.sqlite3', help='观察收据 SQLite 路径')
    parser.add_argument('--json', action='store_true', help='输出完整 JSON 报告')
    args = parser.parse_args()

    server = None
    if args.origin is None:
        server = start_server()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}/'
    else:
        origin = args.origin

    try:
        catalog = read_catalog(origin)
        item_ids = args.item or [row['id'] for row in catalog]
        sessions = patrol(origin, item_ids, database=args.database)
        observations = [observation for session in sessions for observation in session['observations']]
        report = build_report(observations, sessions=sessions)
        report['catalog'] = [{key: row[key] for key in ('id', 'name', 'summary', 'source')}
                             for row in catalog]
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"目录来源：{catalog[0]['source'] if catalog else origin}")
    for session in sessions:
        print(f"\n[{session['status']}] {session['item_id']}  会话 {session['session_id']}")
        print(f"  已完成范围：{'、'.join(session['completed_scopes']) or '无'}")
        print(f"  未访问范围：{'、'.join(session['unvisited_scopes']) or '无'}")
        for observation in session['observations']:
            store = observation.get('store') or '-'
            region = observation.get('region') or '-'
            details = [f"{claim['field']}={claim['value']}"
                       for claim in observation.get('claims', ()) if claim.get('value')]
            print(f"  {observation['sequence']:>2}. {observation['kind']:<20} "
                  f"{region:<4} {store:<9} {observation['observed_at']}  {'; '.join(details)}")
    print('\n来源对比（未取舍）：')
    if not report['conflicts']:
        print('  未发现同一主体同一字段的取值冲突。')
    for conflict in report['conflict_explanations']:
        print(f"  - {conflict['subject']} / {conflict['field']}: {' | '.join(conflict['values'])}")
        for item in conflict['sources']:
            print(f"      {item['raw']} 来自 {item['source_kind']} store={item['store'] or '-'} "
                  f"页面={item['page']} 范围={item['map_scope']} 时间={item['observed_at']}")
    if report['identity_mismatches']:
        print('\n身份错位（页面身份与可见标记不同）：')
        for mismatch in report['identity_mismatches']:
            print(f"  - 页面 {mismatch['page_item']} 的 {'/'.join(mismatch['kinds'])} 打开的是 "
                  f"{mismatch['visible_store']}（范围 {mismatch['region']}，"
                  f"来源 {mismatch['sources'][0]}，时间 {mismatch['observed_at']}）")
    print('\n覆盖范围：')
    for item_id, page in report['coverage']['pages'].items():
        for region, scope in page['scopes'].items():
            if scope.get('visited'):
                print(f"  - {item_id} / {region}: {scope['state']}，观察到 "
                      f"{'、'.join(scope['stores_observed']) or '无可交互标记'}")
            else:
                print(f"  - {item_id} / {region}: 未访问（不能解释为没有门店）")
    for note in report['notes']:
        print(f"  注：{note}")


if __name__ == '__main__':
    main()
