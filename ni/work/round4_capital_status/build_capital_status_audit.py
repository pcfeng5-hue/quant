"""Read-only capital/ownership audit. No main database writes, no trading research."""
import sqlite3,json,pathlib,hashlib,datetime,collections
ROOT=pathlib.Path(__file__).resolve().parents[2]; BASE=ROOT/'outputs/高德红外数据库'; OUT=pathlib.Path(__file__).parent
con=sqlite3.connect(f'file:{BASE / "高德红外_2023起.sqlite"}?mode=ro',uri=True);con.row_factory=sqlite3.Row
checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
def evidence(art,pages,labels,visual=True):
 d=dict(con.execute('select * from announcement_documents where art_code=?',(art,)).fetchone());file=BASE/d['relative_path'];assert hashlib.sha256(file.read_bytes()).hexdigest()==d['sha256']
 ps=[]
 for p in pages:
  r=con.execute('select text,status from announcement_pages where art_code=? and page_number=? and source_sha256=?',(art,p,d['sha256'])).fetchone();assert r
  ps.append({'page_number':p,'full_page_text':r['text'],'extraction_status':r['status']})
 return {'art_code':art,'title':d['title'],'source_sha256':d['sha256'],'source_url':d['url'],'pdf_path':str(file),'provider_notice_date':d['notice_date'][:10],'page_numbers':pages,'original_labels':labels,'page_evidence':ps,'review_method':'full_relevant_page_text_and_selected_fields_visual' if visual else 'full_relevant_page_text','checked_at':checked_at,'first_public_timestamp_status':'unverified'}
reports=[
 ('2022-12-31','AN202304191585591293',77,3285181622,671309264,2613872358,'baseline_before_requested_range'),
 ('2023-06-30','AN202308301596833817',43,4270736108,872689371,3398046737,'matches_existing_provider_period'),
 ('2023-12-31','AN202404151630235965',79,4270736108,872123679,3398612429,'matches_existing_provider_period'),
 ('2024-06-30','AN202408261639461683',38,4270736108,872123677,3398612431,'matches_existing_provider_period'),
 ('2024-12-31','AN202504241661802959',71,4270736108,872123677,3398612431,'new_period_observation'),
 ('2025-06-30','AN202508251734295811',36,4270736108,872123677,3398612431,'new_period_observation'),
 ('2025-12-31','AN202604141821191363',69,4270736108,872123677,3398612431,'new_period_observation'),
 ('2026-06-30','AN202608250006749021',32,4270736108,872123677,3398612431,'new_period_observation')]
observations=[]
for date,art,p,total,limited,unlimited,reconciliation in reports:
 e=evidence(art,[p],['股份变动情况','本次变动后','有限售条件股份','无限售条件股份','股份总数','单位：股'])
 for n in [total,limited,unlimited]:assert f'{n:,}' in e['page_evidence'][0]['full_page_text']
 assert limited+unlimited==total
 observations.append({'observation_id':f'002414.SZ_capital_period_{date}','symbol':'002414.SZ','period_end':date,'total_shares':total,'limited_shares':limited,'unlimited_shares':unlimited,'unit':'shares','evidence_type':'reported_period_end_capital_snapshot','reconciliation':reconciliation,'daily_effective_date':None,'daily_float_pit_eligible':False,'historical_input_eligible':False,'evidence':[e]})
# One existing capital action, phases are evidence additions, never duplicate action counts.
phases=[
 {'phase':'proposal','phase_date':'2023-04-19','date_role':'board_approval_date','effective_date':None,'source':evidence('AN202304191585591299',[1,2,3],['预案','需提请公司2022年年度股东大会审议'])},
 {'phase':'shareholder_approval_authorization','phase_date':'2023-05-16','date_role':'shareholder_meeting_date','effective_date':None,'source':evidence('AN202305161586693421',[1,3,4],['审议通过《关于2022年度利润分配及资本公积金转增股本的预案》','关于年度利润分配增加注册资本并修订《公司章程》的议案'])},
 {'phase':'implementation_schedule','phase_date':'2023-06-20','date_role':'ex_date_and_transfer_listing_date','effective_date':'2023-06-20','source':evidence('AN202306121590866740',[1,2,3],['股权登记日与除权除息日','无限售条件流通股的起始交易日','最终股本变动情况以中国结算深圳分公司登记的股本结构为准'])},
 {'phase':'implemented_securities_registration_reported','phase_date':'2023-06-20','date_role':'actual_implementation_date_reported_in_halfyear','effective_date':'2023-06-20','source':evidence('AN202308301596833817',[43,44],['公司已于2023年6月20日实施完毕权益分派方案','已在中登公司办理了证券登记手续'])},
 {'phase':'business_registration_completed','phase_date':None,'date_role':'completion_date_not_explicit_only_近日','completion_no_later_than_document_date':'2023-06-28','effective_date':None,'registered_capital_cny':'4270736108','source':evidence('AN202306281591781833',[1,2],['近日，公司已完成注册资本变更及《公司章程》备案登记手续','注册资本：肆拾贰亿柒仟零柒拾叁万陆仟壹佰零捌圆人民币'])}]
group={'event_group_id':'002414.SZ_2022annual_distribution_20230620','event_type':'capital_reserve_transfer_and_cash_distribution','existing_corporate_action_art_code':'AN202306121590866740','new_independent_event_count':0,'record_date':'2023-06-19','ex_date':'2023-06-20','total_shares_before':3285181622,'total_shares_after':4270736108,'added_shares':985554486,'transfer_shares_per_10':'3','cash_cny_per_10':'1.3','source_stage_count':len(phases),'phases':phases,'historical_input_eligible':False}
transfers=[]
for art,stage,eventdate,confirmdate,count,holders in [
 ('AN202312281615153661',1,'2023-12-27','2023-12-28','476.4206',369),
 ('AN202412301641472101',2,'2024-12-27','2024-12-30','486.0874',363),
 ('AN202512301811330148',3,'2025-12-29','2025-12-30','952.5293',351)]:
 from decimal import Decimal
 e=evidence(art,[1,2],['办理完成','收到中国证券登记结算有限责任公司深圳分公司下发的《证券过户登记确认书》','非交易过户股份数量','万股'])
 assert count in ''.join(p['full_page_text'] for p in e['page_evidence'])
 transfers.append({'event_id':f'002414.SZ_employee_plan2022_transfer_stage{stage}','event_type':'employee_stock_plan_nontrade_transfer_completed','completion_date':eventdate,'registration_confirmation_received_date':confirmdate,'provider_notice_date':e['provider_notice_date'],'number_of_holders':holders,'shares_original':count,'shares_original_unit':'10000_shares','shares':int(Decimal(count)*10000),'unit':'shares','source_referenced_past_stages_do_not_duplicate':True,'total_capital_change':None,'unlimited_share_change':None,'limits':'完成非交易过户事实；并非新股发行、股份注销或限售股份总数增加的证据。未取得中登确认书本体。','historical_input_eligible':False,'evidence':[e]})
negative=[]
for art,year in [('AN202504241661802971',2024),('AN202604141821191382',2025)]:
 e=evidence(art,[1,2],['回购注销总额（元）','是否触及《股票上市规则》第9.8.1条第（九）项规定的可能被实施其他风险警示情形','否'])
 negative.append({'observation_id':f'002414.SZ_distribution_disclosure_{year}','classification':'explicit_negative_and_zero_disclosed_amount','report_year':year,'repurchase_cancellation_cny':{'current_year':'0','previous_year':'0','two_years_before':'0'},'unit':'CNY','specified_other_risk_warning_condition_triggered':False,'rule_label_as_disclosed':'股票上市规则第9.8.1条第（九）项','limits':'仅为该披露表格覆盖年度的回购注销金额及该项分红条件否定表述；不是所有风险警示、所有停复牌或全日状态历史证明。','historical_input_eligible':False,'evidence':[e]})
issues=[
 {'issue_id':'distribution_table_1share_vs_report','status':'unresolved','scope':'2023-06-20实施公告与2023-06-30中报','details':'实施公告表列限售872689370、无限售3398046738；中报期末限售872689371、无限售3398046737；总股本一致。实施公告明确最终股本变动情况以中登登记股本结构为准。差1股的精确生效日及原因未取得证据，不能将2023-06-30报告日机械当交易生效日。','evidence':[evidence('AN202306121590866740',[3],['注：最终股本变动情况以中国结算深圳分公司登记的股本结构为准']),evidence('AN202308301596833817',[43],['本次变动后'])]},
 {'issue_id':'yearend_to_next_report_opening_2shares','status':'unresolved','scope':'2023-12-31年报期末与2024半年度报告期初','details':'2023年报期末限售872123679、无限售3398612429；2024中报期初和期末均为限售872123677、无限售3398612431，变动栏均为横线。不能据此认定2024-06-30实际解锁2股，也不能回填2023-12-31覆盖原报告。','evidence':[evidence('AN202404151630235965',[79],['本次变动后']),evidence('AN202408261639461683',[38],['本次变动前','本次变动增减','本次变动后'])]},
 {'issue_id':'baseline_to_implementation_9748shares','status':'unresolved_effective_date','scope':'2022期末报告至2023权益分派实施前','details':'2022年报期末限售671309264、无限售2613872358；实施公告本次变动前限售671299516、无限售2613882106。供应商股本记录日期2023-06-12、差9748股，但本次核对未取得能证明该具体日为股份性质变更生效日的原件。','evidence':[evidence('AN202304191585591293',[77],['本次变动后']),evidence('AN202306121590866740',[3],['本次变动前'])]}]
a=json.load(open(BASE/'公告事件候选核对.json'))['evidence_candidates'];selected=[r for r in a if r['category']!='accounting_revision']
result={'audit_version':'round4_capital_status_v1','checked_at':checked_at,'scope':'2023-01-01至2026-10-13已有公告原件；2022期末作为前置基准。未改主数据库。','candidate_review':{'total_candidates':len(a),'capital_candidates':len(selected),'trading_status_candidates':sum(x['category']=='trading_status' for x in a),'resolved_candidates':[{'art_code':'AN202304191585591299','category':'capital_change','classification':'proposal_not_implemented_at_publication','merged_event_group_id':group['event_group_id'],'new_independent_event_count':0}]},'capital_period_observations':observations,'merged_existing_corporate_action':[group],'new_ownership_transfer_events':transfers,'negative_disclosure_observations':negative,'unresolved_capital_issues':issues,'general_reference_classifications':[{'reference':'2023预案引用2022已实施回购300942479.34元（不含交易费用）','classification':'prior_period_reference_not_2023_repurchase_cancellation','source_art_code':'AN202304191585591299','page_number':1},{'reference':'员工过户公告引用2022-12-26回购账户转入员工计划25469082股、5.91元/股','classification':'prior_period_reference_not_new_capital_or_2023_2025_repurchase','source_art_codes':[x['evidence'][0]['art_code'] for x in transfers]},{'reference':'金融工具会计政策模板与子公司注销','classification':'general_accounting_or_subsidiary_reference_not_issuer_stock_cancellation'}],'coverage_limits':['停复牌、ST及*ST全部历史仍未验证，已核交易日行情完整不能替代状态表。','没有发现相关标题或关键词不能证明事件不存在。','四个新增期间末股本观测不是新增4个股本变动事件。','期末观测没有逐日流通股本生效日；全部historical_input_eligible=false，不直接进入历史策略输入。','精确首次公开时间仍未核；notice_date只作供应商公告日。','未探测额外官方历史状态接口，不声明接口不存在或被禁止。']}
result['checks']={'capital_sums_all_match':all(x['limited_shares']+x['unlimited_shares']==x['total_shares'] for x in observations),'eight_period_observations':len(observations)==8,'four_new_periods':sum(x['reconciliation']=='new_period_observation' for x in observations)==4,'three_distinct_transfers':len(set(x['event_id'] for x in transfers))==3,'no_duplicate_capital_action':group['new_independent_event_count']==0,'all_historical_inputs_blocked':all(not x['historical_input_eligible'] for x in observations+transfers+negative)}
json.dump(result,open(OUT/'capital_status_audit.json','w'),ensure_ascii=False,indent=2)
print(json.dumps({'checks':result['checks'],'observations':len(observations),'new_periods':4,'new_ownership_events':len(transfers),'negative_disclosures':len(negative),'unresolved_issues':len(issues)},ensure_ascii=False))
