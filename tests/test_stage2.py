"""Pre-filter, cost-measure flags, per-email usage, pricing, scoring, and the read-only IMAP source (mocked)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from backend import runner
from config import pricing, settings
from tracker import prefilter
from tracker.email_source import SampleMailboxSource

ROOT = Path(__file__).resolve().parents[1]
SRC = SampleMailboxSource()


def test_prefilter_skips_only_emails_that_could_never_pass():
    keep, skipped = prefilter.split(SRC.list_messages())
    reasons = {s["email_id"]: s["outcome"] for s in skipped}
    assert reasons == {"e08": "skipped_quarantined", "e16": "skipped_no_tracker_rows", "e17": "skipped_not_on_roster",
                       "e18": "skipped_auto_reply", "e19": "skipped_not_on_roster"}
    assert len(keep) == 15


def test_measure_flags(monkeypatch):
    assert all(vars(settings.measures()).values())
    monkeypatch.setenv("TRACKER_MEASURES_OFF", "prefilter_emails,batch_intake")
    m = settings.measures()
    assert not m.prefilter_emails and not m.batch_intake and m.stable_prompt_prefix
    monkeypatch.setenv("TRACKER_MEASURES_OFF", "no_such_measure")
    with pytest.raises(ValueError):
        settings.measures()


def test_stable_prefix_flag_changes_instructions():
    from backend.agents import instructions_for
    assert instructions_for("intake") == instructions_for("intake")
    assert instructions_for("intake", "run1").startswith("Run reference: run1")


def test_pricing_cached_and_cache_write_are_subsets_of_input():
    # 1,000,000 input of which 400,000 cached and 100,000 written to cache; 200,000 output
    cost = pricing.cost_usd(1_000_000, 400_000, 200_000, cache_write_tokens=100_000)
    expected = 0.5 * 0.10 + 0.4 * 0.01 + 0.1 * 0.125 + 0.2 * 0.50
    assert cost == pytest.approx(expected)
    assert pricing.as_dict()["placeholders"] is False


def test_per_email_usage_splits_batches_evenly():
    batches = [{"email_ids": ["e01", "e02"], "usage": {"requests": 2, "tool_calls": 4, "input_tokens": 1000,
                                                      "cached_input_tokens": 400, "cache_write_tokens": 0,
                                                      "output_tokens": 100}}]
    out = runner.per_email_usage(["e01", "e02", "e16"], batches, {"checker": {"input_tokens": 50}})
    assert out["emails"]["e01"]["input_tokens"] == 500 and out["emails"]["e16"]["input_tokens"] == 0
    assert out["emails"]["e16"]["processed_by_model"] is False
    assert out["run_overhead"]["input_tokens"] == 50


def test_score_run_on_run1():
    import importlib.util
    spec = importlib.util.spec_from_file_location("score_run", ROOT / "scripts" / "score_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = json.loads((ROOT / "tests" / "fixtures" / "run1_before_fix.json").read_text())
    s = mod.score(report)
    assert (s["precision"], s["recall"], s["exact_match"], s["false_actions"]) == (0.857, 1.0, 18, 2)
    assert set(s["wrong_emails"]) == {"e04", "e20"}


# --- read-only IMAP with a mocked imaplib ------------------------------------------------

RAW = (b"From: Owen Castellano <owen.castellano@brightfutures.example>\r\nSubject: Books invoice\r\n"
       b"Date: Fri, 23 Oct 2026 09:00:00 -0400\r\n\r\nWe paid $100 for books.\r\n")


class FakeIMAP:
    calls: list = []

    def __init__(self, host, port, ssl_context=None, timeout=None):
        FakeIMAP.calls.append(("connect", host, port, ssl_context is not None))

    def login(self, user, password):
        FakeIMAP.calls.append(("login",))
        return "OK", [b""]

    def select(self, mailbox, readonly=False):
        FakeIMAP.calls.append(("select", mailbox, readonly))
        return "OK", [b"1"]

    def uid(self, command, *args):
        FakeIMAP.calls.append(("uid", command, args))
        if command == "SEARCH":
            return "OK", [b"7 9"]
        if command == "FETCH":
            if "HEADER.FIELDS" in args[1]:
                return "OK", [(b"9 (UID 9 BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {80}", RAW.split(b"\r\n\r\n")[0]), b")"]
            return "OK", [(b"9 (UID 9 BODY[] {120}", RAW), b")"]
        raise AssertionError(f"unexpected command {command}")

    def store(self, *a):
        raise AssertionError("STORE must never be called")

    def expunge(self, *a):
        raise AssertionError("EXPUNGE must never be called")

    def logout(self):
        FakeIMAP.calls.append(("logout",))


@pytest.fixture
def fake_imap(monkeypatch):
    import imaplib
    FakeIMAP.calls = []
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setenv("IMAP_HOST", "imap.example.org")
    monkeypatch.setenv("IMAP_USER", "tester@example.org")
    monkeypatch.setenv("IMAP_APP_PASSWORD", "app-pass-secret-123")
    return FakeIMAP


def test_imap_is_off_unless_configured(monkeypatch):
    from tracker import imap_source
    for k in ("IMAP_HOST", "IMAP_USER", "IMAP_APP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    assert imap_source.configured() is False


def test_imap_search_and_import_are_read_only(fake_imap, caplog):
    from tracker import imap_source
    from tracker.email_source import default_source
    caplog.set_level(logging.DEBUG)
    found = imap_source.search(since="2026-10-20", sender='owen"\r\nSTORE', subject="Books")
    assert found[0]["uid"] == "9" and found[0]["from_email"] == "owen.castellano@brightfutures.example"
    ids = imap_source.import_messages(["9"])
    assert ids == ["imap-9"]
    assert default_source().get("imap-9").body.startswith("We paid $100")
    selects = [c for c in fake_imap.calls if c[0] == "select"]
    assert selects and all(c[2] is True for c in selects)  # readonly
    fetches = [c for c in fake_imap.calls if c[0] == "uid" and c[1] == "FETCH"]
    assert fetches and all("BODY.PEEK[" in c[2][1] for c in fetches)
    commands = {c[1] for c in fake_imap.calls if c[0] == "uid"}
    assert commands == {"SEARCH", "FETCH"}
    search = next(c for c in fake_imap.calls if c[0] == "uid" and c[1] == "SEARCH")
    assert all("\r" not in a and "\n" not in a for a in search[2] if a)  # no command injection
    assert "app-pass-secret-123" not in caplog.text and "tester@example.org" not in caplog.text


def test_imap_refuses_non_peek_fetch(fake_imap):
    from tracker import imap_source
    conn = imap_source._connect()
    with pytest.raises(imap_source.ImapError):
        conn.uid_fetch("9", "(BODY[])")
    with pytest.raises(imap_source.ImapError):
        conn.uid_fetch("9", "(RFC822)")


def test_imported_email_goes_through_the_same_defenses(fake_imap):
    from tracker import imap_source, proposals
    from tracker.email_source import default_source
    imap_source.import_messages(["9"])
    p = proposals.create(tracker="budget", run_id="imap-t", email_id="imap-9", row_id="READ-02", field="spent_to_date",
                         amount=100, quote="We paid $100 for books.", rationale="t", source=default_source(),
                         selected_ids={"imap-9"})
    assert p["status"] == "pending"
    bad = proposals.create(tracker="budget", run_id="imap-t", email_id="imap-9", row_id="LIB-01", field="spent_to_date",
                           amount=100, quote="We paid $100 for books.", rationale="t", source=default_source(),
                           selected_ids={"imap-9"})
    assert "permission" in {b["defense"] for b in bad["blocks"]}
