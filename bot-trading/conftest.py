"""
Root conftest.py — ensures project root is on sys.path for imports.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Garante event loop activo antes de qualquer import com ib_insync nos testes
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

# Add project root to sys.path so 'from src.xxx import' works in tests
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
