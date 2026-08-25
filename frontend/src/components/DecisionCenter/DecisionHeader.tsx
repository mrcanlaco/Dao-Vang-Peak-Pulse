import React from 'react';
import { Flame, CheckCircle2, XCircle, Clock, Send, Activity } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type { CandidateCoin, SignalItem } from '../../types';
import { CoinLink } from '../CoinLink';

interface DecisionHeaderProps {
  symbol: string;
  name: string;
  currentPrice: number;
  chartSource?: 'db' | 'api';
  selectedSignal?: SignalItem | null;
  candidates: CandidateCoin[];
  onSelectCandidate: (symbol: string) => void;
  isDeepAnalyzing?: boolean;
}

export const DecisionHeader: React.FC<DecisionHeaderProps> = ({
  symbol,
  name,
  currentPrice,
  chartSource,
  selectedSignal,
  candidates,
  onSelectCandidate,
  isDeepAnalyzing,
}) => {
  const { t } = useTranslation();

  // Top 5 Hot Candidates for quick 1-click bar
  const topCandidates = [...candidates]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 5);

  return (
    <div className="bg-gradient-to-r from-slate-950 via-slate-900/90 to-slate-950 border border-slate-800 rounded-xl p-2.5 sm:px-4 sm:py-3 shadow-md min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3 min-w-0">
        {/* Left: Avatar & Ticker info & Price */}
        <div className="flex items-center gap-2.5 sm:gap-3.5 min-w-0">
          <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/40 flex items-center justify-center shrink-0 shadow-inner">
            <span className="text-amber-400 font-black text-sm sm:text-base tracking-tight font-mono">
              {symbol.replace('USDT', '').slice(0, 3)}
            </span>
          </div>

          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <CoinLink symbol={symbol} onClick={onSelectCandidate} className="text-base sm:text-lg font-black text-white hover:text-amber-300 tracking-tight" />
              <span className="text-xs font-normal text-slate-400">({name})</span>

              {/* Status Badges */}
              {selectedSignal?.hit === true && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded-md flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> {t('ws_hit_status')}
                </span>
              )}
              {selectedSignal?.hit === false && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-red-950 text-red-400 border border-red-800 rounded-md flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> {t('ws_missed_status')}
                </span>
              )}
              {selectedSignal?.hit === null && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-slate-900 text-slate-400 border border-slate-700 rounded-md flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {t('ws_pending_status')}
                </span>
              )}
              {selectedSignal?.telegram_sent && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-sky-950 text-sky-400 border border-sky-800 rounded-md flex items-center gap-1">
                  <Send className="w-3 h-3" /> Telegram
                </span>
              )}
              {chartSource === 'api' && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/80 rounded-md">
                  ● Live API
                </span>
              )}
            </div>

            {/* Live Price & Indicator */}
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-lg sm:text-xl font-black text-amber-400 font-mono tracking-tight">
                ${currentPrice > 0 ? (currentPrice < 1 ? currentPrice.toFixed(6) : currentPrice.toFixed(4)) : '—'}
              </span>
              {isDeepAnalyzing && (
                <span className="text-[10px] text-amber-400/90 font-mono animate-pulse flex items-center gap-1">
                  <Activity className="w-3 h-3 animate-spin" /> {t('refreshing')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Hot Candidates Chips for fast 1-click switching */}
        {topCandidates.length > 0 && (
          <div className="hidden sm:flex items-center gap-1.5 overflow-x-auto max-w-full py-0.5 shrink-0">
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
    </div>
  );
};

