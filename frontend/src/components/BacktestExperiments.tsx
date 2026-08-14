import React, { useState, useEffect } from 'react';
import type { ExperimentsData, ExperimentSummary } from '../types';
import { Search, FlaskConical, CheckCircle2, AlertTriangle, XCircle, Eye, X } from 'lucide-react';
import { CoinLink } from './CoinLink';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';

interface BacktestExperimentsProps {
  onSelectCoin?: (symbol: string) => void;
}

export const BacktestExperiments: React.FC<BacktestExperimentsProps> = ({ onSelectCoin }) => {
  const { language } = useTranslation();

  const getStatusMeta = (status: ExperimentSummary['status'], lang: Language) => {
    const labels: Record<ExperimentSummary['status'], Record<string, string>> = {
      edge: { vi: 'AI tốt hơn mốc', en: 'AI Edge Verified', zh: 'AI 优势已验证', ko: 'AI 우위 검증됨' },
      promising: { vi: 'Có triển vọng', en: 'Promising', zh: '极具前景', ko: '유망함' },
      no_edge: { vi: 'Chưa tốt hơn mốc', en: 'No AI Edge', zh: '未显现 AI 优势', ko: '우위 미검증' },
      leak: { vi: 'Rò rỉ dữ liệu', en: 'Data Leakage', zh: '数据泄漏', ko: '데이터 누수' },
      no_data: { vi: 'Thiếu dữ liệu', en: 'Insufficient Data', zh: '数据不足', ko: '데이터 부족' },
      failed: { vi: 'AI thất bại', en: 'AI Failed', zh: 'AI 评估失败', ko: 'AI 실패' },
    };
    const colors: Record<ExperimentSummary['status'], string> = {
      edge: 'text-emerald-400 bg-emerald-950 border-emerald-800',
      promising: 'text-amber-400 bg-amber-950 border-amber-800',
      no_edge: 'text-yellow-400 bg-yellow-950 border-yellow-800',
      leak: 'text-red-400 bg-red-950 border-red-800',
      no_data: 'text-slate-400 bg-slate-900 border-slate-700',
      failed: 'text-red-500 bg-red-950 border-red-900',
    };
    const icons: Record<ExperimentSummary['status'], React.ReactNode> = {
      edge: <CheckCircle2 className="w-3 h-3" />,
      promising: <AlertTriangle className="w-3 h-3" />,
      no_edge: <AlertTriangle className="w-3 h-3" />,
      leak: <XCircle className="w-3 h-3" />,
      no_data: <AlertTriangle className="w-3 h-3" />,
      failed: <XCircle className="w-3 h-3" />,
    };
    return {
      label: labels[status]?.[lang] ?? labels[status]?.['en'] ?? status,
      color: colors[status] ?? 'text-slate-400 bg-slate-900 border-slate-700',
      icon: icons[status] ?? <AlertTriangle className="w-3 h-3" />,
    };
  };

  const resultStatusLabel = (status?: string) => {
    if (!status) {
      if (language === 'zh') return '待定';
      if (language === 'ko') return '대기';
      if (language === 'en') return 'PENDING';
      return 'CHƯA CÓ';
    }
    const lower = status.toLowerCase();
    if (lower === 'passed') {
      if (language === 'zh') return '通过';
      if (language === 'ko') return '통과';
      if (language === 'en') return 'PASSED';
      return 'ĐẠT';
    }
    if (lower === 'failed') {
      if (language === 'zh') return '失败';
      if (language === 'ko') return '실패';
      if (language === 'en') return 'FAILED';
      return 'KHÔNG ĐẠT';
    }
    if (lower === 'success') {
      if (language === 'zh') return '成功';
      if (language === 'ko') return '성공';
      if (language === 'en') return 'SUCCESS';
      return 'THÀNH CÔNG';
    }
    if (lower === 'error') {
      if (language === 'zh') return '错误';
      if (language === 'ko') return '오류';
      if (language === 'en') return 'ERROR';
      return 'LỖI';
    }
    return status.toUpperCase();
  };

  const [data, setData] = useState<ExperimentsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchExperiments = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/experiments');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : (language === 'en' ? 'Failed to load experiments' : 'Lỗi tải dữ liệu'));
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (artifactId: string) => {
    setDetailLoading(true);
    setSelectedId(artifactId);
    try {
      const res = await fetch(`/api/experiments/${artifactId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setDetail(json);
    } catch (err) {
      setDetail({ error: err instanceof Error ? err.message : (language === 'en' ? 'Error' : 'Lỗi') });
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiments();
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-xs text-slate-400 font-mono">
          {language === 'en' ? 'Loading backtest experiment runs...' : language === 'zh' ? '正在加载历史回测实验数据...' : language === 'ko' ? '백테스트 실험 데이터 로드 중...' : 'Đang tải các thử nghiệm...'}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-3">
        <XCircle className="w-8 h-8 text-red-400" />
        <p className="text-xs text-red-400">{error}</p>
        <button onClick={fetchExperiments} className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-xs">
          {language === 'en' ? 'Retry' : language === 'zh' ? '重试' : language === 'ko' ? '다시 시도' : 'Thử lại'}
        </button>
      </div>
    );
  }

  if (!data) return null;

  const filtered = data.experiments.filter(e => {
    const matchesSearch = e.symbol.toLowerCase().includes(search.toLowerCase()) ||
                          e.hypothesis_id.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'ALL' || e.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const edgeCount = data.experiments.filter(e => e.status === 'edge').length;
  const leakCount = data.experiments.filter(e => e.status === 'leak').length;

  const getHeaderTitle = () => {
    if (language === 'zh') return '历史回测实验 —— 滚动时序基准测试';
    if (language === 'ko') return '역사적 백테스트 실험 — 전진 검증 벤치마크';
    if (language === 'en') return 'HISTORICAL BACKTEST EXPERIMENTS — WALK-FORWARD BENCHMARKS';
    return 'KIỂM THỬ LỊCH SỬ — KẾT QUẢ THỬ NGHIỆM AI';
  };

  const getHeaderSubtitle = () => {
    if (language === 'zh') return `样本外滚动推进式交叉验证：隔离时间分段、数据泄漏审计、基准模型对比。共计: ${data.total} 个实验 · ${edgeCount} 个 AI 优势验证 · ${leakCount} 个泄漏。`;
    if (language === 'ko') return `샘플 외 시계열 전진 검증: 엠바고 분할, 누수 감사, 기준선 비교. 총계: ${data.total}개 실험 · ${edgeCount}개 AI 우위 입증 · ${leakCount}개 누수.`;
    if (language === 'en') return `Out-of-sample walk-forward validation: embargo time splits, leakage audit, baseline comparisons. Total: ${data.total} experiments · ${edgeCount} edge verified · ${leakCount} leakage.`;
    return `Đánh giá AI trên dữ liệu lịch sử: chia theo thời gian, kiểm tra rò rỉ, so sánh mốc chuẩn. Tổng cộng ${data.total} thử nghiệm · ${edgeCount} AI tốt hơn mốc chuẩn · ${leakCount} rò rỉ.`;
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <FlaskConical className="w-3.5 h-3.5 text-amber-400" />
          {getHeaderTitle()}
        </h3>
        <button onClick={fetchExperiments} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10">
          🔄 {language === 'en' ? 'Reload' : language === 'zh' ? '重新加载' : language === 'ko' ? '새로고침' : 'Tải lại'}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {getHeaderSubtitle()}
      </p>

      {/* Filters */}
      <div className="flex gap-2 items-center">
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3 h-3 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder={language === 'en' ? 'Search symbol/hypothesis...' : language === 'zh' ? '搜索币种 / 假设 ID...' : language === 'ko' ? '심볼/가설 검색...' : 'Tìm coin/giả thuyết...'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-7 pr-2 py-1 w-full bg-slate-900 border border-slate-800 rounded text-[11px] text-slate-200 focus:outline-none focus:border-amber-500/50"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[11px] text-slate-200 focus:outline-none focus:border-amber-500/50"
        >
          <option value="ALL">{language === 'en' ? 'All Statuses' : language === 'zh' ? '所有状态' : language === 'ko' ? '모든 상태' : 'Tất cả trạng thái'}</option>
          <option value="edge">{getStatusMeta('edge', language).label}</option>
          <option value="promising">{getStatusMeta('promising', language).label}</option>
          <option value="no_edge">{getStatusMeta('no_edge', language).label}</option>
          <option value="leak">{getStatusMeta('leak', language).label}</option>
          <option value="no_data">{getStatusMeta('no_data', language).label}</option>
          <option value="failed">{getStatusMeta('failed', language).label}</option>
        </select>
      </div>

      {/* Experiments table */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="text-slate-400 font-mono text-[10px] uppercase border-b border-slate-800 sticky top-0 bg-slate-950">
              <tr>
                <th className="p-2">{language === 'en' ? 'Artifact ID' : language === 'zh' ? '产物 ID' : language === 'ko' ? '아티팩트 ID' : 'Gói kết quả'}</th>
                <th className="p-2">{language === 'en' ? 'Coin' : language === 'zh' ? '交易对' : language === 'ko' ? '페어' : 'Coin'}</th>
                <th className="p-2">{language === 'en' ? 'Created At' : language === 'zh' ? '创建时间' : language === 'ko' ? '생성일시' : 'Thời gian'}</th>
                <th className="p-2">{language === 'en' ? 'Status' : language === 'zh' ? '评估状态' : language === 'ko' ? '상태' : 'Trạng thái'}</th>
                <th className="p-2">{language === 'en' ? 'AI Precision' : language === 'zh' ? 'AI 精准率' : language === 'ko' ? 'AI 정밀도' : 'Độ chính xác AI'}</th>
                <th className="p-2">{language === 'en' ? 'Baseline' : language === 'zh' ? '基准线' : language === 'ko' ? '기준선' : 'Mốc chuẩn'}</th>
                <th className="p-2">{language === 'en' ? 'Recall' : language === 'zh' ? '召回率' : language === 'ko' ? '재현율' : 'Tỷ lệ bắt'}</th>
                <th className="p-2">{language === 'en' ? 'Brier Score' : language === 'zh' ? '布里尔分' : language === 'ko' ? '브라이어 점수' : 'Điểm Brier'}</th>
                <th className="p-2">{language === 'en' ? 'Folds' : language === 'zh' ? '分段数' : language === 'ko' ? '폴드수' : 'Số lượt chia'}</th>
                <th className="p-2">{language === 'en' ? 'Dump Events' : language === 'zh' ? '暴跌事件' : language === 'ko' ? '덤프 이벤트' : 'Sự kiện xả'}</th>
                <th className="p-2">{language === 'en' ? 'Leakage' : language === 'zh' ? '泄漏审计' : language === 'ko' ? '누수 검증' : 'Rò rỉ'}</th>
                <th className="p-2 text-right">{language === 'en' ? 'Action' : language === 'zh' ? '操作' : language === 'ko' ? '상세보기' : 'Chi tiết'}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={12} className="p-4 text-center text-slate-500">
                    {language === 'en' ? 'No experiments match search criteria.' : language === 'zh' ? '未找到符合条件的实验记录。' : language === 'ko' ? '검색 조건과 일치하는 실험이 없습니다.' : 'Không có thử nghiệm nào khớp.'}
                  </td>
                </tr>
              ) : filtered.map((e, i) => {
                const meta = getStatusMeta(e.status, language);
                return (
                  <tr key={i} className="hover:bg-slate-900/60">
                    <td className="p-2 text-[10px] text-slate-500">{e.artifact_id.slice(0, 20)}...</td>
                    <td className="p-2">
                      {onSelectCoin ? (
                        <CoinLink symbol={e.symbol} onClick={onSelectCoin} />
                      ) : (
                        <span className="font-mono font-bold text-white">{e.symbol}</span>
                      )}
                    </td>
                    <td className="p-2 text-[10px] text-slate-400">{formatSystemDateTime(e.created_at)}</td>
                    <td className="p-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] border inline-flex items-center gap-1 ${meta.color}`}>
                        {meta.icon}
                        {meta.label}
                      </span>
                    </td>
                    <td className="p-2">
                      <span className={e.precision > e.baseline && e.precision > 0 ? 'text-emerald-400 font-bold' : 'text-slate-400'}>
                        {(e.precision * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="p-2 text-slate-400">{(e.baseline * 100).toFixed(1)}%</td>
                    <td className="p-2 text-slate-400">{(e.recall * 100).toFixed(1)}%</td>
                    <td className="p-2 text-slate-400">{e.brier.toFixed(4)}</td>
                    <td className="p-2 text-slate-400">{e.n_valid_folds}/{e.n_valid_folds + e.n_skipped_folds}</td>
                    <td className="p-2 text-amber-400">{e.n_positive}</td>
                    <td className="p-2">
                      {e.leakage === 'passed' ? <span className="text-emerald-400">✅</span> : <span className="text-red-400">❌</span>}
                    </td>
                    <td className="p-2 text-right">
                      <button
                        onClick={() => fetchDetail(e.artifact_id)}
                        className="px-2 py-0.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-[10px] font-sans font-medium inline-flex items-center gap-1"
                      >
                        <Eye className="w-3 h-3" />
                        {language === 'en' ? 'View' : language === 'zh' ? '查看' : language === 'ko' ? '조회' : 'Xem'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail modal */}
      {selectedId && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setSelectedId(null)}>
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-3xl w-full max-h-[80vh] overflow-y-auto p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-200">
                {language === 'en' ? 'Experiment Details:' : language === 'zh' ? '实验详情:' : language === 'ko' ? '실험 상세:' : 'Chi tiết:'} {selectedId}
              </h3>
              <button onClick={() => setSelectedId(null)} className="p-1 text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>
            {detailLoading ? (
              <p className="text-xs text-slate-400">{language === 'en' ? 'Loading details...' : language === 'zh' ? '正在加载详情...' : language === 'ko' ? '상세 정보 로드 중...' : 'Đang tải...'}</p>
            ) : detail?.error ? (
              <p className="text-xs text-red-400">{detail.error}</p>
            ) : detail?.data ? (
              <>
                {/* Config */}
                <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                  <h4 className="text-xs font-bold text-amber-400 mb-1.5">{language === 'en' ? 'CONFIGURATION' : language === 'zh' ? '量化实验配置' : language === 'ko' ? '설정' : 'CẤU HÌNH'}</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
                    <div><span className="text-slate-500">{language === 'en' ? 'Hypothesis:' : language === 'zh' ? '量化假设:' : language === 'ko' ? '가설 ID:' : 'Giả thuyết:'}</span> <span className="text-slate-200">{detail.data.config?.hypothesis_id}</span></div>
                    <div><span className="text-slate-500">{language === 'en' ? 'Baseline:' : language === 'zh' ? '对照基准:' : language === 'ko' ? '기준선:' : 'Mốc chuẩn:'}</span> <span className="text-slate-200">{detail.data.config?.baseline_model}</span></div>
                    <div><span className="text-slate-500">{language === 'en' ? 'Random Seed:' : language === 'zh' ? '随机种子:' : language === 'ko' ? '시드값:' : 'Hạt ngẫu nhiên:'}</span> <span className="text-slate-200">{detail.data.config?.seed}</span></div>
                    <div><span className="text-slate-500">{language === 'en' ? 'Status:' : language === 'zh' ? '运行状态:' : language === 'ko' ? '상태:' : 'Trạng thái:'}</span> <span className="text-slate-200">{resultStatusLabel(detail.data.status)}</span></div>
                  </div>
                </div>

                {/* Aggregate metrics */}
                {detail.data.results?.aggregate && (
                  <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{language === 'en' ? 'AGGREGATE METRICS' : language === 'zh' ? '综合指标表现' : language === 'ko' ? '종합 지표' : 'CHỈ SỐ TỔNG HỢP'}</h4>
                    <div className="grid grid-cols-3 gap-2 mb-2">
                      <div className="bg-slate-900 p-2 rounded">
                        <div className="text-[9px] text-slate-400 uppercase">{language === 'en' ? 'Precision' : language === 'zh' ? '精准率 (Precision)' : language === 'ko' ? '정밀도' : 'Độ chính xác'}</div>
                        <div className="text-sm font-bold text-emerald-400 font-mono">{(detail.data.results.aggregate.precision_mean * 100).toFixed(1)}%</div>
                        <div className="text-[9px] text-slate-500">±{(detail.data.results.aggregate.precision_std * 100).toFixed(2)}%</div>
                      </div>
                      <div className="bg-slate-900 p-2 rounded">
                        <div className="text-[9px] text-slate-400 uppercase">{language === 'en' ? 'Recall' : language === 'zh' ? '召回率 (Recall)' : language === 'ko' ? '재현율' : 'Tỷ lệ bắt'}</div>
                        <div className="text-sm font-bold text-sky-400 font-mono">{(detail.data.results.aggregate.recall_mean * 100).toFixed(1)}%</div>
                        <div className="text-[9px] text-slate-500">±{(detail.data.results.aggregate.recall_std * 100).toFixed(2)}%</div>
                      </div>
                      <div className="bg-slate-900 p-2 rounded">
                        <div className="text-[9px] text-slate-400 uppercase">{language === 'en' ? 'Brier Score' : language === 'zh' ? '布里尔分 (Brier Score)' : language === 'ko' ? '브라이어 점수' : 'Điểm Brier'}</div>
                        <div className="text-sm font-bold text-slate-200 font-mono">{detail.data.results.aggregate.brier_mean.toFixed(4)}</div>
                        <div className="text-[9px] text-slate-500">±{detail.data.results.aggregate.brier_std.toFixed(4)}</div>
                      </div>
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {language === 'en' ? 'Valid Folds:' : language === 'zh' ? '有效时序折数:' : language === 'ko' ? '유효 폴드:' : 'Lượt chia hợp lệ:'} {detail.data.results.aggregate.n_valid_folds} · {language === 'en' ? 'Skipped:' : language === 'zh' ? '跳过折数:' : language === 'ko' ? '스킵됨:' : 'Bỏ qua:'} {detail.data.results.aggregate.n_skipped_folds}
                    </div>

                    {/* Confidence Intervals */}
                    {detail.data.results.aggregate.confidence_intervals && (
                      <div className="mt-2">
                        <h5 className="text-[10px] font-bold text-slate-300 mb-1">{language === 'en' ? '95% CONFIDENCE INTERVALS (BOOTSTRAP)' : language === 'zh' ? '95% 置信区间 (自助重抽样 BOOTSTRAP)' : language === 'ko' ? '95% 신뢰구간 (부트스트랩)' : 'KHOẢNG TIN CẬY 95% (BOOTSTRAP)'}</h5>
                        <div className="grid grid-cols-3 gap-2">
                          {Object.entries(detail.data.results.aggregate.confidence_intervals).map(([metric, ci]: any) => (
                            <div key={metric} className="bg-slate-900 p-1.5 rounded text-[10px] font-mono">
                              <span className="text-slate-400 uppercase">{metric}: </span>
                              <span className="text-slate-200">[{(ci.ci_lower * 100).toFixed(1)}%, {(ci.ci_upper * 100).toFixed(1)}%]</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Baselines comparison */}
                {detail.data.results?.baselines && Object.keys(detail.data.results.baselines).length > 0 && (
                  <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{language === 'en' ? 'BASELINE COMPARISONS' : language === 'zh' ? '基准线对比' : language === 'ko' ? '기준선 비교' : 'SO SÁNH MỐC CHUẨN'}</h4>
                    <table className="w-full text-[10px] font-mono">
                      <thead className="text-slate-400 uppercase border-b border-slate-800">
                        <tr>
                          <th className="p-1.5 text-left">{language === 'en' ? 'Model' : language === 'zh' ? '模型' : language === 'ko' ? '모델' : 'Mô hình'}</th>
                          <th className="p-1.5 text-right">{language === 'en' ? 'Precision' : language === 'zh' ? '精准率' : language === 'ko' ? '정밀도' : 'Độ chính xác'}</th>
                          <th className="p-1.5 text-right">{language === 'en' ? 'Recall' : language === 'zh' ? '召回率' : language === 'ko' ? '재현율' : 'Tỷ lệ bắt'}</th>
                          <th className="p-1.5 text-right">{language === 'en' ? 'Brier Score' : language === 'zh' ? '布里尔分' : language === 'ko' ? '브라이어 점수' : 'Điểm Brier'}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {Object.entries(detail.data.results.baselines).map(([name, m]: any) => (
                          <tr key={name} className="hover:bg-slate-900/60">
                            <td className="p-1.5 text-slate-200">{name}</td>
                            <td className="p-1.5 text-right text-slate-300">{(m.precision_mean * 100).toFixed(1)}%</td>
                            <td className="p-1.5 text-right text-slate-300">{(m.recall_mean * 100).toFixed(1)}%</td>
                            <td className="p-1.5 text-right text-slate-300">{m.brier_mean?.toFixed(4) ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Data Quality */}
                {detail.data.results?.data_quality && (
                  <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{language === 'en' ? 'DATA QUALITY AUDIT' : language === 'zh' ? '数据质量审计' : language === 'ko' ? '데이터 품질 감사' : 'CHẤT LƯỢNG DỮ LIỆU'}</h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{language === 'en' ? 'Total Rows' : language === 'zh' ? '总行数' : language === 'ko' ? '총 행 수' : 'Tổng số dòng'}</div>
                        <div className="text-slate-200">{detail.data.results.data_quality.n_rows ?? '—'}</div>
                      </div>
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{language === 'en' ? 'Dump Events' : language === 'zh' ? '暴跌事件' : language === 'ko' ? '덤프 이벤트' : 'Sự kiện xả'}</div>
                        <div className="text-emerald-400">{detail.data.results.data_quality.label_distribution?.positive ?? '—'}</div>
                      </div>
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{language === 'en' ? 'Non-events' : language === 'zh' ? '非事件' : language === 'ko' ? '일반 구간' : 'Không xả'}</div>
                        <div className="text-red-400">{detail.data.results.data_quality.label_distribution?.negative ?? '—'}</div>
                      </div>
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{language === 'en' ? 'Prevalence' : language === 'zh' ? '发生率' : language === 'ko' ? '발생 빈도' : 'Tần suất xả'}</div>
                        <div className="text-amber-400">{detail.data.results.data_quality.label_distribution?.positive && detail.data.results.data_quality.n_rows ? ((detail.data.results.data_quality.label_distribution.positive / detail.data.results.data_quality.n_rows) * 100).toFixed(1) : '—'}%</div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Leakage Report */}
                {detail.data.results?.leakage_report && (
                  <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{language === 'en' ? 'LOOKAHEAD DATA LEAKAGE AUDIT' : language === 'zh' ? '无未来函数 / 数据泄漏审计' : language === 'ko' ? '미래참조 데이터 누수 검증' : 'KIỂM TRA RÒ RỈ DỮ LIỆU'}</h4>
                    <div className={`text-[11px] p-2 rounded ${detail.data.results.leakage_report.status === 'passed' ? 'bg-emerald-950/40 text-emerald-300 border border-emerald-800/50' : 'bg-red-950/40 text-red-300 border border-red-800/50'}`}>
                      {detail.data.results.leakage_report.status === 'passed' ? '✅' : '❌'} {resultStatusLabel(detail.data.results.leakage_report.status)}
                      {detail.data.results.leakage_report.message && <br />}
                      {detail.data.results.leakage_report.message}
                    </div>
                  </div>
                )}

                {/* Warning */}
                {detail.data.results?.warning && (
                  <div className="mb-3 bg-amber-950/40 border border-amber-800/50 text-amber-300 p-2 rounded text-[11px]">
                    ⚠️ {detail.data.results.warning}
                  </div>
                )}

                {/* Raw JSON expander */}
                <details className="mt-2">
                  <summary className="text-[10px] text-slate-500 cursor-pointer hover:text-slate-300">
                    📋 {language === 'en' ? 'View Raw JSON' : language === 'zh' ? '查看原始 JSON' : language === 'ko' ? '원본 JSON 보기' : 'Xem JSON gốc'}
                  </summary>
                  <pre className="text-[10px] text-slate-300 font-mono overflow-x-auto bg-slate-950 p-3 rounded border border-slate-800 mt-1">
                    {JSON.stringify(detail, null, 2)}
                  </pre>
                </details>
              </>
            ) : (
              <pre className="text-[10px] text-slate-300 font-mono overflow-x-auto bg-slate-950 p-3 rounded border border-slate-800">
                {JSON.stringify(detail, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
