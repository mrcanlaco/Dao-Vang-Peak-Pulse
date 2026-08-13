with open('frontend/src/components/MainWorkspace.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

chart_title_idx = code.find('BIỂU ĐỒ NẾN {candleInterval}')
title_start = code.rfind('<div className="flex items-center justify-between mb-2 gap-2 flex-wrap">', 0, chart_title_idx)

if title_start != -1:
    metrics_inline = """<div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 text-center"><div className="text-[10px] text-slate-400 uppercase mb-1">OI 24h</div><div className="font-mono font-bold text-base text-red-400">{displayDetail.metrics.oi_change_24h}</div></div>
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 text-center"><div className="text-[10px] text-slate-400 uppercase mb-1">Funding</div><div className="font-mono font-bold text-base text-amber-400">{displayDetail.metrics.funding_rate}</div></div>
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 text-center"><div className="text-[10px] text-slate-400 uppercase mb-1">Taker Sell</div><div className="font-mono font-bold text-base text-slate-200">{(displayDetail.metrics.taker_sell_ratio * 100).toFixed(1)}%</div></div>
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 text-center"><div className="text-[10px] text-slate-400 uppercase mb-1">RSI 15m</div><div className={`font-mono font-bold text-base ${displayDetail.metrics.rsi_15m && displayDetail.metrics.rsi_15m < 30 ? 'text-emerald-400' : 'text-amber-400'}`}>{displayDetail.metrics.rsi_15m?.toFixed(1) || 'N/A'}</div></div>
                  <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 text-center"><div className="text-[10px] text-slate-400 uppercase mb-1">Target -8%</div><div className="font-mono font-bold text-base text-red-400">${displayDetail.target_price.toFixed(6)}</div></div>
                </div>

                """
    code = code[:title_start] + metrics_inline + code[title_start:]

    toggle_button = """<button onClick={() => setShowOiFunding(!showOiFunding)} className="text-[10px] px-2 py-1 bg-slate-800 text-slate-300 rounded hover:bg-slate-700 ml-2">
                            {showOiFunding ? 'Ẩn OI/Funding' : 'Hiện OI/Funding (Mặc định ẩn)'}
                          </button>"""
    code = code.replace("BIỂU ĐỒ NẾN {candleInterval} ({displayDetail.symbol})", "BIỂU ĐỒ NẾN {candleInterval} ({displayDetail.symbol})\n" + toggle_button)

    with open('frontend/src/components/MainWorkspace.tsx', 'w', encoding='utf-8') as f:
        f.write(code)
