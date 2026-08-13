import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
} from 'lightweight-charts';
import { Camera, ChevronDown, Crosshair, Filter, Grid3X3, Maximize2, Minimize2, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { formatSystemDateTime, parseSystemDate, SYSTEM_TIME_ZONE } from '../utils/time';

type AlertVisibilityMode = 'hidden' | 'latest' | 'all' | 'valid';

const alertVisibilityOptions: Array<{ value: AlertVisibilityMode; label: string; hint: string }> = [
  { value: 'hidden', label: 'Ẩn cảnh báo', hint: 'Không vẽ điểm đánh dấu trên biểu đồ' },
  { value: 'latest', label: 'Chỉ gần nhất', hint: 'Chỉ cảnh báo mới nhất' },
  { value: 'all', label: 'Hiển thị tất cả', hint: 'Toàn bộ lịch sử cảnh báo' },
  { value: 'valid', label: 'Còn hiệu lực', hint: 'Chưa hết thời gian hiệu lực' },
];

export interface CandlestickSignalMarker {
  id?: string;
  time: string;
  probability?: number | null;
  isActive?: boolean;
  isValid?: boolean;
}

interface CandlestickChartProps {
  data: Array<{
    time: number | string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
  }>;
  targetPrice?: number;
  height?: number;
  signalMarkers?: CandlestickSignalMarker[];
  // Kept as a fallback for callers that only have one signal.
  signalTime?: string;
  signalProbability?: number | null;
}

export const CandlestickChart: React.FC<CandlestickChartProps> = ({
  data,
  targetPrice,
  height = 400,
  signalMarkers: signalMarkerInputs,
  signalTime,
  signalProbability,
}) => {
  const chartShellRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const alertMenuRef = useRef<HTMLDivElement>(null);
  const [crosshairMode, setCrosshairMode] = useState<'magnet' | 'normal' | 'hidden'>('magnet');
  const [gridVisible, setGridVisible] = useState(true);
  const [priceAutoScale, setPriceAutoScale] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [alertVisibility, setAlertVisibility] = useState<AlertVisibilityMode>('all');
  const [alertMenuOpen, setAlertMenuOpen] = useState(false);

  const formatSignalTime = (time: string, compact = false): string => {
    if (/^\d{2}:\d{2}$/.test(time)) return time;

    // Always render chart annotations in the application's Vietnam timezone.
    const parsed = parseSystemDate(time);
    if (!parsed) return time;

    return new Intl.DateTimeFormat('vi-VN', compact ? {
      timeZone: SYSTEM_TIME_ZONE,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    } : {
      timeZone: SYSTEM_TIME_ZONE,
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(parsed);
  };

  const allSignalMarkers = useMemo<CandlestickSignalMarker[]>(() => (
    signalMarkerInputs?.length
      ? signalMarkerInputs
      : signalTime
        ? [{ time: signalTime, probability: signalProbability }]
        : []
  ), [signalMarkerInputs, signalTime, signalProbability]);

  const visibleSignalMarkers = useMemo<CandlestickSignalMarker[]>(() => {
    if (alertVisibility === 'hidden') return [];

    const parseSignalTimestamp = (time: string): number => {
      if (/^\d{2}:\d{2}$/.test(time)) {
        const [hours, minutes] = time.split(':').map(Number);
        return hours * 60 + minutes;
      }
      const parsed = parseSystemDate(time)?.getTime() ?? Number.NaN;
      return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
    };

    const orderedMarkers = allSignalMarkers.filter(marker => Number.isFinite(parseSignalTimestamp(marker.time))).sort((a, b) => {
      return parseSignalTimestamp(a.time) - parseSignalTimestamp(b.time);
    });

    if (alertVisibility === 'latest') return orderedMarkers.slice(-1);
    if (alertVisibility === 'valid') return orderedMarkers.filter(marker => marker.isValid);
    return orderedMarkers;
  }, [alertVisibility, allSignalMarkers]);

  const alertVisibilityLabel: Record<AlertVisibilityMode, string> = {
    hidden: 'Ẩn cảnh báo',
    latest: 'Gần nhất',
    all: 'Tất cả',
    valid: 'Còn hiệu lực',
  };

  const toolButtonClass = 'inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded border border-slate-700/80 bg-slate-900/90 px-2 text-[10px] font-medium text-slate-300 transition hover:border-amber-500/70 hover:bg-slate-800 hover:text-amber-300 disabled:cursor-not-allowed disabled:opacity-40';

  const applyPriceScaleMode = (autoScale: boolean) => {
    setPriceAutoScale(autoScale);
    chartRef.current?.priceScale('right').applyOptions({ autoScale });
  };

  const adjustZoom = (factor: number) => {
    const timeScale = chartRef.current?.timeScale();
    const range = timeScale?.getVisibleLogicalRange();
    if (!timeScale || !range) return;

    const center = (range.from + range.to) / 2;
    const halfWidth = Math.max(4, ((range.to - range.from) * factor) / 2);
    timeScale.setVisibleLogicalRange({
      from: center - halfWidth,
      to: center + halfWidth,
    });
  };

  const handleResetView = () => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.timeScale().fitContent();
    applyPriceScaleMode(true);
  };

  const handleScreenshot = () => {
    const canvas = chartRef.current?.takeScreenshot(true);
    if (!canvas) return;

    const link = document.createElement('a');
    link.download = `dao-vang-${formatSystemDateTime(new Date().toISOString()).slice(0, 10)}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

  const handleFullscreen = async () => {
    if (!chartShellRef.current) return;

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await chartShellRef.current.requestFullscreen();
      }
    } catch (error) {
      console.warn('Chart fullscreen is not available:', error);
    }
  };

  const chartHeight = isFullscreen
    ? Math.max(320, window.innerHeight - 32)
    : height;

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === chartShellRef.current);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  useEffect(() => {
    const handleOutsidePointerDown = (event: PointerEvent) => {
      if (alertMenuRef.current && !alertMenuRef.current.contains(event.target as Node)) {
        setAlertMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', handleOutsidePointerDown);
    return () => document.removeEventListener('pointerdown', handleOutsidePointerDown);
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    chart.applyOptions({
      crosshair: {
        mode: crosshairMode === 'magnet' ? 1 : crosshairMode === 'normal' ? 0 : 2,
      },
      grid: {
        vertLines: { visible: gridVisible },
        horzLines: { visible: gridVisible },
      },
    });
    chart.priceScale('right').applyOptions({ autoScale: priceAutoScale });
  }, [crosshairMode, gridVisible, priceAutoScale]);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    // Normalize time to UNIX timestamp (seconds). Handles:
    // - millisecond timestamps from Binance API
    // - ISO strings from local DB
    // - HH:MM fallback as a relative index
    const parseTime = (time: number | string, fallbackIndex?: number): number => {
      if (typeof time === 'string') {
        if (time.match(/^\d{2}:\d{2}$/)) {
          return fallbackIndex ?? -1;
        }
        const parsed = parseSystemDate(time)?.getTime() ?? Number.NaN;
        return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : Number.NaN;
      }
      // Binance returns milliseconds; lightweight-charts expects seconds
      return time > 1e10 ? Math.floor(time / 1000) : time;
    };

    const normalizedCandles = data.map((d, index) => ({
      sourceTime: d.time,
      time: parseTime(d.time, index),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
      volume: d.volume || 0,
    })).filter(d =>
      Number.isFinite(d.time) &&
      [d.open, d.high, d.low, d.close].every(value => value != null && Number.isFinite(value)),
    ).sort((a, b) => a.time - b.time);

    const candleData = normalizedCandles.map(d => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const volumeData = normalizedCandles.map(d => ({
      time: d.time as any,
      value: d.volume,
      color: d.close >= d.open ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.4)',
    }));

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: '#f59e0b', width: 1, style: 2 },
        horzLine: { color: '#f59e0b', width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: '#334155',
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });
    candleSeries.setData(candleData);

    // Volume series (histogram at bottom)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(volumeData);

    // Target price line (drawdown -8%)
    if (targetPrice && targetPrice > 0) {
      candleSeries.createPriceLine({
        price: targetPrice,
        color: '#ef4444',
        lineWidth: 2,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Target -8%',
      });
    }

    // Mark every radar signal on the corresponding candle. Alert time may be
    // a candle close time while Binance data uses candle open time, so snap
    // each signal to its nearest candle instead of silently marking "now".
    let signalMarkersApi: ReturnType<typeof createSeriesMarkers> | null = null;
    if (visibleSignalMarkers.length > 0 && normalizedCandles.length > 0) {
      const positiveSteps = normalizedCandles.slice(1).map((candle, index) =>
        Math.abs(candle.time - normalizedCandles[index].time),
      ).filter(step => step > 0);
      const sortedSteps = [...positiveSteps].sort((a, b) => a - b);
      const candleStep = sortedSteps.length > 0
        ? sortedSteps[Math.floor(sortedSteps.length / 2)]
        : 0;
      const maxMarkerDistance = candleStep > 0 ? Math.max(candleStep * 1.5, 60) : 0;

      const resolvedMarkers = visibleSignalMarkers.flatMap((signal, index) => {
        let signalTimestamp: number | undefined;

        if (/^\d{2}:\d{2}$/.test(signal.time)) {
          signalTimestamp = normalizedCandles.find(c => c.sourceTime === signal.time)?.time;
        } else {
          const parsedSignalDate = parseSystemDate(signal.time)?.getTime() ?? Number.NaN;
          const parsedSignalTime = Number.isFinite(parsedSignalDate)
            ? Math.floor(parsedSignalDate / 1000)
            : Number.NaN;
          if (Number.isFinite(parsedSignalTime)) {
            const nearest = normalizedCandles.reduce((best, candle) =>
              Math.abs(candle.time - parsedSignalTime) < Math.abs(best.time - parsedSignalTime)
                ? candle
                : best,
            );
            // Do not place an old alert on the latest candle when the selected
            // interval does not contain its timestamp.
            if (!maxMarkerDistance || Math.abs(nearest.time - parsedSignalTime) <= maxMarkerDistance) {
              signalTimestamp = nearest.time;
            }
          }
        }

        if (signalTimestamp === undefined) return [];

        const probabilityText = signal.probability != null && Number.isFinite(signal.probability)
          ? `${formatSignalTime(signal.time, true)} · ${(signal.probability).toFixed(1)}%`
          : `${formatSignalTime(signal.time, true)} · XẢ`;

        return [{
          id: signal.id || `${signalTimestamp}-${index}`,
          time: signalTimestamp as any,
          position: 'aboveBar' as const,
          shape: 'arrowDown' as const,
          color: signal.isActive ? '#f59e0b' : '#f97316',
          text: probabilityText,
          size: signal.isActive ? 1.2 : 1,
        }];
      }).sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));

      if (resolvedMarkers.length > 0) {
        signalMarkersApi = createSeriesMarkers(candleSeries, resolvedMarkers, { zOrder: 'top' });
      }
    }

    chart.timeScale().fitContent();

    // Resize handler
    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        signalMarkersApi?.detach();
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, targetPrice, visibleSignalMarkers, chartHeight]);

  return (
    <div
      ref={chartShellRef}
      className={`relative w-full overflow-hidden bg-slate-950 ${isFullscreen ? 'h-screen p-4' : ''}`}
      style={isFullscreen ? undefined : { height }}
    >
      <div ref={containerRef} className="w-full" style={{ height: chartHeight }} />
      <div className="pointer-events-auto absolute left-2 right-2 top-2 z-20 flex max-w-[calc(100%-1rem)] items-center gap-1 overflow-x-auto rounded-md border border-slate-700/80 bg-slate-950/95 p-1 shadow-xl shadow-black/20 [&::-webkit-scrollbar]:hidden sm:left-auto sm:right-2 sm:max-w-none sm:overflow-visible">
        <div ref={alertMenuRef} className="relative">
          <button
            type="button"
            aria-label="Lọc cảnh báo trên biểu đồ"
            aria-expanded={alertMenuOpen}
            className={`${toolButtonClass} ${alertMenuOpen ? 'border-amber-500/80 text-amber-300' : ''}`}
            title="Chọn cảnh báo hiển thị trên biểu đồ"
            onClick={() => setAlertMenuOpen(value => !value)}
          >
            <Filter className="h-3.5 w-3.5 text-amber-400" />
            <span>{alertVisibilityLabel[alertVisibility]}</span>
            <ChevronDown className={`h-3 w-3 transition-transform ${alertMenuOpen ? 'rotate-180' : ''}`} />
          </button>
          {alertMenuOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-52 overflow-hidden rounded-lg border border-slate-700 bg-slate-900 p-1 shadow-2xl shadow-black/50">
              {alertVisibilityOptions.map(option => (
                <button
                  key={option.value}
                  type="button"
                  className={`flex w-full flex-col items-start rounded-md px-2.5 py-2 text-left transition ${
                    alertVisibility === option.value
                      ? 'bg-amber-500/15 text-amber-300'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-slate-100'
                  }`}
                  onClick={() => {
                    setAlertVisibility(option.value);
                    setAlertMenuOpen(false);
                  }}
                >
                  <span className="text-[10px] font-semibold">{option.label}</span>
                  <span className="mt-0.5 text-[9px] text-slate-500">{option.hint}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          className={`${toolButtonClass} ${crosshairMode === 'magnet' ? 'border-amber-500/80 text-amber-300' : ''}`}
          title="Con trỏ bám nến (bấm để đổi Tự do / Ẩn)"
          onClick={() => setCrosshairMode(mode => mode === 'magnet' ? 'normal' : mode === 'normal' ? 'hidden' : 'magnet')}
        >
          <Crosshair className="h-3.5 w-3.5" />
          {crosshairMode === 'magnet' ? 'Bám nến' : crosshairMode === 'normal' ? 'Tự do' : 'Ẩn'}
        </button>
        <button type="button" className={toolButtonClass} title="Thu nhỏ khung thời gian" onClick={() => adjustZoom(1.35)}>
          <ZoomOut className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={toolButtonClass} title="Phóng to khung thời gian" onClick={() => adjustZoom(0.7)}>
          <ZoomIn className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={toolButtonClass} title="Vừa toàn bộ dữ liệu và tự co giãn giá" onClick={handleResetView}>
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className={`${toolButtonClass} ${gridVisible ? 'border-slate-500 text-slate-200' : 'text-slate-500'}`}
          title="Bật/tắt lưới"
          onClick={() => setGridVisible(value => !value)}
        >
          <Grid3X3 className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className={`${toolButtonClass} ${priceAutoScale ? 'border-slate-500 text-slate-200' : 'text-slate-500'}`}
          title="Bật/tắt tự co giãn trục giá"
          onClick={() => applyPriceScaleMode(!priceAutoScale)}
        >
          <span className="font-mono text-[9px]">TỰ ĐỘNG</span>
        </button>
        <button type="button" className={toolButtonClass} title="Tải ảnh biểu đồ" onClick={handleScreenshot}>
          <Camera className="h-3.5 w-3.5" />
        </button>
        <button type="button" className={toolButtonClass} title="Toàn màn hình" onClick={handleFullscreen}>
          {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
      </div>
      {visibleSignalMarkers.length > 0 && (
        <div className="pointer-events-none absolute left-2 top-12 z-10 flex max-w-[calc(100%-1rem)] items-center gap-2 overflow-hidden rounded-md border border-amber-500/40 bg-slate-950/90 px-2 py-1 text-[10px] shadow-lg shadow-black/20 sm:top-2 sm:max-w-[70%]">
          <span className="font-bold uppercase tracking-wide text-amber-400">↓ Cảnh báo xả</span>
          {visibleSignalMarkers.length > 1 && (
            <span className="font-mono font-bold text-slate-300">{visibleSignalMarkers.length} tín hiệu</span>
          )}
          {allSignalMarkers.length > visibleSignalMarkers.length && (
            <span className="font-mono text-slate-500">/{allSignalMarkers.length} · {alertVisibilityLabel[alertVisibility]}</span>
          )}
          <span className="font-mono text-slate-300">
            Gần nhất: {formatSignalTime(visibleSignalMarkers[visibleSignalMarkers.length - 1].time)} (VN)
          </span>
          {visibleSignalMarkers[visibleSignalMarkers.length - 1].probability != null && Number.isFinite(visibleSignalMarkers[visibleSignalMarkers.length - 1].probability) && (
            <span className="font-mono font-bold text-red-400">
              {visibleSignalMarkers[visibleSignalMarkers.length - 1].probability?.toFixed(1)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
};
