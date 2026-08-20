import React from 'react';
import { useTranslation } from '../i18n/LanguageContext';

interface CoinLinkProps {
  symbol: string;
  onClick: (symbol: string) => void;
  className?: string;
}

export const CoinLink: React.FC<CoinLinkProps> = ({ symbol, onClick, className = '' }) => {
  const { t } = useTranslation();

  const getTitle = () => {
    return t('coin_link_view_details').replace('{symbol}', symbol);
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
