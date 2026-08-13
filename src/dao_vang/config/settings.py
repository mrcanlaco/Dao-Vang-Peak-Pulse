import typing
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, StringConstraints, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BinanceConfig(BaseModel):
    base_url: HttpUrl = HttpUrl("https://fapi.binance.com")
    symbol: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]+$")] = "BTCUSDT"
    interval: Literal["5m"] = "5m"
    availability_lag_ms: int = Field(default=1000, ge=0)


class CollectionPolicy(BaseModel):
    timeout_seconds: int = Field(default=15, gt=0)
    max_retries: int = Field(default=5, ge=0)
    max_concurrency: int = Field(default=2, gt=0)


class PathsConfig(BaseModel):
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    normalized_dir: Path = Path("data/normalized")


class TelegramConfig(BaseModel):
    bot_token: str | None = Field(default=None, exclude=True)
    chat_id: str | None = Field(default=None, exclude=True)
    api_base: str = "https://api.telegram.org"
    timeout_seconds: int = Field(default=10, gt=0)
    max_retries: int = Field(default=3, ge=0)


class ScannerConfig(BaseModel):
    poll_interval_minutes: int = Field(default=5, ge=1)
    max_coins: int = Field(default=150, ge=1, le=500)
    min_volume_usd: float = Field(default=1_000_000, gt=0)
    cooldown_minutes: int = Field(default=60, ge=0)
    alert_levels: list[str] = Field(default_factory=lambda: ["CAO", "TRUNG BÌNH"])
    frozen_model_id: str | None = None
    db_path: Path = Path("data/dev.duckdb")
    artifact_dir: Path = Path("artifacts")
    watchlist_path: Path = Path("data/watchlist.json")
    kill_switch_path: Path = Path("data/scanner_kill_switch.json")
    rollback_state_path: Path = Path("data/scanner_rollback.json")
    health_report_path: Path = Path("data/scanner_health.json")
    threshold_policy_version: str | None = None
    max_heartbeat_age_minutes: int = Field(default=15, ge=1, le=24 * 60)
    drift_min_samples: int = Field(default=30, ge=1)
    drift_psi_warning: float = Field(default=0.10, ge=0.0)
    drift_psi_critical: float = Field(default=0.25, ge=0.0)
    history_days: int = Field(default=30, ge=1)
    enabled: bool = False
    operating_mode: Literal[
        "research",
        "shadow",
        "canary",
        "production",
        "production_alerting",
    ] = Field(
        default="research",
        description="research/shadow/canary/production(_alerting)",
    )
    global_daily_alert_limit: int = Field(default=15, ge=1)
    coin_daily_alert_limit: int = Field(default=3, ge=1)
    # Explicit opt-in for labelled observational Telegram messages for every
    # Radar detection while the scanner remains in shadow. Shadow delivery
    # intentionally bypasses action-alert cooldown and daily budgets; those
    # limits remain available for canary/production modes.
    shadow_telegram_enabled: bool = False
    # Strict Telegram delivery gate: exactly 70% is not sent.
    telegram_min_probability: float = Field(default=0.70, gt=0.0, lt=1.0)
    # A feature snapshot older than this must never produce an alert.
    max_feature_age_minutes: int = Field(default=10, ge=1, le=24 * 60)
    # Quality score is an explicit gate; missing score is derived from the
    # source quality_status (valid=1.0, warning=0.75).
    min_data_quality_score: float = Field(default=0.8, ge=0.0, le=1.0)

    # === Mở rộng chọn coin quét ===

    # scan_mode: cách chọn coin tự động
    #   "gainers"    — top coin tăng mạnh nhất 24h (mặc định)
    #   "losers"     — top coin giảm mạnh nhất 24h (cơ hội short đã xả)
    #   "volume"     — top coin theo khối lượng giao dịch 24h
    #   "volatile"   — top coin biến động mạnh (|price change| cao)
    #   "all"        — kết hợp gainers + losers + volume
    scan_mode: str = Field(default="gainers")
    # min_price_change_pct: lọc coin phải thay đổi ít nhất X% trong 24h
    # VD: 5.0 = chỉ quét coin tăng/giảm ≥5% (bỏ coin đi ngang)
    min_price_change_pct: float = Field(default=5.0, ge=0.0)
    # include_btc: luôn đảm bảo BTCUSDT trong danh sách quét (bối cảnh BTC)
    include_btc: bool = Field(default=True)
    # exclude_stablecoins: bỏ USDT/USDC/DAI/TUSD/FDUSD/BUSD pairs (không short stablecoin)
    exclude_stablecoins: bool = Field(default=True)


class SelfLearningConfig(BaseModel):
    """Guarded batch retraining settings.

    Self-learning creates and evaluates challengers, but promotion remains an
    explicit operator action until the rollout process has enough evidence.
    """

    enabled: bool = False
    check_interval_cycles: int = Field(default=12, ge=1)
    min_training_outcomes: int = Field(default=200, ge=20)
    min_new_outcomes: int = Field(default=50, ge=1)
    min_positive_events: int = Field(default=20, ge=1)
    min_precision_improvement: float = Field(default=0.01, ge=0.0, le=1.0)
    max_recall_regression: float = Field(default=0.05, ge=0.0, le=1.0)
    max_brier_regression: float = Field(default=0.01, ge=0.0, le=1.0)
    recent_window_days: int = Field(default=14, ge=1, le=365)
    recent_sample_weight: float = Field(default=2.0, ge=1.0, le=10.0)
    historical_max_rows: int = Field(default=100_000, ge=200)
    seed: int = Field(default=42, ge=0)
    state_path: Path = Path("artifacts/self_learning/state.json")
    report_dir: Path = Path("artifacts/self_learning/runs")


class PumpFilterConfig(BaseModel):
    """Config for pre-filter: find coins that pumped 50-300% in 1-5 days."""

    lookback_days: int = Field(default=5, ge=1, le=30)
    min_pump_pct: float = Field(default=0.50, ge=0.0, le=10.0)  # +50%
    max_pump_pct: float = Field(default=5.0, ge=0.0, le=20.0)  # +500% cap
    dump_threshold: float = Field(
        default=0.70, ge=0.0, le=1.0
    )  # skip if close < 70% peak
    min_volume_usd: float = Field(default=500_000, gt=0)


class CandidateComparisonConfig(BaseModel):
    """Shadow comparison between the production pump filter and a challenger.

    The challenger is observational only.  Enabling this section records
    paired decisions and future market outcomes; it never grants the
    challenger permission to score, alert, or send Telegram messages.
    """

    enabled: bool = False
    champion_version: str = "pump_filter_v1"
    challenger_version: str = "candidate_filter_v2"
    universe_size: int = Field(default=150, ge=10, le=500)
    max_candidates: int = Field(default=30, ge=1, le=100)
    max_workers: int = Field(default=4, ge=1, le=16)
    decision_interval_minutes: int = Field(default=60, ge=5, le=24 * 60)
    outcome_check_interval_cycles: int = Field(default=12, ge=1)
    horizon_hours: int = Field(default=24, ge=1, le=168)
    target_drawdown: float = Field(default=0.08, gt=0.0, lt=1.0)
    max_adverse_excursion: float = Field(default=0.04, gt=0.0, lt=1.0)
    gap_tolerance_minutes: int = Field(default=15, ge=5, le=120)
    metrics_window_days: int = Field(default=30, ge=1, le=365)
    min_resolved: int = Field(default=200, ge=1)
    min_positive_events: int = Field(default=50, ge=1)
    min_evaluation_days: int = Field(default=14, ge=1, le=365)
    truth_event_gap_minutes: int = Field(default=240, ge=60, le=24 * 60)
    min_challenger_event_recall: float = Field(default=0.80, ge=0.0, le=1.0)
    precision_at_10_relative_gain: float = Field(default=0.10, ge=0.0, le=1.0)
    max_recall_regression: float = Field(default=0.05, ge=0.0, le=1.0)
    snapshot_path: Path | None = None
    state_path: Path | None = None

    @model_validator(mode="after")
    def validate_comparison(self) -> "CandidateComparisonConfig":
        if self.champion_version == self.challenger_version:
            raise ValueError("champion_version and challenger_version must differ")
        if self.max_candidates > self.universe_size:
            raise ValueError("max_candidates must not exceed universe_size")
        return self



class ThresholdPolicy(BaseModel):
    version: str = "1.0"
    high_confidence_min_prob: float = Field(default=0.60, ge=0.0, le=1.0)
    watch_min_prob: float = Field(default=0.40, ge=0.0, le=1.0)
    high_confidence_min_evidence_groups: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> "ThresholdPolicy":
        if self.watch_min_prob > self.high_confidence_min_prob:
            raise ValueError("watch_min_prob must not exceed high_confidence_min_prob")
        return self

class ScoringConfig(BaseModel):
    """Composite distribution score 0-100."""

    alert_score_threshold: float = Field(default=40.0, ge=0.0, le=100.0)
    # Signal weights (must sum to 1.0)
    weight_price_volume_divergence: float = Field(default=0.20, ge=0.0, le=1.0)
    weight_funding_spike: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_momentum_exhaustion: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_distance_from_high: float = Field(default=0.10, ge=0.0, le=1.0)
    weight_taker_sell_pressure: float = Field(default=0.10, ge=0.0, le=1.0)
    weight_btc_context: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_oi_divergence: float = Field(default=0.10, ge=0.0, le=1.0)
    weight_fake_breakout: float = Field(default=0.05, ge=0.0, le=1.0)
    # BTC context thresholds
    btc_fomo_threshold: float = Field(default=0.05, ge=0.0, le=1.0)  # BTC +5% → FOMO
    btc_weak_threshold: float = Field(default=-0.02, le=0.0)  # BTC -2% → weak


    @model_validator(mode="after")
    def validate_weights(self) -> "ScoringConfig":
        weight_names = (
            "weight_price_volume_divergence",
            "weight_funding_spike",
            "weight_momentum_exhaustion",
            "weight_distance_from_high",
            "weight_taker_sell_pressure",
            "weight_btc_context",
            "weight_oi_divergence",
            "weight_fake_breakout",
        )
        total = sum(float(getattr(self, name)) for name in weight_names)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total:.8f}")
        return self


class CoinGeckoConfig(BaseModel):
    """Multi-source cross-reference via CoinGecko free API."""

    enabled: bool = Field(default=False)
    base_url: str = "https://api.coingecko.com/api/v3"
    timeout_seconds: int = Field(default=15, gt=0)
    max_retries: int = Field(default=3, ge=0)
    price_mismatch_threshold: float = Field(default=0.05, ge=0.0, le=1.0)  # 5%


class WebConfig(BaseModel):
    port: int = Field(default=8000, gt=0, le=65535)
    host: str = Field(default="127.0.0.1")
    # Public address used in Telegram deep links. Keep this separate from
    # `host`: the web server may bind locally while users open the dashboard
    # through a domain or tunnel.
    public_url: str = Field(default="http://127.0.0.1:8000")

class AppSettings(BaseSettings):
    web: WebConfig = WebConfig()
    binance: BinanceConfig = BinanceConfig()
    collection: CollectionPolicy = CollectionPolicy()
    paths: PathsConfig = PathsConfig()
    telegram: TelegramConfig = TelegramConfig()
    scanner: ScannerConfig = ScannerConfig()
    self_learning: SelfLearningConfig = SelfLearningConfig()
    pump_filter: PumpFilterConfig = PumpFilterConfig()
    candidate_comparison: CandidateComparisonConfig = CandidateComparisonConfig()
    threshold: ThresholdPolicy = ThresholdPolicy()
    scoring: ScoringConfig = ScoringConfig()

    coingecko: CoinGeckoConfig = CoinGeckoConfig()

    api_key: str | None = Field(default=None, exclude=True)
    api_secret: str | None = Field(default=None, exclude=True)

    model_config = SettingsConfigDict(
        env_prefix="DAO_VANG_",
        env_nested_delimiter="__",
        env_file=".env",
    )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "AppSettings":
        if not yaml_path.exists():
            return cls()

        with open(yaml_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            config_dict = typing.cast(dict[str, typing.Any], loaded) if loaded else {}

        return cls(**config_dict)
