import React, { useEffect, useState } from 'react';
import { X, Target, Check, Plus, Trash2, Zap, BarChart3, TrendingUp, TrendingDown, Star, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import type { WatchlistPreset } from '../types';
import { CoinLink } from './CoinLink';
import { useTranslation } from '../i18n/LanguageContext';

interface WatchlistFeedback {
  type: 'success' | 'error';
  message: string;
}

interface WatchlistModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeScanMode: string;
  activeScanModes: string[];
  setActiveScanModes: (modes: string[]) => Promise<boolean>;
  manualWatchlist: string[];
  onAddManualCoin: (symbol: string) => Promise<boolean>;
  onRemoveManualCoin: (symbol: string) => Promise<boolean>;
  presets: WatchlistPreset[];
  onSelectCoin?: (symbol: string) => void;
  pendingAction?: string | null;
  feedback?: WatchlistFeedback | null;
}

export const WatchlistModal: React.FC<WatchlistModalProps> = ({
  isOpen,
  onClose,
  activeScanMode,
  activeScanModes,
  setActiveScanModes,
  manualWatchlist,
  onAddManualCoin,
  onRemoveManualCoin,
  presets,
  onSelectCoin,
  pendingAction = null,
  feedback = null,
}) => {
  const { language } = useTranslation();
  const [newSymbolInput, setNewSymbolInput] = useState('');
  
  const scanModeLabelsVi: Record<string, string> = {
    volatile: 'Biến động',
    gainers: 'Tăng mạnh',
    losers: 'Giảm mạnh',
    volume: 'Khối lượng',
    all: 'Tất cả',
    manual: 'Cá nhân',
  };

  const scanModeLabelsEn: Record<string, string> = {
    volatile: 'Volatile',
    gainers: 'Top Gainers',
    losers: 'Top Losers',
    volume: 'Top Volume',
    all: 'All Pairs',
    manual: 'Custom Watchlist',
  };

  const scanModeLabels = language === 'en' ? scanModeLabelsEn : scanModeLabelsVi;

  useEffect(() => {
    if (!isOpen) return undefined;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pendingAction) onClose();
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose, pendingAction]);

  if (!isOpen) return null;

  const isEn = language === 'en';

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    const rawSymbol = newSymbolInput.trim().toUpperCase();
    if (!rawSymbol || pendingAction) return;

    const symbol = rawSymbol.endsWith('USDT') ? rawSymbol : `${rawSymbol}USDT`;
    const added = await onAddManualCoin(symbol);
    if (added) setNewSymbolInput('');
  };

  const getPresetIcon = (id: string) => {
    switch (id) {
      case 'volatile': return <Zap className="h-4 w-4 text-amber-400" />;
      case 'volume':
      case 'volume_100': return <BarChart3 className="h-4 w-4 text-sky-400" />;
      case 'gainers': return <TrendingUp className="h-4 w-4 text-emerald-400" />;
      case 'losers': return <TrendingDown className="h-4 w-4 text-red-400" />;
      default: return <Star className="h-4 w-4 text-yellow-400" />;
    }
  };

  const togglePreset = (presetId: string) => {
    const isSelected = activeScanModes.includes(presetId);
    if (isSelected && activeScanModes.length === 1) return;

    const nextModes = isSelected
      ? activeScanModes.filter((mode) => mode !== presetId)
      : [...activeScanModes, presetId];
    void setActiveScanModes(nextModes);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/80 p-0 backdrop-blur-sm sm:items-center sm:p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pendingAction) onClose();
      }}
    >
      <section
        className="flex h-[min(92dvh,48rem)] w-full flex-col overflow-hidden rounded-t-2xl border border-slate-800 bg-slate-900 shadow-2xl sm:h-auto sm:max-h-[90vh] sm:max-w-2xl sm:rounded-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="watchlist-modal-title"
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 bg-slate-950 px-4 py-3 sm:px-5 sm:py-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400">
              <Target className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h2 id="watchlist-modal-title" className="truncate text-sm font-bold text-slate-100 sm:text-base">
                {isEn ? 'Select Coins for AI Scanner' : 'Chọn danh sách coin để AI quét'}
              </h2>
              <p className="mt-0.5 text-[11px] text-slate-500">
                {isEn ? '24/7 Scanner · Changes apply in the next cycle' : 'Bộ quét 24/7 · thay đổi sẽ áp dụng ở chu kỳ kế tiếp'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={Boolean(pendingAction)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-400 transition hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            aria-label={isEn ? 'Close Watchlist Modal' : 'Đóng danh sách theo dõi'}
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-4 sm:px-5 sm:py-5">
          {feedback && (
            <div
              role={feedback.type === 'error' ? 'alert' : 'status'}
              className={`mb-4 flex items-start gap-2 rounded-xl border px-3 py-2.5 text-xs ${
                feedback.type === 'success'
                  ? 'border-emerald-500/30 bg-emerald-950/50 text-emerald-200'
                  : 'border-red-500/30 bg-red-950/50 text-red-200'
              }`}
            >
              {feedback.type === 'success' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
              <span>{feedback.message}</span>
            </div>
          )}

          <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
            {isEn ? 'Automated Scan Modes' : 'Chế độ quét tự động'}
          </div>

          <p className="mb-3 text-[11px] leading-relaxed text-slate-400">
            {isEn 
              ? 'Select one or more scan pools. Overlapping coins are merged and scanned only once per cycle.'
              : 'Chọn một hoặc nhiều nhóm. Coin trùng giữa các nhóm sẽ được gộp lại và chỉ quét một lần.'}
          </p>

          <div className="space-y-2">
            {presets.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/50 px-3 py-4 text-center text-xs text-slate-500">
                {isEn ? 'Could not load presets. You can still manage your custom watchlist below.' : 'Chưa tải được các chế độ quét. Bạn vẫn có thể quản lý danh sách cá nhân bên dưới.'}
              </div>
            ) : presets.map((preset) => {
              const isSelected = activeScanModes.includes(preset.id);
              const isPending = pendingAction === 'modes' && isSelected;
              return (
                <button
                  key={preset.id}
                  type="button"
                  disabled={Boolean(pendingAction)}
                  onClick={() => togglePreset(preset.id)}
                  className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition sm:p-3.5 ${
                    isSelected
                      ? 'border-amber-500/80 bg-slate-800/90 shadow-md shadow-amber-500/10'
                      : 'border-slate-800 bg-slate-950/70 hover:border-slate-700 hover:bg-slate-900'
                  } ${pendingAction && !isPending ? 'cursor-not-allowed opacity-60' : ''}`}
                  aria-pressed={isSelected}
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-800 bg-slate-900">
                    {getPresetIcon(preset.id)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5 text-xs font-bold text-slate-100">
                      <span>{preset.name}</span>
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] font-mono ${preset.id === 'manual' ? 'border-yellow-800 bg-yellow-950 text-yellow-400' : 'border-slate-700 bg-slate-800 text-slate-400'}`}>
                        {preset.id === 'manual' ? `${manualWatchlist.length} coins` : `${preset.count} coins`}
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] leading-relaxed text-slate-400">{preset.description}</div>
                  </div>
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center">
                    {isPending ? <Loader2 className="h-4 w-4 animate-spin text-amber-400" /> : isSelected ? (
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500 text-slate-950"><Check className="h-3.5 w-3.5" /></span>
                    ) : <span className="h-5 w-5 rounded-full border border-slate-700" />}
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-6 border-t border-slate-800 pt-4">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-bold text-slate-300">
              <Star className="h-4 w-4 text-yellow-400" />
              {isEn ? 'Custom Watchlist' : 'Danh sách theo dõi cá nhân'}
              <span className="ml-auto font-mono text-[11px] text-amber-400">{manualWatchlist.length} coins</span>
            </div>

            <form onSubmit={handleAdd} className="mb-3 flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                inputMode="text"
                enterKeyHint="done"
                autoCapitalize="characters"
                autoComplete="off"
                placeholder={isEn ? 'Enter ticker, e.g. SUI or INJ' : 'Nhập ticker, ví dụ SUI hoặc INJ'}
                value={newSymbolInput}
                onChange={(event) => setNewSymbolInput(event.target.value)}
                disabled={Boolean(pendingAction)}
                className="h-11 min-w-0 flex-1 rounded-xl border border-slate-800 bg-slate-950 px-3 text-sm font-mono uppercase text-slate-200 placeholder:font-sans placeholder:normal-case placeholder:text-slate-600 focus:border-amber-500 focus:outline-none disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={!newSymbolInput.trim() || Boolean(pendingAction)}
                className="inline-flex h-11 shrink-0 items-center justify-center gap-1.5 rounded-xl bg-amber-500 px-4 text-xs font-bold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50 sm:px-3"
              >
                {pendingAction?.startsWith('add:') ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                {isEn ? 'Add Coin' : 'Thêm coin'}
              </button>
            </form>

            {manualWatchlist.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-800 px-3 py-4 text-center text-xs italic text-slate-500">
                {isEn ? 'No coins added yet. Add tickers to prioritize scanning.' : 'Chưa có coin nào. Thêm coin để bộ quét luôn ưu tiên theo dõi chúng.'}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {manualWatchlist.map((symbol) => {
                  const isRemoving = pendingAction === `remove:${symbol}`;
                  return (
                    <div key={symbol} className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2">
                      {onSelectCoin ? (
                        <CoinLink symbol={symbol} onClick={(selectedSymbol) => { onSelectCoin(selectedSymbol); onClose(); }} />
                      ) : <span className="truncate font-mono text-xs text-slate-200">{symbol}</span>}
                      <button
                        type="button"
                        onClick={() => void onRemoveManualCoin(symbol)}
                        disabled={Boolean(pendingAction)}
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-red-950/60 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-50"
                        title={isEn ? 'Remove coin from custom watchlist' : 'Xóa coin khỏi danh sách theo dõi'}
                        aria-label={`Remove ${symbol}`}
                      >
                        {isRemoving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <footer className="flex shrink-0 flex-col gap-2 border-t border-slate-800 bg-slate-950 px-4 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <span className="text-[11px] text-slate-400">
            {isEn ? 'Active Selection: ' : 'Đang chọn: '}
            <strong className="font-mono text-amber-400">
              {activeScanMode.split(' + ').map((mode) => scanModeLabels[mode] || mode).join(' + ')}
            </strong>
          </span>
          <button
            type="button"
            onClick={onClose}
            disabled={Boolean(pendingAction)}
            className="h-11 rounded-xl bg-amber-500 px-4 text-xs font-bold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50 sm:h-9"
          >
            {isEn ? 'Done' : 'Xong'}
          </button>
        </footer>
      </section>
    </div>
  );
};
