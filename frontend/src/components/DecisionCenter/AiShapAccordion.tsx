import React, { useState } from 'react';
import { AlertOctagon, ChevronDown, ChevronUp, Layers } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type { DeepAnalysis, ShapDriver } from '../../types';

interface AiShapAccordionProps {
  shapDrivers: ShapDriver[];
  deepAnalysis?: DeepAnalysis | null;
}

export const AiShapAccordion: React.FC<AiShapAccordionProps> = ({
  shapDrivers,
  deepAnalysis,
}) => {
  const { language } = useTranslation();
  
  const [isExpanded, setIsExpanded] = useState(false);

  const sortedDrivers = [...shapDrivers].sort((a, b) => b.impact_score - a.impact_score);
  const top3Drivers = sortedDrivers.slice(0, 3);
  const components = deepAnalysis?.components || [];
  const sortedComponents = [...components].sort((a, b) => b.weighted_score - a.weighted_score);

  return (
    <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 sm:p-3.5 shadow-md space-y-3 min-w-0">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <AlertOctagon className="w-4 h-4 text-amber-400" />
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            {t('ws_risk_drivers_title')}
          </h3>
        </div>
        <span className="text-[10px] text-slate-400 font-mono">
          {sortedDrivers.length} {t('ws_risk_drivers_factors')}
        </span>
      </div>

      {/* Top 3 Drivers View */}
      {sortedDrivers.length === 0 ? (
        <div className="p-3 text-center text-[11px] text-slate-500 bg-slate-900/60 rounded-lg border border-slate-800">
          {t('ws_risk_drivers_empty')}
        </div>
      ) : (
        <div className="space-y-2">
          {top3Drivers.map((driver, idx) => {
            const impactPct = Math.min(100, driver.impact_score * 100);
            const isHigh = driver.impact_score >= 0.5;
            const isMed = driver.impact_score >= 0.2 && !isHigh;
            return (
              <div key={idx} className="bg-slate-900/90 p-2.5 rounded-lg border border-slate-800">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold shrink-0 ${
                      isHigh ? 'bg-red-950 text-red-300 border border-red-800' :
                      isMed ? 'bg-amber-950 text-amber-300 border border-amber-800' :
                      'bg-slate-800 text-slate-400'
                    }`}>
                      #{idx + 1}
                    </span>
                    <div className="min-w-0 truncate">
                      <div className="text-xs font-bold text-slate-200 truncate">{driver.feature}</div>
                      <div className="text-[10px] text-slate-400 truncate">{driver.description}</div>
                    </div>
                  </div>
                  <span className={`px-2 py-0.5 font-mono font-bold text-xs rounded border shrink-0 ${
                    isHigh ? 'bg-red-950 border-red-800 text-red-400' :
                    isMed ? 'bg-amber-950 border-amber-800 text-amber-400' :
                    'bg-slate-800 border-slate-700 text-slate-400'
                  }`}>
                    +{(driver.impact_score * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      isHigh ? 'bg-gradient-to-r from-red-600 to-red-400' :
                      isMed ? 'bg-gradient-to-r from-amber-600 to-amber-400' :
                      'bg-slate-600'
                    }`}
                    style={{ width: `${impactPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Accordion Toggle for 8-Component Breakdown */}
      {components.length > 0 && (
        <div className="pt-1">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="w-full py-2 px-3 bg-slate-900 hover:bg-slate-850 border border-slate-800 hover:border-slate-700 rounded-lg text-xs font-medium text-amber-400/90 flex items-center justify-between transition"
          >
            <span className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-amber-400" />
              {isExpanded
                ? (language === 'zh' ? '收起 8 因子得分分解' : language === 'ko' ? '8개 요인 점수 분해 접기' : language === 'en' ? 'Collapse 8-Component Score Breakdown' : 'Thu gọn bảng phân rã 8 thành phần') : (language === 'zh' ? '展开完整 8 因子归因分解' : language === 'ko' ? '전체 8개 요인 분해 펼치기' : language === 'en' ? 'Expand Full 8-Component Decomposition' : 'Xem chi tiết phân rã toàn diện 8 thành phần')}
            </span>
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {/* Expanded 8 Components */}
          {isExpanded && (
            <div className="mt-2.5 space-y-2 animate-fadeIn">
              <div className="flex items-center justify-between px-1 text-[10px] text-slate-400">
                <span>{language === 'zh' ? '因子 / 特征分项' : language === 'ko' ? '지표 성분 / 요인' : language === 'en' ? 'Component / Factor' : 'Thành phần chỉ số'}</span>
                <span>{language === 'zh' ? '权重 → 贡献得分' : language === 'ko' ? '가중치 → 기여 점수' : language === 'en' ? 'Weight → Contribution' : 'Trọng số → Điểm đóng góp'}</span>
              </div>
              {sortedComponents.map((comp, idx) => (
                <div key={idx} className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold shrink-0 ${
                        comp.weighted_score >= 10 ? 'bg-red-950 text-red-300 border border-red-800' :
                        comp.weighted_score >= 5 ? 'bg-amber-950 text-amber-300 border border-amber-800' :
                        'bg-slate-800 text-slate-400'
                      }`}>
                        {idx + 1}
                      </span>
                      <div className="min-w-0">
                        <span className="text-xs font-bold text-slate-200">{comp.name}</span>
                        <span className="text-[9px] text-slate-500 font-mono ml-1.5">
                          ({comp.weight}% {language === 'zh' ? '权重' : language === 'ko' ? '가중치' : language === 'en' ? 'weight' : 'trọng số'})
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs font-mono shrink-0">
                      <span className="text-slate-400">{comp.score}/100</span>
                      <span className={`font-bold ${
                        comp.weighted_score >= 10 ? 'text-red-400' :
                        comp.weighted_score >= 5 ? 'text-amber-400' : 'text-slate-400'
                      }`}>
                        → {comp.weighted_score > 0 ? '+' : ''}{comp.weighted_score.toFixed(1)}
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden mb-1">
                    <div
                      className={`h-full rounded-full transition-all ${
                        comp.score >= 60 ? 'bg-gradient-to-r from-red-600 to-red-400' :
                        comp.score >= 30 ? 'bg-gradient-to-r from-amber-600 to-amber-400' : 'bg-slate-600'
                      }`}
                      style={{ width: `${comp.score}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-slate-500 leading-tight">{comp.explanation}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
