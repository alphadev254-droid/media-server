"""
Media Server API Test Script
Tests all endpoints: health, upload, signed URL, delete, and metrics.

Usage:
    python test_api.py                      # Test against localhost:3010
    python test_api.py --host https://media.yourdomain.com   # Test against remote
    python test_api.py --host https://media.yourdomain.com --image "C:/path/to/image.jpg"
"""

import argparse
import httpx
import json
import sys
import os
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────────
DEFAULT_HOST = "http://127.0.0.1:3010"
DEFAULT_IMAGE = Path(__file__).parent / "bedsitter 2.jpg"
DEFAULT_API_KEY = "changeme"
DEFAULT_METRICS_TOKEN = "changeme"
DEFAULT_CLIENT_ID = "your-app-name"
DEFAULT_MEDIA_BASE_URL = "https://media.yourdomain.com"

# ── HELPERS ─────────────────────────────────────────────────────────────────
PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  {PASS} {name}")
        passed += 1
    else:
        print(f"  {FAIL} {name}  \033[90m{detail}\033[0m")
        failed += 1


def summary():
    total = passed + failed
    print(f"\n{'=' * 50}")
    print(f"  Results: {PASS} {passed}/{total}  |  {FAIL} {failed}/{total}")
    print(f"{'=' * 50}")
    return 0 if failed == 0 else 1


# ── TESTS ───────────────────────────────────────────────────────────────────
def test_health(client, host):
    print(f"\n{INFO} Health Check")
    r = client.get(f"{host}/health", timeout=10)
    test("GET /health returns 200", r.status_code == 200, f"got {r.status_code}")
    data = r.json()
    test("Response has status=ok", data.get("status") == "ok", str(data))


def test_upload(client, host, image_path, api_key):
    print(f"\n{INFO} Upload File — POST /upload/")

    # Test 1: Missing required headers
    r = client.post(f"{host}/upload/", timeout=10)
    test("Missing API key - 403", r.status_code == 403, f"got {r.status_code}")

    # Test 2: With API key but missing X-Media-Base-Url (422 because Header(...) is required)
    r = client.post(
        f"{host}/upload/",
        headers={"X-API-Key": api_key, "X-Client-Id": DEFAULT_CLIENT_ID},
        timeout=10,
    )
    test("Missing X-Media-Base-Url - 422", r.status_code == 422, f"got {r.status_code}")

    # Test 3: Invalid media base URL (422 because Header(...) requires value, empty/invalid triggers 422 first)
    r = client.post(
        f"{host}/upload/",
        headers={
            "X-API-Key": api_key,
            "X-Client-Id": DEFAULT_CLIENT_ID,
            "X-Media-Base-Url": "https://evil.com",
        },
        timeout=10,
    )
    test("Invalid X-Media-Base-Url rejected", r.status_code in (403, 422), f"got {r.status_code}")

    # Test 4: Successful image upload
    if not os.path.exists(image_path):
        print(f"  {FAIL} Image not found at: {image_path}")
        return None

    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f, "image/jpeg")}
        r = client.post(
            f"{host}/upload/",
            headers={
                "X-API-Key": api_key,
                "X-Client-Id": DEFAULT_CLIENT_ID,
                "X-Media-Base-Url": DEFAULT_MEDIA_BASE_URL,
            },
            files=files,
            timeout=30,
        )

    test("Upload returns 200", r.status_code == 200, f"got {r.status_code}")

    if r.status_code == 200:
        data = r.json()
        required_fields = ["id", "bucket", "url", "size", "mime"]
        for field in required_fields:
            test(f"Response has '{field}'", field in data, str(data))
        test("URL starts with media base URL", data.get("url", "").startswith(DEFAULT_MEDIA_BASE_URL), data["url"])
        test("MIME is image/webp (auto-converted)", data.get("mime") == "image/webp", data.get("mime"))
        test("Bucket is media-images", data.get("bucket") == "media-images", data.get("bucket"))
        print(f"    URL: {data['url']}")
        print(f"    Size: {data['size']} bytes")
        return data
    else:
        print(f"    Body: {r.text[:200]}")
        return None


def test_uploaded_file_accessible(client, upload_result):
    print(f"\n{INFO} Access Uploaded File (Public URL)")

    if not upload_result:
        print("  [SKIP] No upload result")
        return None

    url = upload_result["url"]
    r = client.get(url, timeout=30, follow_redirects=True)
    test(f"GET {os.path.basename(url)} accessible", r.status_code < 500, f"got {r.status_code}")
    if r.status_code == 200:
        test("Content-Type is image", "image" in (r.headers.get("content-type", "")), r.headers.get("content-type"))
    return upload_result


def test_signed_url(client, host, api_key):
    print(f"\n{INFO} Signed URL — GET /media/signed/")

    # Test: Missing API key
    r = client.get(f"{host}/media/signed/media-videos/test.mp4", timeout=10)
    test("Missing API key - 403", r.status_code == 403, f"got {r.status_code}")

    # Test: Valid request (file may not exist, but endpoint should return a URL)
    r = client.get(
        f"{host}/media/signed/media-videos/test.mp4?expires=3600",
        headers={"X-API-Key": api_key},
        timeout=10,
    )
    test("Signed URL endpoint responds", r.status_code in (200, 404, 403), f"got {r.status_code}")

    if r.status_code == 200:
        data = r.json()
        test("Response has 'url' field", "url" in data, str(data))
        test("Response has 'expires_in' field", "expires_in" in data, str(data))
        test("URL is a signed MinIO URL", "AWSAccessKeyId=" in data.get("url", "") or "X-Amz-Signature" in data.get("url", ""), data["url"][:100])
        print(f"    Signed URL (truncated): {data['url'][:100]}...")
    else:
        print(f"    Body: {r.text[:200]}")


def test_delete(client, host, api_key, upload_result):
    print(f"\n{INFO} Delete File — DELETE /upload/{{bucket}}/{{key}}")

    if not upload_result:
        print("  [SKIP] No file to delete")
        return

    bucket = upload_result["bucket"]
    key = upload_result["id"]

    # Test: Missing API key
    r = client.delete(f"{host}/upload/{bucket}/{key}", timeout=10)
    test("Missing API key - 403", r.status_code == 403, f"got {r.status_code}")

    # Test: Successful delete
    r = client.delete(
        f"{host}/upload/{bucket}/{key}",
        headers={"X-API-Key": api_key},
        timeout=10,
    )
    test("Delete returns 200", r.status_code == 200, f"got {r.status_code}")

    if r.status_code == 200:
        data = r.json()
        test("Response has deleted=true", data.get("deleted") is True, str(data))

    # Test: Delete again (should still work — idempotent)
    r = client.delete(
        f"{host}/upload/{bucket}/{key}",
        headers={"X-API-Key": api_key},
        timeout=10,
    )
    test("Delete already-deleted file returns 200", r.status_code == 200, f"got {r.status_code}")


def test_metrics(client, host):
    print(f"\n{INFO} Metrics — GET /metrics")

    # Test: Missing token (422 because Header(...) requires it)
    r = client.get(f"{host}/metrics", timeout=10)
    test("Missing X-Metrics-Token rejected", r.status_code in (403, 422), f"got {r.status_code}")

    # Test: Invalid token
    r = client.get(
        f"{host}/metrics",
        headers={"X-Metrics-Token": "wrong_token"},
        timeout=10,
    )
    test("Invalid token - 403", r.status_code == 403, f"got {r.status_code}")

    # Test: Valid token
    r = client.get(
        f"{host}/metrics",
        headers={"X-Metrics-Token": DEFAULT_METRICS_TOKEN},
        timeout=10,
    )
    test("Valid token - 200", r.status_code == 200, f"got {r.status_code}")

    if r.status_code == 200:
        test("Response is Prometheus format", "# HELP" in r.text or "# TYPE" in r.text, r.text[:100])
        print(f"    Metrics size: {len(r.text)} bytes")


def test_cors_preflight(client, host):
    print(f"\n{INFO} CORS Preflight - OPTIONS /upload/")

    # Test: Allowed origin
    r = client.options(
        f"{host}/upload/",
        headers={
            "Origin": "https://yourdomain.com",
            "Access-Control-Request-Method": "POST",
        },
        timeout=10,
    )
    test("Allowed origin - CORS headers present", r.status_code in (200, 204), f"got {r.status_code}")
    allow_origin = r.headers.get("access-control-allow-origin", "")
    test("Access-Control-Allow-Origin matches", allow_origin == "https://yourdomain.com", allow_origin)

    # Test: Disallowed origin
    r = client.options(
        f"{host}/upload/",
        headers={
            "Origin": "https://evil-site.com",
            "Access-Control-Request-Method": "POST",
        },
        timeout=10,
    )
    test("Disallowed origin - 400", r.status_code == 400, f"got {r.status_code}")
    test("Disallowed origin message", "Disallowed CORS" in r.text, r.text[:100])


# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Test Media Server API")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Server URL (default: {DEFAULT_HOST})")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help=f"Path to test image (default: {DEFAULT_IMAGE})")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--metrics-token", default=DEFAULT_METRICS_TOKEN, help="Metrics token")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    image_path = args.image

    print(f"{'=' * 50}")
    print(f"  Media Server API Test Suite")
    print(f"{'=' * 50}")
    print(f"  Host:        {host}")
    print(f"  Image:       {image_path}")
    print(f"  API Key:     {args.api_key[:8]}...{args.api_key[-4:]}")
    print(f"  Metrics:     {args.metrics_token[:8]}...{args.metrics_token[-4:]}")
    print(f"{'=' * 50}")

    client = httpx.Client(verify=False)  # noqa for testing

    # Run tests
    test_health(client, host)
    test_cors_preflight(client, host)
    upload_result = test_upload(client, host, image_path, args.api_key)
    test_uploaded_file_accessible(client, upload_result)
    test_signed_url(client, host, args.api_key)
    test_metrics(client, host)
    test_delete(client, host, args.api_key, upload_result)

    return summary()


if __name__ == "__main__":
    sys.exit(main())
