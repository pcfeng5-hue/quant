"""Normalize verified observations and audit flags; no strategy or historical feature approval."""
import collections
import hashlib
import json
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VERSION='supplement-audit-v1'
FUTURE_FIELDS={'CHANGE_RATE_1DAYS','CHANGE_RATE_5DAYS','CHANGE_RATE_10DAYS','CHANGE_RATE_20DAYS',
               'D10_CLOSE_ADJCHRATE','D30_CLOSE_ADJCHRATE'}


def normalized_title(s):
    return re.sub(r'[\s:：()（）《》·]','',re.sub(r'<[^>]*>','',s).replace('高德红外',''))


def main():
    c=sqlite3.connect(ROOT/'高德红外_2023起.sqlite');c.row_factory=sqlite3.Row
    c.executescript('''
      CREATE TABLE IF NOT EXISTS trading_calendar(trade_date TEXT,exchange_scope TEXT,is_scheduled_open INTEGER,calendar_version TEXT,payload_json TEXT,PRIMARY KEY(trade_date,exchange_scope,calendar_version));
      CREATE TABLE IF NOT EXISTS original_report_observations(art_code TEXT,source_sha256 TEXT,report_date TEXT,metric TEXT,value_decimal TEXT,unit TEXT,provider_notice_date TEXT,availability_status TEXT,evidence_json TEXT,PRIMARY KEY(art_code,source_sha256,metric));
      CREATE TABLE IF NOT EXISTS record_temporal_audit(snapshot_id TEXT,row_hash TEXT,audit_version TEXT,report_period TEXT,provider_notice_date TEXT,provider_update_date TEXT,flags_json TEXT,historical_input_eligible INTEGER,PRIMARY KEY(snapshot_id,row_hash,audit_version));
      CREATE TABLE IF NOT EXISTS restricted_source_fields(dataset TEXT,field_name TEXT,reason TEXT,non_null_records INTEGER,audit_version TEXT,PRIMARY KEY(dataset,field_name,audit_version));
      CREATE TABLE IF NOT EXISTS announcement_reconciliation(cninfo_snapshot_id TEXT,cninfo_row_hash TEXT,eastmoney_snapshot_id TEXT,eastmoney_row_hash TEXT,reference_date TEXT,title TEXT,status TEXT,audit_version TEXT,PRIMARY KEY(cninfo_row_hash,eastmoney_row_hash,audit_version));
      CREATE TABLE IF NOT EXISTS announcement_ir_reconciliation(cninfo_snapshot_id TEXT,cninfo_row_hash TEXT,eastmoney_snapshot_id TEXT,eastmoney_row_hash TEXT,reference_date TEXT,title TEXT,status TEXT,audit_version TEXT,PRIMARY KEY(cninfo_row_hash,eastmoney_row_hash,audit_version));
      CREATE TABLE IF NOT EXISTS normalized_fund_flow(snapshot_id TEXT,row_hash TEXT,trade_date TEXT,payload_json TEXT,mapping_source TEXT,unit_status TEXT,PRIMARY KEY(snapshot_id,row_hash));
      CREATE TABLE IF NOT EXISTS candidate_data_sources(source_id TEXT,reviewed_on TEXT,url TEXT,data_status TEXT,payload_json TEXT,PRIMARY KEY(source_id,reviewed_on));
    ''')
    cal=json.loads((ROOT/'official_calendar_2023_to_20261013.json').read_text())
    for r in cal:
        c.execute('INSERT OR IGNORE INTO trading_calendar VALUES (?,?,?,?,?)',
                  (r['trade_date'],r['exchange_scope'],r['is_scheduled_open'],r['calendar_version'],json.dumps(r,ensure_ascii=False)))
    finance=json.loads((ROOT/'finance_pdf_audit.json').read_text())
    originals=finance['original_report_observations']
    notice_dates={r['report_date']:r['provider_notice_date'] for r in originals}
    for r in originals:
        doc=c.execute('SELECT sha256 FROM announcement_documents WHERE art_code=?',(r['art_code'],)).fetchone()
        if doc is None or doc['sha256']!=r['source_sha256']:raise ValueError('original PDF hash mismatch')
        c.execute('INSERT OR IGNORE INTO original_report_observations VALUES (?,?,?,?,?,?,?,?,?)',
          (r['art_code'],r['source_sha256'],r['report_date'],r['metric'],r['value_decimal'],r['unit'],
           r['provider_notice_date'],r['availability_status'],json.dumps(r,ensure_ascii=False)))
    candidates=json.loads((ROOT/'候选数据源.json').read_text())
    for r in candidates['sources']:
        c.execute('INSERT OR IGNORE INTO candidate_data_sources VALUES (?,?,?,?,?)',
                  (r['source_id'],candidates['reviewed_on'],r['url'],r['data_status'],json.dumps(r,ensure_ascii=False)))
    rows=list(c.execute('SELECT * FROM current_source_records'))
    restrictions=collections.Counter(); em=collections.defaultdict(list); cn=collections.defaultdict(list); ir=[]
    flowchecks=[]
    flowfields=('trade_date','main_net_amount','small_net_amount','medium_net_amount','large_net_amount','super_large_net_amount',
                'main_net_percent','small_net_percent','medium_net_percent','large_net_percent','super_large_net_percent','close','change_percent')
    flow_source='https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_fund_em.py'
    bars={r['trade_date']:r for r in c.execute("SELECT * FROM current_daily_bars WHERE source='em_daily_0'")}
    qfq={r['trade_date']:r for r in c.execute("SELECT * FROM current_daily_bars WHERE source='em_daily_1'")}
    unit_failures=[]
    for day,b in bars.items():
        if b['volume']>0 and b['amount'] is not None:
            # Unit consistency: amount / (provider volume * 100) must lie in daily range.
            observed=b['amount']/(b['volume']*100)
            if not b['low']-.02<=observed<=b['high']+.02:unit_failures.append(day)
    for row in rows:
        d=json.loads(row['payload_json']); flags=['historical_first_availability_unverified']
        report=notice=update=None
        if isinstance(d,dict):
            report=(d.get('REPORT_DATE') or d.get('END_DATE') or '')[:10] or None
            notice=(d.get('NOTICE_DATE') or d.get('HOLD_NOTICE_DATE') or d.get('notice_date') or '')[:10] or None
            update=(d.get('UPDATE_DATE') or '')[:10] or None
            if notice and update and update>notice: flags.append('provider_updated_after_notice')
            if report in notice_dates and notice and notice>notice_dates[report]:flags.append('later_comparative_disclosure_version')
            forward_fields=FUTURE_FIELDS | {k for k in d if re.fullmatch(r'D\d+_CLOSE_ADJCHRATE',k)}
            for field in forward_fields:
                if d.get(field) is not None:
                    restrictions[(row['dataset'],field,'forward_return_statistic')]+=1
                    if 'contains_forward_return_statistics' not in flags:flags.append('contains_forward_return_statistics')
            if d.get('FCFF_FORWARD') is not None:
                restrictions[(row['dataset'],'FCFF_FORWARD','formula_and_historical_availability_unknown')]+=1
                flags.append('formula_field_unverified')
            if row['dataset'].startswith('announcements'):
                em[(row['reference_date'],normalized_title(d['title']))].append((row,d))
            if row['dataset'].startswith('cninfo_'):
                flags.append('announcement_epoch_is_date_label_not_first_release')
            if row['dataset'].startswith('cninfo_announcements'):
                cn[(row['reference_date'],normalized_title(d['announcementTitle']))].append((row,d))
            if row['dataset'].startswith('cninfo_ir'):ir.append((row,d))
            if row['dataset'].startswith('capital_structure'):flags.append('capital_change_date_not_publication_date')
        elif row['dataset']=='fund_flow_proxy':
            a=d.split(',')
            if len(a)!=13:raise ValueError('unexpected fund flow schema')
            decoded={k:v if i==0 else float(v) for i,(k,v) in enumerate(zip(flowfields,a))}
            day=decoded['trade_date'];b=bars.get(day)
            main_ok=abs(decoded['main_net_amount']-decoded['large_net_amount']-decoded['super_large_net_amount'])<=1
            balance_ok=abs(sum(decoded[k] for k in ('small_net_amount','medium_net_amount','large_net_amount','super_large_net_amount')))<=1
            close_ok=b is not None and abs(decoded['close']-b['close'])<=.005
            qfq_ok=day in qfq and abs(decoded['close']-qfq[day]['close'])<=.005
            amount_ok=b is not None and abs(decoded['main_net_amount']/b['amount']*100-decoded['main_net_percent'])<=.02
            residual=sum(decoded[k] for k in ('small_net_amount','medium_net_amount','large_net_amount','super_large_net_amount'))
            flowchecks.append(dict(trade_date=day,main_sum=main_ok,net_balance=balance_ok,net_balance_residual_cny=residual,
                                   close_matches_unadjusted=close_ok,close_matches_current_qfq=qfq_ok,percent_unit_consistent=amount_ok))
            decoded.update(evidence_type='provider_trade_size_flow_proxy',amount_unit='CNY',percent_unit='percentage_points',
                           investor_identity='unknown',full_period_coverage=False,historical_availability='unverified',
                           net_balance_residual_cny=residual,price_basis='matches_current_qfq_in_checked_window' if qfq_ok else 'unverified')
            decoded['provider_close']=decoded.pop('close')
            c.execute('INSERT OR REPLACE INTO normalized_fund_flow VALUES (?,?,?,?,?,?)',
                      (row['snapshot_id'],row['row_hash'],day,json.dumps(decoded,ensure_ascii=False),flow_source,'mapped_from_official_library_and_checked_against_daily_amount'))
            flags.append('trade_size_proxy_not_institutional_identity')
            if not close_ok:flags.append('embedded_close_differs_from_unadjusted')
            if not balance_ok:flags.append('net_flow_balance_small_residual_unexplained')
        c.execute('INSERT OR REPLACE INTO record_temporal_audit VALUES (?,?,?,?,?,?,?,?)',
         (row['snapshot_id'],row['row_hash'],VERSION,report,notice,update,json.dumps(flags),0))
    for (dataset,field,reason),count in restrictions.items():
        c.execute('INSERT OR REPLACE INTO restricted_source_fields VALUES (?,?,?,?,?)',(dataset,field,reason,count,VERSION))
    for key in sorted(set(em)|set(cn)):
        left=cn.get(key,[(None,None)]);right=em.get(key,[(None,None)])
        if len(left)!=1 or len(right)!=1:raise ValueError('ambiguous announcement reconciliation')
        cr,cd=left[0];er,ed=right[0]
        status='date_and_normalized_title_match' if cr and er else 'eastmoney_additional_investor_activity' if er else 'cninfo_missing_in_eastmoney'
        c.execute('INSERT OR IGNORE INTO announcement_reconciliation VALUES (?,?,?,?,?,?,?,?)',
         (cr['snapshot_id'] if cr else '',cr['row_hash'] if cr else '',er['snapshot_id'] if er else '',er['row_hash'] if er else '',key[0],cd['announcementTitle'] if cd else ed['title'],status,VERSION))
    for cr,cd in ir:
        key=(cr['reference_date'],normalized_title(cd['announcementTitle']))
        matches=em.get(key,[])
        if len(matches)!=1:raise ValueError('IR catalogue match missing or ambiguous')
        er,ed=matches[0]
        c.execute('INSERT OR IGNORE INTO announcement_ir_reconciliation VALUES (?,?,?,?,?,?,?,?)',
          (cr['snapshot_id'],cr['row_hash'],er['snapshot_id'],er['row_hash'],key[0],cd['announcementTitle'],'official_ir_date_and_title_match',VERSION))
    c.executescript('''
      DROP VIEW IF EXISTS reviewed_historical_source_records;
      CREATE VIEW reviewed_historical_source_records AS SELECT r.* FROM current_source_records r
        JOIN record_temporal_audit a USING(snapshot_id,row_hash)
        WHERE a.audit_version='supplement-audit-v1' AND a.historical_input_eligible=1;
    ''')
    updates=[
      ('trading_calendar_status','partial','Official scheduled calendar 912 sessions checked with no missing/extra dates; individual suspension/risk warning history remains unverified.'),
      ('corporate_actions_float_shares','partial','Five provider capital change records acquired in requested period plus earlier baseline candidates. LISTED_A_SHARES differs from FREE_SHARES; no certified continuous historical float series.'),
      ('news_policy_archive','partial','Declared official policy/news samples archived; full historical news/policy archive and first-public timestamps remain missing.'),
      ('chip_history','access_required','Tushare cyq_perf/cyq_chips documentation claims history since 2018; permission/pricing differs across docs. No paid access or historical observations acquired.'),
      ('financial_point_in_time','partial','135 original-report metric observations across 15 reports verified; 5 differences vs current main values. First public timestamps and complete revision chain not certified.'),
    ]
    c.executemany('INSERT OR REPLACE INTO coverage_gaps VALUES (?,?,?)',updates)
    c.commit()
    report=dict(audit_version=VERSION,original_finance_observations=len(originals),original_reports=finance['report_count'],
                current_main_value_differences=finance['provider_value_differences'],candidate_sources=len(candidates['sources']),
                announcement_status=dict(c.execute('SELECT status,COUNT(*) FROM announcement_reconciliation GROUP BY status')),
                official_ir_matches=c.execute('SELECT COUNT(*) FROM announcement_ir_reconciliation').fetchone()[0],
                forward_or_unknown_fields=[dict(r) for r in c.execute('SELECT * FROM restricted_source_fields')],
                volume_amount_unit_failures=unit_failures,unit_checked_days=len(bars),fund_flow_checks=flowchecks,
                fund_flow_summary=dict(records=len(flowchecks),main_sum_failures=sum(not r['main_sum'] for r in flowchecks),
                    percent_unit_failures=sum(not r['percent_unit_consistent'] for r in flowchecks),
                    price_matches_current_qfq=sum(r['close_matches_current_qfq'] for r in flowchecks),
                    price_differs_from_unadjusted=sum(not r['close_matches_unadjusted'] for r in flowchecks),
                    net_balance_residual_over_one_cny=sum(not r['net_balance'] for r in flowchecks),
                    maximum_abs_residual_cny=max((abs(r['net_balance_residual_cny']) for r in flowchecks),default=0)),
                temporal_record_count=c.execute('SELECT COUNT(*) FROM record_temporal_audit').fetchone()[0],
                approved_historical_record_count=c.execute('SELECT COUNT(*) FROM reviewed_historical_source_records').fetchone()[0],
                historical_input_rule='Default deny: raw collection and numeric verification do not certify first historical availability.')
    (ROOT/'补缺与时点核对结果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('fund_flow_checks','current_main_value_differences','forward_or_unknown_fields')},ensure_ascii=False,indent=2))
    c.close()
    # Balance/embedded-price discrepancies remain explicit warnings, never silently repaired.
    if unit_failures or any(not r['main_sum'] or not r['percent_unit_consistent'] for r in flowchecks):raise SystemExit('Unit/flow check failure')


if __name__=='__main__':main()
