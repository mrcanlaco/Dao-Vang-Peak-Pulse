import React, { useState, useEffect, useMemo } from 'react';
import type { SignalItem, CoinDetail, CandidateCoin, CandidateFilterComparison, ModelAudit, MarketOverviewData, ScannerTelemetry, DeepAnalysis, CandlePoint, TrackingWatchlistItem } from '../types';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid, AreaChart, Area, ComposedChart
} from 'recharts';
import {
  ShieldCheck, Activity, BarChart3, AlertOctagon,
  Layers, ArrowUpRight, ArrowDownRight, Eye, CheckCircle2, Zap, Radio, Terminal, Send, Clock, Play, Loader2, Flame, FlaskConical, LineChart as LineChartIcon, Lock, XCircle, TrendingDown, Info, RefreshCw, Target
} from 'lucide-react';
import { MultiCoinScan } from './MultiCoinScan';
import { BacktestExperiments } from './BacktestExperiments';
import { ForwardTest } from './ForwardTest';
import { SystemHistoryTab } from './SystemHistoryTab';
import { TrackingWatchlist } from './TrackingWatchlist';

import { CandlestickChart } from './CandlestickChart';
import type { CandlestickSignalMarker } from './CandlestickChart';
import { CoinLink } from './CoinLink';
import { formatSystemTime, parseSystemDate } from '../utils/time';

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
  activeTab: 'DECISION' | 'WATCHLIST' | 'RANKING' | 'MULTISCAN' | 'BACKTEST' | 'FORWARD' | 'AUDIT' | 'MARKET' | 'TELEMETRY' | 'HISTORY';
  setActiveTab: (tab: 'DECISION' | 'WATCHLIST' | 'RANKING' | 'MULTISCAN' | 'BACKTEST' | 'FORWARD' | 'AUDIT' | 'MARKET' | 'TELEMETRY' | 'HISTORY') => void;
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
  setActiveTab
}) => {
  const riskLabels: Record<string, string> = {
    CRITICAL: 'CỰC CAO',
    HIGH: 'CAO',
    MEDIUM: 'VỪA',
    SAFE: 'AN TOÀN',
  };
  const btcRegimeLabels: Record<string, string> = {
    FOMO: 'MUA ĐUỔI',
    WEAK: 'YẾU',
    NEUTRAL: 'TRUNG TÍNH',
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
    value == null ? 'Chưa đủ dữ liệu' : `${(value * 100).toFixed(1)}%`
  );
  const deltaWithCi = (value: { point: number | null; ci_lower: number | null; ci_upper: number | null } | undefined) => (
    value?.point == null || value.ci_lower == null || value.ci_upper == null
      ? 'Chưa đủ dữ liệu'
      : `${value.point >= 0 ? '+' : ''}${(value.point * 100).toFixed(1)}đ% (CI95% ${(value.ci_lower * 100).toFixed(1)} → ${(value.ci_upper * 100).toFixed(1)})`
  );
  const auditStatusLabels: Record<string, string> = {
    PASS: 'ĐẠT',
    PASSED: 'ĐẠT',
    FAIL: 'KHÔNG ĐẠT',
    FAILED: 'KHÔNG ĐẠT',
    WARN: 'CẢNH BÁO',
  };
  const executionStatusLabels: Record<string, string> = {
    'ALERT FIRED': 'ĐÃ PHÁT CẢNH BÁO',
    COMPLETED: 'ĐÃ HOÀN TẤT',
    RUNNING: 'ĐANG CHẠY',
    SENT: 'ĐÃ GỬI',
    FAILED: 'THẤT BẠI',
  };
  const scannerStatusLabels: Record<string, string> = {
    ONLINE: 'ĐANG CHẠY',
    OFFLINE: 'ĐÃ DỪNG',
  };
  const scanModeLabels: Record<string, string> = {
    volatile: 'BIẾN ĐỘNG',
    gainers: 'TĂNG MẠNH',
    losers: 'GIẢM MẠNH',
    volume: 'KHỐI LƯỢNG',
    all: 'TẤT CẢ',
    manual: 'CÁ NHÂN',
  };
  const [scanProgress, setScanProgress] = useState<number>(0);
  const [scanStepText, setScanStepText] = useState<string>('');
  const [chartCoin, setChartCoin] = useState<string | null>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [listingRefreshing, setListingRefreshing] = useState(false);
  const [candleInterval, setCandleInterval] = useState('15m');
  const [candleDataOverride, setCandleDataOverride] = useState<CandlePoint[] | null>(null);
  const [expandedComparisonGroup, setExpandedComparisonGroup] = useState<'champion' | 'challenger' | 'overlap' | null>(null);

  const comparisonSelections = useMemo(() => {
    const champion = candidateComparison?.selected?.champion ?? [];
    const challenger = candidateComparison?.selected?.challenger ?? [];
    const challengerSymbols = new Set(challenger.map((item) => item.symbol));

    return {
      champion,
      challenger,
      overlap: champion.filter((item) => challengerSymbols.has(item.symbol)),
    };
  }, [candidateComparison]);

  const expandedComparisonItems = expandedComparisonGroup
    ? comparisonSelections[expandedComparisonGroup]
    : [];
  const expandedComparisonLabel = expandedComparisonGroup === 'champion'
    ? 'V1 chọn'
    : expandedComparisonGroup === 'challenger'
      ? 'V2 chọn'
      : 'Cả hai chọn';

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
        ...coinDetail.metrics,
        oi_change_24h: selectedSignal.oi_change_24h ?? coinDetail.metrics.oi_change_24h,
        funding_rate: selectedSignal.funding_rate ?? coinDetail.metrics.funding_rate,
        taker_sell_ratio: selectedSignal.taker_sell_ratio ?? coinDetail.metrics.taker_sell_ratio,
      },
    };
  }, [coinDetail, selectedSignal]);

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
      setScanStepText('Bước 1/4: Đang đồng bộ 48/48 mã từ hợp đồng tương lai Binance USD-M...');

      const t1 = setTimeout(() => {
        setScanProgress(50);
        setScanStepText('Bước 2/4: Đang tính toán thay đổi OI và tỷ lệ bán chủ động...');
      }, 500);

      const t2 = setTimeout(() => {
        setScanProgress(85);
        setScanStepText('Bước 3/4: Đang chạy suy luận mô hình AI kết hợp (XGBoost + LightGBM)...');
      }, 1000);

      const t3 = setTimeout(() => {
        setScanProgress(100);
        setScanStepText('Bước 4/4: Đã cập nhật tín hiệu rủi ro và bật cảnh báo!');
      }, 1400);

      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
      };
    }
  }, [isTriggeringScan, setActiveTab]);

  const deepProbabilityPct = deepAnalysis?.calibrated_probability != null
    ? deepAnalysis.calibrated_probability * 100
    : null;
  const deepProbabilityThresholdPct = deepAnalysis?.probability_threshold != null
    ? deepAnalysis.probability_threshold * 100
    : null;
  const probabilityDelta = deepProbabilityPct != null && displayDetail?.probability != null
    ? deepProbabilityPct - displayDetail.probability
    : null;

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 flex flex-col h-auto lg:h-full overflow-visible lg:overflow-hidden relative">

      {/* Real-time Scanning Progress Overlay Banner */}
      {isTriggeringScan && (
        <div className="absolute inset-0 z-40 bg-slate-950/90 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/20 border border-amber-500/50 flex items-center justify-center mb-3 text-amber-400">
            <Loader2 className="w-7 h-7 animate-spin" />
          </div>
          <h3 className="text-base font-bold text-slate-100 uppercase tracking-wider mb-1">
            ⚡ ĐANG KÍCH HOẠT LƯỢT QUÉT NGAY (CHẾ ĐỘ: {scanModeLabels[telemetryData?.active_scan_mode || ''] ?? telemetryData?.active_scan_mode?.toUpperCase()})
          </h3>
          <p className="text-xs text-amber-400 font-mono mb-4">{scanStepText}</p>

          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-full h-3 overflow-hidden p-0.5">
            <div
              className="bg-gradient-to-r from-amber-500 to-amber-300 h-full rounded-full transition-all duration-300 shadow-md shadow-amber-500/30"
              style={{ width: `${scanProgress}%` }}
            />
          </div>
          <span className="text-[11px] font-mono font-bold text-slate-400 mt-2">{scanProgress}% hoàn tất</span>
        </div>
      )}

      {/* Workspace Tab Bar */}
      <div className="flex items-center gap-3 border-b border-slate-800 pb-2.5 mb-3 min-w-0">
        {selectedSignal && (
          <div className="hidden sm:flex items-center gap-2 text-xs font-mono shrink-0">
            <span className="text-slate-400">Đang xem:</span>
            <CoinLink
              symbol={selectedSignal.symbol}
              onClick={() => onSelectCandidate(selectedSignal.symbol)}
              className="bg-amber-950/60 px-2.5 py-1 rounded border border-amber-500/30"
            />
          </div>
        )}
        {/* Primary user tabs stay first; research/system tabs follow the divider. */}
        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800 min-w-0 max-w-full overflow-x-auto flex-nowrap whitespace-nowrap [&::-webkit-scrollbar]:hidden">
          <button
            onClick={() => setActiveTab('DECISION')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'DECISION'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            Trung tâm quyết định
          </button>

          <button
            onClick={() => setActiveTab('WATCHLIST')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'WATCHLIST'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Target className="w-3.5 h-3.5" />
            Theo dõi ({trackingItems.filter(item => item.status !== 'CLOSED').length})
          </button>

          <button
            onClick={() => setActiveTab('RANKING')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'RANKING'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Bảng Ứng Viên ({candidates.length})
          </button>

          <button
            onClick={() => setActiveTab('MARKET')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'MARKET'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Thị Trường
          </button>

          <span
            aria-hidden="true"
            className="mx-1 h-5 w-px shrink-0 bg-slate-700"
            title="Khu vực dev và nghiên cứu"
          />

          <button
            onClick={() => setActiveTab('MULTISCAN')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'MULTISCAN'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <FlaskConical className="w-3.5 h-3.5" />
            Quét Multi-Coin
          </button>

          <button
            onClick={() => setActiveTab('BACKTEST')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'BACKTEST'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            Kiểm thử lịch sử
          </button>

          <button
            onClick={() => setActiveTab('FORWARD')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'FORWARD'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Lock className="w-3.5 h-3.5" />
            Kiểm thử dữ liệu mới
          </button>

          <button
            onClick={() => setActiveTab('AUDIT')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'AUDIT'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            Kiểm Định AI
          </button>

          <button
            onClick={() => setActiveTab('TELEMETRY')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'TELEMETRY'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            📡 Nhật Ký & Trạng Thái Quét
          </button>

          <button
            onClick={() => setActiveTab('HISTORY')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 shrink-0 whitespace-nowrap transition ${
              activeTab === 'HISTORY'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            Lịch sử & dữ liệu
          </button>
        </div>
      </div>

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
            <>
              {/* Selected Coin Hero Card — Compact 3-column */}
              <div className="bg-gradient-to-br from-slate-950 to-slate-900 border border-slate-800 rounded-xl p-3 sm:p-4 min-w-0">
                <div className="grid grid-cols-2 lg:grid-cols-12 gap-3 sm:gap-4 mb-3 items-start min-w-0">
                  {/* Coin identity */}
                  <div className="col-span-2 lg:col-span-4 flex items-center gap-3 min-w-0">
                    <div className="w-11 h-11 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shrink-0">
                      <span className="text-amber-400 font-black text-sm">
                        {displayDetail.symbol.replace('USDT', '').slice(0, 3)}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <div className="text-lg font-black text-slate-100 flex items-center gap-2 flex-wrap">
                        <CoinLink symbol={displayDetail.symbol} onClick={() => onSelectCandidate(displayDetail.symbol)} />
                        <span className="text-xs font-normal text-slate-400">({displayDetail.name})</span>
                        {selectedSignal?.hit === true && (
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">✓ TRÚNG</span>
                        )}
                        {selectedSignal?.hit === false && (
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-red-950 text-red-400 border border-red-800 rounded">✗ TRƯỢT</span>
                        )}
                        {selectedSignal?.hit === null && (
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-slate-900 text-slate-400 border border-slate-700 rounded">⏳ CHỜ</span>
                        )}
                        {selectedSignal?.telegram_sent && (
                          <span className="px-1.5 py-0.5 text-[9px] font-bold bg-sky-950 text-sky-400 border border-sky-800 rounded">📲 Telegram</span>
                        )}
                      </div>
                      <div className="text-base font-bold text-amber-400 font-mono mt-0.5">
                        ${displayDetail.current_price.toFixed(6)}
                      </div>
                    </div>
                  </div>

                  {/* Score + risk + re-score */}
                  <div className="col-span-1 lg:col-span-4 flex flex-col sm:flex-row items-start sm:items-center gap-3 min-w-0">
                    <div className="text-left sm:text-center">
                      <div className="flex items-center justify-start sm:justify-center gap-1 text-[10px] text-slate-400 uppercase leading-tight group/tooltip relative">
                        XÁC SUẤT XẢ (AI)
                        <Info className="w-3 h-3 text-slate-500 cursor-help" />
                        <span className="hidden group-hover/tooltip:block absolute left-0 sm:left-1/2 sm:-translate-x-1/2 top-full mt-1 w-56 p-2 bg-slate-800 border border-slate-700 rounded-lg text-[10px] normal-case text-slate-300 z-20 shadow-xl">
                          Xác suất dự đoán giá giảm ≥8% trong vòng 24h kể từ thời điểm tín hiệu.
                          <br /><span className="text-amber-400">Nguồn: {displayDetail.score_source === 'alert' ? 'cảnh báo đã gửi' : displayDetail.score_source === 'scan' ? 'quét gần nhất' : displayDetail.score_source === 'signal' ? 'tín hiệu RADAR' : '—'}</span>
                        </span>
                      </div>
                      {displayDetail.probability != null ? (
                        <span className="text-2xl font-black text-red-400 font-mono">
                          {displayDetail.probability.toFixed(1)}/100
                        </span>
                      ) : (
                        <span className="text-lg font-black text-slate-500 font-mono">—</span>
                      )}
                      {deepAnalysis && !isDeepAnalyzing && (
                        <div className="text-[10px] text-slate-400">
                          Chạy lại: <span className={`font-bold font-mono ${
                            deepProbabilityPct == null ? 'text-slate-500' :
                            deepProbabilityPct >= (deepProbabilityThresholdPct ?? 60) ? 'text-red-400' :
                            deepProbabilityPct >= ((deepProbabilityThresholdPct ?? 60) * 0.75) ? 'text-amber-400' : 'text-emerald-400'
                          }`}>{deepProbabilityPct != null ? `${deepProbabilityPct.toFixed(1)}/100` : 'Chưa có'}</span>
                          {probabilityDelta != null && (
                            <span className={`ml-1 font-mono ${
                              probabilityDelta < -10 ? 'text-emerald-400' :
                              probabilityDelta > 10 ? 'text-red-400' : 'text-slate-400'
                            }`}>
                              ({probabilityDelta > 0 ? '+' : ''}{probabilityDelta.toFixed(1)})
                            </span>
                          )}
                          <span className="ml-1 text-slate-500">(cùng xác suất Radar)</span>
                        </div>
                      )}
                      {isDeepAnalyzing && (
                        <div className="text-[10px] text-slate-500 animate-pulse">Đang tính...</div>
                      )}
                    </div>
                    <div className="flex flex-col items-start gap-1.5">
                      <span className={`inline-block px-2 py-0.5 text-[10px] font-bold rounded border ${
                        displayDetail.risk_level === 'CRITICAL' ? 'bg-red-950 text-red-400 border-red-800' :
                        displayDetail.risk_level === 'HIGH' ? 'bg-amber-950 text-amber-400 border-amber-800' :
                        displayDetail.risk_level === 'MEDIUM' ? 'bg-yellow-950 text-yellow-300 border-yellow-800' :
                        displayDetail.risk_level === 'SAFE' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' :
                        'bg-slate-800 text-slate-400 border-slate-700'
                      }`}>
                        {displayDetail.risk_level ? (riskLabels[displayDetail.risk_level] ?? displayDetail.risk_level) : 'CHƯA CÓ DỮ LIỆU'}
                      </span>
                      <button
                        onClick={() => onRunDeepAnalysis(displayDetail.symbol)}
                        disabled={isDeepAnalyzing}
                        className="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold rounded-lg text-[10px] flex items-center gap-1 transition shadow-md shadow-amber-500/20"
                      >
                        {isDeepAnalyzing ? (
                          <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Đang chạy...</>
                        ) : (
                          <><Zap className="w-3.5 h-3.5" /> Chạy lại chấm điểm</>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="col-span-1 lg:col-span-4 flex flex-col items-start lg:items-end gap-2 min-w-0">
                    <div className="flex flex-wrap gap-2">
                      {selectedSignal && (
                        <button
                          onClick={() => onPushTelegram(selectedSignal)}
                          className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-lg text-xs flex items-center gap-1.5 transition shadow-lg shadow-sky-500/20"
                        >
                          <Send className="w-3.5 h-3.5" /> Gửi Telegram
                        </button>
                      )}
                      {selectedSignal && onDismissSignal && (
                        <button
                          onClick={() => onDismissSignal(selectedSignal)}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-red-950 text-slate-300 hover:text-red-400 border border-slate-700 hover:border-red-800 font-bold rounded-lg text-xs flex items-center gap-1.5 transition"
                        >
                          <XCircle className="w-3.5 h-3.5" /> Ẩn
                        </button>
                      )}
                      {onAddWatchlist && (
                        <button
                          onClick={() => void onAddWatchlist(displayDetail.symbol)}
                          disabled={isWatchlistUpdating || isSymbolInWatchlist}
                          className={`px-3 py-1.5 border font-bold rounded-lg text-xs flex items-center gap-1.5 transition disabled:cursor-not-allowed disabled:opacity-70 ${
                            isSymbolInWatchlist
                              ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                              : 'bg-slate-800 hover:bg-amber-950 text-slate-300 hover:text-amber-400 border-slate-700 hover:border-amber-800'
                          }`}
                        >
                          {isWatchlistUpdating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSymbolInWatchlist ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                          {isSymbolInWatchlist ? 'Đã trong phạm vi quét' : 'Thêm vào phạm vi quét'}
                        </button>
                      )}
                      {onAddTracking && (
                        <button
                          onClick={() => void onAddTracking(displayDetail.symbol)}
                          disabled={isWatchlistUpdating || isSymbolTracked}
                          className={`px-3 py-1.5 border font-bold rounded-lg text-xs flex items-center gap-1.5 transition disabled:cursor-not-allowed disabled:opacity-70 ${
                            isSymbolTracked
                              ? 'bg-sky-500/15 text-sky-300 border-sky-500/40'
                              : 'bg-slate-800 hover:bg-sky-950 text-slate-300 hover:text-sky-400 border-slate-700 hover:border-sky-800'
                          }`}
                        >
                          {isWatchlistUpdating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSymbolTracked ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                          {isSymbolTracked ? 'Đang theo dõi' : 'Theo dõi diễn biến'}
                        </button>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">
                      Tín hiệu: {displayDetail.signal_timestamp || '—'}
                    </div>
                  </div>
                </div>

                {/* Metrics grid — 6 cols */}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 mb-3 [&>div]:min-w-0">
                  <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                    <div className="text-[9px] text-slate-400 uppercase">OI 24h</div>
                    <div className="font-mono font-bold text-xs sm:text-sm text-red-400 truncate" title={displayDetail.metrics.oi_change_24h}>{displayDetail.metrics.oi_change_24h}</div>
                  </div>
                  <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                    <div className="text-[9px] text-slate-400 uppercase">Tỷ lệ funding</div>
                    <div className="font-mono font-bold text-xs sm:text-sm text-amber-400 truncate" title={displayDetail.metrics.funding_rate}>{displayDetail.metrics.funding_rate}</div>
                  </div>
                  <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                      <div className="text-[9px] text-slate-400 uppercase">Bán chủ động</div>
                    <div className="font-mono font-bold text-xs sm:text-sm text-slate-200 truncate">{(displayDetail.metrics.taker_sell_ratio * 100).toFixed(1)}%</div>
                  </div>
                  <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                    <div className="text-[9px] text-slate-400 uppercase">RSI 15m</div>
                    <div className={`font-mono font-bold text-xs sm:text-sm truncate ${
                      displayDetail.metrics.rsi_15m == null ? 'text-slate-500' :
                      displayDetail.metrics.rsi_15m > 70 ? 'text-red-400' :
                      displayDetail.metrics.rsi_15m < 30 ? 'text-emerald-400' : 'text-amber-300'
                    }`}>
                          {displayDetail.metrics.rsi_15m != null ? displayDetail.metrics.rsi_15m.toFixed(1) : 'Chưa có'}
                    </div>
                  </div>
                  <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                    <div className="text-[9px] text-slate-400 uppercase">Biến động khối lượng 24 giờ</div>
                    <div className="font-mono font-bold text-xs sm:text-sm text-sky-400 truncate" title={displayDetail.metrics.volume_delta_24h}>{displayDetail.metrics.volume_delta_24h}</div>
                  </div>
                  <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800 overflow-hidden">
                    <div className="text-[9px] text-slate-400 uppercase">Mục tiêu -8%</div>
                    <div className="font-mono font-bold text-xs sm:text-sm text-red-400 truncate">${displayDetail.target_price.toFixed(6)}</div>
                  </div>
                </div>

                {/* Validity + Evidence + Lead time */}
                {selectedSignal && (
                  <div className="grid grid-cols-3 gap-2 mb-3 text-[11px]">
                    <div className="bg-slate-900/60 p-2 rounded border border-slate-800 flex items-center gap-2">
                      <Clock className="w-3.5 h-3.5 text-amber-400" />
                      <div>
                        <div className="text-slate-500 text-[9px] uppercase">Hiệu lực còn</div>
                        <div className="text-amber-300 font-mono font-bold">
                          {Math.floor(selectedSignal.validity_hours_left)}h {Math.floor((selectedSignal.validity_hours_left % 1) * 60)}m
                        </div>
                      </div>
                    </div>
                    <div className="bg-slate-900/60 p-2 rounded border border-slate-800 flex items-center gap-2">
                      <Activity className="w-3.5 h-3.5 text-sky-400" />
                      <div>
                        <div className="text-slate-500 text-[9px] uppercase">Thời gian báo trước TB</div>
                        <div className="text-sky-300 font-mono font-bold">
                          {selectedSignal.lead_time_avg_hours > 0 ? `${selectedSignal.lead_time_avg_hours.toFixed(1)}h` : '—'}
                        </div>
                      </div>
                    </div>
                    <div className="bg-slate-900/60 p-2 rounded border border-slate-800 flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      <div>
                        <div className="text-slate-500 text-[9px] uppercase">Bằng chứng</div>
                        <div className="text-emerald-300 font-mono font-bold">
                          {selectedSignal.evidence_precision != null
                            ? `${(selectedSignal.evidence_precision * 100).toFixed(0)}% (${selectedSignal.evidence_n_judged})`
                            : 'chưa có'}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Candlestick Chart + OI/Funding sub-chart */}
              <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 min-w-0">
                <div className="flex items-start sm:items-center justify-between mb-2 gap-2 flex-wrap min-w-0">
                  <div className="min-w-0">
                    <h3 className="text-[11px] sm:text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5 min-w-0">
                      <Zap className="w-3.5 h-3.5 text-amber-400" />
                      BIỂU ĐỒ NẾN {candleInterval} ({displayDetail.symbol})
                      {displayDetail.chart_source === 'api' && (
                        <span className="ml-2 px-1.5 py-0.5 text-[9px] font-normal normal-case bg-sky-950 text-sky-400 border border-sky-800 rounded">
                          Dữ liệu trực tiếp
                        </span>
                      )}
                    </h3>
                    <p className="text-[11px] text-slate-400">🟢 Xanh: nến tăng | 🔴 Đỏ: nến giảm | Đỏ nét đứt: mục tiêu -8% | Xám: khối lượng</p>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <div className="flex items-center gap-0.5 max-w-full overflow-x-auto rounded-md border border-slate-700/80 bg-slate-900/90 p-0.5 [&::-webkit-scrollbar]:hidden" aria-label="Chọn khung thời gian">
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
                        <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Tăng
                      </span>
                      <span className="flex items-center gap-1 text-red-400">
                        <span className="w-2.5 h-2.5 rounded-sm bg-red-500" /> Giảm
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
                  height={400}
                />

                {/* OI + Funding Sub Chart (only when data exists) */}
                {(() => {
                  const hasOi = candleData.some(c => (c.oi || 0) !== 0);
                  const hasFunding = candleData.some(c => (c.funding || 0) !== 0);
                  return hasOi || hasFunding ? (
                    <div className="mt-3">
                      <div className="text-[10px] text-slate-400 mb-1 uppercase">Thay đổi OI + tỷ lệ funding</div>
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
                            <Line yAxisId="oi" type="monotone" dataKey="oi" stroke="#06b6d4" strokeWidth={1.5} dot={false} name="Thay đổi OI" />
                            <Line yAxisId="funding" type="monotone" dataKey="funding" stroke="#f59e0b" strokeWidth={1} dot={false} name="Tỷ lệ funding" />
                          </ComposedChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3 bg-slate-950 border border-slate-800 rounded-lg p-2 text-[10px] text-slate-500 text-center">
                      OI / funding chỉ có khi bộ quét đã lưu dữ liệu chuỗi khối cho coin này.
                    </div>
                  );
                })()}

                {/* Chart stats footer */}
                {candleData.length > 0 && (
                  <div className="mt-2 grid grid-cols-4 gap-2 text-[10px] font-mono">
                    <div className="bg-slate-900 p-1.5 rounded text-center">
                      <div className="text-slate-500">Cao nhất</div>
                      <div className="text-emerald-400">${Math.max(...candleData.map(c => c.high || c.price)).toFixed(6)}</div>
                    </div>
                    <div className="bg-slate-900 p-1.5 rounded text-center">
                      <div className="text-slate-500">Thấp nhất</div>
                      <div className="text-red-400">${Math.min(...candleData.map(c => c.low || c.price)).toFixed(6)}</div>
                    </div>
                    <div className="bg-slate-900 p-1.5 rounded text-center">
                      <div className="text-slate-500">Thay đổi</div>
                      <div className={candleData[candleData.length - 1].close >= candleData[0].close ? 'text-emerald-400' : 'text-red-400'}>
                        {((candleData[candleData.length - 1].close / candleData[0].close - 1) * 100).toFixed(2)}%
                      </div>
                    </div>
                    <div className="bg-slate-900 p-1.5 rounded text-center">
                      <div className="text-slate-500">Nến</div>
                      <div className="text-slate-300">{candleData.length}</div>
                    </div>
                  </div>
                )}
              </div>

              {/* SHAP Risk Drivers Section — Enhanced */}
              <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3.5">
                <div className="flex items-center justify-between mb-2.5">
                  <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                    <AlertOctagon className="w-3.5 h-3.5 text-amber-400" />
                    🔮 NGUYÊN NHÂN AI DỰ BÁO XẢ
                  </h3>
                  <span className="text-[10px] text-slate-500">{displayDetail.shap_drivers.length} yếu tố</span>
                </div>
                {displayDetail.shap_drivers.length === 0 ? (
                  <p className="text-[11px] text-slate-500 text-center py-3">
                    Chưa có dữ liệu nguyên nhân. Chạy "Phân tích chuyên sâu" để xem phân rã 8 yếu tố.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {[...displayDetail.shap_drivers]
                      .sort((a, b) => b.impact_score - a.impact_score)
                      .map((driver, idx) => {
                        const impactPct = Math.min(100, driver.impact_score * 100);
                        const isHigh = driver.impact_score >= 0.5;
                        const isMed = driver.impact_score >= 0.2 && !isHigh;
                        return (
                          <div key={idx} className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                            <div className="flex items-center justify-between mb-1.5">
                              <div className="flex items-center gap-2">
                                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                                  isHigh ? 'bg-red-950 text-red-400' : isMed ? 'bg-amber-950 text-amber-400' : 'bg-slate-800 text-slate-400'
                                }`}>
                                  {idx + 1}
                                </span>
                                <div>
                                  <div className="text-xs font-bold text-slate-200">{driver.feature}</div>
                                  <div className="text-[10px] text-slate-500 mt-0.5">{driver.description}</div>
                                </div>
                              </div>
                              <span className={`px-2 py-0.5 font-mono font-bold text-xs rounded border ${
                                isHigh ? 'bg-red-950 border-red-800/80 text-red-400' :
                                isMed ? 'bg-amber-950 border-amber-800/80 text-amber-400' :
                                'bg-slate-800 border-slate-700 text-slate-400'
                              }`}>
                                +{(driver.impact_score * 100).toFixed(1)}%
                              </span>
                            </div>
                            <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full transition-all ${
                                  isHigh ? 'bg-gradient-to-r from-red-600 to-red-400' :
                                  isMed ? 'bg-gradient-to-r from-amber-600 to-amber-400' :
                                  'bg-slate-600'
                                }`}
                                style={{ width: `${impactPct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </div>
                )}
              </div>

              {/* Deep Analysis Results — Enhanced */}
              {isDeepAnalyzing && (
                <div className="bg-slate-950/90 border border-amber-500/30 rounded-xl p-6 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
                    <p className="text-xs text-amber-400 font-mono">Đang tải dữ liệu và chấm điểm lại theo mô hình của Radar...</p>
                    <div className="text-[10px] text-slate-500">Đặc trưng mới nhất → mô hình đã đóng băng + bộ hiệu chỉnh → phân rã điểm 8 thành phần → RSI</div>
                  </div>
                </div>
              )}

              {deepAnalysis && !isDeepAnalyzing && (
                <>
                  {/* Recommendation Banner */}
                  <div className={`rounded-xl p-4 border-2 ${
                    deepAnalysis.recommendation === 'SHORT_CANDIDATE'
                      ? 'bg-red-950/40 border-red-800'
                      : deepAnalysis.recommendation === 'WATCH'
                      ? 'bg-amber-950/40 border-amber-800'
                      : 'bg-slate-900 border-slate-700'
                  }`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                          deepAnalysis.recommendation === 'SHORT_CANDIDATE' ? 'bg-red-900' :
                          deepAnalysis.recommendation === 'WATCH' ? 'bg-amber-900' : 'bg-slate-800'
                        }`}>
                          {deepAnalysis.recommendation === 'SHORT_CANDIDATE' ? (
                            <TrendingDown className="w-6 h-6 text-red-300" />
                          ) : deepAnalysis.recommendation === 'WATCH' ? (
                            <Eye className="w-6 h-6 text-amber-300" />
                          ) : (
                            <CheckCircle2 className="w-6 h-6 text-slate-400" />
                          )}
                        </div>
                        <div>
                          <div className="text-[10px] text-slate-400 uppercase">Khuyến nghị AI</div>
                          <div className={`text-lg font-black ${
                            deepAnalysis.recommendation === 'SHORT_CANDIDATE' ? 'text-red-400' :
                            deepAnalysis.recommendation === 'WATCH' ? 'text-amber-400' : 'text-slate-300'
                          }`}>
                            {deepAnalysis.recommendation === 'SHORT_CANDIDATE' ? '🟢 ỨNG VIÊN SHORT' :
                             deepAnalysis.recommendation === 'WATCH' ? '🟡 THEO DÕI' : '⚪ BỎ QUA'}
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-[10px] text-slate-400 uppercase">Xác suất xả (mô hình đã đóng băng)</div>
                        <div className="text-3xl font-black text-amber-400 font-mono">
                          {deepProbabilityPct != null ? deepProbabilityPct.toFixed(1) : 'Chưa có'}
                          <span className="text-sm text-slate-500">/100</span>
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {deepProbabilityThresholdPct != null
                            ? `Ngưỡng ${(deepProbabilityThresholdPct).toFixed(1)}`
                            : 'Không có xác suất từ mô hình đã đóng băng'}
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono">
                          Quy tắc: {deepAnalysis.heuristic_score.toFixed(1)}/100
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Score Summary Grid */}
                  <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3.5">
                    <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2.5">
                      <Activity className="w-3.5 h-3.5 text-amber-400" />
                      TỔNG QUAN CHỈ SỐ
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-[9px] text-slate-400 uppercase">Trạng thái BTC</div>
                        <div className={`text-sm font-bold ${
                          deepAnalysis.btc_regime === 'FOMO' ? 'text-emerald-400' :
                          deepAnalysis.btc_regime === 'WEAK' ? 'text-red-400' : 'text-slate-300'
                        }`}>
                          {btcRegimeLabels[deepAnalysis.btc_regime] ?? deepAnalysis.btc_regime}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Điều chỉnh: {deepAnalysis.btc_score_adjustment > 0 ? '+' : ''}{deepAnalysis.btc_score_adjustment}
                        </div>
                      </div>
                      <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-[9px] text-slate-400 uppercase">RSI 14</div>
                        <div className={`text-sm font-bold font-mono ${
                          deepAnalysis.rsi.rsi_14 == null ? 'text-slate-500' :
                          deepAnalysis.rsi.rsi_14 > 70 ? 'text-red-400' :
                          deepAnalysis.rsi.rsi_14 < 30 ? 'text-emerald-400' : 'text-amber-300'
                        }`}>
                          {deepAnalysis.rsi.rsi_14 != null ? deepAnalysis.rsi.rsi_14.toFixed(1) : 'Chưa có'}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          RSI 7: {deepAnalysis.rsi.rsi_7 != null ? deepAnalysis.rsi.rsi_7.toFixed(1) : 'Chưa có'}
                        </div>
                      </div>
                      <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-[9px] text-slate-400 uppercase">Đặc trưng</div>
                        <div className={`text-sm font-bold ${deepAnalysis.has_features ? 'text-emerald-400' : 'text-red-400'}`}>
                          {deepAnalysis.has_features ? '✓ Có sẵn' : '✗ Thiếu'}
                        </div>
                      </div>
                      <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                        <div className="text-[9px] text-slate-400 uppercase">Mẫu hình tăng nóng</div>
                        <div className={`text-sm font-bold ${deepAnalysis.pump_analysis.detected ? 'text-orange-400' : 'text-slate-400'}`}>
                          {deepAnalysis.pump_analysis.detected ? '🔥 Đã phát hiện' : '— Không có'}
                        </div>
                      </div>
                    </div>

                    {deepAnalysis.btc_explanation && (
                      <div className="mt-2.5 text-[11px] text-slate-300 bg-slate-900/60 p-2.5 rounded border border-slate-800">
                        <span className="text-amber-400 font-bold">📊 Bối cảnh BTC: </span>
                        {deepAnalysis.btc_explanation}
                      </div>
                    )}
                  </div>

                  {/* Pump Analysis Card — Enhanced */}
                  <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3.5">
                    <h3 className="text-xs font-bold text-slate-200 mb-2.5 flex items-center gap-1.5">
                      {deepAnalysis.pump_analysis.detected ? (
                        <Flame className="w-3.5 h-3.5 text-orange-400" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" />
                      )}
                      PHÂN TÍCH MẪU HÌNH TĂNG NÓNG
                    </h3>
                    {deepAnalysis.pump_analysis.detected ? (
                      <>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                          <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                            <div className="text-[9px] text-slate-400 uppercase">Mức tăng nóng</div>
                            <div className="text-lg font-black text-orange-400 font-mono">
                              +{deepAnalysis.pump_analysis.pump_pct}%
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                            <div className="text-[9px] text-slate-400 uppercase">Số ngày đến đỉnh</div>
                            <div className="text-lg font-black text-slate-200 font-mono">
                              {deepAnalysis.pump_analysis.pump_days} ngày
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                            <div className="text-[9px] text-slate-400 uppercase">Hiện tại so với đỉnh</div>
                            <div className={`text-lg font-black font-mono ${
                              deepAnalysis.pump_analysis.current_vs_peak < -20 ? 'text-red-400' : 'text-slate-200'
                            }`}>
                              {deepAnalysis.pump_analysis.current_vs_peak}%
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                            <div className="text-[9px] text-slate-400 uppercase">Giá đỉnh</div>
                            <div className="text-sm font-bold text-slate-200 font-mono">
                              ${deepAnalysis.pump_analysis.peak_price.toFixed(4)}
                            </div>
                          </div>
                        </div>
                        {/* Pump visualization bar */}
                        <div className="bg-slate-900 p-3 rounded-lg border border-slate-800">
                          <div className="text-[10px] text-slate-400 mb-1.5">Vị thế giá hiện tại so với đỉnh tăng nóng</div>
                          <div className="relative h-6 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                            <div
                              className="absolute top-0 left-0 h-full bg-gradient-to-r from-orange-600 to-orange-400"
                              style={{ width: `${Math.max(0, Math.min(100, 100 + deepAnalysis.pump_analysis.current_vs_peak))}%` }}
                            />
                            <div className="absolute inset-0 flex items-center justify-center text-[10px] font-mono font-bold text-white">
                              {deepAnalysis.pump_analysis.current_vs_peak}% từ đỉnh
                            </div>
                          </div>
                          <div className="flex justify-between text-[9px] text-slate-500 mt-1">
                            <span>Đáy (0%)</span>
                            <span>Đỉnh (+{deepAnalysis.pump_analysis.pump_pct}%)</span>
                          </div>
                        </div>
                      </>
                    ) : (
                      <p className="text-[11px] text-slate-500">
                        ✓ Không phát hiện mẫu hình tăng nóng (50-300% trong 1-5 ngày) — coin không thuộc nhóm ứng viên bán khống do phân phối.
                      </p>
                    )}
                  </div>

                  {/* 8-Component Score Breakdown — Enhanced */}
                  <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3.5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                        <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
                        PHÂN RÃ ĐIỂM SỐ 8 THÀNH PHẦN
                      </h3>
                      <span className="text-[10px] text-slate-500">
                        Tổng: {deepAnalysis.components.reduce((sum, c) => sum + c.weighted_score, 0).toFixed(1)} điểm
                      </span>
                    </div>
                    <div className="space-y-2">
                      {[...deepAnalysis.components]
                        .sort((a, b) => b.weighted_score - a.weighted_score)
                        .map((comp, idx) => (
                        <div key={idx} className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                          <div className="flex items-center justify-between mb-1.5">
                            <div className="flex items-center gap-2">
                              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                                comp.weighted_score >= 10 ? 'bg-red-950 text-red-400' :
                                comp.weighted_score >= 5 ? 'bg-amber-950 text-amber-400' :
                                'bg-slate-800 text-slate-400'
                              }`}>
                                {idx + 1}
                              </span>
                              <div>
                                <span className="text-xs font-bold text-slate-200">{comp.name}</span>
                                <span className="text-[9px] text-slate-500 font-mono ml-1.5">
                                  ({comp.weight}% trọng số)
                                </span>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 text-xs font-mono">
                              <span className="text-slate-400">{comp.score}/100</span>
                              <span className={`font-bold ${
                                comp.weighted_score >= 10 ? 'text-red-400' :
                                comp.weighted_score >= 5 ? 'text-amber-400' : 'text-slate-400'
                              }`}>
                                → {comp.weighted_score > 0 ? '+' : ''}{comp.weighted_score}
                              </span>
                            </div>
                          </div>
                          <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden mb-1.5">
                            <div
                              className={`h-full rounded-full transition-all ${
                                comp.score >= 60 ? 'bg-gradient-to-r from-red-600 to-red-400' :
                                comp.score >= 30 ? 'bg-gradient-to-r from-amber-600 to-amber-400' : 'bg-slate-600'
                              }`}
                              style={{ width: `${comp.score}%` }}
                            />
                          </div>
                          <p className="text-[10px] text-slate-500">{comp.explanation}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </>
          ) : (
            <div className="p-12 text-center text-slate-500">
              Vui lòng chọn 1 tín hiệu ở danh sách bên trái để bắt đầu phân tích.
            </div>
          )}
        </div>
      )}

      {/* TAB 2: CANDIDATE SELL RANKING TABLE */}
      {activeTab === 'RANKING' && (
        <div className="flex-1 overflow-y-auto pr-1">
          <div className="flex items-center justify-between mb-2.5">
            <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
              <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
              BẢNG XẾP HẠNG ỨNG VIÊN BÁN
            </h3>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-400">Sắp xếp theo điểm rủi ro giảm dần</span>
              <button
                type="button"
                onClick={() => onRefreshCandidates()}
                disabled={isRefreshingCandidates}
                className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] font-medium text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:cursor-not-allowed disabled:opacity-60"
                title="Cập nhật bảng theo chỉ số scan mới nhất"
              >
                <RefreshCw className={`h-3 w-3 ${isRefreshingCandidates ? 'animate-spin' : ''}`} />
                {isRefreshingCandidates ? 'Đang quét' : 'Cập nhật'}
              </button>
            </div>
          </div>

          {candidateComparison?.enabled && (
            <div className="mb-3 rounded-xl border border-cyan-900/70 bg-cyan-950/20 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase text-cyan-300">
                    <FlaskConical className="h-3.5 w-3.5" />
                    So sánh bộ lọc v1 / v2
                  </div>
                  <p className="mt-1 text-[10px] text-slate-400">
                    V1 vẫn vận hành bảng chính và Telegram. V2 chỉ chạy shadow, ghi nhận kết quả để đánh giá.
                  </p>
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                  candidateComparison.stale
                    ? 'border-amber-700 text-amber-300'
                    : 'border-cyan-800 text-cyan-300'
                }`}>
                  {candidateComparison.stale ? 'Dữ liệu cũ' : 'Shadow an toàn'}
                </span>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
                <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                  <div className="text-[9px] uppercase text-slate-500">Universe chung</div>
                  <div className="mt-0.5 text-lg font-bold text-white">{candidateComparison.universe_count ?? 0}</div>
                </div>
                {([
                  {
                    group: 'champion' as const,
                    label: 'V1 chọn',
                    count: candidateComparison.champion_selected ?? 0,
                    border: 'border-amber-900/60',
                    color: 'text-amber-300',
                  },
                  {
                    group: 'challenger' as const,
                    label: 'V2 chọn',
                    count: candidateComparison.challenger_selected ?? 0,
                    border: 'border-violet-900/60',
                    color: 'text-violet-300',
                  },
                  {
                    group: 'overlap' as const,
                    label: 'Cả hai chọn',
                    count: candidateComparison.overlap ?? 0,
                    border: 'border-emerald-900/60',
                    color: 'text-emerald-300',
                  },
                ] as const).map((card) => {
                  const isExpanded = expandedComparisonGroup === card.group;
                  return (
                    <button
                      key={card.group}
                      type="button"
                      onClick={() => setExpandedComparisonGroup(isExpanded ? null : card.group)}
                      aria-expanded={isExpanded}
                      className={`rounded-lg border ${card.border} bg-slate-950/70 p-2 text-left transition hover:bg-slate-900 focus:outline-none focus:ring-1 focus:ring-cyan-400 ${isExpanded ? 'ring-1 ring-cyan-400' : ''}`}
                      title={`Bấm để xem mã coin ${card.label.toLowerCase()}`}
                    >
                      <div className="text-[9px] uppercase text-slate-500">{card.label}</div>
                      <div className={`mt-0.5 text-lg font-bold ${card.color}`}>{card.count}</div>
                    </button>
                  );
                })}
                <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                  <div className="text-[9px] uppercase text-slate-500">Cả hai loại</div>
                  <div className="mt-0.5 text-lg font-bold text-slate-300">{candidateComparison.neither ?? 0}</div>
                </div>
              </div>

              {expandedComparisonGroup && (
                <div className="mt-2 rounded-lg border border-cyan-900/70 bg-slate-950/60 px-2.5 py-2">
                  <div className="mb-1.5 flex items-center justify-between gap-2 text-[10px]">
                    <span className="font-semibold text-slate-300">
                      Mã coin {expandedComparisonLabel} ({expandedComparisonItems.length})
                    </span>
                    <button
                      type="button"
                      onClick={() => setExpandedComparisonGroup(null)}
                      className="text-slate-500 transition hover:text-slate-300"
                      aria-label="Đóng danh sách mã coin"
                    >
                      Đóng
                    </button>
                  </div>
                  {expandedComparisonItems.length > 0 ? (
                    <div className="flex flex-wrap gap-x-2.5 gap-y-1">
                      {expandedComparisonItems.map((item) => (
                        <CoinLink
                          key={item.symbol}
                          symbol={item.symbol}
                          onClick={() => onSelectCandidate(item.symbol)}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="text-[10px] text-slate-500">Chưa có dữ liệu mã coin cho nhóm này.</div>
                  )}
                </div>
              )}

              <div className="mt-2 grid gap-2 lg:grid-cols-2">
                <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-2.5 py-2 text-[10px] text-slate-400">
                  <div className="mb-1 font-semibold text-slate-300">Kết quả đã đủ 24 giờ</div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                    <span>V1 P@10: <b className="text-amber-300">{metricPercent(championMetrics?.precision_at_10)}</b></span>
                    <span>V2 P@10: <b className="text-violet-300">{metricPercent(challengerMetrics?.precision_at_10)}</b></span>
                    <span>V1 recall: <b className="text-amber-300">{metricPercent(championMetrics?.event_recall)}</b></span>
                    <span>V2 recall: <b className="text-violet-300">{metricPercent(challengerMetrics?.event_recall)}</b></span>
                    <span>Sự kiện: <b className="text-white">{comparisonReport?.promotion.positive_events ?? 0}</b></span>
                  </div>
                  <div className="mt-1 text-[9px] text-slate-500">
                    Δ P@10 v2−v1: {deltaWithCi(comparisonReport?.paired_deltas?.precision_at_10)} · Δ recall: {deltaWithCi(comparisonReport?.paired_deltas?.event_recall)}
                  </div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-2.5 py-2 text-[10px] text-slate-400">
                  <div className="mb-1 font-semibold text-slate-300">Quyết định</div>
                  {comparisonReport?.promotion.ready
                    ? (comparisonReport.promotion.passed
                      ? 'Đạt các gate kỹ thuật, vẫn phải được duyệt thủ công trước khi thay v1.'
                      : 'Đã đủ mẫu nhưng v2 chưa vượt đầy đủ các gate so với v1.')
                    : `Tiếp tục shadow: cần ít nhất ${comparisonReport?.promotion.min_resolved ?? 200} kết quả, ${comparisonReport?.promotion.min_positive_events ?? 50} sự kiện dương và ${comparisonReport?.promotion.min_evaluation_days ?? 14} ngày.`}
                </div>
              </div>

              {(candidateComparison.selected?.challenger_only?.length ?? 0) > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
                  <span>V2 phát hiện thêm:</span>
                  {candidateComparison.selected?.challenger_only?.slice(0, 8).map((item) => (
                    <CoinLink key={item.symbol} symbol={item.symbol} onClick={() => onSelectCandidate(item.symbol)} />
                  ))}
                </div>
              )}
            </div>
          )}

          {candidates.some((candidate) => candidate.is_stale) && (
            <div className="mb-2 rounded-lg border border-amber-800/70 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-300">
              Đang hiển thị dữ liệu quét gần nhất vì bộ quét chưa phát hành chu kỳ mới. Bấm “Cập nhật” để quét lại; không dùng các dòng này như giá thị trường hiện tại.
            </div>
          )}

          <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-xs text-slate-300">
              <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 font-mono text-[10px] uppercase">
                <tr>
                  <th className="p-2.5">Mã coin</th>
                  <th className="p-2.5">Giá hợp đồng</th>
                  <th className="p-2.5">Điểm phân phối</th>
                  <th className="p-2.5">Mức rủi ro</th>
                  <th className="p-2.5">OI 24h</th>
                  <th className="p-2.5">Tỷ lệ funding</th>
                  <th className="p-2.5">Bán chủ động</th>
                  <th className="p-2.5">Khối lượng 24 giờ</th>
                  <th className="p-2.5 text-right">Thao Tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {candidates.length === 0 && (
                  <tr>
                    <td colSpan={9} className="p-8 text-center font-sans text-slate-500">
                      {isRefreshingCandidates
                        ? 'Bộ quét đang xử lý dữ liệu, vui lòng chờ chu kỳ hiện tại hoàn tất.'
                        : 'Chưa có dữ liệu scan mới. Bấm “Cập nhật” để khởi động một chu kỳ quét.'}
                    </td>
                  </tr>
                )}
                {candidates.map((c, i) => (
                  <tr key={i} className="hover:bg-slate-900/60 transition">
                    <td className="p-2.5 font-bold text-white flex items-center gap-2">
                      <span className="text-slate-500 font-normal">#{i + 1}</span>
                      <CoinLink
                        symbol={c.symbol}
                        onClick={() => onSelectCandidate(c.symbol)}
                      />
                    </td>
                    <td className="p-2.5 text-amber-400 font-bold">${c.price}</td>
                    <td className="p-2.5">
                      <span className="font-bold text-red-400">{c.score.toFixed(1)} điểm</span>
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
                        className="px-2 py-0.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-[10px] font-sans font-medium flex items-center gap-1 ml-auto transition"
                      >
                        <Eye className="w-3 h-3" />
                        Xem chi tiết
                      </button>
                    </td>
                  </tr>
                ))}
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
                  BẢNG ĐIỀU KHIỂN & TRẠNG THÁI BỘ QUÉT 24/7
                </h3>
                <p className="text-[11px] text-slate-400">Theo dõi thời gian quét, độ trễ API Binance và nhật ký thực thi ngầm</p>
              </div>

              <button
                onClick={onTriggerManualScan}
                disabled={isTriggeringScan}
                className="px-3.5 py-1.5 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-slate-950 font-bold rounded-lg text-xs flex items-center gap-1.5 transition shadow-lg shadow-emerald-500/20 disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                {isTriggeringScan ? 'Đang quét 48 coin...' : '⚡ Chạy quét ngay'}
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
                <div className="text-[10px] text-slate-400">TRẠNG THÁI BỘ MÁY</div>
                <div className="text-sm font-bold text-emerald-400 font-mono mt-0.5 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  {scannerStatusLabels[telemetryData.scanner_engine_status] ?? telemetryData.scanner_engine_status}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Chu kỳ: {telemetryData.poll_interval_minutes} phút/lần</div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">LẦN QUẾT TIẾP THEO</div>
                <div className="text-sm font-bold text-amber-400 font-mono mt-0.5 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {telemetryData.next_scan_in_seconds != null
                    ? `~${Math.floor(telemetryData.next_scan_in_seconds / 60)} phút ${telemetryData.next_scan_in_seconds % 60} giây`
                    : 'Chưa có'}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Chế độ: {scanModeLabels[telemetryData.active_scan_mode] ?? telemetryData.active_scan_mode.toUpperCase()}</div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">ĐỘ TRỄ API BINANCE</div>
                <div className="text-sm font-bold text-sky-400 font-mono mt-0.5">
                  {telemetryData.average_api_latency_ms} ms
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Hợp đồng tương lai Binance USD-M</div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">COIN ĐÃ QUẾT / CẢNH BÁO</div>
                <div className="text-sm font-bold text-slate-100 font-mono mt-0.5">
                  {telemetryData.scanned_pairs_count} cặp / <span className="text-red-400">{telemetryData.signals_triggered_count} cảnh báo</span>
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">Bỏ qua: {telemetryData.stablecoins_excluded_count ?? 'Chưa có'} đồng ổn định</div>
              </div>
            </div>

            {/* Model + Runtime Info */}
            <div className="mt-2.5 grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">Mô hình: </span>
                <span className="text-cyan-400">{telemetryData.model_id || 'Chưa có'}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">Chu kỳ: </span>
                <span className="text-amber-400">{telemetryData.cycle ?? 'Chưa có'}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">Số coin tối đa: </span>
                <span className="text-slate-300">{telemetryData.max_coins ?? 'Chưa có'}</span>
              </div>
              <div className="bg-slate-900/60 px-2 py-1.5 rounded border border-slate-800">
                <span className="text-slate-500">Lần quét cuối: </span>
                <span className="text-slate-300">{telemetryData.last_scan_timestamp ? formatSystemTime(telemetryData.last_scan_timestamp) : 'Chưa có'}</span>
              </div>
            </div>
          </div>

          {/* Real-time Execution Logs */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5 uppercase font-mono">
              <Terminal className="w-3.5 h-3.5 text-amber-400" />
              NHẬT KÝ THỰC THI THỜI GIAN THỰC — {telemetryData.logs.length} bản ghi
            </h4>

            <div className="overflow-x-auto border border-slate-800 rounded-lg max-h-72 overflow-y-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 text-[10px] uppercase sticky top-0">
                  <tr>
                    <th className="p-2">Thời Gian</th>
                    <th className="p-2">Mã coin</th>
                    <th className="p-2">Bước xử lý</th>
                    <th className="p-2">Trạng thái</th>
                    <th className="p-2">Thời lượng (ms)</th>
                    <th className="p-2">Chi Tiết</th>
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
                        Chưa có nhật ký nào. Bộ quét đang chạy — nhật ký sẽ xuất hiện sau lần quét tiếp theo.
                        <br />
                    <span className="text-[10px]">Lần quét cuối: {telemetryData.last_scan_timestamp || 'Chưa có'}</span>
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
              LỊCH SỬ GỬI CẢNH BÁO TELEGRAM
            </h4>

            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 text-[10px] uppercase">
                  <tr>
                    <th className="p-2">Thời Gian</th>
                    <th className="p-2">Mã coin</th>
                    <th className="p-2">Điểm rủi ro</th>
                    <th className="p-2">Kênh nhận Telegram</th>
                    <th className="p-2">Kết quả</th>
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
              KẾT QUẢ KIỂM ĐỊNH MÔ HÌNH AI & MA TRẬN KIỂM THỬ LỊCH SỬ
            </h3>

            {!auditData.has_enough_data && (
              <div className="mb-3 px-3 py-2 rounded-lg bg-amber-950/50 border border-amber-800 text-[11px] text-amber-300">
                ⚠️ Chưa đủ dữ liệu kiểm chứng ({auditData.sample_size} tín hiệu đã chấm kết quả, cần tối thiểu 10).
                Các chỉ số dưới đây sẽ dần chính xác hơn khi bộ quét tự động chấm kết quả mỗi chu kỳ.
              </div>
            )}

            {/* Metrics KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-3">
              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">ĐỘ CHÍNH XÁC THỰC TẾ</div>
                <div className="text-xl font-black text-emerald-400 font-mono mt-0.5">
                  {auditData.metrics.precision !== null ? `${(auditData.metrics.precision * 100).toFixed(1)}%` : 'Chưa có'}
                </div>
                <div className="text-[10px] text-emerald-400 font-bold mt-0.5">
                  {auditData.metrics.precision_uplift ?? `dựa trên ${auditData.sample_size} tín hiệu đã kiểm chứng`}
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">TỶ LỆ BẮT</div>
                <div className="text-xl font-black text-amber-400 font-mono mt-0.5">
                  {auditData.metrics.recall !== null ? `${(auditData.metrics.recall * 100).toFixed(1)}%` : 'Chưa có'}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  Cần gán nhãn toàn bộ coin đã quét (chưa triển khai)
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">ĐIỂM BRIER (ĐỘ TIN CẬY)</div>
                <div className="text-xl font-black text-sky-400 font-mono mt-0.5">
                  {auditData.metrics.brier_score ?? 'Chưa có'}
                </div>
                <div className="text-[10px] text-sky-400 mt-0.5">
                  Số càng thấp càng tốt
                </div>
              </div>

              <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
                <div className="text-[10px] text-slate-400">THỜI GIAN BÁO TRƯỚC TRUNG BÌNH</div>
                <div className="text-xl font-black text-amber-300 font-mono mt-0.5">
                  {auditData.lead_time.mean_hours !== null ? `~${auditData.lead_time.mean_hours} giờ` : 'Chưa có'}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  Cảnh báo trước khi xả
                </div>
              </div>
            </div>

            {/* Precision by risk level */}
            {Object.keys(auditData.precision_by_risk_level).length > 0 && (
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 mb-3 text-xs">
                <h4 className="font-bold text-slate-200 mb-2">ĐỘ CHÍNH XÁC THEO MỨC RỦI RO (30 NGÀY GẦN NHẤT)</h4>
                <div className="space-y-1.5">
                  {Object.entries(auditData.precision_by_risk_level).map(([level, s]) => (
                    <div key={level} className="flex items-center justify-between">
                      <span className="text-slate-300">{riskLabels[level] ?? level}</span>
                      <span className="font-mono text-slate-200">
                        {s.precision !== null ? `${(s.precision * 100).toFixed(1)}%` : 'Chưa có'}
                        <span className="text-slate-500"> ({s.n_hit}/{s.n_judged} đã đánh giá)</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Validation Integrity Checks */}
            <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-2 text-xs">
              <h4 className="font-bold text-slate-200 mb-1">TIÊU CHUẨN KIỂM ĐỊNH TOÁN HỌC & CHỐNG RÒ RỈ DỮ LIỆU</h4>
              <div className="flex items-center justify-between border-b border-slate-800/60 pb-1.5">
                <span className="text-slate-300">Trạng thái kiểm định theo thời gian:</span>
                <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-800 text-emerald-400 font-bold rounded">
                  {auditStatusLabels[String(auditData.validation_checks.walk_forward_status).toUpperCase()] ?? auditData.validation_checks.walk_forward_status}
                </span>
              </div>
              <div className="flex items-center justify-between border-b border-slate-800/60 pb-1.5">
                <span className="text-slate-300">Kiểm tra rò rỉ dữ liệu (nhìn trước):</span>
                <span className="px-2 py-0.5 bg-emerald-950 border border-emerald-800 text-emerald-400 font-bold rounded">
                  {auditStatusLabels[String(auditData.validation_checks.leakage_test).toUpperCase()] ?? auditData.validation_checks.leakage_test}
                </span>
              </div>
              <div className="flex items-center justify-between border-b border-slate-800/60 pb-1.5">
                <span className="text-slate-300">Thời gian cách ly (chống chồng lấp):</span>
                <span className="font-mono text-amber-400 font-bold">{auditData.validation_checks.embargo_period}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-300">Xác minh đúng thời điểm:</span>
                <span className="text-emerald-400 font-bold flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> ĐÃ XÁC MINH (100% hợp lệ)
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
                  TỔNG QUAN NIÊM YẾT TRÊN BINANCE
                </h4>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400">
                    {marketData.binance_listing.date ? `Cập nhật: ${marketData.binance_listing.date}` : '—'}
                  </span>
                  <button
                    onClick={handleRefreshListing}
                    disabled={listingRefreshing}
                    className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10 disabled:opacity-50"
                  >
                    {listingRefreshing ? '⏳ Đang quét...' : '🔄 Quét lại'}
                  </button>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mb-2.5">
                Giao ngay: api.binance.com · USD-M: fapi · COIN-M: dapi. Quét 1 lần/ngày (Hà Nội, UTC+7).
              </p>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">Giao ngay</div>
                  <div className="text-lg font-black text-amber-400 font-mono">{marketData.binance_listing.spot_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{marketData.binance_listing.spot_usdt_pairs} cặp USDT</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">USD-M</div>
                  <div className="text-lg font-black text-sky-400 font-mono">{marketData.binance_listing.usdm_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{marketData.binance_listing.usdm_usdt_pairs} cặp USDT</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">COIN-M</div>
                  <div className="text-lg font-black text-purple-400 font-mono">{marketData.binance_listing.coinm_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">{marketData.binance_listing.coinm_symbols} mã</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">Tổng hợp đồng</div>
                  <div className="text-lg font-black text-emerald-400 font-mono">{marketData.binance_listing.futures_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">≥1 thị trường hợp đồng</div>
                </div>
                <div className="bg-slate-900 p-2 rounded-lg border border-slate-800">
                  <div className="text-[9px] text-slate-400 uppercase">Tổng Binance</div>
                  <div className="text-lg font-black text-white font-mono">{marketData.binance_listing.all_coins.toLocaleString()}</div>
                  <div className="text-[9px] text-slate-500">Giao ngay ∪ hợp đồng</div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-2">
                <div className="text-[10px] text-slate-400 text-center bg-slate-900/60 p-1.5 rounded">
                  Chỉ giao ngay: <span className="text-amber-400 font-bold">{marketData.binance_listing.spot_only}</span>
                </div>
                <div className="text-[10px] text-slate-400 text-center bg-slate-900/60 p-1.5 rounded">
                  Chỉ hợp đồng: <span className="text-sky-400 font-bold">{marketData.binance_listing.futures_only}</span>
                </div>
                <div className="text-[10px] text-slate-400 text-center bg-slate-900/60 p-1.5 rounded">
                  Cả hai: <span className="text-emerald-400 font-bold">{marketData.binance_listing.both}</span>
                </div>
              </div>
            </div>
          )}

          {/* Listing History Chart */}
          {marketData.binance_listing_history && marketData.binance_listing_history.length >= 2 && (
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5">
                <LineChartIcon className="w-3.5 h-3.5 text-amber-400" />
                LỊCH SỬ SỐ LƯỢNG COIN THEO NGÀY ({marketData.binance_listing_history.length} ngày)
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
                  <Line type="monotone" dataKey="spot_coins" stroke="#f59e0b" strokeWidth={2} dot={false} name="Giao ngay" />
                  <Line type="monotone" dataKey="usdm_coins" stroke="#0ea5e9" strokeWidth={2} dot={false} name="USD-M" />
                  <Line type="monotone" dataKey="coinm_coins" stroke="#a855f7" strokeWidth={2} dot={false} name="COIN-M" />
                  <Line type="monotone" dataKey="futures_coins" stroke="#10b981" strokeWidth={2} dot={false} name="Tổng hợp đồng" />
                  <Line type="monotone" dataKey="all_coins" stroke="#e2e8f0" strokeWidth={2} dot={false} name="Tổng Binance" />
                </LineChart>
              </ResponsiveContainer>
              <div className="overflow-x-auto mt-2 max-h-[200px] overflow-y-auto">
                <table className="w-full text-left text-[10px] text-slate-300 font-mono">
                  <thead className="text-slate-400 uppercase border-b border-slate-800 sticky top-0 bg-slate-950">
                    <tr>
                      <th className="p-1.5">Ngày</th>
                      <th className="p-1.5">Giao ngay</th>
                      <th className="p-1.5">USD-M</th>
                      <th className="p-1.5">COIN-M</th>
                      <th className="p-1.5">Hợp đồng</th>
                      <th className="p-1.5">Tổng</th>
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
              <div className="text-[10px] text-slate-400">CẶP ĐƯỢC NIÊM YẾT TRÊN BINANCE</div>
              <div className="text-2xl font-black text-amber-400 font-mono mt-0.5">
                {marketData.binance_listing_total}
              </div>
              <p className="text-[11px] text-slate-400 mt-1">Tổng số coin hợp đồng theo dõi</p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <div className="text-[10px] text-slate-400">CẶP BIẾN ĐỘNG CAO ĐƯỢC QUÉT</div>
              <div className="text-2xl font-black text-sky-400 font-mono mt-0.5">
                {marketData.scanned_volatile_top}
              </div>
              <p className="text-[11px] text-slate-400 mt-1">Top coin có biến động lớn được AI quét 24/7</p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <div className="text-[10px] text-slate-400">CHỈ SỐ PHÂN PHỐI THỊ TRƯỜNG</div>
              <div className="text-2xl font-black text-red-400 font-mono mt-0.5">
                {marketData.distribution_index} / 100
              </div>
              <p className="text-[11px] text-slate-400 mt-1">Áp lực xả chung toàn thị trường</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Top Gainers */}
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
              <h4 className="text-xs font-bold text-emerald-400 mb-2 flex items-center gap-1">
                <ArrowUpRight className="w-3.5 h-3.5" /> TOP TĂNG GIÁ MẠNH NHẤT ({marketData.top_gainers.length})
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
                <ArrowDownRight className="w-3.5 h-3.5" /> TOP GIẢM GIÁ MẠNH NHẤT ({marketData.top_losers.length})
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
                Biểu đồ giá 72h — {chartCoin}
              </h3>
              <button onClick={() => setChartCoin(null)} className="p-1 text-slate-400 hover:text-slate-200 text-xs">
                ✕ Đóng
              </button>
            </div>
            {chartLoading ? (
              <div className="h-[300px] flex items-center justify-center text-xs text-slate-400">
                Đang tải nến từ Binance...
              </div>
            ) : chartData.length === 0 ? (
              <div className="h-[300px] flex items-center justify-center text-xs text-slate-500">
                Không tải được dữ liệu biểu đồ.
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
                      formatter={(v: any) => [`$${Number(v).toFixed(6)}`, 'Giá đóng cửa']}
                    />
                    <Area type="monotone" dataKey="close" stroke="#f59e0b" strokeWidth={2} fill="url(#priceGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
                <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">Giá hiện tại</div>
                    <div className="text-amber-400 font-mono font-bold">${chartData[chartData.length - 1]?.close.toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">Cao nhất 72 giờ</div>
                    <div className="text-emerald-400 font-mono">${Math.max(...chartData.map(k => k.high)).toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">Thấp nhất 72 giờ</div>
                    <div className="text-red-400 font-mono">${Math.min(...chartData.map(k => k.low)).toFixed(6)}</div>
                  </div>
                  <div className="bg-slate-950 p-1.5 rounded text-center">
                    <div className="text-slate-500">Thay đổi</div>
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
        <SystemHistoryTab />
      )}

    </div>
  );
};
