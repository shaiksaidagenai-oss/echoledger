from echoledger.approval_tokens import make_token, verify_token


def test_a_valid_token_verifies() -> None:
    token = make_token("1926-11-07", "approve", signing_key="secret")

    assert verify_token("1926-11-07", "approve", token, signing_key="secret") is True


def test_wrong_signing_key_fails() -> None:
    token = make_token("1926-11-07", "approve", signing_key="secret")

    assert verify_token("1926-11-07", "approve", token, signing_key="different") is False


def test_tampering_with_the_date_fails() -> None:
    token = make_token("1926-11-07", "approve", signing_key="secret")

    assert verify_token("1926-11-08", "approve", token, signing_key="secret") is False


def test_tampering_with_the_action_fails() -> None:
    token = make_token("1926-11-07", "approve", signing_key="secret")

    assert verify_token("1926-11-07", "reject", token, signing_key="secret") is False


def test_an_invalid_action_never_verifies_even_with_a_matching_token() -> None:
    token = make_token("1926-11-07", "publish", signing_key="secret")

    assert verify_token("1926-11-07", "publish", token, signing_key="secret") is False
