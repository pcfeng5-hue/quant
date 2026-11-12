"""Cross-track release checks, linking independent reviews and immutable source hashes."""
from pathlib import Path
import csv, hashlib, json, re, shutil, sqlite3

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/三线研究启动_20261025'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)

def main():
    checks=[]
    def check(name,passed,details=None):
        checks.append(dict(check=name,passed=bool(passed),details=details));assert passed,name
    baseline=read(OUT/'量价基线/验证结果.json')
    independent=read(ROOT/'work/baseline_oct25/audit_independent_review.json')
    qc=read(ROOT/'work/chip_summary_quality_oct25/针对性验证.json')
    estimate=read(OUT/'自建筹码样本/验证结果.json')
    reviewer=read(ROOT/'work/chip_summary_quality_oct25/自建样本独立抽核.json')
    check('baseline_25_technical_checks',baseline['passed']==baseline['total']==25)
    check('baseline_14_independent_checks',independent['passed']==independent['total']==14 and not independent['blocking_findings'])
    check('chip_summary_checks_all_pass',all(qc['checks'].values()))
    check('estimated_chip_checks_all_pass',estimate['all_technical_checks_passed'] and all(r['passed'] for r in estimate['checks']))
    # Independent reviewer schema is preserved wholesale; fail rather than guessing a success field.
    review_pass=reviewer.get('all_checks_passed',reviewer.get('all_passed',reviewer.get('passed')))
    if isinstance(review_pass,int) and not isinstance(review_pass,bool):
        review_pass=review_pass==reviewer.get('total',reviewer.get('checks_total'))
    check('estimated_chip_independent_review_pass',review_pass is True)
    with ro(OUT/'量价基线/日线特征与信号.sqlite') as f,ro(OUT/'量价基线/开发期结果隔离.sqlite') as l:
        check('features_and_outcomes_separate_stores','development_price_outcomes' not in {r[0] for r in f.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        check('469_development_labels_484_accounting',l.execute('SELECT COUNT(*) FROM development_price_outcomes').fetchone()[0]==469 and l.execute('SELECT COUNT(*) FROM excluded_anchors').fetchone()[0]==15)
        check('no_2025_2026_price_outcomes',l.execute("SELECT COUNT(*) FROM development_price_outcomes WHERE signal_date>='2025-01-01' OR outcome_observation_date>='2025-01-01'").fetchone()[0]==0)
        check('feature_formal_gates_closed',f.execute('SELECT COUNT(*) FROM features WHERE model_input_approved!=0 OR runtime_usable!=0').fetchone()[0]==0)
    with ro(OUT/'自建筹码样本/自建筹码小样本.sqlite') as e:
        check('estimated_counts_84_runs_111873_grid',e.execute('SELECT COUNT(*) FROM estimate_runs').fetchone()[0]==84 and e.execute('SELECT COUNT(*) FROM estimated_price_bins').fetchone()[0]==111873)
        check('all_estimates_explicitly_not_native_or_approved',e.execute('SELECT COUNT(*) FROM estimate_runs WHERE model_input_approved!=0 OR native_supplier_bins_acquired!=0').fetchone()[0]==0)
        sums=[r[0] for r in e.execute('SELECT SUM(estimated_mass_fraction) FROM estimated_price_bins GROUP BY estimate_id')]
        check('all_84_estimate_mass_sums_one',all(abs(x-1)<1e-12 for x in sums))
    missing=[];bad=[]
    with ro(OUT/'本轮原件证据索引.sqlite') as a:
        rows=list(a.execute('SELECT * FROM file_assets'))
        for r in rows:
            p=ROOT/r['project_relative_path']
            if r['exists_locally']:
                if not p.is_file() or sha(p)!=r['sha256'] or p.stat().st_size!=r['bytes']:bad.append(r['project_relative_path'])
            else:
                missing.append(r['project_relative_path'])
                if p.exists() or r['sha256'] is not None:bad.append(r['project_relative_path'])
        check('merged_index_5444_with_three_rejected_missing',len(rows)==5444 and len(missing)==3 and not bad,dict(missing=missing,bad=bad))
    source_hashes=read(OUT/'量价基线/运行合同.json')['source_hashes']
    check('all_source_databases_and_old_protocol_match_before',all(sha(ROOT/p)==h for p,h in source_hashes.items()),source_hashes)
    protocol=read(ROOT/'outputs/首版预测协议草案_20261016.json')
    check('old_protocol_unfrozen_and_not_runtime_usable',protocol['status']=='draft_not_frozen' and protocol['runtime_usable'] is False and all(v is None for v in protocol['pending_freeze'].values()))
    missing_links=[]
    for f in OUT.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',f.read_text()):
            if target.startswith('/') and not Path(target).is_file():missing_links.append([str(f.relative_to(OUT)),target])
            elif not target.startswith(('https://','http://','/','#')) and not (f.parent/target).is_file():missing_links.append([str(f.relative_to(OUT)),target])
    check('local_report_links_resolve',not missing_links,missing_links)
    for ext in ['.json','.md']:
        shutil.copy2(ROOT/('work/chip_summary_quality_oct25/自建样本独立抽核'+ext),OUT/('自建筹码样本/独立来源复核'+ext))
    with (OUT/'核验汇总.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['check','passed']);w.writeheader();w.writerows({k:r[k] for k in ['check','passed']} for r in checks)
    result={'client_date':'2026-10-25','all_checks_passed':all(r['passed'] for r in checks),'passed':len(checks),'total':len(checks),'checks':checks,
      'track_checks':{'baseline_technical':25,'baseline_independent':14,'chip_summary':len(qc['checks']),'estimator_technical':len(estimate['checks']),'estimator_independent_review':reviewer},
      'source_sha256':source_hashes,'no_new_native_chip_bins':True,'forecast_model_trained':False}
    (OUT/'本轮交付核验.json').write_text(enc(result))
    report=OUT/'三线研究启动报告.md';text=report.read_text()
    marker='\n## 本轮最终核验\n'
    if marker in text:text=text.split(marker)[0]
    text+=marker+f'''\n量价实现25项、独立来源复核14项通过；筹码摘要核查{len(qc['checks'])}项、自建估计实现{len(estimate['checks'])}项通过，另附自建样本独立积分/边界复核。本轮跨目录交付核验{len(checks)}/{len(checks)}项通过。不同检查覆盖有重叠，不能将合计检查次数当成市场有效性证据。\n\n- [量价独立复核]({OUT/'量价基线/独立来源复核.md'})\n- [自建样本独立复核]({OUT/'自建筹码样本/独立来源复核.md'})\n- [本轮交付核验]({OUT/'本轮交付核验.json'})\n\n完整本地快照保存位置：`/Users/puchun/Documents/Codex/项目归档/ni/20261025_三线研究启动完整保存/`。归档是否成功、完整文件数及恢复检查以该目录的`归档校验结果.json`为准。\n'''
    report.write_text(text)
    print(enc({'checks_passed':len(checks),'all_checks_passed':True,'source_stores_unchanged':True}))

if __name__=='__main__':main()
