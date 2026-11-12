from pathlib import Path
import csv, hashlib, html, json, re, shutil

ROOT=Path('/Users/puchun/Documents/Codex/2026-10-07/ni')
SRC=ROOT/'work/chip_history_root_oct16'
DEST=ROOT/'outputs/高德红外数据库/网页筹码核验_20261016'
DEST.mkdir(parents=True,exist_ok=True)
CASES=[('B_20230620','first_session_earlier_history'),('A2_20230620','first_session_returned_window'),('20230103','research_start_sample'),('reload_20230620','fresh_reload_history')]
NAMES=['date','profit_ratio_display','average_cost_display','cost90_display','concentration90_display','cost70_display','concentration70_display']
rows=[]; manifest=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for stem,context in CASES:
    source=SRC/f'{stem}_table.html'
    values=[html.unescape(x).strip() for x in re.findall(r'<td class="qcyq_t_v">([^<]*)</td>',source.read_text())]
    if len(values)!=7:raise ValueError((stem,values))
    ax=(SRC/f'{stem}_ax.txt').read_text()
    ts=re.findall(r'^\s*\d+ text (.*)$',ax,re.M)
    ti=ts.index('时间'); tooltip_date=ts[ti+1]
    if values[0]!=tooltip_date:raise ValueError((stem,values[0],tooltip_date))
    prices={k:ts[ts.index(k,ti)+1] for k in ['开盘','收盘','最高','最低']}
    row=dict(zip(NAMES,values))
    row.update(symbol='002414.SZ',context=context,evidence_stem=stem,
               kline_date=tooltip_date,kline_basis_control='前复权' if 'text 前复权' in ax else 'unknown',
               kline_price_display=prices,chip_price_basis_verified=False,
               historical_input_eligible=False,full_price_bin_data_acquired=False)
    rows.append(row)
    for suffix in ['_table.html','_ax.txt','.jpg']:
        src=SRC/f'{stem}{suffix}'
        dst=DEST/src.name
        shutil.copy2(src,dst)
        manifest.append({'file':dst.name,'sha256':sha(dst),'bytes':dst.stat().st_size})
same_day=[r for r in rows if r['date']=='2023-06-20']
comparison_fields=NAMES[1:]
differences={f:sorted({r[f] for r in same_day}) for f in comparison_fields if len({r[f] for r in same_day})>1}
record={
 'review_date_client':'2026-10-16','timezone_client':'America/Toronto',
 'source_url':'https://quote.eastmoney.com/concept/sz002414.html#fschart-r',
 'method':'CUA可见日K交互及已渲染DOM；保存日期同步的摘要HTML、AX与截图；无隐藏页面状态或后台数据读取',
 'observations':rows,'snapshot_count':len(rows),'unique_observed_dates':sorted({r['date'] for r in rows}),
 'same_date_different_summary_fields':differences,
 'same_date_kline_ohlc_identical':len({json.dumps(r['kline_price_display'],sort_keys=True) for r in same_day})==1,
 'earliest_requested_trading_date_display_verified':True,
 'all_requested_dates_display_verified':False,'complete_daily_price_bins_obtained':0,
 'historical_first_availability_verified':False,'algorithm_and_initialization_verified':False,
 'difference_cause':'尚未确定。差异发生在历史平移/较早数据载入和重新加载等交互之后；不能据此认定唯一原因或哪版正确。',
 'public_export_control':'已检查日K工具栏及筹码面板，未找到公开导出完整价档的控件；不据此断言整个网站没有其他功能。',
 'date_synchronization':'操作/停留后曾见K线日期与筹码默认日期不一致。正式样本只接受两者日期同步的截图与HTML。',
 'excluded_diagnostics':['unsynchronized_after_idle_table.html（读到默认最新日期，非2023样本）','root_observations.json中的辅助尝试及误命名note（以实际values日期为准，不作为本批正式快照）'],
 'main_database_modified':False,'historical_input_eligible':False,
 'evidence_files':manifest
}
(DEST/'核验记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
fields=['symbol','date','context',*NAMES[1:],'kline_basis_control','historical_input_eligible','full_price_bin_data_acquired','evidence_stem']
with (DEST/'筹码摘要观察.csv').open('w',encoding='utf-8-sig',newline='') as fp:
    writer=csv.DictWriter(fp,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
print(json.dumps({'snapshots':len(rows),'unique_dates':record['unique_observed_dates'],'same_date_different_fields':differences,'same_kline_ohlc':record['same_date_kline_ohlc_identical'],'full_bins':0,'historical_input_eligible':False},ensure_ascii=False,indent=2))
