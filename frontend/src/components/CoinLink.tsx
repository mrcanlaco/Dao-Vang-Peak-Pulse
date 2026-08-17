import React from 'react';
import { useTranslation } from '../i18n/LanguageContext';

interface CoinLinkProps {
  symbol: string;
  onClick: (symbol: string) => void;
  className?: string;
}

export const CoinLink: React.FC<CoinLinkProps> = ({ symbol, onClick, className = '' }) => {
  const { language } = useTranslation();

  const getTitle = () => {
    if (language === 'zh') return `查看 ${symbol} 的深度分析`;
    if (language === 'ko') return `${symbol} 정밀 분석 보기`;
    if (language === 'en') return `View detailed analysis for ${symbol}`;
    return `Xem phân tích chi tiết ${symbol}`;
  };

  return (
    <a
      href={`#coin=${encodeURIComponent(symbol)}`}
      onClick={(e) => {
        e.stopPropagation();
        window.location.hash = `#coin=${encodeURIComponent(symbol)}`;
        onClick(symbol);
      }}
      className={`inline-block font-mono font-bold text-amber-400 hover:text-amber-300 hover:underline cursor-pointer transition ${className}`}
      title={getTitle()}
    >
      {symbol}
    </a>
  );
};
