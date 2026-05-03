"""Track C delta monitor for the 3-Track comparison framework."""

from datetime import date
from decimal import Decimal

from src.paper.store import PaperStore


class ProxyDeltaMonitor:
    """Monitors Track C's delta and tracks consecutive days below 0.40."""

    THRESHOLD = Decimal("0.40")
    WARNING_THRESHOLD = Decimal("0.65")
    CRITICAL_DAYS = 3

    def __init__(self, store: PaperStore, strategy_name: str = "paper_nifty_proxy") -> None:
        """Initialize the monitor.
        
        Args:
            store: PaperStore for persisting delta logs.
            strategy_name: The strategy namespace to monitor.
        """
        self.store = store
        self.strategy_name = strategy_name

    def update_and_check(
        self, current_delta: Decimal, current_date: date
    ) -> tuple[str, int]:
        """Record the current delta and check threshold state.
        
        Args:
            current_delta: Current delta of the proxy position.
            current_date: The date of the snapshot.
            
        Returns:
            Tuple of (state_label, consecutive_days).
            state_label is one of 'OK', 'WARNING', or 'CRITICAL'.
        """
        # Convert to absolute delta just in case a signed value is passed
        abs_delta = abs(current_delta)
        is_below = abs_delta < self.THRESHOLD
        
        # Record the log
        self.store.record_proxy_delta_log(
            strategy_name=self.strategy_name,
            log_date=current_date,
            delta=abs_delta,
            is_below_threshold=is_below
        )
        
        # Retrieve consecutive days
        consecutive_days = self.store.get_proxy_delta_consecutive_days(
            strategy_name=self.strategy_name,
            current_date=current_date
        )
        
        if consecutive_days >= self.CRITICAL_DAYS:
            state_label = "CRITICAL"
        elif abs_delta < self.WARNING_THRESHOLD:
            state_label = "WARNING"
        else:
            state_label = "OK"
            
        return state_label, consecutive_days
