"""首店地图的营业状态与预约入口对照：目录卡片既有数据约定。"""
import re

def interpret_card(item):
    parts = item['summary'].split(' · ', 1)
    if len(parts) != 2:
        raise ValueError('卡片摘要格式无效')
    condition, observation = parts
    found = re.fullmatch(r"(?P<amount>营业中|试营业)", observation)
    if not found:
        raise ValueError('卡片状态未识别')
    amount = found.group('amount')
    return {'kind': 'opening', 'identity': item['id'], 'condition': condition, 'opening_state': observation, 'state': int(amount) if amount.isdigit() else amount}
