import React from 'react';
import { X, HelpCircle, Search, BookOpen, Lightbulb } from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';

interface GlossaryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const GLOSSARY_ENTRIES_VI = [
  { term: "Phân phối (Distribution)", desc: "Coin bắt đầu 'xả' — mất động lượng tăng, tích tụ áp lực bán và sắp giảm mạnh. Tính toán tự động bởi AI từ dữ liệu định lượng 5 phút." },
  { term: "Độ chính xác (Precision)", desc: "Trong 100 cảnh báo được phát, bao nhiêu cảnh báo đạt đúng mục tiêu đã định nghĩa? Chỉ so sánh giá trị gắn với cùng Model ID, ngưỡng và giai đoạn đánh giá." },
  { term: "Tỷ lệ bắt được (Recall)", desc: "Trong 100 sự kiện thực sự xảy ra, mô hình bắt được bao nhiêu? Giá trị hiện hành phải được đọc từ báo cáo đánh giá gắn với Model ID production." },
  { term: "Điểm Brier (Độ chuẩn xác)", desc: "Chỉ số đo sai lệch của dự báo xác suất; càng thấp càng tốt (0 = hoàn hảo). Giá trị phải được đối chiếu trên đúng tập và kỳ đánh giá." },
  { term: "Thời gian báo trước (Median Lead Time)", desc: "Trung vị thời gian từ lúc phát tín hiệu đến khi mục tiêu được xác nhận. Chỉ hiển thị khi kỳ forward-test tương ứng có đủ mẫu." },
  { term: "Kiểm định cuốn chiếu (Walk-Forward Validation)", desc: "Phương pháp kiểm định chuỗi thời gian kết hợp Embargo Window: huấn luyện trên quá khứ và đánh giá trên giai đoạn sau, giúp giảm rủi ro nhìn trước nhưng không thay thế kiểm toán dữ liệu." },
  { term: "Khối lượng hợp đồng mở (Open Interest - OI)", desc: "Tổng số lượng hợp đồng phái sinh đang mở. OI tăng vọt nhưng giá đi ngang/suy yếu là dấu hiệu phân phối điển hình." },
  { term: "Tỷ lệ phí Funding (Funding Rate)", desc: "Khoản phí giữa phe Long và Short trên sàn Futures. Funding dương quá cao cho thấy số đông đang FOMO mua đuổi, dễ bị bẫy xả ngược." },
  { term: "Tỷ lệ Taker Sell / Buy", desc: "Tỷ lệ khối lượng bán/mua chủ động từ lệnh thị trường. Taker Sell chiếm ưu thế cho thấy phe bán tổ chức đang xả hàng quyết liệt." },
  { term: "Mức giảm mục tiêu (Target -8%)", desc: "Tiêu chuẩn xác định cú xả: Giá sụt giảm ít nhất 8% trong khung 24h kể từ khi xuất hiện tín hiệu phân phối." }
];

const GLOSSARY_ENTRIES_EN = [
  { term: "Distribution Phase", desc: "Asset begins offloading inventory — loses upward momentum, builds sell pressure, and enters a major markdown. Automatically computed from 5m quantitative derivatives data." },
  { term: "Precision", desc: "Out of 100 issued alerts, how many meet the defined target? Compare only values tied to the same Model ID, threshold, and evaluation window." },
  { term: "Recall (Capture Rate)", desc: "Out of 100 events that actually occur, how many does the model capture? Read the current value from the evaluation report linked to the production Model ID." },
  { term: "Brier Score (Calibration Metric)", desc: "Measures probabilistic forecast error; lower is better (0 = perfect). A value is meaningful only with its dataset and evaluation window." },
  { term: "Median Lead Time", desc: "Median elapsed time from alert issuance until the target is confirmed. It is reported only when the matching forward-test window has enough samples." },
  { term: "Walk-Forward Validation", desc: "Time-series validation with an embargo window: train on earlier data and evaluate on a later period. It reduces lookahead risk but does not replace a data audit." },
  { term: "Open Interest (OI)", desc: "Total outstanding derivatives contracts. Surging OI accompanied by stalled or decelerating price action is a hallmark of institutional distribution." },
  { term: "Funding Rate", desc: "Periodic payment exchanged between Longs and Shorts on perpetual futures. Excessively high positive funding indicates crowded FOMO longs prone to liquidation cascades." },
  { term: "Taker Sell / Buy Ratio", desc: "Ratio of market orders initiated by aggressive sellers vs buyers. Dominant Taker Sell volume reflects aggressive distribution." },
  { term: "Target Drawdown (-8%)", desc: "Standard ground-truth benchmark: Price decreases by at least 8% within 24 hours of signal issuance while adverse upside drift stays ≤ 4%." }
];

const GLOSSARY_ENTRIES_ZH = [
  { term: "派发阶段 (Distribution Phase)", desc: "资产主力开始抛售筹码库存——丧失上涨动能，聚集卖方压力并进入大幅回撤。基于 5 分钟衍生品量化数据实时计算。" },
  { term: "精准率 (Precision)", desc: "在发出的 100 次预警中，有多少次达到既定目标？只能比较绑定同一 Model ID、阈值与评估窗口的数值。" },
  { term: "捕获率 / 召回率 (Recall)", desc: "在 100 次实际事件中，模型成功捕获多少次？当前值应以 production Model ID 对应的评估报告为准。" },
  { term: "布里尔分数 (Brier Score)", desc: "衡量概率预测误差的指标，越低越好（0 为完美）。数值必须连同数据集与评估窗口一起解读。" },
  { term: "提前预警时间 (Median Lead Time)", desc: "从发出预警到目标得到确认的时间中位数；只有对应前向测试样本充足时才应报告。" },
  { term: "推进式前向验证 (Walk-Forward Validation)", desc: "带 Embargo 隔离窗口的时序验证：使用较早数据训练，在较晚时期评估。它可降低未来数据泄漏风险，但不能替代数据审计。" },
  { term: "未平仓合约量 (Open Interest - OI)", desc: "衍生品未平仓总头寸。持仓量剧烈增加但价格停滞或滞涨，是机构派发抛售的典型特征。" },
  { term: "资金费率 (Funding Rate)", desc: "永续合约多空双方定期交换的资金费率。费率异常高说明多头情绪过度拥挤，极易引发踩踏连环爆仓。" },
  { term: "主动卖出/买入比率 (Taker Sell/Buy)", desc: "市场主动吃单方向的成交比。主动卖单占主导地位反映机构正在坚决出货。" },
  { term: "目标回撤 (Target -8%)", desc: "判定暴跌的标准基准：自信号发出起 24 小时内价格回撤至少 8%，且最大逆向波动 ≤ 4%。" }
];

const GLOSSARY_ENTRIES_KO = [
  { term: "분산 국면 (Distribution Phase)", desc: "자산이 물량을 털어내기 시작하는 단계 — 상승 모멘텀 상실, 매도 압력 누적, 급격한 하락 임박. 5분 파생상품 정량 데이터로 실시간 계산." },
  { term: "정밀도 (Precision)", desc: "발행된 100개 경보 중 정의된 목표를 충족한 비율입니다. 동일한 Model ID, 임계값, 평가 기간에 연결된 값만 비교해야 합니다." },
  { term: "재현율 / 포착률 (Recall)", desc: "실제로 발생한 100개 이벤트 중 모델이 포착한 비율입니다. 현재 값은 production Model ID에 연결된 평가 보고서에서 확인합니다." },
  { term: "브라이어 점수 (Brier Score)", desc: "확률 예측 오차를 측정하며 낮을수록 좋습니다(0 = 완벽). 데이터셋과 평가 기간을 함께 제시해야 의미가 있습니다." },
  { term: "사전 경보 리드타임 (Median Lead Time)", desc: "경보 발행부터 목표 확인까지 걸린 시간의 중앙값입니다. 해당 전진 평가에 충분한 표본이 있을 때만 보고합니다." },
  { term: "전진 검증 (Walk-Forward Validation)", desc: "엠바고 윈도우를 둔 시계열 검증으로 과거 구간에서 학습하고 이후 구간에서 평가합니다. 미래 참조 위험을 줄이지만 데이터 감사를 대체하지는 않습니다." },
  { term: "미결제약정 (Open Interest - OI)", desc: "미결제 파생상품 계약 총량. OI가 급증하는 반면 가격 상승이 둔화되는 것은 전형적인 세력 분산(털기) 징후입니다." },
  { term: "펀딩비 (Funding Rate)", desc: "무기한 선물 롱/숏 간 지불 비용. 지나치게 높은 양수 펀딩비는 롱 포지션 과열 및 롱스퀴즈 취약성을 나타냅니다." },
  { term: "테이커 매도 비율 (Taker Sell Ratio)", desc: "시장가 주문 중 매도 주문이 차지하는 비율. 테이커 매도 우위는 기관의 공격적인 물량 출회를 의미합니다." },
  { term: "목표 하락폭 (Target -8%)", desc: "급락 판정 표준 기준: 신호 발생 후 24시간 이내에 가격이 최소 8% 하락하고, 역방향 상승 오차(MAE)는 4% 이하로 제한." }
];

export const GlossaryModal: React.FC<GlossaryModalProps> = ({ isOpen, onClose }) => {
  const { language } = useTranslation();
  const [searchTerm, setSearchTerm] = React.useState('');

  if (!isOpen) return null;

  const entries = language === 'zh'
    ? GLOSSARY_ENTRIES_ZH
    : language === 'ko'
    ? GLOSSARY_ENTRIES_KO
    : language === 'en'
    ? GLOSSARY_ENTRIES_EN
    : GLOSSARY_ENTRIES_VI;

  const filtered = entries.filter(item =>
    item.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.desc.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getTitle = () => {
    if (language === 'zh') return '帮助与指标术语词典';
    if (language === 'ko') return '도움말 및 지표 용어 사전';
    if (language === 'en') return 'Help & Indicator Glossary';
    return 'Trợ giúp & Từ điển Thuật ngữ';
  };

  const getSearchPlaceholder = () => {
    if (language === 'zh') return '搜索术语 (持仓量 OI, 精准率, 资金费率, 提前预警时间)...';
    if (language === 'ko') return '용어 검색 (OI, 정밀도, 펀딩비, 리드타임)...';
    if (language === 'en') return 'Search terms (OI, Precision, Funding, Lead time)...';
    return 'Tìm kiếm thuật ngữ (OI, độ chính xác, funding, lead time...)';
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-amber-400" />
            <h2 className="text-base font-bold text-slate-100">
              {getTitle()}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search */}
        <div className="p-3 border-b border-slate-800 bg-slate-900">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder={getSearchPlaceholder()}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* Intro */}
          <div className="text-xs text-slate-300 leading-relaxed">
            <p className="mb-1">
              <strong className="text-amber-400">
                {language === 'en' ? 'DAO VANG AI Radar' : language === 'zh' ? '刀锋 PeakPulse AI 雷达' : language === 'ko' ? '다오방 AI 레이더' : 'Đảo Vàng AI Radar'}
              </strong>{' '}
              {language === 'en' 
                ? 'provides early detection of distribution phases before major crypto price drops. The system continuously scans Binance Futures pairs 24/7 across multi-dimensional derivatives metrics.'
                : language === 'zh'
                ? '在加密资产发生暴跌之前提前捕捉派发见顶特征。系统全天候 24/7 监控 Binance 合约交易对的多维度衍生品量化指标。'
                : language === 'ko'
                ? '주요 암호화폐 급락이 시작되기 전 세력의 분산 국면을 사전에 포착합니다. 바이낸스 선물 페어를 24/7 지속 모니터링하여 다차원 파생상품 지표를 계산합니다.'
                : 'giúp phát hiện sớm dấu hiệu phân phối — coin sắp xả giá. Hệ thống quét toàn bộ coin hợp đồng tương lai trên Binance 24/7, tính toán điểm số từ dữ liệu phái sinh đa chiều.'}
            </p>
            <ul className="list-disc list-inside space-y-0.5 text-slate-400">
              <li>
                <strong>{language === 'en' ? 'Distribution Score / Probability:' : language === 'zh' ? '派发得分 / 概率:' : language === 'ko' ? '분산 점수 / 확률:' : 'Điểm phân phối / Xác suất:'}</strong>{' '}
                {language === 'en' ? 'Higher score indicates stronger confluence of distribution footprints.' : language === 'zh' ? '得分越高，发生剧烈回撤的概率越大。' : language === 'ko' ? '점수가 높을수록 분산 패턴의 합치도가 높습니다.' : 'Điểm càng cao, xác suất xảy ra pha phân phối càng lớn.'}
              </li>
              <li>
                <strong>{language === 'en' ? 'Target Drawdown -8%:' : language === 'zh' ? '目标回撤 8%:' : language === 'ko' ? '목표 하락 8%:' : 'Mức giảm mục tiêu 8%:'}</strong>{' '}
                {language === 'en' ? 'Expected price drop of ≥8% within a 24h horizon.' : language === 'zh' ? '自信号发出起 24 小时内价格预期下跌 ≥8%。' : language === 'ko' ? '신호 발생 후 24시간 이내 최소 8% 하락 예상.' : 'Giá giảm ít nhất 8% trong vòng 24 giờ kể từ tín hiệu.'}
              </li>
              <li>
                <strong>{language === 'en' ? 'Smart Automation:' : language === 'zh' ? '智能自动化:' : language === 'ko' ? '스마트 자동화:' : 'Tự động thông minh:'}</strong>{' '}
                {language === 'en' ? 'Instant push notifications to Telegram when probability threshold is reached.' : language === 'zh' ? '当概率达到设定阈值时自动向 Telegram 发送即时推送。' : language === 'ko' ? '확률 임계값 도달 시 텔레그램으로 즉시 알림 발송.' : 'Tự động gửi cảnh báo Telegram khi điểm số đạt ngưỡng.'}
              </li>
            </ul>
          </div>

          {/* Dictionary Entries */}
          <div className="space-y-2.5">
            <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5" />
              {language === 'en' ? 'Detailed Concept Guide' : language === 'zh' ? '核心概念详解' : language === 'ko' ? '상세 개념 가이드' : 'Giải thích chi tiết các thuật ngữ'}
            </h3>
            {filtered.map((item, idx) => (
              <div key={idx} className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                <h4 className="text-xs font-bold text-slate-100 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  {item.term}
                </h4>
                <p className="text-xs text-slate-400 leading-relaxed pl-3">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>

          {/* Quick FAQ / Note */}
          <div className="bg-amber-950/20 border border-amber-500/20 rounded-xl p-3 text-xs space-y-1 text-slate-300">
            <div className="font-bold text-amber-400 flex items-center gap-1">
              <Lightbulb className="w-3.5 h-3.5" />
              {language === 'en' ? 'Trading Strategy Notice' : language === 'zh' ? '交易策略提示' : language === 'ko' ? '매매 전략 안내' : 'Lưu ý khi sử dụng'}
            </div>
            <p className="text-[11px] text-slate-400">
              {language === 'en'
                ? 'DAO VANG AI provides early probabilistic risk indicators. Always practice disciplined risk management, avoid overleveraging on newly listed meme tokens, and observe BTC market regime conditions.'
                : language === 'zh'
                ? '刀锋 AI 提供高概率的早期风险预警。请始终执行严格的风控纪律，避免在极高波动的新币上过度杠杆，并密切结合 BTC 宏观环境。'
                : language === 'ko'
                ? '다오방 AI는 조기 확률적 위험 지표를 제공합니다. 항상 엄격한 리스크 관리를 준수하고, 신규 상장 밈코인에 과도한 레버리지를 피하며 BTC 시장 상황을 확인하세요.'
                : 'Đảo Vàng AI cung cấp tín hiệu cảnh báo rủi ro mang tính xác suất. Luôn quản trị vốn cẩn trọng, tránh đòn bẩy quá lớn đối với coin mới lên sàn và theo dõi sát xu hướng của Bitcoin.'}
            </p>
          </div>

        </div>

      </div>
    </div>
  );
};
