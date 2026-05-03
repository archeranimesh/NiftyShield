"""Tests for proxy monitor."""

from datetime import date
from decimal import Decimal

from src.paper.proxy_monitor import ProxyDeltaMonitor


class MockPaperStore:
    def __init__(self):
        self.logs = []
        self.consecutive = 0
        
    def record_proxy_delta_log(self, strategy_name, log_date, delta, is_below_threshold):
        self.logs.append((strategy_name, log_date, delta, is_below_threshold))
        if is_below_threshold:
            self.consecutive += 1
        else:
            self.consecutive = 0
            
    def get_proxy_delta_consecutive_days(self, strategy_name, current_date):
        return self.consecutive


def test_proxy_delta_monitor():
    store = MockPaperStore()
    monitor = ProxyDeltaMonitor(store)
    
    # OK state (>= 0.65)
    state, count = monitor.update_and_check(Decimal("0.70"), date(2023, 1, 1))
    assert state == "OK"
    assert count == 0
    
    # WARNING state (0.40 <= delta < 0.65)
    state, count = monitor.update_and_check(Decimal("0.50"), date(2023, 1, 2))
    assert state == "WARNING"
    assert count == 0
    
    # CRITICAL path (delta < 0.40)
    state, count = monitor.update_and_check(Decimal("0.35"), date(2023, 1, 3))
    # Threshold < 0.40 but consecutive days = 1 (since MockStore increments)
    # The condition in proxy_monitor is:
    # if consecutive_days >= 3: CRITICAL
    # elif delta < 0.65: WARNING
    assert state == "WARNING"
    assert count == 1
    
    state, count = monitor.update_and_check(Decimal("0.30"), date(2023, 1, 4))
    assert state == "WARNING"
    assert count == 2
    
    state, count = monitor.update_and_check(Decimal("0.25"), date(2023, 1, 5))
    assert state == "CRITICAL"
    assert count == 3
    
    # Reset to OK
    state, count = monitor.update_and_check(Decimal("0.80"), date(2023, 1, 6))
    assert state == "OK"
    assert count == 0
