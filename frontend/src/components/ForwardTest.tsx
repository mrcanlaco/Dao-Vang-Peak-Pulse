import React, { useState, useEffect } from 'react';
import type { FrozenModelsData, ForwardTestResult } from '../types';
import { Lock, Play, AlertTriangle, CheckCircle2, XCircle, Loader2, TrendingDown, Snowflake } from 'lucide-react';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';

export const ForwardTest: React.FC = () => {
  const { language } = useTranslation();
  const isEn = language === 'en';

  const modelName = (name?: string, fallback = isEn ? 'Model' : 'Mô hình') => {
    if (!name) return fallback;
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
      .replace(/Train cutoff/g, 'Mốc cắt huấn luyện');
  };

  const riskLabels: Record<string, string> = {
    CRITICAL: isEn ? 'CRITICAL' : 'CỰC CAO',
    HIGH: isEn ? 'HIGH' : 'CAO',
    MEDIUM: isEn ? 'MEDIUM' : 'VỪA',
    SAFE: isEn ? 'SAFE' : 'AN TOÀN',
  };

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
      setError(err instanceof Error ? err.message : (isEn ? 'Failed to load models' : 'Lỗi tải dữ liệu'));
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
      setResult({ status: 'error', message: err instanceof Error ? err.message : (isEn ? 'Error' : 'Lỗi') });
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
      setFreezeResult({ error: err instanceof Error ? err.message : (isEn ? 'Error' : 'Lỗi') });
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
          {isEn ? 'Loading frozen models...' : 'Đang tải các mô hình đã đóng băng...'}
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
          {isEn ? 'Retry' : 'Thử lại'}
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
          {isEn ? 'FORWARD TESTING & OUT-OF-SAMPLE MODEL EVALUATION' : 'KIỂM THỬ DỮ LIỆU MỚI — ĐÁNH GIÁ MÔ HÌNH'}
        </h3>
        <button onClick={fetchModels} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10">
          🔄 {isEn ? 'Reload' : 'Tải lại'}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {isEn 
          ? 'Frozen models locked at train_cutoff evaluated on strictly newer out-of-sample data. If precision drops >10%, model drift is flagged.'
          : 'Đóng băng = khóa mô hình + ngưỡng + cấu hình tại thời điểm hiện tại. Sau đó chấm điểm trên dữ liệu MỚI sinh ra sau mốc cắt để xem mô hình có ổn định không.'}
      </p>

      {/* Freeze button + result */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <Snowflake className="w-3.5 h-3.5 text-sky-400" />
              {isEn ? 'Freeze Current Model Snapshot' : 'Đóng băng mô hình hiện tại'}
            </h4>
            <p className="text-[10px] text-slate-400 mt-0.5">
              {isEn 
                ? 'Train AI on all available labeled data, freeze threshold and save artifacts. Requires ≥200 labeled rows.'
                : 'Huấn luyện AI trên tất cả dữ liệu đã có nhãn, khóa ngưỡng, lưu mô hình + siêu dữ liệu. Cần ≥200 dòng dữ liệu đã gán nhãn.'}
            </p>
          </div>
          <button
            onClick={handleFreezeModel}
            disabled={freezing}
            className="px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-lg text-xs flex items-center gap-1.5 transition disabled:opacity-50"
          >
            {freezing ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" /> {isEn ? 'Freezing...' : 'Đang đóng băng...'}</>
            ) : (
              <><Lock className="w-3.5 h-3.5" /> 🔒 {isEn ? 'Freeze Model' : 'Đóng băng'}</>
            )}
          </button>
        </div>
        {freezeResult && (
          <div className="mt-2 text-[11px]">
            {freezeResult.status === 'success' ? (
              <div className="bg-emerald-950/40 border border-emerald-800/50 text-emerald-300 p-2 rounded">
                ✅ {isEn ? 'Model frozen successfully:' : 'Mô hình đã đóng băng:'} <strong>{freezeResult.model_id}</strong>
                <br />{isEn ? 'Train Cutoff:' : 'Mốc cắt:'} {formatSystemDateTime(freezeResult.train_cutoff)} · {isEn ? 'Threshold:' : 'Ngưỡng:'} {freezeResult.threshold?.toFixed(4)} · {isEn ? 'Features:' : 'Số đặc trưng:'} {freezeResult.n_features} · {isEn ? 'Train size:' : 'Dữ liệu huấn luyện:'} {freezeResult.train_size} ({freezeResult.train_positives} {isEn ? 'dumps' : 'xả'})
              </div>
            ) : (
              <div className="bg-red-950/40 border border-red-800/50 text-red-300 p-2 rounded">
                ❌ {freezeResult.error || freezeResult.message || (isEn ? 'Unknown error' : 'Lỗi không xác định')}
              </div>
            )}
          </div>
        )}
      </div>

      {data.models.length === 0 ? (
        <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400 text-center">
          ⬜ {isEn ? 'No frozen models available yet. Run backtest experiments or freeze a model to evaluate new data.' : 'Chưa có mô hình nào đóng băng. Chạy kiểm thử lịch sử từ ứng dụng hoặc CLI rồi đóng băng mô hình để đánh giá dữ liệu mới.'}
        </div>
      ) : (
        <>
          <p className="text-[11px] text-slate-300">
            <strong className="text-amber-400">{data.models.length}</strong> {isEn ? 'frozen models available. Select a model to evaluate on live data:' : 'mô hình đã đóng băng. Chọn mô hình để đánh giá dữ liệu mới:'}
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
                        {modelName(m.friendly_name, m.model_id)}
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
                      <><Loader2 className="w-3 h-3 animate-spin" /> {isEn ? 'Evaluating...' : 'Đang đánh giá...'}</>
                    ) : (
                      <><Play className="w-3 h-3" /> {isEn ? 'Evaluate' : 'Chấm điểm'}</>
                    )}
                  </button>
                </div>
                {m.description && (
                  <p className="text-[10px] text-slate-400 mb-2 leading-relaxed">
                    {modelDescription(m.description)}
                  </p>
                )}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[10px]">
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{isEn ? 'Cutoff' : 'Mốc cắt'}</div>
                    <div className="text-slate-200 font-mono">{m.train_cutoff.slice(0, 10)}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{isEn ? 'Threshold' : 'Ngưỡng'}</div>
                    <div className="text-amber-400 font-mono">{m.threshold.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{isEn ? 'Features' : 'Đặc trưng'}</div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{isEn ? 'Train Size' : 'Cỡ tập huấn luyện'}</div>
                    <div className="text-slate-200 font-mono">{m.training_stats?.train_size ?? '—'}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{isEn ? 'Train Positives' : 'Mẫu xả khi huấn luyện'}</div>
                    <div className="text-emerald-400 font-mono">{m.training_stats?.train_positives ?? '—'}</div>
                  </div>
                </div>
                {m.label_spec && (
                  <div className="mt-2 flex gap-2 text-[10px] font-mono">
                    <span className="bg-amber-950/60 text-amber-300 px-2 py-0.5 rounded border border-amber-500/20">
                      {isEn ? 'Target:' : 'Mục tiêu:'} {m.label_spec.target_pct}
                    </span>
                    <span className="bg-sky-950/60 text-sky-300 px-2 py-0.5 rounded border border-sky-500/20">
                      MAE: {m.label_spec.mae_pct}
                    </span>
                    <span className="bg-emerald-950/60 text-emerald-300 px-2 py-0.5 rounded border border-emerald-500/20">
                      {isEn ? 'Horizon:' : 'Khung:'} {m.label_spec.horizon_h}
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
                            <div className="text-[9px] text-slate-400 uppercase">{isEn ? 'Precision' : 'Độ chính xác'}</div>
                            <div className="text-sm font-bold text-amber-400 font-mono">
                              {(result.metrics!.precision * 100).toFixed(1)}%
                            </div>
                            <div className="text-[9px] text-slate-500">
                              {isEn ? 'vs training:' : 'so với huấn luyện:'} {result.training_metrics!.precision > 0 ? `${((result.metrics!.precision - result.training_metrics!.precision) * 100).toFixed(+1)} pp` : '—'}
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2 rounded">
                            <div className="text-[9px] text-slate-400 uppercase">{isEn ? 'Recall' : 'Tỷ lệ bắt'}</div>
                            <div className="text-sm font-bold text-sky-400 font-mono">
                              {(result.metrics!.recall * 100).toFixed(1)}%
                            </div>
                            <div className="text-[9px] text-slate-500">
                              {isEn ? 'vs training:' : 'so với huấn luyện:'} {result.training_metrics!.recall > 0 ? `${((result.metrics!.recall - result.training_metrics!.recall) * 100).toFixed(+1)} pp` : '—'}
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2 rounded">
                            <div className="text-[9px] text-slate-400 uppercase">{isEn ? 'Brier Score' : 'Điểm Brier'}</div>
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
                            {isEn 
                              ? '🔴 Drift detected — out-of-sample precision degraded >10% vs training. Retraining recommended.'
                              : '🔴 Phát hiện trôi dịch — độ chính xác giảm >10% so với lúc huấn luyện. Mô hình cần huấn luyện lại trước khi dùng thật.'}
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-[11px] text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 p-2 rounded mb-2">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            {isEn 
                              ? '✅ Model Stable — out-of-sample precision is consistent with training benchmark. Production ready.'
                              : '✅ Mô hình ổn định — độ chính xác ngoài mẫu gần bằng lúc huấn luyện. Có thể dùng cho bộ quét.'}
                          </div>
                        )}

                        {/* Risk breakdown */}
                        {result.risk_breakdown && Object.keys(result.risk_breakdown).length > 0 && (
                          <div>
                            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5">{isEn ? 'Performance by Risk Tier' : 'Phân tích theo mức nguy cơ'}</h5>
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-[10px] text-slate-300 font-mono">
                                <thead className="text-slate-400 uppercase border-b border-slate-800">
                                  <tr>
                                    <th className="p-1.5">{isEn ? 'Tier' : 'Mức'}</th>
                                    <th className="p-1.5">{isEn ? 'Signals' : 'Tín hiệu'}</th>
                                    <th className="p-1.5">{isEn ? 'Actual Dumps' : 'Thực xả'}</th>
                                    <th className="p-1.5">{isEn ? 'Precision' : 'Chính xác'}</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-800/60">
                                  {Object.entries(result.risk_breakdown).map(([level, d]) => (
                                    <tr key={level} className="hover:bg-slate-900/60">
                                      <td className="p-1.5 text-white">{riskLabels[level] || level}</td>
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
                          {isEn ? 'Forward rows:' : 'Dòng dữ liệu mới:'} {result.n_forward_rows} · {isEn ? 'Positive labels:' : 'Nhãn dương:'} {result.n_positive_labels} · {isEn ? 'Predicted positive:' : 'Dự đoán dương:'} {result.n_predicted_positive}
                        </div>
                      </>
                    ) : (
                      <div className="flex items-center gap-2 text-[11px] text-amber-400 bg-amber-950/40 border border-amber-800/50 p-2 rounded">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {result.message || `${isEn ? 'Status:' : 'Trạng thái:'} ${result.status}`}
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
