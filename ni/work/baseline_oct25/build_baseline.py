"""A source-frozen descriptive engineering experiment; no forecasting or execution release."""
from pathlib import Path
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
import csv, hashlib, json, math, shutil, sqlite3, statistics, tempfile

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/三线研究启动_20261025/量价基线'
DB=ROOT/'outputs/统一数据底座_20261022/统一数据底座.sqlite'
MAIN=ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'
PROTOCOL=ROOT/'outputs/首版预测协议草案_20261016.json'
CONTRACT=WORK/'engineering_contract.json'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON');return c
def finite(x):return x is not None and math.isfinite(x)
def mean(xs):return statistics.fmean(xs)
def quantile(xs,q):
    a=sorted(xs)
    if not a:return None
    pos=(len(a)-1)*q;lo=math.floor(pos);hi=math.ceil(pos)
    return a[lo]+(a[hi]-a[lo])*(pos-lo)
def write_csv(path,rows,fields=None):
    if fields is None:fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader();w.writerows(rows)

def kdj_step(rsv,k,d):
    k=(2*k+rsv)/3;d=(2*d+k)/3
    return k,d,3*k-2*d

def compute_features(bars,ex_dates,cfg):
    rows=[];segment=[];ef=es=dea=None;k=d=50.0;seg_start=None
    for i,b in enumerate(bars):
        day=b['trade_date'];r={
          'trade_date':day,'source_observation_id':b.get('observation_id'),
          'source_sha256':b.get('source_sha256'),'source_retrieved_at':b.get('retrieved_at'),
          'raw_open':b['open'],'raw_high':b['high'],'raw_low':b['low'],'raw_close':b['close'],
          'volume_native':b['volume_native'],'amount_cny':b.get('amount_cny'),'turnover_pct_raw':b.get('turnover_pct'),
          'segment_start':None,'segment_bars':0,'known_ex_date':int(day in ex_dates),
          'ma5':None,'ma10':None,'ma15':None,'macd_dif':None,'macd_dea':None,'macd_hist2':None,
          'kdj_rsv':None,'kdj_k':None,'kdj_d':None,'kdj_j':None,
          'volume_ratio_prev5':None,'volume_ratio_prev20':None,'turnover_ratio_prev5':None,
          'close_change_prev':None,'indicator_context':'before_calculation_start',
          'daily_status_certified':0,'model_input_approved':0,'runtime_usable':0}
        if day<cfg['calculation_start']:
            rows.append(r);continue
        if not segment or day in ex_dates:
            segment=[];ef=es=dea=None;k=d=50.0;seg_start=day
        segment.append(b);age=len(segment);close=b['close']
        r.update(segment_start=seg_start,segment_bars=age,indicator_context='raw_price_segment; prospective_formula_not_PIT_certification')
        for n in cfg['ma_windows']:
            if age>=n:r['ma'+str(n)]=mean([z['close'] for z in segment[-n:]])
        ef=close if ef is None else ef+(close-ef)*2/13
        es=close if es is None else es+(close-es)*2/27
        dif=ef-es;dea=dif if dea is None else dea+(dif-dea)*2/10
        if age>=cfg['macd']['minimum_segment_bars']:
            r.update(macd_dif=dif,macd_dea=dea,macd_hist2=2*(dif-dea))
        if age>=9:
            low=min(z['low'] for z in segment[-9:]);high=max(z['high'] for z in segment[-9:])
            rsv=50.0 if high==low else (close-low)/(high-low)*100
            k,d,j=kdj_step(rsv,k,d)
            if age>=cfg['kdj']['minimum_segment_bars']:r.update(kdj_rsv=rsv,kdj_k=k,kdj_d=d,kdj_j=j)
        for n in cfg['volume']['ratios']:
            if age>n:
                prevmean=mean([z['volume_native'] for z in segment[-n-1:-1]])
                if prevmean>0:r['volume_ratio_prev'+str(n)]=b['volume_native']/prevmean
        if age>5:
            turns=[z.get('turnover_pct') for z in segment[-6:-1]]
            if finite(b.get('turnover_pct')) and all(finite(x) for x in turns) and mean(turns)>0:
                r['turnover_ratio_prev5']=b['turnover_pct']/mean(turns)
        if age>1:r['close_change_prev']=close/segment[-2]['close']-1
        rows.append(r)
    return rows

def build_signals(features,cfg):
    result=[]
    for i,r in enumerate(features):
        p=features[i-1] if i else {}
        same=p.get('segment_start')==r['segment_start'] and r['segment_start'] is not None
        def cross(a,b,above):
            vals=[r[a],r[b],p.get(a),p.get(b)]
            if not same or not all(finite(v) for v in vals):return None
            return int(r[a]>r[b] and p[a]<=p[b]) if above else int(r[a]<r[b] and p[a]>=p[b])
        ma_up=cross('ma5','ma10',True);ma_down=cross('ma5','ma10',False)
        macd_up=cross('macd_dif','macd_dea',True);macd_down=cross('macd_dif','macd_dea',False)
        kd_up=cross('kdj_k','kdj_d',True);kd_down=cross('kdj_k','kdj_d',False)
        trend_valid=same and all(finite(v) for v in [r['ma5'],r['ma10'],r['ma15'],p.get('ma15')])
        trend_up=int(r['ma5']>r['ma10']>r['ma15'] and r['ma15']>p['ma15']) if trend_valid else None
        trend_down=int(r['ma5']<r['ma10']<r['ma15'] and r['ma15']<p['ma15']) if trend_valid else None
        volvalid=all(finite(v) for v in [r['volume_ratio_prev20'],r['close_change_prev']])
        volup=int(r['volume_ratio_prev20']>cfg['volume']['spike_threshold'] and r['close_change_prev']>0) if volvalid else None
        voldown=int(r['volume_ratio_prev20']>cfg['volume']['spike_threshold'] and r['close_change_prev']<0) if volvalid else None
        combo_valid=ma_up is not None and all(finite(r[x]) for x in ['macd_dif','macd_dea'])
        combo_up=int(ma_up==1 and r['macd_dif']>r['macd_dea']) if combo_valid else None
        combo_down=int(ma_down==1 and r['macd_dif']<r['macd_dea']) if combo_valid else None
        result.append(dict(trade_date=r['trade_date'],**dict(zip(cfg['registered_signals'],[ma_up,ma_down,macd_up,macd_down,kd_up,kd_down,trend_up,trend_down,volup,voldown,combo_up,combo_down]))))
    return result

def build_development_outcomes(bars,ex_dates,cfg):
    outcomes=[];exclusions=[];h=cfg['horizon_observed_sessions']
    for i,b in enumerate(bars):
        day=b['trade_date']
        if not cfg['development_start']<=day<=cfg['development_end']:continue
        if i+h>=len(bars):
            exclusions.append(dict(trade_date=day,reason='OUTCOME_NOT_OBSERVED'));continue
        entry=bars[i+1];end=bars[i+h]
        if end['trade_date']>cfg['development_end']:
            exclusions.append(dict(trade_date=day,reason='OUTCOME_END_CROSSES_DEVELOPMENT_BOUNDARY'));continue
        if any(entry['trade_date']<=x<=end['trade_date'] for x in ex_dates):
            exclusions.append(dict(trade_date=day,reason='KNOWN_EX_DATE_WITHIN_PRICE_WINDOW'));continue
        value=Decimal(str(end['close']))/Decimal(str(entry['open']))-1
        sign='price_change_gt_0' if value>0 else 'price_change_lt_0' if value<0 else 'price_change_eq_0'
        outcomes.append(dict(signal_date=day,entry_observation_date=entry['trade_date'],outcome_observation_date=end['trade_date'],
          entry_open_raw=entry['open'],outcome_close_raw=end['close'],horizon_observed_sessions=h,
          price_change_fraction=float(value),outcome_sign=sign,entry_source_observation_id=entry['observation_id'],outcome_source_observation_id=end['observation_id'],
          daily_status_certified=0,execution_modelled=0,model_input_approved=0,scope='development_retrospective_price_only'))
    return outcomes,exclusions

def descriptive_summary(rows):
    n=len(rows);counts=Counter(r['outcome_sign'] for r in rows);values=[r['price_change_fraction'] for r in rows]
    return {'n_overlapping_observations':n,'positive_count':counts['price_change_gt_0'],'zero_count':counts['price_change_eq_0'],'negative_count':counts['price_change_lt_0'],
      'positive_observed_frequency':counts['price_change_gt_0']/n if n else None,'zero_observed_frequency':counts['price_change_eq_0']/n if n else None,'negative_observed_frequency':counts['price_change_lt_0']/n if n else None,
      'price_change_median':quantile(values,.5),'price_change_q10':quantile(values,.1),'price_change_q90':quantile(values,.9)}

def run_statistics(features,signals,outcomes,bars,cfg):
    bydate={r['trade_date']:r for r in signals}
    devanchors=[r['trade_date'] for r in bars if cfg['development_start']<=r['trade_date']<=cfg['development_end']]
    # One offset, fixed before observing any outcomes. Never choose a best phase.
    fixed_grid=set(devanchors[::cfg['horizon_observed_sessions']])
    stats=[]
    for signal in ['ALL_PRICE_WINDOWS']+cfg['registered_signals']:
        eligible=outcomes if signal=='ALL_PRICE_WINDOWS' else [r for r in outcomes if bydate[r['signal_date']][signal] is not None]
        selected=eligible if signal=='ALL_PRICE_WINDOWS' else [r for r in eligible if bydate[r['signal_date']][signal]==1]
        baseline=descriptive_summary(eligible);selected_summary=descriptive_summary(selected)
        fixed_selected=[r for r in selected if r['signal_date'] in fixed_grid]
        fixed_baseline=[r for r in eligible if r['signal_date'] in fixed_grid]
        row={'signal':signal,**selected_summary,'eligible_baseline_n':len(eligible),'eligible_baseline_positive_frequency':baseline['positive_observed_frequency'],
          'positive_frequency_difference_to_matched_baseline':selected_summary['positive_observed_frequency']-baseline['positive_observed_frequency'] if selected and eligible else None,
          'fixed_every_fifth_anchor_n':len(fixed_selected),'fixed_grid_positive_frequency':descriptive_summary(fixed_selected)['positive_observed_frequency'],
          'fixed_grid_baseline_n':len(fixed_baseline),'fixed_grid_baseline_positive_frequency':descriptive_summary(fixed_baseline)['positive_observed_frequency'],
          'small_count_note':'fewer_than_30_selected_observations' if len(selected)<30 else 'overlap_and_single_period_dependence_remain',
          'is_predictive_probability':0,'is_trading_profit_probability':0,'model_input_approved':0}
        stats.append(row)
    return stats,fixed_grid

def sqlite_table(c,name,rows):
    if not rows:return
    cols=list(rows[0]);types=[]
    for k in cols:
        nonnull=next((r[k] for r in rows if r[k] is not None),None)
        types.append('INTEGER' if isinstance(nonnull,(int,bool)) else 'REAL' if isinstance(nonnull,float) else 'TEXT')
    quote=lambda x:'"'+x.replace('"','""')+'"'
    c.execute('CREATE TABLE '+quote(name)+'('+','.join(quote(k)+' '+typ for k,typ in zip(cols,types))+')')
    c.executemany('INSERT INTO '+quote(name)+' VALUES('+','.join('?' for _ in cols)+')',[tuple(r[k] for k in cols) for r in rows])

def validate(bars,features,signals,outcomes,exclusions,ex_dates,cfg):
    checks=[]
    def check(name,passed,details=None):
        checks.append(dict(check=name,passed=bool(passed),details=details));assert passed,name
    check('source_dates_sorted_unique',len({r['trade_date'] for r in bars})==len(bars) and [r['trade_date'] for r in bars]==sorted(r['trade_date'] for r in bars))
    check('all_source_ohlc_valid',all(0<r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] for r in bars))
    check('research_918_warmup_242',sum(r['trade_date']>='2023-01-01' for r in bars)==918 and sum(r['trade_date']<'2023-01-01' for r in bars)==242)
    prefixes=['2022-12-30','2023-06-19','2023-06-20','2024-05-24','2026-09-22','2026-10-21']
    for day in prefixes:
        n=next(i+1 for i,r in enumerate(bars) if r['trade_date']==day)
        fs=compute_features(bars[:n],ex_dates,cfg)
        check('prefix_invariance_'+day,fs==features[:n] and build_signals(fs,cfg)==signals[:n])
    # A separate pandas implementation checks MA and recursive EMA on every segment.
    import pandas as pd
    differences=[]
    starts=sorted({r['segment_start'] for r in features if r['segment_start']})
    for start in starts:
        segment=[r for r in features if r['segment_start']==start];s=pd.Series([r['raw_close'] for r in segment],dtype=float)
        dif=s.ewm(span=12,adjust=False).mean()-s.ewm(span=26,adjust=False).mean();dea=dif.ewm(span=9,adjust=False).mean()
        for j,r in enumerate(segment):
            for n in cfg['ma_windows']:
                expected=s.rolling(n,min_periods=n).mean().iloc[j]
                if r['ma'+str(n)] is not None and not math.isclose(r['ma'+str(n)],expected,rel_tol=1e-12,abs_tol=1e-12):differences.append((r['trade_date'],'ma'+str(n)))
            if r['macd_dif'] is not None:
                if not math.isclose(r['macd_dif'],dif.iloc[j],rel_tol=1e-10,abs_tol=1e-12) or not math.isclose(r['macd_dea'],dea.iloc[j],rel_tol=1e-10,abs_tol=1e-12):differences.append((r['trade_date'],'macd'))
    check('independent_pandas_ma_ema_equivalence',not differences,dict(differences=differences[:10]))
    check('kdj_manual_step',kdj_step(80,50,50)==(60.0,53.333333333333336,73.33333333333333))
    check('kdj_flat_seed',kdj_step(50,50,50)==(50.0,50.0,50.0))
    check('ex_dates_reset_all_states',all(r['segment_bars']==1 and all(r[k] is None for k in ['ma5','ma10','ma15','macd_dif','kdj_k','volume_ratio_prev20']) for r in features if r['trade_date'] in ex_dates))
    check('macd_warmup_130',all(r['macd_dif'] is None for r in features if r['segment_bars']<130))
    check('kdj_warmup_30',all(r['kdj_k'] is None for r in features if r['segment_bars']<30))
    check('all_labels_development_only',all(cfg['development_start']<=r['signal_date']<=r['outcome_observation_date']<=cfg['development_end'] for r in outcomes))
    check('no_labels_for_2025_2026',not any(r['signal_date']>='2025-01-01' or r['outcome_observation_date']>='2025-01-01' for r in outcomes))
    dates=[r['trade_date'] for r in bars]
    check('label_exact_next_to_fifth_observation',all(dates.index(r['entry_observation_date'])==dates.index(r['signal_date'])+1 and dates.index(r['outcome_observation_date'])==dates.index(r['signal_date'])+5 for r in outcomes))
    check('no_label_window_crosses_known_ex_date',all(not any(r['entry_observation_date']<=x<=r['outcome_observation_date'] for x in ex_dates) for r in outcomes))
    check('label_sign_partition',all(r['outcome_sign'] in cfg['outcome_signs'] for r in outcomes))
    check('development_anchor_accounting',len(outcomes)+len(exclusions)==484)
    check('all_formal_gates_zero',all(r['model_input_approved']==0 and r['runtime_usable']==0 for r in features))
    # Future mutation must not alter any feature or signal at or before the cutoff.
    cutoff='2024-12-31';mutated=[dict(r) for r in bars]
    for r in mutated:
        if r['trade_date']>cutoff:
            for k in ['open','high','low','close']:r[k]*=3.7
            r['volume_native']*=7
    alternative=compute_features(mutated,ex_dates,cfg)
    check('future_price_volume_mutation_does_not_change_development_features',all(a==b for a,b in zip(features,alternative) if a['trade_date']<=cutoff))
    check('future_mutation_does_not_change_development_labels',build_development_outcomes(mutated,ex_dates,cfg)==(outcomes,exclusions))
    return checks

def main():
    cfg=json.loads(CONTRACT.read_text());before={str(p.relative_to(ROOT)):sha(p) for p in [DB,MAIN,PROTOCOL]}
    with ro(DB) as c:
        # Explicit whitelist, never attached to the quarantined database.
        bars=[dict(r) for r in c.execute('SELECT observation_id,trade_date,open,high,low,close,volume_native,amount_cny,turnover_pct,volume_unit,turnover_unit,source_sha256,retrieved_at FROM stock_raw_reference ORDER BY trade_date')]
        actions=[dict(r) for r in c.execute('SELECT event_id,ex_date,cash_cny_per_10_gross,transfer_shares_per_10 FROM corporate_actions ORDER BY ex_date')]
        calendar={r[0] for r in c.execute('SELECT trade_date FROM trading_calendar WHERE is_scheduled_open=1')}
    ex_dates={r['ex_date'] for r in actions}
    features=compute_features(bars,ex_dates,cfg);signals=build_signals(features,cfg)
    outcomes,exclusions=build_development_outcomes(bars,ex_dates,cfg)
    stats,fixed_grid=run_statistics(features,signals,outcomes,bars,cfg)
    checks=validate(bars,features,signals,outcomes,exclusions,ex_dates,cfg)
    feature_names=['ma5','ma10','ma15','macd_dif','macd_dea','macd_hist2','kdj_rsv','kdj_k','kdj_d','kdj_j','volume_ratio_prev5','volume_ratio_prev20','turnover_ratio_prev5']
    availability=[]
    for k in feature_names:
        for scope,a,b in [('research_all','2023-01-01','2026-12-31'),('development','2023-01-01','2024-12-31')]:
            eligible=[r for r in features if a<=r['trade_date']<=b]
            availability.append(dict(feature=k,scope=scope,total_dates=len(eligible),computed_dates=sum(finite(r[k]) for r in eligible),missing_dates=sum(not finite(r[k]) for r in eligible),missing_reason='segmented lookback or fixed recursive warmup; never zero-filled'))
    metadata={'contract':cfg,'source_hashes':before,'contract_sha256':sha(CONTRACT),'input_bars':len(bars),'research_dates':918,'available_warmup_dates':242,
      'used_warmup_dates':sum(cfg['calculation_start']<=r['trade_date']<'2023-01-01' for r in bars),
      'known_ex_dates':sorted(ex_dates),'development_anchors':484,'development_outcomes':len(outcomes),'label_exclusions':dict(Counter(r['reason'] for r in exclusions)),
      'development_calendar_evidence_missing':sum(r['trade_date'] not in calendar for r in bars if cfg['development_start']<=r['trade_date']<=cfg['development_end']),
      'all_gates_closed':True,'no_2025_2026_outcomes_generated':True,'formal_st_exclusion_certified':False,'not_a_forecast':True}
    OUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='baseline_oct25_',dir=WORK) as td:
        dest=Path(td)
        write_csv(dest/'日线指标_1160日含预热.csv',features)
        write_csv(dest/'固定信号_不含未来结果.csv',signals)
        write_csv(dest/'指标可计算覆盖.csv',availability)
        write_csv(dest/'开发期描述统计_非预测概率.csv',stats)
        write_csv(dest/'开发期剔除记录.csv',exclusions)
        write_csv(dest/'开发期价格结果_仅2023至2024.csv',outcomes)
        for filename,tables in [('日线特征与信号.sqlite',{'input_bars':bars,'features':features,'signals':signals,'feature_availability':availability,'corporate_action_boundaries':actions}),('开发期结果隔离.sqlite',{'development_price_outcomes':outcomes,'excluded_anchors':exclusions,'descriptive_statistics':stats})]:
            with sqlite3.connect(dest/filename) as c:
                for name,rows in tables.items():sqlite_table(c,name,rows)
                c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT)');c.execute('INSERT INTO metadata VALUES(?,?)',('run',enc(metadata)))
                assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        after={str(p.relative_to(ROOT)):sha(p) for p in [DB,MAIN,PROTOCOL]}
        assert before==after
        checks.append(dict(check='source_databases_and_original_forecast_protocol_unchanged',passed=before==after,details=after))
        (dest/'运行合同.json').write_text(enc(metadata))
        (dest/'验证结果.json').write_text(enc({'checks':checks,'passed':sum(r['passed'] for r in checks),'total':len(checks),'source_hashes_before':before,'source_hashes_after':after}))
        baseline=stats[0]
        doc=f'''# 量价基线：首轮回顾性工程样例

运行日期：2026年10月25日，多伦多。行情固定为10月22日取得、截至10月21日的快照，本轮没有刷新市场数据。

已计算MA5/10/15、MACD12/26/9、KDJ9/3/3、相对前5/20日量比及换手比，保存1160个原始日期、918个研究日期，另存每项实际可计算覆盖。指标不是买卖建议。现时前复权快照未用作输入；原始股价按3个已知除权日切段，窗口不跨段，MACD和KDJ重置后分别预热130/30条，缺值不填0。

2022年5月26日存在尚未桥接的原价跳变，计算从2022年6月1日启动，实际使用2022预热{metadata['used_warmup_dates']}日，而不是默认242日全部适合连续计算。这样做损失一部分指标覆盖，避免把已知机械断点当作指标信号。原始行情和全部242个预热日期仍保留。

本轮临时使用5个已观察行情日的工程例子，结果定义为“下一观察日开盘至第5观察日收盘价格变化”，它不是可成交交易收益，也不代表最终预测期限和上涨阈值已获确认。原首版协议仍是草案，待冻结字段没有被改写。

只生成2023—2024开发期的结果：484个日期锚点中，{len(outcomes)}个有本轮可描述的价格窗口，{len(exclusions)}个因已知除权窗口或跨开发边界被剔除。2025/2026本轮未生成、汇总未来方向或条件收益，不据此声明它们此前从未被观察。

开发期全部保留价格窗口中，正变化{baseline['positive_count']}次、零变化{baseline['zero_count']}次、负变化{baseline['negative_count']}次。它们是重叠的历史观察，不是{len(outcomes)}次独立交易或可用于今天的上涨概率。详细表按预先登记的12种信号固定顺序全部报告，每项比较自己的指标可计算日期基准，没有挑选或排名“最佳信号”。

另用从第一个开发锚点起每5日固定取一次的单一网格作敏感性对照，不挑5种相位里最好的结果；非重叠也不保证独立。初轮不提供把日样本当独立试验的置信区间或预测概率。信号样本少于30的组逐项标出；这只是展示不足，不是30个就足够的认证。

全部日级ST、停牌和官方限价仍未完成认证，因此正式“已排除ST”的准入行数为0。原始价格观察可用于带限制的工程描述，不能称已完成执行回测或费后收益评估。所有model_input_approved及runtime_usable仍为0。

本轮{len(checks)}/{len(checks)}项验证通过，包括每个关键前缀只用当时及过去的值、未来价格/成交量变动不改变开发特征及结果、独立pandas均线/EMA对照、KDJ手算、除权重置、标签日期与开发边界、原库和旧协议哈希未变。

文件说明：日线特征与信号.sqlite只含原始观察、当时及过去形成的特征和信号；开发期结果隔离.sqlite单独保存未来价格结果及描述表，不附加到特征连接。所有公式、预热、信号和局限详见运行合同.json；日线指标与证券软件显示未认证相同初始化，不能用几位小数接近就认定同口径。

公式参考：[pandas EMA递推定义](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.ewm.html)；MACD与KDJ在本轮合同中明确固定实现，不声称与任一终端默认设置完全相同。
'''
        (dest/'量价基线报告.md').write_text(doc)
        # Publish only after every check passes. Existing source stores are never opened writable.
        for p in dest.iterdir():shutil.copy2(p,OUT/p.name)
    print(enc({'output':str(OUT),'features':len(features),'research_dates':918,'development_outcomes':len(outcomes),'exclusions':len(exclusions),'registered_signal_rows':len(stats)-1,'checks_passed':len(checks),'sources_unchanged':before==after}))

if __name__=='__main__':main()
