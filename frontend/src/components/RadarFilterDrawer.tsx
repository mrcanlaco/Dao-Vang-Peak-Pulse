import React, { useState, useEffect, useMemo } from 'react';
import type {
  RadarAdvancedFilterState,
  CoinSector,
  MarketCapFilter,
  RadarStrategicPreset,
  SignalItem
} from '../types';
import { getSignalTwoTierState, DEFAULT_RADAR_ADVANCED_FILTERS } from '../types';
import { getCoinSector, getCoinMarketCapInfo } from '../utils/sectors';
import { useTranslation } from '../i18n/LanguageContext';
import {
  X, Filter, RotateCcw, Check, Sparkles, Zap,
  TrendingDown, ShieldAlert, BarChart2, Coins
} from 'lucide-react';

interface RadarFilterDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  filters: RadarAdvancedFilterState;
  onApplyFilters: (newFilters: RadarAdvancedFilterState) => void;
  onResetFilters: () => void;
  signals: SignalItem[];
  allSignals?: SignalItem[];
}

export const RadarFilterDrawer: React.FC<RadarFilterDrawerProps> = ({
  isOpen,
  onClose,
  filters,
  onApplyFilters,
  onResetFilters,
  signals,
  allSignals = signals,
}) => {
  const { t } = useTranslation();
  const [draftFilters, setDraftFilters] = useState<RadarAdvancedFilterState>(filters);

  // Sync draft filters whenever drawer opens or external filters change
  useEffect(() => {
    if (isOpen) {
      setDraftFilters(filters);
    }
  }, [isOpen, filters]);

  // Handle ESC key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Helper to test if a signal matches a filter state
  const testSignalMatch = (sig: SignalItem, f: RadarAdvancedFilterState): boolean => {
    // 1. Preset Check
    if (f.preset === 'CLIMAX_DUMP') {
      if (getSignalTwoTierState(sig) !== 'FIRED') return false;
    } else if (f.preset === 'ARMED_SETUP') {
      if (getSignalTwoTierState(sig) !== 'ARMED') return false;
    } else if (f.preset === 'FUNDING_TRAP') {
      const frStr = sig.funding_rate || '';
      const frVal = parseFloat(frStr.replace('%', ''));
      const hasFundingAnomaly = sig.anomalies?.some(a => a.category === 'funding' || a.code === 'funding_trap');
      if (!hasFundingAnomaly && (isNaN(frVal) || frVal < 0.02)) return false;
    } else if (f.preset === 'OI_SQUEEZE') {
      const oiStr = sig.oi_change_24h || '';
      const oiVal = parseFloat(oiStr.replace('%', '').replace('+', ''));
      const hasOiAnomaly = sig.anomalies?.some(a => a.category === 'open_interest' || a.category === 'volume');
      if (!hasOiAnomaly && (isNaN(oiVal) || oiVal < 5.0)) return false;
    } else if (f.preset === 'HIGH_RR') {
      const rr = sig.trade_setup?.rr_ratio ?? (Math.abs(sig.target_drawdown || 8) / (sig.trade_setup?.stop_loss_pct || 3.8));
      if (rr < 2.3) return false;
    } else if (f.preset === 'AI_MEME') {
      const sector = getCoinSector(sig.symbol);
      if (sector !== 'AI' && sector !== 'MEME') return false;
    } else if (f.preset === 'LOWCAP_GEMS') {
      const capInfo = getCoinMarketCapInfo(sig.symbol, sig);
      if (capInfo.market_cap_tier !== 'SMALL') return false;
    }

    // 2. Two-tier state
    if (f.twoTierState === 'FIRED' && getSignalTwoTierState(sig) !== 'FIRED') return false;
    if (f.twoTierState === 'ARMED' && getSignalTwoTierState(sig) !== 'ARMED') return false;

    // 3. Sector
    if (!f.sectors.includes('ALL')) {
      const sec = getCoinSector(sig.symbol);
      if (!f.sectors.includes(sec)) return false;
    }

    // 4. Market Cap Tier
    if (f.marketCapTier !== 'ALL') {
      const cap = getCoinMarketCapInfo(sig.symbol, sig);
      if (cap.market_cap_tier !== f.marketCapTier) return false;
    }

    // 5. Funding Range
    if (f.fundingRange !== 'ALL') {
      const frStr = sig.funding_rate || '';
      const frVal = parseFloat(frStr.replace('%', ''));
      if (f.fundingRange === 'POSITIVE_HIGH' && (isNaN(frVal) || frVal < 0.025)) return false;
      if (f.fundingRange === 'NEGATIVE_DEEP' && (isNaN(frVal) || frVal > -0.01)) return false;
      if (f.fundingRange === 'NEUTRAL' && (!isNaN(frVal) && Math.abs(frVal) > 0.015)) return false;
    }

    // 6. Min OI Change %
    if (f.minOiChangePct !== null && f.minOiChangePct !== undefined) {
      const oiStr = sig.oi_change_24h || '';
      const oiVal = parseFloat(oiStr.replace('%', '').replace('+', ''));
      if (isNaN(oiVal) || oiVal < f.minOiChangePct) return false;
    }

    // 7. Min Taker Sell Ratio
    if (f.minTakerSellRatio !== null && f.minTakerSellRatio !== undefined) {
      const ts = sig.taker_sell_ratio ?? 0.5;
      if (ts < f.minTakerSellRatio) return false;
    }

    // 8. Min R:R Ratio
    if (f.minRrRatio !== null && f.minRrRatio !== undefined) {
      const rr = sig.trade_setup?.rr_ratio ?? (Math.abs(sig.target_drawdown || 8) / (sig.trade_setup?.stop_loss_pct || 3.8));
      if (rr < f.minRrRatio) return false;
    }

    // 9. Min Target Drawdown
    if (f.minDrawdownPct !== null && f.minDrawdownPct !== undefined) {
      const dd = Math.abs(sig.target_drawdown || 0);
      if (dd < f.minDrawdownPct) return false;
    }

    // 10. Max Stop Loss %
    if (f.maxStopLossPct !== null && f.maxStopLossPct !== undefined) {
      const sl = sig.trade_setup?.stop_loss_pct ?? 3.8;
      if (sl > f.maxStopLossPct) return false;
    }

    // 11. Anomaly Categories
    if (f.anomalyCategories.length > 0) {
      const sigCats = sig.anomaly_categories || (sig.anomalies ? sig.anomalies.map(a => a.category) : []);
      const matchCat = f.anomalyCategories.some(c => sigCats.includes(c));
      if (!matchCat) return false;
    }

    return true;
  };

  // Preview match count across original pool
  const previewMatchCount = useMemo(() => {
    return allSignals.filter(sig => testSignalMatch(sig, draftFilters)).length;
  }, [allSignals, draftFilters]);

  // Sector toggle handler
  const handleToggleSector = (sec: CoinSector) => {
    if (sec === 'ALL') {
      setDraftFilters(prev => ({ ...prev, sectors: ['ALL'] }));
      return;
    }
    setDraftFilters(prev => {
      let current: CoinSector[] = prev.sectors.filter(s => s !== 'ALL');
      if (current.includes(sec)) {
        current = current.filter(s => s !== sec);
      } else {
        current = [...current, sec];
      }
      if (current.length === 0) current = ['ALL'];
      return { ...prev, sectors: current };
    });
  };

  // Anomaly category toggle handler
  const handleToggleAnomalyCategory = (cat: string) => {
    setDraftFilters(prev => {
      let current = [...prev.anomalyCategories];
      if (current.includes(cat)) {
        current = current.filter(c => c !== cat);
      } else {
        current = [...current, cat];
      }
      return { ...prev, anomalyCategories: current };
    });
  };

  // Strategic Preset 1-click select handler
  const handleSelectPreset = (preset: RadarStrategicPreset) => {
    setDraftFilters(prev => ({
      ...prev,
      preset,
    }));
  };

  const handleApply = () => {
    onApplyFilters(draftFilters);
    onClose();
  };

  const handleReset = () => {
    setDraftFilters(DEFAULT_RADAR_ADVANCED_FILTERS);
    onResetFilters();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/80 backdrop-blur-sm transition-all duration-300 animate-fadeIn">
      {/* Backdrop click to close */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Drawer Body Panel */}
      <div className="relative w-full max-w-lg bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col h-full z-10 overflow-hidden">
        
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/30">
              <Filter className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs sm:text-sm font-bold text-slate-100 font-mono tracking-wide">
                {t('radar_filter_modal_title')}
              </h3>
              <div className="text-[11px] font-mono text-amber-400 font-bold flex items-center gap-1.5 mt-0.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                {t('radar_filter_preview_count')
                  .replace('{matched}', previewMatchCount.toString())
                  .replace('{total}', allSignals.length.toString())}
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
            title={t('radar_filter_close_btn')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable Filter Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-5 font-mono text-xs">
          
          {/* SECTION 1: STRATEGIC PRESETS */}
          <div className="space-y-2">
            <label className="text-[10px] uppercase font-bold tracking-wider text-amber-400 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              {t('radar_filter_section_presets')}
            </label>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { id: 'ALL', label: t('preset_all'), icon: '🌐' },
                { id: 'CLIMAX_DUMP', label: t('preset_climax_dump'), icon: '⚡' },
                { id: 'ARMED_SETUP', label: t('preset_armed_setup'), icon: '🧭' },
                { id: 'FUNDING_TRAP', label: t('preset_funding_trap'), icon: '🔥' },
                { id: 'OI_SQUEEZE', label: t('preset_oi_squeeze'), icon: '📈' },
                { id: 'HIGH_RR', label: t('preset_high_rr'), icon: '🎯' },
                { id: 'AI_MEME', label: t('preset_ai_meme'), icon: '🤖' },
                { id: 'LOWCAP_GEMS', label: t('preset_lowcap_gems'), icon: '💎' },
              ].map(p => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleSelectPreset(p.id as RadarStrategicPreset)}
                  className={`p-2 rounded-xl border text-left text-[11px] font-bold transition flex items-center gap-1.5 ${
                    draftFilters.preset === p.id
                      ? 'bg-amber-500/20 border-amber-500 text-amber-300 ring-1 ring-amber-500/40 shadow-sm'
                      : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700 hover:bg-slate-800/60'
                  }`}
                >
                  <span className="shrink-0">{p.icon}</span>
                  <span className="truncate">{p.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* SECTION 2: MARKET CAP TIERS */}
          <div className="space-y-2 pt-2 border-t border-slate-800/80">
            <label className="text-[10px] uppercase font-bold tracking-wider text-slate-400 flex items-center gap-1.5">
              <Coins className="w-3.5 h-3.5 text-blue-400" />
              {t('radar_filter_section_market_cap')}
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
              {[
                { id: 'ALL', label: t('mcap_all'), icon: '🌐' },
                { id: 'LARGE', label: t('mcap_large'), icon: '👑' },
                { id: 'MID', label: t('mcap_mid'), icon: '⚡' },
                { id: 'SMALL', label: t('mcap_small'), icon: '💎' },
              ].map(c => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setDraftFilters(prev => ({ ...prev, marketCapTier: c.id as MarketCapFilter }))}
                  className={`p-2 rounded-xl border text-center text-[10px] font-bold transition ${
                    draftFilters.marketCapTier === c.id
                      ? 'bg-blue-950/80 border-blue-500 text-blue-300 ring-1 ring-blue-500/40'
                      : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                  }`}
                >
                  <span className="block text-xs mb-0.5">{c.icon}</span>
                  <span className="truncate block">{c.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* SECTION 3: SECTORS */}
          <div className="space-y-2 pt-2 border-t border-slate-800/80">
            <label className="text-[10px] uppercase font-bold tracking-wider text-slate-400 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <BarChart2 className="w-3.5 h-3.5 text-amber-400" />
                {t('radar_filter_section_sectors')}
              </span>
              <span className="text-[10px] font-normal text-slate-500">
                {draftFilters.sectors.includes('ALL') ? 'Tất cả' : `${draftFilters.sectors.length} đã chọn`}
              </span>
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
              {[
                { id: 'ALL', label: t('sector_all'), icon: '🌐' },
                { id: 'AI', label: t('sector_ai'), icon: '🤖' },
                { id: 'MEME', label: t('sector_meme'), icon: '🐸' },
                { id: 'L1_L2', label: t('sector_l1_l2'), icon: '⚡' },
                { id: 'DEFI', label: t('sector_defi'), icon: '🏦' },
                { id: 'GAMEFI', label: t('sector_gamefi'), icon: '🎮' },
                { id: 'TOP_CAP', label: t('sector_top_cap'), icon: '👑' },
              ].map(s => {
                const isSelected = draftFilters.sectors.includes(s.id as CoinSector);
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => handleToggleSector(s.id as CoinSector)}
                    className={`p-2 rounded-xl border text-left text-[11px] font-semibold transition flex items-center justify-between ${
                      isSelected
                        ? 'bg-amber-950/70 border-amber-500 text-amber-300 ring-1 ring-amber-500/30'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    <span className="flex items-center gap-1.5 truncate">
                      <span>{s.icon}</span>
                      <span className="truncate">{s.label}</span>
                    </span>
                    {isSelected && <Check className="w-3 h-3 text-amber-400 shrink-0 ml-1" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* SECTION 4: DERIVATIVES */}
          <div className="space-y-3 pt-2 border-t border-slate-800/80">
            <label className="text-[10px] uppercase font-bold tracking-wider text-slate-400 flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              {t('radar_filter_section_derivatives')}
            </label>

            {/* Funding Rate Range */}
            <div className="space-y-1.5">
              <span className="text-[10px] text-slate-500 uppercase block font-bold">Funding Rate</span>
              <div className="grid grid-cols-2 gap-1.5">
                {[
                  { id: 'ALL', label: t('funding_all') },
                  { id: 'POSITIVE_HIGH', label: t('funding_positive_high') },
                  { id: 'NEGATIVE_DEEP', label: t('funding_negative_deep') },
                  { id: 'NEUTRAL', label: t('funding_neutral') },
                ].map(fr => (
                  <button
                    key={fr.id}
                    type="button"
                    onClick={() => setDraftFilters(prev => ({ ...prev, fundingRange: fr.id as any }))}
                    className={`p-1.5 rounded-lg border text-left text-[10px] font-semibold transition ${
                      draftFilters.fundingRange === fr.id
                        ? 'bg-amber-950/80 border-amber-500 text-amber-300 font-bold'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    {fr.label}
                  </button>
                ))}
              </div>
            </div>

            {/* OI Delta 24h Threshold */}
            <div className="space-y-1.5">
              <span className="text-[10px] text-slate-500 uppercase block font-bold">{t('filter_min_oi_change')}</span>
              <div className="grid grid-cols-4 gap-1.5">
                {[
                  { val: null, label: 'Tất cả' },
                  { val: 5, label: '≥ +5%' },
                  { val: 10, label: '≥ +10%' },
                  { val: 20, label: '≥ +20%' },
                ].map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setDraftFilters(prev => ({ ...prev, minOiChangePct: item.val }))}
                    className={`p-1.5 rounded-lg border text-center text-[10px] font-semibold transition ${
                      draftFilters.minOiChangePct === item.val
                        ? 'bg-sky-950 border-sky-500 text-sky-300 font-bold'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Taker Sell Ratio Threshold */}
            <div className="space-y-1.5">
              <span className="text-[10px] text-slate-500 uppercase block font-bold">{t('filter_min_taker_sell')}</span>
              <div className="grid grid-cols-4 gap-1.5">
                {[
                  { val: null, label: 'Tất cả' },
                  { val: 0.50, label: '≥ 50%' },
                  { val: 0.55, label: '≥ 55%' },
                  { val: 0.60, label: '≥ 60%' },
                ].map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setDraftFilters(prev => ({ ...prev, minTakerSellRatio: item.val }))}
                    className={`p-1.5 rounded-lg border text-center text-[10px] font-semibold transition ${
                      draftFilters.minTakerSellRatio === item.val
                        ? 'bg-emerald-950 border-emerald-500 text-emerald-300 font-bold'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* SECTION 5: TRADE SETUP */}
          <div className="space-y-3 pt-2 border-t border-slate-800/80">
            <label className="text-[10px] uppercase font-bold tracking-wider text-slate-400 flex items-center gap-1.5">
              <TrendingDown className="w-3.5 h-3.5 text-red-400" />
              {t('radar_filter_section_setup')}
            </label>

            {/* Min R:R Ratio */}
            <div className="space-y-1.5">
              <span className="text-[10px] text-slate-500 uppercase block font-bold">{t('filter_min_rr_ratio')}</span>
              <div className="grid grid-cols-4 gap-1.5">
                {[
                  { val: null, label: 'Tất cả' },
                  { val: 1.5, label: '≥ 1:1.5' },
                  { val: 2.0, label: '≥ 1:2.0' },
                  { val: 2.5, label: '≥ 1:2.5' },
                ].map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setDraftFilters(prev => ({ ...prev, minRrRatio: item.val }))}
                    className={`p-1.5 rounded-lg border text-center text-[10px] font-semibold transition ${
                      draftFilters.minRrRatio === item.val
                        ? 'bg-amber-950 border-amber-500 text-amber-300 font-bold'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Two-Tier State */}
            <div className="space-y-1.5">
              <span className="text-[10px] text-slate-500 uppercase block font-bold">{t('filter_two_tier_state')}</span>
              <div className="grid grid-cols-3 gap-1.5">
                {[
                  { id: 'ALL', label: t('filter_all_states') },
                  { id: 'FIRED', label: '⚡ FIRED Climax' },
                  { id: 'ARMED', label: '🧭 ARMED Setup' },
                ].map(st => (
                  <button
                    key={st.id}
                    type="button"
                    onClick={() => setDraftFilters(prev => ({ ...prev, twoTierState: st.id as any }))}
                    className={`p-1.5 rounded-lg border text-center text-[10px] font-semibold transition ${
                      draftFilters.twoTierState === st.id
                        ? 'bg-red-950 border-red-500 text-red-300 font-bold'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    {st.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* SECTION 6: MARKET ANOMALIES */}
          <div className="space-y-2 pt-2 border-t border-slate-800/80">
            <label className="text-[10px] uppercase font-bold tracking-wider text-violet-300 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5" />
              {t('radar_filter_section_anomalies')}
            </label>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { id: 'funding', label: '🔥 Bẫy Funding Cực Đại' },
                { id: 'open_interest', label: '📈 Phân Kỳ Đảo Chiều OI' },
                { id: 'volume', label: '⚡ Bùng Nổ Volume Xả' },
                { id: 'reversal', label: '🧭 Phân Kỳ RSI / Đảo Chiều' },
              ].map(cat => {
                const isSelected = draftFilters.anomalyCategories.includes(cat.id);
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => handleToggleAnomalyCategory(cat.id)}
                    className={`p-2 rounded-xl border text-left text-[10px] font-semibold transition flex items-center justify-between ${
                      isSelected
                        ? 'bg-violet-950 border-violet-500 text-violet-300 ring-1 ring-violet-500/30'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    <span className="truncate">{cat.label}</span>
                    {isSelected && <Check className="w-3 h-3 text-violet-400 shrink-0 ml-1" />}
                  </button>
                );
              })}
            </div>
          </div>

        </div>

        {/* Footer Toolbar */}
        <div className="p-3.5 border-t border-slate-800 bg-slate-950/90 flex items-center justify-between gap-2 font-mono">
          <button
            type="button"
            onClick={handleReset}
            className="px-3 py-2 rounded-xl border border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition text-xs font-bold flex items-center gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            {t('radar_filter_reset_btn')}
          </button>

          <button
            type="button"
            onClick={handleApply}
            className="flex-1 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-xs transition flex items-center justify-center gap-1.5 shadow-lg shadow-amber-500/20 active:scale-[0.98]"
          >
            <Check className="w-4 h-4" />
            {t('radar_filter_apply_btn').replace('{count}', previewMatchCount.toString())}
          </button>
        </div>

      </div>
    </div>
  );
};

