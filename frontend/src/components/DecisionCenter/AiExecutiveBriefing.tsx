import React, { useMemo, useState } from 'react';
import {
  Sparkles, ShieldAlert, Award,
  Compass, TrendingDown, CheckCircle, ChevronDown, ChevronUp
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import { normalizeProbability, ALERT_THRESHOLD_PCT } from '../../types';
import type { CoinDetail, DeepAnalysis, SignalItem, TradeSetup, TradeReadinessStatus, ConvictionGrade } from '../../types';

interface AiExecutiveBriefingProps {
  displayDetail: CoinDetail;
  selectedSignal?: SignalItem | null;
  deepAnalysis?: DeepAnalysis | null;
  tradeSetup?: TradeSetup | null;
  onOpenAiChat?: () => void;
}

export const AiExecutiveBriefing: React.FC<AiExecutiveBriefingProps> = ({
  displayDetail,
  deepAnalysis,
  tradeSetup,
  onOpenAiChat,
}) => {
  const { language, t } = useTranslation();
  const [isGameplanExpanded, setIsGameplanExpanded] = useState(false);
  const isEn = language === 'en';
  const isZh = language === 'zh';
  const isKo = language === 'ko';

  const symbol = displayDetail?.symbol || 'COIN';
  const currentPrice = displayDetail?.current_price || 0;
  const prob = normalizeProbability(displayDetail?.probability) ?? 0;
  const btcRegime = deepAnalysis?.btc_regime || 'NEUTRAL';
  const isPump = deepAnalysis?.pump_analysis?.detected || false;
  const metrics = displayDetail?.metrics || {
    oi_change_24h: 'N/A',
    taker_sell_ratio: null,
    funding_rate: 'N/A',
    funding_interval_hours: null,
    funding_apr: null,
    funding_cost_per_1000_usdt: null,
    funding_payer: 'unknown' as const,
    rsi_15m: null,
    volume_delta_24h: 'N/A',
  };
  const featureDrivers = displayDetail?.feature_drivers || [];

  const entry = tradeSetup?.entryPrice ?? null;
  const sl = tradeSetup?.stopLossPrice ?? null;
  const tp1 = tradeSetup?.tp1Price ?? null;
  const tp2 = tradeSetup?.tp2Price ?? null;
  const rr = tradeSetup?.riskRewardRatio ? tradeSetup.riskRewardRatio.toFixed(2) : null;

  // 1. Tính toán Trade Readiness Status
  const readiness: { status: TradeReadinessStatus; label: string; badgeClass: string; desc: string } = useMemo(() => {
    if (!tradeSetup || entry == null) {
      return {
        status: 'STANDBY',
        label: isZh ? '⚪ 观望等待' : isKo ? '⚪ 관망 대기' : isEn ? '⚪ STANDBY / WATCHLIST' : '⚪ ĐỨNG NGOÀI / THEO DÕI',
        badgeClass: 'bg-slate-800 text-slate-300 border-slate-700',
        desc: isZh ? '尚未满足做空派发触发条件，建议保持观望。' : isKo ? '숏 포지션 분산 조건이 미충족되었습니다. 관망을 권장합니다.' : isEn ? 'Setup conditions not yet ripe for distribution short. Standby.' : 'Hệ thống chưa cấp setup giao dịch, hoặc không đủ dữ liệu tính toán. Khuyến nghị đứng ngoài.',
      };
    }
    if (prob < ALERT_THRESHOLD_PCT) {
      return {
        status: 'STANDBY',
        label: isZh ? '⚪ 观望等待' : isKo ? '⚪ 관망 대기' : isEn ? '⚪ STANDBY / WATCHLIST' : '⚪ ĐỨNG NGOÀI / THEO DÕI',
        badgeClass: 'bg-slate-800 text-slate-300 border-slate-700',
        desc: isZh ? '尚未满足做空派发触发条件，建议保持观望。' : isKo ? '숏 포지션 분산 조건이 미충족되었습니다. 관망을 권장합니다.' : isEn ? 'Setup conditions not yet ripe for distribution short. Standby.' : 'Chưa đủ điều kiện kích hoạt phân phối xả. Khuyến nghị đứng ngoài quan sát.',
      };
    }

    const priceDiffPct = ((currentPrice - entry) / entry) * 100;

    if (priceDiffPct <= -3.5) {
      return {
        status: 'CHASED_ENTRY',
        label: isZh ? '🔴 错过最佳点位 (切勿追空)' : isKo ? '🔴 진입가 초과 (추격 금지)' : isEn ? '🔴 MISSED ENTRY (DO NOT CHASE)' : '🔴 ĐÃ QUÁ VÙNG VÀO (KHÔNG ĐUỔI)',
        badgeClass: 'bg-rose-950/80 text-rose-300 border-rose-700',
        desc: isZh ? `价格已自入场点下跌 ${Math.abs(priceDiffPct).toFixed(1)}%，追空盈亏比极差，需等待反弹。` : isKo ? `진입가 대비 ${Math.abs(priceDiffPct).toFixed(1)}% 하락했습니다. 손익비가 나쁘므로 반등을 기다리세요.` : isEn ? `Price dropped ${Math.abs(priceDiffPct).toFixed(1)}% below entry. R:R is poor; wait for a pullback.` : `Giá đã giảm ${Math.abs(priceDiffPct).toFixed(1)}% từ điểm Entry. Tỷ lệ R:R không còn an toàn, hãy chờ nhịp hồi.`,
      };
    }

    if (priceDiffPct >= -2.0 && priceDiffPct <= 1.5) {
      return {
        status: 'READY_TO_ENTER',
        label: isZh ? '🟢 已进入入场区间 (立即就绪)' : isKo ? '🟢 진입 구간 도달 (진입 가능)' : isEn ? '🟢 IN ENTRY ZONE (READY TO ENTER)' : '🟢 ĐÃ VÀO VÙNG ENTRY (SẴN SÀNG)',
        badgeClass: 'bg-emerald-950/90 text-emerald-300 border-emerald-600 ring-1 ring-emerald-500/50 animate-pulse',
        desc: isZh ? '现货与合约价格正处于理想阻力抛压带，可分批建仓。' : isKo ? '현재 가격이 이상적인 저항 분산 구간에 위치하여 분할 진입이 가능합니다.' : isEn ? 'Price is directly inside optimal distribution resistance zone. Favorable R:R.' : 'Giá đang nằm ngay vùng kháng cự phân phối tối ưu. Có thể mở vị thế theo kế hoạch.',
      };
    }

    return {
      status: 'WAIT_FOR_CONFIRM',
      label: isZh ? '🟡 等待 K 线确认信号' : isKo ? '🟡 캔들 반전 확인 대기' : isEn ? '🟡 WAIT FOR REJECTION' : '🟡 CHỜ TÍN HIỆU XÁC NHẬN',
      badgeClass: 'bg-amber-950/80 text-amber-300 border-amber-700',
      desc: isZh ? '处于警报区，建议等待 5m/15m 出现长上影线或跌破微观支撑后再入场。' : isKo ? '경보 영역입니다. 5분/15분봉 윗꼬리 저항 확인 후 진입을 권장합니다.' : isEn ? 'High risk zone. Await 5m/15m pinbar rejection or micro-structure breakdown.' : 'Đang ở vùng cảnh báo. Nên chờ nến 5m/15m rút râu từ chối giá trước khi vào lệnh.',
    };
  }, [prob, currentPrice, entry, isEn, isZh, isKo]);

  // 2. Tính toán Conviction Score & Grade
  const conviction: { grade: ConvictionGrade; score: number; confluenceCount: number; reasons: string[] } = useMemo(() => {
    let score = 0;
    const reasons: string[] = [];

    // Factor 1: AI Probability >= 75%
    if (prob >= 75) {
      score += 30;
      reasons.push(isZh ? '风险值达到 ≥75%' : isKo ? '위험 값 ≥75%' : isEn ? 'Reported risk value ≥75%' : 'Giá trị rủi ro đạt ≥75%');
    } else if (prob >= 60) {
      score += 15;
    }

    // Factor 2: High Funding Rate / Longs paying Shorts
    const fr = metrics.funding_rate || '';
    if (fr.startsWith('+') && !fr.startsWith('+0.00')) {
      score += 25;
      reasons.push(isZh ? '资金费率极度正值 (多头极度拥挤)' : isKo ? '높은 양수 펀딩비 (롱 과열)' : isEn ? 'High Positive Funding (Long Crowded)' : 'Funding Rate dương cao (Phe Long trả phí)');
    }

    // Factor 3: OI Surge or Divergence
    const oi = metrics.oi_change_24h || '';
    if (oi.startsWith('+') || featureDrivers.some(d => d.feature.toLowerCase().includes('oi') || d.feature.toLowerCase().includes('divergence'))) {
      score += 25;
      reasons.push(isZh ? 'OI 持仓激增与顶部分离' : isKo ? 'OI 급증 및 고점 다이버전스' : isEn ? 'OI Expansion & Divergence' : 'Dòng tiền OI tăng nóng & Phân kỳ');
    }

    // Factor 4: observable taker-sell, BTC or pump condition
    const takerSell = metrics.taker_sell_ratio ?? null;
    if (btcRegime === 'WEAK' || isPump || (takerSell != null && takerSell >= 0.52)) {
      score += 20;
      reasons.push(isZh ? '主动卖出 / BTC 条件已触发' : isKo ? '테이커 매도 / BTC 조건 감지' : isEn ? 'Taker-sell / BTC condition observed' : 'Điều kiện Taker-sell / BTC được ghi nhận');
    }

    let grade: ConvictionGrade = 'C';
    if (score >= 80) grade = 'A+';
    else if (score >= 60) grade = 'A';
    else if (score >= 40) grade = 'B';

    return {
      grade,
      score,
      confluenceCount: reasons.length,
      reasons,
    };
  }, [prob, metrics, featureDrivers, btcRegime, isPump, isEn, isZh, isKo]);

  // 3. Xây dựng 3 luận điểm diễn giải tự nhiên (Conversational Narratives)
  const topDriversText = featureDrivers.slice(0, 3).map(d => d.feature).join(', ') || 'N/A';

  const evidenceSummary = useMemo(() => {
    if (featureDrivers.length === 0 || !metrics.oi_change_24h || metrics.oi_change_24h === 'N/A' || !metrics.funding_rate || metrics.funding_rate === 'N/A') return null;
    if (isZh) {
      return `当前观测到 **${symbol}** 的数据特征。24h 持仓量 (OI) 变动为 **${metrics.oi_change_24h || 'N/A'}**，资金费率为 **${metrics.funding_rate || 'N/A'}**。加权评分中贡献较大的分项为 \`${topDriversText}\`。这些分项不是 SHAP，也不代表因果归因。`;
    }
    if (isKo) {
      return `현재 **${symbol}**에 대한 관측 지표입니다. 24시간 미결제약정(OI) 변화율은 **${metrics.oi_change_24h || 'N/A'}**이며 펀딩비는 **${metrics.funding_rate || 'N/A'}**입니다. 가중 점수에서 기여도가 큰 항목은 \`${topDriversText}\`입니다. 이 항목은 SHAP 또는 인과 귀속이 아닙니다.`;
    }
    if (isEn) {
      return `Observed metrics for **${symbol}**: Open Interest change is **${metrics.oi_change_24h || 'N/A'}** with Funding Rate at **${metrics.funding_rate || 'N/A'}**. The largest weighted score components are \`${topDriversText}\`. They are not SHAP values or causal attribution.`;
    }
    return `Dữ liệu quan sát của **${symbol}**: OI thay đổi **${metrics.oi_change_24h || 'N/A'}** và Funding Rate là **${metrics.funding_rate || 'N/A'}**. Các thành phần có trọng số lớn nhất trong điểm tổng hợp gồm \`${topDriversText}\`. Đây không phải giá trị SHAP hay quy kết nhân quả.`;
  }, [symbol, metrics, topDriversText, isEn, isZh, isKo]);

  const gameplan = useMemo(() => {
    if (!tradeSetup || entry == null || sl == null || tp1 == null || tp2 == null || rr == null) return null;
    if (isZh) {
      return `1. **入场策略**: 建议关注 **$${entry}** 附近区域。${readiness.status === 'READY_TO_ENTER' ? '当前价位极佳，可按计划执行。' : '建议分批建仓，切勿单次重仓市价开单。'}\n2. **止损防护**: 严格在 **$${sl}** 设置止损单。\n3. **止盈阶梯**: 第一止盈位 **$${tp1}** (-4%) 建议平仓 50% 并将止损移至开仓价（保本）；第二目标位 **$${tp2}** (-8%)。综合盈亏比: **${rr}**。`;
    }
    if (isKo) {
      return `1. **진입 전략**: **$${entry}** 부근을 주시하세요. ${readiness.status === 'READY_TO_ENTER' ? '현재 완벽한 진입 구간입니다.' : '시장가 몰빵을 피하고 분할로 접근하세요.'}\n2. **손절 방어**: **$${sl}**에 필수 스탑로스를 설정하세요.\n3. **익절 플랜**: 1차 목표가 **$${tp1}** (-4%)에서 50% 분할 익절 후 본절 스탑 설정, 2차 목표가 **$${tp2}** (-8%). 예상 R:R: **${rr}**.`;
    }
    if (isEn) {
      return `1. **Execution**: Focus on entry zone around **$${entry}**. ${readiness.status === 'READY_TO_ENTER' ? 'Price is currently optimal inside entry zone.' : 'Scale in with limit orders; avoid market FOMO.'}\n2. **Defense**: Place mandatory Stop Loss at **$${sl}**.\n3. **Profit Ladder**: Take 50% profit at TP1 **$${tp1}** (-4%) and trail SL to Breakeven; ride remaining runners to TP2 **$${tp2}** (-8%). Calculated R:R: **${rr}**.`;
    }
    return `1. **Điểm vào lệnh**: Tập trung quanh vùng **$${entry}**. ${readiness.status === 'READY_TO_ENTER' ? 'Giá hiện tại đang nằm ngay vùng mở vị thế lý tưởng.' : 'Nên chia vốn làm 2-3 phần, tránh vào lệnh vội vã bằng lệnh Market.'}\n2. **Cắt lỗ bắt buộc**: Đặt sẵn lệnh Stop Loss tại **$${sl}**.\n3. **Chốt lời từng nấc**: Đạt TP1 **$${tp1}** (-4%) ➔ đóng 50% vị thế và dời SL về hòa vốn (Breakeven); giữ 50% còn lại về TP2 **$${tp2}** (-8%). Tỷ lệ R:R: **${rr}**.`;
  }, [entry, sl, tp1, tp2, rr, readiness.status, isEn, isZh, isKo]);

  const riskAlert = useMemo(() => {
    if (!tradeSetup || sl == null) return null;
    if (isZh) {
      return `⚠️ **失效规则**: 若比特币（BTC 目前为 ${btcRegime}）突然放量大阳线突破关键阻力，或 ${symbol} 15分钟收盘突破 **$${sl}**，则必须坚决平仓离场。单笔交易风险严格控制在账户总额的 1%–2% 以内。`;
    }
    if (isKo) {
      return `⚠️ **무효화 규칙**: 비트코인(BTC 현재 상태: ${btcRegime})이 급등하거나 ${symbol}이 **$${sl}** 위에서 15분봉 마감 시 즉시 손절해야 합니다. 1회 거래 손실 한도는 총 자산의 1%–2% 이내로 엄격히 통제하세요.`;
    }
    if (isEn) {
      return `⚠️ **Invalidation Rules**: If Bitcoin (BTC currently: ${btcRegime}) suddenly expands upward with aggressive volume, or if ${symbol} closes a 15m candle above **$${sl}**, invalidate the setup immediately. Cap total risk at 1%–2% of trading capital.`;
    }
    return `⚠️ **Điều kiện hủy kèo**: Nếu Bitcoin (hiện ở trạng thái ${btcRegime}) bất ngờ dựng cột tăng mạnh kéo theo altcoin, hoặc nến 15m của ${symbol} đóng cửa vượt **$${sl}**, bạn bắt buộc phải cắt lỗ và hủy kế hoạch. Luôn giới hạn rủi ro tối đa 1%–2% NAV tài khoản.`;
  }, [btcRegime, symbol, sl, isEn, isZh, isKo]);

  return (
    <div className="bg-gradient-to-b from-slate-950 via-slate-900/90 to-slate-950 border border-slate-800 rounded-xl p-3.5 sm:p-4 shadow-xl space-y-3.5">
      {/* Top Bar: Title + Badges + Ask AI CTA */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs sm:text-sm font-bold text-slate-100 uppercase tracking-wide flex items-center gap-1.5">
              <span>{isZh ? 'AI 首席交易员简报 (执行解读)' : isKo ? 'AI 수석 트레이더 브리핑 (의사결정 가이드)' : isEn ? 'EXECUTIVE AI TRADING BRIEFING' : 'BẢN TIN NHẬN ĐỊNH TRỢ LÝ AI (HỖ TRỢ RA QUYẾT ĐỊNH)'}</span>
              <span className="text-[10px] font-mono text-amber-400 font-semibold px-1.5 py-0.2 bg-amber-500/10 rounded border border-amber-500/20">
                {symbol}
              </span>
            </h3>
            <p className="text-[10px] sm:text-[11px] text-slate-400">
              {isZh ? '基于量化指标、加权评分分项与订单流的通俗摘要' : isKo ? '정량 지표, 가중 점수 구성 및 오더플로를 요약한 안내' : isEn ? 'Plain-language summary of quant features, weighted score components and order flow' : 'Tóm tắt dữ liệu định lượng, thành phần điểm có trọng số và dòng lệnh'}
            </p>
          </div>
        </div>

        {/* Action Cues: Readiness Badge + Conviction Grade */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Readiness Status Badge */}
          <div className={`px-2.5 py-1 rounded-md border text-[11px] font-bold flex items-center gap-1.5 shadow-sm ${readiness.badgeClass}`} title={readiness.desc}>
            <span>{readiness.label}</span>
          </div>

          {/* Conviction Grade Badge */}
          <div className="px-2 py-1 rounded-md border border-violet-700/80 bg-violet-950/40 text-[11px] font-mono font-bold text-violet-300 flex items-center gap-1">
            <Award className="w-3.5 h-3.5 text-violet-400" />
            <span>Grade {conviction.grade}</span>
            <span className="text-[9px] text-slate-400 font-sans">({conviction.confluenceCount}/4)</span>
          </div>

          {/* Interactive Chat Button */}
          {onOpenAiChat && (
            <button
              type="button"
              onClick={onOpenAiChat}
              className="px-2.5 py-1 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-md text-[11px] flex items-center gap-1.5 transition shadow-sm"
              title={isEn ? 'Ask AI Assistant custom questions about this coin' : 'Hỏi đáp chi tiết với Trợ lý AI về coin này'}
            >
              <Sparkles className="w-3.5 h-3.5 fill-current" />
              <span>{isZh ? '💬 咨询 AI 助理' : isKo ? '💬 AI 어시스턴트 질문' : isEn ? '💬 Ask AI Analyst' : '💬 Hỏi Đáp Trợ Lý AI'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Confluence Criteria Chips */}
      {conviction.reasons.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
          <span className="text-slate-500 font-mono uppercase text-[9px] mr-1">
            {isZh ? '共振信号:' : isKo ? '일치 신호:' : isEn ? 'Confluence:' : 'Tín hiệu hội tụ:'}
          </span>
          {conviction.reasons.map((r, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-slate-300">
              <CheckCircle className="w-2.5 h-2.5 text-emerald-400" />
              {r}
            </span>
          ))}
        </div>
      )}

      {/* 3 Main Conversational Sections Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-stretch">
        {/* Section 1: observed market evidence */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-lg p-3 flex flex-col justify-between hover:border-slate-700 transition">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-bold text-sky-300 uppercase mb-2">
              <Compass className="w-3.5 h-3.5 text-sky-400" />
              <span>{isZh ? '1. 已观测市场证据' : isKo ? '1. 관측된 시장 근거' : isEn ? '1. Observed Market Evidence' : '1. Bằng Chứng Thị Trường Quan Sát Được'}</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              {evidenceSummary || (isEn ? 'Insufficient observed data for this summary.' : 'Chưa đủ dữ liệu quan sát để tạo bản tóm tắt.')}
            </p>
          </div>
          {evidenceSummary && (
            <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-400 font-mono">
              <span>OI: <strong className="text-sky-400">{metrics.oi_change_24h || 'N/A'}</strong></span>
              <span>Funding: <strong className="text-amber-400">{metrics.funding_rate || 'N/A'}</strong></span>
              {metrics.funding_interval_hours != null && (
                <span>{t('funding_cadence')}: <strong className="text-slate-300">{metrics.funding_interval_hours.toFixed(metrics.funding_interval_hours % 1 === 0 ? 0 : 2)}h</strong></span>
              )}
              {metrics.funding_apr && (
                <span>{t('funding_apr_label')}: <strong className="text-amber-300">{metrics.funding_apr}</strong></span>
              )}
              {metrics.funding_cost_per_1000_usdt != null
                && (metrics.funding_payer === 'long' || metrics.funding_payer === 'short') && (
                <span>
                  {metrics.funding_payer === 'long' ? t('funding_long_pays') : t('funding_short_pays')}{' '}
                  <strong className="text-amber-300">${metrics.funding_cost_per_1000_usdt.toFixed(2)} USDT {t('funding_per_1000')}</strong>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Section 2: Actionable Gameplan */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-lg p-3 flex flex-col justify-between hover:border-slate-700 transition">
          <button
            type="button"
            onClick={() => setIsGameplanExpanded((expanded) => !expanded)}
            aria-expanded={isGameplanExpanded}
            className="w-full flex items-center justify-between text-left"
          >
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-300 uppercase mb-2">
              <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
              <span>{isZh ? '2. 实战交易行动计划' : isKo ? '2. 실전 매매 실행 계획' : isEn ? '2. Actionable Gameplan' : '2. Kế Hoạch Vào Lệnh Chi Tiết'}</span>
            </div>
            {isGameplanExpanded ? <ChevronUp className="w-4 h-4 text-slate-400 mb-2" /> : <ChevronDown className="w-4 h-4 text-slate-400 mb-2" />}
          </button>
          {isGameplanExpanded && <>
            <div className="text-[11px] text-slate-300 leading-relaxed whitespace-pre-line space-y-1">
              {gameplan || (isEn ? 'No Trade Setup provided by the signal.' : 'Hệ thống chưa cấp setup giao dịch cho tín hiệu này.')}
            </div>
            {gameplan && (
              <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                <span>Entry: <strong className="text-amber-400">${entry}</strong></span>
                <span>TP1: <strong className="text-emerald-400">${tp1}</strong></span>
              </div>
            )}
          </>}
        </div>

        {/* Section 3: Risk & Invalidation Rules */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-lg p-3 flex flex-col justify-between hover:border-slate-700 transition">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-bold text-rose-300 uppercase mb-2">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
              <span>{isZh ? '3. 风险与失效规则' : isKo ? '3. 리스크 및 무효화 규칙' : isEn ? '3. Risk & Invalidation' : '3. Quản Trị Rủi Ro & Hủy Setup'}</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              {riskAlert || (isEn ? 'No invalidation criteria provided.' : 'Chưa có quy tắc hủy setup lệnh.')}
            </p>
          </div>
          {riskAlert && (
            <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-400 font-mono">
              <span>SL: <strong className="text-rose-400">${sl}</strong></span>
              <span>BTC: <strong className="text-indigo-400">{btcRegime}</strong></span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
