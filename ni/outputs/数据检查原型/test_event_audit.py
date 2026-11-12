import unittest
from event_audit import EventBook, timestamp


def sample(**overrides):
    r = dict(record_id="a1", event_id="a", revision=1, title="测试事件",
             source_url="https://example.org/event", source_type="synthetic_test",
             evidence_kind="fact", published_at="2025-09-02T16:00:00+08:00",
             published_precision="second", received_at="2025-09-02T16:05:00+08:00",
             publication_basis="合成测试时间")
    r.update(overrides)
    return r


class EventAuditTests(unittest.TestCase):
    def test_after_close_event_cannot_enter_prior_close(self):
        b = EventBook(); b.add(sample())
        r = b.snapshot("2025-09-02T15:00:00+08:00", mode="historical", delay_seconds=0)
        self.assertEqual(r["eligible_metadata"], [])

    def test_historical_delay_is_required(self):
        with self.assertRaises(ValueError):
            EventBook().snapshot("2025-09-02T15:00:00+08:00", mode="historical")

    def test_live_receipt_delay(self):
        b = EventBook(); b.add(sample())
        r = b.snapshot("2025-09-02T16:03:00+08:00", mode="live")
        self.assertFalse(r["eligible_metadata"])

    def test_historical_assumption_does_not_claim_live_receipt(self):
        b = EventBook(); b.add(sample(received_at="2026-10-09T15:30:22+00:00"))
        r = b.snapshot("2025-09-03T09:00:00+08:00", mode="historical", delay_seconds=60)
        self.assertEqual(r["eligible_metadata"][0]["availability_basis"], "simulated_delay")
        self.assertFalse(b.snapshot("2025-09-03T09:00:00+08:00", mode="live")["eligible_metadata"])

    def test_date_only_does_not_invent_publication_at_midnight(self):
        b = EventBook(); b.add(sample(published_at="2025-09-02", published_precision="day",
                                     source_timezone="Asia/Shanghai"))
        self.assertFalse(b.snapshot("2025-09-02T15:00:00+08:00", mode="historical", delay_seconds=0)["eligible_metadata"])
        self.assertTrue(b.snapshot("2025-09-03T00:00:00+08:00", mode="historical", delay_seconds=0)["eligible_metadata"])

    def test_timezones_represent_same_instant(self):
        b = EventBook(); b.add(sample())
        self.assertTrue(b.snapshot("2025-09-02T08:05:00+00:00", mode="live")["eligible_metadata"])

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError): timestamp("2025-09-02T16:00:00")

    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError): EventBook().add(sample(source_url=""))

    def test_idempotent_duplicate_and_conflicting_overwrite(self):
        b = EventBook(); self.assertTrue(b.add(sample())); self.assertFalse(b.add(sample()))
        with self.assertRaises(ValueError): b.add(sample(title="改写旧内容"))

    def test_revision_does_not_change_past_snapshot(self):
        b = EventBook(); b.add(sample())
        b.add(sample(record_id="a2", revision=2, supersedes="a1", title="更正",
                     published_at="2025-09-03T16:00:00+08:00", received_at="2025-09-03T16:05:00+08:00"))
        self.assertEqual(b.snapshot("2025-09-03T09:00:00+08:00", mode="live")["eligible_metadata"][0]["record"]["revision"], 1)
        self.assertEqual(b.snapshot("2025-09-04T09:00:00+08:00", mode="live")["eligible_metadata"][0]["record"]["revision"], 2)

    def test_missing_revision_parent_rejected(self):
        with self.assertRaises(ValueError): EventBook().add(sample(record_id="a2", revision=2, supersedes="missing"))

    def test_unverified_cannot_be_eligible(self):
        b = EventBook(); b.add(sample(evidence_kind="unverified"))
        self.assertEqual(b.snapshot("2025-09-03T09:00:00+08:00", mode="live")["excluded"][0]["reason"], "UNVERIFIED")

    def test_input_and_output_mutation_do_not_change_book(self):
        b = EventBook(); r = sample(); b.add(r); r["title"] = "改写"
        out = b.snapshot("2025-09-03T09:00:00+08:00", mode="live")
        out["eligible_metadata"][0]["record"]["title"] = "再改写"
        self.assertEqual(b.snapshot("2025-09-03T09:00:00+08:00", mode="live")["eligible_metadata"][0]["record"]["title"], "测试事件")

    def test_receipt_before_publication_rejected(self):
        with self.assertRaises(ValueError): EventBook().add(sample(received_at="2025-09-02T15:00:00+08:00"))

    def test_revision_publication_cannot_be_backdated(self):
        b = EventBook(); b.add(sample())
        with self.assertRaises(ValueError):
            b.add(sample(record_id="a2", revision=2, supersedes="a1",
                         published_at="2025-09-01T16:00:00+08:00",
                         received_at="2025-09-03T16:05:00+08:00"))


if __name__ == "__main__": unittest.main()
