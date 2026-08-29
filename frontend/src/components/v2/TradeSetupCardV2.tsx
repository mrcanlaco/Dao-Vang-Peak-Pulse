import React, { useState } from 'react';
import { Target, ShieldAlert, TrendingDown, Zap, ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';

import type { SignalTradeSetup } from '../../types';

interface TradeSetupCardV2Props {
  symbol?: string;
  currentPrice: number;
  signalPrice?: number | null;
  targetPrice?: number | null;
  peakPrice?: number | null;
  invalidationPrice?: number | null;
  tradeSetup?: SignalTradeSetup | null;
  onOpenOrderModal?: () => void;
}

export const TradeSetupCardV2: React.FC<TradeSetupCardV2Props> = ({
  symbol: _symbol,
  currentPrice,
  signalPrice,
  targetPrice,
  peakPrice,
  invalidationPrice,
  tradeSetup,
  onOpenOrderModal,
}) => {
  const { t } = useTranslation();
  const [marginUsd, setMarginUsd] = useState<number>(100);
  const [leverage, setLeverage] = useState<number>(5);
  const [isExpanded, setIsExpanded] = useState(false);

  const entry = tradeSetup?.entry_price || (signalPrice && signalPrice > 0 ? signalPrice : currentPrice);
  if (!entry || entry <= 0) return null;

  // Stop Loss calculation (from tradeSetup or Invalidation level or peak price + buffer)
  const sl = tradeSetup?.stop_loss
    || (invalidationPrice && invalidationPrice > entry
      ? invalidationPrice
      : peakPrice && peakPrice > entry
      ? peakPrice * 1.008
      : entry * 1.032);

  const tp1 = tradeSetup?.tp1 || (entry * 0.96); // -4%
  const tp2 = tradeSetup?.tp2 || (targetPrice && targetPrice > 0 && targetPrice < entry ? targetPrice : entry * 0.92); // -8%
  const tp3 = tradeSetup?.tp3 || (entry * 0.86); // -14% (Trailing / Deep Dump)

  const slPct = tradeSetup?.stop_loss_pct || Math.max(0.1, ((sl - entry) / entry) * 100);
  const tp1Pct = tradeSetup?.tp1_pct || (((entry - tp1) / entry) * 100);
  const tp2Pct = tradeSetup?.tp2_pct || (((entry - tp2) / entry) * 100);
  const tp3Pct = tradeSetup?.tp3_pct || (((entry - tp3) / entry) * 100);
  const rrRatio = tradeSetup?.rr_ratio || (slPct > 0 ? Number((tp2Pct / slPct).toFixed(1)) : 2.5);
  const totalPos = marginUsd * leverage;
  const maxLoss = totalPos * (slPct / 100);
  const maxProfitTp2 = totalPos * (tp2Pct / 100);
  const maxProfitTp3 = totalPos * (tp3Pct / 100);

  const formatPrice = (p: number) => {
    if (p < 0.001) return p.toFixed(6);
    if (p < 1) return p.toFixed(5);
    if (p < 10) return p.toFixed(4);
    return p.toFixed(2);
  };

  return (
    <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 sm:p-3.5 shadow-lg space-y-3">
      {/* Header */}
      <button
        type="button"
        onClick={() => setIsExpanded((expanded) => !expanded)}
        aria-expanded={isExpanded}
        className="w-full flex items-center justify-between pb-2 border-b border-slate-800/80 text-left"
      >
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400">
            <Target className="w-3.5 h-3.5" />
          </div>
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            {t('trade_setup_plan_title')}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400 font-mono">
            {t('trade_rr_ratio')}
          </span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${
            rrRatio >= 2.0
              ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
              : rrRatio >= 1.5
              ? 'bg-amber-950 text-amber-300 border-amber-800'
              : 'bg-red-950 text-red-300 border-red-800'
          }`}>
            1 : {rrRatio.toFixed(1)}
          </span>
          {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </div>
      </button>

      {isExpanded && <>
        {/* Levels Grid (Entry, SL, TP1, TP2, TP3) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {/* Invalidation / Stop Loss Level (Adaptive) */}
        <div className="bg-slate-900/90 border border-red-500/30 rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[10px] text-red-400 font-semibold mb-1">
            <span className="flex items-center gap-1">
              <ShieldAlert className="w-3 h-3 text-red-400" />
              <span>{t('trade_stop_loss')} (Adaptive)</span>
            </span>
            <span className="font-mono text-[9px] text-red-400 font-bold">+{slPct.toFixed(1)}%</span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-red-400">
            ${formatPrice(sl)}
          </div>
          <div className="text-[9px] text-slate-400 mt-1 font-mono">
            Đỉnh râu nến 5m + buffer
          </div>
        </div>

        {/* Take Profit 1 (-4% - Chốt 50% + SL Hòa vốn) */}
        <div className="bg-slate-900/90 border border-emerald-500/30 rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[10px] text-emerald-400 font-semibold mb-1">
            <span className="flex items-center gap-1">
              <TrendingDown className="w-3 h-3 text-emerald-400" />
              <span>TP1 (50% Vol)</span>
            </span>
            <span className="font-mono text-[9px] text-emerald-400 font-bold">-{tp1Pct.toFixed(1)}%</span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-emerald-300">
            ${formatPrice(tp1)}
          </div>
          <div className="text-[9px] text-emerald-400/80 mt-1 font-mono font-semibold">
            Dời SL về Entry hòa vốn
          </div>
        </div>

        {/* Take Profit 2 (-8% - Chốt 30%) */}
        <div className="bg-slate-900/90 border border-emerald-600/50 rounded-lg p-2.5 flex flex-col justify-between shadow-inner">
          <div className="flex items-center justify-between text-[10px] text-emerald-300 font-bold mb-1">
            <span className="flex items-center gap-1">
              <Target className="w-3 h-3 text-emerald-400" />
              <span>TP2 (30% Vol)</span>
            </span>
            <span className="font-mono text-[9px] text-emerald-300 font-black">-{tp2Pct.toFixed(1)}%</span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-emerald-400">
            ${formatPrice(tp2)}
          </div>
          <div className="text-[9px] text-slate-400 mt-1 font-mono">
            {t('trade_ai_target_8')}
          </div>
        </div>

        {/* Take Profit 3 (-14% - Trailing 20%) */}
        <div className="bg-gradient-to-br from-violet-950/40 to-slate-900/90 border border-violet-500/40 rounded-lg p-2.5 flex flex-col justify-between shadow-inner">
          <div className="flex items-center justify-between text-[10px] text-violet-300 font-bold mb-1">
            <span className="flex items-center gap-1">
              <Zap className="w-3 h-3 text-amber-400" />
              <span>TP3 (20% Vol)</span>
            </span>
            <span className="font-mono text-[9px] text-violet-300 font-black">-{tp3Pct.toFixed(1)}%</span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-violet-300">
            ${formatPrice(tp3)}
          </div>
          <div className="text-[9px] text-violet-400 mt-1 font-mono">
            Trailing gồng xả lũ
          </div>
        </div>
        </div>

        {/* Quick Interactive Sizing Summary & Button */}
        <div className="bg-slate-900/80 rounded-xl p-2.5 border border-slate-800 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-3 text-xs font-mono">
          <div className="flex items-center gap-1.5 text-slate-300">
            <span className="text-slate-400">Margin:</span>
            <button
              onClick={() => setMarginUsd(m => m === 50 ? 100 : m === 100 ? 250 : 50)}
              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 font-bold border border-slate-700"
            >
              ${marginUsd}
            </button>
          </div>
          <div className="flex items-center gap-1.5 text-slate-300">
            <span className="text-slate-400">Lev:</span>
            <button
              onClick={() => setLeverage(l => l === 3 ? 5 : l === 5 ? 10 : 3)}
              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-sky-300 font-bold border border-slate-700"
            >
              {leverage}x
            </button>
          </div>
          <div className="hidden sm:flex items-center gap-2 text-[11px]">
            <span className="text-red-400">SL: -${maxLoss.toFixed(1)}</span>
            <span className="text-emerald-400">TP2: +${maxProfitTp2.toFixed(1)}</span>
            <span className="text-violet-400">TP3: +${maxProfitTp3.toFixed(1)}</span>
          </div>
        </div>

        {onOpenOrderModal && (
          <button
            onClick={onOpenOrderModal}
            className="px-3.5 py-1.5 bg-gradient-to-r from-red-600 to-amber-500 hover:from-red-500 hover:to-amber-400 text-slate-950 font-black rounded-lg text-xs flex items-center justify-center gap-1.5 shadow-md shadow-red-600/20 active:scale-95 transition"
          >
            <Zap className="w-3.5 h-3.5 stroke-[2.5]" />
            <span>{t('sticky_action_short')} (Binance / OKX)</span>
          </button>
        )}
        </div>
      </>}
    </div>
  );
};
