import React, { useState, useEffect, useMemo } from 'react';
import {
  X,
  Search,
  BookOpen,
  Lightbulb,
  Target,
  BarChart3,
  Activity,
  Layers,
  FlaskConical,
  ShieldCheck,
  Cpu,
  Clock,
  GitPullRequest,
  Settings,
  Radio,
  ChevronRight,
  Sparkles,
  CheckCircle2
} from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';
import type { WorkspaceTab } from './WorkspaceTabBar';

export interface TabHelpModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: WorkspaceTab;
}

interface TabGuideItem {
  id: WorkspaceTab;
  name: string;
  nameEn: string;
  icon: React.ComponentType<{ className?: string }>;
  category: 'TRADING' | 'LAB' | 'SYSTEM';
  badge?: string;
  purpose: string;
  mechanism: string[];
  metrics: Array<{ label: string; desc: string }>;
  playbook: string[];
}
export const TabHelpModal: React.FC<TabHelpModalProps> = ({
  isOpen,
  onClose,
  activeTab,
}) => {
  const { language } = useTranslation();
  const [selectedTab, setSelectedTab] = useState<WorkspaceTab>(activeTab);
  const [searchTerm, setSearchTerm] = useState('');

  // Sync selected tab with prop when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedTab(activeTab);
      setSearchTerm('');
    }
  }, [isOpen, activeTab]);

  const guides = useMemo<Record<WorkspaceTab, TabGuideItem>>(() => {
    if (language === 'en') {
      return {
        DECISION: {
          id: 'DECISION',
          name: 'Decision Center',
          nameEn: 'Decision Center',
          icon: Target,
          category: 'TRADING',
          badge: 'V2 2-Tier Engine',
          purpose: 'Real-time quantitative trade cockpit providing concrete trade setups (Entry, SL, TP1-3, R:R), 15m/5m live derivatives candlestick charts, and AI SHAP feature attribution.',
          mechanism: [
            'Two-Tier Climax Scoring: Combines macro pump amplitude (Tier 1 HTF) with micro order-flow exhaustion (Tier 2 LTF).',
            'Dynamic Trade Setup: Automatically calculates Stop Loss based on recent 5m/15m swing highs and Multi-tier Take Profit targets (-4% TP1, -8% TP2, -12% TP3).',
            'Live Binance Integration: Zero-lag order book ticker, live Funding APR, and Open Interest change rates.',
            'Interactive AI Assistant: Built-in LLM analyst for deep coin breakdown and risk diagnosis.'
          ],
          metrics: [
            { label: 'Distribution Score', desc: 'Quantitative composite score (0-100) indicating top climax exhaustion level.' },
            { label: 'Probability (%)', desc: 'Calibrated empirical probability of reaching the -8% drawdown target within 24h.' },
            { label: 'Funding APR', desc: 'Annualized funding cost. Highly positive or inverted negative rates highlight liquidation traps.' },
            { label: 'Taker Sell Ratio', desc: 'Percentage of aggressive market sell orders. Values > 55% show institutional dumping.' },
            { label: 'R:R Ratio', desc: 'Reward-to-Risk ratio calculated as (TP1 potential / SL risk).' }
          ],
          playbook: [
            'Check that the signal is in "FIRED" or high-probability "ARMED" state.',
            'Verify that Taker Sell Ratio >= 55% and OI change is stalling or turning negative.',
            'Enter Short within the suggested Entry Zone, set strict Stop Loss as prescribed, and take 50% profit at TP1 (-4%).'
          ]
        },
        RADAR: {
          id: 'RADAR',
          name: 'Signal Radar',
          nameEn: 'Signal Feed',
          icon: Activity,
          category: 'TRADING',
          badge: 'Real-time Feed',
          purpose: '24/7 continuous signal feed detecting distribution tops across all Binance USDT Futures pairs.',
          mechanism: [
            'Continuous Scanner Daemon: Periodically monitors candidate universe and triggers instant climax alerts.',
            '2-Tier State Classification: Labels signals as ARMED (Pre-condition met, waiting for trigger) or FIRED (Active short trigger).',
            'Multi-dimensional Filtering: Filter by Strategic Presets, Sectors (AI, Meme, L1/L2), Market Cap Tiers, and Risk Levels.',
            'Telegram Push Integration: Instant multi-tier push alerts directly to Telegram channels.'
          ],
          metrics: [
            { label: 'FIRED / ARMED State', desc: 'FIRED = Immediate short execution; ARMED = High-alert setup watching for 5m breakdown.' },
            { label: 'Risk Level', desc: 'CRITICAL / HIGH / MEDIUM / SAFE classified by pump amplitude and volatility.' },
            { label: 'Market Cap Tier', desc: 'LARGE (> $1B), MID ($100M - $1B), SMALL (< $100M) sizing.' },
            { label: 'Validity Hours', desc: 'Hours left before signal expiration (default 24h).' }
          ],
          playbook: [
            'Filter by "FIRED" tab to see coins actively breaking down right now.',
            'Use Strategic Presets like "Climax Dump" or "OI Squeeze" for specific trade setups.',
            'Click on any signal card to instantly load its full chart and analytics in the Decision Center.'
          ]
        },
        WATCHLIST: {
          id: 'WATCHLIST',
          name: 'Tracking Watchlist',
          nameEn: 'Watchlist & PnL',
          icon: Layers,
          category: 'TRADING',
          badge: 'Position Tracker',
          purpose: 'Manage personal coin watchlists, preset scan modes, and track open short positions with live PnL & ROI.',
          mechanism: [
            '5 Scan Presets: Top Volatile, Top Volume, Top Gainers, Top Losers, and Manual Custom Watchlist.',
            'Live Position Tracking: Record Entry Price, Leverage, SL, TP, and monitor real-time unrealized PnL & ROI%.',
            'Local & Server Sync: Watchlist persists across browser sessions and syncs with scanner daemon.'
          ],
          metrics: [
            { label: 'Position PnL ($)', desc: 'Real-time dollar profit/loss based on live Binance market price.' },
            { label: 'Position ROI (%)', desc: 'Percentage return on margin considering leverage.' },
            { label: 'Signal Progress (%)', desc: 'Progress bar measuring distance from Entry to Target TP (-8%).' }
          ],
          playbook: [
            'Add coins from Radar or Ranking directly to Tracking Watchlist with one click.',
            'Log your executed trade details to monitor live SL/TP trailing without switching to exchange.'
          ]
        },
        RANKING: {
          id: 'RANKING',
          name: 'Candidate Ranking',
          nameEn: 'Candidate Filter',
          icon: BarChart3,
          category: 'TRADING',
          badge: 'Tier 1 Filter',
          purpose: 'Tier 1 candidate screening ranking top climax candidates from 678+ Binance Futures coins, featuring live A/B verification progress.',
          mechanism: [
            'Champion V2 vs Challenger V1: V2 (multi-stage quant filter, max 30 coins) runs main lane; V1 (hard threshold, 10 coins) runs parallel shadow baseline.',
            '72-Hour State Memory: Tracks pump lifecycle from Pump Active -> Climax Exhaustion -> Distribution -> Markdown.',
            'A/B Verification Progress: Live countdown tracking 3 promotion gates (14 evaluation days, 50 positive climax events, 200 resolved samples) before safely retiring V1.'
          ],
          metrics: [
            { label: 'Rank Score', desc: 'Multi-factor quantitative score ranking highest probability dump candidates.' },
            { label: 'Stage', desc: 'PUMP_ACTIVE, EXHAUSTION, DISTRIBUTION, or DUMPED.' },
            { label: 'P@10 (Precision at 10)', desc: 'Empirical precision among Top 10 ranked candidates.' },
            { label: 'Event Recall', desc: 'Percentage of total market dump events successfully captured.' }
          ],
          playbook: [
            'Focus on candidates in "EXHAUSTION" or "DISTRIBUTION" stage for imminent short setups.',
            'Check the A/B Test Verification Card to inspect model promotion readiness.'
          ]
        },
        MULTISCAN: {
          id: 'MULTISCAN',
          name: 'Multi-Coin Scan',
          nameEn: 'Multi-Timeframe',
          icon: Radio,
          category: 'LAB',
          badge: 'Multi-TF',
          purpose: 'Multi-timeframe correlation scanner analyzing market-wide volatility across 5m, 15m, 1h, 4h, and 1D.',
          mechanism: [
            'Cross-Timeframe Volatility Matrix: Evaluates synchronized climax patterns across all standard trading frames.',
            'Historical Run Registry: Archives multi-coin scan runs and volatility breakdown artifacts.'
          ],
          metrics: [
            { label: 'Timeframe Alignment', desc: 'Synchronization index across 5m, 15m, 1h, 4h trends.' },
            { label: 'Artifact Runs', desc: 'Total historical scan batches archived for quant verification.' }
          ],
          playbook: [
            'Use Multi-Scan to identify broader sector pumps when multiple related tokens hit climax simultaneously.'
          ]
        },
        BACKTEST: {
          id: 'BACKTEST',
          name: 'Backtest Lab',
          nameEn: 'Validation Lab',
          icon: FlaskConical,
          category: 'LAB',
          badge: '85 Artifacts',
          purpose: 'Rigorous empirical validation lab evaluating strategy performance across 2.6+ years of historical market data.',
          mechanism: [
            'Purged & Embargoed Walk-Forward Cross Validation: Strictly trains on past data, tests on future data with zero lookahead bias.',
            'Leakage Audit Suite: 100% automated check ensuring no future data contamination.',
            'Metric Distributions: Precision mean, baseline comparisons, Brier calibration, and drawdown distributions.'
          ],
          metrics: [
            { label: 'Precision Mean', desc: 'Average precision across all validation folds.' },
            { label: 'Baseline Precision', desc: 'Precision of random / heuristic benchmark for edge verification.' },
            { label: 'Brier Calibration', desc: 'Calibration error score (lower = better probability fidelity).' }
          ],
          playbook: [
            'Inspect backtest artifacts to verify mathematical edge before deploying modified trading rules.'
          ]
        },
        FORWARD: {
          id: 'FORWARD',
          name: 'Forward Test',
          nameEn: 'Out-of-Sample',
          icon: Sparkles,
          category: 'LAB',
          badge: 'Frozen ML',
          purpose: 'Out-of-sample live simulation evaluating frozen Machine Learning models on unseen market periods.',
          mechanism: [
            'Frozen Model Artifacts: Bundled LightGBM models + Isotonic Calibrators stored with immutable hashes.',
            'Out-of-Sample Evaluation: Evaluates performance against live collected market outcomes.'
          ],
          metrics: [
            { label: 'Frozen Model ID', desc: 'Immutable identifier of the production ML model checkpoint.' },
            { label: 'OOS Precision', desc: 'Live out-of-sample precision on newly recorded market cycles.' }
          ],
          playbook: [
            'Compare performance across different frozen models to select the champion checkpoint.'
          ]
        },
        AUDIT: {
          id: 'AUDIT',
          name: 'Model Audit',
          nameEn: 'Audit Matrix',
          icon: ShieldCheck,
          category: 'LAB',
          badge: 'Diagnostics',
          purpose: 'Deep machine learning diagnostics, confusion matrices, probability calibration curves, and feature importance.',
          mechanism: [
            'Confusion Matrix: True Positives (TP), False Positives (FP), True Negatives (TN), False Negatives (FN).',
            'Reliability Curve: Brier score calibration mapping forecasted probability vs actual empirical frequency.'
          ],
          metrics: [
            { label: 'ROC-AUC', desc: 'Area Under the ROC Curve measuring model discriminative power.' },
            { label: 'F1 Score', desc: 'Harmonic mean of Precision and Recall.' },
            { label: 'Target Drawdown Benchmark', desc: 'Standard target: >= 8% drawdown with <= 4% MAE.' }
          ],
          playbook: [
            'Verify model calibration curve to ensure a 75% forecasted probability translates to 75% real-world hit rate.'
          ]
        },
        MARKET: {
          id: 'MARKET',
          name: 'Market Overview & Alpha Lab',
          nameEn: 'Market & Alpha',
          icon: Activity,
          category: 'SYSTEM',
          badge: 'Alpha Lab',
          purpose: 'Comprehensive Binance listing intelligence, market regime diagnostics (ADX/BB), Meta-labeling filter, and Drift Guardian.',
          mechanism: [
            'Binance Listing Breakdown: Daily scan of 810+ coins (Spot vs Futures, Spot-only, Futures-only).',
            'Market Regime Classifier: Identifies Trending Bear / Bull / Choppy regimes to adjust risk multipliers.',
            'Meta-Labeling Engine: Secondary HistGradientBoosting model filtering out 55-60% of false signals.',
            'Drift Guardian: Continuous Population Stability Index (PSI) monitoring to detect alpha decay.'
          ],
          metrics: [
            { label: 'Market Regime', desc: 'Current macro market state (e.g. TRENDING_BEAR, CHOPPY, RANGE).' },
            { label: 'ADX Trend Strength', desc: 'Average Directional Index (> 25 indicates strong directional trend).' },
            { label: 'Drift Status', desc: 'HEALTHY / WARNING / CRITICAL based on feature distribution drift.' }
          ],
          playbook: [
            'Check Market Regime before trading: In TRENDING_BEAR regimes, Short setups have significantly higher winrates.'
          ]
        },
        TELEMETRY: {
          id: 'TELEMETRY',
          name: 'Telemetry & Logs',
          nameEn: 'System Health',
          icon: Cpu,
          category: 'SYSTEM',
          badge: '24/7 Monitor',
          purpose: 'Real-time scanner daemon health monitor, memory/CPU usage, cycle duration, and Telegram bot status.',
          mechanism: [
            'Scanner Heartbeat: Monitors live daemon polling cycles every 5 minutes.',
            'Resource Telemetry: CPU %, Memory RSS (MB), DuckDB locks, and queue lengths.'
          ],
          metrics: [
            { label: 'Daemon Status', desc: 'RUNNING / IDLE / OFFLINE state of the background scanner.' },
            { label: 'Cycle Duration', desc: 'Time taken in seconds to scan and score all coins in universe.' },
            { label: 'Scanned Coins Count', desc: 'Number of active coins processed in latest cycle.' }
          ],
          playbook: [
            'Verify daemon is RUNNING with recent heartbeat timestamp to ensure continuous market protection.'
          ]
        },
        HISTORY: {
          id: 'HISTORY',
          name: 'System History',
          nameEn: 'Archive & DB',
          icon: Clock,
          category: 'SYSTEM',
          badge: 'DuckDB',
          purpose: 'Historical signal archives, daily alert counts, DuckDB storage inspection, and long-term performance logs.',
          mechanism: [
            'DuckDB Aggregation: Daily timeline of signals issued, hit rates, and scan frequencies.',
            'Historical Data Stats: Min/Max timestamps of collected derivatives tables.'
          ],
          metrics: [
            { label: 'Signals per Day', desc: 'Historical daily count of fired alerts and successful target hits.' },
            { label: 'Scan Cycles per Day', desc: 'Daily execution volume of 24/7 scanning daemon.' }
          ],
          playbook: [
            'Review multi-day performance trends to track signal frequency across different market weeks.'
          ]
        },
        UPDATES: {
          id: 'UPDATES',
          name: 'Version & Updates',
          nameEn: 'Git & Auto-updater',
          icon: GitPullRequest,
          category: 'SYSTEM',
          badge: 'v2.0 Pro',
          purpose: 'Git commit history, 8 architectural milestones, development velocity metrics, and 1-click system auto-updater.',
          mechanism: [
            '3-Tier Auto-Updater: 5-minute server auto-sync cron, 1-click UI update button, and PWA v3.1 cache purge.',
            'Git Analytics: Commit classification (feat, fix, perf, docs) and active development days.'
          ],
          metrics: [
            { label: 'Current Commit', desc: 'Active Git commit hash deployed on server.' },
            { label: 'Update Status', desc: 'Displays whether newer commits exist on GitHub origin/main.' }
          ],
          playbook: [
            'Click "Check & Apply Update" whenever new features are pushed to synchronize server in seconds.'
          ]
        },
        SETTINGS: {
          id: 'SETTINGS',
          name: 'System Settings',
          nameEn: 'Settings & AI',
          icon: Settings,
          category: 'SYSTEM',
          badge: 'Config',
          purpose: 'AI Assistant LLM configuration (OpenAI/DeepSeek/Gemini), scanner parameters, alert thresholds, and language preferences.',
          mechanism: [
            'AI Provider Key Management: Secure API key configuration for interactive LLM market analysis.',
            'UI Customization: GUI version selection (V1 / V2), alert sound toggles, and language switching.'
          ],
          metrics: [
            { label: 'AI Provider', desc: 'Selected LLM provider for AI Executive Briefings.' },
            { label: 'Alert Score Threshold', desc: 'Minimum distribution score required to trigger alert.' }
          ],
          playbook: [
            'Configure your Gemini / DeepSeek API key to unlock the Interactive AI Assistant in the Decision Center.'
          ]
        }
      };
    }

    // Default: Tiếng Việt (Vietnamese)
    return {
      DECISION: {
        id: 'DECISION',
        name: 'Trung tâm Ra Quyết Định',
        nameEn: 'Decision Center',
        icon: Target,
        category: 'TRADING',
        badge: 'V2 2-Tier Climax Engine',
        purpose: 'Buồng lái ra quyết định giao dịch theo thời gian thực — cung cấp kế hoạch vào lệnh chuẩn xác (Entry, Stop Loss, TP1-3, R:R), biểu đồ nến 15m/5m live phái sinh và trợ lý AI phân tích chuyên sâu.',
        mechanism: [
          'Chấm điểm Phân phối 2 Tầng (2-Tier Climax Scoring): Kết hợp biên độ bơm vĩ mô khung 1h/4h/24h (Tầng 1) với dấu hiệu xả vi mô dòng lệnh 5m/15m (Tầng 2).',
          'Kế hoạch Trade Setup Động: Tự động tính điểm Stop Loss ngay trên đỉnh nến gần nhất (tránh quét râu) và 3 mức Take Profit (-4% TP1, -8% TP2, -12% TP3).',
          'Tích hợp Trực tiếp Binance Live: Cập nhật giá, funding rate APR, biến động OI và tỷ lệ Taker Sell theo từng giây.',
          'Trợ lý AI Đàm Thoại: Chat trực tiếp với AI để phân tích lý do rủi ro, phân tích SHAP và chiến lược đi vốn.'
        ],
        metrics: [
          { label: 'Điểm Phân Phối (Distribution Score)', desc: 'Điểm số định lượng (0-100) đánh giá mức độ kiệt sức và tạo đỉnh phân phối.' },
          { label: 'Xác Suất (%)', desc: 'Xác suất thực nghiệm đã hiệu chuẩn về khả năng giá sụt giảm >= 8% trong 24h.' },
          { label: 'Funding Rate & APR', desc: 'Tỷ lệ phí funding quy đổi ra %/năm. Giúp nhận diện bẫy ép lệnh Long/Short.' },
          { label: 'Taker Sell Ratio', desc: 'Tỷ lệ lệnh bán chủ động cắn qua giá bid. Vượt > 55% cho thấy phe bán tổ chức đang xả mạnh.' },
          { label: 'Tỷ Lệ R:R (Risk/Reward)', desc: 'Tỷ lệ lợi nhuận / rủi ro tính theo (Biên độ TP1 / Biên độ SL).' }
        ],
        playbook: [
          'Kiểm tra tín hiệu xem đang ở trạng thái "FIRED" (đang xả) hay "ARMED" (sẵn sàng).',
          'Đối chiếu Taker Sell Ratio >= 55% và Open Interest bắt đầu giảm hoặc đi ngang.',
          'Vào lệnh Short trong Vùng Entry gợi ý, cài SL nghiêm ngặt và chốt lời 50% vị thế tại TP1 (-4%).'
        ]
      },
      RADAR: {
        id: 'RADAR',
        name: 'Radar Tín Hiệu Cảnh Báo',
        nameEn: 'Signal Feed',
        icon: Activity,
        category: 'TRADING',
        badge: 'Feed Trực Tiếp 24/7',
        purpose: 'Bảng theo dõi dòng tín hiệu phân phối đỉnh hoạt động liên tục 24/7 trên toàn bộ các cặp coin USDT Futures sàn Binance.',
        mechanism: [
          'Tiến trình Quét Tự động: Quét toàn thị trường định kỳ 5 phút/lần và phát hiện ngay lập tức các coin đạt điểm phân phối.',
          'Phân loại Trạng thái 2 Tầng: Gán nhãn rõ ràng ARMED (Tiền điều kiện đạt, canh nến đảo chiều) hoặc FIRED (Tín hiệu xả đã kích hoạt).',
          'Bộ lọc Chiến lược Đa chiều: Lọc theo Preset (Climax Dump, Bẫy Funding, OI Squeeze), Sector (AI, Meme, L1/L2), Vốn hóa và Mức độ rủi ro.',
          'Đẩy Cảnh báo Telegram: Tự động gửi cảnh báo phân tích chất lượng cao về nhóm Telegram.'
        ],
        metrics: [
          { label: 'Trạng Thái FIRED / ARMED', desc: 'FIRED = Điểm vào lệnh Short ngay; ARMED = Đang tạo đỉnh, chờ nến 5m xác nhận.' },
          { label: 'Mức Độ Rủi Ro (Risk Level)', desc: 'Phân cấp CRITICAL / HIGH / MEDIUM / SAFE dựa trên biến động và biên độ bơm.' },
          { label: 'Phân Hạng Vốn Hóa', desc: 'LARGE (> $1B), MID ($100M - $1B), SMALL (< $100M).' },
          { label: 'Thời Gian Hiệu Lực', desc: 'Số giờ còn lại trước khi tín hiệu hết hạn (mặc định 24h).' }
        ],
        playbook: [
          'Chọn tab "FIRED" để xem các coin đang trong nhịp xả đẹp nhất ở hiện tại.',
          'Sử dụng các Preset chiến lược như "Climax Dump" hoặc "Bẫy Funding" để tìm setup theo sở trường.',
          'Bấm vào bất kỳ thẻ tín hiệu nào để mở ngay biểu đồ chi tiết bên Trung tâm Ra quyết định.'
        ]
      },
      WATCHLIST: {
        id: 'WATCHLIST',
        name: 'Danh Sách Theo Dõi & Vị Thế',
        nameEn: 'Tracking Watchlist',
        icon: Layers,
        category: 'TRADING',
        badge: 'Quản Lý PnL',
        purpose: 'Quản lý danh mục coin theo dõi cá nhân, các chế độ quét tự động và ghi nhận quản trị vị thế Short thực tế với PnL & ROI live.',
        mechanism: [
          '5 Chế độ Preset: Top Biến động, Top Volume, Top Tăng giá, Top Giảm giá và Watchlist tùy chọn.',
          'Theo Dõi Vị Thế Trực Tiếp: Lưu giá Entry, Đòn bẩy, SL, TP và tự động tính toán PnL, ROI% theo thời gian thực.',
          'Đồng Bộ Dữ Liệu: Lưu trữ trên trình duyệt và tự động đồng bộ với Daemon quét thị trường.'
        ],
        metrics: [
          { label: 'PnL Vị Thế ($)', desc: 'Lợi nhuận/thua lỗ danh nghĩa dựa theo giá thị trường Binance hiện tại.' },
          { label: 'ROI Vị Thế (%)', desc: 'Tỷ suất sinh lời trên vốn ký quỹ có tính đòn bẩy.' },
          { label: 'Tiến Độ Tín Hiệu (%)', desc: 'Thanh tiến trình đo khoảng cách từ điểm Entry đến Target TP (-8%).' }
        ],
        playbook: [
          'Thêm coin trực tiếp từ Radar hoặc Ranking vào Watchlist chỉ với 1 click.',
          'Ghi nhận thông số vào lệnh thực tế để theo dõi lãi/lỗ mà không cần mở sàn giao dịch.'
        ]
      },
      RANKING: {
        id: 'RANKING',
        name: 'Bảng Xếp Hạng Ứng Viên Bán',
        nameEn: 'Candidate Filter',
        icon: BarChart3,
        category: 'TRADING',
        badge: 'Bộ Lọc Tầng 1 (V2 Champion)',
        purpose: 'Tầng 1 chọn lọc ứng viên tiềm năng nhất từ ~678 coin Binance Futures, tích hợp bảng theo dõi tiến độ kiểm định A/B để nghiệm thu V2.',
        mechanism: [
          'Champion V2 vs Challenger V1: V2 (lọc đa tầng định lượng, trần 30 coin) vận hành chính; V1 (ngưỡng cứng, 10 coin) chạy ngầm làm mốc đối chứng.',
          'Bộ Nhớ Trạng Thái 72 Giờ: Theo dõi chu kỳ bơm xả qua từng giai đoạn (Đang bơm -> Kiệt sức -> Phân phối -> Bắt đầu xả).',
          'Thanh Tiến Độ Kiểm Định A/B: Đo lường trực tiếp 3 điều kiện thăng hạng (14 ngày quan sát, 50 sự kiện sập đỉnh, 200 mẫu giải quyết) để biết thời điểm gỡ bỏ V1.'
        ],
        metrics: [
          { label: 'Điểm Rank Score', desc: 'Điểm tổng hợp định lượng xếp hạng các ứng viên có xác suất sập cao nhất.' },
          { label: 'Giai Đoạn (Stage)', desc: 'PUMP_ACTIVE (Đang bơm), EXHAUSTION (Kiệt sức), DISTRIBUTION (Phân phối), DUMPED (Đã xả).' },
          { label: 'P@10 (Độ chính xác Top 10)', desc: 'Tỷ lệ chính xác thực nghiệm trong Top 10 ứng viên đứng đầu.' },
          { label: 'Event Recall', desc: 'Tỷ lệ bắt trọn các đợt sập đỉnh lớn của thị trường.' }
        ],
        playbook: [
          'Ưu tiên chọn các coin ở giai đoạn "EXHAUSTION" hoặc "DISTRIBUTION" để chuẩn bị lệnh Short đón đầu.',
          'Theo dõi Card "Tiến độ thử nghiệm A/B" để biết chính xác thời gian hoàn thành nghiệm thu.'
        ]
      },
      MULTISCAN: {
        id: 'MULTISCAN',
        name: 'Quét Đa Khung Thời Gian',
        nameEn: 'Multi-Coin Scan',
        icon: Radio,
        category: 'LAB',
        badge: 'Đa Khung 5m-1D',
        purpose: 'Bộ quét phân tích tương quan đa khung thời gian (5m, 15m, 1h, 4h, 1D) nhằm phát hiện sóng bơm xả đồng pha trên toàn thị trường.',
        mechanism: [
          'Ma Trận Biến Động Đa Khung: Đánh giá sự đồng thuận xu hướng tạo đỉnh giữa khung nến siêu ngắn và khung nến lớn.',
          'Lịch Sử Quét Đa Coin: Lưu trữ các đợt quét toàn thị trường để đối soát và nghiên cứu định lượng.'
        ],
        metrics: [
          { label: 'Độ Đồng Thuận Đa Khung', desc: 'Chỉ số đo lường sự trùng khớp tín hiệu giữa các khung 5m, 15m, 1h, 4h.' },
          { label: 'Lượt Chạy Quét (Runs)', desc: 'Tổng số lượt quét đa coin đã được lưu trữ trong kho lưu trữ.' }
        ],
        playbook: [
          'Dùng MultiScan để nhận diện khi cả một nhóm coin cùng hệ (Meme, AI) đồng loạt tạo đỉnh phân phối.'
        ]
      },
      BACKTEST: {
        id: 'BACKTEST',
        name: 'Phòng Thí Nghiệm Backtest',
        nameEn: 'Backtest Lab',
        icon: FlaskConical,
        category: 'LAB',
        badge: '85 Thí Nghiệm',
        purpose: 'Phòng thí nghiệm kiểm định nghiêm ngặt hiệu quả của thuật toán trên 2.6+ năm dữ liệu lịch sử thị trường.',
        mechanism: [
          'Kiểm Định Cuốn Chiếu (Walk-Forward Validation + Embargo): Chỉ huấn luyện trên quá khứ, kiểm tra trên tương lai — loại bỏ 100% nhìn trước (Zero Data Leakage).',
          'Kiểm Toán Rò Rỉ Dữ Liệu: Tự động chạy bộ test chứng minh thuật toán không sử dụng dữ liệu tương lai.',
          'Phân Phối Kết Quả: Thống kê Precision trung bình, Baseline đối chứng, Brier calibration và phân bố qua các fold.'
        ],
        metrics: [
          { label: 'Precision Mean', desc: 'Độ chính xác trung bình qua tất cả các đợt kiểm định cuốn chiếu.' },
          { label: 'Baseline Precision', desc: 'Độ chính xác của phương pháp ngẫu nhiên / quy tắc đơn giản dùng để chứng minh lợi thế (Alpha).' },
          { label: 'Brier Score', desc: 'Độ chuẩn xác của xác suất (càng thấp càng tốt, lý tưởng < 0.15).' }
        ],
        playbook: [
          'Kiểm tra kết quả backtest của từng giả thuyết trước khi áp dụng tham số mới vào hệ thống chạy thực.'
        ]
      },
      FORWARD: {
        id: 'FORWARD',
        name: 'Forward Test (Out-of-Sample)',
        nameEn: 'Mô Hình Đóng Băng',
        icon: Sparkles,
        category: 'LAB',
        badge: 'Frozen ML',
        purpose: 'Đánh giá các mô hình Machine Learning đóng băng (Frozen LightGBM) trên tập dữ liệu ngoài mẫu (Out-of-Sample) để chống Overfitting.',
        mechanism: [
          'Mô Hình Đóng Băng (Frozen Model): Đóng gói trọng số mô hình LightGBM + Isotonic Calibrator kèm mã băm Checksum bất biến.',
          'Đánh Giá Ngoài Mẫu: So sánh xác suất dự báo với kết quả thực tế phát sinh sau thời điểm đóng băng.'
        ],
        metrics: [
          { label: 'Mã Mô Hình (Model ID)', desc: 'Định danh duy nhất của phiên bản mô hình ML được đóng băng.' },
          { label: 'OOS Precision', desc: 'Độ chính xác thực tế trên các chu kỳ thị trường mới chưa từng xuất hiện trong tập huấn luyện.' }
        ],
        playbook: [
          'So sánh hiệu năng giữa các phiên bản mô hình đóng băng để chọn ra bản Champion tối ưu nhất.'
        ]
      },
      AUDIT: {
        id: 'AUDIT',
        name: 'Kiểm Định Mô Hình & Ma Trận',
        nameEn: 'Model Audit',
        icon: ShieldCheck,
        category: 'LAB',
        badge: 'Chẩn Đoán ML',
        purpose: 'Chẩn đoán chi tiết chất lượng mô hình Machine Learning: Ma trận nhầm lẫn (Confusion Matrix), đường cong hiệu chuẩn Brier và độ quan trọng của đặc trưng.',
        mechanism: [
          'Ma Trận Nhầm Lẫn (Confusion Matrix): Phân tích chi tiết số ca Đúng Dương tính (TP), Sai Dương tính (FP), Đúng Âm tính (TN), Sai Âm tính (FN).',
          'Đường Cong Hiệu Chuẩn (Calibration Curve): Đối chiếu xác suất AI dự báo so với tần suất sụt giảm thực tế.'
        ],
        metrics: [
          { label: 'ROC-AUC', desc: 'Diện tích dưới đường cong ROC đo lường khả năng phân biệt đỉnh của mô hình.' },
          { label: 'F1-Score', desc: 'Trung bình điều hòa giữa Precision (Độ chính xác) và Recall (Độ bao quát).' },
          { label: 'Tiêu Chuẩn Target', desc: 'Quy chuẩn: Giá giảm >= 8% trong 24h và độ giật ngược MAE <= 4%.' }
        ],
        playbook: [
          'Quan sát đường cong hiệu chuẩn: Một mô hình tốt phải đảm bảo khi báo xác suất 75% thì thực tế có đúng 75% trường hợp giá xả thật.'
        ]
      },
      MARKET: {
        id: 'MARKET',
        name: 'Tổng Quan Thị Trường & Alpha Lab',
        nameEn: 'Market & Alpha',
        icon: Activity,
        category: 'SYSTEM',
        badge: 'Alpha Lab Guardian',
        purpose: 'Báo cáo cấu trúc 810 coin Binance, nhận diện trạng thái thị trường (Market Regime), bộ lọc Meta-labeling và giám sát suy hao Alpha (Drift Guardian).',
        mechanism: [
          'Thống Kê Niêm Yết Binance: Quét phân loại 810 coin (Spot vs Futures, Chỉ có Spot, Chỉ có Futures).',
          'Bộ Phân Loại Trạng Thái Thị Trường (Market Regime): Dùng ADX và Bollinger Width để xác định thị trường Xu hướng Giảm (Trending Bear) hay Đi ngang (Choppy).',
          'Mô Hình Meta-Labeling (Lớp 2): Dùng thuật toán HistGradientBoosting để loại bỏ 55-60% tín hiệu giả trước khi bắn cảnh báo.',
          'Drift Guardian: Giám sát chỉ số ổn định dữ liệu (PSI) để phát hiện sớm hiện tượng suy giảm hiệu quả mô hình.'
        ],
        metrics: [
          { label: 'Market Regime', desc: 'Trạng thái vĩ mô hiện tại (ví dụ: TRENDING_BEAR, CHOPPY, RANGE).' },
          { label: 'Độ Mạnh Xu Hướng (ADX)', desc: 'Chỉ số ADX (> 25 biểu thị xu hướng mạnh, thuận lợi cho giao dịch).' },
          { label: 'Trạng Thái Drift Guardian', desc: 'HEALTHY / WARNING / CRITICAL thể hiện mức độ ổn định của các đặc trưng dữ liệu.' }
        ],
        playbook: [
          'Luôn xem trạng thái Market Regime: Khi thị trường là TRENDING_BEAR, các lệnh Short có tỷ lệ thắng và biên độ lợi nhuận cao nhất.'
        ]
      },
      TELEMETRY: {
        id: 'TELEMETRY',
        name: 'Hạ Tầng & Giám Sát Scanner',
        nameEn: 'Scanner Telemetry',
        icon: Cpu,
        category: 'SYSTEM',
        badge: 'Giám Sát 24/7',
        purpose: 'Bảng giám sát sức khỏe của Daemon quét thị trường 24/7, mức tiêu hao RAM/CPU, thời lượng chu kỳ quét và trạng thái bot Telegram.',
        mechanism: [
          'Nhịp Tim Scanner (Heartbeat): Giám sát chu kỳ quét 5 phút/lần của tiến trình ngầm.',
          'Đo Lường Tài Nguyên: Theo dõi CPU %, Memory RSS (MB), khóa cơ sở dữ liệu DuckDB và độ dài hàng đợi.'
        ],
        metrics: [
          { label: 'Trạng Thái Daemon', desc: 'RUNNING / IDLE / OFFLINE thể hiện bộ quét có đang chạy hay không.' },
          { label: 'Thời Lượng Chu Kỳ (Cycle Duration)', desc: 'Số giây cần thiết để quét và chấm điểm toàn bộ coin trong danh sách.' },
          { label: 'Số Coin Quét Trong Chu Kỳ', desc: 'Số lượng coin thực tế được xử lý trong đợt quét gần nhất.' }
        ],
        playbook: [
          'Kiểm tra định kỳ để đảm bảo Daemon luôn ở trạng thái RUNNING với nhịp tim cập nhật liên tục.'
        ]
      },
      HISTORY: {
        id: 'HISTORY',
        name: 'Lịch Sử Hệ Thống & Dữ Liệu',
        nameEn: 'System History',
        icon: Clock,
        category: 'SYSTEM',
        badge: 'Lưu Trữ DuckDB',
        purpose: 'Lưu trữ toàn bộ nhật ký tín hiệu cảnh báo lịch sử, thống kê tần suất phát tín hiệu theo ngày và cấu trúc cơ sở dữ liệu DuckDB.',
        mechanism: [
          'Tổng Hợp Dữ Liệu DuckDB: Lưu trữ chuỗi thời gian của các tín hiệu phát ra, số ca thành công và số chu kỳ quét mỗi ngày.',
          'Thống Kê Kho Dữ Liệu: Đo lường mốc thời gian Min/Max của các bảng phái sinh thu thập.'
        ],
        metrics: [
          { label: 'Tín Hiệu Theo Ngày', desc: 'Biểu đồ số lượng tín hiệu cảnh báo phát ra và số lần giá sụt giảm thành công.' },
          { label: 'Chu Kỳ Quét Mỗi Ngày', desc: 'Tổng số lượt quét thị trường mà Daemon đã hoàn tất trong ngày.' }
        ],
        playbook: [
          'Xem lại lịch sử nhiều ngày để đánh giá tần suất cơ hội của thị trường trong các giai đoạn biến động khác nhau.'
        ]
      },
      UPDATES: {
        id: 'UPDATES',
        name: 'Lịch Sử Phiên Bản & Cập Nhật',
        nameEn: 'Version & Auto-updater',
        icon: GitPullRequest,
        category: 'SYSTEM',
        badge: 'v2.0 Pro',
        purpose: 'Theo dõi 185 commit Git, 8 cột mốc kiến trúc, phân loại thay đổi mã nguồn và kích hoạt cơ chế Auto-Update 1 chạm.',
        mechanism: [
          'Quy Trình Auto-Update 3 Tầng: Cron tự đồng bộ 5 phút trên máy chủ Google, Nút cập nhật 1 chạm trên Web, và PWA v3.1 dọn sạch cache trình duyệt.',
          'Phân Tích Git: Thống kê số lượng tính năng mới (feat), sửa lỗi (fix), tối ưu hiệu năng (perf) và ngày phát triển.'
        ],
        metrics: [
          { label: 'Commit Hiện Tại', desc: 'Mã băm Git commit đang chạy thực tế trên máy chủ.' },
          { label: 'Trạng Thái Cập Nhật', desc: 'Báo hiệu khi có bản cập nhật mới hơn trên nhánh main của GitHub.' }
        ],
        playbook: [
          'Bấm "Kiểm tra & Cập nhật ngay" bất cứ lúc nào bạn muốn đồng bộ mã nguồn mới nhất từ GitHub.'
        ]
      },
      SETTINGS: {
        id: 'SETTINGS',
        name: 'Cài Đặt Hệ Thống & AI Config',
        nameEn: 'Settings & AI',
        icon: Settings,
        category: 'SYSTEM',
        badge: 'Cấu Hình',
        purpose: 'Quản lý API Key nhà cung cấp AI (OpenAI/DeepSeek/Gemini), tinh chỉnh tham số quét, ngưỡng điểm cảnh báo và tùy chọn giao diện/ngôn ngữ.',
        mechanism: [
          'Quản Lý Khóa API AI: Lưu trữ an toàn API Key để kích hoạt Trợ lý AI phân tích thị trường.',
          'Tùy Biến Giao Diện: Chuyển đổi giao diện V1/V2, bật/tắt âm thanh cảnh báo và chuyển đổi 4 ngôn ngữ (VI/EN/ZH/KO).'
        ],
        metrics: [
          { label: 'Nhà Cung Cấp AI', desc: 'Mô hình ngôn ngữ lớn (LLM) được chọn để phân tích thị trường.' },
          { label: 'Ngưỡng Điểm Cảnh Báo', desc: 'Mức điểm phân phối tối thiểu để hệ thống bắt đầu bắn tín hiệu.' }
        ],
        playbook: [
          'Điền API Key Gemini hoặc DeepSeek của bạn để mở khóa toàn bộ tính năng Trợ lý AI thông minh trong Trung tâm Ra quyết định.'
        ]
      }
    };
  }, [language]);

  if (!isOpen) return null;

  const currentGuide = guides[selectedTab] || guides.DECISION;

  const filteredGuides = Object.values(guides).filter(guide =>
    guide.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    guide.nameEn.toLowerCase().includes(searchTerm.toLowerCase()) ||
    guide.purpose.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getCategoryLabel = (cat: 'TRADING' | 'LAB' | 'SYSTEM') => {
    if (cat === 'TRADING') return language === 'en' ? 'Trading Core' : language === 'zh' ? '实盘核心' : language === 'ko' ? '실전 트레이딩' : 'Giao dịch Thực chiến';
    if (cat === 'LAB') return language === 'en' ? 'Quant Lab' : language === 'zh' ? '量化实验室' : language === 'ko' ? '정량 랩' : 'Phòng Thí nghiệm Quant';
    return language === 'en' ? 'System & Data' : language === 'zh' ? '系统与数据' : language === 'ko' ? '시스템 & 데이터' : 'Hệ thống & Dữ liệu';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/85 backdrop-blur-md animate-fade-in">
      <div className="flex flex-col w-full max-w-5xl h-[92vh] max-h-[850px] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-950/80 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg bg-violet-600/20 p-2 text-violet-400 border border-violet-500/30">
              <BookOpen className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                <span>{language === 'en' ? 'Tab Mechanism & Operation Guide' : language === 'zh' ? '各 Tab 功能机制与操作指南' : language === 'ko' ? '탭별 작동 메커니즘 및 가이드' : 'Hướng Dẫn Cơ Chế Hoạt Động Từng Tab'}</span>
                <span className="rounded bg-violet-950 border border-violet-700/80 px-2 py-0.5 text-[10px] font-mono text-violet-300">
                  13 Tabs
                </span>
              </h2>
              <p className="text-[11px] text-slate-400">
                {language === 'en'
                  ? 'Detailed architectural mechanisms, quantitative models, and actionable playbooks for every tab'
                  : language === 'zh'
                  ? '深入解析每个 Tab 的量化模型、底层机制、指标释义与实盘操作策略'
                  : language === 'ko'
                  ? '모든 탭의 정량 모델, 작동 메커니즘, 지표 해석 및 실전 가이드 상세 안내'
                  : 'Mô tả chi tiết nguyên lý định lượng, cơ chế vận hành, giải thích thông số và chiến lược sử dụng của từng tab'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Search & Main Layout Grid */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left Sidebar: Tab List Selector */}
          <div className="w-full md:w-72 bg-slate-950/60 border-b md:border-b-0 md:border-r border-slate-800 flex flex-col shrink-0">
            {/* Search Input */}
            <div className="p-2.5 border-b border-slate-800/80">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder={language === 'en' ? 'Search tab or concept...' : language === 'zh' ? '搜索 Tab 或概念...' : language === 'ko' ? '탭 또는 개념 검색...' : 'Tìm kiếm tab hoặc khái niệm...'}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-violet-500"
                />
                {searchTerm && (
                  <button
                    onClick={() => setSearchTerm('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-xs"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Tab Selector List */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {filteredGuides.map((guide) => {
                const isSelected = selectedTab === guide.id;
                const IconComponent = guide.icon;
                return (
                  <button
                    key={guide.id}
                    onClick={() => setSelectedTab(guide.id)}
                    className={`w-full flex items-center justify-between p-2 rounded-lg text-left transition ${
                      isSelected
                        ? 'bg-violet-950/80 border border-violet-600/80 text-white shadow-sm'
                        : 'text-slate-300 hover:bg-slate-800/60 hover:text-white border border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <div className={`p-1.5 rounded-md ${isSelected ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400'}`}>
                        <IconComponent className="h-3.5 w-3.5" />
                      </div>
                      <div className="truncate">
                        <div className="text-xs font-bold truncate flex items-center gap-1.5">
                          <span>{guide.name}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 font-mono">
                          {guide.id}
                        </div>
                      </div>
                    </div>
                    {isSelected && <ChevronRight className="h-3.5 w-3.5 text-violet-400 shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Content Area: Detailed Guide for Selected Tab */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-5 space-y-4 bg-slate-900/40">
            {/* Header of Selected Tab */}
            <div className="flex flex-wrap items-center justify-between gap-2 p-3.5 rounded-xl border border-violet-900/60 bg-gradient-to-r from-violet-950/40 via-slate-900 to-slate-950">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-violet-600/20 border border-violet-500/40 text-violet-300">
                  {React.createElement(currentGuide.icon, { className: 'h-6 w-6' })}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-black text-white">{currentGuide.name}</h3>
                    <span className="px-2 py-0.5 rounded bg-violet-900/80 border border-violet-700 text-[10px] font-mono text-violet-200 font-bold">
                      {currentGuide.id}
                    </span>
                    {currentGuide.badge && (
                      <span className="px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-700 text-[9px] text-emerald-300 font-semibold">
                        {currentGuide.badge}
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5 font-mono">
                    {getCategoryLabel(currentGuide.category)}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 1: Purpose & Value */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                <Target className="h-4 w-4 text-violet-400" />
                <span>{language === 'en' ? '1. Purpose & Core Value' : language === 'zh' ? '1. 核心定位与业务价值' : language === 'ko' ? '1. 핵심 목적 및 역할' : '1. Mục đích & Giá trị Cốt lõi'}</span>
              </h4>
              <p className="text-xs text-slate-300 leading-relaxed pl-5">
                {currentGuide.purpose}
              </p>
            </div>

            {/* Section 2: Mechanism & Quant Engine */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 space-y-2.5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                <Cpu className="h-4 w-4 text-amber-400" />
                <span>{language === 'en' ? '2. Operating Mechanism & Quant Logic' : language === 'zh' ? '2. 底层机制与量化逻辑' : language === 'ko' ? '2. 작동 메커니즘 및 정량 로직' : '2. Cơ chế Vận hành & Thuật toán Định lượng'}</span>
              </h4>
              <div className="space-y-2 pl-5">
                {currentGuide.mechanism.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-2 text-xs text-slate-300 leading-relaxed">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Section 3: Metrics Glossary */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4 space-y-2.5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                <BarChart3 className="h-4 w-4 text-cyan-400" />
                <span>{language === 'en' ? '3. Key Indicators & Metrics Glossary' : language === 'zh' ? '3. 关键指标与参数释义' : language === 'ko' ? '3. 주요 지표 및 매개변수 해설' : '3. Giải thích Thông số & Chỉ số Định lượng'}</span>
              </h4>
              <div className="grid gap-2 sm:grid-cols-2 pl-5">
                {currentGuide.metrics.map((m, idx) => (
                  <div key={idx} className="rounded-lg border border-slate-800/80 bg-slate-900/60 p-2.5 space-y-1">
                    <div className="text-xs font-bold text-cyan-300 font-mono">{m.label}</div>
                    <div className="text-[11px] text-slate-300 leading-normal">{m.desc}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Section 4: Actionable Playbook */}
            <div className="rounded-xl border border-emerald-900/50 bg-gradient-to-br from-emerald-950/20 via-slate-950 to-slate-950 p-4 space-y-2.5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-300 flex items-center gap-1.5">
                <Lightbulb className="h-4 w-4 text-yellow-400" />
                <span>{language === 'en' ? '4. Actionable Playbook & Best Practices' : language === 'zh' ? '4. 实盘操作指南与最佳实践' : language === 'ko' ? '4. 실전 트레이딩 플레이북' : '4. Chiến lược Sử dụng Thực chiến Hiệu quả'}</span>
              </h4>
              <div className="space-y-2 pl-5">
                {currentGuide.playbook.map((step, idx) => (
                  <div key={idx} className="flex items-start gap-2 text-xs text-slate-200 leading-relaxed">
                    <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-600/30 text-[10px] font-bold text-emerald-400 border border-emerald-500/40 mt-0.5">
                      {idx + 1}
                    </div>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-slate-800 bg-slate-950/80 text-[11px] text-slate-400 shrink-0">
          <div className="flex items-center gap-1.5">
            <Lightbulb className="h-3.5 w-3.5 text-yellow-400" />
            <span>{language === 'en' ? 'Tip: You can switch tabs on the left to read guides for any other tab anytime.' : language === 'zh' ? '提示：在左侧列表中可随意切换查阅任意 Tab 的功能说明。' : language === 'ko' ? '팁: 왼쪽 목록에서 언제든 다른 탭의 가이드를 선택하여 열람할 수 있습니다.' : 'Mẹo: Bạn có thể chọn bất kỳ tab nào ở cột bên trái để xem cơ chế của tab đó.'}</span>
          </div>
          <button
            onClick={onClose}
            className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded-md text-xs font-medium transition"
          >
            {language === 'en' ? 'Close' : language === 'zh' ? '关闭' : language === 'ko' ? '닫기' : 'Đóng'}
          </button>
        </div>
      </div>
    </div>
  );
};
