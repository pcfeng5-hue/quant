"""Offline event metadata audit; no network, broker, signal or order access."""
import argparse
import copy
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return result


def publication_boundary(record):
    precision = record["published_precision"]
    if precision == "second":
        return timestamp(record["published_at"])
    if precision == "day":
        # The hour is unknown: do not invent midnight publication.
        day = date.fromisoformat(record["published_at"])
        return datetime.combine(day + timedelta(days=1), time(),
                                ZoneInfo(record["source_timezone"]))
    raise ValueError("不支持的发布时间精度")


class EventBook:
    def __init__(self):
        self._records = {}

    def add(self, record):
        r = copy.deepcopy(record)
        required = ("record_id", "event_id", "title", "source_url", "source_type",
                    "evidence_kind", "published_at", "published_precision",
                    "received_at", "publication_basis")
        if any(not isinstance(r.get(k), str) or not r[k].strip() for k in required):
            raise ValueError("缺少必填元数据")
        url = urlparse(r["source_url"])
        if url.scheme != "https" or not url.netloc:
            raise ValueError("来源必须是有效HTTPS地址")
        if r["evidence_kind"] not in {"fact", "proxy", "inference", "unverified"}:
            raise ValueError("必须区分事实、代理、推断和未核实线索")
        if type(r.get("revision")) is not int or r["revision"] < 1:
            raise ValueError("版本必须为正整数")
        boundary = publication_boundary(r)
        received = timestamp(r["received_at"])
        # Day precision may be received during the day; compare to day's start.
        earliest = boundary - timedelta(days=1) if r["published_precision"] == "day" else boundary
        if received < earliest:
            raise ValueError("收到时间不能早于来源所述公开时间")
        if r["record_id"] in self._records:
            if self._records[r["record_id"]] == r:
                return False
            raise ValueError("同一记录ID不得覆盖旧内容")
        previous_id = r.get("supersedes")
        if r["revision"] == 1:
            if previous_id is not None:
                raise ValueError("初版不能替代旧版")
        else:
            previous = self._records.get(previous_id)
            if previous is None or previous["event_id"] != r["event_id"]:
                raise ValueError("修订必须关联同一事件的已有记录")
            if r["revision"] != previous["revision"] + 1:
                raise ValueError("修订版本必须连续")
            if received < timestamp(previous["received_at"]):
                raise ValueError("修订收到时间不能倒退")
            previous_boundary = publication_boundary(previous)
            previous_start = previous_boundary - timedelta(days=1) if previous["published_precision"] == "day" else previous_boundary
            if earliest < previous_start:
                raise ValueError("修订公开时间不能倒退")
        if any(v["event_id"] == r["event_id"] and v["revision"] == r["revision"]
               for v in self._records.values()):
            raise ValueError("同一事件版本冲突")
        self._records[r["record_id"]] = r
        return True

    def snapshot(self, as_of, *, mode, delay_seconds=None):
        now = timestamp(as_of)
        if mode not in {"historical", "live"}:
            raise ValueError("模式必须为historical或live")
        if mode == "historical" and (type(delay_seconds) is not int or delay_seconds < 0):
            raise ValueError("历史演示必须明确登记非负模拟延迟")
        candidates, rejected = {}, []
        for record in self._records.values():
            r = copy.deepcopy(record)
            boundary = publication_boundary(r)
            available = max(boundary, timestamp(r["received_at"])) if mode == "live" else (
                boundary + timedelta(seconds=delay_seconds))
            reason = None
            if r["evidence_kind"] == "unverified":
                reason = "UNVERIFIED"
            elif now < available:
                reason = "NOT_AVAILABLE_AT_DECISION"
            row = {"record": r, "available_at": available.isoformat(),
                   "availability_basis": "actual_receipt" if mode == "live" else "simulated_delay"}
            if reason:
                rejected.append(dict(row, reason=reason))
            else:
                old = candidates.get(r["event_id"])
                if old is None or old["record"]["revision"] < r["revision"]:
                    candidates[r["event_id"]] = row
        return {"decision_at": now.isoformat(), "mode": mode,
                "delay_seconds": delay_seconds if mode == "historical" else None,
                "eligible_metadata": list(candidates.values()), "excluded": rejected,
                "note": "元数据可用不等于交易信号；历史发布时间未经过独立档案验证。"}


def main():
    parser = argparse.ArgumentParser(description="检查事件元数据在决策时点是否可用")
    parser.add_argument("records", type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--mode", required=True, choices=["historical", "live"])
    parser.add_argument("--delay-seconds", type=int)
    args = parser.parse_args()
    book = EventBook()
    for record in json.loads(args.records.read_text(encoding="utf-8")):
        book.add(record)
    print(json.dumps(book.snapshot(args.as_of, mode=args.mode,
                                   delay_seconds=args.delay_seconds), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
