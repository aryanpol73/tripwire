"""Redaction: no cookies, tokens or passwords in anything we save (ETHICS rule 9)."""

import json

from tripwire.browser.redact import (
    REDACTED,
    redact_har,
    redact_headers,
    redact_post_data,
    redact_url,
)


def test_form_body_redacts_sensitive_fields_only():
    body = "email=walker%40example.test&csrf_token=abc123&password=hunter2&seats=2"
    out = redact_post_data(body, "application/x-www-form-urlencoded")
    assert "abc123" not in out and "hunter2" not in out
    assert "seats=2" in out
    assert "walker" not in out  # email addresses are personal data


def test_json_body_redacts_nested_keys():
    body = json.dumps({"user": {"token": "t0k", "name": "x"}, "items": [{"cvv": "123"}]})
    out = json.loads(redact_post_data(body, "application/json"))
    assert out["user"]["token"] == REDACTED
    assert out["user"]["name"] == "x"
    assert out["items"][0]["cvv"] == REDACTED


def test_unknown_body_format_is_not_saved_verbatim():
    out = redact_post_data("\x00binary\xffstuff", "application/octet-stream")
    assert "binary" not in out


def test_headers():
    out = redact_headers({"Cookie": "sid=1", "Authorization": "Bearer x", "Accept": "*/*"})
    assert out == {"Cookie": REDACTED, "Authorization": REDACTED, "Accept": "*/*"}


def test_url_query_tokens():
    out = redact_url("https://a.example/cb?session=abc&page=2")
    assert "abc" not in out and "page=2" in out


def test_har_file_is_scrubbed_in_place(tmp_path):
    har = {
        "log": {
            "entries": [
                {
                    "request": {
                        "url": "https://a.example/login?token=zzz",
                        "headers": [{"name": "Cookie", "value": "sid=secret"}],
                        "cookies": [{"name": "sid", "value": "secret"}],
                        "postData": {
                            "mimeType": "application/x-www-form-urlencoded",
                            "text": "password=hunter2",
                            "params": [{"name": "password", "value": "hunter2"}],
                        },
                    },
                    "response": {
                        "headers": [{"name": "Set-Cookie", "value": "sid=secret2"}],
                        "cookies": [{"name": "sid", "value": "secret2"}],
                    },
                }
            ]
        }
    }
    path = tmp_path / "run.har"
    path.write_text(json.dumps(har), encoding="utf-8")
    redact_har(path)
    text = path.read_text(encoding="utf-8")
    for secret in ("secret", "secret2", "hunter2", "zzz"):
        assert secret not in text


def test_boolean_capture_excludes_credentials_and_raw_contact_values():
    from tripwire.browser.redact import hidden_boolean_default

    assert hidden_boolean_default("contact_email_choice", "yes") is True
    assert hidden_boolean_default("contact_email_choice", "walker@example.test") is None
    assert hidden_boolean_default("email_auth_token", "1") is None
