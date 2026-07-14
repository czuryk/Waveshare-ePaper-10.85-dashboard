#!/usr/bin/env python3
"""
Direct ChatGPT/Codex subscription limits monitor
================================================

Single-purpose script for a VPS / e-ink dashboard.

Behavior:
  - Always runs with no command-line parameters.
  - Requires ./auth.json next to this script.
  - Does NOT start browser login.
  - Does NOT require or start Codex CLI.
  - Uses the access_token from auth.json to call the undocumented usage endpoint.
  - Refreshes/rotates tokens with refresh_token when the access token is near expiry
    or when the usage endpoint returns 401/403.
  - Writes ./usage.json every 60 seconds in the Claude-compatible shape:
      {
        "updated_at": "...",
        "five_hour": {"utilization": 0.0, "resets_at": "..."},
        "seven_day": {"utilization": 0.0, "resets_at": "..."}
      }
  - Prints status messages in English.

Requirements:
  pip install requests

Important:
  auth.json is a secret. It contains access and refresh tokens.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests


# ── Configuration ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
AUTH_FILE = SCRIPT_DIR / "auth.json"
# Separate output file: claude.py already owns usage.json, so writing there too
# would make the two monitors overwrite each other's data.
USAGE_FILE = SCRIPT_DIR / "codex_usage.json"
LOG_FILE = SCRIPT_DIR / "monitor.log"

POLL_INTERVAL_SEC = 60
HTTP_TIMEOUT_SEC = 20
REFRESH_BUFFER_SEC = 600  # refresh 10 minutes before access token expiry

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"

USER_AGENT = "limits-new5/1.0"
# ───────────────────────────────────────────────────────────────────────────


class FatalError(RuntimeError):
    pass


# ── Logging / file helpers ─────────────────────────────────────────────────
def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def log(msg: str) -> None:
    print(f"{iso_now()} {msg}", flush=True)


def log_error(msg: str) -> None:
    print(f"{iso_now()} ERROR: {msg}", file=sys.stderr, flush=True)


def append_log(msg: str) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{iso_now()} {msg}\n")
    except Exception:
        pass


def write_json(path: Path, data: Any) -> None:
    """Write JSON the same simple way as the working Claude monitor does."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_usage_error(reason: str) -> None:
    payload = {
        "updated_at": iso_now(),
        "five_hour": {"utilization": -1.0, "resets_at": None},
        "seven_day": {"utilization": -1.0, "resets_at": None},
    }
    write_json(USAGE_FILE, payload)
    append_log(f"ERROR: {reason}")
    log_error(f"Could not update limits: {reason}")


# ── auth.json helpers ──────────────────────────────────────────────────────
def load_auth() -> dict[str, Any]:
    if not AUTH_FILE.exists():
        raise FatalError(f"auth.json was not found next to the script: {AUTH_FILE}")
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FatalError(f"auth.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FatalError("auth.json root must be a JSON object")
    return data


def save_auth(data: dict[str, Any]) -> None:
    write_json(AUTH_FILE, data)


def get_tokens(auth: dict[str, Any]) -> dict[str, Any]:
    tokens = auth.get("tokens")
    if isinstance(tokens, dict):
        return tokens
    # Some tools may store fields at top level. Keep it permissive.
    return auth


def get_token_value(auth: dict[str, Any], *names: str) -> Optional[str]:
    tokens = get_tokens(auth)
    for name in names:
        value = tokens.get(name)
        if isinstance(value, str) and value:
            return value
        value = auth.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def set_token_value(auth: dict[str, Any], name: str, value: Any) -> None:
    tokens = auth.setdefault("tokens", {})
    if isinstance(tokens, dict):
        tokens[name] = value
    else:
        auth[name] = value


def base64url_decode(segment: str) -> bytes:
    segment += "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment.encode("ascii"))


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    try:
        return json.loads(base64url_decode(parts[1]).decode("utf-8"))
    except Exception:
        return {}


def access_token_expiry_epoch(auth: dict[str, Any]) -> Optional[float]:
    tokens = get_tokens(auth)

    # Prefer explicit fields if present.
    for key in ("expires_at", "expiresAt", "access_token_expires_at", "accessTokenExpiresAt"):
        value = tokens.get(key, auth.get(key))
        if isinstance(value, (int, float)):
            # Accept seconds or milliseconds.
            if value > 10_000_000_000:
                return float(value) / 1000.0
            return float(value)
        if isinstance(value, str):
            with contextlib.suppress(Exception):
                parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.timestamp()
            with contextlib.suppress(Exception):
                return float(value)

    access_token = get_token_value(auth, "access_token", "accessToken")
    if not access_token:
        return None
    payload = decode_jwt_payload(access_token)
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        return float(exp)
    return None


def token_needs_refresh(auth: dict[str, Any]) -> bool:
    exp = access_token_expiry_epoch(auth)
    if exp is None:
        # Unknown expiry: try current token first; refresh only on 401/403.
        return False
    return time.time() >= (exp - REFRESH_BUFFER_SEC)


def require_token(auth: dict[str, Any], *names: str) -> str:
    value = get_token_value(auth, *names)
    if not value:
        raise FatalError(f"auth.json is missing required token field: {'/'.join(names)}")
    return value


def get_account_id(auth: dict[str, Any]) -> Optional[str]:
    # Common Codex auth.json field.
    account_id = get_token_value(auth, "account_id", "accountId", "chatgpt_account_id", "chatgptAccountId")
    if account_id:
        return account_id

    # Fallback: some JWTs contain an account id claim. This is intentionally broad.
    for token_name in ("access_token", "id_token"):
        token = get_token_value(auth, token_name, token_name.replace("_", ""))
        if not token:
            continue
        payload = decode_jwt_payload(token)
        for key in ("account_id", "accountId", "https://api.openai.com/account_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return None


# ── OAuth refresh ──────────────────────────────────────────────────────────
def refresh_tokens(auth: dict[str, Any]) -> dict[str, Any]:
    refresh_token = require_token(auth, "refresh_token", "refreshToken")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    }
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }

    log("Refreshing access token...")
    try:
        resp = requests.post(TOKEN_URL, headers=headers, data=data, timeout=HTTP_TIMEOUT_SEC)
    except requests.RequestException as exc:
        raise FatalError(f"token refresh network error: {exc}") from exc

    if resp.status_code != 200:
        body = resp.text[:1000]
        raise FatalError(f"token refresh failed: HTTP {resp.status_code}: {body}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise FatalError(f"token refresh returned non-JSON response: {resp.text[:500]}") from exc

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise FatalError("token refresh response did not include access_token")

    set_token_value(auth, "access_token", access_token)
    # Refresh token rotation: replace it if the server returns a new one.
    if isinstance(payload.get("refresh_token"), str) and payload["refresh_token"]:
        set_token_value(auth, "refresh_token", payload["refresh_token"])
    if isinstance(payload.get("id_token"), str) and payload["id_token"]:
        set_token_value(auth, "id_token", payload["id_token"])
    if isinstance(payload.get("scope"), str):
        set_token_value(auth, "scope", payload["scope"])
    if isinstance(payload.get("token_type"), str):
        set_token_value(auth, "token_type", payload["token_type"])
    if isinstance(payload.get("expires_in"), (int, float)):
        set_token_value(auth, "expires_at", int(time.time() + float(payload["expires_in"])))

    auth["last_refresh"] = iso_now()
    save_auth(auth)
    log("Access token refreshed and auth.json updated.")
    return auth


# ── Usage endpoint ─────────────────────────────────────────────────────────
def usage_headers(auth: dict[str, Any]) -> dict[str, str]:
    access_token = require_token(auth, "access_token", "accessToken")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    account_id = get_account_id(auth)
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def fetch_usage(auth: dict[str, Any]) -> dict[str, Any]:
    try:
        resp = requests.get(USAGE_URL, headers=usage_headers(auth), timeout=HTTP_TIMEOUT_SEC)
    except requests.RequestException as exc:
        raise FatalError(f"usage request network error: {exc}") from exc

    if resp.status_code in (401, 403):
        raise PermissionError(f"usage request unauthorized: HTTP {resp.status_code}: {resp.text[:500]}")
    if resp.status_code == 429:
        raise FatalError(f"usage request rate limited: HTTP 429: {resp.text[:500]}")
    if resp.status_code != 200:
        raise FatalError(f"usage request failed: HTTP {resp.status_code}: {resp.text[:1000]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise FatalError(f"usage endpoint returned non-JSON response: {resp.text[:500]}") from exc
    if not isinstance(data, dict):
        raise FatalError("usage endpoint returned unexpected JSON shape")
    return data


# ── Response parsing ───────────────────────────────────────────────────────
def unix_to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Already ISO-like; normalize Z when possible, otherwise preserve.
        with contextlib.suppress(Exception):
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).isoformat()
        with contextlib.suppress(Exception):
            value = float(text)
        if isinstance(value, str):
            return text
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts /= 1000.0
        with contextlib.suppress(Exception):
            return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()
    return None


def as_percent(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        v = float(value)
    except Exception:
        return 0.0
    # Some APIs use 0..1; WHAM/Codex examples usually use 0..100.
    if 0.0 <= v <= 1.0:
        return round(v * 100.0, 4)
    return round(v, 4)


def dict_get_any(d: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in d:
            return d[name]
    return None


def find_first_key(obj: Any, names: tuple[str, ...]) -> Optional[Any]:
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]
        for value in obj.values():
            found = find_first_key(value, names)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_first_key(value, names)
            if found is not None:
                return found
    return None


def clamp_percent(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 4)


def percent_from_fraction_or_percent(value: Any) -> Optional[float]:
    """Convert an ambiguous percentage value.

    Use this only for fields that are known to sometimes be fractions, such as
    percent_left / remaining_percent. Do NOT use it for WHAM used_percent,
    because WHAM uses 0..100 there and used_percent=1 means 1%, not 100%.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if 0.0 <= v < 1.0:
        return clamp_percent(v * 100.0)
    return clamp_percent(v)


def percent_direct(value: Any) -> Optional[float]:
    """Read a normal 0..100 percent value exactly as returned by WHAM."""
    if value is None:
        return None
    try:
        return clamp_percent(float(value))
    except Exception:
        return None


def normalize_window(window: Any) -> dict[str, Any]:
    if not isinstance(window, dict):
        return {"utilization": 0.0, "resets_at": None}

    # WHAM commonly reports remaining/available quota as percent_left or
    # remaining_percent. The dashboard expects Claude-style utilization
    # (used percent), so convert: used = 100 - remaining.
    # This matters right after a reset: the endpoint may still expose a stale
    # used_percent=100 while percent_left is already ~100.
    remaining = dict_get_any(
        window,
        (
            "percent_left",
            "remaining_percent",
            "remainingPercent",
            "available_percent",
            "availablePercent",
            "percentRemaining",
            "percent_remaining",
        ),
    )

    remaining_percent = percent_from_fraction_or_percent(remaining)
    if remaining_percent is not None:
        utilization = clamp_percent(100.0 - remaining_percent)
    else:
        used = dict_get_any(
            window,
            (
                "usedPercent",
                "used_percent",
                "utilization",
                "usagePercent",
                "usage_percent",
                "percentUsed",
                "percent_used",
            ),
        )
        # WHAM used_percent is already a real 0..100 percentage.
        # Example from debug: used_percent=1 means 1%, not 100%.
        utilization = percent_direct(used)
        if utilization is None:
            utilization = 0.0

    reset = dict_get_any(
        window,
        (
            "resetsAt",
            "resets_at",
            "resetAt",
            "reset_at",
            "resetTime",
            "reset_time",
            "reset_time_ms",
            "endTime",
            "end_time",
        ),
    )

    return {
        "utilization": utilization,
        "resets_at": unix_to_iso(reset),
    }


FIVE_HOUR_SECONDS = 5 * 60 * 60
SEVEN_DAY_SECONDS = 7 * 24 * 60 * 60


def window_duration_seconds(window: Any) -> Optional[float]:
    """Return a rate-limit window duration, accepting known WHAM variants."""
    if not isinstance(window, dict):
        return None

    seconds = dict_get_any(
        window,
        (
            "limit_window_seconds",
            "limitWindowSeconds",
            "window_duration_seconds",
            "windowDurationSeconds",
            "duration_seconds",
            "durationSeconds",
        ),
    )
    if seconds is not None:
        with contextlib.suppress(TypeError, ValueError):
            value = float(seconds)
            if value > 0:
                return value

    minutes = dict_get_any(
        window,
        (
            "windowDurationMins",
            "window_duration_mins",
            "durationMins",
            "duration_mins",
        ),
    )
    if minutes is not None:
        with contextlib.suppress(TypeError, ValueError):
            value = float(minutes)
            if value > 0:
                return value * 60.0

    return None


def map_named_windows(primary: Any, secondary: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map server window names to five-hour/seven-day by actual duration.

    WHAM historically used primary_window for five hours and secondary_window
    for seven days. It can now return a single seven-day primary_window, so the
    field names alone are no longer sufficient.
    """
    five: Any = None
    seven: Any = None
    unknown: list[tuple[str, Any]] = []
    classified_any = False

    for source_name, window in (("primary", primary), ("secondary", secondary)):
        if not isinstance(window, dict):
            continue
        duration = window_duration_seconds(window)
        if duration is not None and abs(duration - FIVE_HOUR_SECONDS) <= 60 * 60:
            five = window
            classified_any = True
        elif duration is not None and abs(duration - SEVEN_DAY_SECONDS) <= 24 * 60 * 60:
            seven = window
            classified_any = True
        else:
            unknown.append((source_name, window))

    if not classified_any:
        # Backward compatibility for old responses without duration metadata.
        return normalize_window(primary), normalize_window(secondary)

    # Preserve the historical name mapping for any remaining unclassified
    # window, but never overwrite a duration-classified result.
    for source_name, window in unknown:
        if source_name == "primary" and five is None:
            five = window
        elif source_name == "secondary" and seven is None:
            seven = window
        elif five is None:
            five = window
        elif seven is None:
            seven = window

    return normalize_window(five), normalize_window(seven)


def extract_limits(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map undocumented WHAM usage response to five_hour/seven_day."""
    rate_limit = find_first_key(raw, ("rate_limit", "rateLimit", "rate_limits", "rateLimits"))

    # Most direct WHAM shape: rate_limit.primary_window / secondary_window.
    if isinstance(rate_limit, dict):
        primary = dict_get_any(rate_limit, ("primary_window", "primaryWindow", "primary"))
        secondary = dict_get_any(rate_limit, ("secondary_window", "secondaryWindow", "secondary"))
        if primary is not None or secondary is not None:
            return map_named_windows(primary, secondary)

    # Fallback: recursively locate windows anywhere in the response.
    primary = find_first_key(raw, ("primary_window", "primaryWindow"))
    secondary = find_first_key(raw, ("secondary_window", "secondaryWindow"))
    if primary is not None or secondary is not None:
        return map_named_windows(primary, secondary)

    # Fallback for app-server-like shape if the backend changes toward it.
    by_id = find_first_key(raw, ("rateLimitsByLimitId", "rate_limits_by_limit_id"))
    if isinstance(by_id, dict):
        for value in by_id.values():
            if not isinstance(value, dict):
                continue
            primary = dict_get_any(value, ("primary", "primary_window", "primaryWindow"))
            secondary = dict_get_any(value, ("secondary", "secondary_window", "secondaryWindow"))
            if primary is not None or secondary is not None:
                return map_named_windows(primary, secondary)

    # Last fallback: search for any list of windows with duration metadata.
    windows = collect_duration_windows(raw)
    if windows:
        five = choose_duration_window(windows, 300.0, tolerance=60.0)
        seven = choose_duration_window(windows, 10080.0, tolerance=1440.0)
        if five is None and seven is None and len(windows) >= 2:
            five = min(windows, key=lambda w: w.get("duration_mins") or 10**9)
            seven = max(windows, key=lambda w: w.get("duration_mins") or -1)
        return normalize_window(five and five.get("window")), normalize_window(seven and seven.get("window"))

    raise FatalError("could not find primary/secondary rate-limit windows in usage response")


def collect_duration_windows(obj: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        duration_seconds = window_duration_seconds(obj)
        if duration_seconds is not None:
            out.append({"duration_mins": duration_seconds / 60.0, "window": obj})
        for value in obj.values():
            out.extend(collect_duration_windows(value))
    elif isinstance(obj, list):
        for value in obj:
            out.extend(collect_duration_windows(value))
    return out


def choose_duration_window(windows: list[dict[str, Any]], target: float, tolerance: float) -> Optional[dict[str, Any]]:
    candidates = [w for w in windows if isinstance(w.get("duration_mins"), float)]
    if not candidates:
        return None
    candidates.sort(key=lambda w: abs(float(w["duration_mins"]) - target))
    best = candidates[0]
    if abs(float(best["duration_mins"]) - target) <= tolerance:
        return best
    return None


# ── Main monitor loop ──────────────────────────────────────────────────────
def update_once() -> dict[str, Any]:
    auth = load_auth()

    if token_needs_refresh(auth):
        auth = refresh_tokens(auth)

    try:
        raw = fetch_usage(auth)
    except PermissionError as exc:
        append_log(f"Usage request failed with auth error; refreshing once and retrying. {exc}")
        auth = refresh_tokens(auth)
        raw = fetch_usage(auth)

    five_hour, seven_day = extract_limits(raw)
    payload = {
        "updated_at": iso_now(),
        "five_hour": five_hour,
        "seven_day": seven_day,
    }
    write_json(USAGE_FILE, payload)
    return payload


def main() -> int:
    # --once: do a single update and exit. The dashboard polls this script
    # periodically (like it does claude.py), so it must not run as a daemon
    # there. Without --once the script keeps updating every 60s as before.
    run_once = "--once" in sys.argv

    if not run_once:
        log("Starting direct ChatGPT/Codex limits monitor. Updates every 60 seconds.")
    if not AUTH_FILE.exists():
        write_usage_error(f"auth.json was not found next to the script: {AUTH_FILE}")
        return 1

    while True:
        started = time.time()
        try:
            payload = update_once()
            five = payload["five_hour"]
            seven = payload["seven_day"]
            log(
                "Limits updated: "
                f"five_hour={five['utilization']}% reset={five['resets_at']}; "
                f"seven_day={seven['utilization']}% reset={seven['resets_at']}"
            )
        except KeyboardInterrupt:
            log("Monitor stopped.")
            return 130
        except Exception as exc:
            write_usage_error(str(exc))

        if run_once:
            return 0

        elapsed = time.time() - started
        time.sleep(max(1.0, POLL_INTERVAL_SEC - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
