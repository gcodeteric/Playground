from __future__ import annotations

import os
from unittest.mock import patch

from config import load_config


def test_ib_port_paper_gateway_auto():
    with patch.dict(os.environ, {"PAPER_TRADING": "true", "USE_GATEWAY": "true", "IB_PORT": ""}, clear=False):
        assert load_config().ib.port == 4002


def test_ib_port_paper_tws_auto():
    with patch.dict(os.environ, {"PAPER_TRADING": "true", "USE_GATEWAY": "false", "IB_PORT": ""}, clear=False):
        assert load_config().ib.port == 7497


def test_ib_port_live_gateway_auto():
    with patch.dict(os.environ, {"PAPER_TRADING": "false", "USE_GATEWAY": "true", "IB_PORT": ""}, clear=False):
        assert load_config().ib.port == 4001


def test_ib_port_live_tws_auto():
    with patch.dict(os.environ, {"PAPER_TRADING": "false", "USE_GATEWAY": "false", "IB_PORT": ""}, clear=False):
        assert load_config().ib.port == 7496


def test_ib_port_manual_override():
    with patch.dict(os.environ, {"PAPER_TRADING": "true", "USE_GATEWAY": "true", "IB_PORT": "1234"}, clear=False):
        assert load_config().ib.port == 1234
