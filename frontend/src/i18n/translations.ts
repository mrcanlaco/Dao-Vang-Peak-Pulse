export type Language = 'vi' | 'en';

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
    tracking: 'Tracking',
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

    // Recommendations
    rec_short_candidate: 'Ứng viên SHORT',
    rec_high_confidence: 'Tín hiệu mạnh',
    rec_watch: 'Theo dõi thêm',
    rec_wait: 'Chờ thêm',

    // Main Tabs
    tab_radar: 'Radar Tín hiệu',
    tab_candidates: 'Ứng viên Tiềm năng',
    tab_system_history: 'Lịch sử & Báo cáo',
    tab_experiments: 'Thực nghiệm Backtest',
    tab_forward_test: 'Forward Test Live',
    tab_multi_scan: 'Quét Đa Khung Giờ',

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

    // Action Drawer & Modals
    drawer_title: 'Trung Tâm Điều Khiển & Cài Đặt',
    drawer_quick_actions: 'Thao tác nhanh',
    drawer_auto_telegram: 'Tự động gửi Telegram khi đạt ngưỡng',
    drawer_audio_alert: 'Âm thanh cảnh báo khi có tín hiệu mới',
    modal_glossary_title: 'Từ Điển Thuật Ngữ & Chỉ Số',
    modal_watchlist_title: 'Quản Lý Danh Sách Theo Dõi (Watchlist)',
    modal_tracking_title: 'Theo Dõi Diễn Biến & Hiệu Quả Tín Hiệu (Tracking PnL)',
    
    // Status & System health
    sys_healthy: 'Bình thường',
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
    tracking: 'Tracking',
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

    // Recommendations
    rec_short_candidate: 'SHORT Candidate',
    rec_high_confidence: 'High Confidence',
    rec_watch: 'Watchlist',
    rec_wait: 'Standby / Wait',

    // Main Tabs
    tab_radar: 'Live Radar Feed',
    tab_candidates: 'Candidate Filter',
    tab_system_history: 'History & Audits',
    tab_experiments: 'Backtest Experiments',
    tab_forward_test: 'Forward Testing Live',
    tab_multi_scan: 'Multi-Timeframe Scan',

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

    // Action Drawer & Modals
    drawer_title: 'Control Center & Settings',
    drawer_quick_actions: 'Quick Actions',
    drawer_auto_telegram: 'Auto-push alerts to Telegram on threshold match',
    drawer_audio_alert: 'Play audio notification on new signals',
    modal_glossary_title: 'Terminology & Indicator Glossary',
    modal_watchlist_title: 'Watchlist Management',
    modal_tracking_title: 'Signal Outcome & PnL Performance Tracking',
    
    // Status & System health
    sys_healthy: 'Healthy',
    sys_degraded: 'Degraded',
    sys_down: 'Disconnected',
    sys_last_scan: 'Last Scan Cycle',
    sys_heartbeat: 'Scanner Heartbeat',

    // Disclaimer
    disclaimer: 'The system operates as a passive decision-support radar (Human-in-the-loop). It does NOT execute automated orders and is not financial advice.',
  },
};

export type TranslationKey = keyof typeof translations.vi;
