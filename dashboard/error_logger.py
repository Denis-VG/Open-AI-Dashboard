"""
Error logging for AI API calls.
Writes timestamped logs to .app_data/ in the project root.
"""

import json
import os
from datetime import datetime
from typing import Any

from .constants import ROOT_DIR

APP_DATA_DIR = os.path.join(ROOT_DIR, '.app_data')

# Sensitive keys whose values will be masked in logs
_SENSITIVE_KEYS = {'api_key', 'apikey', 'authorization', 'x-api-key', 'key',
                   'token', 'secret', 'password', 'api-key'}


def _mask_sensitive(obj: Any) -> Any:
    """Recursively mask sensitive values in a dict/list."""
    if isinstance(obj, dict):
        return {
            k: '***' if k.lower().replace('_', '-') in _SENSITIVE_KEYS
            else _mask_sensitive(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_sensitive(v) for v in obj]
    return obj


def log_api_error(
    provider: str,
    error: str,
    request_body: Any = None,
    response_body: Any = None,
) -> None:
    """Write an API error log to .app_data/YYYYMMDD_HHMMSS.log"""
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filepath = os.path.join(APP_DATA_DIR, f'{timestamp}.log')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('=== AI API Error Log ===\n')
        f.write(f'Timestamp : {datetime.now().isoformat()}\n')
        f.write(f'Provider  : {provider}\n')
        f.write(f'Error     : {error}\n')
        f.write('\n--- Request Body ---\n')
        if request_body is not None:
            safe = _mask_sensitive(request_body)
            if isinstance(safe, (dict, list)):
                f.write(json.dumps(safe, indent=2, ensure_ascii=False))
            else:
                f.write(str(safe))
        else:
            f.write('(no request body captured)')
        f.write('\n\n--- Response Body ---\n')
        if response_body is not None:
            if isinstance(response_body, (dict, list)):
                f.write(json.dumps(response_body, indent=2, ensure_ascii=False))
            else:
                f.write(str(response_body))
        else:
            f.write('(no response body captured)')
        f.write('\n')
