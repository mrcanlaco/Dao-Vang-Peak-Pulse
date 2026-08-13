import React, { useState, useEffect } from 'react';
import type { SystemHistoryData } from '../types';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import {
  Database, Radar, Cpu, Activity, CheckCircle2, XCircle,
  RefreshCw, TrendingUp, Layers, Lock, Trophy, Info, Gauge, AlertTriangle,
} from 'lucide-react';
import { formatSystemDateTime, parseSystemDate } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';

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
  const { language } = useTranslation();
  const isEn = language === 'en';

  const modelName = (name?: string) => {
    if (!name) return isEn ? 'Model' : 'Mô hình';
    return isEn ? name : name.replace(/^Frozen LR/, 'Hồi quy logistic đã đóng băng');
  };

  const modelDescription = (description?: string) => {
    if (!description) return '';
    if (isEn) return description;
    return description
      .replace(/Logistic Regression/g, 'Hồi quy logistic')
      .replace(/rule-based/g, 'theo quy tắc')
      .replace(/funding spike/g, 'tăng đột biến funding')
      .replace(/price-volume/g, 'giá-khối lượng')
      .replace(/backtest/g, 'kiểm thử lịch sử')
      .replace(/baseline/g, 'mốc chuẩn')
      .replace(/Train cutoff/g, 'Mốc cắt huấn luyện')
      .replace(/train model/g, 'huấn luyện mô hình');
  };

  const scanModeLabels: Record<string, string> = {
    volatile: isEn ? 'VOLATILE' : 'BIẾN ĐỘNG',
    gainers: isEn ? 'TOP GAINERS' : 'TĂNG MẠNH',
    losers: isEn ? 'TOP LOSERS' : 'GIẢM MẠNH',
    volume: isEn ? 'VOLUME LEADERS' : 'KHỐI LƯỢNG',
    all: isEn ? 'ALL COINS' : 'TẤT CẢ',
    manual: isEn ? 'CUSTOM' : 'CÁ NHÂN',
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
      setError(err instanceof Error ? err.message : (isEn ? 'Failed to load telemetry' : 'Lỗi tải dữ liệu'));
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
          {isEn ? 'Loading system telemetry and logs...' : 'Đang tải lịch sử hệ thống...'}
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
          {isEn ? 'Retry' : 'Thử lại'}
        </button>
      </div>
    );
  }

  if (!data) return null;

  const fmtNum = (n: number | null | undefined) => {
    if (n == null) return '—';
    return n.toLocaleString(isEn ? 'en-US' : 'vi-VN');
  };
  const fmtTime = formatSystemDateTime;
  const fmtPct = (n: number | null | undefined) => {
    if (n == null) return '—';
    return `${(n * 100).toFixed(1)}%`;
  };

  const hb = data.scanner.heartbeat || {};
  const isOnline = hb.status === 'running';
  const lastCycle = data.scanner.last_cycle || {};

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

  const totalRows = data.data_stats.reduce((s, d) => s + d.rows, 0);
  const latestDataTime = data.data_stats
    .map(d => d.max_time)
    .filter(Boolean)
    .sort()
    .pop();

  const tableTooltips: Record<string, string> = {
    kline: isEn ? '5-minute candles from Binance (OHLCV raw market data).' : 'Nến 5 phút từ Binance — dữ liệu thị trường gốc (OHLCV). Mỗi dòng = 1 nến của 1 mã.',
    aligned_5m: isEn ? 'Synchronized 5m candles at available timestamps for zero lookahead.' : 'Nến đã chuẩn hóa theo thời điểm có sẵn — dùng để tính đặc trưng và nhãn, không nhìn trước dữ liệu tương lai.',
    feature_results: isEn ? 'Calculated ML feature vectors across time horizons.' : 'Vector đặc trưng đã tính cho mỗi mã tại từng thời điểm — đầu vào cho mô hình AI.',
    labels: isEn ? 'Distribution ground truth labels (1 = dump ≥ 8%, 0 = otherwise).' : 'Nhãn phân phối: 1 nếu coin giảm >= mục tiêu trong khung thời gian, 0 nếu không. Dữ liệu thực tế để huấn luyện.',
    scan_results: isEn ? 'Per-cycle scan scores, indicators, and recommendations.' : 'Kết quả mỗi chu kỳ quét: điểm, khuyến nghị, giá, OI, funding... của mọi coin đã quét.',
    alert_history: isEn ? 'Radar alerts logged above threshold with verification outcomes.' : 'Tín hiệu vượt ngưỡng cảnh báo đã ghi lại — kèm kết quả đúng/sai sau khi hết khung thời gian.',
    funding: isEn ? 'Funding rate time series from Binance USD-M futures.' : 'Tỷ lệ funding theo thời gian — tín hiệu áp lực mua/bán trên hợp đồng tương lai.',
    open_interest: isEn ? 'Open Interest (USD) position tracking.' : 'OI (USD) — tổng vị thế đang mở, tăng = dòng tiền vào, giảm = dòng tiền rút ra.',
    taker_volume: isEn ? 'Taker buy / sell active volume metrics.' : 'Khối lượng mua/bán chủ động — chênh lệch giữa bên mua và bên bán trên thị trường.',
  };

  const PIPELINE_SPEC: Array<{
    table: string;
    label: string;
    expectedMin: number;
    onDemand?: boolean;
    desc: string;
  }> = [
    { table: 'kline', label: isEn ? 'Candle Collector' : 'Bộ thu thập nến', expectedMin: 5, desc: isEn ? '5m Binance candles. Updated ~5m.' : 'Nến 5 phút từ Binance. Phải cập nhật mỗi ~5 phút.' },
    { table: 'aligned_5m', label: isEn ? 'Timeline Aligner' : 'Căn chỉnh dữ liệu', expectedMin: 5, desc: isEn ? 'Normalized 5m timestamps for lookahead safety.' : 'Nến đã chuẩn hóa theo đúng thời điểm.' },
    { table: 'feature_results', label: isEn ? 'Feature Pipeline' : 'Luồng đặc trưng', expectedMin: 15, desc: isEn ? 'Computed feature vectors for model scoring.' : 'Vector đặc trưng tính từ aligned_5m.' },
    { table: 'labels', label: isEn ? 'Label Generator' : 'Tạo nhãn', expectedMin: 1440, desc: isEn ? 'Requires 24-48h horizon to evaluate ground truth.' : 'Nhãn phân phối cần chờ khung thời gian (24–48 giờ) để hoàn tất.' },
    { table: 'scan_results', label: isEn ? 'Scanner Loop' : 'Bộ quét', expectedMin: 5, desc: isEn ? 'Outputs scores each cycle to scan_results.' : 'Mỗi chu kỳ quét ghi vào scan_results.' },
    { table: 'funding', label: isEn ? 'Funding Rate' : 'Tỷ lệ funding', expectedMin: 480, desc: isEn ? 'Binance futures funding rate every 8 hours.' : 'Tỷ lệ funding từ hợp đồng tương lai Binance, cập nhật mỗi 8 giờ.' },
    { table: 'open_interest', label: 'OI', expectedMin: 15, desc: isEn ? 'Open Interest snapshot every 15 min.' : 'OI thay đổi mỗi 15 phút.' },
    { table: 'taker_volume', label: isEn ? 'Taker Volume' : 'Khối lượng chủ động', expectedMin: 15, desc: isEn ? 'Taker volume delta every 15 min.' : 'Khối lượng mua/bán chủ động mỗi 15 phút.' },
    { table: 'alert_history', label: isEn ? 'Radar Alerts' : 'Cảnh báo Radar', expectedMin: 0, onDemand: true, desc: isEn ? 'Recorded only when symbols exceed threshold.' : 'Chỉ ghi cảnh báo khi coin vượt ngưỡng.' },
  ];

  const parseTimestamp = (value: string | null | undefined): number | null => {
    return parseSystemDate(value)?.getTime() ?? null;
  };

  const computeAgeMin = (maxTime: string | null | undefined, refIso: string): number | null => {
    const dataTimestamp = parseTimestamp(maxTime);
    const referenceTimestamp = parseTimestamp(refIso);
    if (dataTimestamp == null || referenceTimestamp == null) return null;
    const diffMs = referenceTimestamp - dataTimestamp;
    return Math.max(0, Math.round(diffMs / 60000));
  };

  const fmtAge = (min: number | null) => {
    if (min == null) return '—';
    if (min < 60) return isEn ? `${min}m` : `${min} phút`;
    if (min < 1440) return isEn ? `${Math.round(min / 60)}h` : `${Math.round(min / 60)} giờ`;
    return isEn ? `${Math.round(min / 1440)}d` : `${Math.round(min / 1440)} ngày`;
  };

  const getStatus = (ageMin: number | null, expectedMin: number, onDemand?: boolean) => {
    if (onDemand) return 'ondemand';
    if (ageMin == null) return 'gray';
    if (ageMin <= expectedMin) return 'green';
    if (ageMin <= expectedMin * 2) return 'yellow';
    return 'red';
  };

  const statusStyles: Record<string, { dot: string; text: string; label: string; ring: string }> = {
    green: { dot: 'bg-emerald-400', text: 'text-emerald-400', label: isEn ? 'FRESH' : 'MỚI', ring: 'border-emerald-500/30' },
    yellow: { dot: 'bg-amber-400', text: 'text-amber-400', label: isEn ? 'AGING' : 'ĐANG CŨ', ring: 'border-amber-500/30' },
    red: { dot: 'bg-red-400', text: 'text-red-400', label: isEn ? 'STALE' : 'QUÁ CŨ', ring: 'border-red-500/40' },
    gray: { dot: 'bg-slate-500', text: 'text-slate-400', label: isEn ? 'NO DATA' : 'CHƯA CÓ DỮ LIỆU', ring: 'border-slate-700' },
    ondemand: { dot: 'bg-sky-400', text: 'text-sky-400', label: isEn ? 'ON DEMAND' : 'THEO YÊU CẦU', ring: 'border-sky-500/30' },
  };

  const freshnessRows = PIPELINE_SPEC.map(spec => {
    const stat = data.data_stats.find(d => d.table === spec.table);
    const ageMin = computeAgeMin(stat?.max_time, data.generated_at);
    const status = getStatus(ageMin, spec.expectedMin, spec.onDemand);
    return { ...spec, maxTime: stat?.max_time, ageMin, status, rows: stat?.rows ?? 0 };
  });
  const nStale = freshnessRows.filter(r => r.status === 'red').length;
  const nAging = freshnessRows.filter(r => r.status === 'yellow').length;

  return (
    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <Activity className="w-3.5 h-3.5 text-amber-400" />
          {isEn ? 'SYSTEM TELEMETRY & DATA LAKE AUDIT' : 'LỊCH SỬ & DỮ LIỆU HỆ THỐNG'}
        </h3>
        <button onClick={fetchData} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10 flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> {isEn ? 'Reload' : 'Tải lại'}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {isEn ? 'Report generated at (UTC+7):' : 'Cập nhật lúc (Hà Nội, UTC+7):'} <span className="text-slate-200 font-mono font-bold">{fmtTime(data.generated_at)}</span>
      </p>

      {/* ===== SECTION 0: FRESHNESS HEALTH CHECK ===== */}
      <section className={`bg-slate-950 border rounded-xl p-3 ${nStale > 0 ? 'border-red-500/40' : nAging > 0 ? 'border-amber-500/30' : 'border-emerald-500/30'}`}>
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Gauge className="w-3.5 h-3.5 text-amber-400" />
          {isEn ? 'DATA FRESHNESS & PIPELINE HEALTH' : 'KIỂM TRA ĐỘ MỚI DỮ LIỆU'}
          <InfoTip text={isEn ? 'Monitors each pipeline ingestion table. Red indicates stale feeds requiring log inspection.' : 'Kiểm tra độ mới của từng luồng dữ liệu. Mỗi luồng có tần suất cập nhật riêng.'} />
          {nStale > 0 ? (
            <span className="ml-auto text-[10px] text-red-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nStale} {isEn ? 'stale' : 'quá cũ'}
            </span>
          ) : nAging > 0 ? (
            <span className="ml-auto text-[10px] text-amber-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nAging} {isEn ? 'aging' : 'đang cũ'}
            </span>
          ) : (
            <span className="ml-auto text-[10px] text-emerald-400 font-bold flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> {isEn ? 'ALL PIPELINES FRESH' : 'TẤT CẢ ĐỀU MỚI'}
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
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Latest' : 'Mới nhất'}</div>
                    <div className={`font-mono font-bold ${r.status === 'red' ? 'text-red-400' : 'text-slate-200'}`}>
                      {r.maxTime ? fmtTime(r.maxTime) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Age' : 'Tuổi'}</div>
                    <div className={`font-mono font-bold ${st.text}`}>{fmtAge(r.ageMin)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Rows' : 'Số dòng'}</div>
                    <div className="text-slate-300 font-mono">{fmtNum(r.rows)}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ===== SECTION 1: DATA Stats ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Database className="w-3.5 h-3.5 text-sky-400" />
          {isEn ? 'DUCKDB DATA LAKE STATS' : 'DỮ LIỆU ĐÃ THU THẬP'}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={isEn ? 'Total Rows' : 'Tổng số dòng'}
            value={fmtNum(totalRows)}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={isEn ? 'Tables' : 'Số bảng'}
            value={data.data_stats.length}
            valueClass="text-slate-200"
          />
          <StatCard
            label={isEn ? 'Latest Data' : 'Dữ liệu mới nhất'}
            value={<span className="text-xs">{fmtTime(latestDataTime)}</span>}
            valueClass="text-emerald-400"
            highlight
          />
          <StatCard
            label={isEn ? 'Database Path' : 'Đường dẫn cơ sở dữ liệu'}
            value={<span className="text-[10px]">{data.db_path || '—'}</span>}
            valueClass="text-slate-300 truncate"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[10px] text-slate-300 font-mono">
            <thead className="text-slate-400 uppercase border-b border-slate-800">
              <tr>
                <th className="p-1.5">{isEn ? 'Table' : 'Bảng'}</th>
                <th className="p-1.5">{isEn ? 'Rows' : 'Số dòng'}</th>
                <th className="p-1.5">{isEn ? 'Time Column' : 'Cột thời gian'}</th>
                <th className="p-1.5">{isEn ? 'Earliest' : 'Cũ nhất'}</th>
                <th className="p-1.5">{isEn ? 'Latest' : 'Mới nhất'}</th>
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
      </section>

      {/* ===== SECTION 2: Scanner Activity ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Radar className="w-3.5 h-3.5 text-emerald-400" />
          {isEn ? '24/7 SCANNER DAEMON TELEMETRY' : 'HOẠT ĐỘNG BỘ QUÉT 24/7'}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={isEn ? 'Status' : 'Trạng thái'}
            value={
              <span className="flex items-center gap-1">
                {isOnline ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {isOnline ? (isEn ? 'ONLINE' : 'ĐANG CHẠY') : (isEn ? 'OFFLINE' : 'ĐÃ DỪNG')}
              </span>
            }
            valueClass={isOnline ? 'text-emerald-400' : 'text-red-400'}
            highlight
          />
          <StatCard
            label={isEn ? 'Latest Cycle' : 'Chu kỳ mới nhất'}
            value={`#${lastCycle.cycle ?? '—'}`}
            valueClass="text-amber-400"
          />
          <StatCard
            label={isEn ? 'Last Scan Time' : 'Quét lúc'}
            value={<span className="text-xs">{fmtTime(lastCycle.last_scan_time)}</span>}
            valueClass="text-slate-200"
            highlight
          />
          <StatCard
            label={isEn ? 'Symbols / Cycle' : 'Mã/quét'}
            value={fmtNum(lastCycle.n_symbols)}
            valueClass="text-sky-400"
          />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3 text-[10px]">
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{isEn ? 'Heartbeat:' : 'Nhịp hoạt động:'}</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{fmtTime(hb.timestamp)}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{isEn ? 'Scan Mode:' : 'Chế độ quét:'}</span>{' '}
            <span className="text-amber-400 font-mono uppercase font-bold">{scanModeLabels[data.scanner.scan_mode] ?? data.scanner.scan_mode}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{isEn ? 'Poll Interval:' : 'Chu kỳ kiểm tra:'}</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{hb.poll_minutes || '?'} {isEn ? 'min' : 'phút'}</span>
          </div>
        </div>

        {scanChart.length > 0 && (
          <div className="mt-3">
            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-sky-400" />
              {isEn ? 'Daily Scan Cycles & Unique Symbols (Past 30 Days)' : 'Số chu kỳ quét & mã theo ngày (30 ngày gần nhất)'}
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
                <Bar dataKey="cycles" fill="#0ea5e9" name={isEn ? 'Cycles' : 'Chu kỳ'} radius={[3, 3, 0, 0]} />
                <Bar dataKey="symbols" fill="#10b981" name={isEn ? 'Symbols' : 'Mã coin'} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* ===== SECTION 3: AI Models Progress ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Cpu className="w-3.5 h-3.5 text-amber-400" />
          {isEn ? 'AI PREDICTIVE MODELS & ACTIVE DEPLOYMENT' : 'MÔ HÌNH AI & TIẾN BỘ'}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={isEn ? 'Frozen Models' : 'Mô hình đã đóng băng'}
            value={data.models.length}
            valueClass="text-amber-400"
          />
          <StatCard
            label={isEn ? 'Total Experiments' : 'Thử nghiệm'}
            value={data.experiments.total}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={isEn ? 'Active Scanner Model' : 'Mô hình bộ quét'}
            value={<span className="text-[10px]">{data.current_scanner_model_id || (isEn ? 'Rules-based' : 'chưa cài')}</span>}
            valueClass="text-emerald-400 truncate"
            highlight
          />
          <StatCard
            label={isEn ? 'Latest Artifact' : 'Thử nghiệm mới nhất'}
            value={<span className="text-[10px]">{data.experiments.latest?.artifact_id?.slice(-12) || '—'}</span>}
            valueClass="text-slate-300"
          />
        </div>

        {/* Models list */}
        {data.models.length > 0 && (
          <div className="space-y-2">
            {data.models.map(m => (
              <div key={m.model_id} className={`bg-slate-900 border rounded-lg p-2.5 ${m.is_scanner_model ? 'border-emerald-500/40 ring-1 ring-emerald-500/20' : 'border-slate-800'}`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Lock className="w-3 h-3 text-amber-400 shrink-0" />
                    <span className="text-xs font-bold text-white truncate">{modelName(m.friendly_name)}</span>
                    {m.is_scanner_model && (
                      <span className="text-[9px] text-emerald-400 font-mono bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-500/30 flex items-center gap-0.5 shrink-0 font-bold">
                        <Trophy className="w-2.5 h-2.5" /> {isEn ? 'ACTIVE SCANNER' : 'ĐANG QUÉT'}
                      </span>
                    )}
                  </div>
                  <span className="text-[9px] text-slate-500 font-mono shrink-0">{m.label_version}</span>
                </div>
                <p className="text-[10px] text-slate-400 mb-1.5 leading-relaxed">{modelDescription(m.description)}</p>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-1.5 text-[10px]">
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Train Size' : 'Cỡ tập huấn luyện'}</div>
                    <div className="text-slate-200 font-mono font-bold">{fmtNum(m.train_size)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Positives' : 'Mẫu xả khi huấn luyện'}</div>
                    <div className="text-emerald-400 font-mono font-bold">{fmtNum(m.train_positives)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Precision' : 'Độ chính xác'}</div>
                    <div className="text-amber-400 font-mono font-bold">{fmtPct(m.train_precision)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Recall' : 'Tỷ lệ bắt'}</div>
                    <div className="text-sky-400 font-mono font-bold">{fmtPct(m.train_recall)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Features' : 'Đặc trưng'}</div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{isEn ? 'Threshold' : 'Ngưỡng'}</div>
                    <div className="text-amber-400 font-mono font-bold">{m.threshold.toFixed(2)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ===== SECTION 4: Radar Signals per Day ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Layers className="w-3.5 h-3.5 text-red-400" />
          {isEn ? 'RADAR: SIGNALS DETECTED PER DAY' : 'RADAR: TÍN HIỆU PHÁT HIỆN THEO NGÀY'}
        </h4>
        {signalsChart.length > 0 ? (
          <>
            <div className="grid grid-cols-3 gap-2 mb-3">
              <StatCard
                label={isEn ? 'Total Signals' : 'Tổng tín hiệu'}
                value={data.signals_per_day.reduce((s, d) => s + d.n_signals, 0)}
                valueClass="text-amber-400"
              />
              <StatCard
                label={isEn ? 'Telegram Sent' : 'Telegram đã gửi'}
                value={data.signals_per_day.reduce((s, d) => s + d.n_telegram, 0)}
                valueClass="text-sky-400"
              />
              <StatCard
                label={isEn ? 'Actual Target Hits' : 'Thực xả'}
                value={data.signals_per_day.reduce((s, d) => s + d.n_hit, 0)}
                valueClass="text-emerald-400"
                highlight
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
                <Bar dataKey="signals" fill="#f59e0b" name={isEn ? 'Signals' : 'Tín hiệu'} radius={[3, 3, 0, 0]} />
                <Bar dataKey="telegram" fill="#0ea5e9" name="Telegram" radius={[3, 3, 0, 0]} />
                <Bar dataKey="hits" fill="#10b981" name={isEn ? 'Target Hits' : 'Thực xả'} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </>
        ) : (
          <p className="text-[11px] text-slate-500 italic">
            {isEn ? 'No signals recorded yet in alert history.' : 'Chưa có tín hiệu nào trong alert_history.'}
          </p>
        )}
      </section>
    </div>
  );
};
