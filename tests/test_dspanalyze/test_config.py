"""Regression tests for dspanalyze.config value converters."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dspanalyze.config import convert_value, load_config


def test_q_log_uses_div_100_not_255():
    """raw=25 must decode to Q≈1.69 (formula 0.4·320^(raw/100)).

    Regression for a /255 typo that previously produced Q=0.70.
    Cross-checked against minidsp.protocol.peq_raw_to_q and the
    spec in protocol_config.toml ("Q = 0.40 * 320^(raw/100)").
    """
    cfg = load_config()
    assert "1.69" in convert_value(25, "q_log", cfg)
    # Endpoints that are mathematically exact (no rounding wobble):
    assert "0.40" in convert_value(0, "q_log", cfg)        # min
    assert "128.00" in convert_value(100, "q_log", cfg)    # peak max
