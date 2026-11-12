"""Validate embedded data and JavaScript syntax; does not run or certify the UI."""
import json
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NODE=Path('/Users/puchun/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')


def main():
    html=(ROOT/'数据库浏览.html').read_text()
    raw=re.search(r'<script id="dataset" type="application/json">(.*?)</script>',html,re.S).group(1)
    data=json.loads(raw)
    entries=data['entries']
    c=sqlite3.connect((ROOT/'高德红外_2023起.sqlite').as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    expected=[dict(r) for r in c.execute("SELECT * FROM current_daily_bars WHERE source NOT LIKE 'tencent_daily_%'")]
    shown=[r for r in entries if r['source'] in {r['source'] for r in expected}]
    stock_keys=lambda r:(r['source'],r['symbol'],r['trade_date'])
    actual={stock_keys(r['data']):r for r in shown}
    checks={
        'embedded_json_parses':True,
        'no_closing_script_in_json':'</script' not in raw.lower(),
        'all_displayed_bars_match_sqlite_exactly':len(actual)==len(expected)==len(shown) and all(
            stock_keys(r) in actual and actual[stock_keys(r)]['data']==r and
            actual[stock_keys(r)]['date']==r['trade_date'] for r in expected),
        'oct13_and_oct15_dates_preserved':all(sum(r['source']=='em_daily_0' and r['date']==day for r in entries)==1
                                                for day in ('2026-10-13','2026-10-15')),
    }
    flow=[r for r in entries if r['group']=='资金流代理·已映射字段']
    expected_flow={r['trade_date']:json.loads(r['payload_json']) for r in c.execute('SELECT * FROM latest_available_fund_flow')}
    checks['retained_flow_dates_and_payloads_exact']=len(flow)==len(expected_flow) and {r['date']:r['data'] for r in flow}==expected_flow
    counts=Counter(r['group'] for r in entries)
    checks['shareholder_groups_and_discrepancy_counts_exact']=all(counts[label]==c.execute(query).fetchone()[0] for label,query in [
        ('前十大总股东·定期观察',"SELECT COUNT(*) FROM shareholder_history_observations WHERE observation_scope='periodic_top10'"),
        ('总股东·非定期部分名单',"SELECT COUNT(*) FROM shareholder_history_observations WHERE observation_scope='nonperiodic_partial_holders_only'"),
        ('数据来源差异·待核','SELECT COUNT(*) FROM data_source_discrepancies')])
    checks['coverage_gaps_exact']=len(data['gaps'])==c.execute('SELECT COUNT(*) FROM coverage_gaps').fetchone()[0]
    script=re.findall(r'<script>(.*?)</script>',html,re.S)
    result=subprocess.run([str(NODE),'--check'],input='\n'.join(script),text=True,capture_output=True,timeout=30)
    checks['javascript_syntax']=result.returncode==0
    report=dict(checked_at=datetime.now(timezone.utc).isoformat(),checks=checks,
                failed=[k for k,v in checks.items() if not v],entries=len(entries),groups=len(counts),
                group_counts=dict(sorted(counts.items())),javascript_errors=result.stderr,
                ui_runtime_verified=False,limitation='Static data/syntax checks only; local file preview was blocked by browser policy; no alternate preview attempted.')
    (ROOT/'浏览页静态核对结果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    c.close()
    print(json.dumps({k:v for k,v in report.items() if k!='group_counts'},ensure_ascii=False,indent=2))
    if report['failed']:raise SystemExit(1)


if __name__=='__main__':main()
