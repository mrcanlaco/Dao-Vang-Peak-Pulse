with open('frontend/src/components/MainWorkspace.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

hero_start = code.find('{/* Selected Coin Hero Card — Compact 3-column */}')
valid_end = code.find('{/* Candlestick Chart + OI/Funding sub-chart */}')

if hero_start != -1 and valid_end != -1:
    new_hero = """{/* HERO CARD - ACTION CENTERED */}
              <div className="bg-gradient-to-br from-slate-950 to-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row items-center justify-between gap-4 mb-3">
                
                <div className="flex items-center gap-4">
                   <div className="w-14 h-14 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shrink-0">
                     <span className="text-amber-400 font-black text-lg">
                        {displayDetail.symbol.replace('USDT', '').slice(0, 3)}
                     </span>
                   </div>
                   <div>
                     <div className="text-2xl font-black text-slate-100 flex items-center gap-2">
                        <CoinLink symbol={displayDetail.symbol} onClick={() => onSelectCandidate(displayDetail.symbol)} />
                        {selectedSignal?.hit === true && (
                          <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">✓ TRÚNG</span>
                        )}
                        {selectedSignal?.hit === false && (
                          <span className="px-2 py-0.5 text-[10px] font-bold bg-red-950 text-red-400 border border-red-800 rounded">✗ TRƯỢT</span>
                        )}
                     </div>
                     <div className="text-xl font-bold text-amber-400 font-mono mt-1">
                        ${displayDetail.current_price.toFixed(6)}
                     </div>
                   </div>
                </div>

                <div className="flex items-center gap-8">
                  <div className="text-center">
                    <div className="text-xs text-slate-400 uppercase mb-1 relative group cursor-help">
                        XÁC SUẤT XẢ (AI)
                        <span className="hidden group-hover:block absolute left-1/2 -translate-x-1/2 top-full mt-1 w-56 p-2 bg-slate-800 border border-slate-700 rounded-lg text-[10px] normal-case text-slate-300 z-20 shadow-xl">
                          Nguồn: {displayDetail.score_source}
                        </span>
                    </div>
                    {displayDetail.probability != null ? (
                      <span className="text-4xl font-black text-red-400 font-mono">
                         {displayDetail.probability.toFixed(1)}<span className="text-xl text-slate-500">/100</span>
                      </span>
                    ) : (
                      <span className="text-4xl font-black text-slate-500 font-mono">—</span>
                    )}
                    {isDeepAnalyzing && (
                        <div className="text-[10px] text-slate-500 animate-pulse mt-1">Đang tính...</div>
                    )}
                  </div>
                  <div className="text-center">
                     <div className="text-xs text-slate-400 uppercase mb-2">MỨC RỦI RO</div>
                     <span className={`px-3 py-1.5 text-sm font-bold rounded border ${
                        displayDetail.risk_level === 'CRITICAL' ? 'bg-red-950 text-red-400 border-red-800' :
                        displayDetail.risk_level === 'HIGH' ? 'bg-amber-950 text-amber-400 border-amber-800' :
                        displayDetail.risk_level === 'MEDIUM' ? 'bg-yellow-950 text-yellow-300 border-yellow-800' :
                        displayDetail.risk_level === 'SAFE' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' :
                        'bg-slate-800 text-slate-400 border-slate-700'
                      }`}>
                        {displayDetail.risk_level ?? 'CHƯA CÓ'}
                     </span>
                  </div>
                </div>

                <div className="flex flex-col gap-2 min-w-[200px]">
                   <button 
                     onClick={() => onRunDeepAnalysis(displayDetail.symbol)}
                     disabled={isDeepAnalyzing}
                     className="w-full px-4 py-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold rounded-lg text-sm flex items-center justify-center transition"
                   >
                      {isDeepAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : "Chạy lại Scoring (Update)"}
                   </button>
                   <div className="flex gap-2 w-full">
                     {onAddWatchlist && (
                         <button onClick={() => onAddWatchlist(displayDetail.symbol)} className="px-3 py-1.5 bg-slate-800 hover:bg-amber-950 text-slate-300 border border-slate-700 font-bold rounded-lg text-xs flex items-center justify-center flex-1 transition">
                           <Eye className="w-3.5 h-3.5 mr-1" /> Theo dõi
                         </button>
                     )}
                     {selectedSignal && onDismissSignal && (
                         <button onClick={() => onDismissSignal(selectedSignal)} className="px-3 py-1.5 bg-slate-800 hover:bg-red-950 text-slate-300 border border-slate-700 font-bold rounded-lg text-xs flex items-center justify-center flex-1 transition">
                           <XCircle className="w-3.5 h-3.5 mr-1" /> Ẩn
                         </button>
                     )}
                   </div>
                </div>
              </div>

              """
    code = code[:hero_start] + new_hero + code[valid_end:]
    
    with open('frontend/src/components/MainWorkspace.tsx', 'w', encoding='utf-8') as f:
        f.write(code)
