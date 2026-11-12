"""Read-only, bounded accounting policy review; never mutates the master database."""
from pathlib import Path
import sqlite3, json, hashlib, urllib.request, concurrent.futures
from decimal import Decimal
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "outputs/高德红外数据库"
WORK = Path(__file__).resolve().parent
con = sqlite3.connect(f"file:{DATA / '高德红外_2023起.sqlite'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
raw = json.loads((DATA / "公告事件候选核对.json").read_text())
candidates = [x for x in raw['evidence_candidates'] if x['category'] == 'accounting_revision']
checked_at = datetime.now(timezone.utc).isoformat()
docs = {}
for art in sorted({x['art_code'] for x in candidates}):
    d = dict(con.execute('select * from announcement_documents where art_code=?', (art,)).fetchone())
    path = DATA / d['relative_path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == d['sha256'], art
    catalogue = con.execute('''select s.payload_json from announcement_reconciliation a
      join source_records s on s.snapshot_id=a.cninfo_snapshot_id and s.row_hash=a.cninfo_row_hash
      join source_records e on e.snapshot_id=a.eastmoney_snapshot_id and e.row_hash=a.eastmoney_row_hash
      where json_extract(e.payload_json,'$.art_code')=?''', (art,)).fetchone()
    d['official_catalogue_url'] = None
    if catalogue:
        cp = json.loads(catalogue['payload_json'])
        d['official_catalogue_url'] = 'https://static.cninfo.com.cn/' + cp['adjunctUrl']
        d['cninfo_announcement_id'] = cp['announcementId']
    d['source_file_hash_verified'] = True
    docs[art] = d

policy_arts = ['AN202304191585591326', 'AN202404151630236046',
               'AN202408261639461688', 'AN202504241661802961']

def fetch_counterpart(art):
    d = docs[art]
    out = {'art_code': art, 'url': d['official_catalogue_url'],
           'announcement_id': d['cninfo_announcement_id'], 'provider_source_sha256': d['sha256']}
    try:
        req = urllib.request.Request(out['url'], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=25) as response:
            b = response.read(10_000_001)
        if len(b) > 10_000_000 or not b.startswith(b'%PDF'):
            raise ValueError('response is not a bounded PDF')
        out['retrieved_at'] = datetime.now(timezone.utc).isoformat()
        out['source_sha256'] = hashlib.sha256(b).hexdigest()
        out['comparison'] = 'identical_bytes' if out['source_sha256'] == d['sha256'] else 'different_bytes_requires_review'
        name = f"cninfo_{art}_{out['source_sha256'][:12]}.pdf"
        (WORK / name).write_bytes(b)
        out['path'] = str(WORK / name)
        out['error'] = None
    except Exception as exc:
        out.update({'comparison': 'fetch_failed', 'error': str(exc)})
    return out

if __name__ == '__main__':
    manifest = WORK / 'official_counterparts.json'
    if manifest.exists():
        counterparts = json.loads(manifest.read_text())
        assert {x['art_code'] for x in counterparts} == set(policy_arts)
        for item in counterparts:
            assert item['comparison'] == 'identical_bytes'
            assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['source_sha256']
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            counterparts = list(pool.map(fetch_counterpart, policy_arts))
    (WORK / 'official_counterparts.json').write_text(json.dumps(counterparts, ensure_ascii=False, indent=2))
    seen_pages = set()
    classified = []
    for i, item in enumerate(candidates):
        d = docs[item['art_code']]
        page = con.execute('select * from announcement_pages where art_code=? and page_number=?',
                           (item['art_code'], item['page'])).fetchone()
        assert page['source_sha256'] == d['sha256']
        assert item['matched_term'] in page['text']
        page_key = (item['art_code'], item['page'])
        duplicate_on_page = page_key in seen_pages
        seen_pages.add(page_key)
        if item['art_code'] == policy_arts[0]:
            group, label = 'ex16_early_no_restatement_claim', 'explicit_negated_restatement_claim_not_quantified_revision'
            explanation = '2023年公告明确说不涉及以前年度追溯调整；只是当次披露声明，与2024年量化追溯披露分版本保存。'
        elif item['art_code'] in ['AN202404151630236046','AN202404151630235973','AN202404151630235965','AN202404151630235969']:
            group = 'ex16_2024_disclosed_restatement'
            label = 'quantified_policy_disclosure' if item['art_code'] == policy_arts[1] else 'same_policy_supporting_repeat'
            explanation = '解释16号导致2023年1月1日资产及负债追溯；摘要、年度正文和附注、审计报告不是新事件。'
        elif item['art_code'] in ['AN202408261639461688','AN202408261639461647','AN202408261639461683','AN202408261639461663','AN202410281640541892']:
            group = 'ex17_2024_halfyear_disclosed_reclassification'
            label = 'quantified_policy_disclosure' if item['art_code'] == policy_arts[2] else 'same_policy_supporting_repeat'
            explanation = '解释17号质保金负债流动/非流动分类追溯；金额按2024半年度版本保存。'
        else:
            group = 'ex18_and_ex17_2025_disclosed_comparative_update'
            label = 'quantified_policy_disclosure' if item['art_code'] == policy_arts[3] else 'same_policy_supporting_repeat'
            explanation = '解释18号营业成本/销售费用重分类，与年报中解释17+18负债合并追溯分别记录；未见本组确认会计差错。'
            if item['art_code'] == 'AN202504281663932495':
                explanation += '一季报勾选会计政策变更，差错更正未勾选；该页主要比较指标前后相同，不能认为所有指标都改动。'
        base_ids = con.execute('''select candidate_id from announcement_event_candidates
            where art_code=? and page_number=? and json_extract(payload_json,'$.excerpt')=?''',
            (item['art_code'], item['page'], item['excerpt'])).fetchall()
        assert len(base_ids) == 1, (item['art_code'], item['page'], len(base_ids))
        classified.append({
            'candidate_id': base_ids[0]['candidate_id'],
            'review_input_hash': hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            'candidate_index_in_accounting_subset': i, 'art_code': item['art_code'],
            'page_number': item['page'], 'source_sha256': d['sha256'], 'title': d['title'],
            'provider_notice_date': d['notice_date'], 'source_url': d['url'],
            'official_catalogue_url': d['official_catalogue_url'],
            'policy_version_group': group, 'classification': label,
            'duplicate_keyword_fragment_on_same_page': duplicate_on_page,
            'explanation': explanation, 'matched_term': item['matched_term'], 'excerpt': item['excerpt'],
            'review_method': 'full_relevant_page_text_and_selected_table_visual_review',
            'historical_input_eligible': False,
            'first_publication_time_status': 'unverified_catalogue_day_not_precise_first_publication_time',
            'reviewed_at': checked_at,
        })

    observations = []
    def add_rows(group, art, page_number, effective_date, affected_period, scope, rows, unit_evidence):
        d = docs[art]
        for metric, before, delta, after in rows:
            observation = {'policy_version_group': group, 'art_code': art, 'page_number': page_number,
                'source_sha256': d['sha256'], 'provider_notice_date': d['notice_date'],
                'source_url': d['url'], 'official_catalogue_url': d['official_catalogue_url'],
                'unit': 'CNY', 'unit_evidence': unit_evidence, 'statement_scope': scope,
                'metric_original_label': metric, 'before_decimal': before,
                'adjustment_decimal': delta, 'after_decimal': after,
                'table_period_heading_as_printed': affected_period,
                'company_stated_effective_date': effective_date,
                'affected_period': affected_period,
                'availability_status': 'original_selected_table_visually_verified_first_publication_unverified',
                'historical_input_eligible': False, 'first_publication_time': None,
                'blank_is_not_zero': True, 'reviewed_at': checked_at}
            if before is not None and delta is not None:
                observation['arithmetic_check'] = Decimal(before) + Decimal(delta) == Decimal(after)
                assert observation['arithmetic_check'], observation
            else:
                observation['arithmetic_check'] = None
            identity = {k: observation[k] for k in ['policy_version_group','art_code','page_number',
                'source_sha256','statement_scope','metric_original_label','before_decimal',
                'adjustment_decimal','after_decimal','affected_period']}
            observation['observation_id'] = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            observations.append(observation)

    group = 'ex16_2024_disclosed_restatement'
    art = 'AN202404151630236046'
    unit = {'status': 'cross_document_exact_table_correspondence', 'art_code':'AN202404151630235969',
            'page_number':45, 'source_sha256':docs['AN202404151630235969']['sha256'],
            'explanation':'审计报告页头明确本附注人民币元列示；8行表格与政策公告相同；两页均已视觉核对。'}
    add_rows(group, art, 2, '2023-01-01', '2023-01-01', 'consolidated', [
        ('资产合计','8887797506.62','6018546.37','8893816052.99'),
        ('其中：递延所得税资产','136775483.43','6018546.37','142794029.80'),
        ('负债合计','1764425608.02','6018546.37','1770444154.39'),
        ('其中：递延所得税负债','12560481.79','6018546.37','18579028.16')],unit)
    add_rows(group, art, 2, '2023-01-01', '2023-01-01', 'parent_company', [
        ('资产合计','9196154063.06','4688591.76','9200842654.82'),
        ('其中：递延所得税资产','85063509.93','4688591.76','89752101.69'),
        ('负债合计','2811439710.99','4688591.76','2816128302.75'),
        ('其中：递延所得税负债','1519650.00','4688591.76','6208241.76')],unit)

    group = 'ex17_2024_halfyear_disclosed_reclassification'
    art = 'AN202408261639461688'
    unit = {'status':'cross_document_financial_money_context', 'art_code':'AN202504241661802959',
            'page_number':63, 'source_sha256':docs['AN202504241661802959']['sha256'],
            'explanation':'政策公告本页未印单位；后续年报同一调整前余额表明确单位元。该版本调整额4729772.54必须保留，不能替换成年报合并调整额。'}
    for scope, before_values in [('consolidated',['1499707286.36','434260109.62','337710695.04']),
                                ('parent_company',['1335741404.16','346389528.46','152845708.35'])]:
        b0,b1,b2=before_values
        dlt=Decimal('4729772.54')
        rows=[('流动负债合计',b0,str(-dlt),str(Decimal(b0)-dlt)),
              ('其中：应付账款',b1,str(-dlt),str(Decimal(b1)-dlt)),
              ('非流动负债合计',b2,str(dlt),str(Decimal(b2)+dlt)),
              ('其中：其他非流动负债',None,str(dlt),str(dlt))]
        add_rows(group,art,2,'2024-01-01','2024-01-01',scope,rows,unit)

    group = 'ex18_2025_disclosed_cost_reclassification'
    art = 'AN202504241661802961'
    unit = {'status':'explicit_on_original_page', 'explanation':'合并及母公司表分别标单位元。'}
    add_rows(group,art,2,'2024-01-01','2023年度','consolidated',[
        ('营业成本','1359088447.72','3083668.19','1362172115.91'),
        ('销售费用','99596349.51','-3083668.19','96512681.32')],unit)
    add_rows(group,art,2,'2024-01-01','2023年度','parent_company',[
        ('营业成本','987330719.85','1161243.00','988491962.85'),
        ('销售费用','9126937.61','-1161243.00','7965694.61')],unit)

    group = 'ex17_plus_ex18_2025_disclosed_combined_liability_update'
    art = 'AN202504241661802959'
    unit = {'status':'same_report_duplicate_explicit_unit', 'page_number':63,
            'explanation':'同报告63页相同表标单位元；133页复述。133页完整合并及母公司表已视觉核对。'}
    for scope,bvals,dlt in [('consolidated',['1499707286.36','434260109.62','337710695.04'],Decimal('5285772.54')),
                          ('parent_company',['1335741404.16','346389528.46','152845708.35'],Decimal('4729772.54'))]:
        b0,b1,b2=bvals
        add_rows(group,art,133,'2024-01-01','2024-01-01',scope,[
            ('流动负债合计',b0,str(-dlt),str(Decimal(b0)-dlt)),
            ('其中：应付账款',b1,str(-dlt),str(Decimal(b1)-dlt)),
            ('非流动负债合计',b2,str(dlt),str(Decimal(b2)+dlt)),
            ('其中：其他非流动负债',None,str(dlt),str(dlt))],unit)

    result = {'schema_version':'1.0','reviewed_at':checked_at,
              'scope':'已有公告会计候选逐段去重分类；选定表格28行核对；不是完整财务修订链认证',
              'candidate_count':len(classified),'distinct_candidate_pages':len(seen_pages),
              'source_documents_count':len(docs),'classified_candidates':classified,
              'observations':observations,'source_documents':list(docs.values()),
              'official_counterparts':counterparts,
              'limitations':[
                  '官方公告日期、签署日期、文件抓取时间不是精确首次公开时间；所有历史输入准入仍为False。',
                  '51段不是51件会计事件，同一页关键词重复、摘要与年报附注复述不作为新事件。',
                  '2023年公告不涉及追溯的声明与2024年量化披露按各自版本保留，不覆盖早期原件。',
                  '2024半年度与2024年度披露的合并负债重分类不同；后者为解释17+18的共同披露，不能凭差额独立归因。',
                  '2024年度133页将利润表行与2024年1月1日表头放同一表；成本行改用2025政策公告明确2023年度来源，不自动按该表头映射日期。',
                  '空白调整前单元格保留null，不填0；未核全量会计差错、更正、财务版本链或估计变更。']}
    (WORK/'会计修订候选核对.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'candidates':len(classified),'pages':len(seen_pages),'documents':len(docs),
                      'observations':len(observations), 'arithmetic_rows':sum(x['arithmetic_check'] is True for x in observations),
                      'blank_before_rows':sum(x['before_decimal'] is None for x in observations),
                      'official_counterparts_identical':sum(x['comparison']=='identical_bytes' for x in counterparts)},ensure_ascii=False))
