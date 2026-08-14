import React, { useState, useEffect } from 'react';
import type { FrozenModelsData, ForwardTestResult } from '../types';
import { Lock, Play, AlertTriangle, CheckCircle2, XCircle, Loader2, TrendingDown, Snowflake } from 'lucide-react';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';

export const ForwardTest: React.FC = () => {
  const { language } = useTranslation();

  const modelName = (name?: string, fallback = 'Model') => {
    if (!name) return fallback;
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
        .replace(/Train cutoff/g, '训练截止时间');
    }
    if (language === 'ko') {
      return description
        .replace(/Logistic Regression/g, '로지스틱 회귀')
        .replace(/rule-based/g, '규칙 기반')
        .replace(/funding spike/g, '펀딩비 급증')
        .replace(/price-volume/g, '가격-거래량')
        .replace(/backtest/g, '백테스트')
        .replace(/baseline/g, '기준선')
        .replace(/Train cutoff/g, '학습 기준시점');
    }
    if (language === 'en') return description;
    return description
      .replace(/Logistic Regression/g, 'Hồi quy logistic')
      .replace(/rule-based/g, 'theo quy tắc')
      .replace(/funding spike/g, 'tăng đột biến funding')
      .replace(/price-volume/g, 'giá-khối lượng')
      .replace(/backtest/g, 'kiểm thử lịch sử')
      .replace(/baseline/g, 'mốc chuẩn')
      .replace(/Train cutoff/g, 'Mốc cắt huấn luyện');
  };

  const getRiskLabel = (level: string, lang: Language): string => {
    const map: Record<string, Record<string, string>> = {
      CRITICAL: { vi: 'CỰC CAO', en: 'CRITICAL', zh: '极高风险', ko: '치명적 위험' },
      HIGH: { vi: 'CAO', en: 'HIGH', zh: '高风险', ko: '높은 위험' },
      MEDIUM: { vi: 'VỪA', en: 'MEDIUM', zh: '中等风险', ko: '보통 위험' },
      SAFE: { vi: 'AN TOÀN', en: 'SAFE', zh: '安全', ko: '안전' },
    };
    return map[level]?.[lang] ?? map[level]?.['en'] ?? level;
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
      setError(err instanceof Error ? err.message : (language === 'en' ? 'Failed to load models' : 'Lỗi tải dữ liệu'));
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
      setResult({ status: 'error', message: err instanceof Error ? err.message : (language === 'en' ? 'Error' : 'Lỗi') });
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
      setFreezeResult({ error: err instanceof Error ? err.message : (language === 'en' ? 'Error' : 'Lỗi') });
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
          {language === 'en' ? 'Loading frozen models...' : language === 'zh' ? '正在加载已冻结模型...' : language === 'ko' ? '동결된 모델 로드 중...' : 'Đang tải các mô hình đã đóng băng...'}
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
          {language === 'en' ? 'Retry' : language === 'zh' ? '重试' : language === 'ko' ? '다시 시도' : 'Thử lại'}
        </button>
      </div>
    );
  }

  if (!data) return null;

  const getHeaderTitle = () => {
    if (language === 'zh') return '样本外前向检验 —— 冻结模型泛化评估';
    if (language === 'ko') return '샘플 외 전진 테스트 — 동결 모델 평가';
    if (language === 'en') return 'FORWARD TESTING & OUT-OF-SAMPLE MODEL EVALUATION';
    return 'KIỂM THỬ DỮ LIỆU MỚI — ĐÁNH GIÁ MÔ HÌNH';
  };

  const getHeaderSubtitle = () => {
    if (language === 'zh') return '已在 train_cutoff 节点锁定的冻结模型，在严格后续的新样本外数据上进行持续评分。若精准率下降 >10% 则触发概念漂移警报。';
    if (language === 'ko') return '학습 기준시점에 잠긴 동결 모델을 새로운 외래 데이터에 실시간 평가합니다. 정밀도가 >10% 하락 시 모델 드리프트 경고가 발생합니다.';
    if (language === 'en') return 'Frozen models locked at train_cutoff evaluated on strictly newer out-of-sample data. If precision drops >10%, model drift is flagged.';
    return 'Đóng băng = khóa mô hình + ngưỡng + cấu hình tại thời điểm hiện tại. Sau đó chấm điểm trên dữ liệu MỚI sinh ra sau mốc cắt để xem mô hình có ổn định không.';
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <Lock className="w-3.5 h-3.5 text-amber-400" />
          {getHeaderTitle()}
        </h3>
        <button onClick={fetchModels} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10">
          🔄 {language === 'en' ? 'Reload' : language === 'zh' ? '重新加载' : language === 'ko' ? '새로고침' : 'Tải lại'}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {getHeaderSubtitle()}
      </p>

      {/* Freeze button + result */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <Snowflake className="w-3.5 h-3.5 text-sky-400" />
              {language === 'en' ? 'Freeze Current Model Snapshot' : language === 'zh' ? '冻结当前模型快照' : language === 'ko' ? '현재 모델 스냅샷 동결' : 'Đóng băng mô hình hiện tại'}
            </h4>
            <p className="text-[10px] text-slate-400 mt-0.5">
              {language === 'en' 
                ? 'Train AI on all available labeled data, freeze threshold and save artifacts. Requires ≥200 labeled rows.'
                : language === 'zh'
                ? '在所有已标注数据上训练 AI，锁定判别阈值并持久化产物。要求 ≥200 条标注样本。'
                : language === 'ko'
                ? '모든 레이블된 데이터로 AI를 학습하고, 임계값을 고정하여 아티팩트를 저장합니다. ≥200행 데이터 필요.'
                : 'Huấn luyện AI trên tất cả dữ liệu đã có nhãn, khóa ngưỡng, lưu mô hình + siêu dữ liệu. Cần ≥200 dòng dữ liệu đã gán nhãn.'}
            </p>
          </div>
          <button
            onClick={handleFreezeModel}
            disabled={freezing}
            className="px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-lg text-xs flex items-center gap-1.5 transition disabled:opacity-50"
          >
            {freezing ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" /> {language === 'en' ? 'Freezing...' : language === 'zh' ? '正在冻结...' : language === 'ko' ? '동결 중...' : 'Đang đóng băng...'}</>
            ) : (
              <><Lock className="w-3.5 h-3.5" /> 🔒 {language === 'en' ? 'Freeze Model' : language === 'zh' ? '冻结模型' : language === 'ko' ? '모델 동결' : 'Đóng băng'}</>
            )}
          </button>
        </div>
        {freezeResult && (
          <div className="mt-2 text-[11px]">
            {freezeResult.status === 'success' ? (
              <div className="bg-emerald-950/40 border border-emerald-800/50 text-emerald-300 p-2 rounded">
                ✅ {language === 'en' ? 'Model frozen successfully:' : language === 'zh' ? '模型已成功冻结:' : language === 'ko' ? '모델이 성공적으로 동결되었습니다:' : 'Mô hình đã đóng băng:'} <strong>{freezeResult.model_id}</strong>
                <br />{language === 'en' ? 'Train Cutoff:' : language === 'zh' ? '训练截止:' : language === 'ko' ? '학습 기준시점:' : 'Mốc cắt:'} {formatSystemDateTime(freezeResult.train_cutoff)} · {language === 'en' ? 'Threshold:' : language === 'zh' ? '阈值:' : language === 'ko' ? '임계값:' : 'Ngưỡng:'} {freezeResult.threshold?.toFixed(4)} · {language === 'en' ? 'Features:' : language === 'zh' ? '特征数量:' : language === 'ko' ? '특성 수:' : 'Số đặc trưng:'} {freezeResult.n_features} · {language === 'en' ? 'Train size:' : language === 'zh' ? '样本量:' : language === 'ko' ? '학습 크기:' : 'Dữ liệu huấn luyện:'} {freezeResult.train_size} ({freezeResult.train_positives} {language === 'en' ? 'dumps' : language === 'zh' ? '次暴跌' : language === 'ko' ? '개 덤프' : 'xả'})
              </div>
            ) : (
              <div className="bg-red-950/40 border border-red-800/50 text-red-300 p-2 rounded">
                ❌ {freezeResult.error || freezeResult.message || (language === 'en' ? 'Unknown error' : 'Lỗi không xác định')}
              </div>
            )}
          </div>
        )}
      </div>

      {data.models.length === 0 ? (
        <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400 text-center">
          ⬜ {language === 'en' ? 'No frozen models available yet. Run backtest experiments or freeze a model to evaluate new data.' : language === 'zh' ? '暂无冻结模型。请先运行回测或冻结模型以评估新样本。' : language === 'ko' ? '사용 가능한 동결 모델이 없습니다. 백테스트를 실행하거나 모델을 동결하세요.' : 'Chưa có mô hình nào đóng băng. Chạy kiểm thử lịch sử từ ứng dụng hoặc CLI rồi đóng băng mô hình để đánh giá dữ liệu mới.'}
        </div>
      ) : (
        <>
          <p className="text-[11px] text-slate-300">
            <strong className="text-amber-400">{data.models.length}</strong> {language === 'en' ? 'frozen models available. Select a model to evaluate on live data:' : language === 'zh' ? '个已冻结模型就绪。选择一个模型以在前向样本上评估:' : language === 'ko' ? '개의 동결 모델이 준비되었습니다. 실시간 데이터 평가를 위해 모델을 선택하세요:' : 'mô hình đã đóng băng. Chọn mô hình để đánh giá dữ liệu mới:'}
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
                      <><Loader2 className="w-3 h-3 animate-spin" /> {language === 'en' ? 'Evaluating...' : language === 'zh' ? '正在评估...' : language === 'ko' ? '평가 중...' : 'Đang đánh giá...'}</>
                    ) : (
                      <><Play className="w-3 h-3" /> {language === 'en' ? 'Evaluate' : language === 'zh' ? '运行评估' : language === 'ko' ? '평가 실행' : 'Chấm điểm'}</>
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
                    <div className="text-slate-500 uppercase">{language === 'en' ? 'Cutoff' : language === 'zh' ? '截止时段' : language === 'ko' ? '기준시점' : 'Mốc cắt'}</div>
                    <div className="text-slate-200 font-mono">{m.train_cutoff.slice(0, 10)}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{language === 'en' ? 'Threshold' : language === 'zh' ? '决策阈值' : language === 'ko' ? '임계값' : 'Ngưỡng'}</div>
                    <div className="text-amber-400 font-mono">{m.threshold.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{language === 'en' ? 'Features' : language === 'zh' ? '特征数' : language === 'ko' ? '특성 수' : 'Đặc trưng'}</div>
                    <div className="text-slate-200 font-mono">{m.n_features}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{language === 'en' ? 'Train Size' : language === 'zh' ? '训练样本量' : language === 'ko' ? '학습 데이터' : 'Cỡ tập huấn luyện'}</div>
                    <div className="text-slate-200 font-mono">{m.training_stats?.train_size ?? '—'}</div>
                  </div>
                  <div className="bg-slate-900 p-1.5 rounded">
                    <div className="text-slate-500 uppercase">{language === 'en' ? 'Train Positives' : language === 'zh' ? '训练阳性样本' : language === 'ko' ? '양성 샘플' : 'Mẫu xả khi huấn luyện'}</div>
                    <div className="text-emerald-400 font-mono">{m.training_stats?.train_positives ?? '—'}</div>
                  </div>
                </div>
                {m.label_spec && (
                  <div className="mt-2 flex gap-2 text-[10px] font-mono">
                    <span className="bg-amber-950/60 text-amber-300 px-2 py-0.5 rounded border border-amber-500/20">
                      {language === 'en' ? 'Target:' : language === 'zh' ? '目标:' : language === 'ko' ? '목표:' : 'Mục tiêu:'} {m.label_spec.target_pct}
                    </span>
                    <span className="bg-sky-950/60 text-sky-300 px-2 py-0.5 rounded border border-sky-500/20">
                      MAE: {m.label_spec.mae_pct}
                    </span>
                    <span className="bg-emerald-950/60 text-emerald-300 px-2 py-0.5 rounded border border-emerald-500/20">
                      {language === 'en' ? 'Horizon:' : language === 'zh' ? '周期:' : language === 'ko' ? '시간:' : 'Khung:'} {m.label_spec.horizon_h}
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
                            <div className="text-[9px] text-slate-400 uppercase">{language === 'en' ? 'Precision' : language === 'zh' ? '精准率' : language === 'ko' ? '정밀도' : 'Độ chính xác'}</div>
                            <div className="text-sm font-bold text-amber-400 font-mono">
                              {(result.metrics!.precision * 100).toFixed(1)}%
                            </div>
                            <div className="text-[9px] text-slate-500">
                              {language === 'en' ? 'vs training:' : language === 'zh' ? '对比训练集:' : language === 'ko' ? '학습 대비:' : 'so với huấn luyện:'} {result.training_metrics!.precision > 0 ? `${((result.metrics!.precision - result.training_metrics!.precision) * 100).toFixed(+1)} pp` : '—'}
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2 rounded">
                            <div className="text-[9px] text-slate-400 uppercase">{language === 'en' ? 'Recall' : language === 'zh' ? '召回率' : language === 'ko' ? '재현율' : 'Tỷ lệ bắt'}</div>
                            <div className="text-sm font-bold text-sky-400 font-mono">
                              {(result.metrics!.recall * 100).toFixed(1)}%
                            </div>
                            <div className="text-[9px] text-slate-500">
                              {language === 'en' ? 'vs training:' : language === 'zh' ? '对比训练集:' : language === 'ko' ? '학습 대비:' : 'so với huấn luyện:'} {result.training_metrics!.recall > 0 ? `${((result.metrics!.recall - result.training_metrics!.recall) * 100).toFixed(+1)} pp` : '—'}
                            </div>
                          </div>
                          <div className="bg-slate-900 p-2 rounded">
                            <div className="text-[9px] text-slate-400 uppercase">{language === 'en' ? 'Brier Score' : language === 'zh' ? '布里尔分' : language === 'ko' ? '브라이어 점수' : 'Điểm Brier'}</div>
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
                            {language === 'en' 
                              ? '🔴 Drift detected — out-of-sample precision degraded >10% vs training. Retraining recommended.'
                              : language === 'zh'
                              ? '🔴 检测到概念漂移 — 样本外精准率相比训练集下降 >10%。建议重新校准并再训练。'
                              : language === 'ko'
                              ? '🔴 드리프트 감지됨 — 외래 정밀도가 학습 대비 >10% 하락했습니다. 재학습을 권장합니다.'
                              : '🔴 Phát hiện trôi dịch — độ chính xác giảm >10% so với lúc huấn luyện. Mô hình cần huấn luyện lại trước khi dùng thật.'}
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-[11px] text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 p-2 rounded mb-2">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            {language === 'en' 
                              ? '✅ Model Stable — out-of-sample precision is consistent with training benchmark. Production ready.'
                              : language === 'zh'
                              ? '✅ 模型状态稳定 — 样本外精度与基准测试表现一致，可直接用于生产雷达。'
                              : language === 'ko'
                              ? '✅ 모델 안정적 — 외래 정밀도가 학습 기준선과 일치합니다. 실전 배포 가능.'
                              : '✅ Mô hình ổn định — độ chính xác ngoài mẫu gần bằng lúc huấn luyện. Có thể dùng cho bộ quét.'}
                          </div>
                        )}

                        {/* Risk breakdown */}
                        {result.risk_breakdown && Object.keys(result.risk_breakdown).length > 0 && (
                          <div>
                            <h5 className="text-[11px] font-bold text-slate-300 mb-1.5">{language === 'en' ? 'Performance by Risk Tier' : language === 'zh' ? '各风险等级表现细分' : language === 'ko' ? '위험 등급별 성과 분석' : 'Phân tích theo mức nguy cơ'}</h5>
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-[10px] text-slate-300 font-mono">
                                <thead className="text-slate-400 uppercase border-b border-slate-800">
                                  <tr>
                                    <th className="p-1.5">{language === 'en' ? 'Tier' : language === 'zh' ? '风险层级' : language === 'ko' ? '등급' : 'Mức'}</th>
                                    <th className="p-1.5">{language === 'en' ? 'Signals' : language === 'zh' ? '预警次数' : language === 'ko' ? '신호수' : 'Tín hiệu'}</th>
                                    <th className="p-1.5">{language === 'en' ? 'Actual Dumps' : language === 'zh' ? '真实见顶' : language === 'ko' ? '실제 덤프' : 'Thực xả'}</th>
                                    <th className="p-1.5">{language === 'en' ? 'Precision' : language === 'zh' ? '精准度' : language === 'ko' ? '정밀도' : 'Chính xác'}</th>
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
                          {language === 'en' ? 'Forward rows:' : language === 'zh' ? '前向样本行数:' : language === 'ko' ? '전진 행 수:' : 'Dòng dữ liệu mới:'} {result.n_forward_rows} · {language === 'en' ? 'Positive labels:' : language === 'zh' ? '真实阳性:' : language === 'ko' ? '양성 레이블:' : 'Nhãn dương:'} {result.n_positive_labels} · {language === 'en' ? 'Predicted positive:' : language === 'zh' ? '预测阳性:' : language === 'ko' ? '예측 양성:' : 'Dự đoán dương:'} {result.n_predicted_positive}
                        </div>
                      </>
                    ) : (
                      <div className="flex items-center gap-2 text-[11px] text-amber-400 bg-amber-950/40 border border-amber-800/50 p-2 rounded">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {result.message || `${language === 'en' ? 'Status:' : language === 'zh' ? '状态:' : language === 'ko' ? '상태:' : 'Trạng thái:'} ${result.status}`}
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
