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
} from 'lucide-react';
import { getRiskLabel, getScanModeLabel } from '../i18n/translations';

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
  const { language, setLanguage, t } = useTranslation();
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const selectedModel = availableModels.find((model) => model.key === selectedModelKey);
  const isScannerActive = Boolean(scannerModelId && selectedModel?.frozen_model_id === scannerModelId);

  const currentLangObj = LANGUAGES.find((l) => l.code === language) || LANGUAGES[0];

  const scanLabel = activeScanMode
    .split(' + ')
    .map((mode) => getScanModeLabel(mode, language))
    .join(' + ');

  const getModelLabel = (label?: string) => {
    if (!label) {
      if (language === 'zh') return '选择 AI 模型';
      if (language === 'ko') return 'AI 모델 선택';
      if (language === 'en') return 'Select AI Model';
      return 'Chọn mô hình AI';
    }
    if (language === 'en') {
      return label
        .replace('Heuristic 0-100 (mặc định)', 'Heuristic 0–100 (Default)')
        .replace('Logistic Regression Walk-forward', 'Logistic Regression (Walk-forward)')
        .replace(/^Frozen LR/, 'Frozen Logistic Regression');
    }
    if (language === 'zh') {
      return label
        .replace('Heuristic 0-100 (mặc định)', '规则基准打分 0–100 (默认)')
        .replace('Logistic Regression Walk-forward', '逻辑回归 (时间序列推进)')
        .replace(/^Frozen LR/, '已冻结逻辑回归模型');
    }
    if (language === 'ko') {
      return label
        .replace('Heuristic 0-100 (mặc định)', '휴리스틱 점수 0–100 (기본)')
        .replace('Logistic Regression Walk-forward', '로지스틱 회귀 (전진 검증)')
        .replace(/^Frozen LR/, '동결된 로지스틱 회귀');
    }
    return label
      .replace('Heuristic 0-100 (mặc định)', 'Chấm điểm quy tắc 0–100 (mặc định)')
      .replace('Logistic Regression Walk-forward', 'Hồi quy logistic theo thời gian')
      .replace(/^Frozen LR/, 'Hồi quy logistic đã đóng băng');
  };

  const getModelDescription = (description?: string) => {
    if (!description) return '';
    if (language === 'en') return description;
    if (language === 'zh') {
      return description
        .replace(/Logistic Regression/g, '逻辑回归')
        .replace(/rule-based/g, '基于规则')
        .replace(/funding spike/g, '资金费率异动')
        .replace(/price-volume/g, '量价形态')
        .replace(/backtest/g, '历史回测')
        .replace(/baseline/g, '基准')
        .replace(/Train cutoff/g, '训练集截止日期');
    }
    if (language === 'ko') {
      return description
        .replace(/Logistic Regression/g, '로지스틱 회귀')
        .replace(/rule-based/g, '규칙 기반')
        .replace(/funding spike/g, '펀딩비 급변')
        .replace(/price-volume/g, '가격-거래량')
        .replace(/backtest/g, '백테스트')
        .replace(/baseline/g, '기준선')
        .replace(/Train cutoff/g, '학습 기준일');
    }
    return description
      .replace(/Logistic Regression/g, 'Hồi quy logistic')
      .replace(/rule-based/g, 'theo quy tắc')
      .replace(/funding spike/g, 'tăng đột biến funding')
      .replace(/price-volume/g, 'giá-khối lượng')
      .replace(/backtest/g, 'kiểm thử lịch sử')
      .replace(/baseline/g, 'mốc chuẩn')
      .replace(/Train cutoff/g, 'Mốc cắt huấn luyện');
  };

  const getScanTargetTooltip = () => {
    if (language === 'zh') return '选择扫描币种范围';
    if (language === 'ko') return '스캔 대상 코인 선택';
    if (language === 'en') return 'Select coins to scan';
    return 'Chọn danh sách coin để quét';
  };

  const getScanTargetPrefix = () => {
    if (language === 'zh') return '扫描目标: ';
    if (language === 'ko') return '스캔 대상: ';
    if (language === 'en') return 'Scan Target: ';
    return 'Danh sách quét: ';
  };

  const watchlistButton = (
    <button
      type="button"
      onClick={onOpenWatchlistModal}
      className="header-scan-button inline-flex w-full min-w-0 items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-amber-600 px-3 py-2 text-xs font-bold text-slate-950 shadow-md shadow-amber-500/15 transition hover:from-amber-400 hover:to-amber-500 md:w-auto"
      title={getScanTargetTooltip()}
    >
      <Target className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate whitespace-nowrap">
        {getScanTargetPrefix()}
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
              title={language === 'en' ? 'Go to Home' : language === 'zh' ? '返回首页' : language === 'ko' ? '홈으로' : 'Về trang chủ'}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-amber-700 text-lg font-bold text-slate-950 shadow-lg shadow-amber-500/20 transition group-hover:scale-105 sm:h-10 sm:w-10">
                🪙
              </div>
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-400/80">
                  {language === 'en' ? 'PeakPulse AI' : language === 'zh' ? '刀锋 PeakPulse AI' : language === 'ko' ? '피크펄스 AI' : 'Đảo Vàng AI'}
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
                  title={getModelDescription(selectedModel?.description) || getModelLabel(undefined)}
                >
                  <Cpu className="h-3 w-3 shrink-0" />
                  <span className="truncate">{getModelLabel(selectedModel?.label)}</span>
                  {isScannerActive && (
                    <span
                      className="text-emerald-400"
                      title={language === 'en' ? 'Running on 24/7 Scanner' : language === 'zh' ? '24/7 扫描器运行中' : language === 'ko' ? '24/7 스캐너 가동 중' : 'Đang dùng cho bộ quét 24/7'}
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
                        🧠 {getModelLabel(undefined)}
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
                            <span className="text-xs font-bold">{getModelLabel(model.label)}</span>
                            {scannerModelId && model.frozen_model_id === scannerModelId && (
                              <span className="rounded bg-emerald-950 px-1 py-0.5 text-[9px] font-bold text-emerald-400">
                                {language === 'en' ? 'SCANNER' : language === 'zh' ? '当前扫描器' : language === 'ko' ? '스캐너 적용' : 'BỘ QUÉT'}
                              </span>
                            )}
                          </div>
                          {model.description && (
                            <span className="mt-0.5 text-[10px] text-slate-400">
                              {getModelDescription(model.description)}
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
                <span>Telegram Auto</span>
              </span>
            )}

            {(status?.scanner_status === 'ONLINE' || status?.scanner_status === 'ACTIVE') && (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-400">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                <span>{language === 'en' ? 'Online 24/7' : language === 'zh' ? '24/7 在线' : language === 'ko' ? '24/7 온라인' : 'Trực tuyến 24/7'}</span>
              </span>
            )}
          </div>

          {/* Header Action buttons */}
          <div className="flex items-center justify-end gap-2 lg:shrink-0">
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
                {isActionDrawerOpen
                  ? (language === 'en' ? 'Close' : language === 'zh' ? '关闭' : language === 'ko' ? '닫기' : 'Đóng')
                  : (language === 'en' ? 'Smart Action' : language === 'zh' ? '智能面板' : language === 'ko' ? '제어 패널' : 'Bảng lệnh')}
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
            <span>{language === 'en' ? 'Hotkeys:' : language === 'zh' ? '快捷键:' : language === 'ko' ? '단축키:' : 'Phím tắt:'}</span>
            <kbd className="rounded border border-slate-800 bg-slate-950 px-1 py-0.5 text-slate-300">↑/↓</kbd>
            <span>{language === 'en' ? 'Navigate' : language === 'zh' ? '切换币种' : language === 'ko' ? '코인 이동' : 'Chuyển coin'}</span>
            <kbd className="rounded border border-slate-800 bg-slate-950 px-1 py-0.5 text-slate-300">Space</kbd>
            <span>{language === 'en' ? 'Push Telegram' : language === 'zh' ? '发送 Telegram' : language === 'ko' ? '텔레그램 발송' : 'Bắn Telegram'}</span>
          </div>
        </div>
      </div>
    </header>
  );
};
