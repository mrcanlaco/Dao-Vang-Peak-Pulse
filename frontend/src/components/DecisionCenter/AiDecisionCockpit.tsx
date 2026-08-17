import React from 'react';
import {
  TrendingDown, Eye, CheckCircle2, Zap, Send, XCircle, Loader2,
  Activity, Flame
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import { getRiskLabel, getBtcRegimeLabel } from '../../i18n/translations';
import type { CoinDetail, DeepAnalysis, SignalItem } from '../../types';

interface AiDecisionCockpitProps {
  selectedSignal?: SignalItem | null;
  displayDetail: CoinDetail;
  deepAnalysis?: DeepAnalysis | null;
  isDeepAnalyzing?: boolean;
  isSymbolTracked?: boolean;
  isSymbolInWatchlist?: boolean;
  isWatchlistUpdating?: boolean;
  onRunDeepAnalysis: (symbol: string) => void;
  onPushTelegram?: (sig: SignalItem) => void;
  onDismissSignal?: (sig: SignalItem) => void;
  onAddWatchlist?: (symbol: string) => void | Promise<boolean | void>;
  onAddTracking?: (symbol: string) => void | Promise<boolean | void>;
}

export const AiDecisionCockpit: React.FC<AiDecisionCockpitProps> = ({
  selectedSignal,
  displayDetail,
  deepAnalysis,
  isDeepAnalyzing,
  isSymbolTracked,
  isSymbolInWatchlist,
  isWatchlistUpdating,
  onRunDeepAnalysis,
  onPushTelegram,
  onDismissSignal,
  onAddWatchlist,
  onAddTracking,
}) => {
  const { language, t } = useTranslation();
  const isEn = language === 'en';
  
  const riskLabels: Record<string, string> = {
    CRITICAL: getRiskLabel('CRITICAL', language),
    HIGH: getRiskLabel('HIGH', language),
    MEDIUM: getRiskLabel('MEDIUM', language),
    SAFE: getRiskLabel('SAFE', language),
  };

  const btcRegimeLabels: Record<string, string> = {
    FOMO: getBtcRegimeLabel('FOMO', language),
    WEAK: getBtcRegimeLabel('WEAK', language),
    NEUTRAL: getBtcRegimeLabel('NEUTRAL', language),
  };

  const rawProbability = deepAnalysis?.calibrated_probability ?? deepAnalysis?.model_probability;
  const deepProbabilityPct = rawProbability != null ? (rawProbability <= 1.0 ? rawProbability * 100 : rawProbability) : null;
  const deepThreshold = deepAnalysis?.probability_threshold;
  const deepProbabilityThresholdPct = deepThreshold != null ? (deepThreshold <= 1.0 ? deepThreshold * 100 : deepThreshold) : 60;

  const recommendation = deepAnalysis?.recommendation || (displayDetail.probability && displayDetail.probability >= 60 ? 'SHORT_CANDIDATE' : 'WATCH');

  return (
    <div className="space-y-3 min-w-0">
      {/* AI Recommendation Banner */}
      <div className={`rounded-xl p-3.5 border-2 shadow-lg transition-all ${
        recommendation === 'SHORT_CANDIDATE'
          ? 'bg-gradient-to-br from-red-950/60 via-slate-950 to-slate-900 border-red-700/80 shadow-red-950/30'
          : recommendation === 'WATCH'
          ? 'bg-gradient-to-br from-amber-950/60 via-slate-950 to-slate-900 border-amber-700/80 shadow-amber-950/30'
          : 'bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 border-slate-700 shadow-slate-950/30'
      }`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center shadow-inner shrink-0 ${
              recommendation === 'SHORT_CANDIDATE' ? 'bg-red-900/80 border border-red-500/50 text-red-200' :
              recommendation === 'WATCH' ? 'bg-amber-900/80 border border-amber-500/50 text-amber-200' :
              'bg-slate-800 border border-slate-700 text-slate-300'
            }`}>
              {recommendation === 'SHORT_CANDIDATE' ? (
                <TrendingDown className="w-6 h-6 text-red-400" />
              ) : recommendation === 'WATCH' ? (
                <Eye className="w-6 h-6 text-amber-400" />
              ) : (
                <CheckCircle2 className="w-6 h-6 text-slate-400" />
              )}
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">
                {t('ws_ai_recommendation')}
              </div>
              <div className={`text-base sm:text-lg font-black tracking-tight ${
                recommendation === 'SHORT_CANDIDATE' ? 'text-red-400' :
                recommendation === 'WATCH' ? 'text-amber-400' : 'text-slate-300'
              }`}>
                {recommendation === 'SHORT_CANDIDATE' ? t('ws_rec_short_badge') : recommendation === 'WATCH' ? t('ws_rec_watch_badge') : t('ws_rec_standby_badge')}
              </div>
              <div className="mt-0.5 flex items-center gap-1.5">
                <span className={`px-2 py-0.2 rounded text-[9px] font-bold border ${
                  displayDetail.risk_level === 'CRITICAL' ? 'bg-red-950 text-red-300 border-red-800' :
                  displayDetail.risk_level === 'HIGH' ? 'bg-amber-950 text-amber-300 border-amber-800' :
                  displayDetail.risk_level === 'MEDIUM' ? 'bg-yellow-950 text-yellow-300 border-yellow-800' :
                  'bg-slate-800 text-slate-300 border-slate-700'
                }`}>
                  {displayDetail.risk_level ? (riskLabels[displayDetail.risk_level] ?? displayDetail.risk_level) : (isEn ? 'NO DATA' : 'CHƯA CÓ DỮ LIỆU')}
                </span>
              </div>
            </div>
          </div>

          {/* Probability Gauge */}
          <div className="text-right shrink-0">
            <div className="text-[10px] text-slate-400 uppercase font-mono">
              {isEn ? 'AI DUMP PROB' : 'XÁC SUẤT XẢ'}
            </div>
            <div className="text-2xl sm:text-3xl font-black text-amber-400 font-mono tracking-tight">
              {deepProbabilityPct != null
                ? deepProbabilityPct.toFixed(1)
                : displayDetail.probability != null
                ? displayDetail.probability.toFixed(1)
                : '—'}
              <span className="text-xs text-slate-500 font-normal">/100</span>
            </div>
            <div className="text-[9px] text-slate-400 font-mono">
              {deepProbabilityThresholdPct != null ? `${t('threshold')}: ${deepProbabilityThresholdPct.toFixed(0)}` : ''}
            </div>
          </div>
        </div>

        {/* Probability Gauge Progress Bar */}
        <div className="mt-3">
          <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                (deepProbabilityPct ?? displayDetail.probability ?? 0) >= (deepProbabilityThresholdPct ?? 60)
                  ? 'bg-gradient-to-r from-orange-500 to-red-500 shadow-md shadow-red-500/50'
                  : (deepProbabilityPct ?? displayDetail.probability ?? 0) >= 40
                  ? 'bg-gradient-to-r from-amber-500 to-orange-500'
                  : 'bg-slate-600'
              }`}
              style={{ width: `${Math.min(100, Math.max(0, deepProbabilityPct ?? displayDetail.probability ?? 0))}%` }}
            />
          </div>
        </div>
      </div>

      {/* Action Buttons Grid */}
      <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 shadow-md space-y-2">
        <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
          {isEn ? 'QUICK ACTIONS' : 'THAO TÁC NHANH'}
        </div>
        <div className="grid grid-cols-2 gap-2">
          {/* Re-score Button */}
          <button
            onClick={() => onRunDeepAnalysis(displayDetail.symbol)}
            disabled={isDeepAnalyzing}
            className="px-3 py-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition shadow-md shadow-amber-500/20"
          >
            {isDeepAnalyzing ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" /> {isEn ? 'Re-scoring...' : 'Đang tính...'}</>
            ) : (
              <><Zap className="w-3.5 h-3.5" /> {isEn ? 'Re-score Analysis' : 'Chạy lại chấm điểm'}</>
            )}
          </button>

          {/* Telegram Send */}
          {selectedSignal ? (
            <button
              onClick={() => onPushTelegram && onPushTelegram(selectedSignal)}
              className="px-3 py-2 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition shadow-md shadow-sky-500/20"
            >
              <Send className="w-3.5 h-3.5" /> {isEn ? 'Send Telegram' : 'Gửi Telegram'}
            </button>
          ) : (
            <div className="px-3 py-2 bg-slate-900 border border-slate-800 text-slate-500 rounded-lg text-xs text-center font-mono">
              {isEn ? 'No Telegram Signal' : 'Chưa có tín hiệu'}
            </div>
          )}

          {/* Track Position */}
          {onAddTracking && (
            <button
              onClick={() => void onAddTracking(displayDetail.symbol)}
              disabled={isWatchlistUpdating || isSymbolTracked}
              className={`px-3 py-2 border font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition disabled:cursor-not-allowed disabled:opacity-70 ${
                isSymbolTracked
                  ? 'bg-sky-500/15 text-sky-300 border-sky-500/40'
                  : 'bg-slate-900 hover:bg-sky-950 text-slate-300 hover:text-sky-400 border-slate-700 hover:border-sky-800'
              }`}
            >
              {isWatchlistUpdating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSymbolTracked ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              {isSymbolTracked ? (isEn ? 'Tracking Position' : 'Đang theo dõi') : (isEn ? 'Track Position' : 'Theo dõi diễn biến')}
            </button>
          )}

          {/* Add to Scan Universe */}
          {onAddWatchlist && (
            <button
              onClick={() => void onAddWatchlist(displayDetail.symbol)}
              disabled={isWatchlistUpdating || isSymbolInWatchlist}
              className={`px-3 py-2 border font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition disabled:cursor-not-allowed disabled:opacity-70 ${
                isSymbolInWatchlist
                  ? 'bg-amber-500/15 text-amber-300 border-amber-500/40'
                  : 'bg-slate-900 hover:bg-amber-950 text-slate-300 hover:text-amber-400 border-slate-700 hover:border-amber-800'
              }`}
            >
              {isWatchlistUpdating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSymbolInWatchlist ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              {isSymbolInWatchlist ? (isEn ? 'In Universe' : 'Đã trong DS quét') : (isEn ? 'Add Universe' : 'Thêm DS quét')}
            </button>
          )}
        </div>

        {selectedSignal && onDismissSignal && (
          <button
            onClick={() => onDismissSignal(selectedSignal)}
            className="w-full mt-1 px-3 py-1.5 bg-slate-900 hover:bg-red-950/80 text-slate-400 hover:text-red-400 border border-slate-800 hover:border-red-800/80 font-bold rounded-lg text-xs flex items-center justify-center gap-1.5 transition"
          >
            <XCircle className="w-3.5 h-3.5" /> {isEn ? 'Dismiss Signal' : 'Ẩn tín hiệu này'}
          </button>
        )}
      </div>

      {/* Market Context & Pump Card */}
      {deepAnalysis && (
        <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 sm:p-3.5 shadow-md space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-amber-400" />
              {isEn ? 'MARKET REGIME & PUMP PATTERN' : 'BỐI CẢNH BTC & BƠM XẢ'}
            </h3>
            <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${
              deepAnalysis.btc_regime === 'FOMO' ? 'bg-emerald-950 text-emerald-300 border-emerald-800' :
              deepAnalysis.btc_regime === 'WEAK' ? 'bg-red-950 text-red-300 border-red-800' :
              'bg-slate-900 text-slate-300 border-slate-700'
            }`}>
              BTC: {btcRegimeLabels[deepAnalysis.btc_regime] ?? deepAnalysis.btc_regime}
            </span>
          </div>

          {/* Pump Analysis */}
          <div className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-[10px] text-slate-400 uppercase font-semibold flex items-center gap-1">
                {deepAnalysis.pump_analysis.detected ? (
                  <Flame className="w-3.5 h-3.5 text-orange-400" />
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" />
                )}
                {isEn ? 'Parabolic Pump Detection' : 'Mẫu hình Tăng Nóng'}
              </span>
              <span className={`font-mono font-bold text-xs ${deepAnalysis.pump_analysis.detected ? 'text-orange-400' : 'text-slate-400'}`}>
                {deepAnalysis.pump_analysis.detected ? `+${deepAnalysis.pump_analysis.pump_pct}% (${deepAnalysis.pump_analysis.pump_days}d)` : isEn ? 'None' : 'Không có'}
              </span>
            </div>

            {deepAnalysis.pump_analysis.detected ? (
              <div className="mt-2 space-y-1.5">
                <div className="flex justify-between text-[10px] font-mono text-slate-300">
                  <span>{isEn ? 'Peak:' : 'Đỉnh:'} ${deepAnalysis.pump_analysis.peak_price.toFixed(4)}</span>
                  <span className={deepAnalysis.pump_analysis.current_vs_peak < -20 ? 'text-red-400 font-bold' : 'text-slate-300'}>
                    {deepAnalysis.pump_analysis.current_vs_peak}% {isEn ? 'from peak' : 'từ đỉnh'}
                  </span>
                </div>
                {/* Progress bar from peak */}
                <div className="relative h-3 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                  <div
                    className="absolute top-0 left-0 h-full bg-gradient-to-r from-orange-600 to-orange-400"
                    style={{ width: `${Math.max(0, Math.min(100, 100 + deepAnalysis.pump_analysis.current_vs_peak))}%` }}
                  />
                </div>
              </div>
            ) : (
              <p className="text-[10px] text-slate-500 mt-1">
                {isEn ? '✓ No parabolic surge detected (50-300% in 1-5d).' : '✓ Không có dấu hiệu tăng quá nóng trong 1-5 ngày gần nhất.'}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Validity & Track Record */}
      {selectedSignal && (
        <div className="grid grid-cols-3 gap-2 text-[10px] bg-slate-950/80 p-2.5 rounded-xl border border-slate-800">
          <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800/80">
            <div className="text-slate-500 uppercase">{isEn ? 'Validity' : 'Hiệu lực'}</div>
            <div className="text-amber-300 font-mono font-bold mt-0.5">
              {Math.floor(selectedSignal.validity_hours_left)}h {Math.floor((selectedSignal.validity_hours_left % 1) * 60)}m
            </div>
          </div>
          <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800/80">
            <div className="text-slate-500 uppercase">{isEn ? 'Lead Time' : 'Báo trước'}</div>
            <div className="text-sky-300 font-mono font-bold mt-0.5">
              {selectedSignal.lead_time_avg_hours > 0 ? `${selectedSignal.lead_time_avg_hours.toFixed(1)}h` : '—'}
            </div>
          </div>
          <div className="bg-slate-900/80 p-2 rounded-lg border border-slate-800/80">
            <div className="text-slate-500 uppercase">{isEn ? 'Precision' : 'Độ chính xác'}</div>
            <div className="text-emerald-300 font-mono font-bold mt-0.5">
              {selectedSignal.evidence_precision != null
                ? `${(selectedSignal.evidence_precision * 100).toFixed(0)}%`
                : (isEn ? 'N/A' : '—')}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
