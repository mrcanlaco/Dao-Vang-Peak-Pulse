import React, { useMemo, useState } from 'react';
import {
  Activity,
  Archive,
  CheckCircle2,
  Clock3,
  Eye,
  Loader2,
  Pencil,
  RefreshCw,
  Target,
  ArrowDownRight,
  ArrowUpRight,
  Minus,
  X,
} from 'lucide-react';
import type { TrackingStatus, TrackingWatchlistItem } from '../types';
import { formatSystemTime } from '../utils/time';

type TrackingFilter = 'ACTIVE' | 'WATCHING' | 'IN_POSITION' | 'CLOSED';

interface TrackingWatchlistProps {
  items: TrackingWatchlistItem[];
  isLoading: boolean;
  updatingId?: string | null;
  onRefresh: () => void;
  onSelectCoin: (symbol: string) => void;
  onUpdateItem: (id: string, patch: Record<string, unknown>) => Promise<boolean>;
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

const numberValue = (value: string) => value.trim() === '' ? null : Number(value);

const formatPrice = (value?: number | null) => {
  if (value == null || !Number.isFinite(value)) return '—';
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 8 })}`;
};

const formatPercent = (value?: number | null, signed = false) => {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${signed && value > 0 ? '+' : ''}${value.toFixed(1)}%`;
};

const formatMoney = (value?: number | null) => {
  if (value == null || !Number.isFinite(value)) return '—';
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  return `${sign}$${Math.abs(value).toFixed(2)}`;
};

const statusLabel: Record<TrackingStatus, string> = {
  WATCHING: 'ĐANG THEO DÕI',
  IN_POSITION: 'ĐANG VÀO LỆNH',
  CLOSED: 'ĐÃ ĐÓNG',
};

const signalStatusLabel: Record<string, string> = {
  ACTIVE: 'Radar còn hiệu lực',
  HIT: 'Radar đã trúng mục tiêu',
  EXPIRED: 'Radar hết hạn',
  NO_SIGNAL: 'Theo dõi thủ công',
};

const riskClass = (risk?: string | null) => {
  if (risk === 'CRITICAL') return 'border-red-800 bg-red-950/70 text-red-300';
  if (risk === 'HIGH') return 'border-amber-800 bg-amber-950/70 text-amber-300';
  if (risk === 'MEDIUM') return 'border-yellow-800 bg-yellow-950/70 text-yellow-300';
  if (risk === 'SAFE') return 'border-emerald-800 bg-emerald-950/70 text-emerald-300';
  return 'border-slate-700 bg-slate-900 text-slate-400';
};

const toPositionForm = (item: TrackingWatchlistItem): PositionFormState => ({
  position_side: item.position_side || 'SHORT',
  entry_price: item.entry_price == null ? '' : String(item.entry_price),
  quantity: item.quantity == null ? '' : String(item.quantity),
  notional: item.notional == null ? '' : String(item.notional),
  leverage: item.leverage == null ? '1' : String(item.leverage),
  stop_loss: item.stop_loss == null ? '' : String(item.stop_loss),
  take_profit: item.take_profit == null ? '' : String(item.take_profit),
  notes: item.notes || '',
});

export const TrackingWatchlist: React.FC<TrackingWatchlistProps> = ({
  items,
  isLoading,
  updatingId = null,
  onRefresh,
  onSelectCoin,
  onUpdateItem,
  onRemoveItem,
}) => {
  const [filter, setFilter] = useState<TrackingFilter>('ACTIVE');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PositionFormState>(emptyForm);

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

  return (
    <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-100">
            <Target className="h-4 w-4 text-amber-400" />
            Theo dõi tiến trình
          </h2>
          <p className="mt-1 text-[11px] text-slate-500">Tách khỏi danh sách coin mà scanner dùng để quét.</p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="inline-flex h-8 items-center justify-center gap-1.5 self-start rounded-lg border border-slate-700 bg-slate-900 px-3 text-[11px] font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-60 sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Cập nhật giá
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">Đang theo dõi</div>
          <div className="mt-1 text-xl font-black text-amber-300">{stats.total}</div>
        </div>
        <div className="rounded-xl border border-sky-800/60 bg-sky-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">Radar còn hiệu lực</div>
          <div className="mt-1 text-xl font-black text-sky-300">{stats.activeSignals}</div>
        </div>
        <div className="rounded-xl border border-purple-800/60 bg-purple-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">Đang vào lệnh</div>
          <div className="mt-1 text-xl font-black text-purple-300">{stats.positions}</div>
        </div>
        <div className="rounded-xl border border-red-800/60 bg-red-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">Cần chú ý</div>
          <div className="mt-1 text-xl font-black text-red-300">{stats.attention}</div>
        </div>
      </div>

      <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 p-1 [&::-webkit-scrollbar]:hidden">
        {([
          ['ACTIVE', 'Đang hoạt động'],
          ['WATCHING', 'Chỉ theo dõi'],
          ['IN_POSITION', 'Đang vào lệnh'],
          ['CLOSED', 'Đã đóng'],
        ] as [TrackingFilter, string][]).map(([value, label]) => (
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
          Đang tải danh sách theo dõi...
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/60 p-10 text-center">
          <Eye className="mx-auto mb-2 h-6 w-6 text-slate-600" />
          <div className="text-xs font-semibold text-slate-400">Chưa có coin trong nhóm này</div>
          <div className="mt-1 text-[11px] text-slate-600">Bấm “Theo dõi” trên một cảnh báo Radar để bắt đầu.</div>
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
                        {statusLabel[item.status]}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
                      <span className={`rounded border px-1.5 py-0.5 ${riskClass(item.source_risk_level)}`}>{item.source_risk_level || '—'}</span>
                      <span>{signalStatusLabel[item.signal_status] || item.signal_status}</span>
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
                      <div className="text-[9px] uppercase text-slate-500">Giá hiện tại</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-slate-100">{formatPrice(item.current_price)}</div>
                      <div className={`text-[10px] ${positiveSignalChange ? 'text-emerald-400' : 'text-red-400'}`}>{formatPercent(item.signal_change_pct, true)} từ Radar</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">Tiến trình mục tiêu</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-amber-300">{formatPercent(item.signal_progress_pct)}</div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-amber-600 to-emerald-400" style={{ width: `${progress}%` }} /></div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">Vị thế / PnL</div>
                      {item.status === 'IN_POSITION' ? (
                        <>
                          <div className={`mt-0.5 flex items-center gap-1 font-mono text-xs font-bold ${positivePnl ? 'text-emerald-400' : 'text-red-400'}`}>
                            <PnlIcon className="h-3 w-3" />
                            {formatPercent(item.position_change_pct, true)}
                          </div>
                          <div className={`text-[10px] ${positivePnl ? 'text-emerald-500' : 'text-red-500'}`}>ROI {formatPercent(item.position_roi_pct, true)} · PnL {formatMoney(item.position_pnl)}</div>
                        </>
                      ) : <div className="mt-0.5 text-xs text-slate-500">Chưa nhập lệnh</div>}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-1.5 lg:w-44 lg:justify-end">
                    {item.status !== 'CLOSED' && (
                      <button type="button" onClick={() => openEditor(item)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 text-[10px] font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-50">
                        {isUpdating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pencil className="h-3 w-3" />}
                        {item.status === 'IN_POSITION' ? 'Sửa lệnh' : 'Đã vào lệnh'}
                      </button>
                    )}
                    {item.status === 'IN_POSITION' && (
                      <button type="button" onClick={() => void closeTracking(item)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-emerald-800/70 bg-emerald-950/40 px-2.5 text-[10px] font-semibold text-emerald-300 transition hover:bg-emerald-950 disabled:opacity-50">
                        <CheckCircle2 className="h-3 w-3" /> Đóng lệnh
                      </button>
                    )}
                    {item.status === 'CLOSED' && (
                      <button type="button" onClick={() => void onRemoveItem(item.id)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-red-900/70 bg-red-950/40 px-2.5 text-[10px] font-semibold text-red-300 transition hover:bg-red-950 disabled:opacity-50">
                        <Archive className="h-3 w-3" /> Xóa
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800/80 pt-2 text-[10px] text-slate-500">
                  <span className="inline-flex items-center gap-1"><Clock3 className="h-3 w-3 text-sky-400" />{item.validity_hours_left == null ? 'Không có thời hạn' : item.validity_hours_left > 0 ? `Còn ${item.validity_hours_left.toFixed(1)} giờ` : 'Đã hết hạn'}</span>
                  <span>Mục tiêu {formatPrice(item.source_target_price)}</span>
                  {item.status === 'IN_POSITION' && <span>Entry {formatPrice(item.entry_price)} · {item.position_side}</span>}
                  {item.last_market_update && <span>Cập nhật {formatSystemTime(item.last_market_update)}</span>}
                </div>

                {editingId === item.id && (
                  <form onSubmit={(event) => void submitPosition(event, item)} className="mt-3 rounded-xl border border-amber-800/60 bg-amber-950/20 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="text-xs font-bold text-amber-300">Thông tin lệnh Binance (nhập thủ công)</div>
                      <button type="button" onClick={closeEditor} className="text-slate-500 hover:text-slate-200"><X className="h-4 w-4" /></button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <label className="text-[10px] text-slate-400">Hướng<select value={form.position_side} onChange={event => setForm(prev => ({ ...prev, position_side: event.target.value as 'LONG' | 'SHORT' }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200"><option value="SHORT">SHORT</option><option value="LONG">LONG</option></select></label>
                      <label className="text-[10px] text-slate-400">Giá vào<input required type="number" step="any" min="0" value={form.entry_price} onChange={event => setForm(prev => ({ ...prev, entry_price: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Số lượng coin<input type="number" step="any" min="0" value={form.quantity} onChange={event => setForm(prev => ({ ...prev, quantity: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Notional USDT<input type="number" step="any" min="0" value={form.notional} onChange={event => setForm(prev => ({ ...prev, notional: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Đòn bẩy<input type="number" step="any" min="0" value={form.leverage} onChange={event => setForm(prev => ({ ...prev, leverage: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Stop loss<input type="number" step="any" min="0" value={form.stop_loss} onChange={event => setForm(prev => ({ ...prev, stop_loss: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Take profit<input type="number" step="any" min="0" value={form.take_profit} onChange={event => setForm(prev => ({ ...prev, take_profit: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400 sm:col-span-1">Ghi chú<input value={form.notes} onChange={event => setForm(prev => ({ ...prev, notes: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="text-[10px] text-slate-500">PnL chưa bao gồm phí, funding và giá thanh lý.</span>
                      <button type="submit" disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg bg-amber-500 px-3 text-[10px] font-bold text-slate-950 hover:bg-amber-400 disabled:opacity-50"><Activity className="h-3 w-3" /> Lưu vị thế</button>
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
