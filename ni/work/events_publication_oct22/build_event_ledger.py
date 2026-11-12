from pathlib import Path
import collections,datetime,hashlib,html,json,re,sqlite3
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
NOW=datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text())
def save(n,x):(P/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def plain(s):
 s=re.sub(r'<script\b.*?</script>',' ',s,flags=re.S|re.I);s=re.sub(r'<style\b.*?</style>',' ',s,flags=re.S|re.I)
 return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',s))).strip()
def meta(s,k):
 m=re.search(r'<meta\s+name=[\"\']'+re.escape(k)+r'[\"\']\s+content=[\"\']([^\"\']*)',s,re.I)
 return html.unescape(m.group(1)) if m else None
stage=read(P/'stage_manifest.json');old=read(ROOT/'work/disclosure_time_round6/announcement_time_ledger.json')
em={x['record_id']:x['payload'] for x in stage['catalogues']['eastmoney']['records']}
cn={x['record_id']:x['payload'] for g in ['cninfo_fulltext','cninfo_ir'] for x in stage['catalogues'][g]['records']}
reqs={}
for req in stage['results']:
 for row in req.get('records',[]):reqs[row.get('art_code',row.get('announcementId'))]={k:req.get(k) for k in ['name','url','retrieved_at','completed_at','sha256','raw_path','snapshot_id']}
ann=[];diff=[]
for o in old:
 art=o['art_code'];id=o['official_announcement_id'];a=em.get(art);b=cn.get(id)
 if a is None or b is None:continue
 display=a.get('display_time');previous=o['eastmoney_display_time_raw']
 if display!=previous:diff.append(dict(art_code=art,title=o['title'],field='display_time',previous=previous,current=display,first_publication_semantics_certified=False))
 doc=ROOT/'outputs/高德红外数据库'/o['local_pdf']['relative_path']
 ann.append(dict(record_id=art,official_announcement_id=id,title=o['official_title'],category=o['category'],symbol='002414.SZ',announcement_date=o['official_disclosure_day'],source_timestamp_raw=dict(cninfo_announcementTime_ms=b.get('announcementTime'),cninfo_storageTime=b.get('storageTime'),eastmoney_notice_date=a.get('notice_date'),eastmoney_display_time=display,eastmoney_eiTime=a.get('eiTime'),eastmoney_sort_date=a.get('sort_date')),source_timezone_declared={'cninfo_normalization':'Asia/Shanghai; midnight treated as date label','eastmoney':'not_explicit_in_response'},source_request_current=dict(official=reqs.get(id),provider=reqs.get(art)),retrieved_at=reqs[id]['retrieved_at'],local_original_path=str(doc),local_original_sha256=h(doc),official_original_url='https://static.cninfo.com.cn/'+b['adjunctUrl'],historical_first_publication_timestamp=None,historical_first_publication_status='unknown_no_historical_first_seen_log',earliest_model_use_timestamp=None,historical_input_eligible=False,availability_status='disclosure_day_known_minute_and_original_version_not_certified',original_identity_match_to_previous=h(doc)==o['local_pdf']['source_sha256'],previous_time_audit_reference=str(ROOT/'work/disclosure_time_round6/announcement_time_ledger.json'),research_categories=[name for name,pattern in [('results_or_financial','业绩|年度报告|季度报告|半年度报告|财务'),('dividend_or_capital','分配|分派|股本|回购|股份|减持|增持|股权'),('trade_status','停牌|复牌|风险警示|退市|异常波动')] if re.search(pattern,o['title'])]))
save('announcement_time_ledger_current.json',ann);save('provider_timestamp_revisions_vs_oct15.json',diff)
# Acquired official original HTMLs. Timestamp metadata is evidence, never a certified first-seen clock.
manifest=read(P/'event_source_manifest.json');eventrows=[];sources=[]
newpol=[]
for r in manifest:
 if not r.get('accepted') or not r['name'].startswith('csrc'):continue
 s=Path(r['raw_path']).read_text(errors='replace');t=plain(s)
 title=meta(s,'ArticleTitle');pd=meta(s,'PubDate');day=(pd or '')[:10]
 typ='policy_speech' if 'speech' in r['name'] else 'policy_release' if 'transfer' in r['name'] else 'public_consultation'
 effective='2026-12-01' if typ=='policy_release' else None
 newpol.append(dict(event_id='policy-'+r['name'],event_type=typ,title=title,event_date=day,date_role='official_page_publication_day',effective_date=effective,source_timestamp_raw=pd,source_timestamp_semantics='current_HTML_PubDate; page-generation metadata same value; no immutable first-publication guarantee',timestamp_timezone='not_explicit_in_HTML',historical_first_publication_timestamp=None,earliest_model_use_timestamp=None,historical_input_eligible=False,first_publication_status='unverified_current_metadata_only',publication_date=day,source_level='official_original_html',source_url=r['url'],source_sha256=r['sha256'],raw_path=r['raw_path'],retrieved_at=r['retrieved_at'],economic_episode_id='policy-'+r['name'],scope='capital_market_general; not attributed to stock-specific effect',effect_analysis_performed=False,reposts_counted_as_independent_events=False))
 # Parse body into our own compact evidence index; full raw original retained.
 sources.append(dict(source_url=r['url'],sha256=r['sha256'],raw_path=r['raw_path'],title=title,publication_date=day,pubdate_raw=pd,body_excerpt_hash=hashlib.sha256(t.encode()).hexdigest(),retrieved_at=r['retrieved_at']))
oldpol=read(ROOT/'outputs/高德红外数据库/政策样本采集记录.json')
for r in oldpol:
 eventrows.append(dict(event_id='policy-'+r['document_id'],event_type='policy_sample',title=r['title'],event_date=r.get('issue_date') or (r.get('publication_display') or '')[:10] or None,date_role='issue_date_not_publication_time' if r.get('issue_date') else 'page_display_day',effective_date=r.get('effective_date'),source_timestamp_raw=r.get('publication_display'),historical_first_publication_timestamp=None,earliest_model_use_timestamp=None,historical_input_eligible=False,first_publication_status='unverified_current_metadata_only',source_level='official_or_government_repost_existing_sample',source_url=r['url'],source_sha256=r['sha256'],raw_path=str(ROOT/'outputs/高德红外数据库'/r['relative_path']),retrieved_at=r['retrieved_at'],economic_episode_id='policy-'+r['document_id'],note=r.get('note'),effect_analysis_performed=False,reposts_counted_as_independent_events=False))
eventrows.extend(newpol);save('new_official_policy_samples.json',newpol)
# Three existing corporate actions expanded into date-role records; share one episode per action.
div=read(ROOT/'work/dividend_event_dates_oct15/event_dates.json')
for r in div['corporate_actions']:
 for role in ['record_date','ex_date','official_delegated_cash_distribution_date','capital_transfer_account_credit_date','transferred_unrestricted_shares_first_trading_date']:
  if not r.get(role):continue
  eventrows.append(dict(event_id=r['art_code']+'-'+role,event_type='corporate_action_date',symbol='002414.SZ',title=r['source_notice_title'],event_date=r[role],date_role=role,economic_episode_id=r['art_code'],attributable_period=r['attributable_period'],gross_cash_cny_per_10_shares=r['cash_cny_per_10_shares_gross'],transfer_shares_per_10=r['transfer_shares_per_10'],publication_date=r['provider_implementation_notice_date_candidate'],historical_first_publication_timestamp=None,earliest_model_use_timestamp=None,historical_input_eligible=False,first_publication_status='implementation_terms_verified_exact_first_publication_unverified',source_level='original_PDF_dates_previously_text_and_visually_verified',source_url=r['source_url'],source_sha256=r['source_sha256'],raw_path=r['source_pdf_path'],retrieved_at=next((o['local_pdf']['retrieved_at'] for o in old if o['art_code']==r['art_code']),None),date_scope=r['official_cash_distribution_scope'] if role=='official_delegated_cash_distribution_date' else None,user_account_actual_receipt_verified=False,effect_analysis_performed=False))
# Retain historical formula dates and do not upgrade based merely on today's fact that time has passed.
exp=read(ROOT/'work/expiry_calendar_oct15/historical_expiry_calendar_candidates.json')+read(ROOT/'work/expiry_calendar_oct15/future_expiry_calendar_candidates.json')
notices=read(ROOT/'work/expiry_calendar_oct15/verified_monthly_notices.json');by={x['month']:x for x in notices}
newnotice=[]
for r in manifest:
 if not r.get('accepted') or not r['name'].startswith('cffex_october'):continue
 s=Path(r['raw_path']).read_text(errors='replace');t=plain(s)
 m=re.search(r'IF2610等合约于(\d{4})年(\d{1,2})月(\d{1,2})日进行交割',t)
 if not m or not all(c+'2610' in t for c in ['IF','IH','IC','IM','IO','MO','HO']):continue
 day='-'.join([m[1],m[2].zfill(2),m[3].zfill(2)])
 n=dict(month=day[:7],event_date=day,event_type='CFFEX_index_derivatives_expiry_delivery',applicable_instruments=['IF','IH','IC','IM','IO','MO','HO'],notice_kind='actual_delivery_result',source_level='official_monthly_notice',source_url=r['url'],publication_date=day,publication_time=None,first_publication_time_certified=False,retrieved_at=r['retrieved_at'],source_sha256=r['sha256'],raw_path=r['raw_path'],historical_input_eligible=False,delivery_settlement_prices={'IF_IO':'4162.02','IC':'6805.74','IM_MO':'6716.62','IH_HO':'2755.35'},settlement_price_unit='index_points',availability_note='Actual result publication is post-event evidence; not an advance expiry reminder.')
 newnotice.append(n);by[n['month']]=n
for r in exp:
 n=by.get(r['month']);date=n['event_date'] if n else r.get('event_date_candidate')
 ep=dict(event_id=r['event_id'],event_type=r['event_type'],event_date=date,date_role='futures_delivery_options_expiry_same_economic_date',month=r['month'],instruments=r['instruments'],economic_episode_id=r['event_id'],source_level='official_monthly_notice' if n else 'rule_derived_candidate',official_monthly_notice_verified=bool(n),event_date_certainty='official_notice_date_verified' if n else 'formula_candidate_not_monthly_verified',publication_date=n['publication_date'] if n else None,historical_first_publication_timestamp=None,earliest_model_use_timestamp=None,historical_input_eligible=False,first_publication_status='unknown_clock_and_historical_version' if n else 'not_applicable_rule_candidate_not_official_monthly_evidence',source_url=n['source_url'] if n else None,source_sha256=n['source_sha256'] if n else None,raw_path=(n['raw_path'] if Path(n['raw_path']).is_absolute() else str(ROOT/'work/expiry_calendar_oct15'/n['raw_path'])) if n else None,retrieved_at=n['retrieved_at'] if n else None,rule_sources=r.get('rule_sources'),holiday_roll_candidate=r['holiday_roll_candidate'],event_date_on_or_before_requested_cutoff=date<='2026-10-22',event_occurrence_confirmed=bool(n and n['notice_kind']=='actual_delivery_result'),notice_kind=n['notice_kind'] if n else None,effect_analysis_performed=False)
 if n and 'delivery_settlement_prices' in n:ep['delivery_settlement_prices']=n['delivery_settlement_prices']
 eventrows.append(ep)
save('new_official_expiry_notice.json',newnotice)
# Date granularity and source provenance are explicit; preserve nulls.
eventrows.sort(key=lambda x:(x.get('event_date') or '',x['event_id']))
save('normalized_events.json',eventrows)
# Reposts of the October notice/speech all share one episode, stored as discovery references only.
save('repost_deduplication_notes.json',dict(rule='same issuer + original title + notice number/event date = one economic episode; repost clocks cannot substitute issuer publication clock',clusters=[dict(economic_episode_id='CFFEX-index-expiry-2026-10',official_original='http://www.cffex.com.cn/cn/jystz/20261016/48692.html',discovered_reposts=['https://finance.eastmoney.com/a/202610163898464392.html','https://www.eastmoneyfutures.com/pages/notice-detail.html?channelID=936&newscode=202610163898464392','https://finance.sina.com.cn/money/future/roll/2026-10-16/doc-inivmazq1673705.shtml'],reposts_acquired_as_raw=False,reposts_independent_event_count=0)]))
# Verify all referenced raw catalogue/official sources and existing original identity.
checks=[]
def ck(name,value,detail=None):checks.append(dict(name=name,passed=bool(value),detail=detail))
ck('three_catalogues_complete',all(x['complete'] for x in stage['catalogues'].values()))
ck('312_announcement_rows_mapped_unique',len(ann)==312 and len({x['record_id'] for x in ann})==312)
ck('official_catalogue_ids_match_mapped',set(cn)=={x['official_announcement_id'] for x in ann})
ck('all_catalogue_raw_hashes_match',all(h(Path(x['raw_path']))==x['sha256'] for x in stage['results'] if x.get('raw_path')))
ck('all_new_official_html_hashes_match',all(h(Path(x['raw_path']))==x['sha256'] for x in manifest if x.get('raw_path')))
ck('all_announcement_originals_unchanged',all(x['original_identity_match_to_previous'] for x in ann))
ck('three_new_policy_originals',len(newpol)==3)
ck('october_delivery_official_original_verified',len(newnotice)==1 and newnotice[0]['event_date']=='2026-10-16')
ck('46_expiry_months_5_official_41_formula',len(exp)==46 and sum(x.get('official_monthly_notice_verified',False) for x in eventrows)==5)
ck('no_unknown_first_publication_backfilled',all(x.get('historical_first_publication_timestamp') is None and not x['historical_input_eligible'] for x in eventrows+ann))
ck('unique_normalized_event_ids',len({x['event_id'] for x in eventrows})==len(eventrows))
sourcehash=[]
for x in eventrows:
 if x.get('raw_path') and x.get('source_sha256'):
  path=Path(x['raw_path']);sourcehash.append(dict(event_id=x['event_id'],path=str(path),matches=h(path)==x['source_sha256']))
ck('all_existing_and_new_event_raw_hashes_match',all(x['matches'] for x in sourcehash))
save('source_hash_validation.json',sourcehash);save('validation.json',dict(checks=checks,all_passed=all(x['passed'] for x in checks)))
summary=dict(created_at_utc=NOW,user_date='2026-10-22',requested_start='2023-01-01',requested_end='2026-10-22',main_database_read_only=True,scope='staged public source refresh and time evidence, no forecasts',announcement_catalogues={k:{a:b for a,b in v.items() if a!='records'} for k,v in stage['catalogues'].items()},announcement_time_rows=len(ann),new_official_announcement_ids=0,actual_new_announcement_downloads=len(stage['new_documents']),provider_display_time_changed_vs_oct15=len(diff),historical_first_publication_certified=0,historical_input_eligible=0,expiry_months=len(exp),official_monthly_notice_verified_months=5,rule_derived_only_months=41,new_official_delivery_month='2026-10',new_official_delivery_date='2026-10-16',corporate_action_episodes=3,corporate_action_date_role_rows=11,policy_samples_existing=len(oldpol),policy_samples_new=len(newpol),normalized_event_rows=len(eventrows),normalized_counts=dict(collections.Counter(x['event_type'] for x in eventrows)),checks_passed=sum(x['passed'] for x in checks),checks_total=len(checks),all_checks_passed=all(x['passed'] for x in checks),limitations=['No response after 2026-09-15 in current ordinary directories does not prove no unlisted information or no release anywhere.','312 is catalogue scope, not all internet disclosures. No new originals returned in this refresh.','Current provider display_time changed in 80 rows; true earliest publication time remains unknown, not imputed.','October actual delivery result confirms event date after occurrence; does not certify pre-event historical availability.','41 expiry months remain formula candidates; no upgrade merely because a date has passed.','3 corporate actions are 3 economic episodes, not 11 independent samples. Official delegated payment date is not verified personal bank/broker receipt.','3 new official policy samples are bounded samples; not a complete policy/news feed and not evidence of stock-specific causal effect.','No returns, probabilities, signals, news sentiment, capital-flow effects or strategy analysis computed.'])
save('summary.json',summary)
md=f'''# 公告与事件时间补缺记录（2026年10月22日）\n\n本轮只增加独立暂存证据，主数据库只读。\n\n## 已完成\n\n- 重新请求2023年1月1日至2026年10月22日三个公告目录，共16个完整分页响应：东方财富312条、巨潮普通公告308条、投资者关系4条。均与本地312份映射一致。\n- 实际普通目录末日仍为2026年9月15日，投资者关系末日为4月30日；本轮未返回新增公告，新增公告原件0份。不能把查询截止日误写成公告数据已经覆盖至10月22日。\n- 312份公告生成当前时间台账，保留官方公告日、原始平台时钟字段、请求时间、原件URL和SHA256。相比10月15日留档，东方财富display_time有{len(diff)}行变化；官方目录与实质字段无变化。历史首次公开时刻依旧0确认，全部历史输入准入仍为false。\n- 从中金所官方目录发现并下载2026年10月16日《股指期货和股指期权合约交割的通知》原始HTML，核对IF/IH/IC/IM/IO/HO/MO七类2610合约日期。该月从公式候选升级为官方事后交割日期证据。46个月中5个月有官方逐月通知，41个月仍为规则候选。\n- 复用原件核验过的3次分红/转增，拆成11个日期角色，保留同一经济事件编号。除权、官方代派款、转增入账可同日，不能重复算独立样本；用户实际到账日未知。\n- 新保存证监会2026年10月19日3篇官方HTML样本：主题演讲、违规转让证券处罚规则发布、先行赔付征求意见。区分发布日、当前HTML PubDate元数据和生效日。处罚规则正文列明12月1日施行，征求意见稿不标成已施行。\n\n## 时间准入边界\n\n公告date、来源时钟、抓取时间、首次可用于历史研究的时间分别存储。精确到秒的当前PubDate/平台display_time也不等于有证据的首次公开时间。earliest_model_use_timestamp与historical_first_publication_timestamp未知仍为null，不回填。\n\n10月16日交割结果通知是事后证据，不能提前作为当天开盘前已知公告；现货大量资金流入/流出及波动影响尚未统计。转载聚合到同一原文事件，不新增独立事件。政策新闻仅10个累计样本，不称全网新闻全集。\n\n## 文件与检查\n\n- stage_manifest.json：16次公告目录原始响应、请求与对照；stage_manifest_sandbox_failure.json保留首次DNS失败。\n- announcement_time_ledger_current.json：312份当前公告时间台账。\n- provider_timestamp_revisions_vs_oct15.json：当前时间字段与旧版本差异。\n- normalized_events.json：{len(eventrows)}条标准事件（46个月交割/到期日期，11个企业行动日期角色，10个政策样本）。\n- event_source_manifest.json、event_raw/：6份新增官方HTML（包含2份导航与4份内容），全部URL、采集时间、字节数、哈希。\n- validation.json：{sum(x['passed'] for x in checks)}/{len(checks)}项通过。\n\n本轮没有计算概率、收益、指标或买卖信号，没有购买数据、登录账户或改写主库。\n'''
(P/'补缺报告.md').write_text(md)
print(json.dumps(summary,ensure_ascii=False,indent=2))
