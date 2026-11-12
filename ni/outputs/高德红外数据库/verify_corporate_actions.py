"""Cross-check three implementation records against preserved original PDF text."""
import json
import re
import sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FIXTURES=[
 dict(art_code='AN202306121590866740',record_date='2023-06-19',ex_date='2023-06-20',cash_cny_per_10_shares='1.3',
      transfer_shares_per_10='3',total_shares_before='3285181622',total_shares_after='4270736108',
      evidence_pages=[1,2,3],date_tokens=['2023年6月19日','2023年6月20日']),
 dict(art_code='AN202405151633180433',record_date='2024-05-23',ex_date='2024-05-24',cash_cny_per_10_shares='0.14',
      transfer_shares_per_10='0',total_shares_before='4270736108',total_shares_after='4270736108',
      evidence_pages=[1,2],date_tokens=['2024年5月23日','2024年5月24日']),
 dict(art_code='AN202609141829372726',record_date='2026-09-21',ex_date='2026-09-22',cash_cny_per_10_shares='1',
      transfer_shares_per_10='0',total_shares_before='4270736108',total_shares_after='4270736108',
      evidence_pages=[1,2],date_tokens=['2026年9月21日','2026年9月22日']),
]


def compact(s):return re.sub(r'[\s,，]','',s)


def main():
    c=sqlite3.connect(ROOT/'高德红外_2023起.sqlite');c.row_factory=sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS corporate_action_observations(
      art_code TEXT,source_sha256 TEXT,provider_notice_date TEXT,record_date TEXT,ex_date TEXT,
      cash_cny_per_10_shares TEXT,transfer_shares_per_10 TEXT,total_shares_before TEXT,total_shares_after TEXT,
      availability_status TEXT,evidence_json TEXT,PRIMARY KEY(art_code,source_sha256))''')
    provider=[json.loads(r[0]) for r in c.execute("SELECT payload_json FROM current_source_records WHERE dataset='dividends'")]
    results=[]
    for fixture in FIXTURES:
        r=dict(fixture);doc=c.execute('SELECT * FROM announcement_documents WHERE art_code=?',(r['art_code'],)).fetchone()
        pages=[(n,c.execute('SELECT text FROM announcement_pages WHERE art_code=? AND page_number=? AND source_sha256=?',(r['art_code'],n,doc['sha256'])).fetchone()[0]) for n in r['evidence_pages']]
        text=compact(''.join(t for n,t in pages))
        for token in r['date_tokens']+[r['total_shares_before'],r['total_shares_after'],'每10股派'+r['cash_cny_per_10_shares']]:
            if token not in text:raise ValueError('PDF evidence missing: '+token)
        if r['transfer_shares_per_10']=='0':
            if '不以资本公积金转增股本' not in text:raise ValueError('no-transfer evidence missing')
        elif '每10股转增3股' not in text:raise ValueError('transfer evidence missing')
        match=[d for d in provider if (d.get('EX_DIVIDEND_DATE') or '')[:10]==r['ex_date']]
        if len(match)!=1:raise ValueError('provider action match missing')
        d=match[0]
        if (d['EQUITY_RECORD_DATE'][:10]!=r['record_date'] or float(d['PRETAX_BONUS_RMB'])!=float(r['cash_cny_per_10_shares'])):raise ValueError('source/PDF action mismatch')
        r.update(source_sha256=doc['sha256'],source_url=doc['url'],provider_notice_date=doc['notice_date'][:10],
                 availability_status='original_implementation_terms_checked_first_public_time_unverified',
                 verification_scope='registration/ex-date/gross-cash-per-10/transfer/total-shares only; not all tax or execution terms',
                 page_text_evidence=[dict(page_number=n,text=t) for n,t in pages])
        c.execute('INSERT OR IGNORE INTO corporate_action_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)',
         (r['art_code'],r['source_sha256'],r['provider_notice_date'],r['record_date'],r['ex_date'],r['cash_cny_per_10_shares'],
          r['transfer_shares_per_10'],r['total_shares_before'],r['total_shares_after'],r['availability_status'],json.dumps(r,ensure_ascii=False)))
        results.append(r)
    c.commit();c.close()
    (ROOT/'公司行动原件核对.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print('Corporate action/PDF matches:',len(results))


if __name__=='__main__':main()
