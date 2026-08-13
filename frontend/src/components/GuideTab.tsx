import React from 'react';
import { BookOpen, Terminal, AlertTriangle, Lightbulb, Workflow, Bug } from 'lucide-react';

export const GuideTab: React.FC = () => {
  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
        <BookOpen className="w-3.5 h-3.5 text-amber-400" />
        HƯỚNG DẪN SỬ DỤNG
      </h3>

      {/* Quick Start */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2">🌐 Giao diện web</h4>
        <ol className="text-[11px] text-slate-300 space-y-1.5 list-decimal list-inside">
          <li><strong className="text-slate-100">RADAR CẢNH BÁO</strong> (cột trái): danh sách tín hiệu xả từ bộ quét 24/7. Bấm vào 1 tín hiệu để xem chi tiết.</li>
          <li><strong className="text-slate-100">PHÂN TÍCH</strong> (giữa): phân tích chuyên sâu coin đã chọn — 8 tín hiệu + mô hình tăng nóng + biểu đồ. Bấm "Chạy phân tích" để chạy toàn bộ AI.</li>
          <li><strong className="text-slate-100">Bảng Ứng Viên</strong>: xếp hạng tất cả coin theo điểm rủi ro.</li>
          <li><strong className="text-slate-100">Quét nhiều coin</strong>: kết quả quét các coin biến động mạnh — AI so với mốc cơ sở.</li>
          <li><strong className="text-slate-100">Kiểm thử lịch sử</strong>: 80 thử nghiệm AI trên dữ liệu cũ — độ chính xác, tỷ lệ bắt được, kiểm tra rò rỉ dữ liệu.</li>
          <li><strong className="text-slate-100">Kiểm thử dữ liệu mới</strong>: đóng băng mô hình → chấm điểm trên dữ liệu mới.</li>
          <li><strong className="text-slate-100">THỊ TRƯỜNG</strong>: tổng quan Binance + 50 mã tăng/giảm mạnh. Bấm coin để xem biểu đồ 72 giờ.</li>
          <li><strong className="text-slate-100">GIÁM SÁT</strong>: nhật ký bộ quét 24/7 + các lượt gửi Telegram.</li>
        </ol>
      </div>

      {/* Tabs explanation */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Workflow className="w-3.5 h-3.5" /> CÁC TAB CHÍNH
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-emerald-400">PHÂN TÍCH (Giao dịch)</strong>
            <p className="text-slate-400 mt-0.5">Phân tích chuyên sâu 1 coin: 8 tín hiệu (phân kỳ giá-khối lượng, funding, OI, động lượng, mô hình tăng nóng...), bối cảnh BTC, RSI, mẫu hình tăng nóng. Bấm "Chạy phân tích" để chạy toàn bộ quy trình.</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-amber-400">Bảng Ứng Viên (Giao dịch)</strong>
            <p className="text-slate-400 mt-0.5">Bảng xếp hạng tất cả coin theo điểm phân phối tổng hợp. Bấm vào coin để xem phân tích chi tiết.</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-sky-400">Quét nhiều coin (Nghiên cứu)</strong>
            <p className="text-slate-400 mt-0.5">Quét các coin biến động mạnh → chạy AI → so sánh với "đoán mò". Coin nào AI tốt hơn mốc = có lợi thế.</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-purple-400">Kiểm thử lịch sử (Nghiên cứu)</strong>
            <p className="text-slate-400 mt-0.5">Đánh giá AI trên dữ liệu cũ: chia dữ liệu cuốn chiếu theo thời gian, kiểm tra rò rỉ dữ liệu, khoảng tin cậy. AI phải vượt mốc so sánh và không bị rò rỉ dữ liệu.</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-sky-400">Kiểm thử dữ liệu mới (Nghiên cứu)</strong>
            <p className="text-slate-400 mt-0.5">Đóng băng mô hình → chấm điểm trên dữ liệu MỚI. Kiểm tra độ lệch — mô hình có ổn định không sau khi triển khai.</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">THỊ TRƯỜNG (Quan sát)</strong>
            <p className="text-slate-400 mt-0.5">Tổng quan niêm yết Binance (giao ngay/USD-M/COIN-M) + 50 mã tăng/giảm mạnh. Bấm coin để xem biểu đồ 72 giờ.</p>
          </div>
        </div>
      </div>

      {/* CLI */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5" /> CLI (dòng lệnh)
        </h4>
        <div className="space-y-1.5 text-[11px] font-mono">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang scanner start</span>
            <span className="text-slate-400"> — Bộ quét 24/7 (thu thập + chấm điểm + gửi Telegram)</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang scanner stop</span>
            <span className="text-slate-400"> — Dừng bộ quét</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang experiment run</span>
            <span className="text-slate-400"> — Chạy kiểm thử lịch sử (thu thập + gán nhãn + huấn luyện + đánh giá)</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang data collect</span>
            <span className="text-slate-400"> — Thu thập dữ liệu thủ công</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang data listing-scan</span>
            <span className="text-slate-400"> — Quét danh sách niêm yết Binance (giao ngay/hợp đồng tương lai)</span>
          </div>
        </div>
      </div>

      {/* Workflow */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Lightbulb className="w-3.5 h-3.5" /> QUY TRÌNH TỪ ĐẦU ĐẾN CUỐI
        </h4>
        <div className="text-[11px] text-slate-300 space-y-1.5">
          <div className="flex gap-2">
            <span className="text-amber-400 font-bold">1.</span>
            <span><strong className="text-slate-100">Thu thập dữ liệu</strong>: <code className="text-emerald-400">dao-vang scanner start</code> — bộ quét 24/7 tự thu thập + chấm điểm</span>
          </div>
          <div className="flex gap-2">
            <span className="text-amber-400 font-bold">2.</span>
            <span><strong className="text-slate-100">Xem tín hiệu</strong>: Vào web → RADAR (cột trái) → bấm tín hiệu → tab PHÂN TÍCH</span>
          </div>
          <div className="flex gap-2">
            <span className="text-amber-400 font-bold">3.</span>
            <span><strong className="text-slate-100">Kiểm chứng AI</strong>: tab Kiểm thử lịch sử → xem độ chính xác so với mốc cơ sở + kiểm tra rò rỉ dữ liệu</span>
          </div>
          <div className="flex gap-2">
            <span className="text-amber-400 font-bold">4.</span>
            <span><strong className="text-slate-100">Kiểm thử dữ liệu mới</strong>: tab Kiểm thử dữ liệu mới → đóng băng mô hình → chấm điểm trên dữ liệu mới</span>
          </div>
          <div className="flex gap-2">
            <span className="text-amber-400 font-bold">5.</span>
            <span><strong className="text-slate-100">Triển khai</strong>: Nếu AI vượt mốc + không rò rỉ dữ liệu + ổn định trên dữ liệu mới → dùng tín hiệu thật</span>
          </div>
        </div>
      </div>

      {/* Troubleshooting */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Bug className="w-3.5 h-3.5" /> XỬ LÝ LỖI THƯỜNG GẶP
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">Không có tín hiệu?</strong>
            <p className="text-slate-400 mt-0.5">Kiểm tra tab GIÁM SÁT — bộ quét có chạy không? Chạy <code className="text-emerald-400">dao-vang scanner start</code>. Hạ ngưỡng xuống 0,25 (thanh trượt ở đầu trang).</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">Kiểm thử lịch sử không qua kiểm tra rò rỉ dữ liệu?</strong>
            <p className="text-slate-400 mt-0.5">Đặc trưng đang dùng thông tin tương lai — rà <code className="text-emerald-400">feature_set_version</code> và đảm bảo đặc trưng chỉ dùng dữ liệu ≤ thời điểm đặc trưng.</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">Không có dữ liệu kiểm thử mới?</strong>
            <p className="text-slate-400 mt-0.5">Cần dữ liệu SAU mốc cắt <code className="text-emerald-400">train_cutoff</code>. Nếu mô hình mới đóng băng → chờ hơn 24 giờ để có dữ liệu kiểm thử mới.</p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">Telegram không gửi?</strong>
            <p className="text-slate-400 mt-0.5">Kiểm tra <code className="text-emerald-400">bot_token</code> + <code className="text-emerald-400">chat_id</code> trong phần cấu hình. Xem <code className="text-emerald-400">docs/TELEGRAM_SETUP.md</code>.</p>
          </div>
        </div>
      </div>

      <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-3 text-[11px] text-amber-300 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          <strong>Lưu ý quan trọng:</strong> Đây là công cụ nghiên cứu, không phải lời khuyên đầu tư.
          AI có thể sai — luôn kết hợp với đánh giá thủ công trước khi vào lệnh.
          Kiểm thử lịch sử dùng cách chia dữ liệu cuốn chiếu theo thời gian (không trộn dữ liệu) + khoảng cách 12 giờ giữa huấn luyện/kiểm tra để tránh nhìn trộm tương lai.
        </div>
      </div>
    </div>
  );
};
