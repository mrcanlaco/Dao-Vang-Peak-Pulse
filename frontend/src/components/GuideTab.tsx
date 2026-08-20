import React from 'react';
import { BookOpen, Terminal, AlertTriangle, Workflow, Bug } from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';

export const GuideTab: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
        <BookOpen className="w-3.5 h-3.5 text-amber-400" />
        {t('guide_title')}
      </h3>

      {/* Quick Start */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2">
          {t('guide_overview_title')}
        </h4>
        <ol className="text-[11px] text-slate-300 space-y-1.5 list-decimal list-inside">
          <li>
            <strong className="text-slate-100">{t('guide_radar_title')}</strong>: {t('guide_radar_desc')}
          </li>
          <li>
            <strong className="text-slate-100">{t('guide_workspace_title')}</strong>: {t('guide_workspace_desc')}
          </li>
          <li>
            <strong className="text-slate-100">{t('guide_candidates_title')}</strong>: {t('guide_candidates_desc')}
          </li>
          <li>
            <strong className="text-slate-100">{t('guide_multiscan_title')}</strong>: {t('guide_multiscan_desc')}
          </li>
          <li>
            <strong className="text-slate-100">{t('guide_backtest_title')}</strong>: {t('guide_backtest_desc')}
          </li>
          <li>
            <strong className="text-slate-100">{t('guide_forward_title')}</strong>: {t('guide_forward_desc')}
          </li>
          <li>
            <strong className="text-slate-100">{t('guide_market_title')}</strong>: {t('guide_market_desc')}
          </li>
          <li>
            <strong className="text-slate-100">{t('guide_system_audits_title')}</strong>: {t('guide_system_audits_desc')}
          </li>
        </ol>
      </div>

      {/* Tabs explanation */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Workflow className="w-3.5 h-3.5" /> {t('guide_main_modules_title')}
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-emerald-400">{t('guide_decision_module_title')}</strong>
            <p className="text-slate-400 mt-0.5">
              {t('guide_decision_module_desc')}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-violet-400">{t('guide_candidate_module_title')}</strong>
            <p className="text-slate-400 mt-0.5">
              {t('guide_candidate_module_desc')}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-purple-400">{t('guide_backtest_module_title')}</strong>
            <p className="text-slate-400 mt-0.5">
              {t('guide_backtest_module_desc')}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-sky-400">{t('guide_forward_module_title')}</strong>
            <p className="text-slate-400 mt-0.5">
              {t('guide_forward_module_desc')}
            </p>
          </div>
        </div>
      </div>

      {/* CLI */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5" /> {t('guide_cli_title')}
        </h4>
        <div className="space-y-1.5 text-[11px] font-mono">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang scanner start</span>
            <span className="text-slate-400"> — {t('guide_cli_start_desc')}</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang scanner stop</span>
            <span className="text-slate-400"> — {t('guide_cli_stop_desc')}</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang experiment run</span>
            <span className="text-slate-400"> — {t('guide_cli_exp_desc')}</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang data collect</span>
            <span className="text-slate-400"> — {t('guide_cli_data_desc')}</span>
          </div>
        </div>
      </div>

      {/* Troubleshooting */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Bug className="w-3.5 h-3.5" /> {t('guide_trouble_title')}
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">{t('guide_trouble_no_signals_q')}</strong>
            <p className="text-slate-400 mt-0.5">
              {t('guide_trouble_no_signals_a')}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">{t('guide_trouble_telegram_q')}</strong>
            <p className="text-slate-400 mt-0.5">
              {t('guide_trouble_telegram_a')}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-3 text-[11px] text-amber-300 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          <strong>{t('guide_important_notice_title')}</strong>{' '}
          {t('guide_important_notice_desc')}
        </div>
      </div>
    </div>
  );
};
