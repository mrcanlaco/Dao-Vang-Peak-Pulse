import React, { useMemo, useState } from 'react';
import {
  Activity,
  Archive,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Eye,
  Loader2,
  Minus,
  Pencil,
  RefreshCw,
  Target,
  X,
} from 'lucide-react';
import type {
  TrackingStatus,
  TrackingWatchlistItem,
} from '../types';
import { formatSystemTime } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';

export type TrackingFilter = 'ACTIVE' | TrackingStatus;
export type UpdateTrackingPayload = Record<string, unknown>;

interface TrackingWatchlistProps {
  items: TrackingWatchlistItem[];
  isLoading: boolean;
  updatingId: string | null;
  onRefresh: () => void;
  onSelectCoin: (symbol: string) => void;
  onUpdateItem: (id: string, payload: UpdateTrackingPayload) => Promise<boolean>;
  onRemoveItem: (id: string) => Promise<boolean>;
}

interface PositionFormState {
  position_side: 'LONG' | 'SHORT';
  entry_price: string;
  quantity: string;
  notional: string;
  leverage: string;
  stop_loss: string;
  take_profit: string;
  notes: string;
}

const emptyForm: PositionFormState = {
  position_side: 'SHORT',
  entry_price: '',
  quantity: '',
  notional: '',
  leverage: '1',
  stop_loss: '',
  take_profit: '',
  notes: '',
};

const numberValue = (value: string): number | null => {
  const parsed = Number.parseFloat(value.trim());
  return Number.isFinite(parsed) ? parsed : null;
};

const formatPrice = (value: number | null | undefined): string => {
  if (value == null || !Number.isFinite(value)) return '—';
  if (Math.abs(value) >= 1) return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  return `$${value.toFixed(6)}`;
};

const formatPercent = (value: number | null | undefined, showSign = false): string => {
  if (value == null || !Number.isFinite(value)) return '—';
  const prefix = showSign && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
};

const formatMoney = (value: number | null | undefined): string => {
  if (value == null || !Number.isFinite(value)) return '—';
  const prefix = value > 0 ? '+$' : value < 0 ? '-$' : '$';
  return `${prefix}${Math.abs(value).toFixed(2)}`;
};

const toPositionForm = (item: TrackingWatchlistItem): PositionFormState => ({
  position_side: item.position_side || 'SHORT',
  entry_price: item.entry_price != null ? String(item.entry_price) : item.source_price != null ? String(item.source_price) : '',
  quantity: item.quantity != null ? String(item.quantity) : '',
  notional: item.notional != null ? String(item.notional) : '',
  leverage: item.leverage != null ? String(item.leverage) : '1',
  stop_loss: item.stop_loss != null ? String(item.stop_loss) : '',
  take_profit: item.take_profit != null ? String(item.take_profit) : item.source_target_price != null ? String(item.source_target_price) : '',
  notes: item.notes || '',
});

const riskClass = (risk?: string | null): string => {
  if (!risk) return 'border-slate-700 bg-slate-800 text-slate-400';
  if (risk === 'CRITICAL') return 'border-red-600 bg-red-950/70 text-red-300';
  if (risk === 'HIGH') return 'border-amber-600 bg-amber-950/70 text-amber-300';
  if (risk === 'MEDIUM') return 'border-yellow-600 bg-yellow-950/70 text-yellow-300';
  return 'border-emerald-600 bg-emerald-950/70 text-emerald-300';
};

export const TrackingWatchlist: React.FC<TrackingWatchlistProps> = ({
  items,
  isLoading,
  updatingId,
  onRefresh,
  onSelectCoin,
  onUpdateItem,
  onRemoveItem,
}) => {
  const { language, t } = useTranslation();

  const [filter, setFilter] = useState<TrackingFilter>('ACTIVE');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PositionFormState>(emptyForm);

  const getStatusLabel = (status: TrackingStatus, lang: Language): string => {
    const map: Record<TrackingStatus, Record<string, string>> = {
      WATCHING: { vi: 'ĐANG THEO DÕI', en: 'WATCHING', zh: '观察中', ko: '관찰 중' },
      IN_POSITION: { vi: 'ĐANG VÀO LỆNH', en: 'IN POSITION', zh: '持仓中', ko: '포지션 보유' },
      CLOSED: { vi: 'ĐÃ ĐÓNG', en: 'CLOSED', zh: '已结平', ko: '종료됨' },
    };
    return map[status]?.[lang] ?? map[status]?.['en'] ?? status;
  };

  const getSignalStatusLabel = (status: string, lang: Language): string => {
    const map: Record<string, Record<string, string>> = {
      ACTIVE: { vi: 'Radar còn hiệu lực', en: 'Radar Active', zh: '雷达有效', ko: '레이더 유효' },
      HIT: { vi: 'Radar đã trúng mục tiêu', en: 'Target Hit (-8%)', zh: '已达回撤目标(-8%)', ko: '목표 도달 (-8%)' },
      EXPIRED: { vi: 'Radar hết hạn', en: 'Radar Expired', zh: '雷达已过期', ko: '레이더 만료' },
      NO_SIGNAL: { vi: 'Theo dõi thủ công', en: 'Manual Track', zh: '手动跟踪', ko: '수동 추적' },
    };
    return map[status]?.[lang] ?? map[status]?.['en'] ?? status;
  };

  const stats = useMemo(() => ({
    total: items.filter(item => item.status !== 'CLOSED').length,
    activeSignals: items.filter(item => item.status !== 'CLOSED' && item.signal_status === 'ACTIVE').length,
    positions: items.filter(item => item.status === 'IN_POSITION').length,
    attention: items.filter(item => item.status !== 'CLOSED' && (item.signal_status === 'EXPIRED' || (item.position_change_pct != null && item.position_change_pct < 0))).length,
  }), [items]);

  const filteredItems = useMemo(() => items.filter(item => {
    if (filter === 'ACTIVE') return item.status !== 'CLOSED';
    return item.status === filter;
  }), [filter, items]);

  const openEditor = (item: TrackingWatchlistItem) => {
    setEditingId(item.id);
    setForm(toPositionForm(item));
  };

  const closeEditor = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const submitPosition = async (event: React.FormEvent, item: TrackingWatchlistItem) => {
    event.preventDefault();
    const entryPrice = numberValue(form.entry_price);
    if (entryPrice == null || !Number.isFinite(entryPrice) || entryPrice <= 0) return;
    const updated = await onUpdateItem(item.id, {
      status: 'IN_POSITION',
      position_side: form.position_side,
      entry_price: entryPrice,
      quantity: numberValue(form.quantity),
      notional: numberValue(form.notional),
      leverage: numberValue(form.leverage) ?? 1,
      stop_loss: numberValue(form.stop_loss),
      take_profit: numberValue(form.take_profit),
      notes: form.notes,
    });
    if (updated) closeEditor();
  };

  const closeTracking = async (item: TrackingWatchlistItem) => {
    await onUpdateItem(item.id, { status: 'CLOSED' });
  };

  const getFilterButtons = (lang: Language): Array<[TrackingFilter, string]> => [
    ['ACTIVE', lang === 'en' ? 'Active' : lang === 'zh' ? '当前有效' : lang === 'ko' ? '활성' : 'Đang hoạt động'],
    ['WATCHING', lang === 'en' ? 'Watching Only' : lang === 'zh' ? '仅观察' : lang === 'ko' ? '관찰만' : 'Chỉ theo dõi'],
    ['IN_POSITION', lang === 'en' ? 'In Position' : lang === 'zh' ? '持仓中' : lang === 'ko' ? '포지션 보유' : 'Đang vào lệnh'],
    ['CLOSED', lang === 'en' ? 'Closed' : lang === 'zh' ? '已结平' : lang === 'ko' ? '종료' : 'Đã đóng'],
  ];

  return (
    <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-100">
            <Target className="h-4 w-4 text-amber-400" />
            {t('track_title')}
          </h2>
          <p className="mt-1 text-[11px] text-slate-500">
            {t('track_subtitle')}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="inline-flex h-8 items-center justify-center gap-1.5 self-start rounded-lg border border-slate-700 bg-slate-900 px-3 text-[11px] font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-60 sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          {t('track_refresh_price')}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{t('track_stat_total')}</div>
          <div className="mt-1 text-xl font-black text-amber-300">{stats.total}</div>
        </div>
        <div className="rounded-xl border border-sky-800/60 bg-sky-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{t('track_stat_active')}</div>
          <div className="mt-1 text-xl font-black text-sky-300">{stats.activeSignals}</div>
        </div>
        <div className="rounded-xl border border-purple-800/60 bg-purple-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{t('track_stat_in_pos')}</div>
          <div className="mt-1 text-xl font-black text-purple-300">{stats.positions}</div>
        </div>
        <div className="rounded-xl border border-red-800/60 bg-red-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{t('track_stat_attention')}</div>
          <div className="mt-1 text-xl font-black text-red-300">{stats.attention}</div>
        </div>
      </div>

      <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 p-1 [&::-webkit-scrollbar]:hidden">
        {getFilterButtons(language).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-[10px] font-semibold transition ${filter === value ? 'bg-amber-500 text-slate-950' : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && items.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-10 text-center text-xs text-slate-500">
          <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-amber-400" />
          {t('track_empty_desc')}
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/60 p-10 text-center">
          <Eye className="mx-auto mb-2 h-6 w-6 text-slate-600" />
          <div className="text-xs font-semibold text-slate-400">
            {t('track_empty_title')}
          </div>
          <div className="mt-1 text-[11px] text-slate-600">
            {t('track_empty_desc')}
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredItems.map(item => {
            const isUpdating = updatingId === item.id;
            const progress = item.signal_progress_pct == null ? 0 : Math.min(100, Math.max(0, item.signal_progress_pct));
            const positiveSignalChange = (item.signal_change_pct ?? 0) >= 0;
            const pnlValue = item.position_pnl ?? item.position_change_pct ?? 0;
            const positivePnl = pnlValue >= 0;
            const PnlIcon = pnlValue > 0 ? ArrowUpRight : pnlValue < 0 ? ArrowDownRight : Minus;
            return (
              <article key={item.id} className="rounded-xl border border-slate-800 bg-slate-950/80 p-3 shadow-lg shadow-black/10">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                  <div className="min-w-0 lg:w-48">
                    <div className="flex items-center gap-2">
                      <button type="button" onClick={() => onSelectCoin(item.symbol)} className="font-mono text-sm font-black text-amber-300 hover:text-amber-200">
                        {item.symbol}
                      </button>
                      <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold ${item.status === 'IN_POSITION' ? 'border-purple-800 bg-purple-950/60 text-purple-300' : item.status === 'CLOSED' ? 'border-slate-700 bg-slate-900 text-slate-500' : 'border-amber-800 bg-amber-950/60 text-amber-300'}`}>
                        {getStatusLabel(item.status, language)}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
                      <span className={`rounded border px-1.5 py-0.5 ${riskClass(item.source_risk_level)}`}>{item.source_risk_level || '—'}</span>
                      <span>{getSignalStatusLabel(item.signal_status, language)}</span>
                    </div>
                  </div>

                  <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">Radar</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-red-300">
                        {item.source_probability == null ? '—' : `${(item.source_probability * 100).toFixed(1)}%`}
                      </div>
                      <div className="text-[10px] text-slate-500">{formatPrice(item.source_price)}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">{t('track_card_cur_price')}</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-slate-100">{formatPrice(item.current_price)}</div>
                      <div className={`text-[10px] ${positiveSignalChange ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatPercent(item.signal_change_pct, true)}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">{t('track_card_target_prog')}</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-amber-300">{formatPercent(item.signal_progress_pct)}</div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-amber-600 to-emerald-400" style={{ width: `${progress}%` }} /></div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">{t('track_card_pos_pnl')}</div>
                      {item.status === 'IN_POSITION' ? (
                        <>
                          <div className={`mt-0.5 flex items-center gap-1 font-mono text-xs font-bold ${positivePnl ? 'text-emerald-400' : 'text-red-400'}`}>
                            <PnlIcon className="h-3 w-3" />
                            {formatPercent(item.position_change_pct, true)}
                          </div>
                          <div className={`text-[10px] ${positivePnl ? 'text-emerald-500' : 'text-red-500'}`}>ROI {formatPercent(item.position_roi_pct, true)} · PnL {formatMoney(item.position_pnl)}</div>
                        </>
                      ) : <div className="mt-0.5 text-xs text-slate-500">{t('track_no_position')}</div>}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-1.5 lg:w-44 lg:justify-end">
                    {item.status !== 'CLOSED' && (
                      <button type="button" onClick={() => openEditor(item)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 text-[10px] font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-50">
                        {isUpdating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pencil className="h-3 w-3" />}
                        {item.status === 'IN_POSITION' ? t('track_btn_edit_pos') : t('track_btn_enter_pos')}
                      </button>
                    )}
                    {item.status === 'IN_POSITION' && (
                      <button type="button" onClick={() => void closeTracking(item)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-emerald-800/70 bg-emerald-950/40 px-2.5 text-[10px] font-semibold text-emerald-300 transition hover:bg-emerald-950 disabled:opacity-50">
                        <CheckCircle2 className="h-3 w-3" /> {t('track_btn_close_pos')}
                      </button>
                    )}
                    {item.status === 'CLOSED' && (
                      <button type="button" onClick={() => void onRemoveItem(item.id)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-red-900/70 bg-red-950/40 px-2.5 text-[10px] font-semibold text-red-300 transition hover:bg-red-950 disabled:opacity-50">
                        <Archive className="h-3 w-3" /> {t('track_btn_delete')}
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800/80 pt-2 text-[10px] text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <Clock3 className="h-3 w-3 text-sky-400" />
                    {item.validity_hours_left == null 
                      ? t('feed_no_matching')
                      : item.validity_hours_left > 0 
                        ? `${t('feed_left')} ${item.validity_hours_left.toFixed(1)}h` 
                        : t('feed_tag_expired')}
                  </span>
                  <span>{t('feed_target_drawdown')} {formatPrice(item.source_target_price)}</span>
                  {item.status === 'IN_POSITION' && <span>Entry {formatPrice(item.entry_price)} · {item.position_side}</span>}
                  {item.last_market_update && <span>{t('col_time')} {formatSystemTime(item.last_market_update)}</span>}
                </div>

                {editingId === item.id && (
                  <form onSubmit={(event) => void submitPosition(event, item)} className="mt-3 rounded-xl border border-amber-800/60 bg-amber-950/20 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="text-xs font-bold text-amber-300">
                        {t('track_form_title')}
                      </div>
                      <button type="button" onClick={closeEditor} className="text-slate-500 hover:text-slate-200"><X className="h-4 w-4" /></button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <label className="text-[10px] text-slate-400">{t('track_form_side')}<select value={form.position_side} onChange={event => setForm(prev => ({ ...prev, position_side: event.target.value as 'LONG' | 'SHORT' }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200"><option value="SHORT">SHORT</option><option value="LONG">LONG</option></select></label>
                      <label className="text-[10px] text-slate-400">{t('track_form_entry')}<input required type="number" step="any" min="0" value={form.entry_price} onChange={event => setForm(prev => ({ ...prev, entry_price: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{t('track_form_qty')}<input type="number" step="any" min="0" value={form.quantity} onChange={event => setForm(prev => ({ ...prev, quantity: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Notional USDT<input type="number" step="any" min="0" value={form.notional} onChange={event => setForm(prev => ({ ...prev, notional: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{t('track_form_leverage')}<input type="number" step="any" min="0" value={form.leverage} onChange={event => setForm(prev => ({ ...prev, leverage: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Stop Loss<input type="number" step="any" min="0" value={form.stop_loss} onChange={event => setForm(prev => ({ ...prev, stop_loss: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Take Profit<input type="number" step="any" min="0" value={form.take_profit} onChange={event => setForm(prev => ({ ...prev, take_profit: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400 sm:col-span-1">{t('track_form_notes')}<input value={form.notes} onChange={event => setForm(prev => ({ ...prev, notes: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="text-[10px] text-slate-500">
                        {t('track_form_disclaimer')}
                      </span>
                      <button type="submit" disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg bg-amber-500 px-3 text-[10px] font-bold text-slate-950 hover:bg-amber-400 disabled:opacity-50">
                        <Activity className="h-3 w-3" /> {t('track_form_save')}
                      </button>
                    </div>
                  </form>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
};
