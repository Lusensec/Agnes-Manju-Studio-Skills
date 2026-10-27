"""Shared .env loader + config for all sub-skills.

Usage:
    from load_env import API_KEY, PROJECT_ROOT

.env discovery: walk UP from this file collecting every .env on the chain
(suite-root/.env, <sub-skill>/.env, examples/.env, ...), plus CWD/.env.
All files are merged; for each key the CLOSEST (deepest) file wins and CWD
only fills in keys that no ancestor file set. If no .env is found the module
still imports cleanly and API_KEY stays empty instead of crashing.

Stdio bootstrap: on systems whose console code page is not UTF-8 (e.g.
zh-CN Windows GBK/cp936), reconfigure stdout/stderr to UTF-8 with
errors="replace" so CJK + emoji output never crashes the script.
"""
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------- stdio fix
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass  # not a reconfigurable stream (e.g. pythonw, captured pipes)

# ------------------------------------------------------------- .env loading


def _find_env_files():
    """All .env files on the ancestor chain of this file (shallow->deep),
    with CWD/.env appended last (lowest priority)."""
    here = Path(__file__).resolve()
    chain = []
    for parent in reversed(list(here.parents)):  # shallowest ancestor first
        env = parent / ".env"
        if env.is_file():
            chain.append(env)
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file() and cwd_env not in chain:
        chain.append(cwd_env)
    return chain


def _load_env():
    """Merge KEY=VALUE pairs from all .env files into os.environ.

    Files are loaded shallow->deep with set-if-absent semantics, so the
    deepest (closest to the script) value wins per key; CWD/.env fills in
    keys not provided by any ancestor .env.
    """
    for env_file in _find_env_files():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env()

# ------------------------------------------------------------- config values
API_KEY = os.environ.get("AGNESAI_API_KEY", "")

# API base URL (OpenAI-style /v1 base). Domestic default; override in .env
# (AGNESAI_BASE_URL) to use the international platform (e.g.
# https://apihub.agnes-ai.com/v1) or any compatible endpoint.
API_BASE_URL = (
    os.environ.get("AGNESAI_BASE_URL", "https://api.agnes-ai.cn/v1").strip()
    .rstrip("/")
    or "https://api.agnes-ai.cn/v1"
)

# Configurable project root: MANJU_STUDIO_ROOT > legacy COMIC_STUDIO_ROOT > default
PROJECT_ROOT = Path(
    os.environ.get(
        "MANJU_STUDIO_ROOT",
        os.environ.get(
            "COMIC_STUDIO_ROOT",
            str(Path.home() / "manju-studio" / "projects"),
        ),
    )
)
