"""Tests for scripts.dev.render_payoff_sample."""

from pathlib import Path

from scripts.dev.render_payoff_sample import main


def test_sample_cli_writes_png(tmp_path: Path) -> None:
    out = tmp_path / "sample.png"
    main(["--out", str(out)])

    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG")


def test_sample_cli_flags_degrade(tmp_path: Path) -> None:
    out = tmp_path / "degrade.png"
    main(["--out", str(out), "--no-margin", "--no-pnl", "--no-spot"])

    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG")
