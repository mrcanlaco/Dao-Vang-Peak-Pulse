import React, { useState, useEffect } from 'react';
import {
  X, Scale, Trophy, Zap,
  ArrowUpRight, ArrowDownRight, RefreshCw, Layers
} from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';
import type { EngineComparisonResponse } from '../types';

interface ModelComparisonModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ModelComparisonModal: React.FC<ModelComparisonModalProps> = ({
  isOpen,
  onClose,
}) => {
  const { t } = useTranslation();
  const [data, setData] = useState<EngineComparisonResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchComparison = async () => {
    setIsLoading(true);
    try {
      const res = await fetch('/api/models/comparison-matrix');
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (e) {
      console.error('Failed to fetch model comparison', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchComparison();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const v1 = data?.comparison?.v1;
  const v2 = data?.comparison?.v2;
  const verdict = data?.verdict;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-3xl w-full p-4 sm:p-6 shadow-2xl space-y-4 my-auto">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-violet-500/10 border border-violet-500/30 text-violet-400">
              <Scale className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold text-slate-100 flex items-center gap-2">
                {t('model_comparison_title') || 'So Sánh Hiệu Năng A/B Engine'}
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-violet-950 text-violet-300 border border-violet-700">
                  V1 vs V2
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                {t('model_comparison_subtitle') || 'Đánh giá định lượng độ chính xác thực tế & R:R trên dữ liệu thị trường'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchComparison}
              disabled={isLoading}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Winner Banner */}
        {verdict && (
          <div className="bg-gradient-to-r from-amber-500/15 via-emerald-500/15 to-violet-500/15 border border-amber-500/30 rounded-xl p-3.5 flex items-start gap-3">
            <Trophy className="w-6 h-6 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="flex items-center gap-2 font-bold text-sm text-amber-300">
                <span>{t('model_verdict_winner') || 'Mô Hình Vượt Trội:'}</span>
                <span className="text-emerald-400 font-mono">{verdict.winner}</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                {verdict.explanation}
              </p>
            </div>
          </div>
        )}

        {/* Side by Side Comparison Grid */}
        {v1 && v2 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {/* V1 Card */}
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                <div>
                  <div className="text-xs text-slate-400 uppercase font-mono">{t('model_arm_v1') || 'Arm A: Classic'}</div>
                  <div className="font-bold text-sm text-slate-200">{v1.engine_name}</div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
                  {v1.total_signals} signals
                </span>
              </div>

              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between items-center bg-slate-900/60 p-2 rounded">
                  <span className="text-slate-400">{t('metric_tp1_hit_rate') || 'Đạt Mục Tiêu TP1 (-4%)'}:</span>
                  <span className="font-bold text-emerald-400">{v1.tp1_hit_rate}%</span>
                </div>
                <div className="flex justify-between items-center bg-slate-900/60 p-2 rounded">
                  <span className="text-slate-400">{t('metric_tp2_hit_rate') || 'Đạt Mục Tiêu TP2 (-8%)'}:</span>
                  <span className="font-bold text-emerald-400">{v2.tp2_hit_rate}%</span>
                </div>
                <div className="flex justify-between items-center bg-slate-900/60 p-2 rounded">
                  <span className="text-slate-400">{t('metric_sl_breach_rate') || 'Dính Stop Loss (+4%)'}:</span>
                  <span className="font-bold text-red-400">{v1.sl_breach_rate}%</span>
                </div>
                <div className="flex justify-between items-center bg-slate-900/60 p-2 rounded">
                  <span className="text-slate-400">{t('metric_avg_rr') || 'Tỷ lệ Lợi Nhuận / Rủi Ro (R:R)'}:</span>
                  <span className="font-bold text-amber-300">1 : {v1.avg_risk_reward}</span>
                </div>
                <div className="flex justify-between items-center bg-slate-900/60 p-2 rounded">
                  <span className="text-slate-400">{t('metric_mae') || 'Mức Trượt Giá Ngược (MAE)'}:</span>
                  <span className="font-bold text-red-300">+{v1.avg_mae}%</span>
                </div>
                <div className="flex justify-between items-center bg-slate-900/60 p-2 rounded">
                  <span className="text-slate-400">{t('metric_lead_time') || 'Báo Trước Đỉnh Trung Bình'}:</span>
                  <span className="text-slate-300">{v1.mean_lead_time_min} min</span>
                </div>
              </div>
            </div>

            {/* V2 Card (Challenger / 2-Tier) */}
            <div className="bg-gradient-to-b from-violet-950/20 to-slate-950/80 border-2 border-violet-500/40 rounded-xl p-4 space-y-3 shadow-lg shadow-violet-950/30">
              <div className="flex items-center justify-between pb-2 border-b border-violet-900/40">
                <div>
                  <div className="text-xs text-violet-400 uppercase font-mono flex items-center gap-1">
                    <Zap className="w-3 h-3 text-amber-400" />
                    {t('model_arm_v2') || 'Arm B: 2-Tier Climax'}
                  </div>
                  <div className="font-bold text-sm text-violet-200">{v2.engine_name}</div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-violet-900/60 text-violet-200 border border-violet-700">
                  {v2.total_signals} signals
                </span>
              </div>

              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between items-center bg-violet-950/30 border border-violet-800/30 p-2 rounded">
                  <span className="text-slate-300">{t('metric_tp1_hit_rate') || 'Đạt Mục Tiêu TP1 (-4%)'}:</span>
                  <span className="font-bold text-emerald-400 flex items-center gap-1">
                    {v2.tp1_hit_rate}%
                    <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                  </span>
                </div>
                <div className="flex justify-between items-center bg-violet-950/30 border border-violet-800/30 p-2 rounded">
                  <span className="text-slate-300">{t('metric_tp2_hit_rate') || 'Đạt Mục Tiêu TP2 (-8%)'}:</span>
                  <span className="font-bold text-emerald-400 flex items-center gap-1">
                    {v2.tp2_hit_rate}%
                    <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                  </span>
                </div>
                <div className="flex justify-between items-center bg-violet-950/30 border border-violet-800/30 p-2 rounded">
                  <span className="text-slate-300">{t('metric_sl_breach_rate') || 'Dính Stop Loss (+4%)'}:</span>
                  <span className="font-bold text-emerald-400 flex items-center gap-1">
                    {v2.sl_breach_rate}%
                    <ArrowDownRight className="w-3.5 h-3.5 text-emerald-400" />
                  </span>
                </div>
                <div className="flex justify-between items-center bg-violet-950/30 border border-violet-800/30 p-2 rounded">
                  <span className="text-slate-300">{t('metric_avg_rr') || 'Tỷ lệ Lợi Nhuận / Rủi Ro (R:R)'}:</span>
                  <span className="font-bold text-amber-300 flex items-center gap-1">
                    1 : {v2.avg_risk_reward}
                    <ArrowUpRight className="w-3.5 h-3.5 text-amber-400" />
                  </span>
                </div>
                <div className="flex justify-between items-center bg-violet-950/30 border border-violet-800/30 p-2 rounded">
                  <span className="text-slate-300">{t('metric_mae') || 'Mức Trượt Giá Ngược (MAE)'}:</span>
                  <span className="font-bold text-emerald-400">+{v2.avg_mae}%</span>
                </div>
                <div className="flex justify-between items-center bg-violet-950/30 border border-violet-800/30 p-2 rounded">
                  <span className="text-slate-300">{t('metric_lead_time') || 'Báo Trước Đỉnh Trung Bình'}:</span>
                  <span className="text-slate-300">{v2.mean_lead_time_min} min</span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-8 text-center text-slate-500 font-mono text-xs">
            {isLoading ? 'Đang tính toán ma trận so sánh từ dữ liệu DuckDB...' : 'Không có dữ liệu so sánh.'}
          </div>
        )}

        {/* Architectural Highlights */}
        <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-3.5 text-xs text-slate-400 space-y-2">
          <div className="font-bold text-slate-200 flex items-center gap-1.5">
            <Layers className="w-4 h-4 text-violet-400" />
            <span>{t('model_architecture_why') || 'Tại sao Kiến trúc 2 Tầng (V2) đạt độ chính xác cao hơn?'}</span>
          </div>
          <ul className="list-disc list-inside space-y-1 text-slate-300 pl-1">
            <li><strong>Tầng 1 (Bối cảnh Khung lớn):</strong> Chỉ kích hoạt trạng thái ARMED khi coin đã tăng nóng cực đại (+20% đến +100%) và chạm cản thanh khoản (Không chờ nến đóng đỏ).</li>
            <li><strong>Tầng 2 (Dòng tiền xả 5m):</strong> Bắt tức thì nhịp xả hàng đầu tiên (OI giảm đột ngột + Taker Sell áp đảo + Râu nến xả), cho phép vào lệnh sát đỉnh với Stop Loss ngắn (+3.5%).</li>
          </ul>
        </div>
      </div>
    </div>
  );
};
