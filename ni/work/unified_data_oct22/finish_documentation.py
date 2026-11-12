"""Export actual schema and document the observed data release without changing databases."""
from pathlib import Path
import csv, hashlib, json, shutil, sqlite3

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/统一数据底座_20261022'
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def link(label,path):return f'[{label}]({ROOT/path})'

def main():
    db=sqlite3.connect((OUT/'统一数据底座.sqlite').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    for src,name in [('field_dictionary.json','规范字段提案_188项.json'),('admission_contracts.json','数据使用与准入规范.json')]:
        shutil.copy2(ROOT/'work/field_contracts_oct22'/src,OUT/name)
    descriptions={
      'metadata':'版本、选择策略和受限字段定义。',
      'ingestion_sources':'本次导入清单；行数是来源记录数，不是独立样本数。',
      'file_assets':'本地来源审计选定的5390个原件/证据文件；不是全项目文件清单。',
      'source_requests':'请求与快照登记；不同登记可指向同一响应，不能当独立来源数。',
      'source_records':'保留旧库及补缺资料的清理后结构化载荷；受限字段已另库隔离。',
      'instrument_identifiers':'原供应商标识到统一证券标识及价格单位的映射。',
      'market_daily':'各次采集、供应商、端点、复权方式的独立观察；不跨版本拼接。',
      'chip_observations':'筹码摘要采集尝试；accepted_capture仅指日期对齐等采集检查通过。',
      'chip_evidence_files':'每次筹码观察的真实证据文件及哈希；exists_locally=0显式留缺口。',
      'filings':'312份公告原件；目录刷新时间与首次公开时刻分开。',
      'document_pages':'4253页文本提取结果；不把可提取文字称为全部内容核实。',
      'ocr_pages':'185页本地OCR结果；尚未完成人工核验。',
      'financial_report_observations':'135项财报原件观察；金额单位、期间和修订逐项保留。',
      'corporate_actions':'3次分派经济事件；记录日、除权日与代派支付日分开。',
      'capital_snapshots':'8个期末股本观察；不是逐日流通分母。',
      'trade_conditions':'915日交易条件原记录及最新行情的派生关联；未知状态留NULL。',
      'trade_rules':'3个交易规则历史区间；不等于逐日状态已认证。',
      'fee_components':'7条费用构成/历史段；不是用户真实账户完整费率。',
      'events':'67个日期角色，59个经济事件标识；规则候选不等于逐月官方证实。',
      'trading_calendar':'旧日历原件证据；最新观测行情日未据此补成官方日历。',
      'conflicts':'逐字段或逐日版本差异；条数不等于独立问题日期数。',
      'gaps':'未取得、未核实、版本不一致等9类主要缺口。',
      'daily_coverage':'1160日覆盖矩阵；0表示无对应记录/证据，不表示真实数值为0。',
      'market_reference':'固定选择最新采集集中的东方财富，供浏览；仍显示来源冲突。',
      'stock_raw_reference':'上述浏览入口中的高德红外不复权1160日。',
      'stock_qfq_reference':'上述浏览入口中的高德红外本次前复权快照1160日。',
      'approved_market_inputs':'当前空集；不把资料入库等同研究准入。',
      'approved_chip_inputs':'当前空集；摘要初始化、版本和历史当时可得尚未认证。',
    }
    objects=[];flat=[]
    for o in db.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY type,name"):
        columns=[dict(r) for r in db.execute('PRAGMA table_info("'+o['name']+'")')]
        count=db.execute('SELECT COUNT(*) FROM "'+o['name']+'"').fetchone()[0]
        item=dict(o,rows=count,description=descriptions.get(o['name']),columns=columns)
        objects.append(item)
        for r in columns:flat.append(dict(object_name=o['name'],object_type=o['type'],object_rows=count,table_purpose=item['description'],column_name=r['name'],sqlite_type=r['type'],declared_not_null=r['notnull'],primary_key_position=r['pk'],default_sql=r['dflt_value']))
    (OUT/'实际SQL字段与视图.json').write_text(enc({'database_sha256':sha(OUT/'统一数据底座.sqlite'),'normative_188_are_proposals':True,'objects':objects}))
    with (OUT/'实际SQL字段字典.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    seed=json.loads((ROOT/'work/lineage_audit_oct22/evidence_registry_seed.json').read_text())
    (OUT/'原路径恢复映射.json').write_text(enc({'old_project_root':str(ROOT),'new_project_root':'<解压目录>/project','rule':'仅对需要打开的历史绝对路径做此前缀映射；不批量改写原件，不将绝对路径映射当内容认证。','files':[{'original_absolute_path':r['original_absolute_path'],'project_relative_path':r['project_relative_path']} for r in seed['files']]}))
    qdb=sqlite3.connect((OUT/'受限字段隔离.sqlite').as_uri()+'?mode=ro',uri=True);qdb.row_factory=sqlite3.Row
    restricted=[dict(r) for r in qdb.execute('SELECT dataset,field_name,reason,COUNT(*) AS versioned_cells,SUM(value_json <> \'null\') AS nonnull_cells FROM restricted_values GROUP BY dataset,field_name,reason')]
    with (OUT/'隔离字段计数.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(restricted[0]));w.writeheader();w.writerows(restricted)
    base=(ROOT/'work/field_contracts_oct22/数据整理说明草稿_20261022.md').read_text()
    base=base.replace('本稿数量来自已保存来源和只读核对；统一数据库仍以最终构建和验收记录为准，没有使用尚待验收的筹码观察总行数。','')
    # Derive conflict accounting directly from the finalized observation store.
    bycollection=dict(db.execute('SELECT collection,COUNT(*) FROM conflicts GROUP BY collection'))
    total=sum(bycollection.values())
    conflict_summary=f"当前{total}条差异登记包括：最新市场背景的{bycollection.get('market_industry_oct21',0)}个字段差异、旧预热核对的{bycollection.get('warmup_oct16',0)}个字段差异、{bycollection.get('chip_all_contexts',0)}个筹码日期差异集合。各类可能落在同一天，也可能覆盖相同数值，不能相加作为独立日期或独立样本。"
    addition=f'''
本次统一库的实际规模为23张表、5个视图，保存37,714条行情来源观察。这里包含历史采集版本、供应商和复权方式，不能当成37,714个独立交易日。筹码整理为954次历史观察/尝试，其中943次通过采集检查、11次被拒绝，合计仍是915个有效历史日期；这些数也不是训练样本数。

筹码证据共登记4,756个文件引用，4,753个在本地；缺的3项仅对应一条被拒绝的`round2:R1_pan_later`尝试，其记录索引仍在。所有被接受的观察都有对应登记证据。拒绝尝试不会借用后续`corrected`尝试的文件。早期4条观察没有精确采集时刻，保持留空。

受限字段定义共18项，实际识别出14种字段的6,133个版本化单元（含空值和重复版本），另存隔离库。它们既不代表6,133个训练标签，也不进入默认行情入口。旧原件保留，后续如果设计独立的结果标签表，仍需重新制定时间边界和标签定义。

{conflict_summary}

{link('实际SQL字段字典','outputs/统一数据底座_20261022/实际SQL字段字典.csv')}与{link('使用说明及查询示例','outputs/统一数据底座_20261022/使用说明与查询.sql.md')}说明已建表和字段。原件索引以项目相对路径保存；{link('恢复映射','outputs/统一数据底座_20261022/原路径恢复映射.json')}可定位历史载荷中的旧绝对路径。

完整项目备份单独保存于`/Users/puchun/Documents/Codex/项目归档/ni/20261022_统一整理后完整保存/`，最终是否成功、文件数和哈希以该目录的`归档校验结果.json`为准。该备份包括原项目依赖，而不是只有本轮新增文件。
'''
    audit_path=ROOT/'work/unified_inventory_oct22/unified_store_audit_final.json'
    if audit_path.exists():
        audit=json.loads(audit_path.read_text())
        for suffix in ['.json','.md']:shutil.copy2(audit_path.with_suffix(suffix),OUT/('最终来源对照核验'+suffix))
        addition+=f"\n最终来源对照核验通过{audit['checks_passed']}/{audit['checks_total']}项，包括37,714行行情的377,140个源字段逐值比较、旧源清理载荷和隔离字段逐单元核对、全部登记原件哈希、请求时间映射与SQL元数据核对。被核验的3个数据库在检查中保持不变；旧主库SHA-256仍为`{audit['sha256_after']['outputs/高德红外数据库/高德红外_2023起.sqlite']}`。详见{link('最终核验记录','outputs/统一数据底座_20261022/最终来源对照核验.md')}。\n"
    (OUT/'本轮数据整理报告.md').write_text(base+addition)
    (OUT/'使用说明与查询.sql.md').write_text('''# 统一资料使用说明

这是一份原始观察和质量整理库。使用只读连接；请先查看本轮报告、缺口清单和实际SQL字段字典。不要直接覆盖旧主库，也不要把所有版本拼在一起训练。

`market_daily`保留原`symbol`；跨来源关联使用`canonical_symbol`。`price_unit`区分元/股与指数点。`adjustment`的0/1/2分别对应来源的不复权/前复权/后复权；各次复权价格只是采集时的快照，不能据此声称取得当年历史复权因子。

`market_reference`是固定选择`market_industry_oct21`采集集中的东方财富浏览入口，不按日期自动挑最后值，不平均不同供应商。指数成交量单位和范围仍未统一，查看`volume_unit`、`turnover_unit`及冲突标记。`volume_native`并非统一的股数；`amount_cny`保留各来源换算证据，不能反推未知佣金。

`retrieved_at`记录已保存的采集时间原值；最新行情用请求清单中的完成时间，其他旧记录保留其原始时间命名及语义。`requested_at`为请求发出时间。二者都不是历史首次公开时间。`normalized_requested_start/end`从实际参数或URL恢复，不表示服务端实际返回了该区间；原请求元数据仍在`payload_json`。

`accepted_capture=1`只表示采集校验接受，不代表稳定性、历史可得或模型准入。全部`model_input_approved`为0；两个approved视图是空的。`complete_price_bins=0`表示完整价档未取得，不是该股票没有筹码。日历、状态、官方限价、佣金等未知值留NULL，不用0冒充。`daily_coverage`内的0/1只表示存在相应记录或证据。

`trade_conditions.payload_json`保留当时条件表原值；`original_bar_available`是当时的关联结果，`current_bar_available`是这次重连最新行情的结果。2026-10-16由无行情关联变为已有行情原件，原记录没有重写。`previous_close_unadjusted_candidate`只是上一观察交易日收盘候选，不是官方涨跌停参考价；除权日尤其不能据此直接计算可成交限价。

公告312份、页面4253条及135项财报事实都保留。185页OCR尚未人工核验。分派代派日不等于账户到账日；期末股本不前填为逐日分母。事件按经济标识归并，41个月交割规则候选仍有证据级别标记。资金流、大单和席位数据不推断真实参与者身份。

`受限字段隔离.sqlite`不附加到常规研究连接。其`restricted_values`保存未来收益和时间/定义不明字段的原值、路径与理由，只用于审计或后续另行制定的标签流程。188项规范字段是命名提案；实际SQL列见导出的PRAGMA字典。

以下SQL只查询已有资料，不生成买卖概率：

```sql
-- 1. 查某段研究日期的覆盖；缺记录不代表真实状态为否。
SELECT * FROM daily_coverage
WHERE trade_date BETWEEN '2026-10-12' AND '2026-10-21'
ORDER BY trade_date;

-- 2. 同一天所有筹码读数与加载条件，保留拒绝尝试。
SELECT observation_id,actual_date,kline_date,accepted_capture,
       profit_ratio_pct,average_cost_display,context,observed_at_utc,
       complete_price_bins,model_input_approved
FROM chip_observations WHERE actual_date='2026-10-16'
ORDER BY collection,observation_id;

-- 3. 股票同日不同供应商/版本；观察数不能当独立交易日。
SELECT collection,snapshot_key,provider,endpoint,adjustment,
       trade_date,open,high,low,close,price_unit,volume_native,volume_unit,
       retrieved_at,source_sha256,input_path,input_row_index
FROM market_daily
WHERE canonical_symbol='002414.SZ' AND trade_date='2026-10-16'
ORDER BY collection,provider,adjustment,snapshot_key;

-- 4. 通过真实证据路径追溯某次观察。
SELECT * FROM chip_evidence_files
WHERE observation_id='repeat_oct22:new_session_oct16_default';

-- 5. 查日期角色及其证据级别；这里不是独立事件计数。
SELECT event_id,event_date,date_role,economic_episode_id,source_level,
       first_publication_time,earliest_model_use_time
FROM events ORDER BY event_date,event_id;

-- 6. 核对准入门：当前两项均为0。
SELECT 'market' AS input_type,COUNT(*) AS approved_rows FROM approved_market_inputs
UNION ALL SELECT 'chip',COUNT(*) FROM approved_chip_inputs;
```

恢复到新目录时，以解压后的`project/`为项目根，按相对路径打开文件。历史载荷中的绝对路径先通过`原路径恢复映射.json`转换；不要改写原件。`file_assets`只索引本轮来源审计涉及的5390个文件；全部项目文件的完整清单和恢复校验在独立完整归档中。
''')
    progress=ROOT/'outputs/项目进度与交易需求档案.md'
    text=progress.read_text()
    oldheader='更新日期：2026年10月17日。阶段：P0尚未验收，部分P1数据工作已提前开展；915日网页筹码摘要与截图已采齐并独立验收，完整逐价档数值仍缺，未启动概率实验。'
    newheader='更新日期：2026年10月22日。阶段：数据统一整理；P0尚未验收。新统一库保留全部已导入来源版本，行情研究918日截至10月21日、筹码摘要915日截至10月16日；完整价档仍缺，未启动指标或概率实验。'
    text=text.replace(oldheader,newheader)
    marker='## 本轮补充确认与记账口径\n'
    entry='''
- 2026/10/22统一整理：新建[统一数据底座](./统一数据底座_20261022/本轮数据整理报告.md)，23表5视图，37,714条行情来源观察；有效日期1160=242预热+918研究。954次筹码历史观察/尝试、915有效日期，完整价档0日；原件/版本差异、日期覆盖、缺口、实际SQL字典与188项规范提案分开保存。受限字段6,133个版本化单元另库隔离，主库只读，模型准入全关。补齐采集时间映射、证券标识和单位；修复旧报告生成器硬编码并保留修改前脚本。仅整理既有本地资料，无本轮新增市场采集。完整归档单列保存，是否成功以`项目归档/ni/20261022_统一整理后完整保存/归档校验结果.json`为准。
'''
    if '2026/10/22统一整理' not in text:text=text.replace(marker,marker+entry)
    progress.write_text(text)
    (OUT/'整理变更说明.json').write_text(enc({'baseline_untouched':True,'main_sha256':sha(ROOT/'outputs/高德红外数据库/高德红外_2023起.sqlite'),'historical_builds':['work/unified_data_oct22/build_v1','work/unified_data_oct22/build_v2','work/unified_data_oct22/build_v3'],'current_version':'unified-observation-v4','repairs':['manifest completion times mapped; requested_at remains separate','38 source literal retrieved_at fields mapped','four round1 chip observations typed with exact original fields retained','chip proof paths explicitly indexed; rejected attempt gap retained','legacy index providers mapped from request host','canonical instrument IDs and price units explicit','metadata counts reflect actual stored rows','trade condition current-bar join repaired without overwriting original payload'],'maintenance_log':'work/unified_data_oct22/maintenance_changes.json','new_external_collection_this_round':False}))
    print(enc({'objects':len(objects),'actual_columns_including_views':len(flat),'output':str(OUT),'database_unchanged_by_docs':True}))

if __name__=='__main__':main()
