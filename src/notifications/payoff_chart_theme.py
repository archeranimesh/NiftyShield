import functools
import threading
from dataclasses import dataclass
from pathlib import Path

import matplotlib.font_manager as fm
import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ChartTheme:
    bg: str
    ink: str
    muted: str
    faint: str
    green: str
    red: str
    fill_alpha_green: float
    fill_alpha_red: float


DARK = ChartTheme(
    bg="#0e1117",
    ink="#e5e7eb",
    muted="#9ca3af",
    faint="#1f2937",
    green="#26b3a0",
    red="#ef5350",
    fill_alpha_green=0.22,
    fill_alpha_red=0.14,
)

_font_lock = threading.Lock()

@functools.lru_cache(maxsize=None)
def chart_font_family(font_dir: Path | None = None) -> str:
    with _font_lock:
        try:
            if font_dir is None:
                font_dir = Path(__file__).parent / "assets" / "fonts"
            
            reg_path = font_dir / "Roboto-Regular.ttf"
            bold_path = font_dir / "Roboto-Bold.ttf"
            
            fm.fontManager.addfont(str(reg_path))
            fm.fontManager.addfont(str(bold_path))
            
            return "Roboto"
        except Exception as e:
            logger.warning("payoff_chart.font_fallback", error=str(e))
            return "DejaVu Sans"
