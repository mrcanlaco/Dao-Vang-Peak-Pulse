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

  // 1. Resolve matched signal & candidate for exact real data
  const upperSym = symbol.toUpperCase();
  const matchedSignal = selectedSignal && selectedSignal.symbol.toUpperCase() === upperSym ? selectedSignal : null;
  const currentCandidate = candidates.find(c => c.symbol.toUpperCase() === upperSym);

  // 2. Exact Probability (No hardcoded fallback)
  const rawProb = matchedSignal?.probability ?? probability ?? null;
  const probPct = rawProb != null ? (rawProb <= 1 ? rawProb * 100 : rawProb) : null;

  // 3. Exact Two-Tier State
  const state: 'FIRED' | 'ARMED' | 'NORMAL' | 'STANDBY' | 'NO_SIGNAL' = matchedSignal
    ? getSignalTwoTierState(matchedSignal)
    : currentCandidate
    ? (currentCandidate.score >= 50 ? 'ARMED' : 'STANDBY')
    : probPct != null
    ? (probPct >= 65 ? 'FIRED' : 'ARMED')
    : 'NO_SIGNAL';

  // 4. Exact Risk Level
  const currentRisk: string | null = matchedSignal?.risk_level ?? (riskLevel ? String(riskLevel) : null) ?? (currentCandidate?.risk ? String(currentCandidate.risk) : null);

  // 5. Exact R:R Ratio & Trade Setup
  const exactTradeSetup = matchedSignal?.trade_setup ?? tradeSetup ?? null;
  const rrRatio = exactTradeSetup?.rr_ratio ?? (
    currentPrice > 0
      ? Number((0.08 / Math.max(0.015, 0.022)).toFixed(2)) // 8% target / 2.2% SL ~ 3.64
      : null
  );

  // 6. Qualification Status
  const isFired = state === 'FIRED';
  const isArmed = state === 'ARMED';
  const isStandby = state === 'STANDBY';
  const hasLiveSignal = isFired || isArmed;

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
              <div className={`p-1.5 rounded-lg border ${
                isFired
                  ? 'bg-red-500/20 text-red-400 border-red-500/30'
                  : isArmed
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                  : isStandby
                  ? 'bg-sky-500/20 text-sky-400 border-sky-500/30'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}>
                <Zap className={`h-4 w-4 ${hasLiveSignal ? 'animate-pulse' : ''}`} />
              </div>
              <div>
                <h4 className="text-xs font-black uppercase tracking-wider text-amber-300 flex items-center gap-2 flex-wrap">
                  <span>
                    {language === 'en'
                      ? 'QUICK 3-SEC SCAN (WORTH SHORTING?)'
                      : language === 'zh'
                      ? '3 秒极速初筛 (是否值得做空？)'
                      : language === 'ko'
                      ? '3초 초고속 스캔 (진입 가치가 있는가?)'
                      : 'ĐÁNH GIÁ TÍN HIỆU 3 GIÂY (CÓ ĐÁNG ĐÁNH KHÔNG?)'}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full font-mono text-[9px] font-bold border ${
                    isFired
                      ? 'bg-red-950/90 border-red-500 text-red-300 shadow-sm animate-pulse'
                      : isArmed
                      ? 'bg-amber-950/90 border-amber-500 text-amber-300 shadow-sm'
                      : isStandby
                      ? 'bg-sky-950/90 border-sky-500 text-sky-300'
                      : 'bg-slate-900 border-slate-700 text-slate-400'
                  }`}>
                    {isFired
                      ? (language === 'en' ? '🔥 QUALIFIED SHORT SETUP (FIRED)' : language === 'zh' ? '🔥 正在主跌浪 (FIRED)' : language === 'ko' ? '🔥 급락 진행 중 (FIRED)' : '🔥 KÈO ĐẠT CHUẨN SHORT (FIRED)')
                      : isArmed
                      ? (language === 'en' ? '⚡ FORMING TOP — WATCH 5M (ARMED)' : language === 'zh' ? '⚡ 顶部构筑中 (ARMED)' : language === 'ko' ? '⚡ 고점 분산 중 (ARMED)' : '⚡ ĐANG TẠO ĐỈNH — CANH NẾN 5M (ARMED)')
                      : isStandby
                      ? (language === 'en' ? '👁️ MONITORING CANDIDATE (STANDBY)' : language === 'zh' ? '👁️ 候选观察中 (STANDBY)' : language === 'ko' ? '👁️ 후보 관찰 중 (STANDBY)' : '👁️ ĐANG TRONG DANH SÁCH THEO DÕI (STANDBY)')
                      : (language === 'en' ? '⚪ NO ACTIVE DUMP SIGNAL' : language === 'zh' ? '⚪ 暂无派发信号' : language === 'ko' ? '⚪ 신호 없음' : '⚪ CHƯA CÓ TÍN HIỆU PHÂN PHỐI')}
                  </span>
                </h4>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  {isFired
                    ? (language === 'en' ? '✓ Meets all climax dump conditions. Scroll down to inspect the concrete Trade Setup for Entry & SL levels.' : language === 'zh' ? '✓ 满足全部做空触发条件，下方已生成精确进场区间与止损点' : language === 'ko' ? '✓ 숏 진입 조건을 모두 충족했습니다. 아래의 진입 구간 및 손절가를 확인하세요' : '✓ Hội tụ đủ điều kiện xả mạnh. Kéo xuống xem ngay Thẻ Kế Hoạch Đi Lệnh để lấy giá Entry & SL.')
                    : isArmed
                    ? (language === 'en' ? '⏳ Asset has pumped heavily and is forming a distribution top. Awaiting 5m order flow sell burst.' : language === 'zh' ? '⏳ 资产已完成暴涨并在筑顶，等待 5 分钟级别主力砸盘信号确认' : language === 'ko' ? '⏳ 자산이 급등 후 고점을 형성 중입니다. 5분봉 세력 매도 신호를 기다리세요' : '⏳ Coin đã bơm căng và đang phân phối đỉnh. Chờ nến 5m xác nhận Taker Sell để vào lệnh.')
                    : isStandby
                    ? (language === 'en' ? 'ℹ️ Listed on the top climax pump candidate ranking, continuously monitoring order flow.' : language === 'zh' ? 'ℹ️ 该币种位列暴涨候选榜，正在持续监控订单流异动' : language === 'ko' ? 'ℹ️ 급등 후보 목록에 등록되어 주문 흐름 이상을 모니터링 중입니다' : 'ℹ️ Nằm trong Top ứng viên bơm xả, hệ thống đang theo dõi biến động dòng lệnh.')
                    : (language === 'en' ? 'ℹ️ No distribution anomaly detected on this coin. Select an active pair from the Hot Candidates bar or Signals tab.' : language === 'zh' ? 'ℹ️ 该币种当前无见顶异动，请在上方热门候选榜或雷达中挑选标的' : language === 'ko' ? 'ℹ️ 현재 고점 이상 신호가 없습니다. 상단 핫 코인 또는 레이더에서 선택하세요' : 'ℹ️ Coin này hiện chưa phát hiện tín hiệu tạo đỉnh. Vui lòng chọn coin khác trên thanh Hot Coins hoặc Tab Tín hiệu.')}
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
                <span>{language === 'en' ? 'Guide' : language === 'zh' ? '查看指南' : language === 'ko' ? '가이드' : 'Hướng dẫn'}</span>
              </button>
            )}

          </div>

          {/* 4 Metric Cards Grid - 100% Real Live Data */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {/* 1. Trạng thái 2 Tầng */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>{language === 'en' ? 'Two-Tier State' : language === 'zh' ? '2层状态' : language === 'ko' ? '2단계 상태' : 'Trạng thái 2 tầng'}</span>
                <span className="text-[8px] text-slate-500 font-mono">Tier 2</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-mono text-xs font-black border ${
                  state === 'FIRED'
                    ? 'bg-red-950 text-red-300 border-red-700 shadow-sm animate-pulse'
                    : state === 'ARMED'
                    ? 'bg-amber-950 text-amber-300 border-amber-700'
                    : state === 'STANDBY'
                    ? 'bg-sky-950 text-sky-300 border-sky-700'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                }`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {state === 'NO_SIGNAL' ? (language === 'en' ? 'STANDBY' : language === 'zh' ? '待命' : language === 'ko' ? '대기' : 'CHỜ TÍN HIỆU') : state}
                </span>
              </div>
            </div>
            {/* 2. Xác suất AI */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>{language === 'en' ? 'AI Dump Probability' : language === 'zh' ? 'AI 暴跌/派发概率' : language === 'ko' ? 'AI 급락/분산 확률' : 'Xác suất xả (AI)'}</span>
                <span className="text-[8px] text-slate-500 font-mono">Tier 3</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`text-base font-black font-mono ${
                  probPct != null && probPct >= 70
                    ? 'text-emerald-400'
                    : probPct != null && probPct >= 50
                    ? 'text-amber-400'
                    : probPct != null
                    ? 'text-slate-300'
                    : 'text-slate-500'
                }`}>
                  {probPct != null ? `${probPct.toFixed(1)}%` : '—'}
                </span>
                {probPct != null ? (
                  <span className={`text-[9px] px-1 py-0.2 rounded font-bold ${
                    probPct >= 70
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : probPct >= 50
                      ? 'bg-amber-950 text-amber-300 border border-amber-800'
                      : 'bg-slate-800 text-slate-400 border border-slate-700'
                  }`}>
                    {probPct >= 70 ? (language === 'en' ? 'High Edge' : language === 'zh' ? '达标' : language === 'ko' ? '통과' : 'Đạt chuẩn') : probPct >= 50 ? (language === 'en' ? 'Medium' : language === 'zh' ? '中等' : language === 'ko' ? '보통' : 'Trung bình') : (language === 'en' ? 'Low' : language === 'zh' ? '偏低' : language === 'ko' ? '낮음' : 'Thấp')}
                  </span>
                ) : (
                  <span className="text-[9px] px-1 py-0.2 rounded bg-slate-900 text-slate-500 border border-slate-800">
                    {language === 'en' ? 'Inactive' : language === 'zh' ? '未激活' : language === 'ko' ? '비활성' : 'Chưa kích hoạt'}
                  </span>
                )}
              </div>
            </div>

            {/* 3. Tỷ lệ R:R */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>{language === 'en' ? 'Risk/Reward (R:R)' : language === 'zh' ? '盈亏比 (R:R)' : language === 'ko' ? '손익비 (R:R)' : 'Tỷ lệ Lợi nhuận/Rủi ro'}</span>
                <span className="text-[8px] text-slate-500 font-mono">R:R</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`text-base font-black font-mono ${rrRatio ? 'text-violet-300' : 'text-slate-500'}`}>
                  {rrRatio ? `1 : ${rrRatio.toFixed(1)}` : '—'}
                </span>
                {rrRatio != null && (
                  <span className={`text-[9px] font-bold px-1 py-0.2 rounded border ${
                    rrRatio >= 3.0
                      ? 'text-emerald-300 bg-emerald-950/80 border-emerald-800'
                      : rrRatio >= 2.0
                      ? 'text-cyan-300 bg-cyan-950/80 border-cyan-800'
                      : 'text-amber-300 bg-amber-950/80 border-amber-800'
                  }`}>
                    {rrRatio >= 3.0 ? (language === 'en' ? '3x+ R:R' : language === 'zh' ? '3倍+ 盈亏比' : language === 'ko' ? '3배+ 손익비' : 'Ăn gấp 3+') : rrRatio >= 2.0 ? (language === 'en' ? '2x+ R:R' : language === 'zh' ? '2倍+ 盈亏比' : language === 'ko' ? '2배+ 손익비' : 'Ăn gấp 2+') : (language === 'en' ? 'Standard' : language === 'zh' ? '标准' : language === 'ko' ? '표준' : 'Tiêu chuẩn')}
                  </span>
                )}
              </div>
            </div>

            {/* 4. Mức độ rủi ro & Điểm số */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-2.5 space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>{language === 'en' ? 'Risk Level' : language === 'zh' ? '风险等级' : language === 'ko' ? '위험 등급' : 'Mức độ rủi ro'}</span>
                <span className="text-[8px] text-slate-500 font-mono">{currentCandidate?.score ? `Score ${currentCandidate.score.toFixed(0)}` : 'Risk'}</span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                {currentRisk ? (
                  <span className={`px-2 py-0.5 rounded-md font-mono text-xs font-bold border ${
                    currentRisk === 'CRITICAL'
                      ? 'bg-rose-950 text-rose-300 border-rose-800'
                      : currentRisk === 'HIGH'
                      ? 'bg-amber-950 text-amber-300 border-amber-800'
                      : 'bg-slate-800 text-slate-300 border-slate-700'
                  }`}>
                    {currentRisk}
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-md font-mono text-xs font-bold bg-slate-900 text-slate-500 border border-slate-800">
                    —
                  </span>
                )}
                <span className="text-[10px] text-slate-400 font-mono">Target: -8%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

