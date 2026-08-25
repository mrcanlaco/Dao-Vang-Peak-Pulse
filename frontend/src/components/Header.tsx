import React, { useState, useRef, useEffect } from 'react';
import type { SystemStatus, ModelChoice } from '../types';
import type { MobileTabType } from './v2/MobileBottomNav';
import { useTranslation, LANGUAGES, type LanguageOption } from '../i18n/LanguageContext';
import {
  ChevronDown,
  ChevronLeft,
  Cpu,
  Eye,
  Globe,
  HelpCircle,
  PanelRight,
  PanelRightClose,
  RefreshCw,
  Search,
  Sliders,
  Target,
  Check,
  Sparkles,
  Scale,
  GitPullRequest,
  Settings,
} from 'lucide-react';
import {
  getRiskLabel,
  getScanModeLabel,
  getModelLabel,
  getModelDescription,
} from '../i18n/translations';
import { PwaInstallButton } from './PwaInstallButton';

interface HeaderProps {
  status: SystemStatus | null;
  searchTerm: string;
  setSearchTerm: (val: string) => void;
  selectedRiskFilter: string;
  setSelectedRiskFilter: (val: string) => void;
  threshold: number;
  setThreshold: (val: number) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onOpenGlossary: () => void;
  onOpenWatchlistModal: () => void;
  onOpenTracking: () => void;
  onOpenModelComparison?: () => void;
  onOpenUpdates?: () => void;
  trackingCount: number;
  activeScanMode: string;
  autoTelegramEnabled: boolean;
  isActionDrawerOpen: boolean;
  onToggleActionDrawer: () => void;
  onGoHome?: () => void;
  availableModels?: ModelChoice[];
  selectedModelKey?: string;
  onSelectModel?: (key: string) => void;
  scannerModelId?: string;
  guiVersion?: 'v1' | 'v2';
  onSelectGuiVersion?: (version: 'v1' | 'v2') => void;
  mobileTab?: MobileTabType;
  onBackToRadar?: () => void;
  activeCoinSymbol?: string | null;
  activeCoinPrice?: number | null;
  activeCoinProbability?: number | null;
  activeCoinRisk?: string | null;
  signalCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  searchTerm,
  setSearchTerm,
  selectedRiskFilter,
  setSelectedRiskFilter,
  threshold,
  setThreshold,
  onRefresh,
  isRefreshing,
  onOpenGlossary,
  onOpenWatchlistModal,
  onOpenTracking,
  onOpenModelComparison,
  onOpenUpdates,
  trackingCount,
  activeScanMode,
  autoTelegramEnabled: _autoTelegramEnabled,
  isActionDrawerOpen,
  onToggleActionDrawer,
  onGoHome,
  availableModels = [],
  selectedModelKey = 'heuristic_composite',
  onSelectModel,
  scannerModelId = '',
  guiVersion = 'v2',
  onSelectGuiVersion,
  mobileTab = 'RADAR',
  onBackToRadar,
  activeCoinSymbol = null,
  activeCoinPrice = null,
  activeCoinProbability = null,
  activeCoinRisk: _activeCoinRisk = null,
  signalCount = 0,
}) => {
  const { language, setLanguage, t } = useTranslation();
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const [moreToolsDropdownOpen, setMoreToolsDropdownOpen] = useState(false);
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [commitsBehind, setCommitsBehind] = useState(0);

  const searchInputRef = useRef<HTMLInputElement>(null);

  const isMobileAnalysis = guiVersion === 'v2' && mobileTab === 'ANALYSIS' && Boolean(activeCoinSymbol);

  const formatPrice = (p?: number | null) => {
    if (p == null || p <= 0) return '—';
    if (p < 0.001) return p.toFixed(6);
    if (p < 1) return p.toFixed(5);
    if (p < 10) return p.toFixed(4);
    return p.toFixed(2);
  };

  const probPct = activeCoinProbability != null ? (activeCoinProbability <= 1 ? activeCoinProbability * 100 : activeCoinProbability) : null;

  useEffect(() => {
    let isMounted = true;
    const checkUpdate = async () => {
      try {
        const res = await fetch('/api/system/update-status');
        if (res.ok) {
          const json = await res.json();
          if (isMounted) {
            setUpdateAvailable(Boolean(json.update_available));
            setCommitsBehind(Number(json.commits_behind || 0));
          }
        }
      } catch {
        // silent
      }
    };
    checkUpdate();
    const interval = setInterval(checkUpdate, 60000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Keyboard shortcut '/' to focus search input
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement).tagName)) return;
      if (e.key === '/' || (e.ctrlKey && e.key === 'k') || (e.metaKey && e.key === 'k')) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const selectedModel = availableModels.find((model) => model.key === selectedModelKey);
  const isScannerActive = Boolean(scannerModelId && selectedModel?.frozen_model_id === scannerModelId);
  const currentLangObj = LANGUAGES.find((l) => l.code === language) || LANGUAGES[0];

  const scanLabel = activeScanMode
    .split(' + ')
    .map((mode) => getScanModeLabel(mode, language))
    .join(' + ');

  const watchlistButton = (
    <button
      type="button"
      onClick={onOpenWatchlistModal}
      className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-amber-600 px-2.5 py-1.5 text-xs font-bold text-slate-950 shadow-md shadow-amber-500/15 transition hover:from-amber-400 hover:to-amber-500 active:scale-95 shrink-0"
      title={t('select_coins_to_scan')}
    >
      <Target className="h-3.5 w-3.5 shrink-0 stroke-[2.5]" />
      <span className="truncate whitespace-nowrap text-xs">
        <strong className="font-mono uppercase">{scanLabel}</strong>
      </span>
    </button>
  );

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/90 bg-slate-950/95 px-3 py-2 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1750px] flex-col gap-2">
        {/* =========================================================
            1. MOBILE VIEW (under md)
        ========================================================= */}
        {isMobileAnalysis ? (
          /* Mobile Coin Analysis Bar */
          <div className="flex md:hidden items-center justify-between gap-2 min-w-0">
            {/* Back to Radar Button */}
            <button
              type="button"
              onClick={onBackToRadar || onGoHome}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-amber-500/15 border border-amber-500/40 text-amber-300 hover:bg-amber-500/25 active:scale-95 transition text-xs font-bold shrink-0 shadow-sm"
              title={t('mobile_nav_radar')}
            >
              <ChevronLeft className="w-4 h-4 text-amber-400 stroke-[2.5]" />
              <span>{t('mobile_nav_radar')}</span>
              {signalCount > 0 && (
                <span className="px-1 min-w-[15px] h-[15px] flex items-center justify-center text-[9px] font-mono font-bold rounded-full bg-red-500 text-white ml-0.5">
                  {signalCount}
                </span>
              )}
            </button>

            {/* Center: Coin Ticker & Live Price & AI Prob Badge */}
            <div className="flex items-center gap-1.5 min-w-0 justify-center flex-1">
              <span className="font-black text-amber-400 font-mono text-sm tracking-tight truncate">
                {activeCoinSymbol}
              </span>
              <span className="text-xs font-mono font-bold text-slate-100 shrink-0">
                ${formatPrice(activeCoinPrice)}
              </span>
              {probPct !== null && (
                <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold font-mono border shrink-0 ${
                  probPct >= 70
                    ? 'bg-red-950 text-red-300 border-red-800'
                    : probPct >= 50
                    ? 'bg-amber-950 text-amber-300 border-amber-800'
                    : 'bg-slate-800 text-slate-300 border-slate-700'
                }`}>
                  {probPct.toFixed(0)}%
                </span>
              )}
            </div>

            {/* Right: Quick actions (Refresh, Language) */}
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={onRefresh}
                disabled={isRefreshing}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 active:scale-95 transition disabled:opacity-50"
                title={t('refresh')}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
              </button>

              {/* Language Selector */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setLangDropdownOpen((o) => !o)}
                  className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-amber-500/30 bg-slate-800 px-2 text-xs font-bold text-amber-300 active:scale-95"
                  title={t('language_toggle')}
                >
                  <span className="text-sm leading-none">{currentLangObj.flag}</span>
                </button>
                {langDropdownOpen && (
                  <>
                    <button
                      type="button"
                      aria-label="Close language dropdown"
                      className="fixed inset-0 z-40 h-full w-full cursor-default"
                      onClick={() => setLangDropdownOpen(false)}
                    />
                    <div className="absolute right-0 top-full z-50 mt-1 w-40 rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl backdrop-blur-md">
                      {LANGUAGES.map((item: LanguageOption) => (
                        <button
                          type="button"
                          key={item.code}
                          onClick={() => {
                            setLanguage(item.code);
                            setLangDropdownOpen(false);
                          }}
                          className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                            language === item.code
                              ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40'
                              : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-base leading-none">{item.flag}</span>
                            <span>{item.nativeLabel}</span>
                          </div>
                          {language === item.code && <Check className="w-3.5 h-3.5 text-amber-400" />}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* Mobile Radar View Header (When browsing radar signals) */
          <div className="flex md:hidden flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <div
                role="button"
                tabIndex={0}
                onClick={onGoHome}
                className="flex items-center gap-2 cursor-pointer"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 text-sm font-bold text-slate-950 shadow-md shadow-amber-500/20">
                  🪙
                </div>
                <div>
                  <div className="text-[9px] font-semibold uppercase tracking-wider text-amber-400/80 leading-none">
                    {t('app_subtitle')}
                  </div>
                  <h1 className="text-sm font-black tracking-wide text-amber-300 leading-tight">
                    RADAR
                  </h1>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                {watchlistButton}
                <button
                  type="button"
                  onClick={onRefresh}
                  disabled={isRefreshing}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 active:scale-95"
                  title={t('refresh')}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
                </button>
              </div>
            </div>

            {/* Mobile Search & Risk Toolbar */}
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder={t('search_placeholder')}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500 font-mono"
                />
              </div>
              <select
                value={selectedRiskFilter}
                onChange={(e) => setSelectedRiskFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 rounded-lg px-2 text-xs font-mono text-slate-300 focus:outline-none focus:border-amber-500 cursor-pointer"
              >
                <option value="ALL">{t('risk_all')}</option>
                <option value="CRITICAL">🔴 {getRiskLabel('CRITICAL', language)}</option>
                <option value="HIGH">🟠 {getRiskLabel('HIGH', language)}</option>
                <option value="MEDIUM">🟡 {getRiskLabel('MEDIUM', language)}</option>
                <option value="SAFE">🟢 {getRiskLabel('SAFE', language)}</option>
              </select>
            </div>
          </div>
        )}

        {/* =========================================================
            2. DESKTOP UNIFIED 1-ROW PRO HEADER (md and up)
        ========================================================= */}
        <div className="hidden md:flex items-center justify-between gap-3 min-w-0">
          {/* Left Zone: Brand + Model Selector + Scan Watchlist */}
          <div className="flex items-center gap-2.5 shrink-0">
            {/* Brand Logo & Name */}
            <div
              role="button"
              tabIndex={0}
              onClick={onGoHome}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onGoHome?.();
                }
              }}
              className="group flex items-center gap-2.5 cursor-pointer select-none"
              title={t('go_home')}
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-amber-700 text-base font-bold text-slate-950 shadow-md shadow-amber-500/20 group-hover:scale-105 transition">
                🪙
              </div>
              <div>
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-amber-400/80 leading-none">
                  {t('app_subtitle')}
                </div>
                <h1 className="text-base font-black tracking-wide text-amber-300 group-hover:text-amber-200 leading-tight">
                  RADAR
                </h1>
              </div>
            </div>

            {/* AI Model Selector */}
            {availableModels.length > 0 && onSelectModel && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setModelDropdownOpen((open) => !open)}
                  className="inline-flex max-w-[12rem] lg:max-w-[14rem] items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-[11px] font-bold text-sky-300 transition hover:bg-sky-500/20"
                  title={getModelDescription(selectedModel?.description || selectedModel?.key || '', language)}
                >
                  <Cpu className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{getModelLabel(selectedModel?.label || selectedModel?.key || '', language)}</span>
                  {isScannerActive && (
                    <span className="text-emerald-400" title={t('online_247')}>●</span>
                  )}
                  <ChevronDown className="h-3 w-3 shrink-0 opacity-70" />
                </button>
                {modelDropdownOpen && (
                  <>
                    <button
                      type="button"
                      aria-label="Close model dropdown"
                      className="fixed inset-0 z-40 h-full w-full cursor-default"
                      onClick={() => setModelDropdownOpen(false)}
                    />
                    <div className="absolute left-0 top-full z-50 mt-1.5 w-72 max-h-96 overflow-y-auto rounded-xl border border-slate-700 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-md">
                      <div className="mb-1 border-b border-slate-800 px-2 py-1 text-[10px] font-bold uppercase text-slate-400 flex items-center gap-1.5">
                        <Cpu className="w-3 h-3 text-sky-400" />
                        {t('header_ai_models')}
                      </div>
                      {availableModels.map((model) => (
                        <button
                          type="button"
                          key={model.key}
                          onClick={() => {
                            onSelectModel(model.key);
                            setModelDropdownOpen(false);
                          }}
                          className={`flex w-full flex-col rounded-lg p-2 text-left transition ${
                            model.key === selectedModelKey
                              ? 'border border-sky-500/50 bg-sky-500/20 text-sky-200'
                              : 'text-slate-300 hover:bg-slate-800'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-bold">{getModelLabel(model.label, language)}</span>
                            {scannerModelId && model.frozen_model_id === scannerModelId && (
                              <span className="rounded bg-emerald-950 px-1 py-0.5 text-[9px] font-bold text-emerald-400">
                                {t('sys_heartbeat')}
                              </span>
                            )}
                          </div>
                          {model.description && (
                            <span className="mt-0.5 text-[10px] text-slate-400">
                              {getModelDescription(model.description, language)}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Target Scan Watchlist Button */}
            {watchlistButton}
          </div>

          {/* Center Zone: Unified Search + Risk Filter + Threshold Slider */}
          <div className="flex items-center gap-2 flex-1 max-w-xl justify-center min-w-0">
            {/* Search Input */}
            <div className="relative w-full max-w-xs">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder={`${t('search_placeholder')} (/)`}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-slate-900/90 border border-slate-800 hover:border-slate-700 focus:border-amber-500/80 rounded-lg pl-8 pr-2 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none transition font-mono"
              />
            </div>

            {/* Risk Filter Dropdown */}
            <select
              value={selectedRiskFilter}
              onChange={(e) => setSelectedRiskFilter(e.target.value)}
              className="h-8 bg-slate-900/90 border border-slate-800 hover:border-slate-700 rounded-lg px-2 text-xs font-mono text-slate-300 focus:outline-none focus:border-amber-500 cursor-pointer shrink-0"
              aria-label="Filter risk level"
            >
              <option value="ALL">{t('risk_all')}</option>
              <option value="CRITICAL">🔴 {getRiskLabel('CRITICAL', language)}</option>
              <option value="HIGH">🟠 {getRiskLabel('HIGH', language)}</option>
              <option value="MEDIUM">🟡 {getRiskLabel('MEDIUM', language)}</option>
              <option value="SAFE">🟢 {getRiskLabel('SAFE', language)}</option>
            </select>

            {/* Alert Threshold Slider */}
            <div className="hidden xl:flex items-center gap-1.5 bg-slate-900/80 border border-slate-800 rounded-lg px-2 py-1 text-xs shrink-0">
              <Sliders className="w-3 h-3 text-amber-400 shrink-0" />
              <span className="font-mono text-amber-400 font-bold text-[11px]">{(threshold * 100).toFixed(0)}%</span>
              <input
                type="range"
                min="0.10"
                max="0.85"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="w-12 cursor-pointer accent-amber-500"
                aria-label="Alert threshold"
              />
            </div>
          </div>

          {/* Right Zone: Primary Actions + More Tools Menu + Language */}
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Live 24/7 Status Badge */}
            {(status?.scanner_status === 'ONLINE' || status?.scanner_status === 'ACTIVE') && (
              <span className="hidden xl:inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                </span>
                <span>Live 24/7</span>
              </span>
            )}

            {/* Tracking Watchlist Button */}
            <button
              type="button"
              onClick={onOpenTracking}
              className="relative inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/15 px-2.5 text-xs font-bold text-amber-300 shadow-sm transition hover:bg-amber-500/25 active:scale-95"
              title={t('tracking')}
            >
              <Eye className="h-3.5 w-3.5 text-amber-400" />
              <span className="hidden lg:inline">{t('tracking')}</span>
              {trackingCount > 0 && (
                <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-black text-slate-950">
                  {trackingCount}
                </span>
              )}
            </button>

            {/* Action Drawer Toggle Button */}
            <button
              type="button"
              onClick={onToggleActionDrawer}
              className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border px-2.5 text-xs font-bold shadow-sm transition active:scale-95 ${
                isActionDrawerOpen
                  ? 'border-amber-400 bg-amber-500 text-slate-950 shadow-amber-500/20'
                  : 'border-slate-700 bg-slate-800 text-slate-200 hover:border-amber-500/40 hover:bg-slate-700'
              }`}
              title={isActionDrawerOpen ? t('close_drawer') : t('open_drawer')}
            >
              {isActionDrawerOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRight className="h-3.5 w-3.5 text-amber-400" />}
              <span className="hidden xl:inline">
                {isActionDrawerOpen ? t('btn_close') : t('open_drawer')}
              </span>
            </button>

            {/* Refresh Button */}
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 transition hover:bg-slate-700 active:scale-95 disabled:opacity-50"
              title={t('refresh')}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
            </button>

            {/* More Tools & System Settings Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setMoreToolsDropdownOpen((v) => !v)}
                className={`inline-flex h-8 items-center justify-center gap-1 rounded-lg border px-2 text-xs font-bold shadow-sm transition active:scale-95 ${
                  updateAvailable
                    ? 'border-emerald-500/60 bg-emerald-950/60 text-emerald-300 hover:bg-emerald-900/60'
                    : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
                title="Công cụ & Hệ thống"
              >
                <Settings className={`w-3.5 h-3.5 ${updateAvailable ? 'text-emerald-400' : 'text-slate-400'}`} />
                {updateAvailable && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                )}
                <ChevronDown className="w-2.5 h-2.5 text-slate-400" />
              </button>

              {moreToolsDropdownOpen && (
                <>
                  <button
                    type="button"
                    aria-label="Close tools dropdown"
                    className="fixed inset-0 z-40 h-full w-full cursor-default"
                    onClick={() => setMoreToolsDropdownOpen(false)}
                  />
                  <div className="absolute right-0 top-full z-50 mt-1.5 w-60 rounded-xl border border-slate-700 bg-slate-900/95 p-1.5 shadow-2xl backdrop-blur-md divide-y divide-slate-800">
                    <div className="py-1 space-y-0.5">
                      {/* Version & Updates */}
                      {onOpenUpdates && (
                        <button
                          type="button"
                          onClick={() => {
                            onOpenUpdates();
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                        >
                          <div className="flex items-center gap-2">
                            <GitPullRequest className={`w-3.5 h-3.5 ${updateAvailable ? 'text-emerald-400' : 'text-amber-400'}`} />
                            <span>{updateAvailable ? `Cập nhật (${commitsBehind})` : 'Nhật ký phiên bản'}</span>
                          </div>
                          {updateAvailable && (
                            <span className="text-[9px] bg-emerald-950 text-emerald-300 border border-emerald-700 px-1.5 py-0.2 rounded font-bold">
                              Mới
                            </span>
                          )}
                        </button>
                      )}

                      {/* A/B Engine Comparison */}
                      {onOpenModelComparison && (
                        <button
                          type="button"
                          onClick={() => {
                            onOpenModelComparison();
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                        >
                          <Scale className="w-3.5 h-3.5 text-violet-400" />
                          <span>So sánh A/B Engine</span>
                        </button>
                      )}

                      {/* Glossary */}
                      <button
                        type="button"
                        onClick={() => {
                          onOpenGlossary();
                          setMoreToolsDropdownOpen(false);
                        }}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                      >
                        <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                        <span>{t('glossary')}</span>
                      </button>
                    </div>

                    <div className="py-1 space-y-0.5">
                      {/* GUI Version Switcher */}
                      {onSelectGuiVersion && (
                        <button
                          type="button"
                          onClick={() => {
                            onSelectGuiVersion(guiVersion === 'v1' ? 'v2' : 'v1');
                            setMoreToolsDropdownOpen(false);
                          }}
                          className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition"
                        >
                          <div className="flex items-center gap-2">
                            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                            <span>Giao diện: <strong>{guiVersion === 'v2' ? 'V2 Pro' : 'V1 Classic'}</strong></span>
                          </div>
                        </button>
                      )}

                      {/* PWA Install */}
                      <div className="px-1 py-1">
                        <PwaInstallButton />
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* 4-Language Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setLangDropdownOpen((o) => !o)}
                className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-amber-500/30 bg-slate-800 px-2 text-xs font-bold text-amber-300 shadow-sm transition hover:border-amber-400 hover:bg-slate-700 active:scale-95"
                title={t('language_toggle')}
              >
                <Globe className="h-3 w-3 text-amber-400" />
                <span className="text-xs">{currentLangObj.flag}</span>
                <span className="font-mono text-[10px] uppercase font-bold">{currentLangObj.code}</span>
                <ChevronDown className="h-2.5 w-2.5 text-slate-400" />
              </button>

              {langDropdownOpen && (
                <>
                  <button
                    type="button"
                    aria-label="Close language dropdown"
                    className="fixed inset-0 z-40 h-full w-full cursor-default"
                    onClick={() => setLangDropdownOpen(false)}
                  />
                  <div className="absolute right-0 top-full z-50 mt-1 w-44 rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl backdrop-blur-md">
                    <div className="mb-1 border-b border-slate-800 px-2.5 py-1 text-[10px] font-bold uppercase text-slate-400 flex items-center gap-1.5">
                      <Globe className="w-3 h-3 text-amber-400" />
                      {t('language_toggle')}
                    </div>
                    {LANGUAGES.map((item: LanguageOption) => (
                      <button
                        type="button"
                        key={item.code}
                        onClick={() => {
                          setLanguage(item.code);
                          setLangDropdownOpen(false);
                        }}
                        className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                          language === item.code
                            ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40'
                            : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-base leading-none">{item.flag}</span>
                          <span>{item.nativeLabel}</span>
                        </div>
                        {language === item.code && <Check className="w-3.5 h-3.5 text-amber-400" />}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;

