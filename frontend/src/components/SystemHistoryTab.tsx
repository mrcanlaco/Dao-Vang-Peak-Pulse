import React, { useState, useEffect } from 'react';
import type { SystemHistoryData } from '../types';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import {
  Database, Radar, Cpu, FlaskConical, Activity, CheckCircle2, XCircle,
  RefreshCw, TrendingUp, Clock, Layers, Lock, Trophy, Info, Gauge, AlertTriangle,
} from 'lucide-react';
import { formatSystemDateTime, parseSystemDate } from '../utils/time';

/* ---------- Tooltip helper ---------- */
const InfoTip: React.FC<{ text: string; className?: string }> = ({ text, className = '' }) => {
  const [show, setShow] = useState(false);
  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onClick={(e) => { e.stopPropagation(); setShow(s => !s); }}
    >
      <Info className="w-3 h-3 text-slate-500 hover:text-amber-400 cursor-help" />
      {show && (
        <span className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1 w-56 bg-slate-950 border border-amber-500/30 rounded-md p-2 text-[10px] text-slate-200 leading-relaxed shadow-xl shadow-black/50 pointer-events-none">
          {text}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-amber-500/30" />
        </span>
      )}
    </span>
  );
};

/* ---------- Stat card with tooltip + bold highlight ---------- */
interface StatCardProps {
  label: string;
  value: React.ReactNode;
  tooltip?: string;
  highlight?: boolean;
  valueClass?: string;
}
const StatCard: React.FC<StatCardProps> = ({ label, value, tooltip, highlight, valueClass = '' }) => (
  <div className={`bg-slate-900 p-2 rounded ${highlight ? 'ring-1 ring-amber-500/40' : ''}`}>
    <div className="text-[9px] text-slate-400 uppercase flex items-center gap-1">
      {label}
      {tooltip && <InfoTip text={tooltip} />}
    </div>
    <div className={`text-sm font-bold font-mono ${valueClass}`}>{value}</div>
  </div>
);

export const SystemHistoryTab: React.FC = () => {
  const modelName = (name?: string) => name?.replace(/^Frozen LR/, 'Hồi quy logistic đã đóng băng') || 'Mô hình';
  const modelDescription = (description?: string) => description
    ?.replace(/Logistic Regression/g, 'Hồi quy logistic')
    .replace(/rule-based/g, 'theo quy tắc')
    .replace(/funding spike/g, 'tăng đột biến funding')
    .replace(/price-volume/g, 'giá-khối lượng')
    .replace(/backtest/g, 'kiểm thử lịch sử')
    .replace(/baseline/g, 'mốc chuẩn')
    .replace(/Train cutoff/g, 'Mốc cắt huấn luyện')
    .replace(/train model/g, 'huấn luyện mô hình') || '';
  const scanModeLabels: Record<string, string> = {
    volatile: 'BIẾN ĐỘNG',
    gainers: 'TĂNG MẠNH',
    losers: 'GIẢM MẠNH',
    volume: 'KHỐI LƯỢNG',
    all: 'TẤT CẢ',
    manual: 'CÁ NHÂN',
  };
  const [data, setData] = useState<SystemHistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/system-history');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi tải dữ liệu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Đang tải lịch sử hệ thống...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-3">
        <XCircle className="w-8 h-8 text-red-400" />
        <p className="text-xs text-red-400">{error}</p>
        <button onClick={fetchData} className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-xs">
          Thử lại
        </button>
      </div>
    );
  }

  if (!data) return null;

  // Format helpers
  const fmtNum = (n: number | null | undefined) => {
    if (n == null) return '—';
    return n.toLocaleString('vi-VN');
  };
  const fmtTime = formatSystemDateTime;
  const fmtPct = (n: number | null | undefined) => {
    if (n == null) return '—';
    return `${(n * 100).toFixed(1)}%`;
  };

  // Scanner status
  const hb = data.scanner.heartbeat || {};
  const isOnline = hb.status === 'running';
  const lastCycle = data.scanner.last_cycle || {};

  // Chart data (signals per day, oldest first for chart)
  const signalsChart = [...data.signals_per_day].reverse().map(d => ({
    day: d.day.slice(5),
    signals: d.n_signals,
    telegram: d.n_telegram,
    hits: d.n_hit,
  }));

  const scanChart = [...data.scanner.scan_per_day].reverse().map(d => ({
    day: d.day.slice(5),
    cycles: d.n_cycles,
    symbols: d.n_symbols,
  }));

  // Total data rows
  const totalRows = data.data_stats.reduce((s, d) => s + d.rows, 0);
  const latestDataTime = data.data_stats
    .map(d => d.max_time)
    .filter(Boolean)
    .sort()
    .pop();

  // Table descriptions for tooltips
  const tableTooltips: Record<string, string> = {
    kline: 'Nến 5 phút từ Binance — dữ liệu thị trường gốc (OHLCV). Mỗi dòng = 1 nến của 1 mã.',
    aligned_5m: 'Nến đã chuẩn hóa theo thời điểm có sẵn — dùng để tính đặc trưng và nhãn, không nhìn trước dữ liệu tương lai.',
    feature_results: 'Vector đặc trưng đã tính cho mỗi mã tại từng thời điểm — đầu vào cho mô hình AI.',
    labels: 'Nhãn phân phối: 1 nếu coin giảm >= mục tiêu trong khung thời gian, 0 nếu không. Dữ liệu thực tế để huấn luyện.',
    raw_timeline: 'Dòng thời gian thô của mọi nguồn trước khi căn chỉnh — dùng để kiểm tra rò rỉ dữ liệu.',
    scan_results: 'Kết quả mỗi chu kỳ quét: điểm, khuyến nghị, giá, OI, funding... của mọi coin đã quét.',
    alert_history: 'Tín hiệu vượt ngưỡng cảnh báo đã ghi lại — kèm kết quả đúng/sai sau khi hết khung thời gian.',
    funding: 'Tỷ lệ funding theo thời gian — tín hiệu áp lực mua/bán trên hợp đồng tương lai.',
    open_interest: 'OI (USD) — tổng vị thế đang mở, tăng = dòng tiền vào, giảm = dòng tiền rút ra.',
    taker_volume: 'Khối lượng mua/bán chủ động — chênh lệch giữa bên mua và bên bán trên thị trường.',
    global_ratio: 'Tỷ lệ tài khoản mua/bán toàn thị trường — phản ánh tâm lý đám đông.',
    top_ratio: 'Tỷ lệ mua/bán của nhà giao dịch lớn — phản ánh vị thế của cá voi.',
    _coin_features: 'Bộ nhớ đệm đặc trưng nội bộ — không dùng trực tiếp cho môi trường thật.',
  };

  // ===== Freshness Health Check =====
  // Expected update frequency (minutes) per critical pipeline.
  // Status: green = fresh, yellow = aging (<=2×expected), red = stale (>2×expected), gray = no data.
  const PIPELINE_SPEC: Array<{
    table: string;
    label: string;
    expectedMin: number; // expected update interval in minutes
    onDemand?: boolean; // if true, no fresh data is normal (alerts)
    desc: string;
  }> = [
    { table: 'kline', label: 'Bộ thu thập nến', expectedMin: 5, desc: 'Nến 5 phút từ Binance. Phải cập nhật mỗi ~5 phút. Quá cũ → bộ thu thập dừng hoặc API Binance bị chặn.' },
    { table: 'aligned_5m', label: 'Căn chỉnh dữ liệu', expectedMin: 5, desc: 'Nến đã chuẩn hóa theo đúng thời điểm. Quá cũ → tác vụ căn chỉnh bị treo, không tính được đặc trưng/nhãn.' },
    { table: 'feature_results', label: 'Luồng đặc trưng', expectedMin: 15, desc: 'Vector đặc trưng tính từ aligned_5m. Quá cũ → tác vụ đặc trưng bị treo, bộ quét dùng dữ liệu cũ.' },
    { table: 'labels', label: 'Tạo nhãn', expectedMin: 1440, desc: 'Nhãn phân phối cần chờ khung thời gian (24–48 giờ) để hoàn tất. Quá cũ >2 ngày → tác vụ nhãn dừng, mô hình không tự học được.' },
    { table: 'scan_results', label: 'Bộ quét', expectedMin: 5, desc: 'Mỗi chu kỳ quét ghi vào scan_results. Quá cũ → bộ quét dừng, không có tín hiệu mới.' },
    { table: 'funding', label: 'Tỷ lệ funding', expectedMin: 480, desc: 'Tỷ lệ funding từ hợp đồng tương lai Binance, cập nhật mỗi 8 giờ. Quá cũ → tác vụ thu thập hằng ngày chưa chạy.' },
    { table: 'open_interest', label: 'OI', expectedMin: 15, desc: 'OI thay đổi mỗi 15 phút. Quá cũ → bộ thu thập OI bị treo.' },
    { table: 'taker_volume', label: 'Khối lượng chủ động', expectedMin: 15, desc: 'Khối lượng mua/bán chủ động mỗi 15 phút. Quá cũ → bộ thu thập bị treo.' },
    { table: 'global_ratio', label: 'Tỷ lệ mua/bán toàn thị trường', expectedMin: 15, desc: 'Tỷ lệ mua/bán toàn thị trường mỗi 15 phút. Quá cũ → bộ thu thập bị treo.' },
    { table: 'top_ratio', label: 'Tỷ lệ nhà giao dịch lớn', expectedMin: 15, desc: 'Tỷ lệ mua/bán của nhà giao dịch lớn mỗi 15 phút. Quá cũ → bộ thu thập bị treo.' },
    { table: 'alert_history', label: 'Cảnh báo Radar', expectedMin: 0, onDemand: true, desc: 'Chỉ ghi cảnh báo khi coin vượt ngưỡng. Không có cảnh báo mới là bình thường khi thị trường yên, không phải lỗi.' },
  ];

  // Parse both current API timestamps and older DuckDB strings.  The shared
  // helper treats legacy naive storage timestamps as UTC and always computes
  // age from the same absolute instant.
  const parseTimestamp = (value: string | null | undefined): number | null => {
    return parseSystemDate(value)?.getTime() ?? null;
  };

  // Compute age in minutes from max_time to generated_at
  const computeAgeMin = (maxTime: string | null | undefined, refIso: string): number | null => {
    const dataTimestamp = parseTimestamp(maxTime);
    const referenceTimestamp = parseTimestamp(refIso);
    if (dataTimestamp == null || referenceTimestamp == null) return null;
    const diffMs = referenceTimestamp - dataTimestamp;
    return Math.max(0, Math.round(diffMs / 60000));
  };

  const fmtAge = (min: number | null) => {
    if (min == null) return '—';
    if (min < 60) return `${min} phút`;
    if (min < 1440) return `${Math.round(min / 60)} giờ`;
    return `${Math.round(min / 1440)} ngày`;
  };

  const getStatus = (ageMin: number | null, expectedMin: number, onDemand?: boolean) => {
    if (onDemand) return 'ondemand';
    if (ageMin == null) return 'gray';
    if (ageMin <= expectedMin) return 'green';
    if (ageMin <= expectedMin * 2) return 'yellow';
    return 'red';
  };

  const statusStyles: Record<string, { dot: string; text: string; label: string; ring: string }> = {
    green: { dot: 'bg-emerald-400', text: 'text-emerald-400', label: 'MỚI', ring: 'border-emerald-500/30' },
    yellow: { dot: 'bg-amber-400', text: 'text-amber-400', label: 'ĐANG CŨ', ring: 'border-amber-500/30' },
    red: { dot: 'bg-red-400', text: 'text-red-400', label: 'QUÁ CŨ', ring: 'border-red-500/40' },
    gray: { dot: 'bg-slate-500', text: 'text-slate-400', label: 'CHƯA CÓ DỮ LIỆU', ring: 'border-slate-700' },
    ondemand: { dot: 'bg-sky-400', text: 'text-sky-400', label: 'THEO YÊU CẦU', ring: 'border-sky-500/30' },
  };

  const freshnessRows = PIPELINE_SPEC.map(spec => {
    const stat = data.data_stats.find(d => d.table === spec.table);
    const ageMin = computeAgeMin(stat?.max_time, data.generated_at);
    const status = getStatus(ageMin, spec.expectedMin, spec.onDemand);
    return { ...spec, maxTime: stat?.max_time, ageMin, status, rows: stat?.rows ?? 0 };
  });
  const nStale = freshnessRows.filter(r => r.status === 'red').length;
  const nAging = freshnessRows.filter(r => r.status === 'yellow').length;

  // ===== Guarded self-learning progress =====
  const selfLearning = data.self_learning;
  const trainingOutcomes = selfLearning?.training_outcomes ?? selfLearning?.outcomes ?? 0;
  const trainingPositiveEvents = selfLearning?.training_positive_events ?? selfLearning?.materialized_positive ?? 0;
  const latestSelfLearningRun = selfLearning?.latest_run ?? null;
  const selfLearningStatus = selfLearning?.status ?? 'not_ready';
  const selfLearningStatusMeta: Record<string, { label: string; text: string; border: string }> = {
    disabled: { label: 'TẮT', text: 'text-slate-400', border: 'border-slate-700' },
    not_ready: { label: 'CHỜ THÊM KẾT QUẢ', text: 'text-amber-400', border: 'border-amber-500/30' },
    skipped: { label: 'ĐÃ KIỂM TRA', text: 'text-sky-400', border: 'border-sky-500/30' },
    waiting_new_outcomes: { label: 'CHỜ DỮ LIỆU MỚI', text: 'text-sky-400', border: 'border-sky-500/30' },
    challenger_ready: { label: 'MÔ HÌNH THỬ THÁCH SẴN SÀNG', text: 'text-emerald-400', border: 'border-emerald-500/30' },
    gate_failed: { label: 'CỔNG KIỂM ĐỊNH KHÔNG ĐẠT', text: 'text-red-400', border: 'border-red-500/40' },
    blocked: { label: 'BỊ CHẶN', text: 'text-red-400', border: 'border-red-500/40' },
  };
  const selfLearningMeta = selfLearningStatusMeta[selfLearningStatus] ?? selfLearningStatusMeta.not_ready;
  const outcomeProgress = selfLearning
    ? Math.min(100, (trainingOutcomes / Math.max(1, selfLearning.min_training_outcomes)) * 100)
    : 0;
  const positiveProgress = selfLearning
    ? Math.min(100, (trainingPositiveEvents / Math.max(1, selfLearning.min_positive_events)) * 100)
    : 0;
  const gateChecks = Object.entries(latestSelfLearningRun?.gate?.checks ?? {});
  const gateLabels: Record<string, string> = {
    precision_improvement: 'Độ chính xác cải thiện',
    recall_regression: 'Tỷ lệ bắt không giảm quá mức',
    brier_regression: 'Điểm Brier không xấu hơn',
  };
  const runStatusLabel: Record<string, string> = {
    challenger_ready: 'Mô hình thử thách sẵn sàng',
    gate_failed: 'Cổng kiểm định không đạt',
    blocked: 'Bị chặn',
    skipped: 'Bỏ qua — chưa có dữ liệu mới',
    not_ready: 'Chưa đủ dữ liệu',
  };
  const flowStages = [
    { label: 'Dự đoán', detail: `${fmtNum(selfLearning?.predictions)} dự đoán`, done: (selfLearning?.predictions ?? 0) > 0 },
    { label: 'Kiểm tra thực tế', detail: `${fmtNum(trainingOutcomes)} kết quả train`, done: trainingOutcomes > 0 },
    { label: 'Huấn luyện mô hình thử thách', detail: latestSelfLearningRun?.challenger_model_id ? 'Đã tạo gói kết quả' : 'Lô có kiểm soát', done: Boolean(latestSelfLearningRun?.challenger_model_id) },
    { label: 'Kiểm định cổng', detail: latestSelfLearningRun?.gate ? (latestSelfLearningRun.gate.passed ? 'Đạt' : 'Không đạt') : 'Chưa chạy', done: Boolean(latestSelfLearningRun?.gate) },
    { label: 'Chờ duyệt', detail: latestSelfLearningRun?.challenger_model_id ? 'Cần người duyệt' : 'Không tự thăng hạng', done: Boolean(latestSelfLearningRun?.challenger_model_id && latestSelfLearningRun?.promotion?.requires_human_approval) },
  ];

  return (
    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <Activity className="w-3.5 h-3.5 text-amber-400" />
          LỊCH SỬ & DỮ LIỆU HỆ THỐNG
        </h3>
        <button onClick={fetchData} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10 flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> Tải lại
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        Cập nhật lúc (Hà Nội, UTC+7): <span className="text-slate-200 font-mono font-bold">{fmtTime(data.generated_at)}</span>
      </p>

      {/* ===== SECTION 0: FRESHNESS HEALTH CHECK ===== */}
      <section className={`bg-slate-950 border rounded-xl p-3 ${nStale > 0 ? 'border-red-500/40' : nAging > 0 ? 'border-amber-500/30' : 'border-emerald-500/30'}`}>
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Gauge className="w-3.5 h-3.5 text-amber-400" />
          KIỂM TRA ĐỘ MỚI DỮ LIỆU
          <InfoTip text="Kiểm tra độ mới của từng luồng dữ liệu. Mỗi luồng có tần suất cập nhật riêng. Nếu quá cũ, luồng đó có thể đang bị treo và cần kiểm tra nhật ký." />
          {nStale > 0 ? (
            <span className="ml-auto text-[10px] text-red-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nStale} quá cũ
            </span>
          ) : nAging > 0 ? (
            <span className="ml-auto text-[10px] text-amber-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nAging} đang cũ
            </span>
          ) : (
            <span className="ml-auto text-[10px] text-emerald-400 font-bold flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> TẤT CẢ ĐỀU MỚI
            </span>
          )}
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {freshnessRows.map(r => {
            const st = statusStyles[r.status];
            return (
              <div key={r.table} className={`bg-slate-900 border ${st.ring} rounded-lg p-2`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className={`w-2 h-2 rounded-full ${st.dot} shrink-0 ${r.status === 'red' ? 'animate-pulse' : ''}`} />
                    <span className="text-[11px] font-bold text-white truncate">{r.label}</span>
                    <InfoTip text={r.desc} />
                  </div>
                  <span className={`text-[9px] font-bold font-mono ${st.text} shrink-0`}>{st.label}</span>
                </div>
                <div className="grid grid-cols-3 gap-1 text-[10px]">
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">Mới nhất</div>
                    <div className={`font-mono font-bold ${r.status === 'red' ? 'text-red-400' : 'text-slate-200'}`}>
                      {r.maxTime ? fmtTime(r.maxTime) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">Tuổi</div>
                    <div className={`font-mono font-bold ${st.text}`}>{fmtAge(r.ageMin)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">Số dòng</div>
                    <div className="text-slate-300 font-mono">{fmtNum(r.rows)}</div>
                  </div>
                </div>
                {r.status === 'red' && (
                  <p className="text-[9px] text-red-400 mt-1 leading-relaxed">
                    ⚠ Luồng xử lý bị treo — cần kiểm tra nhật ký và khởi động lại tác vụ.
                  </p>
                )}
                {r.onDemand && r.status === 'ondemand' && (
                  <p className="text-[9px] text-slate-500 mt-1 italic">Theo yêu cầu: không có cảnh báo mới là bình thường.</p>
                )}
              </div>
            );
          })}
        </div>
        <p className="text-[9px] text-slate-500 mt-2 italic">
          Dự kiến: nến/căn chỉnh/đặc trưng/bộ quét ~5–15 phút • nhãn ~24 giờ (chờ khung thời gian) • cảnh báo theo yêu cầu. Di chuột <Info className="w-2.5 h-2.5 inline" /> để xem độ mới dự kiến của từng luồng.
        </p>
      </section>

      {/* ===== SECTION 1: DATA Stats ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Database className="w-3.5 h-3.5 text-sky-400" />
          DỮ LIỆU ĐÃ THU THẬP
          <InfoTip text="Tổng quan dung lượng dữ liệu trong DuckDB. Quan trọng nhất: 'Dữ liệu mới nhất' cho biết hệ thống có đang cập nhật không, và 'feature_results/labels' phải có max_time gần nhau (không rò rỉ dữ liệu tương lai)." />
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label="Tổng số dòng"
            value={fmtNum(totalRows)}
            valueClass="text-sky-400"
            highlight
            tooltip="Tổng số dòng dữ liệu trên tất cả bảng trong DuckDB. Đây là 'nguyên liệu' để huấn luyện AI và chạy bộ quét."
          />
          <StatCard
            label="Số bảng"
            value={data.data_stats.length}
            valueClass="text-slate-200"
            tooltip="Số bảng trong DuckDB — gồm bảng thị trường (kline, funding, OI...), đặc trưng, nhãn, scan_results, alert_history."
          />
          <StatCard
            label="Dữ liệu mới nhất"
            value={<span className="text-xs">{fmtTime(latestDataTime)}</span>}
            valueClass="text-emerald-400"
            highlight
            tooltip="Thời điểm mới nhất trên tất cả bảng. Nếu cũ hơn 1 giờ → bộ thu thập hoặc bộ quét đang bị treo. Mục tiêu: cập nhật liên tục theo thời gian thực."
          />
          <StatCard
            label="Đường dẫn cơ sở dữ liệu"
            value={<span className="text-[10px]">{data.db_path || 'chưa xác định'}</span>}
            valueClass="text-slate-300 truncate"
            tooltip="Tệp DuckDB chứa toàn bộ dữ liệu. Đường dẫn được cấu hình trong settings.scanner.db_path."
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[10px] text-slate-300 font-mono">
            <thead className="text-slate-400 uppercase border-b border-slate-800">
              <tr>
                <th className="p-1.5">Bảng</th>
                <th className="p-1.5">Số dòng</th>
                <th className="p-1.5">Cột thời gian</th>
                <th className="p-1.5">Cũ nhất</th>
                <th className="p-1.5">Mới nhất</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {data.data_stats.map(d => {
                const isImportant = ['feature_results', 'labels', 'kline', 'aligned_5m', 'scan_results', 'alert_history'].includes(d.table);
                return (
                  <tr key={d.table} className="hover:bg-slate-900/60">
                    <td className="p-1.5 text-white">
                      <span className="flex items-center gap-1">
                        {isImportant && <span className="text-amber-400">●</span>}
                        <span className={isImportant ? 'font-bold' : ''}>{d.table}</span>
                        {tableTooltips[d.table] && <InfoTip text={tableTooltips[d.table]} />}
                      </span>
                    </td>
                    <td className={`p-1.5 ${isImportant ? 'text-amber-400 font-bold' : 'text-amber-400/70'}`}>{fmtNum(d.rows)}</td>
                    <td className="p-1.5 text-slate-500">{d.ts_column || '—'}</td>
                    <td className="p-1.5 text-slate-400">{d.min_time ? fmtTime(d.min_time) : '—'}</td>
                    <td className="p-1.5 text-emerald-400 font-bold">{d.max_time ? fmtTime(d.max_time) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-[9px] text-slate-500 mt-2 italic">
          ● Bảng quan trọng (ảnh hưởng huấn luyện AI / bộ quét). Di chuột lên biểu tượng <Info className="w-2.5 h-2.5 inline" /> để xem mô tả từng bảng.
        </p>
      </section>

      {/* ===== SECTION 2: Scanner Activity ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Radar className="w-3.5 h-3.5 text-emerald-400" />
          HOẠT ĐỘNG BỘ QUÉT 24/7
          <InfoTip text="Bộ quét chạy nền, mỗi poll_minutes phút sẽ lấy giá Binance → tính điểm → ghi vào scan_results. Nếu 'Trạng thái' = ĐÃ DỪNG hoặc 'Quét lúc' cũ hơn 15 phút → bộ quét có thể đã dừng, cần khởi động lại." />
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label="Trạng thái"
            value={
              <span className="flex items-center gap-1">
                {isOnline ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {isOnline ? 'ĐANG CHẠY' : 'ĐÃ DỪNG'}
              </span>
            }
            valueClass={isOnline ? 'text-emerald-400' : 'text-red-400'}
            highlight
            tooltip="ĐANG CHẠY = trạng thái nhịp hoạt động là 'running' và thời điểm mới hơn 3×poll_interval. ĐÃ DỪNG = bộ quét đã dừng hoặc treo — cần kiểm tra nhật ký và khởi động lại."
          />
          <StatCard
            label="Chu kỳ mới nhất"
            value={`#${lastCycle.cycle ?? '—'}`}
            valueClass="text-amber-400"
            tooltip="Số thứ tự chu kỳ quét gần nhất. Mỗi chu kỳ = 1 lần bộ quét lấy toàn bộ giá và ghi kết quả. Tăng dần theo thời gian."
          />
          <StatCard
            label="Quét lúc"
            value={<span className="text-xs">{fmtTime(lastCycle.last_scan_time)}</span>}
            valueClass="text-slate-200"
            highlight
            tooltip="Thời gian chu kỳ quét gần nhất hoàn thành. Quan trọng: nếu cũ hơn 15 phút → bộ quét có thể đang bị treo."
          />
          <StatCard
            label="Mã/quét"
            value={fmtNum(lastCycle.n_symbols)}
            valueClass="text-sky-400"
            tooltip="Số coin được quét trong chu kỳ gần nhất. Phụ thuộc scan_mode: 'losers' = các mã giảm mạnh, 'gainers' = các mã tăng mạnh, 'all' = toàn bộ mã USDT."
          />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3 text-[10px]">
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">Nhịp hoạt động:</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{fmtTime(hb.timestamp)}</span>
            <InfoTip text="Thời điểm cuối cùng bộ quét ghi nhịp hoạt động. Dùng để kiểm tra bộ quét còn đang chạy hay không." />
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">Chế độ quét:</span>{' '}
            <span className="text-amber-400 font-mono uppercase font-bold">{scanModeLabels[data.scanner.scan_mode] ?? data.scanner.scan_mode}</span>
            <InfoTip text="losers = quét các coin giảm mạnh (dễ có phân phối), gainers = các mã tăng mạnh, all = toàn bộ cặp USDT. Có thể đổi trong phần đầu trang." />
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">Chu kỳ kiểm tra:</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{hb.poll_minutes || '?'} phút</span>
            <InfoTip text="Khoảng cách giữa 2 chu kỳ quét. Càng ngắn = phát hiện nhanh hơn nhưng tốn API rate limit. Mặc định 5 phút." />
          </div>
        </div>

        {/* Scan per day chart */}
        {scanChart.length > 0 ? (
          <div className="mt-3">
            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-sky-400" />
              Số chu kỳ quét & mã theo ngày (30 ngày gần nhất)
              <InfoTip text="Biểu đồ hoạt động bộ quét theo ngày. 'Chu kỳ' (xanh dương) = số lần quét, 'Mã coin' (xanh lá) = số mã duy nhất được quét. Nếu ngày nào = 0 → bộ quét không chạy ngày đó." />
            </h5>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={scanChart} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 9 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 9 }} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 11 }}
                  labelStyle={{ color: '#fbbf24' }}
                />
                <Bar dataKey="cycles" fill="#0ea5e9" name="Chu kỳ" radius={[3, 3, 0, 0]} />
                <Bar dataKey="symbols" fill="#10b981" name="Mã coin" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-[11px] text-slate-500 italic mt-2">Chưa có dữ liệu quét theo ngày.</p>
        )}
      </section>

      {/* ===== SECTION 3: AI Models Progress ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Cpu className="w-3.5 h-3.5 text-amber-400" />
          MÔ HÌNH AI & TIẾN BỘ
          <InfoTip text="Các mô hình AI đã huấn luyện và đóng băng để dùng cho bộ quét. Mỗi mô hình có đặc tả mục tiêu, mức lệch tối đa và khung thời gian riêng. Phần thử nghiệm cho biết số giả thuyết đã kiểm tra." />
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label="Mô hình đã đóng băng"
            value={data.models.length}
            valueClass="text-amber-400"
            tooltip="Số mô hình đã đóng băng trong artifacts/frozen_models/. Mỗi mô hình = 1 lần huấn luyện thành công với đặc tả nhãn cụ thể."
          />
          <StatCard
            label="Thử nghiệm"
            value={data.experiments.total}
            valueClass="text-sky-400"
            highlight
            tooltip="Tổng số thử nghiệm đã chạy (artifacts/exp_*.json). Mỗi thử nghiệm = 1 lần kiểm tra giả thuyết với kiểm định cuốn chiếu theo thời gian. Càng nhiều = càng nhiều thử nghiệm cải tiến."
          />
          <StatCard
            label="Mô hình bộ quét"
            value={<span className="text-[10px]">{data.current_scanner_model_id || 'chưa cài'}</span>}
            valueClass="text-emerald-400 truncate"
            highlight
            tooltip="Mã mô hình mà bộ quét đang dùng để chấm điểm. Nếu trống → bộ quét dùng quy tắc, không phải mô hình AI."
          />
          <StatCard
            label="Thử nghiệm mới nhất"
            value={<span className="text-[10px]">{data.experiments.latest?.artifact_id?.slice(-12) || '—'}</span>}
            valueClass="text-slate-300"
            tooltip="12 ký tự cuối của artifact_id thử nghiệm gần nhất. Cho biết hệ thống có đang được cải tiến liên tục không."
          />
        </div>

        {/* Latest experiment summary */}
        {data.experiments.latest && (
          <div className="bg-slate-900/60 border border-amber-500/20 rounded p-2 mb-3">
            <div className="text-[10px] text-slate-400 uppercase mb-1 flex items-center gap-1">
              <FlaskConical className="w-3 h-3 text-sky-400" />
              Thử nghiệm mới nhất
              <InfoTip text="Kết quả kiểm định theo thời gian của thử nghiệm gần nhất. Độ chính xác = phần trăm dự đoán giảm là đúng. Tỷ lệ bắt = phần trăm coin thực sự giảm được phát hiện. Cả hai càng cao càng tốt." />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[10px]">
              <div className="flex items-center gap-1">
                <span className="text-slate-500">Giả thuyết:</span>{' '}
                <span className="text-slate-300 font-mono font-bold">{data.experiments.latest.hypothesis_id || '—'}</span>
                <InfoTip text="Mã của giả thuyết đang kiểm tra — ví dụ hyp_label_v0_3_volatile_15 là nhãn v0.3 trên coin biến động, khung 15." />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-slate-500">Nhãn:</span>{' '}
                <span className="text-amber-400 font-mono font-bold">{data.experiments.latest.label_version || '—'}</span>
                <InfoTip text="Phiên bản đặc tả nhãn dùng để huấn luyện. v0.1 = 8%/4%/24h, v0.2 = 20%/10%/24h, v0.3 = 20%/10%/48h." />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-slate-500">Độ chính xác:</span>{' '}
                <span className="text-emerald-400 font-mono font-bold">{fmtPct(data.experiments.latest.precision_mean)}</span>
                <InfoTip text="% dự đoán 'sẽ giảm' mà thực sự giảm. Độ chính xác cao = ít báo sai, nhưng có thể bỏ sót. Mục tiêu ban đầu: >50%." />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-slate-500">Tỷ lệ bắt:</span>{' '}
                <span className="text-sky-400 font-mono font-bold">{fmtPct(data.experiments.latest.recall_mean)}</span>
                <InfoTip text="% coin thực sự giảm mà mô hình phát hiện được. Tỷ lệ bắt cao = bắt được nhiều lần phân phối, nhưng có thể báo sai nhiều. Cần cân bằng với độ chính xác." />
              </div>
              <div className="flex items-center gap-1">
                <span className="text-slate-500">Lượt chia:</span>{' '}
                <span className="text-slate-300 font-mono font-bold">{data.experiments.latest.n_valid_folds ?? '—'}</span>
                <InfoTip text="Số lần chia dữ liệu cuốn chiếu hợp lệ. Dữ liệu được huấn luyện trên quá khứ và kiểm tra lần lượt trên tương lai. Nhiều lần chia = kết quả ổn định hơn." />
              </div>
            </div>
          </div>
        )}

        {/* Models list */}
        {data.models.length === 0 ? (
          <p className="text-[11px] text-slate-500 italic">Chưa có mô hình đã đóng băng nào.</p>
        ) : (
          <div className="space-y-2">
            {data.models.map(m => (
              <div key={m.model_id} className={`bg-slate-900 border rounded-lg p-2.5 ${m.is_scanner_model ? 'border-emerald-500/40 ring-1 ring-emerald-500/20' : 'border-slate-800'}`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Lock className="w-3 h-3 text-amber-400 shrink-0" />
                    <span className="text-xs font-bold text-white truncate">{modelName(m.friendly_name)}</span>
                    {m.is_scanner_model && (
                      <span className="text-[9px] text-emerald-400 font-mono bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-500/30 flex items-center gap-0.5 shrink-0 font-bold">
                        <Trophy className="w-2.5 h-2.5" /> ĐANG QUÉT
                      </span>
                    )}
                  </div>
                  <span className="text-[9px] text-slate-500 font-mono shrink-0">{m.label_version}</span>
                </div>
                <p className="text-[10px] text-slate-400 mb-1.5 leading-relaxed">{modelDescription(m.description)}</p>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-1.5 text-[10px]">
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px] flex items-center gap-0.5">
                      Cỡ tập huấn luyện
                      <InfoTip text="Số mẫu dùng để huấn luyện mô hình. Càng nhiều càng ổn định, nhưng phải đảm bảo không rò rỉ dữ liệu tương lai." />
                    </div>
                    <div className="text-slate-200 font-mono font-bold">{fmtNum(m.train_size)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px] flex items-center gap-0.5">
                      Mẫu xả khi huấn luyện
                      <InfoTip text="Số mẫu dương (coin thực sự giảm >= mục tiêu) trong tập huấn luyện. Quan trọng: nếu quá ít (<50) → mô hình dễ học lệch." />
                    </div>
                    <div className="text-emerald-400 font-mono font-bold">{fmtNum(m.train_positives)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px] flex items-center gap-0.5">
                      Độ chính xác
                      <InfoTip text="% dự đoán 'sẽ giảm' mà đúng. Cao = ít báo sai. Đây là chỉ số quan trọng nhất cho bộ quét." />
                    </div>
                    <div className="text-amber-400 font-mono font-bold">{fmtPct(m.train_precision)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px] flex items-center gap-0.5">
                      Tỷ lệ bắt
                      <InfoTip text="% coin thực sự giảm mà mô hình bắt được. Cao = không bỏ sót các lần phân phối." />
                    </div>
                    <div className="text-sky-400 font-mono font-bold">{fmtPct(m.train_recall)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px] flex items-center gap-0.5">
                      Đặc trưng
                      <InfoTip text="Số đặc trưng đầu vào của mô hình. Nhiều đặc trưng = phức tạp hơn, dễ học lệch nếu dữ liệu ít." />
                    </div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px] flex items-center gap-0.5">
                      Ngưỡng
                      <InfoTip text="Ngưỡng xác suất để ra quyết định 'SHORT_CANDIDATE' (ứng viên bán khống). Điểm số >= ngưỡng → phát cảnh báo. Mặc định 0,60." />
                    </div>
                    <div className="text-amber-400 font-mono font-bold">{m.threshold.toFixed(2)}</div>
                  </div>
                </div>
                {m.label_spec && (
                  <div className="mt-1.5 flex gap-1.5 text-[9px] font-mono flex-wrap items-center">
                    <span className="bg-amber-950/60 text-amber-300 px-1.5 py-0.5 rounded border border-amber-500/20 font-bold" title="Mức giảm tối thiểu để coi là phân phối">
                      Mục tiêu: {m.label_spec.target_pct}
                    </span>
                    <span className="bg-sky-950/60 text-sky-300 px-1.5 py-0.5 rounded border border-sky-500/20 font-bold" title="Mức giảm bất lợi tối đa được phép trước khi chạm mục tiêu">
                      MAE: {m.label_spec.mae_pct}
                    </span>
                    <span className="bg-emerald-950/60 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/20 font-bold" title="Khoảng thời gian (tính bằng giờ) để chờ nhãn hoàn tất">
                      Khung: {m.label_spec.horizon_h}
                    </span>
                    <span className="text-slate-500 ml-auto flex items-center gap-0.5">
                      <Clock className="w-2.5 h-2.5 inline" /> {fmtTime(m.freeze_time)}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ===== SECTION 3.5: Guarded self-learning ===== */}
      <section className={`bg-slate-950 border rounded-xl p-3 ${selfLearningMeta.border}`}>
        <div className="flex items-start justify-between gap-2 mb-2">
          <div>
            <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-violet-400" />
              TỰ HỌC AI & THEO DÕI TIẾN TRÌNH
              <InfoTip text="Vòng lặp có kiểm soát: dự đoán → ghi nhận kết quả → huấn luyện mô hình thử thách → kiểm định giữ lại. Mô hình thử thách chỉ tạo gói kết quả; mô hình đang chạy không tự thay đổi." />
            </h4>
            <p className="text-[10px] text-slate-500 mt-1">
              Mỗi lần kiểm tra sau <span className="text-slate-300 font-mono">{selfLearning?.check_interval_cycles ?? '—'}</span> chu kỳ quét · mô hình chính hiện tại:{' '}
              <span className="text-emerald-400 font-mono">{selfLearning?.champion_model_id || 'chưa cài'}</span>
            </p>
          </div>
          <span className={`shrink-0 text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border ${selfLearningMeta.text} ${selfLearningMeta.border}`}>
            {selfLearningMeta.label}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
          <StatCard
            label="Kết quả hợp lệ"
            value={<span>{fmtNum(trainingOutcomes)} <span className="text-slate-500 font-normal">/ {fmtNum(selfLearning?.min_training_outcomes)}</span></span>}
            valueClass="text-amber-400"
            tooltip="Số dòng có feature + label lịch sử hoặc live outcome hợp lệ dùng được cho huấn luyện hybrid. Không dùng outcome chưa kết thúc horizon hoặc prediction invalid."
          />
          <StatCard
            label="Kết quả mới"
            value={fmtNum(selfLearning?.new_outcomes)}
            valueClass="text-sky-400"
            tooltip="Ước tính số kết quả mới kể từ lần huấn luyện gần nhất; cần đạt số tối thiểu để tránh huấn luyện lại cùng dữ liệu."
          />
          <StatCard
            label="Sự kiện dương"
            value={<span>{fmtNum(trainingPositiveEvents)} <span className="text-slate-500 font-normal">/ {fmtNum(selfLearning?.min_positive_events)}</span></span>}
            valueClass="text-emerald-400"
            tooltip="Nhãn = 1 trong tập huấn luyện hybrid. Đây là điều kiện tối thiểu để mô hình thử thách có đủ tín hiệu dương."
          />
          <StatCard
            label="Đang chờ kết quả"
            value={fmtNum(selfLearning?.pending)}
            valueClass={selfLearning?.pending ? 'text-amber-400' : 'text-slate-300'}
            tooltip="Dự đoán đã hết khung thời gian nhưng chưa ghi nhận kết quả. Số lượng chờ cao nghĩa là vòng phản hồi chưa khép kín."
          />
          <StatCard
            label="Lần chạy gần nhất"
            value={<span className="text-[10px]">{fmtTime(selfLearning?.last_run_at)}</span>}
            valueClass="text-slate-300"
            tooltip="Thời điểm bộ máy chạy tự học AI gần nhất. Xem báo cáo chi tiết trong lịch sử bên dưới."
          />
        </div>

        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="bg-slate-900 rounded p-1.5">
            <div className="flex justify-between text-[9px] text-slate-400 mb-1">
              <span>Đủ dữ liệu huấn luyện</span><span className="font-mono text-amber-400">{outcomeProgress.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden"><div className="h-full bg-amber-400 rounded-full" style={{ width: `${outcomeProgress}%` }} /></div>
          </div>
          <div className="bg-slate-900 rounded p-1.5">
            <div className="flex justify-between text-[9px] text-slate-400 mb-1">
              <span>Đủ sự kiện dương</span><span className="font-mono text-emerald-400">{positiveProgress.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden"><div className="h-full bg-emerald-400 rounded-full" style={{ width: `${positiveProgress}%` }} /></div>
          </div>
        </div>

        <div className="text-[9px] text-slate-500 mb-2">
          Nguồn huấn luyện: <span className="text-slate-300 font-mono">{fmtNum(selfLearning?.historical_outcomes)} lịch sử</span> + <span className="text-sky-300 font-mono">{fmtNum(selfLearning?.live_outcomes)} live</span> · cửa sổ gần đây <span className="text-amber-300 font-mono">{selfLearning?.recent_window_days ?? '—'} ngày</span>, trọng số <span className="text-amber-300 font-mono">×{selfLearning?.recent_sample_weight ?? '—'}</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-1.5 mb-3">
          {flowStages.map((stage, index) => (
            <div key={stage.label} className={`rounded border p-1.5 ${stage.done ? 'border-emerald-500/30 bg-emerald-950/20' : 'border-slate-800 bg-slate-900/60'}`}>
              <div className="flex items-center gap-1 text-[9px] font-bold">
                {stage.done ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <span className="w-3 h-3 rounded-full border border-slate-600 text-[8px] text-slate-500 flex items-center justify-center">{index + 1}</span>}
                <span className={stage.done ? 'text-emerald-300' : 'text-slate-400'}>{stage.label}</span>
              </div>
              <div className="text-[9px] text-slate-500 mt-1 truncate" title={stage.detail}>{stage.detail}</div>
            </div>
          ))}
        </div>

        {latestSelfLearningRun && (latestSelfLearningRun.champion_metrics || latestSelfLearningRun.challenger_metrics) && (
          <div className="bg-slate-900/70 border border-violet-500/20 rounded p-2 mb-3">
            <div className="text-[10px] text-slate-400 uppercase mb-1.5 flex items-center gap-1">
              <FlaskConical className="w-3 h-3 text-violet-400" />
              Kiểm định giữ lại · {runStatusLabel[latestSelfLearningRun.status] ?? latestSelfLearningRun.status}
            </div>
            <div className="grid grid-cols-3 gap-2 text-[10px]">
              <div><div className="text-slate-500">Độ chính xác</div><div className="font-mono"><span className="text-slate-300">{fmtPct(latestSelfLearningRun.champion_metrics?.precision)}</span> <span className="text-slate-600">→</span> <span className="text-emerald-400 font-bold">{fmtPct(latestSelfLearningRun.challenger_metrics?.precision)}</span></div></div>
              <div><div className="text-slate-500">Tỷ lệ bắt</div><div className="font-mono"><span className="text-slate-300">{fmtPct(latestSelfLearningRun.champion_metrics?.recall)}</span> <span className="text-slate-600">→</span> <span className="text-sky-400 font-bold">{fmtPct(latestSelfLearningRun.challenger_metrics?.recall)}</span></div></div>
              <div><div className="text-slate-500">Điểm Brier</div><div className="font-mono"><span className="text-slate-300">{latestSelfLearningRun.champion_metrics?.brier?.toFixed(3) ?? '—'}</span> <span className="text-slate-600">→</span> <span className="text-amber-400 font-bold">{latestSelfLearningRun.challenger_metrics?.brier?.toFixed(3) ?? '—'}</span></div></div>
            </div>
            {gateChecks.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-1.5 mt-2">
                {gateChecks.map(([key, check]) => (
                  <div key={key} className="flex items-center gap-1 text-[9px]">
                    {check.passed ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-red-400" />}
                    <span className="text-slate-400">{gateLabels[key] ?? key}</span>
                    <span className={`font-mono ml-auto ${check.passed ? 'text-emerald-400' : 'text-red-400'}`}>{fmtPct(check.actual)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {(selfLearning?.recent_runs ?? []).length > 0 ? (
          <div className="overflow-x-auto">
            <div className="text-[10px] text-slate-400 uppercase mb-1 flex items-center gap-1"><Clock className="w-3 h-3" /> Lịch sử tự học AI</div>
            <table className="w-full text-[9px]">
              <thead><tr className="text-slate-500 border-b border-slate-800"><th className="text-left p-1">Thời gian</th><th className="text-left p-1">Trạng thái</th><th className="text-right p-1">Độ chính xác</th><th className="text-right p-1">Mô hình thử thách</th></tr></thead>
              <tbody>
                {(selfLearning?.recent_runs ?? []).slice(0, 5).map(run => (
                  <tr key={run.run_id} className="border-b border-slate-900">
                    <td className="p-1 text-slate-400 font-mono">{fmtTime(run.completed_at || run.started_at)}</td>
                    <td className={`p-1 font-bold ${run.status === 'challenger_ready' ? 'text-emerald-400' : run.status === 'gate_failed' || run.status === 'blocked' ? 'text-red-400' : 'text-amber-400'}`}>{runStatusLabel[run.status] ?? run.status}</td>
                    <td className="p-1 text-right font-mono text-slate-300">{fmtPct(run.challenger_metrics?.precision)}</td>
                    <td className="p-1 text-right font-mono text-slate-500">{run.challenger_model_id ? run.challenger_model_id.slice(-12) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-[10px] text-slate-500 italic">Chưa có báo cáo tự học AI. Khi đủ kết quả, hệ thống sẽ ghi lại từng lần huấn luyện và kiểm định tại đây.</p>
        )}

        <div className="mt-2 flex items-start gap-1.5 rounded border border-amber-500/20 bg-amber-950/20 p-1.5 text-[9px] text-amber-300">
          <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
          <span><strong>Chế độ an toàn:</strong> tự động thăng hạng đang TẮT. Mô hình thử thách phải qua kiểm định và được người vận hành duyệt trước khi trở thành mô hình chính; bộ quét hiện vẫn dùng mô hình đã đóng băng màu xanh ở trên.</span>
        </div>
      </section>

      {/* ===== SECTION 4: Radar Signals per Day ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Layers className="w-3.5 h-3.5 text-red-400" />
          RADAR: TÍN HIỆU PHÁT HIỆN THEO NGÀY
          <InfoTip text="Số tín hiệu radar phát hiện theo ngày. 'Tín hiệu' = coin có điểm vượt ngưỡng. 'Telegram' = số cảnh báo đã gửi qua Telegram. 'Thực xả' = số cảnh báo mà coin thực sự giảm >= mục tiêu trong khung thời gian — đây là chỉ số đo độ chính xác thực tế." />
        </h4>
        {signalsChart.length === 0 ? (
          <p className="text-[11px] text-slate-500 italic">
            Chưa có tín hiệu nào trong alert_history. Bộ quét sẽ tự ghi khi phát hiện coin có điểm vượt ngưỡng.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-2 mb-3">
              <StatCard
                label="Tổng tín hiệu"
                value={data.signals_per_day.reduce((s, d) => s + d.n_signals, 0)}
                valueClass="text-amber-400"
                tooltip="Tổng số tín hiệu radar phát hiện trong 30 ngày qua. Mỗi tín hiệu = 1 coin có điểm vượt ngưỡng cảnh báo."
              />
              <StatCard
                label="Telegram đã gửi"
                value={data.signals_per_day.reduce((s, d) => s + d.n_telegram, 0)}
                valueClass="text-sky-400"
                tooltip="Số cảnh báo đã gửi qua Telegram (sau thời gian chờ). Có thể < tổng tín hiệu do thời gian chờ giúp tránh gửi quá nhiều."
              />
              <StatCard
                label="Thực xả"
                value={data.signals_per_day.reduce((s, d) => s + d.n_hit, 0)}
                valueClass="text-emerald-400"
                highlight
                tooltip="Số cảnh báo mà coin thực sự giảm >= target_drawdown trong khung thời gian. Đây là chỉ số đo độ chính xác THỰC TẾ của radar. Thực xả/cảnh báo = độ chính xác thực nghiệm."
              />
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={signalsChart} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 9 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 9 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 11 }}
                  labelStyle={{ color: '#fbbf24' }}
                />
                <ReferenceLine y={0} stroke="#334155" />
                <Bar dataKey="signals" fill="#f59e0b" name="Tín hiệu" radius={[3, 3, 0, 0]} />
                <Bar dataKey="telegram" fill="#0ea5e9" name="Telegram" radius={[3, 3, 0, 0]} />
                <Bar dataKey="hits" fill="#10b981" name="Thực xả" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex gap-3 justify-center text-[10px] mt-1">
              <span className="flex items-center gap-1"><span className="w-2 h-2 bg-amber-500 rounded" />Tín hiệu</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 bg-sky-500 rounded" />Telegram</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 bg-emerald-500 rounded" />Thực xả</span>
            </div>
            <p className="text-[9px] text-slate-500 mt-2 italic text-center">
              Tỷ lệ <span className="text-emerald-400 font-bold">Thực xả / Telegram</span> = độ chính xác thực nghiệm của radar. Mục tiêu ban đầu: &gt;50%.
            </p>
          </>
        )}
      </section>
    </div>
  );
};
