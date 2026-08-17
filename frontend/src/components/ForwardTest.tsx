import React, { useState, useEffect } from 'react';
import type { FrozenModelsData, ForwardTestResult } from '../types';
import { Lock, Play, AlertTriangle, CheckCircle2, XCircle, Loader2, TrendingDown, Snowflake } from 'lucide-react';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';
import { getRiskLabel, getModelLabel, getModelDescription } from '../i18n/translations';

export const ForwardTest: React.FC = () => {
  const { language, t } = useTranslation();

  const [data, setData] = useState<FrozenModelsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [result, setResult] = useState<ForwardTestResult | null>(null);
  const [freezing, setFreezing] = useState(false);
  const [freezeResult, setFreezeResult] = useState<any>(null);

  const fetchModels = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/forward-test/models');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('network_err'));
    } finally {
      setLoading(false);
    }
  };

  const runEvaluate = async (modelId: string) => {
    setEvaluating(true);
    setSelectedModel(modelId);
    setResult(null);
    try {
      const res = await fetch(`/api/forward-test/evaluate/${modelId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setResult(json);
    } catch (err) {
      setResult({ status: 'error', message: err instanceof Error ? err.message : t('network_err') });
    } finally {
      setEvaluating(false);
    }
  };

  const handleFreezeModel = async () => {
    setFreezing(true);
    setFreezeResult(null);
    try {
      const res = await fetch('/api/forward-test/freeze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hypothesis_id: 'hyp_dashboard_001' }),
      });
      const json = await res.json();
      setFreezeResult(json);
      if (json.status === 'success') {
        fetchModels();
      }
    } catch (err) {
      setFreezeResult({ error: err instanceof Error ? err.message : t('network_err') });
    } finally {
      setFreezing(false);
    }
  };

  useEffect(() => {
    fetchModels();
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
        <button onClick={fetchModels} className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-xs">
          {t('refresh')}
        </button>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <Lock className="w-3.5 h-3.5 text-amber-400" />
          {t('forward_header_title')}
        </h3>
        <button onClick={fetchModels} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10">
          🔄 {t('refresh')}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {t('forward_header_sub')}
      </p>

      {/* Freeze button + result */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <Snowflake className="w-3.5 h-3.5 text-sky-400" />
              {t('forward_freeze_title')}
            </h4>
            <p className="text-[10px] text-slate-400 mt-0.5">
              {t('forward_freeze_desc')}
            </p>
          </div>
          <button
            onClick={handleFreezeModel}
            disabled={freezing}
            className="px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-lg text-xs flex items-center gap-1.5 transition disabled:opacity-50"
          >
            {freezing ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('forward_freezing')}</>
            ) : (
              <><Lock className="w-3.5 h-3.5" /> 🔒 {t('forward_freeze_btn')}</>
            )}
          </button>
        </div>
        {freezeResult && (
          <div className="mt-2 text-[11px]">
            {freezeResult.status === 'success' ? (
              <div className="bg-emerald-950/40 border border-emerald-800/50 text-emerald-300 p-2 rounded">
                ✅ {t('forward_freeze_success')}: <strong>{freezeResult.model_id}</strong>
                <br />{t('forward_train_cutoff')}: {formatSystemDateTime(freezeResult.train_cutoff)} · {t('threshold')}: {freezeResult.threshold?.toFixed(4)} · {t('forward_n_features')}: {freezeResult.n_features} · {t('forward_train_size')}: {freezeResult.train_size} ({freezeResult.train_positives} {t('forward_dumps_count')})
              </div>
            ) : (
              <div className="bg-red-950/40 border border-red-800/50 text-red-300 p-2 rounded">
                ❌ {freezeResult.error || freezeResult.message || t('network_err')}
              </div>
            )}
          </div>
        )}
      </div>

      {data.models.length === 0 ? (
        <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400 text-center">
          ⬜ {t('forward_no_models')}
        </div>
      ) : (
        <>
          <p className="text-[11px] text-slate-300">
            <strong className="text-amber-400">{data.models.length}</strong> {t('forward_models_ready')}
          </p>

          {/* Frozen models list */}
          <div className="space-y-2">
            {data.models.map((m) => (
              <div key={m.model_id} className="bg-slate-950 border border-slate-800 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Lock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-white truncate">
                        {getModelLabel(m.friendly_name || m.model_id, language)}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono truncate">{m.model_id}</div>
                    </div>
                    {m.hypothesis_id && (
                      <span className="text-[10px] text-slate-500 shrink-0">({m.hypothesis_id})</span>
                    )}
                  </div>
                  <button
                    onClick={() => runEvaluate(m.model_id)}
                    disabled={evaluating && selectedModel === m.model_id}
                    className="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded text-xs flex items-center gap-1.5 transition disabled:opacity-50 shrink-0"
                  >
                    {evaluating && selectedModel === m.model_id ? (
                      <><Loader2 className="w-3 h-3 animate-spin" /> {t('forward_evaluating')}</>
                    ) : (
                      <><Play className="w-3 h-3" /> {t('forward_evaluate_btn')}</>
                    )}
                  </button>
                </div>
                {m.description && (
                  <p className="text-[10px] text-slate-400 mb-2 leading-relaxed">
                    {getModelDescription(m.description, language)}
                  </p>
                )}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[10px]">
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{t('forward_cutoff')}</div>
                    <div className="text-slate-200 font-mono">{m.train_cutoff.slice(0, 10)}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{t('threshold')}</div>
                    <div className="text-amber-400 font-mono">{m.threshold.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{t('forward_features')}</div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{t('forward_train_size')}</div>
                    <div className="text-slate-200 font-mono">{m.training_stats?.train_size ?? '—'}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{t('forward_train_positives')}</div>
                    <div className="text-emerald-400 font-mono">{m.training_stats?.train_positives ?? '—'}</div>
                  </div>
                </div>
                {m.label_spec && (
                  <div className="mt-2 flex gap-2 text-[10px] font-mono">
                    <span className="bg-amber-950/60 text-amber-300 px-2 py-0.5 rounded border border-amber-500/20">
                      {t('feed_target_drawdown')}: {m.label_spec.target_pct}
                    </span>
                    <span className="bg-sky-950/60 text-sky-300 px-2 py-0.5 rounded border border-sky-500/20">
                      MAE: {m.label_spec.mae_pct}
                    </span>
                    <span className="bg-emerald-950/60 text-emerald-300 px-2 py-0.5 rounded border border-emerald-500/20">
                      {t('forward_horizon')}: {m.label_spec.horizon_h}
                    </span>
                  </div>
                )}

                {/* Evaluation result for this model */}
                {selectedModel === m.model_id && result && !evaluating && (
                  <div className="mt-3 pt-3 border-t border-slate-800">
                    {result.status === 'ok' ? (
                      <>
                        <div className="grid grid-cols-3 gap-2 mb-2">
                          <div className="bg-slate-900 p-2 rounded">
                            <div className="text-[9px] text-slate-400 uppercase">{t('forward_precision')}</div>
                            <div className="text-sm font-bold text-amber-400 font-mono">
                              {(result.metrics!.precision * 100).toFixed(1)}%
                            </div>
                            <div className="text-[9px] text-slate-500">
                              {t('forward_vs_training')} {result.training_metrics!.precision > 0 ? `${((result.metrics!.precision - result.training_metrics!.precision) * 100).toFixed(+1)} pp` : '—'}
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2 rounded">
                            <div className="text-[9px] text-slate-400 uppercase">{t('forward_recall')}</div>
                            <div className="text-sm font-bold text-sky-400 font-mono">
                              {(result.metrics!.recall * 100).toFixed(1)}%
                            </div>
                            <div className="text-[9px] text-slate-500">
                              {t('forward_vs_training')} {result.training_metrics!.recall > 0 ? `${((result.metrics!.recall - result.training_metrics!.recall) * 100).toFixed(+1)} pp` : '—'}
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2 rounded">
                            <div className="text-[9px] text-slate-400 uppercase">{t('forward_brier')}</div>
                            <div className="text-sm font-bold text-slate-200 font-mono">
                              {result.metrics!.brier.toFixed(3)}
                            </div>
                          </div>
                        </div>

                        <div className="text-[11px] text-slate-300 bg-slate-900/60 p-2 rounded mb-2">
                          📊 {result.summary}
                        </div>

                        {/* Drift alert */}
                        {result.drift_check?.precision_drift ? (
                          <div className="flex items-center gap-2 text-[11px] text-red-400 bg-red-950/40 border border-red-800/50 p-2 rounded mb-2">
                            <TrendingDown className="w-3.5 h-3.5" />
                            {t('forward_drift_alert')}
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-[11px] text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 p-2 rounded mb-2">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            {t('forward_stable_alert')}
                          </div>
                        )}

                        {/* Risk breakdown */}
                        {result.risk_breakdown && Object.keys(result.risk_breakdown).length > 0 && (
                          <div>
                            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5">{t('forward_risk_tier_perf')}</h5>
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-[10px] text-slate-300 font-mono">
                                <thead className="text-slate-400 uppercase border-b border-slate-800">
                                  <tr>
                                    <th className="p-1.5">{t('forward_tier_col')}</th>
                                    <th className="p-1.5">{t('forward_signals_col')}</th>
                                    <th className="p-1.5">{t('forward_actual_col')}</th>
                                    <th className="p-1.5">{t('forward_prec_col')}</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-800/60">
                                  {Object.entries(result.risk_breakdown).map(([level, d]) => (
                                    <tr key={level} className="hover:bg-slate-900/60">
                                      <td className="p-1.5 text-white">{getRiskLabel(level, language)}</td>
                                      <td className="p-1.5 text-slate-400">{d.n_signals}</td>
                                      <td className="p-1.5 text-emerald-400">{d.n_actual_distribution}</td>
                                      <td className="p-1.5 text-amber-400">{(d.precision * 100).toFixed(1)}%</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        <div className="mt-2 text-[10px] text-slate-500">
                          {t('forward_rows_count')}: {result.n_forward_rows} · {t('forward_pos_labels')}: {result.n_positive_labels} · {t('forward_pred_pos')}: {result.n_predicted_positive}
                        </div>
                      </>
                    ) : (
                      <div className="flex items-center gap-2 text-[11px] text-amber-400 bg-amber-950/40 border border-amber-800/50 p-2 rounded">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {result.message || `${t('col_status')}: ${result.status}`}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
