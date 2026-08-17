export const SYSTEM_TIME_ZONE = 'Asia/Ho_Chi_Minh';
export const SYSTEM_TIME_ZONE_LABEL = 'Hà Nội / Hồ Chí Minh (UTC+7)';

export const getSystemTimeZoneLabel = (lang?: string): string => {
  if (lang === 'en') return 'Hanoi / HCMC (UTC+7)';
  if (lang === 'zh') return '河内/胡志明市 (UTC+7)';
  if (lang === 'ko') return '하노이/호치민 (UTC+7)';
  return 'Hà Nội / Hồ Chí Minh (UTC+7)';
};

/**
 * Parse API timestamps without ever falling back to the browser's timezone.
 * Legacy naive values are storage timestamps and therefore represent UTC.
 */
export const parseSystemDate = (value?: string | null): Date | null => {
  if (!value) return null;
  const normalized = value.trim()
    .replace(/\s+UTC\+7$/i, '+07:00')
    .replace(/\s+UTC(?:\+0)?$/i, 'Z')
    .replace(' ', 'T');
  if (!normalized) return null;
  const withTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)
    ? normalized
    : `${normalized}Z`;
  const parsed = new Date(withTimezone);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

export const formatSystemDateTime = (value?: string | null): string => {
  const parsed = parseSystemDate(value);
  if (!parsed) return value ? value.slice(0, 19).replace('T', ' ') : '—';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: SYSTEM_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(parsed).reduce<Record<string, string>>((result, part) => {
    result[part.type] = part.value;
    return result;
  }, {});
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
};

export const formatSystemTime = (value?: string | null): string => {
  const parsed = parseSystemDate(value);
  if (!parsed) return value ? value.slice(0, 8) : '—';
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: SYSTEM_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(parsed);
};
