"""Date-aware lot size resolver for derivatives contracts."""

from datetime import date


class DateAwareLotSizeResolver:
    """Resolves market lot sizes for underlying indices/symbols based on date.

    Handles historical and current lot sizes for Indian indices, primarily Nifty 50.
    """

    @staticmethod
    def resolve(symbol: str, query_date: date) -> int:
        """Resolve the lot size for a given symbol and query date.

        Args:
            symbol: The underlying symbol or instrument key (e.g., 'NIFTY' or 'NSE_INDEX|Nifty 50').
            query_date: The date for which the lot size needs to be resolved.

        Returns:
            The resolved lot size (int).
        """
        symbol_upper = symbol.upper()

        # Equity ETFs (like NiftyBees) or normal equities have lot size 1.
        if "BEES" in symbol_upper or "EQ|" in symbol_upper or "INF" in symbol_upper:
            return 1

        is_nifty = (
            ("NIFTY" in symbol_upper)
            and not any(
                x in symbol_upper
                for x in {"BANK", "FIN", "MIDCP", "NEXT"}
            )
        )

        if is_nifty:
            # Nifty lot size history:
            # - January 1, 2026 onwards: 65
            # - November 20, 2024 to December 31, 2025: 75
            # - April 26, 2024 to November 19, 2024: 25
            # - October 1, 2021 to April 25, 2024: 50
            # - October 2015 to September 30, 2021: 75
            if query_date >= date(2026, 1, 1):
                return 65
            elif query_date >= date(2024, 11, 20):
                return 75
            elif query_date >= date(2024, 4, 26):
                return 25
            elif query_date >= date(2021, 10, 1):
                return 50
            else:
                return 75

        is_banknifty = "BANKNIFTY" in symbol_upper or "NIFTY BANK" in symbol_upper
        if is_banknifty:
            # Bank Nifty lot size history:
            # - January 1, 2026 onwards: 30
            # - July 1, 2023 to December 31, 2025: 15
            # - Before July 1, 2023: 25
            if query_date >= date(2026, 1, 1):
                return 30
            elif query_date >= date(2023, 7, 1):
                return 15
            else:
                return 25

        # Fallback default lot size for other symbols
        return 1
