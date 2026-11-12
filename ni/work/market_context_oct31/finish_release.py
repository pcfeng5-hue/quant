"""Package audited market-context preparation and advance only the saved research pointer."""
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import json,shutil,sqlite3,subprocess,sys,re
from build_context import ROOT,WORK,OUT,sha,read,enc,csvout,compact

def main():
    checks=[]
    def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
    cfg=read(WORK/'contract.json');receipt=read(WORK/'registration_receipt.json');prod=read(OUT/'实现核验.json')
    source=read(ROOT/'work/market_sources_oct31/市场来源独立核对.json')
    event=read(ROOT/'work/event_timing_oct31/事件时间准入审查.json')
    industry=read(ROOT/'work/industry_readiness_oct31/行业代理准入审查.json')
    confirmation=read(ROOT/'work/industry_readiness_oct31/最终冻结版本确认.json')
    independent=read(ROOT/'work/market_context_independent_oct31/市场特征独立复核.json')
    ck('frozen_code_contract_match_receipt',sha(WORK/'build_context.py')==receipt['producer_code_sha256'] and sha(WORK/'contract.json')==receipt['contract_sha256'])
    ck('producer_checks_pass',prod['all_checks_passed'] and prod['passed']==prod['total']==26)
    ck('source_reconstruction_checks_pass',source['passed'] and source['checks_passed']==source['checks_total']==34)
    ck('event_admission_checks_pass',event['all_checks_passed'] and event['checks_passed']==event['checks_total']==21)
    ck('industry_review_checks_pass',industry['all_checks_passed'] and len(industry['checks'])==12 and all(r['passed'] for r in industry['checks']))
    ck('final_frozen_contract_review_pass',confirmation['all_checks_passed'] and all(r['passed'] for r in confirmation['checks']))
    ck('independent_feature_reconstruction_pass',independent['passed'] and independent['checks_passed']==independent['checks_total']==21 and all(r['passed'] for r in independent['checks']))
    ck('independent_review_matches_frozen_producer',independent['code_sha256']==sha(WORK/'build_context.py') and independent['contract_sha256']==sha(WORK/'contract.json'))
    sources=receipt['protected_source_sha256']
    ck('17_protected_inputs_unchanged',len(sources)==17 and all(sha(ROOT/p)==h for p,h in sources.items()),sources)
    core_names=['输入收盘及来源.csv','特征公式字典.csv','收盘差异台账.csv','逐日市场环境特征_工程准备.csv','逐值计算依赖.csv','个股价格分段.csv','日期宽表_未获正式准入.csv','特征覆盖与隔离.csv','市场环境工程输入.sqlite','冻结工程规格.json','运行与来源记录.json','实现核验.json']
    before={name:sha(OUT/name) for name in core_names}
    subprocess.run([sys.executable,str(WORK/'build_context.py')],check=True,capture_output=True,text=True)
    after={name:sha(OUT/name) for name in core_names}
    ck('all_twelve_core_outputs_byte_identical_on_full_rerun',before==after)
    (OUT/'完整重跑核验.json').write_text(enc(dict(all_core_files_byte_identical=before==after,core_files=12,file_sha256=after)))
    with sqlite3.connect((OUT/'市场环境工程输入.sqlite').as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        ck('sqlite_quick_check',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
        count=tuple(c.execute('SELECT COUNT(*),COUNT(DISTINCT signal_date) FROM features').fetchone())
        ck('18560_feature_cells_1160_dates',count==(18560,1160))
        ck('96312_exact_dependencies',c.execute('SELECT COUNT(*) FROM feature_dependencies').fetchone()[0]==96312)
        ck('formal_input_view_empty',c.execute('SELECT COUNT(*) FROM approved_market_context_inputs').fetchone()[0]==0)
        ck('all_runtime_flags_closed',c.execute('SELECT COUNT(*) FROM features WHERE model_input_approved!=0 OR runtime_usable!=0 OR historical_first_availability_certified!=0').fetchone()[0]==0)
        conflict=tuple(c.execute("SELECT COUNT(*),COUNT(DISTINCT signal_date) FROM features WHERE status='CLOSE_SOURCE_CONFLICT'").fetchone())
        ck('28_feature_cells_21_dates_quarantined',conflict==(28,21))
        research=tuple(c.execute("SELECT COUNT(*),SUM(engineering_ready) FROM features WHERE signal_date>='2023-01-03'").fetchone())
        ck('research_14688_cells_14600_engineering_ready',research==(14688,14600))
        wide_ready=c.execute("SELECT COUNT(*) FROM (SELECT signal_date FROM features WHERE signal_date>='2023-01-03' GROUP BY signal_date HAVING MIN(engineering_ready)=1)").fetchone()[0]
        dev_wide=c.execute("SELECT COUNT(*) FROM (SELECT signal_date FROM features WHERE signal_date BETWEEN '2023-01-03' AND '2024-12-31' GROUP BY signal_date HAVING MIN(engineering_ready)=1)").fetchone()[0]
        ck('882_research_and474_development_all_column_ready',wide_ready==882 and dev_wide==474)
        catalog=[dict(r) for r in c.execute('SELECT * FROM feature_catalog')]
        ck('15_candidate_definitions_plus_one_auxiliary',len(catalog)==16 and sum(r['role']=='candidate_context_feature' for r in catalog)==15)
    ev=event['event_admission']
    ck('all_67_event_inputs_and_countdowns_blocked',len(ev)==67 and all(not r['historical_feature_input_approved'] and not r['countdown_feature_approved'] for r in ev))
    ck('economic_episode_dedup_and_notice_roles',event['summary']['economic_episode_ids']==59 and len(event['summary']['official_advance_months'])==2 and len(event['summary']['official_result_months'])==3)
    ck('industry_historical_membership_not_promoted',industry['admission']['formal_model_input_approved'] is False and cfg['historical_industry_membership_verified'] is False)
    ck('no_new_targets_or_models_registered',cfg['future_targets_generated_or_scored'] is False and cfg['outcomes_2025_2026_opened'] is False and cfg['new_scored_or_model_variants']==0 and cfg['previous_registered_research_variants']==15)
    for src,name in [(ROOT/'work/market_sources_oct31/市场来源独立核对','市场来源独立核对'),(ROOT/'work/event_timing_oct31/事件时间准入审查','事件时间准入审查'),(ROOT/'work/industry_readiness_oct31/行业代理准入审查','行业代理准入审查'),(ROOT/'work/industry_readiness_oct31/最终冻结版本确认','最终冻结版本确认'),(ROOT/'work/market_context_independent_oct31/市场特征独立复核','市场特征独立复核')]:
        for suffix in ['.json','.md']:shutil.copy2(src.with_suffix(suffix),OUT/(name+suffix))
    shutil.copy2(WORK/'registration_receipt.json',OUT/'工程登记凭证.json')
    csvout(OUT/'逐事件准入与理由.csv',[{k:compact(v) if isinstance(v,(list,dict)) else int(v) if isinstance(v,bool) else v for k,v in r.items()} for r in ev])
    matrix=[
      dict(input_group='固定单源指数收盘与过去特征',engineering_prepared=1,formal_input_approved=0,limitation='28个冲突依赖单元置空；历史首次可得和修订链未认证',next_gate='单独登记有限开发候选，不等同当前预测可用'),
      dict(input_group='个股同段过去5日相对指数强弱',engineering_prepared=1,formal_input_approved=0,limitation='除权后5观察日不跨段；仅价格收益差，不是可实现alpha',next_gate='按共同样本检验增量信息并保留不确定性'),
      dict(input_group='指数成交量、宽度及资金流',engineering_prepared=0,formal_input_approved=0,limitation='指数量单位/覆盖未认证，历史成员宽度不足',next_gate='补正式定义、历史成员、逐股交易状态和分母'),
      dict(input_group='高德红外历史行业/指数成员身份',engineering_prepared=0,formal_input_approved=0,limitation='官方历史起始名单和全部调整链未取得',next_gate='补公告时间、入选剔除和生效边界'),
      dict(input_group='交割/到期/分派/政策事件倒数',engineering_prepared=0,formal_input_approved=0,limitation='67条全部未获历史/倒数准入；有事后资料和未审计规则版本',next_gate='先补事前证据、规则生效链、正确交易所计划日历'),
      dict(input_group='筹码成本估计及网页摘要',engineering_prepared=0,formal_input_approved=0,limitation='本轮未改变其状态；完整原生价档、稳定口径和首次可得问题保留',next_gate='独立专项补证，不因本轮市场输入准备自动晋级')]
    csvout(OUT/'市场环境输入准入总表.csv',matrix)
    prior_registration=read(ROOT/'outputs/量价增量验证_20261026/累计研究试验台账.json')
    ledger=dict(previous_research_trial_log=prior_registration,scored_or_model_variant_count_remains=15,new_scored_or_model_variants=0,engineering_preparations=[dict(id=cfg['preparation_id'],candidate_feature_definitions=15,auxiliary_definitions=1,source='work/market_context_oct31/contract.json',scored=False,predictive_evidence=False)],feature_choices_must_be_disclosed_in_any_later_model_selection=True)
    (OUT/'累计研究与特征准备台账.json').write_text(enc(ledger))
    state=dict(client_date='2026-10-31',origin='direct_human_request_not_scheduled_heartbeat',research_stage=5,status='audited_market_context_engineering_preparation_complete_not_predictive_acceptance',market_data_last_date='2026-10-21',new_network_or_market_collection=False,observed_dates=1160,research_dates=918,prepared_candidate_feature_definitions=15,auxiliary_definitions=1,feature_cells=18560,dependency_rows=96312,research_engineering_ready_cells=14600,research_all_16_ready_dates=882,development_all_16_ready_dates=474,close_conflict_days=1,quarantined_feature_cells=28,quarantine_affected_dates=21,event_date_role_rows=67,economic_episode_ids=59,event_or_countdown_inputs_approved=0,historical_stock_membership_certified=False,previous_research_variants=15,new_scored_or_model_variants=0,future_targets_generated_or_scored=False,outcomes_2025_2026_opened=False,current_forecast_generated=False,model_input_approved=False,runtime_usable=False,old_protocol_or_risk_modified=False,protected_source_sha256=sources,
      next_checkpoint=['Retain the prior M1 and M2 negative development results and all 15 registered research variants',
      'Review the close-only input preparation and register one narrow market-context development candidate with fixed definitions, matching dates, simple comparator, metrics and sparse-evidence policy before scoring; no search across all 15 prepared definitions',
      'Keep formal historical input gates false; a retrospective engineering experiment cannot certify point-in-time versions or current forecast reliability',
      'Keep all event countdown inputs blocked while acquiring pre-event publication, historical rule versions and the appropriate exchange planned calendar; do not infer lead-time from future stock bars',
      'Historical sector membership, breadth, volume definitions and chip limitations remain; background price-index use does not certify them',
      'Do not open 2025/2026 target periods without separately frozen later-phase protocol and prior checks'])
    (OUT/'本轮状态与续作断点.json').write_text(enc(state))
    uses=f'''# 输入使用、复算与恢复

项目根为 {ROOT}。恢复后按相对目录执行 work/market_context_oct31/build_context.py；只需Python3标准库和已有输入，不联网、不接账户。登记凭证已存在，不再次运行register.py覆盖。程序先核对合同、源码及17个旧来源指纹，再只读market_daily的冻结收盘快照和corporate_actions的三条边界；没有查询标签库、受限库或生成未来收益。

市场环境工程输入.sqlite含9280个双源收盘观察、16个公式、18560个逐日特征单元和96312个精确数值依赖。input_closes不包含成交量/金额/换手；features中engineering_value是通过工程缺值和close冲突规则的值，diagnostic_value是保留的单源诊断值。后者不能用来绕过隔离。工程ready不等于历史正式输入准入。approved_market_context_inputs视图应为空。

收益只依赖两个真实端点，MA20依赖包含当日的20个收盘；股票过去5日收益不跨三条已知除权边界。相对强弱是股票与指数收益的差，单位为小数收益差，乘100显示为百分点差；它不是可投资组合收益、贝塔调整alpha或资金流。

特征覆盖与隔离.csv分全部日期、2023起研究期与2023—2024开发期。日期宽表保留原始日期轴和NULL；不要把过滤后的行数当成原交易间隔，也不要把18560个单元当独立样本。所有指数为价格指数，不冒充股息再投资总回报。

逐事件准入与理由.csv来自独立审查，保留经济事件编号、日期角色、来源、已知性及逐条原因。未来事件倒数需单独冻结协议且取得事前证据；本轮没有计算倒数，也没有检验事件涨跌效应。

独立来源、行业、事件与特征复核脚本分别保存在work/market_sources_oct31、work/industry_readiness_oct31、work/event_timing_oct31、work/market_context_independent_oct31。行业初审合同指纹属于冻结前版本；最终冻结版本确认另附，说明只新增坏价整批拒绝语义，原审查保留。
'''
    (OUT/'输入使用与复算说明.md').write_text(uses)
    report=f'''# 市场环境输入准备：本轮进展

2026年10月31日，多伦多。按用户“来，继续咱们的程序”直接推进；本轮为人工请求的协作批次，不计作夜间自动完成。**已完成市场来源、行业代理和事件时点审查，并做成可复算的市场环境工程输入库。尚未证明这些新特征能提高预测。**

## 本轮具体增加了什么

|部分|完成内容|实际成效|
|---|---|---|
|市场来源|三指数各双源1160日逐值和原件核对|明确同源计算口径、差异字段与价格单位|
|过去市场状态|三指数各1/5/20日过去收益、收盘相对MA20位置，共12个定义|可以把市场背景作为独立可追溯输入准备|
|个股相对强弱|高德红外同段过去5日收益减三指数对应收益，共3个定义；另1个股票辅助|区分个股走势与市场背景，同时避开已知除权价差|
|事件与行业边界|67个日期角色/59个经济编号的事前证据审查；军工代理身份及成员缺口|防止事后日期、当前规则或当前成员偷偷变成历史先验|

15个候选特征定义加1个辅助，不是16个新模型。库内18560条为1160日×16个特征单元；96312条为计算依赖，也不是独立交易样本。2023起918研究日期对应14688个单元，其中14600个在工程口径下可算。全部16列同时工程可算的研究日期882个；2023—2024开发期474个。以后模型只采用哪些列，须先登记，不能为了覆盖或得分事后挑选。

## 价格差异怎样处理

2023—2024开发期三指数收盘双源全部一致。全快照只有上证2026-02-11收盘4131.99与4131.98相差0.01指数点；其他指数的四项OHLC差异只在开盘或最高价，不进入本轮close公式。

采用固定东方财富快照计算，腾讯只用于差异核对，不平均、不拼接、不称任何一方是真值。涉及该close的精确计算依赖共影响28个特征单元、21个不同日期，工程值置NULL；原始值及诊断计算保留。1/5/20日收益各只受两个端点影响，MA20受20个收盘影响，相对强弱继续传递上游差异。

股票收益从2022-06-01共同起点计算，避开未桥接的2022-05-26价格断点。三次已知除权日重新分段，除权后前5个观察日不计算股票过去5日收益及对应相对值。不能据此说公司行动历史已经完整。

## 行业代理和事件的结论

中证军工399967是军工价格背景代理。官方2023年12月V1.2方法原件并不提供完整历史成员，也不能证明高德红外整个区间在样本里；PDF版本日期、下载日期、服务器Last-Modified都不是首次公开和历史生效认证。历史成员、权重和行业宽度缺口继续保留。指数点位不能替代真实机构资金流。

67条事件日期角色归为59个经济编号，不等于67次事件或独立样本。46个月中金所到期/交割记录中，5个月有官方逐月资料，但仅2个月为提前提醒，3个月为事后结果；另41个月仍是公式候选。7份当前规则没有完整历史生效链。事件范围未覆盖全部沪深ETF/股票期权。

**全部67条历史事件输入和事件倒数继续未准入。** 这表示证据不足，不证明事件没有影响。未来倒数必须以当时已公布的正确交易所计划日历为基础，不能用后来真实出现的股票K线或后来才知道的停牌倒算。除权、股权登记、官方现金代派与用户到账分开；政策发文、转载、生效也分开。

## 当前可怎样使用

新库是工程准备：可以复算、检查来源、按日期查看过去市场背景；正式历史输入、运行和当前预测门全部保持false，正式输入视图为空。保存快照上的前缀不变和无未来依赖，不能认证历史未修订或首次可得时间。

本轮沿用截至2026-10-21的行情快照，没有刷新到10月31日，没有新增网络采集、未来目标、模型评分或当前买卖预测。2025/2026原始收盘只用于向后看特征准备；后续结果标签继续隔离。此前M1、M2未优于基准的结论和15个累计研究变体保留，15个新特征选择另外登记，不藏在模型计数里。

## 核验和保存

来源34项、事件21项、行业12项、最终冻结版本确认8项、生产实现26项通过；独立特征复算{independent['checks_passed']}项通过。12个核心产物完整进程重跑字节一致，17个受保护旧来源未变。核验次数不表示预测有效。

- [工程输入库]({OUT/'市场环境工程输入.sqlite'})、[特征字典]({OUT/'特征公式字典.csv'})、[日期宽表]({OUT/'日期宽表_未获正式准入.csv'})。
- [覆盖与隔离]({OUT/'特征覆盖与隔离.csv'})、[逐值来源依赖]({OUT/'逐值计算依赖.csv'})、[输入准入总表]({OUT/'市场环境输入准入总表.csv'})。
- [市场来源核对]({OUT/'市场来源独立核对.md'})、[行业代理审查]({OUT/'行业代理准入审查.md'})、[事件时点审查]({OUT/'事件时间准入审查.md'})、[逐事件准入理由]({OUT/'逐事件准入与理由.csv'})。
- [独立特征复核]({OUT/'市场特征独立复核.md'})、[工程规格]({OUT/'冻结工程规格.json'})、[登记凭证]({OUT/'工程登记凭证.json'})、[完整重跑核验]({OUT/'完整重跑核验.json'})。
- [复算说明]({OUT/'输入使用与复算说明.md'})、[续作断点]({OUT/'本轮状态与续作断点.json'})、[累计研究与特征准备台账]({OUT/'累计研究与特征准备台账.json'})。

## 下一步

本轮完成五大项任务清单中市场/行业/事件输入的这一轮核查和工程准备。下一批先固定一个范围有限的市场环境候选及同日基准、训练/验证边界和评价方法，再用2023—2024开发期检验是否有增量价值；不在15列中穷举挑赢家。事件、历史成员和筹码证据继续独立补缺，不因价格工程完成而自动放行。

完整本地备份目录：`/Users/puchun/Documents/Codex/项目归档/ni/20261031_市场环境输入完整保存/`。是否完整及恢复检查以归档校验结果.json为准。
'''
    (OUT/'本轮推进报告.md').write_text(report)
    missing=[]
    for p in OUT.glob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if target.startswith('/') and not Path(target).exists():missing.append([str(p),target])
    ck('all_report_file_links_resolve',not missing,missing)
    (OUT/'本轮交付核验.json').write_text(enc(dict(client_date='2026-10-31',all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_sha256=sources,current_forecast_generated=False,runtime_usable=False,new_model_variants=0)))
    progress=ROOT/'outputs/项目进度与交易需求档案.md';backup=WORK/'进度档案_本轮前.md'
    if not backup.exists():shutil.copy2(progress,backup)
    txt=progress.read_text();old=next(s for s in txt.splitlines() if s.startswith('更新日期：'))
    txt=txt.replace(old,'更新日期：2026年10月31日。人工协作完成市场环境输入准备：15个候选定义加1个辅助、来源/行业/事件审查与独立复算；未评分新模型或生成当前预测，研究仍在第5步。',1)
    entry='\n- 2026/10/31人工续作：完成[市场环境输入准备](./市场环境输入准备_20261031/本轮推进报告.md)。三指数过去收益、相对MA20及个股相对过去5日收益差共15候选定义+1辅助；18560单元、96312计算依赖，28受冲突单元隔离。行业仅背景代理，67条事件/59编号的历史及倒数准入仍0。工程、来源、事件、行业、独立复算和完整重跑通过；旧源未改，快照仍10/21，无新标签/模型/当前预测。此为用户直接请求批次，不计夜间自动完成；此前夜间未有完成记录。下批单独登记有限市场环境候选再评分。\n'
    if '2026/10/31人工续作：' not in txt:txt=txt.replace('## 本轮补充确认与记账口径\n','## 本轮补充确认与记账口径\n'+entry,1)
    start=txt.index('## 下次协作的起点');end=txt.index('## 2026-10-22 五项补缺收尾',start)
    txt=txt[:start]+'''## 下次协作的起点

以[10/31市场环境工程输入续作断点](./市场环境输入准备_20261031/本轮状态与续作断点.json)为当前入口。数据准备已生成15个候选定义及1个辅助，但未评分新模型。下一批先另行登记一个有限市场环境候选，再在共同开发期日期上与简单基准检验；不得穷举15列、隐去旧M1/M2结果或打开后期目标。行业历史成员、事件事前已知性和筹码限制继续保留。夜间指针接到本次人工核验断点，但不把人工工作记为夜间执行成功。

'''+txt[end:];progress.write_text(txt)
    nightly=ROOT/'outputs/夜间自动推进_20261028';pointer=nightly/'最新续作指针.json'
    pointer_backup=WORK/'夜间续作指针_本轮前.json'
    if not pointer_backup.exists():shutil.copy2(pointer,pointer_backup)
    ptr=read(pointer);ptr.update(last_verified_research_state='outputs/市场环境输入准备_20261031/本轮状态与续作断点.json',last_verified_research_report='outputs/市场环境输入准备_20261031/本轮推进报告.md',research_stage=5,research_variants_so_far=15,prepared_unscored_candidate_definitions=15,latest_batch_origin='direct_human_request',latest_batch_client_date='2026-10-31',next_action=state['next_checkpoint'][1])
    pointer.write_text(enc(ptr))
    logs=nightly/'执行日志';logs.mkdir(exist_ok=True)
    record=dict(origin='direct_human_request',client_date='2026-10-31',status='completed_market_context_engineering_preparation',counts_as_completed_nightly_batch=False,report=ptr['last_verified_research_report'],state=ptr['last_verified_research_state'],new_models_scored=0,outcomes_2025_2026_opened=False)
    (logs/'20261031_人工协作市场环境准备.json').write_text(enc(record))
    print(enc(dict(report=str(OUT/'本轮推进报告.md'),release_checks=len(checks),core_outputs_identical=12,nightly_completed_count_not_incremented=ptr.get('nightly_batches_completed_since_setup'),source_inputs_unchanged=True)))

if __name__=='__main__':main()
