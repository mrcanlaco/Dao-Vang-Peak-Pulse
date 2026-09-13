import React from 'react';
import { Flame, ChevronDown, CheckCircle2, XCircle, Clock, Send, Activity } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type { CandidateCoin, SignalItem, SignalTradeSetup, RiskLevel } from '../../types';
import { normalizeProbability } from '../../types';
import { getRiskLabel } from '../../i18n/translations';

interface DecisionHeaderProps {
  symbol: string;
  displayDetail?: any;
  high24h?: number;
  low24h?: number;
  name: string;
  currentPrice: number;
  chartSource?: 'db' | 'api';
  selectedSignal?: SignalItem | null;
  candidates: CandidateCoin[];
  onSelectCandidate: (symbol: string) => void;
  isDeepAnalyzing?: boolean;
  onOpenCoinSelector?: () => void;
  probability?: number | null;
  riskLevel?: RiskLevel | string | null;
  tradeSetup?: SignalTradeSetup | null;
  onOpenTabHelp?: () => void;
}

export const DecisionHeader: React.FC<DecisionHeaderProps> = ({
  symbol,
  name,
  currentPrice,
  selectedSignal,
  candidates,
  onSelectCandidate,
  isDeepAnalyzing,
  onOpenCoinSelector,
  displayDetail,
  high24h,
  low24h,
  probability,
  riskLevel,
}) => {
  const { language, t } = useTranslation();

  // Top 5 Hot Candidates for quick 1-click bar
  const topCandidates = [...candidates]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 5);

  const probabilityPct = normalizeProbability(probability);
  const stateLabel = selectedSignal?.two_tier_state === 'FIRED'
    ? t('feed_tag_fired')
    : selectedSignal?.two_tier_state === 'ARMED'
      ? t('feed_tag_armed')
      : t('ws_rec_watch_badge');
  const localizedRisk = riskLevel ? getRiskLabel(riskLevel, language) : null;


  // 3. Exact Two-Tier State
  return (
    <div className="bg-gradient-to-r from-slate-950 via-slate-900/90 to-slate-950 border border-slate-800 rounded-xl p-3 sm:px-4 sm:py-3 shadow-md min-w-0">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4 min-w-0">
        {/* Left: Ticker info & Price */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={onOpenCoinSelector}
            className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/40 hover:border-amber-400 flex items-center justify-center shrink-0 shadow-inner group transition active:scale-95 cursor-pointer"
            title={t('coin_selector_title')}
          >
            <span className="text-amber-400 group-hover:text-amber-300 font-black text-sm sm:text-base tracking-tight font-mono">
              {symbol.replace('USDT', '').slice(0, 3)}
            </span>
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-0.5">
              <button
                type="button"
                onClick={onOpenCoinSelector}
                className="group flex items-center gap-1 text-base sm:text-lg font-black text-white hover:text-amber-300 tracking-tight transition"
                title={t('coin_selector_title')}
              >
                <span>{symbol}</span>
                <ChevronDown className="w-4 h-4 text-amber-400 group-hover:translate-y-0.5 transition" />
              </button>
              <span className="text-xs font-normal text-slate-400">({name})</span>

              {/* Status Badges */}
              {selectedSignal?.outcome_status === 'TARGET_HIT' && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded-md flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> {t('ws_hit_status')}
                </span>
              )}
              {['STOPPED_OUT', 'FAILED', 'EXPIRED'].includes(selectedSignal?.outcome_status || '') && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-red-950 text-red-400 border border-red-800 rounded-md flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> {t('ws_missed_status')}
                </span>
              )}
              {selectedSignal?.outcome_status === 'ACTIVE' && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-slate-900 text-slate-400 border border-slate-700 rounded-md flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {t('ws_pending_status')}
                </span>
              )}
              {selectedSignal?.telegram_sent && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-sky-950 text-sky-400 border border-sky-800 rounded-md flex items-center gap-1">
                  <Send className="w-3 h-3" /> Telegram
                </span>
              )}
            </div>

            {/* Live Price & Indicator */}
            <div className="flex items-center gap-2">
              <span className="text-2xl sm:text-3xl font-black text-emerald-400 font-mono tracking-tight">
                ${currentPrice > 0 ? (currentPrice < 1 ? currentPrice.toFixed(5) : currentPrice.toFixed(4)) : '—'}
              </span>
              {isDeepAnalyzing && (
                <span className="text-[10px] text-amber-400/90 font-mono animate-pulse flex items-center gap-1">
                  <Activity className="w-3 h-3 animate-spin" /> {t('refreshing')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Binance Style 2x2 Stats Grid */}
        <div className="hidden sm:grid grid-cols-2 gap-x-6 gap-y-1.5 text-[10px] font-mono shrink-0">
          <div className="flex flex-col">
            <span className="text-slate-500 font-sans">{language === 'en' ? '24h High' : 'Giá cao nhất 24h'}</span>
            <span className="text-slate-200 font-bold">{high24h ? (high24h < 1 ? high24h.toFixed(5) : high24h.toFixed(4)) : '—'}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-slate-500 font-sans">{language === 'en' ? '24h Vol(USDT)' : 'Khối lượng 24h'}</span>
            <span className="text-slate-200 font-bold">{displayDetail?.metrics?.volume_delta_24h || '—'}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-slate-500 font-sans">{language === 'en' ? '24h Low' : 'Giá thấp nhất 24h'}</span>
            <span className="text-slate-200 font-bold">{low24h ? (low24h < 1 ? low24h.toFixed(5) : low24h.toFixed(4)) : '—'}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-slate-500 font-sans">{language === 'en' ? 'Funding / Countdown' : 'Funding / Đếm ngược'}</span>
            <span className="text-amber-400 font-bold">{displayDetail?.metrics?.funding_rate || '—'}</span>
          </div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-[1fr_auto] items-center gap-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2.5 py-2 sm:hidden">
        <div className="min-w-0">
          <div className="text-[9px] font-semibold uppercase tracking-wider text-slate-500">
            {language === 'en' ? 'Current decision' : 'Quyết định hiện tại'}
          </div>
          <div className="truncate text-xs font-black text-amber-300">{stateLabel}</div>
        </div>
        <div className="flex items-center gap-1.5 text-right">
          {localizedRisk && (
            <span className="rounded-md border border-red-800/70 bg-red-950/70 px-1.5 py-1 text-[9px] font-bold text-red-300">
              {localizedRisk}
            </span>
          )}
          <span className="font-mono text-lg font-black text-amber-400">
            {probabilityPct != null ? `${probabilityPct.toFixed(1)}%` : '—'}
          </span>
        </div>
      </div>

      {/* Bottom: Hot Candidates Chips for fast 1-click switching */}
      {topCandidates.length > 0 && (
        <div className="hidden sm:flex items-center gap-1.5 overflow-x-auto max-w-full pt-3 mt-3 border-t border-slate-800/50 shrink-0">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1 shrink-0">
            <Flame className="w-3 h-3 text-orange-400" />
            {t('decision_hot_coins')}:
          </span>
          {topCandidates.map((c) => {
            const isSelected = c.symbol === symbol;
            return (
              <button
                key={c.symbol}
                type="button"
                onClick={() => onSelectCandidate(c.symbol)}
                className={`px-2 py-1 rounded-md text-xs font-mono font-bold shrink-0 transition border flex items-center gap-1.5 active:scale-95 ${
                  isSelected
                    ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm shadow-amber-500/30 font-extrabold'
                    : 'bg-slate-900/90 text-slate-300 border-slate-700/80 hover:border-amber-500/50 hover:text-amber-300'
                }`}
                title={`${t('decision_switch_to')} ${c.symbol}`}
              >
                <span>{c.symbol.replace('USDT', '')}</span>
                <span className={`text-[10px] ${isSelected ? 'text-slate-950 font-black' : 'text-amber-400 font-bold'}`}>
                  {c.score?.toFixed(0)}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

