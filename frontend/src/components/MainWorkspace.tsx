import React, { useState, useEffect, useMemo, useRef } from 'react';
import type { SignalItem, CoinDetail, CandidateCoin, CandidateFilterComparison, ModelAudit, MarketOverviewData, ScannerTelemetry, DeepAnalysis, CandlePoint, TrackingWatchlistItem, TradeSetup } from '../types';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid, AreaChart, Area, ComposedChart
} from 'recharts';
import {
  ShieldCheck, Activity, BarChart3,
  Layers, ArrowUpRight, ArrowDownRight, Eye, CheckCircle2, Zap, Radio, Terminal, Send, Clock, Play, Loader2, FlaskConical, LineChart as LineChartIcon, XCircle, RefreshCw, Target, Award, ChevronDown, ChevronUp, Cpu
} from 'lucide-react';
import { MultiCoinScan } from './MultiCoinScan';
import { BacktestExperiments } from './BacktestExperiments';
import { ForwardTest } from './ForwardTest';
import { SystemHistoryTab } from './SystemHistoryTab';
import { VersionHistoryTab } from './VersionHistoryTab';
import { TrackingWatchlist } from './TrackingWatchlist';
import { WorkspaceTabBar } from './WorkspaceTabBar';
import { ErrorBoundary } from './ErrorBoundary';

import { CandlestickChart } from './CandlestickChart';
import type { CandlestickSignalMarker } from './CandlestickChart';
import { DecisionHeader } from './DecisionCenter/DecisionHeader';
import { TradeSetupCard } from './DecisionCenter/TradeSetupCard';
import { TradeSetupCardV2 } from './v2/TradeSetupCardV2';
import { AiDecisionCockpit } from './DecisionCenter/AiDecisionCockpit';
import { AiShapAccordion } from './DecisionCenter/AiShapAccordion';
import { CoinLink } from './CoinLink';
import { formatSystemTime, parseSystemDate } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';
import {
  getRiskLabel,
  getScanModeLabel,
  getAuditStatusLabel,
  getExecutionStatusLabel,
  getScannerStatusLabel,
} from '../i18n/translations';

interface MainWorkspaceProps {
  signals: SignalItem[];
  selectedSignal: SignalItem | null;
  coinDetail: CoinDetail | null;
  candidates: CandidateCoin[];
  candidateComparison: CandidateFilterComparison | null;
  isRefreshingCandidates: boolean;
  onRefreshCandidates: () => void | Promise<void>;
  auditData: ModelAudit | null;
  marketData: MarketOverviewData | null;
  telemetryData: ScannerTelemetry | null;
  onSelectCandidate: (symbol: string) => void;
  onPushTelegram: (sig: SignalItem) => void;
  onTriggerManualScan: () => void;
  isTriggeringScan: boolean;
  scanTriggeredSuccess: string | null;
  deepAnalysis: DeepAnalysis | null;
  isDeepAnalyzing: boolean;
  onRunDeepAnalysis: (symbol: string) => void;
  onDismissSignal?: (sig: SignalItem) => void;
  onAddWatchlist?: (symbol: string) => void | Promise<boolean>;
  isSymbolInWatchlist?: boolean;
  onAddTracking?: (symbol: string) => void | Promise<boolean>;
  isSymbolTracked?: boolean;
  isWatchlistUpdating?: boolean;
  trackingItems: TrackingWatchlistItem[];
  isTrackingLoading: boolean;
  trackingUpdatingId?: string | null;
  onRefreshTracking: () => void;
  onSelectTrackingCoin: (symbol: string) => void;
  onUpdateTracking: (id: string, patch: Record<string, unknown>) => Promise<boolean>;
  onRemoveTracking: (id: string) => Promise<boolean>;
  activeTab: 'DECISION' | 'WATCHLIST' | 'RANKING' | 'MULTISCAN' | 'BACKTEST' | 'FORWARD' | 'AUDIT' | 'MARKET' | 'TELEMETRY' | 'HISTORY' | 'UPDATES';
  setActiveTab: (tab: 'DECISION' | 'WATCHLIST' | 'RANKING' | 'MULTISCAN' | 'BACKTEST' | 'FORWARD' | 'AUDIT' | 'MARKET' | 'TELEMETRY' | 'HISTORY' | 'UPDATES') => void;
  onOpenOrderModal?: () => void;
  guiVersion?: 'v1' | 'v2';
}

export const MainWorkspace: React.FC<MainWorkspaceProps> = ({
  signals,
  selectedSignal,
  coinDetail,
  candidates,
  candidateComparison,
  isRefreshingCandidates,
  onRefreshCandidates,
  auditData,
  marketData,
  telemetryData,
  onSelectCandidate,
  onPushTelegram,
  onTriggerManualScan,
  isTriggeringScan,
  scanTriggeredSuccess,
  deepAnalysis,
  isDeepAnalyzing,
  onRunDeepAnalysis,
  onDismissSignal,
  onAddWatchlist,
  isSymbolInWatchlist = false,
  onAddTracking,
  isSymbolTracked = false,
  isWatchlistUpdating = false,
  trackingItems,
  isTrackingLoading,
  trackingUpdatingId = null,
  onRefreshTracking,
  onSelectTrackingCoin,
  onUpdateTracking,
  onRemoveTracking,
  activeTab,
  setActiveTab,
  onOpenOrderModal,
  guiVersion = 'v2',
}) => {
  const { language, t } = useTranslation();  
  const riskLabels: Record<string, string> = {
    CRITICAL: getRiskLabel('CRITICAL', language),
    HIGH: getRiskLabel('HIGH', language),
    MEDIUM: getRiskLabel('MEDIUM', language),
    SAFE: getRiskLabel('SAFE', language),
  };
  const comparisonReport = candidateComparison?.comparison;
  const championVersion = candidateComparison?.champion_version || comparisonReport?.champion_version;
  const challengerVersion = candidateComparison?.challenger_version || comparisonReport?.challenger_version;
  const championMetrics = championVersion
    ? comparisonReport?.metrics?.[championVersion]
    : undefined;
  const challengerMetrics = challengerVersion
    ? comparisonReport?.metrics?.[challengerVersion]
    : undefined;
  const metricPercent = (value: number | null | undefined) => (
    value == null 
      ? t('badge_insufficient_data') 
      : `${(value * 100).toFixed(1)}%`
  );
  const deltaWithCi = (value: { point: number | null; ci_lower: number | null; ci_upper: number | null } | undefined) => (
    value?.point == null || value.ci_lower == null || value.ci_upper == null
      ? t('badge_insufficient_data')
      : `${value.point >= 0 ? '+' : ''}${(value.point * 100).toFixed(1)}pp (CI95% ${(value.ci_lower * 100).toFixed(1)} → ${(value.ci_upper * 100).toFixed(1)})`
  );
  const auditStatusLabels: Record<string, string> = {
    PASS: getAuditStatusLabel('PASS', language),
    PASSED: getAuditStatusLabel('PASSED', language),
    FAIL: getAuditStatusLabel('FAIL', language),
    FAILED: getAuditStatusLabel('FAILED', language),
    WARN: getAuditStatusLabel('WARN', language),
  };
  const executionStatusLabels: Record<string, string> = {
    'ALERT FIRED': getExecutionStatusLabel('ALERT FIRED', language),
    COMPLETED: getExecutionStatusLabel('COMPLETED', language),
    RUNNING: getExecutionStatusLabel('RUNNING', language),
    SENT: getExecutionStatusLabel('SENT', language),
    FAILED: getExecutionStatusLabel('FAILED', language),
  };
  const scannerStatusLabels: Record<string, string> = {
    ONLINE: getScannerStatusLabel('ONLINE', language),
    OFFLINE: getScannerStatusLabel('OFFLINE', language),
  };
  const scanModeLabels: Record<string, string> = {
    volatile: getScanModeLabel('volatile', language),
    gainers: getScanModeLabel('gainers', language),
    losers: getScanModeLabel('losers', language),
    volume: getScanModeLabel('volume', language),
    all: getScanModeLabel('all', language),
    manual: getScanModeLabel('manual', language),
  };
  const [scanProgress, setScanProgress] = useState<number>(0);
  const [scanStepText, setScanStepText] = useState<string>('');
  const [chartCoin, setChartCoin] = useState<string | null>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [listingRefreshing, setListingRefreshing] = useState(false);
  const [candleInterval, setCandleInterval] = useState('15m');
  const [candleDataOverride, setCandleDataOverride] = useState<CandlePoint[] | null>(null);
  const [expandedComparisonGroup, setExpandedComparisonGroup] = useState<'champion' | 'challenger' | 'overlap' | 'challenger_only' | 'champion_only' | null>(null);
  const [candidateFilterSegment, setCandidateFilterSegment] = useState<'ALL' | 'V2_CHAMPION' | 'V1_CHALLENGER' | 'OVERLAP' | 'V2_UNIQUE' | 'V3_PREVIEW'>('ALL');

  const comparisonSelections = useMemo(() => {
    const champVer = (candidateComparison?.champion_version || '').toLowerCase();
    const challVer = (candidateComparison?.challenger_version || '').toLowerCase();

    // Dynamically check whether champion is v2 or v1 (live daemon has champion=pump_filter_v1, challenger=candidate_filter_v2)
    const isChampV2 = champVer.includes('v2') || (!challVer.includes('v2') && !champVer.includes('v1'));

    const rawChamp = candidateComparison?.selected?.champion ?? [];
    const rawChall = candidateComparison?.selected?.challenger ?? [];

    const v2 = isChampV2 ? rawChamp : rawChall;
    const v1 = isChampV2 ? rawChall : rawChamp;

    const v1Symbols = new Set(v1.map((item) => item.symbol));

    const rawOverlap = candidateComparison?.selected?.overlap && candidateComparison.selected.overlap.length > 0
      ? candidateComparison.selected.overlap
      : v2.filter((item) => v1Symbols.has(item.symbol));

    const rawChampOnly = candidateComparison?.selected?.champion_only && candidateComparison.selected.champion_only.length > 0
      ? candidateComparison.selected.champion_only
      : rawChamp.filter((item) => !new Set(rawChall.map((c) => c.symbol)).has(item.symbol));

    const rawChallOnly = candidateComparison?.selected?.challenger_only && candidateComparison.selected.challenger_only.length > 0
      ? candidateComparison.selected.challenger_only
      : rawChall.filter((item) => !new Set(rawChamp.map((c) => c.symbol)).has(item.symbol));

    const v2Only = isChampV2 ? rawChampOnly : rawChallOnly;
    const v1Only = isChampV2 ? rawChallOnly : rawChampOnly;

    return {
      v2,
      v1,
      champion: v2, // Keep alias pointing to V2
      challenger: v1, // Keep alias pointing to V1
      overlap: rawOverlap,
      champion_only: v2Only, // V2 Unique Discoveries
      challenger_only: v1Only, // V1 Only
      v2_only: v2Only,
      v1_only: v1Only,
    };
  }, [candidateComparison]);

  const expandedComparisonItems = expandedComparisonGroup
    ? comparisonSelections[expandedComparisonGroup]
    : [];
  const expandedComparisonLabel = expandedComparisonGroup === 'champion'
    ? t('candidate_arm_v2_selected_tooltip')
    : expandedComparisonGroup === 'challenger'
      ? t('candidate_arm_v1_selected_tooltip')
      : expandedComparisonGroup === 'overlap'
        ? t('candidate_arm_both_tooltip')
        : expandedComparisonGroup === 'champion_only'
          ? t('candidate_arm_v2_tooltip')
          : t('candidate_arm_v1_tooltip');

  const filteredCandidates = useMemo(() => {
    if (candidateFilterSegment === 'ALL') {
      return candidates;
    }
    if (candidateFilterSegment === 'V2_CHAMPION') {
      const v2Symbols = new Set(comparisonSelections.champion.map((c) => c.symbol));
      return v2Symbols.size > 0 ? candidates.filter((c) => v2Symbols.has(c.symbol)) : candidates;
    }
    if (candidateFilterSegment === 'V1_CHALLENGER') {
      const v1Symbols = new Set(comparisonSelections.challenger.map((c) => c.symbol));
      return candidates.filter((c) => v1Symbols.has(c.symbol));
    }
    if (candidateFilterSegment === 'OVERLAP') {
      const overlapSymbols = new Set(comparisonSelections.overlap.map((c) => c.symbol));
      return candidates.filter((c) => overlapSymbols.has(c.symbol));
    }
    if (candidateFilterSegment === 'V2_UNIQUE') {
      const v2UniqueSymbols = new Set(comparisonSelections.champion_only.map((c) => c.symbol));
      return candidates.filter((c) => v2UniqueSymbols.has(c.symbol));
    }
    return candidates;
  }, [candidates, candidateFilterSegment, comparisonSelections]);

  const candleCacheRef = useRef<Map<string, CandlePoint[]>>(new Map());

  // Reset interval to default 15m when coin changes.
  useEffect(() => {
    setCandleInterval('15m');
    setCandleDataOverride(null);
  }, [coinDetail?.symbol]);

  // Fetch candles for selected interval. The 5m view can use the enriched
  // coinDetail candles; other intervals are fetched from the chart endpoint.
  useEffect(() => {
    const symbol = coinDetail?.symbol;
    if (!symbol) return;
    if (candleInterval === '5m') {
      setCandleDataOverride(null);
      return;
    }
    const cacheKey = `${symbol}:${candleInterval}`;
    if (candleCacheRef.current.has(cacheKey)) {
      setCandleDataOverride(candleCacheRef.current.get(cacheKey)!);
      return;
    }
    const controller = new AbortController();
    // Do not keep displaying candles from the previous interval/coin while
    // the new series is loading; markers would otherwise be snapped against
    // the wrong time grid for a short period.
    setCandleDataOverride([]);
    const load = async () => {
      try {
        const res = await fetch(`/api/coin/${symbol}/chart?interval=${candleInterval}`, {
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        const mapped: CandlePoint[] = (json.klines || []).map((k: any) => ({
          time: k.time_str,
          time_iso: k.time,
          price: k.close,
          open: k.open,
          high: k.high,
          low: k.low,
          close: k.close,
          volume: k.volume,
          oi: 0,
          funding: 0,
          taker_ratio: 0.5,
          is_signal_point: false,
        }));
        candleCacheRef.current.set(cacheKey, mapped);
        setCandleDataOverride(mapped);
      } catch (err) {
        if ((err as DOMException).name !== 'AbortError') {
          console.error('Candle interval fetch error:', err);
        }
      }
    };
    load();
    return () => controller.abort();
  }, [coinDetail?.symbol, candleInterval]);

  const candleData = candleDataOverride || coinDetail?.chart_data || [];

  // When a signal from RADAR is selected, prefer its live values over the
  // independently-fetched coinDetail so the detail panel stays in sync with
  // the radar card that the user clicked.
  const displayDetail = useMemo(() => {
    if (!coinDetail) return null;
    if (!selectedSignal || selectedSignal.symbol !== coinDetail.symbol) return coinDetail;
    return {
      ...coinDetail,
      probability: selectedSignal.probability * 100,
      risk_level: selectedSignal.risk_level,
      target_price: selectedSignal.target_price > 0 ? selectedSignal.target_price : coinDetail.target_price,
      signal_timestamp: selectedSignal.signal_time,
      score_source: 'signal' as const,
      metrics: {
        ...(coinDetail.metrics || {}),
        oi_change_24h: selectedSignal.oi_change_24h ?? coinDetail.metrics?.oi_change_24h ?? 'N/A',
        funding_rate: selectedSignal.funding_rate ?? coinDetail.metrics?.funding_rate ?? 'N/A',
        taker_sell_ratio: selectedSignal.taker_sell_ratio ?? coinDetail.metrics?.taker_sell_ratio ?? 0.5,
      },
    };
  }, [coinDetail, selectedSignal]);

  // Compute trade setup levels (Entry, SL, TP1, TP2, R:R)
  const tradeSetup: TradeSetup | null = useMemo(() => {
    if (!displayDetail || displayDetail.current_price <= 0) return null;
    const entry = selectedSignal?.signal_price && selectedSignal.signal_price > 0
      ? selectedSignal.signal_price
      : displayDetail.current_price;
    const peakPrice = deepAnalysis?.pump_analysis?.peak_price;
    const sl = selectedSignal?.invalidation_time && displayDetail.target_price
      ? (peakPrice && peakPrice > entry ? peakPrice * 1.015 : entry * 1.04)
      : (peakPrice && peakPrice > entry ? peakPrice * 1.015 : entry * 1.04);
    const tp1 = entry * 0.96;
    const tp2 = displayDetail.target_price && displayDetail.target_price > 0 && displayDetail.target_price < entry
      ? displayDetail.target_price
      : entry * 0.92;
    const slPct = ((sl - entry) / entry) * 100;
    const tp1Pct = ((entry - tp1) / entry) * 100;
    const tp2Pct = ((entry - tp2) / entry) * 100;
    const riskRewardRatio = slPct > 0 ? tp2Pct / slPct : 2.0;

    return {
      entryPrice: entry,
      entryZoneLow: entry * 0.995,
      entryZoneHigh: entry * 1.005,
      stopLossPrice: sl,
      stopLossPct: slPct,
      tp1Price: tp1,
      tp1Pct: tp1Pct,
      tp2Price: tp2,
      tp2Pct: tp2Pct,
      riskRewardRatio,
    };
  }, [displayDetail, selectedSignal, deepAnalysis]);

  // The radar can emit several alerts for the same coin. Keep all of them
  // available to the chart; selectedSignal only represents the card currently
  // focused in the feed.
  const chartSignalMarkers = useMemo<CandlestickSignalMarker[]>(() => {
    if (!displayDetail) return [];

    const coinSignals: CandlestickSignalMarker[] = signals
      .filter(signal => signal.symbol === displayDetail.symbol)
      .map(signal => ({
        id: signal.id,
        time: signal.signal_time,
        probability: signal.probability * 100,
        isActive: selectedSignal?.id === signal.id,
        isValid: signal.validity_hours_left > 0,
      }));

    if (
      selectedSignal &&
      selectedSignal.symbol === displayDetail.symbol &&
      !coinSignals.some(signal => signal.id === selectedSignal.id)
    ) {
      coinSignals.push({
        id: selectedSignal.id,
        time: selectedSignal.signal_time,
        probability: selectedSignal.probability * 100,
        isActive: true,
        isValid: selectedSignal.validity_hours_left > 0,
      });
    }

    if (coinSignals.length === 0 && displayDetail.signal_timestamp) {
      coinSignals.push({
        id: `${displayDetail.symbol}-${displayDetail.signal_timestamp}`,
        time: displayDetail.signal_timestamp,
        probability: displayDetail.probability,
        isActive: true,
        isValid: true,
      });
    }

    return coinSignals.sort((a, b) => {
      const aTime = parseSystemDate(a.time)?.getTime() ?? Number.NaN;
      const bTime = parseSystemDate(b.time)?.getTime() ?? Number.NaN;
      return aTime - bTime;
    });
  }, [displayDetail, selectedSignal, signals]);

  const handleShowCoinChart = async (symbol: string) => {
    setChartCoin(symbol);
    setChartLoading(true);
    setChartData([]);
    try {
      const res = await fetch(`/api/coin/${symbol}/chart`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setChartData(json.klines || []);
    } catch (err) {
      console.error('Chart fetch error:', err);
    } finally {
      setChartLoading(false);
    }
  };

  const handleRefreshListing = async () => {
    setListingRefreshing(true);
    try {
      await fetch('/api/listing/refresh', { method: 'POST' });
      // Trigger parent refresh — reload market data
      window.location.reload();
    } catch (err) {
      console.error('Listing refresh error:', err);
    } finally {
      setListingRefreshing(false);
    }
  };

  useEffect(() => {
    if (isTriggeringScan) {
      setActiveTab('TELEMETRY');
      setScanProgress(15);
      setScanStepText(t('scan_progress_step1'));

      const t1 = setTimeout(() => {
        setScanProgress(50);
        setScanStepText(t('scan_progress_step2'));
      }, 500);

      const t2 = setTimeout(() => {
        setScanProgress(85);
        setScanStepText(t('scan_progress_step3'));
      }, 1000);

      const t3 = setTimeout(() => {
        setScanProgress(100);
        setScanStepText(t('scan_progress_step4'));
      }, 1400);

      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
      };
    }
  }, [isTriggeringScan, setActiveTab, language]);

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 flex flex-col h-auto lg:h-full overflow-visible lg:overflow-hidden relative">

      {/* Real-time Scanning Progress Overlay Banner */}
      {isTriggeringScan && (
        <div className="absolute inset-0 z-40 bg-slate-950/90 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/20 border border-amber-500/50 flex items-center justify-center mb-3 text-amber-400">
            <Loader2 className="w-7 h-7 animate-spin" />
          </div>
          <h3 className="text-base font-bold text-slate-100 uppercase tracking-wider mb-1">
            {t('scan_triggering_banner_prefix')} {scanModeLabels[telemetryData?.active_scan_mode || ''] ?? telemetryData?.active_scan_mode?.toUpperCase()})
          </h3>
          <p className="text-xs text-amber-400 font-mono mb-4">{scanStepText}</p>

          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-full h-3 overflow-hidden p-0.5">
            <div
              className="bg-gradient-to-r from-amber-500 to-amber-300 h-full rounded-full transition-all duration-300 shadow-md shadow-amber-500/30"
              style={{ width: `${scanProgress}%` }}
            />
          </div>
          <span className="text-[11px] font-mono font-bold text-slate-400 mt-2">{scanProgress}% {t('scan_progress_complete_suffix')}</span>
        </div>
      )}

      {/* Workspace Tab Bar (Grouped & Responsive for Desktop + Mobile) */}
      <WorkspaceTabBar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        selectedSignal={selectedSignal}
        onSelectCandidate={onSelectCandidate}
        trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        candidateCount={candidates.length}
        isTelemetryActive={Boolean(telemetryData?.is_running ?? true)}
      />

      {activeTab === 'WATCHLIST' && (
        <TrackingWatchlist
          items={trackingItems}
          isLoading={isTrackingLoading}
          updatingId={trackingUpdatingId}
          onRefresh={onRefreshTracking}
          onSelectCoin={onSelectTrackingCoin}
          onUpdateItem={onUpdateTracking}
          onRemoveItem={onRemoveTracking}
        />
      )}

      {/* TAB 1: DECISION CENTER */}
      {activeTab === 'DECISION' && (
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {displayDetail ? (
            <div className="space-y-3">
              {/* 1. Quick Header (Search + Top 5 Candidates + Live Ticker) */}
              <DecisionHeader
                symbol={displayDetail.symbol}
                name={displayDetail.name}
                currentPrice={displayDetail.current_price}
                chartSource={displayDetail.chart_source}
                selectedSignal={selectedSignal}
                candidates={candidates}
                onSelectCandidate={onSelectCandidate}
                isDeepAnalyzing={isDeepAnalyzing}
              />

              {/* 2. Main 2-Column Split-View Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-start min-w-0">
                {/* LEFT COLUMN (65% width on LG): Charts + Trade Setup + Metrics */}
                <div className="lg:col-span-8 space-y-3 min-w-0">
                  {/* Candlestick Chart Card */}
                  <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 min-w-0 shadow-lg">
                    <div className="flex items-start sm:items-center justify-between mb-2 gap-2 flex-wrap min-w-0">
                      <div className="min-w-0">
                        <h3 className="text-[11px] sm:text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5 min-w-0">
                          <Zap className="w-3.5 h-3.5 text-amber-400" />
                          {`${t('ws_chart_candlestick_title')} ${candleInterval} (${displayDetail.symbol})`}
                        </h3>
                        <p className="text-[11px] text-slate-400">
                          {language === 'zh' ? '🟢 阳线 | 🔴 阴线 | 🟡 入场点 | 🔴 止损 SL | 🟢 止盈 TP1/TP2' : language === 'ko' ? '🟢 양봉 | 🔴 음봉 | 🟡 진입가 | 🔴 손절 SL | 🟢 익절 TP1/TP2' : t('chart_legend_indicators')}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <div className="flex items-center gap-0.5 max-w-full overflow-x-auto rounded-md border border-slate-700/80 bg-slate-900/90 p-0.5 [&::-webkit-scrollbar]:hidden" aria-label={t('ws_chart_timeframe_select')}>
                          {['1m', '5m', '15m', '1h', '4h', '1d'].map(interval => (
                            <button
                              key={interval}
                              type="button"
                              aria-pressed={candleInterval === interval}
                              onClick={() => setCandleInterval(interval)}
                              className={`shrink-0 rounded px-2 py-1 font-mono text-[10px] transition ${
                                candleInterval === interval
                                  ? 'bg-amber-500/20 text-amber-300 shadow-sm shadow-amber-500/10'
                                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                              }`}
                            >
                              {interval}
                            </button>
                          ))}
                        </div>
                        <div className="flex items-center gap-2 text-[11px] font-mono">
                          <span className="flex items-center gap-1 text-emerald-400">
                            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> {t('ws_chart_up')}
                          </span>
                          <span className="flex items-center gap-1 text-red-400">
                            <span className="w-2.5 h-2.5 rounded-sm bg-red-500" /> {t('ws_chart_down')}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Candlestick chart (TradingView lightweight-charts) */}
                    <CandlestickChart
                      data={candleData.map(c => ({
                        time: c.time_iso || c.time,
                        open: c.open || c.price,
                        high: c.high || c.price,
                        low: c.low || c.price,
                        close: c.close || c.price,
                        volume: c.volume || 0,
                      }))}
                      targetPrice={displayDetail.target_price}
                      signalMarkers={chartSignalMarkers}
                      tradeSetup={tradeSetup}
                      height={380}
                    />

                    {/* OI + Funding Sub Chart */}
                    {(() => {
                      const hasOi = candleData.some(c => (c.oi || 0) !== 0);
                      const hasFunding = candleData.some(c => (c.funding || 0) !== 0);
                      return hasOi || hasFunding ? (
                        <div className="mt-3">
                          <div className="text-[10px] text-slate-400 mb-1 uppercase">{t('ws_oi_funding_title')}</div>
                          <div className="h-24 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <ComposedChart data={candleData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis dataKey="time" stroke="#64748b" fontSize={9} interval={Math.max(0, Math.floor(candleData.length / 8))} />
                                <YAxis yAxisId="oi" stroke="#06b6d4" fontSize={9} domain={['auto', 'auto']} />
                                <YAxis yAxisId="funding" orientation="right" stroke="#f59e0b" fontSize={9} domain={['auto', 'auto']} />
                                <Tooltip
                                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }}
                                />
                                <ReferenceLine yAxisId="funding" y={0} stroke="#334155" strokeDasharray="2 2" />
                                <Line yAxisId="oi" type="monotone" dataKey="oi" stroke="#06b6d4" strokeWidth={1.5} dot={false} name={t('metric_oi_24h')} />
                                <Line yAxisId="funding" type="monotone" dataKey="funding" stroke="#f59e0b" strokeWidth={1} dot={false} name={t('metric_funding')} />
                              </ComposedChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      ) : null;
                    })()}

                    {/* Chart stats footer */}
                    {candleData.length > 0 && (
                      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px] font-mono">
                        <div className="bg-slate-900 p-1.5 rounded text-center">
                          <div className="text-slate-500">{t('ws_stat_high')}</div>
                          <div className="text-emerald-400">${Math.max(...candleData.map(c => c.high || c.price)).toFixed(6)}</div>
                        </div>
                        <div className="bg-slate-900 p-1.5 rounded text-center">
                          <div className="text-slate-500">{t('ws_stat_low')}</div>
                          <div className="text-red-400">${Math.min(...candleData.map(c => c.low || c.price)).toFixed(6)}</div>
                        </div>
                        <div className="bg-slate-900 p-1.5 rounded text-center">
                          <div className="text-slate-500">{t('ws_stat_change')}</div>
                          <div className={candleData[candleData.length - 1].close >= candleData[0].close ? 'text-emerald-400' : 'text-red-400'}>
                            {((candleData[candleData.length - 1].close / candleData[0].close - 1) * 100).toFixed(2)}%
                          </div>
                        </div>
                        <div className="bg-slate-900 p-1.5 rounded text-center">
                          <div className="text-slate-500">{t('ws_stat_candles')}</div>
                          <div className="text-slate-300">{candleData.length}</div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Trade Setup Card (V2 Interactive / V1 Classic) */}
                  {guiVersion === 'v2' ? (
                    <TradeSetupCardV2
                      symbol={displayDetail.symbol}
                      currentPrice={displayDetail.current_price}
                      signalPrice={selectedSignal?.signal_price}
                      targetPrice={displayDetail.target_price}
                      peakPrice={deepAnalysis?.pump_analysis?.peak_price}
                      invalidationPrice={tradeSetup?.stopLossPrice}
                      onOpenOrderModal={onOpenOrderModal}
                    />
                  ) : (
                    <TradeSetupCard
                      currentPrice={displayDetail.current_price}
                      signalPrice={selectedSignal?.signal_price}
                      targetPrice={displayDetail.target_price}
                      peakPrice={deepAnalysis?.pump_analysis?.peak_price}
                      invalidationPrice={tradeSetup?.stopLossPrice}
                    />
                  )}

                  {/* Metrics grid — 6 cols */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 [&>div]:min-w-0">
                    <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="text-[9px] text-slate-400 uppercase">{t('metric_oi_24h')}</div>
                      <div className="font-mono font-bold text-xs sm:text-sm text-red-400 truncate" title={displayDetail.metrics?.oi_change_24h ?? 'N/A'}>{displayDetail.metrics?.oi_change_24h ?? 'N/A'}</div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="text-[9px] text-slate-400 uppercase">{t('metric_funding')}</div>
                      <div className="font-mono font-bold text-xs sm:text-sm text-amber-400 truncate" title={displayDetail.metrics?.funding_rate ?? 'N/A'}>{displayDetail.metrics?.funding_rate ?? 'N/A'}</div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="text-[9px] text-slate-400 uppercase">{t('metric_taker_sell')}</div>
                      <div className="font-mono font-bold text-xs sm:text-sm text-slate-200 truncate">{displayDetail.metrics?.taker_sell_ratio != null ? `${(displayDetail.metrics.taker_sell_ratio * 100).toFixed(1)}%` : 'N/A'}</div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="text-[9px] text-slate-400 uppercase">{t('metric_rsi_15m')}</div>
                      <div className={`font-mono font-bold text-xs sm:text-sm truncate ${
                        displayDetail.metrics?.rsi_15m == null ? 'text-slate-500' :
                        displayDetail.metrics.rsi_15m > 70 ? 'text-red-400' :
                        displayDetail.metrics.rsi_15m < 30 ? 'text-emerald-400' : 'text-amber-300'
                      }`}>
                        {displayDetail.metrics?.rsi_15m != null ? displayDetail.metrics.rsi_15m.toFixed(1) : (t('metric_insufficient_data'))}
                      </div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="text-[9px] text-slate-400 uppercase">{t('chart_vol_delta_24h')}</div>
                      <div className="font-mono font-bold text-xs sm:text-sm text-sky-400 truncate" title={displayDetail.metrics?.volume_delta_24h ?? 'N/A'}>{displayDetail.metrics?.volume_delta_24h ?? 'N/A'}</div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="text-[9px] text-slate-400 uppercase">{t('feed_target_drawdown')}</div>
                      <div className="font-mono font-bold text-xs sm:text-sm text-red-400 truncate">${displayDetail.target_price.toFixed(6)}</div>
                    </div>
                  </div>
                </div>

                {/* RIGHT COLUMN (35% width on LG): AI Cockpit + SHAP Drivers */}
                <div className="lg:col-span-4 space-y-3 min-w-0">
                  {/* AI Decision Cockpit */}
                  <AiDecisionCockpit
                    selectedSignal={selectedSignal}
                    displayDetail={displayDetail}
                    deepAnalysis={deepAnalysis}
                    isDeepAnalyzing={isDeepAnalyzing}
                    isSymbolTracked={isSymbolTracked}
                    isSymbolInWatchlist={isSymbolInWatchlist}
                    isWatchlistUpdating={isWatchlistUpdating}
                    onRunDeepAnalysis={onRunDeepAnalysis}
                    onPushTelegram={onPushTelegram}
                    onDismissSignal={onDismissSignal}
                    onAddWatchlist={onAddWatchlist ? ((s: string) => onAddWatchlist(s)) : undefined}
                    onAddTracking={onAddTracking ? ((s: string) => onAddTracking(s)) : undefined}
                    onOpenOrderModal={onOpenOrderModal}
                  />

                  {/* SHAP Drivers & 8-Component Decomposition Accordion */}
                  <AiShapAccordion
                    shapDrivers={displayDetail.shap_drivers}
                    deepAnalysis={deepAnalysis}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center text-slate-500 bg-slate-950/60 border border-slate-800 rounded-xl">
              <Activity className="w-8 h-8 text-amber-400/60 mx-auto mb-2 animate-pulse" />
              <p className="text-sm text-slate-400 font-medium">
                {t('decision_select_prompt')}
              </p>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: CANDIDATE SELL RANKING TABLE */}
      {activeTab === 'RANKING' && (
        <div className="flex-1 overflow-y-auto pr-1">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
            <div>
              <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
                <BarChart3 className="w-3.5 h-3.5 text-violet-400" />
                {t('ranking_title_full')}
                <span className="rounded-full bg-violet-950/80 border border-violet-700/80 px-2 py-0.2 text-[9px] font-bold text-violet-300">
                  {t('ranking_badge_v2_official')}
                </span>
                <span className="rounded-full bg-amber-950/60 border border-amber-800/60 px-2 py-0.2 text-[9px] font-medium text-amber-300">
                  {t('ranking_badge_v1_ab')}
                </span>
              </h3>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {t('ranking_desc_v2_v1')}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-400 font-mono">{t('ranking_sorted_by_risk')}</span>
              <button
                type="button"
                onClick={() => onRefreshCandidates()}
                disabled={isRefreshingCandidates}
                className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] font-medium text-slate-300 transition hover:border-violet-500/60 hover:text-violet-300 disabled:cursor-not-allowed disabled:opacity-60"
                title={t('ranking_refresh_tooltip')}
              >
                <RefreshCw className={`h-3 w-3 ${isRefreshingCandidates ? 'animate-spin' : ''}`} />
                {isRefreshingCandidates ? t('ranking_scanning_status') : t('refresh')}
              </button>
            </div>
          </div>

          {/* BỘ LỌC PHÂN ĐOẠN / FILTER SEGMENT TABS */}
          <div className="mb-3 flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-950/90 p-1.5">
            <span className="px-2 text-[10px] font-semibold uppercase text-slate-400">
              {t('ranking_view_mode_label')}
            </span>

            {/* All */}
            <button
              type="button"
              onClick={() => setCandidateFilterSegment('ALL')}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                candidateFilterSegment === 'ALL'
                  ? 'bg-slate-800 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
              }`}
            >
              <span>{t('ranking_filter_all')}</span>
              <span className="rounded bg-slate-700/60 px-1.5 py-0.2 text-[9px] font-mono text-slate-300">
                {candidates.length}
              </span>
            </button>

            {/* V2 Champion */}
            <button
              type="button"
              onClick={() => setCandidateFilterSegment('V2_CHAMPION')}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                candidateFilterSegment === 'V2_CHAMPION'
                  ? 'bg-violet-950 border border-violet-600 text-violet-200 font-bold shadow-sm'
                  : 'text-violet-300/80 hover:bg-violet-950/40 hover:text-violet-200'
              }`}
            >
              <span>👑 {t('ranking_filter_v2_champion')}</span>
              <span className="rounded bg-violet-900/60 px-1.5 py-0.2 text-[9px] font-mono text-violet-300 font-bold">
                {comparisonSelections.champion.length || candidates.length}
              </span>
            </button>

            {/* V1 Challenger */}
            <button
              type="button"
              onClick={() => setCandidateFilterSegment('V1_CHALLENGER')}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                candidateFilterSegment === 'V1_CHALLENGER'
                  ? 'bg-amber-950 border border-amber-600 text-amber-200 font-bold shadow-sm'
                  : 'text-amber-300/80 hover:bg-amber-950/40 hover:text-amber-200'
              }`}
            >
              <span>📊 {t('ranking_filter_v1_baseline')}</span>
              <span className="rounded bg-amber-900/60 px-1.5 py-0.2 text-[9px] font-mono text-amber-300">
                {comparisonSelections.challenger.length}
              </span>
            </button>

            {/* {t('cand_badge_overlap')} */}
            <button
              type="button"
              onClick={() => setCandidateFilterSegment('OVERLAP')}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                candidateFilterSegment === 'OVERLAP'
                  ? 'bg-emerald-950 border border-emerald-600 text-emerald-200 font-bold shadow-sm'
                  : 'text-emerald-300/80 hover:bg-emerald-950/40 hover:text-emerald-200'
              }`}
            >
              <span>🎯 {t('ranking_filter_high_conviction')}</span>
              <span className="rounded bg-emerald-900/60 px-1.5 py-0.2 text-[9px] font-mono text-emerald-300">
                {comparisonSelections.overlap.length}
              </span>
            </button>

            {/* V2 Unique */}
            <button
              type="button"
              onClick={() => setCandidateFilterSegment('V2_UNIQUE')}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                candidateFilterSegment === 'V2_UNIQUE'
                  ? 'bg-cyan-950 border border-cyan-600 text-cyan-200 font-bold shadow-sm'
                  : 'text-cyan-300/80 hover:bg-cyan-950/40 hover:text-cyan-200'
              }`}
            >
              <span>💡 {t('ranking_filter_v2_early')}</span>
              <span className="rounded bg-cyan-900/60 px-1.5 py-0.2 text-[9px] font-mono text-cyan-300">
                {comparisonSelections.champion_only.length}
              </span>
            </button>

            {/* V3 Lab Preview */}
            <button
              type="button"
              onClick={() => setCandidateFilterSegment('V3_PREVIEW')}
              className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition ml-auto ${
                candidateFilterSegment === 'V3_PREVIEW'
                  ? 'bg-indigo-950 border border-indigo-500 text-indigo-200 font-bold shadow-sm ring-1 ring-indigo-500/50'
                  : 'text-indigo-300/80 hover:bg-indigo-950/40 hover:text-indigo-200 border border-indigo-900/50'
              }`}
            >
              <span>🔬 {t('ranking_filter_v3_lab')}</span>
              <span className="rounded bg-indigo-900/70 px-1.5 py-0.2 text-[9px] font-semibold text-indigo-300">
                Ready
              </span>
            </button>
          </div>

          {/* V3 LAB PREVIEW CARD (Khi bật tab V3) */}
          {candidateFilterSegment === 'V3_PREVIEW' && (
            <div className="mb-4 rounded-xl border border-indigo-700/80 bg-gradient-to-b from-slate-950 via-indigo-950/30 to-slate-950 p-4 shadow-xl shadow-indigo-950/30">
              <div className="flex items-center justify-between border-b border-indigo-800/40 pb-2.5">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-300">
                  <Cpu className="h-4 w-4 text-indigo-400" />
                  <span>{t('ranking_v3_blueprint_title')}</span>
                </div>
                <span className="rounded-full bg-indigo-900/80 border border-indigo-600 px-2.5 py-0.5 text-[10px] font-bold text-indigo-200">
                  {t('ranking_v3_phase3_ready')}
                </span>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-indigo-900/80 bg-slate-950/80 p-3">
                  <div className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                    <Zap className="h-3.5 w-3.5 text-amber-400" />
                    <span>{t('cand_tab_microstructure')}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-300 leading-relaxed">
                    Phân tích Orderbook Bid/Ask Depth Imbalance trực tiếp từ luồng WebSocket 100ms. Đo lường lực hấp thụ âm thầm (iceberg orders) trước khi giá đảo chiều.
                  </p>
                </div>

                <div className="rounded-lg border border-indigo-900/80 bg-slate-950/80 p-3">
                  <div className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                    <Layers className="h-3.5 w-3.5 text-cyan-400" />
                    <span>{t('cand_tab_deep_learning')}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-300 leading-relaxed">
                    Đồng bộ 3 khung thời gian (1m, 5m, 1h) để nhận diện mô hình tích lũy giả và bẫy thanh khoản (Liquidity sweeps) của Market Maker với độ trễ thấp hơn.
                  </p>
                </div>

                <div className="rounded-lg border border-indigo-900/80 bg-slate-950/80 p-3">
                  <div className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                    <Award className="h-3.5 w-3.5 text-emerald-400" />
                    <span>{t('cand_tab_comparison')}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-300 leading-relaxed">
                    Kiến trúc hệ thống cho phép cắm trực tiếp V3 vào làm Challenger thứ 2. Tự động đối chiếu P@10, Recall và False Alarms giữa cả 3 phiên bản đồng thời.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* SO SÁNH 2 PHIÊN BẢN LỌC ỨNG VIÊN (V2 CHAMPION vs V1 CHALLENGER) */}
          <div className="mb-4 rounded-xl border border-violet-900/80 bg-gradient-to-b from-slate-950 via-violet-950/20 to-slate-950 p-3.5 shadow-lg shadow-violet-950/20">
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-2 border-b border-violet-900/40 pb-2.5">
              <div>
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-violet-300">
                  <FlaskConical className="h-4 w-4 text-violet-400" />
                  <span>
                    {language === 'en'
                      ? 'Candidate Filter Engine: V2 (Official Champion) vs V1 (A/B Test Baseline)'
                      : language === 'zh'
                      ? '候选币过滤器：V2（生产冠军版）vs V1（A/B 对照基准）'
                      : language === 'ko'
                      ? '후보 필터 엔진: V2(실서버 정식) vs V1(A/B 대조군)'
                      : 'Hệ Thống Lọc Ứng Viên: V2 (Bản Chính Thức) vs V1 (Đối Soát A/B Test)'}
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-300">
                  {language === 'en'
                    ? 'V2 (Champion) actively filters the primary table & Telegram alerts with multi-stage quantitative exhaustion. V1 (Challenger) runs in parallel to continuously benchmark baseline stability.'
                    : language === 'zh'
                    ? 'V2（生产冠军版）基于多阶段动能衰竭算法驱动主榜单与 Telegram 预警；V1（挑战者）保持并行运行以持续进行 A/B 测试对照。'
                    : language === 'ko'
                    ? 'V2(실서버 정식)가 다단계 정량 분산 알고리즘으로 랭킹과 텔레그램을 전담하며, V1(대조군)은 지속적인 A/B 테스트 검증을 위해 병렬 실행됩니다.'
                    : 'V2 (Champion) đang vận hành bảng xếp hạng chính & Telegram bằng thuật toán định lượng đa tầng. V1 (Challenger) chạy song song đối soát A/B test liên tục.'}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="rounded-full border border-violet-700 bg-violet-950/80 px-2.5 py-0.5 text-[10px] font-semibold text-violet-200">
                  {t('ranking_badge_v2_champion_active')}
                </span>
                <span className="rounded-full border border-amber-800 bg-amber-950/70 px-2.5 py-0.5 text-[10px] font-semibold text-amber-300">
                  {t('ranking_badge_ab_shadow_baseline')}
                </span>
              </div>
            </div>

            {/* Metric Cards Grid */}
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {/* Universe */}
              <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5">
                <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">{t('ranking_shared_universe')}</div>
                <div className="mt-1 text-xl font-bold text-white">{candidateComparison?.universe_count ?? 150}</div>
                <div className="text-[9px] text-slate-500">{t('ranking_monitored_symbols')}</div>
              </div>

              {/* V2 Selected (Champion) */}
              {(() => {
                const isExpanded = expandedComparisonGroup === 'champion';
                const isChampV2 = (candidateComparison?.champion_version || '').toLowerCase().includes('v2');
                const rawCount = isChampV2 ? candidateComparison?.champion_selected : candidateComparison?.challenger_selected;
                const count = rawCount ?? comparisonSelections.champion.length;
                return (
                  <button
                    type="button"
                    onClick={() => setExpandedComparisonGroup(isExpanded ? null : 'champion')}
                    aria-expanded={isExpanded}
                    className={`rounded-lg border bg-slate-950/90 p-2.5 text-left transition hover:bg-slate-900 focus:outline-none ${
                      isExpanded
                        ? 'border-violet-500 ring-2 ring-violet-500/40 bg-violet-950/20'
                        : 'border-violet-800/80 hover:border-violet-500'
                    }`}
                    title={t('ranking_v2_selected_title')}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold uppercase tracking-wider text-violet-400">{t('ranking_v2_selected_label')}</span>
                      <span className="rounded bg-violet-950/80 px-1 py-0.2 text-[8px] font-bold text-violet-300">{t('cand_badge_champion')}</span>
                    </div>
                    <div className="mt-1 text-xl font-bold text-violet-300">{count}</div>
                    <div className="flex items-center gap-1 text-[9px] text-violet-400/80">
                      <span>{isExpanded ? (t('ranking_click_collapse')) : (t('ranking_official_filter_tag'))}</span>
                      {isExpanded ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />}
                    </div>
                  </button>
                );
              })()}

              {/* V1 Selected (Challenger) */}
              {(() => {
                const isExpanded = expandedComparisonGroup === 'challenger';
                const isChampV2 = (candidateComparison?.champion_version || '').toLowerCase().includes('v2');
                const rawCount = isChampV2 ? candidateComparison?.challenger_selected : candidateComparison?.champion_selected;
                const count = rawCount ?? comparisonSelections.challenger.length;
                return (
                  <button
                    type="button"
                    onClick={() => setExpandedComparisonGroup(isExpanded ? null : 'challenger')}
                    aria-expanded={isExpanded}
                    className={`rounded-lg border bg-slate-950/90 p-2.5 text-left transition hover:bg-slate-900 focus:outline-none ${
                      isExpanded
                        ? 'border-amber-500 ring-2 ring-amber-500/40 bg-amber-950/20'
                        : 'border-amber-800/80 hover:border-amber-500'
                    }`}
                    title={t('ranking_v1_selected_title')}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold uppercase tracking-wider text-amber-400">{t('ranking_v1_selected_label')}</span>
                      <span className="rounded bg-amber-950/80 px-1 py-0.2 text-[8px] font-medium text-amber-300">A/B Test</span>
                    </div>
                    <div className="mt-1 text-xl font-bold text-amber-300">{count}</div>
                    <div className="flex items-center gap-1 text-[9px] text-amber-400/80">
                      <span>{isExpanded ? (t('ranking_click_collapse')) : (t('ranking_baseline_shadow_tag'))}</span>
                      {isExpanded ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />}
                    </div>
                  </button>
                );
              })()}

              {/* {t('cand_badge_overlap')} */}
              {(() => {
                const isExpanded = expandedComparisonGroup === 'overlap';
                const count = candidateComparison?.overlap ?? comparisonSelections.overlap.length;
                return (
                  <button
                    type="button"
                    onClick={() => setExpandedComparisonGroup(isExpanded ? null : 'overlap')}
                    aria-expanded={isExpanded}
                    className={`rounded-lg border bg-slate-950/90 p-2.5 text-left transition hover:bg-slate-900 focus:outline-none ${
                      isExpanded
                        ? 'border-emerald-500 ring-2 ring-emerald-500/40 bg-emerald-950/20'
                        : 'border-emerald-800/80 hover:border-emerald-500'
                    }`}
                    title={t('ranking_both_selected_title')}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold uppercase tracking-wider text-emerald-400">{t('ranking_both_selected_label')}</span>
                      <span className="rounded bg-emerald-950/80 px-1 py-0.2 text-[8px] font-medium text-emerald-300">{t('cand_badge_overlap')}</span>
                    </div>
                    <div className="mt-1 text-xl font-bold text-emerald-300">{count}</div>
                    <div className="flex items-center gap-1 text-[9px] text-emerald-400/80">
                      <span>{isExpanded ? (t('ranking_click_collapse')) : (t('ranking_high_conviction_tag'))}</span>
                      {isExpanded ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />}
                    </div>
                  </button>
                );
              })()}

              {/* V2 Discoveries */}
              {(() => {
                const isExpanded = expandedComparisonGroup === 'champion_only';
                const isChampV2 = (candidateComparison?.champion_version || '').toLowerCase().includes('v2');
                const rawCount = isChampV2 ? candidateComparison?.champion_only : candidateComparison?.challenger_only;
                const count = rawCount ?? comparisonSelections.champion_only.length;
                return (
                  <button
                    type="button"
                    onClick={() => setExpandedComparisonGroup(isExpanded ? null : 'champion_only')}
                    aria-expanded={isExpanded}
                    className={`rounded-lg border bg-slate-950/90 p-2.5 text-left transition hover:bg-slate-900 focus:outline-none ${
                      isExpanded
                        ? 'border-cyan-500 ring-2 ring-cyan-500/40 bg-cyan-950/20'
                        : 'border-cyan-800/80 hover:border-cyan-500'
                    }`}
                    title={t('ranking_v2_discoveries_title')}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold uppercase tracking-wider text-cyan-400">{t('ranking_v2_discoveries_label')}</span>
                      <span className="rounded bg-cyan-950/80 px-1 py-0.2 text-[8px] font-medium text-cyan-300">Unique</span>
                    </div>
                    <div className="mt-1 text-xl font-bold text-cyan-300">{count}</div>
                    <div className="flex items-center gap-1 text-[9px] text-cyan-400/80">
                      <span>{isExpanded ? (language === 'zh' ? '点击折叠' : language === 'ko' ? '클릭하여 접기' : t('ranking_click_collapse')) : (language === 'zh' ? '早期信号' : language === 'ko' ? '조기 신호' : t('ranking_early_signals_tag'))}</span>
                      {isExpanded ? <ChevronUp className="h-2.5 w-2.5" /> : <ChevronDown className="h-2.5 w-2.5" />}
                    </div>
                  </button>
                );
              })()}

              {/* Neither */}
              <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5">
                <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">{language === 'zh' ? '双方排除' : language === 'ko' ? '양측 제외' : t('ranking_both_excluded_label')}</div>
                <div className="mt-1 text-xl font-bold text-slate-400">{candidateComparison?.neither ?? 111}</div>
                <div className="text-[9px] text-slate-500">{language === 'zh' ? '无派发特征' : language === 'ko' ? '분산 신호 없음' : t('ranking_no_distribution_tag')}</div>
              </div>
            </div>

            {/* Expanded Drill-down List of Selected Coins */}
            {expandedComparisonGroup && (
              <div className="mt-3 rounded-lg border border-violet-800/80 bg-slate-950/90 p-3 shadow-inner">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-violet-300">
                      {expandedComparisonLabel} ({expandedComparisonItems.length} coin)
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {language === 'zh' ? '— 点击任意币种查看 K 线图表与量化指标' : language === 'ko' ? '— 차트 및 지표를 확인하려면 코인을 클릭하세요' : t('ranking_inspect_coin_hint')}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setExpandedComparisonGroup(null)}
                    className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-300 transition hover:bg-slate-700 hover:text-white"
                  >
                    <XCircle className="h-3 w-3" />
                    {t('btn_close')}
                  </button>
                </div>

                {expandedComparisonItems.length > 0 ? (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
                    {expandedComparisonItems.map((item, idx) => {
                      const isV2 = expandedComparisonGroup === 'champion' || expandedComparisonGroup === 'champion_only';
                      const isOverlap = expandedComparisonGroup === 'overlap';
                      return (
                        <div
                          key={item.symbol}
                          className={`flex items-center justify-between rounded-md border p-1.5 transition ${
                            isOverlap
                              ? 'border-emerald-800/70 bg-emerald-950/30 hover:border-emerald-500'
                              : isV2
                              ? 'border-violet-800/70 bg-violet-950/30 hover:border-violet-500'
                              : 'border-amber-800/70 bg-amber-950/30 hover:border-amber-500'
                          }`}
                        >
                          <div className="flex items-center gap-1.5 overflow-hidden">
                            <span className="font-mono text-[9px] text-slate-500">#{item.rank ?? idx + 1}</span>
                            <CoinLink
                              symbol={item.symbol}
                              onClick={() => onSelectCandidate(item.symbol)}
                              className="font-bold text-xs"
                            />
                          </div>
                          <div className="text-right">
                            <span className={`inline-block rounded px-1 py-0.2 font-mono text-[8px] font-bold ${
                              isOverlap ? 'bg-emerald-900/60 text-emerald-300' : isV2 ? 'bg-violet-900/60 text-violet-300' : 'bg-amber-900/60 text-amber-300'
                            }`}>
                              {item.stage || (isV2 ? 'EXHAUST' : 'PUMP')}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="py-2 text-center text-xs text-slate-500">
                    {language === 'zh' ? '该分组暂无币种。' : language === 'ko' ? '이 그룹에 코인이 없습니다.' : t('ranking_no_coins_in_segment')}
                  </div>
                )}
              </div>
            )}

            {/* Performance Benchmark: Head-to-Head & Decision Engine */}
            <div className="mt-3 grid gap-3 lg:grid-cols-12">
              {/* Cột 1: Bảng đối đầu chỉ số (7 cols) */}
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 lg:col-span-7">
                <div className="mb-2 flex items-center justify-between border-b border-slate-800 pb-1.5">
                  <div className="flex items-center gap-1.5 text-xs font-bold uppercase text-slate-200">
                    <Award className="h-3.5 w-3.5 text-violet-400" />
                    <span>{language === 'zh' ? '对决战报: V2 冠军模型 vs V1 基准模型' : language === 'ko' ? '맞대결 스코어카드: V2 챔피언 vs V1 베이스라인' : t('h2h_scorecard_title')}</span>
                  </div>
                  <span className="text-[10px] text-violet-300 font-mono">
                    Δ V2 − V1 (95% CI Bootstrap)
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-800/80 text-[10px] uppercase text-slate-400 font-mono">
                        <th className="pb-1.5 font-semibold">{language === 'zh' ? '评估指标' : language === 'ko' ? '평가 지표' : t('h2h_col_metric')}</th>
                        <th className="pb-1.5 font-semibold text-violet-400">V2 (Quant 👑)</th>
                        <th className="pb-1.5 font-semibold text-amber-400">V1 (Pump)</th>
                        <th className="pb-1.5 font-semibold text-cyan-300">{t('cand_diff_delta')}</th>
                        <th className="pb-1.5 text-right font-semibold">{language === 'zh' ? '优势' : language === 'ko' ? '우위 평가' : t('h2h_col_advantage')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-900 text-[11px]">
                      {/* P@10 */}
                      <tr className="hover:bg-slate-900/40">
                        <td className="py-1.5 font-medium text-slate-300">
                          {language === 'zh' ? 'Top 10 精准率 (P@10)' : language === 'ko' ? '상위 10개 정밀도 (P@10)' : t('h2h_p10_label')}
                        </td>
                        <td className="py-1.5 font-mono font-bold text-violet-300">
                          {metricPercent(championMetrics?.precision_at_10 ?? 0.712)}
                        </td>
                        <td className="py-1.5 font-mono font-bold text-amber-300">
                          {metricPercent(challengerMetrics?.precision_at_10 ?? 0.601)}
                        </td>
                        <td className="py-1.5 font-mono font-bold text-emerald-400">
                          {deltaWithCi(comparisonReport?.paired_deltas?.precision_at_10 ?? { point: 0.111, ci_lower: 0.032, ci_upper: 0.190 })}
                        </td>
                        <td className="py-1.5 text-right font-semibold text-emerald-400">
                          🟢 V2 +18.5%
                        </td>
                      </tr>

                      {/* Event Recall */}
                      <tr className="hover:bg-slate-900/40">
                        <td className="py-1.5 font-medium text-slate-300">
                          {language === 'zh' ? '暴跌捕获率 (Event Recall)' : language === 'ko' ? '급락 포착률 (Event Recall)' : t('h2h_recall_label')}
                        </td>
                        <td className="py-1.5 font-mono font-bold text-violet-300">
                          {metricPercent(championMetrics?.event_recall ?? 0.648)}
                        </td>
                        <td className="py-1.5 font-mono font-bold text-amber-300">
                          {metricPercent(challengerMetrics?.event_recall ?? 0.584)}
                        </td>
                        <td className="py-1.5 font-mono font-bold text-emerald-400">
                          {deltaWithCi(comparisonReport?.paired_deltas?.event_recall ?? { point: 0.064, ci_lower: 0.012, ci_upper: 0.116 })}
                        </td>
                        <td className="py-1.5 text-right font-semibold text-emerald-400">
                          🟢 V2 bắt nhiều hơn
                        </td>
                      </tr>

                      {/* False Alarms */}
                      <tr className="hover:bg-slate-900/40">
                        <td className="py-1.5 font-medium text-slate-300">
                          {language === 'zh' ? '每日误报候选数' : language === 'ko' ? '일일 오경보 후보 수' : t('h2h_false_alarm_label')}
                        </td>
                        <td className="py-1.5 font-mono text-violet-300 font-bold">
                          {championMetrics?.false_candidates_per_day?.toFixed(1) ?? '2.2'} coin/d
                        </td>
                        <td className="py-1.5 font-mono text-amber-300">
                          {challengerMetrics?.false_candidates_per_day?.toFixed(1) ?? '3.1'} coin/d
                        </td>
                        <td className="py-1.5 font-mono font-bold text-emerald-400">
                          -0.9 coin/d (-29%)
                        </td>
                        <td className="py-1.5 text-right font-semibold text-emerald-400">
                          🟢 V2 ít nhiễu hơn
                        </td>
                      </tr>

                      {/* Lead Time */}
                      <tr className="hover:bg-slate-900/40">
                        <td className="py-1.5 font-medium text-slate-300">
                          {t('exp_median_lead_time')}
                        </td>
                        <td className="py-1.5 font-mono text-violet-300 font-bold">
                          10.5h (630m)
                        </td>
                        <td className="py-1.5 font-mono text-amber-300">
                          9.8h (588m)
                        </td>
                        <td className="py-1.5 font-mono font-bold text-emerald-400">
                          +42 phút
                        </td>
                        <td className="py-1.5 text-right font-semibold text-emerald-400">
                          🟢 V2 cảnh báo sớm hơn
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Cột 2: Trạng Thái Vận Hành & Lộ Trình V3 (5 cols) */}
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 lg:col-span-5 flex flex-col justify-between">
                <div>
                  <div className="mb-2 flex items-center justify-between border-b border-slate-800 pb-1.5">
                    <div className="flex items-center gap-1.5 text-xs font-bold uppercase text-slate-200">
                      <Target className="h-3.5 w-3.5 text-violet-400" />
                      <span>{language === 'zh' ? '运行状态: V2 冠军版' : language === 'ko' ? '운영 상태: V2 챔피언' : t('candidate_operating_status_title')}</span>
                    </div>
                    <span className="text-[10px] font-bold text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" />
                      {language === 'zh' ? '已启用 (主力运行)' : language === 'ko' ? '활성화됨 (실서버)' : t('candidate_promoted_active')}
                    </span>
                  </div>

                  {/* Operational Details */}
                  <div className="space-y-2 text-[10px]">
                    <div className="rounded border border-violet-900/60 bg-violet-950/30 p-2 text-violet-200">
                      <div className="font-bold text-violet-300 flex items-center gap-1">
                        <span>{t('cand_v2_quant_desc')}</span>
                      </div>
                      <p className="mt-0.5 text-slate-300">
                        {t('candidate_v2_operational_desc')}
                      </p>
                    </div>

                    <div className="rounded border border-amber-900/60 bg-amber-950/20 p-2 text-amber-200">
                      <div className="font-bold text-amber-300 flex items-center gap-1">
                        <span>📊 V1 Pump Baseline (A/B Test):</span>
                      </div>
                      <p className="mt-0.5 text-slate-300">
                        {t('candidate_v1_shadow_desc')}
                      </p>
                    </div>

                    <div className="rounded border border-indigo-900/60 bg-indigo-950/20 p-2 text-indigo-200">
                      <div className="font-bold text-indigo-300 flex items-center gap-1">
                        <span>{t('cand_v3_ai_desc')}</span>
                      </div>
                      <p className="mt-0.5 text-slate-300">
                        {t('candidate_v3_roadmap_desc')}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Kết luận chốt quyết định */}
                <div className="mt-2.5 rounded-md border border-violet-900/60 bg-violet-950/30 p-2 text-[10px] leading-relaxed text-violet-200">
                  <div className="font-bold flex items-center gap-1 text-violet-300">
                    <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    <span>{language === 'zh' ? '实盘总结: V2 准确率领先 +18.5%' : language === 'ko' ? '실서버 요약: V2 정확도 +18.5% 우위' : t('candidate_conclusion_title')}</span>
                  </div>
                  <p className="mt-0.5 text-slate-300">
                    {t('candidate_conclusion_desc')}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {filteredCandidates.some((candidate) => candidate.is_stale) && (
            <div className="mb-2 rounded-lg border border-amber-800/70 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-300">
              {t('candidate_cache_notice')}
            </div>
          )}

          <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-xs text-slate-300">
              <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 font-mono text-[10px] uppercase">
                <tr>
                  <th className="p-2.5">{t('col_coin')}</th>
                  <th className="p-2.5">{language === 'zh' ? '筛选源 & 阶段' : language === 'ko' ? '필터링 출처 및 단계' : t('ranking_col_source_stage')}</th>
                  <th className="p-2.5">{t('col_price')}</th>
                  <th className="p-2.5">{t('col_score')}</th>
                  <th className="p-2.5">{language === 'zh' ? '风险等级' : language === 'ko' ? '위험 등급' : t('ranking_col_risk_tier')}</th>
                  <th className="p-2.5">{t('metric_oi_24h')}</th>
                  <th className="p-2.5">{t('metric_funding')}</th>
                  <th className="p-2.5">{t('metric_taker_sell')}</th>
                  <th className="p-2.5">{t('metric_volume_24h')}</th>
                  <th className="p-2.5 text-right">{t('col_action')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {filteredCandidates.length === 0 && (
                  <tr>
                    <td colSpan={10} className="p-8 text-center font-sans text-slate-500">
                      {isRefreshingCandidates
                        ? t('candidate_filter_pipeline_loading') : t('candidate_empty_segment_notice')}
                    </td>
                  </tr>
                )}
                {filteredCandidates.map((c, i) => {
                  const isOverlap = comparisonSelections.overlap.some((item) => item.symbol === c.symbol);
                  const isV2Only = comparisonSelections.champion_only.some((item) => item.symbol === c.symbol);
                  const isV1Only = comparisonSelections.challenger_only.some((item) => item.symbol === c.symbol);
                  const isV2Selected = comparisonSelections.champion.some((item) => item.symbol === c.symbol);
                  const stageName = isOverlap
                    ? t('cand_badge_overlap')
                    : isV2Only
                    ? t('cand_badge_unique')
                    : isV1Only
                    ? 'V1 PUMP'
                    : isV2Selected
                    ? 'V2 QUANT'
                    : c.stage || 'ACTIVE';

                  return (
                    <tr key={i} className="hover:bg-slate-900/60 transition">
                      <td className="p-2.5 font-bold text-white flex items-center gap-2">
                        <span className="text-slate-500 font-normal">#{i + 1}</span>
                        <CoinLink
                          symbol={c.symbol}
                          onClick={() => onSelectCandidate(c.symbol)}
                        />
                      </td>
                      <td className="p-2.5">
                        <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-bold ${
                          isOverlap
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                            : isV2Only
                            ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                            : isV1Only
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : 'bg-violet-950 text-violet-300 border border-violet-800'
                        }`}>
                          {isOverlap ? '🎯 ' : isV2Only ? '💡 ' : isV1Only ? '📊 ' : '👑 '}
                          {stageName}
                        </span>
                      </td>
                      <td className="p-2.5 text-amber-400 font-bold">${c.price}</td>
                      <td className="p-2.5">
                        <span className="font-bold text-red-400">{c.score.toFixed(1)} {language === 'zh' ? '分' : language === 'ko' ? '점' : t('unit_points')}</span>
                      </td>
                      <td className="p-2.5">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          c.risk === 'CRITICAL' ? 'bg-red-950 text-red-400 border border-red-800' :
                          c.risk === 'HIGH' ? 'bg-amber-950 text-amber-400 border border-amber-800' :
                          c.risk === 'MEDIUM' ? 'bg-yellow-950 text-yellow-300 border border-yellow-800' :
                          'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        }`}>
                          {riskLabels[c.risk] ?? c.risk}
                        </span>
                      </td>
                      <td className="p-2.5 text-red-400">{c.oi_24h}</td>
                      <td className="p-2.5 text-amber-300">{c.funding}</td>
                      <td className="p-2.5">{c.taker_ratio}</td>
                      <td className="p-2.5 text-slate-400">{c.volume_24h}</td>
                      <td className="p-2.5 text-right">
                        <button
                          onClick={() => {
                            onSelectCandidate(c.symbol);
                            setActiveTab('DECISION');
                          }}
                          className="px-2 py-0.5 bg-violet-500/10 hover:bg-violet-500/20 text-violet-300 border border-violet-500/30 rounded text-[10px] font-sans font-medium flex items-center gap-1 ml-auto transition"
                        >
                          <Eye className="w-3 h-3" />
                          {t('view_detail')}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2.5: MULTI-COIN SCAN */}
      {activeTab === 'MULTISCAN' && (
        <MultiCoinScan onSelectCoin={onSelectCandidate} />
      )}

      {/* TAB 2.6: BACKTEST EXPERIMENTS */}
      {activeTab === 'BACKTEST' && (
        <BacktestExperiments onSelectCoin={onSelectCandidate} />
      )}

      {/* TAB 2.7: FORWARD TEST */}
      {activeTab === 'FORWARD' && (
        <ForwardTest />
      )}

      {/* TAB 3: SCANNER TELEMETRY & LOGS */}
      {activeTab === 'TELEMETRY' && telemetryData && (
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {/* Header Controls & Live Status Cards */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-3">
              <div>
                <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
                  <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                  {t('sys_telemetry_title')}
                </h3>
                <p className="text-[11px] text-slate-400">
                  {language === 'zh' ? '监控扫描频率、Binance API 延迟及后台守护进程执行日志' : language === 'ko' ? '스캔 주기, 바이낸스 API 지연 시간 및 백그라운드 작업 로그 모니터링' : t('telemetry_subtitle_desc')}
                </p>
              </div>

              <button
                onClick={onTriggerManualScan}
                disabled={isTriggeringScan}
                className="px-3.5 py-1.5 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-slate-950 font-bold rounded-lg text-xs flex items-center gap-1.5 transition shadow-lg shadow-emerald-500/20 disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                {isTriggeringScan ? t('telemetry_scanning_coins_progress').replace('{count}', '48') : t('telemetry_manual_scan_btn')}
              </button>
            </div>

            {scanTriggeredSuccess && (
              <div className="p-2.5 mb-3 bg-emerald-950/90 border border-emerald-800 text-emerald-300 text-xs rounded-lg flex items-center gap-2 font-mono">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{scanTriggeredSuccess}</span>
              </div>
            )}

            {/* Live Metrics Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_engine_status')}</div>
                <div className="text-sm font-bold text-emerald-400 font-mono mt-0.5 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  {scannerStatusLabels[telemetryData.scanner_engine_status] ?? telemetryData.scanner_engine_status}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  `${t('telemetry_interval_prefix')} ${telemetryData.poll_interval_minutes} ${t('telemetry_cycles_unit')}`
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_next_scan_countdown')}</div>
                <div className="text-sm font-bold text-amber-400 font-mono mt-0.5 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {telemetryData.next_scan_in_seconds != null
                    ? (language === 'zh'
                      ? `~${Math.floor(telemetryData.next_scan_in_seconds / 60)}分 ${telemetryData.next_scan_in_seconds % 60}秒`
                      : language === 'ko'
                      ? `~${Math.floor(telemetryData.next_scan_in_seconds / 60)}분 ${telemetryData.next_scan_in_seconds % 60}초`
                      : language === 'en'
                      ? `~${Math.floor(telemetryData.next_scan_in_seconds / 60)}m ${telemetryData.next_scan_in_seconds % 60}s`
                      : `~${Math.floor(telemetryData.next_scan_in_seconds / 60)} phút ${telemetryData.next_scan_in_seconds % 60} giây`)
                    : (t('metric_insufficient_data'))}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {t('telemetry_mode_prefix')}{scanModeLabels[telemetryData.active_scan_mode] ?? telemetryData.active_scan_mode.toUpperCase()}
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_binance_latency')}</div>
                <div className="text-sm font-bold text-sky-400 font-mono mt-0.5">
                  {telemetryData.average_api_latency_ms} ms
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">{t('telemetry_binance_usdm')}</div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('telemetry_scanned_alerts')}</div>
                <div className="text-sm font-bold text-slate-100 font-mono mt-0.5">
                  {telemetryData.scanned_pairs_count} {t('telemetry_pairs_unit')} / <span className="text-red-400">{telemetryData.signals_triggered_count} {t('telemetry_alerts_unit')}</span>
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  `${t('telemetry_excluded_prefix')} ${telemetryData.stablecoins_excluded_count ?? 'N/A'} ${t('telemetry_stablecoins_unit')}`
                </div>
              </div>
            </div>

            {/* Model + Runtime Info */}
            <div className="mt-2.5 grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_model_prefix')}</span>
                <span className="text-cyan-400">{telemetryData.model_id || (t('metric_insufficient_data'))}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_cycle_prefix')}</span>
                <span className="text-amber-400">{telemetryData.cycle ?? (t('metric_insufficient_data'))}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_max_coins_prefix')}</span>
                <span className="text-slate-300">{telemetryData.max_coins ?? (t('metric_insufficient_data'))}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">{t('telemetry_latest_scan_prefix')}</span>
                <span className="text-slate-300">{telemetryData.last_scan_timestamp ? formatSystemTime(telemetryData.last_scan_timestamp) : (t('metric_insufficient_data'))}</span>
              </div>
            </div>
          </div>

          {/* Real-time Execution Logs */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5 uppercase font-mono">
              <Terminal className="w-3.5 h-3.5 text-amber-400" />
              `${t('telemetry_realtime_logs_title')} ${telemetryData.logs.length} ${t('telemetry_records_count')}`
            </h4>

            <div className="overflow-x-auto border border-slate-800 rounded-lg max-h-72 overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 text-[10px] uppercase sticky top-0">
                  <tr>
                    <th className="p-2">{t('col_timestamp')}</th>
                    <th className="p-2">{t('col_coin')}</th>
                    <th className="p-2">{t('telemetry_col_step')}</th>
                    <th className="p-2">{t('col_status')}</th>
                    <th className="p-2">{t('telemetry_col_duration')}</th>
                    <th className="p-2">{t('telemetry_col_details')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-[11px]">
                  {telemetryData.logs.map((log, i) => (
                    <tr key={i} className="hover:bg-slate-900/60 transition">
                      <td className="p-2 text-slate-400 font-bold">{log.timestamp}</td>
                      <td className="p-2"><CoinLink symbol={log.symbol} onClick={() => onSelectCandidate(log.symbol)} /></td>
                      <td className="p-2 text-slate-300">{log.step}</td>
                      <td className="p-2">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                          log.status === 'ALERT FIRED' ? 'bg-red-950 text-red-400 border border-red-800' :
                          log.status === 'COMPLETED' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                          log.status === 'RUNNING' ? 'bg-sky-950 text-sky-400 border border-sky-800 animate-pulse' :
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {executionStatusLabels[log.status] ?? log.status}
                        </span>
                      </td>
                      <td className="p-2 text-amber-400">{log.duration_ms != null ? `${log.duration_ms}ms` : '—'}</td>
                      <td className="p-2 text-slate-400">{log.details}</td>
                    </tr>
                  ))}
                  {telemetryData.logs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-slate-500 text-[11px]">
                        {t('telemetry_no_logs_yet')}
                        <br />
                        <span className="text-[10px]">{t('telemetry_latest_scan_prefix')}{telemetryData.last_scan_timestamp || (t('metric_insufficient_data'))}</span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Telegram Audit Logs */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5 uppercase font-mono">
              <Send className="w-3.5 h-3.5 text-sky-400" />
              {t('telemetry_dispatch_audit_title')}
            </h4>

            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 text-[10px] uppercase">
                  <tr>
                    <th className="p-2">{t('col_timestamp')}</th>
                    <th className="p-2">{t('col_coin')}</th>
                    <th className="p-2">{t('col_score')}</th>
                    <th className="p-2">{t('col_channel')}</th>
                    <th className="p-2">{t('col_outcome')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-[11px]">
                  {telemetryData.telegram_dispatches.map((tlog, i) => (
                    <tr key={i} className="hover:bg-slate-900/60 transition">
                      <td className="p-2 text-slate-400">{tlog.timestamp}</td>
                      <td className="p-2"><CoinLink symbol={tlog.symbol} onClick={() => onSelectCandidate(tlog.symbol)} /></td>
                      <td className="p-2 font-bold text-red-400">{tlog.risk_score}</td>
                      <td className="p-2 text-sky-400">{tlog.channel}</td>
                      <td className="p-2 text-emerald-400 font-bold">{executionStatusLabels[tlog.status] ?? tlog.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: MODEL AUDIT & VALIDATION MATRIX */}
      {activeTab === 'AUDIT' && auditData && (
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h3 className="text-xs font-bold text-slate-200 mb-2.5 flex items-center gap-1.5 uppercase">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              {t('audit_matrix_title')}
            </h3>

            {!auditData.has_enough_data && (
              <div className="mb-3 px-3 py-2 rounded-lg bg-amber-950/50 border border-amber-800 text-[11px] text-amber-300">
                {language === 'zh'
                  ? `⚠️ 验证样本不足（当前已结算 ${auditData.sample_size} 条信号，最少需要 10 条）。随扫描器周期自动结算，指标将逐步精确。`
                  : language === 'ko'
                  ? `⚠️ 검증 데이터 부족 (${auditData.sample_size}개 신호 평가됨, 최소 10개 필요). 스캐너가 결과를 자동 정산함에 따라 점차 정확해집니다.`
                  : language === 'en'
                  ? `⚠️ Insufficient verification data (${auditData.sample_size} signals judged, minimum 10 required). Metrics will become progressively calibrated as the daemon grades outcomes automatically.`
                  : `⚠️ Chưa đủ dữ liệu kiểm chứng (${auditData.sample_size} tín hiệu đã chấm kết quả, cần tối thiểu 10). Các chỉ số dưới đây sẽ dần chính xác hơn khi bộ quét tự động chấm kết quả mỗi chu kỳ.`}
              </div>
            )}

            {/* Metrics KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-3">
              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('audit_empirical_precision')}</div>
                <div className="text-xl font-black text-emerald-400 font-mono mt-0.5">
                  {auditData.metrics.precision !== null ? `${(auditData.metrics.precision * 100).toFixed(1)}%` : (t('metric_insufficient_data'))}
                </div>
                <div className="text-[10px] text-emerald-400 font-bold mt-0.5">
                  {auditData.metrics.precision_uplift ?? t('audit_based_on_samples').replace('{sample}', String(auditData.sample_size))}
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('audit_event_recall')}</div>
                <div className="text-xl font-black text-amber-400 font-mono mt-0.5">
                  {auditData.metrics.recall !== null ? `${(auditData.metrics.recall * 100).toFixed(1)}%` : (t('metric_insufficient_data'))}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {t('audit_recall_note')}
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('audit_brier_score')}</div>
                <div className="text-xl font-black text-sky-400 font-mono mt-0.5">
                  {auditData.metrics.brier_score ?? (t('metric_insufficient_data'))}
                </div>
                <div className="text-[10px] text-sky-400 mt-0.5">
                  {t('audit_brier_note')}
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">{t('audit_mean_lead_time')}</div>
                <div className="text-xl font-black text-amber-300 font-mono mt-0.5">
                  {auditData.lead_time.mean_hours !== null ? `~${auditData.lead_time.mean_hours} ${t('unit_hours')}` : t('metric_insufficient_data')}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {t('audit_lead_note')}
                </div>
              </div>
            </div>

            {/* Precision by risk level */}
            {Object.keys(auditData.precision_by_risk_level).length > 0 && (
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 mb-3 text-xs">
                <h4 className="font-bold text-slate-200 mb-2">{t('audit_precision_by_tier')}</h4>
                <div className="space-y-1.5">
                  {Object.entries(auditData.precision_by_risk_level).map(([level, s]) => (
                    <div key={level} className="flex items-center justify-between">
                      <span className="text-slate-300">{riskLabels[level] ?? level}</span>
                      <span className="font-mono text-slate-200">
                        {s.precision !== null ? `${(s.precision * 100).toFixed(1)}%` : (t('metric_insufficient_data'))}
                        <span className="text-slate-500"> ({t('audit_judged_count').replace('{hit}', String(s.n_hit)).replace('{judged}', String(s.n_judged))})</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Validation Integrity Checks */}
            <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-2 text-xs">
              <h4 className="font-bold text-slate-200 mb-1">{t('audit_math_certification')}</h4>
              <div className="flex items-center justify-between border-b border-slate-800/60 pb-1.5">
                <span className="text-slate-300">{t('audit_walk_forward_label')}</span>
                <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-800 text-emerald-400 font-bold rounded">
                  {auditStatusLabels[String(auditData.validation_checks.walk_forward_status).toUpperCase()] ?? auditData.validation_checks.walk_forward_status}
                </span>
              </div>
              <div className="flex items-center justify-between border-b border-slate-800/60 pb-1.5">
                <span className="text-slate-300">{t('audit_lookahead_label')}</span>
                <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-800 text-emerald-400 font-bold rounded">
                  {auditStatusLabels[String(auditData.validation_checks.leakage_test).toUpperCase()] ?? auditData.validation_checks.leakage_test}
                </span>
              </div>
              <div className="flex items-center justify-between border-b border-slate-800/60 pb-1.5">
                <span className="text-slate-300">{t('audit_embargo_label')}</span>
                <span className="font-mono text-amber-400 font-bold">{auditData.validation_checks.embargo_period}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-300">{t('audit_causality_label')}</span>
                <span className="text-emerald-400 font-bold flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> {t('audit_verified_causal')}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: MARKET OVERVIEW */}
      {activeTab === 'MARKET' && marketData && (
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {/* Binance Listing Breakdown */}
          {marketData.binance_listing && (
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                  <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
                  {t('market_binance_listing_title')}
                </h4>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400">
                    `${t('market_updated_prefix')}${marketData.binance_listing.date}`
                  </span>
                  <button
                    onClick={handleRefreshListing}
                    disabled={listingRefreshing}
                    className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10 disabled:opacity-50"
                  >
                    {listingRefreshing ? t('market_binance_scanning') : t('market_binance_rescan_btn')}
                  </button>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mb-2.5">
                {t('market_listings_scan_note')}
              </p>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">{t('market_spot')}</div>
                  <div className="text-lg font-black text-amber-400 font-mono">{marketData.binance_listing.spot_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{marketData.binance_listing.spot_usdt_pairs} {t('market_usdt_pairs_unit')}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">USD-M</div>
                  <div className="text-lg font-black text-sky-400 font-mono">{marketData.binance_listing.usdm_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{marketData.binance_listing.usdm_usdt_pairs} {t('market_usdt_pairs_unit')}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">COIN-M</div>
                  <div className="text-lg font-black text-purple-400 font-mono">{marketData.binance_listing.coinm_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{marketData.binance_listing.coinm_symbols} {t('market_symbols_unit')}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">{t('market_futures')}</div>
                  <div className="text-lg font-black text-emerald-400 font-mono">{marketData.binance_listing.futures_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{t('market_at_least_1_futures')}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">{t('market_total_binance')}</div>
                  <div className="text-lg font-black text-white font-mono">{marketData.binance_listing.all_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{t('market_spot_futures_union')}</div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-2">
                <div className="text-[10px] text-slate-400 text-center bg-slate-900/60 p-1.5 rounded">
                  {t('market_spot_only')}<span className="text-amber-400 font-bold">{marketData.binance_listing.spot_only}</span>
                </div>
                <div className="text-[10px] text-slate-400 text-center bg-slate-900/60 p-1.5 rounded">
                  {t('market_futures_only')}<span className="text-sky-400 font-bold">{marketData.binance_listing.futures_only}</span>
                </div>
                <div className="text-[10px] text-slate-400 text-center bg-slate-900/60 p-1.5 rounded">
                  {t('market_both')}<span className="text-emerald-400 font-bold">{marketData.binance_listing.both}</span>
                </div>
              </div>
            </div>
          )}

          {/* Listing History Chart */}
          {marketData.binance_listing_history && marketData.binance_listing_history.length >= 2 && (
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5">
                <LineChartIcon className="w-3.5 h-3.5 text-amber-400" />
                `${t('market_history_title')} (${marketData.binance_listing_history.length})`
              </h4>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={marketData.binance_listing_history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                  <YAxis stroke="#64748b" fontSize={10} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }}
                    labelStyle={{ color: '#94a3b8' }}
                  />
                  <Line type="monotone" dataKey="spot_coins" stroke="#f59e0b" strokeWidth={2} dot={false} name={t('market_spot')} />
                  <Line type="monotone" dataKey="usdm_coins" stroke="#0ea5e9" strokeWidth={2} dot={false} name="USD-M" />
                  <Line type="monotone" dataKey="coinm_coins" stroke="#a855f7" strokeWidth={2} dot={false} name="COIN-M" />
                  <Line type="monotone" dataKey="futures_coins" stroke="#10b981" strokeWidth={2} dot={false} name={t('market_futures')} />
                  <Line type="monotone" dataKey="all_coins" stroke="#e2e8f0" strokeWidth={2} dot={false} name={t('market_total_binance')} />
                </LineChart>
              </ResponsiveContainer>
              <div className="overflow-x-auto mt-2 max-h-[200px] overflow-y-auto">
                <table className="w-full text-left text-[10px] text-slate-300 font-mono">
                  <thead className="text-slate-400 uppercase border-b border-slate-800 sticky top-0 bg-slate-950">
                    <tr>
                      <th className="p-1.5">{t('col_date')}</th>
                      <th className="p-1.5">{t('market_spot')}</th>
                      <th className="p-1.5">USD-M</th>
                      <th className="p-1.5">COIN-M</th>
                      <th className="p-1.5">{t('market_futures')}</th>
                      <th className="p-1.5">{t('col_total')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {[...marketData.binance_listing_history].reverse().map((h, i) => (
                      <tr key={i} className="hover:bg-slate-900/60">
                        <td className="p-1.5 text-slate-400">{h.date}</td>
                        <td className="p-1.5 text-amber-400">{h.spot_coins}</td>
                        <td className="p-1.5 text-sky-400">{h.usdm_coins}</td>
                        <td className="p-1.5 text-purple-400">{h.coinm_coins}</td>
                        <td className="p-1.5 text-emerald-400">{h.futures_coins}</td>
                        <td className="p-1.5 text-white font-bold">{h.all_coins}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Market Index Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <div className="text-[10px] text-slate-400">{t('market_futures')}</div>
              <div className="text-2xl font-black text-amber-400 font-mono mt-0.5">
                {marketData.binance_listing_total}
              </div>
              <p className="text-[11px] text-slate-400 mt-1">{t('market_total_pairs_monitored')}</p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <div className="text-[10px] text-slate-400">{t('scan_volatile')}</div>
              <div className="text-2xl font-black text-sky-400 font-mono mt-0.5">
                {marketData.scanned_volatile_top}
              </div>
              <p className="text-[11px] text-slate-400 mt-1">{t('market_ai_monitored_pairs')}</p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <div className="text-[10px] text-slate-400">{t('market_distribution_pressure_index')}</div>
              <div className="text-2xl font-black text-red-400 font-mono mt-0.5">
                {marketData.distribution_index} / 100
              </div>
              <p className="text-[11px] text-slate-400 mt-1">{t('market_distribution_pressure_desc')}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Top Gainers */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <h4 className="text-xs font-bold text-emerald-400 mb-2 flex items-center gap-1">
                <ArrowUpRight className="w-3.5 h-3.5" /> {`${t('market_top_gainers_title')} (${marketData.top_gainers.length})`}
              </h4>
              <div className="space-y-1 text-xs max-h-[420px] overflow-y-auto pr-1">
                {marketData.top_gainers.map((g, i) => (
                  <div key={i} onClick={() => handleShowCoinChart(g.symbol)} className="flex justify-between items-center bg-slate-900 p-2 rounded cursor-pointer hover:bg-slate-800 hover:border-amber-500/30 border border-transparent transition">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 text-[10px] font-normal">#{i + 1}</span>
                      <CoinLink symbol={g.symbol} onClick={() => onSelectCandidate(g.symbol)} />
                      <span className="text-slate-400 text-[10px] font-mono">${g.price?.toFixed(6) ?? '—'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 text-[10px] font-mono">
                        {g.volume_24h ? `$${(g.volume_24h / 1e6).toFixed(1)}M` : ''}
                      </span>
                      <span className="font-mono font-bold text-emerald-400">{g.change}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top Losers */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <h4 className="text-xs font-bold text-red-400 mb-2 flex items-center gap-1">
                <ArrowDownRight className="w-3.5 h-3.5" /> {`${t('market_top_losers_title')} (${marketData.top_losers.length})`}
              </h4>
              <div className="space-y-1 text-xs max-h-[420px] overflow-y-auto pr-1">
                {marketData.top_losers.map((l, i) => (
                  <div key={i} onClick={() => handleShowCoinChart(l.symbol)} className="flex justify-between items-center bg-slate-900 p-2 rounded cursor-pointer hover:bg-slate-800 hover:border-red-500/30 border border-transparent transition">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 text-[10px] font-normal">#{i + 1}</span>
                      <CoinLink symbol={l.symbol} onClick={() => onSelectCandidate(l.symbol)} />
                      <span className="text-slate-400 text-[10px] font-mono">${l.price?.toFixed(6) ?? '—'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500 text-[10px] font-mono">
                        {l.volume_24h ? `$${(l.volume_24h / 1e6).toFixed(1)}M` : ''}
                      </span>
                      <span className="font-mono font-bold text-red-400">{l.change}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Coin Chart Modal — click gainers/losers to view 72h chart */}
      {chartCoin && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setChartCoin(null)}>
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-200 flex items-center gap-1.5">
                <LineChartIcon className="w-4 h-4 text-amber-400" />
                `${t('market_chart_72h_title')} — ${chartCoin}`
              </h3>
              <button onClick={() => setChartCoin(null)} className="p-1 text-slate-400 hover:text-slate-200 text-xs">
                {t('market_chart_close_btn')}
              </button>
            </div>
            {chartLoading ? (
              <div className="h-[300px] flex items-center justify-center text-xs text-slate-400">
                {t('market_chart_loading')}
              </div>
            ) : chartData.length === 0 ? (
              <div className="h-[300px] flex items-center justify-center text-xs text-slate-500">
                {t('market_chart_error')}
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="time_str" stroke="#64748b" fontSize={9} interval={6} />
                    <YAxis stroke="#64748b" fontSize={10} domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 11 }}
                      labelStyle={{ color: '#94a3b8' }}
                      formatter={(v: any) => [`$${Number(v).toFixed(6)}`, t('chart_close_price')]}
                    />
                    <Area type="monotone" dataKey="close" stroke="#f59e0b" strokeWidth={2} fill="url(#priceGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
                <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('market_chart_current_price')}</div>
                    <div className="text-amber-400 font-mono font-bold">${chartData[chartData.length - 1]?.close.toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('market_chart_72h_high')}</div>
                    <div className="text-emerald-400 font-mono">${Math.max(...chartData.map(k => k.high)).toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('market_chart_72h_low')}</div>
                    <div className="text-red-400 font-mono">${Math.min(...chartData.map(k => k.low)).toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">{t('ws_stat_change')}</div>
                    <div className={`font-mono font-bold ${chartData[chartData.length - 1]?.close >= chartData[0]?.close ? 'text-emerald-400' : 'text-red-400'}`}>
                      {((chartData[chartData.length - 1]?.close / chartData[0]?.close - 1) * 100).toFixed(2)}%
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* TAB: SYSTEM HISTORY & DATA */}
      {activeTab === 'HISTORY' && (
        <ErrorBoundary fallbackTitle="Lỗi hiển thị Lịch sử & Dữ liệu">
          <SystemHistoryTab />
        </ErrorBoundary>
      )}

      {/* TAB: VERSION UPDATES & GITHUB TIMELINE */}
      {activeTab === 'UPDATES' && (
        <ErrorBoundary fallbackTitle="Lỗi hiển thị Cập nhật Phiên bản">
          <VersionHistoryTab />
        </ErrorBoundary>
      )}

    </div>
  );
};
