import json
import os

import pytest

from echoledger.config import _load_secrets_from_aws

_TEST_ARN = "arn:aws:secretsmanager:ap-southeast-2:529470780389:secret:echoledger/api-keys"


class _FakeSecretsClient:
    def __init__(self, secret: dict[str, str]) -> None:
        self._secret = secret

    def get_secret_value(self, SecretId: str) -> dict[str, str]:
        assert SecretId == _TEST_ARN
        return {"SecretString": json.dumps(self._secret)}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHOLEDGER_SECRETS_ARN", raising=False)
    monkeypatch.delenv("SOME_TEST_SECRET_KEY", raising=False)


def test_does_nothing_when_no_secrets_arn_set() -> None:
    _load_secrets_from_aws(client=_FakeSecretsClient({"SOME_TEST_SECRET_KEY": "fetched"}))

    assert "SOME_TEST_SECRET_KEY" not in os.environ


def test_populates_env_from_secret_when_arn_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECHOLEDGER_SECRETS_ARN", _TEST_ARN)

    _load_secrets_from_aws(client=_FakeSecretsClient({"SOME_TEST_SECRET_KEY": "fetched"}))

    assert os.environ["SOME_TEST_SECRET_KEY"] == "fetched"


def test_does_not_override_an_already_set_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECHOLEDGER_SECRETS_ARN", _TEST_ARN)
    monkeypatch.setenv("SOME_TEST_SECRET_KEY", "already-set-locally")

    _load_secrets_from_aws(client=_FakeSecretsClient({"SOME_TEST_SECRET_KEY": "fetched"}))

    assert os.environ["SOME_TEST_SECRET_KEY"] == "already-set-locally"
