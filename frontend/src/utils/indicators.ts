export function calculateEMA(data: Array<{ time: number; close: number }>, period: number) {
  if (!data || data.length === 0 || period <= 0) return [];
  
  const k = 2 / (period + 1);
  const result: Array<{ time: number; value: number }> = [];
  let sum = 0;
  
  for (let i = 0; i < data.length; i++) {
    if (i < period) {
      sum += data[i].close;
      if (i === period - 1) {
        result.push({ time: data[i].time, value: sum / period });
      }
    } else {
      const prevEma = result[result.length - 1].value;
      const ema = (data[i].close - prevEma) * k + prevEma;
      result.push({ time: data[i].time, value: ema });
    }
  }
  
  return result;
}
