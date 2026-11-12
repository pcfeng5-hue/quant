"""Build an offline raw-data browser, without trading signals or charts."""
import json
import sqlite3
from pathlib import Path
from scope_config import read_scope

ROOT = Path(__file__).resolve().parent


def main():
    c = sqlite3.connect(ROOT/'高德红外_2023起.sqlite')
    c.row_factory = sqlite3.Row
    scope=read_scope(c)
    stock_days=c.execute("SELECT COUNT(*) FROM current_daily_bars WHERE source='em_daily_0'").fetchone()[0]
    entries = []
    labels = {'em_daily_0':'日线·不复权','em_daily_1':'日线·前复权','em_daily_2':'日线·后复权',
              'financial_main':'主要财务数据','balance_sheet':'资产负债表','income_statement':'利润表',
              'cashflow_statement':'现金流量表','holder_count':'股东户数','dividends':'分红',
              'top10_float':'前十大流通股东','block_trade':'大宗交易','billboard':'龙虎榜',
              'institution_seats':'机构席位披露','fund_flow_proxy':'资金流代理·原始响应',
              'capital_structure':'股本变更记录','index_1.000001':'上证指数·东方财富旧快照',
              'index_0.399001':'深证成指·东方财富旧快照','tencent_index_sh000001':'上证指数·腾讯',
              'tencent_index_sz399001':'深证成指·腾讯'}
    for r in c.execute("SELECT * FROM current_daily_bars WHERE source NOT LIKE 'tencent_daily_%'"):
        d = dict(r); group = labels.get(r['source'],r['source'])
        entries.append(dict(group=group,date=r['trade_date'],title=r['symbol'],source=r['source'],data=d))
    audits={(r['snapshot_id'],r['row_hash']):dict(r) for r in c.execute("SELECT * FROM record_temporal_audit WHERE audit_version='supplement-audit-v1'")}
    for r in c.execute('SELECT * FROM current_source_records'):
        d = json.loads(r['payload_json']); dataset = r['dataset']
        group = '巨潮投资者活动核对源' if dataset.startswith('cninfo_ir') else ('巨潮公告核对源' if dataset.startswith('cninfo_announcements') else ('公司公告目录' if dataset.startswith('announcements') else ('融资融券' if dataset.startswith('margin') else labels.get(dataset,dataset))))
        title = d.get('title',d.get('announcementTitle','')) if isinstance(d,dict) else ''
        audit=audits.get((r['snapshot_id'],r['row_hash']))
        display=dict(原始字段=d,参考日期字段=r['date_field'],历史可得性=r['availability_status'],核对=audit)
        entries.append(dict(group=group,date=r['reference_date'] or '',title=title,source=dataset,data=display,
                            date_field=r['date_field'],availability=r['availability_status']))
    for r in c.execute('SELECT * FROM original_report_observations'):
        entries.append(dict(group='财务原报告·已核数值',date=r['provider_notice_date'],title=r['report_date']+' · '+r['metric'],
                            source=r['art_code'],data=json.loads(r['evidence_json'])))
    for r in c.execute('SELECT * FROM latest_available_fund_flow'):
        entries.append(dict(group='资金流代理·已映射字段',date=r['trade_date'],title='非真实机构身份；价格为当前前复权匹配口径',
                            source='fund_flow_proxy',data=json.loads(r['payload_json'])))
    for r in c.execute('SELECT * FROM trading_calendar'):
        entries.append(dict(group='官方计划交易日历',date=r['trade_date'],title='计划开市' if r['is_scheduled_open'] else '计划休市',
                            source='SSE,SZSE',data=json.loads(r['payload_json'])))
    for r in c.execute('SELECT * FROM public_document_samples'):
        data=dict(r);data['metadata']=json.loads(data.pop('metadata_json'))
        entries.append(dict(group='官方政策原文样本·非全集',date=r['reference_date'] or '',title=r['title'],source=r['url'],data=data))
    for r in c.execute('SELECT * FROM candidate_data_sources'):
        entries.append(dict(group='补缺候选来源·未取得数据',date=r['reviewed_on'],title=r['source_id'],source=r['url'],data=json.loads(r['payload_json'])))
    for r in c.execute('SELECT * FROM corporate_action_observations'):
        entries.append(dict(group='公司行动·已核实施条款',date=r['ex_date'],title='每10股现金 '+r['cash_cny_per_10_shares']+'元；除权息日',
                            source=r['art_code'],data=json.loads(r['evidence_json'])))
    for r in c.execute('SELECT * FROM primary_document_checks'):
        data=json.loads(r['payload_json'])
        entries.append(dict(group='巨潮原件交叉核对·非新增样本',date=r['reference_date'] or '',title=data.get('title',r['art_code']),
                            source=r['url'],data=data))
    candidate_reviews={r['candidate_id']:json.loads(r['payload_json']) for r in c.execute("SELECT * FROM announcement_candidate_reviews WHERE audit_version='round4-disclosure-audit-v1'")}
    for r in c.execute('SELECT * FROM announcement_event_candidates'):
        data=json.loads(r['payload_json'])
        data.update(候选类别=r['category'],否定措辞提示=bool(r['has_negation_cue']),历史输入准入=False,逐条分类核对=candidate_reviews.get(r['candidate_id']))
        entries.append(dict(group='公告事件候选·未确认',date=r['reference_date'] or '',title=data.get('title',r['art_code']),
                            source=r['art_code'],data=data))
    for r in c.execute('SELECT * FROM manual_document_observations'):
        data=json.loads(r['payload_json'])
        entries.append(dict(group='扫描页选定字段·视觉核对',date=data.get('provider_notice_date',''),title=r['metric'],
                            source=r['art_code'],data=data))
    extra_labels={'accounting_adjustment':'会计修订·选定原件数值','capital_period':'股本·报告期间末观测',
                  'employee_nontrade_transfer':'员工持股·非交易过户','limited_negative_disclosure':'公告特定否定表述·非全状态',
                  'capital_reconciliation_issue':'股本衔接问题·未解决','existing_action_phase':'既有公司行动·阶段证据'}
    for r in c.execute("SELECT * FROM supplemental_disclosure_observations WHERE audit_version='round4-disclosure-audit-v1'"):
        data=json.loads(r['payload_json'])
        title=data.get('metric_original_label') or data.get('event_type') or data.get('scope') or r['observation_id']
        display=dict(原件核对=data,报告期或事件参考日期=r['report_period'],历史输入准入=False)
        entries.append(dict(group=extra_labels[r['kind']],date=r['reference_date'] or '',title=title,
                            source=r['observation_id'],data=display))
    for r in c.execute('SELECT * FROM announcement_ocr_texts'):
        data=json.loads(r['payload_json'])
        display=dict(原件哈希=r['source_sha256'],PDF页码=r['page_number'],文字=r['text'],
                     引擎=data['engine'],状态=r['status'],低置信度行数=r['low_confidence_lines'],
                     整页人工核对=False,数字已认证=False,历史输入准入=False)
        entries.append(dict(group='公告扫描文字·OCR未核验',date=data['notice_date'][:10],
                            title=data['title']+' · PDF第'+str(r['page_number'])+'页',source=data['url'],data=display))
    for r in c.execute('SELECT * FROM shareholder_history_observations'):
        data=json.loads(r['payload_json'])
        group='前十大总股东·定期观察' if r['observation_scope']=='periodic_top10' else '总股东·非定期部分名单'
        entries.append(dict(group=group,date=r['reference_date'],title=r['holder_name'],source=r['snapshot_id'],data=data))
    for r in c.execute('SELECT * FROM shareholder_disclosure_links'):
        data=json.loads(r['payload_json'])
        entries.append(dict(group='股东原文对应·首次时间待核',date=data['reference_date'],title=data['holder'],source=r['art_code'],data=data))
    for r in c.execute('SELECT * FROM data_source_discrepancies'):
        entries.append(dict(group='数据来源差异·待核',date=r['reference_date'],title=r['dataset'],source=r['run_id'],data=json.loads(r['payload_json'])))
    gaps = [dict(r) for r in c.execute('SELECT * FROM coverage_gaps')]
    c.close()
    gap_labels = {
      'chip_history':f'筹码与股价关系已列核心研究项。离线导入验收已准备，目标{stock_days}日期；实际历史筹码仍为0，权限与复权口径待核。',
      'tick_level2':'逐笔成交与Level-2历史：授权、价格及覆盖尚未确认。',
      'news_policy_archive':'新闻政策档案：已归档部分官方原文样本，完整去重历史及首次公开时间仍缺。',
      'industry_theme_history':'历史行业与题材分类：尚未取得当时有效的完整分类。',
      'fund_holder_history':'已有前十大总股东170行（150定期、20非定期部分名单）及前十大流通股东，不能代表全部基金持仓或实时买卖；首次可得时间待核。',
      'corporate_actions_float_shares':'股本：8个原件期间末观测（含1个期前基准），补4个期间；3个员工非交易过户另列。3项衔接差异及连续每日流通股本仍待核。',
      'trading_calendar_status':f'官方计划交易日历已核对{stock_days}日；停牌接口仅核实精确日期语法，完整历史及风险警示仍待核。',
      'financial_point_in_time':'财务：原有135项数值和新增28行修订分别保存，4行调整前空白保留null；完整修订链与准确首次可得时间仍待核。',
      'announcement_ocr':'公告文字：4068页文字层，加185页本地OCR，共4253页可检索。OCR数字与表格未认证；124页含低置信度行，整页人工核验未完成。',
      'technical_indicators':'技术指标与信号：按本轮要求延后计算，目前只做原始数据归档。'}
    for gap in gaps:
        gap['explanation'] = gap_labels.get(gap['dataset'],gap['explanation'])
    payload = json.dumps(dict(entries=entries,gaps=gaps),ensure_ascii=False).replace('<',r'\u003c')
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>高德红外 · 数据库浏览</title><style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f7fa;color:#172434}main{max-width:1100px;margin:auto;padding:28px}h1{font-size:25px}p{line-height:1.7}.note{padding:14px;background:#fff1d9;border-radius:10px}.controls{display:flex;flex-wrap:wrap;gap:14px;margin:22px 0}label{display:flex;flex-direction:column;gap:6px}select,input,button{padding:9px;border:1px solid #bac4ce;border-radius:6px;background:white;font-size:15px}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:12px;border-bottom:1px solid #e1e5eb}th{background:#eef3f8}details{max-width:650px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:400px;overflow:auto}#pager{display:flex;align-items:center;gap:14px;margin:15px 0}.muted{color:#586879}.wrap{overflow:auto}summary{cursor:pointer}.cards{display:flex;flex-wrap:wrap;gap:8px} .cards span{background:white;padding:9px;border:1px solid #dce2e8;border-radius:6px}
</style><main><h1>高德红外（002414）· 原始数据浏览</h1>
<p>请求区间：2023-01-01 — 2026-10-13。每类数据实际覆盖不同；日期可能是交易日、披露日或报告期，请查看原字段。</p>
<p class="note">统计与核对阶段。原始数据、核对源和已核原件数值分别计数，不能相加当作独立样本。财务含后续修订；资金流附带价格匹配当前前复权口径；筹码历史尚缺。已核数值不等于已认证历史可用，页面不生成买卖信号。</p>
<div class="cards" id="counts"></div>
<div class="controls"><label>数据类别<select id="group"></select></label><label>开始日期<input id="start" type="date" value="2023-01-01"></label><label>结束日期<input id="end" type="date" value="2026-10-13"></label><label>标题或字段检索<input id="search" placeholder="输入名称或关键词"></label></div>
<div id="summary" aria-live="polite"></div><div id="pager"><button id="prev">上一页</button><span id="page"></span><button id="next">下一页</button></div>
<div class="wrap"><table><thead><tr><th>日期</th><th>对象 / 标题</th><th>原始字段</th></tr></thead><tbody id="rows"></tbody></table></div>
<h2>数据缺口</h2><div id="gaps"></div><p class="muted">本页面为离线快照，不自动更新。原始响应、来源URL、取得时间和校验值保存在同目录数据库及raw文件夹。</p></main>
<script id="dataset" type="application/json">__DATA__</script><script>
const model=JSON.parse(document.getElementById('dataset').textContent);
const el=id=>document.getElementById(id); let page=0, filtered=[]; const pageSize=30;
const groups=[...new Set(model.entries.map(r=>r.group))].sort();
for(const name of groups){const o=document.createElement('option');o.value=name;o.textContent=name;el('group').append(o);}
el('group').value='日线·不复权';
for(const name of groups){const s=document.createElement('span');s.textContent=name+'：'+model.entries.filter(r=>r.group===name).length;el('counts').append(s);}
function render(){const from=el('start').value,to=el('end').value,q=el('search').value.toLowerCase();filtered=model.entries.filter(r=>r.group===el('group').value&&(!r.date||(r.date>=from&&r.date<=to))&&(!q||JSON.stringify(r).toLowerCase().includes(q))).sort((a,b)=>b.date.localeCompare(a.date));const max=Math.max(0,Math.ceil(filtered.length/pageSize)-1);page=Math.min(page,max);el('summary').textContent='筛选结果 '+filtered.length+' 条；日期未核实的资料仍显示，请勿按该筛选认定历史归属。';el('page').textContent=(page+1)+' / '+(max+1);el('prev').disabled=page===0;el('next').disabled=page===max;el('rows').replaceChildren();for(const r of filtered.slice(page*pageSize,(page+1)*pageSize)){const tr=document.createElement('tr');for(const s of [r.date||'日期未核实',r.title||r.group]){const td=document.createElement('td');td.textContent=s;tr.append(td);}const td=document.createElement('td'),d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');s.textContent='查看原始字段 · '+r.source;p.textContent=JSON.stringify(r.data,null,2);d.append(s,p);td.append(d);tr.append(td);el('rows').append(tr);}}
for(const id of ['group','start','end','search'])el(id).addEventListener('input',()=>{page=0;render();});el('prev').onclick=()=>{page--;render();};el('next').onclick=()=>{page++;render();};for(const g of model.gaps){const p=document.createElement('p');p.textContent=g.dataset+' ['+g.status+'] '+g.explanation;el('gaps').append(p);}render();
</script></html>'''
    (ROOT/'数据库浏览.html').write_text(template.replace('2026-10-13',scope['end']).replace('__DATA__',payload),encoding='utf-8')
    print('browser entries',len(entries),'groups',len(set(x['group'] for x in entries)))


if __name__ == '__main__': main()
