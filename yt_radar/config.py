from __future__ import annotations

import os
from pathlib import Path
import json

_ENV_FILENAME = ".env"
_KEY_NAME = "YOUTUBE_API_KEY"


def get_api_key() -> str:
    """
    Returns the YouTube API key.

    Lookup order:
      1) Real environment variable: YOUTUBE_API_KEY
      2) Repo-local .env (dev convenience)
      3) Per-user config file (exe-friendly)
    """
    key = os.getenv(_KEY_NAME)
    if key:
        return key

    _load_dotenv_if_present()
    key = os.getenv(_KEY_NAME)
    if key:
        return key

    _load_user_config_if_present()
    key = os.getenv(_KEY_NAME)
    if key:
        return key

    raise RuntimeError(
        f"{_KEY_NAME} not set.\n"
        "Set it in your environment, or enter it in the app when prompted, or create a config file:\n\n"
        f"  {_user_config_path()}\n"
        f"  {_KEY_NAME}=YOUR_KEY_HERE\n"
    )


def save_api_key(key: str) -> None:
    """
    Saves the API key to the per-user config file.
    Does NOT modify the process environment (beyond current runtime).
    """
    key = (key or "").strip()
    if not key:
        return

    path = _user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Simple KEY=VALUE format (like .env)
    path.write_text(f"{_KEY_NAME}={key}\n", encoding="utf-8")


def _load_dotenv_if_present() -> None:
    """
    .env loader:
    Does not override already-set environment variables
    """
    repo_root = _find_repo_root()
    env_path = repo_root / _ENV_FILENAME
    if not env_path.exists():
        return

    _load_env_file(env_path)


def _load_user_config_if_present() -> None:
    """
    Per-user config loader (works great for executables).
    Does not override already-set environment variables.
    """
    path = _user_config_path()
    if not path.exists():
        return

    _load_env_file(path)


def _load_env_file(path: Path) -> None:
    """
    Loads KEY=VALUE lines into os.environ via setdefault (won't override real env vars).
    """
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")  # allow quoted values
            if not k:
                continue

            os.environ.setdefault(k, v)
    except Exception:
        return


def _user_config_path() -> Path:
    """
    %APPDATA%\\yt-radar\\config.env on Windows
    ~/.config/yt-radar/config.env on macOS/Linux
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / "yt-radar" / "config.env"
    return Path.home() / ".config" / "yt-radar" / "config.env"


def _find_repo_root() -> Path:
    """
    Finds the repo root by walking upward until we see main.py or .git.
    Falls back to current working directory.
    """
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / "main.py").exists() or (p / ".git").exists():
            return p
    return cwd


import json
from pathlib import Path
import os

def _user_settings_path() -> Path:
    # keep it alongside your config.env, but as json
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return base / "yt-radar" / "settings.json"
    return Path.home() / ".config" / "yt-radar" / "settings.json"


# new loading setting for additional options (creating a "do not show me again" option for a popup)

def load_setting(key: str, default=None):
    path = _user_settings_path()
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get(key, default)
    except Exception:
        return default


def save_setting(key: str, value) -> None:
    path = _user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = value
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
