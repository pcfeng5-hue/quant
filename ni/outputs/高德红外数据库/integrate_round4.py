"""Integrate versioned read-only disclosure reviews; retain unverified history status."""
import hashlib
import json
import shutil
import sqlite3
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]/'work'
VERSION='round4-disclosure-audit-v1'


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True)


def main():
    sources={
        '会计修订原件核对.json':WORK/'round4_accounting/会计修订候选核对.json',
        '股本与过户原件核对.json':WORK/'round4_capital_status/capital_status_audit.json',
        '会计修订核对说明.md':WORK/'round4_accounting/会计核对简报.md',
        '股本与状态核对说明.md':WORK/'round4_capital_status/股本与状态核对简报.md',
    }
    for name,path in sources.items():
        shutil.copyfile(path,ROOT/name)
    accounting=json.loads((ROOT/'会计修订原件核对.json').read_text())
    capital=json.loads((ROOT/'股本与过户原件核对.json').read_text())
    c=sqlite3.connect(ROOT/'高德红外_2023起.sqlite');c.row_factory=sqlite3.Row
    c.executescript('''
      CREATE TABLE IF NOT EXISTS announcement_candidate_reviews(
        candidate_id TEXT,audit_version TEXT,classification TEXT,source_sha256 TEXT,
        historical_input_eligible INTEGER,payload_json TEXT,PRIMARY KEY(candidate_id,audit_version));
      CREATE TABLE IF NOT EXISTS supplemental_disclosure_observations(
        observation_id TEXT,audit_version TEXT,kind TEXT,reference_date TEXT,report_period TEXT,
        status TEXT,historical_input_eligible INTEGER,payload_json TEXT,
        PRIMARY KEY(observation_id,audit_version));
      CREATE TABLE IF NOT EXISTS supplemental_disclosure_evidence(
        observation_id TEXT,audit_version TEXT,art_code TEXT,page_number INTEGER,
        source_sha256 TEXT,evidence_role TEXT,
        PRIMARY KEY(observation_id,audit_version,art_code,page_number,source_sha256,evidence_role));
    ''')
    docs={r['art_code']:dict(r) for r in c.execute('SELECT * FROM announcement_documents')}

    def check_source(source):
        doc=docs[source['art_code']]
        assert doc['sha256']==source['source_sha256'], 'source document identity mismatch'
        assert hashlib.sha256((ROOT/doc['relative_path']).read_bytes()).hexdigest()==doc['sha256']
        pages=source.get('page_numbers') or [source['page_number']]
        for page in pages:
            assert c.execute('SELECT 1 FROM announcement_pages WHERE art_code=? AND page_number=? AND source_sha256=?',
                (source['art_code'],page,source['source_sha256'])).fetchone(), 'missing source page'
        return pages

    def store_observation(oid,kind,r,reference_date=None,report_period=None,status='selected_original_fields_verified'):
        assert not r.get('historical_input_eligible',False)
        evidence=r.get('evidence') or [r]
        for source in evidence:check_source(source)
        c.execute('INSERT OR IGNORE INTO supplemental_disclosure_observations VALUES (?,?,?,?,?,?,?,?)',
            (oid,VERSION,kind,reference_date,report_period,status,0,encoded(r)))
        for source in evidence:
            for page in check_source(source):
                c.execute('INSERT OR IGNORE INTO supplemental_disclosure_evidence VALUES (?,?,?,?,?,?)',
                    (oid,VERSION,source['art_code'],page,source['source_sha256'],'primary_observation'))
        if r.get('unit_evidence'):
            unit=dict(r['unit_evidence'])
            unit.setdefault('art_code',r['art_code'])
            unit.setdefault('source_sha256',r['source_sha256'])
            unit.setdefault('page_number',r['page_number'])
            for page in check_source(unit):
                c.execute('INSERT OR IGNORE INTO supplemental_disclosure_evidence VALUES (?,?,?,?,?,?)',
                    (oid,VERSION,unit['art_code'],page,unit['source_sha256'],'unit_evidence'))

    for r in accounting['classified_candidates']:
        candidate=c.execute('SELECT * FROM announcement_event_candidates WHERE candidate_id=?',(r['candidate_id'],)).fetchone()
        assert candidate is not None and candidate['source_sha256']==r['source_sha256']
        assert not r['historical_input_eligible']
        c.execute('INSERT OR IGNORE INTO announcement_candidate_reviews VALUES (?,?,?,?,?,?)',
            (r['candidate_id'],VERSION,r['classification'],r['source_sha256'],0,encoded(r)))
    for r in capital['candidate_review']['resolved_candidates']:
        candidate=c.execute('SELECT * FROM announcement_event_candidates WHERE art_code=? AND category=?',
            (r['art_code'],r['category'])).fetchone()
        assert candidate is not None and r['new_independent_event_count']==0
        data=dict(r,historical_input_eligible=False,source_sha256=candidate['source_sha256'])
        c.execute('INSERT OR IGNORE INTO announcement_candidate_reviews VALUES (?,?,?,?,?,?)',
            (candidate['candidate_id'],VERSION,r['classification'],candidate['source_sha256'],0,encoded(data)))
    for r in accounting['observations']:
        assert r['unit']=='CNY'
        if r['before_decimal'] is not None:
            assert Decimal(r['before_decimal'])+Decimal(r['adjustment_decimal'])==Decimal(r['after_decimal'])
        store_observation(r['observation_id'],'accounting_adjustment',r,r['provider_notice_date'][:10],r['affected_period'])
    for r in capital['capital_period_observations']:
        assert r['total_shares']==r['limited_shares']+r['unlimited_shares'] and r['unit']=='shares'
        # Period ends are report observations, never inferred daily effective dates.
        store_observation(r['observation_id'],'capital_period',r,r['evidence'][0]['provider_notice_date'],r['period_end'])
    for r in capital['new_ownership_transfer_events']:
        assert r['shares_original_unit']=='10000_shares' and Decimal(str(r['shares_original']))*10000==r['shares']
        assert r['total_capital_change'] is None and r['unlimited_share_change'] is None
        store_observation(r['event_id'],'employee_nontrade_transfer',r,r['provider_notice_date'],r['completion_date'])
    for r in capital['negative_disclosure_observations']:
        store_observation(r['observation_id'],'limited_negative_disclosure',r,r['evidence'][0]['provider_notice_date'],str(r['report_year']))
    for r in capital['unresolved_capital_issues']:
        store_observation(r['issue_id'],'capital_reconciliation_issue',r,None,None,'unresolved')
    for action in capital['merged_existing_corporate_action']:
        assert action['new_independent_event_count']==0
        assert c.execute('SELECT 1 FROM corporate_action_observations WHERE art_code=?',
            (action['existing_corporate_action_art_code'],)).fetchone()
        for phase in action['phases']:
            r=dict(phase,event_group_id=action['event_group_id'],historical_input_eligible=False,
                   new_independent_event_count=0,evidence=[phase['source']])
            store_observation(action['event_group_id']+':'+phase['phase'],'existing_action_phase',r,
                phase['source']['provider_notice_date'],phase.get('phase_date'))
    for r in accounting['official_counterparts']:
        assert r['error'] is None and r['comparison']=='identical_bytes'
        assert r['source_sha256']==docs[r['art_code']]['sha256']
        src=Path(r['path']);assert hashlib.sha256(src.read_bytes()).hexdigest()==r['source_sha256']
        relative='巨潮核对原件/'+r['announcement_id']+'_'+r['source_sha256'][:16]+'.pdf'
        shutil.copyfile(src,ROOT/relative)
        d=dict(r,relative_path=relative,title=docs[r['art_code']]['title'],
            reference_date=docs[r['art_code']]['notice_date'][:10],historical_first_publication='unverified')
        c.execute('INSERT OR IGNORE INTO primary_document_checks VALUES (?,?,?,?,?,?,?,?,?)',
            (r['art_code'],r['announcement_id'],r['source_sha256'],d['reference_date'],r['url'],
             r['retrieved_at'],relative,r['comparison'],encoded(d)))
    c.execute('UPDATE coverage_gaps SET status=?,explanation=? WHERE dataset=?',
        ('partial','Eight original report capital observations (one pre-2023 baseline), including four added periods. Three non-trade employee transfer completions are not capital creation; three reconciliation gaps unresolved. No certified daily float history.',
         'corporate_actions_float_shares'))
    c.execute('UPDATE coverage_gaps SET status=?,explanation=? WHERE dataset=?',
        ('partial','135 selected original finance metrics plus 28 separately versioned adjustment rows verified; blank cells remain null. Not full statements, first-public timestamps or complete revisions.',
         'financial_point_in_time'))
    c.execute('UPDATE coverage_gaps SET status=?,explanation=? WHERE dataset=?',
        ('access_required','Chip/price relationship prioritized by user. Offline JSON validator prepared; 912 target dates, zero provider chip dates acquired. No local reconstruction counted as supplier history; permissions and price basis not verified.',
         'chip_history'))
    for name in sources:
        raw=(ROOT/name).read_bytes()
        c.execute('INSERT OR IGNORE INTO project_reference_documents VALUES (?,?,?,?)',
            (name,hashlib.sha256(raw).hexdigest(),'data_audit_not_market_input',raw.decode('utf-8')))
    c.commit()
    report=dict(audit_version=VERSION,candidate_reviews=c.execute('SELECT COUNT(*) FROM announcement_candidate_reviews WHERE audit_version=?',(VERSION,)).fetchone()[0],
        observations=dict(c.execute('SELECT kind,COUNT(*) FROM supplemental_disclosure_observations WHERE audit_version=? GROUP BY kind',(VERSION,))),
        primary_document_checks=c.execute('SELECT COUNT(*) FROM primary_document_checks').fetchone()[0],
        input_sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        historical_input_eligible=False)
    (ROOT/'第三轮补缺合库记录.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    c.close();print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
