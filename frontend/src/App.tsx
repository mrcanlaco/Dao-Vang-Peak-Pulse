import { useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { MainWorkspace } from './components/MainWorkspace';
import { ActionDrawer } from './components/ActionDrawer';
import { GlossaryModal } from './components/GlossaryModal';
import { WatchlistModal } from './components/WatchlistModal';
import { ModelComparisonModal } from './components/ModelComparisonModal';
import { CoinSelectorModal } from './components/CoinSelectorModal';
import { MobileBottomNav, type MobileTabType } from './components/v2/MobileBottomNav';
import { StickyActionBar } from './components/v2/StickyActionBar';
import { OrderExecutionModal } from './components/v2/OrderExecutionModal';
import type { WorkspaceTab } from './components/WorkspaceTabBar';
import type {
  SignalItem, CoinDetail, CandidateCoin, CandidateFilterComparison, ModelAudit, MarketOverviewData, SystemStatus, FilterTag, SignalSort, TelegramFilter, AutomationSettings, ScannerTelemetry, WatchlistPreset, DeepAnalysis, ModelChoice, ModelsData, TrackingWatchlistItem
} from './types';
import { parseSystemDate } from './utils/time';
import { useTranslation, type Language } from './i18n/LanguageContext';

export function App() {
  const { language, t } = useTranslation();

  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [signals, setSignals] = useState<SignalItem[]>([]);
  const [candidates, setCandidates] = useState<CandidateCoin[]>([]);
  const [candidateComparison, setCandidateComparison] = useState<CandidateFilterComparison | null>(null);
  const [auditData, setAuditData] = useState<ModelAudit | null>(null);
  const [marketData, setMarketData] = useState<MarketOverviewData | null>(null);
  const [telemetryData, setTelemetryData] = useState<ScannerTelemetry | null>(null);
  const [watchlistPresets, setWatchlistPresets] = useState<WatchlistPreset[]>([]);
  const [availableModels, setAvailableModels] = useState<ModelChoice[]>([]);
  const [selectedModelKey, setSelectedModelKey] = useState<string>('two_tier_climax');
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

  const [activeTab, setActiveTab] = useState<WorkspaceTab>('DECISION');
  const [isActionDrawerOpen, setIsActionDrawerOpen] = useState(false);

  // GUI Version: 'v1' (Classic 3-column) | 'v2' (Pro Mobile / Binance-OKX Style)
  const [guiVersion, setGuiVersion] = useState<'v1' | 'v2'>(() => {
    try {
      const saved = localStorage.getItem('dao_vang_gui_version');
      if (saved === 'v1' || saved === 'v2') return saved;
      if (typeof window !== 'undefined' && window.location.hash.includes('v1')) return 'v1';
      return 'v2';
    } catch {
      return 'v2';
    }
  });

  const handleSelectGuiVersion = (version: 'v1' | 'v2') => {
    setGuiVersion(version);
    try {
      localStorage.setItem('dao_vang_gui_version', version);
    } catch {
      // Ignore localStorage errors
    }
  };

  const [mobileTab, setMobileTab] = useState<MobileTabType>('RADAR');
  const [isOrderModalOpen, setIsOrderModalOpen] = useState(false);
  const [isModelComparisonOpen, setIsModelComparisonOpen] = useState(false);
  const [isCoinSelectorOpen, setIsCoinSelectorOpen] = useState(false);

  const getStepText = (stepKey: string, _lang: Language) => {
    return t(`loading_${stepKey}`);
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
        handleRunDeepAnalysis(sigRes[0].symbol);
      } else if (candRes && candRes.length > 0 && !selectedSignalId && !hashSymbol) {
        fetchCoinDetail(candRes[0].symbol);
        handleRunDeepAnalysis(candRes[0].symbol);
      }
    } catch (err) {
      console.error("Error loading API data:", err);
    } finally {
      setIsRefreshing(false);
      setLoadingStep(null);
    }
  };

  const coinDetailCache = useRef<Map<string, CoinDetail>>(new Map());
  const deepAnalysisCache = useRef<Map<string, DeepAnalysis>>(new Map());

  const fetchCoinDetail = async (symbol: string) => {
    if (coinDetailCache.current.has(symbol)) {
      setCoinDetail(coinDetailCache.current.get(symbol)!);
    }
    try {
      const res = await fetch(`/api/coin/${symbol}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data && !data.error && data.metrics) {
        coinDetailCache.current.set(symbol, data);
        setCoinDetail(data);
      }
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
    if (guiVersion === 'v2') {
      setMobileTab('ANALYSIS');
    }
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
    if (guiVersion === 'v2') {
      setMobileTab('ANALYSIS');
    }
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
      const successMsg = t('toast_telegram_sent').replace('{symbol}', sig.symbol);
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
      const successMsg = t('toast_scan_triggered').replace('{count}', String(data.symbols_scanned ?? 48));
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
      if (!res.ok) throw new Error(data.error || t('error_failed_to_add'));

      setManualWatchlist(data.manual_watchlist || [...manualWatchlist, nextSymbol]);
      const successMsg = t('toast_watchlist_added').replace('{symbol}', nextSymbol);
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_add');
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
      if (!res.ok) throw new Error(data.error || t('error_failed_to_remove'));

      setManualWatchlist(data.manual_watchlist || manualWatchlist.filter((item) => item !== symbol));
      const successMsg = t('toast_watchlist_removed').replace('{symbol}', symbol);
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_remove');
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
      const successMsg = t('toast_tracking_added').replace('{symbol}', symbol);
      setWatchlistFeedback({ type: 'success', message: successMsg });
      setActiveTab('WATCHLIST');
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_update_tracking');
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

  const handleUntrackSignal = async (sig: SignalItem) => {
    const item = trackingItems.find(
      t => t.status !== 'CLOSED' && t.symbol === sig.symbol && (t.source_signal_time === sig.signal_time || !t.source_signal_time)
    ) || trackingItems.find(t => t.status !== 'CLOSED' && t.symbol === sig.symbol);
    if (item) {
      return await removeTrackingItem(item.id);
    }
    return false;
  };

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

  const handleUntrackCurrentCoin = async (symbol: string) => {
    const cleanSymbol = symbol.trim().toUpperCase();
    const items = trackingItems.filter(
      item => item.status !== 'CLOSED' && item.symbol === cleanSymbol
    );
    if (items.length === 0) return false;
    let allOk = true;
    for (const it of items) {
      const ok = await removeTrackingItem(it.id);
      if (!ok) allOk = false;
    }
    return allOk;
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
      const successMsg = t('toast_tracking_updated');
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_update_tracking');
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
      const successMsg = t('toast_tracking_removed');
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : t('error_failed_to_remove_tracking');
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
      if (!res.ok) throw new Error(data.error || t('error_failed_to_change_scan_mode'));
      const confirmedModes = Array.isArray(data.active_scan_modes) && data.active_scan_modes.length > 0
        ? data.active_scan_modes
        : normalizedModes;
      setActiveScanModes(confirmedModes);
      const mode = confirmedModes.join(' + ');
      const successMsg = t('toast_scan_mode_changed').replace('{mode}', String(data.active_scan_mode || mode).toUpperCase());
      setWatchlistFeedback({ type: 'success', message: successMsg });
      return true;
    } catch (err) {
      setActiveScanModes(previousModes);
      const message = err instanceof Error ? err.message : t('error_failed_to_change_scan_mode');
      setWatchlistFeedback({ type: 'error', message });
      console.error("Error updating scan mode:", err);
      return false;
    } finally {
      setWatchlistPendingAction(null);
    }
  };

  const handleRunDeepAnalysis = async (symbol: string) => {
    if (deepAnalysisCache.current.has(symbol)) {
      setDeepAnalysis(deepAnalysisCache.current.get(symbol)!);
    }
    setIsDeepAnalyzing(true);
    try {
      const res = await fetch(`/api/coin/${symbol}/deep-analysis`);
      const data = await res.json();
      deepAnalysisCache.current.set(symbol, data);
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
            {t('loading_telemetry_realtime')}
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
        onOpenTracking={() => {
          setActiveTab('WATCHLIST');
          if (guiVersion === 'v2') setMobileTab('TRACKING');
        }}
        onOpenCoinSelector={() => setIsCoinSelectorOpen(true)}
        onOpenRadar={() => {
          setActiveTab('RADAR');
          if (guiVersion === 'v2') setMobileTab('RADAR');
        }}
        trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        activeScanMode={activeScanMode}
        autoTelegramEnabled={automationSettings.autoTelegramPush}
        isActionDrawerOpen={isActionDrawerOpen}
        onToggleActionDrawer={() => setIsActionDrawerOpen(v => !v)}
        onGoHome={() => {
          setActiveTab('DECISION');
          if (guiVersion === 'v2') setMobileTab('ANALYSIS');
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
        guiVersion={guiVersion}
        onSelectGuiVersion={handleSelectGuiVersion}
        onOpenModelComparison={() => setIsModelComparisonOpen(true)}
        onOpenUpdates={() => setActiveTab('UPDATES')}
        onOpenSettings={() => setActiveTab('SETTINGS')}
        mobileTab={mobileTab}
        onBackToRadar={() => {
          setMobileTab('RADAR');
          setActiveTab('RADAR');
        }}
        activeCoinSymbol={selectedSignal?.symbol || coinDetail?.symbol || (candidates.length > 0 ? candidates[0].symbol : null)}
        activeCoinPrice={coinDetail?.current_price || selectedSignal?.signal_price || (candidates.length > 0 ? candidates[0].price : null)}
        activeCoinProbability={selectedSignal?.probability || coinDetail?.probability || null}
        activeCoinRisk={selectedSignal?.risk_level || coinDetail?.risk_level || null}
        signalCount={signals.length}
      />

      {/* Main Workspace Layout - Full 12 columns by default (or 9 cols if Action Drawer open) */}
      <main className={`flex-1 max-w-[1750px] w-full mx-auto p-2.5 sm:p-3.5 grid grid-cols-1 lg:grid-cols-12 gap-2.5 lg:gap-3.5 lg:overflow-hidden ${
        guiVersion === 'v2' ? 'pb-24 sm:pb-3.5' : ''
      }`}>
        {/* Main Workspace & Charts */}
        <div className={`min-w-0 h-auto lg:h-[calc(100vh-120px)] lg:min-h-[600px] block ${
          isActionDrawerOpen ? 'lg:col-span-9' : 'lg:col-span-12'
        }`}>
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
            onRemoveTrackingSymbol={handleUntrackCurrentCoin}
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
            onOpenOrderModal={() => setIsOrderModalOpen(true)}
            onOpenCoinSelector={() => setIsCoinSelectorOpen(true)}
            onSelectSignal={handleSelectSignal}
            onTrackSignal={handleTrackSignal}
            onUntrackSignal={handleUntrackSignal}
            isSignalTracked={(sig) => trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === sig.symbol && (item.source_signal_time === sig.signal_time || !item.source_signal_time))}
            audioAlertEnabled={automationSettings.audioAlertEnabled}
            activeFilterTag={activeFilterTag}
            setActiveFilterTag={setActiveFilterTag}
            signalSort={signalSort}
            setSignalSort={setSignalSort}
            telegramFilter={telegramFilter}
            setTelegramFilter={setTelegramFilter}
            filteredSignals={filteredSignals}
            guiVersion={guiVersion}
            onSelectGuiVersion={handleSelectGuiVersion}
            threshold={threshold}
            setThreshold={setThreshold}
            activeScanModes={activeScanModes}
            onOpenWatchlistModal={() => setIsWatchlistModalOpen(true)}
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

      {/* GUI V2 Mobile Bottom Navigation Bar */}
      {guiVersion === 'v2' && (
        <MobileBottomNav
          activeTab={mobileTab}
          onSelectTab={(tab) => {
            setMobileTab(tab);
            if (tab === 'RADAR') {
              setActiveTab('RADAR');
            } else if (tab === 'ANALYSIS') {
              setActiveTab('DECISION');
            } else if (tab === 'ORDER') {
              setIsOrderModalOpen(true);
            } else if (tab === 'TRACKING') {
              setActiveTab('WATCHLIST');
            } else if (tab === 'TOOLS') {
              if (activeTab === 'DECISION' || activeTab === 'WATCHLIST' || activeTab === 'RADAR') {
                setActiveTab('RANKING');
              }
            }
          }}
          signalCount={filteredSignals.length}
          selectedSymbol={coinDetail?.symbol || selectedSignal?.symbol || null}
          trackingCount={trackingItems.filter(item => item.status !== 'CLOSED').length}
        />
      )}

      {/* GUI V2 Sticky Action Bar (Mobile when coin selected) */}
      {guiVersion === 'v2' && (coinDetail || selectedSignal) && mobileTab === 'ANALYSIS' && (
        <StickyActionBar
          symbol={coinDetail?.symbol || selectedSignal?.symbol || ''}
          currentPrice={coinDetail?.current_price || selectedSignal?.signal_price || 0}
          probability={deepAnalysis?.calibrated_probability ?? selectedSignal?.probability ?? coinDetail?.probability}
          riskLevel={selectedSignal?.risk_level || coinDetail?.risk_level}
          onOpenOrderModal={() => setIsOrderModalOpen(true)}
          onTrackPosition={handleTrackCurrentCoin}
          onUntrackPosition={handleUntrackCurrentCoin}
          isSymbolTracked={Boolean((coinDetail?.symbol || selectedSignal?.symbol) && trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === (coinDetail?.symbol || selectedSignal?.symbol)?.toUpperCase()))}
          isTrackingLoading={isTrackingLoading}
          onPushTelegram={() => selectedSignal && handlePushTelegram(selectedSignal)}
        />
      )}

      {/* GUI V2 Order Execution & Risk Management Modal */}
      {(coinDetail || selectedSignal) && (
        <OrderExecutionModal
          isOpen={isOrderModalOpen}
          onClose={() => setIsOrderModalOpen(false)}
          symbol={coinDetail?.symbol || selectedSignal?.symbol || ''}
          currentPrice={coinDetail?.current_price || selectedSignal?.signal_price || 0}
          signalPrice={selectedSignal?.signal_price}
          targetPrice={coinDetail?.target_price || selectedSignal?.target_price}
          peakPrice={deepAnalysis?.pump_analysis?.peak_price}
          probability={deepAnalysis?.calibrated_probability ?? selectedSignal?.probability ?? coinDetail?.probability}
          riskLevel={selectedSignal?.risk_level || coinDetail?.risk_level}
          onTrackPosition={handleTrackCurrentCoin}
          onUntrackPosition={handleUntrackCurrentCoin}
          isSymbolTracked={Boolean((coinDetail?.symbol || selectedSignal?.symbol) && trackingItems.some(item => item.status !== 'CLOSED' && item.symbol === (coinDetail?.symbol || selectedSignal?.symbol)?.toUpperCase()))}
          isTrackingLoading={isTrackingLoading}
        />
      )}

      {/* Binance Futures Style Coin Selector Popover/Modal */}
      <CoinSelectorModal
        isOpen={isCoinSelectorOpen}
        onClose={() => setIsCoinSelectorOpen(false)}
        currentSymbol={coinDetail?.symbol || selectedSignal?.symbol || (candidates.length > 0 ? candidates[0].symbol : '')}
        onSelectCoin={handleSelectCandidate}
        signals={signals}
        candidates={candidates}
        marketData={marketData}
        manualWatchlist={manualWatchlist}
        trackingItems={trackingItems}
        onToggleWatchlist={async (sym) => {
          if (manualWatchlist.includes(sym)) {
            return await handleRemoveManualCoin(sym);
          } else {
            return await handleAddManualCoin(sym);
          }
        }}
      />

      {/* Glossary Modal */}
      <GlossaryModal
        isOpen={isGlossaryOpen}
        onClose={() => setIsGlossaryOpen(false)}
      />

      {/* A/B Engine Comparison Benchmark Modal */}
      <ModelComparisonModal
        isOpen={isModelComparisonOpen}
        onClose={() => setIsModelComparisonOpen(false)}
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
