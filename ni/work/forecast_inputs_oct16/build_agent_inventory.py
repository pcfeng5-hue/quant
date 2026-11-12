from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,sqlite3
ROOT=Path('/Users/puchun/Documents/Codex/2026-10-07/ni')
OUT=ROOT/'work/forecast_inputs_oct16'
DB=ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(DB)
c=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
c.execute('PRAGMA query_only=ON')
def rows(q): return [dict(r) for r in c.execute(q)]
refs=[
'outputs/高德红外数据库/查漏补缺报告.md',
'outputs/高德红外数据库/数据库说明与覆盖清单.md',
'outputs/高德红外数据库/筹码基础行情口径核对说明.md',
'outputs/高德红外数据库/筹码基础行情口径核对.json',
'outputs/高德红外数据库/calendar_audit_result.json',
'outputs/高德红外数据库/股本与状态核对说明.md',
'outputs/高德红外数据库/20261015补缺证据/history/index_cross_source_validation.json',
'work/disclosure_time_round6/summary.json',
'work/status_history_round6/local_status_keyword_scan.json',
'work/dividend_event_dates_oct15/event_dates.json',
'outputs/高德红外数据库/东方财富网页筹码核查_20261015.md',
]
bar_groups=rows('''SELECT symbol,source,adjustment,count(*) rows,count(distinct trade_date) dates,min(trade_date) first,max(trade_date) last,volume_unit,turnover_unit,sum(amount IS NULL) amount_null,sum(turnover IS NULL) turnover_null FROM current_daily_bars GROUP BY symbol,source,adjustment''')
base_coverage=rows('''SELECT count(*) rows,count(distinct trade_date) dates,min(trade_date) first,max(trade_date) last,sum(open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL) missing_ohlcv,sum(high<low OR high<open OR high<close OR low>open OR low>close) price_order_failures FROM current_daily_bars WHERE source='em_daily_0' ''')[0]
stock_comparison=rows('''SELECT count(*) paired_dates,sum(abs(e.open-t.open)>0.005 OR abs(e.high-t.high)>0.005 OR abs(e.low-t.low)>0.005 OR abs(e.close-t.close)>0.005 OR abs(e.volume-t.volume)>0.005) differences_over_0_005 FROM current_daily_bars e JOIN current_daily_bars t ON e.trade_date=t.trade_date AND t.source LIKE 'tencent_daily_%' WHERE e.source='em_daily_0' ''')[0]
calendar=rows('''SELECT is_scheduled_open,count(*) rows,min(trade_date) first,max(trade_date) last,calendar_version FROM trading_calendar GROUP BY is_scheduled_open,calendar_version''')
corporate=rows('''SELECT art_code,provider_notice_date,record_date,ex_date,cash_cny_per_10_shares,transfer_shares_per_10,total_shares_before,total_shares_after,availability_status FROM corporate_action_observations ORDER BY ex_date''')
supplemental=rows('''SELECT kind,status,historical_input_eligible,count(*) rows FROM supplemental_disclosure_observations GROUP BY kind,status,historical_input_eligible''')
current_record_eligibility=rows('''SELECT count(*) rows FROM reviewed_historical_source_records''')[0]['rows']
temporal=rows('''SELECT audit_version,historical_input_eligible,count(*) rows FROM record_temporal_audit GROUP BY audit_version,historical_input_eligible''')
columns={t:[r['name'] for r in rows('PRAGMA table_info('+t+')')] for t in ['daily_bars','trading_calendar','source_snapshots','source_records','corporate_action_observations']}
settings={r['key']:r['value'] for r in rows('SELECT * FROM database_settings')}
unit=json.loads((ROOT/'outputs/高德红外数据库/筹码基础行情口径核对.json').read_text())
unit_bad=[r['trade_date'] for r in unit['daily_unit_diagnostics'] if not r['strict_range_consistent']]
index_json=json.loads((ROOT/'outputs/高德红外数据库/20261015补缺证据/history/index_cross_source_validation.json').read_text())
index_summary=[]
for x in index_json['sources']:
 index_summary.append({k:x[k] for k in ['new_source','old_source','overlap_dates','price_difference_dates','volume_difference_dates','difference_source_dates','field_difference_count']})
first_public=json.loads((ROOT/'work/disclosure_time_round6/summary.json').read_text())
items=[]
def add(id,name,coverage,references,blockers,recommendation,status='candidate_not_admitted'):
 items.append({'id':id,'input':name,'verified_coverage':coverage,'historical_model_eligibility':status,'blockers':blockers,'recommended_next_decision':recommendation,'evidence_references':references})
add('raw_ohlcv','个股不复权OHLCV',{'database':base_coverage,'cross_source':stock_comparison},['SQLite:current_daily_bars(source=em_daily_0 / tencent_daily_20xx); daily_bars.volume_unit','outputs/高德红外数据库/查漏补缺报告.md'],['日线为2026年回看版本；没有逐日首次见到/最终修订时间列，不能声称原样复现当时供应商信息。','日线存在不证明盘中可连续成交、可卖数量或涨跌停排队成交；必须与证券状态和执行协议联合验收。'],'可作为下一步工程底座；冻结单一主源、复核容差与收盘后可用时点，并把历史回看假设与未来逐日留存区别记录。不得仅因结构核对通过宣布交易研究整体准入。')
add('scheduled_calendar','沪深计划交易日历',{'natural_days':sum(x['rows'] for x in calendar),'scheduled_open_days':sum(x['rows'] for x in calendar if x['is_scheduled_open']==1),'calendar_groups':calendar},['SQLite:trading_calendar.is_scheduled_open/calendar_version/payload_json','outputs/高德红外数据库/calendar_audit_result.json'],['仅由官方年休市安排及周规则重建，未独立排除临时异常休市。','计划开市不是002414当日正常交易状态。'],'可作为日期索引；若作为事件特征使用，则按年休市公告实际公布日约束已知范围，不能把未来年安排提前加入输入。','structure_verified_semantics_limited')
add('adjusted_price','供应商前复权/后复权价格',{'dates_each':914,'adjustments':['1','2'],'sources':['em_daily_1','em_daily_2']},['SQLite:daily_bars.adjustment/source/snapshot_id','outputs/高德红外数据库/数据库说明与覆盖清单.md'],['只有当前回看价格，没有独立复权因子及其生效/公布/版本表。','未来分红转增可能重写过去价格；三种口径不构成三倍样本。'],'暂不直接作为历史时点合格特征；先确定可在每个决策时点重建的一致价格口径，并以原价及实际权益事件核算持仓。')
add('corporate_actions','权益分派与股本事件',{'implementation_actions':corporate,'supplemental_groups':supplemental},['SQLite:corporate_action_observations.ex_date/availability_status','SQLite:supplemental_disclosure_observations.kind/historical_input_eligible','outputs/高德红外数据库/股本与状态核对说明.md','work/dividend_event_dates_oct15/event_dates.json'],['3项已核实施事件未构成2023年以来所有公司行动无遗漏的认证。','首次公开精确时刻均未认证；公告日、签署日、登记日、生效日不互换。','8个期间末股本不是逐日股本，3处股本性质衔接未解决；3次员工非交易过户不等于新增发行。','代派现金日期不等于用户账户实际到账；税费/持有期应另设账本。'],'将权益核算与预测事件特征分开准入；先补事件全集覆盖声明、有效日和保守信息时点，再做原价/现金/股数核算，不直接回填逐日股本。')
add('historical_security_status','历史停复牌/ST/交易限制状态',{'dedicated_daily_status_table_exists':False,'status_keyword_candidate_pages':8,'status_keyword_fragments':11,'suspension_api_verified_scope':'一个精确日期请求语法，目标股票当日空响应'},['SQLite:coverage_gaps(dataset=trading_calendar_status)','outputs/高德红外数据库/查漏补缺报告.md','work/status_history_round6/local_status_keyword_scan.json','outputs/高德红外数据库/股本与状态核对说明.md'],['没有完整历史日级停牌/复牌/风险警示生效区间。','日报有价格、公告未搜到关键词及单日空响应，都不能认证全部历史没有状态事件。','缺少按历史有效日期版本化的价格限制/可执行条件映射。'],'这是执行与不碰ST约束的必需阻塞项；保持未知，不填正常、不填非ST。')
add('index_prices','市场指数价格',{'sources':index_summary,'latest_source_dates_each':914,'retained_old_source_dates_each':912},['SQLite:database_settings(index_sources)','SQLite:data_source_discrepancies.status/payload_json','outputs/高德红外数据库/20261015补缺证据/history/index_cross_source_validation.json'],['两个价格字段来源相差0.01；尚未独立裁定供应商口径或正确值。','database_settings选择腾讯只是当前展示/日历源选择，不是历史模型输入审批。','同样缺少首次可得/修订时点。'],'预先固定单一来源或登记来源敏感性规则；不得平均、静默覆盖或因某版本结果好而选源。')
add('index_volume','市场指数成交量/额/换手',{'cross_source_volume_difference_dates':194,'new_source_volume_unit':'provider_native_index_volume','tencent_amount_and_turnover_missing_dates_per_index':914},['SQLite:daily_bars.volume_unit/amount/turnover','outputs/高德红外数据库/20261015补缺证据/history/index_cross_source_validation.json'],['统计范围和供应商原生单位未核；数值相同也不足以证明单位相同。','腾讯没有成交额/换手；旧EM有字段不代表语义已核。'],'首轮排除指数成交量/额/换手，价格背景与量背景分开验收。','exclude_until_unit_scope_verified')
add('stock_amount','个股成交额',{'dates':914,'cross_source_independent_amount':False,'unit_check_strict_compatible_days':914-len(unit_bad),'unit_check_strict_exception_dates':unit_bad},['SQLite:daily_bars.amount','outputs/高德红外数据库/筹码基础行情口径核对.json','outputs/高德红外数据库/筹码基础行情口径核对说明.md'],['腾讯未给成交额，不能称914日该字段双源认证。','3日严格反算均价落在不复权高低区间外；0.005元敏感性相容但原因未核。','daily_bars没有独立amount_unit字段，现有元口径证据在外部单位核对文件。'],'先保留原值与三日异常标记；独立确认金额单位、显示精度及异常处置后再按用途准入，不放宽严格检查改写为通过。')
add('turnover_float','个股换手率与流通股本',{'turnover_dates':914,'turnover_unit':'provider_pct','period_end_capital_observations':8,'same_day_examples_unit_compatible':5,'certified_daily_denominator_dates':0},['SQLite:daily_bars.turnover/turnover_unit','SQLite:supplemental_disclosure_observations(kind=capital_period)','outputs/高德红外数据库/筹码基础行情口径核对说明.md','outputs/高德红外数据库/股本与状态核对说明.md'],['换手率缺少独立跨源字段。','8个期末数及5个同日相容点不能认证供应商每日分母或自由流通定义。','无限售股本不等于FREELIQCI_SHARES；不能用当前或之后报告回填过去。'],'把供应商原始换手字段与自算换手分开；分母、历史生效、取值时点未核前先不纳入首轮模型。','exclude_until_denominator_and_time_verified')
add('provenance_availability','来源、版本与首次可得时间',{'source_snapshots':rows('select count(*) n from source_snapshots')[0]['n'],'current_reviewed_source_records':current_record_eligibility,'temporal_audit_groups':temporal,'announcement_documents_mapped':first_public['mapped_pdf_count'],'actual_historical_first_publication_certified':first_public['actual_historical_first_publication_certified_count']},['SQLite:source_snapshots.retrieved_at/sha256/raw_path/dataset','SQLite:source_records.publication_time/availability_status/date_field','SQLite:record_temporal_audit.historical_input_eligible','SQLite:reviewed_historical_source_records view SQL','work/disclosure_time_round6/summary.json'],['retrieved_at是本次真实取得时间，不是当时公开或模型可得时点。','source_snapshots.accepted是解析接受记录数，不是模型资格。','reviewed_historical_source_records仅连接source_records；不能用该视图推导daily_bars已批准或已被逐行审核。','行情与日历缺少独立first_available及historical_input_eligible列；应在准入台账按用途和版本补充。','308份普通目录时间为00:00，不能当真实零点；4份IR时刻语义未认证，NOTICE_DATE不通用。'],'为每项建立观察日/公开候选/供应商时间/取得时间/修订版本/用途/准入决策；无法证明历史原样版本的回看数据须明示假设，未来预测从实际留存快照起建立可靠时点链。')
# Optional priority note only: no extension of chip work in this task.
chip={'priority':'用户最新指示为当前筹码专项；本盘点只作独立候选清单，不改变其优先级。','complete_daily_price_bin_records':rows('select count(*) n from chip_estimates')[0]['n'],'reference':'outputs/高德红外数据库/东方财富网页筹码核查_20261015.md','status':'两日网页摘要不等于914日完整档位；由主agent继续专项核验。'}
c.close();after=sha(DB)
result={'title':'D1候选输入独立准入盘点建议','date_local':'2026-10-16','created_at_utc':datetime.now(timezone.utc).isoformat(),'scope':{'database':str(DB),'database_scope':settings,'read_only':True,'network_collection':False,'indicators_returns_probabilities_computed':False,'main_database_or_formal_specs_modified':False,'database_sha256_before':before,'database_sha256_after':after,'database_bytes_unchanged':before==after},'interpretation':['覆盖/字段核对、研究输入资格和真实执行资格是三个不同结论。','本文件提出候选准入建议，没有新授予任何数据历史模型资格。','当前正式库截至2026-10-15；本轮没有刷新10月16日行情。','914日不是914独立事件；来源、复权口径及快照不能累加成样本。'],'items':items,'current_priority_chip_note':chip,'database_inspection':{'bar_groups':bar_groups,'relevant_columns':columns},'evidence_manifest':[{'path':p,'exists':(ROOT/p).exists(),'sha256':sha(ROOT/p) if (ROOT/p).exists() else None} for p in refs]}
(OUT/'agent_inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
lines=['# D1 候选输入独立准入盘点建议','', '日期：2026年10月16日；只读正式SQLite和既有报告，无网络采集、指标/收益/概率计算、合库或正式规格改动。主库快照仍截至2026年10月15日。','', '**本轮优先级按用户最新指示保留为筹码专项。以下只是独立候选盘点，不延长其他补数工作，也没有授予历史输入资格。**','', '| 输入 | 已核覆盖 | 主要阻塞与建议 |','|---|---|---|']
summary=[
('不复权OHLCV','914日；双源914日配对，价格/量在0.005容差内无差异','可准备工程底座；仍需数据时点、历史状态及执行协议。'),
('计划交易日历','1384自然日，914计划开市日','可作日期索引；不证明个股正常交易或无临时休市。'),
('复权价格','前/后复权各914日','无独立因子及历史版本，不能直接宣称当时可重建。'),
('公司行动','3项实施事件；8股本期末观测；3衔接问题','首次可得及全集覆盖未闭合；权益核算与预测特征分开准入。'),
('证券状态','未取得完整日级状态史','不碰ST及可执行性必需阻塞；未知不能填正常。'),
('指数价格','腾讯各914日，旧EM各912日','2价格字段有差异；固定来源不等于输入审批，需时点与处置规则。'),
('指数量/额/换手','194日量差异；腾讯无额/换手','单位和统计范围未核，建议首轮排除。'),
('个股成交额','914日；911日严格单位相容','3日异常保留；缺跨源金额，核实金额单位和精度。'),
('换手/流通分母','换手914日；8期末股本、5同日相容点','未认证逐日分母，不能回填报告或当前股本。'),
('来源/首次可得','96快照；312公告对应；first-public认证0','当前已审source_records准入0；行情无同类准入字段，需单独用途台账。')]
for a,b,d in summary: lines.append(f'| {a} | {b} | {d} |')
lines+=['','## 重要实现边界','', '- `current_daily_bars` 按最近成功来源快照取数，不是逐历史时点的可得视图。`source_snapshots.accepted` 是解析接受数，不代表准入。','- `reviewed_historical_source_records` 只覆盖 `source_records`，当前0行；不可据此声称914行情已被逐行审批，或将该0行误解释成行情不存在。','- 三日单位严格异常是2024-03-11、2024-08-05、2026-07-09。0.005元敏感性相容没有解决原因；未改写成严格通过。','- 当下历史回看不自动等于当时可见，但也不意味着一律永久不可研究：需明确回看假设、保守滞后、版本限制，以及哪些结论必须等未来逐日留存。','', '## 可复核结果','',f'- 主库只读前后SHA-256一致：`{before}`。','- 原始字段与覆盖SQL核查结果、每项字段阻塞和证据文件哈希，见同目录 `agent_inventory.json`。','- 未补齐证券状态、公司行动/复权与信息时点等必需项前，不建议以“914日已齐”为由启动完整历史交易优势验证。','- 本盘点不改周期、阈值、实验预算、正式规格、账户或账簿。']
(OUT/'候选输入准入盘点建议.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'items':len(items),'database_unchanged':before==after,'raw_coverage':base_coverage,'stock_comparison':stock_comparison,'outputs':['work/forecast_inputs_oct16/agent_inventory.json','work/forecast_inputs_oct16/候选输入准入盘点建议.md']},ensure_ascii=False))
