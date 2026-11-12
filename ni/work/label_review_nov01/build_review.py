"""Build the second bounded design review; no market target database is queried."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/预测问题与标签适用性审查_20261101'
ARCHIVE=Path('/Users/puchun/Documents/Codex/项目归档/ni/20261101_预测问题审查完整保存')
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,obj):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 cfg=read(WORK/'review_contract.json');math=read(ROOT/'work/label_math_nov01/设计审查.json');timing=read(ROOT/'work/label_timing_nov01/来源与设计审查.json')
 checks=[]
 def ck(name,ok,details=None):
  checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
 ck('independent_math_design_review_26_passed',math['all_checks_passed'] and math['passed']==math['total']==26)
 ck('independent_timing_review_22_passed',timing['all_checks_passed'] and timing['passed']==timing['total']==22)
 previous=read(ROOT/'outputs/研究证据与覆盖审查_20261101/本轮交付核验.json')
 sources=dict(previous['protected_source_sha256'])
 # Global progress/pointer are mutable collaboration records; keep their prior
 # snapshots, but protect only immutable research artifacts and old code here.
 for path,h in previous['delivery_sha256'].items():
  if path.startswith('outputs/研究证据与覆盖审查_20261101/') or path.startswith('work/evidence_review_nov01/'):sources[path]=h
 for data,key in [(math,'read_source_sha256'),(timing,'source_sha256_before')]:sources.update(data[key])
 extra=['outputs/概率预测引擎详细方案_20261016.md','outputs/信号组合条件概率研究规格_v0.2.md','outputs/五项数据补缺_20261022/历史交易条件核对.md','outputs/研究证据与覆盖审查_20261101/本轮交付核验.json']
 for p in extra:sources[p]=sha(ROOT/p)
 ck('all_immutable_previous_sources_match',all(sha(ROOT/p)==h for p,h in sources.items()))
 write(OUT/'旧来源保护清单.json',dict(scope='Prior raw databases, contracts, results, evidence release and selected official originals; no source content mutated',sha256=sources))
 confirmation=dict(client_date='2026-11-01',user_original_answer=cfg['user_confirmed']['first_use_case'],source='本聊天用户明确选择',confirmed=['首版优先收盘后判断回落时该买入还是继续等待'],research_starting_cash_condition='本审查的示例设计范围，不代表用户实际空仓或已确认仓位分配',not_confirmed=list(cfg['pending_freeze']),not_a_real_funds_or_order_authorization=True,old_draft_preserved=True)
 write(OUT/'本次用户确认与待定参数.json',confirmation)
 write(OUT/'审查范围与设计合同.json',cfg)
 events=[
  dict(id='L00',name='既有五观察日原价标签',status='old_engineering_definition_unchanged',formula='C[t+5]/O[t+1]-1',positive='>0',zero='=0',negative='<0',binary_zero_group='nonpositive',clock='observed_stock_bars',can_answer='该原价窗口正、零、负的开发诊断',cannot_answer=['实际成交收益','等待优于直接买入','期间风险','已校准当前买卖概率']),
  dict(id='L01',name='下一允许窗口买入的费用后结果',status='design_only_not_generated',formula='(W_now(T)-B)/B',requires=['相同t0初始状态','已冻结分配、执行和费用','有效共同T','权益及税务口径','NAV或清算口径明确'],positive_event='W_now(T)>B; 不同于原价上涨',unknown_if=['费用未知','成交未知','终点口径未明']),
  dict(id='L02',name='预定确认后等待方案结果',status='design_only_not_generated',formula='(W_wait(T)-B)/B',requires=['t0前固定回落与确认定义','最大等待及末次确认/入场','逐时实际可得信息','共同T不随等待改变'],no_confirmation='显式持币路径，不伪造交易收益0',unknown_if=['事后选择最低点','确认时使用尚未可得信息','假定同确认收盘成交']),
  dict(id='L03',name='等待相对立即买入的财富优势',status='proposed_primary_target_not_generated',formula='Delta_W=W_wait(T)-W_now(T)',definition_only_event='Delta_W>0; ties separately recorded',material_advantage_threshold=None,requires=['同一B和t0信息','同一预定分配规则与共同T','同一财富及现金利息口径','两条执行路径有依据或明确限为假设'],probability_condition='仅t0已知信息；未来确认过程是策略路径，不是t0输入',causal_identification_from_daily_bars=False),
  dict(id='L04',name='纯持币参考',status='design_only_not_generated',formula='cash_B(T) under explicitly declared cash-return assumptions',trade_return=None,remarks='零利息只是合成假设；未成交不代表存在零收益交易，订单费用/部分成交另记'),
  dict(id='L05',name='费用后盈利、持平、亏损',status='design_only_not_generated',events=['W(T)>B','W(T)=B','W(T)<B'],economic_neutral_band=None,remarks='有可评估结果时三类互斥完备；不可评估和未成熟不进入零类'),
  dict(id='L06',name='未来幅度分布与不确定性',status='design_only_not_estimated',outputs=['费用后结果分位数','期望净结果','Delta_W分布','估计不确定性'],remarks='未来结果区间与估计误差区间不同；历史10%/90%分位数不自动获得未来覆盖保证'),
  dict(id='L07',name='持有期间风险',status='design_only_not_generated',outputs=['入场后价格最大不利变化','资金曲线回撤','跳空/不能退出风险','资金占用'],remarks='价格MAE、账户回撤、已实现亏损分别定义；两策略在共同T比较财富，同时报告实际入场后风险及空仓暴露差异'),
  dict(id='L08',name='先触及风险线或目标线',status='design_only_not_generated',barriers=None,same_daily_bar_both_touched='ORDER_UNKNOWN，不默认有利顺序',touch_equals_fill=False,remarks='需检查可卖数量、订单及实际成交；开盘跳空可能越线，不能以线价保证退出'),
  dict(id='L09',name='终点估值与实际变现',status='design_only_not_generated',NAV='cash_T+q_T*validated_mark_T+validated_rights_receivables_T-unpaid_tax_fee_and_other_liabilities_T',cash='实际卖出成交后现金及其他明确现金流',remarks='cash已扣已付费用；已到账股息不重复计应收，未知税费负债不填0。未成交退出可有有效NAV，清算结果仍不可评估；不顺延共同T隐藏失败'),
  dict(id='L10',name='持有与卖出后持币',status='later_separate_question_not_this_primary_scope',formula='W_sell_to_cash(T)-W_hold(T)',requires=['已有持仓及可卖数量','同一当前净资产','同终点和未来增量费用/权益'],remarks='历史买价及已实现亏损账本保留，但两动作的未来增量比较不重复扣历史沉没费用；不等于1-买入上涨概率'),
  dict(id='L11',name='盘中做T',status='deferred_not_identifiable_from_current_daily_inputs',requires=['分钟/更细数据及可得时戳','底仓可卖批次与资金','盘中信号与执行协议'],remarks='日K高低/收盘后筹码不能证明盘中时点；没有盘中预测能力承诺')]
 write(OUT/'预测事件字典_v1.json',dict(status='design_review_not_frozen_for_market_labels',user_first_use_case_confirmed=True,events=events,pending_freeze=cfg['pending_freeze'],new_real_labels_generated=False))
 axes=dict(data=['AVAILABLE_WITH_VERSION_AND_TIME','MISSING','SOURCE_CONFLICT','FIRST_AVAILABILITY_UNKNOWN'],policy=['ELIGIBLE','NO_PULLBACK','WAITING_NO_CONFIRMATION','CONFIRMATION_EXPIRED','RISK_BLOCKED'],execution=['NO_ORDER','KNOWN_UNFILLED','PARTIAL_FILL','FILLED','FILL_UNKNOWN','SELLABILITY_BLOCKED'],maturity=['NOT_MATURE','MATURE','UNRESOLVED'],terminal=['VALID_NAV_NOT_REALIZED','VERIFIED_LIQUIDATION_CASH','LIQUIDATION_UNFILLED','TERMINAL_MARK_MISSING'])
 write(OUT/'状态与资格字典.json',dict(status='design_not_runtime',independent_axes=axes,missing_or_unfilled_trade_return=None,unknown_is_not_zero=True,partially_filled='按实际数量、剩余现金与适用费用核算，未成交部分不能假作满额',future_training_policy='须事先登记每类状态的目标资格和分母；无触发/未成交可进入有定义的策略财富路径，交易收益子集另报；未知不得静默剔除或填零',formal_model_input_approved=False,runtime_usable=False))
 ck('12_event_definitions_have_unique_IDs_and_unfrozen_status',len(events)==12 and len({e['id'] for e in events})==12 and all(v is None for v in cfg['pending_freeze'].values()))
 copies=[(ROOT/'work/label_math_nov01/设计审查.json','数学设计独立审查.json'),(ROOT/'work/label_math_nov01/设计审查.md','数学设计独立审查.md'),(ROOT/'work/label_timing_nov01/来源与设计审查.json','时间制度来源独立审查.json'),(ROOT/'work/label_timing_nov01/来源与设计审查.md','时间制度来源独立审查.md')]
 for source,name in copies:shutil.copy2(source,OUT/name)
 ck('independent_design_reports_copied_unchanged',all(sha(source)==sha(OUT/name) for source,name in copies))
 source_records=dict(public_sources=timing['public_sources'],new_web_observation_sha256=timing['new_web_observation_sha256'],root_web_response=dict(path='work/label_review_nov01/官方网页核查原响应.json',sha256=sha(WORK/'官方网页核查原响应.json'),retrieval_date_client='2026-11-01',kind='Fresh tool-parsed observations, not a newly downloaded binary PDF',one_notice_open_failed='An alternate official notice URL timed out; retained in raw response, no bypass or repeated retry'),old_official_source_sha256=timing['source_sha256_before'],rules_not_certified_for_every_historical_date=True)
 write(OUT/'来源与版本索引.json',source_records)
 synth=read(OUT/'合成案例与精确计算.json');sv=read(OUT/'合成案例核验.json')
 ck('21_synthetic_cases_and_23_checks_passed',sv['all_checks_passed'] and sv['passed']==sv['total']==23 and len(synth['cases'])==21 and synth['real_market_observations_used']==0)
 rows=['| 案例 | 说明 |','|---|---|']
 rows += [f"| {r['case_id']} | {r['purpose']} |" for r in synth['cases']]
 (OUT/'合成案例说明.md').write_text('# 全部合成案例\n\n21例的价格、费用、数量和概率全部虚构，只用于核查定义；不是高德红外数据或模型结果，不生成建议仓位。\n\n'+'\n'.join(rows)+'\n\n精确输入与计算值见[合成案例与精确计算](./合成案例与精确计算.json)。算术核验不证明预测或执行有效。\n')
 report=f'''# 预测问题与标签适用性审查 v1

2026年11月1日，多伦多。四份有限审查中的第2份。本轮用户已明确选择：**首版优先“收盘后判断回落时该买入，还是继续等待”。** 这是使用问题的确认，不是预测期限、仓位、费用、信号、资金试验或交易授权。旧草案保留原状，本次确认另存补充记录。

## 审查结论

现有“五个观察日后股价是否上涨”标签适合受限的价格方向开发诊断，不能单独判定买入时机、等待价值、费用后盈利或期间风险。旧16项研究及全部负面结果继续保留；本轮不据此调整旧标签或重跑旧模型。

首版应围绕同一笔可分配资金、同一信息时点、同一个事先固定终点，比较两条预定路径：A在下一允许窗口买入，B等待当时可识别的确认后再在下一允许窗口买入，未等到合格入场则继续持币。另保留纯持币参考。**等待不能被定义为事后买到最低点。**

主比较的定义是 Delta_W=W_wait(T)−W_now(T)。Delta_W>0只表示此口径下等待方案的终点财富更高，不是自动行动阈值、因果效果或已估计概率；金额是否足够有意义、可接受风险及估计证据须另定。两种路径的成交若无法从资料识别，只能保留假设或不可评估，不能用日K证明两种订单都能成交。

本轮完成12项事件定义、五个独立状态维度、时间线、待冻结参数和21个虚构反例；没有生成真实新标签、训练模型、评分或当前预测。审查完成不等于正式预测协议冻结，累计研究变体仍16。

## 旧标签能回答什么

旧公式为 C[t+5]/O[t+1]−1：信号日之后下一条股票观察日的原始开盘，到第5条股票观察日的原始收盘。大于0为正、等于0单列、小于0为负；旧二分类把零与负合并为“非正”。价格源、已知除权窗口排除和开发边界沿旧合同，完全保留。

| 问题 | 旧标签是否足够 | 原因 |
|---|---|---|
|这个原价窗口最后正、零还是负|可做受限的既有开发诊断|不代表当前已校准概率，也不认证历史可得|
|扣费以后是否赚钱|不足|微涨可能不足以覆盖佣金、最低收费、税费与滑点|
|等确认是否比直接买好|不足|没有把等待的晚入场、错过、未触发和共同终点定义进去|
|过程中可能先亏多少|不足|终点上涨仍可能经历大幅不利变化和无法退出|
|风险线一定先于目标线触发吗|日K通常不足|同日高低都跨线时先后不明；触线也不保证成交|
|已有持仓应卖吗|不足|持/卖是从相同当前持仓比较未来财富，不能套空仓买入标签|
|盘中做T的买回点|不足|现有日频输入没有盘内顺序、细粒度信号和可卖账本|

“非正概率=1−正概率”不等于严格下跌概率，因为包含零。旧二分类没有单独估计零概率，不能凭补数补造严格下跌概率。以后若定义经济中性带，它也不同于精确零变动；上下边界目前仍未定。

## 首版比较怎样运转

先固定股票、回落资格、资金分配规则和决策时刻t0。回落资格只能由t0已知资料判断，不能事后挑出反弹成功的日期。相同起始现金B不等于实际把账户全部投入；分配金额、股数与仓位限制均待定。

| 路径 | 入场如何决定 | 没有入场时 | 到共同T看什么 |
|---|---|---|---|
|A：下一窗口买入|t0固定的允许窗口、价格/数量/失效规则|未成交或禁止成交独立记录|终点NAV与可卖性，或另行冻结的实际清算现金|
|B：等待确认|预定义确认在当时可见后，下一允许窗口才可行动|未触发、过期或不能入场则保留现金路径|与A同一个T，不能从晚买日重数H天|
|C：纯持币|整个比较期不持有这笔研究仓位|持续现金参考|同一现金收益/费用假设下的财富|

两种策略采用同一事前资金分配规则，数量会随各自执行价、最小单位和费用改变，余额必须进入财富，不能仅比较股价收益率。未来确认信息可供B在未来时点判断，是B的规则路径；它不能倒流成为t0预测输入。日后同时模拟两条路径需明确小额订单不影响市场等假设，不能宣称已经识别个人真实交易的因果效果。

## 时间线和终点

建议正式设计采用t0已知的交易所计划日历确定单一共同期限，H尚未确认。5个计划交易日只是可讨论的例子，不是用户已选期限，也不能因旧模型用过5观察日就继承为产品参数。计划日历本身仍要核验；自然日、计划交易日和股票实际有观察记录的日子分别保存。

| 时点 | 可用信息及动作 |
|---|---|
|d0信息截止与出卡|仅使用截止前实际已可得并核验的字段；收盘后不等于一切日数据都已齐|
|d1或预定下一窗口|A按冻结规则尝试入场；不能把事后实际开盘价作为d0输入|
|d_j确认形成后|B用截至此时的信息确认；若采用次日模式，最早d_(j+1)允许窗口尝试入场|
|最迟允许入场|与最大等待、T、可卖规则和终点口径一起固定；不能靠晚入场后顺延T|
|共同T|分别保存可核验估值、可卖数量、清算是否成交、权益和缺失；不随股票缺一条数据就顺延|
|结果成熟后|真实标签必须等所有必需结果及费用/权益资料可用后才成熟，不能只看名义T日期|

在合成H=5例子中，d4收盘确认、d5买入，不能默认d5已能卖出。若实验要求T前实际清算，该入场可能不合格；若研究终点估值，则单列NAV及不可卖状态，不叫已实现盈利。未清算也不能把终点偷偷改到d6。

## 现行规则核对带来的修正

深交所2026版规则存在A股盘后固定价格通道，15:05—15:30按当日收盘价撮合，盘后量额在结束后并入当日总量。因此不能笼统说收盘后绝无同收盘价成交途径，也不能默认15:00已拥有完整日量。本项目并未认证用户渠道、字段可得或排队成交，首版次一计划窗口只是设计建议。[深交所规则3.6节](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)

规则还区分交收前可否卖出及回转交易例外；普通A股新买数量不能默认当日卖出。做T须核已有可卖批次与账户状态，不能按净持仓就假定可卖。开/收盘记录、日内触价或有成交量都不能证明特定订单成交。2026制度不能回填2023—2024；逐日历史状态、规则链及实际费用仍未全部认证。[深交所规则3.1.4—3.1.5、4.2节](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)

以上是对官方条文和现有资料的适用性审查，不等于用户账户功能核验；实际数据到达可能晚于交易所结束时刻。官方来源、版本、取得时间和原件/新解析响应SHA分别保留；一处通知入口超时已留原响应，没有冒充新下载PDF。完整来源见[来源与版本索引](./来源与版本索引.json)。

## 财富、费用和公司行动

在无公司行动、无现金利息且两端明确成交的简单例子中：W(T)=B−q×买入价−买入费用+q×卖出价−卖出费用。实际应用要按每笔成交、适用日期、最低收费、包费和舍入核算，不能将已含佣金的项目再加一遍；账户佣金、股息税和真实滑点未知时不能填0。

若T只估值：NAV(T)=现金+持股数量×经核验价格+有依据的权益/应收价值−未付税费及其他负债。现金已反映已付费用；已到账股息不能再计一次应收，未知税费/负债不能默认为0。应收现金不自动等于可用现金，不能提前用来再买。估值可算不代表能卖出；如果选择清算现金事件而退出未成交，该事件结果不能偷换成NAV。

转增、配股和分红影响股数、现金/应收及税务。机械除权价格下落不能直接当财富损失；未来前复权快照也不能改写过去决策输入。旧工程合同的已知行动窗排除作为旧研究范围保留，不能直接当成所有t0均已知道的实时过滤器。新动作标签需另定可追溯权益口径；未能核算时记为相应不可评估并披露覆盖，不能事后只保留有利事件。

为隔离入场问题，本审查建议以一笔未投入的独立研究资金比较，不能据此声称你实际账户空仓或已经确认仓位分配。已有持仓下的新增买入/不加仓、持/卖问题需带入当前净资产、可卖数量和未来权益，另写适用范围。历史买价、既有盈亏和已实现亏损暂停账本仍保留，未来增量比较不重复扣既往买入费，也不以历史套牢自动推断应持有或卖出。

## 概率、幅度与风险分开

建议以后同时审查费用后盈利/亏损、Delta_W分布、期间最大不利变化、资金回撤和无法退出等风险，而非只选最高上涨频率。价格MAE、账户回撤和已实现亏损不是同一个指标；等待方案少持有几天会改变暴露时间，需一并报告。

未来结果区间描述下一次可能结果；估计不确定区间描述概率/参数本身有多不确定。旧描述样本的10%/90%分位数不自动具有未来覆盖保证。不能把两个动作各自的上涨概率相减、相乘或假定独立，就得到等待胜出的概率；若比较两条共同价格路径，需相应配对定义、执行假设及验证。

## 21个合成反例说明了什么

所有数字均虚构，不是高德红外行情或模型概率。部分例子使用B=2000、q=100、单侧费用5，仅为算术，不是账户资金、仓位或券商费率设置。

| 例子 | 精确结果 | 说明 |
|---|---|---|
|同T以10买或等9买，T价10.5|立即终值2040、等待2140|等待可能更好，策略必须事先定义|
|立即10买或等10.8买，T价11|立即2090、等待2010|确认可能带来更高买价，不能预设等待总赢|
|一直未确认，T价12|立即2190、持币2000|错过上涨仍保留，未触发不是零收益成交|
|一直未确认，T价8|立即1790、持币2000|空仓保护也进入同一比较分母|
|10买、10.05卖，100股两端费用各5|价格正0.5%，净亏5|涨了仍可能亏钱|
|70%赚1%、30%亏3%，未计费|期望−0.2%|高胜率不等于好交易；这不是实测概率|
|10买、期间低至7、最后11卖|终点净赚90，价格MAE−30%|最后上涨不等于过程中安全|
|同OHLC 10/12/8/11|两条可能路径的上下线先后相反|日K无法确定顺序或兑现止损|
|B=9900，10买990单位或等11买900单位，d5价9|共同d5终值8910、8100|若错给等待方案d7价12，终值10800会反转结论；禁止跨终点比较|

其余例子覆盖零变动、未成交、部分成交、费用/成交未知、机械除权、非正与严格下跌、晚确认、不同初始资金/终点、NAV和变现、未来信息及缺失交易日。详见[全部合成案例](./合成案例说明.md)及[精确计算](./合成案例与精确计算.json)。23项算术/边界检查通过只证明示例一致，不证明市场预测有效。

## 需要冻结的参数和本步验收

已确认的是首版使用问题和收盘后模式。以下仍为null：回落资格、确认条件、主期限H、具体出卡/信息截止、计划日历、最长等待、最迟确认/入场、订单与取消规则、NAV或清算终点、资金分配、现金利息、费用/税/滑点、经济中性带、风险线和行动门槛。不能拿合成金额或旧5日默认静默填入。后续由我准备可比较方案，你确认使用偏好，研究条件和公式由我负责细化。

本步的验收是：旧标签能力与局限写清；动作共用时间、资金和口径；未触发/未成交/缺失/未成熟保留；定义和例子独立复核；旧数据、草案、源码、累计16变体和风险口径不变。它不是新的信号、模型、盈利或实用验收。

已确认的条件性1万元试验意向、累计已实现亏损2000元暂停新增买入并复核、浮亏单列不变；其他净值/仓位保护仍待确认，不因本步完成使用资金。未采购、未操作证券账户或联系他人。

本批没有查询真实价格结果表，没有新增真实标签/模型/评分，2025/2026后期结果继续隔离，也没有当前买卖预测。

## 交付与下一步

- [预测事件字典](./预测事件字典_v1.json)、[状态与资格字典](./状态与资格字典.json)：每种问题对应什么结果，什么状态不能填0。
- [本次用户确认与待定参数](./本次用户确认与待定参数.json)、[设计合同](./审查范围与设计合同.json)：确认、建议、待定分别记录，旧草案不覆盖。
- [来源与版本索引](./来源与版本索引.json)、[时间制度审查](./时间制度来源独立审查.md)、[数学设计审查](./数学设计独立审查.md)：证据位置与边界。
- [合成案例](./合成案例与精确计算.json)和[核验](./合成案例核验.json)：全部虚构并保持NULL/未成交边界。
- [续作断点](./本轮状态与续作断点.json)：下一批是第3份“时间、执行与数据准入缺口矩阵”；然后才是第4份路线决策。

本批不顺带开始第3/4份或新模型，不扫描剩余14列。完整归档是否完成以项目外{ARCHIVE/'归档校验结果.json'}为准，旧备份全部保留。
'''
 (OUT/'预测问题与标签适用性审查_v1.md').write_text(report)
 ck('readable_review_covers_confirmed_and_pending_separately','首版优先' in report and '仍为null' in report and '当前买卖预测' in report)
 ck('old_forecast_draft_hash_unchanged',sha(ROOT/'outputs/首版预测协议草案_20261016.json')=='f9035be2c22e906eebd6a04f1563021284f18d377450b4b10e0590a4639183ee')
 ck('all_protected_sources_unchanged_after_build',all(sha(ROOT/p)==h for p,h in sources.items()))
 write(OUT/'本轮构建核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,protected_source_sha256=sources,synthetic_case_count=21,new_real_market_targets=0,new_models_fitted=0,new_scores_calculated=0))
 summary=dict(cumulative_registered_variants=16,review_steps_completed=2,review_steps_remaining=2,user_confirmed_first_use_case=cfg['user_confirmed']['first_use_case'],event_definitions=12,status_axes=5,synthetic_case_count=21,synthetic_checks=23,new_real_market_targets=0,new_model_variants=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,phase_promotion_approved=False)
 state=dict(client_date='2026-11-01',origin='direct_human_request_not_scheduled_heartbeat',research_stage=5,status='step_2_design_review_built_awaiting_correspondence_audit',review_package_step=2,review_package_step_completed=False,review_package_steps_total=4,archive_summary=summary,
  user_confirmed_first_use_case=cfg['user_confirmed']['first_use_case'],pending_freeze=cfg['pending_freeze'],completed=['Question and label review document, dictionary, status axes, official source review and synthetic examples built'],partial=['Final independent correspondence audit and frozen archive pending','Formal horizon/confirmation/execution/fees/risk parameters are not frozen'],blocked=['Historical first availability, daily trading status and real costs/fills remain uncertified; no new experiment or trading approved'],
  cumulative_registered_variants=16,new_registered_model_variants=0,new_real_market_targets=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,current_forecast_generated=False,model_input_approved=False,runtime_usable=False,phase_promotion_approved=False,old_protocol_or_risk_modified=False,counts_as_completed_nightly_batch=False,
  source_hashes=sources,next_checkpoint=['Complete the temporal, execution and input-admission gap matrix for the confirmed after-close buy-versus-wait question; no new model, actual outcome label generation or scoring','Then complete next-stage route decision; first use case confirmed, horizon/confirmation/maximum wait/allocation/fees/terminal policy remain unconfirmed','Retain all 16 variants, failed candidates, old protocols and risk settings; keep 2025/2026 target outcomes isolated, do not scan remaining 14 prepared columns'],
  archive_verification_path=str(ARCHIVE/'归档校验结果.json'),confirmed_test_intent_cash_cny=10000,confirmed_pause_cumulative_realized_loss_cny=2000,floating_pnl_separate=True,real_trading_authorized=False)
 write(OUT/'本轮状态与续作断点.json',state)
 print(json.dumps(dict(built=True,build_checks=len(checks),protected_sources=len(sources),synthetic_cases=21,real_market_targets_generated=0),ensure_ascii=False))

if __name__=='__main__':main()
