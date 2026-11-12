"""Read-only October 25 checkpoint audit; writes only beside this script.

Does not generate labels, fetch data, or repeat the project-wide file hash audit.
"""
from pathlib import Path
import copy
import hashlib
import json
import sqlite3
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = Path('/Users/puchun/Documents/Codex/项目归档/ni/20261025_三线研究启动完整保存')
BASE = 'outputs/三线研究启动_20261025/量价基线/'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def ro(path):
    c = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def db_inventory(rel):
    result = {'path': rel, 'tables': {}}
    with ro(ROOT / rel) as c:
        result['quick_check'] = c.execute('PRAGMA quick_check').fetchone()[0]
        for row in c.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name").fetchall():
            name = row['name']
            cols = [r['name'] for r in c.execute('PRAGMA table_info(' + quote(name) + ')')]
            table = {'schema': row['sql'], 'columns': cols,
                     'rows': c.execute('SELECT count(*) FROM ' + quote(name)).fetchone()[0],
                     'date_bounds': {}, 'gates': {}}
            for col in cols:
                if col in {'trade_date', 'signal_date', 'entry_observation_date', 'outcome_observation_date', 'asof_date'}:
                    table['date_bounds'][col] = list(c.execute('SELECT min(' + quote(col) + '),max(' + quote(col) + ') FROM ' + quote(name)).fetchone())
                if col in {'daily_status_certified', 'model_input_approved', 'runtime_usable', 'execution_modelled',
                           'native_supplier_bins_acquired', 'is_predictive_probability', 'is_trading_profit_probability'}:
                    table['gates'][col] = [list(r) for r in c.execute('SELECT ' + quote(col) + ',count(*) FROM ' + quote(name) + ' GROUP BY ' + quote(col))]
            result['tables'][name] = table
    return result


def mask_and_existing_overlap():
    with ro(ROOT / BASE / '日线特征与信号.sqlite') as c:
        bars = [dict(r) for r in c.execute('SELECT * FROM input_bars ORDER BY trade_date')]
        fs = [dict(r) for r in c.execute('SELECT * FROM features ORDER BY trade_date')]
        segments = [dict(r) for r in c.execute('SELECT segment_start,count(*) n,min(trade_date) start,max(trade_date) end,min(CASE WHEN macd_dif IS NOT NULL THEN trade_date END) first_macd,min(CASE WHEN kdj_k IS NOT NULL THEN trade_date END) first_kdj FROM features GROUP BY segment_start')]
    with ro(ROOT / BASE / '开发期结果隔离.sqlite') as c:
        labels = [dict(r) for r in c.execute('SELECT * FROM development_price_outcomes ORDER BY signal_date')]
    dates = [b['trade_date'] for b in bars]
    index = {d: i for i, d in enumerate(dates)}
    windows = [(index[r['entry_observation_date']], index[r['outcome_observation_date']]) for r in labels]
    overlap = lambda a, b: max(a[0], b[0]) <= min(a[1], b[1])
    grid = set([d for d in dates if '2023-01-03' <= d <= '2024-12-31'][::5])
    selected = [r for r in labels if r['signal_date'] in grid]
    fixed_windows = [(index[r['entry_observation_date']], index[r['outcome_observation_date']]) for r in selected]
    indicators = ['ma5', 'ma10', 'ma15', 'macd_dif', 'macd_dea', 'macd_hist2', 'kdj_rsv', 'kdj_k',
                  'kdj_d', 'kdj_j', 'volume_ratio_prev5', 'volume_ratio_prev20', 'turnover_ratio_prev5', 'close_change_prev']
    masks = {'before_calculation_start_rows': sum(r['segment_start'] is None for r in fs),
             'all_early_indicator_values_null': all(all(r[k] is None for k in indicators) for r in fs if r['segment_start'] is None),
             'macd_before_130_all_null': all(all(r[k] is None for k in ['macd_dif', 'macd_dea', 'macd_hist2']) for r in fs if r['segment_bars'] < 130),
             'kdj_before_30_all_null': all(all(r[k] is None for k in ['kdj_k', 'kdj_d', 'kdj_j']) for r in fs if r['segment_bars'] < 30),
             'known_ex_date_rows': [{'date': r['trade_date'], 'age': r['segment_bars'], 'all_indicators_null': all(r[k] is None for k in indicators)} for r in fs if r['known_ex_date']],
             'segments': segments}
    return {'mask_recheck': masks, 'existing_label_overlap': {
        'label_count': len(labels),
        'pairs_with_shared_entry_outcome_observations': sum(overlap(a, b) for i, a in enumerate(windows) for b in windows[i + 1:]),
        'adjacent_pairs_total': len(labels) - 1,
        'adjacent_pairs_with_shared_observations': sum(overlap(a, b) for a, b in zip(windows, windows[1:])),
        'fixed_grid_count': len(selected),
        'fixed_grid_shared_observation_pairs': sum(overlap(a, b) for i, a in enumerate(fixed_windows) for b in fixed_windows[i + 1:]),
        'no_independence_claim': True}}


def main():
    saved = json.loads((ROOT / BASE / '运行合同.json').read_text())
    archive_result = json.loads((ARCHIVE / '归档校验结果.json').read_text())
    manifest_path = ARCHIVE / '文件清单与SHA256.json'
    manifest = json.loads(manifest_path.read_text())
    archived = {r['archive_path']: r for r in manifest['files']}
    sources = {}
    for rel, expected in saved['source_hashes'].items():
        actual = sha(ROOT / rel)
        recorded = archived['project/' + rel]['sha256']
        sources[rel] = {'actual': actual, 'contract_expected': expected, 'archive_manifest_expected': recorded,
                        'all_match': actual == expected == recorded}

    zip_path = Path(archive_result['archive'])
    zip_hash = sha(zip_path)
    with zipfile.ZipFile(zip_path) as z:
        embedded_manifest = z.read('metadata/文件清单与SHA256.json')
        archive_check = {'sidecar_record': archive_result,
                         'zip_size_matches_sidecar': zip_path.stat().st_size == archive_result['zip_bytes'],
                         'zip_sha256_recomputed': zip_hash,
                         'zip_sha256_matches_sidecar': zip_hash == archive_result['sha256'],
                         'manifest_member_bytes_match_sidecar_manifest': embedded_manifest == manifest_path.read_bytes(),
                         'zip_member_count_including_directories_and_metadata': len(z.infolist()),
                         'project_wide_file_rehash_repeated': False,
                         'full_zip_crc_or_restore_test_repeated': False}

    old_artifacts = {}
    for rel in [BASE + '日线特征与信号.sqlite', BASE + '开发期结果隔离.sqlite',
                'outputs/三线研究启动_20261025/自建筹码样本/自建筹码小样本.sqlite',
                BASE + '运行合同.json', 'work/baseline_oct25/engineering_contract.json',
                'work/baseline_oct25/build_baseline.py']:
        actual = sha(ROOT / rel)
        expected = archived['project/' + rel]['sha256']
        old_artifacts[rel] = {'actual': actual, 'archive_manifest_expected': expected, 'match': actual == expected}

    inventories = [db_inventory(rel) for rel in [BASE + '日线特征与信号.sqlite', BASE + '开发期结果隔离.sqlite',
                    'outputs/三线研究启动_20261025/自建筹码样本/自建筹码小样本.sqlite']]

    with ro(ROOT / 'outputs/统一数据底座_20261022/统一数据底座.sqlite') as c:
        bars = [dict(r) for r in c.execute("SELECT * FROM stock_raw_reference WHERE trade_date <= '2024-12-31' ORDER BY trade_date")]
        actions = [dict(r) for r in c.execute('SELECT event_id,ex_date,cash_cny_per_10_gross,transfer_shares_per_10,first_publication_time,model_input_approved FROM corporate_actions ORDER BY ex_date')]
        jump = [dict(r) for r in c.execute("SELECT trade_date,open,close FROM stock_raw_reference WHERE trade_date IN ('2022-05-25','2022-05-26') ORDER BY trade_date")]
    # Execute only definitions; no main(), no source file imports or bytecode writes.
    code_path = ROOT / 'work/baseline_oct25/build_baseline.py'
    ns = {'__name__': '_readonly_checkpoint_audit', '__file__': str(code_path)}
    exec(compile(code_path.read_text(), str(code_path), 'exec'), ns)
    cfg = saved['contract']
    ex_dates = {r['ex_date'] for r in actions}
    base_features = ns['compute_features'](bars, ex_dates, cfg)
    probes = []
    for family, replacement in [
        ('macd', {'fast': 5, 'slow': 35, 'signal': 5, 'ema_seed': 'unsupported_seed', 'adjust': True, 'histogram_multiplier': 1}),
        ('kdj', {'window': 3, 'k_alpha': '1/2', 'd_alpha': '1/2', 'seed_k': 0, 'seed_d': 0, 'flat_range_rsv': 0, 'j_clipped': True}),
    ]:
        altered = copy.deepcopy(cfg)
        altered[family].update(replacement)
        output = ns['compute_features'](bars, ex_dates, altered)
        probes.append({'probe': family + '_advertised_parameter_changes', 'changed_fields': replacement,
                       'computation_accepted': True, 'features_identical': output == base_features,
                       'finding': 'Unsupported configuration is silently accepted and ignored. Current fixed saved contract agrees with the hard-coded implementation.'})
    reordered = copy.deepcopy(cfg)
    reordered['registered_signals'][0:2] = list(reversed(reordered['registered_signals'][0:2]))
    original_signals = ns['build_signals'](base_features, cfg)
    reordered_signals = ns['build_signals'](base_features, reordered)
    probes.append({'probe': 'registered_signal_names_reordered', 'computation_accepted': True,
                   'days_with_changed_named_signal_values': sum(a != b for a, b in zip(original_signals, reordered_signals)),
                   'finding': 'Names are zipped positionally to a fixed 12-value vector; reordering can silently mislabel signals.'})

    protocol = json.loads((ROOT / 'outputs/首版预测协议草案_20261016.json').read_text())
    report = {'audit_date': '2026-10-26', 'scope': 'Local read-only checkpoint audit; feature-only configuration probes through 2024; no new price labels.',
              'sources': sources, 'archive': archive_check, 'old_artifact_hashes': old_artifacts,
              'derived_database_inventory': inventories, 'known_actions': actions, 'unbridged_jump_raw_observations': jump,
              'unbridged_overnight_open_fraction': jump[1]['open'] / jump[0]['close'] - 1,
              'configuration_probes': probes,
              'protocol': {'status': protocol['status'], 'runtime_usable': protocol['runtime_usable'],
                           'all_pending_freeze_fields_still_null': all(v is None for v in protocol['pending_freeze'].values())},
              'limitations': ['No repeated audit of all 5390/10922 project files.',
                              'Archived full per-file, ZIP-member, and restored-SQLite checks are accepted as recorded; current ZIP hash independently rechecked.',
                              'No network access, new source writes, 2025/2026 label generation, model training, or predictive claims.']}
    report.update(mask_and_existing_overlap())
    assert all(r['all_match'] for r in sources.values())
    assert all(r['match'] for r in old_artifacts.values())
    assert archive_check['zip_size_matches_sidecar'] and archive_check['zip_sha256_matches_sidecar'] and archive_check['manifest_member_bytes_match_sidecar_manifest']
    assert all(r['quick_check'] == 'ok' for r in inventories)
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / 'checkpoint_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'source_hashes_match': len(sources), 'archive_zip_hash_matches': True,
                      'old_artifacts_match_archive': len(old_artifacts), 'derived_database_quick_checks': len(inventories),
                      'configuration_probe_results': probes, 'output': str(HERE / 'checkpoint_audit.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
