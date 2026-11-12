"""Package failed OCR pilot honestly; unattempted pages stay unattempted."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
jobs = json.loads((ROOT / "jobs.json").read_text())
key = lambda row: (row["art_code"], row["page_number"], row["source_sha256"])
expected = {key(row) for row in jobs}
trials = {}
for name, filename in [("default_compute", "trial_results.jsonl"),
                       ("cpu_only", "trial_cpu_results.jsonl")]:
    trials[name] = [json.loads(line) for line in (ROOT / filename).read_text().splitlines()]
latest = trials["cpu_only"]
attempted = {key(row) for row in latest}
pending = [row for row in jobs if key(row) not in attempted]
checks = {
    "input_185_unique_pages": len(jobs) == len(expected) == 185,
    "two_unique_pages_attempted": len(latest) == len(attempted) == 2,
    "trials_have_identical_page_identity": {key(x) for x in trials["default_compute"]} == attempted,
    "attempted_pages_subset_of_manifest": attempted <= expected,
    "183_unattempted_pages_retained": len(pending) == 183,
    "all_185_original_sha256_still_match": all(
        hashlib.sha256(Path(row["pdf_path"]).read_bytes()).hexdigest() == row["source_sha256"]
        for row in jobs
    ),
    "no_failure_mislabeled_empty": all(row["status"] == "failed" for row in latest),
    "no_numeric_fact_certified": all(row["numeric_facts_verified"] is False
        for records in trials.values() for row in records),
}
summary = {
    "input_pages": 185, "attempted_unique_pages": 2,
    "successful_ocr_pages": 0, "empty_unverified_pages": 0,
    "failed_unique_pages": 2, "unattempted_pages": 183,
    "remaining_original_text_gap_pages": 185,
    "all_checks_passed": all(checks.values()), "checks": checks,
}
package = {
    "scope": "Original text-empty announcement PDF pages, source database untouched",
    "overall_status": "blocked_local_vision_execution_failed_pilot",
    "reason": "Both default-compute and CPU-only local Vision requests raised nilError on the same two pages. PDFKit rendering succeeded. No explicit permission-denial cause was returned; exact cause remains unverified. Batch intentionally not started.",
    "engine": "Apple Vision VNRecognizeTextRequest revision 3 with PDFKit renderer",
    "recognition_languages": ["zh-Hans", "en-US"],
    "numeric_facts_verified": False,
    "compilation_sdk": "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
    "toolchain_note": "Default SDK 27 was incompatible with installed Swift 6.3.3; compilation with existing SDK 26.5 succeeded. No system configuration was changed.",
    "documentation": [
        "https://developer.apple.com/documentation/vision/recognizing-text-in-images",
        "https://developer.apple.com/documentation/vision/vnrecognizetextrequest/useslanguagecorrection",
        "https://developer.apple.com/documentation/vision/vnrequest/usescpuonly",
        "https://developer.apple.com/documentation/pdfkit/pdfpage/thumbnail(of:for:)",
    ],
    "operations": {"uploaded": False, "models_downloaded": False,
        "privilege_escalation": False, "database_modified": False},
    "verification": summary, "trials": trials,
    "pages": latest, "unattempted_pages": pending,
    "interpretation_limits": [
        "OCR failure does not prove a page is blank",
        "No recognized text or financial number is available from this pilot",
        "Source PDF identity and SHA256 are retained for later authorized local processing",
    ],
}
(ROOT / "ocr_supplement.json").write_text(json.dumps(package, ensure_ascii=False, indent=2))
(ROOT / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False))
assert all(checks.values()), "Provenance packaging validation failed"
