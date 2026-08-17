import React from 'react';
import { Target, ShieldAlert, TrendingDown } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';

interface TradeSetupCardProps {
  currentPrice: number;
  signalPrice?: number | null;
  targetPrice?: number | null;
  peakPrice?: number | null;
  invalidationPrice?: number | null;
}

export const TradeSetupCard: React.FC<TradeSetupCardProps> = ({
  currentPrice,
  signalPrice,
  targetPrice,
  peakPrice,
  invalidationPrice,
}) => {
  const { language } = useTranslation();
  const isEn = language === 'en';
  
  const entry = signalPrice && signalPrice > 0 ? signalPrice : currentPrice;
  if (!entry || entry <= 0) return null;

  // Stop Loss calculation (Invalidation level or peak price + buffer or +4%)
  const sl = invalidationPrice && invalidationPrice > entry
    ? invalidationPrice
    : peakPrice && peakPrice > entry
    ? peakPrice * 1.015
    : entry * 1.04;

  const tp1 = entry * 0.96; // -4%
  const tp2 = targetPrice && targetPrice > 0 && targetPrice < entry ? targetPrice : entry * 0.92; // -8%

  const slPct = ((sl - entry) / entry) * 100;
  const tp1Pct = ((entry - tp1) / entry) * 100;
  const tp2Pct = ((entry - tp2) / entry) * 100;

  const rrRatio = slPct > 0 ? (tp2Pct / slPct) : 2.0;

  const formatPrice = (p: number) => {
    if (p < 0.001) return p.toFixed(6);
    if (p < 1) return p.toFixed(5);
    if (p < 10) return p.toFixed(4);
    return p.toFixed(2);
  };

  return (
    <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 sm:p-3.5 shadow-md">
      <div className="flex items-center justify-between mb-2.5 pb-2 border-b border-slate-800/80">
        <div className="flex items-center gap-1.5">
          <Target className="w-4 h-4 text-amber-400" />
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            {isEn ? 'SHORT TRADE SETUP (PLAN & R:R)' : 'KẾ HOẠCH VÀO LỆNH SHORT (R:R)'}
          </h3>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-400 font-mono">
            {isEn ? 'Risk:Reward' : 'Tỷ lệ Lời/Lỗ'}:
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
        </div>
      </div>

      {/* 4 Levels Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {/* Entry Level */}
        <div className="bg-slate-900/90 border border-amber-500/30 rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[10px] text-amber-300 font-semibold mb-1">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              {isEn ? 'ENTRY ZONE' : 'VÙNG VÀO LỆNH'}
            </span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-slate-100">
            ${formatPrice(entry)}
          </div>
          <div className="text-[9px] text-slate-400 mt-1 font-mono">
            {isEn ? 'Signal / Current' : 'Tín hiệu / Giá hiện tại'}
          </div>
        </div>

        {/* Invalidation / Stop Loss Level */}
        <div className="bg-slate-900/90 border border-red-500/30 rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[10px] text-red-400 font-semibold mb-1">
            <span className="flex items-center gap-1">
              <ShieldAlert className="w-3 h-3 text-red-400" />
              {isEn ? 'STOP LOSS (SL)' : 'CẮT LỖ (SL)'}
            </span>
            <span className="font-mono text-[9px] text-red-400">+{slPct.toFixed(1)}%</span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-red-400">
            ${formatPrice(sl)}
          </div>
          <div className="text-[9px] text-slate-400 mt-1 font-mono">
            {isEn ? 'Invalidation level' : 'Ngưỡng phá vỡ cấu trúc'}
          </div>
        </div>

        {/* Take Profit 1 (-4%) */}
        <div className="bg-slate-900/90 border border-emerald-500/30 rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[10px] text-emerald-400 font-semibold mb-1">
            <span className="flex items-center gap-1">
              <TrendingDown className="w-3 h-3 text-emerald-400" />
              {isEn ? 'TARGET 1 (TP1)' : 'CHỐT LỜI 1 (TP1)'}
            </span>
            <span className="font-mono text-[9px] text-emerald-400">-{tp1Pct.toFixed(1)}%</span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-emerald-300">
            ${formatPrice(tp1)}
          </div>
          <div className="text-[9px] text-slate-400 mt-1 font-mono">
            {isEn ? 'Quick drawdown' : 'Mục tiêu nhanh -4%'}
          </div>
        </div>

        {/* Take Profit 2 (-8%) */}
        <div className="bg-slate-900/90 border border-emerald-600/50 rounded-lg p-2.5 flex flex-col justify-between shadow-inner">
          <div className="flex items-center justify-between text-[10px] text-emerald-300 font-bold mb-1">
            <span className="flex items-center gap-1">
              <Target className="w-3 h-3 text-emerald-400" />
              {isEn ? 'TARGET 2 (TP2)' : 'CHỐT LỜI 2 (TP2)'}
            </span>
            <span className="font-mono text-[9px] text-emerald-300 font-black">-{tp2Pct.toFixed(1)}%</span>
          </div>
          <div className="text-sm sm:text-base font-black font-mono text-emerald-400">
            ${formatPrice(tp2)}
          </div>
          <div className="text-[9px] text-slate-400 mt-1 font-mono">
            {isEn ? 'AI Radar Target -8%' : 'Mục tiêu Radar -8%'}
          </div>
        </div>
      </div>
    </div>
  );
};
