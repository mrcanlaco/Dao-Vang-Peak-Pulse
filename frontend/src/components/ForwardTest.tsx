import React, { useState, useEffect } from 'react';
import type { FrozenModelsData, ForwardTestResult } from '../types';
import { Lock, Play, AlertTriangle, CheckCircle2, XCircle, Loader2, Snowflake } from 'lucide-react';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';
import { getModelLabel, getModelDescription } from '../i18n/translations';

const VI_GATE_LABELS: Record<string, string> = {
  bundle_verified: 'Đúng model và calibrator đã khóa',
  cutoff_locked_after_freeze: 'Dữ liệu bắt đầu sau lúc đóng băng',
  label_contract_verified: 'Đúng phiên bản và horizon của nhãn',
  universe_policy_locked: 'Universe policy đã khóa',
  minimum_evaluated_rows: 'Đủ số dòng đánh giá',
  minimum_positive_events: 'Đủ số sự kiện dương tính',
  minimum_predicted_events: 'Đủ số sự kiện dự báo',
  minimum_evaluation_days: 'Đủ độ dài cửa sổ đánh giá',
};

const formatGateLabel = (name: string, language: string) => {
  if (language === 'vi' && VI_GATE_LABELS[name]) return VI_GATE_LABELS[name];
  return name.replaceAll('_', ' ');
};

const ForwardEvidencePanel: React.FC<{
  result: ForwardTestResult;
  language: string;
}> = ({ result, language }) => {
  const isEvidenceReport =
    result.status === 'ok' || result.status === 'insufficient_evidence';
  const vi = language === 'vi';

  if (!isEvidenceReport) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-amber-400 bg-amber-950/40 border border-amber-800/50 p-2 rounded">
        <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
        {result.message || `Status: ${result.status}`}
      </div>
    );
  }

  const metrics = result.status === 'ok' ? result.metrics : null;
  const counts = result.counts ?? {};
  const gates = Object.entries(result.gates ?? {});

  return (
    <div className="space-y-2">
      <div className={`flex items-center gap-2 text-[11px] p-2 rounded border ${
        metrics
          ? 'text-emerald-300 bg-emerald-950/40 border-emerald-800/50'
          : 'text-amber-300 bg-amber-950/40 border-amber-800/50'
      }`}>
        {metrics
          ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          : <AlertTriangle className="w-3.5 h-3.5 shrink-0" />}
        {metrics
          ? (vi ? 'Đã vượt toàn bộ gate; metric trong phạm vi protocol được hiển thị.' : 'All evidence gates passed; protocol-scoped metrics are available.')
          : (vi ? 'Chưa đủ bằng chứng; hệ thống đang giữ kín toàn bộ metric hiệu năng.' : 'Evidence is insufficient; all performance metrics remain withheld.')}
      </div>

      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {[
            [vi ? 'Precision sự kiện' : 'Event precision', metrics.event_precision],
            [vi ? 'Recall sự kiện' : 'Event recall', metrics.event_recall],
            [vi ? 'Precision theo dòng' : 'Row precision', metrics.row_precision],
            [vi ? 'Recall theo dòng' : 'Row recall', metrics.row_recall],
          ].map(([label, value]) => (
            <div key={String(label)} className="bg-slate-900 p-2 rounded">
              <div className="text-[9px] text-slate-400 uppercase">{label}</div>
              <div className="text-sm font-bold text-amber-400 font-mono">
                {(Number(value) * 100).toFixed(1)}%
              </div>
            </div>
          ))}
          <div className="bg-slate-900 p-2 rounded">
            <div className="text-[9px] text-slate-400 uppercase">Brier</div>
            <div className="text-sm font-bold text-slate-200 font-mono">
              {metrics.brier.toFixed(3)}
            </div>
          </div>
        </div>
      )}

      {gates.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
          {gates.map(([name, gate]) => (
            <div
              key={name}
              className={`flex items-center justify-between gap-2 rounded border px-2 py-1.5 text-[10px] ${
                gate.passed
                  ? 'border-emerald-900/70 bg-emerald-950/20 text-emerald-300'
                  : 'border-amber-900/70 bg-amber-950/20 text-amber-300'
              }`}
            >
              <span>{gate.passed ? '✓' : '…'} {formatGateLabel(name, language)}</span>
              {gate.actual !== undefined && gate.required !== undefined && (
                <span className="font-mono shrink-0">{gate.actual.toFixed(1)} / {gate.required}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="text-[10px] text-slate-400 bg-slate-900/60 p-2 rounded">
        {vi ? 'Dòng trưởng thành' : 'Mature rows'}: {counts.forward_rows ?? 0}
        {' · '}{vi ? 'Dòng dùng được' : 'Usable rows'}: {counts.evaluated_rows ?? 0}
        {' · '}{vi ? 'Sự kiện thật' : 'Positive events'}: {counts.positive_events ?? 0}
        {' · '}{vi ? 'Sự kiện dự báo' : 'Predicted events'}: {counts.predicted_events ?? 0}
      </div>

      {result.operational && (
        <div className="text-[10px] text-slate-500 font-mono">
          {vi ? 'Độ trễ suy luận' : 'Inference latency'}: {result.operational.inference_ms_per_1000_rows.toFixed(1)} ms/1k
          {' · API: $'}{result.operational.external_api_cost_usd.toFixed(4)}
          {' · '}{vi ? 'Chi phí compute' : 'Compute cost'}: {result.operational.compute_cost_usd === null ? (vi ? 'chưa đo' : 'not metered') : `$${result.operational.compute_cost_usd.toFixed(4)}`}
        </div>
      )}

      {result.protocol_fingerprint && (
        <div className="text-[9px] text-slate-600 font-mono break-all">
          Protocol: {result.protocol_fingerprint}
        </div>
      )}
    </div>
  );
};

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
      setResult({
        status: 'error',
        model_id: modelId,
        message: err instanceof Error ? err.message : t('network_err'),
        metrics: null,
      });
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
                    <ForwardEvidencePanel result={result} language={language} />
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
