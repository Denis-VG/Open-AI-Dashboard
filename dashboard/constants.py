"""
Shared constants for the Portable AI Dashboard server.
"""

import os
import sys

__dirname = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = __dirname  # public alias
ROOT_DIR = os.path.join(__dirname, '..')
DATA_DIR = os.path.join(ROOT_DIR, 'data')
ENV_FILE = os.path.join(DATA_DIR, 'ai_settings.env')
CHATS_DIR = os.path.join(DATA_DIR, 'chats')
HTML_FILE = os.path.join(__dirname, 'index.html')
PORT = 3000

IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
PLATFORM = 'win' if IS_WIN else 'darwin' if IS_MAC else 'linux'
ARCH = 'x64' if sys.maxsize > 2**32 else 'arm64'
BIN_DIR = os.path.join(ROOT_DIR, 'engine', f'node-{PLATFORM}-{ARCH}', 'bin')
