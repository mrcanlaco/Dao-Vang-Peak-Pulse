import { useEffect, useState } from 'react';
import { useTranslation } from '../i18n/LanguageContext';
import { formatSystemTime } from '../utils/time';

type Fill = { leg: number; price: number; average_entry: number; target_price: number; stop_price: number };
type Item = {
  id: string; symbol: string; feature_time: string; selected: boolean; scout: boolean; champion?: boolean;
  score: number; reason: string; price: number;
  entry_plan: { leg: number; price: number; notional_weight: number }[];
  outcome?: { status: string; fills: Fill[]; exit_price: number | null; exclusion_reason: string | null } | null;
};
type DiscoveryItem = { symbol: string; ticker_return_24h: number; feature_return_24h: number | null;
  ticker_time: string; feature_time?: string | null; first_seen: string; discovery_reason: string;
  pipeline_stage?: string; backfill?: { attempts?: number; error?: string | null; next_retry_at?: string | null;
    decision_reason?: string; quality?: { price_bars: number; required_price_bars: number; warning?: string | null } } };
type Snapshot = { status: string; stale?: boolean; updated_at?: string; activated_at?: string; candidate_count?: number; entry_count?: number; items?: Item[];
  discovery?: { status: string; stale?: boolean; updated_at?: string; market_count?: number; deferred_count?: number; items: DiscoveryItem[] } };

export function V3ResearchPanel({ onClose }: { onClose: () => void }) {
  const { language } = useTranslation();
  const vi = language === 'vi';
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState(false);
  const [scope, setScope] = useState<'all' | 'parent' | 'scout' | 'champion'>('all');
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch('/api/research/v3', { credentials: 'same-origin', signal: controller.signal });
        if (!response.ok) throw new Error('Unavailable');
        const result = await response.json() as Snapshot;
        if (active) { setSnapshot(result); setError(false); }
      } catch { if (active) setError(true); }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, []);
  const items = (snapshot?.items || []).filter(item => scope === 'all' || (scope === 'parent' ? item.selected : scope === 'scout' ? item.scout : item.champion));
  const price = (value: number) => new Intl.NumberFormat(vi ? 'vi-VN' : 'en-US', { maximumSignificantDigits: 7 }).format(value);
  const stateLabel: Record<string, string> = vi ? {
    DETECTED: 'Đã phát hiện', BACKFILLING: 'Đang bổ sung lịch sử', DATA_READY: 'Dữ liệu sẵn sàng',
    SCORING: 'Sẵn sàng chấm điểm tại mốc giờ', CONFIRMATION: 'Đang chờ đủ điều kiện xác nhận', ENTRY: 'Đã có Entry mô phỏng', REJECT: 'Không đạt điều kiện Entry',
    collecting: 'Đang thu thập dữ liệu', features_pending: 'Chờ dữ liệu phân tích',
    history_24h_pending: 'Chưa đủ lịch sử hợp lệ để tính 24h', features_stale: 'Dữ liệu phân tích đã cũ',
    closed_return_below_15pct: 'Mức tăng theo nến đóng chưa đạt 15%', waiting_hourly_confirmation: 'Chờ đánh giá tại mốc hàng giờ',
    ticker_stale: 'Giá thị trường đã cũ', below_volume: 'Khối lượng dưới 1 triệu USD/24h', capacity_deferred: 'Chờ lượt thu thập: đã đạt giới hạn',
    running: 'Đang thu thập', waiting: 'Chờ chu kỳ quét', disabled: 'Chưa bật trên máy chủ',
    error: 'Nhánh thử nghiệm đang lỗi', target: 'Đạt TP theo giá', stop: 'Chạm stop', stop_ambiguous: 'Stop — nến không rõ thứ tự',
    timeout: 'Hết 48h', open: 'Đang theo dõi', incomplete_final: 'Thiếu dữ liệu kết thúc',
    confirmation_pending: 'Chờ đủ xác nhận', episode_too_young: 'Episode chưa đủ 4h', peak_below_30pct: 'Đỉnh tăng chưa đạt 30%',
    episode_already_consumed: 'Episode đã có quyết định', symbol_cooldown: 'Đang trong thời gian nghỉ',
    score_below_reference_threshold: 'Điểm dưới ngưỡng tham chiếu', stablecoin: 'Loại stablecoin',
    reversal_not_confirmed: 'Chờ đảo chiều từ đỉnh ≥2%', funding_gate_failed: 'Chưa đạt điều kiện cước Funding Scout', funding_features_missing: 'Thiếu chỉ số Funding',
    pump_below_25pct: 'Đỉnh tăng 24h chưa đạt 25%',
  } : { DETECTED: 'Detected', BACKFILLING: 'Backfilling history', DATA_READY: 'Data ready', SCORING: 'Ready for hourly scoring',
    CONFIRMATION: 'Awaiting confirmation', ENTRY: 'Simulated Entry', REJECT: 'Entry conditions rejected',
    collecting: 'Collecting data', features_pending: 'Waiting for features', history_24h_pending: 'Insufficient valid 24h history',
    features_stale: 'Stale features', closed_return_below_15pct: 'Closed-candle return below 15%', waiting_hourly_confirmation: 'Waiting for hourly assessment',
    ticker_stale: 'Stale market price', below_volume: 'Volume below $1M/24h', capacity_deferred: 'Collection capacity reached',
    running: 'Collecting', waiting: 'Waiting for scanner', disabled: 'Not enabled on server', error: 'Research lane error',
    target: 'Price target hit', stop: 'Stop hit', stop_ambiguous: 'Ambiguous stop', timeout: '48h timeout', open: 'Tracking', incomplete_final: 'Incomplete final data',
    reversal_not_confirmed: 'Awaiting ≥2% reversal from peak', funding_gate_failed: 'Funding Scout gate not met', funding_features_missing: 'Funding features missing',
    pump_below_25pct: '24h pump below 25%' };
  return <section data-testid="v3-research" className="flex flex-col gap-4 min-h-[400px] lg:h-full overflow-auto p-2 sm:p-4 text-slate-200">
    <div className="flex flex-wrap justify-between items-start gap-3">
      <div><h2 className="text-lg font-bold text-amber-400">{vi ? 'Thử nghiệm v3 · 20% / 48h' : 'V3 research · 20% / 48h'}</h2>
        <p className="text-xs text-slate-400 mt-1">Challenger + Compact · Funding Scout + Compact</p></div>
      <button onClick={onClose} className="px-3 py-2 rounded-lg border border-slate-600 text-sm">{vi ? 'Về ứng dụng' : 'Back to app'}</button>
    </div>
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm leading-relaxed">
      {vi ? 'Mô phỏng, không đặt lệnh và không gửi Telegram. TP −20% / stop +16% từ giá trung bình; thêm lệnh trong 6h. Điểm model tham chiếu không phải xác suất thắng v3. Funding chưa xác minh — chưa công bố lợi nhuận ròng.' : 'Simulation only: no orders or Telegram. TP −20% / stop +16% from average entry; scale in within 6h. Reference model scores are not calibrated v3 win probabilities. Funding unverified; net returns withheld.'}
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">
      <div className="rounded-lg bg-slate-800 p-3" role="status">{error ? (vi ? 'Không tải được dữ liệu' : 'Unable to load data') : snapshot?.stale ? (vi ? 'Dữ liệu đã cũ — cần kiểm tra scanner' : 'Stale data — check scanner') : stateLabel[snapshot?.status || 'waiting'] || snapshot?.status}
        {snapshot?.updated_at && <p className="text-xs text-slate-400 mt-1">{formatSystemTime(snapshot.updated_at)}</p>}</div>
      <div className="rounded-lg bg-slate-800 p-3">{vi ? 'Snapshot đã quan sát: ' : 'Observed snapshots: '}{snapshot?.candidate_count ?? '—'}</div>
      <div className="rounded-lg bg-slate-800 p-3">{vi ? 'Entry1 mô phỏng: ' : 'Simulated Entry1: '}{snapshot?.entry_count ?? '—'}</div>
    </div>
    {snapshot?.discovery && <div data-testid="v3-discovery" className="rounded-xl border border-slate-700 p-3">
      <h3 className="font-bold">{vi ? 'Phát hiện thị trường ≥15% / 24h' : 'Market discovery ≥15% / 24h'} · {snapshot.discovery.market_count ?? '—'}</h3>
      <p className="text-xs text-slate-400 mt-1">{vi ? 'Cập nhật mỗi lượt quét; kiểm tra nến đóng 5 phút. Xác nhận Entry vẫn theo mốc hàng giờ, đỉnh ≥30% và episode đủ 4h. Coin thiếu dữ liệu vẫn được hiển thị.' : 'Updated each scan using closed 5m candles. Entry confirmation remains hourly with a ≥30% peak and 4h episode. Coins with missing data remain visible.'}</p>
      <p className="text-xs text-slate-400 mt-1">{snapshot.discovery.updated_at && formatSystemTime(snapshot.discovery.updated_at)}
        {(snapshot.discovery.status === 'error' || snapshot.discovery.stale) && <span className="text-rose-300"> · {vi ? 'Phát hiện thị trường đang lỗi hoặc dữ liệu cũ' : 'Discovery error or stale data'}</span>}</p>
      {!!snapshot.discovery.deferred_count && <p className="text-xs text-amber-300">{vi ? 'Chờ lượt thu thập: ' : 'Deferred collection: '}{snapshot.discovery.deferred_count}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">{snapshot.discovery.items.map(coin => <div key={coin.symbol} data-testid={`v3-discovery-${coin.symbol}`} className="rounded-lg bg-slate-800 p-3 text-sm min-w-0">
        <div className="flex flex-wrap justify-between gap-2"><strong>{coin.symbol}</strong><span className="text-emerald-300">+{(coin.ticker_return_24h * 100).toFixed(1)}%</span></div>
        <p className="text-xs mt-1">{stateLabel[coin.discovery_reason] || coin.discovery_reason}</p>
        {coin.pipeline_stage && <p className="text-xs text-amber-300 mt-1">{stateLabel[coin.pipeline_stage] || coin.pipeline_stage}
          {coin.backfill?.decision_reason && <> · {stateLabel[coin.backfill.decision_reason] || coin.backfill.decision_reason}</>}</p>}
        {coin.backfill?.quality && <p className="text-xs text-slate-400">{vi ? 'Nến 24h hợp lệ: ' : 'Valid 24h candles: '}{coin.backfill.quality.price_bars}/{coin.backfill.quality.required_price_bars}
          {coin.backfill.quality.warning && <> · {vi ? 'Lịch sử funding chưa đủ 30 ngày' : 'Funding history shorter than 30 days'}</>}</p>}
        {coin.backfill?.error && <p className="text-xs text-rose-300" title={coin.backfill.error}>{vi ? 'Bổ sung dữ liệu chưa thành công' : 'Backfill not complete'}
          {coin.backfill.next_retry_at && <> · {vi ? 'Thử lại: ' : 'Retry: '}{formatSystemTime(coin.backfill.next_retry_at)}</>}</p>}
        <p className="text-xs text-slate-400 mt-1">{vi ? '24h theo dữ liệu phân tích: ' : 'Feature 24h return: '}{coin.feature_return_24h == null ? '—' : `${(coin.feature_return_24h * 100).toFixed(1)}%`}
          {coin.feature_time && <> · {formatSystemTime(coin.feature_time)}</>}</p>
      </div>)}</div>
    </div>}
    <div className="flex flex-wrap gap-2" aria-label={vi ? 'Chọn nhánh' : 'Select lane'}>
      {(['all', 'parent', 'scout', 'champion'] as const).map(key => <button key={key} onClick={() => setScope(key)} aria-pressed={scope === key}
        className={`rounded-lg px-3 py-2 text-xs border ${scope === key ? 'border-amber-400 text-amber-300' : 'border-slate-700'}`}>
        {key === 'all' ? (vi ? 'Tất cả quan sát' : 'All observations') : key === 'parent' ? 'Challenger' : key === 'scout' ? 'Funding Scout' : (vi ? '★ Champion (+1.8% EV)' : '★ Champion (+1.8% EV)')}
      </button>)}
    </div>
    {!items.length && <p className="p-6 text-sm text-slate-400">{vi ? 'Chưa có quan sát phù hợp. Nhánh v3 chỉ ghi dữ liệu từ lúc bật; cần đủ episode 4h và xác nhận để có Entry1, không lấy backtest cũ làm tín hiệu mới.' : 'No matching observations. V3 starts at activation and needs a 4h episode plus confirmations. Old backtests are not shown as new signals.'}</p>}
    {items.map(item => {
      const last = item.outcome?.fills.at(-1);
      return <article key={item.id} className="rounded-xl border border-slate-700 bg-slate-900 p-3 sm:p-4">
        <div className="flex flex-wrap gap-2 justify-between"><h3 className="font-bold">{item.symbol} <span className="text-xs font-normal text-amber-300">{item.champion ? '★ Champion (+1.8% EV)' : item.scout ? 'Challenger + Scout' : item.selected ? 'Challenger' : (vi ? 'Quan sát' : 'Observation')}</span></h3>
          <span className="text-xs text-slate-400">{formatSystemTime(item.feature_time)}</span></div>
        <p className="text-sm my-2">{stateLabel[item.outcome?.status || item.reason] || item.outcome?.status || item.reason} · {vi ? 'Điểm tham chiếu' : 'Reference score'} {item.score.toFixed(3)}</p>
        {item.selected && <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">{item.entry_plan.map(leg => <div key={leg.leg} className="bg-slate-800 rounded p-2">
            Entry{leg.leg}: {price(leg.price)} · {Math.round(leg.notional_weight * 100)}%<br />
            <span className="text-xs text-slate-400">{item.outcome?.fills.some(fill => fill.leg === leg.leg) ? (vi ? 'Đã khớp mô phỏng' : 'Simulated fill') : (vi ? 'Chưa khớp' : 'Not filled')}</span>
          </div>)}</div>
          <p className="text-sm mt-3 break-words">{vi ? 'Giá TB' : 'Average'}: {price(last?.average_entry ?? item.price)} · TP: {price(last?.target_price ?? item.price * 0.8)} · Stop: {price(last?.stop_price ?? item.price * 1.16)}</p>
          <p className="text-xs text-slate-400 mt-1">{vi ? 'Tỷ trọng theo notional kế hoạch; không phải mức ký quỹ hoặc đòn bẩy.' : 'Weights use planned notional, not margin or leverage.'}</p>
        </>}
      </article>;
    })}
  </section>;
}
