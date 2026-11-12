"""Archive CNINFO counterparts of selected audited reports; compare original bytes."""
import concurrent.futures
import hashlib
import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def fetch(job):
    r=dict(job);r['retrieved_at']=datetime.now(timezone.utc).isoformat()
    try:
        req=urllib.request.Request(r['url'],headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=25) as response:raw=response.read(25*1024*1024+1)
        if not raw.startswith(b'%PDF-') or len(raw)>25*1024*1024:raise ValueError('Invalid PDF or size cap')
        digest=hashlib.sha256(raw).hexdigest()
        relative='巨潮核对原件/'+r['announcement_id']+'_'+digest[:16]+'.pdf'
        (ROOT/relative).write_bytes(raw)
        r.update(sha256=digest,relative_path=relative,bytes=len(raw),
                 comparison='identical_bytes' if digest==r['eastmoney_sha256'] else 'different_bytes_requires_content_review',error=None)
    except Exception as exc:r.update(comparison='not_acquired',error=type(exc).__name__+': '+str(exc))
    return r


def main():
    (ROOT/'巨潮核对原件').mkdir(exist_ok=True)
    c=sqlite3.connect(ROOT/'高德红外_2023起.sqlite');c.row_factory=sqlite3.Row
    selected={r[0] for r in c.execute('SELECT DISTINCT art_code FROM original_report_observations')}
    selected|={r[0] for r in c.execute('SELECT art_code FROM corporate_action_observations')}
    jobs=[]
    for r in c.execute('''SELECT a.*,cr.payload_json cn_payload,er.payload_json em_payload FROM announcement_reconciliation a
       JOIN current_source_records cr ON cr.snapshot_id=a.cninfo_snapshot_id AND cr.row_hash=a.cninfo_row_hash
       JOIN current_source_records er ON er.snapshot_id=a.eastmoney_snapshot_id AND er.row_hash=a.eastmoney_row_hash
       WHERE a.status='date_and_normalized_title_match' '''):
        em=json.loads(r['em_payload']);cn=json.loads(r['cn_payload'])
        if em['art_code'] not in selected:continue
        doc=c.execute('SELECT sha256 FROM announcement_documents WHERE art_code=?',(em['art_code'],)).fetchone()
        jobs.append(dict(art_code=em['art_code'],announcement_id=cn['announcementId'],
                         reference_date=r['reference_date'],title=r['title'],url='https://static.cninfo.com.cn/'+cn['adjunctUrl'],
                         eastmoney_sha256=doc['sha256'],historical_first_publication='unverified',
                         cninfo_snapshot_id=r['cninfo_snapshot_id'],cninfo_row_hash=r['cninfo_row_hash']))
    if len(jobs)!=len(selected):raise ValueError('Selected reports have missing/ambiguous CNINFO match')
    c.execute('''CREATE TABLE IF NOT EXISTS primary_document_checks(art_code TEXT,announcement_id TEXT,source_sha256 TEXT,
      reference_date TEXT,url TEXT,retrieved_at TEXT,relative_path TEXT,comparison TEXT,payload_json TEXT,
      PRIMARY KEY(art_code,announcement_id,source_sha256))''')
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(fetch,jobs):
            results.append(r)
            if not r['error']:
                c.execute('INSERT OR IGNORE INTO primary_document_checks VALUES (?,?,?,?,?,?,?,?,?)',
                  (r['art_code'],r['announcement_id'],r['sha256'],r['reference_date'],r['url'],r['retrieved_at'],
                   r['relative_path'],r['comparison'],json.dumps(r,ensure_ascii=False)))
            print(r['art_code'],r['comparison'],r['error'],flush=True)
    c.commit();c.close()
    (ROOT/'巨潮原件交叉核对.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
