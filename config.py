"""
config.py — XAUUSD FVG Trading System yapılandırma yükleyici.
Değerler config/default.json'dan okunur; dosya yoksa built-in varsayılanlar kullanılır.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parent
_CFG_PATH = _ROOT / "config" / "default.json"

_BUILTIN_DEFAULTS: dict = {
    "version": "10.0",
    "backtest": {
        "initial_capital": 10_000,
        "default_bias": "weekly",
        "default_rr": 2.0,
        "default_tbe_bars": 96,
        "warmup_days": 4,
    },
    "risk": {
        "risk_fraction": 0.005,
        "sl_buffer": 0.0005,
        "min_risk_dollar": 0.50,
        "max_risk_dollar": 150.0,
        "max_risk_pct": 2.0,
    },
    "live": {
        "leverage": 10,
        "risk_pct": 1.0,
        "dry_run": True,
        "tbe_minutes": 480,
        "symbol": "NCCGOLD2USD-USDT",
    },
    "private_bias": {
        "vol_lambda": 0.94,
        "vol_mult": 1.20,
        "ema_fast": 21,
        "ema_slow": 55,
    },
    "paths": {
        "csv_5m": "xauusd_5m.csv",
        "csv_1h": "xauusd_1h.csv",
        "weekly_bias": "weekly_bias.json",
        "daily_bias": "daily_bias.json",
        "reports": "reports",
    },
    "gui": {
        "theme": "dark",
        "window_width": 1100,
        "window_height": 720,
        "font_size": 11,
    },
}


class Config:
    """Thread-safe config container; singleton per path."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else _CFG_PATH
        self._data: dict = self._load()

    # ── I/O ─────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        return _deep_copy(_BUILTIN_DEFAULTS)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ── Erişim ──────────────────────────────────────────────────────────────

    def get(self, *keys: str, default: Any = None) -> Any:
        """cfg.get('backtest', 'initial_capital') → 10000"""
        d: Any = self._data
        for k in keys:
            if not isinstance(d, dict):
                return default
            d = d.get(k, default)
        return d

    def set(self, *keys_and_value: Any) -> None:
        """cfg.set('live', 'dry_run', False)"""
        *keys, value = keys_and_value
        d = self._data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    def section(self, *keys: str) -> dict:
        """cfg.section('backtest') → {'initial_capital': 10000, ...}"""
        result = self.get(*keys, default={})
        return result if isinstance(result, dict) else {}

    # ── Sık kullanılan kısayollar ────────────────────────────────────────────

    @property
    def initial_capital(self) -> float:
        return float(self.get("backtest", "initial_capital", default=10_000))

    @property
    def risk_fraction(self) -> float:
        return float(self.get("risk", "risk_fraction", default=0.005))

    @property
    def sl_buffer(self) -> float:
        return float(self.get("risk", "sl_buffer", default=0.0005))

    @property
    def csv_5m(self) -> str:
        return str(self.get("paths", "csv_5m", default="xauusd_5m.csv"))

    @property
    def csv_1h(self) -> str:
        return str(self.get("paths", "csv_1h", default="xauusd_1h.csv"))

    @property
    def weekly_bias_path(self) -> str:
        return str(self.get("paths", "weekly_bias", default="weekly_bias.json"))

    @property
    def daily_bias_path(self) -> str:
        return str(self.get("paths", "daily_bias", default="daily_bias.json"))


# ── Yardımcı ────────────────────────────────────────────────────────────────

def _deep_copy(d: dict) -> dict:
    import copy
    return copy.deepcopy(d)


# ── Modül seviyesi singleton (isteğe bağlı kullanım) ─────────────────────────

_default: Config | None = None


def get_config() -> Config:
    """Uygulama genelinde paylaşılan Config örneğini döndür."""
    global _default
    if _default is None:
        _default = Config()
    return _default
