"""
test_webhook.py – Automated tests for the POST /webhook/update endpoint.

Run AFTER starting the Flask server:
    python app.py          (Terminal 1)
    python test_webhook.py (Terminal 2)
"""

import json
import sys
import uuid
import requests

BASE_URL      = "http://localhost:5000"
ENDPOINT      = f"{BASE_URL}/webhook/update"
VALID_TOKEN   = "cin-webhook-secret-2026-change-me-in-production"  # must match .env
WRONG_TOKEN   = "this-is-wrong"

# Unique headline per run so re-runs don't hit the duplicate guard
_RUN_ID = str(uuid.uuid4())[:8]

VALID_PAYLOAD = {
    "domain":    "Technology",
    "headline":  f"New AI chip released by leading semiconductor company [{_RUN_ID}]",
    "content":   (
        "A major semiconductor company has unveiled a new AI accelerator chip "
        "that promises 3x performance improvements over previous generations. "
        "The chip uses a novel architecture optimised for transformer-based models "
        "and is expected to ship to data centres in Q3 2026."
    ),
    "sources":   ["https://example.com/ai-chip-news"],
    "timestamp": "2026-02-18T17:00:00+00:00",
}

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    print(f"  {status}  {name}")
    if detail:
        print(f"         {detail}")
    results.append(condition)


def run_tests():
    print("\n" + "=" * 60)
    print("  CIN Webhook – Automated Security & Validation Tests")
    print("=" * 60 + "\n")

    # ── Test 1: Missing token ─────────────────────────────────────────────────
    print("Test 1: Missing X-Webhook-Token header")
    r = requests.post(ENDPOINT, json=VALID_PAYLOAD)
    check("Returns HTTP 401", r.status_code == 401, f"Got {r.status_code}")
    check("Error message present", "message" in r.json())

    # ── Test 2: Wrong token ───────────────────────────────────────────────────
    print("\nTest 2: Wrong X-Webhook-Token value")
    r = requests.post(ENDPOINT, json=VALID_PAYLOAD,
                      headers={"X-Webhook-Token": WRONG_TOKEN})
    check("Returns HTTP 401", r.status_code == 401, f"Got {r.status_code}")

    # ── Test 3: Non-JSON body ─────────────────────────────────────────────────
    print("\nTest 3: Non-JSON body (plain text)")
    r = requests.post(ENDPOINT, data="not json",
                      headers={"X-Webhook-Token": VALID_TOKEN,
                               "Content-Type": "text/plain"})
    check("Returns HTTP 400", r.status_code == 400, f"Got {r.status_code}")

    # ── Test 4: Missing required field ────────────────────────────────────────
    print("\nTest 4: Missing 'headline' field")
    bad_payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "headline"}
    r = requests.post(ENDPOINT, json=bad_payload,
                      headers={"X-Webhook-Token": VALID_TOKEN})
    check("Returns HTTP 400", r.status_code == 400, f"Got {r.status_code}")
    check("Error mentions 'headline'", "headline" in r.text.lower())

    # ── Test 5: Invalid timestamp ─────────────────────────────────────────────
    print("\nTest 5: Invalid timestamp format")
    bad_ts = dict(VALID_PAYLOAD, timestamp="not-a-date")
    r = requests.post(ENDPOINT, json=bad_ts,
                      headers={"X-Webhook-Token": VALID_TOKEN})
    check("Returns HTTP 400", r.status_code == 400, f"Got {r.status_code}")

    # ── Test 6: Valid payload ─────────────────────────────────────────────────
    print("\nTest 6: Valid payload with correct token")
    r = requests.post(ENDPOINT, json=VALID_PAYLOAD,
                      headers={"X-Webhook-Token": VALID_TOKEN})
    check("Returns HTTP 202", r.status_code == 202, f"Got {r.status_code}")
    body = r.json()
    check("Status is 'queued'", body.get("status") == "queued",
          f"Got status={body.get('status')}")
    check("post_id is present", bool(body.get("post_id")))

    # ── Test 7: Duplicate headline ────────────────────────────────────────────
    print("\nTest 7: Duplicate headline (same payload sent again)")
    import time; time.sleep(1)   # let the first request register
    r = requests.post(ENDPOINT, json=VALID_PAYLOAD,
                      headers={"X-Webhook-Token": VALID_TOKEN})
    check("Returns HTTP 200", r.status_code == 200, f"Got {r.status_code}")
    check("Status is 'duplicate'", r.json().get("status") == "duplicate",
          f"Got status={r.json().get('status')}")

    # ── Test 8: Empty sources list ────────────────────────────────────────────
    print("\nTest 8: Empty sources list")
    bad_sources = dict(VALID_PAYLOAD, sources=[])
    r = requests.post(ENDPOINT, json=bad_sources,
                      headers={"X-Webhook-Token": VALID_TOKEN})
    check("Returns HTTP 400", r.status_code == 400, f"Got {r.status_code}")

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print("\n" + "=" * 60)
    print(f"  Results: {passed}/{total} checks passed")
    print("=" * 60 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    try:
        requests.get(BASE_URL, timeout=3)
    except requests.exceptions.ConnectionError:
        print(f"\n\033[91mERROR: Cannot connect to {BASE_URL}\033[0m")
        print("Please start the Flask server first:  python app.py\n")
        sys.exit(1)

    run_tests()
