#!/usr/bin/env python3
"""Read existing industry evidence only; no outcomes, indicators or model scores."""
import hashlib
import json
import math
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
OLD = ROOT / "work/market_industry_oct22"
SOURCE_PATHS = [
    OLD / "industry_proxy_identity.json",
    OLD / "399967_methodology_text.txt",
    OLD / "raw/csi_399967_methodology_v1_2_cb73c7a56453aa32.pdf",
    OLD / "manifest.json",
    OLD / "artifact_hashes.json",
    OLD / "summary.json",
    OLD / "input_admission.json",
    OLD / "alignment.json",
    OLD / "cross_source_comparison.json",
    OLD / "cross_source_differences.json",
    OLD / "market_rows_unique.json",
    OLD / "raw/em_399967.SZ_0_913705bc6bdfc985.json",
    OLD / "raw/tencent_399967.SZ_0_c354ba2aaf3336cd.json",
    OLD / "市场与行业背景补齐核验.md",
    ROOT / "outputs/五项数据补缺_20261022/市场行业核对.md",
    ROOT / "outputs/统一数据底座_20261022/缺口与待核清单.csv",
    ROOT / "work/market_context_oct31/contract.json",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    before = {str(p.relative_to(ROOT)): sha(p) for p in SOURCE_PATHS}
    identity = load(OLD / "industry_proxy_identity.json")
    text = (OLD / "399967_methodology_text.txt").read_text(encoding="utf-8")
    manifest = load(OLD / "manifest.json")
    preparation_contract = load(ROOT / "work/market_context_oct31/contract.json")
    expected = {x["path"]: x["sha256"] for x in load(OLD / "artifact_hashes.json")}
    records = load(OLD / "market_rows_unique.json")
    industry = [r for r in records if r["symbol"] == "399967.SZ" and str(r["adjustment"]) == "0"]
    by_source = {s: sorted([r for r in industry if r["source"] == s], key=lambda x: x["trade_date"]) for s in ("eastmoney", "tencent")}
    east = {r["trade_date"]: r for r in by_source["eastmoney"]}
    tx = {r["trade_date"]: r for r in by_source["tencent"]}
    # Comparing raw historical prices is not reading or generating future outcome labels.
    close_mismatches = [d for d in east.keys() & tx.keys() if Decimal(str(east[d]["close"])) != Decimal(str(tx[d]["close"]))]
    diffs = [x for x in load(OLD / "cross_source_differences.json") if x["symbol"] == "399967.SZ"]
    field_counts = Counter(k for x in diffs for k in x["fields"])
    reqs = [x for x in manifest["results"] if x.get("symbol") == "399967.SZ" or x.get("kind") == "methodology"]
    request_evidence = [{k: x.get(k) for k in ("id", "provider", "url", "requested_at_utc", "finished_at_utc", "raw_path", "sha256", "response_key")} | {"http_last_modified": x.get("response_headers", {}).get("Last-Modified")} for x in reqs]

    checks = []
    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("official_original_hash", sha(Path(identity["official_saved_path"])) == identity["official_sha256"], identity["official_sha256"])
    check("archived_text_and_original_match_existing_manifest", all(sha(OLD / p) == expected[p] for p in ("399967_methodology_text.txt", "raw/csi_399967_methodology_v1_2_cb73c7a56453aa32.pdf")), "核对既有PDF和提取文本哈希；没有重新联网或重新OCR")
    check("identity_and_version", identity["symbol"] == "399967.SZ" and "V1.2" in text and "2023" in text and "399967" in text, "仅2023年12月V1.2版本，不推广至2022以来所有规则")
    check("methodology_sampling_and_rebalance", all(x in text for x in ("20%", "80", "10%", "每半年调整一次", "临时调整", "调整市值")), "流动性筛选、最多80只、权重上限、半年和临时调整均在旧提取文本")
    check("provider_date_unique_and_same", len(east) == len(by_source["eastmoney"]) == len(tx) == len(by_source["tencent"]) == 1160 and east.keys() == tx.keys(), "2022-01-04—2026-10-21供应商观测日期集合；不等于官方交易日历审计")
    check("positive_finite_close", all(isinstance(r["close"], (int, float)) and math.isfinite(r["close"]) and r["close"] > 0 for r in industry), "仅检查原始收盘字段，不计算收益/标签")
    check("399967_two_source_close_agree", len(close_mismatches) == 0, {"close_mismatch_dates": close_mismatches})
    check("unresolved_nonclose_differences_retained", field_counts == {"volume_raw": 6, "high": 2, "open": 1}, dict(field_counts))
    check("historical_membership_not_certified", identity["historical_membership_of_002414_verified"] is False and identity["all_historical_methodology_versions_verified"] is False, "零个日期获得002414历史成员身份认证；不等于认定零个日期入选")
    check("original_model_gate_closed", load(OLD / "input_admission.json")["model_usable"] is False, "本轮不打开正式模型准入")
    check("root_contract_keeps_gates_and_counts", all(preparation_contract[k] is False for k in ("historical_first_availability_certified", "formal_historical_model_input_approved", "runtime_usable", "current_forecast_generated", "future_targets_generated_or_scored", "outcomes_2025_2026_opened", "selection_or_optimization")) and preparation_contract["new_candidate_feature_definitions"] == 15 and preparation_contract["auxiliary_feature_definitions"] == 1 and preparation_contract["new_scored_or_model_variants"] == 0 and preparation_contract["previous_registered_research_variants"] == 15, "3指数×4过去close特征+3相对收益差=15候选；stock past5仅辅助1项；不增加已评分变体")

    review = {
        "review_date_local": "2026-10-31",
        "timezone": "America/Toronto",
        "status": "completed_readonly_industry_evidence_review",
        "scope": "仅审查既有资料、定义和工程准备边界；无新采集、无未来标签、无指标数值、无拟合或评分",
        "identity": identity,
        "basis_is_version_specific": True,
        "official_methodology_interpretation": {
            "eligible_scope": "中证全指样本空间内，经流动性过滤后，十大军工集团控股且主营军工相关及其他代表性军工类上市公司",
            "illiquidity_filter": "过去一年日均成交金额排名后20%剔除",
            "selection": "待选样本按过去一年日均总市值排序，最多80只",
            "weighting": "调整股本及权重因子计算的调整市值，单样本权重不超过10%",
            "rebalances": "每半年，6月和12月第二个星期五的下一交易日；另有临时调整",
            "not_industry_census": "筛选及市值权重导致其并非所有军工证券的等权或全量统计；不能代表每家公司一致走势",
            "constituent_claim": "方法规定候选和筛选框架，不提供任何一天实际样本名单；不能由业务相似推定002414已入选",
            "price_not_total_return": "既有快照以指数点位价格序列管理；没有全收益/股息再投资认证，不贴全收益标签",
        },
        "coverage": {s: {"rows": len(rs), "start": rs[0]["trade_date"], "end": rs[-1]["trade_date"], "research_rows_from_2023": sum(r["trade_date"] >= "2023-01-01" for r in rs), "historical_first_availability_certified": False} for s, rs in by_source.items()},
        "unresolved_cross_source_differences": {"close_difference_dates": close_mismatches, "field_counts": dict(field_counts), "rows": diffs, "treatment": "预先固定单源收盘价，不拼接、不选择事后较有利来源；相等不能证明上游独立或历史不修订"},
        "temporal_limits": [
            "实际保存和请求时间为2026-10-22，不是2022—2026各历史日的首次公开/首次接收时间。",
            "最终日收盘价只能用于当天收盘后且供应商已可得的决策时点；不能放入同日收盘前决策。具体接收延迟尚未认证。",
            "PDF标记2023年12月V1.2；URL内日期不能证明首次公开时点，HTTP Last-Modified为2024-11-30也不能反推原始发布日期或生效日。",
            "当前回溯快照可能包含后续更正；双源一致不能取代历史当时版本和修订链。",
            "行情日期对齐不证明官方日历完整、逐日可交易或成分当时可得。",
        ],
        "admission": {
            "engineering_preparation_allowed": ["固定单源指数收盘点位的过去收益、MA20距离等连续历史背景特征", "同一日期端点下股票同一原始价格分段过去5日收益与指数过去5日收益之差", "单独保留可用性、版本、观测日期与缺失标记"],
            "requires_further_evidence_before_certification": ["历史首次可得/修订链", "历史行业/主题分类", "002414逐次入选剔除和生效边界", "历次方法版本及实施日期", "完整成员/权重及逐股状态数据"],
            "not_permitted_as_current_claims": ["高德红外整个历史区间一直是399967成分股", "军工指数回报是行业宽度或真实大资金净买卖", "当前成员回填过去成员", "用当前方法重选过去成分并称当时行业", "当前前复权快照冒充当时可得因子", "把供应商收盘相等称官方真值或独立上游证据", "把指数点位或相对收益差称可实现收益/因果alpha"],
            "formal_model_input_approved": False,
            "research_experiment_registered_by_this_review": False,
            "prediction_validated": False,
            "trading_runtime_enabled": False,
        },
        "candidate_definition_review": [
            {"candidate": "单源指数过去k日简单价格收益", "formula": "r_I,k(t) = C_I(t) / C_I(t-k) - 1", "engineering_assessment": "可准备", "guards": ["k和观测日轴事前登记，不优化", "固定source/symbol/raw price index口径", "只用<=t的完整收盘观测，分母正且有限", "不前填缺值，不压缩缺失日当连续日", "标记实际端点日期，不称日历k天或官方已认证交易k日", "不当作总收益或可交易组合收益"]},
            {"candidate": "收盘相对MA20", "formula": "MA20_I(t) = mean(C_I(t-19),...,C_I(t)); distance_I,20(t) = C_I(t)/MA20_I(t)-1", "engineering_assessment": "可准备，但必须固定尺度及是否含当日", "guards": ["本定义含t共20个同源正有限收盘价", "若改用严格过去20日或点差，属于另一个定义，应另行登记", "冷启动/缺失返回null，不能以短窗冒充20日", "同日完整收盘之后可算；无趋势方向或概率结论"]},
            {"candidate": "个股相对指数过去5日价格收益差", "formula": "relative_price_return_5(t) = [C_S(t)/C_S(t-5)-1] - [C_I(t)/C_I(t-5)-1]", "engineering_assessment": "可准备；只称价格收益差，不称可实现超额收益", "guards": ["先冻结共同日期轴，个股及指数t与t-5的真实日期必须相同", "股票端点及全部支撑日期处于同一已定义原价连续分段，跨未知2022断点/已知除权日则弃答", "共6个观察日完整，不因任一系列缺值压缩日期", "指数全窗单源同口径，股票用已登记原价，不混入当前前复权", "收益差为百分点尺度，不是两个百分数相除的比率", "成员未知时仅称相对军工背景代理；不能称行业中性或去除行业贡献", "若未来证实股票为成分，需披露指数可能含股票自身贡献；本差值也不证明独立因果信息"]},
        ],
        "minimum_next_evidence": [
            {"priority": "price_feature_engineering", "need": "固定输入快照/单源/日期轴/公式/窗口/缺失及分段规则，保存hash和首次可得未认证标记；不需等完整成员即可准备背景价格特征", "blocks": "防止工程定义含糊；不打开正式预测准入"},
            {"priority": "membership", "need": "覆盖研究期之前的一份官方有效样本快照，加所有定期和临时调整公告，分别保存公告时点、生效日、入选/剔除、证券代码映射及原件hash", "blocks": "认证002414历史成员身份和行业成分横截面"},
            {"priority": "methods", "need": "2022起每个有效编制方案及计算维护规则、变更公告、生效日期；现存V1.2只覆盖身份框架证据", "blocks": "跨版本同质性和历史规则复现"},
            {"priority": "availability", "need": "供应商或官方收盘历史版本/修订记录及首次可得或可验证发布时点，未来持续记录首次接收时间", "blocks": "历史当时可得及正式时点准入"},
            {"priority": "breadth", "need": "当日有效行业成员全集及逐股可比收盘/前收、停牌/ST/上市退市和除权基准，固定分母及纳入规则；指数价格序列本身不够", "blocks": "行业上涨家数、涨跌比例、创新高宽度、相对强弱横截面"},
            {"priority": "weights_and_flows", "need": "若研究资金/集中度，另取历史生效权重、自由流通调整与指数成交统计单位/覆盖说明，不从点位反推资金流", "blocks": "加权行业结构、成交强度或资金结论"},
        ],
        "root_contract_independent_definition_review": {
            "path": str(ROOT / "work/market_context_oct31/contract.json"),
            "sha256": before["work/market_context_oct31/contract.json"],
            "reviewed_before_reading_any_feature_or_model_result": True,
            "verdict": "no_material_definition_omission_found_within_retrospective_engineering_scope",
            "counts": {"index_past_close_candidates": 12, "relative_candidates": 3, "stock_auxiliary": 1, "new_scored_model_variants": 0},
            "implementation_guards": [
                "收益公式仅依赖t与t-k端点；MA20依赖t-19至t全部20个close。冲突隔离按精确数值依赖传播，不对无关开高低或仅中间值有差异的简单收益一刀切。",
                "整个输入日期轴须先验证8个固定来源-证券组合逐日一致、唯一、有序；数值缺失不压缩观察日轴。",
                "参与公式的价格及分母finite且>0；冷启动、股票跨分段、精确close冲突、数值无效分别保留null原因。",
                "精确源对照按保存十进制数值，不用容差抹去0.01差异；冲突台账应保留两源观测ID/原值与hash。",
                "股票已知除权日开新段，股票原价分段不能施加至指数；还需保留未来/遗漏除权完整性未认证限制。",
                "工程ready只能表示可算/满足本合同，不改变首次可得、正式模型或运行准入false。",
                "这15个是候选特征定义；不增加已评分研究变体数，后续模型实验另行登记。",
            ],
            "definition_conflict_with_this_review": False,
        },
        "request_evidence": request_evidence,
        "sources": [{"path": str(p), "relative_path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": before[str(p.relative_to(ROOT))]} for p in SOURCE_PATHS],
        "outcome_label_accessed": False,
        "outcome_label_generated": False,
        "future_returns_computed": False,
        "model_fitted_or_scored": False,
        "new_network_requests": 0,
    }
    after = {str(p.relative_to(ROOT)): sha(p) for p in SOURCE_PATHS}
    check("all_read_sources_unchanged", before == after, {"files": len(before)})
    review["checks"] = checks
    review["check_count"] = len(checks)
    review["all_checks_passed"] = all(x["passed"] for x in checks)
    if not review["all_checks_passed"]:
        raise AssertionError([x for x in checks if not x["passed"]])
    (OUT / "行业代理准入审查.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# 行业代理准入审查（2026-10-31）", "", "中证军工399967可用于准备军工**价格背景代理**特征。现有证据不足以认证高德红外在研究期任一天的实际成员身份；这不是认定它从未入选。正式模型输入、预测有效性和运行准入仍为false。", "", "本轮只读既有资料，无联网、无目标标签、无指标数值计算、无拟合和评分。", "", "## 现有身份和来源证据", "", "- 已有官方2023年12月V1.2编制方案，2页；原件哈希与旧记录一致。", "- 该版本先过滤过去一年日均成交金额后20%，待选样本按过去一年日均总市值选最多80只，单样本权重上限10%；半年调整，并可临时调整。", "- 它是有选样及权重规则的军工指数，不是全行业所有证券的等权统计。官方方法没有提供实际历史样本名单。", "- 方法版本只证明该文件的框架；没有证明2022起所有版本相同。", "", f"官方原件：[编制方案]({identity['official_saved_path']})；来源：[中证指数有限公司]({identity['official_url']})。", "", "## 行情覆盖与差异", "", "东财和腾讯各1160个原始观测日，2022-01-04—2026-10-21，2023起各918日。399967两源全部收盘字段一致；6日成交量差异、3日价格差异均保留，后者为2个最高价和1个开盘价差异，不涉及收盘。来源一致不等于上游独立、官方真值或历史未修订。固定单源收盘特征不会使用这些开盘/最高价差异，但不能据此删除原冲突。", "", "## 当时可得与缺口", "", "- 本地保存日期2026-10-22是本次提取时间，历史首次公开/接收时间仍未认证；完整日收盘只能用于当天收盘之后，不能用于同日更早时点。", "- PDF标记2023年12月，HTTP Last-Modified为2024-11-30。文件名日期及Last-Modified都不能替代初始发布日期、生效日和版本链。", "- 未取得历史实际成员、历史权重、方法实施链和当日行业宽度全集。当前名单即使取得，也不能回填研究期。", "- 原始日期相互对齐不构成官方交易日历和逐日交易状态认证。点位涨跌不能替代上涨家数或资金净流入。", "", "## 拟用定义的独立审查", "", "1. 单源过去收益：`C_I(t)/C_I(t-k)-1`。k、同源和日期轴事前冻结；缺值不前填或压缩，保存真实端点。仅为指数价格收益。", "2. 相对MA20：本审查明确为包含t的20个正有限收盘均值，`C_I(t)/mean(C_I(t-19:t))-1`。不足20个则null；严格过去20日或点差是另一个定义。", "3. 相对5日：个股同段原价过去5日收益减指数同一端点过去5日收益。6个观察日完整且真实端点相同；股票跨除权/未知断点则弃答。它是百分点尺度的价格收益差，不能称可实现超额收益、行业中性或因果alpha。成员未知时只称相对军工背景代理。", "", "这些定义可工程准备，不代表已完成模型实验登记或已经证明有预测信息。股票收益支撑日期和指数支撑日期必须逐日对齐，不能各自取第5个非缺失点。收益公式数值只依赖两端点，MA20则依赖全部20个收盘；冲突隔离按精确数值依赖传播。", "", "已在查看任何特征或模型结果之前只读审查根任务contract.json：3指数×4过去close候选加3个相对收益差，合计15个候选定义，股票past5为1个辅助；固定东财、腾讯只作精确close冲突检测，所有正式/PIT/runtime门槛保持false。未发现工程范围内的明显定义遗漏。实现还应保留两源冲突观测ID/原值、检查正有限价格、区别冷启动/分段/冲突null原因；工程ready不代表模型可用。累计已评分研究变体不因这15个候选定义增加。", "", "## 下一步最小证据", "", "1. 工程准备先固定快照、单源、共同日期轴、窗口、公式、分段和缺失规则，保留时点未认证标记。", "2. 成员认证需研究期起始前官方有效样本快照及全部定期/临时调整公告，区分公告时点与生效日。", "3. 跨期方法认证需所有有效版本、计算维护规则及变更生效链。", "4. 当时可得认证需历史版本/修订和首次发布或可验证接收时点；未来开始持续记录首收时间。", "5. 行业宽度需当日有效成员全集、逐股可比价格及上市退市/停牌/ST/除权与分母定义。指数价量不能代替。", "6. 资金或集中度另需历史生效权重、流通调整及成交单位/覆盖说明，不从点位推定真实机构资金。", "", "## 核验与原件保护", "", f"通过{len(checks)}/{len(checks)}项定向核验。{len(SOURCE_PATHS)}份只读来源哈希前后一致。精确来源、请求时间、差异记录和逐项判断见同目录JSON。", "", "|来源|SHA256|", "|---|---|"]
    lines += [f"|{p.relative_to(ROOT)}|{before[str(p.relative_to(ROOT))]}|" for p in SOURCE_PATHS]
    (OUT / "行业代理准入审查.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"all_checks_passed": review["all_checks_passed"], "checks": len(checks), "source_files": len(SOURCE_PATHS), "rows_per_provider": {s: len(rs) for s, rs in by_source.items()}, "close_disagreements": len(close_mismatches), "model_input_approved": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
