"""
Configuration file read/write helpers.
Reads and writes the ai_settings.env file.
Also manages named configuration profiles in data/profiles/.
"""

import json
import os
from .constants import DATA_DIR, ENV_FILE

PROFILES_DIR = os.path.join(DATA_DIR, 'profiles')


def read_config() -> dict[str, str]:
    """Read ai_settings.env file into dict."""
    if not os.path.exists(ENV_FILE):
        return {}
    config = {}
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    return config


def write_config(config: dict[str, str]) -> None:
    """Write config dict to ai_settings.env."""
    os.makedirs(DATA_DIR, exist_ok=True)
    lines = [
        '# ========================================================',
        '# Portable AI - Master Switchboard',
        '# ========================================================'
    ]
    for key, value in config.items():
        lines.append(f'{key}={value}')
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def ensure_defaults() -> None:
    """Ensure ai_settings.env exists with reasonable defaults.

    If the file does not exist or has no AI_PROVIDER key, writes
    a minimal stub so the dashboard is usable on first launch.
    """
    config = read_config()

    dirty = False

    if 'AI_PROVIDER' not in config:
        config['AI_PROVIDER'] = 'openai'
        dirty = True

    if 'SYSTEM_PROMPT' not in config:
        config['SYSTEM_PROMPT'] = ''
        dirty = True

    if dirty:
        write_config(config)


# ── Profile management ───────────────────────────────────────────────

def _profile_path(name: str) -> str:
    """Return the full path for a named profile file."""
    # Sanitise name: replace path separators and null bytes
    safe = name.replace('\\', '_').replace('/', '_').replace('\x00', '')
    return os.path.join(PROFILES_DIR, f'{safe}.json')


def list_profiles() -> list[dict[str, str]]:
    """List all saved configuration profiles.

    Returns a list of dicts with 'name', 'provider', 'model', 'modified'.
    """
    if not os.path.exists(PROFILES_DIR):
        return []
    profiles = []
    for fname in sorted(os.listdir(PROFILES_DIR)):
        if not fname.endswith('.json'):
            continue
        path = os.path.join(PROFILES_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            config = data.get('config', {})
            name = data.get('name', fname[:-5])
            profiles.append({
                'name': name,
                'provider': config.get('AI_PROVIDER', ''),
                'model': config.get('AI_DISPLAY_MODEL') or config.get('OPENAI_MODEL', ''),
                'modified': data.get('modified', ''),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return profiles


def save_profile(name: str, config: dict[str, str]) -> None:
    """Save a named configuration profile."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    from datetime import datetime
    data = {
        'name': name,
        'config': config,
        'modified': datetime.now().isoformat(),
    }
    with open(_profile_path(name), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_profile(name: str) -> dict[str, str] | None:
    """Load a named configuration profile. Returns the config dict or None."""
    path = _profile_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('config', {})
    except (json.JSONDecodeError, OSError):
        return None


def delete_profile(name: str) -> bool:
    """Delete a named configuration profile. Returns True if deleted."""
    path = _profile_path(name)
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False
