import React from 'react';
import { BookOpen, Terminal, AlertTriangle, Workflow, Bug } from 'lucide-react';
import { useTranslation } from '../i18n/LanguageContext';

export const GuideTab: React.FC = () => {
  const { language } = useTranslation();

  const getGuideTitle = () => {
    if (language === 'zh') return '用户操作指南与系统文档';
    if (language === 'ko') return '사용자 가이드 및 시스템 문서';
    if (language === 'en') return 'USER GUIDE & DOCUMENTATION';
    return 'HƯỚNG DẪN SỬ DỤNG';
  };

  const getDashboardOverviewTitle = () => {
    if (language === 'zh') return '🌐 控制面板全局概览';
    if (language === 'ko') return '🌐 웹 대시보드 개요';
    if (language === 'en') return '🌐 Web Dashboard Overview';
    return '🌐 Giao diện web';
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-1">
      <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase">
        <BookOpen className="w-3.5 h-3.5 text-amber-400" />
        {getGuideTitle()}
      </h3>

      {/* Quick Start */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2">
          {getDashboardOverviewTitle()}
        </h4>
        <ol className="text-[11px] text-slate-300 space-y-1.5 list-decimal list-inside">
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'RADAR FEED' : language === 'zh' ? '预警雷达 (左栏)' : language === 'ko' ? '레이더 피드 (좌측)' : 'RADAR CẢNH BÁO'}
            </strong>: {language === 'en' 
              ? 'Real-time alert list from 24/7 scanner. Click any signal card to open detailed charts.' 
              : language === 'zh'
              ? '来自 24/7 扫描器的实时信号列表。点击任意卡片查看详细图表与量化因子。'
              : language === 'ko'
              ? '24/7 스캐너의 실시간 경보 목록. 카드를 클릭하여 상세 차트와 지표를 확인하세요.'
              : 'danh sách tín hiệu xả từ bộ quét 24/7. Bấm vào 1 tín hiệu để xem chi tiết.'}
          </li>
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'MAIN WORKSPACE' : language === 'zh' ? '研判工作区 (中央)' : language === 'ko' ? '작업 공간 (중앙)' : 'PHÂN TÍCH'}
            </strong>: {language === 'en' 
              ? 'Deep dive analysis into key metrics (OI 24h, Funding, Taker Sell, RSI 15m, Target -8%) and Candlestick chart.' 
              : language === 'zh'
              ? '深入分析选中币种的 5 大关键衍生品指标、8 因子归因及 K 线图表。'
              : language === 'ko'
              ? '선택한 코인의 핵심 파생상품 지표(OI, 펀딩비, 테이커 매도, RSI, -8% 목표) 및 캔들 차트 정밀 분석.'
              : 'phân tích chuyên sâu coin đã chọn — 8 tín hiệu + mô hình tăng nóng + biểu đồ. Bấm "Chạy lại chấm điểm" để chạy toàn bộ AI.'}
          </li>
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'CANDIDATES' : language === 'zh' ? '做空候选榜' : language === 'ko' ? '덤프 후보 순위' : 'Bảng Ứng Viên'}
            </strong>: {language === 'en' 
              ? 'Ranking of all coins filtered by distribution risk.' 
              : language === 'zh'
              ? '按派发见顶风险得分对全市场币种进行降序排名。'
              : language === 'ko'
              ? '세력 분산 위험도에 따라 내림차순 정렬된 후보군 순위.'
              : 'xếp hạng tất cả coin theo điểm rủi ro.'}
          </li>
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'MULTI-COIN SCAN' : language === 'zh' ? '多币种扫描' : language === 'ko' ? '다중 코인 스캔' : 'Quét nhiều coin'}
            </strong>: {language === 'en' 
              ? 'Multi-timeframe scanner results — AI model vs heuristic baselines.' 
              : language === 'zh'
              ? '多周期批量扫描结果——AI 机器学习模型与规则基准对比。'
              : language === 'ko'
              ? '다중 주기 스캐너 결과 — AI 모델 대 휴리스틱 기준선 비교.'
              : 'kết quả quét các coin biến động mạnh — AI so với mốc cơ sở.'}
          </li>
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'BACKTEST EXPERIMENTS' : language === 'zh' ? '历史回测验证' : language === 'ko' ? '백테스트 검증' : 'Kiểm thử lịch sử'}
            </strong>: {language === 'en' 
              ? 'Out-of-sample walk-forward validation — precision, recall, leakage audit.' 
              : language === 'zh'
              ? '样本外滚动时序验证——精准率、召回率、数据泄漏审计。'
              : language === 'ko'
              ? '시계열 전진 검증 — 정밀도, 재현율, 데이터 누수 검증.'
              : 'thử nghiệm AI trên dữ liệu cũ — độ chính xác, tỷ lệ bắt được, kiểm tra rò rỉ dữ liệu.'}
          </li>
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'FORWARD TESTING' : language === 'zh' ? '实盘前向测试' : language === 'ko' ? '실전 전진 테스트' : 'Kiểm thử dữ liệu mới'}
            </strong>: {language === 'en' 
              ? 'Frozen models evaluated on live out-of-sample data.' 
              : language === 'zh'
              ? '使用已冻结的模型对实盘最新样本外数据进行打分与稳定性检验。'
              : language === 'ko'
              ? '동결된 모델로 최신 실전 데이터를 평가하여 모델 안정성 검증.'
              : 'đóng băng mô hình → chấm điểm trên dữ liệu mới.'}
          </li>
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'MARKET CONTEXT' : language === 'zh' ? '市场宏观环境' : language === 'ko' ? '시장 환경' : 'THỊ TRƯỜNG'}
            </strong>: {language === 'en' 
              ? 'Binance derivatives market overview + top gainers/losers.' 
              : language === 'zh'
              ? 'Binance 合约市场全局概览 + 涨跌幅榜异动监控。'
              : language === 'ko'
              ? '바이낸스 선물 시장 전반 개요 + 급등/급락 코인 모니터링.'
              : 'tổng quan Binance + các mã tăng/giảm mạnh.'}
          </li>
          <li>
            <strong className="text-slate-100">
              {language === 'en' ? 'SYSTEM AUDITS' : language === 'zh' ? '系统遥测与审计' : language === 'ko' ? '시스템 텔레메트리' : 'GIÁM SÁT'}
            </strong>: {language === 'en' 
              ? '24/7 background scanner logs + Telegram delivery audits.' 
              : language === 'zh'
              ? '后台 24/7 扫描器运行日志 + Telegram 警报分发审计记录。'
              : language === 'ko'
              ? '24/7 백그라운드 스캐너 로그 + 텔레그램 발송 감사 기록.'
              : 'nhật ký bộ quét 24/7 + các lượt gửi Telegram.'}
          </li>
        </ol>
      </div>

      {/* Tabs explanation */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Workflow className="w-3.5 h-3.5" /> {language === 'en' ? 'MAIN MODULES' : language === 'zh' ? '核心模块说明' : language === 'ko' ? '주요 모듈' : 'CÁC TAB CHÍNH'}
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-emerald-400">{language === 'en' ? 'Decision Center' : language === 'zh' ? '决策中心 (交易研判)' : language === 'ko' ? '의사결정 센터 (트레이딩)' : 'PHÂN TÍCH (Giao dịch)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {language === 'en' 
                ? 'Deep analytics on selected symbol: 5 key derivatives indicators (OI Delta, Funding Rate, Taker Sell Ratio, RSI, Target Drawdown) and interactive Candlestick chart.' 
                : language === 'zh'
                ? '单个币种深度剖析：5 大衍生品核心指标（OI 变化、资金费率、主动卖出比、RSI、目标回撤）、BTC 宏观背景及 8 因子 SHAP 归因。'
                : language === 'ko'
                ? '선택된 심볼 정밀 분석: 5대 파생상품 지표(OI 변화, 펀딩비, 테이커 매도 비율, RSI, 목표 하락폭) 및 캔들 차트 제공.'
                : 'Phân tích chuyên sâu 1 coin: 8 tín hiệu (phân kỳ giá-khối lượng, funding, OI, động lượng, mô hình tăng nóng...), bối cảnh BTC, RSI, mẫu hình tăng nóng.'}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-amber-400">{language === 'en' ? 'Candidate Ranking' : language === 'zh' ? '做空候选榜' : language === 'ko' ? '덤프 후보 순위' : 'Bảng Ứng Viên (Giao dịch)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {language === 'en' ? 'Ranking of coins filtered by distribution risk score.' : language === 'zh' ? '全市场币种按综合派发风险分值排序。点击即可查看深度图表。' : language === 'ko' ? '위험 점수에 따른 전체 코인 랭킹. 클릭하여 상세 분석을 확인하세요.' : 'Bảng xếp hạng tất cả coin theo điểm phân phối tổng hợp. Bấm vào coin để xem phân tích chi tiết.'}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-purple-400">{language === 'en' ? 'Backtest Experiments' : language === 'zh' ? '历史回测实验' : language === 'ko' ? '백테스트 검증' : 'Kiểm thử lịch sử (Nghiên cứu)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {language === 'en' ? 'Walk-forward cross validation across 600k+ candles with strict zero lookahead bias.' : language === 'zh' ? '在 60 万+ K 线跨度上进行无未来函数的滚动时序交叉验证。' : language === 'ko' ? '60만 개 이상의 캔들을 활용한 미래 참조 없는 엄격한 전진 검증.' : 'Đánh giá AI trên dữ liệu cũ: chia dữ liệu cuốn chiếu theo thời gian, kiểm tra rò rỉ dữ liệu, khoảng tin cậy.'}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-sky-400">{language === 'en' ? 'Forward Testing' : language === 'zh' ? '实盘前向测试' : language === 'ko' ? '실전 전진 테스트' : 'Kiểm thử dữ liệu mới (Nghiên cứu)'}</strong>
            <p className="text-slate-400 mt-0.5">
              {language === 'en' ? 'Frozen models scoring live out-of-sample data with calibration curve evaluation.' : language === 'zh' ? '冻结模型在新数据上的表现追踪及概率校准曲线评估。' : language === 'ko' ? '동결된 모델로 새로운 실전 데이터를 평가하고 보정 곡선을 분석.' : 'Đóng băng mô hình → chấm điểm trên dữ liệu MỚI. Kiểm tra độ lệch — mô hình có ổn định không sau khi triển khai.'}
            </p>
          </div>
        </div>
      </div>

      {/* CLI */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5" /> {language === 'en' ? 'CLI Commands' : language === 'zh' ? '终端命令行工具 (CLI)' : language === 'ko' ? 'CLI 명령어' : 'CLI (dòng lệnh)'}
        </h4>
        <div className="space-y-1.5 text-[11px] font-mono">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang scanner start</span>
            <span className="text-slate-400"> — {language === 'en' ? 'Start 24/7 background scanner daemon' : language === 'zh' ? '启动 24/7 后台扫描守护进程' : language === 'ko' ? '24/7 백그라운드 스캐너 데몬 시작' : 'Bộ quét 24/7 (thu thập + chấm điểm + gửi Telegram)'}</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang scanner stop</span>
            <span className="text-slate-400"> — {language === 'en' ? 'Stop scanner daemon' : language === 'zh' ? '停止扫描守护进程' : language === 'ko' ? '스캐너 데몬 중지' : 'Dừng bộ quét'}</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang experiment run</span>
            <span className="text-slate-400"> — {language === 'en' ? 'Execute walk-forward backtest' : language === 'zh' ? '执行全流程推进式时序回测' : language === 'ko' ? '시계열 전진 백테스트 실행' : 'Chạy kiểm thử lịch sử (thu thập + gán nhãn + huấn luyện + đánh giá)'}</span>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <span className="text-emerald-400">dao-vang data collect</span>
            <span className="text-slate-400"> — {language === 'en' ? 'Manual data collection' : language === 'zh' ? '手动采集衍生品数据' : language === 'ko' ? '수동 데이터 수집 실행' : 'Thu thập dữ liệu thủ công'}</span>
          </div>
        </div>
      </div>

      {/* Troubleshooting */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5">
        <h4 className="text-xs font-bold text-amber-400 mb-2 flex items-center gap-1.5">
          <Bug className="w-3.5 h-3.5" /> {language === 'en' ? 'TROUBLESHOOTING' : language === 'zh' ? '常见问题与故障排查' : language === 'ko' ? '문제 해결 (FAQ)' : 'XỬ LÝ LỖI THƯỜNG GẶP'}
        </h4>
        <div className="space-y-2 text-[11px]">
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">{language === 'en' ? 'No signals displaying?' : language === 'zh' ? '未显示任何信号？' : language === 'ko' ? '신호가 표시되지 않나요?' : 'Không có tín hiệu?'}</strong>
            <p className="text-slate-400 mt-0.5">
              {language === 'en' 
                ? 'Check System Telemetry to verify scanner daemon is running. Lower threshold slider to 0.25.' 
                : language === 'zh'
                ? '检查遥测日志确保扫描器进程正常运行，或尝试将顶部阈值滑块调低至 0.25。'
                : language === 'ko'
                ? '시스템 텔레메트리에서 스캐너가 실행 중인지 확인하세요. 상단 임계값 슬라이더를 0.25로 낮춰보세요.'
                : 'Kiểm tra tab GIÁM SÁT — bộ quét có chạy không? Chạy dao-vang scanner start. Hạ ngưỡng xuống 0,25.'}
            </p>
          </div>
          <div className="bg-slate-900 p-2 rounded border border-slate-800">
            <strong className="text-red-400">{language === 'en' ? 'Telegram alerts not sending?' : language === 'zh' ? 'Telegram 未发送警报？' : language === 'ko' ? '텔레그램 알림이 오지 않나요?' : 'Telegram không gửi?'}</strong>
            <p className="text-slate-400 mt-0.5">
              {language === 'en' 
                ? 'Verify bot_token and chat_id in your .env configuration file.' 
                : language === 'zh'
                ? '请检查项目根目录 .env 文件中的 bot_token 与 chat_id 是否正确。'
                : language === 'ko'
                ? '.env 설정 파일에서 bot_token과 chat_id가 올바른지 확인하세요.'
                : 'Kiểm tra bot_token + chat_id trong phần cấu hình .env.'}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-amber-950/20 border border-amber-800/30 rounded-xl p-3 text-[11px] text-amber-300 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          <strong>{language === 'en' ? 'Important Notice:' : language === 'zh' ? '重要声明:' : language === 'ko' ? '중요 안내:' : 'Lưu ý quan trọng:'}</strong>{' '}
          {language === 'en' 
            ? 'This is a quantitative research and decision-support radar (Human-in-the-loop). It is not automated trading and does not constitute financial advice.'
            : language === 'zh'
            ? '本系统为量化研究与人机协同辅助研判雷达，不构成任何投资或自动交易建议。'
            : language === 'ko'
            ? '본 시스템은 정량적 연구 및 의사결정 보조용 레이더입니다. 자동 매매가 아니며 투자 권유에 해당하지 않습니다.'
            : 'Đây là công cụ nghiên cứu, không phải lời khuyên đầu tư. AI có thể sai — luôn kết hợp với đánh giá thủ công trước khi vào lệnh.'}
        </div>
      </div>
    </div>
  );
};
