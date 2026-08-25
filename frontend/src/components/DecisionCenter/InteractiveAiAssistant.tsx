import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles, Send, Settings, Trash2, Bot,
  User, Copy, Check, ChevronDown, ChevronUp,
  HelpCircle
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import type {
  CoinDetail, DeepAnalysis, TradeSetup,
  ChatMessage, LlmConfig, AiAskRequest, AiAskResponse
} from '../../types';
import { LlmConfigModal } from './LlmConfigModal';

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
      provider: 'gemini',
      apiKey: '',
      modelId: 'gemini-1.5-flash',
      enabled: true,
    };
  });

  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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

  // Scroll to bottom when messages update
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

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
      <div className="bg-slate-950/90 border border-slate-800 rounded-xl overflow-hidden shadow-2xl transition-all duration-200">
        {/* Assistant Header */}
        <div className="flex items-center justify-between px-3.5 sm:px-4 py-3 border-b border-slate-800/80 bg-slate-900/60">
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
              <span className="hidden sm:inline">{llmConfig.apiKey ? (llmConfig.provider?.toUpperCase() || 'LLM') : (isEn ? 'Configure API' : 'Gắn API Key')}</span>
            </button>

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

            {/* Minimize / Expand Toggle Button */}
            {onToggleOpen && (
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
        {isOpen && (
          <div className="p-3 sm:p-4 space-y-3.5">
            {/* Quick Suggestion Chips */}
            <div>
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
            <div className="bg-slate-950/80 border border-slate-800/80 rounded-xl p-3 sm:p-4 max-h-80 overflow-y-auto space-y-3.5 font-sans">
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
                      className={`max-w-[85%] sm:max-w-[80%] rounded-xl p-3 text-xs leading-relaxed ${
                        isUser
                          ? 'bg-amber-500 text-slate-950 font-medium rounded-tr-none shadow-md'
                          : msg.isError
                          ? 'bg-rose-950/60 border border-rose-800 text-rose-200 rounded-tl-none'
                          : 'bg-slate-900/90 border border-slate-800 text-slate-200 rounded-tl-none shadow-md'
                      }`}
                    >
                      {/* Provider Header on Assistant Msg */}
                      {!isUser && msg.providerUsed && (
                        <div className="flex items-center justify-between border-b border-slate-800/80 pb-1.5 mb-2 text-[10px] text-slate-400">
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
                                <span className="text-emerald-400">{isEn ? 'Copied' : 'Đã sao chép'}</span>
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
                      <div className="whitespace-pre-line space-y-1.5 prose-invert">
                        {msg.content}
                      </div>

                      <div className={`mt-1.5 text-[9px] font-mono text-right ${isUser ? 'text-slate-800' : 'text-slate-500'}`}>
                        {msg.timestamp}
                      </div>
                    </div>

                    {isUser && (
                      <div className="w-6 h-6 rounded-md bg-slate-800 border border-slate-700 text-slate-300 flex items-center justify-center shrink-0 mt-0.5">
                        <User className="w-3.5 h-3.5" />
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

              <div ref={messagesEndRef} />
            </div>

            {/* Input Box */}
            <div className="relative flex items-center gap-2">
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
                  rows={2}
                  placeholder={
                    isZh
                      ? `输入有关 ${symbol} 的任何问题 (按 Enter 发送)...`
                      : isKo
                      ? `${symbol}에 대해 궁금한 점을 입력하세요 (Enter로 전송)...`
                      : isEn
                      ? `Ask anything about ${symbol} (Press Enter to send)...`
                      : `Hỏi bất kỳ điều gì về ${symbol} (Nhấn Enter để gửi)...`
                  }
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2.5 pr-10 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500 transition resize-none leading-relaxed"
                />
              </div>

              <button
                type="button"
                onClick={() => handleSendQuestion()}
                disabled={!inputQuestion.trim() || isLoading}
                className="px-4 py-3 bg-amber-500 hover:bg-amber-400 disabled:bg-slate-800 text-slate-950 disabled:text-slate-500 font-bold rounded-xl text-xs flex items-center justify-center transition shadow-md shadow-amber-500/20 disabled:cursor-not-allowed shrink-0 h-full"
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
