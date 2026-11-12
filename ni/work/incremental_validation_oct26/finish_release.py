"""Publish independently checked research results and a reproducible checkpoint."""
from pathlib import Path
import csv,hashlib,json,re,shutil,sqlite3,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/量价增量验证_20261026'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def main():
    checks=[]
    def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
    producer=WORK/'run_incremental.py';contract=WORK/'contract.json';receipt=read(WORK/'registration_receipt.json')
    implementation=read(OUT/'实现验证结果.json')
    independent=read(ROOT/'work/incremental_independent_audit_oct26/独立复核.json')
    features=read(ROOT/'work/volume_feature_audit_oct26/独立量价特征核查.json')
    ck('registered_code_and_contract_unchanged',sha(producer)==receipt['producer_code_sha256'] and sha(contract)==receipt['contract_sha256'])
    ck('implementation_checks_pass',implementation['all_checks_passed'] and implementation['passed']==implementation['total']==28)
    ck('independent_checks_pass',independent['all_checks_passed'] and independent['passed']==independent['total'])
    ck('independent_review_matches_final_code_contract',independent['producer_code_sha256']==sha(producer) and independent['contract_sha256']==sha(contract))
    # The feature auditor's public structure is normalized here after inspection.
    ck('feature_source_audit_pass',features['passed']==features['total']==30 and len(features['checks'])==30 and all(r['passed'] for r in features['checks']))
    sources=receipt['protected_source_sha256']
    ck('all_13_registered_sources_unchanged',len(sources)==13 and all(sha(ROOT/p)==v for p,v in sources.items()),sources)
    core=[p for p in OUT.iterdir() if p.is_file() and p.name in ['逐日概率与实际结果_仅开发期.csv','六折训练与覆盖.csv','逐折模型与全部九格.csv','共同训练样本成员.csv','训练与验证弃答台账.csv','概率评分.csv','同日模型对照.csv','固定分箱校准诊断.csv','逐日配对误差差.csv','与上轮覆盖对账.csv','较上轮减少的评分日期.csv','量价增量开发验证.sqlite','预登记研究协议.json','运行与输入合同.json','实现验证结果.json']]
    before={p.name:sha(p) for p in core}
    subprocess.run([sys.executable,str(producer)],check=True,capture_output=True,text=True)
    after={p.name:sha(p) for p in core}
    ck('all_15_core_files_identical_on_full_process_rerun',len(core)==15 and before==after)
    (OUT/'完整重跑核验.json').write_text(enc(dict(all_core_files_byte_identical=before==after,core_file_count=len(core),file_sha256=after)))
    with sqlite3.connect((OUT/'量价增量开发验证.sqlite').as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        ck('sqlite_quick_check',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
        count=tuple(c.execute('SELECT COUNT(*),COUNT(DISTINCT signal_date),MAX(outcome_observation_date) FROM predictions').fetchone())
        ck('894_predictions_298_dates_development_only',count==(894,298,'2024-12-31'),count)
        ck('all_runtime_gates_closed',c.execute('SELECT COUNT(*) FROM predictions WHERE runtime_usable!=0 OR historical_model_input_approved!=0').fetchone()[0]==0)
        folds=[dict(r) for r in c.execute('SELECT * FROM folds')]
        fitted=[dict(r) for r in c.execute('SELECT * FROM fitted')]
        metrics=[dict(r) for r in c.execute("SELECT * FROM metrics WHERE fold_id='POOLED'")]
        comparison=[dict(r) for r in c.execute('SELECT * FROM comparisons')]
        coverage=[dict(r) for r in c.execute('SELECT * FROM prior_coverage_comparison')]
    ck('nine_cells_per_fold_including_empty',all(sum(r['fold_id']==f['fold_id'] and r['model_id']=='M2_ma_volume_hierarchical' for r in fitted)==9 for f in folds))
    ck('loss_of_10_previous_dates_explained',sum(r['old_ma_only_dates'] for r in coverage)==308 and sum(r['joint_dates'] for r in coverage)==298 and sum(r['lost_dates'] for r in coverage)==10)
    allmetric={r['model_id']:r for r in metrics if r['subset']=='all_overlapping'}
    fixedmetric={r['model_id']:r for r in metrics if r['subset']=='fixed_every_fifth_anchor'}
    primary=next(r for r in comparison if r['fold_id']=='POOLED' and r['subset']=='all_overlapping' and r['alternative']=='M2_ma_volume_hierarchical' and r['baseline']=='M1_ma_group_shrinkage')
    ck('current_candidate_negative_result_retained',primary['brier_delta']>0 and primary['logloss_delta']>0 and primary['promotion_approved']==0)
    oldstate=read(ROOT/'outputs/初始化与验证推进_20261026/本轮状态与续作断点.json')
    ck('previous_negative_result_retained',oldstate['validation']['M1_upgrade_supported'] is False)
    for src,name in [(ROOT/'work/incremental_independent_audit_oct26/独立复核','独立模型复核'),(ROOT/'work/volume_feature_audit_oct26/独立量价特征核查','独立量价特征核查')]:
        for ext in ['.json','.md']:shutil.copy2(src.with_suffix(ext),OUT/(name+ext))
    for src,name in [(WORK/'registration_receipt.json','预登记凭证.json'),(ROOT/'work/incremental_design_oct26/量价增量预登记设计建议.md','冻结前设计说明.md'),(ROOT/'work/incremental_design_oct26/冻结前实现符合性审查.md','冻结前实现审查.md')]:shutil.copy2(src,OUT/name)
    experiment=read(WORK/'cumulative_experiment_registration.json')
    ck('cumulative_experiments_not_reset',experiment['cumulative_variants']==15 and [r['variants'] for r in experiment['entries']]==[12,2,1])
    experiment['entries'][-1]['outcome']='No incremental improvement on matched development dates; do not promote or retune'
    experiment['entries'][-1]['result_reference']='outputs/量价增量验证_20261026/同日模型对照.csv'
    experiment['entries'][-1]['primary_brier_delta']=primary['brier_delta']
    (OUT/'累计研究试验台账.json').write_text(enc(experiment))
    state=dict(client_date='2026-10-26',project_step='5: incremental signal development; step 6 framework exists but predictive acceptance unpassed',market_data_last_date='2026-10-21',new_market_collection=False,experiment_id=receipt['experiment_id'],models=list(allmetric),new_model_variants=1,cumulative_registered_variants=15,folds=6,scoring_dates=298,prediction_rows=894,fixed_grid_dates=59,previous_scoring_dates=308,coverage_loss=10,brier={m:r['brier'] for m,r in allmetric.items()},primary_brier_delta_M2_minus_M1=primary['brier_delta'],increment_supported_this_run=False,model_promoted=False,current_forecast_generated=False,outcomes_2025_2026_opened=False,probability_recalibration_fitted=False,runtime_usable=False,model_input_approved=False,old_forecast_protocol_or_risk_modified=False,protected_source_sha256=sources,
      next_checkpoint=['Keep M1 and M2 negative development results and all 15 cumulative variants; no retrospective threshold, group or lambda search',
      'Next audit existing broad-market price history, industry membership and event timing for strictly prior observable market-context inputs; no new model scoring before a separate narrow protocol is frozen',
      'Compare any future candidate against matched simple baselines; report sparse cells and coverage cost, not only pooled scores',
      'Only consider opening later-period outcomes after development-candidate review and independent checks with a separately frozen phase protocol; never certify previously viewed periods untouched',
      'Keep chip estimates conditional and isolated; prioritize turnover definition and historical information time instead of assuming small unknown initial mass proves reliability',
      'Market/state/fees/information-time gaps remain; no current trade probabilities or real-money readiness claim'])
    (OUT/'本轮状态与续作断点.json').write_text(enc(state))
    fold_lines=[]
    for f in folds:
        delta=next(r['brier_delta'] for r in comparison if r['fold_id']==f['fold_id'] and r['subset']=='all_overlapping' and r['alternative']=='M2_ma_volume_hierarchical' and r['baseline']=='M1_ma_group_shrinkage')
        fold_lines.append(f"| {f['fold_id']} | {f['train_used']} | {f['evaluated_dates']} | {delta:+.6f} |")
    model_lines=[]
    labels={'M0_laplace_constant':'M0 历史频率基准','M1_ma_group_shrinkage':'M1 均线分组','M2_ma_volume_hierarchical':'M2 均线＋量价九格'}
    for m,r in allmetric.items():model_lines.append(f"| {labels[m]} | {r['brier']:.6f} | {r['log_loss']:.6f} | {fixedmetric[m]['brier']:.6f} |")
    sparse=sum(r['group_n_lt_20'] for r in fitted if r['model_id']=='M2_ma_volume_hierarchical')
    empty=sum(r['prior_only'] for r in fitted if r['model_id']=='M2_ma_volume_hierarchical')
    report=f'''# 量价增量研究：本轮进展与结论

2026年10月26日，多伦多。按八步计划推进第5步，完成一个新增量价候选的预登记、六折时间验证、独立复算和结果保存。**本轮这套“均线＋放量方向”组合没有提供预测改善证据，暂不升级。**

沿用截至2026-10-21的既有行情快照；没有新增市场数据。只评分2023—2024已探索开发期，不打开2025/2026后续结果，不把历史价格变化当作可成交收益或当前买卖建议。

## 本轮研究的问题

在已经研究的均线上行、下行、其他三种状态中，再区分“放量收涨、放量收跌、其他”，能否提高五个观察日价格方向的概率预测？只新增M2一个候选，两个对照按共同训练日期重新拟合。

量价状态继承既有定义：当日成交量严格大于同一价格段此前20日均量的1.5倍，均量不含当日；配合当日收盘相对前收的方向。平收或未达到放量条件归其他；输入不足保留空值。信号在当日收盘后才完整可计算，不能用于当日盘中时点。

事件固定为下一观察日开盘到第5观察日收盘价格变化>0。零变化计入非正并单列，不能把1−上涨概率直接叫作严格下跌概率；本轮也不是买入、卖出动作的净盈利概率。

## 预先固定的三个模型

M0：p0=(正变化数+1)/(训练数+2)。M1：MA父组以固定20向p0收缩。M2：MA×量价形成九格，以固定20向对应MA父组概率收缩。空父组回到p0，空子格回到父组；全部记录样本数、正例数和回退标志。父组含子组数据，这是固定经验平滑，不是独立先验的贝叶斯后验或置信区间。

每折三个模型使用完全相同的训练及评分日期。训练标签结束日严格早于验证开始，验证标签结束日不跨折末；参数整季不变。没有重新选择阈值、分组、收缩强度或最有利的抽样相位。原来的失败结果仍在原目录。

## 实际评分

共298个共同评分日期、894条概率记录，正变化132日、零变化4日、负变化162日。固定原始锚点每五日取一次的敏感性样本59日。五日窗口有重叠；这些数字不能当成独立试验数量。

误差越低越好；Brier不是收益率，也不是准确率。

|模型|Brier|自然对数损失|固定间隔样本Brier|
|---|---:|---:|---:|
{chr(10).join(model_lines)}

主要比较M2−M1的Brier差为{primary['brier_delta']:+.6f}，对数损失差为{primary['logloss_delta']:+.6f}，均为误差增加。相对常数基准也没有改善。固定间隔样本没有扭转这一结果。本轮没有采用显著性或置信区间论证，因此不推断所有量价特征都无效，也不根据个别季度认定有效。

|验证季度|共同训练数|评分日期|M2−M1 Brier差|
|---|---:|---:|---:|
{chr(10).join(fold_lines)}

每折九格全部保存，共54个子格；其中{sparse}个训练子格少于20行，{empty}个为空。20只是稀疏展示标记，超过20也不认证可靠。未按结果合并、丢弃或排名格子。

## 缺值与公平比较的代价

上一轮MA-only有308个评分日期，本轮共同掩码剩298个。减少10日，均来自两次已知除权后的成交量20日预热，比均线预热多等待5日；全部日期及原因另表保存。M0/M1的训练集合也相应变化，因此本表分数只能在本轮同日比较，不能直接与上轮分数相减宣称改善或恶化。

独立量价核查在484个开发日期中重建均线及量价信号：MA可计算454日，量价444日；用精确有理数独立验证了前20日分母、除权重置、严格阈值、零变动、NULL和前缀时间依赖。这里只认证保存快照上的公式一致，不认证数据商正式单位、历史首次可得、ST/停复牌、涨跌停、费用或成交。

## 八步计划的位置

|步骤|目的|目前成效与下一门槛|
|---|---|---|
|1 目标与风险规则|把等待、仓位及退出纪律变成可核对标准|用户原则及测试暂停线已记录；真实使用细则未验收|
|2 数据库|保留行情、公告、筹码与事件的证据|基础已建；行情截止10/21，原生筹码完整价档等缺口保留|
|3 清洗与追溯|避免单位、版本和未来信息混入|已建立核对与隔离；历史可得时间仍需补证|
|4 指标与筹码特征|把观察转成可重建输入|量价特征独立复算；筹码v2保留未知初始边界，未获预测准入|
|5 单信号与组合研究|检验是否真的有增量信息|本轮完成M2；M1、M2均未取得升级依据|
|6 校准与后期评估|判断概率能否跨时间使用|时间验证和评分框架已搭好；尚未通过预测能力验收|
|7 日常工具与模拟|展示可解释概率、风险和弃答|待研究验收后推进，不能用工程检查代替预测验收|
|8 条件性小额试验|评估实际使用及纪律|仍是后续意向，未进入真实资金阶段|

## 下一步

保留本轮否定结果，不继续在这套九格上反复调参。下一次先审核已存大盘价格、行业成员及事件时间，确定哪些市场环境变量能在信号当时使用；经过有限、另行登记的设计后才考虑新候选。数据新增不能自动成为预测输入。后期年份须等候选审查和下一阶段协议固定后再使用。

累计登记保留先前12个描述信号、2个模型及本轮1个新增模型，共15个研究变体；重复对照、九格、六折不冒充独立新试验，也不重置失败记录。当前尚没有经过可靠性验收的买入或卖出预测卡。

## 文件与验证

- [同日模型对照]({OUT/'同日模型对照.csv'})；[逐日配对误差差]({OUT/'逐日配对误差差.csv'})；[全部九格]({OUT/'逐折模型与全部九格.csv'})。
- [预登记协议]({OUT/'预登记研究协议.json'})；[登记凭证]({OUT/'预登记凭证.json'})；[累计研究台账]({OUT/'累计研究试验台账.json'})。
- [独立模型复核]({OUT/'独立模型复核.md'})；[独立量价核查]({OUT/'独立量价特征核查.md'})；[完整重跑核验]({OUT/'完整重跑核验.json'})。
- [续作断点]({OUT/'本轮状态与续作断点.json'})；[复算说明]({OUT/'复算与文件说明.md'})。

实现28项、独立模型复核{independent['passed']}项、独立特征核查30项通过，15个核心产物完整进程重跑字节一致，13份受保护源文件指纹未变。这些是技术正确性证据，不能证明预测有效。旧原始数据、草案、风险配置和历史产物保留。

完整备份目录：`/Users/puchun/Documents/Codex/项目归档/ni/20261026_量价增量验证完整保存/`；完成与恢复校验以该目录归档校验结果.json为准。
'''
    (OUT/'本轮推进报告.md').write_text(report)
    (OUT/'复算与文件说明.md').write_text(f'''# 复算与文件说明

项目根目录：{ROOT}

在恢复出的项目目录，使用带Python标准库的Python3运行 work/incremental_validation_oct26/run_incremental.py。源码按所在位置发现项目根，相对路径读取既有输入，先核对冻结合同、源码及13份来源指纹；存在任何改动时拒绝运行。无需网络、第三方Python包或券商账户。冻结登记已有receipt，不能再次运行register.py覆盖。

生产脚本只读取2023—2024开发标签。独立审计脚本在work/incremental_independent_audit_oct26；特征精确重建在work/volume_feature_audit_oct26/audit_features.py。冻结前设计、审查、登记与原累计登记均在work内，最后台账另存outputs，不回写登记。

量价增量开发验证.sqlite中predictions为894条概率与实际结果；fitted为6折×(1常数+3父组+9子格)；membership是每折共同训练成员；ledger逐项记录训练使用/剔除与验证弃答；metrics/comparisons/calibration/paired_loss是固定评分与配对明细，prior_coverage_comparison/lost_prior_scoring_dates解释覆盖减少。多折重复使用已成熟训练数据不等于新增独立观察。

CSV使用UTF-8 BOM；空值为留空，不补0。固定概率分箱诊断没有拟合校准函数。源码中的合成与变异核验不会另选市场参数；报告和归档由独立收尾脚本生成。全套研究均不提供当前买卖预测或真实交易权限。
''')
    missing=[]
    for p in OUT.glob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if target.startswith('/') and not Path(target).exists():missing.append([str(p),target])
    ck('all_local_report_links_resolve',not missing,missing)
    validation=dict(client_date='2026-10-26',all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_sha256=sources,current_forecast_generated=False,runtime_usable=False)
    (OUT/'本轮交付核验.json').write_text(enc(validation))
    progress=ROOT/'outputs/项目进度与交易需求档案.md';backup=WORK/'进度档案_本轮前.md'
    if not backup.exists():shutil.copy2(progress,backup)
    text=progress.read_text();old=next(s for s in text.splitlines() if s.startswith('更新日期：'))
    text=text.replace(old,'更新日期：2026年10月26日。阶段：完成第5步首个量价增量候选的同日验证；298评分日期，新增组合未优于匹配基准。尚未通过预测能力验收，继续保留第6步后期结果边界。',1)
    entry='\n- 2026/10/26量价增量：按“继续按照计划往下进行”，完成[单一量价增量候选验证](./量价增量验证_20261026/本轮推进报告.md)。先冻结合同和源码指纹，再用MA×量价九格层级收缩与共同日期M0/M1比较；298评分日期、894概率，M0/M1/M2 Brier为0.247769/0.251374/0.253401，未支持升级。较上一轮少10个日期，除权后量能预热原因已对账；累计15变体不重置。独立特征、模型复核及完整重跑通过，旧来源与风险口径未改，2025/2026结果未打开。续作先审查市场环境输入，不在当前九格上事后调参。\n'
    if '2026/10/26量价增量：' not in text:text=text.replace('## 本轮补充确认与记账口径\n','## 本轮补充确认与记账口径\n'+entry,1)
    start=text.index('## 下次协作的起点');end=text.index('## 2026-10-22 五项补缺收尾',start)
    text=text[:start]+'''## 下次协作的起点

以[10/26量价增量验证续作断点](./量价增量验证_20261026/本轮状态与续作断点.json)为当前入口。M1与M2在开发期均未获升级依据，先保留结果，下一次审查大盘价格、行业成员与事件时间的可得性及定义，再决定有限的新候选。后期结果须经另行协议固定后使用，不在本轮自动开封2025/2026。筹码原生完整价档和换手/历史可得性等缺口仍在；自建估计不自动获准入。当前无可靠性验收通过的买卖概率卡，也未进入真实资金阶段。

旧10/16起点已被后续工程与开发期研究推进取代，修改前文字留存在本轮work备份和历史完整归档。

'''+text[end:]
    progress.write_text(text)
    print(enc(dict(report=str(OUT/'本轮推进报告.md'),release_checks=len(checks),sources_unchanged=True,core_files_identical=len(core))))
if __name__=='__main__':main()
