"""
System information gathering — disk, memory, CPU, session logs.
"""

import ctypes
import os
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Optional

from .constants import DATA_DIR, IS_WIN, IS_MAC, LOG_DIR, ROOT_DIR, ARCH, BIN_DIR, PLATFORM

# Optional psutil
try:
    import psutil
except ImportError:
    psutil = None

# ── helpers ───────────────────────────────────────────────────────

def _disk_info_windows() -> list[dict]:
    disks = []
    try:
        output = subprocess.check_output(
            ['wmic', 'logicaldisk', 'get', 'caption,size,freespace'],
            encoding='cp866',
            errors='replace',
            stderr=subprocess.DEVNULL
        )
        for line in output.strip().split('\n')[1:]:
            parts = line.split()
            if len(parts) >= 3:
                cap, sz, free = parts[0], parts[1], parts[2]
                if sz and free:
                    try:
                        disks.append({
                            'caption': cap,
                            'size': int(sz),
                            'freespace': int(free)
                        })
                    except ValueError:
                        pass
    except Exception:
        pass
    return disks


def _disk_info_unix() -> list[dict]:
    disks = []
    try:
        output = subprocess.check_output(
            ['df', '-B1', '--output=target,size,avail'],
            encoding='utf-8',
            errors='replace',
        )
        for line in output.strip().split('\n')[1:]:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    disks.append({
                        'caption': parts[0],
                        'size': int(parts[1]),
                        'freespace': int(parts[2])
                    })
                except ValueError:
                    pass
    except Exception:
        pass
    return disks


def _disk_free(root: str) -> Optional[int]:
    """Return free bytes for `root` using df (Unix only)."""
    if IS_WIN:
        return None
    try:
        out = subprocess.check_output(
            ['df', '-k', root],
            encoding='utf-8',
            errors='replace',
        )
        parts = out.strip().split('\n')[-1].split()
        if len(parts) >= 4:
            return int(parts[3]) * 1024
    except Exception:
        pass
    return None


def _memory_psutil() -> Optional[dict]:
    if not psutil:
        return None
    mem = psutil.virtual_memory()
    return {
        'total': mem.total,
        'available': mem.available,
        'used': mem.used,
        'percent': mem.percent
    }


def _memory_proc() -> Optional[dict]:
    """Linux /proc/meminfo fallback."""
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        total = avail = None
        for line in lines:
            if line.startswith('MemTotal:'):
                total = int(line.split()[1]) * 1024
            elif line.startswith('MemAvailable:'):
                avail = int(line.split()[1]) * 1024
        if total and avail:
            return {
                'total': total,
                'available': avail,
                'used': total - avail,
                'percent': (1 - avail / total) * 100
            }
    except Exception:
        pass
    return None


def _memory_winapi() -> Optional[dict]:
    """Win32 GlobalMemoryStatusEx fallback."""
    try:

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        kernel32 = ctypes.windll.kernel32
        ms = MEMORYSTATUSEX()
        ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            return {
                'total': ms.ullTotalPhys,
                'available': ms.ullAvailPhys,
                'used': ms.ullTotalPhys - ms.ullAvailPhys,
                'percent': 100 - (ms.ullAvailPhys / ms.ullTotalPhys * 100)
            }
    except Exception:
        pass
    return None


def _cpu_load() -> Optional[float]:
    if psutil:
        return psutil.cpu_percent(interval=0.1)
    return None


# ── public API ────────────────────────────────────────────────────

def get_system_info() -> dict:
    info = {
        'platform': sys.platform,
        'arch': ARCH,
        'hasGit': shutil.which('git') is not None,
        'hasPython': shutil.which('python') is not None or shutil.which('python3') is not None,
        'portableGit': IS_WIN and os.path.exists(os.path.join(BIN_DIR, 'git', 'cmd', 'git.exe')),
        'portablePython': IS_WIN and os.path.exists(os.path.join(BIN_DIR, 'python', 'python.exe')),
        'ollamaInstalled': os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama.exe'))
                           or os.path.exists(os.path.join(DATA_DIR, 'ollama', 'ollama')),
        'diskFree': 0,
        'diskTotal': 0,
    }

    # Disks
    info['disks'] = _disk_info_windows() if IS_WIN else _disk_info_unix()

    # Free space for ROOT_DIR (backwards compat)
    free = _disk_free(ROOT_DIR)
    if free is not None:
        info['diskFree'] = free

    # Memory
    mem = _memory_psutil() or (_memory_proc() if not IS_WIN else _memory_winapi())
    info['memoryTotal'] = mem.get('total') if mem else None
    info['memoryAvailable'] = mem.get('available') if mem else None
    info['memoryUsed'] = mem.get('used') if mem else None
    info['memoryPercent'] = mem.get('percent') if mem else None

    # CPU
    info['cpuLoad'] = _cpu_load()

    return info


# ── session logs ──────────────────────────────────────────────────

def get_session_logs(limit: int = 50) -> list[dict]:
    logs_dir = LOG_DIR
    logs: list[dict] = []
    os.makedirs(logs_dir, exist_ok=True)

    def walk(directory: str, depth: int = 0) -> None:
        if depth > 3:
            return
        try:
            for entry in os.listdir(directory):
                full = os.path.join(directory, entry)
                try:
                    if os.path.isdir(full):
                        walk(full, depth + 1)
                    elif any(entry.endswith(ext) for ext in ('.json', '.log', '.md', '.txt')):
                        st = os.stat(full)
                        logs.append({
                            'name': entry,
                            'path': full.replace(ROOT_DIR, ''),
                            'size': st.st_size,
                            'modified': datetime.fromtimestamp(st.st_mtime).isoformat()
                        })
                except OSError:
                    continue
        except OSError:
            pass

    walk(logs_dir)
    logs.sort(key=lambda x: x.get('modified', ''), reverse=True)
    return logs[:limit]
