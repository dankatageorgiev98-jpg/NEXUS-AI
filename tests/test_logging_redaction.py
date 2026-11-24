import core.activity_logger as activity_logger
from core.activity_logger import ActivityLogger, redact_sensitive_text


FAKE_URL_PASSWORD = "fake-url-password"
FAKE_QUERY_SECRET = "fake-query-api-key"
FAKE_BEARER = "fake.bearer.token"
FAKE_AUTH = "fake-auth-header-value"
FAKE_API_KEY = "fake-api-key-value"
FAKE_SECRET = "fake-secret-value"
FAKE_PRIVATE_KEY = "0123456789abcdef" * 4
FAKE_SEED_PHRASE = " ".join(
    f"fakeword{index}" for index in range(12)
)


def test_url_username_and_password_are_redacted():
    text = (
        "https://fake-user:"
        f"{FAKE_URL_PASSWORD}@rpc.example.test/health"
    )

    redacted = redact_sensitive_text(text)

    assert "fake-user" not in redacted
    assert FAKE_URL_PASSWORD not in redacted
    assert "rpc.example.test/health" in redacted
    assert "[REDACTED]" in redacted


def test_sensitive_url_query_parameter_is_redacted():
    text = (
        "https://rpc.example.test/health"
        f"?api_key={FAKE_QUERY_SECRET}&mode=test"
    )

    redacted = redact_sensitive_text(text)

    assert FAKE_QUERY_SECRET not in redacted
    assert "mode=test" in redacted
    assert "[REDACTED]" in redacted


def test_bearer_token_is_redacted():
    redacted = redact_sensitive_text(
        f"Request failed: Bearer {FAKE_BEARER}"
    )

    assert FAKE_BEARER not in redacted
    assert "Bearer [REDACTED]" in redacted


def test_authorization_header_is_redacted():
    redacted = redact_sensitive_text(
        f"Authorization: Bearer {FAKE_AUTH}"
    )

    assert FAKE_AUTH not in redacted
    assert "Authorization: [REDACTED]" in redacted


def test_api_key_and_secret_fields_are_redacted_case_insensitively():
    text = (
        f'API_KEY="{FAKE_API_KEY}" '
        f'SeCrEt={FAKE_SECRET}'
    )

    redacted = redact_sensitive_text(text)

    assert FAKE_API_KEY not in redacted
    assert FAKE_SECRET not in redacted
    assert "[REDACTED]" in redacted


def test_private_key_field_and_pem_block_are_redacted():
    field_text = redact_sensitive_text(
        f"private_key={FAKE_PRIVATE_KEY}"
    )
    pem_text = (
        "-----BEGIN PRIVATE KEY-----\n"
        "fakepemprivatekeyvalue\n"
        "-----END PRIVATE KEY-----"
    )

    redacted_pem = redact_sensitive_text(pem_text)

    assert FAKE_PRIVATE_KEY not in field_text
    assert "fakepemprivatekeyvalue" not in redacted_pem
    assert "[REDACTED]" in field_text
    assert "[REDACTED PRIVATE KEY]" in redacted_pem


def test_seed_phrase_and_mnemonic_are_redacted():
    seed_text = redact_sensitive_text(
        f"seed_phrase: {FAKE_SEED_PHRASE}"
    )
    mnemonic_text = redact_sensitive_text(
        f"mnemonic={FAKE_SEED_PHRASE}"
    )

    assert FAKE_SEED_PHRASE not in seed_text
    assert FAKE_SEED_PHRASE not in mnemonic_text
    assert "[REDACTED]" in seed_text
    assert "[REDACTED]" in mnemonic_text


def test_multiline_mixed_case_input_is_redacted():
    text = (
        "RPC request failed\n"
        f"Authorization: Bearer {FAKE_AUTH}\n"
        f"access_Token={FAKE_API_KEY}\n"
        "Diagnostic: retry after 429"
    )

    redacted = redact_sensitive_text(text)

    assert FAKE_AUTH not in redacted
    assert FAKE_API_KEY not in redacted
    assert "RPC request failed" in redacted
    assert "retry after 429" in redacted
    assert "[REDACTED]" in redacted


def test_harmless_diagnostic_text_is_preserved():
    text = "HTTP 429 rate limit; timeout=20 seconds"

    redacted = redact_sensitive_text(text)

    assert redacted == text


def test_original_fake_secret_does_not_appear_in_logger_output(monkeypatch):
    captured = {}

    def capture_error(message):
        captured["message"] = message

    monkeypatch.setattr(
        activity_logger._LOGGER,
        "error",
        capture_error,
    )

    ActivityLogger.error(
        f"API_KEY={FAKE_API_KEY}; retrying after HTTP 429"
    )

    assert FAKE_API_KEY not in captured["message"]
    assert "retrying after HTTP 429" in captured["message"]
