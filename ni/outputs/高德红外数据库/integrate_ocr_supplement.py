"""Archive local OCR as unverified evidence, preserving original PDF/text status."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]/'work/round4_ocr'


def main():
    archive=ROOT/'公告OCR补充';archive.mkdir(exist_ok=True)
    raw=(WORK/'pages.jsonl').read_bytes();digest=hashlib.sha256(raw).hexdigest()
    result_name='pages_'+digest[:16]+'.jsonl'
    (archive/result_name).write_bytes(raw)
    for name in ('verification.json','pages_summary.json','jobs.json','original_document_map.json',
                 'model_sources.json','dependency_sources.json','environment.json','install_report.json',
                 'licenses_manifest.json','pilot_validation.json','review_queue.json',
                 'duplicate_text_groups.json','README.md','ocr_local.py','verify_results.py',
                 'requirements.lock','artifact_manifest.json'):
        shutil.copyfile(WORK/name,archive/name)
    shutil.copytree(WORK/'licenses',archive/'licenses',dirs_exist_ok=True)
    rows=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    assert len(rows)==185
    identities={(r['art_code'],r['page_number'],r['source_sha256']) for r in rows}
    assert len(identities)==185
    c=sqlite3.connect(ROOT/'高德红外_2023起.sqlite');c.row_factory=sqlite3.Row
    pending={tuple(r) for r in c.execute("SELECT art_code,page_number,source_sha256 FROM announcement_pages WHERE status='needs_ocr'")}
    assert identities==pending
    docs={r['art_code']:dict(r) for r in c.execute('SELECT * FROM announcement_documents')}
    for art in {r['art_code'] for r in rows}:
        doc=docs[art];assert hashlib.sha256((ROOT/doc['relative_path']).read_bytes()).hexdigest()==doc['sha256']
    c.executescript('''
      CREATE TABLE IF NOT EXISTS announcement_ocr_text_runs(
        run_id TEXT PRIMARY KEY,engine TEXT,model_hashes_json TEXT,result_sha256 TEXT,
        relative_path TEXT,metadata_json TEXT);
      CREATE TABLE IF NOT EXISTS announcement_ocr_texts(
        run_id TEXT,art_code TEXT,page_number INTEGER,source_sha256 TEXT,extracted_at TEXT,
        text TEXT,status TEXT,low_confidence_lines INTEGER,mean_confidence REAL,payload_json TEXT,
        PRIMARY KEY(run_id,art_code,page_number,source_sha256));
      CREATE VIEW IF NOT EXISTS available_announcement_text AS
        SELECT art_code,page_number,source_sha256,text,status,'pdf_text_layer' AS method
          FROM announcement_pages WHERE status='extracted_unverified' AND LENGTH(text)>0
        UNION ALL
        SELECT t.art_code,t.page_number,t.source_sha256,t.text,t.status,'local_ocr_unverified' AS method
          FROM announcement_ocr_texts t JOIN announcement_pages p
            ON t.art_code=p.art_code AND t.page_number=p.page_number AND t.source_sha256=p.source_sha256
          WHERE p.status='needs_ocr' AND LENGTH(t.text)>0
            AND NOT EXISTS(SELECT 1 FROM announcement_ocr_texts n
              WHERE n.art_code=t.art_code AND n.page_number=t.page_number AND n.source_sha256=t.source_sha256
                AND (n.extracted_at>t.extracted_at OR (n.extracted_at=t.extracted_at AND n.run_id>t.run_id)));
    ''')
    run_id='rapidocr:'+digest
    verification=json.loads((WORK/'verification.json').read_text())
    assert verification['all_identity_and_completeness_checks_passed']
    c.execute('INSERT OR IGNORE INTO announcement_ocr_text_runs VALUES (?,?,?,?,?,?)',
        (run_id,rows[0]['engine'],json.dumps(rows[0]['models_sha256'],sort_keys=True),digest,
         '公告OCR补充/'+result_name,json.dumps(verification,ensure_ascii=False,sort_keys=True)))
    for r in rows:
        assert r['status']=='ocr_extracted_unverified' and r['text'].strip()
        assert not r['numeric_facts_verified'] and not r['historical_input_eligible']
        assert r['manual_review_status']=='not_reviewed' and r['error'] is None
        assert r['source_sha256']==docs[r['art_code']]['sha256']
        assert '\n'.join(o['text'] for o in r['observations'])==r['text']
        assert all(0<=o['confidence']<=1 and len(o['box_pixels'])==4 for o in r['observations'])
        c.execute('INSERT OR IGNORE INTO announcement_ocr_texts VALUES (?,?,?,?,?,?,?,?,?,?)',
            (run_id,r['art_code'],r['page_number'],r['source_sha256'],r['retrieved_at'],r['text'],
             r['status'],r['low_confidence_lines'],r['mean_confidence'],json.dumps(r,ensure_ascii=False,sort_keys=True)))
    c.execute('UPDATE coverage_gaps SET status=?,explanation=? WHERE dataset=?',
        ('partial','All 185 originally text-empty pages now have separate local OCR text; original extraction statuses preserved. All 4253 pages have machine-readable text. OCR accuracy/table reconstruction/manual page review unverified; zero newly certified numeric facts. 124 OCR pages contain lines with confidence below 0.8.',
         'announcement_ocr'))
    c.commit()
    report=dict(run_id=run_id,result_sha256=digest,relative_path='公告OCR补充/'+result_name,
        original_pending_pages=185,ocr_text_pages=len(rows),available_machine_text_pages=c.execute('SELECT COUNT(*) FROM available_announcement_text').fetchone()[0],
        text_characters=sum(len(r['text']) for r in rows),manual_full_page_reviews=0,
        newly_certified_numeric_facts=0,historical_input_eligible=False,
        verification=verification)
    (ROOT/'公告OCR补充合库记录.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    c.close();print(json.dumps({k:v for k,v in report.items() if k!='verification'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
