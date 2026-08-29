import React from 'react';
import { 
  Brain, Shield, BarChart3, History, Network, Settings, Check, X, AlertTriangle
} from 'lucide-react';
const ModelsDocTab: React.FC = () => {
  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 text-slate-300">
      <div className="flex items-center space-x-3 border-b border-slate-800 pb-4">
        <div className="p-2 bg-slate-800 rounded-lg">
          <Brain className="w-6 h-6 text-amber-400" />
        </div>
        <div>
          <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Tài Liệu Models & Kiến Trúc Đánh Giá</h2>
          <p className="text-[11px] text-slate-400 mt-1">
            Mô tả chi tiết các models, pipeline học máy, các quy tắc heuritsic và lịch sử đánh giá chiến lược.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Section 1: Kiến Trúc Hệ Thống */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <Network className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-slate-200 uppercase">1. Kiến Trúc Đánh Giá</h3>
          </div>
          <div className="space-y-4 text-[11px]">
            <div className="bg-slate-950 p-3 rounded border border-slate-800/50">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-amber-400">V1 Heuristic Engine</span>
                <span className="text-[9px] px-1.5 py-0.5 bg-slate-800 rounded text-slate-400">distribution_scorer.py</span>
              </div>
              <p className="text-slate-400 mb-2">Hệ thống trọng số 9 thành phần dựa trên quy tắc chuyên gia:</p>
              <ul className="list-disc pl-4 space-y-1 text-slate-300">
                <li><span className="text-cyan-300">20%</span> Khúc xạ giá/khối lượng (Price-Volume Divergence)</li>
                <li><span className="text-cyan-300">15%</span> Đột biến Funding Rate (Funding Spike)</li>
                <li><span className="text-cyan-300">15%</span> Cạn kiệt xung lượng (Momentum Exhaustion)</li>
                <li><span className="text-slate-500">50%</span> 6 thành phần khác (Orderbook, Liquidation, Open Interest...)</li>
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
                <span className="font-semibold text-purple-400">Frozen ML Pipeline</span>
              </div>
              <p className="text-slate-400">Pipeline học máy cô lập trạng thái với LightGBM / Logistic Regression. Sử dụng <strong>Isotonic Calibration</strong> để hiệu chuẩn xác suất đầu ra chính xác.</p>
            </div>
          </div>
        </div>

        {/* Section 2: Models Đang Dùng */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <Settings className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-slate-200 uppercase">2. Models Trạng Thái</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px] whitespace-nowrap">
              <thead>
                <tr className="border-b border-slate-800 text-slate-500 uppercase">
                  <th className="pb-2 font-medium">Vai trò</th>
                  <th className="pb-2 font-medium">Mô hình</th>
                  <th className="pb-2 font-medium">Artifact</th>
                  <th className="pb-2 font-medium">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                <tr className="text-slate-300">
                  <td className="py-2"><span className="text-amber-400 font-medium">Champion</span></td>
                  <td className="py-2">LogisticRegression (25 features)</td>
                  <td className="py-2 font-mono text-[10px] text-slate-400">frozen_20260811</td>
                  <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900/50">Active</span></td>
                </tr>
                <tr className="text-slate-300">
                  <td className="py-2"><span className="text-purple-400 font-medium">Meta-labeling</span></td>
                  <td className="py-2">HistGradientBoosting</td>
                  <td className="py-2 font-mono text-[10px] text-slate-400">meta_model.joblib</td>
                  <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900/50">Active</span></td>
                </tr>
                <tr className="text-slate-300">
                  <td className="py-2"><span className="text-blue-400 font-medium">Regime Gate</span></td>
                  <td className="py-2">ADX + BB + EMA</td>
                  <td className="py-2 font-mono text-[10px] text-slate-400">Built-in</td>
                  <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900/50">Active</span></td>
                </tr>
                <tr className="text-slate-300">
                  <td className="py-2"><span className="text-slate-400 font-medium">Challenger</span></td>
                  <td className="py-2">LightGBM + Isotonic</td>
                  <td className="py-2 font-mono text-[10px] text-slate-400">-</td>
                  <td className="py-2"><span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">Testing</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Section 3: Regime Gate (MỚI) */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <Shield className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold text-slate-200 uppercase">3. Bộ Lọc Môi Trường (Regime Gate)</h3>
          </div>
          <p className="text-[11px] text-slate-400 mb-3">Phân loại cấu trúc thị trường để lọc bỏ tín hiệu nhiễu (Dựa trên ADX, Bollinger Bands, EMA):</p>
          <div className="grid grid-cols-2 gap-3 text-[11px]">
            <div className="bg-slate-950 p-2.5 rounded border border-emerald-900/50">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-emerald-400">SIDEWAY_DISTRIBUTION</span>
                <Check className="w-3 h-3 text-emerald-400" />
              </div>
              <p className="text-slate-500 mb-1">Thị trường đi ngang/phân phối. Hiệu quả cao nhất.</p>
              <div className="text-cyan-300">Precision: 31% - 23.8%</div>
            </div>
            
            <div className="bg-slate-950 p-2.5 rounded border border-amber-900/50">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-amber-400">TRENDING_BEAR</span>
                <Check className="w-3 h-3 text-emerald-400" />
              </div>
              <p className="text-slate-500 mb-1">Xu hướng giảm. Vẫn tìm được phân kỳ.</p>
              <div className="text-cyan-300">Precision: 16.3%</div>
            </div>

            <div className="bg-slate-950 p-2.5 rounded border border-red-900/50 opacity-70">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-red-400">TRENDING_BULL</span>
                <X className="w-3 h-3 text-red-400" />
              </div>
              <p className="text-slate-500">Xu hướng tăng mạnh. Rủi ro fomo, chặn tín hiệu.</p>
            </div>

            <div className="bg-slate-950 p-2.5 rounded border border-red-900/50 opacity-70">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-red-400">HIGH_VOLATILITY</span>
                <X className="w-3 h-3 text-red-400" />
              </div>
              <p className="text-slate-500">Nhiễu động lớn, spread cao. Chặn tín hiệu.</p>
            </div>
          </div>
        </div>

        {/* Section 5: Feature Importance */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <BarChart3 className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-slate-200 uppercase">4. Độ Quan Trọng Đặc Trưng</h3>
            </div>
            <span className="text-[9px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400">LightGBM Gain</span>
          </div>
          <div className="space-y-3 text-[11px]">
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300 font-mono">volatility_24h</span>
                <span className="text-cyan-300">536K</span>
              </div>
              <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-amber-400" style={{ width: '100%' }}></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300 font-mono">funding_rate_raw</span>
                <span className="text-cyan-300">296K</span>
              </div>
              <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-cyan-400" style={{ width: '55.2%' }}></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300 font-mono">top_acct_ratio</span>
                <span className="text-cyan-300">235K</span>
              </div>
              <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-cyan-400" style={{ width: '43.8%' }}></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300 font-mono">global_ls_ratio</span>
                <span className="text-cyan-300">218K</span>
              </div>
              <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-cyan-400" style={{ width: '40.6%' }}></div>
              </div>
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-slate-300 font-mono">return_24h</span>
                <span className="text-cyan-300">134K</span>
              </div>
              <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-cyan-400" style={{ width: '25%' }}></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Section 4: Lịch Sử Đánh Giá & Cải Tiến */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center space-x-2 mb-4">
          <History className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold text-slate-200 uppercase">5. Lịch Sử Cải Tiến & Đánh Giá</h3>
        </div>
        <div className="space-y-4">
          
          <div className="border-l-2 border-slate-700 pl-4 pb-2 relative">
            <div className="absolute w-3 h-3 bg-amber-400 rounded-full -left-[7px] top-1 border-2 border-slate-900"></div>
            <div className="text-[10px] text-amber-400 font-semibold mb-1">30/08/2026</div>
            <h4 className="text-xs font-bold text-slate-200 mb-2">Thí Nghiệm 8 Chiến Lược (210 coins, 1 năm)</h4>
            <ul className="list-disc pl-4 space-y-1 text-[11px] text-slate-400">
              <li><strong className="text-emerald-400">Best:</strong> Regime + LGB p98 đạt <span className="text-cyan-300">20.83% precision</span></li>
              <li>Ensemble LGB+LogReg: 16.93% (KHÔNG hiệu quả)</li>
              <li>Tăng threshold p99/p99.5: Cắt giảm tín hiệu quá đáng kể, không mang lại cải thiện.</li>
              <li><strong className="text-amber-400">Quyết định:</strong> Triển khai Regime Gate, từ chối Ensemble.</li>
            </ul>
          </div>

          <div className="border-l-2 border-slate-700 pl-4 pb-2 relative">
            <div className="absolute w-3 h-3 bg-slate-600 rounded-full -left-[7px] top-1 border-2 border-slate-900"></div>
            <div className="text-[10px] text-slate-500 font-semibold mb-1">30/08/2026</div>
            <h4 className="text-xs font-bold text-slate-200 mb-2">Backtest Mid-Cap 210 Coins</h4>
            <ul className="list-disc pl-4 space-y-1 text-[11px] text-slate-400">
              <li>Dữ liệu: 210 altcoins, 1 năm, 1.35M rows</li>
              <li>LightGBM: <span className="text-cyan-300">21.2%</span> | LogReg: <span className="text-slate-500">14.9%</span></li>
              <li>LightGBM vượt LogReg mạnh mẽ trên phân khúc mid-cap/low-cap.</li>
              <li>3/5 quality gates PASS.</li>
            </ul>
          </div>

          <div className="border-l-2 border-slate-700 pl-4 pb-2 relative">
            <div className="absolute w-3 h-3 bg-red-400 rounded-full -left-[7px] top-1 border-2 border-slate-900"></div>
            <div className="text-[10px] text-red-400 font-semibold mb-1">29/08/2026</div>
            <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center space-x-2">
              <span>Kiểm Định Toàn Diện (30 coins, 2.6 năm)</span>
              <AlertTriangle className="w-3 h-3 text-red-400" />
            </h4>
            <ul className="list-disc pl-4 space-y-1 text-[11px] text-slate-400">
              <li>Phát hiện 2 lỗi FAKE trong báo cáo agent cũ gây sai lệch performance.</li>
              <li>Kết quả thực tế sau khi sửa lỗi: LGB <span className="text-slate-500">16.2%</span>, LogReg <span className="text-cyan-300">27.8%</span></li>
              <li>Môi trường SIDEWAY_DISTRIBUTION đạt precision cao nhất: <span className="text-cyan-300">31%</span></li>
              <li><strong className="text-amber-400">Quyết định:</strong> Giữ LogReg là Champion cho mega-cap.</li>
            </ul>
          </div>

          <div className="border-l-2 border-slate-700 pl-4 pb-0 relative">
            <div className="absolute w-3 h-3 bg-cyan-400 rounded-full -left-[7px] top-1 border-2 border-slate-900"></div>
            <div className="text-[10px] text-cyan-400 font-semibold mb-1">29/08/2026</div>
            <h4 className="text-xs font-bold text-slate-200 mb-2">7 Cải Tiến Độ Chính Xác (Accuracy)</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] text-slate-400">
              <ul className="list-disc pl-4 space-y-1">
                <li>Parquet lookback 3d → 30d (Tránh null rolling windows)</li>
                <li>Zero-fill COALESCE → NULL (Để model tự quyết định dữ liệu thiếu)</li>
                <li>Meta-labeling chạy ở chế độ active</li>
                <li>Hiệu chuẩn: Sigmoid → Isotonic (ECE giảm 0.03 → 0.0004)</li>
              </ul>
              <ul className="list-disc pl-4 space-y-1">
                <li>Thêm features cạn kiệt đa khung thời gian (Multi-TF exhaustion)</li>
                <li>Khởi tạo LightGBM training pipeline</li>
                <li>Hỗ trợ Multi-horizon outcomes (Đánh giá đa khung thời gian sau tín hiệu)</li>
              </ul>
            </div>
          </div>

        </div>
      </div>
      
    </div>
  );
};

export default ModelsDocTab;
