from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import matplotlib.font_manager as fm
import pytest
from fontTools.ttLib import TTFont

from src.notifications.payoff_chart_theme import DARK, chart_font_family


def test_dark_theme_is_frozen():
    with pytest.raises(FrozenInstanceError):
        DARK.bg = "#ffffff"  # type: ignore


def test_font_family_returns_roboto_with_bundled_files():
    chart_font_family.cache_clear()
    family = chart_font_family()
    
    assert family == "Roboto"
    # Findfont should resolve to one of our bundled paths
    found = fm.findfont(family)
    assert "assets/fonts/Roboto-" in found.replace("\\", "/")


def test_font_family_falls_back_when_missing(tmp_path, caplog):
    chart_font_family.cache_clear()
    
    with caplog.at_level("WARNING"):
        family = chart_font_family(tmp_path)
    
    assert family == "DejaVu Sans"
    assert any("payoff_chart.font_fallback" in rec.message for rec in caplog.records)


def test_font_family_registers_once(tmp_path):
    chart_font_family.cache_clear()
    
    # Needs to be a valid dir so it doesn't fail, but we don't need real fonts if we patch addfont
    # Actually wait, if we patch addfont it won't raise.
    with patch("matplotlib.font_manager.fontManager.addfont") as mock_addfont:
        chart_font_family(tmp_path)
        chart_font_family(tmp_path)
        
        assert mock_addfont.call_count == 2 # 1 per weight (reg, bold) for the first call


def test_bundled_fonts_have_rupee_and_tabular_digits():
    font_dir = Path(__file__).parent.parent.parent.parent / "src" / "notifications" / "assets" / "fonts"
    
    for filename, expected_adv in [("Roboto-Regular.ttf", 1151), ("Roboto-Bold.ttf", 1175)]:
        font = TTFont(font_dir / filename)
        cmap = font.getBestCmap()
        
        # Has Rupee
        assert 0x20B9 in cmap
        
        # Tabular digits
        hmtx = font['hmtx']
        advances = set()
        for digit in "0123456789":
            glyph_name = cmap[ord(digit)]
            advances.add(hmtx[glyph_name][0])
            
        assert len(advances) == 1
        assert list(advances)[0] == expected_adv
