"""
Configuration file read/write helpers.
Reads and writes the ai_settings.env file.
"""

import os
from .constants import DATA_DIR, ENV_FILE


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

    if dirty:
        write_config(config)
