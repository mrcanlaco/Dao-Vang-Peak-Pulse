import { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { SignalFeed } from './components/SignalFeed';
import { MainWorkspace } from './components/MainWorkspace';
import { ActionDrawer } from './components/ActionDrawer';
import { GlossaryModal } from './components/GlossaryModal';
import { WatchlistModal } from './components/WatchlistModal';
import type {
  SignalItem, CoinDetail, CandidateCoin, CandidateFilterComparison, ModelAudit, MarketOverviewData, SystemStatus, FilterTag, SignalSort, TelegramFilter, AutomationSettings, ScannerTelemetry, WatchlistPreset, DeepAnalysis, ModelChoice, ModelsData, TrackingWatchlistItem
} from './types';
import { parseSystemDate } from './utils/time';
import { useTranslation, type Language } from './i18n/LanguageContext';

export function App() {
  const { language } = useTranslation();

  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [signals, setSignals] = useState<SignalItem[]>([]);
  const [candidates, setCandidates] = useState<CandidateCoin[]>([]);
  const [candidateComparison, setCandidateComparison] = useState<CandidateFilterComparison | null>(null);
  const [auditData, setAuditData] = useState<ModelAudit | null>(null);
  const [marketData, setMarketData] = useState<MarketOverviewData | null>(null);
  const [telemetryData, setTelemetryData] = useState<ScannerTelemetry | null>(null);
  const [watchlistPresets, setWatchlistPresets] = useState<WatchlistPreset[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelChoice[]>([]);
  const [selectedModelKey, setSelectedModelKey] = useState<string>('heuristic_composite');
  const [scannerModelId, setScannerModelId] = useState<string>('');

  const [activeScanModes, setActiveScanModes] = useState<string[]>(['volatile']);
  const [manualWatchlist, setManualWatchlist] = useState<string[]>([]);
  const [trackingItems, setTrackingItems] = useState<TrackingWatchlistItem[]>([]);
  const [isTrackingLoading, setIsTrackingLoading] = useState(false);
  const [trackingUpdatingId, setTrackingUpdatingId] = useState<string | null>(null);
  const [isWatchlistModalOpen, setIsWatchlistModalOpen] = useState(false);
  const [watchlistPendingAction, setWatchlistPendingAction] = useState<string | null>(null);
  const [watchlistFeedback, setWatchlistFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  useEffect(() => {
    if (!watchlistFeedback) return undefined;
    const timeoutId = window.setTimeout(() => setWatchlistFeedback(null), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [watchlistFeedback]);

  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<SignalItem | null>(null);
  const [coinDetail, setCoinDetail] = useState<CoinDetail | null>(null);
  const [deepAnalysis, setDeepAnalysis] = useState<DeepAnalysis | null>(null);
  const [isDeepAnalyzing, setIsDeepAnalyzing] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRiskFilter, setSelectedRiskFilter] = useState('ALL');
  const [activeFilterTag, setActiveFilterTag] = useState<FilterTag>('ALL');
  const [signalSort, setSignalSort] = useState<SignalSort>('NEWEST');
  const [telegramFilter, setTelegramFilter] = useState<TelegramFilter>('ALL');
  const [threshold, setThreshold] = useState(0.25);

  const [automationSettings, setAutomationSettings] = useState<AutomationSettings>({
    autoTelegramPush: true,
    autoPushThreshold: 0.80,
    audioAlertEnabled: true,
    webhookUrl: ''
  });

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRefreshingCandidates, setIsRefreshingCandidates] = useState(false);
  const [loadingStep, setLoadingStep] = useState<string | null>(null);
  const [isTriggeringScan, setIsTriggeringScan] = useState(false);
  const [scanTriggeredSuccess, setScanTriggeredSuccess] = useState<string | null>(null);

  const [isGlossaryOpen, setIsGlossaryOpen] = useState(false);
  const [telegramSentSuccess, setTelegramSentSuccess] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<'DECISION' | 'WATCHLIST' | 'RANKING' | 'MULTISCAN' | 'BACKTEST' | 'FORWARD' | 'AUDIT' | 'MARKET' | 'TELEMETRY' | 'HISTORY'>('DECISION');
  const [isActionDrawerOpen, setIsActionDrawerOpen] = useState(false);
  const [isRadarCollapsed, setIsRadarCollapsed] = useState(false);

  const getStepText = (stepKey: string, lang: Language) => {
    const steps: Record<string, Record<string, string>> = {
      init: { vi: 'Đang khởi tạo kết nối máy chủ...', en: 'Initializing server connection...', zh: '正在初始化服务器连接...', ko: '서버 연결 초기화 중...' },
      s1: { vi: '1/8: Tải trạng thái hệ thống...', en: '1/8: Loading system status...', zh: '1/8: 正在加载系统状态...', ko: '1/8: 시스템 상태 로드 중...' },
      s2: { vi: '2/8: Tải tín hiệu cảnh báo Radar...', en: '2/8: Loading Radar alert signals...', zh: '2/8: 正在加载雷达预警信号...', ko: '2/8: 레이더 경보 신호 로드 중...' },
      s3: { vi: '3/8: Tải danh sách ứng viên xả...', en: '3/8: Loading dump candidates...', zh: '3/8: 正在加载做空候选榜...', ko: '3/8: 덤프 후보 목록 로드 중...' },
      s4: { vi: '4/8: Tải dữ liệu kiểm định mô hình...', en: '4/8: Loading model audit & validation...', zh: '4/8: 正在加载模型审计与验证...', ko: '4/8: 모델 감사 및 검증 데이터 로드 중...' },
      s5: { vi: '5/8: Tải thông tin thị trường...', en: '5/8: Loading market context...', zh: '5/8: 正在加载市场宏观环境...', ko: '5/8: 시장 환경 데이터 로드 중...' },
      s6: { vi: '6/8: Tải danh sách theo dõi và giá Binance 24 giờ...', en: '6/8: Loading watchlist & tracking items...', zh: '6/8: 正在加载跟踪列表与 24h 价格...', ko: '6/8: 관심목록 및 24시간 가격 로드 중...' },
      s7: { vi: '7/8: Tải thông số giám sát bộ quét...', en: '7/8: Loading scanner telemetry...', zh: '7/8: 正在加载扫描器遥测指标...', ko: '7/8: 스캐너 텔레메트리 지표 로드 중...' },
      s8: { vi: '8/8: Tải danh sách mô hình...', en: '8/8: Loading AI models...', zh: '8/8: 正在加载 AI 模型列表...', ko: '8/8: AI 모델 목록 로드 중...' },
    };
    return steps[stepKey]?.[lang] ?? steps[stepKey]?.['en'] ?? stepKey;
  };

  const fetchJsonOr = async <T,>(url: string, fallback: T): Promise<T> => {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) return fallback;
      return await res.json() as T;
    } catch {
      return fallback;
    }
  };

  const loadSignals = async (): Promise<SignalItem[] | null> => {
    try {
      const res = await fetch('/api/signals', { cache: 'no-store' });
      if (!res.ok) return null;
      const payload = await res.json() as unknown;
      return Array.isArray(payload) ? payload as SignalItem[] : null;
    } catch {
      return null;
    }
  };

  const loadTrackingWatchlist = async (): Promise<TrackingWatchlistItem[]> => {
    try {
      const res = await fetch('/api/tracking-watchlist', { cache: 'no-store' });
      if (!res.ok) return [];
      const payload = await res.json() as unknown;
      return Array.isArray(payload) ? payload as TrackingWatchlistItem[] : [];
    } catch {
      return [];
    }
  };

  const refreshTrackingWatchlist = async () => {
    setIsTrackingLoading(true);
    try {
      setTrackingItems(await loadTrackingWatchlist());
    } finally {
      setIsTrackingLoading(false);
    }
  };

  const loadCandidates = async (): Promise<CandidateCoin[]> => {
    const res = await fetchJsonOr<CandidateCoin[] | null>('/api/candidates', null);
    return Array.isArray(res) ? res : [];
  };

  const loadCandidateComparison = async (): Promise<CandidateFilterComparison | null> => {
    return fetchJsonOr<CandidateFilterComparison | null>('/api/candidates/compare', null);
  };

  const handleRefreshCandidates = async () => {
    setIsRefreshingCandidates(true);
    try {
      const res = await fetch('/api/candidates/refresh', { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (Array.isArray(data?.candidates)) {
        setCandidates(data.candidates);
      } else {
        setCandidates(await loadCandidates());
      }
      setCandidateComparison(await loadCandidateComparison());
    } catch (err) {
      console.error('Candidate ranking refresh error:', err);
    } finally {
      setIsRefreshingCandidates(false);
    }
  };

  // Fetch initial data & telemetry with progress tracking
  const fetchData = async () => {
    setIsRefreshing(true);
    setLoadingStep(getStepText('init', language));
    try {
      setLoadingStep(getStepText('s1', language));
      const statusRes = await fetchJsonOr<SystemStatus | null>('/api/status', null);

      setLoadingStep(getStepText('s2', language));
      const sigRes = await loadSignals();

      setLoadingStep(getStepText('s3', language));
      const candRes = await loadCandidates().catch(() => []);
      const comparisonRes = await loadCandidateComparison();

      setLoadingStep(getStepText('s4', language));
      const auditRes = await fetchJsonOr<ModelAudit | null>('/api/audit', null);

      setLoadingStep(getStepText('s5', language));
      const mktRes = await fetchJsonOr<MarketOverviewData | null>('/api/market', null);

      setLoadingStep(getStepText('s6', language));
      const wlRes = await fetchJsonOr<{
        active_scan_mode?: string;
        active_scan_modes?: string[];
        manual_watchlist?: string[];
        presets?: WatchlistPreset[];
      } | null>('/api/watchlist', null);

      const trackingRes = await fetchJsonOr<TrackingWatchlistItem[]>('/api/tracking-watchlist', []);

      setLoadingStep(getStepText('s7', language));
      const telemRes = await fetchJsonOr<ScannerTelemetry | null>('/api/scanner/telemetry', null);

      setLoadingStep(getStepText('s8', language));
      const modelsRes = await fetchJsonOr<ModelsData | null>('/api/models', null);

      setStatus(statusRes);
      if (sigRes !== null) setSignals(sigRes);
      setCandidates(candRes);
      setCandidateComparison(comparisonRes);
      setAuditData(auditRes);
      setMarketData(mktRes);
      setTelemetryData(telemRes);
      setTrackingItems(trackingRes);
      if (modelsRes) {
        setAvailableModels(modelsRes.models);
        setScannerModelId(modelsRes.current_scanner_model_id || '');
        const currentKey = modelsRes.models.find(
          (m) => m.frozen_model_id === modelsRes.current_scanner_model_id
        )?.key;
        if (currentKey) setSelectedModelKey(currentKey);
      }
      if (wlRes) {
        const modes = Array.isArray(wlRes.active_scan_modes) && wlRes.active_scan_modes.length > 0
          ? wlRes.active_scan_modes
          : (wlRes.active_scan_mode || 'volatile').split(',').map((mode) => mode.trim()).filter(Boolean);
        setActiveScanModes(modes.length > 0 ? modes : ['volatile']);
        setManualWatchlist(wlRes.manual_watchlist || []);
        if (wlRes.presets) setWatchlistPresets(wlRes.presets);
      }

      const hashSymbol = typeof window !== 'undefined'
        ? (window.location.hash.match(/^#coin=([A-Za-z0-9]+)$/)?.[1]?.toUpperCase() || null)
        : null;

      if (sigRes && sigRes.length > 0 && !selectedSignalId && !hashSymbol) {
        setSelectedSignalId(sigRes[0].id);
        setSelectedSignal(sigRes[0]);
        fetchCoinDetail(sigRes[0].symbol);
      }
    } catch (err) {
      console.error("Error loading API data:", err);
    } finally {
      setIsRefreshing(false);
      setLoadingStep(null);
    }
  };

  const fetchCoinDetail = async (symbol: string) => {
    try {
      const res = await fetch(`/api/coin/${symbol}`);
      const data = await res.json();
      setCoinDetail(data);
    } catch (err) {
      console.error(`Error loading detail for ${symbol}:`, err);
    }
  };

  useEffect(() => {
    fetchData();

    const timer = setInterval(async () => {
      const freshSignals = await loadSignals();
      if (freshSignals !== null) setSignals(freshSignals);
      try {
        setTrackingItems(await loadTrackingWatchlist());
      } catch {
        // keep previous snapshot
      }
      const freshComparison = await loadCandidateComparison();
      if (freshComparison !== null) setCandidateComparison(freshComparison);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  // Load coin from URL hash on mount
  useEffect(() => {
    const hash = window.location.hash;
    const match = hash.match(/^#coin=([A-Za-z0-9]+)$/);
    if (match) {
      const symbol = match[1].toUpperCase();
      if (symbol) {
        setSelectedSignalId(null);
        setSelectedSignal(null);
        setDeepAnalysis(null);
        setActiveTab('DECISION');
        fetchCoinDetail(symbol);
        handleRunDeepAnalysis(symbol);
      }
    }
  }, []);

  const handleSelectSignal = (sig: SignalItem) => {
    setSelectedSignalId(sig.id);
    setSelectedSignal(sig);
    setDeepAnalysis(null);
    setActiveTab('DECISION');
    fetchCoinDetail(sig.symbol);
    handleRunDeepAnalysis(sig.symbol);
  };

  const handleSelectCandidate = (symbol: string) => {
    const existingSig = signals.find(s => s.symbol === symbol);
    if (existingSig) {
      handleSelectSignal(existingSig);
      return;
    }
    setSelectedSignalId(null);
    setSelectedSignal(null);
    setDeepAnalysis(null);
    setActiveTab('DECISION');
    fetchCoinDetail(symbol);
    handleRunDeepAnalysis(symbol);
  };

  const handlePushTelegram = async (sig: SignalItem) => {
    try {
      await fetch('/api/telegram/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sig.symbol, probability: sig.probability })
      });
      const successMsg = language === 'en'
        ? `Dispatched ${sig.symbol} alert to Telegram!`
        : language === 'zh'
        ? `已将 ${sig.symbol} 警报推送至 Telegram！`
        : language === 'ko'
        ? `${sig.symbol} 텔레그램 경보가 발송되었습니다!`
        : `Đã gửi cảnh báo ${sig.symbol} sang Telegram!`;
      setTelegramSentSuccess(successMsg);
      setTimeout(() => setTelegramSentSuccess(null), 4000);
    } catch (err) {
      console.error("Telegram push error:", err);
    }
  };

  const handleDismissSignal = async (sig: SignalItem) => {
    try {
      await fetch('/api/alerts/dismiss', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alert_id: sig.id })
      });
      setSignals(prev => prev.filter(s => s.id !== sig.id));
      if (selectedSignalId === sig.id) {
        setSelectedSignalId(null);
        setSelectedSignal(null);
        setCoinDetail(null);
        setDeepAnalysis(null);
      }
    } catch (err) {
      console.error("Error dismissing signal:", err);
    }
  };

  const handleTriggerManualScan = async () => {
    setIsTriggeringScan(true);
    setScanTriggeredSuccess(null);
    try {
      const res = await fetch('/api/scanner/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: true })
      });
      const data = await res.json();
      const successMsg = language === 'en'
        ? `Manual scan completed! Inspected ${data.symbols_scanned ?? 48} pairs across Binance futures.`
        : language === 'zh'
        ? `手动扫描完成！已对 Binance 合约 ${data.symbols_scanned ?? 48} 个交易对完成深度量化分析。`
        : language === 'ko'
        ? `수동 스캔 완료! 바이낸스 선물 ${data.symbols_scanned ?? 48}개 페어 분석을 마쳤습니다.`
        : `Đã kích hoạt quét thành công! Đã quét ${data.symbols_scanned ?? 48} mã trên Binance Futures.`;
      setScanTriggeredSuccess(successMsg);
      await fetchData();
      setTimeout(() => setScanTriggeredSuccess(null), 6000);
    } catch (err) {
      console.error("Error triggering manual scan:", err);
    } finally {
      setIsTriggeringScan(false);
    }
  };

  const handleAddManualCoin = async (symbol: string): Promise<boolean> => {
    const nextSymbol = symbol.trim().toUpperCase();
    if (!nextSymbol) return false;

    setWatchlistPendingAction(`add:${nextSymbol}`);
    setWatchlistFeedback(null);
    try {
      const res = await fetch('/api/watchlist/manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: nextSymbol })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || (language === 'en' ? `Failed to add ${nextSymbol}` : `Không thể thêm ${nextSymbol}`));

      setManualWatchlist(data.manual_watchlist || [...manualWatchlist, nextSymbol]);
      const successMsg = language === 'en'
        ? `Added ${nextSymbol} to custom watchlist.`
        : language === 'zh'
        ? `已将 ${nextSymbol} 添加至自定义扫描列表。`
        : language === 'ko'
        ? `${nextSymbol}이(가) 관심 스캔 목록에 추가되었습니다.`
        : `Đã thêm ${nextSymbol} vào danh sách theo dõi cá nhân.`;
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : (language === 'en' ? 'Failed to add symbol.' : 'Không thể thêm coin.');
      setWatchlistFeedback({ type: 'error', message });
      console.error("Error adding manual coin:", err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const handleRemoveManualCoin = async (symbol: string): Promise<boolean> => {
    setWatchlistPendingAction(`remove:${symbol}`);
    setWatchlistFeedback(null);
    try {
      const res = await fetch(`/api/watchlist/manual/${symbol}`, {
        method: 'DELETE'
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || (language === 'en' ? `Failed to remove ${symbol}` : `Không thể xóa ${symbol}`));

      setManualWatchlist(data.manual_watchlist || manualWatchlist.filter((item) => item !== symbol));
      const successMsg = language === 'en'
        ? `Removed ${symbol} from custom watchlist.`
        : language === 'zh'
        ? `已将 ${symbol} 从自定义扫描列表中移除。`
        : language === 'ko'
        ? `${symbol}이(가) 관심 스캔 목록에서 삭제되었습니다.`
        : `Đã xóa ${symbol} khỏi danh sách theo dõi cá nhân.`;
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : (language === 'en' ? 'Failed to remove symbol.' : 'Không thể xóa coin.');
      setWatchlistFeedback({ type: 'error', message });
      console.error("Error removing manual coin:", err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const addTrackingItem = async (payload: {
    symbol: string;
    source?: 'radar' | 'manual';
    source_signal_time?: string | null;
    source_probability?: number | null;
    source_risk_level?: string | null;
    source_price?: number | null;
    source_target_price?: number | null;
    source_invalidation_time?: string | null;
  }): Promise<boolean> => {
    const symbol = payload.symbol.trim().toUpperCase();
    if (!symbol) return false;
    setWatchlistPendingAction(`tracking:add:${symbol}`);
    setWatchlistFeedback(null);
    try {
      const res = await fetch('/api/tracking-watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, symbol }),
      });
      const data = await res.json().catch(() => ({})) as { item?: TrackingWatchlistItem; error?: string };
      if (!res.ok || !data.item) throw new Error(data.error || `Tracking HTTP ${res.status}`);
      setTrackingItems(prev => {
        const exists = prev.some(item => item.id === data.item?.id);
        return exists ? prev.map(item => item.id === data.item?.id ? data.item! : item) : [data.item!, ...prev];
      });
      const successMsg = language === 'en'
        ? `${symbol} added to position tracking.`
        : language === 'zh'
        ? `${symbol} 已加入仓位走势跟踪。`
        : language === 'ko'
        ? `${symbol}이(가) 포지션 추적 목록에 추가되었습니다.`
        : `${symbol} đã được thêm vào danh sách theo dõi tiến trình.`;
      setWatchlistFeedback({ type: 'success', message: successMsg });
      setActiveTab('WATCHLIST');
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : (language === 'en' ? 'Failed to add symbol to tracking.' : 'Không thể thêm coin vào danh sách theo dõi.');
      setWatchlistFeedback({ type: 'error', message });
      console.error('Tracking watchlist add error:', err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const handleTrackSignal = (sig: SignalItem) => addTrackingItem({
    symbol: sig.symbol,
    source: 'radar',
    source_signal_time: sig.signal_time,
    source_probability: sig.probability,
    source_risk_level: sig.risk_level,
    source_price: sig.signal_price,
    source_target_price: sig.target_price,
    source_invalidation_time: sig.invalidation_time,
  });

  const handleTrackCurrentCoin = (symbol: string) => {
    const signal = selectedSignal?.symbol === symbol ? selectedSignal : signals.find(item => item.symbol === symbol);
    return addTrackingItem(signal ? {
      symbol,
      source: 'radar',
      source_signal_time: signal.signal_time,
      source_probability: signal.probability,
      source_risk_level: signal.risk_level,
      source_price: signal.signal_price,
      source_target_price: signal.target_price,
      source_invalidation_time: signal.invalidation_time,
    } : { symbol, source: 'manual' });
  };

  const updateTrackingItem = async (id: string, patch: Record<string, unknown>): Promise<boolean> => {
    setTrackingUpdatingId(id);
    try {
      const res = await fetch(`/api/tracking-watchlist/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data = await res.json().catch(() => ({})) as { item?: TrackingWatchlistItem; error?: string };
      if (!res.ok || !data.item) throw new Error(data.error || `Tracking HTTP ${res.status}`);
      setTrackingItems(prev => prev.map(item => item.id === id ? data.item! : item));
      const successMsg = language === 'en'
        ? 'Tracking status updated.'
        : language === 'zh'
        ? '跟踪状态已更新。'
        : language === 'ko'
        ? '추적 상태가 업데이트되었습니다.'
        : 'Đã cập nhật trạng thái theo dõi.';
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : (language === 'en' ? 'Failed to update tracking.' : 'Không thể cập nhật theo dõi.');
      setWatchlistFeedback({ type: 'error', message });
      console.error('Tracking watchlist update error:', err);
      return false;
    } finally {
      setTrackingUpdatingId(null);
    }
  };

  const removeTrackingItem = async (id: string): Promise<boolean> => {
    setTrackingUpdatingId(id);
    try {
      const res = await fetch(`/api/tracking-watchlist/${encodeURIComponent(id)}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Tracking HTTP ${res.status}`);
      setTrackingItems(prev => prev.filter(item => item.id !== id));
      const successMsg = language === 'en'
        ? 'Tracking item removed.'
        : language === 'zh'
        ? '已移除跟踪项目。'
        : language === 'ko'
        ? '추적 항목이 삭제되었습니다.'
        : 'Đã xóa mục theo dõi.';
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : (language === 'en' ? 'Failed to remove tracking item.' : 'Không thể xóa mục theo dõi.');
      setWatchlistFeedback({ type: 'error', message });
      console.error('Tracking watchlist remove error:', err);
      return false;
    } finally {
      setTrackingUpdatingId(null);
    }
  };

  const handleChangeScanModes = async (modes: string[]): Promise<boolean> => {
    const normalizedModes = Array.from(new Set(modes.map((mode) => mode.trim().toLowerCase()).filter(Boolean)));
    if (normalizedModes.length === 0) return false;

    const previousModes = activeScanModes;
    setWatchlistPendingAction('modes');
    setWatchlistFeedback(null);
    setActiveScanModes(normalizedModes);
    try {
      const res = await fetch('/api/watchlist/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modes: normalizedModes })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || (language === 'en' ? `Failed to change scan mode (HTTP ${res.status})` : `Không thể đổi chế độ quét (HTTP ${res.status})`));
      const confirmedModes = Array.isArray(data.active_scan_modes) && data.active_scan_modes.length > 0
        ? data.active_scan_modes
        : normalizedModes;
      setActiveScanModes(confirmedModes);
      const mode = confirmedModes.join(' + ');
      const successMsg = language === 'en'
        ? `Selected mode ${String(data.active_scan_mode || mode).toUpperCase()}. Scanner will apply in next cycle.`
        : language === 'zh'
        ? `已切换至模式 ${String(data.active_scan_mode || mode).toUpperCase()}。扫描器将在下一轮生效。`
        : language === 'ko'
        ? `${String(data.active_scan_mode || mode).toUpperCase()} 모드가 선택되었습니다. 다음 주기부터 적용됩니다.`
        : `Đã chọn chế độ ${String(data.active_scan_mode || mode).toUpperCase()}. Bộ quét sẽ áp dụng ở chu kỳ kế tiếp.`;
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      setActiveScanModes(previousModes);
      const message = err instanceof Error ? err.message : (language === 'en' ? 'Failed to change scan mode.' : 'Không thể đổi chế độ quét.');
      setWatchlistFeedback({ type: 'error', message });
      console.error("Error updating scan mode:", err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const handleRunDeepAnalysis = async (symbol: string) => {
    setIsDeepAnalyzing(true);
    try {
      const res = await fetch(`/api/coin/${symbol}/deep-analysis`);
      const data = await res.json();
      setDeepAnalysis(data);
    } catch (err) {
      console.error(`Deep analysis error for ${symbol}:`, err);
    } finally {
      setIsDeepAnalyzing(false);
    }
  };

  const filteredSignals = signals.filter(sig => {
    const matchesSearch = sig.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          sig.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRisk = selectedRiskFilter === 'ALL' || sig.risk_level === selectedRiskFilter;
    const matchesThreshold = sig.probability >= threshold;
    const matchesTelegram = telegramFilter === 'ALL'
      || (telegramFilter === 'SENT' ? sig.telegram_sent === true : sig.telegram_sent !== true);

    let matchesTag = true;
    if (activeFilterTag === 'HOT_RISK') {
      matchesTag = sig.probability >= 0.75;
    } else if (activeFilterTag === 'EXPIRING') {
      matchesTag = sig.validity_hours_left <= 22.0;
    } else if (activeFilterTag === 'VOLUME_SPIKE') {
      matchesTag = sig.is_volume_spike || sig.taker_sell_ratio < 0.42;
    } else if (activeFilterTag === 'ACTIVE') {
      matchesTag = sig.validity_hours_left > 0;
    } else if (activeFilterTag === 'EXPIRED') {
      matchesTag = sig.validity_hours_left <= 0;
    }

    return matchesSearch && matchesRisk && matchesThreshold && matchesTelegram && matchesTag;
  }).sort((a, b) => {
    const aTime = parseSystemDate(a.event_time || a.signal_time)?.getTime() ?? Number.NaN;
    const bTime = parseSystemDate(b.event_time || b.signal_time)?.getTime() ?? Number.NaN;
    const safeTime = (value: number) => Number.isFinite(value) ? value : 0;

    if (signalSort === 'NEWEST') return safeTime(bTime) - safeTime(aTime);
    if (signalSort === 'EXPIRING_SOON') return a.validity_hours_left - b.validity_hours_left;
    if (signalSort === 'HIGHEST_RISK') {
      const riskRank: Record<SignalItem['risk_level'], number> = {
        CRITICAL: 4,
        HIGH: 3,
        MEDIUM: 2,
        SAFE: 1,
      };
      return riskRank[b.risk_level] - riskRank[a.risk_level] || b.probability - a.probability;
    }
    return b.probability - a.probability;
  });

  const activeScanMode = activeScanModes.join(' + ');

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col font-sans">
      
      {/* Loading Progress Indicator Overlay */}
      {loadingStep && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-2 flex items-center justify-between text-xs font-mono text-amber-300">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            <span className="font-semibold">{loadingStep}</span>
          </div>
          <span className="text-slate-400">
            {language === 'en' ? 'Loading real-time system telemetry...' : language === 'zh' ? '正在加载实时系统遥测数据...' : language === 'ko' ? '실시간 시스템 텔레메트리 로드 중...' : 'Đang tải dữ liệu thời gian thực từ hệ thống...'}
          </span>
        </div>
      )}

      {/* Header */}
      <Header
        status={status}
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        selectedRiskFilter={selectedRiskFilter}
        setSelectedRiskFilter={setSelectedRiskFilter}
        threshold={threshold}
        setThreshold={setThreshold}
        onRefresh={fetchData}
        isRefreshing={isRefreshing}
        onOpenGlossary={() => setIsGlossaryOpen(true)}
        onOpenWatchlistModal={() => setIsWatchlistModalOpen(true)}
        onOpenTracking={() => setActiveTab('WATCHLIST')}
        trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        activeScanMode={activeScanMode}
        autoTelegramEnabled={automationSettings.autoTelegramPush}
        isActionDrawerOpen={isActionDrawerOpen}
        onToggleActionDrawer={() => setIsActionDrawerOpen(v => !v)}
        onGoHome={() => {
          setActiveTab('DECISION');
          setSelectedSignal(null);
          setSelectedSignalId(null);
          setCoinDetail(null);
          setDeepAnalysis(null);
          window.location.hash = '';
        }}
        availableModels={availableModels}
        selectedModelKey={selectedModelKey}
        onSelectModel={setSelectedModelKey}
        scannerModelId={scannerModelId}
      />

      {/* Main 3-Column Layout: Feed (Left) - Decision Center (Center) - Smart Action (Right) */}
      <main className="flex-1 max-w-[1700px] w-full mx-auto p-2.5 sm:p-3.5 grid grid-cols-1 lg:grid-cols-12 gap-2.5 lg:gap-3.5 lg:overflow-hidden">
        
        {/* Left Column: Signal Feed Radar (3 cols) */}
        <div className={`lg:col-span-3 ${isRadarCollapsed ? 'h-auto' : 'h-[min(68vh,620px)]'} lg:h-[calc(100vh-120px)] lg:min-h-[600px]`}>
          <SignalFeed
            signals={filteredSignals}
            selectedSignalId={selectedSignalId}
            onSelectSignal={handleSelectSignal}
            onPushTelegram={handlePushTelegram}
            audioAlertEnabled={automationSettings.audioAlertEnabled}
            onDismissSignal={handleDismissSignal}
            onTrackSignal={handleTrackSignal}
            isSignalTracked={(sig) => trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === sig.symbol && item.source_signal_time === sig.signal_time)}
            activeFilterTag={activeFilterTag}
            setActiveFilterTag={setActiveFilterTag}
            signalSort={signalSort}
            setSignalSort={setSignalSort}
            telegramFilter={telegramFilter}
            setTelegramFilter={setTelegramFilter}
            isCollapsed={isRadarCollapsed}
            onToggleCollapse={() => setIsRadarCollapsed(value => !value)}
          />
        </div>

        {/* Center Column: Main Workspace & Charts (6 or 9 cols depending on drawer) */}
        <div className={`min-w-0 h-auto lg:h-[calc(100vh-120px)] lg:min-h-[600px] ${isActionDrawerOpen ? 'lg:col-span-6' : 'lg:col-span-9'}`}>
          <MainWorkspace
            signals={signals}
            selectedSignal={selectedSignal}
            coinDetail={coinDetail}
            candidates={candidates}
            candidateComparison={candidateComparison}
            isRefreshingCandidates={isRefreshingCandidates}
            onRefreshCandidates={handleRefreshCandidates}
            auditData={auditData}
            marketData={marketData}
            telemetryData={telemetryData}
            onSelectCandidate={handleSelectCandidate}
            onPushTelegram={handlePushTelegram}
            onTriggerManualScan={handleTriggerManualScan}
            isTriggeringScan={isTriggeringScan}
            scanTriggeredSuccess={scanTriggeredSuccess}
            deepAnalysis={deepAnalysis}
            isDeepAnalyzing={isDeepAnalyzing}
            onRunDeepAnalysis={handleRunDeepAnalysis}
            onDismissSignal={handleDismissSignal}
            onAddWatchlist={handleAddManualCoin}
            isSymbolInWatchlist={Boolean(coinDetail?.symbol && manualWatchlist.includes(coinDetail.symbol.toUpperCase()))}
            onAddTracking={handleTrackCurrentCoin}
            isSymbolTracked={Boolean(coinDetail?.symbol && trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === coinDetail.symbol.toUpperCase()))}
            isWatchlistUpdating={watchlistPendingAction !== null}
            trackingItems={trackingItems}
            isTrackingLoading={isTrackingLoading}
            trackingUpdatingId={trackingUpdatingId}
            onRefreshTracking={refreshTrackingWatchlist}
            onSelectTrackingCoin={handleSelectCandidate}
            onUpdateTracking={updateTrackingItem}
            onRemoveTracking={removeTrackingItem}
            activeTab={activeTab}
            setActiveTab={setActiveTab}
          />
        </div>

        {/* Right Column: Smart Automation & Action Drawer (3 cols) */}
        {isActionDrawerOpen && (
          <div className="lg:col-span-3 h-auto lg:h-[calc(100vh-120px)] lg:min-h-[600px]">
            <ActionDrawer
              selectedSignal={selectedSignal}
              onPushTelegram={handlePushTelegram}
              telegramSentSuccess={telegramSentSuccess}
              automationSettings={automationSettings}
              setAutomationSettings={setAutomationSettings}
              onSelectCoin={handleSelectCandidate}
              onCloseDrawer={() => setIsActionDrawerOpen(false)}
            />
          </div>
        )}

      </main>

      {/* Glossary Modal */}
      <GlossaryModal
        isOpen={isGlossaryOpen}
        onClose={() => setIsGlossaryOpen(false)}
      />

      {/* Watchlist Preset Modal */}
      <WatchlistModal
        isOpen={isWatchlistModalOpen}
        onClose={() => setIsWatchlistModalOpen(false)}
        activeScanMode={activeScanMode}
        activeScanModes={activeScanModes}
        setActiveScanModes={handleChangeScanModes}
        manualWatchlist={manualWatchlist}
        onAddManualCoin={handleAddManualCoin}
        onRemoveManualCoin={handleRemoveManualCoin}
        presets={watchlistPresets}
        onSelectCoin={handleSelectCandidate}
        pendingAction={watchlistPendingAction}
        feedback={watchlistFeedback}
      />

      {watchlistFeedback && !isWatchlistModalOpen && (
        <div
          role="status"
          className={`fixed bottom-4 left-3 right-3 sm:left-auto sm:right-4 sm:max-w-sm z-[60] rounded-xl border px-4 py-3 text-xs shadow-2xl backdrop-blur-md ${
            watchlistFeedback.type === 'success'
              ? 'border-emerald-500/40 bg-emerald-950/95 text-emerald-200'
              : 'border-red-500/40 bg-red-950/95 text-red-200'
          }`}
        >
          {watchlistFeedback.message}
        </div>
      )}

    </div>
  );
}

export default App;
