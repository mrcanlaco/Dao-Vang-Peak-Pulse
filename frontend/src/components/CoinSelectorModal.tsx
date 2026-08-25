import React, { useState, useMemo, useRef, useEffect } from 'react';
import {
  Search,
  Star,
  Flame,
  Radio,
  TrendingUp,
  TrendingDown,
  Layers,
  X,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { SignalItem, CandidateCoin, MarketOverviewData, TrackingWatchlistItem, RiskLevel } from '../types';
import { useTranslation } from '../i18n/LanguageContext';
import { getRiskLabel } from '../i18n/translations';

export type CoinCategoryTab = 'ALL' | 'RADAR' | 'GAINERS' | 'LOSERS' | 'TOP' | 'FAVORITES';

export interface UnifiedCoinItem {
  symbol: string;
  name?: string;
  price: number;
  change24h?: number | null; // e.g. +5.2 or -3.1
  change24hStr?: string;
  volume24h?: number | null; // in USD
  volume24hStr?: string;
  fundingRate?: string | null;
  score?: number | null;
  probability?: number | null;
  riskLevel?: RiskLevel | null;
  hasRadarSignal?: boolean;
  isFavorite?: boolean;
  isTracking?: boolean;
  sourceType: 'radar' | 'candidate' | 'gainer' | 'loser' | 'market' | 'watchlist';
}

interface CoinSelectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentSymbol: string;
  onSelectCoin: (symbol: string) => void;
  signals: SignalItem[];
  candidates: CandidateCoin[];
  marketData: MarketOverviewData | null;
  manualWatchlist: string[];
  trackingItems: TrackingWatchlistItem[];
  onToggleWatchlist?: (symbol: string) => void | Promise<boolean>;
}

type SortField = 'symbol' | 'price' | 'change' | 'score' | 'volume';
type SortOrder = 'asc' | 'desc';

export const CoinSelectorModal: React.FC<CoinSelectorModalProps> = ({
  isOpen,
  onClose,
  currentSymbol,
  onSelectCoin,
  signals,
  candidates,
  marketData,
  manualWatchlist,
  trackingItems,
  onToggleWatchlist,
}) => {
  const { language, t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<CoinCategoryTab>('ALL');
  const [sortField, setSortField] = useState<SortField>('score');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const searchInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-focus search input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }, 50);
    } else {
      setSearchQuery('');
    }
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Aggregate all unique coins from all sources into unified structure
  const unifiedCoins = useMemo(() => {
    const coinMap = new Map<string, UnifiedCoinItem>();

    // 1. Process Active Radar Signals
    signals.forEach((sig) => {
      const sym = sig.symbol.trim().toUpperCase();
      coinMap.set(sym, {
        symbol: sym,
        name: sig.name || sym,
        price: sig.signal_price || 0,
        fundingRate: sig.funding_rate,
        probability: sig.probability,
        riskLevel: sig.risk_level,
        hasRadarSignal: true,
        sourceType: 'radar',
      });
    });

    // 2. Process Candidates
    candidates.forEach((cand) => {
      const sym = cand.symbol.trim().toUpperCase();
      const existing = coinMap.get(sym);
      const volNum = cand.volume_24h && cand.volume_24h.includes('M')
        ? parseFloat(cand.volume_24h.replace('$', '').replace('M', '')) * 1_000_000
        : null;

      coinMap.set(sym, {
        symbol: sym,
        name: existing?.name || sym,
        price: cand.price || existing?.price || 0,
        score: cand.score,
        riskLevel: cand.risk || existing?.riskLevel,
        fundingRate: cand.funding !== 'N/A' ? cand.funding : existing?.fundingRate,
        volume24h: volNum,
        volume24hStr: cand.volume_24h,
        hasRadarSignal: existing?.hasRadarSignal || false,
        probability: existing?.probability,
        sourceType: existing ? existing.sourceType : 'candidate',
      });
    });

    // 3. Process Market Top Gainers
    if (marketData?.top_gainers) {
      marketData.top_gainers.forEach((g) => {
        const sym = g.symbol.trim().toUpperCase();
        const existing = coinMap.get(sym);
        const changeNum = parseFloat(g.change.replace('%', '').replace('+', ''));
        coinMap.set(sym, {
          symbol: sym,
          name: existing?.name || sym,
          price: g.price || existing?.price || 0,
          change24h: isNaN(changeNum) ? null : changeNum,
          change24hStr: g.change,
          volume24h: g.volume_24h || existing?.volume24h,
          fundingRate: existing?.fundingRate,
          score: existing?.score,
          probability: existing?.probability,
          riskLevel: existing?.riskLevel,
          hasRadarSignal: existing?.hasRadarSignal || false,
          sourceType: existing ? existing.sourceType : 'gainer',
        });
      });
    }

    // 4. Process Market Top Losers
    if (marketData?.top_losers) {
      marketData.top_losers.forEach((l) => {
        const sym = l.symbol.trim().toUpperCase();
        const existing = coinMap.get(sym);
        const changeNum = parseFloat(l.change.replace('%', ''));
        coinMap.set(sym, {
          symbol: sym,
          name: existing?.name || sym,
          price: l.price || existing?.price || 0,
          change24h: isNaN(changeNum) ? null : changeNum,
          change24hStr: l.change,
          volume24h: l.volume_24h || existing?.volume24h,
          fundingRate: existing?.fundingRate,
          score: existing?.score,
          probability: existing?.probability,
          riskLevel: existing?.riskLevel,
          hasRadarSignal: existing?.hasRadarSignal || false,
          sourceType: existing ? existing.sourceType : 'loser',
        });
      });
    }

    // 5. Process Manual Watchlist & Tracking
    manualWatchlist.forEach((sym) => {
      const cleanSym = sym.trim().toUpperCase();
      const existing = coinMap.get(cleanSym);
      if (!existing) {
        coinMap.set(cleanSym, {
          symbol: cleanSym,
          name: cleanSym,
          price: 0,
          sourceType: 'watchlist',
        });
      }
    });

    trackingItems.forEach((it) => {
      const cleanSym = it.symbol.trim().toUpperCase();
      const existing = coinMap.get(cleanSym);
      if (existing) {
        existing.isTracking = true;
        if (it.current_price && it.current_price > 0) existing.price = it.current_price;
        if (it.current_probability) existing.probability = it.current_probability;
      } else {
        coinMap.set(cleanSym, {
          symbol: cleanSym,
          name: cleanSym,
          price: it.current_price || it.source_price || 0,
          probability: it.current_probability || it.source_probability,
          isTracking: true,
          sourceType: 'watchlist',
        });
      }
    });

    // Populate isFavorite flag
    const list = Array.from(coinMap.values()).map((coin) => ({
      ...coin,
      isFavorite: manualWatchlist.includes(coin.symbol) || trackingItems.some((t) => t.symbol === coin.symbol && t.status !== 'CLOSED'),
    }));

    return list;
  }, [signals, candidates, marketData, manualWatchlist, trackingItems]);

  // Tab Counts for badges
  const counts = useMemo(() => {
    const radarCount = unifiedCoins.filter((c) => c.hasRadarSignal).length;
    const favCount = unifiedCoins.filter((c) => c.isFavorite).length;
    const gainersCount = marketData?.top_gainers?.length || 0;
    const losersCount = marketData?.top_losers?.length || 0;
    const topCount = candidates.length;
    return {
      all: unifiedCoins.length,
      radar: radarCount,
      gainers: gainersCount,
      losers: losersCount,
      top: topCount,
      favorites: favCount,
    };
  }, [unifiedCoins, marketData, candidates]);

  // Filter by Tab and Search Query
  const filteredCoins = useMemo(() => {
    let list = unifiedCoins;

    // Filter by Tab
    if (activeTab === 'RADAR') {
      list = list.filter((c) => c.hasRadarSignal);
    } else if (activeTab === 'FAVORITES') {
      list = list.filter((c) => c.isFavorite);
    } else if (activeTab === 'GAINERS') {
      list = list.filter((c) => (c.change24h != null && c.change24h > 0) || c.sourceType === 'gainer');
    } else if (activeTab === 'LOSERS') {
      list = list.filter((c) => (c.change24h != null && c.change24h < 0) || c.sourceType === 'loser');
    } else if (activeTab === 'TOP') {
      list = list.filter((c) => c.score != null || c.sourceType === 'candidate');
    }

    // Filter by Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toUpperCase();
      list = list.filter((c) => c.symbol.includes(q) || (c.name && c.name.toUpperCase().includes(q)));
    }

    // Sort list
    return [...list].sort((a, b) => {
      let comparison = 0;
      if (sortField === 'symbol') {
        comparison = a.symbol.localeCompare(b.symbol);
      } else if (sortField === 'price') {
        comparison = (a.price || 0) - (b.price || 0);
      } else if (sortField === 'change') {
        comparison = (a.change24h ?? -9999) - (b.change24h ?? -9999);
      } else if (sortField === 'score') {
        const aScore = a.probability != null ? a.probability * 100 : (a.score ?? -1);
        const bScore = b.probability != null ? b.probability * 100 : (b.score ?? -1);
        comparison = aScore - bScore;
      } else if (sortField === 'volume') {
        comparison = (a.volume24h || 0) - (b.volume24h || 0);
      }
      return sortOrder === 'desc' ? -comparison : comparison;
    });
  }, [unifiedCoins, activeTab, searchQuery, sortField, sortOrder]);

  const handleSortToggle = (field: SortField) => {
    if (sortField === field) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  const formatPrice = (p?: number | null) => {
    if (p == null || p <= 0) return '—';
    if (p < 0.0001) return p.toFixed(6);
    if (p < 1) return p.toFixed(4);
    if (p < 10) return p.toFixed(3);
    return p.toFixed(2);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-10 sm:pt-16 p-2 sm:p-4 bg-slate-950/80 backdrop-blur-sm">
      {/* Backdrop click to close */}
      <div
        className="fixed inset-0"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Main Binance-Style Modal Container */}
      <div
        ref={containerRef}
        className="relative z-10 w-full max-w-3xl max-h-[85vh] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-100 font-sans"
      >
        {/* 1. Header with Search Bar and Close button */}
        <div className="p-3 sm:p-4 border-b border-slate-800 bg-slate-950/90 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-lg">🪙</span>
              <h2 className="text-sm sm:text-base font-black tracking-wide text-slate-100 flex items-center gap-2">
                {t('coin_selector_title')}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Đóng (Esc)"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Search Input Box */}
          <div className="relative flex items-center">
            <Search className="absolute left-3 w-4 h-4 text-slate-400" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder={t('coin_selector_search_placeholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700/80 hover:border-amber-500/50 focus:border-amber-500 rounded-xl pl-9 pr-8 py-2 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none transition font-mono shadow-inner"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 p-1 text-slate-400 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Category Tabs (Binance Style Pill Buttons) */}
          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
            {/* All */}
            <button
              type="button"
              onClick={() => setActiveTab('ALL')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition shrink-0 flex items-center gap-1.5 ${
                activeTab === 'ALL'
                  ? 'bg-amber-500 text-slate-950 shadow-sm shadow-amber-500/20'
                  : 'bg-slate-800/80 text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>{t('coin_tab_all')}</span>
              <span className={`text-[10px] px-1 rounded font-mono ${activeTab === 'ALL' ? 'bg-amber-600 text-white' : 'bg-slate-700 text-slate-300'}`}>
                {counts.all}
              </span>
            </button>

            {/* Radar Signals */}
            <button
              type="button"
              onClick={() => setActiveTab('RADAR')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition shrink-0 flex items-center gap-1.5 ${
                activeTab === 'RADAR'
                  ? 'bg-red-500 text-white shadow-sm shadow-red-500/20'
                  : 'bg-slate-800/80 text-red-300 hover:bg-slate-800'
              }`}
            >
              <Radio className="w-3.5 h-3.5" />
              <span>{t('coin_tab_radar')}</span>
              {counts.radar > 0 && (
                <span className="text-[10px] px-1.5 py-0.2 rounded-full font-mono bg-red-600 text-white font-bold animate-pulse">
                  {counts.radar}
                </span>
              )}
            </button>

            {/* Top Gainers */}
            <button
              type="button"
              onClick={() => setActiveTab('GAINERS')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition shrink-0 flex items-center gap-1.5 ${
                activeTab === 'GAINERS'
                  ? 'bg-emerald-500 text-slate-950 font-black shadow-sm'
                  : 'bg-slate-800/80 text-emerald-400 hover:bg-slate-800'
              }`}
            >
              <TrendingUp className="w-3.5 h-3.5" />
              <span>{t('coin_tab_gainers')}</span>
            </button>

            {/* Top Losers */}
            <button
              type="button"
              onClick={() => setActiveTab('LOSERS')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition shrink-0 flex items-center gap-1.5 ${
                activeTab === 'LOSERS'
                  ? 'bg-rose-600 text-white font-black shadow-sm'
                  : 'bg-slate-800/80 text-rose-400 hover:bg-slate-800'
              }`}
            >
              <TrendingDown className="w-3.5 h-3.5" />
              <span>{t('coin_tab_losers')}</span>
            </button>

            {/* Top Candidate / Score */}
            <button
              type="button"
              onClick={() => setActiveTab('TOP')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition shrink-0 flex items-center gap-1.5 ${
                activeTab === 'TOP'
                  ? 'bg-amber-500 text-slate-950 shadow-sm'
                  : 'bg-slate-800/80 text-amber-300 hover:bg-slate-800'
              }`}
            >
              <Flame className="w-3.5 h-3.5 text-orange-400" />
              <span>{t('coin_tab_top')}</span>
              <span className={`text-[10px] px-1 rounded font-mono ${activeTab === 'TOP' ? 'bg-amber-600 text-white' : 'bg-slate-700 text-slate-300'}`}>
                {counts.top}
              </span>
            </button>

            {/* Favorites / Tracking */}
            <button
              type="button"
              onClick={() => setActiveTab('FAVORITES')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition shrink-0 flex items-center gap-1.5 ${
                activeTab === 'FAVORITES'
                  ? 'bg-yellow-400 text-slate-950 shadow-sm'
                  : 'bg-slate-800/80 text-yellow-300 hover:bg-slate-800'
              }`}
            >
              <Star className="w-3.5 h-3.5 fill-yellow-400 text-yellow-400" />
              <span>{t('coin_tab_favorites')}</span>
              {counts.favorites > 0 && (
                <span className={`text-[10px] px-1 rounded font-mono ${activeTab === 'FAVORITES' ? 'bg-yellow-600 text-white' : 'bg-slate-700 text-slate-300'}`}>
                  {counts.favorites}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* 2. Coin Table Header */}
        <div className="grid grid-cols-12 px-3 sm:px-4 py-2 border-b border-slate-800 bg-slate-950/60 text-[11px] font-bold text-slate-400 uppercase tracking-wider select-none">
          <div className="col-span-5 sm:col-span-4 flex items-center gap-1.5 cursor-pointer hover:text-slate-200" onClick={() => handleSortToggle('symbol')}>
            <span className="w-5 text-center">⭐</span>
            <span>{t('coin_th_contract')}</span>
            {sortField === 'symbol' && (sortOrder === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </div>

          <div className="col-span-3 sm:col-span-3 text-right flex items-center justify-end gap-1 cursor-pointer hover:text-slate-200" onClick={() => handleSortToggle('price')}>
            <span>{t('coin_th_last_price')}</span>
            {sortField === 'price' && (sortOrder === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </div>

          <div className="col-span-4 sm:col-span-3 text-right flex items-center justify-end gap-1 cursor-pointer hover:text-slate-200" onClick={() => handleSortToggle('change')}>
            <span>{t('coin_th_24h_change')}</span>
            {sortField === 'change' && (sortOrder === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </div>

          <div className="hidden sm:col-span-2 sm:flex items-center justify-end gap-1 cursor-pointer hover:text-slate-200" onClick={() => handleSortToggle('score')}>
            <span>{t('coin_th_metrics')}</span>
            {sortField === 'score' && (sortOrder === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
          </div>
        </div>

        {/* 3. Coin List Body */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60 max-h-[55vh]">
          {filteredCoins.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-xs sm:text-sm">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-40 text-slate-400" />
              {t('coin_empty_search')}
            </div>
          ) : (
            filteredCoins.map((coin) => {
              const isSelected = coin.symbol === currentSymbol;
              const probPct = coin.probability != null ? (coin.probability <= 1 ? coin.probability * 100 : coin.probability) : null;
              const isPositiveChange = coin.change24h != null ? coin.change24h >= 0 : (coin.change24hStr?.startsWith('+') ?? false);

              return (
                <div
                  key={coin.symbol}
                  onClick={() => {
                    onSelectCoin(coin.symbol);
                    onClose();
                  }}
                  className={`grid grid-cols-12 px-3 sm:px-4 py-2.5 items-center cursor-pointer transition select-none ${
                    isSelected
                      ? 'bg-amber-500/15 border-l-4 border-amber-500 text-amber-200'
                      : 'hover:bg-slate-800/80 text-slate-200'
                  }`}
                >
                  {/* Column 1: Star & Symbol */}
                  <div className="col-span-5 sm:col-span-4 flex items-center gap-2 min-w-0">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleWatchlist?.(coin.symbol);
                      }}
                      className="p-1 text-slate-500 hover:text-yellow-400 transition shrink-0"
                      title={coin.isFavorite ? 'Bỏ theo dõi' : 'Thêm vào yêu thích'}
                    >
                      <Star
                        className={`w-4 h-4 ${
                          coin.isFavorite
                            ? 'fill-yellow-400 text-yellow-400'
                            : 'text-slate-500 hover:text-yellow-300'
                        }`}
                      />
                    </button>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`font-mono font-bold text-xs sm:text-sm tracking-tight ${isSelected ? 'text-amber-400 font-black' : 'text-slate-100'}`}>
                          {coin.symbol}
                        </span>
                        <span className="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">
                          {t('coin_badge_perpetual')}
                        </span>
                        {coin.hasRadarSignal && (
                          <span className="text-[9px] px-1 py-0.2 rounded bg-red-950 text-red-400 border border-red-800 font-bold font-mono flex items-center gap-0.5">
                            <Radio className="w-2.5 h-2.5" />
                            {probPct ? `${probPct.toFixed(0)}%` : 'RADAR'}
                          </span>
                        )}
                      </div>
                      {coin.volume24hStr && coin.volume24hStr !== 'N/A' && (
                        <div className="text-[10px] text-slate-400 font-mono">
                          KL: {coin.volume24hStr}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Column 2: Last Price */}
                  <div className="col-span-3 sm:col-span-3 text-right">
                    <div className="font-mono text-xs sm:text-sm font-bold text-slate-100">
                      ${formatPrice(coin.price)}
                    </div>
                    {coin.fundingRate && coin.fundingRate !== 'N/A' && (
                      <div className="text-[10px] text-slate-400 font-mono">
                        FR: {coin.fundingRate}
                      </div>
                    )}
                  </div>

                  {/* Column 3: 24h Change */}
                  <div className="col-span-4 sm:col-span-3 text-right">
                    {coin.change24hStr || coin.change24h != null ? (
                      <span
                        className={`inline-block font-mono text-xs sm:text-sm font-bold px-2 py-0.5 rounded-md ${
                          isPositiveChange
                            ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/80'
                            : 'bg-rose-950/80 text-rose-400 border border-rose-800/80'
                        }`}
                      >
                        {coin.change24hStr || `${coin.change24h! > 0 ? '+' : ''}${coin.change24h!.toFixed(2)}%`}
                      </span>
                    ) : (
                      <span className="font-mono text-xs text-slate-500">—</span>
                    )}
                  </div>

                  {/* Column 4: Score / Risk Badge */}
                  <div className="hidden sm:col-span-2 sm:flex flex-col items-end">
                    {coin.probability != null ? (
                      <span className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded ${
                        coin.probability >= 0.7
                          ? 'bg-red-950 text-red-300 border border-red-800'
                          : coin.probability >= 0.5
                          ? 'bg-amber-950 text-amber-300 border border-amber-800'
                          : 'bg-slate-800 text-slate-300'
                      }`}>
                        {(coin.probability * 100).toFixed(0)}% {coin.riskLevel ? getRiskLabel(coin.riskLevel, language) : ''}
                      </span>
                    ) : coin.score != null ? (
                      <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-950/60 text-amber-300 border border-amber-800/60">
                        Score: {coin.score.toFixed(0)}
                      </span>
                    ) : (
                      <span className="text-[10px] font-mono text-slate-500">—</span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* 4. Footer Note */}
        <div className="px-4 py-2.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400 font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span>{filteredCoins.length} / {unifiedCoins.length} coins</span>
          </div>
          <div className="text-[11px] text-slate-400">
            Ấn <kbd className="px-1 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Esc</kbd> để đóng
          </div>
        </div>
      </div>
    </div>
  );
};
