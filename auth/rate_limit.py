"""Small in-memory limiter for OTP send/verify.

Per-process only: it resets when the server restarts. A lockout also clears
the stored OTP in the database, so guessing stops even if memory resets.
"""
import hmac
import secrets
import threading
import time

from fastapi import HTTPException

MAX_VERIFY_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60
SEND_MIN_INTERVAL_SECONDS = 60
SEND_MAX_PER_HOUR = 5

_lock = threading.Lock()
_send_log = {}
_failures = {}


def _norm(identifier):
    return str(identifier or "").strip().lower()


def generate_otp():
    return str(100000 + secrets.randbelow(900000))


def otps_match(stored, submitted):
    if not stored or submitted is None:
        return False
    return hmac.compare_digest(str(stored).encode(), str(submitted).strip().encode())


def check_send_allowed(identifier):
    key = _norm(identifier)
    now = time.time()
    with _lock:
        log = [t for t in _send_log.get(key, []) if now - t < 3600]
        if log and now - log[-1] < SEND_MIN_INTERVAL_SECONDS:
            wait = int(SEND_MIN_INTERVAL_SECONDS - (now - log[-1])) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {wait} seconds before requesting another OTP.",
            )
        if len(log) >= SEND_MAX_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail="Too many OTP requests. Please try again later.",
            )
        log.append(now)
        _send_log[key] = log


def check_verify_allowed(identifier):
    key = _norm(identifier)
    now = time.time()
    with _lock:
        entry = _failures.get(key)
        if entry and entry["locked_until"] > now:
            raise HTTPException(
                status_code=429,
                detail="Too many wrong OTP attempts. Please request a new OTP later.",
            )


def record_verify_failure(identifier):
    """Returns True when this failure locked the identifier."""
    key = _norm(identifier)
    now = time.time()
    with _lock:
        entry = _failures.get(key)
        if not entry or entry["locked_until"] and entry["locked_until"] <= now:
            entry = {"count": 0, "locked_until": 0}
        entry["count"] += 1
        locked = entry["count"] >= MAX_VERIFY_FAILURES
        if locked:
            entry["locked_until"] = now + LOCKOUT_SECONDS
        _failures[key] = entry
        return locked


def record_verify_success(identifier):
    with _lock:
        _failures.pop(_norm(identifier), None)


def reset_all():
    with _lock:
        _send_log.clear()
        _failures.clear()
