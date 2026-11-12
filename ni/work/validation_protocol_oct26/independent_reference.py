"""Read-only independent arithmetic/date reference for the two-model development run."""
from pathlib import Path
import csv
import hashlib
import json
import math
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
SOURCE = ROOT / 'outputs/三线研究启动_20261025/量价基线'


def read_table(filename, query):
    con = sqlite3.connect((SOURCE / filename).as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    try:
        return [dict(r) for r in con.execute(query)]
    finally:
        con.close()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def main():
    contract_path = ROOT / 'work/forecast_validation_oct26/contract.json'
    contract = json.loads(contract_path.read_text())
    assert contract['shrinkage_lambda'] == 20
    assert contract['minimum_training_rows'] == 100
    labels = read_table('开发期结果隔离.sqlite',
        'SELECT * FROM development_price_outcomes ORDER BY signal_date')
    assert len(labels) == 469
    assert all('2023-01-03' <= r['signal_date'] < r['outcome_observation_date'] <= '2024-12-31' for r in labels)
    signals = read_table('日线特征与信号.sqlite',
        "SELECT * FROM signals WHERE trade_date >= '2023-01-03' AND trade_date <= '2024-12-31' ORDER BY trade_date")
    signal_map = {r['trade_date']: r for r in signals}
    assert len(signal_map) == 484
    grid = set([r['trade_date'] for r in signals][::5])
    eligible = []
    for r in labels:
        s = signal_map[r['signal_date']]
        up = s['MA5_gt_MA10_gt_MA15_and_MA15_rising']
        down = s['MA5_lt_MA10_lt_MA15_and_MA15_falling']
        assert not (up == 1 and down == 1)
        if up is None or down is None:
            continue
        r = dict(r)
        r['group'] = 'up' if up == 1 else 'down' if down == 1 else 'other'
        r['y'] = int(r['outcome_sign'] == 'price_change_gt_0')
        eligible.append(r)
    summaries = []
    predictions = []
    for f in contract['folds']:
        start, end = f['validation_start'], f['validation_end']
        train = [r for r in eligible if r['signal_date'] < start and r['outcome_observation_date'] < start]
        valid = [r for r in eligible if start <= r['signal_date'] <= end and r['outcome_observation_date'] <= end]
        n, k = len(train), sum(r['y'] for r in train)
        assert n >= 100
        p0 = (k + 1) / (n + 2)
        group_values = {}
        for g in ['up', 'down', 'other']:
            chosen = [r for r in train if r['group'] == g]
            ng, kg = len(chosen), sum(r['y'] for r in chosen)
            group_values[g] = {'n': ng, 'positive': kg, 'p': (kg + 20 * p0) / (ng + 20)}
        for r in valid:
            p1 = group_values[r['group']]['p']
            predictions.append({'fold': f['id'], 'signal_date': r['signal_date'],
                'outcome_end': r['outcome_observation_date'], 'group': r['group'],
                'y': r['y'], 'zero': int(r['outcome_sign'] == 'price_change_eq_0'),
                'p0': p0, 'p1': p1, 'fixed_grid': int(r['signal_date'] in grid)})
        summaries.append({'fold': f['id'], 'train_n': n, 'train_positive': k,
            'train_last_anchor': max(r['signal_date'] for r in train),
            'train_last_label_end': max(r['outcome_observation_date'] for r in train),
            'validation_n': len(valid), 'validation_first_scored_anchor': valid[0]['signal_date'],
            'validation_last_scored_anchor': valid[-1]['signal_date'],
            'p0': p0, 'groups': group_values})
    assert len(predictions) == len({r['signal_date'] for r in predictions}) == 308
    metrics = []
    for scope in ['all', 'fixed_every_fifth_anchor']:
        chosen = predictions if scope == 'all' else [r for r in predictions if r['fixed_grid']]
        for model in ['p0', 'p1']:
            brier = sum((r[model] - r['y']) ** 2 for r in chosen) / len(chosen)
            clipped = [min(1 - 1e-12, max(1e-12, r[model])) for r in chosen]
            logloss = -sum(r['y'] * math.log(p) + (1-r['y']) * math.log1p(-p) for r, p in zip(chosen, clipped)) / len(chosen)
            metrics.append({'scope': scope, 'model': model, 'n': len(chosen), 'brier': brier, 'log_loss': logloss})
    with (WORK / 'independent_expected_predictions.csv').open('w', encoding='utf-8', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(predictions[0]))
        w.writeheader()
        w.writerows(predictions)
    report = {'status': 'independent_arithmetic_reference_not_an_effectiveness_claim',
        'contract_sha256': digest(contract_path),
        'source_hashes': {str(p.relative_to(ROOT)): digest(p) for p in [SOURCE/'日线特征与信号.sqlite', SOURCE/'开发期结果隔离.sqlite']},
        'read_label_period': ['2023-01-03', '2024-12-31'], 'folds': summaries,
        'metrics': metrics, 'unique_scored_anchors': 308, 'read_2025_2026_outcomes': False}
    (WORK / 'independent_reference_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'fold_counts': [[r['train_n'], r['validation_n']] for r in summaries], 'metrics': metrics}, indent=2))


if __name__ == '__main__':
    main()
