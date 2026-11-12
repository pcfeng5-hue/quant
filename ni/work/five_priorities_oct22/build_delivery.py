from pathlib import Path
import hashlib, json, shutil, sqlite3, zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/五项数据补缺_20261022'
ARCH=Path('/Users/puchun/Documents/Codex/项目归档/ni/20261022_五项数据补缺')

def read(rel): return json.loads((ROOT/rel).read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

OUT.mkdir(parents=True,exist_ok=True); ARCH.mkdir(parents=True,exist_ok=True)
main_db=ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'
before=digest(main_db)
chips=read('work/chip_audit_oct22/records.json')
assert len(chips)==6 and all(r['accepted'] for r in chips)
byid={r['id']:r for r in chips}
assert byid['new_session_oct16_default']['values']==byid['new_session_oct16_return']['values']
assert byid['expanded_oct16']['values']==byid['expanded_oct16_return']['values']
assert byid['expanded_oct16']['values']!=byid['new_session_oct16_default']['values']
assert byid['expanded_oct16']['kline']==byid['new_session_oct16_default']['kline']
prior=read('work/chip_refine_first3_oct17/records.json')[0]
assert prior['values']==byid['new_session_oct16_default']['values']
chip_summary={'accepted_observations':6,'unique_dates':2,'default_context_cross_session_equal':True,
 'adjacent_returns_equal_in_each_context':True,'different_loading_context_values_differ':True,
 'same_OHLCV_amount_turnover':True,'cause_verified':False,'complete_price_bin_days':0,
 'historical_input_eligible':False,'default_values':byid['new_session_oct16_default']['values'],
 'expanded_values':byid['expanded_oct16']['values']}
(OUT/'筹码重复性核对.json').write_text(json.dumps(chip_summary,ensure_ascii=False,indent=2))
summaries={'chip':chip_summary,'market':read('work/market_warmup_finalize_oct22/summary.json'),
 'corporate':read('work/corporate_actions_refine_oct17/summary.json'),
 'conditions':read('work/conditions_finish_oct22/summary.json'),
 'industry':read('work/market_industry_oct22/summary.json'),
 'events':read('work/events_publication_oct22/summary.json')}
(OUT/'五项进度.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2))
copies=[('work/market_warmup_finalize_oct22/行情预热与末日核对.md','行情预热核对.md'),
 ('work/corporate_actions_refine_oct17/核对报告.md','公司行动核对.md'),
 ('work/conditions_finish_oct22/历史交易条件补核报告.md','历史交易条件核对.md'),
 ('work/market_industry_oct22/市场与行业背景补齐核验.md','市场行业核对.md'),
 ('work/events_publication_oct22/补缺报告.md','公告政策事件核对.md')]
for src,dst in copies: shutil.copy2(ROOT/src,OUT/dst)
datasets={
 'chip_original_attempts':'work/chip_full_capture_oct17/records.json',
 'chip_repeatability_oct22':'work/chip_audit_oct22/records.json',
 'market_warmup_snapshots':'work/market_warmup_finalize_oct22/market_rows_all_endpoints.json',
 'market_industry_snapshots':'work/market_industry_oct22/market_rows_unique.json',
 'corporate_actions':'work/corporate_actions_refine_oct17/corporate_actions.json',
 'non_distribution_decisions':'work/corporate_actions_refine_oct17/non_distribution_decisions.json',
 'historical_trade_conditions':'work/conditions_finish_oct22/daily_trade_conditions_915.json',
 'trade_rule_regimes':'work/conditions_finish_oct22/rule_regimes.json',
 'historical_fees':'work/conditions_finish_oct22/fee_schedule.json',
 'announcement_time_ledger':'work/events_publication_oct22/announcement_time_ledger_current.json',
 'events':'work/events_publication_oct22/normalized_events.json'}
db=OUT/'五项补缺原始观察.sqlite'
if db.exists(): raise FileExistsError(db)
con=sqlite3.connect(db)
con.executescript('''CREATE TABLE datasets(name TEXT PRIMARY KEY,source_path TEXT,source_sha256 TEXT,rows INTEGER);
CREATE TABLE records(dataset TEXT,seq INTEGER,observed_date TEXT,payload_json TEXT,PRIMARY KEY(dataset,seq));
CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT);
CREATE TABLE input_gates(feature_group TEXT PRIMARY KEY,status TEXT,reason TEXT,historical_input_eligible INTEGER CHECK(historical_input_eligible=0));''')
counts={}
for name,rel in datasets.items():
 d=read(rel); rows=d if isinstance(d,list) else [d]
 con.execute('INSERT INTO datasets VALUES(?,?,?,?)',(name,rel,digest(ROOT/rel),len(rows)))
 for i,r in enumerate(rows):
  day=(r.get('trade_date') or r.get('date') or r.get('event_date')) if isinstance(r,dict) else None
  con.execute('INSERT INTO records VALUES(?,?,?,?)',(name,i,day,json.dumps(r,ensure_ascii=False)))
 counts[name]=len(rows)
for k,v in summaries.items(): con.execute('INSERT INTO metadata VALUES(?,?)',(k,json.dumps(v,ensure_ascii=False)))
gates=[('chip','blocked','完整数值价档0日；加载条件差异原因与历史可得未认证'),
 ('market_and_corporate_actions','partial','行情已扩展；正式PIT因子及逐日流通股本仍缺'),
 ('trade_conditions','partial','月度证据不能代替逐日状态；账户佣金、官方日限价未知'),
 ('market_industry','partial','指数差异保留；背景代理不认证历史成员，宽度仍缺'),
 ('events','partial','312公告目录已刷新；历史首次精确公开时间未认证')]
con.executemany('INSERT INTO input_gates VALUES(?,?,?,0)',gates)
con.commit(); assert con.execute('PRAGMA quick_check').fetchone()[0]=='ok';con.close()
assert digest(main_db)==before
report='''# 五项数据补缺阶段报告

收尾日期：2026年10月22日，多伦多。五项均已实际推进、保存并核对；仍处数据阶段，没有计算指标、买卖概率或交易结果。新资料保存在独立观察库，原主库未改。

|工作|本轮取得和核对|仍未完成|
|---|---|---|
|1 筹码|新增6套日期同步证据，2个历史日；默认条件跨会话读数一致，相邻返回一致；扩展加载范围后同日6个筹码字段不同而K线相同|完整数值价档0日；算法、初始化、筹码复权、历史时点未认证，暂不进入概率输入|
|2 行情及公司行动|242个2022预热日；行情延伸到10月21日，2023起918日；本股不复权/前复权双源OHLCV一致。3个分派条款、2个最终不分配决议、8期末股本及7段总股本桥接已整理|现时复权快照不是PIT因子；3个股份性质衔接和160.22元派息总额口径差异仍待核|
|3 历史交易条件|915行状态表；45份停牌月报和45份证券统计；规则及费用按有效期分段，并纠正两处来源版本标签|未把月度无命中当逐日正常；逐日状态、官方日限价、账户佣金仍缺；执行准入全false|
|4 市场行业背景|上证、深成、中证军工与本股共同1160日（含242预热日），截至10月21日；官方军工指数编制说明已存，差异逐项保留|指数价格/量来源差异未裁定；历史成分和市场宽度未取得|
|5 公告政策事件|16页目录全量刷新，仍312公告、无新增返回；312条时间台账；新增3篇官方政策原文；10月16日交割获中金所原文核验；共67条标准事件|首次精确公开时间仍未知；46个月交割中5个月官方核验、41个月公式候选；政策样本不是新闻全集|

筹码同一2026-10-16历史日：默认加载时获利比例2.13%、平均成本13.14；扩展窗口后1.73%、13.08。各自返回读数可复现，但不能推断原因已查明，也不任选一个值覆盖旧版。获利比例不是未来上涨概率。

行情补充端点的成交量、金额、换手率误差保留。1157日金额比较有8日超显示舍入边界（2022年6日、研究期2日），最大52元；未因此放宽原阈值。新行情共同截止10月21日，筹码915日全量摘要仍截止10月16日，交易条件915日表也截止10月16日，不能宣称所有数据都已到10月21日。

## 文件

- `五项补缺原始观察.sqlite`：以数据集和版本分开保存原始观察，JSON载荷保留全部字段；不合并重复供应商快照为独立样本。
- `五项进度.json`、`筹码重复性核对.json`：结构化状态和边界。
- 本目录5份专项报告；其相对文件名应结合证据包中的原工作目录读取。
- 证据包按原项目相对路径保存原件、响应、截图、请求、脚本、SHA256及以上新库。解压后 `project/` 对应原项目根目录。旧报告与旧归档保留，不替换。

当前仍有数据准入缺口，不宣称五项全部验收完成，也没有购买数据、登录付费账户或进行交易。
'''
(OUT/'阶段报告.md').write_text(report)
progress=ROOT/'outputs/项目进度与交易需求档案.md'
with progress.open('a') as f:f.write('\n\n## 2026-10-22 五项补缺收尾\n\n已推进五项并保存独立观察库，详见[阶段报告](./五项数据补缺_20261022/阶段报告.md)。行情和行业共同截至10月21日，筹码全量摘要及交易条件表截至10月16日；口径、逐日状态、PIT等缺口保留，主库未改，无概率模型结论。\n')
roots=['work/chip_audit_oct22','work/chip_refine_first3_oct17','work/market_warmup_verify_oct17',
 'work/market_warmup_finalize_oct22','work/corporate_actions_refine_oct17','work/historical_trade_conditions_oct17',
 'work/conditions_finish_oct22','work/market_industry_oct22','work/events_publication_oct22',
 'work/five_priorities_oct22','outputs/五项数据补缺_20261022']
pairs=[('project/'+p.relative_to(ROOT).as_posix(),p) for rel in roots for p in sorted((ROOT/rel).rglob('*')) if p.is_file()]
pairs.append(('project/outputs/项目进度与交易需求档案.md',progress))
manifest=[{'path':name,'bytes':p.stat().st_size,'sha256':digest(p)} for name,p in pairs]
archive=ARCH/'五项数据补缺_原始数据与证据_20261022.zip'
if archive.exists():raise FileExistsError(archive)
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name,p in pairs:z.write(p,name)
 z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
with zipfile.ZipFile(archive) as z:
 for r in manifest:
  b=z.read(r['path']);assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
assert digest(main_db)==before
result={'archive':str(archive),'source_files':len(manifest),'zip_bytes':archive.stat().st_size,
 'sha256':digest(archive),'every_file_verified':True,'main_database_unchanged':True,'dataset_rows':counts}
(ARCH/'归档校验结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
