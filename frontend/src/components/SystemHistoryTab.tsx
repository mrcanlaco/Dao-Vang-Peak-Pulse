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

  const modelName = (name?: string) => {
    if (!name) return language === 'en' ? 'Model' : language === 'zh' ? '模型' : language === 'ko' ? '모델' : 'Mô hình';
    if (language === 'zh') return name.replace(/^Frozen LR/, '已冻结逻辑回归');
    if (language === 'ko') return name.replace(/^Frozen LR/, '동결된 로지스틱 회귀');
    if (language === 'en') return name;
    return name.replace(/^Frozen LR/, 'Hồi quy logistic đã đóng băng');
  };

  const modelDescription = (description?: string) => {
    if (!description) return '';
    if (language === 'zh') {
      return description
        .replace(/Logistic Regression/g, '逻辑回归')
        .replace(/rule-based/g, '基于规则')
        .replace(/funding spike/g, '资金费率异动')
        .replace(/price-volume/g, '量价')
        .replace(/backtest/g, '历史回测')
        .replace(/baseline/g, '基准')
        .replace(/Train cutoff/g, '训练截止时间')
        .replace(/train model/g, '训练模型');
    }
    if (language === 'ko') {
      return description
        .replace(/Logistic Regression/g, '로지스틱 회귀')
        .replace(/rule-based/g, '규칙 기반')
        .replace(/funding spike/g, '펀딩비 급증')
        .replace(/price-volume/g, '가격-거래량')
        .replace(/backtest/g, '백테스트')
        .replace(/baseline/g, '기준선')
        .replace(/Train cutoff/g, '학습 기준시점')
        .replace(/train model/g, '모델 학습');
    }
    if (language === 'en') return description;
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

  const getScanModeLabel = (mode: string, lang: Language): string => {
    const map: Record<string, Record<string, string>> = {
      volatile: { vi: 'BIẾN ĐỘNG', en: 'VOLATILE', zh: '高波动', ko: '고변동성' },
      gainers: { vi: 'TĂNG MẠNH', en: 'TOP GAINERS', zh: '涨幅榜', ko: '급등 코인' },
      losers: { vi: 'GIẢM MẠNH', en: 'TOP LOSERS', zh: '跌幅榜', ko: '급락 코인' },
      volume: { vi: 'KHỐI LƯỢNG', en: 'VOLUME LEADERS', zh: '成交榜', ko: '거래대금 상위' },
      all: { vi: 'TẤT CẢ', en: 'ALL COINS', zh: '全部币种', ko: '전체 코인' },
      manual: { vi: 'CÁ NHÂN', en: 'CUSTOM', zh: '自定义', ko: '사용자 정의' },
    };
    return map[mode]?.[lang] ?? map[mode]?.['en'] ?? mode.toUpperCase();
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
      setError(err instanceof Error ? err.message : (language === 'en' ? 'Failed to load telemetry' : 'Lỗi tải dữ liệu'));
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
          {language === 'en' ? 'Loading system telemetry and logs...' : language === 'zh' ? '正在加载系统遥测与日志...' : language === 'ko' ? '시스템 텔레메트리 및 로그 로드 중...' : 'Đang tải lịch sử hệ thống...'}
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
          {language === 'en' ? 'Retry' : language === 'zh' ? '重试' : language === 'ko' ? '다시 시도' : 'Thử lại'}
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
      gray: { vi: 'CHƯA CÓ DỮ LIỆU', en: 'NO DATA', zh: '无数据', ko: '데이터 없음' },
      ondemand: { vi: 'THEO YÊU CẦU', en: 'ON DEMAND', zh: '按需触发', ko: '이벤트 기반' },
    };
    return {
      green: { dot: 'bg-emerald-400', text: 'text-emerald-400', label: labels.green[lang] ?? 'FRESH', ring: 'border-emerald-500/30' },
      yellow: { dot: 'bg-amber-400', text: 'text-amber-400', label: labels.yellow[lang] ?? 'AGING', ring: 'border-amber-500/30' },
      red: { dot: 'bg-red-400', text: 'text-red-400', label: labels.red[lang] ?? 'STALE', ring: 'border-red-500/40' },
      gray: { dot: 'bg-slate-500', text: 'text-slate-400', label: labels.gray[lang] ?? 'NO DATA', ring: 'border-slate-700' },
      ondemand: { dot: 'bg-sky-400', text: 'text-sky-400', label: labels.ondemand[lang] ?? 'ON DEMAND', ring: 'border-sky-500/30' },
    };
  };

  const statusStyles = getStatusStyles(language);
  const pipelineSpec = getPipelineSpec(language);

  const freshnessRows = pipelineSpec.map(spec => {
    const stat = data.data_stats.find(d => d.table === spec.table);
    const ageMin = computeAgeMin(stat?.max_time, data.generated_at);
    const status = getStatus(ageMin, spec.expectedMin, spec.onDemand);
    return { ...spec, maxTime: stat?.max_time, ageMin, status, rows: stat?.rows ?? 0 };
  });
  const nStale = freshnessRows.filter(r => r.status === 'red').length;
  const nAging = freshnessRows.filter(r => r.status === 'yellow').length;

  const getHeaderTitle = () => {
    if (language === 'zh') return '系统遥测与 DUCKDB 数据湖审计';
    if (language === 'ko') return '시스템 텔레메트리 & 데이터 레이크 감사';
    if (language === 'en') return 'SYSTEM TELEMETRY & DATA LAKE AUDIT';
    return 'LỊCH SỬ & DỮ LIỆU HỆ THỐNG';
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-4 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <Activity className="w-3.5 h-3.5 text-amber-400" />
          {getHeaderTitle()}
        </h3>
        <button onClick={fetchData} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10 flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> {language === 'en' ? 'Reload' : language === 'zh' ? '重新加载' : language === 'ko' ? '새로고침' : 'Tải lại'}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {language === 'en' ? 'Report generated at (UTC+7):' : language === 'zh' ? '报告生成时间 (UTC+7):' : language === 'ko' ? '보고서 생성 시각 (UTC+7):' : 'Cập nhật lúc (Hà Nội, UTC+7):'} <span className="text-slate-200 font-mono font-bold">{fmtTime(data.generated_at)}</span>
      </p>

      {/* ===== SECTION 0: FRESHNESS HEALTH CHECK ===== */}
      <section className={`bg-slate-950 border rounded-xl p-3 ${nStale > 0 ? 'border-red-500/40' : nAging > 0 ? 'border-amber-500/30' : 'border-emerald-500/30'}`}>
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Gauge className="w-3.5 h-3.5 text-amber-400" />
          {language === 'en' ? 'DATA FRESHNESS & PIPELINE HEALTH' : language === 'zh' ? '数据新鲜度与流水线健康度' : language === 'ko' ? '데이터 신선도 및 파이프라인 상태' : 'KIỂM TRA ĐỘ MỚI DỮ LIỆU'}
          <InfoTip text={language === 'en' ? 'Monitors each pipeline ingestion table. Red indicates stale feeds requiring log inspection.' : language === 'zh' ? '监控各数据表摄取状态。红色表示数据过期，需要排查日志。' : language === 'ko' ? '각 데이터 파이프라인 수집 상태를 모니터링합니다.' : 'Kiểm tra độ mới của từng luồng dữ liệu. Mỗi luồng có tần suất cập nhật riêng.'} />
          {nStale > 0 ? (
            <span className="ml-auto text-[10px] text-red-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nStale} {language === 'en' ? 'stale' : language === 'zh' ? '个过旧' : language === 'ko' ? '개 지연' : 'quá cũ'}
            </span>
          ) : nAging > 0 ? (
            <span className="ml-auto text-[10px] text-amber-400 font-bold flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {nAging} {language === 'en' ? 'aging' : language === 'zh' ? '个轻微延迟' : language === 'ko' ? '개 경고' : 'đang cũ'}
            </span>
          ) : (
            <span className="ml-auto text-[10px] text-emerald-400 font-bold flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> {language === 'en' ? 'ALL PIPELINES FRESH' : language === 'zh' ? '所有流水线处于最新状态' : language === 'ko' ? '모든 파이프라인 정상' : 'TẤT CẢ ĐỀU MỚI'}
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
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Latest' : language === 'zh' ? '最新' : language === 'ko' ? '최신' : 'Mới nhất'}</div>
                    <div className={`font-mono font-bold ${r.status === 'red' ? 'text-red-400' : 'text-slate-200'}`}>
                      {r.maxTime ? fmtTime(r.maxTime) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Age' : language === 'zh' ? '延迟' : language === 'ko' ? '경과' : 'Tuổi'}</div>
                    <div className={`font-mono font-bold ${st.text}`}>{fmtAge(r.ageMin)}</div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Rows' : language === 'zh' ? '行数' : language === 'ko' ? '행 수' : 'Số dòng'}</div>
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
          {language === 'en' ? 'DUCKDB DATA LAKE STATS' : language === 'zh' ? 'DUCKDB 数据湖统计' : language === 'ko' ? 'DUCKDB 데이터 레이크 통계' : 'DỮ LIỆU ĐÃ THU THẬP'}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={language === 'en' ? 'Total Rows' : language === 'zh' ? '总记录行数' : language === 'ko' ? '총 행 수' : 'Tổng số dòng'}
            value={fmtNum(totalRows)}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={language === 'en' ? 'Tables' : language === 'zh' ? '数据表数量' : language === 'ko' ? '테이블 수' : 'Số bảng'}
            value={data.data_stats.length}
            valueClass="text-slate-200"
          />
          <StatCard
            label={language === 'en' ? 'Latest Data' : language === 'zh' ? '最新数据时点' : language === 'ko' ? '최신 데이터' : 'Dữ liệu mới nhất'}
            value={<span className="text-xs">{fmtTime(latestDataTime)}</span>}
            valueClass="text-emerald-400"
            highlight
          />
          <StatCard
            label={language === 'en' ? 'Database Path' : language === 'zh' ? '数据库路径' : language === 'ko' ? '데이터베이스 경로' : 'Đường dẫn cơ sở dữ liệu'}
            value={<span className="text-[10px]">{data.db_path || '—'}</span>}
            valueClass="text-slate-300 truncate"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[10px] text-slate-300 font-mono">
            <thead className="text-slate-400 uppercase border-b border-slate-800">
              <tr>
                <th className="p-1.5">{language === 'en' ? 'Table' : language === 'zh' ? '数据表' : language === 'ko' ? '테이블' : 'Bảng'}</th>
                <th className="p-1.5">{language === 'en' ? 'Rows' : language === 'zh' ? '行数' : language === 'ko' ? '행 수' : 'Số dòng'}</th>
                <th className="p-1.5">{language === 'en' ? 'Time Column' : language === 'zh' ? '时间戳列' : language === 'ko' ? '시간 컬럼' : 'Cột thời gian'}</th>
                <th className="p-1.5">{language === 'en' ? 'Earliest' : language === 'zh' ? '最早时段' : language === 'ko' ? '최초 시점' : 'Cũ nhất'}</th>
                <th className="p-1.5">{language === 'en' ? 'Latest' : language === 'zh' ? '最新时段' : language === 'ko' ? '최신 시점' : 'Mới nhất'}</th>
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
          {language === 'en' ? '24/7 SCANNER DAEMON TELEMETRY' : language === 'zh' ? '24/7 守护扫描进程遥测' : language === 'ko' ? '24/7 스캐너 데몬 텔레메트리' : 'HOẠT ĐỘNG BỘ QUÉT 24/7'}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={language === 'en' ? 'Status' : language === 'zh' ? '运行状态' : language === 'ko' ? '상태' : 'Trạng thái'}
            value={
              <span className="flex items-center gap-1">
                {isOnline ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {isOnline ? (language === 'en' ? 'ONLINE' : language === 'zh' ? '运行中' : language === 'ko' ? '온라인' : 'ĐANG CHẠY') : (language === 'en' ? 'OFFLINE' : language === 'zh' ? '已停止' : language === 'ko' ? '오프라인' : 'ĐÃ DỪNG')}
              </span>
            }
            valueClass={isOnline ? 'text-emerald-400' : 'text-red-400'}
            highlight
          />
          <StatCard
            label={language === 'en' ? 'Latest Cycle' : language === 'zh' ? '当前周期' : language === 'ko' ? '최신 주기' : 'Chu kỳ mới nhất'}
            value={`#${lastCycle.cycle ?? '—'}`}
            valueClass="text-amber-400"
          />
          <StatCard
            label={language === 'en' ? 'Last Scan Time' : language === 'zh' ? '上次扫描时间' : language === 'ko' ? '마지막 스캔' : 'Quét lúc'}
            value={<span className="text-xs">{fmtTime(lastCycle.last_scan_time)}</span>}
            valueClass="text-slate-200"
            highlight
          />
          <StatCard
            label={language === 'en' ? 'Symbols / Cycle' : language === 'zh' ? '每轮币种数' : language === 'ko' ? '스캔 코인수' : 'Mã/quét'}
            value={fmtNum(lastCycle.n_symbols)}
            valueClass="text-sky-400"
          />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3 text-[10px]">
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{language === 'en' ? 'Heartbeat:' : language === 'zh' ? '心跳时间:' : language === 'ko' ? '하트비트:' : 'Nhịp hoạt động:'}</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{fmtTime(hb.timestamp)}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{language === 'en' ? 'Scan Mode:' : language === 'zh' ? '扫描模式:' : language === 'ko' ? '스캔 모드:' : 'Chế độ quét:'}</span>{' '}
            <span className="text-amber-400 font-mono uppercase font-bold">{getScanModeLabel(data.scanner.scan_mode, language)}</span>
          </div>
          <div className="bg-slate-900 p-1.5 rounded flex items-center gap-1">
            <span className="text-slate-500">{language === 'en' ? 'Poll Interval:' : language === 'zh' ? '轮询间隔:' : language === 'ko' ? '폴링 주기:' : 'Chu kỳ kiểm tra:'}</span>{' '}
            <span className="text-slate-300 font-mono font-bold">{hb.poll_minutes || '?'} {language === 'en' ? 'min' : language === 'zh' ? '分钟' : language === 'ko' ? '분' : 'phút'}</span>
          </div>
        </div>

        {scanChart.length > 0 && (
          <div className="mt-3">
            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-sky-400" />
              {language === 'en' ? 'Daily Scan Cycles & Unique Symbols (Past 30 Days)' : language === 'zh' ? '每日扫描轮数与覆盖币种 (过去30天)' : language === 'ko' ? '일일 스캔 횟수 및 코인 수 (최근 30일)' : 'Số chu kỳ quét & mã theo ngày (30 ngày gần nhất)'}
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
                <Bar dataKey="cycles" fill="#0ea5e9" name={language === 'en' ? 'Cycles' : language === 'zh' ? '扫描轮数' : language === 'ko' ? '사이클 수' : 'Chu kỳ'} radius={[3, 3, 0, 0]} />
                <Bar dataKey="symbols" fill="#10b981" name={language === 'en' ? 'Symbols' : language === 'zh' ? '覆盖币种' : language === 'ko' ? '코인 수' : 'Mã coin'} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* ===== SECTION 3: AI Models Progress ===== */}
      <section className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 mb-2">
          <Cpu className="w-3.5 h-3.5 text-amber-400" />
          {language === 'en' ? 'AI PREDICTIVE MODELS & ACTIVE DEPLOYMENT' : language === 'zh' ? 'AI 预测模型与在线部署状态' : language === 'ko' ? 'AI 예측 모델 및 배포 현황' : 'MÔ HÌNH AI & TIẾN BỘ'}
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <StatCard
            label={language === 'en' ? 'Frozen Models' : language === 'zh' ? '已冻结模型' : language === 'ko' ? '동결된 모델' : 'Mô hình đã đóng băng'}
            value={data.models.length}
            valueClass="text-amber-400"
          />
          <StatCard
            label={language === 'en' ? 'Total Experiments' : language === 'zh' ? '总实验数' : language === 'ko' ? '총 실험' : 'Thử nghiệm'}
            value={data.experiments.total}
            valueClass="text-sky-400"
            highlight
          />
          <StatCard
            label={language === 'en' ? 'Active Scanner Model' : language === 'zh' ? '当前雷达模型' : language === 'ko' ? '활성 스캐너 모델' : 'Mô hình bộ quét'}
            value={<span className="text-[10px]">{data.current_scanner_model_id || (language === 'en' ? 'Rules-based' : language === 'zh' ? '基于规则' : language === 'ko' ? '규칙 기반' : 'chưa cài')}</span>}
            valueClass="text-emerald-400 truncate"
            highlight
          />
          <StatCard
            label={language === 'en' ? 'Latest Artifact' : language === 'zh' ? '最新产物' : language === 'ko' ? '최신 아티팩트' : 'Thử nghiệm mới nhất'}
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
                        <Trophy className="w-2.5 h-2.5" /> {language === 'en' ? 'ACTIVE SCANNER' : language === 'zh' ? '当前生产雷达' : language === 'ko' ? '활성 스캐너' : 'ĐANG QUÉT'}
                      </span>
                    )}
                  </div>
                  <span className="text-[9px] text-slate-500 font-mono shrink-0">{m.label_version}</span>
                </div>
                <p className="text-[10px] text-slate-400 mb-1.5 leading-relaxed">{modelDescription(m.description)}</p>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-1.5 text-[10px]">
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Train Size' : language === 'zh' ? '训练样本量' : language === 'ko' ? '학습 데이터' : 'Cỡ tập huấn luyện'}</div>
                    <div className="text-slate-200 font-mono font-bold">{fmtNum(m.train_size)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Positives' : language === 'zh' ? '训练暴跌样本' : language === 'ko' ? '양성 샘플' : 'Mẫu xả khi huấn luyện'}</div>
                    <div className="text-emerald-400 font-mono font-bold">{fmtNum(m.train_positives)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Precision' : language === 'zh' ? '精准率' : language === 'ko' ? '정밀도' : 'Độ chính xác'}</div>
                    <div className="text-amber-400 font-mono font-bold">{fmtPct(m.train_precision)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Recall' : language === 'zh' ? '召回率' : language === 'ko' ? '재현율' : 'Tỷ lệ bắt'}</div>
                    <div className="text-sky-400 font-mono font-bold">{fmtPct(m.train_recall)}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Features' : language === 'zh' ? '特征数量' : language === 'ko' ? '특성 수' : 'Đặc trưng'}</div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-950 p-1 rounded">
                    <div className="text-slate-500 uppercase text-[8px]">{language === 'en' ? 'Threshold' : language === 'zh' ? '决策阈值' : language === 'ko' ? '임계값' : 'Ngưỡng'}</div>
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
          {language === 'en' ? 'RADAR: SIGNALS DETECTED PER DAY' : language === 'zh' ? '雷达: 每日捕获警报统计' : language === 'ko' ? '레이더: 일별 감지 신호 수' : 'RADAR: TÍN HIỆU PHÁT HIỆN THEO NGÀY'}
        </h4>
        {signalsChart.length > 0 ? (
          <>
            <div className="grid grid-cols-3 gap-2 mb-3">
              <StatCard
                label={language === 'en' ? 'Total Signals' : language === 'zh' ? '总捕获信号' : language === 'ko' ? '총 감지 신호' : 'Tổng tín hiệu'}
                value={data.signals_per_day.reduce((s, d) => s + d.n_signals, 0)}
                valueClass="text-amber-400"
              />
              <StatCard
                label={language === 'en' ? 'Telegram Sent' : language === 'zh' ? '已推送 Telegram' : language === 'ko' ? '텔레그램 발송' : 'Telegram đã gửi'}
                value={data.signals_per_day.reduce((s, d) => s + d.n_telegram, 0)}
                valueClass="text-sky-400"
              />
              <StatCard
                label={language === 'en' ? 'Actual Target Hits' : language === 'zh' ? '实际见顶达成' : language === 'ko' ? '목표 달성' : 'Thực xả'}
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
                <Bar dataKey="signals" fill="#f59e0b" name={language === 'en' ? 'Signals' : language === 'zh' ? '警报信号' : language === 'ko' ? '신호' : 'Tín hiệu'} radius={[3, 3, 0, 0]} />
                <Bar dataKey="telegram" fill="#0ea5e9" name="Telegram" radius={[3, 3, 0, 0]} />
                <Bar dataKey="hits" fill="#10b981" name={language === 'en' ? 'Target Hits' : language === 'zh' ? '达成目标' : language === 'ko' ? '실제 하락' : 'Thực xả'} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </>
        ) : (
          <p className="text-[11px] text-slate-500 italic">
            {language === 'en' ? 'No signals recorded yet in alert history.' : language === 'zh' ? '暂无历史警报记录。' : language === 'ko' ? '경보 이력이 아직 없습니다.' : 'Chưa có tín hiệu nào trong alert_history.'}
          </p>
        )}
      </section>
    </div>
  );
};
