"""Re-read saved responses with decimal arithmetic, add newer Tencent schema, audit scope."""
from __future__ import annotations
from collections import Counter, defaultdict
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
D=Decimal

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def h(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def number(value):return float(value) if isinstance(value,D) else value
def jsonp(path):
    text=path.read_text(encoding='utf-8')
    try:return json.loads(text)
    except json.JSONDecodeError:
        match=re.fullmatch(r'\s*[A-Za-z_$][\w$]*\s*=\s*(\{.*\})\s*;?\s*',text,re.S)
        assert match,'unexpected wrapper'
        return json.loads(match.group(1))

def write_csv(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def main():
    manifest=read(OUT/'manifest.json')
    supplement=read(OUT/'supplement_requests.json')
    checks=[]
    for item in manifest['results']+supplement:
        if item.get('raw_path'):
            p=Path(item['raw_path'])
            checks.append(dict(name=item['name'],raw_path=str(p),hash_match=h(p)==item['sha256'],size_match=p.stat().st_size==item['bytes']))
    assert all(c['hash_match'] and c['size_match'] for c in checks),'raw hash/size mismatch'
    oldrows=read(OUT/'market_rows.json')
    sources=defaultdict(dict)
    for row in oldrows:
        sources[(row['provider'],row['adjustment_flag'])][row['date']]=row

    newrows=[];framing=[];outside=[];newchecks=[]
    for item in supplement:
        match=re.fullmatch(r'tencent_new_([012])_(202[2-6])',item['name'])
        if not match:continue
        assert not item.get('error'),item
        flag,year=match.groups();key={'0':'day','1':'qfqday','2':'hfqday'}[flag]
        data=jsonp(Path(item['raw_path']))
        values=data['data']['sz002414'][key]
        before_count=len(newrows)
        year_start=year+'-01-01';year_end=min(year+'-12-31','2026-10-16')
        outside_count=0
        for pos,a in enumerate(values):
            day=a[0]
            if not year_start<=day<=year_end:
                outside_count+=1
                outside.append(dict(source_request=item['name'],source_row_index=pos,date=day,reason='provider_returned_outside_requested_annual_window; retained_in_raw_response'))
                continue
            o,c,hi,lo,v=map(D,a[1:6]);turn=D(a[7]);amount=D(a[8])*D('10000')
            assert 0<lo<=min(o,c)<=max(o,c)<=hi and v>=0 and amount>=0 and turn>=0
            old=sources[('tencent',flag)][day]
            row=dict(date=day,symbol='002414.SZ',provider='tencent',endpoint='newfqkline',
                     adjustment_flag=flag,adjustment=old['adjustment'],open=float(o),high=float(hi),low=float(lo),close=float(c),
                     volume_provider_native=float(v),volume_unit='hands_per_AKShare_SDK_mapping_not_vendor_certified',
                     volume_shares_sdk_normalized=float(v*100),
                     amount_provider_native=float(D(a[8])),amount_provider_unit='ten_thousand_CNY_per_AKShare_SDK_mapping',amount_cny=float(amount),
                     turnover_provider_native=float(turn),turnover_percent=float(turn),turnover_fraction=float(turn/100),
                     price_unit='CNY_per_share',source_request=item['name'],source_row_index=pos,source_sha256=item['sha256'],
                     retrieved_at_utc=item['retrieved_at_utc'],raw_row=a,
                     adjustment_vintage='retrieval_snapshot; not_point_in_time',historical_factor_eligible=False)
            newrows.append(row)
            newchecks.append(dict(source_request=item['name'],date=day,adjustment_flag=flag,
                                  old_endpoint_price_within_half_cent=all(abs(D(str(old[f]))-rowvalue)<=D('.005') for f,rowvalue in [('open',o),('close',c),('high',hi),('low',lo)]),
                                  old_endpoint_volume_exact=D(str(old['volume_provider_native']))==v))
        framing.append(dict(name=item['name'],requested_start=year_start,requested_end=year_end,
                            returned_rows=len(values),returned_start=values[0][0] if values else None,
                            returned_end=values[-1][0] if values else None,accepted_annual_window_rows=len(newrows)-before_count,
                            outside_annual_window_rows=outside_count,
                            note='Observed provider returns a 640-bar window ending at request end; start parameter not respected. Entire raw response preserved.'))
    dump(OUT/'tencent_new_market_rows.json',newrows)
    dump(OUT/'tencent_new_outside_annual_window_rows.json',outside)
    dump(OUT/'tencent_new_response_framing.json',framing)
    dump(OUT/'tencent_old_new_endpoint_comparison.json',newchecks)
    write_csv(OUT/'tencent_new_market_rows.csv',newrows,
              ['date','symbol','provider','endpoint','adjustment_flag','adjustment','open','high','low','close',
               'volume_provider_native','volume_shares_sdk_normalized','amount_provider_native','amount_cny',
               'turnover_percent','turnover_fraction','source_request','source_sha256','retrieved_at_utc','adjustment_vintage'])

    allrows=[dict(r,endpoint='kline' if r['provider']=='eastmoney' else 'fqkline') for r in oldrows]+newrows
    dump(OUT/'market_rows_all_endpoints.json',allrows)
    write_csv(OUT/'market_rows_all_endpoints.csv',allrows,
              ['date','symbol','provider','endpoint','adjustment_flag','adjustment','open','high','low','close',
               'volume_provider_native','amount_cny','turnover_percent','source_request','source_sha256','retrieved_at_utc','adjustment_vintage'])
    newmaps=defaultdict(dict)
    for row in newrows:
        assert row['date'] not in newmaps[row['adjustment_flag']]
        newmaps[row['adjustment_flag']][row['date']]=row

    comparisons=[];mismatches=[]
    for day,e in sorted(sources[('eastmoney','0')].items()):
        t=newmaps['0'][day]
        fields={}
        for field,tolerance in [('open',D('.005')),('high',D('.005')),('low',D('.005')),('close',D('.005')),
                                ('volume_provider_native',D('0')),('amount_cny',D('50.005')),('turnover_percent',D('0'))]:
            a,b=D(str(e[field])),D(str(t[field]));delta=abs(a-b)
            check=dict(eastmoney=float(a),tencent_new=float(b),absolute_difference=float(delta),tolerance=float(tolerance),pass_check=delta<=tolerance)
            if field=='volume_provider_native':
                check['within_half_hand_quantization']=delta<=D('.5')
            if field=='amount_cny':
                check['tolerance_basis']='Tencent native amount printed to .01 ten-thousand CNY (=100 CNY); half-width50 plus Eastmoney .01 CNY half-width .005. Boundary check only, not proof of common upstream precision.'
            fields[field]=check
            if not check['pass_check']:
                mismatches.append(dict(date=day,scope='warmup_2022' if day<'2023-01-01' else 'research_2023_onward',field=field,**check))
        comparisons.append(dict(date=day,fields=fields))
    dump(OUT/'tencent_new_cross_source_daily_comparison.json',comparisons)
    dump(OUT/'tencent_new_cross_source_strict_mismatches.json',mismatches)
    mismatch_summary=[]
    for scope in ('all','warmup_2022','research_2023_onward'):
        selected=[r for r in comparisons if scope=='all' or (scope=='warmup_2022')==(r['date']<'2023-01-01')]
        counters={}
        for field in ('open','high','low','close','volume_provider_native','amount_cny','turnover_percent'):
            fields=[r['fields'][field] for r in selected]
            counters[field]=dict(compared_dates=len(fields),strict_pass_dates=sum(r['pass_check'] for r in fields),
                                 strict_mismatch_dates=sum(not r['pass_check'] for r in fields),
                                 max_absolute_difference=max((r['absolute_difference'] for r in fields),default=None))
            if field=='volume_provider_native':counters[field]['within_half_hand_quantization_dates']=sum(r['within_half_hand_quantization'] for r in fields)
        mismatch_summary.append(dict(scope=scope,fields=counters))

    expected_path=ROOT/'outputs/高德红外数据库/历史筹码采集_20261017/每日筹码摘要_915日.csv'
    with expected_path.open(encoding='utf-8-sig',newline='') as f:
        chips=list(csv.DictReader(f))
    chip_dates={r['trade_date'] for r in chips}
    db=ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'
    conn=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    db_dates={r[0] for r in conn.execute("select distinct trade_date from daily_bars where source='em_daily_0'")}
    quick_check=conn.execute('pragma quick_check').fetchone()[0];conn.close()
    assert len(chip_dates)==915
    date_checks=[]
    for key,mapping in list(sources.items())+[(('tencent_new',flag),mapping) for flag,mapping in newmaps.items()]:
        warmup={d for d in mapping if d<'2023-01-01'};research={d for d in mapping if d>='2023-01-01'}
        date_checks.append(dict(provider_endpoint=key[0],adjustment_flag=key[1],total_dates=len(mapping),
                               warmup_dates=len(warmup),research_dates=len(research),missing_vs_chip_dates=sorted(chip_dates-research),
                               extra_vs_chip_dates=sorted(research-chip_dates),added_vs_existing_main_database=sorted(research-db_dates)))
    assert all(c['total_dates']==1157 and c['warmup_dates']==242 and c['research_dates']==915 and not c['missing_vs_chip_dates'] and not c['extra_vs_chip_dates'] for c in date_checks)

    # Re-read Eastmoney raw response, independent of normalized rows, and use decimal math.
    emitem=next(x for x in manifest['results'] if x['name']=='em_0_20220101_20261016')
    rawem=read(Path(emitem['raw_path']))['data']['klines']
    unit_rows=[]
    for item in rawem:
        a=item.split(',');low,high,vol,amount=D(a[4]),D(a[3]),D(a[5]),D(a[6])
        avg=amount/(vol*100) if vol else None
        unit_rows.append(dict(date=a[0],raw_low=float(low),raw_high=float(high),volume_raw=float(vol),amount_cny=float(amount),
                              implied_avg_if_hands=float(avg) if avg is not None else None,
                              strict_inside_range=avg is not None and low<=avg<=high,
                              half_cent_compatible=avg is not None and low-D('.005')<=avg<=high+D('.005')))
    dump(OUT/'unit_amount_range_diagnostics.json',unit_rows)
    unit_summary=dict(dates=len(unit_rows),strict_inside_dates=sum(r['strict_inside_range'] for r in unit_rows),
                      half_cent_compatible_dates=sum(r['half_cent_compatible'] for r in unit_rows),
                      exceptions=[r for r in unit_rows if not r['strict_inside_range']],
                      conclusion='Hands convention is supported by primary SDK mapping and implied average-price range checks; formal provider API unit/factor specification not obtained. Exceptions retained, cause unknown.')
    all_checks=dict(raw_files=checks,all_raw_hashes_and_sizes_match=all(c['hash_match'] and c['size_match'] for c in checks),
                    date_scope_checks=date_checks,new_endpoint_framing=framing,
                    older_newer_tencent_all_adjustments=dict(compared_source_dates=len(newchecks),
                        ohlc_within_half_cent=sum(c['old_endpoint_price_within_half_cent'] for c in newchecks),
                        volume_exact=sum(c['old_endpoint_volume_exact'] for c in newchecks)),
                    unit_diagnostic_summary=unit_summary,new_cross_source_field_summary=mismatch_summary,
                    main_database_quick_check=quick_check,
                    main_database_sha256=h(db),main_database_unchanged_vs_agent_start=h(db)==read(OUT/'main_database_before.json')['sha256'])
    dump(OUT/'verification.json',all_checks)

    # Keep the first collection summary as a historical intermediate, then publish the final stage summary.
    initial_path=OUT/'summary_initial_collection.json'
    if not initial_path.exists():dump(initial_path,read(OUT/'summary.json'))
    summary=read(initial_path)
    summary.update(finalized_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                   provider_count=2,endpoint_variants=3,accepted_source_rows_initial_endpoints=len(oldrows),
                   accepted_source_rows_new_endpoint=len(newrows),accepted_source_rows=len(allrows),
                   canonical_date_count=1157,warmup_date_count=242,research_date_count=915,
                   new_endpoint_raw_rows=sum(r['returned_rows'] for r in framing),
                   new_endpoint_raw_rows_outside_requested_annual_windows=len(outside),
                   new_endpoint_cross_source=mismatch_summary,
                   target_20261016=dict(open=10.70,high=10.94,low=10.60,close=10.78,
                                       volume_native_eastmoney=447709,amount_cny_eastmoney=481724556.97,
                                       amount_cny_tencent_new=481724600.0,turnover_percent_both=1.32),
                   verification_path=str(OUT/'verification.json'),
                   main_database_unchanged=all_checks['main_database_unchanged_vs_agent_start'],
                   adjusted_old_endpoint_comparison_status='All 3 adjustment modes: OHLC within half cent and native volume exact between Eastmoney and old Tencent across all 1157 dates; current snapshots only.',
                   amount_and_turnover_cross_source_status='New Tencent endpoint acquired and checked; strict exceptions retained, see field summary.',
                   provider_api_factor_documentation_obtained=False,
                   historical_factor_eligible=False,
                   sdk_unit_source='https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_hist_tx.py',
                   unit_diagnostics=unit_summary,
                   extra_gap_status=dict(formal_PIT_adjustment_factor_series='not_obtained',
                                         price_bin_chip_distribution='outside_this_subtask',
                                         tradability_status='handled_by_separate_subtask; bars do not prove executable orders'))
    summary['known_boundaries']=[x for x in summary['known_boundaries'] if not x.startswith('Tencent daily schema')]
    summary['known_boundaries']+=['Old Tencent fqkline schema has only price/volume; new Tencent newfqkline amount and turnover retained separately with SDK normalization provenance.',
                                   'SDK documentation is primary for its own mapping; it is not a formal vendor-certified API contract.',
                                   'New Tencent endpoint ignores start date and returns 640 bars ending at end date; out-of-window rows preserved in original raw responses.']
    dump(OUT/'summary.json',summary)
    all_raw_supplement=[x for x in supplement if x.get('raw_path')]
    report='''# 高德红外行情预热与末日核对（暂存完成）

- 固定范围：2022-01-01—2026-10-16。两供应商、三个端点，915个研究交易日（2023年起）及242个2022年预热交易日，各复权分别保存。
- 东方财富与腾讯旧端点各有不复权、前复权、后复权1,157日；新增腾讯端点同样各1,157日，共10,413条规范化源行。
- 原始响应、请求URL/参数、UTC读取时间、响应头、SHA-256、默认网络DNS失败记录均保存；没有登录、付费、下单或修改主数据库。

|核验项目|结果|
|---|---|
|末日|2026-10-16：开10.70、高10.94、低10.60、收10.78，成交量原数447,709手（SDK口径）|
|东方财富与腾讯旧端点|三复权各1,157日，OHLC在0.005元容差内全部一致，成交量原数全部相等|
|研究日期集合|9个供应商/端点/复权序列均覆盖915日，与网页筹码摘要的日期集合相同|
|与10月15日旧东方财富快照|三复权各914个重叠日，原始逐行0修订|
|新腾讯研究期成交量|915日原数全部相等|
|新腾讯2022预热成交量|58日原数有小数差异，全部在半手量化范围内；严格不相等标记保留|
|新腾讯换手率|研究915日全部相等；2022-05-30为0.73%，东方财富0.72%，保留差异|
|新腾讯成交额|按万元转元；研究915日有__RESEARCH_AMOUNT_DAYS__日、预热242日有__WARMUP_AMOUNT_DAYS__日超出50.005元的显示舍入边界，最大52元，原因未查明，不擅自放宽容差|

10月16日东方财富成交额481,724,556.97元；腾讯新端点481,724,600元，相差43.03元，落在腾讯金额精度对应的半幅范围内。换手率均为1.32%。

## 单位与响应边界

腾讯旧端点仅有日线日期、OHLC和成交量。新端点有11列，原始零基索引 a[5]（第6列）为成交量、a[7]（第8列）为换手率百分数、a[8]（第9列）为万元成交额，完整原数保留。AKShare官方源码将主板股票成交量乘100统一为股、成交额乘10,000统一为元、换手率除100统一为小数。该映射仅是SDK自身定义，不等同腾讯正式接口合同。

新端点实际每次返回以请求结束日期为终点的640根日线，不遵守起始日。15个原件的9,600根源行全部保留；规范化时按各年度请求窗口取3,471行，其余6,129行没有混入研究样本，留在原始响应并逐行列明。

价格为每股人民币，成交量保留供应商原数与SDK换算股数。东方财富成交额除以手数乘100得到的均价范围核验保留严格异常，不因半分范围兼容而删除异常。详见verification.json和unit_amount_range_diagnostics.json。

## 复权边界

三种复权价格都是本次读取的历史快照。前复权会随着后续权益事件改变历史价格，不能把这些快照当作2023年当时可获取的数据版本。尚未取得有正式供应商定义的独立复权因子或历史版本序列；不把前复权收盘与不复权收盘之比标记成“已验证因子”。不复权、前复权、后复权互不覆盖，量额字段也不因价格复权模式而擅自修改。

2022年只作为指标预热，不增加研究结果样本数；未计算任何MA/MACD/KDJ、买卖概率或收益标签。行情存在不证明当日订单可成交，交易状态须与另一路核验合并。

## 来源与主要文件

- [AKShare官方股票文档](https://akshare.akfamily.xyz/data/stock/stock.html)：单位、复权选项及历史前复权时变说明。
- [AKShare官方腾讯源码](https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_hist_tx.py)：新端点及单位转换的可核查实现，未执行该代码。
- [AKShare官方东方财富源码](https://raw.githubusercontent.com/akfamily/akshare/main/akshare/stock_feature/stock_hist_em.py)：fqt映射及列顺序，未执行该代码。
- [东方财富复权说明](https://baike.eastmoney.com/item/%E5%A4%8D%E6%9D%83)：教育性背景，不用于证明具体端点计算方法。
- market_rows_all_endpoints.json / .csv：10,413条规范化源行。
- manifest.json、approved_network_requests.json、supplement_requests.json：完整请求和证据索引。
- tencent_new_cross_source_strict_mismatches.json：严格不一致的逐字段原数。
- verification.json：原件哈希、日期集合、端点差异、单位核对与主库只读检查。
- summary.json：最终结构化摘要；summary_initial_collection.json为补充新端点之前的中间状态。
'''
    amount_counts={r['scope']:r['fields']['amount_cny']['strict_mismatch_dates'] for r in mismatch_summary}
    report=report.replace('__RESEARCH_AMOUNT_DAYS__',str(amount_counts['research_2023_onward'])).replace('__WARMUP_AMOUNT_DAYS__',str(amount_counts['warmup_2022']))
    (OUT/'行情预热与末日核对.md').write_text(report,encoding='utf-8')
    print(json.dumps(dict(total_canonical_source_rows=len(allrows),new_canonical_rows=len(newrows),
                          raw_hash_checks=len(checks),all_hashes_match=all_checks['all_raw_hashes_and_sizes_match'],
                          date_scope_checks=len(date_checks),new_endpoint_fields=mismatch_summary,
                          unit_summary=unit_summary,main_database_unchanged=summary['main_database_unchanged']),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
