"""
utils/validation.py – Payload schema validation for the webhook endpoint.

Validates that incoming JSON has all required fields with correct types.
"""

from datetime import datetime
from typing import Any


REQUIRED_FIELDS = {
    "domain": str,
    "headline": str,
    "content": str,
    "sources": list,
    "timestamp": str,
}

ALLOWED_DOMAINS = {
    "Technology", "Politics", "Economics", "Health", "Science",
    "Environment", "Energy", "Space", "Security", "Education",
    "Business", "General",
}


def validate_payload(data: Any) -> tuple[bool, str | None]:
    """
    Validate the webhook payload.

    Returns:
        (True, None)           – payload is valid
        (False, error_message) – payload is invalid
    """
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object."

    # Check required fields exist and have correct types
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            return False, f"Missing required field: '{field}'."
        if not isinstance(data[field], expected_type):
            return False, (
                f"Field '{field}' must be of type "
                f"{expected_type.__name__}, got {type(data[field]).__name__}."
            )

    # Non-empty string checks
    for field in ("domain", "headline", "content", "timestamp"):
        if not data[field].strip():
            return False, f"Field '{field}' must not be empty."

    # sources must be a non-empty list of strings
    if not data["sources"]:
        return False, "Field 'sources' must contain at least one entry."
    if not all(isinstance(s, str) for s in data["sources"]):
        return False, "All entries in 'sources' must be strings."

    # Validate ISO-8601 timestamp (basic check)
    try:
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    except ValueError:
        return False, "Field 'timestamp' must be a valid ISO-8601 datetime string."

    # Headline length sanity check
    if len(data["headline"]) > 500:
        return False, "Field 'headline' must not exceed 500 characters."

    # Content length sanity check
    if len(data["content"]) > 50_000:
        return False, "Field 'content' must not exceed 50,000 characters."

    return True, None
