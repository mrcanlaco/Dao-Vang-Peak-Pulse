import type { CoinSector, SignalItem } from '../types';

export const SECTOR_MAPPING: Record<string, CoinSector> = {
  // AI & Big Data
  FET: 'AI',
  AGIX: 'AI',
  OCEAN: 'AI',
  RENDER: 'AI',
  RNDR: 'AI',
  NEAR: 'AI',
  TAO: 'AI',
  WLD: 'AI',
  ARKM: 'AI',
  IO: 'AI',
  ATH: 'AI',
  GRT: 'AI',
  AI: 'AI',
  NFP: 'AI',
  PHB: 'AI',
  GLM: 'AI',
  ACT: 'AI',
  GOAT: 'AI',

  // Memecoins
  DOGE: 'MEME',
  SHIB: 'MEME',
  PEPE: 'MEME',
  WIF: 'MEME',
  FLOKI: 'MEME',
  BONK: 'MEME',
  BOME: 'MEME',
  MEME: 'MEME',
  POPCAT: 'MEME',
  NEIRO: 'MEME',
  TURBO: 'MEME',
  BRETT: 'MEME',
  PEOPLE: 'MEME',
  MYRO: 'MEME',
  MEW: 'MEME',
  SLERF: 'MEME',
  PONKE: 'MEME',
  DOGS: 'MEME',
  CHEEMS: 'MEME',
  PENGU: 'MEME',

  // Layer 1 / Layer 2
  BTC: 'L1_L2',
  ETH: 'L1_L2',
  SOL: 'L1_L2',
  BNB: 'L1_L2',
  ADA: 'L1_L2',
  AVAX: 'L1_L2',
  SUI: 'L1_L2',
  APT: 'L1_L2',
  ARB: 'L1_L2',
  OP: 'L1_L2',
  MATIC: 'L1_L2',
  POL: 'L1_L2',
  SEI: 'L1_L2',
  TIA: 'L1_L2',
  FTM: 'L1_L2',
  SONIC: 'L1_L2',
  DOT: 'L1_L2',
  ATOM: 'L1_L2',
  TRX: 'L1_L2',
  TON: 'L1_L2',
  KAS: 'L1_L2',
  STX: 'L1_L2',
  ALGO: 'L1_L2',
  VET: 'L1_L2',
  HBAR: 'L1_L2',
  ZRO: 'L1_L2',
  STRK: 'L1_L2',
  MANTA: 'L1_L2',
  BLAST: 'L1_L2',
  ZK: 'L1_L2',
  SC: 'L1_L2',
  ENA: 'L1_L2',

  // DeFi & Derivatives
  UNI: 'DEFI',
  AAVE: 'DEFI',
  MKR: 'DEFI',
  CRV: 'DEFI',
  LDO: 'DEFI',
  PENDLE: 'DEFI',
  JUP: 'DEFI',
  CAKE: 'DEFI',
  INJ: 'DEFI',
  RUNE: 'DEFI',
  SNX: 'DEFI',
  DYDX: 'DEFI',
  GMX: 'DEFI',
  COMP: 'DEFI',
  SUSHI: 'DEFI',
  RAY: 'DEFI',
  ORCA: 'DEFI',
  ONDO: 'DEFI',
  RSR: 'DEFI',
  COW: 'DEFI',

  // GameFi & Metaverse & NFT
  AXS: 'GAMEFI',
  SAND: 'GAMEFI',
  MANA: 'GAMEFI',
  GALA: 'GAMEFI',
  BEAM: 'GAMEFI',
  PIXEL: 'GAMEFI',
  NOT: 'GAMEFI',
  ILV: 'GAMEFI',
  IMX: 'GAMEFI',
  ENJ: 'GAMEFI',
  YGG: 'GAMEFI',
  BIGTIME: 'GAMEFI',
  RONIN: 'GAMEFI',
  ALICE: 'GAMEFI',
  SUPER: 'GAMEFI',
  PORTAL: 'GAMEFI',
  HMSTR: 'GAMEFI',
};

export const TOP_CAP_SYMBOLS = new Set([
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX',
  'LINK', 'SHIB', 'SUI', 'DOT', 'TRX', 'TON', 'NEAR', 'BCH',
  'LTC', 'PEPE', 'APT', 'XLM', 'HBAR', 'UNI'
]);

export const LARGE_CAP_LOOKUP: Record<string, number> = {
  BTC: 1_300_000_000_000,
  ETH: 350_000_000_000,
  SOL: 85_000_000_000,
  BNB: 90_000_000_000,
  XRP: 140_000_000_000,
  DOGE: 35_000_000_000,
  ADA: 28_000_000_000,
  AVAX: 12_000_000_000,
  SUI: 10_000_000_000,
  LINK: 11_000_000_000,
  SHIB: 15_000_000_000,
  TON: 16_000_000_000,
  TRX: 18_000_000_000,
  DOT: 9_000_000_000,
  NEAR: 7_500_000_000,
  BCH: 9_500_000_000,
  LTC: 8_000_000_000,
  XLM: 12_000_000_000,
  HBAR: 11_000_000_000,
  PEPE: 8_500_000_000,
  APT: 6_500_000_000,
};

export const MID_CAP_LOOKUP: Record<string, number> = {
  UNI: 4_800_000_000,
  FET: 3_500_000_000,
  RENDER: 3_200_000_000,
  TAO: 4_200_000_000,
  WIF: 2_800_000_000,
  AAVE: 2_500_000_000,
  MKR: 1_800_000_000,
  ARB: 2_100_000_000,
  OP: 1_900_000_000,
  TIA: 1_600_000_000,
  SEI: 1_700_000_000,
  INJ: 2_200_000_000,
  FLOKI: 2_100_000_000,
  BONK: 2_400_000_000,
  PENDLE: 1_200_000_000,
  ENA: 1_500_000_000,
  JUP: 1_800_000_000,
  RUNE: 1_600_000_000,
  ICP: 4_500_000_000,
  FIL: 3_100_000_000,
  ETC: 3_800_000_000,
  KAS: 3_400_000_000,
  STX: 2_900_000_000,
  BEAM: 1_100_000_000,
  GALA: 1_300_000_000,
  SAND: 1_400_000_000,
  MANA: 1_200_000_000,
  CRV: 1_100_000_000,
  LDO: 1_700_000_000,
  ALGO: 2_500_000_000,
  VET: 3_200_000_000,
  ATOM: 2_100_000_000,
  POL: 3_900_000_000,
  WLD: 2_600_000_000,
  POPCAT: 1_400_000_000,
  THETA: 1_800_000_000,
};

export const getCleanSymbol = (symbol: string): string => {
  return (symbol || '')
    .toUpperCase()
    .replace('USDT', '')
    .replace('BUSD', '')
    .replace('USDC', '')
    .replace('PERP', '')
    .trim();
};

export const getCoinSector = (symbol: string): CoinSector => {
  const clean = getCleanSymbol(symbol);
  if (SECTOR_MAPPING[clean]) {
    return SECTOR_MAPPING[clean];
  }
  if (TOP_CAP_SYMBOLS.has(clean)) {
    return 'TOP_CAP';
  }
  return 'OTHER';
};

export const formatMarketCap = (mcapUsd: number): string => {
  if (!mcapUsd || mcapUsd <= 0) return 'N/A';
  if (mcapUsd >= 1_000_000_000_000) {
    return `$${(mcapUsd / 1_000_000_000_000).toFixed(2)}T`;
  }
  if (mcapUsd >= 1_000_000_000) {
    return `$${(mcapUsd / 1_000_000_000).toFixed(1)}B`;
  }
  if (mcapUsd >= 1_000_000) {
    return `$${(mcapUsd / 1_000_000).toFixed(0)}M`;
  }
  return `$${mcapUsd.toLocaleString()}`;
};

export const getCoinMarketCapInfo = (
  symbol: string,
  existingSignal?: Partial<SignalItem> | null
): { market_cap_usd: number; market_cap_str: string; market_cap_tier: 'LARGE' | 'MID' | 'SMALL' } => {
  if (existingSignal?.market_cap_usd && existingSignal.market_cap_tier) {
    const tier = (existingSignal.market_cap_tier.toUpperCase() === 'LARGE' || existingSignal.market_cap_tier.toUpperCase() === 'MEGA')
      ? 'LARGE'
      : existingSignal.market_cap_tier.toUpperCase() === 'MID'
      ? 'MID'
      : 'SMALL';
    return {
      market_cap_usd: existingSignal.market_cap_usd,
      market_cap_str: existingSignal.market_cap_str || formatMarketCap(existingSignal.market_cap_usd),
      market_cap_tier: tier,
    };
  }

  const clean = getCleanSymbol(symbol);
  if (LARGE_CAP_LOOKUP[clean]) {
    const val = LARGE_CAP_LOOKUP[clean];
    return {
      market_cap_usd: val,
      market_cap_str: formatMarketCap(val),
      market_cap_tier: 'LARGE',
    };
  }
  if (MID_CAP_LOOKUP[clean]) {
    const val = MID_CAP_LOOKUP[clean];
    return {
      market_cap_usd: val,
      market_cap_str: formatMarketCap(val),
      market_cap_tier: 'MID',
    };
  }

  const defaultLowcap = 85_000_000;
  return {
    market_cap_usd: defaultLowcap,
    market_cap_str: '',
    market_cap_tier: 'SMALL',
  };
};

export const getSectorBadgeConfig = (
  sector: CoinSector,
  language: string = 'vi'
): { label: string; icon: string; className: string } => {
  switch (sector) {
    case 'AI':
      return {
        label: language === 'vi' ? 'AI' : 'AI Tech',
        icon: '🤖',
        className: 'bg-violet-950/80 text-violet-300 border-violet-700/60',
      };
    case 'MEME':
      return {
        label: language === 'vi' ? 'Meme' : 'Meme',
        icon: '🐸',
        className: 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60',
      };
    case 'L1_L2':
      return {
        label: language === 'vi' ? 'L1/L2' : 'L1 / L2',
        icon: '⚡',
        className: 'bg-sky-950/80 text-sky-300 border-sky-700/60',
      };
    case 'DEFI':
      return {
        label: language === 'vi' ? 'DeFi' : 'DeFi',
        icon: '🏦',
        className: 'bg-amber-950/80 text-amber-300 border-amber-700/60',
      };
    case 'GAMEFI':
      return {
        label: language === 'vi' ? 'GameFi' : 'GameFi',
        icon: '🎮',
        className: 'bg-pink-950/80 text-pink-300 border-pink-700/60',
      };
    case 'TOP_CAP':
      return {
        label: language === 'vi' ? 'Top Cap' : 'Top Cap',
        icon: '👑',
        className: 'bg-amber-900/60 text-amber-200 border-amber-600/70',
      };
    default:
      return {
        label: language === 'vi' ? 'Altcoin' : 'Altcoin',
        icon: '🪙',
        className: 'bg-slate-800 text-slate-400 border-slate-700/60',
      };
  }
};

export const getMarketCapBadgeConfig = (
  tier: string,
  mcapStr?: string | null,
  language: string = 'vi'
): { label: string; icon: string; className: string } => {
  const normTier = (tier || 'SMALL').toUpperCase();
  if (normTier === 'LARGE' || normTier === 'MEGA') {
    return {
      label: mcapStr ? mcapStr : (language === 'vi' ? 'Vốn hóa lớn' : 'Large Cap'),
      icon: '👑',
      className: 'bg-blue-950/70 text-blue-300 border-blue-700/50',
    };
  }
  if (normTier === 'MID') {
    return {
      label: mcapStr ? mcapStr : (language === 'vi' ? 'Vốn hóa vừa' : 'Mid Cap'),
      icon: '⚡',
      className: 'bg-indigo-950/70 text-indigo-300 border-indigo-700/50',
    };
  }
  return {
    label: mcapStr ? mcapStr : (language === 'vi' ? 'Vốn hóa nhỏ' : 'Small Cap'),
    icon: '💎',
    className: 'bg-teal-950/70 text-teal-300 border-teal-700/50',
  };
};
