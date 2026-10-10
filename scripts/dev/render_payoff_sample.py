"""Sample CLI to render the reference Iron Condor payoff chart."""

import argparse
from decimal import Decimal as D
from pathlib import Path

import structlog

from src.notifications.payoff_chart import render_payoff_png
from src.payoff.core import PayoffLeg, compute_payoff
from src.utils.logging import setup_logging

_SCRIPT_NAME = "scripts.dev.render_payoff_sample"
logger = structlog.get_logger(_SCRIPT_NAME)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render the reference IC payoff chart.")
    parser.add_argument("--out", type=Path, required=True, help="Output PNG path")
    parser.add_argument("--no-margin", action="store_true", help="Omit margin")
    parser.add_argument("--no-pnl", action="store_true", help="Omit current P&L")
    parser.add_argument("--no-spot", action="store_true", help="Omit spot line")

    args = parser.parse_args(argv)

    setup_logging()

    q = 65
    payoff = compute_payoff(
        [
            PayoffLeg("PE", D("21000"), q, D("20.0"), "long_put"),
            PayoffLeg("PE", D("21900"), -q, D("100.0"), "short_put"),
            PayoffLeg("CE", D("23000"), -q, D("95.8"), "short_call"),
            PayoffLeg("CE", D("23500"), q, D("28.0"), "long_call"),
        ]
    )

    spot = None if args.no_spot else D("22348")
    margin = None if args.no_margin else D("86937")
    pnl = None if args.no_pnl else D("3200")

    png = render_payoff_png(
        payoff,
        spot=spot,
        current_pnl=pnl,
        dte=19,
        margin=margin,
        title="Iron Condor v2",
        subtitle="Monthly expiry",
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(png)

    print(f"Sample chart written to: {args.out.absolute()}")
    logger.info("render_payoff_sample.done", bytes=len(png), out_path=str(args.out))


if __name__ == "__main__":
    main()
