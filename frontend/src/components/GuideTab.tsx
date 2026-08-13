import React from 'react';
import { BookOpen, Terminal, AlertTriangle, Workflow, Bug } from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';

export const GuideTab: React.FC = () => {
  const { language } = useTranslation();
  const isEn = language === 'en';

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
        <BookOpen className="w-3.5 h-3.5 text-amber-400" />
        {isEn ? 'USER GUIDE & DOCUMENTATION' : 'HƯỚNG DẪN SỬ DỤNG'}
      </h3>

      {/* Quick Start */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2">
          {isEn ? '🌐 Web Dashboard Overview' : '🌐 Giao diện web'}
        </h4>
        <ol className="text-[11px] text-slate-300 space-y-1.5 list-decimal list-inside">
          <li><strong className="text-slate-100">{isEn ? 'RADAR FEED' : 'RADAR CẢNH BÁO'}</strong> (cột trái): {isEn ? 'Real-time alert list from 24/7 scanner. Click any signal card to open detailed charts.' : 'danh sách tín hiệu xả từ bộ quét 24/7. Bấm vào 1 tín hiệu để xem chi tiết.'}</li>
          <li><strong className="text-slate-100">{isEn ? 'MAIN WORKSPACE' : 'PHÂN TÍCH'}</strong> (giữa): {isEn ? 'Deep dive analysis into 5 key metrics (OI 24h, Funding, Taker Sell, RSI 15m, Target -8%) and Candlestick chart.' : 'phân tích chuyên sâu coin đã chọn — 8 tín hiệu + mô hình tăng nóng + biểu đồ. Bấm "Chạy lại chấm điểm" để chạy toàn bộ AI.'}</li>
          <li><strong className="text-slate-100">{isEn ? 'CANDIDATES' : 'Bảng Ứng Viên'}</strong>: {isEn ? 'Ranking of all coins filtered by distribution risk.' : 'xếp hạng tất cả coin theo điểm rủi ro.'}</li>
          <li><strong className="text-slate-100">{isEn ? 'MULTI-COIN SCAN' : 'Quét nhiều coin'}</strong>: {isEn ? 'Multi-timeframe scanner results — AI model vs heuristic baselines.' : 'kết quả quét các coin biến động mạnh — AI so với mốc cơ sở.'}</li>
          <li><strong className="text-slate-100">{isEn ? 'BACKTEST EXPERIMENTS' : 'Kiểm thử lịch sử'}</strong>: {isEn ? 'Out-of-sample walk-forward validation — precision, recall, leakage audit.' : 'thử nghiệm AI trên dữ liệu cũ — độ chính xác, tỷ lệ bắt được, kiểm tra rò rỉ dữ liệu.'}</li>
          <li><strong className="text-slate-100">{isEn ? 'FORWARD TESTING' : 'Kiểm thử dữ liệu mới'}</strong>: {isEn ? 'Frozen models evaluated on live out-of-sample data.' : 'đóng băng mô hình → chấm điểm trên dữ liệu mới.'}</li>
          <li><strong className="text-slate-100">{isEn ? 'MARKET CONTEXT' : 'THỊ TRƯỜNG'}</strong>: {isEn ? 'Binance derivatives market overview + top gainers/losers.' : 'tổng quan Binance + các mã tăng/giảm mạnh.'}</li>
          <li><strong className="text-slate-100">{isEn ? 'SYSTEM AUDITS' : 'GIÁM SÁT'}</strong>: {isEn ? '24/7 background scanner logs + Telegram delivery audits.' : 'nhật ký bộ quét 24/7 + các lượt gửi Telegram.'}</li>
        </ol>
      </div>

      {/* Tabs explanation */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Workflow className="w-3.5 h-3.5" /> {isEn ? 'MAIN MODULES' : 'CÁC TAB CHÍNH'}
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-emerald-400">{isEn ? 'Decision Center' : 'PHÂN TÍCH (Giao dịch)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {isEn 
                ? 'Deep analytics on selected symbol: 5 key derivatives indicators (OI Delta, Funding Rate, Taker Sell Ratio, RSI, Target Drawdown) and interactive Candlestick chart.' 
                : 'Phân tích chuyên sâu 1 coin: 8 tín hiệu (phân kỳ giá-khối lượng, funding, OI, động lượng, mô hình tăng nóng...), bối cảnh BTC, RSI, mẫu hình tăng nóng.'}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-amber-400">{isEn ? 'Candidate Ranking' : 'Bảng Ứng Viên (Giao dịch)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {isEn ? 'Ranking of coins filtered by distribution risk score.' : 'Bảng xếp hạng tất cả coin theo điểm phân phối tổng hợp. Bấm vào coin để xem phân tích chi tiết.'}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-purple-400">{isEn ? 'Backtest Experiments' : 'Kiểm thử lịch sử (Nghiên cứu)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {isEn ? 'Walk-forward cross validation across 600k+ candles with strict zero lookahead bias.' : 'Đánh giá AI trên dữ liệu cũ: chia dữ liệu cuốn chiếu theo thời gian, kiểm tra rò rỉ dữ liệu, khoảng tin cậy.'}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-sky-400">{isEn ? 'Forward Testing' : 'Kiểm thử dữ liệu mới (Nghiên cứu)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {isEn ? 'Frozen models scoring live out-of-sample data with calibration curve evaluation.' : 'Đóng băng mô hình → chấm điểm trên dữ liệu MỚI. Kiểm tra độ lệch — mô hình có ổn định không sau khi triển khai.'}
            </p>
          </div>
        </div>
      </div>

      {/* CLI */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5" /> {isEn ? 'CLI Commands' : 'CLI (dòng lệnh)'}
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
            <span className="text-slate-400"> — {isEn ? 'Execute walk-forward backtest' : 'Chạy kiểm thử lịch sử (thu thập + gán nhãn + huấn luyện + đánh giá)'}</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang data collect</span>
            <span className="text-slate-400"> — {isEn ? 'Manual data collection' : 'Thu thập dữ liệu thủ công'}</span>
          </div>
        </div>
      </div>

      {/* Troubleshooting */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Bug className="w-3.5 h-3.5" /> {isEn ? 'TROUBLESHOOTING' : 'XỬ LÝ LỖI THƯỜNG GẶP'}
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">{isEn ? 'No signals displaying?' : 'Không có tín hiệu?'}</strong>
            <p className="text-slate-400 mt-0.5">{isEn ? 'Check System Telemetry to verify scanner daemon is running. Lower threshold slider to 0.25.' : 'Kiểm tra tab GIÁM SÁT — bộ quét có chạy không? Chạy dao-vang scanner start. Hạ ngưỡng xuống 0,25.'}</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">{isEn ? 'Telegram alerts not sending?' : 'Telegram không gửi?'}</strong>
            <p className="text-slate-400 mt-0.5">{isEn ? 'Verify bot_token and chat_id in your .env configuration file.' : 'Kiểm tra bot_token + chat_id trong phần cấu hình .env.'}</p>
          </div>
        </div>
      </div>

      <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-3 text-[11px] text-amber-300 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          <strong>{isEn ? 'Important Notice:' : 'Lưu ý quan trọng:'}</strong> {isEn 
            ? 'This is a quantitative research and decision-support radar (Human-in-the-loop). It is not automated trading and does not constitute financial advice.'
            : 'Đây là công cụ nghiên cứu, không phải lời khuyên đầu tư. AI có thể sai — luôn kết hợp với đánh giá thủ công trước khi vào lệnh.'}
        </div>
      </div>
    </div>
  );
};
