#!/usr/bin/env python3
"""Read-only local evidence audit. Never requests data or writes source directories."""
import collections, datetime, hashlib, json, pathlib, re, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent
SCOPES = [ROOT / 'work' / n for n in [
    'market_industry_oct22', 'market_warmup_finalize_oct22',
    'events_publication_oct22', 'conditions_finish_oct22',
    'chip_full_capture_oct17', 'chip_audit_oct22']]
FILES = {}
REFS = collections.defaultdict(list)
ISSUES = []
REQUESTS = {}

def rel(p):
    try: return str(p.relative_to(ROOT))
    except ValueError: return str(p)

def issue(code, severity, detail, **kw):
    ISSUES.append(dict(code=code, severity=severity, detail=detail, **kw))

def addfile(p):
    p = pathlib.Path(p).resolve()
    if str(p) in FILES: return FILES[str(p)]
    if not p.is_file(): return None
    b = p.read_bytes()
    e = dict(project_relative_path=rel(p), original_absolute_path=str(p),
             bytes=len(b), sha256=hashlib.sha256(b).hexdigest())
    FILES[str(p)] = e
    return e

def resolve(value, src):
    p = pathlib.Path(value)
    if p.is_absolute(): return p
    local = src.parent / p
    return local if local.exists() else ROOT / p

def walk(o, src, ptr='$'):
    if isinstance(o, list):
        for i,v in enumerate(o): walk(v, src, f'{ptr}[{i}]')
    elif isinstance(o,dict):
        pathkeys = {'raw_path','path','local_original_path','official_saved_path',
                    'attempt_file','previous_time_audit_reference'}
        for k,v in o.items():
            if k in pathkeys and isinstance(v,str) and not v.startswith(('http:','https:')):
                p = resolve(v,src)
                # Some operational path fields deliberately point to directories.
                if p.is_dir(): continue
                expected = {'raw_path':o.get('sha256',o.get('source_sha256')),
                            'path':o.get('sha256'),
                            'local_original_path':o.get('local_original_sha256'),
                            'official_saved_path':o.get('official_sha256')}.get(k)
                e = addfile(p)
                rr=dict(reference_file=rel(src),json_pointer=f'{ptr}.{k}',
                        recorded_path=v,was_absolute=pathlib.Path(v).is_absolute(),
                        expected_sha256=expected)
                if rr not in REFS[str(p.resolve())]: REFS[str(p.resolve())].append(rr)
                if e is None:
                    issue('missing_referenced_file','error','Recorded local evidence file is absent',
                          reference=rr,resolved_path=str(p))
                elif expected and expected != e['sha256']:
                    issue('hash_mismatch','error','Recorded evidence hash does not match bytes',
                          reference=rr,actual_sha256=e['sha256'])
                if e and k=='raw_path' and (o.get('name') or o.get('id')) and o.get('url'):
                    request_id = o.get('id',o.get('name'))
                    payload={k:o.get(k) for k in ['url','method','parameters','retrieved_at',
                              'retrieved_at_utc','requested_at_utc','status','error',
                              'requested_range','response_key','provider_rows','accepted_rows',
                              'rejected_rows','min_date','max_date'] if k in o}
                    key=json.dumps([request_id,str(p.resolve()),payload],sort_keys=True,ensure_ascii=False)
                    if key not in REQUESTS:
                        REQUESTS[key]=dict(request_id=request_id,
                              source_sha256=e['sha256'],raw_project_relative_path=rel(p.resolve()),
                              **payload,manifest_references=[])
                    mr=dict(reference_file=rel(src),json_pointer=ptr)
                    if mr not in REQUESTS[key]['manifest_references']:
                        REQUESTS[key]['manifest_references'].append(mr)
            if k not in ['data','raw_row']:
                walk(v,src,f'{ptr}.{k}')

for scope in SCOPES:
    for p in sorted(scope.rglob('*')):
        if p.is_file(): addfile(p)
    for p in sorted(scope.glob('*.json')):
        try: walk(json.loads(p.read_text()),p)
        except Exception as e: issue('json_parse_error','error',str(e),file=rel(p))

# Compact repeated path-reference defects without suppressing their source locations.
by_id=collections.defaultdict(list)
for r in REQUESTS.values(): by_id[r['request_id']].append(r)
ROW_AUDITS=[]
RAWCACHE={}
def response_rows(req, row):
    path=ROOT/req['raw_project_relative_path']
    if str(path) not in RAWCACHE:
        s=path.read_text()
        try: d=json.loads(s)
        except json.JSONDecodeError:
            s=s[s.index('=')+1:].strip().rstrip(';')
            d=json.loads(s)
        RAWCACHE[str(path)]=d
    d=RAWCACHE[str(path)]
    if row.get('source',row.get('provider'))=='eastmoney': return d['data']['klines']
    sym=row['symbol'];code=('sh' if sym.endswith('.SH') else 'sz')+sym[:6]
    obj=d['data'][code]
    adj=row.get('adjustment_flag',row.get('adjustment'))
    key={'0':'day','1':'qfqday','2':'hfqday'}.get(adj,'day')
    if key not in obj and 'day' in obj:key='day'
    return obj[key]

for filename in ['work/market_industry_oct22/market_rows_unique.json',
                 'work/market_warmup_finalize_oct22/market_rows_all_endpoints.json']:
    rows=json.loads((ROOT/filename).read_text())
    counters=collections.Counter(); anomalies=[]
    for i,row in enumerate(rows):
        rid=row.get('source_request_id',row.get('source_request'))
        candidates=[r for r in by_id[rid] if r['source_sha256']==row.get('source_sha256')]
        counters['rows']+=1
        if not candidates:
            counters['unresolved_source']+=1;anomalies.append(dict(index=i,request_id=rid,kind='unresolved'));continue
        counters['source_request_and_hash_resolved']+=1
        req=candidates[0]
        try:
            raw=response_rows(req,row);pos=row['source_row_index']
            original=raw[pos]
            if original==row['raw_row']:counters['exact_raw_row_match']+=1
            else:
                counters['raw_row_mismatch']+=1;anomalies.append(dict(index=i,request_id=rid,kind='raw_row_mismatch'))
            date=(original.split(',')[0] if isinstance(original,str) else original[0])
            if date==row.get('trade_date',row.get('date')):counters['date_match']+=1
            else:counters['date_mismatch']+=1
        except Exception as e:
            counters['raw_parse_error']+=1;anomalies.append(dict(index=i,request_id=rid,kind='raw_parse_error',error=repr(e)))
    ROW_AUDITS.append(dict(file=filename,counters=dict(counters),anomalies=anomalies))

# Annual framing and apparent 640-row caps: preserve outside rows and use bounded selection.
framing=json.loads((ROOT/'work/market_warmup_finalize_oct22/tencent_new_response_framing.json').read_text())
annual_mislabels=[]
for request in REQUESTS.values():
    param=request.get('parameters',{}).get('param')
    if param and request.get('requested_range'):
        parts=param.split(',')
        if len(parts)>3:
            actual={'start':parts[2],'end':parts[3]}
            if actual != request['requested_range']:
                annual_mislabels.append(dict(request_id=request['request_id'],
                    recorded_requested_range=request['requested_range'],
                    request_parameter_range=actual,raw_path=request['raw_project_relative_path']))
if annual_mislabels:
    issue('requested_range_metadata_not_request_parameters','warning',
          'Historical annual requests carry the overall collector range in requested_range; URL/parameters and response date span must prevail.',
          unique_request_ids=sorted({r['request_id'] for r in annual_mislabels}),
          details=annual_mislabels)

CHIPS=[]
for name in ['chip_full_capture_oct17','chip_audit_oct22']:
    base=ROOT/'work'/name
    rows=json.loads((base/'records.json').read_text())
    accepted=[r for r in rows if r.get('accepted')]
    missing=[];mismatched=[];date_bad=[];html_bad=[];summaries=collections.defaultdict(set)
    for row in rows:
        folder=base/'records'/row['id']
        for leaf in ['record.json','summary.html','kline.html','chart.jpg','ax.txt']:
            if not (folder/leaf).is_file():missing.append(rel(folder/leaf))
        if (folder/'record.json').exists():
            copy=json.loads((folder/'record.json').read_text())
            if copy!=row:mismatched.append(row['id'])
        if (folder/'summary.html').exists() and (folder/'kline.html').exists():
            values=re.findall(r'<td class="qcyq_t_v">\s*([^<]*)\s*</td>',(folder/'summary.html').read_text())
            kdate=re.findall(r'<td class="kline_date">\s*([^<]*)\s*</td>',(folder/'kline.html').read_text())
            if values!=row.get('values') or kdate!=[row.get('kline',{}).get('时间')]:
                html_bad.append(dict(id=row['id'],summary_values=values,kline_date=kdate))
        if row.get('accepted'):
            date=row.get('date');kl=row.get('kline',{}).get('时间')
            post=row.get('post',{});postkl=post.get('kline_date',post.get('kline'))
            if date!=row.get('expected') or date!=kl or date!=post.get('date') or date!=postkl:
                date_bad.append(row['id'])
            summaries[date].add(tuple(row.get('values',[])))
    target=json.loads((base/'target_dates.json').read_text()) if (base/'target_dates.json').exists() else None
    if isinstance(target,dict):target=target.get('dates',target.get('target_dates'))
    date_set=set(summaries)
    CHIPS.append(dict(scope=rel(base),attempts=len(rows),accepted=len(accepted),
        unique_accepted_dates=len(date_set),missing_artifact_files=missing,
        record_copy_mismatches=mismatched,date_synchronization_failures=date_bad,
        html_evidence_mismatches=html_bad,
        same_session_multi_value_dates=[d for d,v in summaries.items() if len(v)>1],
        missing_target_dates=sorted(set(target or [])-date_set),
        historical_input_eligible_true=sum(bool(r.get('historical_input_eligible')) for r in rows)))

# Verify that deduplication has not discarded conflicting overlaps or supporting requests.
all_industry=json.loads((ROOT/'work/market_industry_oct22/all_request_market_rows.json').read_text())
unique_industry=json.loads((ROOT/'work/market_industry_oct22/market_rows_unique.json').read_text())
groups=collections.defaultdict(list)
def rowkey(r): return tuple(r.get(k) for k in ['symbol','source','adjustment','trade_date'])
for r in all_industry:groups[rowkey(r)].append(r)
conflicts=[];support_errors=[]
for r in unique_industry:
    group=groups[rowkey(r)]
    values={json.dumps([x.get(k) for k in ['open','high','low','close','volume_raw','amount_raw','turnover_raw']]) for x in group}
    if len(values)>1:conflicts.append(rowkey(r))
    if {x['source_request_id'] for x in group} != set(r['all_supporting_request_ids']):support_errors.append(rowkey(r))
DEDUP=dict(request_rows=len(all_industry),unique_rows=len(unique_industry),
           independent_group_count=len(groups),duplicate_overlap_rows=sum(len(g)-1 for g in groups.values()),
           normalized_field_conflicts=conflicts,supporting_request_id_mismatches=support_errors,
           input_and_output_key_sets_match=set(groups)=={rowkey(r) for r in unique_industry})
if conflicts or support_errors or not DEDUP['input_and_output_key_sets_match']:
    issue('deduplication_lineage_defect','error','Industry deduplication lineage inconsistent',details=DEDUP)

# Restoration dependency closure against the earlier 31 MB incremental evidence package.
zip_path=ROOT.parent.parent/'项目归档/ni/20261022_五项数据补缺/五项数据补缺_原始数据与证据_20261022.zip'
ZIPCHECK={}
if zip_path.exists():
    with zipfile.ZipFile(zip_path) as z:
        names=set(z.namelist());missing=[];checked=0;bad=[]
        referenced=set(REFS)
        for ap in referenced:
            p=pathlib.Path(ap)
            rp=rel(p);member='project/'+rp
            if member not in names:missing.append(rp);continue
            checked+=1
            if hashlib.sha256(z.read(member)).hexdigest()!=FILES[ap]['sha256']:bad.append(rp)
        ZIPCHECK=dict(archive=str(zip_path),referenced_files_checked=checked,
            absent_referenced_files=sorted(missing),hash_mismatches=bad,
            archive_is_incremental_not_self_contained=bool(missing))
        if missing:
            issue('incremental_archive_external_dependencies','warning',
                  'Earlier incremental archive does not independently contain all local evidence referenced by staged manifests. Full-project backup or dependency-closure export is required.',
                  missing_count=len(missing),missing_paths=sorted(missing))

absrefs=sum(r['was_absolute'] for refs in REFS.values() for r in refs)
if absrefs:
    issue('absolute_paths_need_restore_mapping','warning',
          'Existing metadata embeds original-machine absolute paths. This registry provides project-relative aliases without rewriting original evidence.',
          absolute_reference_occurrences=absrefs,
          restore_rule='Resolve project_relative_path under chosen restored project root; keep original_absolute_path only as provenance.')

for audit in ROW_AUDITS:
    if audit['anomalies']:issue('row_lineage_anomalies','error','Rows did not exactly resolve to recorded raw responses',file=audit['file'],count=len(audit['anomalies']))
for chip in CHIPS:
    if chip['missing_artifact_files'] or chip['record_copy_mismatches'] or chip['date_synchronization_failures'] or chip['html_evidence_mismatches']:
        issue('chip_evidence_anomalies','error','Chip snapshot consistency issue',details=chip)

content=collections.defaultdict(list)
entries=[]
for ap,e in sorted(FILES.items(),key=lambda x:x[1]['project_relative_path']):
    refs=REFS.get(ap,[])
    entry={**e,'references':refs}
    entries.append(entry);content[e['sha256']].append(e['project_relative_path'])
summary=dict(client_date='2026-10-22',generated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    mode='local_read_only_source_audit',source_dirs=[rel(p) for p in SCOPES],
    main_database_sqlite_connection_opened=False,network_used=False,browser_used=False,
    registered_files=len(entries),total_registered_bytes=sum(e['bytes'] for e in entries),
    unique_content_hashes=len(content),source_requests=len(REQUESTS),
    referenced_file_paths=len(REFS),missing_referenced_files=sum(i['code']=='missing_referenced_file' for i in ISSUES),
    hash_mismatches=sum(i['code']=='hash_mismatch' for i in ISSUES),
    severity_counts=dict(collections.Counter(i['severity'] for i in ISSUES)),
    market_row_lineage=ROW_AUDITS,chip_snapshot_audits=CHIPS,
    market_industry_deduplication=DEDUP,
    annual_response_framing=dict(requests=len(framing),returned_rows=sum(r['returned_rows'] for r in framing),
        accepted_annual_rows=sum(r['accepted_annual_window_rows'] for r in framing),
        outside_annual_window_rows=sum(r['outside_annual_window_rows'] for r in framing),
        outside_rows_preserved_in_raw=True),
    previous_incremental_archive_dependency_audit=ZIPCHECK,
    limitations=['Checks local existence, exact-byte hashes, raw-row ancestry and visible-record consistency only.',
                'Does not certify vendor truth, chip algorithm, historical point-in-time correctness, executable conditions or completeness of unobserved sources.',
                'Directories dated Oct22 can legitimately preserve retrievals performed Oct18; directory labels are batch labels, not retrieval timestamps.'])
(OUT/'evidence_registry_seed.json').write_text(json.dumps(dict(schema_version=1,project_root_at_audit=str(ROOT),
    restore_mapping='Use project_relative_path under restored project root; original_absolute_path is historical provenance.',
    files=entries,content_groups=[dict(sha256=h,paths=ps) for h,ps in sorted(content.items())],
    requests=list(REQUESTS.values())),ensure_ascii=False,indent=2))
(OUT/'lineage_issues.json').write_text(json.dumps(dict(summary=summary,issues=ISSUES),ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
