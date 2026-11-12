from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from html.parser import HTMLParser
import re,json,hashlib
ROOT=Path('/Users/puchun/Documents/Codex/2026-10-07/ni')
SRC=ROOT/'work/chip_history_root_oct16'
OUT=ROOT/'work/forecast_inputs_oct16'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source_paths=sorted(p for p in SRC.iterdir() if p.is_file())
initial={str(p.relative_to(ROOT)):sha(p) for p in source_paths}
class Values(HTMLParser):
 def __init__(self):super().__init__();self.capture=False;self.current=[];self.values=[]
 def handle_starttag(self,tag,attrs):
  if tag=='td' and 'qcyq_t_v' in dict(attrs).get('class','').split():self.capture=True;self.current=[]
 def handle_data(self,data):
  if self.capture:self.current.append(data)
 def handle_endtag(self,tag):
  if tag=='td' and self.capture:self.values.append(''.join(self.current).strip());self.capture=False
fields=['date','profit_ratio','avg_cost','cost90','concentration90','cost70','concentration70']
def html_values(p):
 a=Values();a.feed(p.read_text());assert len(a.values)==7,(str(p),a.values);return dict(zip(fields,a.values))
def ax_values(p):
 lines=p.read_text().splitlines()
 ts=[{'line':i+1,'value':m.group(1)} for i,s in enumerate(lines) if (m:=re.search(r'\btext (.*)$',s))]
 start=next(i for i,x in enumerate(ts) if x['value']=='前复权')
 labels=['时间','开盘','收盘','最高','最低','涨跌幅','涨跌额','成交量','成交额','振幅','换手率']
 market={};line_refs={}
 for j in range(start+1,len(ts)):
  if ts[j]['value'] in labels:
   market[ts[j]['value']]=ts[j+1]['value'];line_refs[ts[j]['value']]=[ts[j]['line'],ts[j+1]['line']]
  if ts[j]['value']=='日期:':break
 chip_start=next(j for j in range(start+1,len(ts)) if ts[j]['value']=='日期:')
 chip={};chip_line_refs={};conc=0
 mapping={'日期:':'date','获利比例:':'profit_ratio','平均成本:':'avg_cost','90%成本:':'cost90','70%成本:':'cost70'}
 for j in range(chip_start,len(ts)):
  label=ts[j]['value']
  if label in mapping:
   k=mapping[label];chip[k]=ts[j+1]['value'];chip_line_refs[k]=[ts[j]['line'],ts[j+1]['line']]
  elif label=='集中度:':
   conc+=1;k='concentration90' if conc==1 else 'concentration70';chip[k]=ts[j+1]['value'];chip_line_refs[k]=[ts[j]['line'],ts[j+1]['line']]
   if conc==2:break
 return {'adjustment_control_display':'前复权','adjustment_line':ts[start]['line'],'market_tooltip':market,'market_line_refs':line_refs,'chip_summary':chip,'chip_line_refs':chip_line_refs}
artifacts=[]
for stem in ['B_20230620','A2_20230620','reload_20230620','20230103']:
 h=html_values(SRC/(stem+'_table.html'));a=ax_values(SRC/(stem+'_ax.txt'))
 assert h==a['chip_summary'],stem
 assert a['market_tooltip']['时间']==h['date'],stem
 artifacts.append({'stem':stem,'summary':h,'ax':a,'html_ax_date_and_summary_match':True,'screenshot_visual_review':{'performed':True,'confirms':['前复权控件显示','筹码面板日期','筹码摘要值'],'limitation':'左侧行情提示框部分裁剪，完整OHLC依据对应AX文本，不将截图当作全部行情数字的独立读数。'},'sources':{k:str((SRC/(stem+suffix)).relative_to(ROOT)) for k,suffix in [('html','_table.html'),('ax','_ax.txt'),('screenshot','.jpg')]}})
base=artifacts[0];jun=[x for x in artifacts if x['summary']['date']=='2023-06-20']
comparisons=[]
for x in jun[1:]:
 comparisons.append({'left':base['stem'],'right':x['stem'],'same_summary_date':base['summary']['date']==x['summary']['date'],'same_adjustment_control_display':base['ax']['adjustment_control_display']==x['ax']['adjustment_control_display'],'same_full_market_tooltip':base['ax']['market_tooltip']==x['ax']['market_tooltip'],'summary_differences':{k:{'left':base['summary'][k],'right':x['summary'][k]} for k in fields if base['summary'][k]!=x['summary'][k]}})
root=json.loads((SRC/'root_observations.json').read_text())
ledger=[]
for i,row in enumerate(root['observations']):
 val=dict(zip(root['fields'],row['values']));ledger.append({'row_number_1_based':i+1,'values':val,'note':row.get('note'),'treat_as_historical_observation':val['date']<'2026-10-16','exclusion_reason':'实际表内日期为默认最新2026-10-16，不能按note的目标日期计历史' if val['date']>='2026-10-16' else None})
history=[r for r in ledger if r['treat_as_historical_observation']]
summary_tuple=lambda v:tuple(v[k] for k in fields)
all_june=[r for r in history if r['values']['date']=='2023-06-20']
diag=html_values(SRC/'unsynchronized_after_idle_table.html')
checks={
'four_artifact_sets_read':len(artifacts)==4,
'html_ax_dates_summaries_consistent':all(x['html_ax_date_and_summary_match'] for x in artifacts),
'four_local_screenshots_visually_reviewed':all(x['screenshot_visual_review']['performed'] for x in artifacts),
'june20_three_complete_artifact_sets':len(jun)==3,
'june20_control_same':len({x['ax']['adjustment_control_display'] for x in jun})==1,
'june20_market_tooltip_same':len({json.dumps(x['ax']['market_tooltip'],sort_keys=True) for x in jun})==1,
'B_A2_summary_same':artifacts[0]['summary']==artifacts[1]['summary'],
'reload_five_summary_fields_differ':len(comparisons[1]['summary_differences'])==5,
'january03_market_and_chip_date_synchronized':artifacts[3]['ax']['market_tooltip']['时间']==artifacts[3]['summary']['date']=='2023-01-03',
'unsynchronized_diagnostic_excluded':diag['date']=='2026-10-16',
}
result={
'audit_date_local':'2026-10-16','created_at_utc':datetime.now(timezone.utc).isoformat(),'audit_scope':'只读现有HTML/AX/截图/root_observations；无UI、网络、主库或正式文件操作。',
'fact_conclusion':'2023-06-20在保存的相同日期、相同前复权控件显示、相同行情提示数据下，存在两个不同的筹码摘要。B与A2一致，reload不同。只能认定摘要复现尚未通过，不能裁定哪版正确或确定原因。',
'complete_artifact_observations':artifacts,'comparisons':comparisons,
'counts':{
'complete_html_ax_screenshot_sets':4,'complete_sets_unique_historical_dates':2,'complete_sets_dates':['2023-01-03','2023-06-20'],
'complete_sets_observations_for_june20':3,'complete_sets_distinct_summaries_for_june20':2,
'complete_sets_identical_summary_repeat_observations_beyond_first':1,
'complete_sets_repeat_same_date_observations_beyond_one_per_date':2,
'root_ledger_total_rows':len(ledger),'root_ledger_excluded_default_latest_rows':len(ledger)-len(history),
'root_ledger_historical_rows_after_exclusion':len(history),'root_ledger_unique_historical_dates':len({r['values']['date'] for r in history}),
'root_ledger_unique_historical_date_values':sorted({r['values']['date'] for r in history}),
'root_ledger_june20_observations':len(all_june),'root_ledger_june20_distinct_summaries':len({summary_tuple(r['values']) for r in all_june}),
'root_ledger_historical_exact_repeat_rows_beyond_first':len(history)-len({summary_tuple(r['values']) for r in history}),
'complete_price_bin_distribution_dates_certified':0,
'count_interpretation':'全证据文件支持2个唯一历史日期。root账本还记有6月1日和6月21日，缺独立成套截图/AX/HTML，单独列账本层，不把4日说成4日均完成成套核验。重复观测或摘要版本不增加历史日期覆盖，也不是独立统计样本。'},
'ledger_review':ledger,'excluded_diagnostic':{'path':str((SRC/'unsynchronized_after_idle_table.html').relative_to(ROOT)),'actual_values':diag,'historical_sample_eligible':False,'reason':'异步/空闲后未同步选择的默认最新读数；只作同步失败诊断。'},
'supported_facts':[
'网页保存证据确实可回看到2023-01-03的筹码摘要，行情日期与筹码日期一致。',
'2023-06-20的B与A2摘要相同；reload在5项摘要不同，平均成本同为9.03。',
'三份2023-06-20 AX的开7.63/收7.68/高7.71/低7.61，以及量额换手等提示完全相同；前复权控件显示均相同。',
'两个相同摘要出现在不同可见历史窗口中；另一次reload摘要不同，说明当前证据不足以把所有回看读数当作唯一稳定历史版本。'],
'cannot_assert':[
'不能仅凭reload差异断定某版本正确、供应商数据错误、页面算法错误或历史重绘。',
'不能断定加载历史长度、视窗跨度、缓存、初始化、异步状态、供应商修订或复权机制是确定原因；尚无控制变量和官方算法/版本证据。',
'相同前复权控件只认证可见主图选择，不证明筹码算法实际使用同一复权基准、初始化数据或价格档位。',
'这次不是独立复权/公司行动正确性认证；2023-06-20恰有权益事件，不能据此推断因果。',
'摘要与分布形状截图都不是完整价格档位、权重和算法版本数据；不能声称已建成2023起完整筹码库或有完整历史模型准入。',
'root_observations中的操作note不是日期证据；必须采用实际面板日期，不把最新或相邻日按目标日期重标。',
'截图/AX/HTML是当前回看观察，不证明2023当时已公开或当时算法版本相同。'],
'recommended_next_acceptance':['保持两版本及原件，禁止静默择一覆盖。','后续在明示相同日期、可见复权状态、加载历史范围等记录下做受控复验；每次读数同时校对行情日期和筹码日期。','若不能确定稳定口径或取得算法/版本说明，继续作为网页观察证据，暂不升格为合格历史预测输入。'],
'checks':checks,
'source_manifest':[{'path':str(p.relative_to(ROOT)),'sha256':initial[str(p.relative_to(ROOT))],'bytes':p.stat().st_size} for p in source_paths]
}
final={str(p.relative_to(ROOT)):sha(p) for p in source_paths}
result['source_files_unchanged']=initial==final
assert result['source_files_unchanged'] and all(checks.values())
(OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'audit':'work/forecast_inputs_oct16/audit.json','checks':len(checks),'passed':all(checks.values()),'source_files_unchanged':initial==final,'counts':result['counts'],'reload_different_fields':list(comparisons[1]['summary_differences'])},ensure_ascii=False))
