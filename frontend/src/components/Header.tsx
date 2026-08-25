import React, { useState } from 'react';
import type { SystemStatus, ModelChoice } from '../types';
import { useTranslation, LANGUAGES, type LanguageOption } from '../i18n/LanguageContext';
import {
  ChevronDown,
  Cpu,
  Eye,
  Globe,
  HelpCircle,
  Keyboard,
  PanelRight,
  PanelRightClose,
  RefreshCw,
  Search,
  Send,
  Sliders,
  Target,
  Check,
  Sparkles,
  Scale,
  GitPullRequest,
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
  autoTelegramEnabled,
  isActionDrawerOpen,
  onToggleActionDrawer,
  onGoHome,
  availableModels = [],
  selectedModelKey = 'heuristic_composite',
  onSelectModel,
  scannerModelId = '',
  guiVersion = 'v2',
  onSelectGuiVersion,
}) => {
  const { language, setLanguage, t } = useTranslation();
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [commitsBehind, setCommitsBehind] = useState(0);

  React.useEffect(() => {
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
      className="header-scan-button inline-flex w-full min-w-0 items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-amber-600 px-3 py-2 text-xs font-bold text-slate-950 shadow-md shadow-amber-500/15 transition hover:from-amber-400 hover:to-amber-500 md:w-auto"
      title={t('select_coins_to_scan')}
    >
      <Target className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate whitespace-nowrap">
        {t('scan_target_prefix')}
        <strong className="font-mono uppercase">{scanLabel}</strong>
      </span>
    </button>
  );

  return (
    <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-900/95 px-3 py-2.5 backdrop-blur-md sm:px-4">
      <div className="mx-auto flex max-w-[1700px] flex-col gap-2.5">
        <div className="flex flex-col gap-2.5 lg:flex-row lg:items-center lg:gap-4">
          {/* Brand and model selector */}
          <div className="flex min-w-0 items-center justify-between gap-3 lg:w-[22rem] lg:shrink-0 lg:justify-start">
            <div
              role="button"
              tabIndex={0}
              onClick={onGoHome}
              onKeyDown={(event) => {
                if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                  event.preventDefault();
                  onGoHome?.();
                }
              }}
              className="group flex min-w-0 cursor-pointer items-center gap-2.5 bg-transparent p-0 text-left"
              title={t('go_home')}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-amber-700 text-lg font-bold text-slate-950 shadow-lg shadow-amber-500/20 transition group-hover:scale-105 sm:h-10 sm:w-10">
                🪙
              </div>
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-400/80">
                  {t('app_subtitle')}
                </div>
                <h1 className="truncate text-base font-black leading-tight tracking-wide text-amber-300 transition group-hover:text-amber-200 sm:text-lg">
                  RADAR
                </h1>
              </div>
            </div>

            {availableModels.length > 0 && onSelectModel && (
              <div className="relative min-w-0">
                <button
                  type="button"
                  onClick={() => setModelDropdownOpen((open) => !open)}
                  className="inline-flex max-w-[12rem] items-center gap-1.5 rounded-md border border-sky-500/30 bg-sky-500/10 px-2 py-1 text-[10px] font-bold text-sky-300 transition hover:bg-sky-500/20 sm:max-w-[15rem]"
                  title={getModelDescription(selectedModel?.description || selectedModel?.key || '', language)}
                >
                  <Cpu className="h-3 w-3 shrink-0" />
                  <span className="truncate">{getModelLabel(selectedModel?.label || selectedModel?.key || '', language)}</span>
                  {isScannerActive && (
                    <span
                      className="text-emerald-400"
                      title={t('online_247')}
                    >
                      ●
                    </span>
                  )}
                  <ChevronDown className="h-2.5 w-2.5 shrink-0" />
                </button>
                {modelDropdownOpen && (
                  <>
                    <button
                      type="button"
                      aria-label="Close model dropdown"
                      className="fixed inset-0 z-40 h-full w-full cursor-default"
                      onClick={() => setModelDropdownOpen(false)}
                    />
                    <div className="absolute right-0 top-full z-50 mt-1 max-h-96 w-[min(20rem,calc(100vw-1.5rem))] overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-xl lg:left-0 lg:right-auto">
                      <div className="mb-1 border-b border-slate-800 px-2 py-1 text-[10px] font-bold uppercase text-slate-400">
                        🧠 {t('header_ai_models')}
                      </div>
                      {availableModels.map((model) => (
                        <button
                          type="button"
                          key={model.key}
                          onClick={() => {
                            onSelectModel(model.key);
                            setModelDropdownOpen(false);
                          }}
                          className={`flex w-full flex-col rounded-md p-2 text-left transition ${
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
          </div>

          {/* Quick status badges */}
          <div className="hidden flex-wrap items-center gap-2 md:flex lg:flex-1">
            {watchlistButton}

            {autoTelegramEnabled && (
              <span className="inline-flex items-center gap-1 rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-1 text-[11px] font-semibold text-sky-400">
                <Send className="h-3 w-3" />
                <span>{t('auto_telegram')}</span>
              </span>
            )}

            {(status?.scanner_status === 'ONLINE' || status?.scanner_status === 'ACTIVE') && (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-400">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                <span>{t('online_247')}</span>
              </span>
            )}
          </div>

          {/* Header Action buttons */}
          <div className="flex items-center justify-end gap-2 lg:shrink-0">
            <PwaInstallButton />

            <button
              type="button"
              onClick={onOpenTracking}
              className="relative inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/15 px-3 py-1 text-xs font-bold text-amber-300 shadow-sm transition hover:border-amber-400 hover:bg-amber-500/25"
              title={t('tracking')}
            >
              <Eye className="h-3.5 w-3.5 text-amber-400" />
              <span className="hidden sm:inline">{t('tracking')}</span>
              {trackingCount > 0 && (
                <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-black text-slate-950">
                  {trackingCount}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={onToggleActionDrawer}
              className={`inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border px-3 py-1 text-xs font-bold shadow-sm transition ${
                isActionDrawerOpen
                  ? 'border-amber-400 bg-amber-500 text-slate-950 shadow-amber-500/20'
                  : 'border-slate-700 bg-slate-800 text-slate-200 hover:border-amber-500/40 hover:bg-slate-700'
              }`}
              title={isActionDrawerOpen ? t('close_drawer') : t('open_drawer')}
            >
              {isActionDrawerOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRight className="h-4 w-4 text-amber-400" />}
              <span className="hidden sm:inline">
                {isActionDrawerOpen ? t('btn_close') : t('open_drawer')}
              </span>
            </button>

            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 transition hover:border-slate-600 hover:bg-slate-700 disabled:opacity-50"
              title={t('refresh')}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin text-amber-400' : ''}`} />
            </button>

            <button
              type="button"
              onClick={onOpenGlossary}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-amber-400 transition hover:bg-amber-500/20 sm:w-auto sm:gap-1.5"
              title={t('glossary')}
            >
              <HelpCircle className="h-3.5 w-3.5" />
              <span className="hidden text-xs font-medium sm:inline">{t('glossary')}</span>
            </button>

            {/* GUI Version Switcher: V1 Classic ⇄ V2 Pro */}
            {onSelectGuiVersion && (
              <button
                type="button"
                onClick={() => onSelectGuiVersion(guiVersion === 'v1' ? 'v2' : 'v1')}
                className={`inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border px-2.5 text-xs font-bold shadow-sm transition ${
                  guiVersion === 'v2'
                    ? 'border-amber-400/80 bg-gradient-to-r from-amber-500/25 via-red-500/20 to-amber-500/15 text-amber-300 shadow-amber-500/15 ring-1 ring-amber-500/30'
                    : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-600 hover:text-white'
                }`}
                title={guiVersion === 'v2' ? 'Đang dùng GUI V2 Pro (Bấm để chuyển về V1 Classic)' : 'Đang dùng GUI V1 Classic (Bấm để nâng cấp lên V2 Pro Mobile)'}
                aria-label="Toggle GUI Version"
              >
                <Sparkles className={`h-3.5 w-3.5 ${guiVersion === 'v2' ? 'text-amber-400 animate-pulse' : 'text-slate-400'}`} />
                <span className="font-mono text-[11px] font-bold">
                  {guiVersion === 'v2' ? t('gui_version_v2') : t('gui_version_v1')}
                </span>
              </button>
            )}

            {/* A/B Engine Comparison Button */}
            {onOpenModelComparison && (
              <button
                type="button"
                onClick={onOpenModelComparison}
                className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-violet-500/40 bg-violet-950/40 px-2.5 py-1 text-violet-300 shadow-sm transition hover:bg-violet-900/50 hover:border-violet-400 active:scale-95"
                title={t('model_comparison_button') || 'So Sánh A/B Engine (V1 vs V2)'}
                aria-label="Open Engine A/B Comparison"
              >
                <Scale className="h-3.5 w-3.5 text-violet-400" />
                <span className="hidden text-xs font-bold sm:inline font-mono">A/B Engine</span>
              </button>
            )}

            {/* Version Updates Button */}
            {onOpenUpdates && (
              <button
                type="button"
                onClick={onOpenUpdates}
                className={`relative inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg border px-2.5 py-1 shadow-sm transition active:scale-95 ${
                  updateAvailable
                    ? 'border-emerald-500/60 bg-emerald-950/60 text-emerald-300 hover:bg-emerald-900/70 hover:border-emerald-400'
                    : 'border-amber-500/40 bg-amber-950/40 text-amber-300 hover:bg-amber-900/50 hover:border-amber-400'
                }`}
                title={updateAvailable ? `Có ${commitsBehind} commit mới trên GitHub` : t('ws_tab_updates')}
                aria-label="Open Version Updates"
              >
                <GitPullRequest className={`h-3.5 w-3.5 ${updateAvailable ? 'text-emerald-400' : 'text-amber-400'}`} />
                <span className="hidden text-xs font-bold sm:inline font-mono">
                  {updateAvailable ? `⚡ Update (${commitsBehind})` : 'v2.0-pro'}
                </span>
                {updateAvailable && (
                  <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                  </span>
                )}
              </button>
            )}

            {/* 4-Language Dropdown Selector */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setLangDropdownOpen((o) => !o)}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-amber-500/30 bg-slate-800 px-2.5 text-xs font-bold text-amber-300 shadow-sm transition hover:border-amber-400 hover:bg-slate-700"
                title={t('language_toggle')}
                aria-label="Select language"
              >
                <Globe className="h-3.5 w-3.5 text-amber-400" />
                <span className="text-sm leading-none">{currentLangObj.flag}</span>
                <span className="font-mono text-[11px] font-bold uppercase">{currentLangObj.code}</span>
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
                        className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-xs font-semibold transition ${
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

        {/* Search and filtering toolbar */}
        <div className="flex flex-col gap-2 border-t border-slate-800/70 pt-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_8.5rem] gap-2 sm:flex sm:flex-wrap sm:items-center lg:flex-nowrap">
            <div className="col-span-2 md:hidden">{watchlistButton}</div>
            <label className="relative col-start-1 row-start-2 min-w-0 sm:w-56 lg:w-64" aria-label="Search coin">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder={t('search_placeholder')}
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                className="h-9 w-full rounded-lg border border-slate-800 bg-slate-950 pl-8 pr-2 text-xs text-slate-200 outline-none transition placeholder:text-slate-500 focus:border-amber-500/60"
              />
            </label>
            <select
              value={selectedRiskFilter}
              onChange={(event) => setSelectedRiskFilter(event.target.value)}
              className="col-start-2 row-start-2 h-9 w-full cursor-pointer rounded-lg border border-slate-800 bg-slate-950 px-2.5 text-xs font-mono text-slate-300 outline-none transition focus:border-amber-500/60 sm:w-auto"
              aria-label="Filter risk level"
            >
              <option value="ALL">{t('risk_all')}</option>
              <option value="CRITICAL">🔴 {getRiskLabel('CRITICAL', language)}</option>
              <option value="HIGH">🟠 {getRiskLabel('HIGH', language)}</option>
              <option value="MEDIUM">🟡 {getRiskLabel('MEDIUM', language)}</option>
              <option value="SAFE">🟢 {getRiskLabel('SAFE', language)}</option>
            </select>
            <div className="hidden h-9 items-center gap-2 rounded-lg border border-slate-800 bg-slate-950 px-2.5 text-xs sm:flex">
              <Sliders className="h-3.5 w-3.5 shrink-0 text-amber-400" />
              <span className="text-[11px] text-slate-400">{t('threshold')}</span>
              <span className="font-mono font-bold text-amber-400">{(threshold * 100).toFixed(0)}%</span>
              <input
                type="range"
                min="0.10"
                max="0.85"
                step="0.05"
                value={threshold}
                onChange={(event) => setThreshold(parseFloat(event.target.value))}
                className="w-16 cursor-pointer accent-amber-500"
                aria-label="Alert threshold"
              />
            </div>
          </div>

          <div className="hidden items-center gap-2 text-[10px] text-slate-400 lg:flex">
            <Keyboard className="h-3 w-3 text-amber-400" />
            <span>{t('hotkeys')}:</span>
            <kbd className="rounded border border-slate-800 bg-slate-950 px-1 py-0.5 text-slate-300">↑/↓</kbd>
            <span>{t('hotkey_navigate')}</span>
            <kbd className="rounded border border-slate-800 bg-slate-950 px-1 py-0.5 text-slate-300">Space</kbd>
            <span>{t('hotkey_push_tg')}</span>
          </div>
        </div>
      </div>
    </header>
  );
};
