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
  const { language } = useTranslation();

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
            {language === 'en' ? 'Signal & PnL Performance Tracking' : language === 'zh' ? '信号验证与 PnL 盈亏表现跟踪' : language === 'ko' ? '신호 및 PnL 실적 추적' : 'Theo dõi tiến trình & Hiệu quả PnL'}
          </h2>
          <p className="mt-1 text-[11px] text-slate-500">
            {language === 'en' 
              ? 'Independent performance tracking pool from 24/7 scanner alerts.' 
              : language === 'zh' 
              ? '独立于 24/7 扫描池的个人跟单与 PnL 盈亏追踪表。' 
              : language === 'ko' 
              ? '24/7 스캐너와 분리된 개별 신호 및 손익(PnL) 추적 공간입니다.' 
              : 'Tách khỏi danh sách coin mà scanner dùng để quét.'}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="inline-flex h-8 items-center justify-center gap-1.5 self-start rounded-lg border border-slate-700 bg-slate-900 px-3 text-[11px] font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-60 sm:self-auto"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          {language === 'en' ? 'Refresh Prices' : language === 'zh' ? '刷新行情' : language === 'ko' ? '시세 새로고침' : 'Cập nhật giá'}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{language === 'en' ? 'Total Tracked' : language === 'zh' ? '跟踪总数' : language === 'ko' ? '총 추적' : 'Đang theo dõi'}</div>
          <div className="mt-1 text-xl font-black text-amber-300">{stats.total}</div>
        </div>
        <div className="rounded-xl border border-sky-800/60 bg-sky-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{language === 'en' ? 'Radar Active' : language === 'zh' ? '雷达有效' : language === 'ko' ? '레이더 유효' : 'Radar còn hiệu lực'}</div>
          <div className="mt-1 text-xl font-black text-sky-300">{stats.activeSignals}</div>
        </div>
        <div className="rounded-xl border border-purple-800/60 bg-purple-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{language === 'en' ? 'In Position' : language === 'zh' ? '持仓中' : language === 'ko' ? '포지션 보유' : 'Đang vào lệnh'}</div>
          <div className="mt-1 text-xl font-black text-purple-300">{stats.positions}</div>
        </div>
        <div className="rounded-xl border border-red-800/60 bg-red-950/30 p-3">
          <div className="text-[10px] uppercase text-slate-500">{language === 'en' ? 'Attention Needed' : language === 'zh' ? '需关注' : language === 'ko' ? '주의 필요' : 'Cần chú ý'}</div>
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
          {language === 'en' ? 'Loading tracking list...' : language === 'zh' ? '正在加载跟踪列表...' : language === 'ko' ? '추적 목록 로드 중...' : 'Đang tải danh sách theo dõi...'}
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/60 p-10 text-center">
          <Eye className="mx-auto mb-2 h-6 w-6 text-slate-600" />
          <div className="text-xs font-semibold text-slate-400">
            {language === 'en' ? 'No coins in this group' : language === 'zh' ? '当前分组暂无币种' : language === 'ko' ? '이 그룹에 코인이 없습니다' : 'Chưa có coin trong nhóm này'}
          </div>
          <div className="mt-1 text-[11px] text-slate-600">
            {language === 'en' ? 'Click "Track" on any Radar alert to start monitoring performance.' : language === 'zh' ? '在任意雷达警报卡片上点击“跟踪”即可开始监控。' : language === 'ko' ? '레이더 경보 카드에서 "추적"을 클릭하여 모니터링을 시작하세요.' : 'Bấm "Theo dõi" trên một cảnh báo Radar để bắt đầu.'}
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
                      <div className="text-[9px] uppercase text-slate-500">{language === 'en' ? 'Current Price' : language === 'zh' ? '当前行情价' : language === 'ko' ? '현재가' : 'Giá hiện tại'}</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-slate-100">{formatPrice(item.current_price)}</div>
                      <div className={`text-[10px] ${positiveSignalChange ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatPercent(item.signal_change_pct, true)} {language === 'en' ? 'from Radar' : language === 'zh' ? '较警报点' : language === 'ko' ? '경보 시점 대비' : 'từ Radar'}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">{language === 'en' ? 'Target Progress' : language === 'zh' ? '目标进度 (-8%)' : language === 'ko' ? '목표 진행률' : 'Tiến trình mục tiêu'}</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-amber-300">{formatPercent(item.signal_progress_pct)}</div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-amber-600 to-emerald-400" style={{ width: `${progress}%` }} /></div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                      <div className="text-[9px] uppercase text-slate-500">{language === 'en' ? 'Position / PnL' : language === 'zh' ? '持仓 / 盈亏' : language === 'ko' ? '포지션 / 손익' : 'Vị thế / PnL'}</div>
                      {item.status === 'IN_POSITION' ? (
                        <>
                          <div className={`mt-0.5 flex items-center gap-1 font-mono text-xs font-bold ${positivePnl ? 'text-emerald-400' : 'text-red-400'}`}>
                            <PnlIcon className="h-3 w-3" />
                            {formatPercent(item.position_change_pct, true)}
                          </div>
                          <div className={`text-[10px] ${positivePnl ? 'text-emerald-500' : 'text-red-500'}`}>ROI {formatPercent(item.position_roi_pct, true)} · PnL {formatMoney(item.position_pnl)}</div>
                        </>
                      ) : <div className="mt-0.5 text-xs text-slate-500">{language === 'en' ? 'No position entered' : language === 'zh' ? '未录入持仓' : language === 'ko' ? '포지션 미입력' : 'Chưa nhập lệnh'}</div>}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-1.5 lg:w-44 lg:justify-end">
                    {item.status !== 'CLOSED' && (
                      <button type="button" onClick={() => openEditor(item)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 text-[10px] font-semibold text-slate-300 transition hover:border-amber-500/60 hover:text-amber-300 disabled:opacity-50">
                        {isUpdating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pencil className="h-3 w-3" />}
                        {item.status === 'IN_POSITION' ? (language === 'en' ? 'Edit Position' : language === 'zh' ? '修改持仓' : language === 'ko' ? '포지션 수정' : 'Sửa lệnh') : (language === 'en' ? 'Enter Position' : language === 'zh' ? '录入持仓' : language === 'ko' ? '포지션 입력' : 'Đã vào lệnh')}
                      </button>
                    )}
                    {item.status === 'IN_POSITION' && (
                      <button type="button" onClick={() => void closeTracking(item)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-emerald-800/70 bg-emerald-950/40 px-2.5 text-[10px] font-semibold text-emerald-300 transition hover:bg-emerald-950 disabled:opacity-50">
                        <CheckCircle2 className="h-3 w-3" /> {language === 'en' ? 'Close Position' : language === 'zh' ? '平仓结算' : language === 'ko' ? '포지션 종료' : 'Đóng lệnh'}
                      </button>
                    )}
                    {item.status === 'CLOSED' && (
                      <button type="button" onClick={() => void onRemoveItem(item.id)} disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg border border-red-900/70 bg-red-950/40 px-2.5 text-[10px] font-semibold text-red-300 transition hover:bg-red-950 disabled:opacity-50">
                        <Archive className="h-3 w-3" /> {language === 'en' ? 'Delete' : language === 'zh' ? '删除' : language === 'ko' ? '삭제' : 'Xóa'}
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800/80 pt-2 text-[10px] text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <Clock3 className="h-3 w-3 text-sky-400" />
                    {item.validity_hours_left == null 
                      ? (language === 'en' ? 'No expiration' : language === 'zh' ? '无有效期限制' : language === 'ko' ? '만료 기한 없음' : 'Không có thời hạn') 
                      : item.validity_hours_left > 0 
                        ? (language === 'en' ? `${item.validity_hours_left.toFixed(1)}h left` : language === 'zh' ? `剩余 ${item.validity_hours_left.toFixed(1)} 小时` : language === 'ko' ? `${item.validity_hours_left.toFixed(1)}시간 남음` : `Còn ${item.validity_hours_left.toFixed(1)} giờ`) 
                        : (language === 'en' ? 'Expired' : language === 'zh' ? '已过期' : language === 'ko' ? '만료됨' : 'Đã hết hạn')}
                  </span>
                  <span>{language === 'en' ? 'Target' : language === 'zh' ? '目标' : language === 'ko' ? '목표가' : 'Mục tiêu'} {formatPrice(item.source_target_price)}</span>
                  {item.status === 'IN_POSITION' && <span>Entry {formatPrice(item.entry_price)} · {item.position_side}</span>}
                  {item.last_market_update && <span>{language === 'en' ? 'Updated' : language === 'zh' ? '更新于' : language === 'ko' ? '갱신 시각' : 'Cập nhật'} {formatSystemTime(item.last_market_update)}</span>}
                </div>

                {editingId === item.id && (
                  <form onSubmit={(event) => void submitPosition(event, item)} className="mt-3 rounded-xl border border-amber-800/60 bg-amber-950/20 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="text-xs font-bold text-amber-300">
                        {language === 'en' ? 'Binance Position Tracker (Manual Entry)' : language === 'zh' ? '币安持仓记录器 (手动输入)' : language === 'ko' ? '바이낸스 포지션 기록 (수동 입력)' : 'Thông tin lệnh Binance (nhập thủ công)'}
                      </div>
                      <button type="button" onClick={closeEditor} className="text-slate-500 hover:text-slate-200"><X className="h-4 w-4" /></button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <label className="text-[10px] text-slate-400">{language === 'en' ? 'Side' : language === 'zh' ? '多空方向' : language === 'ko' ? '방향' : 'Hướng'}<select value={form.position_side} onChange={event => setForm(prev => ({ ...prev, position_side: event.target.value as 'LONG' | 'SHORT' }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200"><option value="SHORT">SHORT</option><option value="LONG">LONG</option></select></label>
                      <label className="text-[10px] text-slate-400">{language === 'en' ? 'Entry Price' : language === 'zh' ? '开仓价' : language === 'ko' ? '진입가' : 'Giá vào'}<input required type="number" step="any" min="0" value={form.entry_price} onChange={event => setForm(prev => ({ ...prev, entry_price: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{language === 'en' ? 'Quantity' : language === 'zh' ? '持币数量' : language === 'ko' ? '수량' : 'Số lượng coin'}<input type="number" step="any" min="0" value={form.quantity} onChange={event => setForm(prev => ({ ...prev, quantity: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{language === 'en' ? 'Notional USDT' : language === 'zh' ? '名义价值 USDT' : language === 'ko' ? '명목가치 USDT' : 'Notional USDT'}<input type="number" step="any" min="0" value={form.notional} onChange={event => setForm(prev => ({ ...prev, notional: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">{language === 'en' ? 'Leverage' : language === 'zh' ? '杠杆倍数' : language === 'ko' ? '레버리지' : 'Đòn bẩy'}<input type="number" step="any" min="0" value={form.leverage} onChange={event => setForm(prev => ({ ...prev, leverage: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Stop Loss<input type="number" step="any" min="0" value={form.stop_loss} onChange={event => setForm(prev => ({ ...prev, stop_loss: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400">Take Profit<input type="number" step="any" min="0" value={form.take_profit} onChange={event => setForm(prev => ({ ...prev, take_profit: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                      <label className="text-[10px] text-slate-400 sm:col-span-1">{language === 'en' ? 'Notes' : language === 'zh' ? '备注' : language === 'ko' ? '메모' : 'Ghi chú'}<input value={form.notes} onChange={event => setForm(prev => ({ ...prev, notes: event.target.value }))} className="mt-1 h-8 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 text-xs text-slate-200" /></label>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="text-[10px] text-slate-500">
                        {language === 'en' ? 'PnL excludes exchange fees, funding and liquidation limits.' : language === 'zh' ? '盈亏计算暂未扣除手续费、资金费及强制平仓线。' : language === 'ko' ? '손익(PnL)은 거래 수수료, 펀딩비, 청산가를 제외한 추정치입니다.' : 'PnL chưa bao gồm phí, funding và giá thanh lý.'}
                      </span>
                      <button type="submit" disabled={isUpdating} className="inline-flex h-8 items-center gap-1 rounded-lg bg-amber-500 px-3 text-[10px] font-bold text-slate-950 hover:bg-amber-400 disabled:opacity-50">
                        <Activity className="h-3 w-3" /> {language === 'en' ? 'Save Position' : language === 'zh' ? '保存持仓' : language === 'ko' ? '포지션 저장' : 'Lưu vị thế'}
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
