"""Review saved optional-feature evidence only; no market queries or labels."""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib

ROOT=Path(__file__).resolve().parents[2]
DEST=Path(__file__).resolve().parent
SOURCES=[
 'outputs/市场环境输入准备_20261031/本轮推进报告.md',
 'outputs/市场环境输入准备_20261031/本轮状态与续作断点.json',
 'outputs/市场环境输入准备_20261031/市场来源独立核对.md',
 'outputs/市场环境输入准备_20261031/行业代理准入审查.json',
 'outputs/市场环境输入准备_20261031/事件时间准入审查.json',
 'outputs/五项数据补缺_20261022/市场行业核对.md',
 'outputs/五项数据补缺_20261022/公告政策事件核对.md',
 'outputs/五项数据补缺_20261022/阶段报告.md',
 'outputs/三线研究启动_20261025/筹码摘要核查/筹码摘要质量报告.md',
 'outputs/三线研究启动_20261025/筹码摘要核查/筹码摘要质量台账.json',
 'outputs/初始化与验证推进_20261026/筹码初始化/筹码初始化改进v2报告.md',
 'outputs/高德红外数据库/财务原件核对报告.md',
 'outputs/高德红外数据库/会计修订核对说明.md',
 'outputs/高德红外数据库/查漏补缺报告.md',
 'outputs/高德红外数据库/查漏补缺报告_v0.4.md',
 'outputs/高德红外数据库/股本与状态核对说明.md',
 'outputs/统一数据底座_20261022/本轮数据整理报告.md',
 'outputs/统一数据底座_20261022/数据使用与准入规范.json',
 'work/market_industry_oct22/input_admission.json',
 'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json',
 'outputs/研究证据与覆盖审查_20261101/本轮状态与续作断点.json'
]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(rel):return json.loads((ROOT/rel).read_text())
def row(id,name,existing,missing,affected,minimal,workflow,independent,alternative,sources,owner='助手',user='目前不需要用户另找数据渠道或提供账户资料；研究准入由助手核查',priority='可选输入；仅在未来协议明确使用时形成该输入的准入前置'):
 return dict(gap_id=id,name=name,role_in_confirmed_first_use_case=priority,evidence_basis='已保存本地资料的有日期快照；本次未刷新行情或外部覆盖',existing_evidence=existing,unresolved_evidence=missing,affected_tasks=affected,minimum_additional_evidence=minimal,proposed_acquisition_and_verification=workflow,independent_work_possible_now=independent,limited_alternative=alternative,owner=owner,user_participation=user,user_required_now=False,source_paths=sources,current_use=dict(source_audit_allowed=True,engineering_reconstruction='only within saved definitions or separately registered retrospective scope',formal_historical_input_approved=False,current_decision_approved=False,runtime_usable=False),does_not_block_all_other_research=True,acceptance='核验所列最小证据、时点、版本、口径与适用范围；另行登记使用协议，不因资料存在或本审查完成自动放行')

def main():
 before={p:sha(ROOT/p) for p in SOURCES}
 context=read(SOURCES[1]);industry=read(SOURCES[3]);events=read(SOURCES[4]);chips=read(SOURCES[9]);contract=read(SOURCES[19])
 rows=[
 row('F01','市场/指数收盘背景及版本',
     '三指数双源各1160日截至2026-10-21，2023起918日；固定东方财富单源、腾讯差异核对；12过去收盘定义+3相对强弱定义及1股票辅助共18560单元，工程可重建。开发期三指数close一致；全快照上证2026-02-11 close相差0.01指数点，精确传播隔离28单元/21日。',
     '回采快照的历史首次可得/修订链未认证；源一致也不证明上游独立或官方真值。15候选准备列不是15个已验证模型，M3失败不自动给其他列有效性。',
     ['以市场价格作辅助特征的正式时间验证','当前可用背景更新'],
     '逐字段固定来源/版本/单位/观察日轴；供应商历史版本或可验证首次发布时间/接收记录；冲突处保留两源原值、裁定或缺值政策。',
     '先盘点既有close差异及精确依赖，不改原件；补文档/历史版本证据并建立今后首收日志；取得新观察另存快照，不拼接平均或按结果择源。',
     '整理源版本和冲突依赖，审核首收日志字段；旧失败结果保留，不扫描剩余14列。',
     '固定单源过去价格背景可限作工程准备，仍未授予正式PIT或当前预测资格。',[SOURCES[0],SOURCES[1],SOURCES[2],SOURCES[5],SOURCES[18]]),
 row('F02','指数成交量/成交额单位与统计范围',
     '三指数原生量值及跨源差异保留；10/22对照各1160日，成交量差异日上证77、深成291、中证军工6；腾讯对应金额/换手不可比字段为空。',
     '股/手/张、合计范围、是否含全部交易方式、指数成员范围与供应商汇总定义未取得正式连续证据；不能跨源拼量或从点位倒推资金。',
     ['指数量能/成交强度','资金流解释'],
     '对应来源和有效版本的字段文档、单位/包含范围，选取日期的原始明细或官方汇总可核对；转换公式和舍入误差范围。',
     '先按源保存单位候选，不推定倍数；取得说明后以可复核样本核对，再把转换和未解决差异显式登记。',
     '设计单位核查表和来源分层，不动原量值。',
     '当前只用close背景的工程路线可避开量值；同源量比也需清楚说明口径且不能等同真实外部资金流。',[SOURCES[5],SOURCES[18]]),
 row('F03','历史行业/题材成员及方法版本',
     '399967中证军工价格代理双源1160日；官方2023年12月V1.2方法PDF与身份可追溯。',
     '未取得研究期前有效成员基准及所有定期/临时调整、权重与生效边界；未证明002414整个历史区间属于该样本。现有方法版本/文件Last-Modified不能认证初发或历史生效。',
     ['按历史行业分组','行业相对强弱/成员控制','横截面样本总体'],
     '研究期前官方有效成员清单+全期入选/剔除调整公告，分别记录公布/生效/首次可用；历次编制方法、权重维护及证券代码映射。',
     '先以官方历史基准与调整链还原逐日有效成员，再独立核公告时点、调整边界和退市/停牌处理。',
     '列官方原件与缺失版本/成员区间索引，不先用当前成员回填。',
     '可作为军工背景价格代理工程特征；不能称该股票的已认证历史行业或全行业代表。',[SOURCES[3],SOURCES[5]]),
 row('F04','行业/市场宽度与历史权重',
     '已有指数点位，行业审查已明确它是筛选、市值加权的价格代理。',
     '完整当日成员及逐股前收/收盘、ST/停牌/上市退市、除权基准和历史权重不全；没有涨跌家数/宽度全集。',
     ['涨跌家数、创新高比例、等权宽度','加权成交或行业集中度'],
     '先获得当时有效成员全集、逐股可比数据与状态、固定分母/缺失纳入规则；加权研究另需生效权重与股本。',
     '先写总体和分母规范，随后依历史成员取样而非事后选股，逐日覆盖对账。',
     '制定分母/缺值规则；区分价格指数、总回报指数、等权宽度。',
     '指数过去回报不能替代行业宽度；本首版可暂不纳入宽度而继续定义/底座核查。',[SOURCES[3],SOURCES[5]]),
 row('F05','交割/到期/公司行动/政策事件的事前可得',
     '67日期角色归59经济编号；46个月中金所记录，5月有官方逐月资料：仅2023-12、2025-01为提前提醒，2026-08/09/10为事后结果；41月仍规则候选。现存7规则文件无完整历史生效链。11公司行动日期角色来自既有3分派等事件；政策共10样本。',
     '全部67历史事件输入与倒数准入0；事件发生/生效/公告/转载/实际可得未闭合，日历仅SSE/SZSE且非CFFEX前瞻认证，亦未覆盖全部沪深ETF/股票期权。日期角色不等于独立事件。',
     ['事件前后环境条件','可在t0知道的事件倒数','避免事后日期/多次计数'],
     '事件前已公布原件及可信首次可得、正确交易所提前公布的计划日历、有效规则全链；每类事件范围及经济去重键。',
     '按46月/各事件补证清单核原文发布时间、计划日历和生效链；区分事前提醒与事后结果。倒数按t0已知计划日历，不用后来股票K线倒算。',
     '整理来源/角色/生效/时点缺口，完善去重与日历契约，不计算影响收益。',
     '保留事件事实档案和公式候选，尚不能据事后事实作当时预测输入；未准入不表示事件无影响。',[SOURCES[4],SOURCES[6]]),
 row('F06','公告/财务首次公开与修订版本',
     '312原件PDF/4253页和时间台账；普通目录实际末日2026-09-15、投资者关系2026-04-30，目录查询曾到10/22但无新增。15份报告135选定原数字核对，5处提供商与原报告版本差异；原报告与后续重述分开保留。',
     '全部历史首次公开准确时刻仍未认证；当前display_time/PubDate可能变化，报告期/目录日/采集日不是知识时点；135值不认证全表或全部版本。',
     ['财务/公告特征','历史决策信息截断','修订与迟发避免泄漏'],
     '原件及可验证发布/首收记录、完整修订顺序、生效知识时点，指标范围/单位/合并归母及报告期映射；所需字段逐项核验。',
     '先以字段需求收窄原件核查，建立as-of版本表；无可信时点者保留未知或限回顾性说明。今后可记录首收，不倒填历史。',
     '定义版本/知识时间和字段来源；核对原件页数、已核字段边界。',
     '可作基本面背景和版本差异审查；不能把最新重述回填旧决策或当全网资料已齐。',[SOURCES[6],SOURCES[11],SOURCES[12],SOURCES[16]]),
 row('F07','扫描页OCR和机器文本到事实的认证',
     '312PDF共4253页：4068有可提取文字，185页有本地OCR；185页OCR中124页622低置信度行提示，整页人工核验和新OCR数字认证仍0。旧选定原件数值/会计表另有逐项核验，不等于整页通过。',
     '扫描表格列序、单位、符号、否定词、数字和签章可能错误；高置信度也不保证正确，关键词重复不等于新事件。',
     ['公告文本分类和财务数字特征','事件否定/条件措辞','金额及审计结论'],
     '按将使用的字段/段落做原PDF视觉与双重数字/语义核对，保留页坐标、单位、合并范围、版本及核验记录。',
     '助手优先核首版确实需要的段落/表格，建立待核队列；不把全文OCR可检索直接当模型事实。',
     '整理低置信度与重复页队列、否定语句分类、原件页码映射。',
     '机器文字可检索定位；未认证段落不能直接作为事实或无事件判定。',[SOURCES[12],SOURCES[14],SOURCES[16]]),
 row('F08','新闻政策覆盖、首发和样本选择',
     '有10个政策/新闻官方样本，区分发文/转载/发布日期/生效及征求意见；不是全量新闻。',
     '没有预定媒体/机构范围的完整逐日档案、首发时间链、转载去重、修订和无事件覆盖证明；不能按已知大涨日反选新闻。',
     ['新闻/政策触发与环境','事件缺失是否可解释为无新闻','模型样本选择'],
     '事前定义来源全集与主题/收录规则、成功失败抓取日志、原文/版本/可信首发或首收、事件去重与否定/草案/生效状态。',
     '先固定来源与事件语义，不看收益挑事件；可先建立未来首收档案，历史缺口明确保留。',
     '制定来源目录和事件字典、去重规则与缺失状态。',
     '现有10样本可做来源和语义核查；不能声称全网覆盖或缺失即无政策，现阶段无须强塞首版模型。',[SOURCES[6],SOURCES[4]]),
 row('F09','网页筹码摘要版本、稳定性与历史时点',
     '954观察/943接受/11拒绝，915不同日期截至2026-10-16；902日仅单次接受，13日重复中8相同/5异版；18预定比较均一致但共享基准。5日异版均保留，价格K线相同不解释摘要原因。915日历史首次可得认证0、完整价档0、模型批准0。',
     '供应商算法/参数/加载范围/复权版本未认证；单次日无重复性证据，重复相同也不认证全历史稳定或当时版本；获利比例不是未来上涨概率。',
     ['摘要变化/筹码与价格pattern','筹码特征历史可用','版本冲突传播'],
     '明确供应商摘要定义、算法/加载范围、价格标尺、换手口径及版本；同日期可重复实验条件/原件、首次可得与修订证据；冲突处理预登记。',
     '优先整理已存5异版和采集条件，不平均或择优；只有在渠道允许并有具体问题时补受控同条件读数，另存新版本。',
     '维护版本/条件/日期同步和冲突字段字典，设计后续受控采集记录。',
     '可保留网页摘要观察与限制图；不能称完整筹码分布、真实持有人或已准入预测输入。',[SOURCES[8],SOURCES[9],SOURCES[7]]),
 row('F10','供应商完整原生筹码价档',
     '现有完整原生每日价档实际覆盖0日；网页摘要915日、自建模型价档不计入此覆盖。',
     '未取得供应商逐价档样本、完整覆盖、授权、算法/初值、复权、历史版本/可得性与可恢复原格式证据；渠道存在/采购能否填满仍未知。',
     ['原生分布迁移/集中和成本分位','声称含原生完整筹码的模型'],
     '先取合法可用的小样本及官方字段/单位/覆盖/算法和版本说明，验证完整价轴/质量/复权及与源摘要关系，再评估所需历史范围和权限。',
     '助手先整理既有候选文档和样本验收条件；若必须登录/付费，再形成具体方案由用户决定，不能预先购买或承诺补齐。',
     '维护接口无关的价档验收规格与覆盖台账；对未知字段保留NULL。',
     '摘要、自建估计、原生价档三轨分别研究；可不含原生筹码继续其他定义/数据核查，不以替代路线冒充取得。',[SOURCES[8],SOURCES[9],SOURCES[10]],user='只有确需授权/付费渠道时才向用户说明可核验样本、成本与限制并请求决定；目前不要求用户凭空找到渠道'),
 row('F11','自建筹码初始化、换手机制和日分布假设',
     'v2从2022-06-01共同起点递推1064日，36组技术样本/3192日诊断；未知初始质量U显式保留，Q为次概率，不归一冒充总体；三角日分布、0.01网格、0.5/1/1.5换手倍率是工程假设。原生价档未取得、全部准入false。',
     '真实初始持仓价位、随机均匀替换假设、换手分母/单位/全日量范围、完整权益史和历史时点未认证。U很小只约束模型内初始差异，不涵盖机制或遗漏事件误差。',
     ['估计筹码成本/获利/分位与迁移','初始化敏感性','声称真实机构持仓'],
     '明确换手分母和当时可得流通量、完整坐标变换权益链；给模型机制/日内分布的证据或声明的敏感性范围，未知初始边界保留；如有合法供应商样本只作有边界外部对照。',
     '先做假设/版本/单位/未知质量说明，不因未来表现选择倍率；日后另立有无估计特征同日对照协议。',
     '梳理假设到输出依赖及失败状态，保留初值/模型误差的区别。',
     '自建估计可作声明假设下的工程诊断；小U、复算通过均不授予真实筹码或预测资格。',[SOURCES[10],SOURCES[16]],priority='用户重点专项，但不是阻塞所有其他首版研究的先决条件；只有明确选用估计筹码时才受其准入门约束'),
 row('F12','滚动资金流/大单分类代理',
     '10/15已保存滚动120日窗口及退出窗口日期，共122个已取得日期（240原始行分版本）；最新行视图不是240独立日。',
     '缺2023以来完整历史、分类算法/成交归属单位、修订和首次发布时间；大单/主力分类不能识别真实基金、投行或外部资金净进出。',
     ['资金线索特征','机构行为解释','时间覆盖与样本选择'],
     '供应商分类定义/单位与窗口限制、版本和首次可得；所需连续历史或事前声明的较短研究范围及覆盖偏差。',
     '先核算法/窗口并保持追加原始响应，追踪失去窗口日期；不能将滚动缺失填0、将分类净额称真实机构持仓变化。',
     '整理字段语义、覆盖缺口与留存策略；不补算概率。',
     '现有范围可作带限制的交易分类观察，不能当全历史机构资金数据；可不加入首版候选。',[SOURCES[13]]),
 row('F13','融资融券余额与流量',
     '已保存10/15阶段913日期，最晚2026-10-14，未返回10/15处保留未取得；该阶段之后刷新状态未在本审查确认。',
     '公告/源日更新何时可用、余额/买入/偿还/余券各字段口径、适用证券与资格变化、后续日期覆盖及修订未完全闭合；两融不是全市场或机构总体仓位。',
     ['杠杆交易背景','将余额/流量关联到信号时间','缺失与非适用区分'],
     '对应交易所/供应商字段定义、适用资格/单位、生效/发布时刻、原始版本与所需日期覆盖。',
     '先确认字段与次日发布/首次可得事实，再按真实时点接入；未返回日不推断余额为0，金额余额不能误当当日净买卖。',
     '设计余额/流量及披露滞后的字典，更新覆盖索引计划。',
     '可作有限已披露背景，不能称已覆盖至11/02或有实时机构交易信息。',[SOURCES[13]]),
 row('F14','公开大宗/龙虎榜/席位与事后字段',
     '旧原件核查保存大宗交易72条、公开榜单/机构席位线索；部分大宗字段含事后1/5/10/20日变化，旧阶段318个事后收益统计值及后续版本化限制单元已隔离；数值单元数不是不同字段数或独立目标数。',
     '公开数据的完整范围/发布时间/更正、席位分类与具体账户身份、对倒/转让性质、其他交易渠道未认证；不能由席位和大单推断真实机构全部买卖。事后变化绝不能进t0特征。',
     ['公开交易线索输入','机构身份解释','未来信息隔离'],
     '官方原披露记录/版本、真实发布或保守可证时点、字段语义与买卖身份边界；以白名单允许当时事实，事后统计保持隔离。',
     '先检查原字段白名单和披露时点，不为找涨跌pattern解开事后列；公开事实有范围，个体真实账户不可据此补造。',
     '维护禁止列、源到字段的语义和披露范围说明。',
     '可使用明确获准的公开事实线索而非真实机构账户账本；缺身份不阻塞不含此组的研究。',[SOURCES[11],SOURCES[13],SOURCES[16]]),
 row('F15','股东/流通股本与换手率分母',
     '8个期末总/限售/无限售原件观测和3个员工非交易过户事件已去重；3个股份性质衔接问题保留。10/15总股东170行含150定期+20部分名单，未有公告日资格；不是25期完整十大或每日持仓。',
     '期间末股份及后来公告不能回填每日当时分母；无限售不等于供应商自由流通定义。实际变动生效日、分母链、首发时点及股东披露范围/期间滞后不完整。',
     ['换手/筹码更新分母','股东结构与持仓特征','股份变动事件'],
     '官方权益/解禁/转让/注销等生效登记链、每天适用股本定义和供应商分母说明；股东名单原件与首次可得、完整/部分标识。',
     '按观察期、公告时点、生效时点分别表述；先核3衔接差异，不把员工非交易过户视为流通股增加或市场买卖。',
     '整理分母定义和原件桥接需求，保持未知生效区间。',
     '期末结构和名单可做有日期原件事实；不能据此得到逐日真实持仓或精确历史换手分母。',[SOURCES[15],SOURCES[13],SOURCES[7]],priority='具体股本分母若用于原始换手/自建筹码则是该字段的必要证据；股东结构为可选增量组')
 ]
 checks=[]
 def ck(name,ok):checks.append(dict(check=name,passed=bool(ok)));assert ok,name
 ck('all21_source_files_exist',len(before)==21 and all((ROOT/p).is_file() for p in before))
 ck('fifteen_unique_optional_gap_rows',len(rows)==15 and len({r['gap_id'] for r in rows})==15)
 ck('all_rows_have_evidence_and_actionable_minimum',all(r['source_paths'] and r['minimum_additional_evidence'] and r['independent_work_possible_now'] and r['acceptance'] for r in rows))
 ck('formal_and_current_gates_remain_false',all(not r['current_use']['formal_historical_input_approved'] and not r['current_use']['current_decision_approved'] and not r['current_use']['runtime_usable'] for r in rows))
 ck('optional_gaps_not_blocking_everything',all(r['does_not_block_all_other_research'] for r in rows))
 ck('event_counts_match_frozen_summary',events['summary']['date_role_rows']==67 and events['summary']['economic_episode_ids']==59 and events['summary']['expiry_months']==46 and events['summary']['official_expiry_months']==5 and events['summary']['rule_candidate_months']==41 and events['summary']['historical_event_input_approved']==0)
 ck('event_advance_result_split_retained',events['summary']['official_advance_months']==['2023-12','2025-01'] and events['summary']['official_result_months']==['2026-08','2026-09','2026-10'])
 ck('chip_exact_coverage_and_version_counts',chips['summary']['accepted_unique_dates']==915 and chips['summary']['single_observation_dates']==902 and chips['summary']['different_version_dates']==5 and chips['summary']['complete_price_bin_dates']==0 and chips['summary']['historical_first_availability_certified_dates']==0)
 ck('market_close_conflict_propagation_counts',context['close_conflict_days']==1 and context['quarantined_feature_cells']==28 and context['quarantine_affected_dates']==21)
 ck('industry_historical_membership_still_uncertified',industry['identity']['historical_membership_of_002414_verified'] is False)
 ck('confirmed_use_case_not_extended_to_actual_account_state',contract['user_confirmed']['first_use_case']=='收盘后判断回落时该买入还是继续等待' and 'starting_comparison_state' not in contract['user_confirmed'])
 after={p:sha(ROOT/p) for p in SOURCES};ck('all_sources_unchanged',after==before)
 output=dict(review_id='optional_feature_gap_review_20261102_v1',client_date='2026-11-02',created_at_utc=datetime.now(timezone.utc).isoformat(),scope='Readonly saved evidence and admission planning; no new data collection, source database query, indicators, actual labels, fit or score',all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,source_sha256_before=before,source_sha256_after=after,gaps=rows,important_distinctions=['可选特征没有准入不等于已经检验无效，也不阻塞其他独立工程或研究定义工作','已保存的16研究选择及M1/M2/M3负面结果不重置；本批缺口审查不是新试验','市场收盘特征工程可计算≠历史PIT认证；对照一致≠官方真值或独立上游','事件角色/原始观察/工程单元/价档不等于独立结果样本','当前覆盖以各自证据截止日为准，未刷新至2026-11-02','供应商原生价档、网页摘要、自建估计三轨分别管理；无采购/开户/联系/必能取得的承诺'],new_market_collection=False,new_actual_target_labels=False,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,cumulative_registered_variants_unchanged=16,old_protocol_or_risk_modified=False,formal_input_approved=False,runtime_usable=False)
 (DEST/'特征缺口审查.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 text=['# 可选特征与覆盖准入缺口审查','2026年11月2日，多伦多。本轮只核查既有本地证据，不刷新行情、不查询价格结果库、不生成标签、模型或评分。首版优先问题保持收盘后回落买入vs等待；不推定实际账户空仓、H=5或仓位。','## 核心判断','这15行是特征/资料准入缺口，不是15个新候选。除非未来实验明确需要该字段，可选缺口不作为阻塞全部其他研究的条件。所有正式历史、当前决策和运行门保持false；可继续来源审查、定义、版本/覆盖与最小补证规格。']
 for r in rows:
  text += ['\n## '+r['gap_id']+' '+r['name'],'- **用途位置：** '+r['role_in_confirmed_first_use_case'],'- **已有：** '+r['existing_evidence'],'- **还缺：** '+r['unresolved_evidence'],'- **影响：** '+'；'.join(r['affected_tasks']),'- **最小补证：** '+r['minimum_additional_evidence'],'- **如何补：** '+r['proposed_acquisition_and_verification'],'- **现在可独立做：** '+r['independent_work_possible_now'],'- **有边界替代：** '+r['limited_alternative'],'- **负责人/用户参与：** '+r['owner']+'；'+r['user_participation'],'- **验收：** '+r['acceptance'],'- **证据：** '+'、'.join('['+Path(p).name+']('+str(ROOT/p)+')' for p in r['source_paths'])]
 text+=['\n## 核查与保存',str(len(checks))+'/'+str(len(checks))+'项源引用、既有精确计数与准入边界核查通过；21源文件前后SHA一致。完整结构化矩阵、源SHA和限制见同目录JSON。没有新增事实数据或放行任何输入。']
 (DEST/'特征缺口审查.md').write_text('\n\n'.join(text)+'\n')
 print(json.dumps(dict(saved=True,gaps=15,checks=len(checks),sources=len(before),new_labels=0,new_scores=0),ensure_ascii=False))

if __name__=='__main__':main()
