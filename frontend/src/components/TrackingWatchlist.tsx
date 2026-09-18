import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Archive,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Eye,
  EyeOff,
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
import { formatSystemDateTime } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';
import { TrackingJourney } from './TrackingJourney';

export type TrackingFilter = 'ACTIVE' | 'ALL' | TrackingStatus;
export type UpdateTrackingPayload = Record<string, unknown>;

interface TrackingWatchlistProps {
  onAddTracking?: (symbol: string) => void | Promise<boolean>;
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
  onAddTracking,
}) => {
  const { language, t } = useTranslation();

  const [filter, setFilter] = useState<TrackingFilter>('ACTIVE');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PositionFormState>(emptyForm);
  const [newSymbol, setNewSymbol] = useState('');
  const [adding, setAdding] = useState(false);
  const [usage, setUsage] = useState<{ visitors_7d: number; returning_visitors_7d: number } | null>(null);
  useEffect(() => {
    let active = true;
    const key = 'dao_vang_tracking_visitor';
    const visitor = localStorage.getItem(key) || crypto.randomUUID();
    localStorage.setItem(key, visitor);
    void fetch('/api/tracking-usage', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ visitor_id: visitor }) })
      .then(async res => { if (res.ok && active) setUsage(await res.json()); }).catch(() => {});
    return () => { active = false; };
  }, []);

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
      ACTIVE: { vi: 'Radar còn hiệu lực', en: t('track_status_radar_active'), zh: '雷达有效', ko: '레이더 유효' },
      HIT: { vi: 'Radar đã trúng mục tiêu', en: t('track_status_target_hit'), zh: '已达回撤目标', ko: '목표 도달' },
      MISS: { vi: 'Không đạt điều kiện mục tiêu', en: 'Target conditions not met' },
      EXPIRED: { vi: 'Hết hạn · chưa có kết quả xác minh', en: 'Expired · outcome unverified', zh: '已过期 · 结果未验证', ko: '만료 · 결과 미검증' },
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
    if (filter === 'ALL') return true;
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

  const getFilterButtons = (): Array<[TrackingFilter, string]> => [
    ['ACTIVE', t('track_filter_active')],
    ['ALL', language === 'vi' ? 'Toàn bộ lịch sử' : 'All history'],
    ['WATCHING', t('track_filter_watching')],
    ['IN_POSITION', t('track_filter_in_pos')],
    ['CLOSED', t('track_filter_closed')],
  ];

  return (
    <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-100">
            <Target className="h-4 w-4 text-amber-400" />
            {language === 'vi' ? 'Coin của tôi' : 'My coins'}
          </h2>
          <p className="mt-1 text-[11px] text-slate-500">
            {language === 'vi' ? 'Theo dõi thay đổi, kiểm chứng cảnh báo và thử bằng vốn giả lập.' : 'Follow changes, review alerts and practice with paper trades.'}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {language === 'vi' ? 'Chọn coin trong Radar và bấm Theo dõi. Mỗi mục giữ lại thông tin lúc lưu để đối chiếu kết quả sau này.' : 'Choose a coin in Radar and follow it. Saved observations retain their original signal details.'}
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

      {onAddTracking && <form className="flex flex-wrap items-end gap-2" onSubmit={event => {
        event.preventDefault(); setAdding(true);
        void Promise.resolve(onAddTracking(newSymbol.trim().toUpperCase())).then(ok => { if (ok !== false) setNewSymbol(''); }).finally(() => setAdding(false));
      }}>
        <label className="text-xs text-slate-300">{language === 'vi' ? 'Coin muốn theo dõi' : 'Coin to follow'}<input required pattern="[A-Za-z0-9]{2,30}" maxLength={30} placeholder="BTC, ETH, SOL…" value={newSymbol} onChange={e => setNewSymbol(e.target.value)} className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" /></label>
        <button disabled={adding} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">{adding ? '…' : language === 'vi' ? 'Thêm coin theo dõi' : 'Follow coin'}</button>
      </form>}
      <p className="text-xs text-slate-400">{language === 'vi' ? 'Thông báo khi giá thay đổi từ 5%, dữ liệu mất/phục hồi hoặc có kết quả 24/48 giờ. Biến động giá được giãn cách tối thiểu 2 giờ; không cần mở trang liên tục.' : 'Notifications cover 5% price moves, data outages/recovery and 24/48h results. Price alerts have a two-hour cooldown; the page need not stay open.'}</p>
      <p className="text-xs text-slate-500">{language === 'vi' ? 'Phản hồi đã nhận' : 'Feedback received'}: {items.filter(i => i.feedback).length} · {language === 'vi' ? 'Hữu ích' : 'Useful'}: {items.filter(i => i.feedback === 'USEFUL').length} · {language === 'vi' ? 'Gây phiền' : 'Noisy'}: {items.filter(i => i.feedback === 'NOISY').length}
        {usage && Number.isFinite(usage.visitors_7d) && <> · {language === 'vi' ? 'Thiết bị quay lại / đã dùng trong 7 ngày' : 'Returning / active devices in 7 days'}: {usage.returning_visitors_7d}/{usage.visitors_7d}</>}
      </p>
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
        {getFilterButtons().map(([value, label]) => (
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
              <article key={item.id} id={`tracking-${item.id}`} data-testid={`tracking-${item.symbol}`} className="rounded-xl border border-slate-800 bg-slate-950/80 p-3 shadow-lg shadow-black/10">
                {item.market_data_status !== 'FRESH' && (
                  <p role="status" className="mb-2 rounded-lg border border-amber-800/60 bg-amber-950/30 p-2 text-xs text-amber-200">
                    {language === 'vi'
                      ? item.market_data_status === 'STALE' ? 'Dữ liệu giá đã cũ — chưa tính lãi/lỗ hiện tại. Hãy làm mới trước khi đánh giá.' : 'Chưa xác minh được giá mới — chưa tính lãi/lỗ hiện tại.'
                      : item.market_data_status === 'STALE' ? 'Price data is stale. Current P&L is unavailable until refreshed.' : 'A fresh price could not be verified. Current P&L is unavailable.'}
                  </p>
                )}
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
                      <div className="text-[9px] uppercase text-slate-500">{language === 'vi' ? 'Điểm dự báo lúc lưu' : 'Saved forecast score'}</div>
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

                  <div className="flex shrink-0 items-center gap-1.5 lg:w-48 lg:justify-end">
                    {item.status === 'WATCHING' && item.paper_trade?.status !== 'OPEN' && (
                      <button
                        type="button"
                        onClick={() => void onRemoveItem(item.id)}
                        disabled={isUpdating}
                        className="inline-flex h-8 items-center gap-1 rounded-lg border border-red-900/70 bg-red-950/40 px-2.5 text-[10px] font-semibold text-red-300 transition hover:bg-red-950 hover:border-red-700 disabled:opacity-50"
                        title={t('track_btn_unfollow')}
                      >
                        {isUpdating ? <Loader2 className="h-3 w-3 animate-spin" /> : <EyeOff className="h-3 w-3" />}
                        {t('track_btn_unfollow')}
                      </button>
                    )}
                    {item.status !== 'CLOSED' && (
                      <button
                        type="button"
                        onClick={() => openEditor(item)}
                        disabled={isUpdating}
                        className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 text-[10px] font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-50"
                      >
                        {isUpdating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pencil className="h-3 w-3" />}
                        {language === 'vi' ? 'Ghi chép vị thế' : 'Position notes'}
                      </button>
                    )}
                    {item.status === 'IN_POSITION' && (
                      <button
                        type="button"
                        onClick={() => void closeTracking(item)}
                        disabled={isUpdating}
                        className="inline-flex h-8 items-center gap-1 rounded-lg border border-emerald-800/70 bg-emerald-950/40 px-2.5 text-[10px] font-semibold text-emerald-300 transition hover:bg-emerald-950 disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-3 w-3" /> {t('track_btn_close_pos')}
                      </button>
                    )}
                    {item.status === 'CLOSED' && !item.archived_at && (
                      <button
                        type="button"
                        onClick={() => void onRemoveItem(item.id)}
                        disabled={isUpdating}
                        className="inline-flex h-8 items-center gap-1 rounded-lg border border-red-900/70 bg-red-950/40 px-2.5 text-[10px] font-semibold text-red-300 transition hover:bg-red-950 disabled:opacity-50"
                      >
                        <Archive className="h-3 w-3" /> {language === 'vi' ? 'Lưu trữ' : 'Archive'}
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800/80 pt-2 text-[10px] text-slate-500">
                  <span>{language === 'vi' ? 'Điểm dự báo không phải xác suất có lãi. Đạt mục tiêu không đồng nghĩa lệnh giao dịch có lãi.' : 'Forecast score is not profit probability. A target hit does not establish trading profit.'}</span>
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
                  {item.last_market_update && <span>{t('col_time')} {formatSystemDateTime(item.last_market_update)}</span>}
                </div>

                {!!item.history?.length && (
                  <details className="mt-2 rounded-lg border border-slate-800 p-2 text-xs text-slate-400">
                    <summary className="cursor-pointer">{language === 'vi' ? 'Nhật ký theo dõi' : 'Tracking journal'}</summary>
                    <ol className="mt-2 space-y-1">
                      {item.history.map((event, index) => (
                        <li key={`${event.at}-${index}`}>
                          {formatSystemDateTime(event.at)} · {event.event === 'SAVED' ? (language === 'vi' ? 'Đã lưu tín hiệu gốc' : 'Original observation saved') : event.event === 'ARCHIVED' ? (language === 'vi' ? 'Đã ngừng theo dõi, giữ lịch sử' : 'Archived; history retained') : (language === 'vi' ? 'Đã cập nhật ghi chép' : 'Journal updated')}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
                <p className="mt-2 text-xs text-slate-400">
                  {language === 'vi' ? 'Lý do lúc lưu: ' : 'Saved reason: '}{item.source_reason || (language === 'vi' ? 'Chưa có giải thích được lưu.' : 'No explanation was saved.')}
                  {item.outcome_exclusion_reason && <span className="block text-amber-300">{language === 'vi' ? 'Chưa đủ dữ liệu đánh giá: ' : 'Insufficient outcome evidence: '}{item.outcome_exclusion_reason}</span>}
                </p>
                <TrackingJourney item={item} onRefresh={onRefresh} onUpdate={onUpdateItem} />

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
                      <label className="text-[10px] text-slate-400">{t('track_notional_usdt')}<input type="number" step="any" min="0" value={form.notional} onChange={event => setForm(prev => ({ ...prev, notional: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{t('track_form_leverage')}<input type="number" step="any" min="0" value={form.leverage} onChange={event => setForm(prev => ({ ...prev, leverage: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{t('track_stop_loss_label')}<input type="number" step="any" min="0" value={form.stop_loss} onChange={event => setForm(prev => ({ ...prev, stop_loss: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{t('track_take_profit_label')}<input type="number" step="any" min="0" value={form.take_profit} onChange={event => setForm(prev => ({ ...prev, take_profit: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
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
