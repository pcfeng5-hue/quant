"""Independent SSE/SZSE holiday-calendar audit; main database opened read-only.

Holiday intervals are manually transcribed from the linked official notices,
not inferred from the stock or index price series. All weekend days remain
closed, including government compensatory working weekends. This is a
scheduled-session calendar, not a proof of intraday tradability or individual
stock suspension status.
"""
import datetime as dt
import json
import sqlite3
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB_PATH = ROOT / "outputs/高德红外数据库/高德红外_2023起.sqlite"
START = dt.date(2023, 1, 1)
END = dt.date(2026, 10, 13)
VERSION = "official-holidays-manual-transcription-v1"

# Reviewed against BOTH exchanges' dated official annual notices.
NOTICES = {
    "2023": {
        "published_date": "2022-12-27",
        "sse_url": "https://www.sse.com.cn/disclosure/announcement/general/c/c_20221227_5714458.shtml",
        "szse_url": "https://www.szse.cn/disclosure/notice/general/t20221227_598022.html",
        "closures": [
            ["元旦", "2022-12-31", "2023-01-02"],
            ["春节", "2023-01-21", "2023-01-27"],
            ["清明节", "2023-04-05", "2023-04-05"],
            ["劳动节", "2023-04-29", "2023-05-03"],
            ["端午节", "2023-06-22", "2023-06-24"],
            ["中秋节、国庆节", "2023-09-29", "2023-10-06"],
        ],
        "explicit_other_weekend_closures": ["2023-01-28", "2023-01-29", "2023-04-23", "2023-05-06", "2023-06-25", "2023-10-07", "2023-10-08"],
    },
    "2024": {
        "published_date": "2023-12-26",
        "sse_url": "https://www.sse.com.cn/disclosure/announcement/general/c/c_20231226_5733939.shtml",
        "szse_url": "https://www.szse.cn/disclosure/notice/t20231226_605108.html",
        "closures": [
            ["元旦", "2023-12-30", "2024-01-01"],
            ["春节", "2024-02-09", "2024-02-17"],
            ["清明节", "2024-04-04", "2024-04-06"],
            ["劳动节", "2024-05-01", "2024-05-05"],
            ["端午节", "2024-06-10", "2024-06-10"],
            ["中秋节", "2024-09-15", "2024-09-17"],
            ["国庆节", "2024-10-01", "2024-10-07"],
        ],
        "explicit_other_weekend_closures": ["2024-02-04", "2024-02-18", "2024-04-07", "2024-04-28", "2024-05-11", "2024-09-14", "2024-09-29", "2024-10-12"],
    },
    "2025": {
        "published_date": "2024-12-23",
        "sse_url": "https://www.sse.com.cn/disclosure/announcement/general/c/c_20241223_10767108.shtml",
        "szse_url": "https://www.szse.cn/disclosure/notice/t20241223_611283.html",
        "closures": [
            ["元旦", "2025-01-01", "2025-01-01"],
            ["春节", "2025-01-28", "2025-02-04"],
            ["清明节", "2025-04-04", "2025-04-06"],
            ["劳动节", "2025-05-01", "2025-05-05"],
            ["端午节", "2025-05-31", "2025-06-02"],
            ["国庆节、中秋节", "2025-10-01", "2025-10-08"],
        ],
        "explicit_other_weekend_closures": ["2025-01-26", "2025-02-08", "2025-04-27", "2025-09-28", "2025-10-11"],
    },
    "2026": {
        "published_date": "2025-12-22",
        "sse_url": "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml",
        "szse_url": "https://www.szse.cn/disclosure/notice/general/t20251222_618087.html",
        "closures": [
            ["元旦", "2026-01-01", "2026-01-03"],
            ["春节", "2026-02-15", "2026-02-23"],
            ["清明节", "2026-04-04", "2026-04-06"],
            ["劳动节", "2026-05-01", "2026-05-05"],
            ["端午节", "2026-06-19", "2026-06-21"],
            ["中秋节", "2026-09-25", "2026-09-27"],
            ["国庆节", "2026-10-01", "2026-10-07"],
        ],
        "explicit_other_weekend_closures": ["2026-01-04", "2026-02-14", "2026-02-28", "2026-05-09", "2026-09-20", "2026-10-10"],
        "sse_seasonal_confirmation_url": "https://www.sse.com.cn/disclosure/announcement/general/c/c_20260915_10832273.shtml",
        "sse_seasonal_notice_display_date": "2026-09-17",
    },
}
RULE_SOURCES = {
    "sse_2026_rule_2_4_1": "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml",
    "szse_2026_rule_2_3_1_pdf_page_6": "https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf",
    "szse_2021_rule_2_4_1_pdf_page_5": "https://docs.static.szse.cn/www/lawrules/rule/trade/W020210331716400647184.pdf",
}


def dates_between(start, end):
    date = start
    while date <= end:
        yield date
        date += dt.timedelta(days=1)


def build_calendar():
    explicit_weekends = set()
    for notice in NOTICES.values():
        explicit_weekends.update(notice["explicit_other_weekend_closures"])
    rows = []
    for date in dates_between(START, END):
        year = str(date.year)
        holidays = []
        # Include intervals crossing years in both adjacent notices.
        for notice in NOTICES.values():
            for name, start, end in notice["closures"]:
                if start <= date.isoformat() <= end:
                    holidays.append(name)
        weekend = date.weekday() >= 5
        scheduled_open = not weekend and not holidays
        rows.append({
            "trade_date": date.isoformat(), "exchange_scope": "SSE,SZSE",
            "is_scheduled_open": int(scheduled_open),
            "is_weekend": int(weekend),
            "is_announced_holiday": int(bool(holidays)),
            "closure_names": sorted(set(holidays)),
            "is_explicit_other_weekend_closure": int(date.isoformat() in explicit_weekends),
            "source_urls": [NOTICES[year]["sse_url"], NOTICES[year]["szse_url"]],
            "calendar_version": VERSION,
        })
    return rows


def main():
    rows = build_calendar()
    expected = {r["trade_date"] for r in rows if r["is_scheduled_open"]}
    groups = {
        "高德红外_不复权": ["em_daily_0"],
        "高德红外_前复权": ["em_daily_1"],
        "高德红外_后复权": ["em_daily_2"],
        "高德红外_腾讯": ["tencent_daily_2023", "tencent_daily_2024", "tencent_daily_2025", "tencent_daily_2026"],
        "上证指数": ["index_1.000001"],
        "深证成指": ["index_0.399001"],
    }
    db = sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True)
    checks = {}
    for name, sources in groups.items():
        placeholders = ",".join("?" for _ in sources)
        actual_rows = db.execute(
            "SELECT trade_date FROM current_daily_bars WHERE source IN (" + placeholders + ")",
            sources,
        ).fetchall()
        actual = {r[0] for r in actual_rows}
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        checks[name] = {
            "source_names": sources,
            "expected_trading_days": len(expected),
            "actual_unique_dates": len(actual),
            "actual_rows": len(actual_rows),
            "duplicate_date_rows": len(actual_rows) - len(actual),
            "missing_dates": missing,
            "unexpected_dates": extra,
            "passed": not missing and not extra and len(actual_rows) == len(actual),
        }
    db.close()
    counts = Counter(r["trade_date"][:4] for r in rows if r["is_scheduled_open"])
    result = {
        "audited_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_checked_via": "web tool official source pages, manually transcribed dates",
        "calendar_version": VERSION,
        "start": START.isoformat(), "end": END.isoformat(),
        "expected_total_trading_days": len(expected),
        "expected_by_year": dict(sorted(counts.items())),
        "holiday_notices": NOTICES, "weekday_rule_sources": RULE_SOURCES,
        "checks": checks,
        "all_passed": all(c["passed"] for c in checks.values()),
        "limitations": [
            "Expected days are scheduled market sessions derived from official holidays and weekdays; the annual notices do not independently rule out exceptional unscheduled closures.",
            "A stock bar existing on a scheduled trading day does not certify continuous intraday trading or individual stock suspension history.",
            "Holiday dates were transcribed manually from the reviewed official pages. This audit does not validate price/volume values or indicator calculations.",
        ],
    }
    (HERE / "official_calendar_2023_to_20261013.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "calendar_audit_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"expected_total": len(expected), "expected_by_year": result["expected_by_year"], "checks": checks, "all_passed": result["all_passed"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
