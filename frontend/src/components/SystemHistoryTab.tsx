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
import { useTranslation, type Language } from '../i18n/LanguageContext';
import { getModelLabel, getModelDescription, getScanModeLabel } from '../i18n/translations';

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
  const { language, t } = useTranslation();

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
      setError(err instanceof Error ? err.message : t('network_err'));
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
          {t('tab_loading')}
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
          {t('refresh')}
        </button>
      </div>
    );
  }

  if (!data) return null;

  const fmtNum = (n: number | null | undefined) => {
    if (n == null) return '—';
    const locale = language === 'zh' ? 'zh-CN' : language === 'ko' ? 'ko-KR' : language === 'en' ? 'en-US' : 'vi-VN';
    return n.toLocaleString(locale);
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

  const getTableTooltip = (table: string, lang: Language): string => {
    const map: Record<string, Record<string, string>> = {
      kline: {
        vi: 'Nến 5 phút từ Binance — dữ liệu thị trường gốc (OHLCV). Mỗi dòng = 1 nến của 1 mã.',
        en: '5-minute candles from Binance (OHLCV raw market data).',
        zh: '来自币安的 5 分钟 K 线（OHLCV 原始市场数据）。',
        ko: '바이낸스 5분봉 캔들 (OHLCV 원시 시장 데이터).',
      },
      aligned_5m: {
        vi: 'Nến đã chuẩn hóa theo thời điểm có sẵn — dùng để tính đặc trưng và nhãn, không nhìn trước dữ liệu tương lai.',
        en: 'Synchronized 5m candles at available timestamps for zero lookahead.',
        zh: '已对齐时间戳的 5 分钟 K 线，杜绝未来函数。',
        ko: '미래참조 방지를 위해 시계열 정렬된 5분봉 캔들.',
      },
      feature_results: {
        vi: 'Vector đặc trưng đã tính cho mỗi mã tại từng thời điểm — đầu vào cho mô hình AI.',
        en: 'Calculated ML feature vectors across time horizons.',
        zh: '已计算的多周期特征向量，作为 AI 模型输入。',
        ko: 'AI 모델 입력을 위한 다주기 계산 특성 벡터.',
      },
      labels: {
        vi: 'Nhãn phân phối: 1 nếu coin giảm >= mục tiêu trong khung thời gian, 0 nếu không. Dữ liệu thực tế để huấn luyện.',
        en: 'Distribution ground truth labels (1 = dump ≥ 8%, 0 = otherwise).',
        zh: '见顶派发真实标签（1 = 跌幅 ≥ 8%，0 = 否），用于模型训练。',
        ko: '분산 국면 정답 라벨 (1 = 하락 ≥ 8%, 0 = 기타).',
      },
      scan_results: {
        vi: 'Kết quả mỗi chu kỳ quét: điểm, khuyến nghị, giá, OI, funding... của mọi coin đã quét.',
        en: 'Per-cycle scan scores, indicators, and recommendations.',
        zh: '每轮扫描输出：得分、建议、价格、持仓量、费率等。',
        ko: '매 스캔 주기별 점수, 지표, 추천 결과.',
      },
      alert_history: {
        vi: 'Tín hiệu vượt ngưỡng cảnh báo đã ghi lại — kèm kết quả đúng/sai sau khi hết khung thời gian.',
        en: 'Radar alerts logged above threshold with verification outcomes.',
        zh: '超过阈值的雷达警报记录及后续验证结果。',
        ko: '임계값을 초과한 레이더 경보 이력 및 실현 결과.',
      },
      funding: {
        vi: 'Tỷ lệ funding theo thời gian — tín hiệu áp lực mua/bán trên hợp đồng tương lai.',
        en: 'Funding rate time series from Binance USD-M futures.',
        zh: '币安 U 本位合约资金费率时序。',
        ko: '바이낸스 선물 펀딩비 시계열 데이터.',
      },
      open_interest: {
        vi: 'OI (USD) — tổng vị thế đang mở, tăng = dòng tiền vào, giảm = dòng tiền rút ra.',
        en: 'Open Interest (USD) position tracking.',
        zh: '未平仓合约量 (OI USD) 持仓跟踪。',
        ko: '미결제약정 (OI USD) 포지션 추적.',
      },
      taker_volume: {
        vi: 'Khối lượng mua/bán chủ động — chênh lệch giữa bên mua và bên bán trên thị trường.',
        en: 'Taker buy / sell active volume metrics.',
        zh: '主动买入/卖出吃单成交量指标。',
        ko: '테이커 매수/매도 거래량 델타 지표.',
      },
    };
    return map[table]?.[lang] ?? map[table]?.['en'] ?? '';
  };

  const getPipelineSpec = (lang: Language) => [
    {
      table: 'kline',
      label: lang === 'en' ? 'Candle Collector' : lang === 'zh' ? 'K 线采集器' : lang === 'ko' ? '캔들 수집기' : 'Bộ thu thập nến',
      expectedMin: 5,
      desc: lang === 'en' ? '5m Binance candles. Updated ~5m.' : lang === 'zh' ? '币安 5 分钟 K 线，每 5 分钟更新。' : lang === 'ko' ? '바이낸스 5분 캔들. ~5분마다 갱신.' : 'Nến 5 phút từ Binance. Phải cập nhật mỗi ~5 phút.',
    },
    {
      table: 'aligned_5m',
      label: lang === 'en' ? 'Timeline Aligner' : lang === 'zh' ? '时间对齐引擎' : lang === 'ko' ? '시계열 정렬기' : 'Căn chỉnh dữ liệu',
      expectedMin: 5,
      desc: lang === 'en' ? 'Normalized 5m timestamps for lookahead safety.' : lang === 'zh' ? '严格对齐时间戳确保无数据泄漏。' : lang === 'ko' ? '데이터 누수 방지를 위한 정규화.' : 'Nến đã chuẩn hóa theo đúng thời điểm.',
    },
    {
      table: 'feature_results',
      label: lang === 'en' ? 'Feature Pipeline' : lang === 'zh' ? '特征流水线' : lang === 'ko' ? '특성 파이프라인' : 'Luồng đặc trưng',
      expectedMin: 15,
      desc: lang === 'en' ? 'Computed feature vectors for model scoring.' : lang === 'zh' ? '用于模型打分的特征向量。' : lang === 'ko' ? '모델 추론용 특성 벡터 생성.' : 'Vector đặc trưng tính từ aligned_5m.',
    },
    {
      table: 'labels',
      label: lang === 'en' ? 'Label Generator' : lang === 'zh' ? '标签生成器' : lang === 'ko' ? '라벨 생성기' : 'Tạo nhãn',
      expectedMin: 1440,
      desc: lang === 'en' ? 'Requires 24-48h horizon to evaluate ground truth.' : lang === 'zh' ? '需 24-48 小时周期以判定真实见顶。' : lang === 'ko' ? '정답 판정을 위해 24-48시간 대기 필요.' : 'Nhãn phân phối cần chờ khung thời gian (24–48 giờ) để hoàn tất.',
    },
    {
      table: 'scan_results',
      label: lang === 'en' ? 'Scanner Loop' : lang === 'zh' ? '扫描引擎循环' : lang === 'ko' ? '스캐너 루프' : 'Bộ quét',
      expectedMin: 5,
      desc: lang === 'en' ? 'Outputs scores each cycle to scan_results.' : lang === 'zh' ? '每个周期写入最新扫描评分。' : lang === 'ko' ? '주기마다 scan_results에 점수 기록.' : 'Mỗi chu kỳ quét ghi vào scan_results.',
    },
    {
      table: 'funding',
      label: lang === 'en' ? 'Funding Rate' : lang === 'zh' ? '资金费率' : lang === 'ko' ? '펀딩비' : 'Tỷ lệ funding',
      expectedMin: 480,
      desc: lang === 'en' ? 'Binance futures funding rate every 8 hours.' : lang === 'zh' ? '币安合约资金费率每 8 小时更新。' : lang === 'ko' ? '바이낸스 선물 펀딩비 8시간 주기.' : 'Tỷ lệ funding từ hợp đồng tương lai Binance, cập nhật mỗi 8 giờ.',
    },
    {
      table: 'open_interest',
      label: 'OI',
      expectedMin: 15,
      desc: lang === 'en' ? 'Open Interest snapshot every 15 min.' : lang === 'zh' ? '未平仓量快照每 15 分钟更新。' : lang === 'ko' ? '미결제약정 15분 주기 갱신.' : 'OI thay đổi mỗi 15 phút.',
    },
    {
      table: 'taker_volume',
      label: lang === 'en' ? 'Taker Volume' : lang === 'zh' ? '主动成交量' : lang === 'ko' ? '테이커 볼륨' : 'Khối lượng chủ động',
      expectedMin: 15,
      desc: lang === 'en' ? 'Taker volume delta every 15 min.' : lang === 'zh' ? '主动买卖差每 15 分钟计算。' : lang === 'ko' ? '테이커 매수/매도 델타 15분 주기.' : 'Khối lượng mua/bán chủ động mỗi 15 phút.',
    },
    {
      table: 'alert_history',
      label: lang === 'en' ? 'Radar Alerts' : lang === 'zh' ? '雷达警报' : lang === 'ko' ? '레이더 경보' : 'Cảnh báo Radar',
      expectedMin: 0,
      onDemand: true,
      desc: lang === 'en' ? 'Recorded only when symbols exceed threshold.' : lang === 'zh' ? '仅当币种突破预警阈值时记录。' : lang === 'ko' ? '임계값을 초과할 때만 기록됨.' : 'Chỉ ghi cảnh báo khi coin vượt ngưỡng.',
    },
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
    if (min < 60) return language === 'en' ? `${min}m` : language === 'zh' ? `${min} 分钟` : language === 'ko' ? `${min}분` : `${min} phút`;
    if (min < 1440) return language === 'en' ? `${Math.round(min / 60)}h` : language === 'zh' ? `${Math.round(min / 60)} 小时` : language === 'ko' ? `${Math.round(min / 60)}시간` : `${Math.round(min / 60)} giờ`;
    return language === 'en' ? `${Math.round(min / 1440)}d` : language === 'zh' ? `${Math.round(min / 1440)} 天` : language === 'ko' ? `${Math.round(min / 1440)}일` : `${Math.round(min / 1440)} ngày`;
  };

  const getStatus = (ageMin: number | null, expectedMin: number, onDemand?: boolean) => {
    if (onDemand) return 'ondemand';
    if (ageMin == null) return 'gray';
    if (ageMin <= expectedMin) return 'green';
    if (ageMin <= expectedMin * 2) return 'yellow';
    return 'red';
  };

  const getStatusStyles = (lang: Language): Record<string, { dot: string; text: string; label: string; ring: string }> => {
    const labels: Record<string, Record<string, string>> = {
      green: { vi: 'MỚI', en: 'FRESH', zh: '最新', ko: '최신' },
      yellow: { vi: 'ĐANG CŨ', en: 'AGING', zh: '轻微延迟', ko: '지연' },
      red: { vi: 'QUÁ CŨ', en: 'STALE', zh: '数据过旧', ko: '오래됨' },
      gray: { vi: 'CHƯA CÓ DỮ LIỆU', en: 'NO DATA', zh: '暂无数据', ko: '데이터 없음' },
      ondemand: { vi: 'THEO SỰ KIỆN', en: 'ON DEMAND', zh: '按需触发', ko: '이벤트 기반' },
    };
    return {
      green: { dot: 'bg-emerald-400', text: 'text-emerald-400', label: labels.green[lang] || labels.green.en, ring: 'border-emerald-500/30' },
      yellow: { dot: 'bg-amber-400', text: 'text-amber-400', label: labels.yellow[lang] || labels.yellow.en, ring: 'border-amber-500/30' },
      red: { dot: 'bg-red-400', text: 'text-red-400', label: labels.red[lang] || labels.red.en, ring: 'border-red-500/40' },
      gray: { dot: 'bg-slate-500', text: 'text-slate-500', label: labels.gray[lang] || labels.gray.en, ring: 'border-slate-800' },
      ondemand: { dot: 'bg-sky-400', text: 'text-sky-400', label: labels.ondemand[lang] || labels.ondemand.en, ring: 'border-sky-500/30' },
    };
  };

  const statusStyles = getStatusStyles(language);
  const pipelineSpec = getPipelineSpec(language);
  const dataStatsMap = new Map((data?.data_stats || []).map(d => [d.table, d]));
  const freshnessRows = pipelineSpec.map(spec => {
    const tableData = data?.freshness?.[spec.table] || dataStatsMap.get(spec.table);
    const maxTime = tableData?.max_time;
    const rowCount = 'row_count' in (tableData || {}) ? (tableData as any).row_count : (tableData as any)?.rows;
    const ageMin = computeAgeMin(maxTime, data?.generated_at || '');
    const status = getStatus(ageMin, spec.expectedMin, spec.onDemand);
    return {
      ...spec,
      max_time: maxTime,
      row_count: rowCount,
      ageMin,
      status,
    };
  });
  const nStale = freshnessRows.filter(r => r.status === 'red').length;
  const nAging = freshnessRows.filter(r => r.status === 'yellow').length;

  if (!data) return null;

  return (
    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <Activity className="w-3.5 h-3.5 text-amber-400" />
          {t('history_header_title')}
        </h3>
        <button onClick={fetchData} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10 flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> {t('refresh')}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {t('history_report_gen')} (Hà Nội, UTC+7): <span className="text-slate-200 font-mono font-bold">{fmtTime(data.generated_at)}</span>
      </p>

      {/* ===== SECTION 0: FRESHNESS HEALTH CHECK ===== */}
      <section className={`bg-slate-950 border rounded-xl p-3 ${nStale > 0 ? 'border-red-500/40' : nAging > 0 ? 'border-amber-500/30' : 'border-emerald-500/30'}`}>
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Gauge className="w-3.5 h-3.5 text-amber-400" />
          {t('history_freshness_title')}
          <InfoTip text={t('history_freshness_desc')} />
          {nStale > 0 ? (
            <span className="ml-auto text-[10px] text-red-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nStale} {t('history_stale_count')}
            </span>
          ) : nAging > 0 ? (
            <span className="ml-auto text-[10px] text-amber-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nAging} {t('history_aging_count')}
            </span>
          ) : (
            <span className="ml-auto text-[10px] text-emerald-400 font-bold flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> {t('history_all_fresh')}
            </span>
          )}
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {freshnessRows.map(r => {
            const st = statusStyles[r.status] || statusStyles.gray;
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
                    <div className="text-slate-500 uppercase text-[8px]">{t('history_col_latest')}</div>
                    <div className={`font-mono font-bold ${r.status === 'red' ? 'text-red-400' : 'text-slate-200'}`}>
                      {r.max_time ? fmtTime(r.max_time) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{t('history_col_age')}</div>
                    <div className={`font-mono font-bold ${st.text}`}>{fmtAge(r.ageMin)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{t('backtest_modal_total_rows')}</div>
                    <div className="text-slate-300 font-mono">{fmtNum(r.row_count)}</div>
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
          {t('history_duckdb_title')}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={t('history_total_rows')}
            value={fmtNum(totalRows)}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={t('history_tables_count')}
            value={data.data_stats.length}
            valueClass="text-slate-200"
          />
          <StatCard
            label={t('history_latest_data')}
            value={<span className="text-xs">{fmtTime(latestDataTime)}</span>}
            valueClass="text-emerald-400"
            highlight
          />
          <StatCard
            label={t('history_db_path')}
            value={<span className="text-[10px]">{data.db_path || '—'}</span>}
            valueClass="text-slate-300 truncate"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[10px] text-slate-300 font-mono">
            <thead className="text-slate-400 uppercase border-b border-slate-800">
              <tr>
                <th className="p-1.5">{t('history_col_table')}</th>
                <th className="p-1.5">{t('backtest_modal_total_rows')}</th>
                <th className="p-1.5">{t('history_col_time_col')}</th>
                <th className="p-1.5">{t('history_col_earliest')}</th>
                <th className="p-1.5">{t('history_col_latest')}</th>
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
                        {getTableTooltip(d.table, language) && <InfoTip text={getTableTooltip(d.table, language)} />}
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
          {t('history_scanner_daemon')}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={t('col_status')}
            value={
              <span className="flex items-center gap-1">
                {isOnline ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {isOnline ? t('scanner_running') : t('scanner_stopped')}
              </span>
            }
            valueClass={isOnline ? 'text-emerald-400' : 'text-red-400'}
            highlight
          />
          <StatCard
            label={t('history_latest_cycle')}
            value={`#${lastCycle.cycle ?? '—'}`}
            valueClass="text-amber-400"
          />
          <StatCard
            label={t('history_last_scan_time')}
            value={<span className="text-xs">{fmtTime(lastCycle.last_scan_time)}</span>}
            valueClass="text-slate-200"
            highlight
          />
          <StatCard
            label={t('history_symbols_per_cycle')}
            value={fmtNum(lastCycle.n_symbols)}
            valueClass="text-sky-400"
          />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3 text-[10px]">
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{t('history_heartbeat')}:</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{fmtTime(hb.timestamp)}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{t('history_scan_mode')}:</span>{' '}
            <span className="text-amber-400 font-mono uppercase font-bold">{getScanModeLabel(data.scanner.scan_mode, language)}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{t('history_poll_interval')}:</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{hb.poll_minutes || '?'} {language === 'en' ? 'min' : language === 'zh' ? '分钟' : language === 'ko' ? '분' : 'phút'}</span>
          </div>
        </div>

        {scanChart.length > 0 && (
          <div className="mt-3">
            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-sky-400" />
              {t('history_daily_scan_chart')}
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
                <Bar dataKey="cycles" fill="#0ea5e9" name={t('history_chart_cycles')} radius={[3, 3, 0, 0]} />
                <Bar dataKey="symbols" fill="#10b981" name={t('history_chart_symbols')} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* ===== SECTION 3: AI Models Progress ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Cpu className="w-3.5 h-3.5 text-amber-400" />
          {t('history_ai_models_title')}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={t('history_frozen_models')}
            value={data.models.length}
            valueClass="text-amber-400"
          />
          <StatCard
            label={t('history_total_experiments')}
            value={data.experiments.total}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={t('history_active_scanner_model')}
            value={<span className="text-[10px]">{data.current_scanner_model_id ? getModelLabel(data.current_scanner_model_id, language) : (language === 'en' ? 'Rules-based' : language === 'zh' ? '基于规则' : language === 'ko' ? '규칙 기반' : 'chưa cài')}</span>}
            valueClass="text-emerald-400 truncate"
            highlight
          />
          <StatCard
            label={t('history_latest_artifact')}
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
                    <span className="text-xs font-bold text-white truncate">{getModelLabel(m.friendly_name || m.model_id, language)}</span>
                    {m.is_scanner_model && (
                      <span className="text-[9px] text-emerald-400 font-mono bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-500/30 flex items-center gap-0.5 shrink-0 font-bold">
                        <Trophy className="w-2.5 h-2.5" /> {t('history_active_badge')}
                      </span>
                    )}
                  </div>
                  <span className="text-[9px] text-slate-500 font-mono shrink-0">{m.label_version}</span>
                </div>
                <p className="text-[10px] text-slate-400 mb-1.5 leading-relaxed">{getModelDescription(m.description, language)}</p>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-1.5 text-[10px]">
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_train_size')}</div>
                    <div className="text-slate-200 font-mono font-bold">{fmtNum(m.train_size)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_train_positives')}</div>
                    <div className="text-emerald-400 font-mono font-bold">{fmtNum(m.train_positives)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_precision')}</div>
                    <div className="text-amber-400 font-mono font-bold">{fmtPct(m.train_precision)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_recall')}</div>
                    <div className="text-sky-400 font-mono font-bold">{fmtPct(m.train_recall)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('forward_features')}</div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{t('threshold')}</div>
                    <div className="text-amber-400 font-mono font-bold">{m.threshold != null ? m.threshold.toFixed(2) : "—"}</div>
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
          {t('history_radar_signals_title')}
        </h4>
        {signalsChart.length > 0 ? (
          <>
            <div className="grid grid-cols-3 gap-2 mb-3">
              <StatCard
                label={t('history_total_signals')}
                value={data.signals_per_day.reduce((s, d) => s + d.n_signals, 0)}
                valueClass="text-amber-400"
              />
              <StatCard
                label={t('history_tg_sent')}
                value={data.signals_per_day.reduce((s, d) => s + d.n_telegram, 0)}
                valueClass="text-sky-400"
              />
              <StatCard
                label={t('history_actual_hits')}
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
                <Bar dataKey="signals" fill="#f59e0b" name={t('feed_tab_all')} radius={[3, 3, 0, 0]} />
                <Bar dataKey="telegram" fill="#0ea5e9" name="Telegram" radius={[3, 3, 0, 0]} />
                <Bar dataKey="hits" fill="#10b981" name={t('history_actual_hits')} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </>
        ) : (
          <p className="text-[11px] text-slate-500 italic">
            {t('history_no_signals')}
          </p>
        )}
      </section>
    </div>
  );
};
