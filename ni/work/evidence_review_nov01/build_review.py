"""Inventory existing research evidence only. Never fit, predict or score.

Copied sources are immutable. All decoded outcome rows are existing 2023-2024
development results. Indicator snapshots may contain later raw inputs, which are
copied byte-for-byte but not queried here for later outcome generation.
"""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import shutil
import sqlite3

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/研究证据与覆盖审查_20261101'
FOLDERS=[
 'outputs/三线研究启动_20261025/量价基线',
 'outputs/初始化与验证推进_20261026/时间验证',
 'outputs/量价增量验证_20261026',
 'outputs/市场环境候选验证_20261031']
DBS=[FOLDERS[0]+'/开发期结果隔离.sqlite',FOLDERS[1]+'/开发期滚动验证.sqlite',FOLDERS[2]+'/量价增量开发验证.sqlite',FOLDERS[3]+'/市场状态候选开发验证.sqlite']
ROUND_IDS=['D12_20261025','M1_round','M2_round','M3_round']
ARCHIVE=Path('/Users/puchun/Documents/Codex/项目归档/ni/20261101_研究证据复盘完整保存')

def read(p):return json.loads(Path(p).read_text())
def write(p,obj):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def pct(x):return '—' if x is None else f'{100*x:.2f}%'
def num(x):return '—' if x is None or x=='' else f'{float(x):.9f}'
def mdtable(headers,rows):
 return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(str(v).replace('|','\\|').replace('\n',' ') for v in row)+' |' for row in rows])
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 checks=[]
 def ck(name,ok,details=None):
  checks.append(dict(check=name,passed=bool(ok),details=details))
  if not ok:raise AssertionError(name)
 signal=read(ROOT/'work/evidence_signals_nov01/独立审查.json')
 models=read(ROOT/'work/evidence_models_nov01/独立审查.json')
 ck('signal_independent_35_checks',signal['all_checks_passed'] and signal['passed']==signal['total']==35)
 ck('model_independent_54_checks',models['all_checks_passed'] and models['passed']==models['total']==54)
 source_paths={str(p.relative_to(ROOT)) for f in FOLDERS for p in (ROOT/f).rglob('*') if p.is_file()}
 ck('all_88_prior_round_files_included',len(source_paths)==88)
 source_paths.update(signal['source_sha256_before'])
 source_paths.update(models['source_sha256'])
 receipt=read(ROOT/'work/market_model_oct31/registration_receipt.json')
 source_paths.update(receipt['protected_source_sha256'])
 for rel in ['work/market_model_oct31/contract.json','work/market_model_oct31/run_market_model.py','work/market_model_oct31/registration_receipt.json','work/market_model_oct31/strict_screen_review.py']:
  source_paths.add(rel)
 protected={p:sha(ROOT/p) for p in sorted(source_paths)}
 ck('previous_protected_source_hashes_still_match',all(protected[p]==v for p,v in receipt['protected_source_sha256'].items()))
 ck('signal_and_model_audit_sources_match',all(protected[p]==v for p,v in signal['source_sha256_before'].items()) and signal['source_sha256_before']==signal['source_sha256_after'] and all(protected[p]==v for p,v in models['source_sha256'].items()))
 snapshot=OUT/'原有结果原样快照'
 manifest=[]
 for folder in FOLDERS:
  for source in sorted((ROOT/folder).rglob('*')):
   if not source.is_file():continue
   rel=str(source.relative_to(ROOT));dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
   manifest.append(dict(source=rel,snapshot=str(dest.relative_to(OUT)),bytes=dest.stat().st_size,sha256=sha(dest)))
 ck('all_88_copied_files_byte_identical',len(manifest)==88 and all(r['sha256']==protected[r['source']] for r in manifest))
 write(OUT/'原有结果文件清单与SHA256.json',dict(scope='All 88 files from four saved result directories; originals retained',files=manifest))
 variants=[]
 for v in signal['variants']:
  variants.append(dict(variant_id=v['cumulative_variant_id'],key=v['registered_signal_id'],kind='development_descriptive_signal',name=v['chinese_name'],definition=v['definition'],eligible_definition=v['eligible_definition'],first_registered_date='2026-10-25',rounds=['D12_20261025'],existing_statistics=v['source_saved_statistics'],eligible_missing_relative_to_469=v['eligible_missing_relative_to_469'],evidence_status=v['status'],current_forecast_approved=False))
 model_definitions=[
  (13,'M0_laplace_constant','历史频率常数基准','p0=(k+1)/(n+2)','2026-10-26',['M1_round','M2_round','M3_round'],'Comparator only; not a profitable or calibrated benchmark certification'),
  (14,'M1_ma_group_shrinkage','均线三组收缩','pMA=(kMA+20*p0)/(nMA+20); MA5>MA10>MA15且MA15上升/反向/其他','2026-10-26',['M1_round','M2_round'],'No upgrade evidence on matched dates; repeated in M2 round as comparator'),
  (15,'M2_ma_volume_hierarchical','均线×量价九格','pCell=(kCell+20*pMA)/(nCell+20); MA三组×放量收涨/放量收跌/其他','2026-10-26',['M2_round'],'No improvement over matched M1 or M0; 37/54 cells sparse, 3 empty'),
  (16,'M3_shenzhen_ma20_group_shrinkage','深成指MA20两组收缩','pGroup=(kGroup+20*p0)/(nGroup+20); 399001.SZ close/MA20-1>0或<=0','2026-10-31',['M3_round'],'All four descriptive screen conditions failed; not a conditional increment above M1 or M2')]
 for vid,key,name,formula,date,runs,status in model_definitions:
  evaluations=[]
  for rid in runs:
   run=models['runs'][rid]
   evaluations.append(dict(round_id=rid,scoring_dates=len(run['scoring_dates']),fixed_grid_dates=len(run['fixed_grid_dates']),all_saved_metrics=[r for r in run['metrics'] if r['model_id']==key],contract_experiment_id=run['contract']['experiment_id']))
  variants.append(dict(variant_id=vid,key=key,kind='registered_probability_model_definition',name=name,definition=formula,first_registered_date=date,rounds=runs,evaluations=evaluations,evidence_status=status,current_forecast_approved=False))
 ck('exact_16_unique_in_original_registration_order',[v['variant_id'] for v in variants]==list(range(1,17)) and len({v['key'] for v in variants})==16)
 ck('12_descriptive_plus_four_model_definitions',Counter(v['kind'] for v in variants)=={'development_descriptive_signal':12,'registered_probability_model_definition':4})
 ck('all_three_runs_included_with_exact_saved_row_counts',set(models['runs'])==set(ROUND_IDS[1:]) and sum(len(r['metrics']) for r in models['runs'].values())==98 and sum(len(r['comparisons']) for r in models['runs'].values())==70 and sum(len(r['folds']) for r in models['runs'].values())==18)
 ledger=dict(review_id='002414_existing_research_evidence_review_20261101_v1',client_date='2026-11-01',scope='Existing results inventory only; no fitting, target generation, scoring or winner selection',variant_count=16,descriptive_signal_definitions=12,unique_model_definitions=4,counting='12 + (M0,M1) + M2 + M3 = 16; repeated comparators, cells, folds, warmup studies and prepared columns not extra variants',all_price_window_statistics=signal['all_price_window_saved_statistics'],variants=variants,model_rounds=models['runs'],coverage_reconciliation_M1_to_M2=models['coverage_reconciliation_M1_to_M2'],lost_M2_dates=models['lost_M2_dates'],old_audit_records=models['prior_audit_records'],new_models_fitted=0,new_scores_calculated=0,new_target_labels_generated=False,outcomes_2025_2026_opened=False,current_forecast_generated=False,formal_model_input_approved=False,runtime_usable=False,limitations=signal['limitations']+models['limitations'])
 write(OUT/'16项研究变体完整台账.json',ledger)
 # SQLite stores exact existing rows, never newly calculated probabilities or losses.
 db=OUT/'研究证据汇总.sqlite'
 if db.exists():raise FileExistsError(db)
 table_inventory=[]
 with sqlite3.connect(db) as target:
  target.execute('CREATE TABLE variants(variant_id INTEGER PRIMARY KEY,entry_key TEXT UNIQUE,kind TEXT,name TEXT,record_json TEXT)')
  target.executemany('INSERT INTO variants VALUES(?,?,?,?,?)',[(v['variant_id'],v['key'],v['kind'],v['name'],json.dumps(v,ensure_ascii=False,allow_nan=False)) for v in variants])
  target.execute('CREATE TABLE saved_result_rows(round_id TEXT,table_name TEXT,row_number INTEGER,source_database TEXT,record_json TEXT,PRIMARY KEY(round_id,table_name,row_number))')
  for rid,rel in zip(ROUND_IDS,DBS):
   with sqlite3.connect((ROOT/rel).as_uri()+'?mode=ro',uri=True) as src:
    src.row_factory=sqlite3.Row
    ck('source_database_quick_check_'+rid,src.execute('PRAGMA quick_check').fetchone()[0]=='ok')
    tables=[r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for table in tables:
     records=[dict(r) for r in src.execute('SELECT * FROM "'+table+'" ORDER BY rowid')]
     if table in ['predictions','development_price_outcomes']:
      ck('existing_target_date_bound_'+rid,all('2023-01-03'<=r['signal_date']<=r['outcome_observation_date']<='2024-12-31' for r in records))
     target.executemany('INSERT INTO saved_result_rows VALUES(?,?,?,?,?)',[(rid,table,i,rel,json.dumps(r,ensure_ascii=False,allow_nan=False)) for i,r in enumerate(records)])
     table_inventory.append(dict(round_id=rid,table_name=table,rows=len(records),source_database=rel))
  ck('new_evidence_database_quick_check',target.execute('PRAGMA quick_check').fetchone()[0]=='ok')
  ck('all_2172_existing_prediction_rows_preserved',target.execute("SELECT count(*) FROM saved_result_rows WHERE table_name='predictions'").fetchone()[0]==2172)
  ck('all_98_metrics_and_70_comparisons_preserved',target.execute("SELECT count(*) FROM saved_result_rows WHERE table_name='metrics'").fetchone()[0]==98 and target.execute("SELECT count(*) FROM saved_result_rows WHERE table_name='comparisons'").fetchone()[0]==70)
 write(OUT/'全部结果表与样本索引.json',dict(tables=table_inventory,original_file_manifest='原有结果文件清单与SHA256.json',all_sample_dates={rid:dict(scoring_dates=run['scoring_dates'],fixed_grid_dates=run['fixed_grid_dates'],training_membership_file=run['training_membership_file'],exclusion_ledger_file=run['exclusion_ledger_file']) for rid,run in models['runs'].items()},raw_descriptive_sample_reconstruction='Use unchanged saved fixed signals joined by trade_date=signal_date to the 469 existing development outcome rows; do not generate targets from later raw inputs',not_independent_cases=True))
 for name,sub in [('12信号独立核查','evidence_signals_nov01'),('三轮模型独立核查','evidence_models_nov01')]:
  for ext in ['json','md']:shutil.copy2(ROOT/f'work/{sub}/独立审查.{ext}',OUT/f'{name}.{ext}')
 # Readable annex displays every saved metric, comparison, fold and fitted group.
 annex=['# 全部既有评分、对照、参数和覆盖','2026-11-01。以下逐行抄录旧结果，不重新计算评分。顺序按轮次、原表顺序；没有挑季度、组或抽样相位。完整逐日记录、训练成员、排除、校准和源版本均见原样快照及研究证据汇总.sqlite。']
 for rid,run in models['runs'].items():
  annex+=['\n## '+rid+'：全部分数',mdtable(['折','样本','模型','n','Brier','对数损失'],[[r['fold_id'],r['subset'],r['model_id'],r['n'],num(r['brier']),num(r['log_loss'])] for r in run['metrics']]),'\n### 全部配对对照','每行保留原始字段名，正差通常表示候选误差增加；定义见该轮合同。','```json',json.dumps(run['comparisons'],ensure_ascii=False,indent=2),'```','\n### 六折覆盖','```json',json.dumps(run['folds'],ensure_ascii=False,indent=2),'```','\n### 全部拟合参数（含空组与回退）','```json',json.dumps(run['fitted_rows'],ensure_ascii=False,indent=2),'```','\n### 全部固定分箱校准诊断','```json',json.dumps(run['calibration_rows'],ensure_ascii=False,indent=2),'```']
 (OUT/'全部既有评分与覆盖.md').write_text('\n\n'.join(annex)+'\n')
 desc_rows=[]
 for v in variants[:12]:
  s=v['existing_statistics'];desc_rows.append([v['variant_id'],v['name'],s['n_overlapping_observations'],f"{s['positive_count']}/{s['zero_count']}/{s['negative_count']}",pct(s['positive_observed_frequency']),s['eligible_baseline_n'],pct(s['eligible_baseline_positive_frequency']),s['fixed_every_fifth_anchor_n'],pct(s['fixed_grid_positive_frequency'])])
 descriptable=mdtable(['编号','信号定义','触发n','正/零/负','历史正频率','资格基准n','基准正频率','固定网格n','网格正频率'],desc_rows)
 pooled_rows=[]
 for rid,run in models['runs'].items():
  for m in run['metrics']:
   if m['fold_id']=='POOLED':pooled_rows.append([rid,m['subset'],m['model_id'],m['n'],num(m['brier']),num(m['log_loss'])])
 modeltable=mdtable(['轮次','样本','模型','日期n','Brier','对数损失'],pooled_rows)
 report=f'''# 研究证据与覆盖审查 v1

2026年11月1日，多伦多。完成用户指定的第一步：整理已有16项研究选择、样本和全部结果。本批没有训练模型、生成新目标或重新评分。项目仍在第5步。

## 目前可以下的结论

16项的确切组成是**12个描述性信号定义＋4个模型定义（M0/M1/M2/M3）**。M0是比较基准；M1、M2、M3分别检验均线、量价增量和市场状态，目前均未取得升级依据。12项信号中有高、低历史频率，但没有据此完成预测或盈利验证。不能把这16项称为16个已验证模型，也不能把三个未改善候选泛化成所有这些信息均无用。

三轮模型保持各自共同样本：308、298、331个评分日期。M0及M1在后续轮次重新拟合，只算原有模型定义，不重复计新变体。折、组、参数行、固定网格、筹码初始化敏感性和15个市场输入准备定义均不另算新模型。累计16的账法是12+2+1+1；它记录研究选择，不是16次独立检验或多重试验校正。

## 1—12：按登记顺序列出所有信号

统计对象都是2023—2024已经保存的开发期：484个原始锚点，469个价格窗口；正219、零6、负244。15个原排除包括10个已知除权窗口和5个跨开发结束边界窗口。信号在完成当日收盘后形成，工程标签为C[t+5]/O[t+1]−1，零变动单列；它不是费用后交易收益。每项公式、分段、预热与缺失定义完整存入JSON台账。

{descriptable}

“历史正频率”是既有开发期观察比例，不是当前上涨概率或交易胜率。每项资格基准只含该信号可计算且有既有标签的日期，其中也包含信号触发日；它不是互斥的未触发控制组。不同资格分母不可统一替换为469。MACD交叉资格209、MA交叉结合当日MACD资格211的差异来自前者另需前日MACD，不是数据错漏。

12项中7项触发样本少于30，固定网格11项少于30；30只是原展示警示，达到30也不证明充分。网格从484个原锚点事先每5条取一次，不在筛选后重排或挑相位。重叠、共同市场时期及信号间相关性仍在，不能把这些观察当独立试验。全部原有频率差、零/负频率、变化中位数、10%/90%分位数和网格资格基准均保存在[完整台账](./16项研究变体完整台账.json)及原样快照，未按高低排名。

## 13—16：模型定义与三轮结果

| 累计编号 | 定义 | 首次出现 | 解释 |
|---|---|---|---|
|13|M0常数基准，p0=(k+1)/(n+2)|2026-10-26|每轮在本轮共同训练池重新拟合；基准不是有效交易策略认证|
|14|M1均线上行/下行/其他三组，向p0固定20收缩|2026-10-26|在M1轮为候选，在M2轮为重复对照|
|15|M2均线×放量收涨/收跌/其他九格，向均线父组固定20收缩|2026-10-26|主问题是相对同轮M1能否增加信息|
|16|M3深成指close/MA20−1大于0或不大于0两组，向p0固定20收缩|2026-10-31|与同轮M0比较，并未检验在M1/M2之上的增量|

均线组沿用MA5/10/15及MA15斜率；放量严格大于此前20个同段观察日均量的1.5倍，分母不含当日。M3均价含当日。缺失不填0。空组按各轮合同回到基准或父组，训练少于100共同弃答；20和100均为冻结工程选择，不是可信度门槛或独立贝叶斯先验。原合同、登记、代码和结果不修改。

Brier和自然对数损失均为概率误差，越低越好，不是收益率或准确率。以下每一轮只能在轮内同日期比较：

{modeltable}

| 候选问题 | 同日主对照 | 全重叠Brier差（候选−对照） | 结论 |
|---|---|---:|---|
|均线三组是否改善|M1−M0，308日期|+0.002997484|未支持升级|
|量价是否在均线上增加信息|M2−M1，298日期|+0.002026685|未支持升级；对同轮M0也较差|
|深成指MA20状态是否有用|M3−M0，331日期|+0.003201429|未支持升级，四项描述筛选均不通过|

固定网格的主对照方向也没有扭转上述结论。这里只转录既有分数，没有新拟合校准或显著性检验；不能从个别季度改善宣布有效。全部98行模型评分、70行配对对照、18行折覆盖、全部拟合组及空箱诊断见[完整附件](./全部既有评分与覆盖.md)，2172条旧概率及原始成员/排除逐行存于汇总SQLite和88份原样快照。2172是含重复模型和日期的存储行数，不是独立样本数。

## 样本为什么不同

| 轮次 | 六折验证锚点 | 无原标签 | 结果跨折末 | 特征未就绪 | 最终共同日期 | 固定网格日期 | 概率行 |
|---|---:|---:|---:|---:|---:|---:|---:|
|M1|366|10|25|23|308|61|616|
|M2|366|10|25|33|298|59|894|
|M3|366|10|25|0|331|66|662|

所有轮次使用同样六个验证季度：2023Q3、2023Q4、2024Q1—Q4，训练为扩展历史。训练标签实际结束必须早于验证首日，验证标签结束不跨折末，每折拟合一次后冻结。原15项标签排除与各折35项无标签/跨折记录是不同层次，不能直接相加当独立损失。

M2比M1少10个评分日期，来自两次已知除权后量能20日预热比均线额外等待5日；完整日期和原因保留。M3只要求选定市场特征，其开发期484日均可算，故无需承担个股均线预热的23日评分损失。331比308多不是预测更准的证据。共同训练池也随特征资格改变，不能拿跨轮M0或M1分数直接相减排名。六折共享历史，固定网格也未认证独立。

M2的54个逐折九格中37个训练样本少于20、3个空格，完整保留，不按结果合并或丢弃。M3有6折中3折Brier较低，但合并Brier、合并对数损失、固定网格Brier和至少4折改善四项筛选全部不通过；这是既有描述筛选，不是统计显著性检验。

## 已有复核证据及实际边界

| 成果 | 已保存技术核查 | 这些检查能说明什么 |
|---|---|---|
|12信号|实现25、来源独立14、11核心文件重跑一致|公式、时间依赖和原件对应；不认证预测|
|M1轮|实现24、独立20、完整重跑记录保留|训练与评分的实现对应冻结协议|
|M2轮|实现28、独立模型34、独立输入30、15核心文件重跑一致|同日对照、量能/分段、稀疏格和剔除对账|
|M3轮|实现31、输入22、冻结前静态14、模型独立47、严格发布门14、16核心文件重跑一致|依赖、样本、分数和完整身份对应|

M3冻结生产器的独立筛选辅助函数有“等长度重复一折/缺一折”身份检查边界。实际结果完整，数值不受影响；旧源码保留，额外必须经过的严格发布门精确核对折/子集、计数、指标与准入标记，并拒绝空结果自批准。不能把这个辅助函数说成已在原源码修好，也不能以检查通过代替预测有效。

本次另完成12信号证据审查35项、三轮模型证据审查54项；对应源哈希和全部原记录另附。它们是整理的准确性核查，没有重算新收益标签或概率评分。

## 三类事情分开记录

1. **已经测过但未见改善：** 本轮列出的M1、M2、M3固定候选。保留否定结果，不用代码正确性升级。
2. **数据还不能支持正式验证：** 历史首次可得/修订、逐日官方ST/停复牌/限价、真实费用成交、行业历史成员和事件事前已知性仍有缺口。筹码摘要、自建估计、供应商原生完整价档分开；未准入不能当已测试无效。
3. **尚未验收的产品：** 买/等/持/卖、净收益及路径风险未由这个五日方向标签完整回答，当前没有通过验收的买卖预测卡，也没有进入模拟使用或真实资金阶段。

这些结果来自已反复探索的2023—2024，不能称全新独立测试。本批不读、生成或汇总2025/2026后期目标；不能因保留了原始行情就称后期标签已开放。沿用行情快照截至2026-10-21，本批没有刷新行情。正式输入、运行、晋级门保持false，已确认资金和已实现亏损口径不变。

## 本步交付与续作

- [16项完整台账](./16项研究变体完整台账.json)：定义、资格、全部旧统计和模型轮次。
- [全部既有评分与覆盖](./全部既有评分与覆盖.md)：所有季度和固定网格、对照、覆盖、组参数及校准。
- [研究证据汇总SQLite](./研究证据汇总.sqlite)：16定义与四轮既有结果逐行汇总，不改变原字段值。
- [原样快照文件清单](./原有结果文件清单与SHA256.json)、[结果表与样本索引](./全部结果表与样本索引.json)：88原文件、逐表行数、日期、训练/排除位置及SHA，原件全部保留。
- [本轮状态与续作断点](./本轮状态与续作断点.json)：本步已完成，剩余三个审查未冒充完成。

下一步是“预测问题与标签适用性审查”，先明确买/等/持/卖、期限、收益幅度与风险怎样对应。此后才做准入缺口矩阵和路线决策。仍不扫描其余14准备列、不开新模型、不开放后期目标。完整归档在项目外保存，最终是否通过以{ARCHIVE/'归档校验结果.json'}为准。
'''
 (OUT/'研究证据与覆盖审查_v1.md').write_text(report)
 ck('primary_report_and_all_definitions_saved',len(report)>4000 and len(read(OUT/'16项研究变体完整台账.json')['variants'])==16)
 ck('all_protected_sources_unchanged_after_build',all(sha(ROOT/p)==v for p,v in protected.items()))
 write(OUT/'本轮构建核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,protected_source_sha256=protected,source_file_count_copied=88,no_new_models_or_scores=True))
 summary=dict(cumulative_registered_variants=16,descriptive_signal_definitions=12,unique_model_definitions=4,model_rounds=3,existing_prediction_rows=2172,existing_metric_rows=98,existing_comparison_rows=70,existing_fold_rows=18,prior_result_files_copied=88,new_model_variants=0,new_models_fitted=0,new_scores_calculated=0,later_target_outcomes_opened=False,phase_promotion_approved=False)
 state=dict(client_date='2026-11-01',origin='direct_human_request_not_scheduled_heartbeat',research_stage=5,status='evidence_review_built_awaiting_final_correspondence_audit',review_package_step=1,review_package_step_completed_pending_audit=True,review_package_steps_total=4,
  completed=['Inventory of all 16 original research choices, four saved result packages, every quarter/grid metric and all sample/exclusion records'],partial=['Final independent correspondence review and archive completion pending'],blocked=['Formal PIT/state/cost/fill certification and predictive acceptance remain unfulfilled'],
  archive_summary=summary,cumulative_registered_variants=16,new_registered_model_variants=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,current_forecast_generated=False,model_input_approved=False,runtime_usable=False,phase_promotion_approved=False,old_protocol_or_risk_modified=False,
  source_hashes=protected,counts_as_completed_nightly_batch=False,
  next_checkpoint=['Complete only the prediction-question and label-suitability review using existing definitions and synthetic examples; no new real outcome generation or score search','Then prepare temporal/execution/input-admission gap matrix and a next-stage route decision; do not claim those reviews already complete','No scanning remaining 14 prepared columns, no new candidate and no later target opening without separate protocol and acceptance gates'],
  archive_verification_path=str(ARCHIVE/'归档校验结果.json'),confirmed_test_intent_cash_cny=10000,confirmed_pause_cumulative_realized_loss_cny=2000,floating_pnl_separate=True,real_trading_authorized=False)
 write(OUT/'本轮状态与续作断点.json',state)
 print(json.dumps(dict(built=True,checks=len(checks),variants=16,copied_result_files=88,existing_prediction_rows=2172,protected_sources=len(protected),new_scores=0),ensure_ascii=False))

if __name__=='__main__':main()
