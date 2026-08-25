import React, { useState } from 'react';
import {
  X, Settings, Key, Cpu, Globe, CheckCircle2,
  AlertTriangle, Loader2, Eye, EyeOff, Sparkles, RefreshCw
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type { LlmConfig, LlmProvider } from '../../types';

interface LlmConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: LlmConfig;
  onSaveConfig: (newConfig: LlmConfig) => void;
}

const PROVIDER_OPTIONS: { id: LlmProvider; name: string; icon: string; defaultModel: string; placeholderUrl?: string; desc: string }[] = [
  {
    id: 'gemini',
    name: 'Google Gemini',
    icon: '✨',
    defaultModel: 'gemini-1.5-flash',
    desc: 'Miễn phí, tốc độ cao, nhận thức ngữ cảnh tốt',
  },
  {
    id: 'openai',
    name: 'OpenAI (ChatGPT)',
    icon: '🟢',
    defaultModel: 'gpt-4o-mini',
    placeholderUrl: 'https://api.openai.com/v1',
    desc: 'Mô hình tiêu chuẩn ngành, suy luận logic tốt',
  },
  {
    id: 'deepseek',
    name: 'DeepSeek AI',
    icon: '🐳',
    defaultModel: 'deepseek-chat',
    placeholderUrl: 'https://api.deepseek.com',
    desc: 'Chi phí cực thấp, hiệu năng suy luận xuất sắc',
  },
  {
    id: 'claude',
    name: 'Anthropic Claude',
    icon: '🟣',
    defaultModel: 'claude-3-5-haiku-20241022',
    desc: 'Văn phong tự nhiên, phân tích định lượng chuyên sâu',
  },
  {
    id: 'ollama',
    name: 'Local / Ollama / Custom API',
    icon: '💻',
    defaultModel: 'llama3.2',
    placeholderUrl: 'http://localhost:11434/v1',
    desc: 'Chạy offline bảo mật trên máy chủ riêng',
  },
];

export const LlmConfigModal: React.FC<LlmConfigModalProps> = ({
  isOpen,
  onClose,
  config,
  onSaveConfig,
}) => {
  const { language } = useTranslation();
  const isEn = language === 'en';
  const isZh = language === 'zh';
  const isKo = language === 'ko';

  const [provider, setProvider] = useState<LlmProvider>(config.provider || 'gemini');
  const [apiKey, setApiKey] = useState<string>(config.apiKey || '');
  const [modelId, setModelId] = useState<string>(config.modelId || '');
  const [baseUrl, setBaseUrl] = useState<string>(config.baseUrl || '');
  const [enabled, setEnabled] = useState<boolean>(config.enabled !== false);
  const [showKey, setShowKey] = useState<boolean>(false);

  const [testing, setTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  if (!isOpen) return null;

  const currentProviderMeta = PROVIDER_OPTIONS.find(p => p.id === provider) || PROVIDER_OPTIONS[0];

  const handleSelectProvider = (newProvider: LlmProvider) => {
    setProvider(newProvider);
    const meta = PROVIDER_OPTIONS.find(p => p.id === newProvider);
    if (meta) {
      if (!modelId || PROVIDER_OPTIONS.some(p => p.defaultModel === modelId)) {
        setModelId(meta.defaultModel);
      }
      if (meta.placeholderUrl) {
        setBaseUrl(meta.placeholderUrl);
      }
    }
    setTestResult(null);
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: 'Kiểm tra kết nối API. Hãy trả lời "OK Đã kết nối thành công".',
          symbol: 'BTCUSDT',
          context: { current_price: 95000, probability: 75 },
          llm_config: {
            provider,
            apiKey: apiKey.trim(),
            modelId: modelId.trim() || currentProviderMeta.defaultModel,
            baseUrl: baseUrl.trim(),
            enabled: true,
          },
        }),
      });
      const data = await res.json();
      if (res.ok && data.answer) {
        setTestResult({
          success: true,
          message: isZh ? `连接成功！使用模型: ${data.model} (${data.provider})` : isKo ? `연결 성공! 사용 모델: ${data.model} (${data.provider})` : isEn ? `Connected successfully! Provider: ${data.provider} (${data.model})` : `Kết nối thành công! Mô hình: ${data.model} (${data.provider})`,
        });
      } else {
        setTestResult({
          success: false,
          message: data.error || (isEn ? 'Failed to connect. Check API key.' : 'Không thể kết nối. Kiểm tra lại API Key hoặc Endpoint.'),
        });
      }
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.message || (isEn ? 'Network error' : 'Lỗi kết nối mạng.'),
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = () => {
    const updated: LlmConfig = {
      provider,
      apiKey: apiKey.trim(),
      modelId: modelId.trim() || currentProviderMeta.defaultModel,
      baseUrl: baseUrl.trim(),
      enabled,
    };
    onSaveConfig(updated);
    onClose();
  };

  const handleReset = () => {
    setProvider('openai');
    setApiKey('');
    setModelId('antigravity/gemini-3.7-flash-tiered');
    setBaseUrl('https://proxy-ai.comaygiauco.com/v1');
    setEnabled(true);
    setTestResult(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <Settings className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100">
                {isZh ? '配置 AI 语言模型 (LLM API Settings)' : isKo ? 'AI 언어 모델 설정 (LLM API Settings)' : isEn ? 'LLM API & AI Provider Settings' : 'Cấu Hình API Trợ Lý AI (LLM Provider)'}
              </h3>
              <p className="text-[11px] text-slate-400">
                {isZh ? '支持接入 Google Gemini、OpenAI、DeepSeek、Claude 或本地 Ollama' : isKo ? 'Gemini, OpenAI, DeepSeek, Claude 또는 로컬 Ollama 연동 지원' : isEn ? 'Connect Gemini, OpenAI, DeepSeek, Claude, or Local Ollama' : 'Gắn API Key của riêng bạn để nhận phân tích chuyên sâu đa chiều'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1 text-xs">
          {/* Server Default AI Info Banner */}
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-start gap-2.5 text-xs">
            <Sparkles className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-slate-300 leading-relaxed text-[11px]">
              <span className="font-semibold text-amber-300">Model Mặc Định Hệ Thống: </span>
              Hệ thống đã cấu hình sẵn <strong>Gemini 3.7 Flash Tiered</strong> chạy qua Server. Bạn có thể sử dụng ngay mà không cần nhập key, hoặc nhập key riêng dưới đây nếu muốn.
            </div>
          </div>

          {/* Provider Selection */}
          <div>
            <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2">
              {isZh ? '选择 AI 提供商 (Provider)' : isKo ? 'AI 제공자 선택 (Provider)' : isEn ? 'Select AI Provider' : '1. Chọn Nhà Cung Cấp AI (Provider)'}
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {PROVIDER_OPTIONS.map((opt) => {
                const isSelected = provider === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => handleSelectProvider(opt.id)}
                    className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-left transition ${
                      isSelected
                        ? 'border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/40 text-amber-200'
                        : 'border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700 hover:bg-slate-800/60'
                    }`}
                  >
                    <span className="text-base">{opt.icon}</span>
                    <div className="min-w-0 flex-1">
                      <div className="font-bold text-xs flex items-center justify-between">
                        <span>{opt.name}</span>
                        {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-amber-400" />}
                      </div>
                      <div className="text-[10px] text-slate-400 truncate mt-0.5">{opt.desc}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* API Key Input */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-amber-400" />
                <span>{isZh ? 'API 密钥 (API Key)' : isKo ? 'API 키 (API Key)' : isEn ? 'API Key' : '2. Khóa API (API Key)'}</span>
              </label>
              <span className="text-[10px] text-slate-400">
                {isZh ? '保存在本地浏览器中，绝不上报云端' : isKo ? '브라우저 로컬에만 안전하게 저장됨' : isEn ? 'Saved locally in your browser only' : 'Chỉ lưu trong bộ nhớ máy của bạn'}
              </span>
            </div>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={provider === 'ollama' ? (isEn ? 'Optional for local Ollama' : 'Không bắt buộc với Ollama local') : `Nhập ${currentProviderMeta.name} API Key...`}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 pr-10 text-slate-200 font-mono text-xs focus:outline-none focus:border-amber-500 transition"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Model ID & Custom Endpoint Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-sky-400" />
                <span>{isZh ? '模型名称 (Model ID)' : isKo ? '모델 ID (Model ID)' : isEn ? 'Model ID' : 'Mã Mô Hình (Model ID)'}</span>
              </label>
              <input
                type="text"
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                placeholder={currentProviderMeta.defaultModel}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs focus:outline-none focus:border-amber-500 transition"
              />
            </div>

            <div>
              <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-violet-400" />
                <span>{isZh ? '自定义地址 (Base URL)' : isKo ? '기본 URL (Base URL)' : isEn ? 'Custom Base URL' : 'Địa Chỉ API (Base URL)'}</span>
              </label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={currentProviderMeta.placeholderUrl || (isEn ? 'Default endpoint' : 'Mặc định nhà cung cấp')}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs focus:outline-none focus:border-amber-500 transition"
              />
            </div>
          </div>

          {/* Test Connection Output */}
          {testResult && (
            <div
              className={`p-3 rounded-lg border flex items-start gap-2 ${
                testResult.success
                  ? 'bg-emerald-950/60 border-emerald-700/80 text-emerald-200'
                  : 'bg-rose-950/60 border-rose-700/80 text-rose-200'
              }`}
            >
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              )}
              <div className="text-[11px] leading-relaxed">{testResult.message}</div>
            </div>
          )}

          {/* Fallback Notice */}
          <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800 text-[11px] text-slate-400 leading-relaxed">
            💡 <strong className="text-slate-200">{isZh ? '内置量化分析引擎' : isKo ? '기본 탑재 정량 분석 엔진' : isEn ? 'Built-in Quant Analyst' : 'Bộ Phân Tích Định Lượng Tích Hợp'}:</strong>{' '}
            {isZh ? '若未配置 API 密钥或外部 API 出现异常，系统将自动启用内置的高级定量专家规则引擎，确保问答功能 100% 随时可用。' : isKo ? 'API 키를 입력하지 않거나 외부 오류 발생 시, 자체 정량 분석 엔진이 즉시 전환되어 100% 정상 작동합니다.' : isEn ? 'If no API key is provided or the external service fails, the system seamlessly falls back to the built-in quantitative expert reasoning engine.' : 'Nếu chưa gắn API Key hoặc API ngoài bị gián đoạn, hệ thống sẽ tự động sử dụng Bộ máy phân tích định lượng tích hợp sẵn để phục vụ bạn.'}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-5 py-3.5 border-t border-slate-800 bg-slate-950/90">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testing}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium rounded-lg text-xs flex items-center gap-1.5 transition border border-slate-700 disabled:opacity-50"
            >
              {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" /> : <Sparkles className="w-3.5 h-3.5 text-amber-400" />}
              <span>{testing ? (isEn ? 'Testing...' : 'Đang kiểm tra...') : (isZh ? '测试连接' : isKo ? '연결 테스트' : isEn ? 'Test Connection' : 'Kiểm Tra Kết Nối')}</span>
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="px-2.5 py-1.5 text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1 transition"
              title={isEn ? 'Reset to default' : 'Đặt lại mặc định'}
            >
              <RefreshCw className="w-3 h-3" />
              <span>{isEn ? 'Reset' : 'Đặt lại'}</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium rounded-lg text-xs transition"
            >
              {isZh ? '取消' : isKo ? '취소' : isEn ? 'Cancel' : 'Hủy'}
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-lg text-xs flex items-center gap-1.5 transition shadow-md shadow-amber-500/20"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{isZh ? '保存配置' : isKo ? '설정 저장' : isEn ? 'Save Config' : 'Lưu Cấu Hình'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
