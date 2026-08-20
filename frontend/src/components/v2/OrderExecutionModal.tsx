import React, { useState } from 'react';
import {
  X, Target, ExternalLink,
  Copy, Check, Eye, CheckCircle2, Loader2, DollarSign
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';

interface OrderExecutionModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  currentPrice: number;
  signalPrice?: number | null;
  targetPrice?: number | null;
  peakPrice?: number | null;
  invalidationPrice?: number | null;
  probability?: number | null;
  riskLevel?: string | null;
  onTrackPosition?: (symbol: string) => void | Promise<void | boolean>;
  isSymbolTracked?: boolean;
  isTrackingLoading?: boolean;
}

export const OrderExecutionModal: React.FC<OrderExecutionModalProps> = ({
  isOpen,
  onClose,
  symbol,
  currentPrice,
  signalPrice,
  targetPrice,
  peakPrice,
  invalidationPrice,
  probability,
  riskLevel: _riskLevel,
  onTrackPosition,
  isSymbolTracked = false,
  isTrackingLoading = false,
}) => {
  const { t } = useTranslation();

  // Position Sizing State
  const [marginUsd, setMarginUsd] = useState<number>(100);
  const [leverage, setLeverage] = useState<number>(5);
  const [copiedCommand, setCopiedCommand] = useState<boolean>(false);

  if (!isOpen) return null;

  const entry = signalPrice && signalPrice > 0 ? signalPrice : currentPrice;
  const sl = invalidationPrice && invalidationPrice > entry
    ? invalidationPrice
    : peakPrice && peakPrice > entry
    ? peakPrice * 1.015
    : entry * 1.04;

  const tp1 = entry * 0.96; // -4%
  const tp2 = targetPrice && targetPrice > 0 && targetPrice < entry ? targetPrice : entry * 0.92; // -8%

  const slPct = entry > 0 ? ((sl - entry) / entry) * 100 : 4.0;
  const tp1Pct = entry > 0 ? ((entry - tp1) / entry) * 100 : 4.0;
  const tp2Pct = entry > 0 ? ((entry - tp2) / entry) * 100 : 8.0;
  const rrRatio = slPct > 0 ? (tp2Pct / slPct) : 2.0;

  const totalPositionSize = marginUsd * leverage;
  const maxLossUsd = totalPositionSize * (slPct / 100);
  const estProfitTp1Usd = totalPositionSize * (tp1Pct / 100);
  const estProfitTp2Usd = totalPositionSize * (tp2Pct / 100);

  const formatPrice = (p: number) => {
    if (p < 0.001) return p.toFixed(6);
    if (p < 1) return p.toFixed(5);
    if (p < 10) return p.toFixed(4);
    return p.toFixed(2);
  };

  const probValue = probability != null ? (probability <= 1 ? probability * 100 : probability) : null;

  // External Links for Binance & OKX Futures
  const binanceFuturesUrl = `https://www.binance.com/en/futures/${symbol}`;
  const okxSymbol = symbol.endsWith('USDT')
    ? `${symbol.replace('USDT', '')}-USDT-SWAP`.toLowerCase()
    : `${symbol}-SWAP`.toLowerCase();
  const okxFuturesUrl = `https://www.okx.com/trade-swap/${okxSymbol}`;

  // Copy Standardized Trade Command
  const handleCopyCommand = () => {
    const text = [
      `🔻 [ĐẢO VÀNG AI] SHORT SETUP: ${symbol}`,
      `💵 Entry Zone: $${formatPrice(entry)}`,
      `🛑 Stop Loss: $${formatPrice(sl)} (+${slPct.toFixed(1)}%)`,
      `🎯 Target 1: $${formatPrice(tp1)} (-${tp1Pct.toFixed(1)}%)`,
      `🎯 Target 2: $${formatPrice(tp2)} (-${tp2Pct.toFixed(1)}%)`,
      `⚖️ R:R: 1 : ${rrRatio.toFixed(1)} | Rec. Leverage: ${leverage}x`,
      probValue !== null ? `📊 AI Dump Probability: ${probValue.toFixed(1)}%` : '',
    ].filter(Boolean).join('\n');

    navigator.clipboard.writeText(text);
    setCopiedCommand(true);
    setTimeout(() => setCopiedCommand(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-slate-950/85 backdrop-blur-sm p-0 sm:p-4 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-800 rounded-t-2xl sm:rounded-2xl w-full max-w-lg max-h-[92vh] flex flex-col overflow-hidden shadow-2xl">
        
        {/* Header */}
        <div className="p-3.5 sm:p-4 bg-slate-950/90 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-red-600 to-amber-600 flex items-center justify-center text-slate-950 font-black shadow-md">
              <Target className="w-5 h-5 stroke-[2.5]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-black font-mono text-slate-100 tracking-tight">
                  {symbol}
                </h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-black bg-red-950 text-red-400 border border-red-800 uppercase">
                  SHORT SETUP
                </span>
                {probValue !== null && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-950 text-amber-300 border border-amber-800">
                    {probValue.toFixed(0)}% PROB
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 font-mono">
                ${formatPrice(currentPrice)} • {t('order_modal_title')}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-xl bg-slate-800 hover:bg-red-950 text-slate-400 hover:text-red-400 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-3.5 sm:p-4 overflow-y-auto space-y-4 text-xs font-sans">
          
          {/* 4 Levels Summary Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {/* Entry */}
            <div className="bg-slate-950/80 border border-amber-500/30 rounded-xl p-2.5">
              <span className="text-[10px] font-semibold text-amber-400 block mb-0.5">
                {t('trade_entry_zone')}
              </span>
              <span className="text-sm font-black font-mono text-slate-100 block">
                ${formatPrice(entry)}
              </span>
              <span className="text-[9px] text-slate-400 font-mono">
                {t('trade_signal_current')}
              </span>
            </div>

            {/* Stop Loss */}
            <div className="bg-slate-950/80 border border-red-500/30 rounded-xl p-2.5">
              <div className="flex items-center justify-between text-[10px] font-semibold text-red-400 mb-0.5">
                <span>{t('trade_stop_loss')}</span>
                <span className="font-mono text-[9px]">+{slPct.toFixed(1)}%</span>
              </div>
              <span className="text-sm font-black font-mono text-red-400 block">
                ${formatPrice(sl)}
              </span>
              <span className="text-[9px] text-slate-400 font-mono">
                {t('trade_invalidation_level')}
              </span>
            </div>

            {/* Target 1 */}
            <div className="bg-slate-950/80 border border-emerald-500/30 rounded-xl p-2.5">
              <div className="flex items-center justify-between text-[10px] font-semibold text-emerald-400 mb-0.5">
                <span>{t('trade_target_1')}</span>
                <span className="font-mono text-[9px]">-{tp1Pct.toFixed(1)}%</span>
              </div>
              <span className="text-sm font-black font-mono text-emerald-300 block">
                ${formatPrice(tp1)}
              </span>
              <span className="text-[9px] text-slate-400 font-mono">
                {t('trade_quick_drawdown_4')}
              </span>
            </div>

            {/* Target 2 */}
            <div className="bg-slate-950/80 border border-emerald-600/50 rounded-xl p-2.5">
              <div className="flex items-center justify-between text-[10px] font-semibold text-emerald-300 mb-0.5">
                <span>{t('trade_target_2')}</span>
                <span className="font-mono text-[9px] font-bold">-{tp2Pct.toFixed(1)}%</span>
              </div>
              <span className="text-sm font-black font-mono text-emerald-400 block">
                ${formatPrice(tp2)}
              </span>
              <span className="text-[9px] text-slate-400 font-mono">
                {t('trade_ai_target_8')}
              </span>
            </div>
          </div>

          {/* Position Sizing & Leverage Calculator */}
          <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 sm:p-3.5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5" />
                {t('quick_calc_title')}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                R:R 1 : {rrRatio.toFixed(1)}
              </span>
            </div>

            {/* Margin Inputs */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-slate-300 mb-1.5">
                <label className="font-medium">{t('order_margin_usd')}</label>
                <span className="font-mono font-bold text-amber-400">${marginUsd} USD</span>
              </div>
              <div className="grid grid-cols-5 gap-1.5 mb-2">
                {[25, 50, 100, 250, 500].map((val) => (
                  <button
                    key={val}
                    onClick={() => setMarginUsd(val)}
                    className={`py-1 rounded-lg text-xs font-mono font-bold border transition ${
                      marginUsd === val
                        ? 'bg-amber-500 text-slate-950 border-amber-400'
                        : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800'
                    }`}
                  >
                    ${val}
                  </button>
                ))}
              </div>
              <input
                type="number"
                min={5}
                max={50000}
                value={marginUsd}
                onChange={(e) => setMarginUsd(Math.max(1, Number(e.target.value) || 0))}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 font-mono text-slate-100 text-xs focus:outline-none focus:border-amber-500"
                placeholder="Nhập số vốn custom..."
              />
            </div>

            {/* Leverage Selector */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-slate-300 mb-1.5">
                <label className="font-medium">{t('order_leverage')}</label>
                <span className="font-mono font-bold text-sky-400">{leverage}x (Cross / Isolated)</span>
              </div>
              <div className="grid grid-cols-5 gap-1.5">
                {[1, 2, 3, 5, 10].map((lev) => (
                  <button
                    key={lev}
                    onClick={() => setLeverage(lev)}
                    className={`py-1 rounded-lg text-xs font-mono font-bold border transition ${
                      leverage === lev
                        ? 'bg-sky-500 text-slate-950 border-sky-400'
                        : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800'
                    }`}
                  >
                    {lev}x
                  </button>
                ))}
              </div>
            </div>

            {/* Calculated Results Table */}
            <div className="bg-slate-900/90 rounded-lg p-2.5 border border-slate-800 space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between text-slate-300">
                <span>{t('order_total_position')}:</span>
                <span className="font-bold text-slate-100">${totalPositionSize.toLocaleString()} USD</span>
              </div>
              <div className="flex justify-between text-red-400">
                <span>{t('order_max_loss')}:</span>
                <span className="font-bold">-${maxLossUsd.toFixed(2)} USD (-{(slPct * leverage).toFixed(1)}%)</span>
              </div>
              <div className="flex justify-between text-emerald-400">
                <span>{t('order_est_profit_tp1')}:</span>
                <span className="font-bold">+${estProfitTp1Usd.toFixed(2)} USD (+{(tp1Pct * leverage).toFixed(1)}%)</span>
              </div>
              <div className="flex justify-between text-emerald-300">
                <span>{t('order_est_profit_tp2')}:</span>
                <span className="font-bold">+${estProfitTp2Usd.toFixed(2)} USD (+{(tp2Pct * leverage).toFixed(1)}%)</span>
              </div>
            </div>
          </div>

          {/* Action Row: Direct Exchange Links & Copy */}
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              {/* Binance Futures Link */}
              <a
                href={binanceFuturesUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="py-2.5 px-3 bg-gradient-to-r from-amber-500 to-yellow-500 hover:from-amber-400 hover:to-yellow-400 text-slate-950 font-bold rounded-xl text-xs flex items-center justify-center gap-1.5 shadow-md shadow-amber-500/20 active:scale-95 transition"
              >
                <ExternalLink className="w-3.5 h-3.5 stroke-[2.5]" />
                <span>{t('order_open_binance')}</span>
              </a>

              {/* OKX Futures Link */}
              <a
                href={okxFuturesUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="py-2.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-100 font-bold rounded-xl text-xs flex items-center justify-center gap-1.5 border border-slate-700 active:scale-95 transition"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>{t('order_open_okx')}</span>
              </a>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {/* Copy Command */}
              <button
                onClick={handleCopyCommand}
                className="py-2.5 px-3 bg-slate-950 hover:bg-slate-900 text-slate-300 hover:text-white font-bold rounded-xl text-xs flex items-center justify-center gap-1.5 border border-slate-800 active:scale-95 transition"
              >
                {copiedCommand ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedCommand ? t('order_command_copied') : t('order_copy_command')}</span>
              </button>

              {/* Auto Track Position */}
              {onTrackPosition && (
                <button
                  onClick={() => void onTrackPosition(symbol)}
                  disabled={isTrackingLoading || isSymbolTracked}
                  className={`py-2.5 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 border transition ${
                    isSymbolTracked
                      ? 'bg-sky-500/15 text-sky-300 border-sky-500/40'
                      : 'bg-sky-950/80 hover:bg-sky-900 text-sky-300 border-sky-800/80 active:scale-95'
                  }`}
                >
                  {isTrackingLoading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : isSymbolTracked ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-sky-400" />
                  ) : (
                    <Eye className="w-3.5 h-3.5" />
                  )}
                  <span>{isSymbolTracked ? t('order_tracked_success') : t('order_track_now')}</span>
                </button>
              )}
            </div>
          </div>

        </div>

      </div>
    </div>
  );
};
