"""Compile existing evidence and bounded gap-closure criteria, not market data.

No market/target database is queried; no new label, fit, score or admission occurs.
The matrix is a review artifact, never a runtime whitelist.
"""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
from collections import Counter
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/时间执行与数据准入缺口矩阵_20261102'
ARCHIVE=Path('/Users/puchun/Documents/Codex/项目归档/ni/20261102_准入缺口矩阵完整保存')
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,data):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)

def control_rows():
 specs=[
 ('P01','回落、确认、期限及等待策略尚未冻结',
  '用户只确认首版优先收盘后回落买入vs等待；15组研究参数仍NULL，现金子仓为建议假设，不是已核实实际空仓。',
  ['回落资格和反转确认的可观测公式','主期限、最大等待、最迟入场和出卡时点','配置资金、NAV或实际清算及经济意义边界'],
  ['先由助手给出单一可解释设计及备选取舍，不能按旧分数选期限','用户确认使用期限/问题偏好，研究公式及证据由助手负责；另立协议后方可计算'],
  '全部必需参数有定义、单位、时间和版本；终点共同且晚确认不顺延；不把21个合成例的金额/5日默认为参数。',
  ['列决策项和取舍，不运行候选或真实标签'],
  ['T01','T02','T03','X04','V01'],
  {'required_now':False,'required_before_product_protocol_freeze':True,'minimum_private_evidence':'使用偏好及期限选择即可；不要求用户编程或设计指标公式'}),
 ('P02','结果资格、未知状态与共同样本分母',
  '已有12事件、五状态维度及21合成反例；旧469原价窗口不等于新动作标签已建立。',
  ['每类缺失/未触发/未成交/部分成交/未成熟的目标资格','费用后财富及期间风险的同口径标签和成熟时点','两路径同日起点、同终点和完整排除/覆盖账本'],
  ['另立标签规格，逐字段列信息和实际结果成熟时点','保留现金策略结果与NULL交易收益，价格方向/账户回撤/实现亏损分别定义'],
  '每个进入比较或被剔除的锚点均有事前理由；共同分母可对账；未知不填0、未成交不冒充零收益交易，NAV不冒充可实现现金。',
  ['先做状态/分母规则和合成边界，不能批量产生新真实目标'],
  ['P01','V01','R01'],{'required_now':False}),
 ('P03','预测验收、重叠样本与反复开发证据不足',
  '累计16=12描述信号+4模型定义；M1/M2/M3在各轮308/298/331同日样本未获升级依据。工程和独立复算通过不等于预测通过。',
  ['经济问题相匹配的统计/校准/成本/风险验收条件','考虑重复开发和样本相关的有效证据及不确定性设计','未用于调整规则的后续验证协议'],
  ['继续保留16项与全部失败，不直接跨轮排名或扫描剩余14列','路线决策若不能提出有证据的新假设，可继续补证或等待；后期阶段另登记'],
  '先冻结试验范围、共同基准、时间边界、校准与验收方法后才允许研究；2025/2026目标不因本矩阵开放，过去看过的年份不能称未见测试。',
  ['只复用已保存的审查结论和方法设计，不新增评分'],
  ['P01','P02'],{'required_now':False}),
 ('P04','风险、账户账本与旧模拟配置未迁移',
  '已确认条件性1万元意向、已实现亏损2000元暂停新增买入并复核、浮亏另列；旧模拟原型仍是5万元和旧口径，尚无完整真实执行验收。',
  ['单笔/单股/总仓位、含浮亏净值保护及恢复条件','费用归集、成本批次、人工交易归属、在途状态与账本对账','新配置独立验证而非覆盖旧5万元账簿'],
  ['由助手准备风险参数和账本适配设计，保留旧配置与历史数据','相应真实使用前用户确认风险边界及必要脱敏账户事实'],
  '研究/预测/账务/风控各自验收；不以不卖亏损绕开风险，也不擅自把用户已实现暂停线改成含浮亏线；未验收不进真实资金。',
  ['做账务映射与合成场景，当前不修改任何运行风险设置'],
  ['X05','X06','C01','V01'],
  {'required_now':False,'required_before_personalized_risk_use':True,'minimum_private_evidence':'未来风险偏好与脱敏必要账户字段；不需要密码/接口/经理回复'}),
 ('P05','持续接收、数据故障和版本恢复尚未验收',
  '原件、SHA、旧版本和全量归档已保存；夜间指针可接续。保存成功与设置任务不等于数据持续齐备、预测有效或已运行夜间研究。',
  ['字段首收/重收/修订的连续日志及质量拒绝规则','源失败、过期、断网、冲突、版本回滚和恢复验证','预测生成时版本不可覆盖、到期后才回填的流程'],
  ['以新目录建立采集/版本日志和拒答设计，先做本地合成故障测试','后续在公开或已获授权范围按实际选定字段留原件；不采购、换账户或密集重试绕过限制'],
  '每次有效出卡能恢复当时版本及截止；缺数据可暂停并解释原因；重启/新资金不自动解除风险暂停；前向日志不反向认证历史PIT。',
  ['目前只列首收日志、状态与恢复验收规格，不启动新市场采集'],
  ['T01','T02','D02','P02'],{'required_now':False})]
 rows=[]
 for gid,title,fact,missing,minimum,criterion,independent,deps,user in specs:
  rows.append(dict(gap_id=gid,title=title,source_reference_ids=['CONTROL:LABEL_CONTRACT','CONTROL:EVIDENCE','CONTROL:PROTOTYPE'],evidence_as_of_scope=fact,missing_evidence=missing,affected_claims=['首版买入vs等待的正式研究或使用'],minimum_completion_evidence=minimum,completion_criterion=criterion,independent_work_possible_now=independent,owner='助手负责定义、代码、核对及文档；用户只在列明使用偏好或账户私有用途前参与',user_participation=user,dependencies=deps,current_use_limit=dict(saved_engineering='定义、现有证据与合成检查；不是新实验许可',formal_historical_action_validation=False,current_decision_or_execution=False),all_formal_gates_remain_false=True))
 return rows

def validate(rows,refs):
 ids=[r['gap_id'] for r in rows]
 if len(ids)!=len(set(ids)):raise ValueError('Duplicate gap ID')
 byid={r['gap_id']:r for r in rows}
 required=['title','group','required_for','evidence_as_of_scope','missing_evidence','affected_claims','minimum_completion_evidence','completion_criterion','independent_work_possible_now','owner','user_participation','dependencies','current_use_limit','source_reference_ids']
 for r in rows:
  if any(k not in r or r[k] in (None,'',[]) for k in required if k!='dependencies'):raise ValueError('Incomplete gap or criterion')
  if any(k not in refs for k in r['source_reference_ids']):raise ValueError('Unknown evidence reference')
  if any(k not in byid for k in r['dependencies']):raise ValueError('Unknown dependency')
  if r['user_participation'].get('required_now') is not False:raise ValueError('This inventory cannot require user evidence now')
  if r['current_use_limit']['formal_historical_action_validation'] is not False or r['current_use_limit']['current_decision_or_execution'] is not False or r['all_formal_gates_remain_false'] is not True:raise ValueError('Gap matrix cannot grant approval')
  if r['blocks_all_research_now'] is not False:raise ValueError('Unclosed gap must not block independent review work')
 visited=set();active=set()
 def walk(key):
  if key in active:raise ValueError('Cyclic gap dependency')
  if key in visited:return
  active.add(key)
  for dep in byid[key]['dependencies']:walk(dep)
  active.remove(key);visited.add(key)
 for key in ids:walk(key)

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 core=read(ROOT/'work/gap_core_nov02/核心缺口审查.json')
 feature=read(ROOT/'work/gap_features_nov02/特征缺口审查.json')
 checks=[]
 def ck(name,ok,details=None):checks.append(dict(check=name,passed=bool(ok),details=details));assert ok,name
 ck('core_independent_review_passed',core['all_checks_passed'] and core['passed']==core['total'])
 ck('feature_independent_review_passed',feature['all_checks_passed'] and feature['passed']==feature['total'])
 # Feature review is copied in full; normalization follows the review's schema.
 refs={}
 for key,record in core['sources'].items():refs['CORE:'+key]=dict(record,review_namespace='CORE')
 feature_ref_for_path={}
 for i,(path,h) in enumerate(sorted(feature['source_sha256_before'].items()),1):
  key=f'FEATURE:S{i:02d}';refs[key]=dict(path=path,sha256=h,review_namespace='FEATURE');feature_ref_for_path[path]=key
 controlsources={'LABEL_CONTRACT':'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json','EVIDENCE':'outputs/研究证据与覆盖审查_20261101/研究证据与覆盖审查_v1.md','PROTOTYPE':'outputs/风控原型/原型说明与测试结果.md'}
 for key,path in controlsources.items():refs['CONTROL:'+key]=dict(path=path,sha256=sha(ROOT/path),review_namespace='CONTROL')
 ck('all_evidence_references_exist_and_match_hash',all((ROOT/r['path']).is_file() and sha(ROOT/r['path'])==r['sha256'] for r in refs.values()))
 sources=dict(read(ROOT/'outputs/预测问题与标签适用性审查_20261101/本轮交付核验.json')['protected_source_sha256'])
 oldqa=read(ROOT/'outputs/预测问题与标签适用性审查_20261101/本轮交付核验.json')
 for p,h in oldqa['delivery_sha256'].items():
  if p.startswith('outputs/预测问题与标签适用性审查_20261101/') or p.startswith('work/label_review_nov01/'):sources[p]=h
 sources.update({r['path']:r['sha256'] for r in refs.values()})
 for p in (ROOT/'outputs/风控原型').rglob('*'):
  if p.is_file():sources[str(p.relative_to(ROOT))]=sha(p)
 ck('all_immutable_sources_match_before_build',all(sha(ROOT/p)==h for p,h in sources.items()))
 rows=[]
 for group,data in [('core_temporal_execution',core),('optional_feature',feature)]:
  for original in data['gaps']:
   r=deepcopy(original);r['source_record']=deepcopy(original)
   if group=='core_temporal_execution':
    r['source_reference_ids']=['CORE:'+key for key in original['source_reference_ids']]
   else:
    r.update(title=original['name'],source_reference_ids=[feature_ref_for_path[p] for p in original['source_paths']],evidence_as_of_scope=original['existing_evidence'],missing_evidence=[original['unresolved_evidence']],affected_claims=original['affected_tasks'],minimum_completion_evidence=[original['minimum_additional_evidence'],original['proposed_acquisition_and_verification']],completion_criterion=original['acceptance'],independent_work_possible_now=[original['independent_work_possible_now']],user_participation=dict(required_now=original['user_required_now'],description=original['user_participation']),dependencies=['T01'],current_use_limit=dict(saved_engineering=original['current_use']['engineering_reconstruction'],formal_historical_action_validation=original['current_use']['formal_historical_input_approved'],current_decision_or_execution=original['current_use']['current_decision_approved']),all_formal_gates_remain_false=True,alternative_route_and_limit=original['limited_alternative'])
   r['group']=group
   r['required_for']='所声明首版范围的正式历史动作/净结果验证或个性化使用，具体按affected_claims；账户私有事实只在相应实际用途前核对' if group=='core_temporal_execution' else '只有选用该特征或后续问题时必须补证；可在另行登记范围中明确不使用，不能假造等价替代'
   r['blocks_all_research_now']=False;r['newly_closed_this_batch']=False
   r.setdefault('alternative_route_and_limit','可继续定义、整理既有资料及合成核对；未知不能填0或升级准入，替代路线需保留假设和不同数据身份')
   rows.append(r)
 for r in control_rows():
  r.update(group='research_and_use_control',required_for='只有计划进入相应新研究、正式预测或账户使用阶段时必须完成；不阻止当前文档与补证设计',blocks_all_research_now=False,newly_closed_this_batch=False,alternative_route_and_limit='保留现有工程成果；无足够证据时允许停止晋级，不因日期或文件数量强行实验')
  rows.append(r)
 validate(rows,refs)
 ck('all_rows_complete_unique_nonpromoting_and_dependencies_valid',True)
 negative=[]
 for kind in ['duplicate','missing_evidence','unknown_reference','promote','require_user_now','unknown_dependency','cycle','block_all']:
  bad=deepcopy(rows)
  if kind=='duplicate':bad.append(deepcopy(bad[0]))
  if kind=='missing_evidence':bad[0]['minimum_completion_evidence']=[]
  if kind=='unknown_reference':bad[0]['source_reference_ids']=['UNREGISTERED']
  if kind=='promote':bad[0]['current_use_limit']['formal_historical_action_validation']=True
  if kind=='require_user_now':bad[0]['user_participation']['required_now']=True
  if kind=='unknown_dependency':bad[0]['dependencies']=['unknown']
  if kind=='cycle':bad[0]['dependencies']=[bad[0]['gap_id']]
  if kind=='block_all':bad[0]['blocks_all_research_now']=True
  rejected=False
  try:validate(bad,refs)
  except ValueError:rejected=True
  ck('negative_'+kind+'_rejected',rejected);negative.append(kind)
 # Index recorded definitions, not a newly executable admission configuration.
 matrix=dict(review_id='002414_temporal_execution_input_gap_review_20261102_v1',client_date='2026-11-02',status='review_inventory_not_runtime_admission',user_confirmed_first_use_case='收盘后判断回落时该买入还是继续等待',matrix_row_count=len(rows),counts_by_group=dict(Counter(r['group'] for r in rows)),dependency_semantics='Dependencies apply to admission of the declared affected use, never to independent source collection or document work; unknown account fees do not prevent public market-data preparation',gaps=rows,new_gaps_closed=0,new_market_data_acquired=False,new_models_fitted=0,new_target_labels_generated=0,new_scores_calculated=0,cumulative_registered_variants=16,formal_model_input_approved=False,runtime_usable=False,current_forecast_generated=False,outcomes_2025_2026_opened=False)
 write(OUT/'完整缺口矩阵_v1.json',matrix)
 write(OUT/'来源索引与SHA256.json',dict(evidence_references=refs,protected_source_sha256=sources,official_online_observation=dict(path='work/gap_matrix_nov02/官方规则核查原响应.json',sha256=sha(WORK/'官方规则核查原响应.json'),url='https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf',client_date='2026-11-02',raw_response_saved_at_utc=datetime.fromtimestamp((WORK/'官方规则核查原响应.json').stat().st_mtime,timezone.utc).isoformat(),network_completion_timestamp_precisely_logged=False,publisher='深圳证券交易所',version='2026年修订',unit='不适用（制度条文）',kind='Fresh parsed official rule-page observation only; not a new binary download or complete historical rule chain')))
 for folder,filename,label in [('gap_core_nov02','核心缺口审查','核心缺口独立审查'),('gap_features_nov02','特征缺口审查','特征缺口独立审查')]:
  for ext in ['json','md']:shutil.copy2(ROOT/f'work/{folder}/{filename}.{ext}',OUT/f'{label}.{ext}')
 # Full details preserve evidence/unknown/affected use/minimum/acceptance/owner.
 detail=['# 完整缺口矩阵与逐项补证条件','2026-11-02。每条只描述待补证据及合格条件；不是已补齐或已准入。路径以项目根为准。']
 for r in rows:
  detail += ['\n## '+r['gap_id']+' '+r['title'], '**已有证据及范围：** '+r['evidence_as_of_scope'], '**何时必须补：** '+r['required_for']]
  for title,key in [('尚缺什么','missing_evidence'),('影响什么','affected_claims'),('最小补证与获取办法','minimum_completion_evidence'),('现在可独立推进','independent_work_possible_now')]:
   detail += ['**'+title+'：**\n\n'+'\n'.join('- '+str(s) for s in r[key])]
  detail += ['**达到什么程度才算本项补证合格：** '+r['completion_criterion'],'**责任：** '+r['owner'],'**用户参与：** '+json.dumps(r['user_participation'],ensure_ascii=False),'**用途限制：** '+json.dumps(r['current_use_limit'],ensure_ascii=False),'**可选/替代路线及限制：** '+r['alternative_route_and_limit'],'**所声明用途的放行依赖（不是采集先后或独立文档工作的前置）：** '+('、'.join(r['dependencies']) or '无其他行依赖；仍受用途准入约束'),'**证据位置：**\n\n'+'\n'.join('- '+key+'：['+refs[key]['path']+']('+str(ROOT/refs[key]['path'])+')' for key in r['source_reference_ids'])]
 (OUT/'逐项补证与验收细则.md').write_text('\n\n'.join(detail)+'\n')
 brief=['| 编号 | 缺口 | 已有证据/限制 | 最小补证与合格条件 |','|---|---|---|---|']
 for r in rows:
  brief.append('| '+' | '.join([r['gap_id'],r['title'],r['evidence_as_of_scope'].replace('|','/'),('；'.join(r['minimum_completion_evidence'])+'。验收：'+r['completion_criterion']).replace('|','/')])+' |')
 (OUT/'缺口矩阵总表.md').write_text('# 缺口矩阵总表\n\n每条的责任、来源SHA、用途、替代方案与依赖见[逐项细则](./逐项补证与验收细则.md)；这里不因已有数据就放行。\n\n'+'\n'.join(brief)+'\n')
 # Templates request no user data in this batch; all fields stay NULL.
 private_template=dict(required_now=False,not_a_request_for_credentials=True,stage='仅供后续相应个性化使用前参考，不是当前任务前置',account_fee_fields={k:None for k in ['effective_dates','commission_rate','minimum_charge','included_fee_components','partial_fill_aggregation','rounding','redacted_statement_reference']},account_position_fields={k:None for k in ['cash_available','position_quantity','sellable_quantity','purchase_lots','cost_basis','unsettled_or_pending_orders']},corporate_action_fields={k:None for k in ['actual_cash_receipt','applicable_withholding','eligible_quantity','rights_receivable_status']},use_preferences={k:None for k in ['horizon_preference','maximum_wait_preference','allocation_and_risk_limits','NAV_or_cash_endpoint']},forbidden_to_request=['账户密码','验证码','完整账号','远程登录权限'],user_provides_only_if_needed_and_redacted=True)
 write(OUT/'后续脱敏资料字段模板.json',private_template)
 worklist='''# 最小补证作业清单 v1

2026-11-02。以下均为后续待办，不是本轮已经取得的新数据，也不代表已决定新实验路线。第4份路线决策尚未完成。

1. **先建立必要字段的时点和版本证据表。** 助手负责逐字段列源版本、公布/接收/修订时间、时区、未知和证据，先用已有原件定位。无法恢复的历史版本明确保留未知；前向首收日志不能追认过去PIT。对应T01/T02、P05。
2. **续接正确交易所的计划日历和逐日交易条件。** 助手按官方通知/生效版本核开休市、ST/停复牌/临停、限价参考与数量规则；保留旧日历机器件与更早MD的差别，不把正常成交量当正常状态。对应T03、X01—X03、D02。
3. **明确收益能算到哪一级。** 助手先做佣金包费/最低额/舍入模板和权益现金流、负债、部分成交/晚入场边界；真实精确净结果及账户适用时才需用户脱敏费率/有限对账，不能靠费用场景冒充实际。对应C01—C03、X04—X06、V01。
4. **由研究方给出参数与适用范围方案。** 用户只需以后确认期限/等待/风险等偏好，不需要编程或自己发明信号。15组待定参数仍NULL，现金子仓不是实际空仓事实。对应P01/P02/P04。
5. **可选特征按用途补证。** 先说明是否真的使用，再补筹码、成员、事件、新闻等所需证据。未选入的可从新协议范围明确排除；摘要/估计/代理不能冒充原生分布、真实机构持仓或全行业成员。对应全部特征行，具体ID以矩阵为准。
6. **最后再作路线决策。** 区分数据不能准入、已有候选没有增量、工具未验收三类问题；保留16项与全部失败，不用数据数量或技术检查代替预测验收。本清单不执行新模型、不打开2025/2026目标，也不转入模拟或真实资金。对应P03及后续第4份审查。

当前用户无需提供材料、联系证券经理或寻找不存在渠道。若后续确需账户私有信息，只按[脱敏字段模板](./后续脱敏资料字段模板.json)核最小必要字段，不能要求密码、验证码或账户控制权。
'''
 (OUT/'最小补证作业清单_v1.md').write_text(worklist)
 report=f'''# 时间、执行与数据准入缺口矩阵 v1

2026年11月2日，多伦多。完成四份有限审查中的第3份，围绕用户确认的“收盘后判断回落时该买入还是继续等待”。本批只整理证据及补证方案，没有补齐全部数据、生成真实标签、拟合模型或评分；也没有因完成矩阵放行任何输入。

## 结论

已建立{len(rows)}项缺口：{len(core['gaps'])}项时点与执行核心项、{len(feature['gaps'])}项条件性特征项、5项研究与使用控制。每项列已有证据、未知、受影响用途、最小补证、合格条件、责任、用户参与、用途限制和依赖。矩阵整理完成不代表这些缺口解决，本批新增已关闭数据缺口为0。

当前可继续的是原件整理、定义、合成检查及已登记旧工程结果的受限解释。正式历史动作/费用后结果验证和当前预测的准入仍未通过；未准入的数据不能填0、按正常状态代替或因已存原件升级。另一方面，可选特征没有补齐也不阻止独立的底座整理；未来若明确不用某特征，要在新范围中登记，而非用不等价代理顶替。

## 最需要先分清的证据

| 部分 | 现有证据 | 尚不能据此声称 | 最小补证方向 |
|---|---|---|---|
|字段时间与版本|原件、抓取时间和版本多数已留存|2026取得的历史回看版本在2023年当时已经可见|字段级首次可得/修订及as-of版本证据；恢复不了就限定用途或转明确前向方案|
|日历与交易状态|日历机器核验件914日止10/15；交易条件915日止10/16|行情止10/21就代表所有日历、ST、临停和限价同步更新|正确交易所的计划日历及有效规则；逐日状态与官方限价证据|
|费用与执行|有公共费用候选、未知账户佣金字段和合成例子|开盘/收盘/触价保证成交，或成本场景就是实际净结果|明确订单/部分未成交/可卖数量；实际费率、最低收费、包费和舍入适用证据|
|共同终点财富|已有NAV、实际清算、应收和负债的设计|能估值就能卖出，或等待可多给几天|同资金、同终点、现金/NAV分开；权益/应收/未付税费和失败清算保留|
|研究与风险|16项旧定义、三轮未获升级结论、旧风险原型|模型实现正确等于可靠买点，或旧5万元模拟配置已迁移|15组参数、目标资格、验收和账户风险另行冻结核验|

日历机器件是10/15及914日，旁边同名交易日历MD仍保留10/13和912日的旧说明；这是版本差异，均保留，不覆盖。对应T03的证据路径和SHA可以直接追溯。月报中未查到停牌记录不等于逐日全天正常，官方日限价/执行/完整成本认证仍未完成。

行情统一快照是2022-01-04—2026-10-21共1160个日期，含242个2022预热和918个2023起研究日；指标实际可计算范围还受已知除权、2022未知原价断点及各自预热影响。它不是1160个独立交易样本，更不是全部字段都已可用于当前决策。

## 全部矩阵与逐项细则

- [缺口矩阵总表](./缺口矩阵总表.md)：全部{len(rows)}项的已有范围、缺什么、怎样补及合格条件。
- [逐项补证与验收细则](./逐项补证与验收细则.md)：受影响用途、助手/用户分工、独立可推进项、替代限制、依赖与逐源位置。
- [完整机器可读矩阵](./完整缺口矩阵_v1.json)：保留独立审查原记录，不是可执行白名单。
- [来源索引与SHA256](./来源索引与SHA256.json)：旧来源与本次官方解析观察分开，哈希不代表内容全正确或覆盖全完整。

## 条件性输入为什么单列

筹码摘要915日止10/16、完整供应商原生价档0日；摘要存在版本差异、许多日期只观察一次。自建估计另有未知初始化、换手分母和算法假设。三者分别管理，不能把“获利比例”当上涨概率或真实持有人分布。补摘要重复性不等于取得原生价档；取得原生价档也仍需查时点和版本。

市场环境已有15候选定义与1辅助，工程ready不等于正式PIT或预测有效；只评分过一个深成指候选M3且未升级，其余14列不在本批扫描。既有上证收盘冲突0.01点及28个特征单元隔离保留；指数成交量单位不因收盘一致获认证。399967只能是军工价格背景代理，历史成员、权重和行业宽度未知。

事件为67个日期角色、59个经济事件编号，全部历史事件/倒数准入仍未取得；46个月中5个月有逐月官方通知，41个月仍规则候选，事后交割结果不能前置。企业除权、代派款和用户实际到账分开，不能拆成独立样本。公告312原件/4253页与10个政策样本不代表完整新闻库，OCR和首次公开/修订仍有缺口。资金流、大宗、席位和定期持股不能解释为机构真实账户实时买卖。

这些未准入或尚未测试的输入，与“M1/M2/M3已经测试但没有改善”的证据是两回事。补证顺序按问题需要和可追溯性确定，不能为解释已知赢家而挑事件或股票。分钟/逐笔和盘中做T属于后续范围，不作为当前日线定义审查的前置。

## 收盘后仍要核字段可得与执行渠道

本批重新读取了深交所2026版官方规则的解析页面，原始本地PDF和历史版本链仍按旧索引保存。现行3.6节存在盘后固定价格交易，盘后量额结束后才并入当日总量，故不能统一假定15:00全部日量已齐；也不能笼统说收盘后绝无同收盘价通道。用户渠道、实收到达、排队和实际成交仍未核验，当前没有采用该通道，也不能把2026制度回填2023—2024。[深交所交易规则](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)

## 谁负责、用户何时需要参与

公开原件定位、版本/日历/状态核对、编码、字段定义、合成验证和报告由助手负责。用户当前不需要写代码、找数据渠道、联系亲属或提供账户材料。后续相应精确账户费后结果或个性化使用前，可能需要脱敏费率/有限成交对账、现金持仓与可卖批次、实际分红税费；期限与风险偏好也需确认。这些是后续用途前提，不是完成本矩阵的前置。

已提供[后续脱敏字段模板](./后续脱敏资料字段模板.json)，全部值为NULL，不请求密码、验证码、完整账号或账户控制权，也不根据人在加拿大推断税务身份。

已确认的1万元条件性试验意向、累计已实现亏损2000元暂停新增买入并复核、浮亏单列不变；其他仓位/净值保护待确认。旧5万元账簿及旧配置保留，不默默迁移，不购买或使用真实资金。

## 如何补、补到哪一步才进入研究

[最小补证作业清单](./最小补证作业清单_v1.md)按时点版本、日历交易条件、费用/权益/执行、参数适用范围、可选特征和验收列出六组后续作业，每项对应矩阵ID；这些作业目前是计划，没有被本批视为执行完成。

用途层次要分别判断：工程准备和合成检查；明确假设且另行登记的回顾性诊断；正式历史动作验证；当前个人决策。矩阵依赖关系是针对所声明用途的放行条件，不是采集先后；例如账户费用未知不妨碍助手整理公共行情与日历。前两层的技术检查或受限例外不能升级后两层。能补到哪里、哪些历史事实无法恢复，要在下一份路线决策中如实判断；缺口不能用填零、统一滞后或假定成交绕过。

## 本批完成与下一断点

完成的是这份矩阵、来源核对、依赖与补证条件、责任及最小资料模板。数据覆盖沿用旧快照；没有刷新行情、关闭数据缺口、生成真实标签、拟合/评分模型或当前预测。2025/2026后期目标继续隔离，累计16和全部失败保留。

下一批完成第4份“下一阶段路线决策记录”：用前三份审查判断先补什么、是否能提出单一可检验新假设、或应继续补证/等待。**本矩阵不提前宣布路线已选、新模型必须开跑或后期目标可开放。** [续作断点](./本轮状态与续作断点.json)。全量归档完成以项目外{ARCHIVE/'归档校验结果.json'}为准，旧包不删。
'''
 (OUT/'时间执行与数据准入缺口矩阵_v1.md').write_text(report)
 ck('readable_matrix_and_detail_have_every_ID',all(r['gap_id'] in (OUT/'缺口矩阵总表.md').read_text() and r['gap_id'] in (OUT/'逐项补证与验收细则.md').read_text() for r in rows))
 ck('no_user_material_is_required_now',all(r['user_participation']['required_now'] is False for r in rows) and not private_template['required_now'])
 ck('all_immutable_sources_match_after_build',all(sha(ROOT/p)==h for p,h in sources.items()))
 write(OUT/'本轮构建核验.json',dict(all_checks_passed=True,passed=len(checks),total=len(checks),checks=checks,protected_source_sha256=sources,matrix_rows=len(rows),newly_closed_data_gaps=0,new_real_labels_models_scores=0))
 labelcfg=read(ROOT/'outputs/预测问题与标签适用性审查_20261101/审查范围与设计合同.json')
 summary=dict(cumulative_registered_variants=16,review_steps_completed=3,review_steps_remaining=1,matrix_rows=len(rows),groups=matrix['counts_by_group'],newly_closed_data_gaps=0,new_market_data_acquired=False,new_real_market_targets=0,new_model_variants=0,new_models_fitted=0,new_scores_calculated=0,outcomes_2025_2026_opened=False,phase_promotion_approved=False)
 state=dict(client_date='2026-11-02',origin='direct_human_request_not_scheduled_heartbeat',research_stage=5,status='step_3_gap_matrix_built_awaiting_correspondence_audit',review_package_step=3,review_package_step_completed=False,review_package_steps_total=4,archive_summary=summary,
  completed=['Complete gap matrix, source/coverage distinctions, minimum evidence and acceptance criteria built','Responsibility, optional feature scope, independent work and private-field template prepared'],partial=['Final correspondence audit and frozen archive pending','Actual gap closure, parameter freeze and formal admission are not completed'],blocked=['Formal historical first-availability/trading-state/cost/fill evidence and predictive acceptance unresolved'],
  user_confirmed_first_use_case=labelcfg['user_confirmed']['first_use_case'],pending_freeze=labelcfg['pending_freeze'],cumulative_registered_variants=16,new_registered_model_variants=0,new_real_market_targets=0,new_models_fitted=0,new_scores_calculated=0,newly_closed_data_gaps=0,new_market_data_acquired=False,outcomes_2025_2026_opened=False,current_forecast_generated=False,model_input_approved=False,runtime_usable=False,phase_promotion_approved=False,old_protocol_or_risk_modified=False,counts_as_completed_nightly_batch=False,
  source_hashes=sources,next_checkpoint=['Complete only the next-stage route decision record using the three completed reviews; decide whether to prioritize bounded evidence closure, reformulate, wait, or justify a single separately registered hypothesis','Do not treat matrix completion as data gap closure or formal admission; fifteen parameter groups remain unconfirmed; do not start a new model by default','Keep all 16 prior variants and negative outcomes, 2025/2026 target isolation, existing risk settings and no scanning the remaining 14 prepared columns'],archive_verification_path=str(ARCHIVE/'归档校验结果.json'),confirmed_test_intent_cash_cny=10000,confirmed_pause_cumulative_realized_loss_cny=2000,floating_pnl_separate=True,real_trading_authorized=False)
 write(OUT/'本轮状态与续作断点.json',state)
 print(json.dumps(dict(built=True,checks=len(checks),matrix_rows=len(rows),protected_sources=len(sources),new_data_gaps_closed=0),ensure_ascii=False))

if __name__=='__main__':main()
