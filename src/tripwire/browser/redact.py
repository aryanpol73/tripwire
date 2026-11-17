"""Scrub secrets and personal data before anything is written to disk (ETHICS rule 9).

Redaction is deliberately over-eager: losing a harmless value from a log costs little,
saving one real session cookie or password costs a lot.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"pass|pwd|token|csrf|xsrf|secret|session|sid$|auth|otp|card|cc[-_]?(num|exp)|cvv|cvc"
    r"|^pin$|pincode|upi|iban|ifsc|account|ssn|aadhaar|^pan$|api[-_]?key|signature|phone|email",
    re.IGNORECASE,
)
_SENSITIVE_HEADER = {
    "cookie",
    "set-cookie",
    "authorization",
    "proxy-authorization",
    "x-csrf-token",
    "x-xsrf-token",
    "x-api-key",
}
_EMAIL = re.compile(r"[^@\s&=]+@[^@\s&=]+\.[A-Za-z]{2,}")


def redact_value(key: str, value: str) -> str:
    """Redact one key/value pair if the key looks sensitive or the value is an email."""
    if _SENSITIVE_KEY.search(key) or _EMAIL.search(value):
        return REDACTED
    return value


def _redact_json(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: REDACTED if _SENSITIVE_KEY.search(str(k)) else _redact_json(v)
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_redact_json(v) for v in node]
    if isinstance(node, str) and _EMAIL.search(node):
        return REDACTED
    return node


def redact_post_data(body: str | None, content_type: str | None = None) -> str | None:
    if body is None:
        return None
    kind = (content_type or "").lower()
    if "json" in kind or body.lstrip().startswith(("{", "[")):
        try:
            return json.dumps(_redact_json(json.loads(body)), separators=(",", ":"))
        except ValueError:
            pass
    if "form-urlencoded" in kind or ("=" in body and body.isprintable() and " " not in body):
        pairs = parse_qsl(body, keep_blank_values=True)
        return urlencode([(k, redact_value(k, v)) for k, v in pairs], safe="[]")
    # Unknown format (multipart, binary, ...): record only its size, never its content.
    return f"{REDACTED}: {len(body)} characters of {content_type or 'unknown type'}"


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: REDACTED if k.lower() in _SENSITIVE_HEADER else v for k, v in headers.items()}


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode([(k, redact_value(k, v)) for k, v in pairs], safe="[]")
    return urlunsplit(parts._replace(query=query))


def _redact_har_message(message: dict) -> None:
    if "url" in message:
        message["url"] = redact_url(message["url"])
    for header in message.get("headers", []):
        if header.get("name", "").lower() in _SENSITIVE_HEADER:
            header["value"] = REDACTED
    message["cookies"] = []
    message.pop("queryString", None)
    post = message.get("postData")
    if post:
        post["text"] = redact_post_data(post.get("text"), post.get("mimeType"))
        for param in post.get("params", []):
            param["value"] = redact_value(param.get("name", ""), param.get("value", ""))


def redact_har(path: Path) -> None:
    """Scrub a HAR file in place. Playwright writes it unredacted when the context closes."""
    har = json.loads(path.read_text(encoding="utf-8"))
    for entry in har.get("log", {}).get("entries", []):
        _redact_har_message(entry.get("request", {}))
        _redact_har_message(entry.get("response", {}))
    path.write_text(json.dumps(har, indent=1), encoding="utf-8")
