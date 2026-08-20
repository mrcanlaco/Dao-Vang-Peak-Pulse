import React from 'react';
import { Radio, BarChart3, Target, Eye, Wrench } from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';

export type MobileTabType = 'RADAR' | 'ANALYSIS' | 'ORDER' | 'TRACKING' | 'TOOLS';

interface MobileBottomNavProps {
  activeTab: MobileTabType;
  onSelectTab: (tab: MobileTabType) => void;
  signalCount?: number;
  selectedSymbol?: string | null;
  trackingCount?: number;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  activeTab,
  onSelectTab,
  signalCount = 0,
  selectedSymbol = null,
  trackingCount = 0,
}) => {
  const { t } = useTranslation();

  const navItems: Array<{
    id: MobileTabType;
    label: string;
    icon: React.ElementType;
    badge?: string | number | null;
    badgeColor?: string;
  }> = [
    {
      id: 'RADAR',
      label: t('mobile_nav_radar'),
      icon: Radio,
      badge: signalCount > 0 ? signalCount : null,
      badgeColor: 'bg-red-500 text-white',
    },
    {
      id: 'ANALYSIS',
      label: t('mobile_nav_analysis'),
      icon: BarChart3,
      badge: selectedSymbol ? selectedSymbol.replace('USDT', '') : null,
      badgeColor: 'bg-amber-500/90 text-slate-950 font-black',
    },
    {
      id: 'ORDER',
      label: t('mobile_nav_order'),
      icon: Target,
      badge: null,
    },
    {
      id: 'TRACKING',
      label: t('mobile_nav_tracking'),
      icon: Eye,
      badge: trackingCount > 0 ? trackingCount : null,
      badgeColor: 'bg-sky-500 text-slate-950 font-bold',
    },
    {
      id: 'TOOLS',
      label: t('mobile_nav_tools'),
      icon: Wrench,
      badge: null,
    },
  ];

  return (
    <nav
      aria-label="Mobile Bottom Navigation"
      className="fixed bottom-0 left-0 right-0 z-40 bg-slate-950/95 backdrop-blur-lg border-t border-slate-800/90 px-1 py-1 sm:hidden pb-safe"
    >
      <div className="grid grid-cols-5 gap-0.5 items-center justify-around">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`relative flex flex-col items-center justify-center py-1.5 px-1 rounded-xl transition-all duration-200 ${
                isActive
                  ? 'text-amber-400 bg-amber-500/10'
                  : 'text-slate-400 hover:text-slate-200 active:bg-slate-900'
              }`}
            >
              <div className="relative">
                <Icon className={`w-5 h-5 transition-transform duration-200 ${isActive ? 'scale-110 stroke-[2.5]' : 'stroke-[1.75]'}`} />
                {item.badge !== null && item.badge !== undefined && (
                  <span
                    className={`absolute -top-1.5 -right-2 px-1 min-w-[15px] h-[15px] flex items-center justify-center text-[9px] font-mono font-bold rounded-full shadow-sm ${
                      item.badgeColor || 'bg-amber-500 text-slate-950'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </div>
              <span className={`text-[10px] tracking-tight mt-0.5 font-medium leading-none ${isActive ? 'text-amber-300 font-bold' : ''}`}>
                {item.label}
              </span>
              {isActive && (
                <span className="w-1 h-1 rounded-full bg-amber-400 mt-0.5" />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};
