import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "dhan_chain"


def check_no_credentials_leak(obj, path=""):
    """Deep scan for common credential/account identifiers."""
    forbidden_keys = {"clientid", "client_id", "accountid", "account_id", "token", "authorization"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert str(k).lower() not in forbidden_keys, f"Found forbidden key {k} at path {path}"
            check_no_credentials_leak(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            check_no_credentials_leak(item, f"{path}[{idx}]")


@pytest.mark.parametrize(
    "filename, min_strikes",
    [
        ("dec2026.json", 20),
        ("dec2027.json", 15),
    ],
)
def test_dhan_chain_fixture_validity(filename, min_strikes):
    filepath = FIXTURES_DIR / filename
    assert filepath.exists(), f"Fixture {filename} missing"

    with open(filepath) as f:
        data = json.load(f)

    check_no_credentials_leak(data, "root")

    assert "data" in data
    assert "oc" in data["data"]

    oc = data["data"]["oc"]
    assert len(oc) >= min_strikes, (
        f"Expected at least {min_strikes} strikes in {filename}, got {len(oc)}"
    )

    has_zero_delta = False
    has_nonzero_delta = False

    for _strike, val in oc.items():
        for opt_type in ("ce", "pe"):
            opt_data = val.get(opt_type, {})
            if "greeks" in opt_data:
                delta = opt_data["greeks"].get("delta")
                if delta == 0:
                    has_zero_delta = True
                elif delta is not None and delta != 0:
                    has_nonzero_delta = True

    assert has_zero_delta, "No zero-delta (absent) rows found in fixture"
    assert has_nonzero_delta, "No populated (nonzero) delta rows found in fixture"
