import type { ModelAudit } from '../types';
import { useTranslation } from '../i18n/LanguageContext';
import { formatSystemDateTime } from '../utils/time';

const percent = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value) ? '—' : `${(value * 100).toFixed(1)}%`;

export function ModelAuditPanel({ audit }: { audit: ModelAudit }) {
  const { t, language } = useTranslation();
  const vi = language === 'vi';
  const missing = vi ? 'Chưa có dữ liệu' : 'No data available';
  const card = 'rounded-xl border border-slate-800 bg-slate-950 p-4';
  return (
    <div data-testid="model-audit-report" className="flex-1 overflow-y-auto space-y-4 pr-1">
      <section className={card}>
        <h3 className="text-sm font-bold text-slate-100">{t('audit_matrix_title')}</h3>
        <p className="mt-2 text-xs text-slate-400">{vi ? 'Mô hình đang cấu hình' : 'Configured model'}: {audit.model_name}</p>
        <p className="mt-2 text-xs text-slate-400">
          {vi ? 'Kết quả thực tế tổng hợp tất cả mô hình trong 30 ngày; chỉ tính tín hiệu đã có kết quả.'
            : 'Live outcomes across all models over 30 days; only resolved signals are counted.'}
        </p>
        <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            [t('audit_empirical_precision'), percent(audit.metrics.precision)],
            [vi ? 'Tín hiệu đã đánh giá' : 'Resolved signals', String(audit.sample_size)],
            [vi ? 'Tổng tín hiệu' : 'Total signals', String(audit.total_alerts ?? 0)],
            [t('audit_mean_lead_time'), audit.lead_time.mean_hours == null ? '—' : `${audit.lead_time.mean_hours.toFixed(2)} h`],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-900 p-3">
              <p className="text-xs text-slate-400">{label}</p>
              <p className="mt-2 text-xl font-bold font-mono text-amber-300">{value}</p>
            </div>
          ))}
        </div>
        {!audit.has_enough_data && <p className="mt-3 text-xs text-amber-300">{missing}</p>}
        <h4 className="mt-4 text-xs font-semibold text-slate-200">{t('audit_precision_by_tier')}</h4>
        <div className="mt-2 space-y-2">
          {Object.entries(audit.precision_by_risk_level).map(([level, result]) => (
            <div key={level} className="flex justify-between gap-3 text-xs text-slate-300">
              <span>{level}</span><span>{percent(result.precision)} · {result.n_hit}/{result.n_judged}</span>
            </div>
          ))}
          {Object.keys(audit.precision_by_risk_level).length === 0 && <p className="text-xs text-slate-500">{missing}</p>}
        </div>
      </section>
      <section className={card}>
        <h3 className="text-sm font-bold text-slate-100">{vi ? 'Báo cáo kiểm định lịch sử' : 'Saved historical validation report'}</h3>
        <p className="mt-2 text-xs text-slate-400">{audit.report_generated_at ? formatSystemDateTime(audit.report_generated_at) : missing}</p>
        {!audit.report_matches_current_model && (
          <p className="mt-2 text-xs text-amber-300">{vi
            ? 'Báo cáo này chưa được xác nhận thuộc mô hình đang chạy. Các chỉ số dưới đây chỉ mô tả báo cáo đã lưu.'
            : 'This report is not verified against the running model. The values below describe the saved report only.'}</p>
        )}
        <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            ['OOS precision', percent(audit.metrics.walk_forward_precision)],
            ['ECE', audit.metrics.ece?.toFixed(4) ?? '—'],
            ['Brier', audit.metrics.brier_score?.toFixed(4) ?? '—'],
            [vi ? 'Số lượt kiểm định' : 'Validation folds', String(audit.walk_forward_folds?.length ?? 0)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-900 p-3">
              <p className="text-xs text-slate-400">{label}</p>
              <p className="mt-2 text-xl font-bold font-mono text-sky-300">{value}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-400">95% CI: {percent(audit.metrics.ci_95_lower)} – {percent(audit.metrics.ci_95_upper)}</p>
        <div className="mt-4 space-y-2">
          {Object.entries(audit.quality_gates ?? {}).map(([name, passed]) => (
            <div key={name} className="flex justify-between gap-3 text-xs">
              <span className="text-slate-400">{name.replaceAll('_', ' ')}</span>
              <span className={passed ? 'text-emerald-300' : 'text-rose-300'}>{passed ? (vi ? 'Đạt theo báo cáo' : 'Passed in report') : (vi ? 'Không đạt' : 'Failed')}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="text-xs font-semibold text-slate-200">{vi ? 'Hiệu quả theo trạng thái thị trường' : 'Performance by market regime'}</h4>
            {Object.entries(audit.regime_performance ?? {}).map(([name, result]) => (
              <p key={name} className="mt-2 flex justify-between gap-2 text-xs text-slate-400"><span>{name}</span><span>{percent(result.precision)}</span></p>
            ))}
          </div>
          <div>
            <h4 className="text-xs font-semibold text-slate-200">{vi ? 'Độ quan trọng đặc trưng trong báo cáo' : 'Reported feature importance'}</h4>
            {(audit.feature_importance_ranking ?? []).slice(0, 8).map(item => (
              <p key={item.feature} className="mt-2 flex justify-between gap-2 text-xs text-slate-400"><span>{item.feature}</span><span>{item.importance_gain?.toFixed(1) ?? '—'}</span></p>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
