from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from mujuthaek_extraction.publication_gate import PublicationGate


def notice(status):
    return {"eventId": "test-event", "eventType": "extraction.completed", "payload": {"reviewStatus": status}}


@pytest.mark.parametrize("status", ["AUTO_PASSED", "PARTIALLY_PASSED", "IN_REVIEW", "APPROVED"])
def test_initial_review_blocks_all_automatic_notices(status):
    assert PublicationGate("manual").allows(notice(status)) == (status == "APPROVED")


@pytest.mark.parametrize("status", ["AUTO_PASSED", "PARTIALLY_PASSED", "IN_REVIEW", "APPROVED"])
def test_verified_mode_rejects_partial_and_unverified_results(status):
    assert PublicationGate("verified").allows(notice(status)) == (status in {"AUTO_PASSED", "APPROVED"})


def test_benefit_requires_verification_or_explicit_human_review():
    event = {"eventType": "policy.extracted", "payload": {"quality": {"needsReview": False}}}
    assert not PublicationGate("manual").allows(event)
    assert PublicationGate("verified").allows(event)
    event["payload"]["quality"]["needsReview"] = True
    assert not PublicationGate("verified").allows(event)
    event["payload"]["quality"]["reviewed"] = True
    assert PublicationGate("manual").allows(event)
    assert not PublicationGate("verified").allows({"eventType": "unknown"})


def test_invalid_mode_fails_closed():
    with pytest.raises(ValueError):
        PublicationGate("verfied")


def test_held_result_is_preserved_without_outbox_publication(monkeypatch):
    publish = Mock()
    monkeypatch.setattr("mujuthaek_extraction.publication_gate.outbox.add", publish)
    cur = Mock()
    event = notice("AUTO_PASSED")
    assert not PublicationGate("manual").enqueue(cur, event, job_id="job-1")
    publish.assert_not_called()
    sql, params = cur.execute.call_args.args
    assert "publication_holds" in sql and params[2].obj == event and params[-1] == "job-1"


def test_release_only_sends_verified_records_and_updates_the_exact_job(monkeypatch):
    publish = Mock()
    monkeypatch.setattr("mujuthaek_extraction.publication_gate.outbox.add", publish)
    cur = Mock()
    cur.execute.return_value.fetchall.return_value = [("event-1", notice("AUTO_PASSED"), "job-1"), ("event-2", notice("PARTIALLY_PASSED"), "job-2")]
    conn = Mock()
    conn.transaction.return_value = nullcontext()
    conn.cursor.return_value = nullcontext(cur)
    assert PublicationGate("verified").release(conn) == 1
    publish.assert_called_once_with(cur, notice("AUTO_PASSED"))
    updates = [(args[0], args[1]) for args, _ in cur.execute.call_args_list if args[0].startswith("update ")]
    assert len(updates) == 2 and updates[-1][1] == ("event-1", "job-1")
    with pytest.raises(ValueError):
        PublicationGate("manual").release(conn)
