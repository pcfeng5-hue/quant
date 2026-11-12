from pathlib import Path
import csv
import hashlib
import json
import shutil
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'work/chip_full_capture_oct17'
AUDIT = ROOT / 'work/chip_capture_oct17_audit'
OUT = ROOT / 'outputs/高德红外数据库/历史筹码采集_20261017'
ARCH = Path('/Users/puchun/Documents/Codex/项目归档/ni/20261017_历史筹码采集')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    audit = json.loads((AUDIT / 'full_capture_final.json').read_text())
    assert audit['collection_target']['acquired_dates'] == 915
    assert not audit['missing_collection_target_dates']
    assert audit['main_database_unchanged']
    rows = json.loads((RAW / 'records.json').read_text())
    accepted = [r for r in rows if r['accepted']]
    first = {}
    for r in accepted:
        if r['date'] in first:
            assert r['values'] == first[r['date']]['values']
        first.setdefault(r['date'], r)
    assert len(first) == 915
    fields = ['trade_date', 'profit_ratio_pct', 'average_cost_display', 'cost90_low',
              'cost90_high', 'concentration90_pct', 'cost70_low', 'cost70_high',
              'concentration70_pct', 'open_qfq_display', 'high_qfq_display',
              'low_qfq_display', 'close_qfq_display', 'volume_display',
              'amount_display', 'turnover_display', 'observation_id',
              'observed_at_utc', 'historical_input_eligible', 'complete_price_bins']
    with (OUT / '每日筹码摘要_915日.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for day, r in sorted(first.items()):
            v, k = r['values'], r['kline']
            low90, high90 = v[3].split('-')
            low70, high70 = v[5].split('-')
            data = [day, v[1].rstrip('%'), v[2], low90, high90, v[4].rstrip('%'),
                    low70, high70, v[6].rstrip('%'), k['开盘'], k['最高'], k['最低'],
                    k['收盘'], k['成交量'], k['成交额'], k['换手率'], r['id'],
                    r['observed_at_utc'], False, False]
            w.writerow(dict(zip(fields, data)))
    prior = json.loads((ROOT / 'outputs/高德红外数据库/网页筹码核验_20261016/核验记录.json').read_text())['observations']
    contrasts = []
    names = ['profit_ratio_display', 'average_cost_display', 'cost90_display',
             'concentration90_display', 'cost70_display', 'concentration70_display']
    for p in prior:
        day = p['date']
        if day not in first:
            continue
        old = [p.get(n) for n in names]
        new = first[day]['values'][1:]
        contrasts.append({'date': day, 'prior_context': p.get('context'),
                          'prior_values': old, 'current_values': new,
                          'same_values': old == new,
                          'current_observation_id': first[day]['id'],
                          'cause_verified': False, 'historical_input_eligible': False})
    (OUT / '旧版与本次读数对照.json').write_text(json.dumps(contrasts, ensure_ascii=False, indent=2))
    copies = {
        'full_capture_final.sqlite': '筹码网页原始观察.sqlite',
        'full_capture_final.json': '独立验收结果.json',
        'full_capture_final_manifest.json': '原始证据SHA256清单.json',
        'full_capture_final_coverage.csv': '逐日覆盖核对.csv',
        'full_capture_final_ohlc_comparison.csv': '前复权OHLC逐值核对.csv',
    }
    for src, dest in copies.items():
        shutil.copy2(AUDIT / src, OUT / dest)
    for src in ['渠道核查结论.md', '来源结论.json']:
        shutil.copy2(ROOT / 'work/chip_fullbins_route_oct17' / src, OUT / src)
    summary = {
        'symbol': '002414.SZ', 'collection_date_client': '2026-10-17',
        'range': ['2023-01-03', '2026-10-16'], 'target_dates': 915,
        'summary_dates': 915, 'missing_summary_dates': [], 'attempts': 932,
        'accepted_observations': 923, 'rejected_observations_preserved': 9,
        'duplicate_control_observations': 8, 'duplicate_control_differences': 0,
        'main_database_date_baseline': 914, 'main_database_unchanged': True,
        'main_database_ohlc_compared_dates': 914, 'ohlc_mismatched_fields': 0,
        'complete_numerical_price_bin_days': 0, 'historical_input_eligible': False,
        'full_chip_dataset_complete': False,
        'completed_scope': 'Rendered daily summaries and dated screenshots only',
        'outstanding': ['完整逐价档数值', '筹码复权口径', '初始化与历史加载依赖', '历史时点可获得性'],
        'raw_source_root': str(RAW), 'archive_raw_prefix': 'current_capture/',
        'note': '前复权OHLC匹配不认证筹码算法；截图仅为当时可见价格轴下的页面绘图，不保证全部筹码价位可见。',
    }
    (OUT / '采集状态.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (OUT / '字段说明.md').write_text('''# 字段与读取说明

`每日筹码摘要_915日.csv` 是每个已接受日期的首个原始观察；本次8个重复控制读数与对应首个读数完全一致，因此未平均或挑选数值。全部932次尝试保存在SQLite和原件中。

- `profit_ratio_pct` 是网页“获利比例”，单位为百分数，例如4.81代表4.81%，不代表未来上涨概率。
- `average_cost_display`、`cost90_low/high`、`cost70_low/high` 保存网页显示价格；筹码的复权和估计口径尚未认证。
- `concentration90_pct`、`concentration70_pct` 是网页显示的集中度百分数，尚未获算法认证。
- `*_qfq_display` 是页面选择“前复权”时显示的日K开高低收，不等于筹码价格口径已认证。
- `volume_display`、`amount_display` 保留万/亿等原单位；未混合推断为股、手或元。
- `turnover_display` 原样保留百分号。
- `historical_input_eligible=false`：当前只作原始证据保存，未获准用于历史概率回测。
- `complete_price_bins=false`：尚未取得每价位的数值占比。
- SQLite 的 `observations` 保存全部尝试及验收状态，`evidence` 保存采集目录相对路径和SHA256，`expected_dates` 区分914日主库日期集合与1日网页新增日期。证据路径相对于解压后的 `current_capture/`。
- `ax.txt` 是沿用的证据文件名；前874条为native AX，后58条为Playwright DOM snapshot，并在记录中标注来源。两者均来自授权页面的可见界面。

不要把日历天数、观察次数、独立样本数或完整价档覆盖混为一谈。915是独立历史日期，不是915笔独立交易。
''')
    (OUT / '采集报告.md').write_text('''# 高德红外历史筹码采集报告

采集日期：2026年10月17日（多伦多）。来源为用户指定的[东方财富高德红外页面](https://quote.eastmoney.com/concept/sz002414.html#fschart-r)。

已采齐2023年1月3日至2026年10月16日的915个目标交易日网页筹码摘要，并逐日保存日K表、筹码摘要HTML、界面文字和当时的页面截图。**完成的是逐日摘要与页面绘图留存；每个价档的数值比例仍未取得，完整筹码数值数据库尚未完成。**

|项目|结果|
|---|---|
|目标日期/已采日期|915 / 915，日期缺口0|
|主库已有日期基准|914 / 914，覆盖100%|
|新增网页观察日|2026-10-16；尚无主库同日行情交叉核对|
|尝试/接受/拒绝|932 / 923 / 9；失败原件全部保留|
|换窗重复对照|8份；本次会话内摘要无差异|
|日K价格核对|914日，922份接受观察的3,688个开高低收显示值，与主库前复权值完全一致|
|原始采集文件|4,665个；已生成逐文件SHA256清单|
|完整逐价档数值|0日；独立列为缺口|
|历史模型准入|未批准；没有计算买卖概率或交易信号|

采集先通过日K图逐窗回看至2010年7月附近，再顺序返回2023年，尽量统一本会话加载过程。这个操作不能证明内部实际加载了所有交易日，也不证明初始化条件正确。每次只有预期日、实际日K日、筹码日一致且截图前后日期一致时才接受。页面偶发恢复最新筹码日期的9次失败尝试不计覆盖；重采均已通过。浏览器中断后的坐标重新标定，并保留恢复记录。

此前同一历史日在不同加载条件下存在数值差异，本次值也可能与旧版不同，详见 `旧版与本次读数对照.json`。旧版本未被替换。本次8份跨窗口对照一致，只能支持本次会话中的局部重复性，不能消除更换历史初始化、刷新、复权或算法版本造成的差异。

截图保留的是网页当时可见价格轴范围的绘图。有些日期的90%成本上界高于图轴上界，截图不能被解释为覆盖了所有价格档位。日K前复权选项也不能认证筹码使用相同口径。回看得到的历史估计，不证明当时交易者可获得同样数值。

## 文件与恢复

- `每日筹码摘要_915日.csv`：每日期一行的显示值导出。
- `筹码网页原始观察.sqlite`：932次观察、验收状态、证据索引和范围元数据。
- `独立验收结果.json`、`逐日覆盖核对.csv`、`前复权OHLC逐值核对.csv`：检查结果。
- `原始证据SHA256清单.json`：采集源目录中的每个文件及哈希。
- 证据包的 `current_capture/records/`：每次尝试的5份原件；`prior_evidence/`：旧版历史证据；`validation/`：独立验收脚本；`dataset/`：本目录资料。

主数据库和已有文件未被替换。此数据保存于独立观察库，下一步先解决口径与价档数据渠道，再讨论信号与概率。

## 数值价档的下一步

本轮未在东方财富/Choice公开文档中找到可证实的历史逐价档导出承诺。[Tushare官方cyq_chips文档](https://tushare.pro/document/2?doc_id=294)提供另一供应商的逐价档 `price / percent` 候选，文档列有权限门槛；本轮未登录、开通、购买或取得其实测样本。这一来源的估计不能当作东方财富原值，须另建来源、先检验样本和日期完整性。详见 `渠道核查结论.md`。
''')
    with sqlite3.connect((OUT / '筹码网页原始观察.sqlite').as_uri() + '?mode=ro', uri=True) as conn:
        assert conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT count(DISTINCT actual_date) FROM observations WHERE audit_accepted=1').fetchone()[0] == 915
    package = ARCH / '高德红外_历史筹码摘要与全部证据_20261017.zip'
    if package.exists():
        raise FileExistsError(package)
    roots = [
        ('current_capture', RAW), ('dataset', OUT),
        ('prior_evidence/round1', ROOT / 'outputs/高德红外数据库/网页筹码核验_20261016'),
        ('prior_evidence/round2', ROOT / 'work/chip_repeatability_round2_oct16/ui'),
        ('channel_research', ROOT / 'work/chip_fullbins_route_oct17'),
    ]
    pairs = [(prefix + '/' + p.relative_to(root).as_posix(), p)
             for prefix, root in roots for p in sorted(root.rglob('*')) if p.is_file()]
    pairs += [('validation/validate_capture.py', AUDIT / 'validate_capture.py'),
              ('validation/build_delivery.py', Path(__file__).resolve())]
    guide = AUDIT / '正式采集验收说明.md'
    if guide.exists():
        pairs.append(('validation/独立验收说明.md', guide))
    for name in ['screenshot_spotcheck.json', 'final_audit_artifact_hashes.json']:
        pairs.append(('validation/' + name, AUDIT / name))
    manifest = [{'archive_path': key, 'bytes': p.stat().st_size,
                 'sha256': sha(p.read_bytes())} for key, p in pairs]
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for key, p in pairs:
            z.write(p, key)
        z.writestr('PACKAGE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(manifest) + 1
        for r in manifest:
            data = z.read(r['archive_path'])
            assert len(data) == r['bytes'] and sha(data) == r['sha256']
    result = {'archive': str(package), 'sha256': sha(package.read_bytes()),
              'bytes': package.stat().st_size, 'source_files': len(manifest),
              'verified_every_file': True, 'summary_dates': 915,
              'complete_numerical_price_bin_days': 0}
    (ARCH / '归档校验结果.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
