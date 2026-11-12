#!/usr/bin/env python3
"""Read-only chip-summary quality audit. All generated files stay in task folders."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import itertools
import json
import math
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work/chip_summary_quality_oct25'
OUT = ROOT / 'outputs/三线研究启动_20261025/筹码摘要核查'
DB = ROOT / 'outputs/统一数据底座_20261022/统一数据底座.sqlite'
FIELDS = ['profit_ratio_pct', 'average_cost_display', 'cost90_low', 'cost90_high',
          'concentration90_pct', 'cost70_low', 'cost70_high', 'concentration70_pct']
LABELS = dict(zip(FIELDS, ['获利比例(%)', '平均成本', '90%下限', '90%上限',
                         '90%集中度(%)', '70%下限', '70%上限', '70%集中度(%)']))
PRICE_FIELDS = ['average_cost_display', 'cost90_low', 'cost90_high', 'cost70_low', 'cost70_high']
RATIO_FIELDS = ['profit_ratio_pct', 'concentration90_pct', 'concentration70_pct']


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fingerprint(path: Path):
    st = path.stat()
    return {'path': str(path.relative_to(ROOT)), 'bytes': st.st_size,
            'mtime_ns': st.st_mtime_ns, 'sha256': sha256(path)}


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


class ValueParser(HTMLParser):
    def __init__(self, target_class):
        super().__init__()
        self.target_class = target_class
        self.depth = 0
        self.text_parts = []
        self.values = []

    def handle_starttag(self, tag, attrs):
        if self.depth:
            self.depth += 1
        elif self.target_class in dict(attrs).get('class', '').split():
            self.depth = 1
            self.text_parts = []

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1
            if not self.depth:
                self.values.append(''.join(self.text_parts).strip())

    def handle_data(self, data):
        if self.depth:
            self.text_parts.append(data)


def parse_values(text, target_class):
    parser = ValueParser(target_class)
    parser.feed(text)
    return parser.values


def numeric_display(values):
    if not isinstance(values, list) or len(values) != 7:
        return None
    try:
        c90 = [float(x) for x in values[3].split('-')]
        c70 = [float(x) for x in values[5].split('-')]
        if len(c90) != 2 or len(c70) != 2:
            return None
        return [float(values[1].rstrip('%')), float(values[2]), *c90,
                float(values[4].rstrip('%')), *c70, float(values[6].rstrip('%'))]
    except (ValueError, TypeError, AttributeError):
        return None


def get_kline(payload):
    return (payload.get('kline') or payload.get('kline_prices') or
            payload.get('kline_price_display') or {})


def md_table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    out += ['| ' + ' | '.join(str(v).replace('|', '\\|').replace('\n', ' ') for v in row) + ' |' for row in rows]
    return '\n'.join(out)


def fmt_number(value):
    return f'{value:.2f}'


def audit():
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    before = fingerprint(DB)
    conn = sqlite3.connect(DB.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    observations = [dict(r) for r in conn.execute('SELECT * FROM chip_observations ORDER BY collection,observation_id')]
    evidence = [dict(r) for r in conn.execute('SELECT * FROM chip_evidence_files ORDER BY observation_id,role')]
    assets = {r['project_relative_path']: dict(r) for r in conn.execute('SELECT * FROM file_assets')}
    existing_conflicts = [dict(r) for r in conn.execute("SELECT * FROM conflicts WHERE collection='chip_all_contexts'")]
    daily_coverage = {r['trade_date']: dict(r) for r in conn.execute('SELECT * FROM daily_coverage')}
    study_dates = {r[0] for r in conn.execute('SELECT trade_date FROM trade_conditions')}
    integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
    foreign_key_violations = [list(r) for r in conn.execute('PRAGMA foreign_key_check')]
    sources = [dict(r) for r in conn.execute("SELECT * FROM ingestion_sources WHERE dataset_id LIKE 'chip%'")]
    conn.close()
    by_id = {r['observation_id']: r for r in observations}
    payloads = {r['observation_id']: json.loads(r['payload_json']) for r in observations}
    accepted = [r for r in observations if r['accepted_capture'] == 1]
    rejected = [r for r in observations if r['accepted_capture'] == 0]
    accepted_dates = sorted({r['actual_date'] for r in accepted})
    evidence_by_obs = collections.defaultdict(list)

    # Every evidence path is hashed once, including shared record indexes.
    inventory = {}
    for item in evidence:
        rel = item['project_relative_path']
        if rel not in inventory:
            path = ROOT / rel
            inventory[rel] = {'project_relative_path': rel, 'exists_now': path.is_file(),
                              'actual_sha256': sha256(path) if path.is_file() else None,
                              'bytes_now': path.stat().st_size if path.is_file() else None,
                              'references': []}
        file_state = inventory[rel]
        edge = dict(item)
        edge['exists_now'] = file_state['exists_now']
        edge['hash_matches'] = (file_state['actual_sha256'] == item['sha256']) if item['sha256'] else None
        edge['stored_exists_matches_now'] = bool(item['exists_locally']) == file_state['exists_now']
        a = assets.get(rel)
        edge['file_assets_catalog_present'] = a is not None
        edge['file_assets_hash_matches'] = (a['sha256'] == item['sha256']) if a else None
        evidence_by_obs[item['observation_id']].append(edge)
        file_state['references'].append({'observation_id': item['observation_id'], 'role': item['role'],
                                         'stored_sha256': item['sha256'], 'hash_matches': edge['hash_matches']})
    all_edges = list(itertools.chain.from_iterable(evidence_by_obs.values()))
    missing = [e for e in all_edges if not e['exists_now']]
    hash_mismatch = [e for e in all_edges if e['exists_now'] and e['hash_matches'] is not True]
    evidence_role_stats = []
    for role in sorted({e['role'] for e in all_edges}):
        group = [e for e in all_edges if e['role'] == role]
        evidence_role_stats.append({'role': role, 'links': len(group),
                                    'exists_now': sum(e['exists_now'] for e in group),
                                    'hash_matches': sum(e['hash_matches'] is True for e in group),
                                    'missing': sum(not e['exists_now'] for e in group)})

    checks = {}
    def add_check(name, predicate, universe=observations, severity='hard_structure'):
        bad = [r['observation_id'] for r in universe if not predicate(r)]
        checks[name] = {'severity': severity, 'checked': len(universe), 'passed': len(universe)-len(bad),
                        'flagged': len(bad), 'flagged_observation_ids': bad}

    def post_state(r):
        post = payloads[r['observation_id']].get('post')
        return post if isinstance(post, dict) else None

    def initial_sync(r):
        return r['expected_date'] == r['actual_date'] == r['kline_date']

    add_check('initial_date_synchronization_all', initial_sync)
    add_check('initial_date_synchronization_accepted', initial_sync, accepted)
    with_post = [r for r in observations if post_state(r)]
    accepted_with_post = [r for r in accepted if post_state(r)]
    def post_sync(r):
        post = post_state(r)
        return (post['date'] == r['expected_date'] == (post.get('kline_date') or post.get('kline'))
                and post.get('visible') == 'block')
    add_check('post_date_visibility_accepted_where_available', post_sync, accepted_with_post)
    add_check('post_date_visibility_all_where_available', post_sync, with_post)
    add_check('payload_summary_date_matches_normalized_actual', lambda r: payloads[r['observation_id']]['values'][0] == r['actual_date'])
    add_check('payload_kline_date_matches_normalized_kline', lambda r: (payloads[r['observation_id']].get('kline_date') or get_kline(payloads[r['observation_id']]).get('时间')) == r['kline_date'])
    add_check('payload_accepted_matches_normalized', lambda r: int(payloads[r['observation_id']]['accepted']) == r['accepted_capture'])
    add_check('display_values_match_eight_numeric_columns', lambda r: numeric_display(payloads[r['observation_id']]['values']) == [r[k] for k in FIELDS])
    add_check('eight_numeric_columns_non_null_finite', lambda r: all(isinstance(r[k], (int,float)) and math.isfinite(r[k]) for k in FIELDS))
    add_check('costs_strictly_positive', lambda r: all(r[k] > 0 for k in PRICE_FIELDS))
    add_check('cost_intervals_low_not_above_high', lambda r: r['cost90_low'] <= r['cost90_high'] and r['cost70_low'] <= r['cost70_high'])
    add_check('three_ratios_in_0_100', lambda r: all(0 <= r[k] <= 100 for k in RATIO_FIELDS))
    add_check('cost70_nested_in_cost90', lambda r: r['cost90_low'] <= r['cost70_low'] <= r['cost70_high'] <= r['cost90_high'], severity='descriptive_soft_check')
    add_check('average_in_cost90', lambda r: r['cost90_low'] <= r['average_cost_display'] <= r['cost90_high'], severity='descriptive_soft_check')
    add_check('average_in_cost70', lambda r: r['cost70_low'] <= r['average_cost_display'] <= r['cost70_high'], severity='descriptive_soft_check')
    add_check('concentration70_not_above_concentration90', lambda r: r['concentration70_pct'] <= r['concentration90_pct'], severity='descriptive_soft_check')
    add_check('model_input_approval_stays_zero', lambda r: r['model_input_approved'] == 0)
    add_check('complete_price_bins_stays_zero', lambda r: r['complete_price_bins'] == 0)

    # Independently re-read retained rendered HTML rather than only trust normalized columns.
    content_checks = []
    for r in observations:
        p = payloads[r['observation_id']]
        for e in evidence_by_obs[r['observation_id']]:
            if not e['exists_now'] or e['role'] not in ['summary_html','kline_html','record']:
                continue
            text = (ROOT / e['project_relative_path']).read_text(encoding='utf-8')
            if e['role'] == 'summary_html':
                actual, expected = parse_values(text, 'qcyq_t_v'), p['values']
            elif e['role'] == 'kline_html':
                actual, expected = parse_values(text, 'kline_date'), [r['kline_date']]
            else:
                actual, expected = json.loads(text), p
            content_checks.append({'observation_id': r['observation_id'], 'role': e['role'],
                                   'project_relative_path': e['project_relative_path'],
                                   'matches': actual == expected,
                                   **({'actual': actual, 'expected': expected} if actual != expected else {})})

    collection_stats = []
    for collection in sorted({r['collection'] for r in observations}):
        group = [r for r in observations if r['collection'] == collection]
        acc = [r for r in group if r['accepted_capture']]
        collection_stats.append({'collection': collection, 'observations': len(group), 'accepted': len(acc),
                                 'rejected': len(group)-len(acc), 'accepted_unique_dates': len({r['actual_date'] for r in acc}),
                                 'accepted_date_min': min(r['actual_date'] for r in acc),
                                 'accepted_date_max': max(r['actual_date'] for r in acc),
                                 'precise_observation_time_missing': sum(not r['observed_at_utc'] for r in group)})
    contexts = []
    for key in sorted({(r['collection'],r['context']) for r in observations}):
        group = [r for r in observations if (r['collection'],r['context']) == key]
        contexts.append({'collection': key[0], 'context': key[1], 'observations': len(group),
                         'accepted': sum(r['accepted_capture'] for r in group)})
    ranges = {scope: {k: {'min': min(r[k] for r in rows), 'max': max(r[k] for r in rows),
                          'observations': len(rows), 'unit': 'percent' if k in RATIO_FIELDS else 'displayed_price_basis_unverified'}
                      for k in FIELDS} for scope,rows in [('all',observations),('accepted',accepted)]}

    per_date = []
    differences = []
    accepted_by_date = collections.defaultdict(list)
    for r in accepted:
        accepted_by_date[r['actual_date']].append(r)
    for date in accepted_dates:
        rows = accepted_by_date[date]
        variants = collections.defaultdict(list)
        for r in rows:
            variants[tuple(r[k] for k in FIELDS)].append(r)
        per_date.append({'date': date, 'accepted_observations': len(rows), 'distinct_value_sets': len(variants),
                         'observation_ids': [r['observation_id'] for r in rows],
                         'repeat_evidence_state': ('single_observation_no_repeat_test' if len(rows)==1 else
                                                   'observed_differences' if len(variants)>1 else 'repeated_observations_equal_within_samples'),
                         'historical_first_availability': 'not_certified', 'model_input_approved': False})
        if len(variants) > 1:
            version_rows = []
            for i,(key, group) in enumerate(sorted(variants.items()), 1):
                version_rows.append({'version_label': f'V{i}', 'values': dict(zip(FIELDS,key)),
                                     'display_values': payloads[group[0]['observation_id']]['values'],
                                     'observations': [{'observation_id': r['observation_id'], 'collection':r['collection'],
                                                       'context':r['context'], 'observed_at_utc':r['observed_at_utc'],
                                                       'session':payloads[r['observation_id']].get('session'),
                                                       'phase':payloads[r['observation_id']].get('phase'),
                                                       'experiment':payloads[r['observation_id']].get('experiment'),
                                                       'visible_range_approx':payloads[r['observation_id']].get('visible_range_approx'),
                                                       'evidence': evidence_by_obs[r['observation_id']]}
                                                      for r in group]})
            kline_fields = {}
            for k in ['开盘','收盘','最高','最低','成交量','成交额','换手率']:
                vals = [get_kline(payloads[r['observation_id']]).get(k) for r in rows]
                available = [v for v in vals if v is not None]
                kline_fields[k] = {'observations_with_field':len(available),'distinct_values':sorted(set(available)),
                                   'enough_for_pairwise_comparison':len(available)>=2,
                                   'all_available_equal':len(set(available))==1 if len(available)>=2 else None}
            differences.append({'date':date,'accepted_observations':len(rows),'distinct_value_sets':len(variants),
                                'versions':version_rows, 'varying_numeric_fields':[k for k in FIELDS if len({r[k] for r in rows})>1],
                                'field_ranges_without_averaging': {k:{'min':min(r[k] for r in rows),'max':max(r[k] for r in rows),
                                                                     'max_minus_min':round(max(r[k] for r in rows)-min(r[k] for r in rows),10)} for k in FIELDS},
                                'kline_display_comparison':kline_fields,'cause_verified':False,
                                'version_selected_as_truth':None,'version_average_computed':False})

    # Predeclared, traceable comparisons; their baselines overlap and are not independent replications.
    comparison_specs = [
        ('no_action_same_session','round2:R1_baseline','round2:R1_no_action_repeat','未操作复读；最接近固定条件；只有一对'),
        ('adjacent_return_same_session','round2:R1_baseline','round2:R1_return_1','相邻K线后返回，同一R1会话'),
        ('adjacent_return_same_session','round2:R1_baseline','round2:R1_return_2','第二次相邻K线后返回，同一R1会话'),
        ('pan_return_same_session','round2:R1_baseline','round2:R1_pan_return','平移返回；不认证载入范围完全不变'),
        ('pan_return_same_session','round2:R1_baseline','round2:R1_pan_later_corrected','平移后修正到目标日；拒绝尝试不冒充此证据'),
        ('pan_return_same_session','round2:R1_baseline','round2:R1_pan_return_2','第二次平移返回；不认证载入范围完全不变'),
        ('early_return_window','round1:B_20230620','round1:A2_20230620','早期会话返回视窗；两条精确采集时间缺失'),
        ('default_recent_cross_session','refine_oct17:fresh_default_latest','repeat_oct22:new_session_oct16_default','默认近期载入跨采集会话；完整加载起止未记录'),
        ('adjacent_return_same_session','repeat_oct22:new_session_oct16_default','repeat_oct22:new_session_oct16_return','默认近期窗口相邻日返回'),
        ('adjacent_return_same_session','repeat_oct22:expanded_oct16','repeat_oct22:expanded_oct16_return','扩展窗口相邻日返回'),
    ]
    full_by_date = collections.defaultdict(list)
    for r in accepted:
        if r['collection']=='full_capture':
            full_by_date[r['actual_date']].append(r)
    for date,rows in sorted(full_by_date.items()):
        if len(rows)>1:
            assert len(rows)==2
            comparison_specs.append(('cross_window_overlap_same_session',rows[0]['observation_id'],rows[1]['observation_id'],
                                     '全量采集窗口交叠；不同stage不当作严格相同加载context'))
    comparisons = []
    for category,a,b,note in comparison_specs:
        left,right = by_id[a],by_id[b]
        differing = [k for k in FIELDS if left[k]!=right[k]]
        comparisons.append({'category':category,'left':a,'right':b,'date':left['actual_date'],
                            'same_date':left['actual_date']==right['actual_date'],
                            'both_accepted':left['accepted_capture']==right['accepted_capture']==1,
                            'equal_eight_numeric_fields':not differing,'differing_fields':differing,'scope_note':note})

    rejection_ledger = []
    for r in rejected:
        post = post_state(r)
        reasons = []
        if r['expected_date']!=r['actual_date']:
            reasons.append('expected_date_differs_from_summary_date')
        if r['actual_date']!=r['kline_date']:
            reasons.append('summary_date_differs_from_kline_date')
        if post and not post_sync(r):
            reasons.append('post_date_or_visibility_not_target_synchronized')
        rejection_ledger.append({'observation_id':r['observation_id'],'collection':r['collection'],
                                 'expected_date':r['expected_date'],'actual_date':r['actual_date'],
                                 'kline_date':r['kline_date'],'post':post,'reasons':reasons,
                                 'retained_in_raw_observations':True,'accepted_for_date_coverage':False,
                                 'missing_evidence_roles':[e['role'] for e in evidence_by_obs[r['observation_id']] if not e['exists_now']]})

    timestamp_missing = [r['observation_id'] for r in observations if not r['observed_at_utc']]
    timestamp_invalid = []
    for r in observations:
        if r['observed_at_utc']:
            try:
                parsed = dt.datetime.fromisoformat(r['observed_at_utc'].replace('Z','+00:00'))
                if parsed.tzinfo is None:
                    timestamp_invalid.append(r['observation_id'])
            except ValueError:
                timestamp_invalid.append(r['observation_id'])
    coverage_mismatches = []
    for d in per_date:
        c = daily_coverage.get(d['date'])
        if c is None or c['chip_accepted_observations']!=d['accepted_observations'] or c['chip_distinct_value_sets']!=d['distinct_value_sets']:
            coverage_mismatches.append(d['date'])
    sources_verification = []
    for s in sources:
        path = ROOT / s['source_path']
        sources_verification.append({'dataset_id':s['dataset_id'],'path':s['source_path'],
                                     'exists_now':path.is_file(), 'stored_sha256':s['source_sha256'],
                                     'actual_sha256':sha256(path) if path.is_file() else None,
                                     'matches':path.is_file() and sha256(path)==s['source_sha256']})
    after = fingerprint(DB)
    assert before == after, 'Read-only audit detected source DB fingerprint change'
    assert len(observations)==954 and len(accepted)==943 and len(rejected)==11 and len(accepted_dates)==915
    assert len(differences)==5
    summary = {
        'observations':len(observations),'accepted_observations':len(accepted),'rejected_observations':len(rejected),
        'accepted_unique_dates':len(accepted_dates),'date_min':accepted_dates[0],'date_max':accepted_dates[-1],
        'repeated_dates':sum(d['accepted_observations']>1 for d in per_date),
        'single_observation_dates':sum(d['accepted_observations']==1 for d in per_date),
        'repeated_equal_dates':sum(d['accepted_observations']>1 and d['distinct_value_sets']==1 for d in per_date),
        'different_version_dates':len(differences),'different_version_date_list':[d['date'] for d in differences],
        'precise_capture_time_present':len(observations)-len(timestamp_missing),'precise_capture_time_missing':len(timestamp_missing),
        'historical_first_availability_certified_dates':0,'historical_first_availability_uncertified_dates':len(accepted_dates),
        'complete_price_bin_dates':0,'model_approved_observations':sum(r['model_input_approved'] for r in observations),
        'evidence_links':len(evidence),'evidence_unique_paths':len(inventory),'evidence_missing_links':len(missing),
        'evidence_present_hash_mismatches':len(hash_mismatch),'source_database_unchanged':before==after,
        'file_assets_catalog_missing_links':sum(not e['file_assets_catalog_present'] for e in all_edges),
        'file_assets_catalog_missing_unique_paths':len({e['project_relative_path'] for e in all_edges if not e['file_assets_catalog_present']}),
        'predeclared_repeat_comparisons':len(comparisons),'repeat_comparisons_equal':sum(c['equal_eight_numeric_fields'] for c in comparisons),
        'independent_repeat_experiment_count':None,
        'all_accepted_initial_date_sync_pass':checks['initial_date_synchronization_accepted']['flagged']==0,
        'rendered_summary_checked':sum(c['role']=='summary_html' for c in content_checks),
        'rendered_summary_mismatches':sum(c['role']=='summary_html' and not c['matches'] for c in content_checks),
    }
    observation_ledger = []
    for r in observations:
        observation_ledger.append({k:v for k,v in r.items() if k!='payload_json'} |
                                  {'display_values':payloads[r['observation_id']]['values'],
                                   'payload_post':post_state(r), 'payload_session':payloads[r['observation_id']].get('session'),
                                   'payload_phase':payloads[r['observation_id']].get('phase'),
                                   'accessibility_source_marker':payloads[r['observation_id']].get('accessibility_source'),
                                   'failed_or_flagged_checks':[k for k,v in checks.items() if r['observation_id'] in v['flagged_observation_ids']],
                                   'historical_first_availability':'not_certified',
                                   'evidence':evidence_by_obs[r['observation_id']]})
    audit_result = {
        'audit_version':'chip-summary-quality-v1','requested_date':'2026-10-25',
        'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'source_database':{'read_mode':'sqlite URI mode=ro&immutable=1; PRAGMA query_only=ON',
                           'before':before,'after':after,'unchanged':before==after,
                           'integrity_check':integrity,'foreign_key_violations':foreign_key_violations},
        'scope':{'source':'existing unified DB and referenced local evidence only','new_capture':False,
                 'future_returns_computed':False,'prediction_probabilities_computed':False,
                 'version_averaging':False,'version_selection':False,'existing_database_or_documents_modified':False,
                 'display_precision':'compare stored displayed values, not unobserved algorithm precision'},
        'summary':summary,'collection_counts':collection_stats,'context_counts':contexts,
        'checks':checks,'numeric_ranges':ranges,
        'ratio_boundary_observations':{k:{str(boundary):[r['observation_id'] for r in accepted if r[k]==boundary]
                                          for boundary in [0,100]} for k in RATIO_FIELDS},
        'soft_check_interpretation':'区间嵌套、平均成本处于区间和集中度相对次序仅为样本描述，不是无算法定义时的数学硬必然，不单独授予或撤销资格。',
        'date_sync_details':{'accepted_with_post_check':len(accepted_with_post),
                             'accepted_without_post_check':[r['observation_id'] for r in accepted if not post_state(r)],
                             'raw_actual_key_disagrees_with_summary_date':[r['observation_id'] for r in observations
                                  if payloads[r['observation_id']].get('actual') is not None and payloads[r['observation_id']]['actual']!=r['actual_date']],
                             'raw_actual_key_note':'full_capture.payload.actual 是鼠标命中/K线日期；规范化actual_date来自筹码摘要date/values[0]；拒绝记录中的不同值保留，不能覆盖。'},
        'rejection_ledger':rejection_ledger,'date_ledger':per_date,'cross_version_differences':differences,
        'repeatability':{'comparisons':comparisons,'all_pairs_are_independent':False,
                         'full_loaded_history_range_or_algorithm_version_verified':False,
                         'strict_no_action_pair_count':sum(c['category']=='no_action_same_session' for c in comparisons),
                         'no_repeat_means_stable':False,
                         'limitations':['比较组共享基准，不能当作18次独立实验。','同名context不保证同一加载条件：round2还包含扩展较早历史的R2记录。',
                                        '可见范围不等于实际算法使用的载入范围；完整初始化、修订、算法版本未认证。',
                                        '单次读取的902日期没有重复性结论；8日重复相同也仅对现存样本成立。']},
        'evidence_verification':{'role_counts':evidence_role_stats,'missing_links':missing,
                                 'present_hash_mismatches':hash_mismatch,
                                 'stored_exists_flags_disagree_now':[e for e in all_edges if not e['stored_exists_matches_now']],
                                 'file_assets_catalog_missing_entries':[e for e in all_edges if not e['file_assets_catalog_present']],
                                 'file_assets_hash_disagreements':[e for e in all_edges if e['file_assets_hash_matches'] is False],
                                 'files':list(inventory.values()),'content_checks':content_checks,
                                 'accessibility_explicit_dom_snapshot_markers':sum(payloads[r['observation_id']].get('accessibility_source')=='playwright_dom_snapshot' for r in observations),
                                 'manual_image_spot_checks':[{'observation_id':'repeat_oct22:expanded_oct16',
                                   'path':'work/chip_audit_oct22/records/expanded_oct16/chart.jpg',
                                   'result':'已目视确认K线与筹码面板同为2026-10-16，摘要1.73%、13.08及区间与保存值一致。截图裁剪未显示复权工具栏。'}],
                                 'image_content_all_rows_certified':False,
                                 'hash_interpretation':'哈希一致只证明本地文件与归档指纹一致，不证明供应商算法、历史可得性或每张截图内容正确。'},
        'source_indexes_verification':sources_verification,
        'coverage_reconciliation':{'trade_condition_dates':len(study_dates),
                                   'accepted_dates_not_in_trade_conditions':sorted(set(accepted_dates)-study_dates),
                                   'trade_condition_dates_without_accepted_chip':sorted(study_dates-set(accepted_dates)),
                                   'daily_coverage_count_or_version_mismatches':coverage_mismatches,
                                   'existing_conflict_dates':sorted(r['reference_date'] for r in existing_conflicts),
                                   'recomputed_conflict_dates_match':sorted(r['reference_date'] for r in existing_conflicts)==[d['date'] for d in differences]},
        'time_and_semantics':{'capture_times_missing_observation_ids':timestamp_missing,
                              'capture_times_invalid_or_timezone_missing':timestamp_invalid,
                              'capture_time_not_first_publication_time':True,
                              'historical_certification_status':'全部915日均无历史当时可得认证；当前网页回看观察不能替代当时发布、首次接收及修订链。',
                              'kline_basis_control_counts':dict(collections.Counter(r['kline_basis_control'] for r in observations)),
                              'chip_adjustment_basis_verified_observations':0,
                              'kline_control_not_chip_basis_certification':True,
                              'profit_ratio_not_up_probability':True},
        'observation_ledger':observation_ledger,
    }
    write_json(OUT / '筹码摘要质量台账.json', audit_result)
    write_json(WORK / '核查摘要.json', summary)
    write_report(audit_result)
    verification = validate_result(audit_result)
    write_json(WORK / '针对性验证.json', verification)
    print(json.dumps({'summary':summary,'validation':verification,'outputs':[str((OUT/f).relative_to(ROOT)) for f in ['筹码摘要质量台账.json','筹码摘要质量报告.md']]},ensure_ascii=False,indent=2))


def write_report(a):
    s=a['summary']; c=a['checks']; ev=a['evidence_verification']
    text = []
    text.append('# 现有筹码摘要质量核查（2026-10-25）\n')
    text.append(f"核查结论：现有底座保存 **{s['observations']}条观察、{s['accepted_observations']}条接受、{s['rejected_observations']}条拒绝**，接受记录覆盖 **{s['accepted_unique_dates']}个日期（{s['date_min']}至{s['date_max']}）**。结构、日期同步与证据指纹有明确可核查结果；**全部915日仍无历史当时可得认证，模型输入获准数为0**。完整价格档为0日。\n")
    text.append('本次只读统一数据底座及其本地证据，没有新增网页采集、修改既有数据库或文档，没有计算未来收益、预测概率，没有对多个版本求平均或挑选“较好”版本。接受表示通过原采集的日期/留证门槛，不表示算法、复权、完整性或历史使用资格获准。\n')
    text.append('## 1. 数据覆盖与collection\n')
    text.append(md_table(['collection','观察','接受','拒绝','接受唯一日期','接受日期范围','精确采集时间缺失'],[
        [r['collection'],r['observations'],r['accepted'],r['rejected'],r['accepted_unique_dates'],r['accepted_date_min']+'～'+r['accepted_date_max'],r['precise_observation_time_missing']] for r in a['collection_counts']]))
    text.append('\n各collection日期相互重叠，不能把列内日期数相加当作新增覆盖。915日期与底座trade_conditions的915日期完全对齐；daily_coverage保存的接受观察数及版本数逐日重算一致，现有5条chip冲突日期也与本次重算一致。这里核对的是底座内部覆盖，不新增官方交易日历认证。\n')
    text.append(f"915日中，**{s['single_observation_dates']}日只有1条接受观察**；{s['repeated_dates']}日有重复，其中{s['repeated_equal_dates']}日现存摘要相同、{s['different_version_dates']}日不同。单样本日没有重复性证据；重复相同也只说明这些读取一致，不能据此称全历史稳定。\n")
    text.append('## 2. 日期同步及11条拒绝记录\n')
    text.append(f"943条接受记录均满足预期日期＝筹码摘要日期＝K线日期；其中{a['date_sync_details']['accepted_with_post_check']}条另有读取后的post日期/可见性检查且全部通过，13条早期接受记录没有post字段，不能补写成已有复核。\n")
    text.append('11条拒绝记录全部保留并排除覆盖：10条初始摘要日期与目标日不同；另1条初始三日期一致，但post检查发现筹码面板已跳回最新日期。7条拒绝记录同时出现筹码日期与K线日期不一致。原因计数重叠。\n')
    text.append(md_table(['拒绝观察','预期','筹码','K线','post筹码','缺失证据'],[
        [r['observation_id'],r['expected_date'],r['actual_date'],r['kline_date'],(r['post'] or {}).get('date','无'),','.join(r['missing_evidence_roles']) or '无'] for r in a['rejection_ledger']]))
    text.append('\n注意：原payload中的actual在full_capture里记录鼠标命中/K线日期；规范化actual_date来自筹码面板date/values[0]。7条拒绝记录这两种“actual”不同是实际日期错位的留痕，不能用预期日期或文件名覆盖真实筹码日期。\n')
    text.append('## 3. 数值与区间检查\n')
    text.append(md_table(['检查','范围','通过','标记','解释'],[
        ['8数值非空且有限','954条',c['eight_numeric_columns_non_null_finite']['passed'],c['eight_numeric_columns_non_null_finite']['flagged'],'与原display values逐项一致'],
        ['成本为正、区间下限≤上限','954条',c['cost_intervals_low_not_above_high']['passed'],c['cost_intervals_low_not_above_high']['flagged'],'基础结构检查'],
        ['获利比例、两集中度在0～100%','954条',c['three_ratios_in_0_100']['passed'],c['three_ratios_in_0_100']['flagged'],'仅范围合理性'],
        ['70%区间嵌于90%区间','954条',c['cost70_nested_in_cost90']['passed'],c['cost70_nested_in_cost90']['flagged'],'软检查'],
        ['平均成本处于90%区间','954条',c['average_in_cost90']['passed'],c['average_in_cost90']['flagged'],'软检查'],
        ['平均成本处于70%区间','954条',c['average_in_cost70']['passed'],c['average_in_cost70']['flagged'],'软检查'],
        ['70%集中度≤90%集中度','954条',c['concentration70_not_above_concentration90']['passed'],c['concentration70_not_above_concentration90']['flagged'],'软检查'],
    ]))
    text.append('\n接受记录的实际显示范围如下；按943条带版本观察统计上下界，不生成单日合成值。价格字段保留网页显示单位和未认证口径，不推定为前复权价格。\n')
    text.append(md_table(['字段','最小','最大'],[[LABELS[k],fmt_number(v['min']),fmt_number(v['max'])] for k,v in a['numeric_ranges']['accepted'].items()]))
    boundary=a['ratio_boundary_observations']['profit_ratio_pct']
    text.append(f"\n获利比例恰为0%的接受观察有{len(boundary['0'])}条，恰为100%的有{len(boundary['100'])}条，均按闭区间合法边界保留；不把0改为缺失，也不把100解释成未来必涨。\n")
    text.append('\n区间嵌套、平均成本位置及集中度次序只作描述性检查。没有供应商算法及区间定义时，不把它们当成硬性数学必然；即使所有样本通过，也不构成算法正确证明。数值范围通过同样不能证明价格档完整、统计定义正确或历史可得。\n')
    text.append('## 4. 五个同日跨版本日：全部列值\n')
    text.append('版本标签仅按本次数值向量排序，便于引用，没有优先级。下列8个数值列完整列出，每版的全部观察ID、collection、context、时间和证据路径/哈希见JSON的cross_version_differences。不同版本没有被平均、删去或选定为真值。\n')
    for d in a['cross_version_differences']:
        text.append(f"### {d['date']}：{d['accepted_observations']}条接受观察，{d['distinct_value_sets']}套值\n")
        text.append(md_table(['版','获利%','均成本','90%成本','90%集中%','70%成本','70%集中%','观察数'],[
            [v['version_label'],v['display_values'][1],v['display_values'][2],v['display_values'][3],v['display_values'][4],v['display_values'][5],v['display_values'][6],len(v['observations'])] for v in d['versions']]))
        text.append('\n'+md_table(['版','观察ID / collection / context / UTC采集时间'],[
            [v['version_label'],'；'.join(f"{o['observation_id']} / {o['collection']} / {o['context']} / {o['observed_at_utc'] or '缺失'}" for o in v['observations'])] for v in d['versions']]))
        varied=', '.join(LABELS[k] for k in d['varying_numeric_fields'])
        text.append(f"\n不同数值列：{varied}。变动幅度（最大－最小）已按列写入台账，只描述版本差异，不产生平均或择优值。\n")
    text.append('五日各自的已保存K线OHLC均相同；量、额、换手率在有该字段的记录中也相同，早期round1缺少后三项，未把缺项判作相等实测。差异确实出现在筹码摘要读数中；同时存在历史载入、窗口、会话或刷新差异，唯一原因和正确版本均未认证。\n')
    text.append('## 5. 同加载条件附近的重复性证据\n')
    category_labels={
        'no_action_same_session':'同会话不操作复读', 'adjacent_return_same_session':'相邻K线后返回',
        'pan_return_same_session':'平移/返回诊断', 'early_return_window':'早期返回视窗',
        'default_recent_cross_session':'默认近期窗口跨会话',
        'cross_window_overlap_same_session':'全量同会话跨窗口交叠',
    }
    categories=collections.Counter(r['category'] for r in a['repeatability']['comparisons'])
    text.append(md_table(['比较类别','比较对','8数值均相同的对数','可解释范围'],[
        [category_labels[k],n,sum(r['category']==k and r['equal_eight_numeric_fields'] for r in a['repeatability']['comparisons']),
         '只限现存样本；完整载入范围/算法版本未认证'] for k,n in categories.items()]))
    text.append('\n18对预先明确ID的比较全部相同，但比较共享基准，不能解释为18次独立实验。最接近严格固定条件的不操作复读仅1对（2023-06-20，R1）；同会话相邻返回4对，平移诊断3对、早期视窗返回1对、默认近期载入跨会话1对、跨窗口交叠8对。后四类条件相近但强度各异，完整加载范围没有被认证。\n')
    text.append('同名context也不自动可比：round2的context统一写为round2，但其中R1记录与较后扩展历史的R2记录在2023-06-20有两套值。本次使用原payload的session、phase、experiment及明确操作ID区分，保留条件改变后的差异。902个单次读取日的重复性状态为“未检验”，不是“稳定”。\n')
    text.append('## 6. 证据存在、哈希与内容核对\n')
    text.append(md_table(['证据角色','引用数','当前存在','SHA256一致','缺失'],[[r['role'],r['links'],r['exists_now'],r['hash_matches'],r['missing']] for r in ev['role_counts']]))
    n_existing=sum(f['exists_now'] for f in ev['files'])
    text.append(f"\n共4756条证据引用、4744个唯一路径，当前存在{n_existing}个文件；4753条存在的引用全部与底座哈希一致，存在文件哈希不一致为0，存在标记与本次检查不一致为0。共享记录索引按唯一路径只重算一次哈希，引用不被当作独立文件。\n")
    uncataloged=ev['file_assets_catalog_missing_entries']
    uncataloged_present_paths={r['project_relative_path'] for r in uncataloged if r['exists_now']}
    text.append(f"**另有资产目录覆盖缺口**：file_assets未收录round1、round2、refine_oct17对应的{s['file_assets_catalog_missing_links']}条证据引用、{s['file_assets_catalog_missing_unique_paths']}个唯一路径。其中{len(uncataloged_present_paths)}个文件当前存在，且它们的chip_evidence_files指纹均相符；另3个为上述拒绝尝试缺失文件。已在file_assets中出现的4690条引用，跨表指纹没有冲突。这是总资产目录与专门筹码证据表之间的覆盖差异，不等于66份文件丢失，也不能因此省略该目录缺口。本次只登记，不改旧DB。\n")
    role_content=collections.defaultdict(list)
    for r in ev['content_checks']:role_content[r['role']].append(r)
    text.append(md_table(['内容检查','已读文件','与原记录一致','不一致'],[[role,len(rows),sum(r['matches'] for r in rows),sum(not r['matches'] for r in rows)] for role,rows in sorted(role_content.items())]))
    text.append('\n缺失的3份证据全部属于已拒绝的round2:R1_pan_later：summary_html、accessibility、chart。其原records.json索引存在；不会拿R1_pan_later_corrected的证据补作失败尝试的证据。接受记录的摘要HTML、截图、文本证据均存在并通过存档指纹核对。\n')
    text.append('940份单条record.json与DB payload逐项比较；953份现存摘要HTML重新提取7个显示值核对；940份K线HTML重新提取日期核对。58条明确标记accessibility_source=playwright_dom_snapshot，台账保留该标记，不能因文件名为ax.txt便把它们全部描述为原生AX。只目视抽查1张现存截图（expanded_oct16），日期及摘要吻合；本次未逐张图像OCR认证。哈希一致证明归档文件未变，不能证明源算法或历史真实性。\n')
    text.append('## 7. 时间、复权与后续使用边界\n')
    text.append(f"954条中{s['precise_capture_time_present']}条有带时区的精确采集时间，4条round1记录缺失。缺失ID为："+'、'.join(a['time_and_semantics']['capture_times_missing_observation_ids'])+'。已有日期级核查日不能补造精确时刻；已有采集时间也只是2026年回看网页的读取时间，不是对应历史日的首次公开或首次可用时间。\n')
    text.append('954条记录的K线复权控制均记为“前复权”。即使截图或页面控件显示前复权，它也只认证当时K线控件，**不等于筹码价格已经获得前复权口径认证**。本次查看的expanded_oct16截图裁剪未显示复权工具栏，未把它作为新增控件证据。筹码算法版本、初始化、实际载入范围、复权与修订链仍未认证。获利比例是网页统计读数，不能读作未来上涨概率。\n')
    text.append('后续可以把这些内容用于带来源、时间、版本和限制的观察性质量研究；若要进入历史预测输入，仍需补齐历史当时可得、算法/初始化/复权口径和修订证据。发现5日差异应保留每版，不为得到一条平滑序列而平均或挑版本；其余日也不因暂未发现差异而自动获准。\n')
    text.append('## 8. 只读保护与交付\n')
    fp=a['source_database']['before']
    text.append(f"统一DB以mode=ro&immutable=1连接并开启query_only；integrity_check={a['source_database']['integrity_check']}，外键检查违规数={len(a['source_database']['foreign_key_violations'])}。源文件前后字节数、mtime_ns、SHA256均一致。\n\n前后SHA256：`{fp['sha256']}`。\n")
    text.append('- `筹码摘要质量台账.json`：全954条观察、915日状态、5日全部版本、18对比较、每条证据存在/哈希、全部结构检查。\n- `work/chip_summary_quality_oct25/audit_chip_summary.py`：可重复运行脚本。\n- `work/chip_summary_quality_oct25/针对性验证.json`：针对日期错位、拒绝记录、数值边界、版本差异、证据缺失及只读保护的验证结果。\n')
    (OUT/'筹码摘要质量报告.md').write_text('\n'.join(text),encoding='utf-8')


def validate_result(a):
    s=a['summary'];c=a['checks'];ev=a['evidence_verification']
    assertions={
        '954_equals_943_plus_11':s['observations']==s['accepted_observations']+s['rejected_observations']==954,
        'accepted_dates_915':len(a['date_ledger'])==915,
        'collection_counts_reconcile':sum(r['observations'] for r in a['collection_counts'])==954,
        '943_accepted_date_sync':c['initial_date_synchronization_accepted']['passed']==943,
        '930_accepted_post_sync':c['post_date_visibility_accepted_where_available']['passed']==930,
        'late_rollover_rejection_preserved':any(r['observation_id']=='full_capture:0068_2023-04-13_window1' and r['expected_date']==r['actual_date']==r['kline_date'] and r['post']['date']!=r['expected_date'] for r in a['rejection_ledger']),
        'rejected_round2_missing_three_roles':next(r for r in a['rejection_ledger'] if r['observation_id']=='round2:R1_pan_later')['missing_evidence_roles']==['accessibility','chart','summary_html'],
        'five_version_dates_reconcile':s['different_version_date_list']==['2023-01-03','2023-06-19','2023-06-20','2026-10-15','2026-10-16'],
        'version_counts_2_2_4_3_3':[r['distinct_value_sets'] for r in a['cross_version_differences']]==[2,2,4,3,3],
        'display_matches_all_954':c['display_values_match_eight_numeric_columns']['passed']==954,
        '953_html_summaries_match':sum(r['role']=='summary_html' and r['matches'] for r in ev['content_checks'])==953,
        '940_kline_html_dates_match':sum(r['role']=='kline_html' and r['matches'] for r in ev['content_checks'])==940,
        '940_record_payloads_match':sum(r['role']=='record' and r['matches'] for r in ev['content_checks'])==940,
        'no_existing_evidence_hash_mismatch':len(ev['present_hash_mismatches'])==0,
        '4753_evidence_link_hashes_match':sum(r['hash_matches'] for r in ev['role_counts'])==4753,
        'asset_catalog_gap_separated_from_hash_conflict':len(ev['file_assets_catalog_missing_entries'])==66 and s['file_assets_catalog_missing_unique_paths']==54 and len(ev['file_assets_hash_disagreements'])==0,
        'ratio_boundaries_preserved':len(a['ratio_boundary_observations']['profit_ratio_pct']['0'])>0 and len(a['ratio_boundary_observations']['profit_ratio_pct']['100'])>0 and c['three_ratios_in_0_100']['passed']==954,
        'six_source_index_links_match':len(a['source_indexes_verification'])==6 and all(r['matches'] for r in a['source_indexes_verification']),
        '18_comparisons_all_equal':s['predeclared_repeat_comparisons']==s['repeat_comparisons_equal']==18,
        '902_single_dates_not_marked_stable':sum(r['repeat_evidence_state']=='single_observation_no_repeat_test' for r in a['date_ledger'])==902,
        'every_915_date_uncertified':all(r['historical_first_availability']=='not_certified' and r['model_input_approved'] is False for r in a['date_ledger']),
        'four_missing_times_preserved':len(a['time_and_semantics']['capture_times_missing_observation_ids'])==4,
        'db_before_after_identical':a['source_database']['before']==a['source_database']['after'],
        'coverage_and_conflicts_reconcile':not a['coverage_reconciliation']['daily_coverage_count_or_version_mismatches'] and a['coverage_reconciliation']['recomputed_conflict_dates_match'],
        'no_average_or_selected_version':all(r['version_average_computed'] is False and r['version_selected_as_truth'] is None for r in a['cross_version_differences']),
    }
    result={'checks':assertions,'passed':sum(assertions.values()),'failed':sum(not x for x in assertions.values())}
    assert result['failed']==0,json.dumps(result,ensure_ascii=False)
    return result


if __name__=='__main__':
    audit()
