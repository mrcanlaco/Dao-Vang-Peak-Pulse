import React, { useState, useEffect } from 'react';
import type { ExperimentsData, ExperimentSummary } from '../types';
import { Search, FlaskConical, CheckCircle2, AlertTriangle, XCircle, Eye, X } from 'lucide-react';
import { CoinLink } from './CoinLink';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';
import { getAuditStatusLabel } from '../i18n/translations';

interface BacktestExperimentsProps {
  onSelectCoin?: (symbol: string) => void;
}

export const BacktestExperiments: React.FC<BacktestExperimentsProps> = ({ onSelectCoin }) => {
  const { language, t } = useTranslation();

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
      setError(err instanceof Error ? err.message : t('network_err'));
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
      setDetail({ error: err instanceof Error ? err.message : t('network_err') });
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
        <button onClick={fetchExperiments} className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-xs">
          {t('refresh')}
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

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <FlaskConical className="w-3.5 h-3.5 text-amber-400" />
          {t('backtest_header_title')}
        </h3>
        <button onClick={fetchExperiments} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10">
          🔄 {t('refresh')}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {t('backtest_header_sub')} ({data.total} · {edgeCount} · {leakCount})
      </p>

      {/* Filters */}
      <div className="flex gap-2 items-center">
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3 h-3 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder={t('backtest_search_placeholder')}
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
          <option value="ALL">{t('backtest_filter_all')}</option>
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
                <th className="p-2">{t('backtest_col_artifact')}</th>
                <th className="p-2">{t('col_coin')}</th>
                <th className="p-2">{t('col_time')}</th>
                <th className="p-2">{t('col_status')}</th>
                <th className="p-2">{t('backtest_col_ai_prec')}</th>
                <th className="p-2">{t('backtest_col_baseline')}</th>
                <th className="p-2">{t('forward_recall')}</th>
                <th className="p-2">{t('forward_brier')}</th>
                <th className="p-2">{t('backtest_col_folds')}</th>
                <th className="p-2">{t('backtest_col_dumps')}</th>
                <th className="p-2">{t('backtest_col_leakage')}</th>
                <th className="p-2 text-right">{t('col_action')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={12} className="p-4 text-center text-slate-500">
                    {t('exp_no_matching')}
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
                        {t('view_detail')}
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
                {t('backtest_modal_detail')}: {selectedId}
              </h3>
              <button onClick={() => setSelectedId(null)} className="p-1 text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>
            {detailLoading ? (
              <p className="text-xs text-slate-400">{t('tab_loading')}</p>
            ) : detail?.error ? (
              <p className="text-xs text-red-400">{detail.error}</p>
            ) : detail?.data ? (
              <>
                {/* Config */}
                <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                  <h4 className="text-xs font-bold text-amber-400 mb-1.5">{t('backtest_modal_config')}</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
                    <div><span className="text-slate-500">{t('backtest_modal_hyp')}:</span> <span className="text-slate-200">{detail.data.config?.hypothesis_id}</span></div>
                    <div><span className="text-slate-500">{t('backtest_modal_baseline')}:</span> <span className="text-slate-200">{detail.data.config?.baseline_model}</span></div>
                    <div><span className="text-slate-500">{t('backtest_modal_seed')}:</span> <span className="text-slate-200">{detail.data.config?.seed}</span></div>
                    <div><span className="text-slate-500">{t('col_status')}:</span> <span className="text-slate-200">{getAuditStatusLabel(detail.data.status, language)}</span></div>
                  </div>
                </div>

                {/* Aggregate metrics */}
                {detail.data.results?.aggregate && (
                  <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{t('backtest_modal_aggregate')}</h4>
                    <div className="grid grid-cols-3 gap-2 mb-2">
                      <div className="bg-slate-900 p-2 rounded">
                        <div className="text-[9px] text-slate-400 uppercase">{t('forward_precision')}</div>
                        <div className="text-sm font-bold text-emerald-400 font-mono">{(detail.data.results.aggregate.precision_mean * 100).toFixed(1)}%</div>
                        <div className="text-[9px] text-slate-500">±{(detail.data.results.aggregate.precision_std * 100).toFixed(2)}%</div>
                      </div>
                      <div className="bg-slate-900 p-2 rounded">
                        <div className="text-[9px] text-slate-400 uppercase">{t('forward_recall')}</div>
                        <div className="text-sm font-bold text-sky-400 font-mono">{(detail.data.results.aggregate.recall_mean * 100).toFixed(1)}%</div>
                        <div className="text-[9px] text-slate-500">±{(detail.data.results.aggregate.recall_std * 100).toFixed(2)}%</div>
                      </div>
                      <div className="bg-slate-900 p-2 rounded">
                        <div className="text-[9px] text-slate-400 uppercase">{t('forward_brier')}</div>
                        <div className="text-sm font-bold text-slate-200 font-mono">{detail.data.results.aggregate.brier_mean.toFixed(4)}</div>
                        <div className="text-[9px] text-slate-500">±{detail.data.results.aggregate.brier_std.toFixed(4)}</div>
                      </div>
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {t('backtest_modal_valid_folds')}: {detail.data.results.aggregate.n_valid_folds} · {t('backtest_modal_skipped')}: {detail.data.results.aggregate.n_skipped_folds}
                    </div>

                    {/* Confidence Intervals */}
                    {detail.data.results.aggregate.confidence_intervals && (
                      <div className="mt-2">
                        <h5 className="text-[10px] font-bold text-slate-300 mb-1">{t('backtest_modal_ci')}</h5>
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
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{t('backtest_modal_baselines')}</h4>
                    <table className="w-full text-[10px] font-mono">
                      <thead className="text-slate-400 uppercase border-b border-slate-800">
                        <tr>
                          <th className="p-1.5 text-left">{t('nav_model')}</th>
                          <th className="p-1.5 text-right">{t('forward_precision')}</th>
                          <th className="p-1.5 text-right">{t('forward_recall')}</th>
                          <th className="p-1.5 text-right">{t('forward_brier')}</th>
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
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{t('backtest_modal_quality')}</h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{t('backtest_modal_total_rows')}</div>
                        <div className="text-slate-200">{detail.data.results.data_quality.n_rows ?? '—'}</div>
                      </div>
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{t('backtest_col_dumps')}</div>
                        <div className="text-emerald-400">{detail.data.results.data_quality.label_distribution?.positive ?? '—'}</div>
                      </div>
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{t('backtest_modal_non_events')}</div>
                        <div className="text-red-400">{detail.data.results.data_quality.label_distribution?.negative ?? '—'}</div>
                      </div>
                      <div className="bg-slate-900 p-1.5 rounded">
                        <div className="text-slate-500">{t('backtest_modal_prevalence')}</div>
                        <div className="text-amber-400">{detail.data.results.data_quality.label_distribution?.positive && detail.data.results.data_quality.n_rows ? ((detail.data.results.data_quality.label_distribution.positive / detail.data.results.data_quality.n_rows) * 100).toFixed(1) : '—'}%</div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Leakage Report */}
                {detail.data.results?.leakage_report && (
                  <div className="mb-3 bg-slate-950 p-3 rounded border border-slate-800">
                    <h4 className="text-xs font-bold text-amber-400 mb-1.5">{t('backtest_modal_leakage')}</h4>
                    <div className={`text-[11px] p-2 rounded ${detail.data.results.leakage_report.status === 'passed' ? 'bg-emerald-950/40 text-emerald-300 border border-emerald-800/50' : 'bg-red-950/40 text-red-300 border border-red-800/50'}`}>
                      {detail.data.results.leakage_report.status === 'passed' ? '✅' : '❌'} {getAuditStatusLabel(detail.data.results.leakage_report.status, language)}
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
                    📋 {t('drawer_raw_json')}
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
