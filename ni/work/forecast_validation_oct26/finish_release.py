"""Cross-track release entry point, provenance checks and resumable checkpoint."""
from pathlib import Path
import csv,hashlib,json,math,re,shutil,sqlite3,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/初始化与验证推进_20261026'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def csvread(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def main():
    time=OUT/'时间验证';chip=OUT/'筹码初始化';checks=[]
    def check(name,passed,details=None):checks.append(dict(check=name,passed=bool(passed),details=details));assert passed,name
    fit=read(time/'验证结果.json');fitreview=read(ROOT/'work/validation_protocol_oct26/独立复核.json')
    init=read(chip/'验证结果.json');initreview=read(ROOT/'work/continuation_audit_oct26/新筹码独立复核.json')
    initaudit=read(chip/'独立本地核验与完整重跑.json')
    check('time_production_24_checks',fit['all_checks_passed'] and fit['passed']==fit['total']==24)
    check('time_independent_20_checks',fitreview['all_checks_passed'] and fitreview['passed']==fitreview['total']==20)
    check('time_audit_matches_final_code_and_contract',fitreview['producer_code_sha256']==sha(ROOT/'work/forecast_validation_oct26/run_validation.py') and fitreview['contract_sha256']==sha(ROOT/'work/forecast_validation_oct26/contract.json'))
    check('initialization_20_implementation_checks',init['all_technical_checks_passed'] and len(init['checks'])==20 and all(r['passed'] for r in init['checks']))
    check('initialization_19_independent_checks',initreview['passed']==initreview['total']==19 and not initreview['failed'])
    check('initialization_full_rerun_audit_passes',initaudit['all_checks_passed'])
    for a,b in [(ROOT/'work/validation_protocol_oct26/独立复核',time/'独立来源复核'),(ROOT/'work/continuation_audit_oct26/新筹码独立复核',chip/'独立来源复核')]:
        for suffix in ['.json','.md']:shutil.copy2(a.with_suffix(suffix),b.with_suffix(suffix))
    # A fresh process reconstructs every core validation output; no new model choice.
    core=[p for p in time.iterdir() if p.is_file() and p.name not in ['独立来源复核.json','独立来源复核.md','重跑产物核验.json']]
    before={p.name:sha(p) for p in core}
    subprocess.run([sys.executable,str(ROOT/'work/forecast_validation_oct26/run_validation.py')],check=True,capture_output=True,text=True)
    after={p.name:sha(p) for p in core}
    check('all_time_core_files_byte_identical_on_full_process_rerun',before==after,{'files':len(core)})
    (time/'重跑产物核验.json').write_text(enc({'all_core_files_byte_identical':before==after,'core_file_count':len(core),'file_sha256':after}))
    sources=read(time/'运行与输入合同.json')['source_sha256']
    check('seven_protected_inputs_unchanged',len(sources)==7 and all(sha(ROOT/p)==h for p,h in sources.items()),sources)
    with ro(time/'开发期滚动验证.sqlite') as c:
        check('validation_sqlite_quick_check',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
        check('616_rows_308_dates_and_no_2025_2026_outcomes',tuple(c.execute("SELECT COUNT(*),COUNT(DISTINCT signal_date),MAX(outcome_observation_date) FROM predictions").fetchone())==(616,308,'2024-12-31'))
        check('all_prediction_release_flags_closed',c.execute('SELECT COUNT(*) FROM predictions WHERE historical_model_input_approved!=0 OR runtime_usable!=0').fetchone()[0]==0)
    summaries=read(chip/'固定日期结果.json')['results']
    check('36_partial_distributions_not_native_bins',len(summaries)==36 and all(not r['summary']['model_input_approved'] and not r['summary']['native_supplier_bins_acquired'] for r in summaries))
    check('unknown_mass_not_silently_zeroed',all(0<r['summary']['unknown_initial_mass']<1 for r in summaries))
    check('known_plus_unknown_mass_conserved',all(abs(sum(r['observed_mass'])+r['summary']['unknown_initial_mass']-1)<1e-12 for r in summaries))
    with ro(chip/'初始化改进v2.sqlite') as c:check('initialization_sqlite_quick_check',c.execute('PRAGMA quick_check').fetchone()[0]=='ok')
    base={r['summary']['asof_date']:r['summary'] for r in summaries if r['params']['turnover_multiplier']==1}
    stress={r['summary']['asof_date']:r['summary'] for r in summaries if r['params']['turnover_multiplier']==.5}
    comparisons=csvread(time/'与常数基准对照.csv')
    pooled=next(r for r in comparisons if r['fold_id']=='POOLED' and r['subset']=='all_overlapping')
    check('negative_development_result_retained',float(pooled['brier_delta_M1_minus_M0'])>0 and float(pooled['logloss_delta_M1_minus_M0'])>0)
    state={'client_date':'2026-10-26','market_data_last_date':'2026-10-21','new_market_collection':False,
      'initialization':{'version':'common_origin_partial_identification_v2','origin':'2022-06-01','fixed_dates':12,'stress_multipliers':[.5,1,1.5],'stored_runs':36,'stored_daily_diagnostics':3192,'research_diagnostic_rows':2754,'native_supplier_bins_acquired':False,'prediction_reliability_certified':False,'unknown_mass_explicit':True},
      'validation':{'status':'frozen_research_only_development_diagnostic','models':['M0_laplace_constant','M1_ma_group_shrinkage'],'folds':6,'evaluated_dates':308,'prediction_rows':616,'fixed_grid_dates':61,'brier_M0':float(pooled['brier_M0']),'brier_M1':float(pooled['brier_M1']),'M1_upgrade_supported':False,'current_forecast_generated':False,'2025_2026_outcomes_generated':False},
      'protected_source_sha256':sources,'old_forecast_protocol_or_risk_modified':False,'runtime_usable':False,
      'next_checkpoint':['Keep the current two-model development result; no lambda or group re-optimization on this run','Register a narrow next candidate using incremental price/volume information and test against the same eligible dates','Continue to treat estimated chip features as conditional diagnostics until turnover and information-time limitations are resolved','Keep 2025 calibration and 2026 evaluation candidate outcomes unopened by this pipeline until the research design and checks for that phase are frozen']}
    (OUT/'本轮状态与续作断点.json').write_text(enc(state))
    report=f'''# 初始化与首版时间验证推进

2026年10月26日，多伦多。从10月25日保存断点继续，完成筹码初始化v2和首轮按时间推进的概率对照。本轮沿用截至10月21日的行情快照，没有刷新市场数据或开通付费数据。

## 结果与意义

|工作|已完成|实际结论|
|---|---|---|
|筹码初始化|固定2022-06-01共同起点，已观察贡献和未知初始质量分别递推；12日×3换手压力，36组价档、3192条日诊断|不再每120日重置，也不把未知初始筹码随意设成一个确定分布；能量化初始条件的影响边界|
|预测验证|固定5观察日价格正变化事件，6个季度按时间训练和验证；2个预登记简单模型、308个评分日期|已跑通“只用过去成熟结果训练，再评价后续概率”的流程；本轮均线模型没有优于常数基准|

## 筹码初始化现在怎样处理

未知初始质量U保留独立记录；已观察日线量价在假设模型中产生的贡献Q保持质量1−U，不把Q归一后冒充全部筹码。总体CDF和获利质量给上下界，均值在不限制未知初始价位时不虚构有限范围；已观察部分的条件均值另列。

|日期|基准倍率1的未知质量|倍率0.5压力下未知质量|
|---|---:|---:|
|2023-01-03|{base['2023-01-03']['unknown_initial_mass']*100:.6f}%|{stress['2023-01-03']['unknown_initial_mass']*100:.6f}%|
|2023-06-19|{base['2023-06-19']['unknown_initial_mass']*100:.6f}%|{stress['2023-06-19']['unknown_initial_mass']*100:.6f}%|
|2026-10-21|{base['2026-10-21']['unknown_initial_mass']*100:.9f}%|{stress['2026-10-21']['unknown_initial_mass']*100:.6f}%|

这些百分比是既定换手衰减假设下的初始影响，不是真实筹码误差，也不是上涨概率。较小U不能消除换手分母、持有人换仓机制、日内分配、遗漏分派及历史信息当时可用的问题。供应商原生完整价档仍未取得；新估计不填入原生采集覆盖。

## 首轮概率对照的真实结果

固定事件是“下一观察日开盘到第5观察日收盘，价格变化是否>0”，零变化归非正、另计零值。它不等于净盈利，也不等于卖出或买入动作的成功概率。旧首版协议和风险口径没有被改写；本轮冻结的是助手的研究协议。

M0只用过去训练期的平滑正变化频率；M1按上一轮已有的均线上行/下行/其他三组，向M0收缩，强度固定20。每折模型冻结一季，训练标签结束日严格早于验证开始，验证结果不能跨出该折末日。两个模型使用同一可计算日期，不通过缺值填0扩大覆盖。

|模型|Brier预测误差，越低越好|
|---|---:|
|M0 常数基准|{float(pooled['brier_M0']):.6f}|
|M1 均线分组收缩|{float(pooled['brier_M1']):.6f}|

M1的Brier和对数损失均略高，当前没有升级依据。本轮保留这个否定结果，没有事后换组、优化收缩强度或另挑最好的时间相位。308个评分日期的5日窗口有重叠；固定每5锚点取一次只有61个评分日期，仍不能认定独立。该开发期此前已经看过描述统计，时间分割正确也不使它变成从未观察的最终测试。

2025/2026未来价格结果本轮仍未生成或评分，保留为后续校准/评估候选，不能追认从未被观察。未拟合校准变换，没有当前买卖预测卡、净收益回测或真实资金操作。ST/停牌、信息时间和费用等缺口继续保留。

## 交付与复核

- [筹码初始化v2报告]({chip/'筹码初始化改进v2报告.md'})；[原始诊断和参数]({chip/'来源与参数.json'})；[独立数值复核]({chip/'独立来源复核.md'})。
- [首版时间验证报告]({time/'首版时间验证报告.md'})；[研究协议v1]({time/'研究验证协议_v1.json'})；[逐折覆盖]({time/'时间分折与覆盖.csv'})；[独立概率复核]({time/'独立来源复核.md'})。
- [本轮状态和续作断点]({OUT/'本轮状态与续作断点.json'})。

筹码实现20项、独立数值重建19项通过；时间验证实现24项、独立复核20项通过。检查覆盖有重叠，检查次数不能用来证明市场预测有效。旧原件、旧源码、旧协议和既有模型/风险配置保留。

下次从这里继续：保持这次均线模型结果，预登记一组范围有限的新增量价候选，用同一可评分日期检验增量信息；筹码继续作为带边界的独立专项，不因初始化残量变小就自动进入预测输入。后续任何新模型试验继续累计登记，保留2025/2026结果边界。

完整本地备份位置：`/Users/puchun/Documents/Codex/项目归档/ni/20261026_初始化与验证完整保存/`。是否完成、文件数与恢复检查以该目录的`归档校验结果.json`为准。
'''
    (OUT/'本轮推进报告.md').write_text(report)
    missing=[]
    for f in OUT.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',f.read_text()):
            if target.startswith('/') and not Path(target).is_file():missing.append([str(f.relative_to(OUT)),target])
    check('all_absolute_report_links_resolve',not missing,missing)
    validation={'client_date':'2026-10-26','all_checks_passed':all(r['passed'] for r in checks),'passed':len(checks),'total':len(checks),'checks':checks,
      'source_sha256':sources,'native_chip_bins_acquired':False,'current_forecast_generated':False,'runtime_usable':False}
    (OUT/'本轮交付核验.json').write_text(enc(validation))
    with (OUT/'本轮核验汇总.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['check','passed']);w.writeheader();w.writerows({k:r[k] for k in ['check','passed']} for r in checks)
    progress=ROOT/'outputs/项目进度与交易需求档案.md';txt=progress.read_text()
    old=next(r for r in txt.splitlines() if r.startswith('更新日期：'))
    txt=txt.replace(old,'更新日期：2026年10月26日。阶段：自建筹码初始化v2和首轮开发期按时间概率对照已完成。均线分组模型本轮未优于常数基准；正式预测使用门仍关闭，未生成当前买卖预测。',1)
    entry='\n- 2026/10/26继续断点：完成[初始化与验证推进](./初始化与验证推进_20261026/本轮推进报告.md)。自建筹码改用2022-06-01共同起点，分开追踪未知初始质量；36组样本、3192日诊断，原生价档覆盖仍0。冻结研究-only的5观察日事件、M0/M1两模型及6季度折，2023—2024产生308评分日期/616记录；M1 Brier0.250382略高于M0的0.247384，保留否定结果，不调lambda或改组挑赢家。2025/2026结果本轮未生成。实现/独立复核及源hash检查通过，旧协议/原库/风险设置均未改。本轮沿用截至10/21行情。续作断点保存在本轮状态JSON。\n'
    if '2026/10/26继续断点' not in txt:txt=txt.replace('## 本轮补充确认与记账口径\n','## 本轮补充确认与记账口径\n'+entry)
    progress.write_text(txt)
    print(enc({'report':str(OUT/'本轮推进报告.md'),'checks_passed':len(checks),'source_unchanged':True,'time_core_files_identical':len(core)}))

if __name__=='__main__':main()
