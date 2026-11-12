#!/usr/bin/env python3
"""Read-only event provenance and ex-ante eligibility audit; never open returns.

Run from any directory. Only writes the two reports beside this script. All
historical eligibility remains closed; this audit is not a rule-version or
first-publication certification and performs no event-effect calculation.
"""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DB = ROOT / 'outputs/统一数据底座_20261022/统一数据底座.sqlite'
EXPECTED_DB = '9538ca8bf5944acca50a563967c98f04c010943637bf608ba17fc50eda25dd14'
NORM = ROOT / 'work/events_publication_oct22/normalized_events.json'
RULES = ROOT / 'work/expiry_calendar_oct15/contract_rules.json'
DIV = ROOT / 'work/dividend_event_dates_oct15/event_dates.json'
LEDGER = ROOT / 'work/events_publication_oct22/announcement_time_ledger_current.json'
REVISIONS = ROOT / 'work/events_publication_oct22/provider_timestamp_revisions_vs_oct15.json'
REPOST = ROOT / 'work/events_publication_oct22/repost_deduplication_notes.json'
STAGE = ROOT / 'work/events_publication_oct22/stage_manifest.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def root_path(path, base=ROOT):
    p = Path(path)
    return p if p.is_absolute() else base / p


def relative(path):
    return str(path.relative_to(ROOT))


def main():
    inputs = [DB, NORM, RULES, DIV, LEDGER, REVISIONS, REPOST, STAGE,
              ROOT / 'work/expiry_calendar_oct15/verified_monthly_notices.json',
              ROOT / 'work/events_publication_oct22/new_official_expiry_notice.json']
    before = {relative(p): sha(p) for p in inputs}
    events, rules, dividends = load(NORM), load(RULES), load(DIV)['corporate_actions']
    ledger, revisions, repost = load(LEDGER), load(REVISIONS), load(REPOST)
    stage = load(STAGE)
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    allowed = {'events', 'corporate_actions', 'trading_calendar'}

    def authorizer(action, arg1, arg2, db, trigger):
        if action == sqlite3.SQLITE_READ and arg1 not in allowed:
            return sqlite3.SQLITE_DENY
        if action in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE,
                      sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE,
                      sqlite3.SQLITE_DROP_TABLE}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    c.set_authorizer(authorizer)
    db_events = [dict(r) for r in c.execute('SELECT * FROM events ORDER BY event_id')]
    actions = [dict(r) for r in c.execute('SELECT * FROM corporate_actions ORDER BY event_id')]
    calendar = [dict(r) for r in c.execute('SELECT * FROM trading_calendar ORDER BY trade_date')]
    c.close()
    by = {e['event_id']: e for e in events}
    episodes = defaultdict(list)
    for e in events:
        episodes[e['economic_episode_id']].append(e)
    expiry = [e for e in events if e['event_type'] == 'CFFEX_index_derivatives_expiry_delivery']
    corporate = [e for e in events if e['event_type'] == 'corporate_action_date']
    policy = [e for e in events if e not in expiry and e not in corporate]

    raw_references = []
    for e in events:
        if not e.get('raw_path'):
            continue
        p = root_path(e['raw_path'])
        raw_references.append(dict(kind='event_original', event_id=e['event_id'],
                                   path=relative(p), url=e.get('source_url'),
                                   retrieved_at=e.get('retrieved_at'),
                                   expected_sha256=e['source_sha256'],
                                   exists=p.is_file(), actual_sha256=sha(p) if p.is_file() else None))
    for r in rules:
        p = root_path(r['raw_path'], ROOT / 'work/expiry_calendar_oct15')
        raw_references.append(dict(kind='current_contract_rule', instrument=r['instrument'],
                                   path=relative(p), url=r['source_url'], retrieved_at=r['retrieved_at'],
                                   expected_sha256=r['source_sha256'], exists=p.is_file(),
                                   actual_sha256=sha(p) if p.is_file() else None))
    catalogue_references = []
    for req in stage['results']:
        if req.get('raw_path'):
            p = root_path(req['raw_path'])
            catalogue_references.append(dict(path=relative(p), url=req.get('url'),
                                             retrieved_at=req.get('retrieved_at'),
                                             expected_sha256=req['sha256'], exists=p.is_file(),
                                             actual_sha256=sha(p) if p.is_file() else None))

    rows = []
    for e in events:
        reasons = ['earliest_model_use_timestamp_unknown',
                   'historical_first_publication_version_unverified']
        if e in expiry:
            reasons.append('historical_contract_rule_effective_dates_unverified')
            if not e.get('official_monthly_notice_verified'):
                reasons.append('monthly_date_is_formula_candidate')
            elif e.get('notice_kind') == 'actual_delivery_result':
                reasons.append('post_event_result_must_not_be_used_as_advance_notice')
            else:
                reasons.append('advance_reminder_has_day_only_no_first_seen_clock')
            if e.get('holiday_roll_candidate'):
                reasons.append('holiday_roll_not_monthly_officially_confirmed')
        elif e in corporate:
            reasons.append('signature_and_catalogue_notice_day_not_first_seen_clock')
            if e['date_role'] == 'official_delegated_cash_distribution_date':
                reasons.append('delegated_payment_scope_not_personal_receipt')
        else:
            reasons += ['bounded_non_exhaustive_policy_sample',
                        'issue_publication_repost_effective_dates_not_interchangeable']
            if e['event_date'] is None:
                reasons.append('economic_or_display_date_unknown')
        rows.append(dict(event_id=e['event_id'], economic_episode_id=e['economic_episode_id'],
                         event_type=e['event_type'], date_role=e['date_role'],
                         event_date=e['event_date'], publication_date=e.get('publication_date'),
                         source_timestamp_raw=e.get('source_timestamp_raw'),
                         effective_date=e.get('effective_date'),
                         source_level=e['source_level'], notice_kind=e.get('notice_kind'),
                         original_url=e.get('source_url'), original_path=e.get('raw_path'),
                         source_sha256=e.get('source_sha256'),
                         historical_first_publication_timestamp=None,
                         earliest_model_use_timestamp=None,
                         historical_feature_input_approved=False,
                         countdown_feature_approved=False, reasons=reasons))

    advance = [e for e in expiry if e.get('notice_kind') == 'advance_reminder']
    actual = [e for e in expiry if e.get('notice_kind') == 'actual_delivery_result']
    formula = [e for e in expiry if not e.get('official_monthly_notice_verified')]
    missing_dates = [e['event_id'] for e in events if e['event_date'] is None]
    checks = []

    def ck(name, passed, detail=None):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))

    ck('frozen_unified_source_db_hash', before[relative(DB)] == EXPECTED_DB)
    ck('67_unique_date_role_records_59_episodes', len(events) == len(by) == 67 and len(episodes) == 59)
    ck('database_payloads_equal_saved_normalized_events',
       len(db_events) == 67 and all(json.loads(r['payload_json']) == by[r['event_id']] for r in db_events))
    projected = {'event_type': 'event_type', 'event_date': 'event_date', 'date_role': 'date_role',
                 'economic_episode_id': 'economic_episode_id', 'source_url': 'source_url',
                 'source_sha256': 'source_sha256', 'source_level': 'source_level',
                 'first_publication_time': 'historical_first_publication_timestamp',
                 'earliest_model_use_time': 'earliest_model_use_timestamp'}
    ck('database_exposed_event_columns_match_payload',
       all(all(r[k] == by[r['event_id']].get(v) for k, v in projected.items()) and
           (r['raw_path'] == relative(root_path(by[r['event_id']]['raw_path']))
            if by[r['event_id']].get('raw_path') else r['raw_path'] is None) for r in db_events))
    ck('expiry_46_months_5_official_41_candidates', len(expiry) == 46 and len(advance)+len(actual) == 5 and len(formula) == 41)
    ck('official_evidence_separates_2_advance_3_result', len(advance) == 2 and len(actual) == 3 and
       all(e['publication_date'] < e['event_date'] for e in advance) and
       all(e['publication_date'] == e['event_date'] for e in actual))
    ck('7_rule_sources_no_historical_effective_certification', len(rules) == 7 and
       all(r['effective_from'] is None and not r['effective_date_verified'] and
           not r['historical_rule_change_audit_complete'] for r in rules))
    ck('4_futures_3_index_options_separate_product_types', Counter(r['instrument_type'] for r in rules) ==
       Counter(index_futures=4, index_options=3))
    ck('three_holiday_roll_candidates_not_upgraded',
       [(e['month'], e['event_date']) for e in expiry if e.get('holiday_roll_candidate')] ==
       [('2024-02', '2024-02-19'), ('2026-02', '2026-02-24'), ('2026-06', '2026-06-22')] and
       all(not e.get('official_monthly_notice_verified') for e in expiry if e.get('holiday_roll_candidate')))
    ck('corporate_11_role_rows_3_episodes', len(corporate) == 11 and
       len({e['economic_episode_id'] for e in corporate}) == len(actions) == len(dividends) == 3)
    ck('corporate_date_roles_match_original_date_ledger',
       all(e['event_date'] == next(d for d in dividends if d['art_code'] == e['economic_episode_id'])[e['date_role']]
           for e in corporate))
    ck('personal_cash_receipt_stays_unknown', all(d.get('user_account_actual_cash_receipt_date') is None for d in dividends) and
       all(not e.get('user_account_actual_receipt_verified', False) for e in corporate))
    ck('policy_10_non_exhaustive_episodes_one_missing_display_date', len(policy) == 10 and
       len({e['economic_episode_id'] for e in policy}) == 10 and missing_dates == ['policy-mofcom_uav_explanation_2024'])
    ck('67_unknown_first_use_times_no_approval', all(e.get('historical_first_publication_timestamp') is None and
       e.get('earliest_model_use_timestamp') is None and not e.get('historical_input_eligible') for e in events) and
       all(not e['model_input_approved'] for e in db_events))
    ck('33_event_and_rule_references_all_hash_match', len(raw_references) == 33 and
       all(r['exists'] and r['expected_sha256'] == r['actual_sha256'] for r in raw_references))
    ck('16_catalogue_response_files_all_hash_match', len(catalogue_references) == 16 and
       all(r['exists'] and r['expected_sha256'] == r['actual_sha256'] for r in catalogue_references))
    ck('312_current_announcement_times_stay_unapproved', len(ledger) == 312 and
       all(e['historical_first_publication_timestamp'] is None and e['earliest_model_use_timestamp'] is None and
           not e['historical_input_eligible'] for e in ledger))
    ck('80_provider_clock_revisions_not_certified', len(revisions) == 80 and
       all(not r['first_publication_semantics_certified'] for r in revisions))
    ck('reposts_not_counted_new_episodes', all(r['reposts_independent_event_count'] == 0 for r in repost['clusters']))
    after = {relative(p): sha(p) for p in inputs}
    ck('protected_inputs_unchanged', before == after)
    ck('all_67_countdowns_remain_closed', len(rows) == 67 and all(not r['countdown_feature_approved'] for r in rows))

    result = dict(
        user_date='2026-10-31', status='completed_local_admission_audit',
        scope='event definitions, existing evidence hashes and historical ex-ante eligibility only',
        source_database_read_only=True, network_used=False,
        return_labels_read_or_generated=False, later_period_outcomes_opened=False,
        event_effect_or_capital_flow_analysis_performed=False,
        model_variant_count_increment=0, formal_model_or_runtime_approved=False,
        summary=dict(date_role_rows=len(events), economic_episode_ids=len(episodes),
                     type_counts=dict(Counter(e['event_type'] for e in events)),
                     role_counts=dict(Counter(e['date_role'] for e in events)),
                     expiry_months=len(expiry), official_expiry_months=5,
                     official_advance_months=[e['month'] for e in advance],
                     official_result_months=[e['month'] for e in actual],
                     rule_candidate_months=len(formula),
                     missing_date_event_ids=missing_dates, historical_event_input_approved=0,
                     historical_countdown_features_approved=0,
                     raw_event_reference_rows=sum(r['kind'] == 'event_original' for r in raw_references),
                     unique_event_original_files=len({r['path'] for r in raw_references if r['kind'] == 'event_original'}),
                     rule_source_files=7, catalogue_response_files=16,
                     calendar_min=calendar[0]['trade_date'], calendar_max=calendar[-1]['trade_date'],
                     calendar_days=len(calendar), calendar_scope=sorted({r['exchange_scope'] for r in calendar}),
                     calendar_forward_availability_certified=False),
        source_manifests=dict(inputs_before=before, inputs_after=after, raw_references=raw_references,
                              catalogue_references=catalogue_references, audit_code_sha256=sha(Path(__file__))),
        episode_groups=[dict(economic_episode_id=k, role_row_count=len(v),
                             event_ids=[e['event_id'] for e in v], dates=sorted({e['event_date'] for e in v if e['event_date']}))
                        for k,v in sorted(episodes.items())],
        event_admission=rows,
        required_future_countdown_contract=dict(
            status='not_implemented_no_event_is_currently_approved',
            definition='Count pre-announced scheduled exchange-open dates d with as_of_session_date < d <= event_date; event session=0. Define pre/post-event sign and exchange separately before any experiment.',
            exchange_time_zone='Asia/Shanghai, with explicit UTC mapping and information cutoff',
            must_have=['unchanged historical source version and known-by evidence or a separately declared conservative date-level protocol',
                       'event announcement/active rule/calendar known by the prediction cutoff',
                       'historical effective rule version plus holiday and exceptional closure treatment',
                       'correct exchange scope: CFFEX expiry and SSE/SZSE equity observation clocks are separate',
                       'one economic episode ID across instruments, date roles and reposts; correlation retained',
                       'missing/uncertain date returns NULL and abstains, never zero or normal'],
            forbidden=['derive future remaining observed sessions from future realized stock bars or future suspension status',
                       'use actual-delivery result or later notice version as an earlier advance announcement',
                       'replace first-use time by document signature, URL date, current metadata or fetch time in the past',
                       'turn one monthly date into seven independent events or one dividend into multiple independent episodes',
                       'interpret scheduled dividend payment as personal receipt or mandatory market-wide reinvestment']),
        next_steps=['Keep all 67 historical event input gates closed in this run.',
                    'Prioritize historical known-by/rule-effective evidence and correct exchange calendars; collect without reading target outcomes.',
                    'Separate a future predeclared conservative day-level sensitivity study from certified point-in-time use; do not retroactively claim exact first-publication proof.',
                    'Only after input eligibility and candidate protocol freeze may event candidates be evaluated on registered development outcomes.'],
        checks=checks, checks_passed=sum(x['passed'] for x in checks), checks_total=len(checks),
        all_checks_passed=all(x['passed'] for x in checks))
    (HERE / '事件时间准入审查.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    md = f'''# 事件时间准入审查（2026年10月31日）

本轮完成既有资料的定义、去重、来源哈希和事前可得性审查。**67条日期角色目前没有任何一条获得历史事件输入或事件倒数特征准入**。这表示证据门槛仍未满足，不表示事件没有影响。没有读取或生成收益标签，没有计算事件涨跌概率，没有新增模型变体。

## 一、规模和范围

- 67条日期角色对应59个经济事件编号：46个月中金所事件、3次公司行动、10个政策样本。编号去重不等于统计独立性。
- 中金所范围是IF/IH/IC/IM四类股指期货与IO/MO/HO三类股指期权。七种合约同月暂用同一经济事件编号；日期重合不把期货交割与期权到期概念混同。没有覆盖沪深交易所全部ETF/股票期权，更不能说已整理所有期权到期日。
- 3次公司行动拆成11个日期角色：3股权登记、3除权除息、3官方代派现金、1转增入账、1转增无限售股起始交易日。11条不能算11次分红。除权除息与现金代派同日的角色不能充作独立证据。
- 10个政策样本不是完整新闻或政策总体；1条网页显示/经济日期缺失（policy-mofcom_uav_explanation_2024）。

## 二、官方日期和事前已知是两种证据

- 46个月中5个月具有逐月官方通知，41个月仍为公式候选。
- 提前提醒仅2023-12、2025-01两个月，公告日早于事件日，但首次公开时刻及历史版本未认证。
- 2026-08、09、10三个月保存的是事后交割结果。它们确认经济日期，不能拿来证明该日开盘前已知；尤其不得提前使用结果价格等事后字段。
- 7份现行合约规则原件均存在且哈希匹配，但effective_from与规则发布时间未知，历史规则变更审计未完成。不能仅凭今天的规则追溯认证2023年当时可用的日期。
- 2024-02-19、2026-02-24、2026-06-22三处顺延日期仍为候选，不能因时间已过去而升级。
- 企业实施公告原文核对过经济日期，但签署日、目录公告日、首次公开时刻分别保存；目前签署日与目录候选日有一日差别，不推定哪一个是可用时刻。
- 官方代派现金日期有适用股东范围，不代表用户实际证券账户到账，也不能据此预设资金再投入股票。转增入账也不等于现金流入。

## 三、事件倒数的默认规则

本轮不产出任何历史事件倒数值。将来须先固定预测截止时刻，采用Asia/Shanghai交易时钟，证明公告或有效规则及日历在该截止前可得。若只拥有可靠日期级证据，可以另立保守滞后协议做敏感性研究；不能将这种协议称为已认证首次公开时刻。

可考虑的候选定义是“预测日之后至事件日、当时已公布的交易所计划开市日数量”，事件当日为0；正负方向和跨交易所对齐须在实验前固定。不能用后来真正出现的高德红外K线数量或后来才知道的停牌安排反推当时剩余观察日。缺失或不确定返回NULL并弃答，不填0。

既有日历覆盖{calendar[0]['trade_date']}至{calendar[-1]['trade_date']}，共{len(calendar)}个自然日，范围是SSE/SZSE；不能直接宣称完整CFFEX历史日历，也没有完成每份日历规则在当时的已知性认证。

## 四、政策、公告与重复来源

发文、网页发布、政府转载、生效、咨询截止各有含义。2024年第51号相关样本发文11月15日、政府转载11月19日、生效12月1日不能互换；URL月份不能补首次公开日。征求意见稿不标成已施行，演讲不强行赋予生效日。

312份当前公告时间台账依然全部未准入。80条东方财富display_time相对旧版变化，说明当前平台时钟不能直接当首次发布证明；不是80个新经济事件。原文转载沿用同一经济事件ID，不把多个新闻网站当多个信号样本。

## 五、来源核验和结论

- 数据库events的67条payload与原标准事件JSON逐条一致；暴露列与来源也核对。
- 26条事件原件引用对应18个独立文件；另有7份合约原件、16份公告目录响应，路径存在且哈希全部匹配。
- 本轮受保护输入前后SHA256一致；数据库只读并设置表读取白名单，未打开行情/标签表。
- {sum(x['passed'] for x in checks)}/{len(checks)}项技术与语义检查通过。技术通过不构成事件预测有效证明。

下一步先补历史已知性、有效规则版本与正确交易所日历证据；取得准入后另行登记有限候选和共同开发期样本，再研究事件是否增加预测价值。**不能跳过准入直接研究“交割前必跌、除息后必涨”一类模式。**

机器可读逐条理由、经济事件分组、来源路径、URL、请求时间与SHA256保存在同目录事件时间准入审查.json。可复算程序为audit.py。未请求网络，不宣称更新到今天的事件全集。
'''
    (HERE / '事件时间准入审查.md').write_text(md)
    print(json.dumps({'all_checks_passed': result['all_checks_passed'],
                      'checks_passed': result['checks_passed'], 'checks_total': result['checks_total'],
                      'summary': result['summary']}, ensure_ascii=False, indent=2))
    if not result['all_checks_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
