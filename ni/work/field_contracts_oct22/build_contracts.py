"""Build read-only source dictionaries and conservative research admission contracts.

This script never changes an existing data file or database and makes no requests.
Only its own work/field_contracts_oct22 directory is writable.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import csv
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
MAIN = ROOT / 'outputs/高德红外数据库/高德红外_2023起.sqlite'
OUT.mkdir(exist_ok=True)


def load(rel):
    return json.loads((ROOT / rel).read_text())


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    h = sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def field(name, typ, unit, definition, aliases=None, caveat=None, nullable=True):
    d = dict(name=name, logical_type=typ, unit=unit, definition=definition,
             nullable=nullable, source_aliases=aliases or [name],
             null_handling='preserve_null_plus_missing_reason; never_coalesce_to_zero')
    if caveat:
        d['caveat'] = caveat
    return d


groups = []


def group(group_id, title, paths, key, fields, time_basis, restrictions, status='exploration_only_unreleased'):
    groups.append(dict(group_id=group_id, title=title, source_paths=paths,
                       observation_key=key, fields=fields, temporal_contract=time_basis,
                       restrictions=restrictions, admission_status=status,
                       historical_predictive_eligibility=False))


S = 'string'
D = 'date_ISO8601'
TS = 'timestamp_ISO8601_with_explicit_offset'
N = 'decimal_text_or_decimal_derived_from_raw_string'
I = 'int64'
B = 'nullable_boolean'
J = 'JSON'

group('source_evidence', '来源、版本与证据', ['main:source_snapshots', 'main:source_requests',
      'work/market_industry_oct22/manifest.json', 'work/events_publication_oct22/stage_manifest.json'],
      ['snapshot_id', 'source_sha256'], [
    field('snapshot_id', S, 'identifier', '请求/采集快照标识；不可只按证券和日期覆盖', ['snapshot_id', 'source_request_id', 'source_request']),
    field('source_provider', S, 'category', '实际提供者；与官方身份和上游独立性分别记录', ['source', 'provider']),
    field('source_url', S, 'URL', '实际请求或原文URL', ['url', 'source_url']),
    field('request_parameters', J, 'provider_specific', '请求参数原值；起止范围与实际返回范围分别保存', ['parameters', 'parameters_json']),
    field('source_sha256', S, 'SHA256', '原始响应/文件字节哈希', ['sha256', 'source_sha256', 'pdf_sha256']),
    field('raw_path', S, 'local_path', '原始文件位置；搬迁后按归档相对路径解析'),
    field('source_row_index', I, 'zero_based_index', '该原件内源行索引；不同请求内的索引不能合并'),
    field('raw_row', J, 'provider_native', '原始字符串/数组/对象，不经单位或复权覆盖'),
    field('retrieved_at_utc', TS, 'UTC', '本项目实际观察/请求起始时刻，不是历史首次公开时刻', ['retrieved_at', 'retrieved_at_utc', 'requested_at_utc', 'observed_at_utc']),
    field('completed_at_utc', TS, 'UTC', '下载结束时刻，可与起始时刻组成观察区间', ['completed_at', 'finished_at_utc']),
    field('error', S, 'diagnostic', '失败仍留记录；失败响应不升级为成功的数据源'),
], '采集时间是当前证据版本的观察时间；不回填为历史知识时间。',
      ['两个网址不证明上游独立', '哈希匹配只认证字节身份，不认证经济正确或全量覆盖'])

group('stock_daily_bars', '股票日行情及复权快照',
      ['work/market_warmup_finalize_oct22/market_rows_all_endpoints.json', 'work/market_industry_oct22/market_rows_unique.json', 'main:daily_bars'],
      ['symbol', 'trade_date', 'source_provider', 'endpoint', 'adjustment', 'snapshot_id'], [
    field('symbol', S, 'exchange_qualified_symbol', '证券和交易所标识，例如002414.SZ'),
    field('trade_date', D, 'Asia/Shanghai_trading_date', '该根日线交易日，不是采集日', ['trade_date', 'date']),
    field('endpoint', S, 'category', '提供者端点版本；腾讯旧fqkline与新newfqkline须区分'),
    field('adjustment', S, 'enum', '0=不复权，1=前复权当次快照，2=后复权当次快照', ['adjustment', 'adjustment_flag']),
    field('adjustment_vintage', S, 'version', '复权价格所基于的当前获取版本', caveat='现时前复权/后复权并非PIT因子；与原始不复权分表或按键隔离'),
    *[field(x, N, 'CNY_per_share', '当日'+y+'；继承该行的复权口径', [x]) for x,y in [('open','开盘'),('high','最高'),('low','最低'),('close','收盘')]],
    field('volume_provider_native', N, 'provider_native', '供应商成交量原数', ['volume_provider_native', 'volume_raw', 'volume'], '股票手数习惯由SDK映射和量额诊断支持；不是正式供应商接口单位认证'),
    field('volume_shares_sdk_normalized', N, 'shares', '股票SDK解释口径下的股数；原始数乘100', caveat='仅股票且单位契约明确时适用；不向指数套用；不将调整价模式等同调整成交量'),
    field('amount_provider_native', N, 'provider_native', '成交额原数；腾讯新端点万元，东方财富元', ['amount_provider_native', 'amount_raw', 'amount']),
    field('amount_cny', N, 'CNY', '东方财富保持元；腾讯新端点SDK解释为原数×10000', ['amount_cny', 'amount_raw'], '腾讯旧端点没有成交额，缺失不是0；保留来源精度与严格差异'),
    field('turnover_percent', N, 'percentage_points', '1.32表示1.32%，不是1.32倍', ['turnover_percent', 'turnover_raw', 'turnover']),
    field('turnover_fraction', N, 'dimensionless_fraction', 'turnover_percent÷100；例如1.32%为0.0132', caveat='不以未经认证的每日自由流通分母重算并覆盖供应商换手率'),
], '完整日K含最终高低收盘和全天量额，只能在该日收盘且数据实际可得之后作为输入；已采历史快照没有历史首次可得日志。2022年为预热，不计入2023起结果样本。',
      ['价格不是总收益', '同日供应商/端点/复权重复观察不增加独立交易日', '行情存在不能证明指定时刻指定订单可成交', '复权快照比值不是已验证历史因子'])

group('index_daily_bars', '市场和行业指数日行情',
      ['work/market_industry_oct22/market_rows_unique.json', 'work/market_industry_oct22/industry_proxy_identity.json'],
      ['symbol', 'trade_date', 'source_provider', 'snapshot_id'], [
    field('symbol', S, 'index_symbol', '000001.SH上证；399001.SZ深成；399967.SZ中证军工'),
    field('trade_date', D, 'Asia/Shanghai_trading_date', '指数日线所属日'),
    *[field(x, N, 'index_points', '价格指数点数，非个股每股价格') for x in ['open','high','low','close']],
    field('volume_raw', N, 'unverified_provider_native_index_volume', '指数源成交量原数', caveat='单位及成分/市场范围未正式认证；不得跨来源拼接、平均或按股票100股套算'),
    field('amount_raw', N, 'provider_reported_CNY_definition_pending', '供应商指数成交额原数', caveat='腾讯旧端点缺失；即使标签为元也未验证指数覆盖范围一致'),
    field('turnover_raw', N, 'provider_pct_definition_unverified', '指数源换手字段，分母和覆盖待核'),
    field('methodology_version', S, 'document_version', '已保存中证军工2023年12月V1.2编制文件，不覆盖所有历史版本'),
    field('historical_membership_verified', B, 'predicate', '是否已取得002414在特定历史日成分资格证据', caveat='当前为未认证；行业背景代理不等于历史成分成员'),
], '完整日线规则同股票；指数方法版本和历史成分有效期另存；同日期对齐不是官方交易日历审计。',
      ['价格指数不是分红再投资总收益指数', '不得从代理指数推断整段历史行业成员', '来源价格/量差异未裁定，全部并存'])

group('chip_web_summary', '网页筹码摘要及同步证据',
      ['outputs/高德红外数据库/历史筹码采集_20261017/每日筹码摘要_915日.csv', 'work/chip_audit_oct22/records/'],
      ['symbol', 'trade_date', 'observation_id', 'observed_at_utc', 'load_context_id'], [
    field('trade_date', D, 'displayed_date', '筹码摘要与K线同步显示日期；意图点击日期不能替代实际显示日期'),
    field('observation_id', S, 'identifier', '每次取样的唯一证据标识'),
    field('observed_at_utc', TS, 'UTC', '页面观察实际时刻，不是历史当日可用时间'),
    field('load_context_id', S, 'context_identifier', '会话、前后复权按钮、可见日期窗口和操作序列，缺失须标注'),
    field('profit_ratio_pct', N, 'percentage_points', '页面显示的估算获利筹码比例', caveat='不是未来上涨概率、真实盈利账户比例或已识别持有人比例'),
    field('average_cost_display', N, 'page_displayed_price_basis_unverified', '网页标称平均成本', caveat='算法、初始化、成本统计量定义及筹码复权未认证，不假定等于真实加权成交成本'),
    *[field(x, N, 'page_displayed_price_basis_unverified', '页面显示成本覆盖区间的对应边界') for x in ['cost90_low','cost90_high','cost70_low','cost70_high']],
    *[field(x, N, 'percentage_points', '页面标称筹码集中度；公式未获供应商认证') for x in ['concentration90_pct','concentration70_pct']],
    *[field(x, N, 'CNY_per_share_display_qfq', '截图K线前复权显示读数，仅用于同步核验') for x in ['open_qfq_display','high_qfq_display','low_qfq_display','close_qfq_display']],
    *[field(x, S, 'page_display_string', '保留万/亿/%及舍入原值，不直接当精确数值') for x in ['volume_display','amount_display','turnover_display']],
    field('complete_price_bins', B, 'data_completeness_predicate', '是否取得完整逐价格档位数值，当前未取得'),
], '显示历史日是估算对象日期；采集日是现时网页算法输出日期。同日不同加载窗口结果必须分版本保存。',
      ['历史获利率不是预测概率', '可见柱状图截图不是全价档数值', '同日不同加载值不平均，不任选为真', '日期数不代表PIT历史认证'])

group('chip_price_bins', '逐价格档位筹码（尚未取得）',
      [], ['symbol', 'trade_date', 'source_provider', 'algorithm_version', 'snapshot_id', 'price_bin_index'], [
    field('price_bin_index', I, 'zero_based_or_provider_defined', '须记录提供者档位顺序定义'),
    field('price_bin_low', N, 'declared_price_basis', '档位下界；未取得，不能由截图自造'),
    field('price_bin_high', N, 'declared_price_basis', '档位上界；闭开边界须有定义'),
    field('weight_provider_native', N, 'provider_native', '原始档位权重，单位须另证'),
    field('weight_fraction', N, 'dimensionless_fraction', '权重换算须有百分比/份额/归一化契约后方可生成'),
    field('algorithm_version', S, 'version', '估算公式版本和初始化规则'),
], '未来取得时也须记录样本日期、算法版本、采集版本及历史首次可得性；第三方估算不能冒充东方财富原值。',
      ['没有数据行，不生成0权重占位', '不以摘要反推唯一完整分布', '不执行未经审阅的下载代码'], 'not_obtained')

group('trade_conditions', '历史交易状态与条件限价',
      ['work/conditions_finish_oct22/daily_trade_conditions_915.json', 'work/conditions_finish_oct22/monthly_report_observations.json'],
      ['symbol', 'trade_date', 'condition_version'], [
    field('trade_date', D, 'Asia/Shanghai_trading_date', '条件适用日；表截止2026-10-16'),
    field('rule_id', S, 'identifier', '按有效期引用规则制度，不证明证券当天状态'),
    field('rule_effective_date', D, 'effective_date', '规则生效日期；区别发布日'),
    field('buy_lot_shares', I, 'shares', '所选普通主板条款的买入数量单位，不外推到所有证券或交易类型'),
    field('price_tick_cny', N, 'CNY_per_share', '所选普通主板报价最小变动单位'),
    field('newly_bought_same_day_resale_allowed', B, 'rule_predicate', '新买股票同日再售规则；已有可卖底仓另计'),
    *[field(x, N, 'percentage_points', '普通或ST制度候选涨跌幅，不是个股已核官方限价') for x in ['default_normal_mainboard_limit_pct','st_regime_limit_pct']],
    field('historical_st_status', S, 'tri_state_predicate', '日级ST状态：true/false/unknown；原源为unknown字符串'),
    field('monthly_suspension_evidence', S, 'scope_limited_evidence', '月报内是否命中，不能推断每日无停牌'),
    field('month_report_name', S, 'monthly_snapshot_label', '月报观察到的简称，不回填日级状态'),
    field('observed_positive_day_volume', B, 'observation_predicate', '当日成交量大于零；仅证明至少有交易'),
    field('intraday_suspension_status', S, 'tri_state_or_unknown', '日内暂停情况未知，日线不能代替'),
    field('conditional_reference_close', N, 'CNY_per_share_unadjusted', '计算候选限价时的条件参考价，不是官方除权参考价'),
    *[field(x, N, 'CNY_per_share_unadjusted', '普通主板假设下的计算值，非官方限价') for x in ['candidate_normal_upper_limit','candidate_normal_lower_limit']],
    *[field(x, N, 'CNY_per_share_official', '官方日限价：尚未取得，不用候选值填空') for x in ['official_daily_upper_limit','official_daily_lower_limit']],
    field('ex_rights_date_from_existing_original_terms', B, 'covered_events_predicate', '是否命中已核3次实施条款，不是全历史事件穷尽证明'),
    field('limit_up_queue_or_fillability', S, 'status', '排队及成交能力需当时盘口/订单/成交信息，当前未知'),
    field('daily_status_verified_normal', B, 'verification_flag', '源false表示未证实正常，并非已证实异常', caveat='规范层应拆 observed_status=unknown 与 certification=false'),
    field('execution_eligible', B, 'admission_decision', '拒绝执行准入的布尔决定；不等于证券无法成交'),
], '规则发布日、生效日、状态所属日、月报期与月报取得时间分开；事后月报不得作为月初已知特征。',
      ['未出现于月报不等于逐日无停牌', '月末简称不等于日级ST认证', '3个除权日禁止简单前收×1.1/0.9', '新股/复牌等特殊情形须额外处理，不能只套普通10%'])

group('cost_schedule', '税费组件及账户计费口径',
      ['work/conditions_finish_oct22/fee_schedule.json', 'work/conditions_finish_oct22/commission_accounting_contract.json'],
      ['fee', 'effective_date', 'research_from', 'research_to', 'evidence_version'], [
    field('fee', S, 'enum', '印花税、经手费、证管费、过户费、券商佣金分别记录'),
    field('effective_date', D, 'effective_date', '真实生效日；未知保持null，不拿研究起日替代'),
    *[field(x, D, 'coverage_date', '本轮选择引用的覆盖区间边界，不宣称完整法律修订链') for x in ['research_from','research_to']],
    *[field(x, N, 'fraction_of_turnover_per_side', '费率小数，不是百分数；逐买/卖侧适用') for x in ['buy_rate','sell_rate']],
    field('status', S, 'evidence_status', '原件、转载、连续性待核或账户未知等等级'),
    field('minimum_per_order_cny', N, 'CNY', '账户最低佣金；未取得，不能默认5元'),
    field('commission_package_mode', S, 'enum_unknown_inclusive_net', '全佣或净佣包费范围由账户证据确认'),
    *[field(x, B, 'inclusion_predicate', '账户佣金是否已含该组件；未知不能当不含') for x in ['contains_exchange_fee','contains_regulatory_fee','contains_transfer_fee']],
    field('rounding_and_order_aggregation', S, 'account_contract', '成交/委托计费、最低费及舍入规则，未知'),
    field('dividend_tax_user_applicable', J, 'tax_status_and_holding_dependent', '个人税务身份和持股期限未确认，不默认0'),
    field('cost_model_complete', B, 'certification_predicate', '所有必要组件/包费/舍入/税务适用满足后方能认证；当前false'),
], '税率按成交发生日适用，印花税按卖出侧；红利税依持股/税务条件另计，发生与扣收时点分开。',
      ['全佣包含的经手/证管等不得再加一次', '过户费是否包含也需证据', '未知佣金不输出精确净收益', '费用边界只做数据合同，不设用户仓位或交易阈值'])

group('corporate_actions', '权益分派及不分配决议',
      ['work/corporate_actions_refine_oct17/corporate_actions.json', 'work/corporate_actions_refine_oct17/non_distribution_decisions.json'],
      ['event_id', 'source_sha256', 'date_role'], [
    field('event_id', S, 'economic_episode_id', '同一次分派不同日期角色共用同一经济事件'),
    field('attributable_period', S, 'financial_period', '利润归属年度/半年度，不是实施年度'),
    field('record_date', D, 'scheduled_record_date', '股权登记日'),
    field('ex_date', D, 'ex_rights_ex_dividend_date', '除权除息日，区别现金到账'),
    field('official_delegated_cash_distribution_date', D, 'scheduled_payment_date_for_delegated_scope', '中国结算代派范围的公告约定支付日'),
    field('user_actual_cash_receipt_date', D, 'account_receipt_date', '用户券商实际到账日，尚未取得'),
    field('capital_transfer_account_credit_date', D, 'scheduled_credit_date', '转增股份记账日'),
    field('transferred_unrestricted_shares_first_trading_date', D, 'scheduled_first_trading_date', '所转无限售股份开始交易日'),
    field('cash_cny_per_10_shares_gross', N, 'CNY_per_10_shares_gross', '公告税前现金条款', ['cash_cny_per_10_shares_gross','gross_cash_cny_per_10_shares']),
    field('transfer_shares_per_10', N, 'new_shares_per_10_old_shares', '转增条款，不是每股比例数'),
    field('cash_cny_per_share_gross', N, 'CNY_per_share_gross', '仅由每10股条款÷10的规范化值，不覆盖原值'),
    *[field(x, I, 'shares', '公告整数登记总股本/新增股份，不用比例理论小数重写') for x in ['total_shares_before','total_shares_after','actual_added_shares']],
    field('shareholder_approval_date', D, 'meeting_date', '最终审议日期；不是首次公开时刻'),
    field('is_cash_or_share_distribution_event', B, 'event_type_predicate', '不分配决议为false，不制造实施事件'),
], '归属报告期、董事会/股东会日期、落款日、公告目录日、登记/除权/支付/工商生效日期分别保存；全部精确历史首次可用仍未认证。',
      ['3次分派是3个事件，11个日期角色不是11次独立样本', '自派两名股东支付日不套用代派日', '不分配的除权和支付日期null原因是不适用', '后续报告修订/总额差异不覆盖先前每股条款'])

group('capital_and_nontrade', '期末股本、股份性质和非交易过户',
      ['work/corporate_actions_refine_oct17/capital_period_observations.json', 'work/corporate_actions_refine_oct17/nontrade_transfers.json', 'main:capital_baseline_candidates'],
      ['observation_id_or_event_id', 'source_sha256', 'period_end_or_completion_date'], [
    field('period_end', D, 'reported_period_end', '期末状态观测的归属日，不是公开日'),
    *[field(x, I, 'shares', '该报告期末披露的股本性质数') for x in ['total_shares','limited_shares','unlimited_shares']],
    field('daily_effective_date', D, 'status_change_effective_date', '期间变化真实生效日，缺失不以期末日替代'),
    field('completion_date', D, 'nontrade_transfer_completion_date', '员工计划非交易过户完成日'),
    field('registration_confirmation_received_date', D, 'confirmation_receipt_date', '公司收到确认的日期，区别过户日'),
    field('shares_original', N, '10000_shares_when_declared', '非交易过户原文万股数'),
    field('shares', I, 'shares', '原文万股×10000，保留原文和转换关系'),
    field('daily_float_pit_eligible', B, 'certification_predicate', '期末股本不能直接当每日自由流通分母，当前false'),
], '报告所属期、披露期、实际股份生效期分开；2024报告回述2023工商日是追溯证据，不能回填2023知识时间。',
      ['无限售股不等于指数方法意义自由流通股', '非交易过户不自动等于发行/注销/限售增加', '算术桥接一致不能认证全部中间事件', '3处股份性质差值留冲突，不能制造解锁日期'])

group('announcements_events', '公告、政策、交割和事件时间台账',
      ['work/events_publication_oct22/announcement_time_ledger_current.json', 'work/events_publication_oct22/normalized_events.json'],
      ['record_id_or_event_id', 'economic_episode_id', 'date_role', 'source_sha256'], [
    field('record_id', S, 'identifier', '来源公告唯一编号及官方编号映射'),
    field('title', S, 'text', '原始题名；标题分类不是因果效应证据'),
    field('event_type', S, 'enum', '公告/政策样本/征求意见/演讲/交割/企业日期角色分别存'),
    field('economic_episode_id', S, 'identifier', '去除转载、日期角色重复的经济事件标识'),
    field('event_date', D, 'event_date_with_role', '发生日、约定日期或候选日期必须用date_role区分'),
    field('date_role', S, 'enum', '登记、除权、支付、期货交割期权到期、页面显示日等'),
    field('announcement_date', D, 'disclosure_day_label', '公告目录所列日期，零点不认证发布分钟', ['announcement_date','publication_date']),
    field('effective_date', D, 'effective_date', '政策或规则施行日，征求意见不标成已施行'),
    field('source_timestamp_raw', J, 'provider_raw_clock', 'announcementTime/storageTime/display_time/eiTime/sort_date/PubDate原值分别保存'),
    field('historical_first_publication_timestamp', TS, 'first_public_availability', '有证据的历史首次公开时刻；当前未认证仍null'),
    field('earliest_model_use_timestamp', TS, 'validated_knowledge_time', '只有历史可得性和决策频率满足后才能设置，不直接用当前采集时间反推'),
    field('historical_input_eligible', B, 'admission_decision', '当前false，不能当历史无公告或数据错误的事实'),
    field('official_monthly_notice_verified', B, 'evidence_predicate', '交割逐月通知是否已核；规则公式不升级为官方逐月原件'),
    field('event_occurrence_confirmed', B, 'evidence_predicate', '事后发生证据；即使true也不认证事前可知'),
], '事件日、官方目录日、网页当前元数据日、生效日、采集时间和首次可用时间六者不混同；312目录查询到10月22日不表示实际公告末日也到该日。',
      ['精确到秒的当前平台字段仍非历史首次发布时间', '公告分类不能直接当涨跌方向', '到期日不能预设大资金净流入或大波动', '转载归同事件，11企业日期角色归3事件', '政策样本非全网政策新闻全集'])

group('financial_reports', '财报原件、供应商报表和修订版本',
      ['main:source_records financial_main/balance_sheet/income_statement/cashflow_statement', 'main:original_report_observations'],
      ['symbol', 'report_period', 'metric', 'statement_scope', 'source_sha256', 'revision_version'], [
    field('report_period', D, 'financial_period_end', '报表归属期末，不当作可用日期', ['REPORT_DATE','report_date','report_period']),
    field('statement_scope', S, 'enum', '合并/母公司、累计/单季、原报/重述必须明确'),
    field('metric', S, 'metric_identifier', '保留供应商原字段名和规范化定义，不凭缩写猜单位'),
    field('value_decimal', N, 'per_metric_declared_unit', '原件数值精确字符串；元/万元/每股/比率逐字段注明'),
    field('unit', S, 'declared_unit', '由具体原件表头或映射证据提供，不以整个JSON统一设为元'),
    field('NOTICE_DATE', D, 'provider_disclosure_day', '提供者披露日，不等于历史精确首次发布'),
    field('UPDATE_DATE', D, 'provider_update_day', '提供者当前修订字段，不当作报告发生日'),
    field('revision_version', S, 'version', '原报和后续重述并存，不把修订覆盖全历史'),
], '报告期末、原披露日、修订披露日及采集版本分别保存；尚无认证可用时间时只可文档探索。',
      ['原报空白保持null不补0', '后续重述不得回填早年特征', '现金流前瞻字段与供应商未来收益类字段须隔离', '已核135数值不代表全部财务字段已核'])

group('shareholder_disclosures', '股东户数、前十流通和股东历史',
      ['main:source_records holder_count/top10_float', 'main:shareholder_history_observations'],
      ['symbol', 'period_end', 'holder_id_or_name', 'source_sha256', 'disclosure_version'], [
    field('period_end', D, 'reported_holding_period_end', '持仓所属期末，不是交易发生或公开日期', ['END_DATE','reference_date']),
    field('holder_name', S, 'reported_entity_name', '原件/来源所列股东，保持匿名/席位身份边界', ['HOLDER_NAME','holder_name']),
    field('holding_shares', N, 'provider_candidate_shares', '来源持有数，须对应原件单位', ['HOLD_NUM']),
    field('holder_count', I, 'accounts_or_holders_provider_definition', '提供者户数，未确认账户/人数身份细分', ['HOLDER_NUM']),
    field('holding_ratio_percent', N, 'percentage_points', '分母须分总股本与流通股本，不能混用', ['HOLD_RATIO','FREE_HOLDNUM_RATIO']),
    field('disclosure_date', D, 'provider_disclosure_day', '持仓披露目录日；缺失不以期末日填补', ['NOTICE_DATE','HOLD_NOTICE_DATE']),
], '期末持仓在后续公布，不能当该期末已知；170源行中的不完整时期不可称完整前十股东。',
      ['持仓变化不等于每日买卖路径', '同名股东不证明整个市场同一批人交易', '供应商排名/类型不推断真实控制人、买卖意图或资金方向'])

group('margin_trading', '融资融券日统计', ['main:source_records margin/margin_page2'],
      ['symbol', 'reference_date', 'snapshot_id', 'row_hash'], [
    field('reference_date', D, 'provider_statistics_date', '统计所属交易日，不是公开日', ['DATE']),
    *[field(x, N, 'provider_candidate_CNY', '来源融资/融券金额，原名和单位证据需保留') for x in ['RZYE','RZMRE','RZCHE','RZJME','RQYE','RZRQYE']],
    *[field(x, N, 'provider_candidate_shares', '来源融券数量，正式单位仍需按原接口/原表认证') for x in ['RQYL','RQMCL','RQCHL','RQJMG']],
    field('source_publication_timestamp', TS, 'availability_time', '实际公布时间缺失，不能默认统计日开盘可知'),
], '日统计公开滞后未认证，按所属日保存并暂阻断历史预测准入。',
      ['余额变化不等于机构方向或下一日价格', '空缺末日不补0', 'RCHANGE3D/5D/10D等未来/含义未核字段进入限制字段表'])

group('fund_flow_proxy', '资金流供应商代理', ['main:normalized_fund_flow', 'main:source_records fund_flow_proxy'],
      ['trade_date', 'snapshot_id', 'mapping_version'], [
    field('trade_date', D, 'provider_statistics_date', '资金流代理所属日'),
    field('flow_amount_raw', N, 'provider_declared_candidate_CNY', '主力/超大/大/中/小单等供应商分类数额，不是交易所净现金总量'),
    field('flow_ratio_pct', N, 'provider_percentage_points', '分类净额占比；分母须引用供应商映射'),
    field('mapping_source', S, 'versioned_mapping_reference', '源串列序和分类口径的映射证据'),
], '全天代理仅收盘后可能可用；滚动窗口各快照分别存，不能冒充2023起全历史。',
      ['大单不等于基金或投行', '不同来源对主力的定义不直接合并', '市场买卖双方成交配对，代理净额不等于全市场净现金流入'])

group('disclosed_trades_seats', '龙虎榜、机构席位和大宗交易',
      ['main:source_records billboard/institution_seats/block_trade'],
      ['dataset', 'trade_date', 'event_window', 'seat_or_trade_key', 'snapshot_id'], [
    field('trade_date', D, 'reported_trade_or_window_end_date', '单日/连续多日榜必须标出窗口', ['TRADE_DATE']),
    field('event_window', S, 'time_window', '例如单日与连续三日榜，不能当独立同口径事件'),
    field('seat_label', S, 'provider_reported_label', '机构专用/营业部名称等披露标签', ['BUYER_NAME','SELLER_NAME']),
    *[field(x, N, 'provider_candidate_CNY', '来源披露金额，不是全市场机构交易') for x in ['BUY_AMT','SELL_AMT','NET_BUY_AMT','DEAL_AMT','BILLBOARD_BUY_AMT','BILLBOARD_SELL_AMT']],
    field('DEAL_PRICE', N, 'CNY_per_share', '大宗成交价，不替代当日日线收盘'),
    field('DEAL_VOLUME', N, 'provider_candidate_shares', '大宗数量，须保留原字段单位证据'),
    field('EXPLANATION', S, 'trigger_reason', '上榜原因；不是投资理由或预测成功率'),
    field('provider_future_return_fields', J, 'restricted_outcome_metadata', 'D1/D2/D3/D5/D10与CHANGE_RATE_nDAYS等需物理隔离'),
], '交易/统计窗口结束日与公开日不同，不能把事后榜单在盘中或窗口初始日使用。',
      ['机构专用不识别具体基金经理或投行', 'EXPLAIN内供应商成功率不是本项目验证概率', '多日榜与单日榜重叠不能重复计收益样本', '累计/榜单金额与单笔交易金额不混算'])

group('calendar', '交易日历与衍生品规则候选', ['main:trading_calendar', 'work/events_publication_oct22/normalized_events.json'],
      ['date', 'exchange_scope', 'calendar_version', 'event_family'], [
    field('trade_date', D, 'calendar_date', '日历日期或事件日期，需区分'),
    field('exchange_scope', S, 'exchange_and_instrument_scope', '沪深现货与中金所衍生品分别适用'),
    field('is_scheduled_open', B, 'scheduled_calendar_predicate', '计划开市不是特定股票实际可交易'),
    field('calendar_version', S, 'version', '日历发布/修订版本，事后日历不证明历史已知'),
    field('source_level', S, 'evidence_grade', '官方逐月、规则推算、供应商日期集合分别记录'),
], '规则候选可解释日期来源但不自动认证事件已发生或当时已知；经过日期不能提升证据等级。',
      ['期货交割和期权到期同日归同经济日期', '股息除权和现金到账分角色', '同日期不能预设因果影响'])

# Profile every old SQLite table and source-record raw key without guessing semantics.
before = digest(MAIN)
conn = sqlite3.connect(MAIN.as_uri() + '?mode=ro', uri=True)
schema_profiles = []
for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    columns = [dict(cid=r[0], name=r[1], sqlite_declared_type=r[2], not_null=bool(r[3]),
                    default_sql=r[4], primary_key_position=r[5]) for r in conn.execute(f'PRAGMA table_info("{name}")')]
    schema_profiles.append(dict(table=name, row_count=conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0], columns=columns))

raw_profiles = []
for (dataset,) in conn.execute('SELECT DISTINCT dataset FROM source_records ORDER BY dataset'):
    records = conn.execute('SELECT payload_json FROM source_records WHERE dataset=?', (dataset,)).fetchall()
    keys = {}
    payload_types = Counter()
    for (payload,) in records:
        obj = json.loads(payload)
        payload_types[type(obj).__name__] += 1
        if not isinstance(obj, dict):
            continue
        for k, v in obj.items():
            entry = keys.setdefault(k, dict(present_count=0, null_count=0, observed_json_types=Counter()))
            entry['present_count'] += 1
            entry['null_count'] += v is None
            entry['observed_json_types'][type(v).__name__] += 1
    prof = dict(dataset=dataset, source_row_count=len(records), payload_type_counts=payload_types,
                row_count_is_not_unique_events=True, fields=[])
    for k, v in sorted(keys.items()):
        prof['fields'].append(dict(field=k, **v, absent_count=len(records)-v['present_count'],
                                   unit='not_inferred_from_name; see_per_metric_or_normalized_contract',
                                   historical_predictive_eligibility=False))
    raw_profiles.append(prof)
conn.close()
after = digest(MAIN)
assert before == after

INPUTS = [
    'work/market_industry_oct22/market_rows_unique.json',
    'work/market_industry_oct22/manifest.json',
    'work/market_industry_oct22/input_admission.json',
    'work/market_industry_oct22/industry_proxy_identity.json',
    'work/market_warmup_finalize_oct22/market_rows_all_endpoints.json',
    'work/market_warmup_finalize_oct22/summary.json',
    'work/market_warmup_finalize_oct22/tencent_new_cross_source_daily_comparison.json',
    'work/market_warmup_finalize_oct22/verify_and_supplement.py',
    'work/market_warmup_finalize_oct22/行情预热与末日核对.md',
    'work/conditions_finish_oct22/daily_trade_conditions_915.json',
    'work/conditions_finish_oct22/monthly_report_observations.json',
    'work/conditions_finish_oct22/fee_schedule.json',
    'work/conditions_finish_oct22/rule_regimes.json',
    'work/conditions_finish_oct22/commission_accounting_contract.json',
    'work/events_publication_oct22/normalized_events.json',
    'work/events_publication_oct22/announcement_time_ledger_current.json',
    'work/events_publication_oct22/summary.json',
    'work/corporate_actions_refine_oct17/corporate_actions.json',
    'work/corporate_actions_refine_oct17/non_distribution_decisions.json',
    'work/corporate_actions_refine_oct17/capital_period_observations.json',
    'work/corporate_actions_refine_oct17/nontrade_transfers.json',
    'work/corporate_actions_refine_oct17/cash_total_scope_difference.json',
    'outputs/高德红外数据库/历史筹码采集_20261017/每日筹码摘要_915日.csv',
    'outputs/五项数据补缺_20261022/行情预热核对.md',
    'outputs/五项数据补缺_20261022/阶段报告.md',
]
input_manifest = [dict(path=p, bytes=(ROOT/p).stat().st_size, sha256=digest(ROOT/p)) for p in INPUTS]

dictionary = dict(
    schema_version='1.0', client_as_of_date='2026-10-22',
    prepared_at_utc=datetime.now(timezone.utc).isoformat(),
    scope='Read-only organization of existing local evidence; no network, browser, new market data, indicators or forecast calculations',
    status='dictionary_and_contract_proposal_not_a_model_release',
    normalized_field_names_are_proposals=True,
    observation_identity_contract='Group observation_key entries describe semantic dimensions, not an executable SQL PRIMARY KEY. Assign a non-null immutable observation_id from source identity/hash and native row identity; unknown dates/units stay null and are not sentinel-key values. A table requiring a known trade_date admits only observations with a verified date and quarantines undated rows.',
    physical_unit_storage='Preserve original numeric strings. For financial/fee arithmetic use decimal, not binary-float sum as source truth. SQLite REAL remains an observation convenience, not a new exact original.',
    inherited_null_rule='Every nullable economic value needs missing_reason_code; null, 0, false, not applicable and not collected are distinct.',
    groups=groups, legacy_sqlite_schema=schema_profiles, legacy_source_payload_field_profiles=raw_profiles,
    source_manifest=input_manifest,
    main_database=dict(path=str(MAIN), sha256_before=before, sha256_after=after, unchanged=before==after),
)
dump('field_dictionary.json', dictionary)

missing_codes = [
    ('NOT_REQUESTED', '本轮没有请求该数据'),
    ('ACCESS_OR_PERMISSION_REQUIRED', '现有授权或公开渠道不足；未登录、购买或绕过'),
    ('REQUEST_FAILED', '网络、HTTP或提供者请求失败，保留诊断'),
    ('PROVIDER_FIELD_ABSENT', '端点模式本身没有该字段，例如腾讯旧端点金额'),
    ('PROVIDER_NULL', '响应字段存在但值为null'),
    ('SOURCE_BLANK', '原件为空白；不补0'),
    ('NOT_APPLICABLE', '经济上不适用，例如已批准不分配的除权日'),
    ('NOT_YET_PUBLISHED', '目标时点尚未公开，不能当缺失0'),
    ('OUTSIDE_RETURNED_COVERAGE', '提供者滚动窗口或起止范围之外'),
    ('OUTSIDE_REQUESTED_SCOPE', '原件返回但不在本轮请求或研究窗口，保留原件不计研究行'),
    ('PARSING_FAILED', '解析失败，原件仍保留'),
    ('OCR_UNVERIFIED', '仅OCR候选且未人工/原件认证'),
    ('UNIT_UNVERIFIED', '单位或统计范围未认证'),
    ('TIME_PRECISION_OR_FIRST_PUBLICATION_UNKNOWN', '只有日标签或当前时钟，真实首次可得时刻未知'),
    ('PIT_VINTAGE_UNVERIFIED', '仅现时历史快照，未认证历史版本'),
    ('DAILY_STATUS_UNCERTIFIED', '月报或日量不足以认证日级ST/暂停/特殊状态'),
    ('OFFICIAL_REFERENCE_NOT_OBTAINED', '缺官方日限价/参考价等'),
    ('SOURCE_CONFLICT_UNRESOLVED', '多来源同字段矛盾，尚未裁定'),
    ('ACCOUNT_SPECIFIC_UNKNOWN', '账户佣金/最低收费/包费/税务未知'),
    ('NOT_OBSERVED_IN_BOUNDED_SEARCH', '限定目录/表中未命中，不能推断全局不存在'),
    ('NOT_OBTAINED_COMPLETE_BINS', '未取得完整逐价格档位数值'),
]

contracts = dict(
    schema_version='1.0', client_as_of_date='2026-10-22',
    status='proposed_conservative_data_contract; not research_hypothesis_or_trade_configuration',
    current_project_release=dict(historical_predictive_release=False, execution_release=False,
                                 probabilities_computed=False, features_computed=False,
                                 reason='Evidence organization is not historical first-availability/PIT, unit, state or execution certification.'),
    use_tiers=[
        dict(tier='raw_archive', allowed='Preserve originals and all outcomes including failed requests/rejected observations', required='Byte identity and explicit origin/observation time'),
        dict(tier='exploratory_observation', allowed='Inspect coverage, field meaning, retrospective charts and source differences', required='Provenance + scope + units/status labels; no forecast performance claim'),
        dict(tier='retrospective_sensitivity_research', allowed='Only after a separate explicit feature/label protocol; compare data-version effects', required='Declared provider/vintage, unresolved flags, no use as untouched historical proof', currently_released=False),
        dict(tier='historical_predictive_validation', allowed='Chronological forecasts using information genuinely known before decision', required='Certified event/knowledge time, version, causality-safe lags, split/purge protocol and independent holdout', currently_released=False),
        dict(tier='execution_or_exact_net_result', allowed='Only with executable-order and complete cost evidence', required='Daily state, official reference/limits, order/lot/cash/settlement and account fees', currently_released=False),
    ],
    temporal_contract=dict(
        exchange_timezone='Asia/Shanghai', persisted_timestamps='ISO8601 with explicit timezone offset; UTC preferred for observation stamps',
        distinct_fields=['event_date', 'report_period_end', 'announcement_day_label', 'source_timestamp_raw',
                         'effective_date', 'historical_first_publication_timestamp', 'earliest_model_use_timestamp',
                         'retrieved_at_utc', 'completed_at_utc', 'revision_publication_timestamp'],
        null_time_is_not_midnight=True,
        naive_provider_clock='Keep raw; do not silently attach timezone or convert midnight date labels to exact releases.',
        daily_bars='Final OHLCV cannot enter a decision before that same day closes and data is available. No speculative universal lag is imposed here.',
        first_availability='A current retrieval proves availability now only; does not prove the same vintage existed on the historical date.',
        historical_join='When released, select versions with certified earliest_model_use_timestamp <= decision_timestamp, and an explicit within-time correction policy. Period-end joins or unconditional forward-fill are forbidden.',
        retrospective_fact='A later report may verify an earlier occurrence, but its later knowledge time remains later.',
        calendar='A third-Friday formula candidate is not upgraded to verified occurrence merely because date has passed.',
    ),
    tri_state_contract=dict(
        value_domain=[True, False, None], status_domain=['confirmed_true','confirmed_false','unknown'],
        false_requires='Affirmative evidence supporting the negative predicate for the declared full scope.',
        unknown_requires='null plus missing_reason_code; may coexist with bounded positive or negative evidence.',
        admission_boolean='A false eligibility/certification gate is a decision/status about evidence, not a fact that trading was impossible or data was false.',
        legacy_examples=[
            dict(source_field='daily_status_verified_normal=false', normalized_fact='daily_normal_status=null', normalized_certification=False, reason='DAILY_STATUS_UNCERTIFIED'),
            dict(source_field='monthly_suspension_target_rows=0', normalized_fact='daily_suspended=null', reason='NOT_OBSERVED_IN_BOUNDED_SEARCH'),
            dict(source_field='historical_st_status=unknown_daily_status_not_certified', normalized_fact='is_st=null', reason='DAILY_STATUS_UNCERTIFIED'),
            dict(source_field='broker_commission_rate=null', normalized_fact='commission_rate=null', reason='ACCOUNT_SPECIFIC_UNKNOWN'),
            dict(source_field='no-distribution ex_date=null', normalized_fact='ex_date=null', reason='NOT_APPLICABLE'),
        ],
    ),
    missing_reason_codes=[dict(code=c, explanation_zh=t) for c,t in missing_codes],
    missing_reason_assignment='A reason is an evidence-backed state, not a fill heuristic. For example NOT_YET_PUBLISHED requires proof that publication had not occurred by the decision time; unknown publication uses TIME_PRECISION_OR_FIRST_PUBLICATION_UNKNOWN. Multiple reasons may apply and should be stored as a linked set.',
    source_conflict_contract=dict(
        key='symbol + event/trade date + field + price basis + unit/scope + source/vintage',
        compare_only_if='Semantic field, time scope, units, adjustment basis and comparison precision are compatible.',
        states=['not_compared','incomparable_unit_or_scope','strict_match','quantization_compatible_not_equal',
                'same_provider_revision','cross_provider_conflict_unresolved','load_context_sensitive',
                'adjudicated_preferred_for_declared_use','rejected_as_mislabelled_with_evidence'],
        no_average=True, no_cross_provider_splice=True, never_overwrite_original=True,
        comparison_record_fields=['left_observation_id','right_observation_id','field','left_raw','right_raw',
                                  'unit','adjustment_basis','difference','comparison_rule_id','tolerance',
                                  'strict_equal','within_tolerance','status','review_evidence','review_version'],
        tolerance='Use an existing documented comparison rule without widening it to erase exceptions; no new research/decision threshold is created here.',
        duplicate_handling='Identical content observations retain all request evidence. A declared deduplicated view may list support IDs; conflict creates separate versions, never multiple independent samples.',
        adjudication='An explicit scoped reviewer decision may later choose a source, recording rationale and sensitivity; no provider is presumed ground truth here.',
        index_volume='Blocked for pooled/spliced quantitative comparison until unit and coverage match.',
        chip='Different initialization/load contexts retain separate observation versions; do not average to create a synthetic chip distribution.',
    ),
    units_and_adjustment=dict(
        raw_immutable=True, record_conversion_expression_and_evidence=True,
        percent='percentage_points / 100 = fraction. Rates in fee_schedule are already fractions; do not divide by 100 again.',
        stock_volume='SDK-explained hands *100 = shares; preserve unit certification status and raw precision. No index extrapolation.',
        tencent_new_amount='raw row[8] *10000 = CNY according to inspected SDK mapping; row indices are zero-based.',
        qfq_hfq='Price snapshot vintage, not historical point-in-time factor. Never label adjusted/unadjusted ratio an independently verified factor.',
        capital='Reported unlimited shares != daily free-float denominator. Do not forward-fill period-end shares into turnover reconstruction.',
        financial='Unit and consolidated/parent/YTD/quarter scope are per metric and per report. Preserve revisions and blank values.',
    ),
    cost_contract=dict(
        account_mode='unknown', exact_net_return_released=False,
        inclusive_mode='Count verified all-in commission once. Add transfer only if known excluded, stamp tax only on applicable sale, and other genuinely excluded components once.',
        net_mode='Only if proven net commission: net brokerage + exchange + regulatory + transfer components not already included, with historical dates and account rounding/minimum.',
        unknown_mode='Do not add every candidate component mechanically. Preserve separate components and unknown package flags; do not output exact net result.',
        dividend_tax='Separate conditional event/holding tax calculation; do not assume zero or charge every trade a generic dividend tax.',
        project_operating_cost='Separate from transaction fees. May later be reported as operating expense and total project P&L without charging it again per trade.',
    ),
    feature_label_isolation=dict(
        status='design_contract_only; no features or labels calculated',
        physical_layout_proposal=dict(
            raw_observations='Read-only versioned source database; includes explicitly restricted provider outcome metadata.',
            features='Separate feature DB/files, whitelist-only columns, decision_timestamp, feature_window_end, max_certified_input_available_at, provenance and contract_version.',
            labels='Separate labels DB/files with outcome_start/end, horizon, maturity flag, future returns/path outcomes/cost assumptions. Feature builder receives no label path or connection.',
            training_join='Join only in evaluation/training pipeline after chronological split and maturity/purge rules are frozen; no labels/views attached during raw feature extraction.',
        ),
        restricted_fields='Provider D1/D2/D3/D5/D10, CHANGE_RATE_nDAYS, RCHANGE3D/5D/10D and ambiguous forward fields remain quarantined pending exact semantics; confirmed future outputs belong only in labels.',
        statistical_boundaries=['Do not call 915 dates 915 independent trades.', '2022 prehistory is warmup, not outcome sample.',
                                'Duplicate sources and date roles do not expand effective sample.',
                                'No random time shuffle; chronological development/calibration/final test and overlapping-label purge remain a future protocol requirement.',
                                'No label that crosses a split boundary or is not mature at evaluation time.'],
        no_blanket_select_star=True,
    ),
    group_gates=[dict(group_id=g['group_id'], exploration_status=g['admission_status'],
                      historical_predictive_eligible=False, execution_eligible=False,
                      remaining_restrictions=g['restrictions']) for g in groups],
)
dump('admission_contracts.json', contracts)

comparison = load('work/market_warmup_finalize_oct22/tencent_new_cross_source_daily_comparison.json')
counts = Counter()
amount_exceptions = []
for row in comparison:
    check = row['fields']['amount_cny']
    if not check['pass_check']:
        scope = 'warmup_2022' if row['date'] < '2023-01-01' else 'research_2023_onward'
        counts[scope] += 1
        amount_exceptions.append(dict(date=row['date'], scope=scope, **check))
assert counts == Counter(warmup_2022=6, research_2023_onward=2)

issues = [
    dict(issue_id='REPORT_GENERATOR_AMOUNT_COUNT_HARDCODE', severity='reproducibility',
         source='work/market_warmup_finalize_oct22/verify_and_supplement.py', line=224,
         observed='生成报告模板硬编码研究3日/预热5日；当前实际报告已手工纠正为2/6。',
         verified_counts=dict(counts), actual_dates=amount_exceptions,
         affected_current_reports=['outputs/五项数据补缺_20261022/行情预热核对.md', 'work/market_warmup_finalize_oct22/行情预热与末日核对.md'],
         current_report_status='currently_correct_2_and_6; generator_can_reintroduce_error',
         count_source_path='work/market_warmup_finalize_oct22/tencent_new_cross_source_daily_comparison.json',
         count_predicate="not row['fields']['amount_cny']['pass_check']",
         scope_predicate="row['date'] < '2023-01-01' means warmup_2022, else research_2023_onward",
         summary_alternative="summary['new_endpoint_cross_source'][scope]['fields']['amount_cny']['strict_mismatch_dates'] after selecting scope; do not use numeric list position",
         minimal_fix='从已有比较行或按scope查找summary聚合，分别格式化研究计数和预热计数进报告模板；不改原50.005元比较边界。',
         recommended_action='后续由根代理把模板改为从比较行聚合计数；本子任务不修改既有文件。', changed=False),
    dict(issue_id='REPORT_RAW_COLUMN_INDEX_AMBIGUITY', severity='documentation',
         source='outputs/五项数据补缺_20261022/行情预热核对.md', line=22,
         observed='“原始第5列/第7列/第8列”实际对应数组row[5]/row[7]/row[8]（零基）。',
         recommended_action='写为零基索引5/7/8，或一基第6/8/9列；数值解析本身当前正确。', changed=False),
    dict(issue_id='LEGACY_FALSE_CERTIFICATION_NOT_FALSE_FACT', severity='semantic_contract',
         source='work/conditions_finish_oct22/daily_trade_conditions_915.json',
         observed='daily_status_verified_normal全部false与ST/日内状态unknown并存，直接转is_normal=false会误称全部异常。',
         recommended_action='保留原字段并拆日级状态unknown和未认证false，拒绝执行准入独立保存。', changed=False),
    dict(issue_id='LEGACY_DAILY_TURNOVER_UNIT_LABEL_NEEDS_MAPPING', severity='unit_contract',
         source='main:daily_bars',
         observed='同名turnover与volume在旧主库和新阶段文件具有不同单位说明和端点可用性；不能只凭列名通用合并。',
         recommended_action='按snapshot/endpoint附单位和原数映射；腾讯旧端点的缺失金额/换手保留null。', changed=False),
]
dump('issues.json', dict(status='read_only_review_no_source_edits', issues=issues))

summary = dict(client_as_of_date='2026-10-22', dictionary_groups=len(groups),
               normalized_field_definitions=sum(len(g['fields']) for g in groups),
               legacy_tables_profiled=len(schema_profiles),
               legacy_source_datasets_profiled=len(raw_profiles),
               raw_field_profiles=sum(len(d['fields']) for d in raw_profiles),
               missing_reason_codes=len(missing_codes), issues=len(issues),
               source_files_hashed=len(input_manifest), main_database_unchanged=before==after,
               no_network_or_browser=True, no_indicators_or_probabilities=True,
               historical_predictive_release=False)
dump('summary.json', summary)

checks = [
    dict(name='unique_group_ids', passed=len({g['group_id'] for g in groups}) == len(groups)),
    dict(name='unique_field_names_within_groups', passed=all(len({f['name'] for f in g['fields']}) == len(g['fields']) for g in groups)),
    dict(name='all_fields_have_types_units_aliases_and_null_rules', passed=all(f['logical_type'] and f['unit'] and f['source_aliases'] and f['null_handling'] for g in groups for f in g['fields'])),
    dict(name='no_group_released_for_historical_prediction', passed=all(g['historical_predictive_eligibility'] is False for g in groups)),
    dict(name='missing_reason_codes_unique', passed=len({c for c,t in missing_codes}) == len(missing_codes)),
    dict(name='amount_exception_count_from_daily_comparison', passed=counts == Counter(warmup_2022=6, research_2023_onward=2), observed=dict(counts)),
    dict(name='main_database_unchanged', passed=before == after, sha256=after),
    dict(name='all_915_conditions_not_certified_normal_without_claiming_abnormal', passed=all(r['daily_status_verified_normal'] is False and r['historical_st_status'] == 'unknown_daily_status_not_certified' for r in load('work/conditions_finish_oct22/daily_trade_conditions_915.json'))),
    dict(name='no_existing_evidence_file_write_operations', passed=True, basis='Builder writes only its OUT directory; all other access uses read_text/read_bytes/sqlite mode=ro.'),
]
assert all(c['passed'] for c in checks)
dump('verification.json', dict(checks=checks, passed=sum(c['passed'] for c in checks), total=len(checks),
                               verification_scope='Contract consistency and targeted source facts, not a complete economic-data certification.'))

note = f'''# 字段、时间与数据准入整理（2026-10-22）

本轮仅只读已有数据，建立 **{len(groups)} 类数据、{summary['normalized_field_definitions']} 个规范字段**的定义和使用边界；另逐表记录旧主库 {len(schema_profiles)} 张表的物理字段，并对 {len(raw_profiles)} 个原始数据集的 {summary['raw_field_profiles']} 个字段记录实际JSON类型、空值和缺列数。没有联网、采集行情、改库或计算指标/概率。

- `field_dictionary.json`：规范字段、类型、单位、来源别名、原数和换算、时间语义、原始字段全量画像及证据哈希。规范名字是新库建议，未声称旧物理字段已经迁移。
- `admission_contracts.json`：探索/历史预测/执行分级、三态、{len(missing_codes)} 个缺失原因、来源冲突和版本保留、费用防重复、特征与未来标签隔离合同。
- `issues.json`：既有文件的4项复现/表述/语义问题；本轮未修改它们。

## 关键边界

筹码获利率是供应商估算的持仓成本分布摘要，**不是未来上涨概率**；915个日期与完整价档是两种覆盖。不同加载上下文的同日数值各自保留，不能平均出新分布。

当次前/后复权是当前回溯版本，不认证历史PIT因子。股票的SDK手数×100、腾讯新端点万元×10000、百分数÷100均保留原数与映射证据，不能套到指数成交量。期末无限售股本不等于逐日自由流通分母。

事件发生日、财报所属期、公告日标签、平台原始时钟、生效日、真实首次公开时刻、采集时刻分开。日K最终高低收量不能进入该日更早盘中决策；精确到秒的平台当前元数据也不自动认证首次公开。现有数据可做证据和覆盖探索，仍未获历史预测认证。

`unknown`、已证实`false`和“不具准入资格”分开。停牌月报未命中只证明该月报未命中，日量大于零只证明当日至少有过交易。`daily_status_verified_normal=false`应读为未认证，不能翻译为该日异常。源冲突保留双方、单位、口径和版本，不覆盖、不拼接、不平均。

全佣/净佣和包费范围未知时不精确算净收益。包含在全佣中的经手费/证管费等不能再加；过户费是否包含另核。股息税不默认0，运营费用与交易费分开核算。

模型特征与未来收益建议使用独立数据库/文件和只读白名单。原库的供应商未来收益仍作原始证据保存，不能被`SELECT *`带进特征；未来标签在单独流水线生成，只有成熟标签并在时间切分后才允许用于评估。

## 发现的可复现性问题

现有正式行情报告已正确写 **研究期2日、预热6日**金额超出原50.005元显示舍入边界；按1157个逐日比较记录重新聚合也得到2/6。但生成器`verify_and_supplement.py`第224行仍硬编码3/5，重跑会把正确文档覆盖错。另“原始第5/7/8列”实际是零基索引5/7/8，宜明确为索引或第6/8/9列。均只列问题，不改原文件。

主库读取前后SHA256相同：`{before}`。合同不新增策略阈值、选股规则、仓位或资金配置。
'''
(OUT / '字段与准入整理说明.md').write_text(note)

outputs = []
for path in sorted(OUT.iterdir()):
    if path.is_file() and path.name != 'artifact_manifest.json':
        outputs.append(dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=digest(path)))
dump('artifact_manifest.json', dict(source_manifest=input_manifest, outputs=outputs))
print(json.dumps(summary, ensure_ascii=False))
