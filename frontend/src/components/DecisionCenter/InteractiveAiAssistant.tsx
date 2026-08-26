import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles, Send, Settings, Trash2, Bot,
  User, Copy, Check, ChevronDown, ChevronUp,
  HelpCircle, Maximize2, Minimize2, X
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type {
  CoinDetail, DeepAnalysis, TradeSetup,
  ChatMessage, LlmConfig, AiAskRequest, AiAskResponse
} from '../../types';
import { LlmConfigModal } from './LlmConfigModal';
import { MarkdownRenderer } from './MarkdownRenderer';

interface InteractiveAiAssistantProps {
  displayDetail: CoinDetail;
  deepAnalysis?: DeepAnalysis | null;
  tradeSetup?: TradeSetup | null;
  isOpen?: boolean;
  onToggleOpen?: () => void;
}

const STORAGE_CONFIG_KEY = 'dao_vang_llm_config';

export const InteractiveAiAssistant: React.FC<InteractiveAiAssistantProps> = ({
  displayDetail,
  deepAnalysis,
  tradeSetup,
  isOpen = true,
  onToggleOpen,
}) => {
  const { language } = useTranslation();
  const isEn = language === 'en';
  const isZh = language === 'zh';
  const isKo = language === 'ko';

  const symbol = displayDetail?.symbol || 'COIN';
  const currentPrice = displayDetail?.current_price || 0;
  const prob = displayDetail?.probability || 0;
  const riskLevel = displayDetail?.risk_level || 'MEDIUM';
  const btcRegime = deepAnalysis?.btc_regime || 'NEUTRAL';
  const isPump = deepAnalysis?.pump_analysis?.detected || false;
  const metrics = displayDetail?.metrics || {
    oi_change_24h: 'N/A',
    taker_sell_ratio: 0.5,
    funding_rate: 'N/A',
    rsi_15m: 50,
    volume_delta_24h: 'N/A',
  };
  const shapDrivers = displayDetail?.shap_drivers || [];

  // LLM Config state
  const [llmConfig, setLlmConfig] = useState<LlmConfig>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_CONFIG_KEY);
      if (saved) return JSON.parse(saved);
    } catch {
      // fallback
    }
    return {
      provider: 'openai',
      apiKey: '',
      modelId: 'antigravity/gemini-3.7-flash-tiered',
      baseUrl: 'https://proxy-ai.comaygiauco.com/v1',
      enabled: true,
    };
  });

  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isAllCopied, setIsAllCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Close full screen on ESC
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isExpanded) {
        setIsExpanded(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExpanded]);

  // Auto-fetch default server AI config if apiKey is empty
  useEffect(() => {
    if (!llmConfig.apiKey) {
      fetch('/api/ai/config')
        .then((res) => res.json())
        .then((data) => {
          if (data && data.apiKey) {
            setLlmConfig((prev) => ({
              ...prev,
              apiKey: data.apiKey,
              provider: prev.provider || data.provider || 'openai',
              modelId: prev.modelId || data.modelId || 'antigravity/gemini-3.7-flash-tiered',
              baseUrl: prev.baseUrl || data.baseUrl || 'https://proxy-ai.comaygiauco.com/v1',
            }));
          }
        })
        .catch(() => {});
    }
  }, [llmConfig.apiKey]);

  // Initialize welcome message when symbol changes
  useEffect(() => {
    const welcomeMsg: ChatMessage = {
      id: `welcome-${symbol}-${Date.now()}`,
      role: 'assistant',
      content: isZh
        ? `👋 你好！我是 **${symbol}** 的专属 AI 量化分析助理。当前价格 **$${currentPrice}**，AI 派发概率 **${prob.toFixed(1)}%** (${riskLevel})。请从下方快捷提问或直接输入你想了解的交易问题。`
        : isKo
        ? `👋 안녕하세요! **${symbol}** 전담 AI 퀀트 어시스턴트입니다. 현재가 **$${currentPrice}**, AI 덤프 확률 **${prob.toFixed(1)}%** (${riskLevel})입니다. 아래 빠른 질문을 누르거나 무엇이든 질문하세요.`
        : isEn
        ? `👋 Hello! I am your dedicated AI Quant Assistant for **${symbol}**. Current Mark Price is **$${currentPrice}** with **${prob.toFixed(1)}%** Dump Probability (${riskLevel}). Ask any question or click a prompt below!`
        : `👋 Xin chào! Tôi là Trợ lý Định lượng AI cho cặp **${symbol}**. Giá hiện tại **$${currentPrice}**, Xác suất xả AI **${prob.toFixed(1)}%** (${riskLevel}). Bạn có thể bấm câu hỏi gợi ý nhanh bên dưới hoặc nhập câu hỏi bất kỳ!`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      providerUsed: 'PeakPulse Assistant',
    };
    setMessages([welcomeMsg]);
  }, [symbol, currentPrice, prob, riskLevel, isEn, isZh, isKo]);

  const prevSymbolRef = useRef(symbol);

  // Scroll internal chat container to bottom when user sends questions or AI responds
  useEffect(() => {
    if (prevSymbolRef.current !== symbol) {
      prevSymbolRef.current = symbol;
      return;
    }
    if ((isOpen || isExpanded) && messages.length > 1 && chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages, isLoading, isOpen, isExpanded, symbol]);

  const handleSaveConfig = (newConfig: LlmConfig) => {
    setLlmConfig(newConfig);
    try {
      localStorage.setItem(STORAGE_CONFIG_KEY, JSON.stringify(newConfig));
    } catch (e) {
      console.error('Failed to save LLM config to localStorage', e);
    }
  };

  const handleSendQuestion = async (overrideQuestion?: string) => {
    const questionText = (overrideQuestion || inputQuestion).trim();
    if (!questionText || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: questionText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const recentHistory = messages
      .filter((m): m is ChatMessage & { role: 'user' | 'assistant' } => (m.role === 'user' || m.role === 'assistant') && !m.id.startsWith('welcome-') && !m.isError)
      .slice(-8)
      .map(m => ({ role: m.role, content: m.content }));

    setMessages(prev => [...prev, userMsg]);
    if (!overrideQuestion) {
      setInputQuestion('');
    }
    setIsLoading(true);

    try {
      const payload: AiAskRequest = {
        question: questionText,
        symbol,
        context: {
          current_price: currentPrice,
          signal_price: currentPrice,
          probability: prob,
          risk_level: riskLevel,
          trade_setup: tradeSetup || undefined,
          shap_drivers: shapDrivers,
          metrics,
          btc_regime: btcRegime,
          parabolic_pump: isPump,
        },
        llm_config: llmConfig,
        history: recentHistory,
      };

      const res = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data: AiAskResponse = await res.json();

      const botMsg: ChatMessage = {
        id: `bot-${Date.now()}`,
        role: 'assistant',
        content: data.answer || (isEn ? 'No response received.' : 'Không nhận được câu trả lời từ máy chủ.'),
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        providerUsed: `${data.provider} (${data.model})`,
      };

      setMessages(prev => [...prev, botMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ ${isEn ? 'Failed to process question:' : 'Lỗi khi gửi câu hỏi:'} ${err.message || 'Network error'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        isError: true,
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleCopyEntireHistory = () => {
    if (messages.length === 0) return;
    const dateStr = new Date().toLocaleString();
    let text = `=== HỘI THOẠI VỚI TRỢ LÝ AI ĐẢO VÀNG — ${symbol} (${dateStr}) ===\n`;
    text += `Bối cảnh thị trường: Giá Mark $${currentPrice} | Xác suất xả AI: ${prob.toFixed(1)}% (${riskLevel}) | Trạng thái BTC: ${btcRegime}\n`;
    text += `Chỉ số: OI 24h: ${metrics.oi_change_24h || 'N/A'} | Funding: ${metrics.funding_rate || 'N/A'} | Taker Buy/Sell: ${(metrics.taker_sell_ratio || 0.5) * 100}%\n`;
    text += `================================================================================\n\n`;

    messages.forEach((m) => {
      const speaker = m.role === 'user' ? `[TRADER (${m.timestamp})]` : `[AI TRỢ LÝ - ${m.providerUsed || 'PeakPulse AI'} (${m.timestamp})]`;
      text += `${speaker}:\n${m.content}\n\n--------------------------------------------------------------------------------\n\n`;
    });

    navigator.clipboard.writeText(text.trim());
    setIsAllCopied(true);
    setTimeout(() => setIsAllCopied(false), 2500);
  };

  const handleClearHistory = () => {
    setMessages(prev => prev.slice(0, 1));
  };

  // Quick prompt chips
  const quickChips = [
    {
      label: isZh ? '🔍 为什么此币风险评分高？' : isKo ? '🔍 왜 이 코인의 위험 점수가 높나요?' : isEn ? '🔍 Why is this coin risk score high?' : '🔍 Tại sao coin này có điểm rủi ro cao?',
      prompt: `Tại sao ${symbol} lại có xác suất phân phối xả ${prob.toFixed(1)}%? Giải thích các yếu tố định lượng chính.`,
    },
    {
      label: isZh ? '📈 如果 BTC 暴涨该如何应对？' : isKo ? '📈 BTC가 급등할 경우 대응 시나리오는?' : isEn ? '📈 What if BTC pumps aggressively?' : '📈 Kịch bản nếu BTC đột ngột tăng mạnh?',
      prompt: `Nếu Bitcoin đột ngột tăng mạnh thì kịch bản giao dịch của ${symbol} sẽ bị ảnh hưởng thế nào? Khi nào cần hủy kèo?`,
    },
    {
      label: isZh ? '🛡️ 最佳止损与止盈点位在哪里？' : isKo ? '🛡️ 최적의 손절 및 익절 위치는 어디인가요?' : isEn ? '🛡️ Optimal SL and TP levels?' : '🛡️ Điểm cắt lỗ SL và chốt lời ở đâu an toàn nhất?',
      prompt: `Điểm cắt lỗ SL và các mốc chốt lời TP cho ${symbol} được tính toán như thế nào?`,
    },
    {
      label: isZh ? '💰 建议仓位大小与杠杆倍数？' : isKo ? '💰 추천 포지션 크기 및 레버리지는?' : isEn ? '💰 Suggested sizing & leverage?' : '💰 Chiến lược đi vốn & đòn bẩy đề xuất?',
      prompt: `Với mức rủi ro ${riskLevel} của ${symbol}, tôi nên phân bổ bao nhiêu % vốn và dùng đòn bẩy bao nhiêu là an toàn?`,
    },
    {
      label: isZh ? '📊 解释当前 OI 与资金费率' : isKo ? '📊 현재 OI 및 펀딩비 해석' : isEn ? '📊 Explain current OI & Funding Rate' : '📊 Giải thích chỉ số OI và Funding Rate hiện tại?',
      prompt: `Giải thích ý nghĩa của biến động OI (${metrics.oi_change_24h || 'N/A'}) và Funding Rate (${metrics.funding_rate || 'N/A'}) đối với ${symbol}.`,
    },
  ];

  return (
    <>
      {/* Backdrop overlay when in Fullscreen / Expanded view */}
      {isExpanded && (
        <div
          className="fixed inset-0 bg-slate-950/80 backdrop-blur-md z-50 transition-opacity"
          onClick={() => setIsExpanded(false)}
        />
      )}

      <div
        className={`transition-all duration-200 ${
          isExpanded
            ? 'fixed inset-2 sm:inset-4 md:inset-6 lg:inset-8 z-50 bg-slate-950/98 border border-slate-700/90 rounded-2xl shadow-2xl flex flex-col backdrop-blur-2xl overflow-hidden'
            : 'bg-slate-950/90 border border-slate-800 rounded-xl overflow-hidden shadow-2xl'
        }`}
      >
        {/* Assistant Header */}
        <div className="flex items-center justify-between px-3.5 sm:px-4 py-3 border-b border-slate-800/80 bg-slate-900/60 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-amber-600 to-amber-400 text-slate-950 flex items-center justify-center font-bold shrink-0 shadow-sm">
              <Bot className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xs sm:text-sm font-bold text-slate-100 flex items-center gap-1.5 truncate">
                <span>{isZh ? 'AI 首席分析师问答' : isKo ? 'AI 수석 분석가 질의응답' : isEn ? 'AI ANALYST CHAT & Q&A' : 'TRỢ LÝ AI ĐẢO VÀNG (HỎI ĐÁP CHUYÊN SÂU)'}</span>
                <span className="text-[10px] font-mono text-cyan-400 font-bold px-1.5 py-0.2 bg-cyan-500/10 rounded border border-cyan-500/20">
                  {symbol}
                </span>
                {isExpanded && (
                  <span className="hidden md:inline-flex items-center gap-1.5 text-[10px] font-mono text-amber-400/90 px-2 py-0.5 bg-amber-500/10 rounded border border-amber-500/20">
                    <span>${currentPrice}</span>
                    <span>•</span>
                    <span>Xác suất xả: {prob.toFixed(1)}% ({riskLevel})</span>
                    <span>•</span>
                    <span>BTC: {btcRegime}</span>
                  </span>
                )}
              </h3>
              <p className="text-[10px] text-slate-400 truncate">
                {isZh ? '实时注入行情、订单流与 SHAP 特征的多模型问答助理' : isKo ? '실시간 오더플로우 및 SHAP 지표가 주입된 다중 모델 AI 어시스턴트' : isEn ? 'Real-time context-injected quant assistant for deep analysis' : 'Trợ lý phân tích có nạp toàn bộ dữ liệu dòng tiền & SHAP của coin'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
            {/* LLM Config Button */}
            <button
              type="button"
              onClick={() => setIsConfigModalOpen(true)}
              className="px-2 py-1 rounded-md border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-300 text-[11px] font-medium flex items-center gap-1 transition"
              title={isEn ? 'Configure LLM Provider (Gemini / OpenAI / Claude / Ollama)' : 'Cấu hình API LLM (Gemini, OpenAI, Claude, DeepSeek, Ollama)'}
            >
              <Settings className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden sm:inline">{llmConfig.apiKey ? (llmConfig.provider?.toUpperCase() || 'LLM') : 'Gemini 3.7 Tiered'}</span>
            </button>

            {/* Copy Entire Chat History Button */}
            {messages.length > 1 && (
              <button
                type="button"
                onClick={handleCopyEntireHistory}
                className={`px-2 py-1 rounded-md border text-[11px] font-medium flex items-center gap-1 transition ${
                  isAllCopied
                    ? 'border-emerald-500/60 bg-emerald-500/20 text-emerald-300'
                    : 'border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-300'
                }`}
                title={isEn ? 'Copy entire conversation to clipboard' : 'Sao chép toàn bộ nội dung hội thoại'}
              >
                {isAllCopied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-emerald-300">{isEn ? 'Copied' : 'Đã chép'}</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5 text-amber-400" />
                    <span className="hidden sm:inline">{isEn ? 'Copy All' : 'Chép hội thoại'}</span>
                  </>
                )}
              </button>
            )}

            {/* Clear Chat Button */}
            {messages.length > 1 && (
              <button
                type="button"
                onClick={handleClearHistory}
                className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
                title={isEn ? 'Clear chat history' : 'Xóa lịch sử chat'}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}

            {/* Fullscreen / Expand Window Toggle Button */}
            <button
              type="button"
              onClick={() => setIsExpanded(prev => !prev)}
              className={`p-1 sm:px-2 sm:py-1 rounded-md border text-[11px] font-medium flex items-center gap-1 transition ${
                isExpanded
                  ? 'border-amber-500/60 bg-amber-500/20 text-amber-300'
                  : 'border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-amber-300'
              }`}
              title={isExpanded ? (isEn ? 'Exit Fullscreen (Esc)' : 'Thu nhỏ cửa sổ (Esc)') : (isEn ? 'Expand Fullscreen' : 'Mở rộng toàn màn hình')}
            >
              {isExpanded ? (
                <>
                  <Minimize2 className="w-3.5 h-3.5 text-amber-400" />
                  <span className="hidden sm:inline">{isEn ? 'Minimize' : 'Thu nhỏ'}</span>
                </>
              ) : (
                <>
                  <Maximize2 className="w-3.5 h-3.5 text-amber-400" />
                  <span className="hidden sm:inline">{isEn ? 'Expand Full' : 'Mở rộng'}</span>
                </>
              )}
            </button>

            {/* Close button if expanded */}
            {isExpanded && (
              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                className="p-1 rounded-md text-slate-400 hover:text-rose-300 hover:bg-rose-950/40 border border-transparent hover:border-rose-800/50 transition"
                title={isEn ? 'Close Fullscreen' : 'Đóng toàn màn hình'}
              >
                <X className="w-4 h-4" />
              </button>
            )}

            {/* Minimize / Expand Toggle Button for Accordion */}
            {!isExpanded && onToggleOpen && (
              <button
                type="button"
                onClick={onToggleOpen}
                className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
              >
                {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>

        {/* Expandable Chat Body */}
        {(isOpen || isExpanded) && (
          <div className={`p-3 sm:p-4 space-y-3.5 flex flex-col ${isExpanded ? 'flex-1 min-h-0' : ''}`}>
            {/* Quick Suggestion Chips */}
            <div className="shrink-0">
              <div className="text-[10px] text-slate-500 font-mono uppercase mb-1.5 flex items-center gap-1">
                <HelpCircle className="w-3 h-3 text-amber-400" />
                <span>{isZh ? '快捷提问建议:' : isKo ? '빠른 질문 제안:' : isEn ? 'Quick Suggestion Prompts:' : 'Câu hỏi gợi ý nhanh 1-chạm:'}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {quickChips.map((chip, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSendQuestion(chip.prompt)}
                    disabled={isLoading}
                    className="px-2.5 py-1 rounded-full bg-slate-900 hover:bg-slate-800 border border-slate-700/80 hover:border-amber-500/50 text-[11px] text-slate-300 hover:text-amber-300 transition text-left disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    <span>{chip.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Chat Messages Log */}
            <div
              ref={chatContainerRef}
              className={`bg-slate-950/80 border border-slate-800/80 rounded-xl p-3 sm:p-4 overflow-y-auto space-y-3.5 font-sans ${
                isExpanded ? 'flex-1 min-h-0' : 'max-h-[460px] sm:max-h-[520px]'
              }`}
            >
              {messages.map((msg) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={msg.id}
                    className={`flex items-start gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div className="w-6 h-6 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center shrink-0 mt-0.5">
                        <Sparkles className="w-3.5 h-3.5" />
                      </div>
                    )}

                    <div
                      className={`rounded-xl p-3 sm:p-3.5 text-xs leading-relaxed ${
                        isExpanded ? 'max-w-[94%] sm:max-w-[90%]' : 'max-w-[90%] sm:max-w-[85%]'
                      } ${
                        isUser
                          ? 'bg-gradient-to-r from-amber-500 to-amber-400 text-slate-950 font-medium rounded-tr-none shadow-md'
                          : msg.isError
                          ? 'bg-rose-950/60 border border-rose-800 text-rose-200 rounded-tl-none shadow-md'
                          : 'bg-slate-900/95 border border-slate-800/90 text-slate-200 rounded-tl-none shadow-xl'
                      }`}
                    >
                      {/* Provider Header on Assistant Msg */}
                      {!isUser && msg.providerUsed && (
                        <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2.5 text-[10px] text-slate-400">
                          <span className="font-mono text-amber-400 font-semibold">{msg.providerUsed}</span>
                          <button
                            type="button"
                            onClick={() => handleCopyMessage(msg.id, msg.content)}
                            className="text-slate-400 hover:text-slate-200 flex items-center gap-1 text-[9px] transition"
                            title="Sao chép nội dung"
                          >
                            {copiedId === msg.id ? (
                              <>
                                <Check className="w-3 h-3 text-emerald-400" />
                                <span className="text-emerald-400 font-medium">{isEn ? 'Copied' : 'Đã sao chép'}</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3" />
                                <span>{isEn ? 'Copy' : 'Sao chép'}</span>
                              </>
                            )}
                          </button>
                        </div>
                      )}

                      {/* Content rendering */}
                      {isUser ? (
                        <div className="whitespace-pre-wrap leading-relaxed font-sans text-slate-950 font-medium">
                          {msg.content}
                        </div>
                      ) : (
                        <MarkdownRenderer content={msg.content} />
                      )}

                      <div className={`mt-2 text-[9px] font-mono text-right ${isUser ? 'text-slate-800 font-semibold' : 'text-slate-500'}`}>
                        {msg.timestamp}
                      </div>
                    </div>

                    {isUser && (
                      <div className="flex flex-col items-center gap-1 shrink-0 mt-0.5">
                        <div className="w-6 h-6 rounded-md bg-slate-800 border border-slate-700 text-slate-300 flex items-center justify-center">
                          <User className="w-3.5 h-3.5" />
                        </div>
                        <button
                          type="button"
                          onClick={() => handleCopyMessage(msg.id, msg.content)}
                          className="text-slate-500 hover:text-slate-300 p-0.5 transition"
                          title="Sao chép câu hỏi"
                        >
                          {copiedId === msg.id ? <Check className="w-2.5 h-2.5 text-emerald-400" /> : <Copy className="w-2.5 h-2.5" />}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Loading Indicator */}
              {isLoading && (
                <div className="flex items-start gap-2.5">
                  <div className="w-6 h-6 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center shrink-0 mt-0.5">
                    <Sparkles className="w-3.5 h-3.5 animate-pulse" />
                  </div>
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-400 rounded-tl-none flex items-center gap-2 font-mono">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                    <span>{isZh ? '正在深度分析市场数据与订单流...' : isKo ? '시장 데이터 및 오더플로우를 심층 분석 중...' : isEn ? 'Analyzing real-time market data & orderflow...' : 'Đang phân tích dữ liệu thị trường & dòng tiền...'}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Input Box */}
            <div className="relative flex items-center gap-2 shrink-0">
              <div className="relative flex-1">
                <textarea
                  ref={inputRef}
                  value={inputQuestion}
                  onChange={(e) => setInputQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendQuestion();
                    }
                  }}
                  rows={isExpanded ? 3 : 2}
                  placeholder={
                    isZh
                      ? `输入有关 ${symbol} 的任何问题 (按 Enter 发送, Shift+Enter 换行)...`
                      : isKo
                      ? `${symbol}에 대해 궁금한 점을 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)...`
                      : isEn
                      ? `Ask anything about ${symbol} (Press Enter to send, Shift+Enter for newline)...`
                      : `Hỏi bất kỳ điều gì về ${symbol} (Nhấn Enter để gửi, Shift+Enter để xuống dòng)...`
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2.5 pr-10 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500 transition resize-none leading-relaxed"
                />
              </div>

              <button
                type="button"
                onClick={() => handleSendQuestion()}
                disabled={!inputQuestion.trim() || isLoading}
                className="px-4 sm:px-5 py-3 bg-amber-500 hover:bg-amber-400 disabled:bg-slate-800 text-slate-950 disabled:text-slate-500 font-bold rounded-xl text-xs flex items-center justify-center transition shadow-md shadow-amber-500/20 disabled:cursor-not-allowed shrink-0 h-full"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* LLM Provider Configuration Modal */}
      <LlmConfigModal
        isOpen={isConfigModalOpen}
        onClose={() => setIsConfigModalOpen(false)}
        config={llmConfig}
        onSaveConfig={handleSaveConfig}
      />
    </>
  );
};
