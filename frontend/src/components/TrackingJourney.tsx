import { useState } from 'react';
import type { TrackingWatchlistItem } from '../types';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';

const money = (n: number | null | undefined) => n == null || !Number.isFinite(n) ? '—' : `${n.toFixed(2)} USDT`;
const pct = (n: number | null | undefined) => n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
const button = 'rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:border-amber-500 disabled:opacity-40';
const input = 'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-100';

export function TrackingJourney({ item, onRefresh, onUpdate }: { item: TrackingWatchlistItem; onRefresh: () => void; onUpdate: (id: string, patch: Record<string, unknown>) => Promise<boolean> }) {
  const { language } = useTranslation();
  const vi = language === 'vi';
  const [side, setSide] = useState('SHORT');
  const [size, setSize] = useState('1000');
  const [fee, setFee] = useState('5');
  const [slippage, setSlippage] = useState('5');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const trade = item.paper_trade;
  const act = async (action: 'open' | 'close' | 'reconcile') => {
    setBusy(true); setError('');
    try {
      const res = await fetch(`/api/tracking-watchlist/${encodeURIComponent(item.id)}/paper`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, side, notional: Number(size), fee_bps: Number(fee), slippage_bps: Number(slippage) }),
      });
      if (!res.ok) throw new Error(vi ? 'Chưa thực hiện được. Cần giá mới dưới 2 phút và thông số hợp lệ; hãy làm mới rồi thử lại.' : 'Unable to continue. A price under two minutes old and valid parameters are required. Refresh and retry.');
      onRefresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Request failed'); }
    finally { setBusy(false); }
  };
  return <section className="mt-3 space-y-3 border-t border-slate-800 pt-3" aria-label={vi ? 'Kết quả và giả lập' : 'Outcomes and simulation'}>
    <div className="text-xs leading-relaxed text-slate-400">
      <span className="font-semibold text-amber-200">{item.source_shadow_mode ? (vi ? 'Dự báo thử nghiệm' : 'Experimental forecast') : (vi ? 'Quan sát thị trường' : 'Market observation')}</span>
      {' · '}{vi ? 'Mốc giá: ' : 'Price reference: '}{item.source_price_time ? formatSystemDateTime(item.source_price_time) : (vi ? 'Chưa xác minh' : 'Unverified')}
      {item.source_invalidation_time && <span className="block">{vi ? 'Nhận định hết hiệu lực lúc ' : 'Forecast expires at '}{formatSystemDateTime(item.source_invalidation_time)}{item.source_stop_price ? ` · ${vi ? 'Mức bất lợi của mô hình' : 'Model adverse limit'}: ${item.source_stop_price}` : ''}</span>}
      {item.source_model_id && <span className="block break-all">{vi ? 'Mô hình gốc: ' : 'Original model: '}{item.source_model_id} · {item.source_label_version}</span>}
      <span className="block">{vi ? 'Theo dõi nền lần cuối: ' : 'Last background check: '}{item.monitor_checked_at ? formatSystemDateTime(item.monitor_checked_at) : (vi ? 'Đang chờ lượt kiểm tra đầu tiên' : 'Waiting for the first check')}</span>
    </div>
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {[24, 48].map(hours => {
        const result = item.checkpoints?.[String(hours)];
        return <div key={hours} className="rounded-lg border border-slate-700 bg-slate-900/50 p-3" data-testid={`checkpoint-${hours}`}>
          <h4 className="text-xs font-bold text-slate-200">{vi ? `Sau ${hours} giờ` : `After ${hours} hours`}</h4>
          {result?.status === 'READY' ? <>
            <p className="mt-1 text-base font-semibold text-slate-100">{pct(result.return_pct)}</p>
            <p className="text-xs text-slate-400">{vi ? 'Giảm sâu nhất' : 'Maximum drop'} {pct(result.max_drop_pct)} · {vi ? 'Tăng cao nhất' : 'Maximum rise'} {pct(result.max_rise_pct)}</p>
            <p className="text-xs text-slate-500">{result.at && formatSystemDateTime(result.at)}</p>
          </> : <p className="mt-1 text-xs text-amber-200">{result?.status === 'MISSING' ? (vi ? 'Chưa đủ dữ liệu để đánh giá; hệ thống sẽ thử lại.' : 'Insufficient evidence; the system will retry.') : (vi ? 'Đang chờ đủ thời gian và dữ liệu.' : 'Waiting for the horizon and market data.')}</p>}
        </div>;
      })}
    </div>
    <p className="text-xs text-slate-500">{vi ? 'Biến động từ giá đóng nến 5 phút tại mốc lưu, không phải lợi nhuận giao dịch hay kết luận mô hình đúng/sai.' : 'Movement from the reference five-minute close, not trading returns or a model success verdict.'}</p>
    <div className="flex flex-wrap items-center gap-2">
      {!item.archived_at && <label className="flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" checked={item.notifications_enabled !== false} onChange={e => void onUpdate(item.id, { notifications_enabled: e.target.checked })} />{vi ? 'Thông báo trong ứng dụng' : 'In-app notifications'}</label>}
      {!!item.notifications?.some(n => !n.read) && <button className={button} onClick={() => void onUpdate(item.id, { read_notifications: true })}>{vi ? 'Đánh dấu đã đọc' : 'Mark as read'}</button>}
    </div>
    {!!item.notifications?.length && <ul className="space-y-1 text-xs" aria-label={vi ? 'Thông báo theo dõi' : 'Tracking notifications'}>
      {item.notifications.slice(-5).reverse().map(n => <li key={n.id} className={n.read ? 'text-slate-500' : 'text-amber-200'}>{formatSystemDateTime(n.at)} · {n.message}</li>)}
    </ul>}
    <details className="rounded-lg border border-sky-900 bg-sky-950/20 p-3" data-testid="paper-journal">
      <summary className="cursor-pointer text-sm font-semibold text-sky-200">{vi ? 'Thử bằng vốn giả lập' : 'Paper trading journal'}{trade ? ` · ${trade.status === 'OPEN' ? (vi ? 'Đang mở' : 'Open') : (vi ? 'Đã đóng' : 'Closed')}` : ''}</summary>
      <p className="my-2 text-xs text-slate-400">{vi ? 'Mô phỏng giá và chi phí, không đặt lệnh thật, không dùng đòn bẩy. Chưa mô phỏng thanh lý, khả năng khớp lệnh hoặc độ sâu thị trường. Phí và trượt giá là giả định; funding lấy từ lịch sử khi đóng.' : 'Price and cost simulation only: no real orders or leverage. Liquidation, fills and market depth are not simulated. Fees and slippage are assumptions; funding is read from history at close.'}</p>
      {!trade && !item.archived_at && <form onSubmit={e => { e.preventDefault(); void act('open'); }}>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <label className="text-xs text-slate-400">{vi ? 'Hướng giả lập' : 'Side'}<select className={input} value={side} onChange={e => setSide(e.target.value)}><option>SHORT</option><option>LONG</option></select></label>
          <label className="text-xs text-slate-400">{vi ? 'Quy mô (USDT)' : 'Size (USDT)'}<input className={input} required type="number" min="1" max="1000000" value={size} onChange={e => setSize(e.target.value)} /></label>
          <label className="text-xs text-slate-400">{vi ? 'Phí mỗi chiều (bps)' : 'Fee per side (bps)'}<input className={input} required type="number" min="0" max="100" step="0.1" value={fee} onChange={e => setFee(e.target.value)} /></label>
          <label className="text-xs text-slate-400">{vi ? 'Trượt giá mỗi chiều (bps)' : 'Slippage per side (bps)'}<input className={input} required type="number" min="0" max="100" step="0.1" value={slippage} onChange={e => setSlippage(e.target.value)} /></label>
        </div>
        <p className="my-2 text-xs text-slate-500">{vi ? '1 bps = 0,01%. Giá mở lấy từ thị trường khi bấm nút; không lấy giá tín hiệu trong quá khứ.' : '1 bps = 0.01%. Entry uses the market price when you submit, not a historical signal price.'}</p>
        <button className={button} disabled={busy} type="submit">{busy ? '…' : vi ? 'Mở giả lập' : 'Open paper trade'}</button>
      </form>}
      {trade && <div className="space-y-2 text-xs text-slate-300">
        <p>{trade.side} · {money(trade.notional)} · {vi ? 'Giá mở' : 'Entry'} {trade.entry_price.toPrecision(7)} · {formatSystemDateTime(trade.opened_at)}</p>
        <p>{vi ? 'Giả định mỗi chiều: phí' : 'Per-side assumptions: fee'} {trade.fee_bps} bps · {vi ? 'trượt giá' : 'slippage'} {trade.slippage_bps} bps</p>
        {trade.status === 'OPEN' ? <><p>{vi ? 'Funding và lãi/lỗ ròng sẽ được đối chiếu khi đóng giả lập.' : 'Funding and net P&L are reconciled on close.'}</p><button className={button} disabled={busy} onClick={() => void act('close')}>{busy ? '…' : vi ? 'Đóng giả lập theo giá mới' : 'Close at current price'}</button></> : <>
          <p>{vi ? 'Giá đóng' : 'Exit'} {trade.exit_price?.toPrecision(7)} · {trade.closed_at && formatSystemDateTime(trade.closed_at)}</p>
          <p>{vi ? 'Lãi/lỗ giá (đã tính trượt giá)' : 'Price P&L (including slippage)'}: {money(trade.gross_pnl)} · {vi ? 'Tổng phí' : 'Fees'}: {money(trade.fees)}</p>
          <p>Funding: {money(trade.funding.cashflow)}{trade.funding.status !== 'VERIFIED' ? (vi ? ' · Chưa đủ dữ liệu, chưa công bố lãi/lỗ ròng.' : ' · Unverified; net P&L is withheld.') : ` · ${trade.funding.settlements ?? 0} ${vi ? 'kỳ ghi nhận' : 'settlements'}`}</p>
          <p className="text-sm font-bold text-sky-200">{vi ? 'Lãi/lỗ ròng giả lập' : 'Paper net P&L'}: {money(trade.net_pnl)}</p>
          {trade.funding.status !== 'VERIFIED' && <button className={button} disabled={busy} onClick={() => void act('reconcile')}>{vi ? 'Đối chiếu lại funding' : 'Retry funding reconciliation'}</button>}
        </>}
      </div>}
      {error && <p role="alert" className="mt-2 text-xs text-red-300">{error}</p>}
    </details>
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
      <span>{vi ? 'Cảnh báo này có ích không?' : 'Was this observation useful?'}</span>
      {(['USEFUL', 'NOISY', 'UNCLEAR'] as const).map((value, i) => <button key={value} aria-pressed={item.feedback === value} className={`${button} ${item.feedback === value ? 'bg-amber-900/50 border-amber-500' : ''}`} onClick={() => void onUpdate(item.id, { feedback: value })}>{(vi ? ['Hữu ích', 'Gây phiền', 'Khó hiểu'] : ['Useful', 'Noisy', 'Unclear'])[i]}</button>)}
    </div>
  </section>;
}
