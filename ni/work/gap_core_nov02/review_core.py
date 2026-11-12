"""Evidence-only core gap review. No market outcome table is opened."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
def read(p):return json.loads((ROOT/p).read_text())
def sha(p):
 h=hashlib.sha256()
 with (ROOT/p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

SOURCE_PATHS={
 'S01':'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json',
 'S02':'outputs/预测问题与标签适用性审查_20261101/来源与版本索引.json',
 'S03':'work/conditions_finish_oct22/summary.json',
 'S04':'work/conditions_finish_oct22/daily_trade_conditions_915.json',
 'S05':'work/conditions_finish_oct22/commission_accounting_contract.json',
 'S06':'work/conditions_finish_oct22/fee_schedule.json',
 'S07':'work/conditions_finish_oct22/rule_regimes.json',
 'S08':'outputs/高德红外数据库/calendar_audit_result.json',
 'S09':'outputs/高德红外数据库/official_calendar_2023_to_20261015.json',
 'S10':'outputs/高德红外数据库/交易日历核对报告.md',
 'S11':'outputs/统一数据底座_20261022/数据使用与准入规范.json',
 'S12':'outputs/五项数据补缺_20261022/公司行动核对.md',
 'S13':'outputs/市场环境输入准备_20261031/输入使用与复算说明.md',
 'S14':'outputs/预测问题与标签适用性审查_20261101/本轮状态与续作断点.json',
 'S15':'work/market_warmup_finalize_oct22/summary.json',
 'S16':'outputs/市场环境输入准备_20261031/本轮状态与续作断点.json',
 'S17':'work/conditions_finish_oct22/source_identity_corrections.json',
 'S18':'outputs/五项数据补缺_20261022/历史交易条件核对.md'
}

def main():
 before={p:sha(p) for p in SOURCE_PATHS.values()}
 contract=read(SOURCE_PATHS['S01']);summary=read(SOURCE_PATHS['S03']);daily=read(SOURCE_PATHS['S04']);calendar=read(SOURCE_PATHS['S08'])
 rows=[]
 def add(id,title,refs,evidence,missing,impact,minimum,acceptance,now,user=None,depends=None,allowed=None):
  rows.append(dict(gap_id=id,title=title,source_reference_ids=refs,evidence_as_of_scope=evidence,missing_evidence=missing,affected_claims=impact,minimum_completion_evidence=minimum,completion_criterion=acceptance,independent_work_possible_now=now,owner='助手负责整理、核对、代码及公开来源；用户仅在明确列出的账户私有或使用偏好部分参与',user_participation=user or dict(required_now=False,required_for_public_evidence=False),dependencies=depends or [],current_use_limit=allowed or dict(saved_engineering='仅声明来源/范围和假设的工程研究；本矩阵不新放行模型',formal_historical_action_validation=False,current_decision_or_execution=False),all_formal_gates_remain_false=True))
 add('T01','历史首次可得、修订和版本连接',['S01','S11'],
  '已保存原件/采集时刻/版本；采集时间只证明当下取得，不证明2023年当时已见该版本。旧源的PIT/首次可得认证仍未完成。',
  ['每个拟用字段的历史首次公开或可验证接收时点','修订版本何时可用及旧版是否可恢复','日期标签的时区、精度及缺失理由'],
  ['正式历史预测的输入时间资格','确认信号是否含未来信息'],
  ['按字段/版本保存原件、事件时刻、公布候选时刻、接收时刻、修订时刻及SHA','取得可追溯的时点证明；仅有日期时用有来源依据的保守可用边界或停用，不套统一猜测滞后'],
  '对声明实验范围的每次as-of连接，可解释何版本在decision_ts之前可用；不可认证的保留未知及覆盖损失。历史无法恢复时可转为明确受限的回顾敏感性研究或冻结后前向采集，不能称历史PIT通过。',
  ['先写字段级时间/版本证据表、未知状态和as-of连接合成反例','按已存原件定位候选证据，历史不可恢复处记录限制而非要求用户找不存在渠道'])
 add('T02','收盘字段何时真正齐备',['S01','S02'],
  '11/01已核2026盘后固定价格通道及盘后量额并入全日总量；并未认证供应商最终字段实际到达时刻。用户只确认收盘后买vs等，未确认15:00或具体出卡时刻。',
  ['OHLC、全日量额、换手、筹码摘要等各自最终/暂定定义','各端点实际可取得时刻及修订延迟','历史制度与当前供应商截面能否对应'],
  ['收盘后预测的信息截止','盘后价格/成交假设','放量确认是否在决策前已知'],
  ['列出每项字段的生成阶段和实际采集/接收日志','选定拟用字段集合后将decision_ts置于其已认证可得边界之后，保存修订和超时状态','若研究盘后同价成交须另证通道、申报/排队及该时点输入齐备'],
  '在声明的规则有效期和数据版本内，所有用作该张卡输入的字段earliest_use_ts<=cutoff；15:30结束也不是供应商准时到达保证。未齐则延后新出卡或弃答，不能回填原卡。',
  ['建立字段到达时刻登记模板和版本字段；保留现有盘后来源','先限定字段和时间语义，不新增真实信号或以现行通道回填旧年'])
 add('T03','计划交易日历、范围续接和异常闭市',['S08','S09','S10','S01'],
  '最新机器日历核验截止2026-10-15、914个预期交易日；旁边说明MD仍为10/13、912，是旧说明。年度休市公告已保存链接及人工转录，未由股价有数据与否反推计划。',
  ['新协议拟用期间的计划日历版本、原公告与发布日期映射','10/15后续接与非计划闭市/修订公告','H、等待上限及共同终点的明确绑定'],
  ['五个计划交易日与五观察日不混用','等待方案共同T和标签成熟边界'],
  ['用已有官方年度休市公告原件/页面独立复核机器日历，补到声明范围','另记事前计划版本和后来异常闭市事实/知悉时点','先固定H与共同T规则，个股缺失或停牌不自动顺延'],
  '声明范围日历集合、来源/生效时点和异常处理可复现；旧MD/新JSON差异保留并给出版本优先级，不能据新行情日期自动宣布日历续齐。',
  ['整理914机器日历与912旧文档的版本对照','准备计划/观察日分离及假日/缺失日合成边界'],depends=['T01'])
 add('X01','历史有效规则、数量单位与价格步长',['S07','S17','S02'],
  '已有2021/2023/2026三段选定条款。2023原PDF仍缺，中间完整修订链未认证；一份旧件错归2023已纠正，原件保留。2026原件及部分条款已核，不代表全历史齐备。',
  ['2023完整官方原件及中间修订/暂缓条款链','拟用日期适用的申报单位、价位、涨跌幅和特殊状态映射'],
  ['历史订单合法性','可卖及限价条件','当前规则不能倒填旧年'],
  ['按制度切换点取得官方原件、通知和有效日期；检查文件正文而非仅文件名','为声明标的板块/证券类别列条款和边界；证据不足日期保留未知'],
  '每一声明日期的规则ID能定位有效原件/条款，切换日和特殊情形验证；只补3个版本标题不能算完整规则审计。',
  ['沿现有通知/原PDF清单整理缺件优先级','用合成数量/步长和切换日核对器准备，不开放执行'],depends=['T01','T03'])
 add('X02','逐日ST、停复牌和临时状态',['S03','S04','S18'],
  '交易条件915行截止10/16；45份停牌月报和45份成交统计提供908日月度范围线索。停牌表未出现002414、月末名称正常或有正成交量均不证明逐日全天正常。实际daily_verified_normal=0。',
  ['逐日风险警示/撤销及适用生效时点','全日/盘中停复牌原始事件与时点','对无记录日期的范围完备性证据'],
  ['用户ST禁入','当日可尝试交易资格','未成交/不可执行分母'],
  ['从官方证券状态/公告事件清单重建区间与生效时刻，保存原件及来源范围','用另一合适官方/授权来源或完整事件清单核对空白；未知不填false'],
  '仅对证据覆盖的日期/窗口给出状态值及认证；未查到不等于未发生。主张全日正常需覆盖全日且负面范围有依据，不能用月度证据升格。',
  ['先按915原表列哪些是月度观察、哪些是每日未知','准备三态状态和禁入原因，不要求用户提供券商密码'],depends=['T01','X01'])
 add('X03','官方日限价、除权参考与订单成交可能性',['S03','S04','S12'],
  '915日官方逐日上下限认证数0；现有候选限价按条件规则算，仅供诊断。三已知除权日未套前收×比例。是否可排队成交仍未知。',
  ['官方当日参考价/上下限及特殊无涨跌幅状态','除权参考和精确步长舍入','价格触及、排队顺序和实际成交的区分'],
  ['价格/订单是否有效','涨跌停买不到或卖不掉','风险线触及后的可实现损益'],
  ['补声明日期官方价格限制/参考和状态，核对规则有效期及舍入','若研究成交，另补订单/成交或具范围的盘口证据；日K不能单独证明排队'],
  '合法价格、可申报窗口、排队/成交分别有状态；官方限价记录通过不自动把fill=true。',
  ['对候选限价保留candidate标签；准备除权/新股/特殊状态拒绝合成例'],depends=['X01','X02'])
 add('D01','原价、复权、单位和冲突处理',['S15','S13','S11'],
  '固定行情有双供应商/多端点核对，旧预热补核资料止10/16；后续市场输入用10/21快照。SDK单位映射和严格差异均已留存，供应商正式单位/因子合同未齐；当前复权快照不是历史时点版本。',
  ['拟用字段正式定义/单位或带明确限制的映射证据','历史可重建复权/公司行动桥接','严格冲突裁定与版本选择协议'],
  ['信号数值一致性','费用/成交数量金额核算','机械除权不误作反转/跌幅'],
  ['逐字段固定价格口径、原数/转换/单位及源版本','保留严格差异和源标识，按事先规则隔离而非挑对模型有利的源','用有效时点公司行动桥接，未桥接段限用或显式切段'],
  '声明字段可从原件/公式重建；双源一致只证明相容，不是交易所真值或PIT认证。量额单位未核不得跨股票/指数换算或输出精确费后结果。',
  ['整理现有单位、差异、预热及切段事实，不刷新收益目标','先限定最小价格/量字段集合再补证'],depends=['T01'])
 add('X04','入场策略、订单有效期和反事实成交',['S01','S04'],
  '前一步已明确现在买/等待/持币共B、共信息、共T；但回落、确认、订单、等待上限等15组参数仍NULL。日K不识别两条反事实订单都能成交。',
  ['事前可观察的回落资格和确认规则','入场窗口、报价/数量、失效/取消、最长等待','双路径执行假设及其可识别边界'],
  ['等待优于立即买入的标签是否有定义','不在结果后挑最低价或延长等待','未知执行的处理'],
  ['由助手先给有限且可实现方案，记录选择原因和失败时处理，再由用户确认使用期限/偏好','将假设成交、已知成交、未知成交分离，另定覆盖及敏感性报告'],
  '比较双方同起点/同规则种类/同T；未触发保留现金路径，未知成交结果不当0；只可登记边界明确的假设研究，不能声称日K还原真实个人成交。',
  ['整理待定参数与最小证据依赖；用已存21合成例讲清，不启动候选'],
  user=dict(required_now=False,required_for_public_evidence=False,required_before_final_usage_preferences=['预测期限和使用偏好；助手提供具体选项，用户无需设计公式']),depends=['T01','T02','T03','X01','X02','X03'])
 add('X05','部分成交、取消、预留现金及实际资金分配',['S01','S04'],
  '已有离线账务原型及合成边界，未核验用户真实现金、持仓或订单。新标签设计区分NO_ORDER/UNFILLED/PARTIAL/FILLED/UNKNOWN，不等于实际订单日志已取得。',
  ['申报/成交/撤单、实际数量和时戳','未成交余量和冻结/释放现金','佣金最小额按订单还是成交归集的实际规则'],
  ['策略财富及剩余现金','满额成交假象','精确账务/费后收益'],
  ['先冻结订单生命周期与分配/归集口径，建立可恢复的合成流水核对','账户使用前以脱敏成交/撤单和资金流水校对，不以日线补造订单'],
  '逐笔量价费与剩余现金闭合，部分成交不记请求全量，未成交收益NULL而有依据的现金路径可估值；未知保持未知。',
  ['完善离线审计字段和合成复核方案；研究阶段不需实际账户访问'],
  user=dict(required_now=False,required_before_account_specific_use=True,minimum_private_evidence='届时可提供脱敏订单/成交/撤单及资金流水；不需要密码或身份证全文'),depends=['X04','C01'])
 add('X06','持仓批次、可卖数量及T+1时间',['S01','S02'],
  '现行普通股票交收前卖出限制的选定条款已核；不代表用户仓位、买入日及可卖数量已核。用户选的是首版问题，未声明实际空仓；研究现金子仓只是设计假设。',
  ['初始持仓/成本批次、买入日和可卖数量','末次确认/入场与共同T可清算条件','现有持仓下新增买/不加仓的适用范围'],
  ['晚入场当日不可默认卖出','持仓退出/做T适用性','实际可买可卖金额'],
  ['为声明策略范围设置初始状态、可卖批次和结算迁移规则','对现金子仓与已有持仓两种范围分别声明，不能从用户选项推断实际账户状态'],
  '在共同T下，清算可执行性与NAV分开；不合法卖出不得假设成功，不能偷偷延T到可卖日。',
  ['继续用虚构批次边界测试和范围说明；不查询证券账户'],
  user=dict(required_now=False,required_before_account_specific_use=True,minimum_private_evidence='使用前核对脱敏当前现金/持仓/买入批次和可卖数量；首版研究可先声明假设，不当用户事实'),depends=['T03','X01','X04'])
 add('C01','账户佣金、最低收费、包费和舍入',['S05','S03'],
  'commission_accounting_contract默认unknown，账户费率、最低额、经手/证管/过户是否已含及归集舍入均NULL；915日完整成本认证0。每月2000预算不是费率证据或采购授权。',
  ['适用日期和证券/通道的账户佣金','最低收费、全佣/净佣包含项','订单/分笔归集及金额舍入'],
  ['精确费用后盈利与财富差','小额交易成本','运营费不能混进交易费后概率'],
  ['由用户在正式账户使用前提供一份脱敏有效费率说明及数笔不同金额/分批成交对账；助手据此拆包并核最低额','公共费用原件与账户包费逐项去重'],
  '每一笔拟算精确净结果的适用费率/最低额/包含项/舍入均可追溯并与对账一致；未知时只可声明成本场景，不能称实际净收益。',
  ['先列包费字段与对账模板，准备全佣/净佣和小额合成例'],
  user=dict(required_now=False,required_before_account_specific_net_result=True,minimum_private_evidence='脱敏账户费率说明及有限成交对账；不用联系亲属、开通API或提供密码'),depends=['X01'])
 add('C02','法定和交易结算费用历史有效期',['S06','S03'],
  '既有印花税/经手费调整与部分有效期证据；证管费更早连续链、2022过户费原始发布件仍有证据等级缺口。2026表能证其所述时点，不能自动覆盖全部历史。',
  ['声明区间内费项起止/生效时点原件','历史连续性、包费与证券/通道范围','停用或调整项目的版本'],
  ['跨历史日期精确税费','成本压力和可比净财富'],
  ['按现有fee_schedule逐行补官方原始通知和适用范围，保留转载/检索证据的低等级标记','将法定费用有效期与账户包费连接，禁重复收费'],
  '声明日期和证券类型的费用版本有原件链或明确限制；不得以2026最新费率回填2023，未知不填0。',
  ['先做已有原件/缺件索引及日期边界核对，不需用户私有信息'],depends=['X01','C01'])
 add('C03','公司行动、股数权益与股息税',['S12','S01'],
  '3个既有分派的登记/除权/公告约定代派日已保存；代派不证明用户实际到账。旧资料明确税务身份不由居住加拿大推断；权益公告首次时刻和逐日股本仍有未知。',
  ['声明窗口内适用的全部权益事件及其历史可得版本','个人持有期限/税务身份和实际税款/应收到账','公司自派范围或特殊权益的日期/金额'],
  ['机械价格变化与经济收益区分','终点股数、可用现金、应收及负债','跨分派窗口净财富'],
  ['先以官方实施/登记资料建立时点、股数、现金及应收路径并保留未知','账户使用前只核影响本次权益的必要持有/税费资料；不能把公告代派日当个人到账'],
  '股数和权益能对原件/持仓范围，现金与应收无重复，未付税费负债不填0；不完整窗口保留不可评估及覆盖影响。',
  ['用已有3事件核状态字段，不新增实际收益标签；未知权益优先补证而非挑有利样本'],
  user=dict(required_now=False,required_before_person_specific_tax_or_cash=True,minimum_private_evidence='仅在涉权益净结果时补脱敏持有日期、适用身份/税单及到账资料；不自行推断税务居民身份'),depends=['T01','X06','C02'])
 add('V01','终点估值、负债和实际清算',['S01'],
  '前一步已分NAV与实现现金，NAV要减未付税费/其他负债，到账股息不重计应收；终点口径本身仍NULL。',
  ['共同T的有效估值源、停牌/过时价格规则','未付费用/权益负债和可用现金','若主张清算，实际退出成交及可卖性'],
  ['等待相对立即买的终点财富','已实现亏损与浮动盈亏分列','卖不掉时不能按收盘价记已实现'],
  ['在协议中先选NAV或清算事件，二者均可同时展示但不能混评分','保存T时戳、标记价来源/陈旧性、现金/股数/应收/负债以及退出状态'],
  '有有效NAV不等于清算现金；清算未成交时该清算标签不可评估，不顺延T或用NAV替代成功。',
  ['复用21合成例制作终点字段清单；不需要本轮真实账户或新价数据'],depends=['T03','X04','X05','X06','C01','C03'])
 add('R01','日K路径风险、跳空和不能退出',['S01','S04'],
  '旧方向标签只看终点，现有日K不能识别同日上下风险线先后。合成反例已示范：最后上涨仍可能中途大幅不利变化，触线不等于成交。',
  ['入场后风险路径的可识别时间粒度','盘中先后与开盘跳空的执行规则','若研究做T，分钟/逐笔时点及底仓账本'],
  ['期间最大不利波动、风险线触及与可实现止损','盘中精确时点或做T承诺'],
  ['先声明日频可识别指标及不可识别状态，遇同日双线只给未知/保守边界','只有确需路径/做T才另取有授权细粒度数据并核时间；不以日K低点做事后最优入场'],
  '风险测量与执行分别认证；不能由日K路径不足而把风险当0，也不把细粒度数据数量当成交保证。',
  ['整理日K可/不可识别问题和合成双线/跳空例；做T保留后续范围'],depends=['T02','X03','X06'])
 add('D02','不同数据轨道的截止与当前新鲜度',['S03','S08','S16','S14'],
  '行情/市场环境快照沿用10/21，官方计划日历机器件10/15，交易条件915日止10/16，月报截至9月；这些不是一个“全部更新到今天”的数据库。',
  ['拟用期间与当前最近闭市日期的逐轨道覆盖','真实采集到达、完整性与源版本健康','明确的旧数据过期/拒答条件'],
  ['当前预测卡的有效性','最新行情不能替代状态/费用/日历证据','研究范围的真实覆盖'],
  ['按字段/来源分别记录last_verified_date、last_received_ts、范围缺口和状态','后续采集只用公开或授权来源逐批留原件及核验，不把新价同日自动放行其他轨道'],
  '每张未来卡所有必需输入均满足预定新鲜度/版本条件；缺任一项显式不可评估。当前本批不声称已更新行情或可出卡。',
  ['先列截止差异与补齐顺序；可完成矩阵而不读取后期结果'],depends=['T01','T02','T03','X02','C01'])

 checks=[]
 def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
 ck('confirmed_question_only_not_trading_authorization',contract['user_confirmed']['first_use_case']=='收盘后判断回落时该买入还是继续等待' and not contract['user_confirmed']['is_trading_or_capital_authorization'])
 ck('15_grouped_parameters_unfrozen',len(contract['pending_freeze'])==15 and all(v is None for v in contract['pending_freeze'].values()))
 ck('calendar_latest_machine_end_and914',calendar['end']=='2026-10-15' and calendar['expected_total_trading_days']==914)
 ck('calendar_old_MD_retained_scope_not_promoted','10 月 13 日' in (ROOT/SOURCE_PATHS['S10']).read_text() and '912' in (ROOT/SOURCE_PATHS['S10']).read_text())
 ck('915_condition_rows_to1016',len(daily)==summary['daily_rows']==915 and daily[-1]['trade_date']=='2026-10-16')
 ck('no_daily_state_limit_fill_cost_certified',summary['actual_daily_verified_normal_count']==summary['official_daily_limit_price_count']==summary['execution_eligible_count']==summary['complete_account_cost_model_count']==0)
 ck('monthly_observations_bounded',summary['days_with_monthly_scope_evidence']==908 and summary['monthly_suspension_reports']==summary['monthly_stats_reports']==45)
 ck('all_16_gaps_distinct',len(rows)==16 and len({r['gap_id'] for r in rows})==16)
 required=['evidence_as_of_scope','missing_evidence','affected_claims','minimum_completion_evidence','completion_criterion','independent_work_possible_now','owner','user_participation','current_use_limit']
 for row in rows:ck('complete_matrix_fields_'+row['gap_id'],all(row[k] for k in required) and all(s in SOURCE_PATHS for s in row['source_reference_ids']))
 ck('no_gap_demands_user_or_purchase_now',all(r['user_participation']['required_now'] is False for r in rows))
 ck('no_admission_or_runtime_promotion',all(r['all_formal_gates_remain_false'] and not r['current_use_limit']['formal_historical_action_validation'] and not r['current_use_limit']['current_decision_or_execution'] for r in rows))
 after={p:sha(p) for p in SOURCE_PATHS.values()};ck('all18_saved_sources_unchanged',before==after)
 result=dict(audit_id='core_temporal_execution_admission_gap_review_20261102',client_date='2026-11-02',scope='Saved evidence review and completion design; no real outcome query/new target/model/score',created_at_utc=datetime.now(timezone.utc).isoformat(),all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,sources={sid:dict(path=p,sha256=before[p]) for sid,p in SOURCE_PATHS.items()},source_sha256_before=before,source_sha256_after=after,gaps=rows,new_actual_labels_generated=False,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,current_forecast_generated=False,formal_input_approved=False,runtime_usable=False,old_risk_settings_modified=False,limitations=['本批仅核对已存证据，不认证其后没有新规则/状态变化；规则事实依原有版本日期。','16项core子任务不是整个项目最终缺口数量，根矩阵可合并/拆分但要保留含义和证据。','不完整成本/状态/PIT不等同数据内容必错或历史不可交易；认证门false是证据限制。','不能把未完整认证的某一可选输入变成所有受限工程研究都不能继续的绝对阻塞。'])
 (OUT/'核心缺口审查.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 parts=['# 核心时间、执行与准入缺口独立审查','2026-11-02。以已确认收盘后回落买入vs等待为主，仅整理既有证据和最小补证，不新查询真实结果、生成标签、模型或评分。','重要版本差异：最新日历机器件到10/15、914日；同名说明MD是10/13、912日旧版本。交易条件到10/16，行情轨道到10/21，不互相冒充更新。']
 for row in rows:
  parts+=['\n## '+row['gap_id']+' '+row['title'],'**已有证据及范围：** '+row['evidence_as_of_scope'],'**仍缺：** '+'；'.join(row['missing_evidence']),'**影响：** '+'；'.join(row['affected_claims']),'**最小补证：** '+'；'.join(row['minimum_completion_evidence']),'**完成标准：** '+row['completion_criterion'],'**现在可独立做：** '+'；'.join(row['independent_work_possible_now']),'**用户参与：** '+json.dumps(row['user_participation'],ensure_ascii=False),'**证据位置：** '+'；'.join(SOURCE_PATHS[s] for s in row['source_reference_ids'])]
 parts+=['\n## 核验及限制',f'{len(checks)}/{len(checks)}项检查通过，18份源文件前后哈希一致。费用/真实账户私有事实仅在相应正式使用前需要用户提供脱敏证据；本批无一项必须用户现在先提供。工程/来源核验不能证明预测有效；累计16变体和全部门槛不变。']
 (OUT/'核心缺口审查.md').write_text('\n\n'.join(parts)+'\n')
 print(json.dumps(dict(gaps=len(rows),checks=len(checks),sources=len(SOURCE_PATHS),written=True),ensure_ascii=False))

if __name__=='__main__':main()
