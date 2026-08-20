import React, { useState, useEffect } from 'react';
import type { FilterTag, SignalItem, RiskLevel, SignalSort, TelegramFilter } from '../types';
import { parseSystemDate } from '../utils/time';
import { Clock, TrendingDown, Send, Copy, Check, Volume2, AlertOctagon, X, ChevronDown, ChevronUp, Flame, Zap, Eye } from 'lucide-react';
import { CoinLink } from './CoinLink';
import { useTranslation } from '../i18n/LanguageContext';
import { getRiskLabel, formatDuration } from '../i18n/translations';

interface SignalFeedProps {
  signals: SignalItem[];
  selectedSignalId: string | null;
  onSelectSignal: (signal: SignalItem) => void;
  onPushTelegram: (signal: SignalItem) => void;
  onTrackSignal?: (signal: SignalItem) => void;
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
  selectedSignalId,
  onSelectSignal,
  onPushTelegram,
  onTrackSignal,
  isSignalTracked,
  audioAlertEnabled,
  onDismissSignal,
  activeFilterTag,
  setActiveFilterTag,
  signalSort,
  setSignalSort,
  telegramFilter,
  setTelegramFilter,
  isCollapsed = false,
  onToggleCollapse
}) => {
  const { language, t } = useTranslation();
  const [, setTicks] = useState(0);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Real-time ticking countdown timer effect
  useEffect(() => {
    const timer = setInterval(() => {
      setTicks(t => t + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Group signals by symbol to avoid duplicates, keep track of count
  const groupedSignals = React.useMemo(() => {
    const map = new Map<string, { signal: SignalItem; count: number }>();
    for (const sig of signals) {
      const symKey = (sig.symbol || '').trim();
      if (map.has(symKey)) {
        map.get(symKey)!.count++;
      } else {
        map.set(symKey, { signal: sig, count: 1 });
      }
    }
    return Array.from(map.values());
  }, [signals]);

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
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-950/90 border border-red-600/90 text-red-400 animate-pulse">
            🔴 {getRiskLabel('CRITICAL', language)}
          </span>
        );
      case 'HIGH':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 border border-amber-500/80 text-amber-400">
            🟠 {getRiskLabel('HIGH', language)}
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-yellow-950/80 border border-yellow-500/60 text-yellow-300">
            🟡 {getRiskLabel('MEDIUM', language)}
          </span>
        );
      case 'SAFE':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 border border-emerald-500/60 text-emerald-400">
            🟢 {getRiskLabel('SAFE', language)}
          </span>
        );
    }
  };

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
      case 'EXPIRING_SOON': return t('sort_expiring_soon');
      default: return sort;
    }
  };

  const getTelegramFilterLabel = (filter: TelegramFilter) => {
    switch (filter) {
      case 'ALL': return t('feed_tg_all');
      case 'SENT': return t('feed_tg_sent');
      case 'UNSENT': return t('feed_tg_unsent');
      default: return filter;
    }
  };

  return (
    <div className={`bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 flex flex-col overflow-hidden ${isCollapsed ? 'h-auto lg:h-full' : 'h-[min(68vh,620px)] lg:h-full'}`}>
      
      {/* Header of Feed */}
      <div className={`flex items-center justify-between border-b border-slate-800 ${isCollapsed ? 'pb-0' : 'pb-2.5 mb-2.5'}`}>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
          <h2 className="text-xs font-bold text-slate-100 uppercase tracking-wider flex items-center gap-1.5">
            <AlertOctagon className="w-3.5 h-3.5 text-red-500" />
            {t('feed_live_title')}
          </h2>
        </div>
        <div className="flex items-center gap-1.5">
          {audioAlertEnabled && (
            <button
              onClick={playAlertSound}
              className="p-1 text-amber-400 hover:bg-slate-800 rounded"
              title={t('signal_play_test_sound')}
            >
              <Volume2 className="w-3.5 h-3.5" />
            </button>
          )}
          <span className="px-2 py-0.5 bg-slate-800 text-slate-400 text-[10px] rounded-full font-mono font-bold">
            {signals.length} {t('unit_signals')}
          </span>
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
        <div className="mb-2.5 rounded-lg border border-slate-800/80 bg-slate-950/70 p-1.5">
          <div className="flex items-center justify-between gap-2 mb-1.5 px-0.5">
            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500">
              {t('feed_quick_filters')}
            </span>
            <span className="text-[9px] font-mono text-slate-500">
              {signals.length} {t('feed_results_count')}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1.5 mb-1.5">
            <label className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-[10px] text-slate-400">
              <span className="shrink-0 text-slate-500">{t('feed_filter_sort')}</span>
              <select
                value={signalSort}
                onChange={event => setSignalSort(event.target.value as SignalSort)}
                className="min-w-0 flex-1 rounded bg-slate-900 px-1 text-[10px] font-semibold text-slate-200 outline-none [color-scheme:dark]"
                style={{ colorScheme: 'dark' }}
                aria-label="Sort alerts"
              >
                <option className="bg-slate-900 text-slate-200" value="NEWEST">{getSortLabel('NEWEST')}</option>
                <option className="bg-slate-900 text-slate-200" value="HIGHEST_PROBABILITY">{getSortLabel('HIGHEST_PROBABILITY')}</option>
                <option className="bg-slate-900 text-slate-200" value="HIGHEST_RISK">{getSortLabel('HIGHEST_RISK')}</option>
                <option className="bg-slate-900 text-slate-200" value="EXPIRING_SOON">{getSortLabel('EXPIRING_SOON')}</option>
              </select>
            </label>
            <label className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-[10px] text-slate-400">
              <span className="shrink-0 text-slate-500">{t('feed_filter_status')}</span>
              <select
                value={telegramFilter}
                onChange={event => setTelegramFilter(event.target.value as TelegramFilter)}
                className="min-w-0 flex-1 rounded bg-slate-900 px-1 text-[10px] font-semibold text-slate-200 outline-none [color-scheme:dark]"
                style={{ colorScheme: 'dark' }}
                aria-label="Telegram filter"
              >
                <option className="bg-slate-900 text-slate-200" value="ALL">{getTelegramFilterLabel('ALL')}</option>
                <option className="bg-slate-900 text-slate-200" value="SENT">{getTelegramFilterLabel('SENT')}</option>
                <option className="bg-slate-900 text-slate-200" value="UNSENT">{getTelegramFilterLabel('UNSENT')}</option>
              </select>
            </label>
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 [&::-webkit-scrollbar]:hidden">
            <button
              type="button"
              onClick={() => setActiveFilterTag('ALL')}
              className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold transition ${
                activeFilterTag === 'ALL'
                  ? 'border-slate-600 bg-slate-700 text-white'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700 hover:text-slate-200'
              }`}
            >
              {t('feed_tag_all')}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilterTag('HOT_RISK')}
              className={`shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-semibold transition ${
                activeFilterTag === 'HOT_RISK'
                  ? 'border-red-700 bg-red-950/80 text-red-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-red-900/70 hover:text-red-300'
              }`}
            >
              <Flame className="w-3 h-3" /> {t('feed_tag_hot_risk')}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilterTag('EXPIRING')}
              className={`shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-semibold transition ${
                activeFilterTag === 'EXPIRING'
                  ? 'border-amber-700 bg-amber-950/80 text-amber-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-amber-900/70 hover:text-amber-300'
              }`}
            >
              <Clock className="w-3 h-3" /> {t('feed_tag_expiring')}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilterTag('VOLUME_SPIKE')}
              className={`shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-semibold transition ${
                activeFilterTag === 'VOLUME_SPIKE'
                  ? 'border-sky-700 bg-sky-950/80 text-sky-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-sky-900/70 hover:text-sky-300'
              }`}
            >
              <Zap className="w-3 h-3" /> {t('feed_tag_volume_spike')}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilterTag('ACTIVE')}
              className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold transition ${
                activeFilterTag === 'ACTIVE'
                  ? 'border-emerald-700 bg-emerald-950/80 text-emerald-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-emerald-900/70 hover:text-emerald-300'
              }`}
            >
              {t('feed_tag_active')}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilterTag('EXPIRED')}
              className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold transition ${
                activeFilterTag === 'EXPIRED'
                  ? 'border-slate-600 bg-slate-700 text-slate-200'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700 hover:text-slate-200'
              }`}
            >
              {t('feed_tag_expired')}
            </button>
          </div>
        </div>
      )}

      {/* Live Signal Feed List */}
      {!isCollapsed && <div id="radar-signal-list" className="flex-1 min-h-0 overflow-y-auto space-y-2.5 pr-1">
        {groupedSignals.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs">
            {t('feed_no_matching')}
          </div>
        ) : (
          groupedSignals.map(({ signal: sig, count }) => {
            const isSelected = sig.id === selectedSignalId;
            const probPct = (sig.probability * 100).toFixed(1);

            return (
              <div
                key={sig.id}
                onClick={() => onSelectSignal(sig)}
                className={`p-3 rounded-xl border transition-all cursor-pointer relative group ${
                  isSelected
                    ? 'bg-slate-800/90 border-amber-500 shadow-md shadow-amber-500/10'
                    : 'bg-slate-950/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900/90'
                }`}
              >
                {/* Top Row: Symbol, Name, Risk Badge */}
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <CoinLink symbol={sig.symbol} onClick={() => onSelectSignal(sig)} className="text-sm group-hover:text-amber-300 transition" />
                    <span className="text-[11px] text-slate-400">({sig.name})</span>
                    {count > 1 && (
                      <span className="ml-1 px-1.5 py-0.5 bg-slate-800 text-amber-400 text-[10px] rounded font-bold border border-amber-500/30">
                        x{count}
                      </span>
                    )}
                  </div>
                  {getRiskBadge(sig.risk_level)}
                </div>

                {/* Middle Row: Probability Gauge Bar & Price */}
                <div className="grid grid-cols-2 gap-2 mb-2 bg-slate-900/70 p-2 rounded-lg border border-slate-800/60">
                  <div>
                    <div className="text-[9px] text-slate-400 uppercase font-medium">
                      {t('feed_dist_prob')}
                    </div>
                    <div className="text-base font-extrabold text-amber-400 font-mono">
                      {probPct}%
                    </div>
                  </div>
                  <div>
                    <div className="text-[9px] text-slate-400 uppercase font-medium">
                      {t('feed_target_drawdown')}
                    </div>
                    <div className="text-xs font-bold text-red-400 font-mono flex items-center gap-1">
                      <TrendingDown className="w-3.5 h-3.5" />
                      {sig.target_drawdown}% (${sig.target_price})
                    </div>
                  </div>
                </div>

                {/* Progress bar for probability */}
                <div className="w-full bg-slate-800 rounded-full h-1.5 mb-2 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      sig.risk_level === 'CRITICAL'
                        ? 'bg-gradient-to-r from-red-600 to-red-400'
                        : sig.risk_level === 'HIGH'
                        ? 'bg-gradient-to-r from-amber-600 to-amber-400'
                        : 'bg-gradient-to-r from-yellow-500 to-amber-300'
                    }`}
                    style={{ width: `${probPct}%` }}
                  />
                </div>

                {/* Signal age, remaining validity and progress */}
                {(() => {
                  const timing = getSignalTiming(sig);
                  return (
                    <div className="pt-1 mb-2">
                      <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                        <div className="flex items-center gap-1 text-slate-400">
                          <Clock className="w-3 h-3 text-sky-400" />
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
                      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-slate-800" title={`${timing.progress.toFixed(0)}%`}>
                        <div
                          className={`h-full rounded-full transition-all ${timing.isExpired ? 'bg-red-500' : timing.remainingSeconds <= 7200 ? 'bg-gradient-to-r from-amber-500 to-red-500' : 'bg-sky-500'}`}
                          style={{ width: `${timing.progress}%` }}
                        />
                      </div>
                    </div>
                  );
                })()}

                {/* Action Buttons */}
                <div className="flex items-center justify-end text-[10px] pt-1">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCopyAlertText(sig);
                      }}
                      className="p-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded text-[10px] flex items-center gap-1 transition"
                      title={t('drawer_copy_text')}
                    >
                      {copiedId === sig.id ? (
                        <Check className="w-3 h-3 text-emerald-400" />
                      ) : (
                        <Copy className="w-3 h-3 text-slate-400" />
                      )}
                    </button>

                    {onTrackSignal && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onTrackSignal(sig);
                        }}
                        disabled={Boolean(isSignalTracked?.(sig))}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 transition border ${isSignalTracked?.(sig)
                          ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                          : 'border-slate-800 bg-slate-900 text-slate-300 hover:border-sky-800 hover:bg-sky-950 hover:text-sky-300'}`}
                        title={isSignalTracked?.(sig) ? t('btn_tracked') : t('btn_track')}
                      >
                        <Eye className="w-2.5 h-2.5" />
                        {isSignalTracked?.(sig) ? t('btn_tracked') : t('btn_track')}
                      </button>
                    )}

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onPushTelegram(sig);
                      }}
                      className="px-2 py-0.5 bg-sky-950 hover:bg-sky-900 border border-sky-800 text-sky-400 rounded text-[10px] font-semibold flex items-center gap-1 transition"
                      title={t('drawer_push_telegram')}
                    >
                      <Send className="w-2.5 h-2.5" />
                      Telegram
                    </button>

                    {onDismissSignal && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDismissSignal(sig);
                        }}
                        className="p-1 bg-slate-900 hover:bg-red-950 border border-slate-800 hover:border-red-800 text-slate-400 hover:text-red-400 rounded text-[10px] transition"
                        title={t('btn_close')}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Driver Tags preview */}
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {sig.drivers.map((driver, idx) => (
                    <span
                      key={idx}
                      className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 text-[9px] border border-slate-800"
                    >
                      • {driver.name}
                    </span>
                  ))}
                </div>

              </div>
            );
          })
        )}
      </div>}

    </div>
  );
};
