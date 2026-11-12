"""Publish a three-track entry point and extend the file catalogue without modifying sources."""
from pathlib import Path
from collections import Counter
import csv,hashlib,json,sqlite3

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/三线研究启动_20261025'
SOURCE=ROOT/'outputs/统一数据底座_20261022/统一数据底座.sqlite'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def read(p):return json.loads((ROOT/p).read_text())

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source_before=sha(SOURCE)
    c=sqlite3.connect(SOURCE.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    assets={r['project_relative_path']:dict(r) for r in c.execute('SELECT * FROM file_assets')}
    supplements={}
    for e in c.execute('SELECT * FROM chip_evidence_files ORDER BY project_relative_path,observation_id,role'):
        path=e['project_relative_path']
        if path in assets:
            assert e['sha256']==assets[path]['sha256']
            continue
        p=ROOT/path;exists=p.is_file();h=sha(p) if exists else None
        assert exists==bool(e['exists_locally']) and h==e['sha256']
        r=supplements.setdefault(path,{'project_relative_path':path,'sha256':h,'bytes':p.stat().st_size if exists else None,'exists_locally':int(exists),'origin':'chip_evidence_supplement_oct25','references':[]})
        r['references'].append({'observation_id':e['observation_id'],'role':e['role']})
    c.close()
    assert len(supplements)==54 and sum(r['exists_locally'] for r in supplements.values())==51
    merged=[]
    for path,r in sorted(assets.items()):
        merged.append({'project_relative_path':path,'sha256':r['sha256'],'bytes':r['bytes'],'exists_locally':r['exists_locally'],'origin':'unified_v4_prior_index','references_json':r['references_json']})
    for path,r in sorted(supplements.items()):
        merged.append({k:v for k,v in r.items() if k!='references'}|{'references_json':enc(r['references'])})
    merged.sort(key=lambda r:r['project_relative_path'])
    idx=OUT/'本轮原件证据索引.sqlite'
    if idx.exists():idx.unlink() # This derived catalogue is reproducible and contains no source records.
    with sqlite3.connect(idx) as d:
        d.execute('CREATE TABLE file_assets(project_relative_path TEXT PRIMARY KEY,sha256 TEXT,bytes INTEGER,exists_locally INTEGER,origin TEXT,references_json TEXT)')
        d.executemany('INSERT INTO file_assets VALUES(?,?,?,?,?,?)',[tuple(r[k] for k in ['project_relative_path','sha256','bytes','exists_locally','origin','references_json']) for r in merged])
        assert d.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    with (OUT/'本轮原件证据索引.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(merged[0]));w.writeheader();w.writerows(merged)
    catalogue={'source_index_rows':len(assets),'supplement_unique_paths':len(supplements),'supplement_present_paths':51,'supplement_missing_rejected_attempt_paths':3,'merged_unique_paths':len(merged),'source_db_unchanged':sha(SOURCE)==source_before,'source_db_sha256':source_before,'supplement_records':list(supplements.values()),'not_a_full_project_file_inventory':True}
    assert catalogue['source_db_unchanged']
    (OUT/'原件目录补充说明.json').write_text(enc(catalogue))
    baseline=read('outputs/三线研究启动_20261025/量价基线/运行合同.json')
    baseline_checks=read('outputs/三线研究启动_20261025/量价基线/验证结果.json')
    chip_checks=read('outputs/三线研究启动_20261025/自建筹码样本/验证结果.json')
    qc=read('work/chip_summary_quality_oct25/核查摘要.json')
    # Preserve all detailed audit files; the entry point only points to them.
    (OUT/'三线状态.json').write_text(enc({
      'client_date':'2026-10-25','authorization':'好的 123 开始','market_data_last_date':'2026-10-21','new_market_collection_this_round':False,
      'track1':{'status':'engineering_features_and_development_descriptive_example_built','research_dates':918,'features_include_warmup_dates':1160,'registered_signals':12,'development_anchors':484,'development_price_windows':469,'excluded_anchors':15,'forecast_model_trained':False,'model_input_approved':False,'final_protocol_changed':False},
      'track2':{'status':'full_saved_summary_quality_audit_complete','observations':954,'accepted':943,'rejected':11,'dates':915,'dates_with_version_differences':5,'single_capture_dates':902,'historical_availability_certified_dates':0,'model_input_approved':False},
      'track3':{'status':'small_sample_hypothetical_estimator_implemented','technical_dates':12,'scenarios':7,'groups':84,'grid_rows_including_zeros':111873,'supplier_native_bins_acquired':False,'model_input_approved':False},
      'evidence_index':{k:v for k,v in catalogue.items() if k!='supplement_records'},
      'next_steps':['review indicator warmup coverage and a narrow baseline admission scope','freeze final horizon, target definition, and validation protocol before predictive model fitting','resolve estimator initialization and turnover sensitivity before expanding or claiming a stable chip feature','evaluate any future chip feature only against matched no-chip baseline dates'],
      'no_live_trade_or_risk_configuration_change':True}))
    report='''# 三线研究启动：本轮完成情况

2026年10月25日，多伦多。按“123开始”推进了量价基线、筹码摘要质量核查、自建筹码技术样本。三项均已产生程序和可复核文件；付费筹码回复不再阻止这三项工作。本轮使用既有行情快照，截至10月21日，没有新增市场数据采集。

| 任务 | 本轮实际结果 | 现在能说明什么 |
|---|---|---|
| ① 量价基线 | 1160日含预热的指标表；918日研究范围；MA5/10/15、MACD、KDJ、量比和换手比；12种预登记信号；2023—2024开发期469个价格窗口 | 已跑通从原行情到指标、信号和历史描述统计的流程；不等于获得当前买卖概率 |
| ② 筹码摘要核查 | 全954条观察、943接受、11拒绝、915日；5日存在不同版本；902日没有重复样本；证据与原件内容重新核对 | 能明确哪些值有版本差异、哪些尚未检验稳定；全部历史可用性及筹码复权仍未认证 |
| ③ 自建筹码估计 | 12个固定技术日期×7种情景＝84组，保存111873行估计网格，含零质量格；源码和参数可重复重建 | 已有可解释的筹码成本估计器；没有取得供应商原生价格档，也不是实际持仓记录 |

三项原始输入和旧预测协议都保持只读。第一项的5观察日是登记的工程例子，正式预测期限、方向阈值、准入和执行配置仍未冻结；没有生成2025/2026的未来结果统计。2026先前已见的个案也不被重新称为从未观察的封存样本。

## 本轮最重要的发现

量价方面，除权不仅影响涨跌幅，也会影响均线、MACD、KDJ和量比。因此按3个已知除权日分段，指标需要重新形成窗口/预热。MA5/10/15分别能计算906/891/876个研究日，MACD为644日、KDJ为844日。各组统计都单独使用自己的有效日期基准，不把指标缺失填0，也不把不同日期组成造成的差别当成指标收益。

开发期484个锚点中保留469个价格窗口，15个因除权或跨开发边界剔除。5日窗口会重叠；固定每5锚点取一次后，全价格基准只有94个窗口，而且仍可能相互依赖。首次表格只是历史描述，不据高百分比或低样本组挑“最佳策略”。逐日ST、停牌、官方限价和实际费用尚未认证，不能声称已完成排ST和可成交、费后回测。

筹码方面，902个单次日没有重复证据，不能按“没有发现差异”写成稳定。5个跨版本日期的全部读数保留，不平均，也不按预测效果挑版本。现存证据4753条引用哈希吻合；一条拒绝尝试缺3份独立文件，记录索引仍在。

自建估计方面，120日基准的初始化残存质量仍为6.22%—51.06%，说明起始假设有明显影响。增加到240日也不能自动解决：2023年1月3日的240日窗口穿过2022年未桥接价格断点，已标成诊断情景。换手口径敏感性也已保存。因此这批价档先作为技术样本，不直接进入预测模型，不把111873行网格算成新增111873条市场观察。

## 文件入口

- [量价基线报告](./量价基线/量价基线报告.md)；[实际指标覆盖](./量价基线/指标可计算覆盖.csv)；[开发期全部描述表](./量价基线/开发期描述统计_非预测概率.csv)。
- [筹码摘要质量报告](./筹码摘要核查/筹码摘要质量报告.md)；[全量质量台账](./筹码摘要核查/筹码摘要质量台账.json)。
- [自建筹码估计报告](./自建筹码样本/自建筹码估计报告.md)；[小样本数据库](./自建筹码样本/自建筹码小样本.sqlite)；[算法与重建说明](./自建筹码样本/重建说明.md)。
- [三线状态](./三线状态.json)；[本轮原件证据索引](./本轮原件证据索引.csv)；[目录补充说明](./原件目录补充说明.json)。

另修正一处目录覆盖问题：旧总资产表漏登记54个筹码证据路径，其中51个文件实际存在，3个是上述已拒绝尝试的缺件。本轮另建合并索引，5444个唯一路径、5441个存在文件，补上登记而不改写旧库。这不等于又丢失54个文件。完整项目文件清单仍以外部完整归档为准。

接下来的重点是核定一套可解释、可验证的首版预测规格，同时改善自建筹码初始化；在这些问题解决前，不把本轮历史频率作为今天的买卖指令。无需新增付费权限即可继续这些研究工作。
'''
    # App file links use absolute targets; restore still retains relative directory structure.
    import re
    report=re.sub(r'\]\(\./([^)]+)\)',lambda m:']('+str(OUT/m.group(1))+')',report)
    (OUT/'三线研究启动报告.md').write_text(report)
    progress=ROOT/'outputs/项目进度与交易需求档案.md'
    txt=progress.read_text()
    first=next(x for x in txt.splitlines() if x.startswith('更新日期：'))
    txt=txt.replace(first,'更新日期：2026年10月25日。阶段：三线研究首轮工程样例已完成，正式预测准入仍未开放。量价指标及开发期描述表已计算；915日筹码摘要完成全量质量核查；12日期自建筹码估计仍为技术情景样本。',1)
    marker='## 本轮补充确认与记账口径\n'
    entry='\n- 2026/10/25：用户明确“好的123开始”，执行量价基线、现有筹码摘要QC、自建筹码小样本三条路线，不再以供应商回复为前置。交付见[三线研究启动报告](./三线研究启动_20261025/三线研究启动报告.md)。首次计算MA5/10/15、MACD、KDJ等及12预登记信号，仅在2023—2024生成469个价格窗口的描述统计；2025/2026本轮不产未来结果。自建12日期×7情景共84组、111873网格行不计入原生筹码采集覆盖；初始残存6.22%—51.06%、换手与历史标尺仍有边界。旧主库、统一库、原预测草案和风险配置未改；正式准入门仍关。\n'
    if '2026/10/25：用户明确' not in txt:txt=txt.replace(marker,marker+entry)
    progress.write_text(txt)
    print(enc({'catalogue_paths':len(merged),'supplement_present':51,'supplement_rejected_missing':3,'source_unchanged':sha(SOURCE)==source_before,'report':str(OUT/'三线研究启动报告.md')}))

if __name__=='__main__':main()
