#!/usr/bin/env python3
"""Verify identity/completeness of local OCR results, never OCR factual accuracy."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
jobs = json.loads((HERE / 'jobs.json').read_text())
rows = [json.loads(line) for line in (HERE / 'pages.jsonl').read_text().splitlines()]
key = lambda x: (x['art_code'], x['page_number'], x['source_sha256'])
job_map = {key(x): x for x in jobs}
row_keys = [key(x) for x in rows]
checks = {
    '185_original_gap_pages': len(jobs) == 185,
    '185_page_results': len(rows) == 185,
    'no_duplicate_page_identity': len(set(row_keys)) == len(row_keys),
    'all_original_gap_pages_have_result': set(row_keys) == set(job_map),
    'all_original_pdf_hashes_unchanged': all(
        hashlib.sha256(Path(j['pdf_path']).read_bytes()).hexdigest() == j['source_sha256']
        for j in jobs
    ),
    'source_hash_checked_before_each_ocr': all(r.get('source_hash_verified_before_ocr') for r in rows),
    'all_page_outputs_link_original_url_title_notice_date': all(
        r['url'] and r['title'] and r['notice_date'] and r['page_number'] > 0
        for r in rows
    ),
    'each_observation_has_coordinates_and_confidence': all(
        'confidence' in o and len(o['box_pixels']) == 4
        for r in rows for o in r['observations']
    ),
    'observation_text_matches_page_text': all(
        '\n'.join(o['text'] for o in r['observations']) == r['text'] for r in rows
    ),
    'all_numeric_and_historical_inputs_unapproved': all(
        not r['numeric_facts_verified'] and not r['historical_input_eligible'] for r in rows
    ),
    'no_failure_labeled_blank': all(
        r['status'] == 'failed' if r['error'] else r['status'] != 'failed' for r in rows
    ),
    'no_page_manually_certified': all(r['manual_review_status'] == 'not_reviewed' for r in rows),
}
models = json.loads((HERE / 'model_sources.json').read_text())
checks['model_file_hashes_still_match'] = all(
    hashlib.sha256((HERE / 'deps' / 'rapidocr' / 'models' / m['name']).read_bytes()).hexdigest() == m['sha256']
    for m in models
)
review_queue = sorted([
    {'art_code': r['art_code'], 'page_number': r['page_number'],
     'source_sha256': r['source_sha256'], 'title': r['title'],
     'mean_confidence': r['mean_confidence'], 'minimum_confidence': r['minimum_confidence'],
     'low_confidence_lines': r['low_confidence_lines'],
     'status': r['status'], 'priority_is_heuristic_only': True}
    for r in rows
], key=lambda r: (-r['low_confidence_lines'], r['mean_confidence'] or 0))
(HERE / 'review_queue.json').write_text(json.dumps(review_queue, ensure_ascii=False, indent=2))
text_groups = defaultdict(list)
for r in rows:
    # Repeated annexes can occur in different announcements. Keep all source links.
    if r['text'].strip():
        digest = hashlib.sha256(r['text'].encode('utf-8')).hexdigest()
        text_groups[digest].append({'art_code': r['art_code'], 'page_number': r['page_number'],
                                    'source_sha256': r['source_sha256']})
duplicates = [{'ocr_text_sha256': h, 'pages': ps,
               'status': 'identical_ocr_text_possible_repeated_evidence_not_collapsed'}
              for h, ps in text_groups.items() if len(ps) > 1]
(HERE / 'duplicate_text_groups.json').write_text(json.dumps(duplicates, ensure_ascii=False, indent=2))
result = {
    'all_identity_and_completeness_checks_passed': all(checks.values()),
    'checks': checks, 'pages': len(rows), 'documents': len({r['art_code'] for r in rows}),
    'statuses': dict(Counter(r['status'] for r in rows)),
    'total_chars': sum(len(r['text']) for r in rows),
    'total_observations': sum(len(r['observations']) for r in rows),
    'pages_with_any_line_confidence_below_0_8': sum(r['low_confidence_lines'] > 0 for r in rows),
    'total_lines_confidence_below_0_8': sum(r['low_confidence_lines'] for r in rows),
    'elapsed_seconds_for_pages': sum(r['elapsed_seconds'] for r in rows),
    'completed_page_manual_review': 0, 'certified_numeric_facts': 0,
    'identical_ocr_text_duplicate_groups': len(duplicates),
    'pages_in_identical_ocr_text_groups': sum(len(g['pages']) for g in duplicates),
    'scope': 'Checks verify linkage and output completeness only, not OCR factual accuracy.',
    'known_failure_modes': [
        'Signature and seal graphics produce spurious text.',
        'Digits and punctuation can be misrecognized even at high OCR confidence.',
        'Sideways table output may be ordered by original columns; no table reconstruction is certified.',
        'Current download and signature dates do not establish first historical publication time.',
    ],
}
(HERE / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
assert all(checks.values())
