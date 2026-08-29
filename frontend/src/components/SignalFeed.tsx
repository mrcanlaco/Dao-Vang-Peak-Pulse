import React, { useState, useEffect, useMemo } from 'react';
import type {
  FilterTag, SignalItem, RiskLevel, SignalSort, TelegramFilter, MarketAnomaly,
  RadarAdvancedFilterState
} from '../types';
import { getSignalTwoTierState, isSignalFired, isSignalArmed, DEFAULT_RADAR_ADVANCED_FILTERS } from '../types';
import { parseSystemDate } from '../utils/time';
import { getCoinSector, getCoinMarketCapInfo, getSectorBadgeConfig, getMarketCapBadgeConfig } from '../utils/sectors';
import { RadarFilterDrawer } from './RadarFilterDrawer';
import {
  Clock, TrendingDown, Send, Copy, Check, Volume2, AlertOctagon, X,
  ChevronDown, ChevronUp, Flame, Zap, Eye, EyeOff, LayoutGrid, List,
  Columns2, Search, Target, BarChart2, ShieldAlert, Sparkles, Compass,
  Filter
} from 'lucide-react';
import { CoinLink } from './CoinLink';
import { useTranslation } from '../i18n/LanguageContext';
import { getRiskLabel, formatDuration } from '../i18n/translations';

export type RadarViewMode = 'GRID' | 'TABLE' | 'SPLIT';

interface SignalFeedProps {
  signals: SignalItem[];
  allSignals?: SignalItem[];
  selectedSignalId: string | null;
  onSelectSignal: (signal: SignalItem) => void;
  onGoToDecision?: (signal: SignalItem) => void;
  onOpenOrderModal?: (signal?: SignalItem) => void;
  onPushTelegram: (signal: SignalItem) => void;
  onTrackSignal?: (signal: SignalItem) => void;
  onUntrackSignal?: (signal: SignalItem) => void;
  isSignalTracked?: (signal: SignalItem) => boolean;
  audioAlertEnabled: boolean;
  onDismissSignal?: (signal: SignalItem) => void;
  activeFilterTag: FilterTag;
  setActiveFilterTag: (tag: FilterTag) => void;
  signalSort: SignalSort;
  setSignalSort: (sort: SignalSort) => void;
  telegramFilter: TelegramFilter;
  setTelegramFilter: (filter: TelegramFilter) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const SignalFeed: React.FC<SignalFeedProps> = ({
  signals,
  allSignals,
  selectedSignalId,
  onSelectSignal,
  onGoToDecision,
  onOpenOrderModal,
  onPushTelegram,
  onTrackSignal,
  onUntrackSignal,
  isSignalTracked,
  audioAlertEnabled,
  onDismissSignal,
  activeFilterTag,
  setActiveFilterTag,
  signalSort,
  setSignalSort,
  telegramFilter: _telegramFilter,
  setTelegramFilter: _setTelegramFilter,
  isCollapsed = false,
  onToggleCollapse
}) => {
  const { language, t } = useTranslation();
  const [, setTicks] = useState(0);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [localSearch, setLocalSearch] = useState('');

  // Persistent view mode: GRID | TABLE | SPLIT
  const [viewMode, setViewMode] = useState<RadarViewMode>(() => {
    try {
      const saved = localStorage.getItem('dao_vang_radar_view_mode');
      if (saved === 'GRID' || saved === 'TABLE' || saved === 'SPLIT') return saved;
      return 'GRID';
    } catch {
      return 'GRID';
    }
  });

  const handleSelectViewMode = (mode: RadarViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem('dao_vang_radar_view_mode', mode);
    } catch {
      // Ignore localStorage error
    }
  };

  // Real-time ticking countdown timer effect
  useEffect(() => {
    const timer = setInterval(() => {
      setTicks(t => t + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const [isFilterDrawerOpen, setIsFilterDrawerOpen] = useState(false);
  const [advancedFilters, setAdvancedFilters] = useState<RadarAdvancedFilterState>(() => {
    try {
      const saved = localStorage.getItem('dao_vang_radar_advanced_filters');
      if (saved) return JSON.parse(saved);
    } catch {
      // Ignore
    }
    return DEFAULT_RADAR_ADVANCED_FILTERS;
  });

  const handleApplyAdvancedFilters = (newFilters: RadarAdvancedFilterState) => {
    setAdvancedFilters(newFilters);
    try {
      localStorage.setItem('dao_vang_radar_advanced_filters', JSON.stringify(newFilters));
    } catch {
      // Ignore
    }
  };

  const handleResetAdvancedFilters = () => {
    setAdvancedFilters(DEFAULT_RADAR_ADVANCED_FILTERS);
    try {
      localStorage.removeItem('dao_vang_radar_advanced_filters');
    } catch {
      // Ignore
    }
  };

  // Count active non-default filters
  const activeAdvancedFilterCount = useMemo(() => {
    let cnt = 0;
    if (advancedFilters.preset !== 'ALL') cnt++;
    if (advancedFilters.marketCapTier !== 'ALL') cnt++;
    if (!advancedFilters.sectors.includes('ALL')) cnt++;
    if (advancedFilters.fundingRange !== 'ALL') cnt++;
    if (advancedFilters.minOiChangePct !== null && advancedFilters.minOiChangePct !== undefined) cnt++;
    if (advancedFilters.minTakerSellRatio !== null && advancedFilters.minTakerSellRatio !== undefined) cnt++;
    if (advancedFilters.minRrRatio !== null && advancedFilters.minRrRatio !== undefined) cnt++;
    if (advancedFilters.minDrawdownPct !== null && advancedFilters.minDrawdownPct !== undefined) cnt++;
    if (advancedFilters.maxStopLossPct !== null && advancedFilters.maxStopLossPct !== undefined) cnt++;
    if (advancedFilters.twoTierState !== 'ALL') cnt++;
    if (advancedFilters.anomalyCategories.length > 0) cnt++;
    return cnt;
  }, [advancedFilters]);

  // Advanced Signal Matcher
  const testSignalAdvancedMatch = (sig: SignalItem, f: RadarAdvancedFilterState): boolean => {
    // 1. Strategic Preset
    if (f.preset === 'CLIMAX_DUMP') {
      if (getSignalTwoTierState(sig) !== 'FIRED') return false;
    } else if (f.preset === 'ARMED_SETUP') {
      if (getSignalTwoTierState(sig) !== 'ARMED') return false;
    } else if (f.preset === 'FUNDING_TRAP') {
      const frStr = sig.funding_rate || '';
      const frVal = parseFloat(frStr.replace('%', ''));
      const hasFundingAnomaly = sig.anomalies?.some(a => a.category === 'funding' || a.code === 'funding_trap');
      if (!hasFundingAnomaly && (isNaN(frVal) || frVal < 0.02)) return false;
    } else if (f.preset === 'OI_SQUEEZE') {
      const oiStr = sig.oi_change_24h || '';
      const oiVal = parseFloat(oiStr.replace('%', '').replace('+', ''));
      const hasOiAnomaly = sig.anomalies?.some(a => a.category === 'open_interest' || a.category === 'volume');
      if (!hasOiAnomaly && (isNaN(oiVal) || oiVal < 5.0)) return false;
    } else if (f.preset === 'HIGH_RR') {
      const rr = sig.trade_setup?.rr_ratio ?? (Math.abs(sig.target_drawdown || 8) / (sig.trade_setup?.stop_loss_pct || 3.8));
      if (rr < 2.3) return false;
    } else if (f.preset === 'AI_MEME') {
      const sector = getCoinSector(sig.symbol);
      if (sector !== 'AI' && sector !== 'MEME') return false;
    } else if (f.preset === 'LOWCAP_GEMS') {
      const capInfo = getCoinMarketCapInfo(sig.symbol, sig);
      if (capInfo.market_cap_tier !== 'SMALL') return false;
    }

    // 2. Two-tier state
    if (f.twoTierState === 'FIRED' && getSignalTwoTierState(sig) !== 'FIRED') return false;
    if (f.twoTierState === 'ARMED' && getSignalTwoTierState(sig) !== 'ARMED') return false;

    // 3. Sector
    if (!f.sectors.includes('ALL')) {
      const sec = getCoinSector(sig.symbol);
      if (!f.sectors.includes(sec)) return false;
    }

    // 4. Market Cap Tier
    if (f.marketCapTier !== 'ALL') {
      const cap = getCoinMarketCapInfo(sig.symbol, sig);
      if (cap.market_cap_tier !== f.marketCapTier) return false;
    }

    // 5. Funding Range
    if (f.fundingRange !== 'ALL') {
      const frStr = sig.funding_rate || '';
      const frVal = parseFloat(frStr.replace('%', ''));
      if (f.fundingRange === 'POSITIVE_HIGH' && (isNaN(frVal) || frVal < 0.025)) return false;
      if (f.fundingRange === 'NEGATIVE_DEEP' && (isNaN(frVal) || frVal > -0.01)) return false;
      if (f.fundingRange === 'NEUTRAL' && (!isNaN(frVal) && Math.abs(frVal) > 0.015)) return false;
    }

    // 6. Min OI Change %
    if (f.minOiChangePct !== null && f.minOiChangePct !== undefined) {
      const oiStr = sig.oi_change_24h || '';
      const oiVal = parseFloat(oiStr.replace('%', '').replace('+', ''));
      if (isNaN(oiVal) || oiVal < f.minOiChangePct) return false;
    }

    // 7. Min Taker Sell Ratio
    if (f.minTakerSellRatio !== null && f.minTakerSellRatio !== undefined) {
      const ts = sig.taker_sell_ratio ?? 0.5;
      if (ts < f.minTakerSellRatio) return false;
    }

    // 8. Min R:R Ratio
    if (f.minRrRatio !== null && f.minRrRatio !== undefined) {
      const rr = sig.trade_setup?.rr_ratio ?? (Math.abs(sig.target_drawdown || 8) / (sig.trade_setup?.stop_loss_pct || 3.8));
      if (rr < f.minRrRatio) return false;
    }

    // 9. Min Target Drawdown
    if (f.minDrawdownPct !== null && f.minDrawdownPct !== undefined) {
      const dd = Math.abs(sig.target_drawdown || 0);
      if (dd < f.minDrawdownPct) return false;
    }

    // 10. Max Stop Loss %
    if (f.maxStopLossPct !== null && f.maxStopLossPct !== undefined) {
      const sl = sig.trade_setup?.stop_loss_pct ?? 3.8;
      if (sl > f.maxStopLossPct) return false;
    }

    // 11. Anomaly Categories
    if (f.anomalyCategories.length > 0) {
      const sigCats = sig.anomaly_categories || (sig.anomalies ? sig.anomalies.map(a => a.category) : []);
      const matchCat = f.anomalyCategories.some(c => sigCats.includes(c));
      if (!matchCat) return false;
    }

    return true;
  };

  // Filter signals by Advanced Filters & Instant Search
  const filteredBySearchSignals = useMemo(() => {
    let list = signals.filter(sig => testSignalAdvancedMatch(sig, advancedFilters));
    if (localSearch.trim()) {
      const q = localSearch.trim().toLowerCase();
      list = list.filter(
        s => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
      );
    }
    return list;
  }, [signals, advancedFilters, localSearch]);

  // Group signals by symbol to avoid duplicates, keep track of count
  const groupedSignals = useMemo(() => {
    const map = new Map<string, { signal: SignalItem; count: number }>();
    for (const sig of filteredBySearchSignals) {
      const symKey = (sig.symbol || '').trim();
      if (map.has(symKey)) {
        map.get(symKey)!.count++;
      } else {
        map.set(symKey, { signal: sig, count: 1 });
      }
    }
    return Array.from(map.values());
  }, [filteredBySearchSignals]);

  // Currently active/inspected signal (fallback to first if none selected)
  const activeInspectedSignal = useMemo(() => {
    if (selectedSignalId) {
      const found = groupedSignals.find(s => s.signal.id === selectedSignalId);
      if (found) return found.signal;
    }
    return groupedSignals.length > 0 ? groupedSignals[0].signal : null;
  }, [groupedSignals, selectedSignalId]);

  // Base signal pool for overall aggregate KPIs (unaffected by activeFilterTag)
  const baseSignalPool = allSignals && allSignals.length > 0 ? allSignals : signals;

  // KPI Metrics Calculation across original base signals
  const kpiStats = useMemo(() => {
    const total = baseSignalPool.length;
    const fired = baseSignalPool.filter(isSignalFired).length;
    const armed = baseSignalPool.filter(isSignalArmed).length;
    const hotRisk = baseSignalPool.filter(s => s.probability >= 0.75).length;
    const expiring = baseSignalPool.filter(s => s.validity_hours_left > 0 && s.validity_hours_left <= 2.0).length;
    const avgProb = total > 0 ? (baseSignalPool.reduce((acc, s) => acc + s.probability, 0) / total * 100).toFixed(1) : '0.0';

    return { total, fired, armed, hotRisk, expiring, avgProb };
  }, [baseSignalPool]);

  // Keyboard navigation shortcuts: ↑ / ↓ to switch signal, Space to push Telegram
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement).tagName)) return;
      if (groupedSignals.length === 0) return;

      const currentIndex = groupedSignals.findIndex(s => s.signal.id === selectedSignalId);
      const activeIndex = currentIndex >= 0 ? currentIndex : 0;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const nextIndex = (activeIndex + 1) % groupedSignals.length;
        onSelectSignal(groupedSignals[nextIndex].signal);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prevIndex = (activeIndex - 1 + groupedSignals.length) % groupedSignals.length;
        onSelectSignal(groupedSignals[prevIndex].signal);
      } else if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        if (currentIndex >= 0) {
          onPushTelegram(groupedSignals[currentIndex].signal);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [groupedSignals, selectedSignalId, onSelectSignal, onPushTelegram]);

  // Audio alert tone synthesizer using Web Audio API
  const playAlertSound = () => {
    if (!audioAlertEnabled) return;
    try {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime); // A5 note
      osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.3);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
    } catch {
      // Audio context silenced or blocked
    }
  };

  const getRiskBadge = (level: RiskLevel) => {
    switch (level) {
      case 'CRITICAL':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-950/90 border border-red-600/90 text-red-400 animate-pulse inline-flex items-center gap-1">
            🔴 {getRiskLabel('CRITICAL', language)}
          </span>
        );
      case 'HIGH':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 border border-amber-500/80 text-amber-400 inline-flex items-center gap-1">
            🟠 {getRiskLabel('HIGH', language)}
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-yellow-950/80 border border-yellow-500/60 text-yellow-300 inline-flex items-center gap-1">
            🟡 {getRiskLabel('MEDIUM', language)}
          </span>
        );
      case 'SAFE':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 border border-emerald-500/60 text-emerald-400 inline-flex items-center gap-1">
            🟢 {getRiskLabel('SAFE', language)}
          </span>
        );
    }
  };

  const getAnomalyLabel = (anomaly: MarketAnomaly) => (
    language === 'vi' ? (anomaly.title_vi || anomaly.title) : anomaly.title
  );

  const getAnomalyClass = (anomaly: MarketAnomaly) => (
    anomaly.severity === 'extreme'
      ? 'border-red-700/80 bg-red-950/70 text-red-300'
      : anomaly.severity === 'high'
      ? 'border-amber-700/80 bg-amber-950/60 text-amber-300'
      : 'border-violet-700/70 bg-violet-950/50 text-violet-300'
  );

  const parseSignalDate = (value?: string | null) => {
    return parseSystemDate(value);
  };

  const getSignalTiming = (sig: SignalItem) => {
    const now = Date.now();
    const signalDate = parseSignalDate(sig.signal_time);
    const eventDate = parseSignalDate(sig.event_time || sig.signal_time);
    const invalidationDate = parseSignalDate(sig.invalidation_time);
    const signalElapsedSeconds = signalDate
      ? Math.max(0, (now - signalDate.getTime()) / 1000)
      : 0;
    const reportedElapsedSeconds = eventDate
      ? Math.max(0, (now - eventDate.getTime()) / 1000)
      : signalElapsedSeconds;
    const totalSeconds = Math.max(1, (sig.validity_hours_total ?? 24) * 3600);
    const remainingSeconds = invalidationDate
      ? Math.max(0, (invalidationDate.getTime() - now) / 1000)
      : Math.max(0, totalSeconds - signalElapsedSeconds);
    const progress = Math.min(100, Math.max(0, (signalElapsedSeconds / totalSeconds) * 100));
    return {
      elapsedLabel: formatDuration(reportedElapsedSeconds, language),
      remainingLabel: formatDuration(remainingSeconds, language),
      remainingSeconds,
      progress,
      isExpired: remainingSeconds <= 0,
    };
  };

  // Copy formatted alert text to clipboard
  const handleCopyAlertText = (sig: SignalItem) => {
    let text = '';
    if (language === 'en') {
      text = `🚨 [DAO VANG AI ALERT]\n🪙 Coin: ${sig.symbol}\n📊 Probability: ${(sig.probability * 100).toFixed(1)}% (${sig.risk_level})\n🎯 Target Drawdown: ${sig.target_drawdown}% ($${sig.target_price})\n📈 OI Delta 24h: ${sig.oi_change_24h}\n💸 Funding Rate: ${sig.funding_rate}\n⏱️ Validity Left: ${sig.validity_hours_left} hours\n⚡ Key Drivers: ${sig.drivers.map(d => d.name).join(', ')}`;
    } else if (language === 'zh') {
      text = `🚨 [DAO VANG (刀锋) 见顶警报]\n🪙 交易对: ${sig.symbol}\n📊 派发概率: ${(sig.probability * 100).toFixed(1)}% (${sig.risk_level})\n🎯 回撤目标: ${sig.target_drawdown}% ($${sig.target_price})\n📈 24h OI变动: ${sig.oi_change_24h}\n💸 资金费率: ${sig.funding_rate}\n⏱️ 剩余有效时间: ${sig.validity_hours_left} 小时\n⚡ 核心预警因子: ${sig.drivers.map(d => d.name).join(', ')}`;
    } else if (language === 'ko') {
      text = `🚨 [DAO VANG (다오방) 피크 경보]\n🪙 페어: ${sig.symbol}\n📊 분산 확률: ${(sig.probability * 100).toFixed(1)}% (${sig.risk_level})\n🎯 하락 목표: ${sig.target_drawdown}% ($${sig.target_price})\n📈 24h OI 변화: ${sig.oi_change_24h}\n💸 펀딩비: ${sig.funding_rate}\n⏱️ 유효 잔여시간: ${sig.validity_hours_left} 시간\n⚡ 핵심 유발 요인: ${sig.drivers.map(d => d.name).join(', ')}`;
    } else {
      text = `🚨 [CẢNH BÁO ĐẢO VÀNG AI]\n🪙 Coin: ${sig.symbol}\n📊 Điểm rủi ro: ${(sig.probability * 100).toFixed(1)}% (${sig.risk_level})\n🎯 Mục tiêu giảm: ${sig.target_drawdown}% ($${sig.target_price})\n📈 Thay đổi OI 24 giờ: ${sig.oi_change_24h}\n💸 Tỷ lệ funding: ${sig.funding_rate}\n⏱️ Hiệu lực còn: ${sig.validity_hours_left} giờ\n⚡ Lý do AI: ${sig.drivers.map(d => d.name).join(', ')}`;
    }
    navigator.clipboard.writeText(text);
    setCopiedId(sig.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getSortLabel = (sort: SignalSort) => {
    switch (sort) {
      case 'NEWEST': return t('sort_newest');
      case 'HIGHEST_PROBABILITY': return t('sort_prob_desc');
      case 'HIGHEST_RISK': return t('sort_risk_desc');
      case 'LARGEST_DRAWDOWN': return t('sort_drawdown_desc');
      case 'EXPIRING_SOON': return t('sort_expiring_soon');
      default: return sort;
    }
  };


  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-2.5 sm:p-3.5 flex flex-col h-full overflow-hidden space-y-3">
      
      {/* 1. Header of Radar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="relative flex items-center justify-center">
            <div className="w-3 h-3 rounded-full bg-red-500 animate-ping absolute" />
            <div className="w-2.5 h-2.5 rounded-full bg-red-500 relative" />
          </div>
          <h2 className="text-xs sm:text-sm font-black text-slate-100 uppercase tracking-wider flex items-center gap-1.5 font-mono">
            <AlertOctagon className="w-4 h-4 text-red-500" />
            {t('feed_live_title')}
          </h2>
          <span className="px-2 py-0.5 bg-slate-800 text-amber-400 text-[10px] sm:text-xs rounded-full font-mono font-bold border border-amber-500/30">
            {activeFilterTag === 'ALL'
              ? `${kpiStats.total} ${t('unit_signals')}`
              : `${signals.length} / ${kpiStats.total} ${t('unit_signals')}`}
          </span>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2">
          {audioAlertEnabled && (
            <button
              onClick={playAlertSound}
              className="p-1.5 text-amber-400 hover:bg-slate-800 rounded-lg border border-slate-800 hover:border-amber-500/40 transition"
              title={t('signal_play_test_sound')}
            >
              <Volume2 className="w-3.5 h-3.5" />
            </button>
          )}

          {/* View Mode Switcher (Desktop / Tablet) */}
          <div className="hidden sm:inline-flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5">
            <button
              type="button"
              onClick={() => handleSelectViewMode('GRID')}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold transition ${
                viewMode === 'GRID'
                  ? 'bg-amber-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title={t('feed_view_grid')}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>{t('feed_view_grid')}</span>
            </button>

            <button
              type="button"
              onClick={() => handleSelectViewMode('TABLE')}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold transition ${
                viewMode === 'TABLE'
                  ? 'bg-amber-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title={t('feed_view_table')}
            >
              <List className="w-3.5 h-3.5" />
              <span>{t('feed_view_table')}</span>
            </button>

            <button
              type="button"
              onClick={() => handleSelectViewMode('SPLIT')}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold transition ${
                viewMode === 'SPLIT'
                  ? 'bg-amber-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title={t('feed_view_split')}
            >
              <Columns2 className="w-3.5 h-3.5" />
              <span>{t('feed_view_split')}</span>
            </button>
          </div>

          {onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="lg:hidden min-h-8 min-w-8 inline-flex items-center justify-center rounded-lg border border-slate-700 bg-slate-800/80 text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 active:scale-95"
              aria-expanded={!isCollapsed}
              aria-controls="radar-signal-list"
              aria-label={isCollapsed ? t('btn_track') : t('btn_tracked')}
              title={isCollapsed ? t('btn_track') : t('btn_tracked')}
            >
              {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            </button>
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className="rounded-xl border border-slate-800/90 bg-slate-950/80 p-2 sm:p-2.5 space-y-2">
          {/* Streamlined Main Action Bar */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            {/* Left: Search Bar & Core Tabs */}
            <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
              {/* Search Box */}
              <div className="relative w-full sm:w-56 shrink-0">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={localSearch}
                  onChange={(e) => setLocalSearch(e.target.value)}
                  placeholder={t('feed_search_placeholder')}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/40 font-mono transition"
                />
                {localSearch && (
                  <button
                    onClick={() => setLocalSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 p-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>

              {/* 4 Core Focus Tabs */}
              <div className="inline-flex items-center gap-1 p-0.5 rounded-lg bg-slate-900 border border-slate-800 overflow-x-auto max-w-full [&::-webkit-scrollbar]:hidden">
                {/* ALL */}
                <button
                  type="button"
                  onClick={() => setActiveFilterTag('ALL')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition shrink-0 ${
                    activeFilterTag === 'ALL'
                      ? 'bg-slate-700 text-white shadow-sm font-bold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  <span>{t('feed_tag_all')}</span>
                  <span className="ml-1 text-[10px] opacity-80 font-mono">({kpiStats.total})</span>
                </button>

                {/* FIRED */}
                <button
                  type="button"
                  onClick={() => setActiveFilterTag(activeFilterTag === 'FIRED' ? 'ALL' : 'FIRED')}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition shrink-0 ${
                    activeFilterTag === 'FIRED'
                      ? 'bg-red-950 border border-red-600 text-red-200 shadow-sm font-bold'
                      : 'text-red-400 hover:bg-red-950/40'
                  }`}
                >
                  <Zap className="w-3 h-3 fill-current" />
                  <span>{t('feed_tag_fired')}</span>
                  <span className="ml-0.5 text-[10px] font-mono font-bold">({kpiStats.fired})</span>
                  {kpiStats.fired > 0 && <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-ping" />}
                </button>

                {/* ARMED */}
                <button
                  type="button"
                  onClick={() => setActiveFilterTag(activeFilterTag === 'ARMED' ? 'ALL' : 'ARMED')}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition shrink-0 ${
                    activeFilterTag === 'ARMED'
                      ? 'bg-amber-950 border border-amber-600 text-amber-200 shadow-sm font-bold'
                      : 'text-amber-400 hover:bg-amber-950/40'
                  }`}
                >
                  <Compass className="w-3 h-3" />
                  <span>{t('feed_tag_armed')}</span>
                  <span className="ml-0.5 text-[10px] font-mono font-bold">({kpiStats.armed})</span>
                </button>

                {/* HOT RISK */}
                <button
                  type="button"
                  onClick={() => setActiveFilterTag(activeFilterTag === 'HOT_RISK' ? 'ALL' : 'HOT_RISK')}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold transition shrink-0 ${
                    activeFilterTag === 'HOT_RISK'
                      ? 'bg-orange-950 border border-orange-600 text-orange-200 shadow-sm font-bold'
                      : 'text-orange-400 hover:bg-orange-950/40'
                  }`}
                >
                  <Flame className="w-3 h-3" />
                  <span>{t('feed_tag_hot_risk')}</span>
                  <span className="ml-0.5 text-[10px] font-mono font-bold">({kpiStats.hotRisk})</span>
                </button>
              </div>
            </div>

            {/* Right: Sort Dropdown + Advanced Filter Drawer Trigger */}
            <div className="flex items-center gap-2 shrink-0">
              {/* Sort Dropdown */}
              <label className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-2 py-1 text-[11px] text-slate-400">
                <span className="shrink-0 text-slate-500 hidden sm:inline">{t('feed_filter_sort')}</span>
                <select
                  value={signalSort}
                  onChange={event => setSignalSort(event.target.value as SignalSort)}
                  className="min-w-0 rounded bg-slate-900 px-1 text-[11px] font-semibold text-slate-200 outline-none [color-scheme:dark]"
                  aria-label="Sort alerts"
                >
                  <option className="bg-slate-900 text-slate-200" value="NEWEST">{getSortLabel('NEWEST')}</option>
                  <option className="bg-slate-900 text-slate-200" value="HIGHEST_PROBABILITY">{getSortLabel('HIGHEST_PROBABILITY')}</option>
                  <option className="bg-slate-900 text-slate-200" value="HIGHEST_RISK">{getSortLabel('HIGHEST_RISK')}</option>
                  <option className="bg-slate-900 text-slate-200" value="LARGEST_DRAWDOWN">{getSortLabel('LARGEST_DRAWDOWN')}</option>
                  <option className="bg-slate-900 text-slate-200" value="EXPIRING_SOON">{getSortLabel('EXPIRING_SOON')}</option>
                </select>
              </label>

              {/* Advanced Filter Trigger Button */}
              <button
                type="button"
                onClick={() => setIsFilterDrawerOpen(true)}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-bold transition shadow-sm ${
                  activeAdvancedFilterCount > 0
                    ? 'border-amber-500 bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40'
                    : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-amber-500/60 hover:text-amber-300'
                }`}
                title="Mở bảng lọc nâng cao (Preset, Vốn hóa, Khối lượng, Sector...)"
              >
                <Filter className="w-3.5 h-3.5 text-amber-400" />
                <span>{language === 'en' ? 'Filters' : language === 'zh' ? '高级筛选' : language === 'ko' ? '필터' : 'Bộ lọc'}</span>
                {activeAdvancedFilterCount > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full bg-amber-500 text-slate-950 text-[10px] font-black">
                    {activeAdvancedFilterCount}
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* Active Filter Tags Bar (Only appears when secondary filters are applied) */}
          {(activeAdvancedFilterCount > 0 || (activeFilterTag !== 'ALL' && activeFilterTag !== 'FIRED' && activeFilterTag !== 'ARMED' && activeFilterTag !== 'HOT_RISK')) && (
            <div className="flex flex-wrap items-center gap-1.5 pt-1.5 border-t border-slate-800/80 text-[10px]">
              <span className="text-slate-400 font-semibold uppercase">{language === 'en' ? 'Active Filters:' : language === 'zh' ? '当前生效筛选:' : language === 'ko' ? '적용된 필터:' : 'Đang lọc:'}</span>

              {advancedFilters.preset !== 'ALL' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-950 border border-amber-800 text-amber-300 font-mono">
                  Preset: {advancedFilters.preset}
                  <button onClick={() => handleApplyAdvancedFilters({ ...advancedFilters, preset: 'ALL' })}><X className="w-2.5 h-2.5 hover:text-white" /></button>
                </span>
              )}

              {advancedFilters.marketCapTier !== 'ALL' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-violet-950 border border-violet-800 text-violet-300 font-mono">
                  Cap: {advancedFilters.marketCapTier}
                  <button onClick={() => handleApplyAdvancedFilters({ ...advancedFilters, marketCapTier: 'ALL' })}><X className="w-2.5 h-2.5 hover:text-white" /></button>
                </span>
              )}

              {!advancedFilters.sectors.includes('ALL') && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-950 border border-sky-800 text-sky-300 font-mono">
                  Sector: {advancedFilters.sectors.join(', ')}
                  <button onClick={() => handleApplyAdvancedFilters({ ...advancedFilters, sectors: ['ALL'] })}><X className="w-2.5 h-2.5 hover:text-white" /></button>
                </span>
              )}

              <button
                type="button"
                onClick={() => {
                  handleResetAdvancedFilters();
                  setActiveFilterTag('ALL');
                }}
                className="text-[10px] text-red-400 hover:text-red-300 font-bold ml-1 transition underline"
              >
                {language === 'en' ? 'Reset All' : language === 'zh' ? '清空全部' : language === 'ko' ? '모두 초기화' : 'Xóa tất cả'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* 4. Main Signals Content Area (GRID / TABLE / SPLIT) */}
      {!isCollapsed && (
        <div id="radar-signal-list" className="flex-1 min-h-0 overflow-y-auto pr-0.5">
          {groupedSignals.length === 0 ? (
            <div className="p-12 text-center text-slate-500 text-xs flex flex-col items-center justify-center gap-2">
              <ShieldAlert className="w-8 h-8 text-slate-600" />
              <span>{t('feed_no_matching')}</span>
              {localSearch && (
                <button
                  onClick={() => setLocalSearch('')}
                  className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-400 text-xs transition mt-1"
                >
                  {t('chart_reset')}
                </button>
              )}
            </div>
          ) : viewMode === 'TABLE' ? (
            /* =========================================================================
             * VIEW MODE 2: TABLE VIEW (Dense scanning for power traders)
             * ========================================================================= */
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/70">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/80 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    <th className="py-2.5 px-3">{t('feed_col_coin')}</th>
                    <th className="py-2.5 px-3">{t('feed_col_risk')}</th>
                    <th className="py-2.5 px-3">{t('feed_col_prob')}</th>
                    <th className="py-2.5 px-3">{t('feed_col_target')}</th>
                    <th className="py-2.5 px-3 hidden sm:table-cell">{t('feed_col_derivatives')}</th>
                    <th className="py-2.5 px-3 hidden md:table-cell">{t('feed_col_validity')}</th>
                    <th className="py-2.5 px-3 text-right">{t('feed_col_actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {groupedSignals.map(({ signal: sig, count }) => {
                    const isSelected = sig.id === selectedSignalId;
                    const probPct = (sig.probability * 100).toFixed(1);
                    const timing = getSignalTiming(sig);
                    const isTracked = Boolean(isSignalTracked?.(sig));

                    return (
                      <tr
                        key={sig.id}
                        onClick={() => onSelectSignal(sig)}
                        className={`transition cursor-pointer ${
                          isSelected
                            ? 'bg-amber-500/10 hover:bg-amber-500/15'
                            : 'hover:bg-slate-900/70'
                        }`}
                      >
                        {/* Coin & Multiplier & State */}
                        <td className="py-2.5 px-3">
                          {(() => {
                            const sector = getCoinSector(sig.symbol);
                            const sectorCfg = getSectorBadgeConfig(sector, language);
                            const capInfo = getCoinMarketCapInfo(sig.symbol, sig);
                            const capCfg = getMarketCapBadgeConfig(capInfo.market_cap_tier, capInfo.market_cap_str, language);

                            return (
                              <div className="space-y-1">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <CoinLink symbol={sig.symbol} onClick={() => onSelectSignal(sig)} className="font-bold text-slate-100 hover:text-amber-300" />
                                  {count > 1 && (
                                    <span className="px-1 py-0.2 bg-slate-800 text-amber-400 text-[9px] rounded font-bold border border-amber-500/30">
                                      x{count}
                                    </span>
                                  )}
                                  {getSignalTwoTierState(sig) === 'FIRED' ? (
                                    <span className="px-1.5 py-0.5 rounded text-[9px] font-black bg-red-950 text-amber-300 border border-red-600 animate-pulse">
                                      FIRED
                                    </span>
                                  ) : getSignalTwoTierState(sig) === 'ARMED' ? (
                                    <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-950/80 text-amber-300 border border-amber-600/80">
                                      ARMED
                                    </span>
                                  ) : null}

                                  {/* Smart Sector & Market Cap Badges */}
                                  <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold border flex items-center gap-1 ${sectorCfg.className}`} title={`Sector: ${sectorCfg.label}`}>
                                    <span>{sectorCfg.icon}</span>
                                    <span>{sectorCfg.label}</span>
                                  </span>
                                  <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold border flex items-center gap-1 ${capCfg.className}`} title={`Market Cap: ${capInfo.market_cap_str}`}>
                                    <span>{capCfg.icon}</span>
                                    <span>{capCfg.label}</span>
                                  </span>
                                </div>
                                {(sig.trigger_pattern || sig.trigger_pattern_vi) && (
                                  <div className="text-[9px] text-amber-400 font-normal truncate max-w-[220px] flex items-center gap-1">
                                    <Sparkles className="w-2.5 h-2.5 text-amber-400 shrink-0" />
                                    <span className="truncate">{language === 'vi' ? (sig.trigger_pattern_vi || sig.trigger_pattern) : (sig.trigger_pattern || sig.trigger_pattern_vi)}</span>
                                  </div>
                                )}
                              </div>
                            );
                          })()}
                        </td>

                        {/* Risk Badge */}
                        <td className="py-2.5 px-3 whitespace-nowrap">
                          {getRiskBadge(sig.risk_level)}
                        </td>

                        {/* Probability */}
                        <td className="py-2.5 px-3 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-amber-400">{probPct}%</span>
                            <div className="w-12 bg-slate-800 rounded-full h-1.5 overflow-hidden hidden sm:block">
                              <div
                                className={`h-full ${
                                  sig.risk_level === 'CRITICAL'
                                    ? 'bg-red-500'
                                    : sig.risk_level === 'HIGH'
                                    ? 'bg-amber-500'
                                    : 'bg-yellow-400'
                                }`}
                                style={{ width: `${probPct}%` }}
                              />
                            </div>
                          </div>
                        </td>

                        {/* Target Price */}
                        <td className="py-2.5 px-3 whitespace-nowrap">
                          <span className="text-red-400 font-bold flex items-center gap-0.5">
                            <TrendingDown className="w-3 h-3 shrink-0" />
                            {sig.target_drawdown}% (${sig.target_price})
                          </span>
                        </td>

                        {/* Derivatives (OI & Funding) */}
                        <td className="py-2.5 px-3 hidden sm:table-cell whitespace-nowrap">
                          <div className="text-[10px] text-slate-300">
                            OI: <span className="font-semibold text-sky-400">{sig.oi_change_24h || 'N/A'}</span>
                            <span className="mx-1 text-slate-600">|</span>
                            FR: <span className="font-semibold text-amber-400">{sig.funding_rate || 'N/A'}</span>
                          </div>
                          {sig.anomalies && sig.anomalies.length > 0 && (
                            <div className="mt-1 flex max-w-[220px] flex-wrap gap-1">
                              {sig.anomalies.slice(0, 2).map((anomaly) => (
                                <span
                                  key={anomaly.code}
                                  className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${getAnomalyClass(anomaly)}`}
                                  title={anomaly.explanation}
                                >
                                  {getAnomalyLabel(anomaly)}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>

                        {/* Timing */}
                        <td className="py-2.5 px-3 hidden md:table-cell whitespace-nowrap">
                          <div className="text-[10px]">
                            <span className="text-slate-400">{timing.elapsedLabel}</span>
                            <span className="mx-1 text-slate-600">·</span>
                            <span className={timing.isExpired ? 'text-red-400' : 'text-amber-300 font-semibold'}>
                              {timing.isExpired ? t('feed_tag_expired') : timing.remainingLabel}
                            </span>
                          </div>
                        </td>

                        {/* Actions */}
                        <td className="py-2.5 px-3 text-right whitespace-nowrap">
                          <div className="inline-flex items-center gap-1" onClick={e => e.stopPropagation()}>
                            {onGoToDecision && (
                              <button
                                onClick={() => onGoToDecision(sig)}
                                className="px-2 py-1 rounded bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-[10px] transition flex items-center gap-1 shadow-sm"
                                title={t('feed_btn_analyze')}
                              >
                                <BarChart2 className="w-3 h-3" />
                                <span className="hidden sm:inline">{t('feed_btn_analyze')}</span>
                              </button>
                            )}

                            {onOpenOrderModal && (
                              <button
                                onClick={() => {
                                  onSelectSignal(sig);
                                  onOpenOrderModal(sig);
                                }}
                                className="px-2 py-1 rounded bg-red-950 hover:bg-red-900 border border-red-700 text-red-300 font-bold text-[10px] transition flex items-center gap-1"
                                title={t('feed_btn_short')}
                              >
                                <Target className="w-3 h-3 text-red-400" />
                                <span className="hidden sm:inline">{t('feed_btn_short')}</span>
                              </button>
                            )}

                            {onTrackSignal && (
                              <button
                                onClick={() => {
                                  if (isTracked && onUntrackSignal) onUntrackSignal(sig);
                                  else onTrackSignal(sig);
                                }}
                                className={`p-1 rounded border transition text-[10px] ${
                                  isTracked
                                    ? 'border-amber-500/50 bg-amber-500/10 text-amber-300'
                                    : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200'
                                }`}
                                title={isTracked ? t('btn_untrack') : t('btn_track')}
                              >
                                {isTracked ? <Eye className="w-3 h-3 text-amber-400" /> : <EyeOff className="w-3 h-3" />}
                              </button>
                            )}

                            <button
                              onClick={() => handleCopyAlertText(sig)}
                              className="p-1 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 transition"
                              title={t('drawer_copy_text')}
                            >
                              {copiedId === sig.id ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                            </button>

                            <button
                              onClick={() => onPushTelegram(sig)}
                              className="p-1 rounded bg-sky-950 hover:bg-sky-900 border border-sky-800 text-sky-400 transition"
                              title={t('drawer_push_telegram')}
                            >
                              <Send className="w-3 h-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : viewMode === 'SPLIT' ? (
            /* =========================================================================
             * VIEW MODE 3: SPLIT INSPECTOR VIEW (Feed on Left + Live Inspector on Right)
             * ========================================================================= */
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 h-full items-start">
              {/* Left Column: Compact Signals List */}
              <div className="lg:col-span-5 xl:col-span-5 space-y-2.5 overflow-y-auto max-h-[calc(100vh-280px)] pr-1">
                {groupedSignals.map(({ signal: sig, count }) => {
                  const isSelected = sig.id === (activeInspectedSignal?.id || selectedSignalId);
                  const probPct = (sig.probability * 100).toFixed(1);
                  const timing = getSignalTiming(sig);

                  return (
                    <div
                      key={sig.id}
                      onClick={() => onSelectSignal(sig)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer relative ${
                        isSelected
                          ? 'bg-slate-800/95 border-amber-500 ring-1 ring-amber-500/40 shadow-lg shadow-amber-500/10'
                          : 'bg-slate-950/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900/80'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5">
                          <CoinLink symbol={sig.symbol} onClick={() => onSelectSignal(sig)} className="text-sm font-bold text-slate-100" />
                          <span className="text-[11px] text-slate-400 font-normal">({sig.name})</span>
                          {count > 1 && (
                            <span className="px-1.5 py-0.2 bg-slate-800 text-amber-400 text-[10px] rounded font-bold border border-amber-500/30">
                              x{count}
                            </span>
                          )}
                        </div>
                        {getRiskBadge(sig.risk_level)}
                      </div>

                      <div className="flex items-center justify-between text-xs font-mono mb-1">
                        <div>
                          <span className="text-[10px] text-slate-400 block">{t('feed_dist_prob')}</span>
                          <span className="font-bold text-amber-400">{probPct}%</span>
                        </div>
                        <div className="text-right">
                          <span className="text-[10px] text-slate-400 block">{t('feed_target_drawdown')}</span>
                          <span className="font-bold text-red-400 flex items-center justify-end gap-0.5">
                            <TrendingDown className="w-3 h-3" />
                            {sig.target_drawdown}%
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-800/60 font-mono">
                        <span className="text-sky-300">{timing.elapsedLabel}</span>
                        <span className={timing.isExpired ? 'text-red-400' : 'text-amber-300'}>
                          {timing.isExpired ? t('feed_tag_expired') : timing.remainingLabel}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Right Column: Live Inspector Panel */}
              <div className="lg:col-span-7 xl:col-span-7 sticky top-0 bg-slate-950/90 border border-slate-800 rounded-xl p-4 space-y-3.5 shadow-xl">
                {activeInspectedSignal ? (
                  <>
                    {/* Inspector Top Row */}
                    <div className="flex items-start justify-between border-b border-slate-800 pb-3">
                      <div>
                        {(() => {
                          const inspSector = getCoinSector(activeInspectedSignal.symbol);
                          const inspSectorCfg = getSectorBadgeConfig(inspSector, language);
                          const inspCapInfo = getCoinMarketCapInfo(activeInspectedSignal.symbol, activeInspectedSignal);
                          const inspCapCfg = getMarketCapBadgeConfig(inspCapInfo.market_cap_tier, inspCapInfo.market_cap_str, language);

                          return (
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="text-lg font-black text-slate-100 font-mono flex items-center gap-1.5">
                                  {activeInspectedSignal.symbol}
                                  <span className="text-xs text-slate-400 font-normal">({activeInspectedSignal.name})</span>
                                </h3>
                                {getSignalTwoTierState(activeInspectedSignal) === 'FIRED' ? (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-black bg-red-950 text-amber-300 border border-red-600 animate-pulse">
                                    ⚡ FIRED CLIMAX
                                  </span>
                                ) : getSignalTwoTierState(activeInspectedSignal) === 'ARMED' ? (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 text-amber-300 border border-amber-600/80">
                                    🧭 ARMED SETUP
                                  </span>
                                ) : null}

                                {/* Sector & Market Cap Badges */}
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${inspSectorCfg.className}`}>
                                  <span>{inspSectorCfg.icon}</span>
                                  <span>{inspSectorCfg.label}</span>
                                </span>
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${inspCapCfg.className}`}>
                                  <span>{inspCapCfg.icon}</span>
                                  <span>{inspCapCfg.label}</span>
                                </span>
                              </div>
                              <div className="text-xs text-slate-400 mt-1">
                                {t('feed_inspector_title')}
                              </div>
                            </div>
                          );
                        })()}
                      </div>

                      <div className="flex items-center gap-1.5">
                        {getRiskBadge(activeInspectedSignal.risk_level)}
                      </div>
                    </div>

                    {/* Inspector Action Buttons */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      {onGoToDecision && (
                        <button
                          onClick={() => onGoToDecision(activeInspectedSignal)}
                          className="px-3 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-xs transition flex items-center justify-center gap-1.5 shadow-md shadow-amber-500/20"
                        >
                          <BarChart2 className="w-4 h-4" />
                          {t('feed_btn_analyze')}
                        </button>
                      )}

                      {onOpenOrderModal && (
                        <button
                          onClick={() => {
                            onSelectSignal(activeInspectedSignal);
                            onOpenOrderModal(activeInspectedSignal);
                          }}
                          className="px-3 py-2 rounded-lg bg-red-950 hover:bg-red-900 border border-red-600 text-red-300 font-black text-xs transition flex items-center justify-center gap-1.5 shadow-md shadow-red-950/50"
                        >
                          <Target className="w-4 h-4 text-red-400" />
                          {t('feed_btn_short')}
                        </button>
                      )}

                      {onTrackSignal && (
                        <button
                          onClick={() => {
                            const isTracked = Boolean(isSignalTracked?.(activeInspectedSignal));
                            if (isTracked && onUntrackSignal) onUntrackSignal(activeInspectedSignal);
                            else onTrackSignal(activeInspectedSignal);
                          }}
                          className={`px-3 py-2 rounded-lg border text-xs font-bold transition flex items-center justify-center gap-1.5 ${
                            isSignalTracked?.(activeInspectedSignal)
                              ? 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:border-red-600 hover:bg-red-950'
                              : 'border-slate-800 bg-slate-900 text-slate-300 hover:border-sky-800 hover:bg-sky-950'
                          }`}
                        >
                          {isSignalTracked?.(activeInspectedSignal) ? (
                            <>
                              <Eye className="w-3.5 h-3.5 text-amber-400" />
                              {t('btn_tracked')}
                            </>
                          ) : (
                            <>
                              <EyeOff className="w-3.5 h-3.5" />
                              {t('btn_track')}
                            </>
                          )}
                        </button>
                      )}

                      <button
                        onClick={() => onPushTelegram(activeInspectedSignal)}
                        className="px-3 py-2 rounded-lg bg-sky-950 hover:bg-sky-900 border border-sky-800 text-sky-400 font-bold text-xs transition flex items-center justify-center gap-1.5"
                      >
                        <Send className="w-3.5 h-3.5" />
                        Telegram
                      </button>
                    </div>

                    {/* Trigger Pattern & R:R */}
                    {(activeInspectedSignal.trigger_pattern || activeInspectedSignal.trigger_pattern_vi) && (
                      <div className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-red-500/10 border border-amber-500/30 flex items-center justify-between text-xs font-mono">
                        <span className="font-bold text-amber-300 flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                          <span>{language === 'vi' ? (activeInspectedSignal.trigger_pattern_vi || activeInspectedSignal.trigger_pattern) : (activeInspectedSignal.trigger_pattern || activeInspectedSignal.trigger_pattern_vi)}</span>
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-700 font-bold shrink-0">
                          R:R 1:{activeInspectedSignal.trade_setup?.rr_ratio?.toFixed(1) ?? '2.1'}
                        </span>
                      </div>
                    )}

                    {/* Trade Setup Matrix Box */}
                    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 space-y-2">
                      <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <Target className="w-3.5 h-3.5 text-amber-400" />
                          {t('feed_inspector_trade_plan')}
                        </div>
                        <span className="font-mono text-[10px] text-red-400 font-bold">
                          Target {activeInspectedSignal.target_drawdown}% (${activeInspectedSignal.target_price})
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center font-mono">
                        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
                          <span className="text-[9px] text-slate-400 block uppercase">Entry Zone</span>
                          <span className="text-xs sm:text-sm font-bold text-slate-200 truncate block">
                            ${activeInspectedSignal.trade_setup?.entry_price ?? (activeInspectedSignal.signal_price || activeInspectedSignal.target_price)}
                          </span>
                        </div>

                        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
                          <span className="text-[9px] text-red-400 block uppercase">SL (+{activeInspectedSignal.trade_setup?.stop_loss_pct ?? 3.8}%)</span>
                          <span className="text-xs sm:text-sm font-bold text-red-400 truncate block">
                            ${activeInspectedSignal.trade_setup?.stop_loss ?? ((activeInspectedSignal.signal_price || activeInspectedSignal.target_price) * 1.038).toFixed(6)}
                          </span>
                        </div>

                        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
                          <span className="text-[9px] text-emerald-400 block uppercase">TP1 (-4%)</span>
                          <span className="text-xs sm:text-sm font-bold text-emerald-400 truncate block">
                            ${activeInspectedSignal.trade_setup?.tp1 ?? ((activeInspectedSignal.signal_price || activeInspectedSignal.target_price) * 0.96).toFixed(6)}
                          </span>
                        </div>

                        <div className="bg-slate-950 p-2 rounded-lg border border-slate-800/80">
                          <span className="text-[9px] text-emerald-400 block uppercase">TP2 (-8%)</span>
                          <span className="text-xs sm:text-sm font-bold text-emerald-400 truncate block">
                            ${activeInspectedSignal.trade_setup?.tp2 ?? activeInspectedSignal.target_price}
                          </span>
                        </div>
                      </div>

                      {/* Live MFE / MAE & Outcome Status in Inspector Pane */}
                      <div className="mt-2 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800/80 flex items-center justify-between text-[11px] font-mono">
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-500">MFE:</span>
                          <span className="font-bold text-emerald-400">{activeInspectedSignal.mfe_pct !== undefined && activeInspectedSignal.mfe_pct !== null ? `${activeInspectedSignal.mfe_pct.toFixed(1)}%` : '-2.8%'}</span>
                          <span className="text-slate-600">|</span>
                          <span className="text-slate-500">MAE:</span>
                          <span className="font-bold text-red-400">{activeInspectedSignal.mae_pct !== undefined && activeInspectedSignal.mae_pct !== null ? `+${activeInspectedSignal.mae_pct.toFixed(1)}%` : '+1.1%'}</span>
                        </div>
                        <div>
                          {activeInspectedSignal.outcome_status === 'TARGET_HIT' || activeInspectedSignal.hit === true ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">
                              TARGET HIT
                            </span>
                          ) : activeInspectedSignal.outcome_status === 'STOPPED_OUT' || activeInspectedSignal.hit === false ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-950 text-red-300 border border-red-700">
                              STOPPED OUT
                            </span>
                          ) : activeInspectedSignal.outcome_status === 'EXPIRED' ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-900 text-slate-400 border border-slate-700">
                              EXPIRED
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-950 text-sky-300 border border-sky-800">
                              ACTIVE TRACKING
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Microstructure & Derivatives Box */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs font-mono">
                      <div className="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800">
                        <span className="text-[10px] text-slate-400 block">OI Delta 24h</span>
                        <span className="text-sm font-bold text-sky-400">{activeInspectedSignal.oi_change_24h || 'N/A'}</span>
                      </div>

                      <div className="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800">
                        <span className="text-[10px] text-slate-400 block">Funding Rate</span>
                        <span className="text-sm font-bold text-amber-400">{activeInspectedSignal.funding_rate || 'N/A'}</span>
                      </div>

                      <div className="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800 col-span-2 sm:col-span-1">
                        <span className="text-[10px] text-slate-400 block">Taker Sell Ratio</span>
                        <span className="text-sm font-bold text-emerald-400">
                          {activeInspectedSignal.taker_sell_ratio ? `${(activeInspectedSignal.taker_sell_ratio * 100).toFixed(1)}%` : 'N/A'}
                        </span>
                      </div>
                    </div>

                    {activeInspectedSignal.anomalies && activeInspectedSignal.anomalies.length > 0 && (
                      <div className="rounded-xl border border-violet-900/70 bg-violet-950/20 p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-violet-300">
                            {language === 'vi' ? 'Radar bất thường' : 'Anomaly radar'}
                          </span>
                          <span className="font-mono text-xs font-bold text-violet-300">
                            {activeInspectedSignal.anomaly_level || 'WATCH'} · {activeInspectedSignal.anomaly_score?.toFixed(0) ?? '—'}/100
                          </span>
                        </div>
                        <div className="space-y-1.5">
                          {activeInspectedSignal.anomalies.map((anomaly) => (
                            <div key={anomaly.code} className="flex items-start justify-between gap-2 text-[10px]">
                              <span className={`rounded border px-1.5 py-0.5 font-semibold ${getAnomalyClass(anomaly)}`}>
                                {getAnomalyLabel(anomaly)}
                              </span>
                              <span className="text-right text-slate-400">{anomaly.explanation}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* AI Warning Drivers */}
                    <div className="space-y-1.5">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Lý do AI Cảnh báo (SHAP / Feature Drivers)
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {activeInspectedSignal.drivers.map((d, idx) => (
                          <span
                            key={idx}
                            className="px-2.5 py-1 rounded-lg bg-slate-900 text-slate-300 text-xs border border-slate-800 flex items-center gap-1.5"
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                            {d.name}
                            {d.score && <span className="text-amber-400 font-mono text-[10px]">({d.score})</span>}
                          </span>
                        ))}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="p-8 text-center text-slate-500 text-xs">
                    {t('feed_no_matching')}
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* =========================================================================
             * VIEW MODE 1: MODERN RESPONSIVE GRID VIEW (1 col Mobile, 2 col Tablet, 3 col 2XL)
             * ========================================================================= */
            <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3">
              {groupedSignals.map(({ signal: sig, count }) => {
                const isSelected = sig.id === selectedSignalId;
                const probPct = (sig.probability * 100).toFixed(1);
                const timing = getSignalTiming(sig);
                const isTracked = Boolean(isSignalTracked?.(sig));

                return (
                  <div
                    key={sig.id}
                    onClick={() => onSelectSignal(sig)}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer relative group flex flex-col justify-between ${
                      isSelected
                        ? 'bg-slate-800/90 border-amber-500 shadow-lg shadow-amber-500/10 ring-1 ring-amber-500/30'
                        : 'bg-slate-950/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900/80 hover:shadow-md'
                    }`}
                  >
                    {/* Top Row: Symbol, Name, Multiplier & Badges */}
                    <div>
                      {(() => {
                        const gridSector = getCoinSector(sig.symbol);
                        const gridSectorCfg = getSectorBadgeConfig(gridSector, language);
                        const gridCapInfo = getCoinMarketCapInfo(sig.symbol, sig);
                        const gridCapCfg = getMarketCapBadgeConfig(gridCapInfo.market_cap_tier, gridCapInfo.market_cap_str, language);

                        return (
                          <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <CoinLink
                                symbol={sig.symbol}
                                onClick={() => onSelectSignal(sig)}
                                className="text-base font-extrabold text-slate-100 group-hover:text-amber-300 transition"
                              />
                              <span className="text-xs text-slate-400 font-normal">({sig.name})</span>
                              {count > 1 && (
                                <span className="px-1.5 py-0.2 bg-slate-800 text-amber-400 text-[10px] rounded font-bold border border-amber-500/30 font-mono">
                                  x{count}
                                </span>
                              )}

                              {/* Smart Sector Badge & Market Cap Badge */}
                              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border flex items-center gap-1 ${gridSectorCfg.className}`} title={`Hệ sinh thái: ${gridSectorCfg.label}`}>
                                <span>{gridSectorCfg.icon}</span>
                                <span>{gridSectorCfg.label}</span>
                              </span>
                              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border flex items-center gap-1 ${gridCapCfg.className}`} title={`Vốn hóa: ${gridCapInfo.market_cap_str}`}>
                                <span>{gridCapCfg.icon}</span>
                                <span>{gridCapCfg.label}</span>
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              {getSignalTwoTierState(sig) === 'FIRED' ? (
                                <span className="px-2 py-0.5 rounded text-[10px] font-black font-mono bg-red-950 text-amber-300 border border-red-600 animate-pulse flex items-center gap-1 shadow-sm shadow-red-900/50">
                                  <Zap className="w-3 h-3 text-amber-400 fill-amber-400" />
                                  FIRED
                                </span>
                              ) : getSignalTwoTierState(sig) === 'ARMED' ? (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-950/80 text-amber-300 border border-amber-600/80 flex items-center gap-1">
                                  <Compass className="w-3 h-3 text-amber-400" />
                                  ARMED
                                </span>
                              ) : null}
                              {getRiskBadge(sig.risk_level)}
                            </div>
                          </div>
                        );
                      })()}

                      {/* Trigger Pattern & R:R Badge */}
                      {(sig.trigger_pattern || sig.trigger_pattern_vi) && (
                        <div className="mb-2 px-2.5 py-1 rounded-lg bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-red-500/10 border border-amber-500/30 flex items-center justify-between text-[10px]">
                          <span className="font-bold text-amber-300 flex items-center gap-1 min-w-0">
                            <Sparkles className="w-3 h-3 text-amber-400 shrink-0" />
                            <span className="truncate">{language === 'vi' ? (sig.trigger_pattern_vi || sig.trigger_pattern) : (sig.trigger_pattern || sig.trigger_pattern_vi)}</span>
                          </span>
                          <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-700 font-bold shrink-0 ml-1">
                            R:R 1:{sig.trade_setup?.rr_ratio?.toFixed(1) ?? '2.1'}
                          </span>
                        </div>
                      )}

                      {/* Middle Row: Probability & Target Drawdown */}
                      <div className="grid grid-cols-2 gap-2 mb-2 bg-slate-900/80 p-2.5 rounded-xl border border-slate-800/80">
                        <div>
                          <div className="text-[10px] text-slate-400 uppercase font-medium">
                            {t('feed_dist_prob')}
                          </div>
                          <div className="text-lg font-black text-amber-400 font-mono">
                            {probPct}%
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-[10px] text-slate-400 uppercase font-medium">
                            {t('feed_target_drawdown')}
                          </div>
                          <div className="text-sm font-black text-red-400 font-mono flex items-center justify-end gap-1">
                            <TrendingDown className="w-3.5 h-3.5" />
                            {sig.target_drawdown}% (${sig.target_price})
                          </div>
                        </div>
                      </div>

                      {/* Actionable Trade Setup Plan Box */}
                      <div className="grid grid-cols-4 gap-1 mb-2 font-mono text-[10px] bg-slate-900/90 p-2 rounded-lg border border-slate-800/90">
                        <div className="text-left">
                          <span className="text-[9px] text-slate-500 block uppercase">Entry</span>
                          <span className="font-bold text-slate-200 truncate block">${sig.trade_setup?.entry_price ?? sig.signal_price}</span>
                        </div>
                        <div className="text-left">
                          <span className="text-[9px] text-red-400 block uppercase">SL (+{sig.trade_setup?.stop_loss_pct ?? 3.8}%)</span>
                          <span className="font-bold text-red-300 truncate block">${sig.trade_setup?.stop_loss ?? (sig.signal_price ? (sig.signal_price * 1.038).toFixed(4) : 0)}</span>
                        </div>
                        <div className="text-left">
                          <span className="text-[9px] text-emerald-400 block uppercase">TP1 (-4%)</span>
                          <span className="font-bold text-emerald-300 truncate block">${sig.trade_setup?.tp1 ?? (sig.signal_price ? (sig.signal_price * 0.96).toFixed(4) : 0)}</span>
                        </div>
                        <div className="text-right">
                          <span className="text-[9px] text-emerald-400 block uppercase">TP2 (-8%)</span>
                          <span className="font-bold text-emerald-300 truncate block">${sig.trade_setup?.tp2 ?? sig.target_price}</span>
                        </div>
                      </div>

                      {/* Live MFE / MAE & Outcome Status Bar */}
                      <div className="mb-2 px-2.5 py-1 rounded-lg bg-slate-950/70 border border-slate-800/70 flex items-center justify-between text-[10px] font-mono">
                        <div className="flex items-center gap-1">
                          <span className="text-slate-500">MFE:</span>
                          <span className="font-bold text-emerald-400">{sig.mfe_pct !== undefined && sig.mfe_pct !== null ? `${sig.mfe_pct.toFixed(1)}%` : '-2.8%'}</span>
                          <span className="text-slate-600">|</span>
                          <span className="text-slate-500">MAE:</span>
                          <span className="font-bold text-red-400">{sig.mae_pct !== undefined && sig.mae_pct !== null ? `+${sig.mae_pct.toFixed(1)}%` : '+1.1%'}</span>
                        </div>
                        <div>
                          {sig.outcome_status === 'TARGET_HIT' || sig.hit === true ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">
                              TARGET HIT
                            </span>
                          ) : sig.outcome_status === 'STOPPED_OUT' || sig.hit === false ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-red-950 text-red-300 border border-red-700">
                              STOPPED OUT
                            </span>
                          ) : sig.outcome_status === 'EXPIRED' ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-900 text-slate-400 border border-slate-700">
                              EXPIRED
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-sky-950 text-sky-300 border border-sky-800">
                              ACTIVE
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Probability Gauge Bar */}
                      <div className="w-full bg-slate-800 rounded-full h-1.5 mb-2.5 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${
                            sig.risk_level === 'CRITICAL'
                              ? 'bg-gradient-to-r from-red-600 to-red-400'
                              : sig.risk_level === 'HIGH'
                              ? 'bg-gradient-to-r from-amber-600 to-amber-400'
                              : 'bg-gradient-to-r from-yellow-500 to-amber-300'
                          }`}
                          style={{ width: `${probPct}%` }}
                        />
                      </div>

                      {/* Microstructure Row (OI & Funding) */}
                      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-400 bg-slate-950/60 px-2.5 py-1.5 rounded-lg border border-slate-800/60 mb-2">
                        <div>
                          <span className="text-slate-500">OI 24h: </span>
                          <span className="text-sky-300 font-bold">{sig.oi_change_24h || 'N/A'}</span>
                        </div>
                        <div className="text-right">
                          <span className="text-slate-500">Funding: </span>
                          <span className="text-amber-300 font-bold">{sig.funding_rate || 'N/A'}</span>
                        </div>
                      </div>

                      {sig.anomalies && sig.anomalies.length > 0 && (
                        <div className="mb-2 rounded-lg border border-violet-900/60 bg-violet-950/20 px-2.5 py-1.5">
                          <div className="mb-1 flex items-center justify-between text-[9px] font-bold uppercase tracking-wider text-violet-300">
                            <span>{language === 'vi' ? 'Bất thường phát hiện' : 'Detected anomalies'}</span>
                            <span className="font-mono text-violet-400">{sig.anomaly_score?.toFixed(0) ?? '—'}/100</span>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {sig.anomalies.slice(0, 3).map((anomaly) => (
                              <span
                                key={anomaly.code}
                                className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${getAnomalyClass(anomaly)}`}
                                title={anomaly.explanation}
                              >
                                {getAnomalyLabel(anomaly)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Timing, remaining validity and progress */}
                      <div className="pt-0.5 mb-2.5">
                        <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                          <div className="flex items-center gap-1 text-slate-400">
                            <Clock className="w-3 h-3 text-sky-400 shrink-0" />
                            <span>{t('feed_reported')}:</span>
                            <span className="text-sky-300 font-semibold">{timing.elapsedLabel}</span>
                          </div>
                          <div className={`flex items-center justify-end gap-1 ${timing.isExpired ? 'text-red-400' : 'text-slate-400'}`}>
                            <span>{t('feed_left')}:</span>
                            <span className={`font-semibold ${timing.isExpired ? 'text-red-400' : timing.remainingSeconds <= 7200 ? 'text-red-300' : 'text-amber-300'}`}>
                              {timing.isExpired ? t('feed_tag_expired') : timing.remainingLabel}
                            </span>
                          </div>
                        </div>
                        <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-slate-800">
                          <div
                            className={`h-full rounded-full transition-all ${timing.isExpired ? 'bg-red-500' : timing.remainingSeconds <= 7200 ? 'bg-gradient-to-r from-amber-500 to-red-500' : 'bg-sky-500'}`}
                            style={{ width: `${timing.progress}%` }}
                          />
                        </div>
                      </div>

                      {/* Driver Tags preview */}
                      <div className="flex flex-wrap gap-1 mb-3">
                        {sig.drivers.slice(0, 3).map((driver, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 rounded bg-slate-900 text-slate-300 text-[10px] border border-slate-800"
                          >
                            • {driver.name}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Action Buttons Toolbar Footer */}
                    <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-1.5">
                      <div className="flex items-center gap-1.5">
                        {onGoToDecision && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onGoToDecision(sig);
                            }}
                            className="px-2.5 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-[11px] transition flex items-center gap-1 shadow-sm"
                            title={t('feed_btn_analyze')}
                          >
                            <BarChart2 className="w-3 h-3" />
                            <span>{t('feed_btn_analyze')}</span>
                          </button>
                        )}

                        {onOpenOrderModal && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectSignal(sig);
                              onOpenOrderModal(sig);
                            }}
                            className="px-2.5 py-1 rounded-lg bg-red-950 hover:bg-red-900 border border-red-700 text-red-300 font-bold text-[11px] transition flex items-center gap-1"
                            title={t('feed_btn_short')}
                          >
                            <Target className="w-3 h-3 text-red-400" />
                            <span>{t('feed_btn_short')}</span>
                          </button>
                        )}
                      </div>

                      <div className="flex items-center gap-1">
                        {onTrackSignal && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isTracked && onUntrackSignal) {
                                onUntrackSignal(sig);
                              } else {
                                onTrackSignal(sig);
                              }
                            }}
                            className={`group/track px-2 py-1 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition border ${
                              isTracked
                                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:border-red-600/70 hover:bg-red-950/80 hover:text-red-300'
                                : 'border-slate-800 bg-slate-900 text-slate-300 hover:border-sky-800 hover:bg-sky-950 hover:text-sky-300'
                            }`}
                            title={isTracked ? t('btn_untrack') : t('btn_track')}
                          >
                            {isTracked ? (
                              <>
                                <Eye className="w-3 h-3 text-amber-400" />
                                <span className="hidden sm:inline">{t('btn_tracked')}</span>
                              </>
                            ) : (
                              <>
                                <EyeOff className="w-3 h-3" />
                                <span className="hidden sm:inline">{t('btn_track')}</span>
                              </>
                            )}
                          </button>
                        )}

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopyAlertText(sig);
                          }}
                          className="p-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-lg text-[10px] flex items-center gap-1 transition"
                          title={t('drawer_copy_text')}
                        >
                          {copiedId === sig.id ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5 text-slate-400" />
                          )}
                        </button>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onPushTelegram(sig);
                          }}
                          className="px-2 py-1 bg-sky-950 hover:bg-sky-900 border border-sky-800 text-sky-400 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition"
                          title={t('drawer_push_telegram')}
                        >
                          <Send className="w-3 h-3" />
                          <span className="hidden sm:inline">Telegram</span>
                        </button>

                        {onDismissSignal && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onDismissSignal(sig);
                            }}
                            className="p-1 bg-slate-900 hover:bg-red-950 border border-slate-800 hover:border-red-800 text-slate-400 hover:text-red-400 rounded-lg text-[10px] transition"
                            title={t('btn_close')}
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 5. Advanced Radar Filter Drawer */}
      <RadarFilterDrawer
        isOpen={isFilterDrawerOpen}
        onClose={() => setIsFilterDrawerOpen(false)}
        filters={advancedFilters}
        onApplyFilters={handleApplyAdvancedFilters}
        onResetFilters={handleResetAdvancedFilters}
        signals={signals}
        allSignals={allSignals && allSignals.length > 0 ? allSignals : signals}
      />

    </div>
  );
};
