export type Language = 'vi' | 'en' | 'zh' | 'ko';

export const translations = {
  vi: {
    // Header & Brand
    app_title: 'DAO VANG',
    app_subtitle: 'PeakPulse AI',
    app_tagline: 'Hệ thống Radar cảnh báo sớm phân phối & tạo đỉnh thị trường Crypto bằng Máy học',
    active_coins: 'Coins quét',
    scan_mode: 'Chế độ quét',
    model: 'Mô hình',
    threshold: 'Ngưỡng lọc',
    auto_telegram: 'Auto Telegram',
    watchlist: 'Watchlist',
    tracking: 'Tracking PnL',
    glossary: 'Thuật ngữ',
    guide: 'Hướng dẫn',
    refresh: 'Làm mới',
    refreshing: 'Đang tải...',
    search_placeholder: 'Tìm mã coin (VD: BTC, ETH, SOL)...',
    open_drawer: 'Mở bảng điều khiển',
    close_drawer: 'Đóng bảng điều khiển',
    language_toggle: 'Ngôn ngữ',

    // Scan Modes & Filter Tags
    scan_volatile: 'Biến động mạnh',
    scan_gainers: 'Tăng mạnh',
    scan_losers: 'Giảm mạnh',
    scan_volume: 'Khối lượng cao',
    scan_all: 'Tất cả',
    scan_manual: 'Watchlist cá nhân',

    // Risk Levels
    risk_all: 'Tất cả mức độ',
    risk_high: 'Rủi ro cao',
    risk_medium: 'Trung bình',
    risk_low: 'Thấp',
    risk_very_low: 'Rất thấp',

    // Recommendations & Signal Statuses
    rec_short_candidate: 'Ứng viên SHORT',
    rec_high_confidence: 'Tín hiệu mạnh',
    rec_watch: 'Theo dõi thêm',
    rec_wait: 'Chờ thêm',
    status_confirmed: 'XÁC NHẬN PHÂN PHỐI',
    status_early_watch: 'THEO DÕI SỚM',
    status_invalidated: 'ĐÃ BỊ HỦY',
    status_resolved: 'ĐÃ CHẠM TARGET',

    // Main Tabs
    tab_radar: 'Radar Tín hiệu',
    tab_candidates: 'Ứng viên Tiềm năng',
    tab_system_history: 'Lịch sử & Báo cáo',
    tab_experiments: 'Thực nghiệm Backtest',
    tab_forward_test: 'Forward Test Live',
    tab_multi_scan: 'Quét Đa Khung Giờ',
    tab_audit: 'Kiểm định Mô hình',
    tab_market: 'Bối cảnh Thị trường',
    tab_telemetry: 'Telemetry Hệ thống',

    // Signal Feed & Table Columns
    col_coin: 'Cặp Coin',
    col_price: 'Giá',
    col_score: 'Điểm tín hiệu',
    col_prob: 'Xác suất ML',
    col_pump: 'Tăng trước đó',
    col_btc: 'Bối cảnh BTC',
    col_signals: 'Tín hiệu chính',
    col_time: 'Thời gian',
    col_actions: 'Thao tác',
    no_signals_found: 'Không tìm thấy tín hiệu nào phù hợp với bộ lọc hiện tại.',
    btn_chart: 'Biểu đồ',
    btn_track: 'Theo dõi',
    btn_telegram: 'Gửi Telegram',
    btn_deep_dive: 'Phân tích sâu',
    sort_newest: 'Mới nhất',
    sort_score_desc: 'Điểm cao nhất',
    sort_prob_desc: 'Xác suất cao nhất',
    sort_price_change: 'Biến động 24h',

    // Main Workspace & Candlestick Chart
    chart_candlestick: 'BIỂU ĐỒ NẾN',
    chart_toggle_oi_funding: 'Hiện/Ẩn OI & Funding',
    chart_timeframe_5m: '5m',
    chart_timeframe_15m: '15m',
    chart_timeframe_1h: '1h',
    chart_timeframe_4h: '4h',
    metric_oi_24h: 'OI 24h',
    metric_funding: 'Funding Rate',
    metric_taker_sell: 'Taker Sell',
    metric_rsi_15m: 'RSI 15m',
    metric_target_drawdown: 'Target -8%',
    metric_distance_from_high: 'Cách đỉnh 24h',
    metric_volume_24h: 'Volume 24h',
    metric_top_ls_ratio: 'Top Long/Short',
    metric_global_ls_ratio: 'Global Long/Short',

    // Workspace Deep Dive Tabs
    ws_tab_decision: 'Nhận định & Khuyến nghị',
    ws_tab_market_context: 'Bối cảnh Thị trường',
    ws_tab_order_flow: 'Dòng tiền & Phái sinh',
    ws_tab_ml_model: 'Mô hình ML & Giải thích',
    ws_tab_indicators: 'Chỉ báo Kỹ thuật',

    // Decision Breakdown
    decision_verdict_title: 'Đánh Giá Tổng Quan Tín Hiệu',
    decision_verdict_short: 'Có dấu hiệu phân phối đỉnh rõ ràng. Ưu tiên canh nhịp hồi để mở vị thế SHORT.',
    decision_verdict_watch: 'Dấu hiệu phân phối mới bắt đầu nhen nhóm. Cần theo dõi thêm diễn biến nến tiếp theo.',
    decision_verdict_wait: 'Chưa đủ điều kiện xác nhận phân phối. Giữ trạng thái quan sát.',
    decision_invalidation_rule: 'Mức hủy tín hiệu (Stoploss tham khảo): Vượt đỉnh gần nhất +4%.',
    decision_target_rule: 'Mục tiêu sụt giảm kỳ vọng: -8% so với giá đóng nến tín hiệu.',
    decision_lead_time_est: 'Thời gian phản ứng dự kiến (Median Lead Time): ~4 - 12 giờ.',

    // Action Drawer & Settings
    drawer_title: 'Trung Tâm Điều Khiển & Cài Đặt',
    drawer_quick_actions: 'Thao tác nhanh',
    drawer_auto_telegram: 'Tự động gửi Telegram khi đạt ngưỡng',
    drawer_audio_alert: 'Âm thanh cảnh báo khi có tín hiệu mới',
    drawer_min_prob_threshold: 'Ngưỡng xác suất tối thiểu',
    drawer_scan_frequency: 'Tần suất quét tự động (5 phút/chu kỳ)',
    drawer_test_telegram: 'Gửi tin nhắn thử nghiệm Telegram',
    drawer_test_telegram_sending: 'Đang gửi...',
    drawer_test_telegram_sent: 'Đã gửi thành công!',
    drawer_reset_defaults: 'Khôi phục mặc định',

    // Modals
    modal_glossary_title: 'Từ Điển Thuật Ngữ & Chỉ Số Định Lượng',
    modal_watchlist_title: 'Quản Lý Danh Sách Theo Dõi (Watchlist)',
    modal_tracking_title: 'Theo Dõi Diễn Biến & Hiệu Quả Tín Hiệu (Tracking PnL)',
    watchlist_add_placeholder: 'Nhập mã coin để thêm (VD: SOLUSDT)...',
    watchlist_add_btn: 'Thêm vào Watchlist',
    watchlist_empty: 'Chưa có coin nào trong Watchlist cá nhân.',
    tracking_empty: 'Chưa có tín hiệu nào đang được theo dõi.',
    tracking_col_symbol: 'Cặp Coin',
    tracking_col_entry: 'Giá vào (Signal Price)',
    tracking_col_current: 'Giá hiện tại',
    tracking_col_pnl: 'Hiệu suất (PnL %)',
    tracking_col_status: 'Trạng thái',
    tracking_col_time: 'Thời gian trôi qua',

    // Status & System health
    sys_healthy: 'Hoạt động tốt',
    sys_degraded: 'Cảnh báo',
    sys_down: 'Mất kết nối',
    sys_last_scan: 'Lần quét gần nhất',
    sys_heartbeat: 'Heartbeat Scanner',

    // Disclaimer
    disclaimer: 'Hệ thống hoạt động như một Radar thụ động cung cấp thông tin tham khảo (Human-in-the-loop). Không tự động đặt lệnh và không phải lời khuyên tài chính.',
  },

  en: {
    // Header & Brand
    app_title: 'DAO VANG',
    app_subtitle: 'PeakPulse AI',
    app_tagline: 'Machine Learning Crypto Distribution & Top Formation Early Warning Radar',
    active_coins: 'Active Coins',
    scan_mode: 'Scan Mode',
    model: 'ML Model',
    threshold: 'Threshold',
    auto_telegram: 'Auto Telegram',
    watchlist: 'Watchlist',
    tracking: 'Tracking PnL',
    glossary: 'Glossary',
    guide: 'Guide',
    refresh: 'Refresh',
    refreshing: 'Loading...',
    search_placeholder: 'Search coin (e.g. BTC, ETH, SOL)...',
    open_drawer: 'Open Drawer',
    close_drawer: 'Close Drawer',
    language_toggle: 'Language',

    // Scan Modes & Filter Tags
    scan_volatile: 'High Volatility',
    scan_gainers: 'Top Gainers',
    scan_losers: 'Top Losers',
    scan_volume: 'High Volume',
    scan_all: 'All Pairs',
    scan_manual: 'Custom Watchlist',

    // Risk Levels
    risk_all: 'All Risk Levels',
    risk_high: 'High Risk',
    risk_medium: 'Medium',
    risk_low: 'Low',
    risk_very_low: 'Very Low',

    // Recommendations & Signal Statuses
    rec_short_candidate: 'SHORT Candidate',
    rec_high_confidence: 'High Confidence',
    rec_watch: 'Watchlist',
    rec_wait: 'Standby / Wait',
    status_confirmed: 'CONFIRMED DISTRIBUTION',
    status_early_watch: 'EARLY WATCH',
    status_invalidated: 'INVALIDATED',
    status_resolved: 'TARGET HIT (-8%)',

    // Main Tabs
    tab_radar: 'Live Radar Feed',
    tab_candidates: 'Candidate Filter',
    tab_system_history: 'History & Audits',
    tab_experiments: 'Backtest Experiments',
    tab_forward_test: 'Forward Testing Live',
    tab_multi_scan: 'Multi-Timeframe Scan',
    tab_audit: 'Model Audit',
    tab_market: 'Market Context',
    tab_telemetry: 'System Telemetry',

    // Signal Feed & Table Columns
    col_coin: 'Pair',
    col_price: 'Price',
    col_score: 'Composite Score',
    col_prob: 'ML Probability',
    col_pump: 'Prior Pump',
    col_btc: 'BTC Regime',
    col_signals: 'Key Signals',
    col_time: 'Timestamp',
    col_actions: 'Actions',
    no_signals_found: 'No signals match the current filter criteria.',
    btn_chart: 'Chart',
    btn_track: 'Track',
    btn_telegram: 'Send Telegram',
    btn_deep_dive: 'Deep Dive',
    sort_newest: 'Newest First',
    sort_score_desc: 'Highest Score',
    sort_prob_desc: 'Highest Probability',
    sort_price_change: '24h Price Change',

    // Main Workspace & Candlestick Chart
    chart_candlestick: 'CANDLESTICK CHART',
    chart_toggle_oi_funding: 'Toggle OI & Funding',
    chart_timeframe_5m: '5m',
    chart_timeframe_15m: '15m',
    chart_timeframe_1h: '1h',
    chart_timeframe_4h: '4h',
    metric_oi_24h: 'OI 24h',
    metric_funding: 'Funding Rate',
    metric_taker_sell: 'Taker Sell',
    metric_rsi_15m: 'RSI 15m',
    metric_target_drawdown: 'Target -8%',
    metric_distance_from_high: 'From 24h High',
    metric_volume_24h: 'Volume 24h',
    metric_top_ls_ratio: 'Top Long/Short',
    metric_global_ls_ratio: 'Global Long/Short',

    // Workspace Deep Dive Tabs
    ws_tab_decision: 'Verdict & Strategy',
    ws_tab_market_context: 'Market Context',
    ws_tab_order_flow: 'Order Flow & Derivatives',
    ws_tab_ml_model: 'ML Model & Explainability',
    ws_tab_indicators: 'Technical Indicators',

    // Decision Breakdown
    decision_verdict_title: 'Signal Synthesis & Verdict',
    decision_verdict_short: 'Distinct top distribution signals detected. Favor seeking pullback retests to initiate SHORT positions.',
    decision_verdict_watch: 'Early-stage distribution footprints emerging. Observe upcoming candle confirmations.',
    decision_verdict_wait: 'Insufficient confluence for distribution confirmation. Maintain neutral standby.',
    decision_invalidation_rule: 'Signal Invalidation Rule: Price exceeds recent peak by +4% (Stoploss anchor).',
    decision_target_rule: 'Target Drawdown: -8% from signal close price.',
    decision_lead_time_est: 'Estimated Median Lead Time: ~4 - 12 hours.',

    // Action Drawer & Settings
    drawer_title: 'Control Center & Settings',
    drawer_quick_actions: 'Quick Actions',
    drawer_auto_telegram: 'Auto-push alerts to Telegram on threshold match',
    drawer_audio_alert: 'Play audio notification on new signals',
    drawer_min_prob_threshold: 'Minimum Probability Threshold',
    drawer_scan_frequency: 'Scan Frequency (5-minute candle cycles)',
    drawer_test_telegram: 'Send Test Telegram Alert',
    drawer_test_telegram_sending: 'Sending...',
    drawer_test_telegram_sent: 'Test alert sent successfully!',
    drawer_reset_defaults: 'Reset to Defaults',

    // Modals
    modal_glossary_title: 'Quantitative Terminology & Indicator Glossary',
    modal_watchlist_title: 'Watchlist Management',
    modal_tracking_title: 'Signal Outcome & PnL Performance Tracking',
    watchlist_add_placeholder: 'Enter symbol to add (e.g. SOLUSDT)...',
    watchlist_add_btn: 'Add to Watchlist',
    watchlist_empty: 'No symbols currently in custom watchlist.',
    tracking_empty: 'No signals currently being tracked.',
    tracking_col_symbol: 'Pair',
    tracking_col_entry: 'Signal Entry Price',
    tracking_col_current: 'Current Price',
    tracking_col_pnl: 'Performance (PnL %)',
    tracking_col_status: 'Status',
    tracking_col_time: 'Elapsed Time',

    // Status & System health
    sys_healthy: 'Healthy',
    sys_degraded: 'Degraded',
    sys_down: 'Disconnected',
    sys_last_scan: 'Last Scan Cycle',
    sys_heartbeat: 'Scanner Heartbeat',

    // Disclaimer
    disclaimer: 'The system operates as a passive decision-support radar (Human-in-the-loop). It does NOT execute automated orders and is not financial advice.',
  },

  zh: {
    // Header & Brand
    app_title: 'DAO VANG (刀锋)',
    app_subtitle: 'PeakPulse AI',
    app_tagline: '基于机器学习的加密货币顶部派发与见顶预警雷达系统',
    active_coins: '扫描币种',
    scan_mode: '扫描模式',
    model: 'AI模型',
    threshold: '过滤阈值',
    auto_telegram: 'Telegram 推送',
    watchlist: '自选列表',
    tracking: '仓位跟踪',
    glossary: '术语表',
    guide: '使用指南',
    refresh: '刷新',
    refreshing: '加载中...',
    search_placeholder: '搜索币种 (如 BTC, ETH, SOL)...',
    open_drawer: '打开控制抽屉',
    close_drawer: '关闭控制抽屉',
    language_toggle: '语言切换',

    // Scan Modes & Filter Tags
    scan_volatile: '高波动币种',
    scan_gainers: '涨幅榜',
    scan_losers: '跌幅榜',
    scan_volume: '高成交量',
    scan_all: '全部交易对',
    scan_manual: '自定义自选',

    // Risk Levels
    risk_all: '全部风险级别',
    risk_high: '高风险',
    risk_medium: '中风险',
    risk_low: '低风险',
    risk_very_low: '极低风险',

    // Recommendations & Signal Statuses
    rec_short_candidate: '做空 (SHORT) 候选',
    rec_high_confidence: '高确信度信号',
    rec_watch: '重点观察',
    rec_wait: '观望等待',
    status_confirmed: '确认派发见顶',
    status_early_watch: '早期观察中',
    status_invalidated: '信号已失效',
    status_resolved: '已触及止盈 (-8%)',

    // Main Tabs
    tab_radar: '实时雷达信号',
    tab_candidates: '潜在做空候选',
    tab_system_history: '系统历史与审计',
    tab_experiments: '历史回测矩阵',
    tab_forward_test: '实盘前向测试',
    tab_multi_scan: '多周期同步扫描',
    tab_audit: '模型数学审计',
    tab_market: '全网市场概况',
    tab_telemetry: '扫描器遥测日志',

    // Signal Feed & Table Columns
    col_coin: '交易对',
    col_price: '当前价',
    col_score: '综合评分',
    col_prob: '机器学习概率',
    col_pump: '前期涨幅',
    col_btc: 'BTC 市场状态',
    col_signals: '核心预警信号',
    col_time: '触发时间',
    col_actions: '操作',
    no_signals_found: '当前过滤条件下未发现符合条件的信号。',
    btn_chart: 'K线图表',
    btn_track: '加入跟踪',
    btn_telegram: '发送TG',
    btn_deep_dive: '深度分析',
    sort_newest: '最新触发',
    sort_score_desc: '最高评分',
    sort_prob_desc: '最高概率',
    sort_price_change: '24h 涨跌幅',

    // Main Workspace & Candlestick Chart
    chart_candlestick: 'K线行情图表',
    chart_toggle_oi_funding: '显示/隐藏 持仓量(OI)与费率',
    chart_timeframe_5m: '5分钟',
    chart_timeframe_15m: '15分钟',
    chart_timeframe_1h: '1小时',
    chart_timeframe_4h: '4小时',
    metric_oi_24h: '24h 持仓量',
    metric_funding: '资金费率',
    metric_taker_sell: '主动卖出比例',
    metric_rsi_15m: '15m RSI',
    metric_target_drawdown: '预期目标 -8%',
    metric_distance_from_high: '距24h最高点',
    metric_volume_24h: '24h 成交额',
    metric_top_ls_ratio: '大户多空比',
    metric_global_ls_ratio: '全网多空比',

    // Workspace Deep Dive Tabs
    ws_tab_decision: '综合研判与策略',
    ws_tab_market_context: '市场背景环境',
    ws_tab_order_flow: '资金流与衍生品',
    ws_tab_ml_model: '机器学习归因解释',
    ws_tab_indicators: '技术量化指标',

    // Decision Breakdown
    decision_verdict_title: '信号综合研判结论',
    decision_verdict_short: '检测到显著的高位派发特征。建议等待反弹回抽关键阻力位分批建立空头 (SHORT) 仓位。',
    decision_verdict_watch: '派发迹象初现，动能尚未完全衰竭。建议观察后续K线确认形态。',
    decision_verdict_wait: '尚未达到多重共振派发标准，保持观望。',
    decision_invalidation_rule: '失效止损规则: 突破近期最高点 +4% (硬性止损防线)。',
    decision_target_rule: '预期回撤目标: 较信号收盘价下行 -8%。',
    decision_lead_time_est: '中位数预警提前量 (Median Lead Time): 约 4 - 12 小时。',

    // Action Drawer & Settings
    drawer_title: '控制中心与系统设置',
    drawer_quick_actions: '快捷操作',
    drawer_auto_telegram: '达到概率阈值自动推送 Telegram',
    drawer_audio_alert: '发现新信号时播放音频警报',
    drawer_min_prob_threshold: '最小概率触发阈值',
    drawer_scan_frequency: '自动扫描频率 (每5分钟周期)',
    drawer_test_telegram: '发送 Telegram 测试消息',
    drawer_test_telegram_sending: '正在发送...',
    drawer_test_telegram_sent: '测试消息发送成功！',
    drawer_reset_defaults: '恢复默认设置',

    // Modals
    modal_glossary_title: '量化术语与指标字典',
    modal_watchlist_title: '自选扫描监控池管理',
    modal_tracking_title: '仓位跟踪与 PnL 收益归因',
    watchlist_add_placeholder: '输入交易对以添加 (如 SOLUSDT)...',
    watchlist_add_btn: '加入自选池',
    watchlist_empty: '当前自定义自选池中暂无币种。',
    tracking_empty: '当前没有正在跟踪的信号仓位。',
    tracking_col_symbol: '交易对',
    tracking_col_entry: '入场参考价',
    tracking_col_current: '当前价格',
    tracking_col_pnl: '盈亏表现 (PnL %)',
    tracking_col_status: '状态',
    tracking_col_time: '已过去时间',

    // Status & System health
    sys_healthy: '运行正常',
    sys_degraded: '性能降级',
    sys_down: '断开连接',
    sys_last_scan: '上次扫描周期',
    sys_heartbeat: '扫描器心跳',

    // Disclaimer
    disclaimer: '本系统仅作为被动式量化决策辅助雷达（人机协同）。不执行自动交易，亦不构成任何财务投资建议。',
  },

  ko: {
    // Header & Brand
    app_title: 'DAO VANG (다오방)',
    app_subtitle: 'PeakPulse AI',
    app_tagline: '머신러닝 기반 암호화폐 고점 분산(덤프) 조기 경보 레이더 시스템',
    active_coins: '스캔 코인',
    scan_mode: '스캔 모드',
    model: 'AI 모델',
    threshold: '필터 임계값',
    auto_telegram: '텔레그램 자동전송',
    watchlist: '관심 종목',
    tracking: '포지션 추적',
    glossary: '용어 사전',
    guide: '사용 가이드',
    refresh: '새로고침',
    refreshing: '로딩 중...',
    search_placeholder: '코인 심볼 검색 (예: BTC, ETH, SOL)...',
    open_drawer: '제어 패널 열기',
    close_drawer: '제어 패널 닫기',
    language_toggle: '언어 변경',

    // Scan Modes & Filter Tags
    scan_volatile: '고변동성 코인',
    scan_gainers: '급상승 코인',
    scan_losers: '급하락 코인',
    scan_volume: '대량 거래량',
    scan_all: '전체 마켓',
    scan_manual: '사용자 지정 목록',

    // Risk Levels
    risk_all: '모든 위험 수준',
    risk_high: '고위험 (High)',
    risk_medium: '중간 위험 (Medium)',
    risk_low: '낮은 위험 (Low)',
    risk_very_low: '극히 낮음 (Safe)',

    // Recommendations & Signal Statuses
    rec_short_candidate: '숏 (SHORT) 유력 후보',
    rec_high_confidence: '강력한 신호',
    rec_watch: '관찰 필요',
    rec_wait: '대기 관망',
    status_confirmed: '고점 분산 확인',
    status_early_watch: '초기 모니터링',
    status_invalidated: '신호 무효화',
    status_resolved: '목표 도달 (-8%)',

    // Main Tabs
    tab_radar: '실시간 레이더 피드',
    tab_candidates: '덤프 유력 후보',
    tab_system_history: '시스템 이력 및 감사',
    tab_experiments: '백테스트 검증 행렬',
    tab_forward_test: '실전 전진 테스트 (Live)',
    tab_multi_scan: '다중 타임프레임 스캔',
    tab_audit: 'AI 모델 수학적 검증',
    tab_market: '시장 거시 지표',
    tab_telemetry: '스캐너 텔레메트리',

    // Signal Feed & Table Columns
    col_coin: '페어 심볼',
    col_price: '현재가',
    col_score: '종합 위험도',
    col_prob: '머신러닝 확률',
    col_pump: '직전 펌핑률',
    col_btc: 'BTC 시장 국면',
    col_signals: '핵심 경보 요인',
    col_time: '발생 시각',
    col_actions: '작업',
    no_signals_found: '현재 필터 조건에 부합하는 신호가 없습니다.',
    btn_chart: '차트 보기',
    btn_track: '추적 등록',
    btn_telegram: '텔레그램 발송',
    btn_deep_dive: '정밀 분석',
    sort_newest: '최신 발생순',
    sort_score_desc: '점수 높은순',
    sort_prob_desc: '확률 높은순',
    sort_price_change: '24시간 변동률',

    // Main Workspace & Candlestick Chart
    chart_candlestick: '캔들스틱 차트',
    chart_toggle_oi_funding: 'OI 및 펀딩비 토글',
    chart_timeframe_5m: '5분',
    chart_timeframe_15m: '15분',
    chart_timeframe_1h: '1시간',
    chart_timeframe_4h: '4시간',
    metric_oi_24h: '24h 미결제약정(OI)',
    metric_funding: '펀딩비(Funding)',
    metric_taker_sell: '테이커 매도 비율',
    metric_rsi_15m: '15m RSI',
    metric_target_drawdown: '목표 하락폭 -8%',
    metric_distance_from_high: '24h 고점 대비',
    metric_volume_24h: '24h 거래대금',
    metric_top_ls_ratio: '상위 롱/숏 비율',
    metric_global_ls_ratio: '전체 롱/숏 비율',

    // Workspace Deep Dive Tabs
    ws_tab_decision: '종합 판단 및 전략',
    ws_tab_market_context: '시장 배경 환경',
    ws_tab_order_flow: '자금 흐름 및 파생상품',
    ws_tab_ml_model: '머신러닝 SHAP 요인 분석',
    ws_tab_indicators: '기술적 퀀트 지표',

    // Decision Breakdown
    decision_verdict_title: '신호 종합 판정 결과',
    decision_verdict_short: '뚜렷한 고점 분산(매도세) 징후가 포착되었습니다. 반등 리테스트 구간에서 숏(SHORT) 진입을 권장합니다.',
    decision_verdict_watch: '초기 분산 신호가 감지되었습니다. 다음 캔들의 추세 반전 여부를 추가 확인하세요.',
    decision_verdict_wait: '다중 조건 충족이 미흡합니다. 관망세를 유지하세요.',
    decision_invalidation_rule: '신호 무효화(손절 기준): 직전 고점 대비 +4% 돌파 시.',
    decision_target_rule: '예상 하락 목표가: 신호 캔들 종가 대비 -8%.',
    decision_lead_time_est: '평균 사전 경보 여유 시간 (Median Lead Time): 약 4 - 12시간.',

    // Action Drawer & Settings
    drawer_title: '제어 센터 및 환경 설정',
    drawer_quick_actions: '빠른 실행',
    drawer_auto_telegram: '확률 임계값 도달 시 텔레그램 자동 전송',
    drawer_audio_alert: '새 신호 발생 시 오디오 알림 재생',
    drawer_min_prob_threshold: '최소 확률 트리거 임계값',
    drawer_scan_frequency: '자동 스캔 주기 (5분봉 단위)',
    drawer_test_telegram: '텔레그램 테스트 메시지 전송',
    drawer_test_telegram_sending: '전송 중...',
    drawer_test_telegram_sent: '테스트 알림이 성공적으로 전송되었습니다!',
    drawer_reset_defaults: '기본값으로 복원',

    // Modals
    modal_glossary_title: '퀀트 용어 및 정량 지표 사전',
    modal_watchlist_title: '스캔 관심 종목 풀 관리',
    modal_tracking_title: '포지션 추적 및 PnL 성과 모니터링',
    watchlist_add_placeholder: '추가할 코인 심볼 입력 (예: SOLUSDT)...',
    watchlist_add_btn: '관심 목록에 추가',
    watchlist_empty: '현재 사용자 지정 관심 목록에 코인이 없습니다.',
    tracking_empty: '현재 추적 중인 신호 포지션이 없습니다.',
    tracking_col_symbol: '페어 심볼',
    tracking_col_entry: '진입 기준가',
    tracking_col_current: '현재가',
    tracking_col_pnl: '수익률 (PnL %)',
    tracking_col_status: '상태',
    tracking_col_time: '경과 시간',

    // Status & System health
    sys_healthy: '정상 작동',
    sys_degraded: '주의 상태',
    sys_down: '연결 끊김',
    sys_last_scan: '최근 스캔 주기',
    sys_heartbeat: '스캐너 하트비트',

    // Disclaimer
    disclaimer: '본 시스템은 수동적 의사결정 보조 레이더(Human-in-the-loop)로 작동합니다. 자동 매매를 수행하지 않으며 재무적 투자 조언이 아닙니다.',
  },
};

export type TranslationKey = keyof typeof translations.vi;

// Helper lookup records for components
export function getRiskLabel(risk: string, lang: Language): string {
  const map: Record<string, Record<Language, string>> = {
    CRITICAL: { vi: 'RỦI RO CỰC CAO', en: 'CRITICAL RISK', zh: '极高风险', ko: '극도로 위험' },
    HIGH: { vi: 'RỦI RO CAO', en: 'HIGH RISK', zh: '高风险', ko: '고위험' },
    MEDIUM: { vi: 'RỦI RO TRUNG BÌNH', en: 'MEDIUM RISK', zh: '中风险', ko: '중간 위험' },
    SAFE: { vi: 'AN TOÀN', en: 'SAFE / LOW RISK', zh: '低风险安全', ko: '안전 / 저위험' },
    ALL: { vi: 'Tất cả mức độ', en: 'All Risk Levels', zh: '全部风险级别', ko: '모든 위험 수준' },
  };
  return map[risk.toUpperCase()]?.[lang] ?? risk;
}

export function getScanModeLabel(mode: string, lang: Language): string {
  const map: Record<string, Record<Language, string>> = {
    volatile: { vi: 'Biến động mạnh', en: 'High Volatility', zh: '高波动', ko: '고변동성' },
    gainers: { vi: 'Top tăng giá', en: 'Top Gainers', zh: '涨幅榜', ko: '급상승' },
    losers: { vi: 'Top giảm giá', en: 'Top Losers', zh: '跌幅榜', ko: '급하락' },
    manual: { vi: 'Danh sách cá nhân', en: 'Custom Watchlist', zh: '自定义自选', ko: '관심목록' },
    all: { vi: 'Toàn bộ thị trường', en: 'All Pairs', zh: '全网交易对', ko: '전체 마켓' },
    volume: { vi: 'Khối lượng cao', en: 'High Volume', zh: '高交易量', ko: '대량 거래량' },
  };
  return map[mode.toLowerCase()]?.[lang] ?? mode.toUpperCase();
}

export function getAuditStatusLabel(status: string, lang: Language): string {
  const map: Record<string, Record<Language, string>> = {
    PASSED: { vi: 'ĐẠT CHUẨN', en: 'PASSED', zh: '通过检验', ko: '검증 통과' },
    FAILED: { vi: 'KHÔNG ĐẠT', en: 'FAILED', zh: '未通过', ko: '검증 실패' },
    VERIFIED: { vi: 'ĐÃ XÁC MINH', en: 'VERIFIED', zh: '已验证', ko: '확인 완료' },
    PENDING: { vi: 'ĐANG XỬ LÝ', en: 'PENDING', zh: '待处理', ko: '대기 중' },
  };
  return map[status.toUpperCase()]?.[lang] ?? status;
}

export function getExecutionStatusLabel(status: string, lang: Language): string {
  const map: Record<string, Record<Language, string>> = {
    COMPLETED: { vi: 'HOÀN THÀNH', en: 'COMPLETED', zh: '执行完成', ko: '완료됨' },
    RUNNING: { vi: 'ĐANG CHẠY', en: 'RUNNING', zh: '正在运行', ko: '실행 중' },
    FAILED: { vi: 'LỖI', en: 'FAILED', zh: '失败', ko: '실패' },
    'ALERT FIRED': { vi: 'ĐÃ BẮN CẢNH BÁO', en: 'ALERT FIRED', zh: '警报触发', ko: '경보 발송됨' },
    SENT: { vi: 'ĐÃ GỬI', en: 'SENT', zh: '已发送', ko: '전송 완료' },
  };
  return map[status.toUpperCase()]?.[lang] ?? status;
}

export function getScannerStatusLabel(status: string, lang: Language): string {
  const map: Record<string, Record<Language, string>> = {
    IDLE: { vi: 'ĐANG CHỜ CHU KỲ TIẾP', en: 'IDLE (AWAITING CYCLE)', zh: '待机中 (等待下个周期)', ko: '대기 중 (다음 주기 대기)' },
    SCANNING: { vi: 'ĐANG QUÉT THỜI GIAN THỰC', en: 'SCANNING IN PROGRESS', zh: '正在实时扫描', ko: '실시간 스캔 진행 중' },
    ERROR: { vi: 'GẶP LỖI KẾT NỐI', en: 'CONNECTION ERROR', zh: '连接异常', ko: '연결 오류' },
    ACTIVE: { vi: 'ĐANG HOẠT ĐỘNG 24/7', en: 'ACTIVE 24/7', zh: '24/7 运行中', ko: '24/7 정상 가동 중' },
  };
  return map[status.toUpperCase()]?.[lang] ?? status;
}
