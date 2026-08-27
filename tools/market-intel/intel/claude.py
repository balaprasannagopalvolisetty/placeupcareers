"""Wrapper around the Claude Code CLI.

Two jobs: keep token spend inside a hard budget, and turn a usage limit into a
scheduled resume instead of a crash.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, time
from dataclasses import dataclass

EX_TEMPFAIL = 75          # tells systemd this was a soft failure worth retrying

_LIMIT_PAT = re.compile(
    r"(usage limit|rate.?limit|quota|too many requests|overloaded|resets? at|try again)",
    re.I)
_RESET_EPOCH = re.compile(r"\b(1[6-9]\d{8}|2\d{9})\b")          # unix seconds in the message
_RESET_CLOCK = re.compile(r"resets?\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)


class UsageLimit(Exception):
    def __init__(self, resume_at: float, detail: str):
        super().__init__(detail)
        self.resume_at = resume_at
        self.detail = detail


@dataclass
class Result:
    text: str
    output_tokens: int


def available() -> bool:
    return shutil.which("claude") is not None


def ask(prompt: str, model: str, max_output_tokens: int,
        system: str | None = None, timeout: int = 300) -> Result:
    """One non-interactive Claude Code call. Raises UsageLimit when the account is
    out of budget, carrying the time it becomes worth retrying."""
    if not available():
        raise RuntimeError("claude CLI not found on PATH - run install.sh and authenticate once")

    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
    if system:
        cmd += ["--append-system-prompt", system]

    env = dict(os.environ, CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(max_output_tokens))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise UsageLimit(time.time() + 900, "cli timeout")

    blob = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 or not p.stdout.strip():
        if _LIMIT_PAT.search(blob):
            raise UsageLimit(_parse_resume(blob), blob.strip()[:500])
        raise RuntimeError(f"claude exited {p.returncode}: {blob.strip()[:500]}")

    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return Result(p.stdout.strip(), _estimate(p.stdout))

    if isinstance(data, dict) and data.get("is_error"):
        detail = json.dumps(data)[:500]
        if _LIMIT_PAT.search(detail):
            raise UsageLimit(_parse_resume(detail), detail)
        raise RuntimeError(f"claude error: {detail}")

    text = data.get("result") or data.get("text") or ""
    usage = (data.get("usage") or {})
    out = int(usage.get("output_tokens") or 0) or _estimate(text)
    return Result(text.strip(), out)


def _estimate(s: str) -> int:
    return max(1, len(s) // 4)


def _parse_resume(msg: str) -> float:
    """Prefer the reset time the service told us. Fall back to a fixed backoff."""
    m = _RESET_EPOCH.search(msg)
    if m:
        ts = float(m.group(1))
        if time.time() < ts < time.time() + 30 * 86400:
            return ts + 60
    m = _RESET_CLOCK.search(msg)
    if m:
        hour = int(m.group(1)) % 12
        if (m.group(3) or "").lower() == "pm":
            hour += 12
        now = time.localtime()
        target = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour,
                              int(m.group(2) or 0), 0, 0, 0, -1))
        if target <= time.time():
            target += 86400
        return target + 60
    return time.time() + int(os.environ.get("INTEL_BACKOFF_MINUTES", "90")) * 60
