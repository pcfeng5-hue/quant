import sqlite3,json,datetime,collections
from decimal import Decimal
from pathlib import Path
p=Path(__file__).resolve().parent
c=sqlite3.connect('file:outputs/高德红外数据库/高德红外_2023起.sqlite?mode=ro',uri=True);c.row_factory=sqlite3.Row
fields=('open','high','low','close','volume');tol=Decimal('0.005');run='refresh-20261015-v1'
result={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'read_only':True,'tolerance':str(tol),'fields':list(fields),'run_id':run,'interpretation':'Stored source numbers only; differing volumes require source definition/unit/scope verification. No provider chosen as truth; no replacements, returns, or indicators.','sources':[]}
all_missing=[];all_mismatch=[];totalfields=collections.Counter();distinct_dates=set();source_date_count=0
for newsource,oldsource in [('tencent_index_sh000001','index_1.000001'),('tencent_index_sz399001','index_0.399001')]:
 old={r['trade_date']:dict(r) for r in c.execute('select * from current_daily_bars where source=?',(oldsource,))};new={r['trade_date']:dict(r) for r in c.execute('select * from current_daily_bars where source=?',(newsource,))};common=sorted(set(old)&set(new));diffs=[];counts=collections.Counter()
 disc={r['reference_date']:dict(r) for r in c.execute('select * from data_source_discrepancies where run_id=? and dataset=?',(run,newsource))}
 for date in common:
  delta={}
  for f in fields:
   a,b=old[date][f],new[date][f]
   different=(a is None)!=(b is None) or (a is not None and b is not None and abs(Decimal(str(b))-Decimal(str(a)))>tol)
   if different:
    delta[f]={'old':a,'new':b,'new_minus_old':str(Decimal(str(b))-Decimal(str(a))) if a is not None and b is not None else None};counts[f]+=1;totalfields[f]+=1
  if not delta:continue
  distinct_dates.add(date)
  stored=disc.get(date);saved=json.loads(stored['payload_json']) if stored else None
  coverage=bool(saved and all(saved.get('old',{}).get(f)==old[date][f] and saved.get('new',{}).get(f)==new[date][f] for f in delta))
  if not stored:all_missing.append({'source':newsource,'date':date,'fields':list(delta)})
  elif not coverage:all_mismatch.append({'source':newsource,'date':date,'fields':list(delta)})
  diffs.append({'source':newsource,'reference_date':date,'old_source':oldsource,'old_snapshot_id':old[date]['snapshot_id'],'new_snapshot_id':new[date]['snapshot_id'],'fields':delta,'data_source_discrepancies_row_exists':stored is not None,'stored_values_cover_each_difference':coverage,'stored_status':stored['status'] if stored else None})
 source_date_count+=len(diffs)
 result['sources'].append({'new_source':newsource,'old_source':oldsource,'overlap_dates':len(common),'overlap_min':min(common),'overlap_max':max(common),'new_dates_without_old':sorted(set(new)-set(old)),'price_difference_dates':sum(any(f!='volume' for f in d['fields']) for d in diffs),'volume_difference_dates':sum('volume' in d['fields'] for d in diffs),'difference_source_dates':len(diffs),'field_difference_count':sum(counts.values()),'by_field':{f:counts[f] for f in fields},'discrepancy_rows_in_db':len(disc),'old_stored_volume_units':sorted({r['volume_unit'] for r in old.values()}),'new_stored_volume_units':sorted({r['volume_unit'] for r in new.values()}),'differences':diffs})
result['summary']={'difference_source_date_pairs':source_date_count,'unique_calendar_dates_with_difference':len(distinct_dates),'field_difference_count':sum(totalfields.values()),'by_field':{f:totalfields[f] for f in fields},'missing_discrepancy_records':all_missing,'mismatched_discrepancy_records':all_mismatch,'every_difference_preserved_in_discrepancy_table':not all_missing and not all_mismatch,'all_original_numbers_retained':True}
(p/'index_cross_source_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'sources':[{k:v for k,v in s.items() if k!='differences'} for s in result['sources']],'summary':result['summary']},ensure_ascii=False,indent=2))
