"""Read-only business smoke check for an explicitly selected deployed application."""

import argparse
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request


def check(base, password):
    def request(opener, path, payload=None, csrf=None):
        headers = {"Origin": base}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = urllib.request.Request(
            base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
        )
        with opener.open(req, timeout=15) as response:
            return response.read()

    public = urllib.request.build_opener()
    assert json.loads(request(public, "/health"))["status"] == "ok", "Unhealthy database"
    assert json.loads(request(public, "/api/config"))["dev_routes_enabled"] is False, "Dev routes enabled"
    html = request(public, "/").decode()
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    assert assets, "Frontend assets missing"
    for asset in assets:
        assert request(public, asset), "Empty frontend asset"
    try:
        request(public, "/api/v1/courses")
    except urllib.error.HTTPError as error:
        assert error.code == 401, "Unexpected unauthenticated status"
    else:
        raise AssertionError("Courses exposed without login")

    for username, role in (("teacher", "teacher"), ("student01", "student")):
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        login = json.loads(request(opener, "/api/v1/auth/login", {
            "username": username, "password": password,
        }))
        me = json.loads(request(opener, "/api/v1/auth/me"))
        assert me["user"]["role"] == role, "Role mismatch"
        assert json.loads(request(opener, "/api/v1/courses"))["items"], "Seed course missing"
        request(opener, "/api/v1/auth/logout", {}, login["csrf_token"])
    print("Deployment smoke passed: health, frontend assets, access control, teacher/student login.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Application origin, for example http://127.0.0.1:8080")
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        parser.error("base-url must be an HTTP(S) origin without a path")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("base-url must not contain credentials, query or fragment")
    password = os.environ.get("DEPLOY_SEED_PASSWORD", "")
    if not password:
        parser.error("Set DEPLOY_SEED_PASSWORD locally; do not pass a password on the command line")
    try:
        check(args.base_url.rstrip("/"), password)
    except (AssertionError, OSError, ValueError, KeyError):
        # Avoid emitting HTTP request bodies, environment values, or credentials.
        raise SystemExit("Deployment smoke failed. Check service health, origin configuration and test account credentials.") from None


if __name__ == "__main__":
    main()
