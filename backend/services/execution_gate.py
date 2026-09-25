"""Central fail-closed execution gate.

All real-money, on-chain, instant and autonomous execution must be explicitly
enabled by the operator. Defaults are OFF.
"""
from __future__ import annotations
import os

TRUE={"1","true","yes","on"}

def _flag(name:str)->bool:
    return os.getenv(name,"false").strip().lower() in TRUE

def real_execution_enabled()->bool:
    return _flag("NN_REAL_EXECUTION_ENABLED")

def automation_enabled()->bool:
    return _flag("NN_AUTOMATION_ENABLED")

def live_trading_enabled()->bool:
    return _flag("NN_LIVE_TRADING_ENABLED") and real_execution_enabled()

def instant_withdraw_enabled()->bool:
    return _flag("NN_INSTANT_WITHDRAW_ENABLED") and real_execution_enabled()

def autonomous_execution_enabled()->bool:
    return _flag("NN_AUTONOMOUS_EXECUTION_ENABLED") and real_execution_enabled() and automation_enabled()

def require_real_execution():
    if not real_execution_enabled():
        raise PermissionError("REAL_EXECUTION_LOCKED")

def require_live_trading():
    if not live_trading_enabled():
        raise PermissionError("LIVE_TRADING_LOCKED")

def require_instant_withdraw():
    if not instant_withdraw_enabled():
        raise PermissionError("INSTANT_WITHDRAW_LOCKED")

def require_autonomous_execution():
    if not autonomous_execution_enabled():
        raise PermissionError("AUTONOMOUS_EXECUTION_LOCKED")

def status()->dict:
    return {
        "real_execution": real_execution_enabled(),
        "live_trading": live_trading_enabled(),
        "instant_withdraw": instant_withdraw_enabled(),
        "autonomous_execution": autonomous_execution_enabled(),
    }
