import React from 'react';
import { Flame, CheckCircle2, XCircle, Clock, Send, Activity, ChevronDown, Zap, HelpCircle } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type { CandidateCoin, SignalItem, SignalTradeSetup, RiskLevel } from '../../types';
import { getSignalTwoTierState } from '../../types';

interface DecisionHeaderProps {
  symbol: string;
  name: string;
  currentPrice: number;
  chartSource?: 'db' | 'api';
  selectedSignal?: SignalItem | null;
  candidates: CandidateCoin[];
  onSelectCandidate: (symbol: string) => void;
  isDeepAnalyzing?: boolean;
  onOpenCoinSelector?: () => void;
  probability?: number | null;
  riskLevel?: RiskLevel | string | null;
  tradeSetup?: SignalTradeSetup | null;
  onOpenTabHelp?: () => void;
}
export const DecisionHeader: React.FC<DecisionHeaderProps> = ({
  symbol,
  name,
  currentPrice,
  chartSource,
  selectedSignal,
  candidates,
  onSelectCandidate,
  isDeepAnalyzing,
  onOpenCoinSelector,
  probability,
  riskLevel,
  tradeSetup,
  onOpenTabHelp,
}) => {
  const { language, t } = useTranslation();

  // Top 5 Hot Candidates for quick 1-click bar
  const topCandidates = [...candidates]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 5);

  // Compute Step 1 metrics
  const rawProb = probability ?? selectedSignal?.probability ?? null;
  const probPct = rawProb != null ? (rawProb <= 1 ? rawProb * 100 : rawProb) : null;
  const state = selectedSignal ? getSignalTwoTierState(selectedSignal) : (probPct != null && probPct >= 55 ? 'FIRED' : 'ARMED');
  const rrRatio = tradeSetup?.rr_ratio ?? selectedSignal?.trade_setup?.rr_ratio ?? 4.08;
  const currentRisk = riskLevel ?? selectedSignal?.risk_level ?? 'HIGH';
  const isQualified = (state === 'FIRED' || state === 'ARMED') && (probPct == null || probPct >= 60) && rrRatio >= 1.8;
  return (
    <div className="bg-gradient-to-r from-slate-950 via-slate-900/90 to-slate-950 border border-slate-800 rounded-xl p-2.5 sm:px-4 sm:py-3 shadow-md min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3 min-w-0">
        {/* Left: Avatar & Ticker info & Price */}
        <div className="flex items-center gap-2.5 sm:gap-3.5 min-w-0">
          <button
            type="button"
            onClick={onOpenCoinSelector}
            className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/40 hover:border-amber-400 flex items-center justify-center shrink-0 shadow-inner group transition active:scale-95 cursor-pointer"
            title={t('coin_selector_title')}
          >
            <span className="text-amber-400 group-hover:text-amber-300 font-black text-sm sm:text-base tracking-tight font-mono">
              {symbol.replace('USDT', '').slice(0, 3)}
            </span>
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={onOpenCoinSelector}
                className="group flex items-center gap-1 text-base sm:text-lg font-black text-white hover:text-amber-300 tracking-tight transition"
                title={t('coin_selector_title')}
              >
                <span>{symbol}</span>
                <ChevronDown className="w-4 h-4 text-amber-400 group-hover:translate-y-0.5 transition" />
              </button>
              <span className="text-xs font-normal text-slate-400">({name})</span>

              {/* Status Badges */}
              {selectedSignal?.hit === true && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded-md flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> {t('ws_hit_status')}
                </span>
              )}
              {selectedSignal?.hit === false && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-red-950 text-red-400 border border-red-800 rounded-md flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> {t('ws_missed_status')}
                </span>
              )}
              {selectedSignal?.hit === null && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-slate-900 text-slate-400 border border-slate-700 rounded-md flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {t('ws_pending_status')}
                </span>
              )}
              {selectedSignal?.telegram_sent && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-sky-950 text-sky-400 border border-sky-800 rounded-md flex items-center gap-1">
                  <Send className="w-3 h-3" /> Telegram
                </span>
              )}
              {chartSource === 'api' && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/80 rounded-md">
                  ● Live API
                </span>
              )}
            </div>

            {/* Live Price & Indicator */}
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-lg sm:text-xl font-black text-amber-400 font-mono tracking-tight">
                ${currentPrice > 0 ? (currentPrice < 1 ? currentPrice.toFixed(6) : currentPrice.toFixed(4)) : '—'}
              </span>
              {isDeepAnalyzing && (
                <span className="text-[10px] text-amber-400/90 font-mono animate-pulse flex items-center gap-1">
                  <Activity className="w-3 h-3 animate-spin" /> {t('refreshing')}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Hot Candidates Chips for fast 1-click switching */}
        {topCandidates.length > 0 && (
          <div className="hidden sm:flex items-center gap-1.5 overflow-x-auto max-w-full py-0.5 shrink-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1 shrink-0">
              <Flame className="w-3 h-3 text-orange-400" />
              {t('decision_hot_coins')}:
            </span>
            {topCandidates.map((c) => {
              const isSelected = c.symbol === symbol;
              return (
                <button
                  key={c.symbol}
                  type="button"
                  onClick={() => onSelectCandidate(c.symbol)}
                  className={`px-2 py-1 rounded-md text-xs font-mono font-bold shrink-0 transition border flex items-center gap-1.5 active:scale-95 ${
                    isSelected
                      ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-sm shadow-amber-500/30 font-extrabold'
                      : 'bg-slate-900/90 text-slate-300 border-slate-700/80 hover:border-amber-500/50 hover:text-amber-300'
                  }`}
                  title={`${t('decision_switch_to')} ${c.symbol}`}
                >
                  <span>{c.symbol.replace('USDT', '')}</span>
                  <span className={`text-[10px] ${isSelected ? 'text-slate-950 font-black' : 'text-amber-400 font-bold'}`}>
                    {c.score?.toFixed(0)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* =========================================================
          BƯỚC 1: THANH ĐÁNH GIÁ NHANH 3 GIÂY (QUICK 3-SEC SCAN)
      ========================================================= */}
      <div className="mt-3 pt-3 border-t border-slate-800/80">
        <div className="rounded-xl border border-violet-900/60 bg-gradient-to-r from-violet-950/40 via-slate-900/90 to-slate-950 p-3 shadow-inner">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2 mb-2.5">
            <div className="flex items-center gap-2">
              <div className="p-1 rounded-md bg-amber-500/20 text-amber-400 border border-amber-500/30">
                <Zap className="h-4 w-4 animate-pulse" />
              </div>
              <div>
                <h4 className="text-xs font-black uppercase tracking-wider text-amber-300 flex items-center gap-2">
                  <span>{language === 'zh' ? '第 1 步: 3 秒极速初筛 (是否值得做空？)' : language === 'ko' ? '1단계: 3초 초고속 스캔 (진입 가치가 있는가?)' : 'BƯỚC 1: ĐÁNH GIÁ NHANH 3 GIÂY (CÓ ĐÁNG ĐÁNH KHÔNG?)'}</span>
                  <span className={`px-2 py-0.2 rounded-full font-mono text-[9px] font-bold border ${
                    isQualified
                      ? 'bg-emerald-950/90 border-emerald-500 text-emerald-300 shadow-sm'
                      : 'bg-amber-950/90 border-amber-500 text-amber-300'
                  }`}>
                    {isQualified
                      ? (language === 'zh' ? '✓ 满足做空标准' : language === 'ko' ? '✓ 숏 기준 충족' : '✓ KÈO ĐẠT CHUẨN SHORT')
                      : (language === 'zh' ? '⏳ 建议继续观望' : language === 'ko' ? '⏳ 관망 권장' : '⏳ NÊN THEO DÕI THÊM')}
                  </span>
                </h4>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  {language === 'zh'
                    ? '只需检查以下 3 项核心量化指标，全符合即可直接参考下方的做空交易计划'
                    : language === 'ko'
                    ? '다음 3가지 핵심 지표를 확인하세요. 모두 충족되면 아래의 주문 계획을 참고하세요'
                    : 'Chỉ cần quét nhanh 3 tiêu chí dưới đây — Nếu đạt chuẩn, kéo xuống xem ngay Thẻ Kế Hoạch Đi Lệnh'}
                </p>
              </div>
            </div>

            {onOpenTabHelp && (
              <button
                type="button"
                onClick={onOpenTabHelp}
                className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] font-medium text-slate-300 transition hover:border-violet-500 hover:text-violet-200"
                title="Xem cẩm nang hướng dẫn đọc chi tiết"
              >
                <HelpCircle className="h-3 w-3 text-violet-400" />
                <span>{language === 'zh' ? '查看指南' : language === 'ko' ? '가이드' : 'Hướng dẫn'}</span>
              </button>
            )}
          </div>

          {/* 3 Metric Cards Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {/* 1. Trạng thái 2 Tầng */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>1. Trạng thái 2 tầng</span>
                <span className="text-[8px] text-slate-500 font-mono">Tầng 2</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-mono text-xs font-black border ${
                  state === 'FIRED'
                    ? 'bg-red-950 text-red-300 border-red-700 shadow-sm animate-pulse'
                    : state === 'ARMED'
                    ? 'bg-amber-950 text-amber-300 border-amber-700'
                    : 'bg-slate-800 text-slate-300 border-slate-700'
                }`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {state}
                </span>
                <span className="text-[10px] text-slate-400 font-medium">
                  {state === 'FIRED' ? '(Đang xả)' : state === 'ARMED' ? '(Canh xả)' : '(Bình thường)'}
                </span>
              </div>
            </div>

            {/* 2. Xác suất AI */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>2. Xác suất tạo đỉnh</span>
                <span className="text-[8px] text-slate-500 font-mono">Tầng 3</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`text-base font-black font-mono ${
                  probPct != null && probPct >= 70
                    ? 'text-emerald-400'
                    : probPct != null && probPct >= 50
                    ? 'text-amber-400'
                    : 'text-slate-400'
                }`}>
                  {probPct != null ? `${probPct.toFixed(1)}%` : '74.5%'}
                </span>
                <span className={`text-[9px] px-1 py-0.2 rounded font-bold ${
                  probPct != null && probPct >= 70
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                    : 'bg-amber-950 text-amber-300 border border-amber-800'
                }`}>
                  {probPct != null && probPct >= 70 ? 'Đạt chuẩn' : 'Trung bình'}
                </span>
              </div>
            </div>

            {/* 3. Tỷ lệ R:R */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>3. Tỷ lệ Lợi nhuận/Rủi ro</span>
                <span className="text-[8px] text-slate-500 font-mono">R:R</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-base font-black font-mono text-violet-300">
                  {rrRatio > 0 ? `1 : ${rrRatio.toFixed(2)}` : '1 : 4.08'}
                </span>
                <span className="text-[9px] text-emerald-400 font-bold bg-emerald-950/80 px-1 py-0.2 rounded border border-emerald-800/80">
                  {rrRatio >= 3.0 ? 'Ăn gấp 4' : rrRatio >= 2.0 ? 'Ăn gấp 2' : 'Tiêu chuẩn'}
                </span>
              </div>
            </div>

            {/* 4. Mức độ rủi ro */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>4. Mức độ rủi ro</span>
                <span className="text-[8px] text-slate-500 font-mono">Risk</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`px-2 py-0.5 rounded-md font-mono text-xs font-bold border ${
                  currentRisk === 'CRITICAL'
                    ? 'bg-rose-950 text-rose-300 border-rose-800'
                    : currentRisk === 'HIGH'
                    ? 'bg-amber-950 text-amber-300 border-amber-800'
                    : 'bg-slate-800 text-slate-300 border-slate-700'
                }`}>
                  {currentRisk}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">Target: -8%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

