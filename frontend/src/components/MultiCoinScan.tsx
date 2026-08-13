import React, { useState, useEffect } from 'react';
import type { MultiCoinScanData, MultiCoinScanCoin } from '../types';
import { Search, BarChart3, FlaskConical, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { CoinLink } from './CoinLink';
import { formatSystemDateTime } from '../utils/time';

const STATUS_META: Record<MultiCoinScanCoin['status'], { label: string; color: string; icon: React.ReactNode }> = {
  edge: { label: 'AI tốt hơn mốc', color: 'text-emerald-400 bg-emerald-950 border-emerald-800', icon: <CheckCircle2 className="w-3 h-3" /> },
  no_edge: { label: 'AI chưa tốt hơn', color: 'text-amber-400 bg-amber-950 border-amber-800', icon: <AlertTriangle className="w-3 h-3" /> },
  leak: { label: 'Rò rỉ dữ liệu', color: 'text-red-400 bg-red-950 border-red-800', icon: <XCircle className="w-3 h-3" /> },
  no_data: { label: 'Thiếu dữ liệu', color: 'text-slate-400 bg-slate-900 border-slate-700', icon: <AlertTriangle className="w-3 h-3" /> },
  not_run: { label: 'Chưa chạy', color: 'text-slate-500 bg-slate-900 border-slate-800', icon: <FlaskConical className="w-3 h-3" /> },
};

interface MultiCoinScanProps {
  onSelectCoin?: (symbol: string) => void;
}

export const MultiCoinScan: React.FC<MultiCoinScanProps> = ({ onSelectCoin }) => {
  const [data, setData] = useState<MultiCoinScanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  const fetchScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/scan/multi-coin');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lỗi tải dữ liệu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScan();
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-xs text-slate-400 font-mono">Đang tải dữ liệu quét đa coin...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-3">
        <XCircle className="w-8 h-8 text-red-400" />
        <p className="text-xs text-red-400">{error}</p>
        <button onClick={fetchScan} className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-xs">
          Thử lại
        </button>
      </div>
    );
  }

  if (!data) return null;

  const edgeCoins = data.coin_list.filter(c => c.status === 'edge');

  const filteredCoins = data.coin_list.filter(c => {
    const matchesSearch = c.symbol.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'ALL' || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <FlaskConical className="w-3.5 h-3.5 text-amber-400" />
          QUÉT NHIỀU COIN — AI SO VỚI MỐC CHUẨN
        </h3>
        <div className="flex gap-2">
          <span className="text-[11px] text-slate-400">{data.n_artifacts} thử nghiệm · {data.n_runs} lần quét</span>
          <button onClick={fetchScan} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10">
            🔄 Tải lại
          </button>
        </div>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        Quét nhóm coin biến động mạnh → thu thập 90 ngày → đếm sự kiện xả → chạy AI → so sánh với mốc chuẩn.
        Tiêu chí xả: giá giảm ≥8% trong 24h, không tăng quá 4% trước khi giảm.
      </p>

      {!data.has_db && (
        <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400">
          ⬜ Chưa có cơ sở dữ liệu scan_volatile.duckdb. Chạy quét đa coin từ ứng dụng hoặc CLI để tạo dữ liệu.
        </div>
      )}

      {/* Edge coins highlight */}
      {edgeCoins.length > 0 && (
        <div className="p-3 bg-emerald-950/40 border border-emerald-800/50 rounded-lg">
          <p className="text-xs text-emerald-300">
            🟢 <strong>{edgeCoins.length} coin: AI tốt hơn mốc</strong>: {' '}
            {edgeCoins.map((c, i) => (
              <span key={c.symbol}>
                {onSelectCoin ? (
                  <CoinLink symbol={c.symbol} onClick={onSelectCoin} className="text-emerald-300 hover:text-emerald-200" />
                ) : (
                  <span className="font-mono font-bold">{c.symbol}</span>
                )}
                {i < edgeCoins.length - 1 ? ', ' : ''}
              </span>
            ))}
          </p>
        </div>
      )}

      {/* Run history */}
      {data.run_history.length > 0 && (
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
          <h4 className="text-xs font-bold text-slate-200 mb-2 flex items-center gap-1.5">
            <BarChart3 className="w-3.5 h-3.5 text-amber-400" /> LỊCH SỬ CÁC LẦN QUÉT
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-slate-400 font-mono text-[10px] uppercase border-b border-slate-800">
                <tr>
                  <th className="p-2">Lần quét</th>
                  <th className="p-2">Số coin</th>
                  <th className="p-2">Hợp lệ</th>
                  <th className="p-2">AI tốt hơn mốc</th>
                  <th className="p-2">Coin tốt nhất</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {data.run_history.slice(0, 15).map((r, i) => (
                  <tr key={i} className="hover:bg-slate-900/60">
                    <td className="p-2">{formatSystemDateTime(r.run_time)}</td>
                    <td className="p-2">{r.n_coins}</td>
                    <td className="p-2">{r.n_valid}</td>
                    <td className="p-2">
                      <span className={r.n_edge > 0 ? 'text-emerald-400 font-bold' : 'text-slate-500'}>
                        {r.n_edge}
                      </span>
                    </td>
                    <td className="p-2">
                      {r.best_coin ? `${r.best_coin} (P=${(r.best_precision * 100).toFixed(1)}%)` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Coin list */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <div className="flex items-center justify-between mb-2.5">
          <h4 className="text-xs font-bold text-slate-200">🪙 DANH SÁCH COIN ĐÃ QUÉT ({filteredCoins.length})</h4>
          <div className="flex gap-2 items-center">
            <div className="relative">
              <Search className="w-3 h-3 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Tìm coin..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-7 pr-2 py-1 bg-slate-900 border border-slate-800 rounded text-[11px] text-slate-200 w-32 focus:outline-none focus:border-amber-500/50"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[11px] text-slate-200 focus:outline-none focus:border-amber-500/50"
            >
              <option value="ALL">Tất cả trạng thái</option>
              <option value="edge">AI tốt hơn mốc</option>
              <option value="no_edge">AI chưa tốt hơn</option>
              <option value="leak">Rò rỉ</option>
              <option value="no_data">Thiếu dữ liệu</option>
              <option value="not_run">Chưa chạy</option>
            </select>
          </div>
        </div>

        {filteredCoins.length === 0 ? (
          <p className="text-xs text-slate-500 p-4 text-center">Không có coin nào khớp.</p>
        ) : (
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-slate-400 font-mono text-[10px] uppercase border-b border-slate-800 sticky top-0 bg-slate-950">
                <tr>
                  <th className="p-2">Coin</th>
                  <th className="p-2">Trạng thái</th>
                  <th className="p-2">Sự kiện xả</th>
                  <th className="p-2">Tần suất</th>
                  <th className="p-2">Độ chính xác AI</th>
                  <th className="p-2">Mốc tốt nhất</th>
                  <th className="p-2">Khoảng tin cậy 95%</th>
                  <th className="p-2">Hợp lệ</th>
                  <th className="p-2">Rò rỉ</th>
                  <th className="p-2">Lần quét</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {filteredCoins.map((c, i) => {
                  const meta = STATUS_META[c.status];
                  return (
                    <tr key={i} className="hover:bg-slate-900/60">
                      <td className="p-2">
                        {onSelectCoin ? (
                          <CoinLink symbol={c.symbol} onClick={onSelectCoin} />
                        ) : (
                          <span className="font-mono font-bold text-white">{c.symbol}</span>
                        )}
                      </td>
                      <td className="p-2">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] border inline-flex items-center gap-1 ${meta.color}`}>
                          {meta.icon}
                          {meta.label}
                        </span>
                      </td>
                      <td className="p-2 text-amber-400">{c.pos}</td>
                      <td className="p-2 text-slate-400">{(c.prevalence * 100).toFixed(1)}%</td>
                      <td className="p-2">
                        <span className={c.precision > c.baseline && c.precision > 0 ? 'text-emerald-400 font-bold' : 'text-slate-400'}>
                          {c.precision > 0 ? `${(c.precision * 100).toFixed(1)}%` : '—'}
                        </span>
                      </td>
                      <td className="p-2 text-slate-400">
                        {c.baseline > 0 ? `${(c.baseline * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td className="p-2 text-slate-400 text-[10px]">
                        {c.n_valid_folds > 0 ? `[${(c.ci_lower * 100).toFixed(1)}%, ${(c.ci_upper * 100).toFixed(1)}%]` : '—'}
                      </td>
                      <td className="p-2 text-slate-400">{c.n_valid_folds}</td>
                      <td className="p-2">
                        {c.leakage === 'passed' ? <span className="text-emerald-400">✅</span> : <span className="text-red-400">❌</span>}
                      </td>
                      <td className="p-2 text-slate-400">{c.n_runs}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
