import React from 'react';
import { X, HelpCircle, Search, BookOpen, Terminal, AlertTriangle, Lightbulb, Workflow, Bug } from 'lucide-react';

interface GlossaryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const GLOSSARY_ENTRIES = [
  { term: "Phân phối", desc: "Coin bắt đầu 'xả' — mất động lượng tăng, sắp giảm mạnh. Tính toán tự động bởi AI từ dữ liệu định lượng 5 phút." },
  { term: "Độ chính xác", desc: "Trong 100 lần AI báo 'sắp xả', bao nhiêu lần đúng? Cao = ít báo sai. Đảo Vàng đạt 38,5% (gấp 7,4 lần mốc cơ sở)." },
  { term: "Tỷ lệ bắt được", desc: "Trong 100 lần coin THẬT SỰ xả, AI bắt được bao nhiêu? Cao = ít bỏ sót. Đảo Vàng đạt 88,2%." },
  { term: "Điểm Brier (độ chuẩn xác)", desc: "Mức độ tin cậy của xác suất báo từ AI. Số càng THẤP càng tốt (0 = hoàn hảo, 1 = sai hoàn toàn)." },
  { term: "Thời gian báo trước", desc: "AI báo trước trung bình khoảng 6,8 giờ trước khi cú xả 8% thực sự diễn ra." },
  { term: "Kiểm định cuốn chiếu theo thời gian", desc: "Kiểm tra theo chuỗi thời gian — huấn luyện trên quá khứ, kiểm tra trên tương lai. Đảm bảo không 'nhìn trộm' tương lai." },
  { term: "Khối lượng hợp đồng mở (OI)", desc: "Tổng số lượng hợp đồng tương lai đang mở. OI tăng vọt + giá suy yếu = dấu hiệu tích tụ vị thế xả mạnh." },
  { term: "Tỷ lệ phí funding", desc: "Khoản phí giữa vị thế mua và bán. Funding dương quá cao = số đông đang FOMO mua đuổi, dễ bị bóp ngắn ngược." },
  { term: "Tỷ lệ mua/bán chủ động", desc: "Tỷ lệ khối lượng mua/bán chủ động từ lệnh thị trường. < 1,0 nghĩa là phe bán đang xả hàng chủ động." },
  { term: "Mức giảm mục tiêu (-8%)", desc: "Tiêu chuẩn xác định cú xả: Giá giảm ít nhất 8% trong vòng 24 giờ kể từ tín hiệu." }
];

export const GlossaryModal: React.FC<GlossaryModalProps> = ({ isOpen, onClose }) => {
  const [searchTerm, setSearchTerm] = React.useState('');

  if (!isOpen) return null;

  const filtered = GLOSSARY_ENTRIES.filter(item =>
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
            <h2 className="text-base font-bold text-slate-100">Trợ giúp & Từ điển</h2>
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
              placeholder="Tìm kiếm thuật ngữ (OI, độ chính xác, funding...)"
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
            <p className="mb-1"><strong className="text-amber-400">Đảo Vàng AI Radar</strong> giúp phát hiện sớm dấu hiệu <strong>phân phối</strong> — coin sắp xả giá. Hệ thống quét toàn bộ coin hợp đồng tương lai trên Binance 24/7, tính toán điểm số từ 8 yếu tố kỹ thuật và dữ liệu chuỗi khối.</p>
            <ul className="list-disc list-inside space-y-0.5 text-slate-400">
              <li><strong>Điểm phân phối:</strong> điểm càng cao, khả năng xả càng lớn.</li>
              <li><strong>Mức giảm mục tiêu 8%:</strong> giá giảm ít nhất 8% trong 24 giờ kể từ tín hiệu.</li>
              <li><strong>Tự động thông minh:</strong> tự động gửi cảnh báo Telegram khi điểm số đạt ngưỡng.</li>
            </ul>
          </div>

          {/* Quick Start */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5" /> HƯỚNG DẪN SỬ DỤNG
            </h4>
            <ol className="text-[11px] text-slate-300 space-y-1.5 list-decimal list-inside">
              <li><strong className="text-slate-100">RADAR CẢNH BÁO</strong> (cột trái): danh sách tín hiệu xả từ bộ quét 24/7. Bấm vào 1 tín hiệu để xem chi tiết.</li>
              <li><strong className="text-slate-100">PHÂN TÍCH</strong> (giữa): phân tích chuyên sâu coin đã chọn — 8 tín hiệu + mô hình tăng nóng + biểu đồ. Bấm "Chạy lại chấm điểm" để chạy toàn bộ AI.</li>
              <li><strong className="text-slate-100">Bảng Ứng Viên</strong>: xếp hạng tất cả coin theo điểm rủi ro.</li>
              <li><strong className="text-slate-100">Quét nhiều coin</strong>: kết quả quét các coin biến động mạnh — AI so với mốc cơ sở.</li>
              <li><strong className="text-slate-100">Kiểm thử lịch sử</strong>: thử nghiệm AI trên dữ liệu cũ — độ chính xác, tỷ lệ bắt được, kiểm tra rò rỉ dữ liệu.</li>
              <li><strong className="text-slate-100">Kiểm thử dữ liệu mới</strong>: đóng băng mô hình → chấm điểm trên dữ liệu mới.</li>
              <li><strong className="text-slate-100">THỊ TRƯỜNG</strong>: tổng quan Binance + các mã tăng/giảm mạnh. Bấm coin để xem biểu đồ.</li>
              <li><strong className="text-slate-100">GIÁM SÁT</strong>: nhật ký bộ quét 24/7 + các lượt gửi Telegram.</li>
            </ol>
          </div>

          {/* CLI */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5" /> LỆNH CLI HỮU ÍCH
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
                <span className="text-slate-400"> — Chạy kiểm thử lịch sử</span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <span className="text-emerald-400">dao-vang data collect</span>
                <span className="text-slate-400"> — Thu thập dữ liệu thủ công</span>
              </div>
            </div>
          </div>

          {/* Workflow */}
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
            <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
              <Workflow className="w-3.5 h-3.5" /> QUY TRÌNH TỪ ĐẦU ĐẾN CUỐI
            </h4>
            <div className="text-[11px] text-slate-300 space-y-1.5">
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">1.</span>
                <span><strong className="text-slate-100">Thu thập dữ liệu</strong>: <code className="text-emerald-400">dao-vang scanner start</code> — bộ quét 24/7 tự thu thập + chấm điểm</span>
              </div>
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">2.</span>
                <span><strong className="text-slate-100">Xem tín hiệu</strong>: Vào web → RADAR → bấm tín hiệu → tab PHÂN TÍCH</span>
              </div>
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">3.</span>
                <span><strong className="text-slate-100">Kiểm chứng AI</strong>: Kiểm thử lịch sử → xem độ chính xác so với mốc cơ sở + kiểm tra rò rỉ dữ liệu</span>
              </div>
              <div className="flex gap-2">
                <span className="text-amber-400 font-bold">4.</span>
                <span><strong className="text-slate-100">Kiểm thử dữ liệu mới</strong>: Kiểm thử dữ liệu mới → đóng băng mô hình → chấm điểm trên dữ liệu mới</span>
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
                <p className="text-slate-400 mt-0.5">Kiểm tra GIÁM SÁT — bộ quét có chạy không? Chạy <code className="text-emerald-400">dao-vang scanner start</code>. Hạ ngưỡng xuống 0,25 (thanh trượt ở đầu trang).</p>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <strong className="text-red-400">Điểm phân phối = 0 hoặc không có biểu đồ?</strong>
                <p className="text-slate-400 mt-0.5">Coin có thể chưa được bộ quét lưu nến. Máy chủ sẽ tự lấy dữ liệu dự phòng từ API Binance. Nếu vẫn lỗi, hãy khởi động lại máy chủ.</p>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800">
                <strong className="text-red-400">Telegram không gửi?</strong>
                <p className="text-slate-400 mt-0.5">Kiểm tra <code className="text-emerald-400">bot_token</code> + <code className="text-emerald-400">chat_id</code> trong config.</p>
              </div>
            </div>
          </div>

          {/* Important note */}
          <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-3 text-[11px] text-amber-300 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <div>
              <strong>Lưu ý quan trọng:</strong> Đây là công cụ nghiên cứu, không phải lời khuyên đầu tư. AI có thể sai — luôn kết hợp với đánh giá thủ công trước khi vào lệnh.
            </div>
          </div>

          {/* Glossary */}
          <div className="space-y-3">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5" /> TỪ ĐIỂN THUẬT NGỮ
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
            Đóng
          </button>
        </div>

      </div>
    </div>
  );
};
