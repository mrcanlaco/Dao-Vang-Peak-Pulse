import { useEffect, useState } from 'react';
import { useTranslation } from '../i18n/LanguageContext';
import { formatSystemTime } from '../utils/time';

type Fill = { leg: number; price: number; average_entry: number; target_price: number; stop_price: number; filled_at?: string };
type PatternDiscrepancy = {
  feature?: string;
  value?: number | string | null;
  template_value?: number | string | null;
  standardized_abs_error?: number | null;
  [key: string]: unknown;
};
type PostStopTracking = {
  status?: string;
  price_only?: boolean;
  price_only_post_stop?: boolean;
  frozen_average_at_stop?: number | null;
  frozen_average_entry?: number | null;
  frozen_target_price?: number | null;
  stop_average_entry?: number | null;
  average_entry_at_stop?: number | null;
  return_from_frozen_average?: number | null;
  post_stop_return?: number | null;
  horizon_hours?: number;
  original_horizon_hours?: number;
  horizon_time?: string | null;
  target_time?: string | null;
  target_after_stop?: boolean;
  target_price?: number | null;
  exclusion_reason?: string | null;
  fills?: Fill[];
  no_fills?: boolean;
  started_at?: string | null;
  ended_at?: string | null;
};
type Outcome = {
  status: string;
  fills: Fill[];
  exit_price: number | null;
  exclusion_reason: string | null;
  actual_outcome?: boolean | null;
  actual_win?: boolean | null;
  eligible?: boolean | null;
  label?: number | null;
  funding_verified?: boolean | null;
  paired_evidence_eligible?: boolean | null;
  outcome_kind?: string | null;
  price_only_post_stop?: boolean;
  post_stop?: PostStopTracking | null;
  post_stop_tracking?: PostStopTracking | null;
  stop_average_entry?: number | null;
  frozen_average_at_stop?: number | null;
  post_stop_return?: number | null;
  original_horizon_hours?: number | null;
  frozen_average_entry?: number | null;
  frozen_target_price?: number | null;
};
type CriteriaProgress = {
  score: number;
  met_count: number;
  total_count: number;
  criteria: {
    pump: { current: number; target: number; passed: boolean };
    reversal: { current: number; target: number; passed: boolean };
    funding: { current: number; target: number; passed: boolean };
    funding_persistence: { current: number | null; target: number; passed: boolean };
    funding_change: { current: number; target: number; passed: boolean };
    score: { current: number; target: number; passed: boolean };
  };
};
type Item = {
  id: string; symbol: string; feature_time: string; selected: boolean; scout: boolean; champion?: boolean;
  score: number; reason: string; price: number;
  price_ret_24h?: number; distance_from_high_24h?: number; funding_percentile_30d?: number; funding_persistence_7d?: number; funding_change_8h?: number;
  progress?: CriteriaProgress;
  entry_plan: { leg: number; price: number; notional_weight: number }[];
  outcome?: Outcome | null;
  pattern_id?: string | null;
  pattern_type?: string | null;
  pattern_stage?: string | null;
  pattern_status?: string | null;
  nearest_pattern?: string | null;
  pattern_distance?: number | null;
  pattern_discrepancies?: PatternDiscrepancy[] | string[] | string | null;
  pattern_quality?: string | null;
  quality_status?: string | null;
  data_quality_score?: number | null;
  high_quality?: boolean | null;
  quality_validated?: boolean | null;
  evidence_corroborated?: boolean | null;
  validated_evidence?: boolean | null;
  evidence_kind?: string | null;
  score_kind?: string | null;
  post_stop?: PostStopTracking | null;
};
type DiscoveryItem = { symbol: string; ticker_return_24h: number; feature_return_24h: number | null;
  ticker_time: string; feature_time?: string | null; first_seen: string; discovery_reason: string;
  pipeline_stage?: string; backfill?: { attempts?: number; error?: string | null; next_retry_at?: string | null;
    decision_reason?: string; quality?: { price_bars: number; required_price_bars: number; warning?: string | null } } };
type Snapshot = { status: string; stale?: boolean; updated_at?: string; activated_at?: string; candidate_count?: number; entry_count?: number; items?: Item[];
  discovery?: { status: string; stale?: boolean; updated_at?: string; market_count?: number; deferred_count?: number; items: DiscoveryItem[] } };

const postStopTracking = (item: Item): PostStopTracking | null => {
  const outcome = item.outcome;
  const tracking = outcome?.post_stop_tracking || outcome?.post_stop || item.post_stop;
  if (tracking && String(tracking.status || '').toLowerCase() === 'not_applicable'
    && !tracking.price_only && !tracking.price_only_post_stop
    && !outcome?.price_only_post_stop && outcome?.outcome_kind !== 'price_only_post_stop') return null;
  if (!tracking && !(outcome?.price_only_post_stop || outcome?.outcome_kind === 'price_only_post_stop')) return null;
  return tracking || {
    price_only: true,
    price_only_post_stop: true,
    frozen_average_at_stop: outcome?.frozen_average_at_stop ?? outcome?.stop_average_entry ?? null,
    frozen_average_entry: outcome?.frozen_average_entry ?? null,
    frozen_target_price: outcome?.frozen_target_price ?? null,
    post_stop_return: outcome?.post_stop_return ?? null,
    original_horizon_hours: outcome?.original_horizon_hours ?? 48,
  };
};

const hasActualOutcome = (outcome?: Outcome | null): boolean => {
  if (!outcome) return false;
  const status = String(outcome.status).toLowerCase();
  if (['post_stop', 'post_stop_price_only', 'target_after_stop', 'timeout_after_stop', 'price_only_post_stop'].includes(status)) return false;
  if (outcome.actual_outcome === false || outcome.price_only_post_stop || outcome.outcome_kind === 'price_only_post_stop') return false;
  if (outcome.actual_outcome === true) return true;
  return ['target', 'stop', 'stop_ambiguous', 'timeout'].includes(status);
};

const isHighQuality = (item: Item): boolean => {
  // ``quality_status=valid`` and a numeric score describe source hygiene, not
  // validated pattern evidence.  The backend must explicitly certify the
  // high-quality lane; corroboration flags can only veto that certification.
  const certified = item.high_quality === true
    || item.quality_validated === true
    || String(item.pattern_quality || '').toLowerCase() === 'high_quality';
  if (!certified) return false;
  return item.evidence_corroborated !== false && item.validated_evidence !== false;
};

const patternDiscrepancyText = (value: PatternDiscrepancy[] | string[] | string | null | undefined): string => {
  if (!Array.isArray(value)) return value || '';
  return value.map(entry => {
    if (typeof entry === 'string') return entry;
    const feature = entry.feature || 'feature';
    const current = entry.value == null ? '—' : String(entry.value);
    const template = entry.template_value == null ? '—' : String(entry.template_value);
    const error = entry.standardized_abs_error == null ? '' : ` (|z| ${entry.standardized_abs_error})`;
    return `${feature}: ${current} vs ${template}${error}`;
  }).join(', ');
};

const getProgress = (item: Item): CriteriaProgress => {
  if (item.progress && item.progress.criteria && item.progress.criteria.score) {
    const criteria = item.progress.criteria;
    const persistence = criteria.funding_persistence || {
      current: item.funding_persistence_7d ?? null,
      target: 0,
      passed: Number(item.funding_persistence_7d ?? 0) > 0,
    };
    const market = [criteria.pump, criteria.reversal, criteria.funding, criteria.funding_change, criteria.score];
    const met = market.filter(condition => condition.passed).length;
    return {
      ...item.progress,
      score: Math.round((met / 5) * 100),
      met_count: met,
      total_count: 5,
      criteria: { ...criteria, funding_persistence: persistence },
    };
  }
  const p = Number(item.price_ret_24h ?? 0);
  const d = Number(item.distance_from_high_24h ?? 0);
  const f = Number(item.funding_percentile_30d ?? 0);
  const fp = Number(item.funding_persistence_7d ?? 0);
  const fc = Number(item.funding_change_8h ?? 0);
  const s = Number(item.score ?? 0);
  const c_pump = p >= 0.25;
  const c_rev = d <= -0.02;
  const c_fund = f >= 0.80;
  const c_persistence = fp > 0;
  const c_chg = fc > 0;
  const c_score = s >= 0.39;
  const met = [c_pump, c_rev, c_fund, c_chg, c_score].filter(Boolean).length;
  return {
    score: Math.round((met / 5) * 100),
    met_count: met,
    total_count: 5,
    criteria: {
      pump: { current: p, target: 0.25, passed: c_pump },
      reversal: { current: d, target: -0.02, passed: c_rev },
      funding: { current: f, target: 0.80, passed: c_fund },
      funding_persistence: { current: fp, target: 0.0, passed: c_persistence },
      funding_change: { current: fc, target: 0.0, passed: c_chg },
      score: { current: s, target: 0.39, passed: c_score },
    },
  };
};

export function V3ResearchPanel({ onClose }: { onClose: () => void }) {
  const { language } = useTranslation();
  const vi = language === 'vi';
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState(false);
  const [scope, setScope] = useState<'all' | 'parent' | 'scout' | 'champion'>('all');
  const [qualityFilter, setQualityFilter] = useState<'all' | 'high'>('all');
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
  const items = (snapshot?.items || []).filter(item => {
    const inScope = scope === 'all' || (scope === 'parent' ? item.selected : scope === 'scout' ? item.scout : item.champion);
    return inScope && (qualityFilter === 'all' || isHighQuality(item));
  });
  const price = (value: number) => new Intl.NumberFormat(vi ? 'vi-VN' : 'en-US', { maximumSignificantDigits: 7 }).format(value);
  const stateLabel: Record<string, string> = vi ? {
    DETECTED: 'Đã phát hiện', BACKFILLING: 'Đang bổ sung lịch sử', DATA_READY: 'Dữ liệu sẵn sàng',
    SCORING: 'Sẵn sàng chấm điểm tại mốc giờ', CONFIRMATION: 'Đang chờ đủ điều kiện xác nhận', ENTRY: 'Đã có Entry mô phỏng', REJECT: 'Không đạt điều kiện Entry',
    collecting: 'Đang thu thập dữ liệu', features_pending: 'Chờ dữ liệu phân tích',
    history_24h_pending: 'Chưa đủ lịch sử hợp lệ để tính 24h', features_stale: 'Dữ liệu phân tích đã cũ',
    closed_return_below_15pct: 'Mức tăng theo nến đóng chưa đạt 15%', waiting_hourly_confirmation: 'Chờ đánh giá tại mốc hàng giờ',
    ticker_stale: 'Giá thị trường đã cũ', below_volume: 'Khối lượng dưới 1 triệu USD/24h', capacity_deferred: 'Chờ lượt thu thập: đã đạt giới hạn',
    running: 'Đang thu thập', waiting: 'Chờ chu kỳ quét', disabled: 'Chưa bật trên máy chủ',
    error: 'Nhánh thử nghiệm đang lỗi', target: 'Đạt TP theo giá thực tế', target_after_stop: 'Giá đạt TP sau stop (chỉ theo dõi giá)', stop: 'Chạm stop thực tế', stop_ambiguous: 'Stop — nến không rõ thứ tự',
    timeout: 'Hết 48h', open: 'Đang theo dõi', incomplete_final: 'Thiếu dữ liệu kết thúc',
    price_only_post_stop: 'Theo dõi giá sau stop (không phải outcome thực tế)', post_stop: 'Theo dõi giá sau stop (không phải outcome thực tế)',
    unknown: 'Chưa nhận diện mẫu', unmatched: 'Chưa khớp mẫu', uncertain: 'Mẫu chưa chắc chắn',
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
    target: 'Actual TP outcome', target_after_stop: 'Price target after stop (price-only tracking)', stop: 'Actual stop outcome', stop_ambiguous: 'Ambiguous stop', timeout: '48h timeout', open: 'Tracking', incomplete_final: 'Incomplete final data',
    price_only_post_stop: 'Post-stop price-only tracking (not an actual outcome)', post_stop: 'Post-stop price-only tracking (not an actual outcome)',
    unknown: 'Pattern unknown', unmatched: 'Pattern unmatched', uncertain: 'Pattern uncertain',
    reversal_not_confirmed: 'Awaiting ≥2% reversal from peak', funding_gate_failed: 'Funding Scout gate not met', funding_features_missing: 'Funding features missing',
    pump_below_25pct: '24h pump below 25%' };
  return <section data-testid="v3-research" className="flex flex-col gap-4 min-h-[400px] lg:h-full overflow-auto p-2 sm:p-4 text-slate-200">
    <div className="flex flex-wrap justify-between items-start gap-3">
      <div><h2 className="text-lg font-bold text-amber-400">{vi ? 'Thử nghiệm V3 · Champion (Pump ≥25% + Đảo chiều)' : 'V3 Champion · (Pump ≥25% + Reversal)'}</h2>
        <p className="text-xs text-slate-400 mt-1">{vi ? 'Các điều kiện V3 đang được quan sát: Bơm kiệt sức ≥25% · Đảo chiều ≥2% · Funding Scout' : 'Configured V3 conditions under observation: Climax pump ≥25% · Reversal ≥2% · Funding Scout'}</p></div>
      <button onClick={onClose} className="px-3 py-2 rounded-lg border border-slate-600 text-sm">{vi ? 'Về ứng dụng' : 'Back to app'}</button>
    </div>
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm leading-relaxed">
      {vi ? 'Mô phỏng thử nghiệm V3 Champion: Bơm kiệt sức ≥25% + Rơi từ đỉnh ≥2% + Funding Scout. TP −20% / Stop +16% từ giá trung bình theo cấu hình hiện tại (0, +3%, +6% | 20/30/50). Thời hạn 48h.' : 'V3 Champion observation: Climax pump ≥25% + Reversal from peak ≥2% + Funding Scout. TP −20% / Stop +16% from average entry under the current configuration (0, +3%, +6% | 20/30/50). Horizon 48h.'}
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
        {key === 'all' ? (vi ? 'Tất cả quan sát' : 'All observations') : key === 'parent' ? 'Challenger' : key === 'scout' ? 'Funding Scout' : (vi ? '★ Champion' : '★ Champion')}
      </button>)}
      <button onClick={() => setQualityFilter(qualityFilter === 'all' ? 'high' : 'all')} aria-pressed={qualityFilter === 'high'}
        className={`rounded-lg px-3 py-2 text-xs border ${qualityFilter === 'high' ? 'border-emerald-400 text-emerald-300' : 'border-slate-700'}`}>
        {qualityFilter === 'high' ? (vi ? 'Chỉ chất lượng cao' : 'High-quality only') : (vi ? 'Mọi chất lượng' : 'All quality')}
      </button>
    </div>
    <p className="text-[11px] text-slate-500 -mt-2">{vi ? 'Bộ lọc này chỉ thay đổi hiển thị; không chặn tín hiệu đủ điều kiện gửi Telegram.' : 'This filter changes display only; it never suppresses an eligible Telegram signal.'}</p>
    {!items.length && <p className="p-6 text-sm text-slate-400">{vi ? 'Chưa có quan sát phù hợp. Nhánh v3 chỉ ghi dữ liệu từ lúc bật; cần đủ episode 4h và xác nhận để có Entry1, không lấy backtest cũ làm tín hiệu mới.' : 'No matching observations. V3 starts at activation and needs a 4h episode plus confirmations. Old backtests are not shown as new signals.'}</p>}
    {items.map(item => {
      const last = item.outcome?.fills?.at(-1);
      const prog = getProgress(item);
      const actualOutcome = hasActualOutcome(item.outcome);
      const postStop = postStopTracking(item);
      const patternStatus = String(item.pattern_status || 'unknown').toLowerCase();
      const patternName = item.pattern_type || item.pattern_id || 'UNKNOWN';
      const discrepancies = patternDiscrepancyText(item.pattern_discrepancies);
      return <article key={item.id} className="rounded-xl border border-slate-700 bg-slate-900 p-3 sm:p-4">
        <div className="flex flex-wrap gap-2 justify-between items-center">
          <h3 className="font-bold flex items-center gap-2">
            <span>{item.symbol}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
              item.champion ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40' :
              item.scout ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' :
              item.selected ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40' :
              'bg-slate-800 text-slate-400 border border-slate-700'
            }`}>
              {item.champion ? '★ Champion' : item.scout ? 'Challenger + Scout' : item.selected ? 'Challenger' : (vi ? 'Quan sát' : 'Observation')}
            </span>
            {isHighQuality(item) && <span className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300">
              {vi ? 'Bằng chứng chất lượng cao' : 'High-quality evidence'}
            </span>}
          </h3>
          <span className="text-xs text-slate-400 font-mono">{formatSystemTime(item.feature_time)}</span>
        </div>
        <p className="text-xs text-slate-300 mt-1 mb-2.5">
          {stateLabel[item.outcome?.status || item.reason] || item.outcome?.status || item.reason} · {vi ? 'Điểm tham chiếu' : 'Reference score'} <span className="font-mono font-bold text-amber-400">{item.score.toFixed(3)}</span>
        </p>

        <div data-testid={`v3-pattern-${item.symbol}`} className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-2.5 text-xs">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-cyan-200">[PATTERN:{patternName}]</span>
            <span className="font-mono text-amber-200">[STAGE:{String(item.pattern_stage || 'SIGNAL').toUpperCase()}]</span>
            <span className={patternStatus === 'unknown' || patternStatus === 'unmatched' || patternStatus === 'uncertain' ? 'text-amber-300' : 'text-emerald-300'}>
              {stateLabel[patternStatus] || patternStatus}
            </span>
          </div>
          {(patternStatus === 'unknown' || patternStatus === 'unmatched' || patternStatus === 'uncertain') && <p className="mt-1 text-slate-300">
            {vi ? 'Mẫu gần nhất: ' : 'Nearest pattern: '}<span className="font-mono">{item.nearest_pattern || '—'}</span>
            {item.pattern_distance != null && <> · {vi ? 'khoảng cách: ' : 'distance: '}{Number(item.pattern_distance).toFixed(3)}</>}
          </p>}
          {discrepancies && <p className="mt-1 text-amber-200">{vi ? 'Sai khác: ' : 'Discrepancies: '}{discrepancies}</p>}
          <p className="mt-1 text-slate-400">{vi ? 'Bằng chứng: ' : 'Evidence: '}{isHighQuality(item) ? (vi ? 'đã xác thực chất lượng cao' : 'validated high-quality') : (vi ? 'chưa xác thực chất lượng' : 'not quality-validated')}
            {item.evidence_kind && <> · {item.evidence_kind}</>}</p>
        </div>

        {/* Configured five-condition progress. */}
        <div className="my-2 bg-slate-800/80 rounded-lg p-2.5 border border-slate-700/60">
          <div className="flex justify-between items-center text-xs mb-1.5 font-medium">
            <span className="text-slate-300 flex items-center gap-1.5">
              <span>{vi ? 'Tiến trình 5 điều kiện cấu hình:' : 'Configured five-condition progress:'}</span>
              <span className={`font-bold ${prog.score >= 80 ? 'text-emerald-400' : prog.score >= 60 ? 'text-amber-400' : 'text-slate-400'}`}>
                {prog.met_count}/5 {vi ? 'điều kiện' : 'met'} ({prog.score}%)
              </span>
            </span>
            <span className="text-[10px] text-slate-400 font-mono">{vi ? 'TP -20% / 48h' : 'TP -20% / 48h'}</span>
          </div>
          <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden flex">
            <div
              className={`h-full transition-all duration-500 rounded-full ${
                prog.score >= 100
                  ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]'
                  : prog.score >= 60
                  ? 'bg-amber-400'
                  : 'bg-indigo-400'
              }`}
              style={{ width: `${Math.max(6, prog.score)}%` }}
            />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-1.5 mt-2.5 text-[11px] font-mono">
            <div className={`p-1.5 rounded border ${prog.criteria.pump.passed ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-slate-900/80 border-slate-700/50 text-slate-300'}`}>
              <div className="text-[9px] text-slate-400 font-sans">{vi ? 'Bơm 24h (Mốc ≥25%)' : '24h Pump (≥25%)'}</div>
              <div className="font-bold flex items-center justify-between mt-0.5">
                <span>+{(prog.criteria.pump.current * 100).toFixed(1)}%</span>
                <span className="text-[10px]">{prog.criteria.pump.passed ? '✅' : '⏳'}</span>
              </div>
            </div>
            <div className={`p-1.5 rounded border ${prog.criteria.reversal.passed ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-slate-900/80 border-slate-700/50 text-slate-300'}`}>
              <div className="text-[9px] text-slate-400 font-sans">{vi ? 'Rơi đỉnh (Mốc ≤-2%)' : 'Drop peak (≤-2%)'}</div>
              <div className="font-bold flex items-center justify-between mt-0.5">
                <span>{(prog.criteria.reversal.current * 100).toFixed(1)}%</span>
                <span className="text-[10px]">{prog.criteria.reversal.passed ? '✅' : '⏳'}</span>
              </div>
            </div>
            <div className={`p-1.5 rounded border ${prog.criteria.funding.passed ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-slate-900/80 border-slate-700/50 text-slate-300'}`}>
              <div className="text-[9px] text-slate-400 font-sans">{vi ? 'Funding 30d (≥80%)' : 'Funding 30d (≥80%)'}</div>
              <div className="font-bold flex items-center justify-between mt-0.5">
                <span>{(prog.criteria.funding.current * 100).toFixed(0)}%</span>
                <span className="text-[10px]">{prog.criteria.funding.passed ? '✅' : '⏳'}</span>
              </div>
            </div>
            <div className={`p-1.5 rounded border ${prog.criteria.funding_change.passed ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-slate-900/80 border-slate-700/50 text-slate-300'}`}>
              <div className="text-[9px] text-slate-400 font-sans">{vi ? 'Funding 8h (tăng)' : 'Funding change (8h)'}</div>
              <div className="font-bold flex items-center justify-between mt-0.5">
                <span>{(prog.criteria.funding_change.current * 100).toFixed(2)}%</span>
                <span className="text-[10px]">{prog.criteria.funding_change.passed ? '✅' : '⏳'}</span>
              </div>
            </div>
            <div className={`p-1.5 rounded border ${prog.criteria.score.passed ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-slate-900/80 border-slate-700/50 text-slate-300'}`}>
              <div className="text-[9px] text-slate-400 font-sans">{vi ? 'Điểm tham chiếu (≥.39)' : 'Reference score (≥.39)'}</div>
              <div className="font-bold flex items-center justify-between mt-0.5">
                <span>{prog.criteria.score.current.toFixed(3)}</span>
                <span className="text-[10px]">{prog.criteria.score.passed ? '✅' : '⏳'}</span>
              </div>
            </div>
            <div className={`p-1.5 rounded border ${prog.criteria.funding_persistence.passed ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-slate-900/80 border-slate-700/50 text-slate-300'}`}>
              <div className="text-[9px] text-slate-400 font-sans">{vi ? 'Funding bền 7 ngày' : 'Funding persistence (7d)'}</div>
              <div className="font-bold flex items-center justify-between mt-0.5">
                <span>{(Number(prog.criteria.funding_persistence.current ?? 0) * 100).toFixed(2)}%</span>
                <span className="text-[10px]">{prog.criteria.funding_persistence.passed ? '✅' : '⏳'}</span>
              </div>
            </div>
          </div>
          <p className="text-[10px] text-slate-400 mt-1.5">{vi ? 'Điểm tham chiếu / điều kiện thời điểm: ' : 'Reference score / timing eligibility: '}<span className="font-mono text-amber-300">{item.score.toFixed(3)}</span></p>
        </div>
        {item.selected && <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">{item.entry_plan.map(leg => <div key={leg.leg} className="bg-slate-800 rounded p-2">
            Entry{leg.leg}: {price(leg.price)} · {Math.round(leg.notional_weight * 100)}%<br />
            <span className="text-xs text-slate-400">{item.outcome?.fills.some(fill => fill.leg === leg.leg) ? (vi ? 'Đã khớp mô phỏng' : 'Simulated fill') : (vi ? 'Chưa khớp' : 'Not filled')}</span>
          </div>)}</div>
          <p className="text-sm mt-3 break-words">{vi ? 'Giá TB' : 'Average'}: {price(last?.average_entry ?? item.price)} · TP: {price(last?.target_price ?? item.price * 0.8)} · Stop: {price(last?.stop_price ?? item.price * 1.16)}</p>
          <p className="text-xs text-slate-400 mt-1">{vi ? 'Tỷ trọng theo notional kế hoạch; không phải mức ký quỹ hoặc đòn bẩy.' : 'Weights use planned notional, not margin or leverage.'}</p>
        </>}
        {item.outcome && <div data-testid={`v3-outcome-${item.symbol}`} className={`mt-3 rounded-lg border p-2.5 text-sm ${actualOutcome ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-amber-500/30 bg-amber-500/5'}`}>
          <div className="flex flex-wrap justify-between gap-2">
            <strong>{actualOutcome ? (vi ? 'Đường giá outcome thực tế mô phỏng' : 'Actual simulated price-path outcome') : (vi ? 'Trạng thái chưa phải outcome thực tế' : 'Not an actual outcome')}</strong>
            <span className="font-mono text-xs">{stateLabel[item.outcome.status] || item.outcome.status}</span>
          </div>
          {item.outcome.exit_price != null && <p className="text-xs mt-1">{vi ? 'Giá thoát: ' : 'Exit price: '}{price(item.outcome.exit_price)}</p>}
          {item.outcome.exclusion_reason && <p className="text-xs text-amber-200 mt-1">{item.outcome.exclusion_reason}</p>}
          {actualOutcome && item.outcome.eligible === false && <p className="text-xs text-amber-200 mt-1">{vi ? 'Đường giá đã kết thúc nhưng chưa đủ điều kiện/cost coverage để dùng làm nhãn đủ điều kiện.' : 'The price path resolved, but funding/cost coverage is not eligible for a fully costed label.'}</p>}
        </div>}
        {postStop && <div data-testid={`v3-post-stop-${item.symbol}`} className="mt-2 rounded-lg border border-sky-500/30 bg-sky-500/5 p-2.5 text-sm">
          <strong className="text-sky-200">{vi ? 'Theo dõi giá sau stop — không phải outcome thực tế' : 'Post-stop price-only tracking — not an actual outcome'}</strong>
          <p className="text-xs text-slate-300 mt-1">{vi ? 'Không thêm fill sau stop; giữ nguyên giá TB tại thời điểm stop trong cửa sổ gốc ' : 'No fills are added after stop; average at stop is frozen for the original '}{postStop.original_horizon_hours ?? postStop.horizon_hours ?? 48}h.</p>
          {(postStop.frozen_average_at_stop ?? postStop.frozen_average_entry ?? postStop.stop_average_entry ?? postStop.average_entry_at_stop) != null && <p className="text-xs text-slate-300 mt-1">{vi ? 'Giá TB đóng băng: ' : 'Frozen average at stop: '}{price(Number(postStop.frozen_average_at_stop ?? postStop.frozen_average_entry ?? postStop.stop_average_entry ?? postStop.average_entry_at_stop))}</p>}
          {postStop.frozen_target_price != null && <p className="text-xs text-sky-200 mt-1">{vi ? 'Mốc TP chỉ theo dõi giá: ' : 'Price-only target reference: '}{price(Number(postStop.frozen_target_price))}</p>}
          {(postStop.target_time || postStop.horizon_time) && <p className="text-xs text-slate-400 mt-1">{vi ? 'Mốc giá: ' : 'Price timestamps: '}{postStop.target_time ? formatSystemTime(postStop.target_time) : '—'}{postStop.horizon_time && <> · {vi ? 'Kết thúc cửa sổ: ' : 'Horizon end: '}{formatSystemTime(postStop.horizon_time)}</>}</p>}
          {(postStop.post_stop_return ?? postStop.return_from_frozen_average) != null && <p className="text-xs text-sky-200 mt-1">{vi ? 'Biến động chỉ theo giá: ' : 'Price-only return: '}{(Number(postStop.post_stop_return ?? postStop.return_from_frozen_average) * 100).toFixed(1)}%</p>}
        </div>}
      </article>;
    })}
  </section>;
}
