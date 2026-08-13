import React, { useState } from 'react';
import type { SystemStatus, ModelChoice } from '../types';
import { useTranslation } from '../i18n/LanguageContext';
import {
  ChevronDown,
  Cpu,
  Eye,
  Globe,
  HelpCircle,
  Keyboard,
  PanelRight,
  PanelRightClose,
  Radio,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  Sliders,
  Target,
} from 'lucide-react';

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
}

const scanModeLabelsVi: Record<string, string> = {
  volatile: 'Biến động',
  gainers: 'Tăng mạnh',
  losers: 'Giảm mạnh',
  volume: 'Khối lượng',
  all: 'Tất cả',
  manual: 'Cá nhân',
};

const scanModeLabelsEn: Record<string, string> = {
  volatile: 'Volatile',
  gainers: 'Gainers',
  losers: 'Losers',
  volume: 'Volume',
  all: 'All',
  manual: 'Manual',
};

const modelTypeLabelsVi: Record<string, string> = {
  heuristic: 'Quy tắc',
  walkforward: 'Theo thời gian',
  frozen: 'Đã đóng băng',
};

const modelTypeLabelsEn: Record<string, string> = {
  heuristic: 'Heuristic Rule',
  walkforward: 'Walk-forward',
  frozen: 'Frozen Model',
};

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
}) => {
  const { language, toggleLanguage, t } = useTranslation();
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const selectedModel = availableModels.find((model) => model.key === selectedModelKey);
  const isScannerActive = Boolean(scannerModelId && selectedModel?.frozen_model_id === scannerModelId);

  const scanModeLabels = language === 'en' ? scanModeLabelsEn : scanModeLabelsVi;
  const modelTypeLabels = language === 'en' ? modelTypeLabelsEn : modelTypeLabelsVi;

  const scanLabel = activeScanMode
    .split(' + ')
    .map((mode) => scanModeLabels[mode] || mode)
    .join(' + ');

  const getModelLabel = (label?: string) => {
    if (!label) return language === 'en' ? 'Select Model' : 'Chọn mô hình';
    if (language === 'en') {
      return label
        .replace('Heuristic 0-100 (mặc định)', 'Heuristic 0–100 (Default)')
        .replace('Logistic Regression Walk-forward', 'Logistic Regression (Walk-forward)')
        .replace(/^Frozen LR/, 'Frozen Logistic Regression');
    }
    return label
      .replace('Heuristic 0-100 (mặc định)', 'Chấm điểm quy tắc 0–100 (mặc định)')
      .replace('Logistic Regression Walk-forward', 'Hồi quy logistic theo thời gian')
      .replace(/^Frozen LR/, 'Hồi quy logistic đã đóng băng');
  };

  const getModelDescription = (description?: string) => {
    if (!description) return '';
    if (language === 'en') return description;
    return description
      .replace(/Logistic Regression/g, 'Hồi quy logistic')
      .replace(/rule-based/g, 'theo quy tắc')
      .replace(/funding spike/g, 'tăng đột biến funding')
      .replace(/price-volume/g, 'giá-khối lượng')
      .replace(/backtest/g, 'kiểm thử lịch sử')
      .replace(/baseline/g, 'mốc chuẩn')
      .replace(/Train cutoff/g, 'Mốc cắt huấn luyện');
  };

  const watchlistButton = (
    <button
      type="button"
      onClick={onOpenWatchlistModal}
      className="header-scan-button inline-flex w-full min-w-0 items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-amber-600 px-3 py-2 text-xs font-bold text-slate-950 shadow-md shadow-amber-500/15 transition hover:from-amber-400 hover:to-amber-500 md:w-auto"
      title={language === 'en' ? 'Select coins to scan' : 'Chọn danh sách coin để quét'}
    >
      <Target className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate whitespace-nowrap">
        {language === 'en' ? 'Scan Target: ' : 'Danh sách quét: '}
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
              title={language === 'en' ? 'Go to Home' : 'Về trang chủ'}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-amber-700 text-lg font-bold text-slate-950 shadow-lg shadow-amber-500/20 transition group-hover:scale-105 sm:h-10 sm:w-10">
                🪙
              </div>
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-400/80">
                  {language === 'en' ? 'PeakPulse AI' : 'Đảo Vàng AI'}
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
                  title={getModelDescription(selectedModel?.description) || (language === 'en' ? 'Select AI Model' : 'Chọn mô hình AI')}
                >
                  <Cpu className="h-3 w-3 shrink-0" />
                  <span className="truncate">{getModelLabel(selectedModel?.label)}</span>
                  {isScannerActive && <span className="text-emerald-400" title={language === 'en' ? 'Running on 24/7 Scanner' : 'Đang dùng cho bộ quét 24/7'}>●</span>}
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
                        🧠 {language === 'en' ? 'Select AI Model' : 'Chọn mô hình AI'}
                      </div>
                      {availableModels.map((model) => (
                        <button
                          type="button"
                          key={model.key}
                          onClick={() => {
                            onSelectModel(model.key);
                            setModelDropdownOpen(false);
                          }}
                          className={`w-full rounded px-2 py-2 text-left text-xs transition ${
                            model.key === selectedModelKey
                              ? 'border border-sky-500/40 bg-sky-500/20 text-sky-200'
                              : 'border border-transparent text-slate-300 hover:bg-slate-800'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex min-w-0 items-center gap-1.5">
                              <span className="truncate font-bold">{getModelLabel(model.label)}</span>
                              {model.frozen_model_id === scannerModelId && scannerModelId && (
                                <span className="shrink-0 font-mono text-[9px] text-emerald-400">
                                  {language === 'en' ? 'SCANNER' : 'BỘ QUÉT'}
                                </span>
                              )}
                            </div>
                            <span className="shrink-0 text-[9px] uppercase text-slate-500">
                              {modelTypeLabels[model.model_type] || model.model_type}
                            </span>
                          </div>
                          <div className="mt-0.5 line-clamp-2 text-[10px] text-slate-400">{getModelDescription(model.description)}</div>
                          {model.label_spec && (
                            <div className="mt-1 flex gap-2 font-mono text-[9px] text-slate-500">
                              <span>{language === 'en' ? 'Target:' : 'Mục tiêu:'} {model.label_spec.target_pct}</span>
                              <span>MAE: {model.label_spec.mae_pct}</span>
                              <span>{language === 'en' ? 'Horizon:' : 'Khung:'} {model.label_spec.horizon_h}</span>
                            </div>
                          )}
                        </button>
                      ))}
                      <div className="mt-1 border-t border-slate-800 px-2 py-1.5 text-[9px] text-slate-500">
                        {isScannerActive
                          ? (language === 'en' ? '✅ This model is active in the 24/7 Scanner.' : '✅ Mô hình này đang được dùng cho bộ quét 24/7.')
                          : scannerModelId
                            ? (language === 'en' ? 'ℹ️ Scanner is running a different model.' : 'ℹ️ Bộ quét đang dùng mô hình khác.')
                            : (language === 'en' ? 'ℹ️ No frozen model attached to scanner.' : 'ℹ️ Bộ quét chưa cài mô hình đóng băng.')}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Live status rail */}
          <div className="header-status-rail flex min-w-0 flex-1 items-center gap-2 overflow-x-auto pb-0.5 lg:border-l lg:border-slate-800 lg:pl-4">
            <div className="inline-flex min-w-max items-center gap-1.5 rounded-full border border-emerald-800/60 bg-emerald-950/70 px-2.5 py-1 font-mono text-[10px] font-bold text-emerald-400">
              <Radio className="h-3 w-3 animate-pulse" />
              <span>{language === 'en' ? 'LIVE 24/7 SCANNER' : 'QUÉT 24/7 ĐANG CHẠY'}</span>
            </div>
            <div className="inline-flex min-w-max items-center gap-1 rounded-full bg-slate-800/80 px-2.5 py-1 font-mono text-[10px] text-slate-300">
              <span className="text-slate-500">{t('active_coins')}</span>
              <span className="font-bold text-amber-400">{status?.scanned_coins_count || 48}</span>
            </div>
            <div className="inline-flex min-w-max items-center gap-1.5 rounded-full border border-red-800/60 bg-red-950/70 px-2.5 py-1 font-mono text-[10px] font-bold text-red-400">
              <ShieldAlert className="h-3 w-3" />
              <span>{status?.active_signals_count || 6} {language === 'en' ? 'Alerts' : 'cảnh báo'}</span>
            </div>
            {autoTelegramEnabled && (
              <div className="inline-flex min-w-max items-center gap-1.5 rounded-full border border-sky-800/60 bg-sky-950/70 px-2.5 py-1 text-[10px] font-bold text-sky-400">
                <Send className="h-3 w-3 animate-pulse" />
                <span>{language === 'en' ? 'Auto Telegram ≥80%' : 'Tự động Telegram ≥80%'}</span>
              </div>
            )}
          </div>

          {/* Quick actions */}
          <div className="flex shrink-0 items-center justify-end gap-1.5">
            <div className="hidden md:block">{watchlistButton}</div>
            <button
              type="button"
              onClick={onOpenTracking}
              className="inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-sky-500/30 bg-sky-500/10 px-2 text-[11px] font-bold text-sky-300 transition hover:bg-sky-500/20 sm:px-2.5"
              title={language === 'en' ? 'Open tracking list' : 'Mở danh sách theo dõi tiến trình'}
            >
              <Eye className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{t('tracking')}</span>
              <span className="rounded-full bg-sky-500/20 px-1.5 font-mono">{trackingCount}</span>
            </button>
            <button
              type="button"
              onClick={onToggleActionDrawer}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border p-1.5 transition sm:w-auto sm:gap-1 sm:px-2 ${
                isActionDrawerOpen
                  ? 'border-amber-500/40 bg-amber-500/20 text-amber-400 hover:bg-amber-500/30'
                  : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-amber-400'
              }`}
              title={isActionDrawerOpen ? t('close_drawer') : t('open_drawer')}
            >
              {isActionDrawerOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRight className="h-3.5 w-3.5" />}
              <span className="hidden text-[10px] font-bold sm:inline">{language === 'en' ? 'Auto' : 'Tự động'}</span>
            </button>
            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 transition hover:bg-slate-700 hover:text-amber-400 disabled:opacity-50"
              title={t('refresh')}
              aria-label={t('refresh')}
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

            {/* Language Switcher Toggle Button */}
            <button
              type="button"
              onClick={toggleLanguage}
              className="inline-flex h-9 items-center justify-center gap-1 rounded-lg border border-amber-500/30 bg-slate-800 px-2 text-xs font-bold text-amber-300 shadow-sm transition hover:border-amber-400 hover:bg-slate-700 sm:px-2.5"
              title={language === 'vi' ? 'Switch to English' : 'Chuyển sang Tiếng Việt'}
              aria-label="Toggle language"
            >
              <Globe className="h-3.5 w-3.5 text-amber-400" />
              <span className="font-mono text-[11px] font-bold uppercase">{language === 'vi' ? '🇻🇳 VI' : '🇬🇧 EN'}</span>
            </button>
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
              <option value="CRITICAL">🔴 {language === 'en' ? 'Critical' : 'Cực Cao'}</option>
              <option value="HIGH">🟠 {language === 'en' ? 'High' : 'Cao'}</option>
              <option value="MEDIUM">🟡 {language === 'en' ? 'Medium' : 'Vừa'}</option>
              <option value="SAFE">🟢 {language === 'en' ? 'Safe' : 'An Toàn'}</option>
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
            <span>{language === 'en' ? 'Hotkeys:' : 'Phím tắt:'}</span>
            <kbd className="rounded border border-slate-800 bg-slate-950 px-1 py-0.5 text-slate-300">↑/↓</kbd>
            <span>{language === 'en' ? 'Navigate' : 'Chuyển coin'}</span>
            <kbd className="rounded border border-slate-800 bg-slate-950 px-1 py-0.5 text-slate-300">Space</kbd>
            <span>{language === 'en' ? 'Push Telegram' : 'Bắn Telegram'}</span>
          </div>
        </div>
      </div>
    </header>
  );
};

