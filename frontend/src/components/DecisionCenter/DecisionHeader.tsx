import React, { useState, useRef, useEffect } from 'react';
import { Search, Flame, CheckCircle2, XCircle, Clock, Send, Activity } from 'lucide-react';
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
  
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setIsSearchOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  // Top 5 Hot Candidates for quick 1-click bar
  const topCandidates = [...candidates]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 5);

  // Filtered search list
  const filteredCandidates = candidates.filter(c =>
    c.symbol.toLowerCase().includes(searchQuery.trim().toLowerCase())
  ).slice(0, 8);

  const handleSelectCoin = (targetSymbol: string) => {
    onSelectCandidate(targetSymbol);
    setSearchQuery('');
    setIsSearchOpen(false);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const q = searchQuery.trim().toUpperCase();
      if (q) {
        const fullSymbol = q.endsWith('USDT') ? q : `${q}USDT`;
        handleSelectCoin(fullSymbol);
      }
    }
  };

  return (
    <div className="bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 border border-slate-800 rounded-xl p-3 sm:p-4 shadow-lg min-w-0">
      {/* Top Quick Bar: Quick Search + Top Hot Candidates */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pb-3 mb-3 border-b border-slate-800/80">
        {/* Quick Search Input */}
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs" ref={searchContainerRef}>
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setIsSearchOpen(true);
              }}
              onFocus={() => setIsSearchOpen(true)}
              onKeyDown={handleSearchKeyDown}
              placeholder={t('search_placeholder')}
              className="w-full bg-slate-900/90 border border-slate-700/80 hover:border-amber-500/50 focus:border-amber-500 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none transition font-mono"
            />
          </div>

          {/* Autocomplete Dropdown */}
          {isSearchOpen && searchQuery.trim().length > 0 && (
            <div className="absolute left-0 right-0 top-full mt-1 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl z-30 max-h-56 overflow-y-auto divide-y divide-slate-800">
              {filteredCandidates.length > 0 ? (
                filteredCandidates.map((c) => (
                  <button
                    key={c.symbol}
                    type="button"
                    onClick={() => handleSelectCoin(c.symbol)}
                    className={`w-full px-3 py-2 text-left flex items-center justify-between hover:bg-slate-800 transition text-xs ${
                      c.symbol === symbol ? 'bg-amber-500/10 text-amber-300' : 'text-slate-200'
                    }`}
                  >
                    <span className="font-bold font-mono">{c.symbol}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-400 font-mono">${c.price?.toFixed(4) || '—'}</span>
                      <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-950 text-amber-400 border border-amber-800">
                        {c.score?.toFixed(0) || 0} pts
                      </span>
                    </div>
                  </button>
                ))
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    const q = searchQuery.trim().toUpperCase();
                    const full = q.endsWith('USDT') ? q : `${q}USDT`;
                    handleSelectCoin(full);
                  }}
                  className="w-full px-3 py-2 text-left text-xs text-amber-400 hover:bg-slate-800 transition"
                >
                  {`${t('decision_search_analyze')} "${searchQuery.toUpperCase()}"`}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Top 5 Hot Candidates Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto max-w-full py-0.5 [&::-webkit-scrollbar]:hidden">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1 shrink-0">
            <Flame className="w-3 h-3 text-orange-400" />
            {t('decision_hot_coins')}
          </span>
          {topCandidates.map((c) => {
            const isSelected = c.symbol === symbol;
            return (
              <button
                key={c.symbol}
                type="button"
                onClick={() => handleSelectCoin(c.symbol)}
                className={`px-2 py-1 rounded-md text-[11px] font-mono font-bold shrink-0 transition border flex items-center gap-1 ${
                  isSelected
                    ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm shadow-amber-500/30'
                    : 'bg-slate-900/80 text-slate-300 border-slate-700/70 hover:border-amber-500/50 hover:text-amber-300'
                }`}
                title={`${t('decision_switch_to')} ${c.symbol}`}
              >
                <span>{c.symbol.replace('USDT', '')}</span>
                <span className={`text-[9px] ${isSelected ? 'text-slate-900 font-extrabold' : 'text-amber-400'}`}>
                  {c.score?.toFixed(0)}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Identity Row */}
      <div className="flex flex-wrap items-center justify-between gap-3 min-w-0">
        {/* Left: Avatar & Ticker info */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/5 border border-amber-500/40 flex items-center justify-center shrink-0 shadow-inner">
            <span className="text-amber-400 font-black text-base tracking-tight">
              {symbol.replace('USDT', '').slice(0, 3)}
            </span>
          </div>
          <div className="min-w-0">
            <div className="text-lg font-black text-slate-100 flex items-center gap-2 flex-wrap">
              <CoinLink symbol={symbol} onClick={onSelectCandidate} className="text-lg font-black text-white hover:text-amber-300" />
              <span className="text-xs font-normal text-slate-400">({name})</span>

              {/* Status Badges */}
              {selectedSignal?.hit === true && (
                <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded-md flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> {t('ws_hit_status')}
                </span>
              )}
              {selectedSignal?.hit === false && (
                <span className="px-2 py-0.5 text-[10px] font-bold bg-red-950 text-red-400 border border-red-800 rounded-md flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> {t('ws_missed_status')}
                </span>
              )}
              {selectedSignal?.hit === null && (
                <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-900 text-slate-400 border border-slate-700 rounded-md flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {t('ws_pending_status')}
                </span>
              )}
              {selectedSignal?.telegram_sent && (
                <span className="px-2 py-0.5 text-[10px] font-bold bg-sky-950 text-sky-400 border border-sky-800 rounded-md flex items-center gap-1">
                  <Send className="w-3 h-3" /> Telegram
                </span>
              )}
              {chartSource === 'api' && (
                <span className="px-2 py-0.5 text-[10px] font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/80 rounded-md">
                  ● Live API
                </span>
              )}
            </div>

            {/* Price line */}
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xl font-black text-amber-400 font-mono tracking-tight">
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
      </div>
    </div>
  );
};
