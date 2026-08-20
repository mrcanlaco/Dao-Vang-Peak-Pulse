import React from 'react';
import { Target, Eye, CheckCircle2, Send, Loader2 } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';

interface StickyActionBarProps {
  symbol: string;
  currentPrice: number;
  probability?: number | null;
  riskLevel?: string | null;
  onOpenOrderModal: () => void;
  onTrackPosition?: (symbol: string) => void | Promise<void | boolean>;
  isSymbolTracked?: boolean;
  isTrackingLoading?: boolean;
  onPushTelegram?: () => void;
}

export const StickyActionBar: React.FC<StickyActionBarProps> = ({
  symbol,
  currentPrice,
  probability,
  riskLevel: _riskLevel,
  onOpenOrderModal,
  onTrackPosition,
  isSymbolTracked = false,
  isTrackingLoading = false,
  onPushTelegram,
}) => {
  const { t } = useTranslation();

  const formatPrice = (p: number) => {
    if (p < 0.001) return p.toFixed(6);
    if (p < 1) return p.toFixed(5);
    if (p < 10) return p.toFixed(4);
    return p.toFixed(2);
  };

  const probValue = probability != null ? (probability <= 1 ? probability * 100 : probability) : null;

  return (
    <div className="fixed bottom-[52px] left-0 right-0 z-30 sm:hidden bg-slate-950/95 backdrop-blur-md border-t border-slate-800/90 px-3 py-2 shadow-2xl">
      <div className="flex items-center justify-between gap-2 max-w-lg mx-auto">
        {/* Coin Info Left */}
        <div className="flex flex-col min-w-0 pr-1">
          <div className="flex items-center gap-1.5">
            <span className="font-black text-amber-400 font-mono text-sm truncate">
              {symbol}
            </span>
            {probValue !== null && (
              <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold font-mono border ${
                probValue >= 70
                  ? 'bg-red-950/90 text-red-300 border-red-800'
                  : probValue >= 50
                  ? 'bg-amber-950/90 text-amber-300 border-amber-800'
                  : 'bg-slate-800 text-slate-300 border-slate-700'
              }`}>
                {probValue.toFixed(0)}%
              </span>
            )}
          </div>
          <span className="text-xs font-mono font-bold text-slate-100">
            ${formatPrice(currentPrice)}
          </span>
        </div>

        {/* Action Buttons Right */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Quick Track Button */}
          {onTrackPosition && (
            <button
              onClick={() => void onTrackPosition(symbol)}
              disabled={isTrackingLoading || isSymbolTracked}
              className={`p-2 rounded-xl border text-xs font-bold transition flex items-center justify-center ${
                isSymbolTracked
                  ? 'bg-sky-500/20 text-sky-300 border-sky-500/50'
                  : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-700 active:scale-95'
              }`}
              title={isSymbolTracked ? t('order_tracked_success') : t('sticky_action_track')}
            >
              {isTrackingLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : isSymbolTracked ? (
                <CheckCircle2 className="w-4 h-4 text-sky-400" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          )}

          {/* Quick Telegram Button */}
          {onPushTelegram && (
            <button
              onClick={onPushTelegram}
              className="p-2 rounded-xl bg-slate-900 hover:bg-sky-950 border border-slate-700 hover:border-sky-700 text-sky-400 active:scale-95 transition flex items-center justify-center"
              title={t('sticky_action_telegram')}
            >
              <Send className="w-4 h-4" />
            </button>
          )}

          {/* Primary Short Setup Button */}
          <button
            onClick={onOpenOrderModal}
            className="px-3.5 py-2 rounded-xl bg-gradient-to-r from-red-600 via-red-500 to-amber-500 hover:from-red-500 hover:to-amber-400 text-slate-950 font-black text-xs flex items-center gap-1.5 shadow-lg shadow-red-600/30 active:scale-95 transition"
          >
            <Target className="w-4 h-4 stroke-[2.5]" />
            <span>{t('sticky_action_short')}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
