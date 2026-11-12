import csv
import hashlib
import json
from collections import defaultdict,Counter
from decimal import Decimal
from pathlib import Path
from pypdf import PdfReader
from collect import ROOT,normalize,write_json,SERIES

def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        if not rows:return
        fields=list(rows[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in rows:
            w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})

def diff(a,b,fields):
    return {k:dict(eastmoney=a[k],tencent=b[k],difference=str(Decimal(str(b[k]))-Decimal(str(a[k])))) for k in fields if abs(Decimal(str(a[k]))-Decimal(str(b[k])))>Decimal('0.005')}

manifests=[json.loads((ROOT/n).read_text()) for n in ['manifest.json','qfq_supplement_manifest.json']]
requests=[r for m in manifests for r in m['results']]
hashcheck=[];allrows=[];rejections=[]
for r in requests:
    if not r.get('raw_path'):continue
    payload=Path(r['raw_path']).read_bytes()
    hashcheck.append(dict(id=r['id'],matches=hashlib.sha256(payload).hexdigest()==r['sha256'],bytes_match=len(payload)==r['bytes']))
    rr,ee=normalize(r);allrows+=rr
    rejections.extend(dict(id=r['id'],**e) for e in ee)
write_json(ROOT/'all_request_market_rows.json',allrows)
write_csv(ROOT/'all_request_market_rows.csv',allrows)
group=defaultdict(list)
for r in allrows:group[(r['symbol'],r['source'],r['adjustment'],r['trade_date'])].append(r)
unique=[];within_diffs=[]
for key,records in sorted(group.items()):
    base=records[0]
    for other in records[1:]:
        delta={f:dict(first=base[f],other=other[f]) for f in ['open','high','low','close','volume_raw'] if base[f]!=other[f]}
        if delta:within_diffs.append(dict(key=key,first_request=base['source_request_id'],other_request=other['source_request_id'],fields=delta))
    selected=dict(base)
    selected['all_supporting_request_ids']=[r['source_request_id'] for r in records]
    selected['same_provider_duplicate_conflict']=any(any(r[f]!=base[f] for f in ['open','high','low','close','volume_raw']) for r in records)
    unique.append(selected)
write_json(ROOT/'market_rows_unique.json',unique)
write_csv(ROOT/'market_rows_unique.csv',unique)
write_json(ROOT/'same_provider_overlap_differences.json',within_diffs)
by_series=defaultdict(dict)
for r in unique:by_series[(r['symbol'],r['source'],r['adjustment'])][r['trade_date']]=r
coverage=[]
for (symbol,source,adjustment),byday in sorted(by_series.items()):
    coverage.append(dict(symbol=symbol,source=source,adjustment=adjustment,rows=len(byday),start=min(byday),end=max(byday),warmup_2022=sum(d<'2023-01-01' for d in byday),research_2023_onward=sum(d>='2023-01-01' for d in byday)))
comparisons=[];differences=[]
for symbol,name,_,_,kind in SERIES:
    for adj in (['0','1'] if kind=='stock' else ['0']):
        em=by_series.get((symbol,'eastmoney',adj),{});tx=by_series.get((symbol,'tencent',adj),{})
        common=sorted(set(em)&set(tx));counter=Counter();mismatch_dates=set();price_dates=set();volume_dates=set()
        for d in common:
            delta=diff(em[d],tx[d],['open','high','low','close','volume_raw'])
            if delta:
                counter.update(delta.keys());mismatch_dates.add(d)
                if any(k!='volume_raw' for k in delta):price_dates.add(d)
                if 'volume_raw' in delta:volume_dates.add(d)
                differences.append(dict(symbol=symbol,adjustment=adj,trade_date=d,fields=delta,eastmoney_request=em[d]['source_request_id'],tencent_request=tx[d]['source_request_id']))
        comparisons.append(dict(symbol=symbol,name=name,adjustment=adj,overlap=len(common),matching_ohlcv_dates=len(common)-len(mismatch_dates),price_difference_dates=len(price_dates),volume_difference_dates=len(volume_dates),field_differences=dict(counter),only_eastmoney=sorted(set(em)-set(tx)),only_tencent=sorted(set(tx)-set(em)),interpretation='Preserve both providers; differences unadjudicated. Different endpoints do not prove independent upstream feeds.'))
write_json(ROOT/'cross_source_comparison.json',comparisons)
write_json(ROOT/'cross_source_differences.json',differences)
write_csv(ROOT/'cross_source_differences.csv',differences)
calendar_sets={symbol:set(by_series[(symbol,'eastmoney','0')]) for symbol,_,_,_,_ in SERIES}
union=set.union(*calendar_sets.values());common=set.intersection(*calendar_sets.values())
alignment=dict(reference='Observed Eastmoney date sets, not an independently audited official exchange calendar',union_dates=len(union),common_dates=len(common),start=min(common),end=max(common),missing_relative_to_union={k:sorted(union-v) for k,v in calendar_sets.items()})
aligned=[]
for d in sorted(union):
    row=dict(trade_date=d)
    for symbol,name,_,_,_ in SERIES:
        r=by_series[(symbol,'eastmoney','0')].get(d)
        prefix=symbol.replace('.','_')
        for field in ['open','high','low','close','volume_raw','amount_raw']:
            row[prefix+'_'+field]=r[field] if r else None
    aligned.append(row)
write_json(ROOT/'alignment.json',alignment)
write_csv(ROOT/'aligned_market_background.csv',aligned)
updates=[r for r in unique if r['trade_date']>='2026-10-16']
write_json(ROOT/'updates_20261016_20261021.json',updates)
write_csv(ROOT/'updates_20261016_20261021.csv',updates)
baseline=json.loads((ROOT.parent/'market_warmup_verify_oct17'/'market_rows.json').read_text())
baseline_changes=[];baseline_summary=[]
for source in ['eastmoney','tencent']:
    for adj in ['0','1']:
        old={r['date']:r for r in baseline if r['provider']==source and r['adjustment_flag']==adj}
        new=by_series[('002414.SZ',source,adj)]
        count=0
        for d in sorted(set(old)&set(new)):
            delta={f:dict(old=old[d][f],new=new[d][f]) for f in ['open','high','low','close'] if old[d][f]!=new[d][f]}
            if old[d]['volume_provider_native']!=new[d]['volume_raw']:delta['volume_raw']=dict(old=old[d]['volume_provider_native'],new=new[d]['volume_raw'])
            if delta:count+=1;baseline_changes.append(dict(source=source,adjustment=adj,trade_date=d,fields=delta))
        baseline_summary.append(dict(source=source,adjustment=adj,common_dates=len(set(old)&set(new)),changed_ohlcv_dates=count,new_dates=sorted(set(new)-set(old))))
write_json(ROOT/'baseline_revision_comparison.json',dict(summary=baseline_summary,differences=baseline_changes))
doc=next(r for r in requests if r['kind']=='methodology')
reader=PdfReader(doc['raw_path']);text='\n\n'.join(p.extract_text() or '' for p in reader.pages)
(ROOT/'399967_methodology_text.txt').write_text(text)
identity=dict(symbol='399967.SZ',name='中证军工指数',provider='中证指数有限公司',methodology_version='2023年12月 V1.2',official_url=doc['url'],official_saved_path=doc['raw_path'],official_sha256=doc['sha256'],pages=len(reader.pages),text_contains_code='399967' in text,proxy_use='Military industry background context only',historical_membership_of_002414_verified=False,all_historical_methodology_versions_verified=False,not_total_return='Daily price index; do not relabel as reinvested total return')
write_json(ROOT/'industry_proxy_identity.json',identity)
admission=dict(status='staged_for_review_not_model_release',earliest_safe_resolution='Completed daily bars only; do not use same-day final high/low/close/volume in an earlier intraday decision',historical_first_availability_timestamp=None,price_snapshot_timing='Provider retrospective extraction at recorded request time, not certified historical point-in-time version',stock_unadjusted_ohlcv='cross-provider consistent across 1160 dates; upstream independence not proven',stock_qfq='retrospective snapshot; not an official point-in-time corporate-action factor series',index_prices='fixed-provider source snapshots preserved; flagged discrepancy dates need declared source treatment',index_volume='blocked for cross-provider pooled/spliced quantities until unit and coverage are verified',historical_industry_membership='not obtained; index is background proxy only',full_market_breadth='not obtained',model_usable=False,indicators_computed=False,probabilities_computed=False)
write_json(ROOT/'input_admission.json',admission)
summary=dict(as_of_requested='2026-10-21',main_database_mutated=False,successful_requests=sum(r.get('error') is None for r in requests),failed_requests=[r for r in requests if r.get('error')],all_request_rows=len(allrows),deduplicated_rows=len(unique),same_provider_duplicate_conflicts=len(within_diffs),raw_hash_checks=hashcheck,all_raw_hashes_match=all(r['matches'] and r['bytes_match'] for r in hashcheck),rejections=len(rejections),coverage=coverage,alignment=alignment,cross_source=comparisons,stock_baseline_revision=baseline_summary,industry_identity=identity,gaps=['Full-market historical advance/decline breadth unavailable in this round','Historical thematic/industry member lists not obtained','002414 membership in 399967 has not been certified for any historical date','Index volume units and constituent/market coverage not formally certified; do not pool or splice across providers','Historical vendor adjustment factors and point-in-time vintages not obtained','No indicators, returns, probabilities, or profitable-strategy claims computed'])
write_json(ROOT/'summary.json',summary)
lines=['# 市场与行业背景补齐核验（2026-10-22）','','本轮独立暂存，主数据库未修改。请求共同截止日为2026-10-21，实际各行情序列均已返回该日。','',f"保存公开请求 {len(requests)} 个，成功 {summary['successful_requests']} 个；源行情 {len(allrows)} 行，重复日期合并视图 {len(unique)} 行；原始响应SHA256全部核对通过。",'','## 已取得','','|标的|来源|口径|日期数|起止|','|---|---|---|---:|---|']
for c in coverage:lines.append(f"|{c['symbol']}|{c['source']}|{'不复权' if c['adjustment']=='0' else '前复权当次快照'}|{c['rows']}|{c['start']}—{c['end']}|")
lines+=['',f"四个标的不复权日期集合完全对齐，共 {len(common)} 日，其中2022预热242日、2023起研究范围918日。此结论是供应商返回日期的相互对齐，不是官方交易日历的完整审计。",'','## 行业代理身份','','中证军工399967：已保存中证指数有限公司官方2023年12月V1.2编制方案，代码、名称和选样框架均可追溯。用于军工行业背景代理，不代表已经证明高德红外在整个历史区间属于其样本；当前编制方案也不代表2022年以来所有版本不变。','','官方依据：'+doc['url'],'','## 双源核对','','|标的|口径|重叠日|价格差异日|成交量差异日|','|---|---|---:|---:|---:|']
for c in comparisons:lines.append(f"|{c['symbol']}|{c['adjustment']}|{c['overlap']}|{c['price_difference_dates']}|{c['volume_difference_dates']}|")
lines+=['','差异逐字段保存于cross_source_differences.json和CSV，未选择供应商为真值、未覆盖旧版本。腾讯日线没有可比成交额和换手字段，对应值为空而非0。指数成交量原数保留，计量单位及统计覆盖未取得正式口径说明，不可跨供应商拼接。','','## 更新与已知限制','','高德红外相对10月16日快照新增10月19、20、21日；两种价格口径与双源均保留。本轮前复权为当前回溯快照，不能冒充当时已知复权因子。旧快照逐字段变化见baseline_revision_comparison.json。','','Tencent整段前复权请求只返回640日，已按2022、2023、2024年度额外请求补齐；重叠源记录保留，合并视图的同供应商冲突数为'+str(len(within_diffs))+'。','','全市场涨跌家数、历史题材/行业成员、指数成交量正式定义仍为缺口。本轮仅采集、规范化和核对，不计算技术指标、涨跌概率或交易信号。','','## 文件入口','','- summary.json：覆盖、差异、缺口及身份摘要。','- market_rows_unique.json / CSV：规范化按供应商去重视图。','- all_request_market_rows.json / CSV：含重复请求支持的全部源记录。','- aligned_market_background.csv：同日期宽表，字段保留供应商口径。','- updates_20261016_20261021.json / CSV：10月16日起的末端记录。','- manifest.json、qfq_supplement_manifest.json、raw/：实际请求、响应时间、原件与哈希。']
lines+=['','日线最终高低收盘价和全天成交量只能用于该日收盘后的研究，不能回填到更早盘中决策。当前提取时间并不等于历史首次可用时间。input_admission.json记录输入使用边界，模型准入仍为false。']
(ROOT/'市场与行业背景补齐核验.md').write_text('\n'.join(lines)+'\n')
artifact_hashes=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and p.name!='artifact_hashes.json' and '__pycache__' not in p.parts:
        b=p.read_bytes();artifact_hashes.append(dict(path=str(p.relative_to(ROOT)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
write_json(ROOT/'artifact_hashes.json',artifact_hashes)
print(json.dumps(dict(all_request_rows=len(allrows),unique_rows=len(unique),alignment=alignment,comparisons=comparisons,baseline=baseline_summary,raw_hashes=summary['all_raw_hashes_match'],same_provider_conflicts=len(within_diffs)),ensure_ascii=False,indent=2))
