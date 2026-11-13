from datetime import date

import pytest

from echoledger.approval_email import send_approval_email, send_approved_post_email
from echoledger.approval_tokens import verify_token
from echoledger.models import NewsSummary, Prediction


class _FakeSesClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs: object) -> None:
        self.sent.append(kwargs)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECHOLEDGER_APPROVAL_BASE_URL", "http://1.2.3.4:8080")
    monkeypatch.setenv("APPROVAL_SIGNING_KEY", "test-signing-key")
    monkeypatch.setenv("ECHOLEDGER_NOTIFY_EMAIL", "owner@example.com")
    monkeypatch.setenv("ECHOLEDGER_APPROVED_NOTIFY_EMAIL", "posts@example.com")


def test_sends_to_the_configured_recipient() -> None:
    client = _FakeSesClient()

    send_approval_email(date(1926, 11, 7), "A draft entry.", "pass", [], client=client)

    assert len(client.sent) == 1
    sent = client.sent[0]
    assert sent["Source"] == "owner@example.com"
    assert sent["Destination"] == {"ToAddresses": ["owner@example.com"]}


def test_body_contains_the_full_entry_text_and_verdict() -> None:
    client = _FakeSesClient()

    send_approval_email(date(1926, 11, 7), "A draft entry.", "pass", [], client=client)

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    assert "A draft entry." in body
    assert "pass" in body


def test_body_lists_any_violations() -> None:
    client = _FakeSesClient()

    send_approval_email(date(1926, 11, 7), "A draft entry.", "fail", ["mentions TV"], client=client)

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    assert "mentions TV" in body


def test_approve_and_reject_links_carry_valid_signed_tokens() -> None:
    client = _FakeSesClient()

    send_approval_email(date(1926, 11, 7), "A draft entry.", "pass", [], client=client)

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    approve_line = next(line for line in body.splitlines() if line.startswith("Approve:"))
    reject_line = next(line for line in body.splitlines() if line.startswith("Reject:"))

    approve_sig = approve_line.split("sig=")[1]
    reject_sig = reject_line.split("sig=")[1]
    assert verify_token("1926-11-07", "approve", approve_sig, "test-signing-key") is True
    assert verify_token("1926-11-07", "reject", reject_sig, "test-signing-key") is True
    # And a token for the wrong action should never verify, proving these
    # aren't interchangeable.
    assert verify_token("1926-11-07", "reject", approve_sig, "test-signing-key") is False


def _summary(text: str = "News today.") -> NewsSummary:
    return NewsSummary(
        headline_id="h1", date=date(2026, 11, 12), summary_text=text, model="claude-haiku-4-5"
    )


def test_approved_post_email_goes_to_the_approved_notify_address() -> None:
    client = _FakeSesClient()

    send_approved_post_email(
        date(1926, 11, 12),
        date(2026, 11, 12),
        "A diary entry.",
        [_summary()],
        "A Catchy Title",
        None,
        None,
        [],
        client=client,
    )

    assert len(client.sent) == 1
    sent = client.sent[0]
    assert sent["Source"] == "owner@example.com"
    assert sent["Destination"] == {"ToAddresses": ["posts@example.com"]}


def test_approved_post_email_subject_includes_both_dates() -> None:
    client = _FakeSesClient()

    send_approved_post_email(
        date(1926, 11, 12),
        date(2026, 11, 12),
        "A diary entry.",
        [],
        "A Catchy Title",
        None,
        None,
        [],
        client=client,
    )

    subject = client.sent[0]["Message"]["Subject"]["Data"]  # type: ignore[index]
    assert "2026-11-12" in subject
    assert "1926-11-12" in subject
    assert "approved for LinkedIn post" in subject


def test_approved_post_email_body_has_title_diary_and_news() -> None:
    client = _FakeSesClient()
    summaries = [_summary("Paraphrased news item.")]

    send_approved_post_email(
        date(1926, 11, 12),
        date(2026, 11, 12),
        "Arthur writes about the weather.",
        summaries,
        "A Catchy Title",
        None,
        None,
        [],
        client=client,
    )

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    assert "Article Title: A Catchy Title" in body
    assert "Arthur writes about the weather." in body
    assert "Paraphrased news item." in body


def test_approved_post_email_omits_echo_section_when_no_match() -> None:
    client = _FakeSesClient()

    send_approved_post_email(
        date(1926, 11, 12), date(2026, 11, 12), "Entry.", [], "Title", None, None, [], client=client
    )

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    assert "ECHO OF THE DAY" not in body


def test_approved_post_email_includes_echo_section_when_match_given() -> None:
    client = _FakeSesClient()

    send_approved_post_email(
        date(1926, 11, 12),
        date(2026, 11, 12),
        "Entry.",
        [],
        "Title",
        "Foreign ministers confer on government relations.",
        "US-mediated talks bring Russia and Ukraine to the table.",
        [],
        client=client,
    )

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    assert "ECHO OF THE DAY" in body
    assert "Foreign ministers confer on government relations." in body
    assert "US-mediated talks bring Russia and Ukraine to the table." in body


def test_approved_post_email_omits_predictions_section_when_none() -> None:
    client = _FakeSesClient()

    send_approved_post_email(
        date(1926, 11, 12), date(2026, 11, 12), "Entry.", [], "Title", None, None, [], client=client
    )

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    assert "PREDICTION" not in body


def test_approved_post_email_includes_predictions_when_given() -> None:
    client = _FakeSesClient()
    prediction = Prediction(
        id="pred-1",
        created_date=date(2026, 11, 12),
        resolution_date=date(2027, 3, 31),
        statement="A ceasefire will be signed",
        probability=0.25,
        forecaster="claude-haiku-4-5",
    )

    send_approved_post_email(
        date(1926, 11, 12),
        date(2026, 11, 12),
        "Entry.",
        [],
        "Title",
        None,
        None,
        [prediction],
        client=client,
    )

    body = client.sent[0]["Message"]["Body"]["Text"]["Data"]  # type: ignore[index]
    assert "TODAY'S PREDICTION" in body
    assert "A ceasefire will be signed by 2027-03-31" in body
    assert "25%" in body
