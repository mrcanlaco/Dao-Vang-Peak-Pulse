import cmcSlugMapRaw from './cmc_slug_map.json';

const cmcSlugMap = cmcSlugMapRaw as Record<string, string>;

/**
 * Returns canonical CoinMarketCap URL for a token symbol or detail object.
 * Guarantee: NEVER throws, handles multiplier prefixes, aliases, and falls back
 * safely to Binance Futures trading link if no CMC slug exists.
 */
export const getCoinExternalUrl = (
  symbol: string,
  detail?: { cmc_url?: string | null; cmc_slug?: string | null } | null
): string => {
  if (detail?.cmc_url) {
    return detail.cmc_url;
  }
  if (detail?.cmc_slug) {
    return `https://coinmarketcap.com/currencies/${detail.cmc_slug}/`;
  }

  const s = (symbol || '').toUpperCase().trim();
  const clean = s
    .replace(/(USDT|USDC|BUSD|PERP)$/, '')
    .replace(/^(1000000|100000|10000|1000)/, '');

  const slug = cmcSlugMap[s] || cmcSlugMap[clean] || (clean ? clean.toLowerCase() : '');
  if (slug) {
    return `https://coinmarketcap.com/currencies/${slug}/`;
  }

  return `https://www.binance.com/en/futures/${s}`;
};
