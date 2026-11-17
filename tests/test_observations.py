import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from test_browser import BrowserBaselineTest
from app.capture import capture_observations
from app.domain import compare_observations, review_observations
from app.records import (read_conflicts, read_observations, read_sessions,
                         save_observations)
from app.review import build_report, explain_conflicts
from app.site import DATA


def claim(subject, field, value, basis='visible_marker'):
    return {'subject': subject, 'subject_basis': basis, 'field': field,
            'raw': value, 'value': value}


def observation(sequence, kind, store, source, region, value, field='status'):
    return {'kind': kind, 'session_id': 's1', 'sequence': sequence,
            'observed_at': f'2026-01-01T00:00:0{sequence}+00:00',
            'source': source, 'item_id': 'store-01', 'region': region,
            'scope_visited': 'center', 'scope_loaded': None, 'selection': None,
            'store': store, 'claims': [claim(f'store:{store}', field, value)]}


class ObservationCaptureTest(BrowserBaselineTest):
    def test_patrol_walks_scopes_and_keeps_reused_marker_per_store(self):
        session = capture_observations(self.origin, DATA['items'][0]['id'])
        self.assertTrue(session['complete'])
        self.assertEqual(session['status'], 'complete')
        self.assertEqual(session['unvisited_scopes'], [])
        self.assertEqual(set(session['completed_scopes']), {'中心区', '东区'})

        markers = [row for row in session['observations'] if row['kind'] == 'map_marker']
        self.assertEqual([(row['region'], row['store']) for row in markers],
                         [('中心区', 'store-01'), ('东区', 'store-02')])
        brands = [row for row in session['observations'] if row['kind'] == 'brand_page']
        statuses = {(row['region'], row['store']): [c['value'] for c in row['claims']
                                                    if c['field'] == 'status'][0]
                    for row in brands}
        self.assertEqual(statuses, {('中心区', 'store-01'): '营业中',
                                    ('东区', 'store-02'): '试营业'})

        # 页面身份与浮动标记身份不同时，报告明确指出是哪家门店，避免张冠李戴。
        report = review_observations(session['observations'], sessions=[session])
        mismatched = {(row['page_item'], row['visible_store'], row['region']): row
                      for row in report['identity_mismatches']}
        self.assertIn(('store-01', 'store-02', '东区'), mismatched)
        self.assertEqual(set(mismatched[('store-01', 'store-02', '东区')]['kinds']),
                         {'map_marker', 'brand_page'})

    def test_zoom_is_observed_as_partial_not_as_missing_store(self):
        session = capture_observations(self.origin, DATA['items'][0]['id'])
        report = review_observations(session['observations'], sessions=[session])
        east = report['coverage']['pages']['store-01']['scopes']['东区']
        self.assertEqual(east['state'], 'partial')
        self.assertFalse(east['absence_claim'])
        self.assertIn('store-02', east['stores_observed'])

    def test_checkpoint_after_interruption_keeps_unvisited_scopes(self):
        saved = []

        def checkpoint(payload):
            saved.append(payload)
            if payload['status'] == 'running' and len(payload['observations']) >= 3:
                raise KeyboardInterrupt('巡查中途退出')

        with self.assertRaises(KeyboardInterrupt):
            capture_observations(self.origin, DATA['items'][0]['id'],
                                 checkpoint=checkpoint)
        interrupted = saved[-1]
        self.assertEqual(interrupted['status'], 'interrupted')
        self.assertFalse(interrupted['complete'])
        self.assertIn('东区', interrupted['unvisited_scopes'])
        self.assertNotIn('东区', interrupted['completed_scopes'])
        running = [row for row in saved if row['status'] == 'running']
        self.assertTrue(running)
        self.assertTrue(all(observation['kind'] != 'map_zoom'
                            for row in running for observation in row['observations']))

        # 未完成会话不能给出缺店结论；未访问范围单独列出。
        report = review_observations(interrupted['observations'], sessions=[interrupted])
        east = report['coverage']['pages']['store-01']['scopes']['东区']
        self.assertFalse(east['visited'])
        self.assertFalse(east['absence_claim'])
        self.assertEqual(east['state'], 'unvisited')

    def test_observations_round_trip_and_conflicts_cite_sources(self):
        first = observation(1, 'catalog_card', 'store-01', 'http://127.0.0.1/catalog',
                            '中心区', '营业中')
        second = observation(2, 'brand_page', 'store-01',
                             'http://127.0.0.1/detail?id=store-01', '东区', '临时闭店')
        with TemporaryDirectory() as directory:
            database = Path(directory) / 'observations.sqlite3'
            payload = {'session_id': 's1', 'item_id': 'store-01', 'status': 'complete',
                       'complete': True, 'started_at': first['observed_at'],
                       'updated_at': second['observed_at'], 'completed_scopes': ['中心区', '东区'],
                       'unvisited_scopes': [], 'error': None,
                       'observations': [first, second], 'notes': []}
            self.assertEqual(save_observations(database, payload), 2)
            self.assertEqual(len(read_observations(database)), 2)
            self.assertEqual(len(read_sessions(database)), 1)
            conflicts = read_conflicts(database)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0]['values'], ['营业中', '临时闭店'])
            cited = explain_conflicts(read_observations(database))
            self.assertEqual([item['page'] for item in cited[0]['sources']],
                             ['http://127.0.0.1/catalog',
                              'http://127.0.0.1/detail?id=store-01'])
            self.assertEqual([item['map_scope'] for item in cited[0]['sources']],
                             ['中心区（visited=center）', '东区（visited=center）'])
            # 同一会话重复保存按会话替换，不产生重复观察。
            save_observations(database, payload)
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM observations').fetchone()[0], 2)

    def test_conflict_does_not_choose_a_truth(self):
        observations = [
            observation(1, 'catalog_card', 'store-01', 'catalog', '中心区', '营业中'),
            observation(2, 'brand_page', 'store-01', 'detail', '中心区', '预约制'),
            observation(3, 'map_marker', 'store-01', 'detail', '中心区', '营业中'),
        ]
        conflicts = compare_observations(observations)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['values'], ['营业中', '预约制'])
        self.assertEqual(len(conflicts[0]['observations']), 3)
        self.assertNotIn('truth', conflicts[0])
        self.assertIn('未选择真值', conflicts[0]['note'])


class ReportTest(unittest.TestCase):
    def test_report_lists_pages_ranges_and_times(self):
        observations = [
            observation(1, 'catalog_card', 'store-01', 'catalog', '中心区', '营业中'),
            observation(2, 'brand_page', 'store-01', 'detail', '东区', '试营业'),
        ]
        session = {'session_id': 's1', 'item_id': 'store-01', 'status': 'interrupted',
                   'complete': False, 'started_at': observations[0]['observed_at'],
                   'updated_at': observations[1]['observed_at'],
                   'completed_scopes': ['中心区', '东区'], 'unvisited_scopes': ['西区']}
        report = build_report(observations, sessions=[session])
        west = report['coverage']['pages']['store-01']['scopes']['西区']
        self.assertEqual(west['state'], 'unvisited')
        self.assertFalse(west['absence_claim'])
        self.assertEqual(report['coverage']['known_scopes'], ['东区', '中心区', '西区'])
        explanation = report['conflict_explanations'][0]
        self.assertEqual(explanation['field'], 'status')
        self.assertEqual({item['store'] for item in explanation['sources']}, {'store-01'})
        self.assertEqual({item['source_kind'] for item in explanation['sources']},
                         {'catalog_card', 'brand_page'})
        self.assertTrue(all(item['observed_at'] for item in explanation['sources']))


if __name__ == '__main__':
    unittest.main()
