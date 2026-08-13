import React, { useState } from 'react';
import type { SignalItem, AutomationSettings } from '../types';
import { Send, FileText, Settings, Bell, Sparkles, CheckCircle2, Zap, Copy, Check, Globe, X } from 'lucide-react';
import { CoinLink } from './CoinLink';
import { useTranslation } from '../i18n/LanguageContext';

interface ActionDrawerProps {
  selectedSignal: SignalItem | null;
  onPushTelegram: (sig: SignalItem) => void;
  telegramSentSuccess: string | null;
  automationSettings: AutomationSettings;
  setAutomationSettings: React.Dispatch<React.SetStateAction<AutomationSettings>>;
  onSelectCoin?: (symbol: string) => void;
  onCloseDrawer?: () => void;
}

export const ActionDrawer: React.FC<ActionDrawerProps> = ({
  selectedSignal,
  onPushTelegram,
  telegramSentSuccess,
  automationSettings,
  setAutomationSettings,
  onSelectCoin,
  onCloseDrawer
}) => {
  const { language } = useTranslation();
  const [telegramChatId, setTelegramChatId] = useState('@DaoVangAlerts');
  const [copiedTextSuccess, setCopiedTextSuccess] = useState(false);

  // Copy formatted alert text
  const handleCopyFormattedText = () => {
    if (!selectedSignal) return;
    const isEn = language === 'en';
    const text = isEn
      ? `🚨 [DAO VANG AI ALERT]\n🪙 Coin: ${selectedSignal.symbol}\n📊 Probability: ${(selectedSignal.probability * 100).toFixed(1)}% (${selectedSignal.risk_level})\n🎯 Target Drawdown: ${selectedSignal.target_drawdown}% ($${selectedSignal.target_price})\n📈 OI Delta 24h: ${selectedSignal.oi_change_24h}\n💸 Funding Rate: ${selectedSignal.funding_rate}\n⏱️ Validity Left: ${selectedSignal.validity_hours_left} hours\n⚡ Key Drivers: ${selectedSignal.drivers.map(d => d.name).join(', ')}`
      : `🚨 [TÍN HIỆU ĐẢO VÀNG AI]\n🪙 Coin: ${selectedSignal.symbol}\n📊 Xác suất: ${(selectedSignal.probability * 100).toFixed(1)}% (${selectedSignal.risk_level})\n🎯 Mục tiêu giảm: ${selectedSignal.target_drawdown}% ($${selectedSignal.target_price})\n📈 OI 24 giờ: ${selectedSignal.oi_change_24h}\n💸 Tỷ lệ funding: ${selectedSignal.funding_rate}\n⏱️ Hiệu lực còn: ${selectedSignal.validity_hours_left} giờ\n⚡ Nguyên nhân AI: ${selectedSignal.drivers.map(d => d.name).join(', ')}`;
    navigator.clipboard.writeText(text);
    setCopiedTextSuccess(true);
    setTimeout(() => setCopiedTextSuccess(false), 2000);
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 flex flex-col h-full overflow-y-auto space-y-3.5">
      
      {/* Header */}
      <div className="border-b border-slate-800 pb-2.5 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-xs font-bold text-slate-100 uppercase tracking-wider flex items-center gap-1.5">
            <Settings className="w-3.5 h-3.5 text-amber-400" />
            {language === 'en' ? 'CONTROL CENTER & SMART AUTOMATION' : 'QUYẾT ĐỊNH & TỰ ĐỘNG HÓA THÔNG MINH'}
          </h2>
          <p className="text-[11px] text-slate-400">
            {language === 'en' ? 'Alert Dispatch & Automation Settings' : 'Trung tâm phát cảnh báo & Cấu hình tự động'}
          </p>
        </div>
        {onCloseDrawer && (
          <button
            onClick={onCloseDrawer}
            className="p-1 rounded-md bg-slate-800 hover:bg-red-950 text-slate-400 hover:text-red-400 transition shrink-0"
            title={language === 'en' ? 'Collapse' : 'Thu gọn'}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Telegram Alert Pusher Box */}
      <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-bold text-sky-400">
            <Send className="w-3.5 h-3.5" />
            {language === 'en' ? 'TELEGRAM ALERT DISPATCH' : 'CẢNH BÁO QUA TELEGRAM'}
          </div>
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        </div>

        {selectedSignal ? (
          <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 space-y-1 font-mono text-[11px]">
            <div className="flex justify-between text-slate-300">
              <span>{language === 'en' ? 'Pair:' : 'Mã coin:'}</span>
              {onSelectCoin ? (
                <CoinLink symbol={selectedSignal.symbol} onClick={onSelectCoin} />
              ) : (
                <span className="font-bold text-amber-400">{selectedSignal.symbol}</span>
              )}
            </div>
            <div className="flex justify-between text-slate-300">
              <span>{language === 'en' ? 'Probability:' : 'Điểm rủi ro:'}</span>
              <span className="font-bold text-red-400">{(selectedSignal.probability * 100).toFixed(1)}%</span>
            </div>
            <div className="flex justify-between text-slate-300">
              <span>{language === 'en' ? 'Target Drawdown:' : 'Mục tiêu giảm:'}</span>
              <span className="font-bold text-red-400">{selectedSignal.target_drawdown}% (${selectedSignal.target_price})</span>
            </div>
          </div>
        ) : (
          <div className="text-xs text-slate-500 italic p-2 text-center">
            {language === 'en' ? 'Please select a signal to dispatch alert' : 'Vui lòng chọn 1 tín hiệu để bắn cảnh báo'}
          </div>
        )}

        <div>
          <label className="text-[10px] text-slate-400 font-medium">
            {language === 'en' ? 'Target Channel:' : 'Kênh nhận:'}
          </label>
          <input
            type="text"
            value={telegramChatId}
            onChange={(e) => setTelegramChatId(e.target.value)}
            className="w-full mt-0.5 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500"
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => selectedSignal && onPushTelegram(selectedSignal)}
            disabled={!selectedSignal}
            className="py-2 bg-gradient-to-r from-sky-600 to-sky-500 hover:from-sky-500 hover:to-sky-400 text-slate-950 font-bold rounded-lg text-xs flex items-center justify-center gap-1 transition shadow-md shadow-sky-500/20 disabled:opacity-50"
          >
            <Send className="w-3 h-3" />
            {language === 'en' ? 'Push Telegram' : 'Bắn Telegram'}
          </button>

          <button
            onClick={handleCopyFormattedText}
            disabled={!selectedSignal}
            className="py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold rounded-lg text-xs flex items-center justify-center gap-1 transition border border-slate-700 disabled:opacity-50"
          >
            {copiedTextSuccess ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            {language === 'en' ? 'Copy Text' : 'Sao chép nội dung'}
          </button>
        </div>

        {telegramSentSuccess && (
          <div className="p-2 bg-emerald-950/80 border border-emerald-800 text-emerald-400 text-[11px] rounded flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
            <span>{telegramSentSuccess}</span>
          </div>
        )}
      </div>

      {/* Smart Automation Rules */}
      <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 space-y-2.5 text-xs">
        <div className="font-bold text-amber-400 flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5" />
          {language === 'en' ? 'SMART AUTOMATION RULES' : 'QUY TẮC TỰ ĐỘNG HÓA THÔNG MINH'}
        </div>

        {/* Auto Telegram Toggle */}
        <div className="flex items-center justify-between bg-slate-900 p-2 rounded border border-slate-800">
          <div>
            <div className="font-medium text-slate-200 text-[11px]">
              {language === 'en' ? 'Auto-push Telegram' : 'Tự động bắn Telegram'}
            </div>
            <div className="text-[10px] text-slate-400">
              {language === 'en' ? 'When probability ≥ 80%' : 'Khi điểm rủi ro ≥ 80%'}
            </div>
          </div>
          <input
            type="checkbox"
            checked={automationSettings.autoTelegramPush}
            onChange={(e) => setAutomationSettings(prev => ({ ...prev, autoTelegramPush: e.target.checked }))}
            className="accent-amber-500 w-4 h-4 cursor-pointer"
          />
        </div>

        {/* Audio Siren Toggle */}
        <div className="flex items-center justify-between bg-slate-900 p-2 rounded border border-slate-800">
          <div className="flex items-center gap-1.5 text-slate-200">
            <Bell className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-[11px]">{language === 'en' ? 'Audio Siren Alert' : 'Âm thanh còi báo xả'}</span>
          </div>
          <input
            type="checkbox"
            checked={automationSettings.audioAlertEnabled}
            onChange={(e) => setAutomationSettings(prev => ({ ...prev, audioAlertEnabled: e.target.checked }))}
            className="accent-amber-500 w-4 h-4 cursor-pointer"
          />
        </div>

        {/* Webhook Integration */}
        <div>
          <label className="text-[10px] text-slate-400 font-medium flex items-center gap-1">
            <Globe className="w-3 h-3 text-sky-400" /> {language === 'en' ? 'Webhook URL (Auto Bot):' : 'URL Webhook (bot tự động):'}
          </label>
          <input
            type="text"
            placeholder="https://api.yourbot.com/webhook"
            value={automationSettings.webhookUrl}
            onChange={(e) => setAutomationSettings(prev => ({ ...prev, webhookUrl: e.target.value }))}
            className="w-full mt-1 bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-[11px] font-mono text-slate-200 focus:outline-none focus:border-amber-500"
          />
        </div>
      </div>

      {/* Quick Export */}
      <div className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 space-y-2">
        <div className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5 text-amber-400" />
          {language === 'en' ? 'DATA EXPORT' : 'XUẤT BÁO CÁO'}
        </div>

        <button
          onClick={() => {
            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(selectedSignal, null, 2));
            const downloadAnchor = document.createElement('a');
            downloadAnchor.setAttribute("href", dataStr);
            downloadAnchor.setAttribute("download", `dao_vang_signal_${selectedSignal?.symbol || 'data'}.json`);
            document.body.appendChild(downloadAnchor);
            downloadAnchor.click();
            downloadAnchor.remove();
          }}
          className="w-full py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-amber-400 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition"
        >
          {language === 'en' ? '📥 Download Signal JSON Config' : '📥 Tải cấu hình tín hiệu JSON'}
        </button>
      </div>

      {/* Spec summary */}
      <div className="p-2.5 bg-amber-950/20 border border-amber-500/20 rounded-xl text-[11px] space-y-1 text-slate-400">
        <div className="font-bold text-amber-400 flex items-center gap-1">
          <Sparkles className="w-3 h-3" /> {language === 'en' ? 'ENGINE V1.5 SPECIFICATION' : 'ĐẶC TẢ BỘ MÁY V1.5'}
        </div>
        <div>{language === 'en' ? 'Prediction Horizon:' : 'Khung dự báo:'} <span className="text-slate-200 font-mono">24h</span></div>
        <div>{language === 'en' ? 'Target Drawdown:' : 'Mục tiêu giảm:'} <span className="text-slate-200 font-mono">≥ 8.0%</span></div>
        <div>{language === 'en' ? 'Max Adverse Excursion (MAE):' : 'Mức lệch tối đa:'} <span className="text-slate-200 font-mono">≤ 4.0%</span></div>
      </div>

    </div>
  );
};
