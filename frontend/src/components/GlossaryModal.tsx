import React from 'react';
import { X, HelpCircle, Search, BookOpen, Terminal, AlertTriangle, Lightbulb, Workflow, Bug } from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';

interface GlossaryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const GLOSSARY_ENTRIES_VI = [
  { term: "Phân phối (Distribution)", desc: "Coin bắt đầu 'xả' — mất động lượng tăng, tích tụ áp lực bán và sắp giảm mạnh. Tính toán tự động bởi AI từ dữ liệu định lượng 5 phút." },
  { term: "Độ chính xác (Precision)", desc: "Trong 100 lần AI báo 'sắp xả', bao nhiêu lần giá thực sự sụt giảm ≥ 8%? Đảo Vàng đạt độ chính xác thực nghiệm cao, vượt trội so với các mốc chuẩn ngẫu nhiên." },
  { term: "Tỷ lệ bắt được (Recall)", desc: "Trong 100 lần coin THẬT SỰ xả, AI bắt được bao nhiêu? Tỷ lệ bắt sóng của Đảo Vàng đạt ~60.1% trên tập dữ liệu kiểm định 600k+ nến." },
  { term: "Điểm Brier (Độ chuẩn xác)", desc: "Chỉ số đo lường độ sai lệch xác suất của AI. Số càng THẤP càng tốt (0 = hoàn hảo, 1 = sai hoàn toàn). Đảo Vàng đạt ~0.113." },
  { term: "Thời gian báo trước (Median Lead Time)", desc: "Khoảng thời gian từ khi AI phát tín hiệu đến khi cú xả 8% thực sự diễn ra. Trung bình khoảng ~9.8 giờ (590 phút)." },
  { term: "Kiểm định cuốn chiếu (Walk-Forward Validation)", desc: "Phương pháp kiểm định theo chuỗi thời gian kết hợp Embargo Window — chỉ huấn luyện trên quá khứ và kiểm tra trên tương lai, loại bỏ 100% rủi ro nhìn trước (Zero Data Leakage)." },
  { term: "Khối lượng hợp đồng mở (Open Interest - OI)", desc: "Tổng số lượng hợp đồng phái sinh đang mở. OI tăng vọt nhưng giá đi ngang/suy yếu là dấu hiệu phân phối điển hình." },
  { term: "Tỷ lệ phí Funding (Funding Rate)", desc: "Khoản phí giữa phe Long và Short trên sàn Futures. Funding dương quá cao cho thấy số đông đang FOMO mua đuổi, dễ bị bẫy xả ngược." },
  { term: "Tỷ lệ Taker Sell / Buy", desc: "Tỷ lệ khối lượng bán/mua chủ động từ lệnh thị trường. Taker Sell chiếm ưu thế cho thấy phe bán tổ chức đang xả hàng quyết liệt." },
  { term: "Mức giảm mục tiêu (Target -8%)", desc: "Tiêu chuẩn xác định cú xả: Giá sụt giảm ít nhất 8% trong khung 24h kể từ khi xuất hiện tín hiệu phân phối." }
];

const GLOSSARY_ENTRIES_EN = [
  { term: "Distribution Phase", desc: "Asset begins offloading inventory — loses upward momentum, builds sell pressure, and enters a major markdown. Automatically computed from 5m quantitative derivatives data." },
  { term: "Precision", desc: "Out of 100 alerts issued by AI, how many actually achieve a ≥8% drawdown? DAO VANG achieves high empirical precision substantially outperforming random baselines." },
  { term: "Recall (Capture Rate)", desc: "Out of 100 actual market dumps, how many were successfully anticipated by AI? DAO VANG achieves ~60.1% recall across 600,000+ validation candles." },
  { term: "Brier Score (Calibration Metric)", desc: "Measures accuracy of probabilistic forecasts. Lower values represent better calibration (0 = perfect, 1 = completely wrong). DAO VANG achieves ~0.113." },
  { term: "Median Lead Time", desc: "The time elapsed from initial AI alert delivery until the -8% drawdown target is reached. DAO VANG provides an average median lead time of ~9.8 hours (590 min)." },
  { term: "Walk-Forward Validation", desc: "Time-series validation method incorporating Embargo Windows — strictly trains on past data and evaluates on future data, eliminating 100% of lookahead bias and data leakage." },
  { term: "Open Interest (OI)", desc: "Total outstanding derivatives contracts. Surging OI accompanied by stalled or decelerating price action is a hallmark of institutional distribution." },
  { term: "Funding Rate", desc: "Periodic payment exchanged between Longs and Shorts on perpetual futures. Excessively high positive funding indicates crowded FOMO longs prone to liquidation cascades." },
  { term: "Taker Sell / Buy Ratio", desc: "Ratio of market orders initiated by aggressive sellers vs buyers. Dominant Taker Sell volume reflects aggressive distribution." },
  { term: "Target Drawdown (-8%)", desc: "Standard ground-truth benchmark: Price decreases by at least 8% within 24 hours of signal issuance while adverse upside drift stays ≤ 4%." }
];

export const GlossaryModal: React.FC<GlossaryModalProps> = ({ isOpen, onClose }) => {
  const { language } = useTranslation();
  const [searchTerm, setSearchTerm] = React.useState('');

  if (!isOpen) return null;

  const isEn = language === 'en';
  const entries = isEn ? GLOSSARY_ENTRIES_EN : GLOSSARY_ENTRIES_VI;

  const filtered = entries.filter(item =>
    item.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.desc.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-amber-400" />
            <h2 className="text-base font-bold text-slate-100">
              {isEn ? 'Help & Indicator Glossary' : 'Trợ giúp & Từ điển Thuật ngữ'}
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
              placeholder={isEn ? 'Search terms (OI, Precision, Funding, Lead time)...' : 'Tìm kiếm thuật ngữ (OI, độ chính xác, funding, lead time...)'}
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
              <strong className="text-amber-400">{isEn ? 'DAO VANG AI Radar' : 'Đảo Vàng AI Radar'}</strong> {isEn 
                ? 'provides early detection of distribution phases before major crypto price drops. The system continuously scans Binance Futures pairs 24/7 across multi-dimensional derivatives metrics.'
                : 'giúp phát hiện sớm dấu hiệu phân phối — coin sắp xả giá. Hệ thống quét toàn bộ coin hợp đồng tương lai trên Binance 24/7, tính toán điểm số từ dữ liệu phái sinh đa chiều.'}
            </p>
            <ul className="list-disc list-inside space-y-0.5 text-slate-400">
              <li><strong>{isEn ? 'Distribution Score / Probability:' : 'Điểm phân phối / Xác suất:'}</strong> {isEn ? 'Higher score indicates stronger confluence of distribution footprints.' : 'Điểm càng cao, xác suất xảy ra pha phân phối càng lớn.'}</li>
              <li><strong>{isEn ? 'Target Drawdown -8%:' : 'Mức giảm mục tiêu 8%:'}</strong> {isEn ? 'Expected price drop of ≥8% within a 24h horizon.' : 'Giá giảm ít nhất 8% trong vòng 24 giờ kể từ tín hiệu.'}</li>
              <li><strong>{isEn ? 'Smart Automation:' : 'Tự động thông minh:'}</strong> {isEn ? 'Instant push notifications to Telegram when probability threshold is reached.' : 'Tự động gửi cảnh báo Telegram khi điểm số đạt ngưỡng.'}</li>
            </ul>
          </div>

          {/* Quick Start */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5" /> {isEn ? 'USER WORKFLOW GUIDE' : 'HƯỚNG DẪN SỬ DỤNG NHANH'}
            </h4>
            <ol className="text-[11px] text-slate-300 space-y-1.5 list-decimal list-inside">
              <li><strong className="text-slate-100">{isEn ? 'RADAR FEED' : 'RADAR CẢNH BÁO'}</strong>: {isEn ? 'Real-time alert list from 24/7 scanner. Click any signal card to open detailed charts.' : 'Danh sách tín hiệu xả từ bộ quét 24/7. Bấm vào 1 tín hiệu để xem chi tiết.'}</li>
              <li><strong className="text-slate-100">{isEn ? 'MAIN WORKSPACE' : 'KHÔNG GIAN LÀM VIỆC'}</strong>: {isEn ? 'Deep dive analysis into 5 key metrics (OI 24h, Funding, Taker Sell, RSI 15m, Target -8%) and Candlestick chart.' : 'Phân tích chuyên sâu 5 chỉ số (OI 24h, Funding, Taker Sell, RSI 15m, Target -8%) và Biểu đồ nến.'}</li>
              <li><strong className="text-slate-100">{isEn ? 'CANDIDATES' : 'ỨNG VIÊN'}</strong>: {isEn ? 'Ranking of high-volatility coins filtered by distribution risk.' : 'Xếp hạng tất cả coin biến động mạnh theo điểm rủi ro.'}</li>
              <li><strong className="text-slate-100">{isEn ? 'BACKTEST EXPERIMENTS' : 'THỰC NGHIỆM BACKTEST'}</strong>: {isEn ? 'Historical walk-forward evaluation, precision, recall, and leakage audit verification.' : 'Thử nghiệm AI trên dữ liệu quá khứ — độ chính xác, tỷ lệ bắt được, kiểm tra rò rỉ dữ liệu.'}</li>
              <li><strong className="text-slate-100">{isEn ? 'FORWARD TEST' : 'FORWARD TEST LIVE'}</strong>: {isEn ? 'Frozen models evaluated on live out-of-sample data.' : 'Đóng băng mô hình → chấm điểm trên dữ liệu mới.'}</li>
              <li><strong className="text-slate-100">{isEn ? 'SYSTEM AUDITS & TELEMETRY' : 'LỊCH SỬ & GIÁM SÁT'}</strong>: {isEn ? 'Scanner cycle telemetry, heartbeat health, and Telegram delivery audits.' : 'Nhật ký bộ quét 24/7 + các lượt gửi Telegram.'}</li>
            </ol>
          </div>

          {/* CLI */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5" /> {isEn ? 'USEFUL CLI COMMANDS' : 'LỆNH CLI HỮU ÍCH'}
            </h4>
            <div className="space-y-1.5 text-[11px] font-mono">
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <span className="text-emerald-400">dao-vang scanner start</span>
                <span className="text-slate-400"> — {isEn ? 'Start 24/7 background scanner daemon' : 'Bộ quét 24/7 (thu thập + chấm điểm + gửi Telegram)'}</span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <span className="text-emerald-400">dao-vang scanner stop</span>
                <span className="text-slate-400"> — {isEn ? 'Stop scanner daemon' : 'Dừng bộ quét'}</span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <span className="text-emerald-400">dao-vang experiment run</span>
                <span className="text-slate-400"> — {isEn ? 'Execute walk-forward backtest' : 'Chạy kiểm thử lịch sử'}</span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <span className="text-emerald-400">dao-vang data collect</span>
                <span className="text-slate-400"> — {isEn ? 'Manual data collection' : 'Thu thập dữ liệu thủ công'}</span>
              </div>
            </div>
          </div>

          {/* Workflow */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
              <Workflow className="w-3.5 h-3.5" /> {isEn ? 'END-TO-END PIPELINE' : 'QUY TRÌNH TỪ ĐẦU ĐẾN CUỐI'}
            </h4>
            <div className="text-[11px] text-slate-300 space-y-1.5">
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">1.</span>
                <span><strong className="text-slate-100">{isEn ? 'Data Ingestion' : 'Thu thập dữ liệu'}</strong>: <code className="text-emerald-400">dao-vang scanner start</code> — {isEn ? '24/7 automated continuous data collection & scoring' : 'bộ quét 24/7 tự thu thập + chấm điểm'}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">2.</span>
                <span><strong className="text-slate-100">{isEn ? 'Review Signals' : 'Xem tín hiệu'}</strong>: {isEn ? 'Open Web UI → RADAR → click signal → review Workspace metrics' : 'Vào web → RADAR → bấm tín hiệu → xem chỉ số Workspace'}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">3.</span>
                <span><strong className="text-slate-100">{isEn ? 'Validate AI' : 'Kiểm chứng AI'}</strong>: {isEn ? 'Check Backtest tab → evaluate precision vs baselines and verify zero-leakage' : 'Kiểm thử lịch sử → xem độ chính xác so với mốc cơ sở + kiểm tra rò rỉ'}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">4.</span>
                <span><strong className="text-slate-100">{isEn ? 'Forward Test' : 'Kiểm thử dữ liệu mới'}</strong>: {isEn ? 'Observe real-time out-of-sample performance and PnL tracking' : 'Quan sát hiệu quả thực tế và theo dõi PnL'}</span>
              </div>
            </div>
          </div>

          {/* Troubleshooting */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
              <Bug className="w-3.5 h-3.5" /> {isEn ? 'TROUBLESHOOTING & FAQS' : 'XỬ LÝ LỖI THƯỜNG GẶP'}
            </h4>
            <div className="space-y-2 text-[11px]">
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <strong className="text-red-400">{isEn ? 'No signals displaying?' : 'Không có tín hiệu?'}</strong>
                <p className="text-slate-400 mt-0.5">{isEn ? 'Check System Telemetry to verify scanner daemon is running. Lower threshold slider to 0.25 (top bar).' : 'Kiểm tra GIÁM SÁT — bộ quét có chạy không? Chạy dao-vang scanner start. Hạ ngưỡng xuống 0,25 (thanh trượt ở đầu trang).'}</p>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <strong className="text-red-400">{isEn ? 'Probability = 0 or chart missing?' : 'Điểm phân phối = 0 hoặc không có biểu đồ?'}</strong>
                <p className="text-slate-400 mt-0.5">{isEn ? 'Server automatically fetches fallback candles from Binance API if database is initializing.' : 'Máy chủ sẽ tự lấy dữ liệu dự phòng từ API Binance. Nếu vẫn lỗi, hãy khởi động lại máy chủ.'}</p>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <strong className="text-red-400">{isEn ? 'Telegram alerts not sending?' : 'Telegram không gửi?'}</strong>
                <p className="text-slate-400 mt-0.5">{isEn ? 'Verify bot_token and chat_id in your .env configuration file.' : 'Kiểm tra bot_token và chat_id trong file cấu hình .env.'}</p>
              </div>
            </div>
          </div>

          {/* Important note */}
          <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-3 text-[11px] text-amber-300 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <div>
              <strong>{isEn ? 'Important Disclaimer:' : 'Lưu ý quan trọng:'}</strong> {isEn 
                ? 'This is a quantitative research and decision-support radar (Human-in-the-loop). It is not automated trading and does not constitute financial advice.'
                : 'Đây là công cụ nghiên cứu và hỗ trợ ra quyết định, không phải lời khuyên đầu tư. AI có thể sai — luôn kết hợp với đánh giá thủ công trước khi vào lệnh.'}
            </div>
          </div>

          {/* Glossary */}
          <div className="space-y-3">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5" /> {isEn ? 'INDICATOR GLOSSARY' : 'TỪ ĐIỂN THUẬT NGỮ'}
            </div>
            {filtered.map((item, idx) => (
              <div key={idx} className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="text-xs font-bold text-amber-400 font-mono mb-1">{item.term}</div>
                <div className="text-xs text-slate-300 leading-relaxed">{item.desc}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="p-3 border-t border-slate-800 bg-slate-950 text-right">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold"
          >
            {isEn ? 'Close' : 'Đóng'}
          </button>
        </div>

      </div>
    </div>
  );
};
