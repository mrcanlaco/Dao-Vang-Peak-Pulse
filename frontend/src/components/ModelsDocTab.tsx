import React, { useState, useEffect, useMemo } from 'react';
import { 
  Brain, Shield, BarChart3, Network, Settings, Check, X,
  FileText, Download, Copy, CheckCheck, BookOpen, Sparkles,
  ChevronRight, Calendar, Users, Database, Loader2
} from 'lucide-react';
import { MarkdownRenderer } from './DecisionCenter/MarkdownRenderer';

interface ResearchPaper {
  id: string;
  code: string;
  title: string;
  title_en?: string;
  date: string;
  category: string;
  tags: string[];
  key_metric: string;
  sample_size: string;
  badge: string;
  badge_color: 'emerald' | 'amber' | 'cyan' | 'purple' | 'blue' | 'slate';
  abstract: string;
  content: string;
  file_size_bytes?: number;
}

const FALLBACK_REPORTS: ResearchPaper[] = [
  {
    id: "01_so_sanh_heuristic_vs_machine_learning",
    code: "RES-2026-0830-01",
    title: "So Sánh Đối Đầu: Mô Hình Heuristic 0–100 vs Machine Learning (LightGBM & LogReg)",
    title_en: "Benchmark: V1 Heuristic (0-100) vs Machine Learning (LightGBM & LogReg)",
    date: "2026-08-30",
    category: "BENCHMARK",
    tags: ["HEURISTIC", "LIGHTGBM", "ROC_AUC", "FEATURE_IMPORTANCE"],
    key_metric: "LightGBM 20.93% vs Heuristic 13.28% (Gấp 1.6x)",
    sample_size: "160 altcoins, 1.16M rows (1 năm)",
    badge: "Mới nhất",
    badge_color: "emerald",
    abstract: "Kiểm định độc lập trên 160 altcoins chứng minh Heuristic gốc chỉ đạt 13.28% precision (ngưỡng >=70 đạt 0%). Regime + LightGBM đạt 20.93% nhờ khai thác tương quan phi tuyến và hiệu chuẩn xác suất.",
    content: `# 📊 Báo Cáo Nghiên Cứu #01: So Sánh Đối Đầu Mô Hình Heuristic 0–100 vs Machine Learning

> **Mã nghiên cứu:** \`RES-2026-0830-01\`  
> **Ngày công bố:** 30/08/2026  
> **Tác giả:** Đội ngũ Nghiên cứu & Định lượng Đảo Vàng (\`dao_vang Quant Lab\`)  
> **Quy mô mẫu:** 160 Altcoins vốn hóa vừa và nhỏ ($10M–$500M)  
> **Khoảng thời gian:** 1 năm gần nhất (08/2025 → 08/2026, nến 5 phút)  
> **Tổng số nến đánh giá:** 1,164,492 hàng dữ liệu điều kiện xả (Exhaustion Candidates)  
> **Phương pháp xác thực:** 8-Fold Walk-Forward Cross-Validation (Embargo 48 giờ chống rò rỉ dữ liệu)

---

## 1. Tóm Tắt Nghiên Cứu (Executive Abstract)

Hệ thống Đảo Vàng ban đầu sử dụng mô hình chấm điểm theo quy tắc chuyên gia **V1 Heuristic (thang điểm 0–100)** gồm 8 thành phần trọng số tuyến tính để phát hiện các tín hiệu phân phối đỉnh và tìm cơ hội Short.

Nghiên cứu này thực hiện kiểm định độc lập trên dữ liệu lịch sử quy mô lớn nhằm trả lời câu hỏi:
1. *Hiệu quả thực tế của mô hình Heuristic gốc là bao nhiêu khi so với tỷ lệ ngẫu nhiên của thị trường?*
2. *Khi nâng ngưỡng điểm Heuristic lên cao (>= 70 hoặc >= 80), tỷ lệ thắng có tăng theo không?*
3. *Mô hình Machine Learning (LightGBM kết hợp Isotonic Calibration và Regime Gate) cải thiện độ chính xác bao nhiêu lần so với Heuristic?*

### Kết quả then chốt:
- **Tỷ lệ nền ngẫu nhiên (Base Rate):** 11.74%
- **Heuristic gốc ở cấu hình mặc định (>= 40):** Đạt **13.28% precision** (chỉ nhỉnh hơn ngẫu nhiên 1.54%, tỷ lệ báo động giả lên tới 86.7%).
- **Heuristic ở ngưỡng khuyến nghị Short (>= 70):** Đạt **0.00% precision** (31/31 tín hiệu thua do rơi vào bẫy bắt đỉnh nến đang pump).
- **Regime Gate + LightGBM (p98):** Đạt **20.93% precision** (gấp **1.6 lần** Heuristic, vượt trội trên mọi chu kỳ kiểm định).

---

## 2. Bảng So Sánh Hiệu Năng Toàn Diện

| Mô hình / Chiến lược | Ngưỡng kích hoạt | Precision (Độ chính xác) | Recall (Độ bao phủ) | Tổng tín hiệu | Lệnh đúng (TP) | Báo động giả (False Alarms) | Precision ở Sideway |
| :---| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 🥇 **Optimal: Regime + LightGBM** | **Top 2% (p98)** | **20.93%** 🏆 | **14.69%** | **92,587** | **19,375** | **73,212** | **20.98%** |
| 🥈 **Challenger: LightGBM** | **Top 2% (p98)** | **20.59%** | 18.98% | 121,628 | 25,044 | 96,584 | 20.98% |
| 🥉 **V1 Heuristic gốc (Live)** | **Điểm >= 40** | **13.28%** | 15.55% | 139,890 | 18,580 | 121,310 | 13.34% |
| 4. **Champion: LogisticRegression** | **Top 2% (p98)** | **12.75%** | 2.48% | 22,670 | 2,891 | 19,779 | 12.08% |
| 5. **V1 Heuristic (Watch)** | **Điểm >= 50** | **12.56%** | 1.36% | 12,400 | 1,557 | 10,843 | 11.80% |
| 6. **Regime + Heuristic** | **Điểm >= 50** | **12.52%** | 1.14% | 10,464 | 1,310 | 9,154 | 11.80% |
| 7. **V1 Heuristic** | **Điểm >= 60** | **11.20%** | 0.07% | 732 | 82 | 650 | 6.99% |
| 8. **V1 Heuristic (Short Candidate)** | **Điểm >= 70** | **0.00%** ⚠️ | 0.00% | 31 | 0 | 31 | 0.00% |
| 9. **V1 Heuristic (Extreme)** | **Điểm >= 80** | **0.00%** ⚠️ | 0.00% | 0 | 0 | 0 | 0.00% |

---

## 3. Bóc Tách Sức Mạnh 8 Thành Phần Heuristic (ROC-AUC Analysis)

| Thành phần | Trọng số cũ | ROC-AUC | Hệ số tương quan | Điểm TB lệnh Thắng | Điểm TB lệnh Thua | Nhận xét & Đánh giá |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **BTC Context Filter** | 15% | **0.5707** 🟢 | +0.0863 | **52.5** | **46.0** | **Tốt nhất**: Xu hướng BTC giảm là bối cảnh thuận lợi nhất cho Short |
| **Price-Volume Divergence** | 20% | **0.5486** 🟢 | +0.0556 | **11.9** | **10.0** | **Hiệu quả**: Giá tăng nhưng khối lượng giảm thể hiện lực mua ảo |
| **Momentum Exhaustion** | 15% | **0.5227** 🟡 | +0.0263 | **24.0** | **21.8** | **Đóng góp dương nhẹ**: Tốc độ tăng 1h suy giảm |
| **Open Interest Divergence** | 10% | **0.5060** ⚪ | -0.0002 | **32.1** | **32.2** | **Vô nghĩa**: Chưa nắm bắt được dòng tiền phái sinh |
| **Fake Breakout (Bull Trap)** | 5% | **0.5021** ⚪ | +0.0079 | **11.7** | **11.5** | **Vô nghĩa**: Nến 5m quá nhiều râu giả gây nhiễu |
| **Taker Sell Pressure** | 10% | **0.4956** ⚪ | +0.0116 | **63.5** | **62.2** | **Vô nghĩa**: Tỷ lệ taker sell thường xuất hiện trễ |
| **Funding Spike** | 15% | **0.4495** 🔴 | -0.0587 | **3.7** | **7.0** | ⚠️ **Phản tác dụng**: Funding cực cao hay bị kéo Short Squeeze tiếp |
| **Distance from High** | 10% | **0.4120** 🔴 | -0.0917 | **79.9** | **84.9** | ⚠️ **Nguy hiểm nhất**: Càng sát đỉnh 24h thì giá càng dễ phá đỉnh tiếp |
| **TỔNG ĐIỂM HEURISTIC (0-100)** | 100% | **0.5338** | +0.0367 | **32.6** | **31.7** | **Kém**: Điểm khi thắng (32.6) và khi thua (31.7) gần như y hệt nhau |

---

## 4. Kết Luận Thực Thi
- **Giao diện Web:** Tiếp tục duy trì Điểm Heuristic 0–100 để hiển thị trực quan các đặc tính thị trường.
- **Quyết định Bắn Tín Hiệu (Execution Gate):** Chuyển dịch hoàn toàn sang **Bộ đôi Regime Gate + LightGBM Calibrated Probability**.`
  }
];

export const ModelsDocTab: React.FC = () => {
  const [subTab, setSubTab] = useState<'OVERVIEW' | 'RESEARCH'>('RESEARCH');
  const [reports, setReports] = useState<ResearchPaper[]>(FALLBACK_REPORTS);
  const [selectedReportId, setSelectedReportId] = useState<string>('01_so_sanh_heuristic_vs_machine_learning');
  const [selectedTag, setSelectedTag] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Fetch reports list from backend API
  useEffect(() => {
    let isMounted = true;
    const fetchReports = async () => {
      try {
        setIsLoading(true);
        const res = await fetch('/api/research/reports');
        if (res.ok) {
          const data = await res.json();
          if (data.reports && data.reports.length > 0 && isMounted) {
            setReports(data.reports);
            if (!data.reports.some((r: ResearchPaper) => r.id === selectedReportId)) {
              setSelectedReportId(data.reports[0].id);
            }
          }
        }
      } catch (err) {
        console.warn('Failed to fetch research reports API, using fallback:', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };
    fetchReports();
    return () => { isMounted = false; };
  }, []);

  // Filter tags
  const allTags = useMemo(() => {
    const set = new Set<string>();
    reports.forEach(r => r.tags?.forEach(t => set.add(t)));
    return ['ALL', ...Array.from(set)];
  }, [reports]);

  // Filtered reports
  const filteredReports = useMemo(() => {
    return reports.filter(r => {
      const matchTag = selectedTag === 'ALL' || r.tags?.includes(selectedTag);
      const matchSearch = !searchQuery.trim() || 
        r.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.abstract.toLowerCase().includes(searchQuery.toLowerCase()) ||
        r.code.toLowerCase().includes(searchQuery.toLowerCase());
      return matchTag && matchSearch;
    });
  }, [reports, selectedTag, searchQuery]);

  const selectedReport = useMemo(() => {
    return reports.find(r => r.id === selectedReportId) || reports[0] || FALLBACK_REPORTS[0];
  }, [reports, selectedReportId]);

  const handleCopyMarkdown = () => {
    if (!selectedReport?.content) return;
    navigator.clipboard.writeText(selectedReport.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    if (!selectedReport?.content) return;
    const blob = new Blob([selectedReport.content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedReport.id || 'research_report'}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getBadgeColor = (color: string) => {
    switch (color) {
      case 'emerald': return 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60';
      case 'amber': return 'bg-amber-950/80 text-amber-400 border-amber-800/60';
      case 'cyan': return 'bg-cyan-950/80 text-cyan-400 border-cyan-800/60';
      case 'purple': return 'bg-purple-950/80 text-purple-400 border-purple-800/60';
      case 'blue': return 'bg-blue-950/80 text-blue-400 border-blue-800/60';
      default: return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-950 text-slate-300">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800 px-4 py-3 bg-slate-900/60 backdrop-blur shrink-0 gap-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-gradient-to-br from-amber-500/20 to-cyan-500/20 border border-amber-500/30 rounded-lg">
            <Brain className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Tài Liệu Models & Thư Viện Nghiên Cứu Lịch Sử</h2>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50 font-mono flex items-center gap-1">
                {isLoading && <Loader2 className="w-2.5 h-2.5 animate-spin text-cyan-400" />}
                <span>{reports.length} Papers</span>
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Kiến trúc thuật toán, báo cáo kiểm định thực tế và tài liệu lưu trữ so sánh chất lượng mô hình.
            </p>
          </div>
        </div>

        {/* Sub-tab Navigation */}
        <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 self-start sm:self-auto">
          <button
            onClick={() => setSubTab('RESEARCH')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              subTab === 'RESEARCH'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>Thư Viện Nghiên Cứu ({reports.length})</span>
          </button>
          <button
            onClick={() => setSubTab('OVERVIEW')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              subTab === 'OVERVIEW'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Network className="w-3.5 h-3.5" />
            <span>Kiến Trúc & Trạng Thái Live</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {subTab === 'RESEARCH' ? (
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left Sidebar: Report List */}
          <div className="w-full md:w-80 lg:w-96 border-r border-slate-800 flex flex-col bg-slate-900/40 shrink-0 h-1/2 md:h-full">
            {/* Filter & Search */}
            <div className="p-3 border-b border-slate-800 space-y-2 bg-slate-900/60">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm kiếm nghiên cứu, mô hình, mã..."
                className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-[11px] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500/50"
              />
              <div className="flex flex-wrap gap-1 max-h-16 overflow-y-auto no-scrollbar pt-1">
                {allTags.map(tag => (
                  <button
                    key={tag}
                    onClick={() => setSelectedTag(tag)}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                      selectedTag === tag
                        ? 'bg-amber-500/30 text-amber-300 border border-amber-500/50'
                        : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Reports List */}
            <div className="flex-1 overflow-y-auto divide-y divide-slate-800/40 p-2 space-y-1.5">
              {filteredReports.map((report) => {
                const isSelected = report.id === selectedReportId;
                return (
                  <div
                    key={report.id}
                    onClick={() => setSelectedReportId(report.id)}
                    className={`p-2.5 rounded-lg border cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-slate-800/90 border-amber-500/50 shadow-md ring-1 ring-amber-500/20'
                        : 'bg-slate-950/60 border-slate-800/60 hover:bg-slate-850 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="text-[10px] font-mono text-cyan-400 font-semibold">{report.code}</span>
                      <span className={`text-[9px] px-1.5 py-0.2 rounded border font-medium ${getBadgeColor(report.badge_color)}`}>
                        {report.badge}
                      </span>
                    </div>
                    <h3 className={`text-xs font-semibold line-clamp-2 mb-1.5 ${isSelected ? 'text-amber-300' : 'text-slate-200'}`}>
                      {report.title}
                    </h3>
                    <p className="text-[10px] text-slate-400 line-clamp-2 mb-2 leading-relaxed">
                      {report.abstract}
                    </p>
                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-800/40">
                      <div className="flex items-center gap-1 font-mono text-emerald-400 font-medium">
                        <span>{report.key_metric}</span>
                      </div>
                      <span className="text-slate-400 text-[9px]">{report.date}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Main Area: Full Paper Markdown Reader */}
          <div className="flex-1 flex flex-col h-1/2 md:h-full bg-slate-950 overflow-hidden">
            {/* Paper Toolbar */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800 bg-slate-900/70 shrink-0">
              <div className="flex items-center gap-2 overflow-hidden">
                <FileText className="w-4 h-4 text-amber-400 shrink-0" />
                <span className="text-xs font-bold text-slate-200 truncate">{selectedReport?.title}</span>
                <span className="text-[10px] font-mono text-slate-400 shrink-0 hidden sm:inline">({selectedReport?.code})</span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={handleCopyMarkdown}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] border border-slate-700 transition-colors"
                  title="Sao chép Markdown vào bộ nhớ tạm"
                >
                  {copied ? <CheckCheck className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? 'Đã chép' : 'Chép MD'}</span>
                </button>
                <button
                  onClick={handleDownloadMarkdown}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-[11px] border border-amber-500/40 transition-colors"
                  title="Tải về file tài liệu Markdown (.md)"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Tải .md</span>
                </button>
              </div>
            </div>

            {/* Paper Header Metadata Card */}
            <div className="bg-slate-900/40 border-b border-slate-800 px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] shrink-0">
              <div className="flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Ngày công bố</div>
                  <div className="font-mono text-slate-200">{selectedReport?.date}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Database className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Quy mô mẫu</div>
                  <div className="text-slate-200 font-medium truncate">{selectedReport?.sample_size}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Kết quả cốt lõi</div>
                  <div className="text-emerald-400 font-bold truncate">{selectedReport?.key_metric}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Users className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                <div>
                  <div className="text-[9px] text-slate-400 uppercase">Phân loại</div>
                  <div className="font-mono text-cyan-300">{selectedReport?.category}</div>
                </div>
              </div>
            </div>

            {/* Document Content */}
            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
              <MarkdownRenderer content={selectedReport?.content || ''} />
            </div>
          </div>
        </div>
      ) : (
        /* Overview Sub-tab */
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Section 1: Kiến Trúc Hệ Thống */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-4">
                <Network className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase">1. Kiến Trúc Đánh Giá 3 Động Cơ</h3>
              </div>
              <div className="space-y-4 text-[11px]">
                <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-amber-400">V1 Heuristic Engine (Giải thích trực quan)</span>
                    <span className="text-[9px] px-1.5 py-0.5 bg-slate-800 rounded text-slate-400">distribution_scorer.py</span>
                  </div>
                  <p className="text-slate-400 mb-2">Hệ thống trọng số 8 thành phần để người dùng quan sát lý do thị trường:</p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-300">
                    <li><span className="text-cyan-300">20%</span> Khúc xạ giá/khối lượng (Price-Volume Divergence)</li>
                    <li><span className="text-cyan-300">15%</span> Đột biến Funding Rate (Funding Spike)</li>
                    <li><span className="text-cyan-300">15%</span> Cạn kiệt xung lượng (Momentum Exhaustion)</li>
                    <li><span className="text-cyan-300">15%</span> Bối cảnh thị trường BTC (BTC Context Filter)</li>
                    <li><span className="text-slate-400">35%</span> Orderbook, Taker Sell, Open Interest, Fake Breakout</li>
                  </ul>
                </div>
                
                <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-emerald-400">V2 Two-Tier Climax</span>
                  </div>
                  <p className="text-slate-400 mb-1">Xác nhận tín hiệu qua 2 khung thời gian:</p>
                  <div className="flex flex-col space-y-1">
                    <div className="flex items-center space-x-2"><div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div><span><strong className="text-slate-300">HTF (High Timeframe):</strong> Trạng thái Armed / Normal</span></div>
                    <div className="flex items-center space-x-2"><div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div><span><strong className="text-slate-300">LTF (Low Timeframe):</strong> Kích hoạt Fired / Watch / Standby</span></div>
                  </div>
                </div>

                <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-purple-400">Frozen ML Pipeline (Bộ lọc quyết định bắn tín hiệu)</span>
                  </div>
                  <p className="text-slate-400">Pipeline học máy cô lập trạng thái với LightGBM / Logistic Regression. Sử dụng <strong>Isotonic Calibration</strong> để hiệu chuẩn xác suất đầu ra đạt ECE &lt; 0.03.</p>
                </div>
              </div>
            </div>

            {/* Section 2: Models Đang Dùng */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-4">
                <Settings className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase">2. Trạng Thái Mô Hình Đang Chạy</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px] whitespace-nowrap">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-500 uppercase">
                      <th className="pb-2 font-medium">Vai trò</th>
                      <th className="pb-2 font-medium">Mô hình</th>
                      <th className="pb-2 font-medium">Precision</th>
                      <th className="pb-2 font-medium">Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-amber-400 font-medium">Champion</span></td>
                      <td className="py-2">LogisticRegression (25 features)</td>
                      <td className="py-2 font-mono text-cyan-300">27.84% (Mega-Cap)</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900/50">Active</span></td>
                    </tr>
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-purple-400 font-medium">Meta-labeling</span></td>
                      <td className="py-2">HistGradientBoosting</td>
                      <td className="py-2 font-mono text-slate-400">Gác cổng lọc nhiễu</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900/50">Active</span></td>
                    </tr>
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-blue-400 font-medium">Regime Gate</span></td>
                      <td className="py-2">ADX + BB + EMA (BTC 5m)</td>
                      <td className="py-2 font-mono text-cyan-300">Triệt 23% nhiễu</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900/50">Active</span></td>
                    </tr>
                    <tr className="text-slate-300">
                      <td className="py-2"><span className="text-emerald-400 font-medium">Challenger</span></td>
                      <td className="py-2">LightGBM + Isotonic</td>
                      <td className="py-2 font-mono text-emerald-300 font-bold">20.93% (Altcoins)</td>
                      <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800">Benchmark Ready</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 3: Regime Gate */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-4">
                <Shield className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase">3. Bộ Lọc Chế Độ Thị Trường (Regime Gate)</h3>
              </div>
              <p className="text-[11px] text-slate-400 mb-3">Phân loại cấu trúc thị trường để chỉ phát cảnh báo trong môi trường thuận lợi:</p>
              <div className="grid grid-cols-2 gap-3 text-[11px]">
                <div className="bg-slate-950 p-2.5 rounded border border-emerald-900/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-emerald-400">SIDEWAY_DISTRIBUTION</span>
                    <Check className="w-3 h-3 text-emerald-400" />
                  </div>
                  <p className="text-slate-400 mb-1">Thị trường đi ngang/phân phối. Hiệu quả cao nhất.</p>
                  <div className="text-cyan-300 font-bold">Precision: 23.8% - 31.0%</div>
                </div>
                
                <div className="bg-slate-950 p-2.5 rounded border border-amber-900/50">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-amber-400">TRENDING_BEAR</span>
                    <Check className="w-3 h-3 text-emerald-400" />
                  </div>
                  <p className="text-slate-400 mb-1">Xu hướng giảm. Vẫn tìm được phân kỳ phục hồi.</p>
                  <div className="text-cyan-300 font-bold">Precision: 16.3%</div>
                </div>

                <div className="bg-slate-950 p-2.5 rounded border border-red-900/50 opacity-70">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-red-400">TRENDING_BULL</span>
                    <X className="w-3 h-3 text-red-400" />
                  </div>
                  <p className="text-slate-400">Xu hướng tăng mạnh. Ngăn chặn bắt đỉnh sớm.</p>
                </div>

                <div className="bg-slate-950 p-2.5 rounded border border-red-900/50 opacity-70">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-red-400">HIGH_VOLATILITY</span>
                    <X className="w-3 h-3 text-red-400" />
                  </div>
                  <p className="text-slate-400">Nhiễu động lớn, spread quét râu. Chặn tín hiệu.</p>
                </div>
              </div>
            </div>

            {/* Section 4: Feature Importance */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                  <BarChart3 className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-xs font-bold text-slate-200 uppercase">4. Độ Quan Trọng Đặc Trưng (Information Gain)</h3>
                </div>
                <span className="text-[9px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400">LightGBM (210 Coins)</span>
              </div>
              <div className="space-y-3 text-[11px]">
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">volatility_24h</span>
                    <span className="text-cyan-300 font-mono font-bold">536K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-400" style={{ width: '100%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">funding_rate_raw</span>
                    <span className="text-cyan-300 font-mono font-bold">296K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '55.2%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">top_acct_ratio</span>
                    <span className="text-cyan-300 font-mono font-bold">235K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '43.8%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">global_ls_ratio</span>
                    <span className="text-cyan-300 font-mono font-bold">218K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '40.6%' }}></div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-mono">return_24h</span>
                    <span className="text-cyan-300 font-mono font-bold">134K</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-cyan-400" style={{ width: '25%' }}></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Access to Research Archive Banner */}
          <div className="bg-gradient-to-r from-amber-500/10 via-slate-900 to-cyan-500/10 border border-amber-500/30 rounded-lg p-4 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center space-x-3">
              <BookOpen className="w-6 h-6 text-amber-400 shrink-0" />
              <div>
                <h4 className="text-xs font-bold text-slate-100 uppercase">Khám Phá Thư Viện Nghiên Cứu Định Lượng</h4>
                <p className="text-[11px] text-slate-400">Xem đầy đủ 5 báo cáo khoa học với bảng dữ liệu chi tiết, phân tích ROC-AUC và kết quả Walk-Forward.</p>
              </div>
            </div>
            <button
              onClick={() => setSubTab('RESEARCH')}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 rounded-lg border border-amber-500/50 text-xs font-semibold shrink-0 transition-colors"
            >
              <span>Xem Thư Viện Papers</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ModelsDocTab;
