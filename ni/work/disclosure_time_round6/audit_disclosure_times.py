#!/usr/bin/env python3
"""Read-only disclosure identity/date evidence ledger; no first-public certification."""
from __future__ import annotations

import collections
import csv
import datetime as dt
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ROOT = PROJECT / 'outputs/高德红外数据库'
DB = ROOT / '高德红外_2023起.sqlite'
TZ = ZoneInfo('Asia/Shanghai')

def jdump(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def normalize_title(s):
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'<[^>]+>', '', s or '')
    s = s.replace('高德红外:', '').replace('高德红外：', '')
    s = s.replace('002414高德红外', '002414')
    return re.sub(r'\s+', '', s)

def em_time(value):
    if not value:
        return None
    # Raw has no explicit UTC offset; retain the candidate as a provider-local string.
    return dt.datetime.strptime(value, '%Y-%m-%d %H:%M:%S:%f')

def main():
    c = sqlite3.connect(DB.resolve().as_uri() + '?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    before_counts = {r['name']: c.execute('SELECT COUNT(*) FROM "' + r['name'] + '"').fetchone()[0]
                     for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    snapshots = {r['snapshot_id']: dict(r) for r in c.execute('SELECT * FROM source_snapshots')}
    source = {(r['snapshot_id'], r['row_hash']): dict(r) for r in c.execute('SELECT * FROM source_records')}
    docs = {r['art_code']: dict(r) for r in c.execute('SELECT * FROM announcement_documents')}
    ordinary = [dict(r) for r in c.execute('SELECT * FROM current_announcement_reconciliation')]
    ir = [dict(r) for r in c.execute('SELECT * FROM current_announcement_ir_reconciliation')]
    pairs = [r for r in ordinary if r['status'] == 'date_and_normalized_title_match'] + ir
    primary = collections.defaultdict(list)
    for r in c.execute('SELECT * FROM primary_document_checks'):
        primary[r['art_code']].append(dict(r))

    raw_hash_checks = {}
    pdf_hash_checks = {}
    rows = []
    for link in pairs:
        er = source[(link['eastmoney_snapshot_id'], link['eastmoney_row_hash'])]
        cr = source[(link['cninfo_snapshot_id'], link['cninfo_row_hash'])]
        ep, cp = json.loads(er['payload_json']), json.loads(cr['payload_json'])
        es, cs = snapshots[er['snapshot_id']], snapshots[cr['snapshot_id']]
        art = ep['art_code']
        doc = docs[art]
        for s in (es, cs):
            path = ROOT / s['raw_path']
            raw_hash_checks[s['snapshot_id']] = {'path': str(path), 'expected': s['sha256'], 'actual': sha(path), 'matches': sha(path) == s['sha256']}
        docpath = ROOT / doc['relative_path']
        pdf_hash_checks[art] = {'path': str(docpath), 'expected': doc['sha256'], 'actual': sha(docpath), 'matches': sha(docpath) == doc['sha256']}
        cn_time = dt.datetime.fromtimestamp(cp['announcementTime'] / 1000, TZ)
        cn_day = cn_time.date().isoformat()
        path_match = re.search(r'finalpage/(\d{4}-\d{2}-\d{2})/', cp['adjunctUrl'])
        path_day = path_match.group(1) if path_match else None
        em_day = ep['notice_date'][:10]
        display = em_time(ep.get('display_time'))
        ei_time = em_time(ep.get('eiTime'))
        sort_date = ep.get('sort_date')
        is_ir = cr['dataset'].startswith('cninfo_ir')
        checks = []
        if cn_day != em_day: checks.append('official_day_vs_provider_notice_day')
        if path_day != cn_day: checks.append('official_path_day_vs_official_epoch_day')
        if normalize_title(cp['announcementTitle']) != normalize_title(ep['title']): checks.append('normalized_title')
        official_copies = []
        for p in primary[art]:
            ppath = ROOT / p['relative_path']
            official_copies.append({
                'announcement_id': p['announcement_id'], 'url': p['url'], 'retrieved_at': p['retrieved_at'],
                'relative_path': p['relative_path'], 'source_sha256': p['source_sha256'],
                'comparison': p['comparison'], 'local_sha256_matches': sha(ppath) == p['source_sha256'],
                'same_pdf_as_eastmoney': p['source_sha256'] == doc['sha256'],
            })
        gap = {
            'minute_level_first_publication': 'not_certified',
            'historical_capture_or_archive_evidence': 'not_acquired',
            'current_pdf_original_version_available_on_disclosure_day': 'not_certified',
            'pdf_body_signed_date_equals_public_date': 'not_assumed',
            'timezone_of_eastmoney_timestamps': 'not_explicit_in_raw_fields',
            'official_pdf_download': 'local_identical_official_copy_present' if official_copies else 'not_downloaded_in_this_round; official_url_linked_only',
        }
        row = {
            'art_code': art, 'title': ep['title'], 'official_title': cp['announcementTitle'],
            'category': 'investor_relations' if is_ir else 'ordinary_announcement',
            'official_announcement_id': cp['announcementId'], 'official_org_id': cp['orgId'],
            'official_security_code': cp['secCode'],
            'official_disclosure_day': cn_day,
            'official_day_evidence_level': 'D1_current_official_catalogue_day_crosschecked_with_provider',
            'official_announcementTime_raw_ms': cp['announcementTime'],
            'official_announcementTime_asia_shanghai': cn_time.isoformat(),
            'official_announcementTime_precision_observed': 'clock_time_candidate' if is_ir else 'date_label_midnight',
            'official_storageTime': cp.get('storageTime'),
            'official_adjunct_url': 'https://static.cninfo.com.cn/' + cp['adjunctUrl'],
            'official_adjunct_path_day': path_day,
            'eastmoney_notice_date_raw': ep['notice_date'],
            'eastmoney_display_time_raw': ep.get('display_time'),
            'eastmoney_eiTime_raw': ep.get('eiTime'),
            'eastmoney_sort_date_raw': sort_date,
            'display_calendar_day_minus_official_day': (display.date() - cn_time.date()).days if display else None,
            'display_candidate_after_official_day_midnight': (display - dt.datetime.combine(cn_time.date(), dt.time())).total_seconds() if display else None,
            'official_and_provider_same_disclosure_day': cn_day == em_day,
            'official_url_day_matches_catalogue_day': cn_day == path_day,
            'normalized_title_matches': normalize_title(cp['announcementTitle']) == normalize_title(ep['title']),
            'title_width_or_punctuation_variation': ('（' in cp['announcementTitle'] or '）' in cp['announcementTitle']) and normalize_title(cp['announcementTitle']) == normalize_title(ep['title']),
            'date_or_identity_conflicts': checks,
            'first_publication_time_certified': None,
            'first_publication_minute_certified': False,
            'historical_input_eligible': False,
            'official_catalogue': {'snapshot_id': cs['snapshot_id'], 'row_hash': cr['row_hash'],
                'raw_sha256': cs['sha256'], 'raw_path': cs['raw_path'], 'retrieved_at': cs['retrieved_at'],
                'request_url': cs['url'], 'stored_publication_time': cr['publication_time'],
                'stored_availability_status': cr['availability_status']},
            'provider_catalogue': {'snapshot_id': es['snapshot_id'], 'row_hash': er['row_hash'],
                'raw_sha256': es['sha256'], 'raw_path': es['raw_path'], 'retrieved_at': es['retrieved_at'],
                'request_url': es['url'], 'stored_publication_time': er['publication_time'],
                'stored_availability_status': er['availability_status']},
            'local_pdf': {'relative_path': doc['relative_path'], 'source_sha256': doc['sha256'],
                'retrieved_at': doc['retrieved_at'], 'url': doc['url'], 'local_sha256_matches': pdf_hash_checks[art]['matches']},
            'official_pdf_identity_checks': official_copies,
            'time_evidence_gaps': gap,
        }
        rows.append(row)
    rows.sort(key=lambda r: (r['official_disclosure_day'], r['art_code']))

    # Show the NOTICE_DATE field from other dataset types separately. It is a current-provider
    # report/disclosure-date label, not an official per-document ID or first-public timestamp.
    notice_records = []
    for r in source.values():
        if r['date_field'] != 'NOTICE_DATE':
            continue
        p = json.loads(r['payload_json'])
        notice_records.append({
            'dataset': r['dataset'], 'snapshot_id': r['snapshot_id'], 'row_hash': r['row_hash'],
            'raw_sha256': snapshots[r['snapshot_id']]['sha256'], 'raw_path': snapshots[r['snapshot_id']]['raw_path'],
            'retrieved_at': snapshots[r['snapshot_id']]['retrieved_at'],
            'NOTICE_DATE_raw': p.get('NOTICE_DATE'), 'REPORT_DATE_raw': p.get('REPORT_DATE'),
            'UPDATE_DATE_raw': p.get('UPDATE_DATE'), 'stored_publication_time': r['publication_time'],
            'document_identity_certified_by_this_field': False, 'historical_input_eligible': False,
        })
    ids = {r['art_code'] for r in rows}
    mapped_cn = {r['official_announcement_id'] for r in rows}
    all_current_cn = []
    for r in source.values():
        if r['snapshot_id'].endswith(':refresh-20261015-v1') and r['dataset'].startswith(('cninfo_announcements', 'cninfo_ir')):
            all_current_cn.append(json.loads(r['payload_json'])['announcementId'])
    unmatched = {
        'local_pdf_art_codes_not_mapped': sorted(set(docs) - ids),
        'mapped_art_codes_without_local_pdf': sorted(ids - set(docs)),
        'current_official_announcement_ids_not_mapped': sorted(set(all_current_cn) - mapped_cn),
        'mapped_official_ids_not_in_current_catalogue': sorted(mapped_cn - set(all_current_cn)),
        'date_or_identity_conflicts': [r['art_code'] for r in rows if r['date_or_identity_conflicts']],
    }
    jitter = []
    for r in rows:
        curr = source[(r['provider_catalogue']['snapshot_id'], r['provider_catalogue']['row_hash'])]
        cp = json.loads(curr['payload_json'])
        prior = []
        for rr in source.values():
            if rr['dataset'].startswith('announcements') and rr['snapshot_id'] != curr['snapshot_id']:
                pp = json.loads(rr['payload_json'])
                if pp.get('art_code') == r['art_code']:
                    prior.append((snapshots[rr['snapshot_id']]['retrieved_at'], rr, pp))
        prior.sort(key=lambda t: t[0], reverse=True)
        if prior:
            _, rr, pp = prior[0]
            fields = sorted(k for k in set(pp) | set(cp) if pp.get(k) != cp.get(k))
            if fields:
                jitter.append({'art_code': r['art_code'], 'changed_fields': fields,
                    'current_snapshot_id': curr['snapshot_id'], 'prior_snapshot_id': rr['snapshot_id'],
                    'current_row_hash': curr['row_hash'], 'prior_row_hash': rr['row_hash'],
                    'changes': {k: {'prior': pp.get(k), 'current': cp.get(k)} for k in fields},
                    'display_delta_ms': int(round((em_time(cp['display_time']) - em_time(pp['display_time'])).total_seconds()*1000)) if fields == ['display_time'] else None,
                    'is_first_publication_revision_certified': False})
    counts = collections.Counter(r['display_calendar_day_minus_official_day'] for r in rows)
    minute_times = [r for r in rows if r['official_announcementTime_precision_observed'] == 'clock_time_candidate']
    summary = {
        'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'main_database_open_mode': 'ro', 'source_reconciliation_version': 'refresh-20261015-v1',
        'mapped_pdf_count': len(rows), 'ordinary_count': sum(r['category']=='ordinary_announcement' for r in rows),
        'investor_relations_count': len(minute_times),
        'official_disclosure_days_crosschecked': sum(r['official_and_provider_same_disclosure_day'] for r in rows),
        'official_adjunct_path_days_crosschecked': sum(r['official_url_day_matches_catalogue_day'] for r in rows),
        'official_catalogue_midnight_only_count': sum(r['official_announcementTime_precision_observed']=='date_label_midnight' for r in rows),
        'official_storageTime_nonnull_count': sum(r['official_storageTime'] is not None for r in rows),
        'title_width_or_punctuation_variation_count': sum(r['title_width_or_punctuation_variation'] for r in rows),
        'eastmoney_display_time_nonempty_count': sum(bool(r['eastmoney_display_time_raw']) for r in rows),
        'eastmoney_eiTime_nonempty_count': sum(bool(r['eastmoney_eiTime_raw']) for r in rows),
        'eastmoney_sort_date_nonempty_count': sum(bool(r['eastmoney_sort_date_raw']) for r in rows),
        'display_day_minus_official_day_counts': {str(k):v for k,v in sorted(counts.items(), key=lambda p: str(p[0]))},
        'actual_historical_first_publication_certified_count': 0,
        'historical_input_eligible_count': 0,
        'existing_official_identical_pdf_count': sum(bool(r['official_pdf_identity_checks']) for r in rows),
        'all_local_pdf_sha256_verified': all(v['matches'] for v in pdf_hash_checks.values()),
        'raw_catalogue_snapshot_hashes_verified': len(raw_hash_checks),
        'all_catalogue_raw_sha256_verified': all(v['matches'] for v in raw_hash_checks.values()),
        'provider_current_vs_previous_changed_row_count': len(jitter),
        'provider_current_vs_previous_changed_fields_counts': dict(collections.Counter(k for r in jitter for k in r['changed_fields'])),
        'unmatched_and_conflicts': unmatched,
        'NOTICE_DATE_record_count_all_stored_snapshots': len(notice_records),
        'NOTICE_DATE_by_dataset_including_retained_versions': dict(collections.Counter(r['dataset'] for r in notice_records)),
        'main_database_table_counts_unchanged_during_read_only_audit': before_counts == {r['name']: c.execute('SELECT COUNT(*) FROM "' + r['name'] + '"').fetchone()[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")},
        'limitations': [
            '312 reflects the three current returned catalogues, not a certificate of the entire internet or all possible disclosure categories.',
            'No historical acquisition log or archived first-seen timestamp acquired; current retrieval is never backdated.',
            'D1 day evidence does not certify a version existed before a trade decision; all historical eligibility remains false.',
            '4 IR clock times are candidate official-provider times; minute-level first-public semantics not independently certified.',
            '22 official PDFs were already verified identical in earlier rounds; remaining 290 official URLs are mapped, not newly downloaded or byte-certified.',
            'EM display_time/eiTime have no explicit time zone or documented immutable first-public meaning in the archived response.',
            'NOTICE_DATE is dataset-specific provider metadata and cannot serve as a universal release instant.',
        ],
    }
    checks = [
        ('exactly_312_unique_local_pdfs_mapped', len(rows)==312 and len(ids)==312 and ids==set(docs)),
        ('ordinary308_and_ir4_separate', summary['ordinary_count']==308 and len(minute_times)==4),
        ('all_312_official_ids_unique_and_complete', len(mapped_cn)==312 and set(all_current_cn)==mapped_cn),
        ('all_312_official_days_match_provider_and_path', summary['official_disclosure_days_crosschecked']==312 and summary['official_adjunct_path_days_crosschecked']==312),
        ('all_312_normalized_titles_match', all(r['normalized_title_matches'] for r in rows)),
        ('all_308_ordinary_timestamps_only_midnight', summary['official_catalogue_midnight_only_count']==308),
        ('all_312_official_storageTime_missing', summary['official_storageTime_nonnull_count']==0),
        ('all_312_current_pdf_hashes_match', summary['all_local_pdf_sha256_verified']),
        ('all_16_current_catalogue_raw_hashes_match', len(raw_hash_checks)==16 and summary['all_catalogue_raw_sha256_verified']),
        ('all_22_official_pdf_identity_checks_retained_and_valid', summary['existing_official_identical_pdf_count']==22 and all(p['local_sha256_matches'] and p['same_pdf_as_eastmoney'] for r in rows for p in r['official_pdf_identity_checks'])),
        ('first_public_and_historical_eligibility_not_fabricated', all(r['first_publication_time_certified'] is None and not r['historical_input_eligible'] for r in rows)),
        ('previous104_rows_only_display_time_jitter', len(jitter)==104 and all(r['changed_fields']==['display_time'] for r in jitter)),
        ('main_database_unchanged_during_read_only_audit', summary['main_database_table_counts_unchanged_during_read_only_audit']),
    ]
    jdump(OUT/'announcement_time_ledger.json', rows)
    jdump(OUT/'announcement_time_gaps.json', [{'art_code': r['art_code'], 'official_announcement_id':r['official_announcement_id'], 'official_disclosure_day':r['official_disclosure_day'], 'time_evidence_gaps':r['time_evidence_gaps'], 'historical_input_eligible':False} for r in rows])
    jdump(OUT/'unmatched_conflicts.json', unmatched)
    jdump(OUT/'provider_time_revisions.json', jitter)
    jdump(OUT/'provider_NOTICE_DATE_fields.json', notice_records)
    jdump(OUT/'source_hash_validation.json', {'catalogue_snapshots':raw_hash_checks, 'pdfs':pdf_hash_checks})
    jdump(OUT/'summary.json', summary)
    jdump(OUT/'validation.json', {'checks':[{'name':k,'passed':v} for k,v in checks], 'all_passed':all(v for k,v in checks)})
    fields = ['art_code','official_announcement_id','category','official_disclosure_day','official_announcementTime_asia_shanghai','official_announcementTime_precision_observed','eastmoney_notice_date_raw','eastmoney_display_time_raw','eastmoney_eiTime_raw','eastmoney_sort_date_raw','display_calendar_day_minus_official_day','first_publication_time_certified','historical_input_eligible','title','official_adjunct_url']
    with (OUT/'announcement_time_ledger.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({'validation':checks},ensure_ascii=False))

if __name__ == '__main__':
    main()
