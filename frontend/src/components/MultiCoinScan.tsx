import React, { useState, useEffect } from 'react';
import type { MultiCoinScanData, MultiCoinScanCoin } from '../types';
import { Search, BarChart3, FlaskConical, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { CoinLink } from './CoinLink';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation, type Language } from '../i18n/LanguageContext';

interface MultiCoinScanProps {
  onSelectCoin?: (symbol: string) => void;
}

export const MultiCoinScan: React.FC<MultiCoinScanProps> = ({ onSelectCoin }) => {
  const { language } = useTranslation();

  const getStatusMeta = (status: MultiCoinScanCoin['status'], lang: Language) => {
    const labels: Record<MultiCoinScanCoin['status'], Record<string, string>> = {
      edge: { vi: 'AI tốt hơn mốc', en: 'AI Edge Verified', zh: 'AI 优势已验证', ko: 'AI 우위 검증됨' },
      no_edge: { vi: 'AI chưa tốt hơn', en: 'No AI Edge', zh: '未显现优势', ko: '우위 미검증' },
      leak: { vi: 'Rò rỉ dữ liệu', en: 'Data Leakage', zh: '数据泄漏', ko: '데이터 누수' },
      no_data: { vi: 'Thiếu dữ liệu', en: 'Insufficient Data', zh: '数据不足', ko: '데이터 부족' },
      not_run: { vi: 'Chưa chạy', en: 'Not Evaluated', zh: '未评估', ko: '미평가' },
    };
    const colors: Record<MultiCoinScanCoin['status'], string> = {
      edge: 'text-emerald-400 bg-emerald-950 border-emerald-800',
      no_edge: 'text-amber-400 bg-amber-950 border-amber-800',
      leak: 'text-red-400 bg-red-950 border-red-800',
      no_data: 'text-slate-400 bg-slate-900 border-slate-700',
      not_run: 'text-slate-500 bg-slate-900 border-slate-800',
    };
    const icons: Record<MultiCoinScanCoin['status'], React.ReactNode> = {
      edge: <CheckCircle2 className="w-3 h-3" />,
      no_edge: <AlertTriangle className="w-3 h-3" />,
      leak: <XCircle className="w-3 h-3" />,
      no_data: <AlertTriangle className="w-3 h-3" />,
      not_run: <FlaskConical className="w-3 h-3" />,
    };
    return {
      label: labels[status]?.[lang] ?? labels[status]?.['en'] ?? status,
      color: colors[status] ?? 'text-slate-400 bg-slate-900 border-slate-700',
      icon: icons[status] ?? <FlaskConical className="w-3 h-3" />,
    };
  };

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
      setError(err instanceof Error ? err.message : (language === 'en' ? 'Failed to load data' : 'Lỗi tải dữ liệu'));
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
        <div className="text-xs text-slate-400 font-mono">
          {language === 'en' ? 'Loading multi-coin scan experiments...' : language === 'zh' ? '正在加载多币种扫描实验数据...' : language === 'ko' ? '다중 코인 스캔 실험 데이터 로드 중...' : 'Đang tải dữ liệu quét đa coin...'}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-3">
        <XCircle className="w-8 h-8 text-red-400" />
        <p className="text-xs text-red-400">{error}</p>
        <button onClick={fetchScan} className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded text-xs">
          {language === 'en' ? 'Retry' : language === 'zh' ? '重试' : language === 'ko' ? '다시 시도' : 'Thử lại'}
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

  const getHeaderTitle = () => {
    if (language === 'zh') return '多币种扫描 —— 机器学习与规则基准对比';
    if (language === 'ko') return '멀티 코인 스캔 — AI vs 휴리스틱 기준선';
    if (language === 'en') return 'MULTI-COIN SCAN — ML VS HEURISTIC BASELINES';
    return 'QUÉT NHIỀU COIN — AI SO VỚI MỐC CHUẨN';
  };

  const getHeaderSubtitle = () => {
    if (language === 'zh') return '扫描高波动币种池 → 90天全量数据收集 → 派发暴跌事件标注 (24小时内回撤 ≥8%) → 滚动时序前向回测验证。';
    if (language === 'ko') return '변동성 코인 유니버스 스캔 → 90일 데이터 수집 → 분산 덤프 이벤트 라벨링 (24시간 내 ≥8% 하락) → 시계열 전진 검증.';
    if (language === 'en') return 'Scanning volatile coin universe → 90-day data collection → distribution event labeling (drawdown ≥8% in 24h) → walk-forward ML vs baselines.';
    return 'Quét nhóm coin biến động mạnh → thu thập 90 ngày → đếm sự kiện xả → chạy AI → so sánh với mốc chuẩn. Tiêu chí xả: giá giảm ≥8% trong 24h, không tăng quá 4% trước khi giảm.';
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
          <FlaskConical className="w-3.5 h-3.5 text-amber-400" />
          {getHeaderTitle()}
        </h3>
        <div className="flex gap-2">
          <span className="text-[11px] text-slate-400">
            {data.n_artifacts} {language === 'en' ? 'experiments' : language === 'zh' ? '个实验' : language === 'ko' ? '개 실험' : 'thử nghiệm'} · {data.n_runs} {language === 'en' ? 'scan runs' : language === 'zh' ? '轮扫描' : language === 'ko' ? '회 스캔' : 'lần quét'}
          </span>
          <button onClick={fetchScan} className="px-2 py-0.5 text-[10px] text-amber-400 border border-amber-500/30 rounded hover:bg-amber-500/10">
            🔄 {language === 'en' ? 'Reload' : language === 'zh' ? '重新加载' : language === 'ko' ? '새로고침' : 'Tải lại'}
          </button>
        </div>
      </div>
      <p className="text-[11px] text-slate-400 -mt-2">
        {getHeaderSubtitle()}
      </p>

      {!data.has_db && (
        <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-400">
          ⬜ {language === 'en' ? 'Database scan_volatile.duckdb not found. Trigger multi-coin scan to generate empirical records.' : language === 'zh' ? '未找到数据库 scan_volatile.duckdb。运行多币种扫描以生成实证记录。' : language === 'ko' ? 'scan_volatile.duckdb 데이터베이스가 없습니다. 다중 코인 스캔을 실행하여 실증 데이터를 생성하세요.' : 'Chưa có cơ sở dữ liệu scan_volatile.duckdb. Chạy quét đa coin từ ứng dụng hoặc CLI để tạo dữ liệu.'}
        </div>
      )}

      {/* Edge coins highlight */}
      {edgeCoins.length > 0 && (
        <div className="p-3 bg-emerald-950/40 border border-emerald-800/50 rounded-lg">
          <p className="text-xs text-emerald-300">
            🟢 <strong>{edgeCoins.length} {language === 'en' ? 'symbols with proven ML edge' : language === 'zh' ? '个已验证具有 AI 优势的币种' : language === 'ko' ? '개 코인에서 AI 우위 검증됨' : 'coin: AI tốt hơn mốc'}</strong>: {' '}
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
            <BarChart3 className="w-3.5 h-3.5 text-amber-400" /> {language === 'en' ? 'HISTORICAL SCAN RUNS' : language === 'zh' ? '历史扫描批次记录' : language === 'ko' ? '스캔 실행 이력' : 'LỊCH SỬ CÁC LẦN QUÉT'}
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-slate-400 font-mono text-[10px] uppercase border-b border-slate-800">
                <tr>
                  <th className="p-2">{language === 'en' ? 'Run Time' : language === 'zh' ? '扫描时间' : language === 'ko' ? '스캔 시간' : 'Lần quét'}</th>
                  <th className="p-2">{language === 'en' ? 'Symbols' : language === 'zh' ? '覆盖币种' : language === 'ko' ? '코인 수' : 'Số coin'}</th>
                  <th className="p-2">{language === 'en' ? 'Valid' : language === 'zh' ? '有效样本' : language === 'ko' ? '유효' : 'Hợp lệ'}</th>
                  <th className="p-2">{language === 'en' ? 'ML Edge' : language === 'zh' ? 'AI 占优' : language === 'ko' ? 'AI 우위' : 'AI tốt hơn mốc'}</th>
                  <th className="p-2">{language === 'en' ? 'Top Performer' : language === 'zh' ? '最佳表现' : language === 'ko' ? '최고 성과 코인' : 'Coin tốt nhất'}</th>
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
          <h4 className="text-xs font-bold text-slate-200">
            🪙 {language === 'en' ? `SCANNED ASSETS LIST (${filteredCoins.length})` : language === 'zh' ? `已扫描资产列表 (${filteredCoins.length})` : language === 'ko' ? `스캔된 자산 목록 (${filteredCoins.length})` : `DANH SÁCH COIN ĐÃ QUÉT (${filteredCoins.length})`}
          </h4>
          <div className="flex gap-2 items-center">
            <div className="relative">
              <Search className="w-3 h-3 text-slate-500 absolute left-2 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder={language === 'en' ? 'Search coin...' : language === 'zh' ? '搜索币种...' : language === 'ko' ? '코인 검색...' : 'Tìm coin...'}
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
              <option value="ALL">{language === 'en' ? 'All Statuses' : language === 'zh' ? '所有状态' : language === 'ko' ? '모든 상태' : 'Tất cả trạng thái'}</option>
              <option value="edge">{getStatusMeta('edge', language).label}</option>
              <option value="no_edge">{getStatusMeta('no_edge', language).label}</option>
              <option value="leak">{getStatusMeta('leak', language).label}</option>
              <option value="no_data">{getStatusMeta('no_data', language).label}</option>
              <option value="not_run">{getStatusMeta('not_run', language).label}</option>
            </select>
          </div>
        </div>

        {filteredCoins.length === 0 ? (
          <p className="text-xs text-slate-500 p-4 text-center">{language === 'en' ? 'No symbols match filter.' : language === 'zh' ? '无匹配币种。' : language === 'ko' ? '일치하는 코인이 없습니다.' : 'Không có coin nào khớp.'}</p>
        ) : (
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-slate-400 font-mono text-[10px] uppercase border-b border-slate-800 sticky top-0 bg-slate-950">
                <tr>
                  <th className="p-2">{language === 'en' ? 'Coin' : language === 'zh' ? '交易对' : language === 'ko' ? '페어' : 'Coin'}</th>
                  <th className="p-2">{language === 'en' ? 'Status' : language === 'zh' ? '状态' : language === 'ko' ? '상태' : 'Trạng thái'}</th>
                  <th className="p-2">{language === 'en' ? 'Dump Events' : language === 'zh' ? '暴跌事件' : language === 'ko' ? '덤프 이벤트' : 'Sự kiện xả'}</th>
                  <th className="p-2">{language === 'en' ? 'Prevalence' : language === 'zh' ? '发生率' : language === 'ko' ? '발생 빈도' : 'Tần suất'}</th>
                  <th className="p-2">{language === 'en' ? 'AI Precision' : language === 'zh' ? 'AI 精准率' : language === 'ko' ? 'AI 정밀도' : 'Độ chính xác AI'}</th>
                  <th className="p-2">{language === 'en' ? 'Best Baseline' : language === 'zh' ? '最佳基准' : language === 'ko' ? '최고 기준선' : 'Mốc tốt nhất'}</th>
                  <th className="p-2">{language === 'en' ? '95% CI' : language === 'zh' ? '95% 置信区间' : language === 'ko' ? '95% 신뢰구간' : 'Khoảng tin cậy 95%'}</th>
                  <th className="p-2">{language === 'en' ? 'Valid Folds' : language === 'zh' ? '有效折数' : language === 'ko' ? '유효 폴드' : 'Hợp lệ'}</th>
                  <th className="p-2">{language === 'en' ? 'Leakage' : language === 'zh' ? '泄漏审计' : language === 'ko' ? '누수 검증' : 'Rò rỉ'}</th>
                  <th className="p-2">{language === 'en' ? 'Runs' : language === 'zh' ? '扫描轮数' : language === 'ko' ? '스캔 횟수' : 'Lần quét'}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {filteredCoins.map((c, i) => {
                  const meta = getStatusMeta(c.status, language);
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
