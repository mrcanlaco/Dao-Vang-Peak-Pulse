export type RiskLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'SAFE';
export type FilterTag = 'ALL' | 'HOT_RISK' | 'EXPIRING' | 'VOLUME_SPIKE' | 'ACTIVE' | 'EXPIRED';
export type SignalSort = 'NEWEST' | 'HIGHEST_PROBABILITY' | 'HIGHEST_RISK' | 'EXPIRING_SOON';
export type TelegramFilter = 'ALL' | 'SENT' | 'UNSENT';

export interface SignalDriver {
  name: string;
  impact: string;
  score: string;
}

export interface SignalItem {
  id: string;
  symbol: string;
  name: string;
  probability: number;
  risk_level: RiskLevel;
  signal_time: string;
  /** Observation/delivery time used by the live Radar's "newest" sort. */
  event_time?: string | null;
  telegram_sent_at?: string | null;
  signal_price: number;
  target_drawdown: number;
  target_price: number;
  validity_hours_left: number;
  validity_hours_total?: number;
  invalidation_time?: string | null;
  lead_time_avg_hours: number;
  oi_change_24h: string;
  taker_sell_ratio: number;
  funding_rate: string;
  rsi_divergence: boolean;
  is_volume_spike?: boolean;
  drivers: SignalDriver[];
  evidence_precision?: number | null;
  evidence_n_judged?: number | null;
  hit?: boolean | null;
  telegram_sent?: boolean;
}

export interface WatchlistPreset {
  id: string;
  name: string;
  description: string;
  count: number;
}

export interface WatchlistData {
  active_scan_mode: string;
  active_scan_modes?: string[];
  presets: WatchlistPreset[];
  manual_watchlist: string[];
}

export type TrackingStatus = 'WATCHING' | 'IN_POSITION' | 'CLOSED';
export type TrackingSignalStatus = 'ACTIVE' | 'HIT' | 'EXPIRED' | 'NO_SIGNAL';

export interface TrackingWatchlistItem {
  id: string;
  symbol: string;
  source: 'radar' | 'manual' | string;
  source_signal_time?: string | null;
  source_probability?: number | null;
  source_risk_level?: RiskLevel | string | null;
  source_price?: number | null;
  source_target_price?: number | null;
  source_invalidation_time?: string | null;
  status: TrackingStatus;
  position_side?: 'LONG' | 'SHORT' | null;
  entry_price?: number | null;
  quantity?: number | null;
  notional?: number | null;
  leverage?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  opened_at?: string | null;
  closed_at?: string | null;
  notes?: string;
  created_at: string;
  updated_at: string;
  signal_status: TrackingSignalStatus;
  hit?: boolean | null;
  hit_time?: string | null;
  validity_hours_left?: number | null;
  current_price?: number | null;
  current_probability?: number | null;
  current_risk_level?: RiskLevel | string | null;
  signal_change_pct?: number | null;
  signal_progress_pct?: number | null;
  position_change_pct?: number | null;
  position_pnl?: number | null;
  position_roi_pct?: number | null;
  last_market_update?: string | null;
}

export interface CandidateCoin {
  symbol: string;
  scan_time?: string;
  price: number;
  score: number;
  risk: RiskLevel;
  oi_24h: string;
  funding: string;
  taker_ratio: number;
  volume_24h: string;
  age: string;
  is_stale?: boolean;
  stage?: string;
  filter_version?: string;
  pump_pct?: number;
}

export type CandidateFilterSegment = 'ALL' | 'V2_CHAMPION' | 'V1_CHALLENGER' | 'OVERLAP' | 'V2_UNIQUE' | 'V3_PREVIEW';

export interface CandidateFilterArmMetrics {
  anchors: number;
  resolved: number;
  excluded: number;
  selected_resolved: number;
  positive_anchors: number;
  positive_events: number;
  anchor_precision: number | null;
  anchor_recall: number | null;
  event_recall: number | null;
  precision_at_10: number | null;
  episodes_resolved: number;
  episode_precision: number | null;
  median_lead_time_minutes: number | null;
  false_candidates_per_day: number;
}

export interface CandidateFilterPromotion {
  ready: boolean;
  passed: boolean;
  requires_human_approval: boolean;
  positive_anchors: number;
  positive_events: number;
  min_resolved: number;
  min_positive_events: number;
  min_evaluation_days: number;
  min_challenger_event_recall: number;
  reasons: string[];
}

export interface CandidateFilterDecisionSummary {
  symbol: string;
  rank?: number | null;
  rank_score?: number | null;
  stage?: string;
  reason_codes?: string[];
}

export interface CandidateFilterDelta {
  point: number | null;
  ci_lower: number | null;
  ci_upper: number | null;
  n?: number;
  n_blocks?: number;
}

export interface CandidateFilterComparison {
  available: boolean;
  enabled: boolean;
  status: string;
  generated_at: string | null;
  stale: boolean;
  cycle?: number;
  champion_version?: string;
  challenger_version?: string;
  future_versions?: Array<{
    version: string;
    name: string;
    status: string;
    description: string;
  }>;
  universe_count?: number;
  champion_selected?: number;
  challenger_selected?: number;
  overlap?: number;
  champion_only?: number;
  challenger_only?: number;
  neither?: number;
  selected?: {
    champion?: CandidateFilterDecisionSummary[];
    challenger?: CandidateFilterDecisionSummary[];
    overlap?: CandidateFilterDecisionSummary[];
    champion_only?: CandidateFilterDecisionSummary[];
    challenger_only?: CandidateFilterDecisionSummary[];
  };
  comparison?: {
    window_days: number;
    champion_version: string;
    challenger_version: string;
    metrics: Record<string, CandidateFilterArmMetrics>;
    paired_deltas?: {
      precision_at_10: CandidateFilterDelta;
      event_recall: CandidateFilterDelta;
      confidence_level: number;
      bootstrap_samples: number;
    };
    promotion: CandidateFilterPromotion;
  };
}

export interface CandlePoint {
  time: string;
  time_iso?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  price: number;
  volume?: number;
  oi: number;
  funding: number;
  taker_ratio: number;
  is_signal_point?: boolean;
}

export interface ShapDriver {
  feature: string;
  impact_score: number;
  description: string;
}

export interface CoinDetail {
  symbol: string;
  name: string;
  current_price: number;
  chart_source?: 'db' | 'api';
  has_alert?: boolean;
  score_source?: 'alert' | 'scan' | 'signal' | null;
  probability: number | null;
  risk_level: RiskLevel | null;
  target_drawdown: number;
  target_price: number;
  signal_timestamp: string;
  chart_data: CandlePoint[];
  metrics: {
    oi_change_24h: string;
    taker_sell_ratio: number;
    funding_rate: string;
    rsi_15m: number;
    volume_delta_24h: string;
  };
  shap_drivers: ShapDriver[];
}

export interface DeepAnalysisComponent {
  name: string;
  raw_name: string;
  raw_value: number | string;
  score: number;
  weight: number;
  weighted_score: number;
  explanation: string;
}

export interface DeepAnalysisPump {
  detected: boolean;
  pump_pct: number;
  pump_days: number;
  peak_price: number;
  current_price: number;
  current_vs_peak: number;
  quote_volume: number;
}

export interface DeepAnalysis {
  symbol: string;
  analysis_time: string;
  feature_time: string | null;
  current_price: number | null;
  total_score: number;
  heuristic_score: number;
  heuristic_recommendation?: string;
  recommendation: string;
  model_probability: number | null;
  calibrated_probability: number | null;
  risk_tier: string | null;
  probability_threshold: number | null;
  quality_status?: string | null;
  frozen_model_id?: string | null;
  frozen_model_error?: string | null;
  btc_regime: string;
  btc_explanation: string;
  btc_score_adjustment: number;
  components: DeepAnalysisComponent[];
  pump_analysis: DeepAnalysisPump;
  rsi: { rsi_14?: number; rsi_7?: number };
  threshold: number;
  has_features: boolean;
}

export interface TradeSetup {
  entryPrice: number;
  entryZoneLow: number;
  entryZoneHigh: number;
  stopLossPrice: number;
  stopLossPct: number;
  tp1Price: number;
  tp1Pct: number;
  tp2Price: number;
  tp2Pct: number;
  riskRewardRatio: number;
}

export interface SystemStatus {
  scanner_status: string;
  scanner_mode: string;
  heartbeat: string;
  scanned_coins_count: number;
  active_signals_count: number;
  top_risk_symbol: string;
  model_version: string;
  model_id?: string;
  telegram_connected: boolean;
  threshold: number;
}

export interface RiskLevelPrecision {
  n_judged: number;
  n_hit: number;
  precision: number | null;
}

export interface ModelAudit {
  model_name: string;
  horizon: string;
  target_drawdown: string;
  mae_allowed: string;
  sample_size: number;
  has_enough_data: boolean;
  metrics: {
    precision: number | null;
    recall: number | null;
    f1_score: number | null;
    brier_score: number | null;
    baseline_precision: number | null;
    precision_uplift: string | null;
  };
  precision_by_risk_level: Record<string, RiskLevelPrecision>;
  lead_time: {
    mean_hours: number | null;
    median_hours: number | null;
    min_hours: number | null;
    max_hours: number | null;
  };
  validation_checks: {
    walk_forward_status: string;
    leakage_test: string;
    embargo_period: string;
    point_in_time_verified: boolean;
  };
}

export interface MarketTicker {
  symbol: string;
  change: string;
  price: number;
  volume_24h: number;
}

export interface BinanceListingStats {
  spot_coins: number;
  usdm_coins: number;
  coinm_coins: number;
  futures_coins: number;
  all_coins: number;
  spot_only: number;
  futures_only: number;
  both: number;
  spot_symbols: number;
  spot_usdt_pairs: number;
  usdm_symbols: number;
  usdm_usdt_pairs: number;
  coinm_symbols: number;
  date: string;
  fetched_at: string;
}

export interface BinanceListingHistoryEntry {
  date: string;
  spot_coins: number;
  usdm_coins: number;
  coinm_coins: number;
  futures_coins: number;
  all_coins: number;
  fetched_at: string;
}

export interface MarketOverviewData {
  binance_listing_total: number;
  binance_listing: BinanceListingStats;
  binance_listing_history: BinanceListingHistoryEntry[];
  scanned_volatile_top: number;
  market_regime: string;
  distribution_index: number;
  top_gainers: MarketTicker[];
  top_losers: MarketTicker[];
}

export interface AutomationSettings {
  autoTelegramPush: boolean;
  autoPushThreshold: number;
  audioAlertEnabled: boolean;
  webhookUrl: string;
}

export interface TelemetryLog {
  timestamp: string;
  symbol: string;
  step: string;
  status: string;
  duration_ms: number;
  details: string;
}

export interface TelegramDispatchLog {
  timestamp: string;
  symbol: string;
  risk_score: string;
  channel: string;
  status: string;
}

export interface ScannerTelemetry {
  scanner_engine_status: string;
  last_scan_timestamp: string;
  next_scan_in_seconds: number | null;
  poll_interval_minutes: number;
  api_endpoint: string;
  average_api_latency_ms: number | null;
  active_scan_mode: string;
  active_scan_modes?: string[];
  scanned_pairs_count: number;
  signals_triggered_count: number;
  stablecoins_excluded_count: number | null;
  runtime_state?: Record<string, any>;
  model_id?: string;
  cycle?: number;
  max_coins?: number;
  logs: TelemetryLog[];
  telegram_dispatches: TelegramDispatchLog[];
}

export interface MultiCoinScanRun {
  run_time: string;
  n_coins: number;
  n_valid: number;
  n_edge: number;
  best_coin: string;
  best_precision: number;
}

export interface MultiCoinScanCoin {
  symbol: string;
  status: 'edge' | 'no_edge' | 'leak' | 'no_data' | 'not_run';
  pos: number;
  total: number;
  prevalence: number;
  precision: number;
  baseline: number;
  ci_lower: number;
  ci_upper: number;
  n_valid_folds: number;
  leakage: string;
  n_runs: number;
  latest_time: string;
}

export interface MultiCoinScanData {
  has_db: boolean;
  n_artifacts: number;
  n_runs: number;
  run_history: MultiCoinScanRun[];
  coin_list: MultiCoinScanCoin[];
}

export interface ExperimentSummary {
  artifact_id: string;
  created_at: string;
  hypothesis_id: string;
  symbol: string;
  status: 'edge' | 'promising' | 'no_edge' | 'leak' | 'no_data' | 'failed';
  precision: number;
  baseline: number;
  recall: number;
  brier: number;
  n_valid_folds: number;
  n_skipped_folds: number;
  n_positive: number;
  leakage: string;
  warning: string | null;
}

export interface ExperimentsData {
  experiments: ExperimentSummary[];
  total: number;
}

export interface FrozenModel {
  model_id: string;
  freeze_time: string;
  train_cutoff: string;
  threshold: number;
  n_features: number;
  hypothesis_id: string;
  training_stats: {
    train_size?: number;
    train_positives?: number;
    threshold?: number;
    n_features?: number;
    precision?: number;
    recall?: number;
  };
  label_spec?: {
    target_drawdown: number;
    max_ae: number;
    horizon_minutes: number;
    target_pct: string;
    mae_pct: string;
    horizon_h: string;
  };
  label_version?: string;
  friendly_name?: string;
  description?: string;
}

export interface ModelChoice {
  key: string;
  label: string;
  description: string;
  model_type: 'heuristic' | 'walkforward' | 'frozen';
  frozen_model_id: string | null;
  label_spec?: {
    target_drawdown: number;
    max_ae: number;
    horizon_minutes: number;
    target_pct: string;
    mae_pct: string;
    horizon_h: string;
  };
  train_cutoff?: string;
  threshold?: number;
}

export interface ModelsData {
  models: ModelChoice[];
  total: number;
  current_scanner_model_id: string;
  error?: string;
}

export interface FrozenModelsData {
  models: FrozenModel[];
  total: number;
  error?: string;
}

export interface ForwardTestResult {
  status: string;
  model_id?: string;
  message?: string;
  train_cutoff?: string;
  threshold?: number;
  n_forward_rows?: number;
  n_positive_labels?: number;
  n_predicted_positive?: number;
  metrics?: {
    precision: number;
    recall: number;
    brier: number;
  };
  training_metrics?: {
    precision: number;
    recall: number;
  };
  risk_breakdown?: Record<string, {
    n_signals: number;
    n_actual_distribution: number;
    precision: number;
  }>;
  drift_check?: {
    precision_delta: number;
    recall_delta: number;
    precision_drift: boolean;
  };
  summary?: string;
}

// ===== System History tab =====

export interface DataStat {
  table: string;
  rows: number;
  ts_column?: string;
  min_time?: string | null;
  max_time?: string | null;
}

export interface ScanPerDay {
  day: string;
  n_rows: number;
  n_cycles: number;
  n_symbols: number;
}

export interface SignalPerDay {
  day: string;
  n_signals: number;
  n_telegram: number;
  n_hit: number;
}

export interface ModelProgress {
  model_id: string;
  friendly_name: string;
  description: string;
  label_version: string;
  label_spec?: {
    target_drawdown: number;
    max_ae: number;
    horizon_minutes: number;
    target_pct: string;
    mae_pct: string;
    horizon_h: string;
  };
  train_cutoff: string;
  freeze_time: string;
  threshold: number;
  n_features: number;
  train_size?: number | null;
  train_positives?: number | null;
  train_precision?: number | null;
  train_recall?: number | null;
  is_scanner_model: boolean;
}

export interface LatestExperiment {
  artifact_id: string;
  created_at: string;
  hypothesis_id?: string;
  label_version?: string;
  precision_mean?: number | null;
  recall_mean?: number | null;
  brier_mean?: number | null;
  n_valid_folds?: number | null;
}

export interface SelfLearningMetrics {
  precision?: number | null;
  recall?: number | null;
  brier?: number | null;
  threshold?: number | null;
  n_rows?: number | null;
  n_positive?: number | null;
  n_predicted_positive?: number | null;
}

export interface SelfLearningRun {
  run_id: string;
  started_at?: string | null;
  completed_at?: string | null;
  status: string;
  reason?: string;
  champion_model_id?: string | null;
  challenger_model_id?: string | null;
  readiness?: {
    training_outcomes?: number | null;
    historical_outcomes?: number | null;
    live_outcomes?: number | null;
    recent_outcomes?: number | null;
    positive_events?: number | null;
    new_outcomes?: number | null;
    min_training_outcomes?: number | null;
    min_positive_events?: number | null;
    min_new_outcomes?: number | null;
    recent_window_days?: number | null;
    recent_sample_weight?: number | null;
  } | null;
  threshold?: number | null;
  champion_metrics?: SelfLearningMetrics | null;
  challenger_metrics?: SelfLearningMetrics | null;
  gate?: {
    passed?: boolean;
    checks?: Record<string, {
      actual?: number | null;
      required?: number | null;
      minimum?: number | null;
      maximum?: number | null;
      passed?: boolean;
    }>;
  } | null;
  report_path?: string | null;
  promotion?: {
    auto_promote?: boolean;
    promoted?: boolean;
    requires_human_approval?: boolean;
  } | null;
}

export interface SelfLearningStatus {
  enabled: boolean;
  check_interval_cycles: number;
  status: string;
  champion_model_id: string;
  current_scanner_model_id: string;
  predictions: number;
  outcomes: number;
  new_outcomes?: number;
  pending: number;
  excluded: number;
  materialized_positive: number;
  training_outcomes?: number;
  historical_outcomes?: number;
  live_outcomes?: number;
  training_positive_events?: number;
  recent_outcomes?: number;
  recent_window_days?: number;
  recent_sample_weight?: number;
  min_training_outcomes: number;
  min_new_outcomes: number;
  min_positive_events: number;
  latest_outcome_time?: string | null;
  last_run_at?: string | null;
  last_training_outcome_count?: number | null;
  last_report_path?: string | null;
  last_challenger_model_id?: string | null;
  latest_run?: SelfLearningRun | null;
  recent_runs?: SelfLearningRun[];
}

export interface SystemHistoryData {
  generated_at: string;
  db_path?: string;
  freshness?: Record<string, { max_time?: string | null; row_count?: number | null }>;
  data_stats: DataStat[];
  scanner: {
    heartbeat: Record<string, any>;
    runtime_state: Record<string, any>;
    scan_mode: string;
    last_cycle: {
      last_scan_time?: string | null;
      cycle?: number | null;
      n_symbols?: number;
      n_alerts?: number;
    };
    scan_per_day: ScanPerDay[];
  };
  signals_per_day: SignalPerDay[];
  models: ModelProgress[];
  experiments: {
    total: number;
    latest: LatestExperiment | null;
  };
  current_scanner_model_id: string;
  self_learning: SelfLearningStatus;
}
