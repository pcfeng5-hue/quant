"""Verify local OCR provenance, never classify recognized numbers as facts."""
import hashlib
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
jobs = json.loads((ROOT / "jobs.json").read_text())
rows = [json.loads(line) for line in (ROOT / "results.jsonl").read_text().splitlines()]
key = lambda row: (row["art_code"], row["page_number"], row["source_sha256"])
expected = {key(row) for row in jobs}
actual = {key(row) for row in rows}
checks = {
    "job_count_185": len(jobs) == 185,
    "input_unique": len(expected) == len(jobs),
    "output_unique": len(actual) == len(rows),
    "output_exactly_matches_jobs": actual == expected and len(rows) == len(jobs),
    "source_hashes_still_match": all(
        hashlib.sha256(Path(job["pdf_path"]).read_bytes()).hexdigest() == job["source_sha256"]
        for job in jobs
    ),
    "no_verified_financial_fact": all(row["numeric_facts_verified"] is False for row in rows),
    "expected_languages": all(row["recognition_languages"] == ["zh-Hans", "en-US"] for row in rows),
    "valid_status": all(row["status"] in {
        "ocr_extracted_unverified", "empty_unverified", "failed"} for row in rows),
    "nonempty_text_has_ocr_status": all(
        bool(row["text"].strip()) == (row["status"] == "ocr_extracted_unverified")
        for row in rows
    ),
    "confidence_in_range": all(
        0 <= obs["confidence"] <= 1
        for row in rows for obs in row["observations"]
    ),
    "normalized_bounding_boxes": all(
        -0.001 <= obs["bounding_box"][field] <= 1.001
        for row in rows for obs in row["observations"]
        for field in ("x", "y", "width", "height")
    ),
}
counts = dict(Counter(row["status"] for row in rows))
summary = {
    "total_pages": len(rows), "status_counts": counts,
    "characters": sum(len(row["text"]) for row in rows),
    "checks": checks,
    "all_checks_passed": all(checks.values()),
    "jsonl_sha256": hashlib.sha256((ROOT / "results.jsonl").read_bytes()).hexdigest(),
    "input_sha256": hashlib.sha256((ROOT / "jobs.json").read_bytes()).hexdigest(),
}
(ROOT / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
package = {
    "scope": "Supplement to 185 originally text-empty PDF pages; original PDF and database untouched",
    "engine": "Apple Vision VNRecognizeTextRequest, PDFKit renderer; on-device only",
    "compilation_sdk": "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
    "documentation": [
        "https://developer.apple.com/documentation/vision/recognizing-text-in-images",
        "https://developer.apple.com/documentation/vision/vnrecognizetextrequest/useslanguagecorrection",
        "https://developer.apple.com/documentation/pdfkit/pdfpage/thumbnail(of:for:)",
    ],
    "interpretation_limits": [
        "OCR and confidence are unverified search text, not verified numbers or financial facts",
        "Table row/column relationships and stamps/signatures can be misread",
        "No recognized text does not prove a page is blank",
        "Source page identity and original file hash retained; text must be checked against original before numeric use",
    ],
    "verification": summary, "pages": rows,
}
(ROOT / "ocr_supplement.json").write_text(json.dumps(package, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False))
if not all(checks.values()):
    raise SystemExit("OCR provenance validation failed")
