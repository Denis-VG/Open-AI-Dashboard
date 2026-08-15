"""
Error logging for AI API calls.
Writes timestamped logs to data/logs/ in the server directory.
"""

import json
import os
import re
from datetime import datetime
from typing import Any

from .constants import LOG_DIR

# Sensitive keys whose values will be masked in logs
_SENSITIVE_KEYS = {'api_key', 'apikey', 'authorization', 'x-api-key', 'key',
                   'token', 'secret', 'password', 'api-key'}

# Pattern to mask API keys in URL query strings
_KEY_IN_URL = re.compile(r'(key|api_key|apikey|token)=([^&\s]+)', re.IGNORECASE)
# Pattern to mask Bearer tokens in string values
_BEARER_TOKEN = re.compile(r'Bearer\s+\S+', re.IGNORECASE)


def _mask_sensitive(obj: Any) -> Any:
    """Recursively mask sensitive values in a dict/list/str."""
    if isinstance(obj, dict):
        return {
            k: '***' if k.lower().replace('_', '-') in _SENSITIVE_KEYS
            else _mask_sensitive(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_sensitive(v) for v in obj]
    if isinstance(obj, str):
        # Mask API keys embedded in URLs
        obj = _KEY_IN_URL.sub(r'\1=***', obj)
        # Mask Bearer tokens
        obj = _BEARER_TOKEN.sub('Bearer ***', obj)
        return obj
    return obj


def log_api_error(
    provider: str,
    error: str,
    request_body: Any = None,
    response_body: Any = None,
) -> None:
    """Write an API error log to data/logs/YYYYMMDD_HHMMSS.log"""
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filepath = os.path.join(LOG_DIR, f'{timestamp}.log')

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
