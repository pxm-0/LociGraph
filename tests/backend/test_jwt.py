from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from jwt import InvalidTokenError

from backend.app.auth.jwt import create_token, decode_token

SECRET = "test-secret"


def test_roundtrip():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = create_token("user-123", SECRET, now=now)
    # Mock datetime.now() to return the token creation time for validation
    with patch("jwt.api_jwt.datetime") as mock_datetime_module:
        mock_datetime_module.now.return_value = now
        mock_datetime_module.timezone.utc = UTC
        assert decode_token(token, SECRET) == "user-123"


def test_expired_token_rejected():
    past = datetime(2020, 1, 1, tzinfo=UTC)
    token = create_token("u", SECRET, now=past, ttl_days=1)
    with pytest.raises(InvalidTokenError):
        decode_token(token, SECRET)


def test_wrong_secret_rejected():
    token = create_token("u", SECRET, now=datetime.now(UTC))
    with pytest.raises(InvalidTokenError):
        decode_token(token, "other-secret")
