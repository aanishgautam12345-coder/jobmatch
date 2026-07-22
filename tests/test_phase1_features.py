"""Focused tests for password recovery and profile preference validation."""

import logging
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from jose import jwt

from app.api.auth import ForgotPasswordRequest, forgot_password
from app.config import get_settings
from app.core.security import create_access_token, verify_password
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.services.password_reset import (
    GENERIC_RESET_MESSAGE,
    InvalidResetTokenError,
    request_password_reset,
    reset_password,
)
from app.services.preferences import (
    validate_job_types,
    validate_notification_frequency,
    validate_notification_score,
)


class _Query:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class _Session:
    def __init__(self, user=None, blacklist=None):
        self.user = user
        self.blacklist = blacklist
        self.added = []
        self.commits = 0

    def query(self, model):
        return _Query(self.blacklist if model is TokenBlacklist else self.user)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1


def _user(active=True):
    return User(
        id=uuid.uuid4(), email="person@example.com",
        password_hash="unused", is_active=active,
    )


def test_forgot_response_is_identical_for_existing_and_unknown_email():
    with patch("app.services.password_reset.send_password_reset_email", return_value=True):
        existing = forgot_password.__wrapped__(None, ForgotPasswordRequest(email="person@example.com"), _Session(_user()))
        unknown = forgot_password.__wrapped__(None, ForgotPasswordRequest(email="unknown@example.com"), _Session())
    assert existing.message == unknown.message == GENERIC_RESET_MESSAGE


def test_reset_email_only_attempted_for_existing_account():
    with patch("app.services.password_reset.send_password_reset_email", return_value=True) as sender:
        request_password_reset(_Session(_user()), "person@example.com")
        request_password_reset(_Session(), "unknown@example.com")
    sender.assert_called_once()


def test_reset_token_is_not_logged(caplog):
    caplog.set_level(logging.INFO)
    with patch("app.services.password_reset.send_password_reset_email", return_value=True) as sender:
        request_password_reset(_Session(_user()), "person@example.com")
    reset_url = sender.call_args.args[1]
    token = reset_url.rsplit("/", 1)[-1]
    assert token not in caplog.text
    assert reset_url not in caplog.text


def test_smtp_failure_does_not_change_forgot_response():
    with patch("app.services.password_reset.send_password_reset_email", return_value=False):
        response = forgot_password.__wrapped__(None, ForgotPasswordRequest(email="person@example.com"), _Session(_user()))
    assert response.message == GENERIC_RESET_MESSAGE


def test_expired_reset_token_is_rejected():
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()), "purpose": "password_reset", "jti": str(uuid.uuid4()),
            "iat": datetime.utcnow() - timedelta(minutes=20),
            "exp": datetime.utcnow() - timedelta(minutes=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(InvalidResetTokenError):
        reset_password(_Session(_user()), token, "new-password")


def test_wrong_purpose_reset_token_is_rejected():
    token = create_access_token({"sub": str(uuid.uuid4())})
    with pytest.raises(InvalidResetTokenError):
        reset_password(_Session(_user()), token, "new-password")


def test_reused_reset_token_is_rejected():
    token = create_access_token({"sub": str(uuid.uuid4()), "purpose": "password_reset"}, 15)
    with pytest.raises(InvalidResetTokenError):
        reset_password(_Session(_user(), blacklist=object()), token, "new-password")


def test_valid_reset_changes_password_and_blacklists_token():
    user = _user()
    session = _Session(user)
    token = create_access_token({"sub": str(user.id), "purpose": "password_reset"}, 15)
    reset_password(session, token, "new-password")
    assert verify_password("new-password", user.password_hash)
    assert not verify_password("old-password", user.password_hash)
    assert session.commits == 1
    assert len(session.added) == 1


def test_job_types_are_canonical_and_unknown_values_rejected():
    assert validate_job_types(["Full-Time", "contract", "full-time"]) == ["full-time", "contract"]
    with pytest.raises(ValueError):
        validate_job_types(["permanent-ish"])


@pytest.mark.parametrize("score", [0.0, 1.0])
def test_notification_threshold_boundaries(score):
    assert validate_notification_score(score) == score


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_notification_threshold_out_of_range(score):
    with pytest.raises(ValueError):
        validate_notification_score(score)


def test_invalid_notification_frequency_rejected():
    assert validate_notification_frequency("Weekly") == "weekly"
    with pytest.raises(ValueError):
        validate_notification_frequency("hourly")


def test_flask_csrf_is_enabled_by_default():
    with patch("webapp.app.init_db"):
        from webapp.app import create_app
        app = create_app()
    assert app.config["WTF_CSRF_ENABLED"] is True
