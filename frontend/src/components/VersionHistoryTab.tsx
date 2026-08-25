import React, { useState, useEffect, useMemo } from 'react';
import type { VersionHistoryData, GitCommitItem, SystemUpdateStatus, SystemUpdateLogs } from '../types';
import {
  GitCommit,
  GitBranch,
  GitPullRequest,
  Tag,
  Calendar,
  ExternalLink,
  Copy,
  Check,
  RefreshCw,
  Search,
  Code2,
  Sparkles,
  Zap,
  Wrench,
  BookOpen,
  Box,
  Layers,
  CheckCircle2,
  Clock,
  TrendingUp,
  FileCode,
  SlidersHorizontal,
  Flame,
  Info,
  Rocket,
  Terminal,
  AlertTriangle,
  X,
  ArrowDownCircle,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';
import { formatSystemDateTime } from '../utils/time';
import { useTranslation } from '../i18n/LanguageContext';

export const VersionHistoryTab: React.FC = () => {
  const { t } = useTranslation();

  const [data, setData] = useState<VersionHistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Filters
  const [activeSubTab, setActiveSubTab] = useState<'TIMELINE' | 'ROADMAP' | 'ANALYTICS' | 'CHANGELOG'>('TIMELINE');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('ALL');
  const [selectedScope, setSelectedScope] = useState<string>('ALL');
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // System 1-Click Update State
  const [updateStatus, setUpdateStatus] = useState<SystemUpdateStatus | null>(null);
  const [isCheckingUpdate, setIsCheckingUpdate] = useState(false);
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateLogs, setUpdateLogs] = useState<string[]>([]);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [updateSuccess, setUpdateSuccess] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);

  // Fetch Update Status
  const fetchUpdateStatus = async () => {
    setIsCheckingUpdate(true);
    try {
      const res = await fetch('/api/system/update-status');
      if (res.ok) {
        const json: SystemUpdateStatus = await res.json();
        setUpdateStatus(json);
      }
    } catch {
      // silent
    } finally {
      setIsCheckingUpdate(false);
    }
  };

  // Start 1-Click System Update
  const handleStartUpdate = async () => {
    setIsUpdating(true);
    setUpdateError(null);
    setUpdateSuccess(false);
    setUpdateLogs(['[HỆ THỐNG] Đang gửi yêu cầu cập nhật tới máy chủ...']);

    try {
      const res = await fetch('/api/system/update-apply', { method: 'POST' });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || errJson.message || `HTTP ${res.status}`);
      }

      // Start polling logs every 1 second
      const pollInterval = setInterval(async () => {
        try {
          const logRes = await fetch('/api/system/update-logs');
          if (logRes.ok) {
            const logData: SystemUpdateLogs = await logRes.json();
            if (logData.logs && logData.logs.length > 0) {
              setUpdateLogs(logData.logs);
            }

            if (!logData.is_updating) {
              clearInterval(pollInterval);
              setIsUpdating(false);
              if (logData.last_result?.success) {
                setUpdateSuccess(true);
                fetchUpdateStatus();
                // Countdown to refresh
                let c = 5;
                setCountdown(c);
                const countTimer = setInterval(() => {
                  c -= 1;
                  setCountdown(c);
                  if (c <= 0) {
                    clearInterval(countTimer);
                    window.location.reload();
                  }
                }, 1000);
              } else if (logData.last_result?.error) {
                setUpdateError(logData.last_result.error);
              }
            }
          }
        } catch {
          // If server is restarting, keep polling
        }
      }, 1000);
    } catch (err) {
      setIsUpdating(false);
      setUpdateError(err instanceof Error ? err.message : 'Lỗi khi kích hoạt cập nhật');
    }
  };

  // Fetch version history
  const fetchVersionHistory = async (force: boolean = false) => {
    if (force) {
      setIsSyncing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const url = force ? '/api/version-history/refresh' : '/api/version-history';
      const options = force ? { method: 'POST' } : { method: 'GET' };
      const res = await fetch(url, options);

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const json = await res.json();
      const payload: VersionHistoryData = json.data || json;
      setData(payload);

      if (force) {
        setFeedback({ type: 'success', message: t('updates_sync_success') });
        fetchUpdateStatus();
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : t('network_err');
      if (force) {
        setFeedback({ type: 'error', message: t('updates_sync_failed') });
      } else {
        setError(errMsg);
      }
    } finally {
      setLoading(false);
      setIsSyncing(false);
    }
  };

  useEffect(() => {
    fetchVersionHistory();
    fetchUpdateStatus();
  }, []);

  useEffect(() => {
    if (!feedback) return;
    const timer = setTimeout(() => setFeedback(null), 4000);
    return () => clearTimeout(timer);
  }, [feedback]);

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Filtered commits
  const filteredCommits = useMemo(() => {
    if (!data || !data.commits) return [];
    return data.commits.filter((c) => {
      // Type filter
      if (selectedType !== 'ALL' && c.type !== selectedType) {
        return false;
      }
      // Scope filter
      if (selectedScope !== 'ALL' && c.scope !== selectedScope) {
        return false;
      }
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchSubject = c.subject.toLowerCase().includes(q);
        const matchHash = c.hash.toLowerCase().includes(q) || c.short_hash.toLowerCase().includes(q);
        const matchAuthor = c.author.toLowerCase().includes(q);
        const matchScope = c.scope ? c.scope.toLowerCase().includes(q) : false;
        if (!matchSubject && !matchHash && !matchAuthor && !matchScope) {
          return false;
        }
      }
      return true;
    });
  }, [data, selectedType, selectedScope, searchQuery]);

  // Group commits by date
  const groupedCommits = useMemo(() => {
    const groups: Record<string, GitCommitItem[]> = {};
    for (const c of filteredCommits) {
      const day = c.date ? c.date.slice(0, 10) : 'Unknown';
      if (!groups[day]) groups[day] = [];
      groups[day].push(c);
    }
    return groups;
  }, [filteredCommits]);

  // Helper for type styling & badges
  const getTypeBadge = (type: string) => {
    switch (type) {
      case 'feat':
        return {
          label: 'FEAT',
          icon: <Sparkles className="w-3 h-3 text-emerald-400" />,
          className: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
        };
      case 'fix':
        return {
          label: 'FIX',
          icon: <Wrench className="w-3 h-3 text-amber-400" />,
          className: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
        };
      case 'perf':
        return {
          label: 'PERF',
          icon: <Zap className="w-3 h-3 text-cyan-400" />,
          className: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
        };
      case 'refactor':
        return {
          label: 'REFACTOR',
          icon: <Code2 className="w-3 h-3 text-blue-400" />,
          className: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
        };
      case 'docs':
        return {
          label: 'DOCS',
          icon: <BookOpen className="w-3 h-3 text-violet-400" />,
          className: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
        };
      case 'build':
      case 'ci':
        return {
          label: 'BUILD',
          icon: <Box className="w-3 h-3 text-rose-400" />,
          className: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
        };
      case 'chore':
        return {
          label: 'CHORE',
          icon: <Layers className="w-3 h-3 text-slate-400" />,
          className: 'bg-slate-500/10 text-slate-300 border-slate-500/30',
        };
      default:
        return {
          label: type.toUpperCase(),
          icon: <GitCommit className="w-3 h-3 text-slate-400" />,
          className: 'bg-slate-800 text-slate-300 border-slate-700',
        };
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center p-12">
        <div className="flex flex-col items-center gap-3 text-slate-400 font-mono text-xs">
          <RefreshCw className="w-6 h-6 animate-spin text-amber-400" />
          <span>{t('tab_loading')}</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-4">
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 font-mono text-xs max-w-md text-center">
          {error || 'Không thể tải dữ liệu lịch sử phiên bản'}
        </div>
        <button
          onClick={() => fetchVersionHistory(false)}
          className="px-4 py-2 bg-amber-500 text-slate-950 rounded-lg text-xs font-bold hover:bg-amber-400 transition"
        >
          {t('btn_retry')}
        </button>
      </div>
    );
  }

  const { repo, stats, top_scopes, daily_velocity, milestones, changelog_raw } = data;

  return (
    <div className="flex-1 flex flex-col gap-4 p-3 sm:p-5 overflow-y-auto bg-slate-950 text-slate-200">
      {/* Feedback Toast */}
      {feedback && (
        <div
          className={`fixed top-16 right-5 z-50 flex items-center gap-2 px-4 py-2.5 rounded-lg border text-xs font-medium shadow-2xl backdrop-blur-md transition-all ${
            feedback.type === 'success'
              ? 'bg-emerald-950/90 text-emerald-300 border-emerald-500/40 shadow-emerald-950/40'
              : 'bg-red-950/90 text-red-300 border-red-500/40 shadow-red-950/40'
          }`}
        >
          {feedback.type === 'success' ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <Info className="w-4 h-4 text-red-400" />}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Header & GitHub Repo Link */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between bg-slate-900/80 border border-slate-800 p-4 rounded-2xl shadow-xl backdrop-blur-md">
        <div className="flex items-start gap-3.5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/30 text-amber-400 shadow-lg shadow-amber-500/10">
            <GitPullRequest className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base sm:text-lg font-black tracking-wide text-amber-300">
                {t('updates_header_title')}
              </h2>
              <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] font-mono font-bold text-amber-300">
                <Tag className="w-3 h-3" />
                {repo.current_tag}
              </span>
              <span className="inline-flex items-center gap-1 rounded-md border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] font-mono text-sky-300">
                <GitBranch className="w-3 h-3" />
                {repo.branch}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed max-w-3xl">
              {t('updates_header_sub')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 shrink-0 self-end lg:self-center flex-wrap">
          <a
            href={repo.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white transition shadow-sm"
          >
            <ExternalLink className="w-3.5 h-3.5 text-amber-400" />
            <span>GitHub</span>
          </a>

          <button
            type="button"
            onClick={() => fetchVersionHistory(true)}
            disabled={isSyncing}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-bold transition disabled:opacity-50"
            title={t('updates_btn_sync_github')}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
            <span>{isSyncing ? t('updates_syncing') : t('updates_btn_sync_github')}</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setShowUpdateModal(true);
              fetchUpdateStatus();
            }}
            className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold shadow-md transition active:scale-95 ${
              updateStatus?.update_available
                ? 'bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-slate-950 shadow-emerald-500/20 animate-pulse'
                : 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 shadow-amber-500/20'
            }`}
            title="Cập nhật hệ thống 1-Click"
          >
            <Rocket className="w-3.5 h-3.5" />
            <span>{t('updates_btn_one_click_update')}</span>
            {updateStatus?.update_available && (
              <span className="ml-1 rounded-full bg-emerald-950 px-1.5 py-0.2 text-[10px] font-mono font-bold text-emerald-300">
                +{updateStatus.commits_behind}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Update Available Notification Banner */}
      {updateStatus?.update_available && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-gradient-to-r from-emerald-950/90 via-slate-900 to-slate-900 border border-emerald-500/40 p-4 rounded-2xl shadow-xl backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-400">
              <Sparkles className="h-5 w-5 animate-spin" style={{ animationDuration: '4s' }} />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs sm:text-sm font-black text-emerald-300">
                  {t('updates_new_version_available')}
                </span>
                <span className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-mono font-bold text-emerald-300">
                  {updateStatus.commits_behind} Commits mới ({updateStatus.remote_commit_short})
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-0.5 font-mono">
                {updateStatus.remote_commit_message}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowUpdateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-black text-xs shadow-lg shadow-emerald-500/20 transition active:scale-95 shrink-0"
          >
            <Rocket className="w-4 h-4" />
            <span>{t('updates_btn_start_update')}</span>
          </button>
        </div>
      )}

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Total Commits */}
        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
            <span>{t('updates_stat_total_commits')}</span>
            <GitCommit className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-black font-mono text-amber-300">
              {stats.total_commits}
            </span>
            <span className="text-[11px] font-mono text-emerald-400">
              +{stats.total_insertions.toLocaleString()} / -{stats.total_deletions.toLocaleString()}
            </span>
          </div>
        </div>

        {/* Current Version */}
        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
            <span>{t('updates_stat_current_version')}</span>
            <Tag className="w-4 h-4 text-sky-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-lg font-black font-mono text-sky-300 truncate">
              {repo.current_tag}
            </span>
            {repo.head_hash && (
              <span className="text-[10px] font-mono text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">
                {repo.head_hash.slice(0, 7)}
              </span>
            )}
          </div>
        </div>

        {/* Latest Push */}
        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
            <span>{t('updates_stat_last_push')}</span>
            <Clock className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2">
            <div className="text-xs font-mono font-bold text-slate-200 truncate">
              {formatSystemDateTime(stats.last_commit_date)}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              branch <span className="text-amber-400 font-mono">{repo.branch}</span>
            </div>
          </div>
        </div>

        {/* Active Days */}
        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
            <span>{t('updates_stat_active_days')}</span>
            <Calendar className="w-4 h-4 text-violet-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-black font-mono text-violet-300">
              {stats.active_days}
            </span>
            <span className="text-[11px] text-slate-400">ngày phát triển</span>
          </div>
        </div>
      </div>

      {/* Sub-Tabs View Switcher */}
      <div className="flex items-center justify-between flex-wrap gap-3 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-1.5 bg-slate-900 p-1 rounded-xl border border-slate-800">
          <button
            type="button"
            onClick={() => setActiveSubTab('TIMELINE')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeSubTab === 'TIMELINE'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>{t('updates_tab_timeline')}</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-950/40 font-mono">
              {filteredCommits.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('ROADMAP')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeSubTab === 'ROADMAP'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>{t('updates_tab_roadmap')}</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-950/40 font-mono">
              {milestones.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('ANALYTICS')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeSubTab === 'ANALYTICS'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Flame className="w-3.5 h-3.5" />
            <span>{t('updates_velocity_chart_title')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('CHANGELOG')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeSubTab === 'CHANGELOG'
                ? 'bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <FileCode className="w-3.5 h-3.5" />
            <span>{t('updates_tab_changelog')}</span>
          </button>
        </div>

        {/* Quick Type breakdown stats bar */}
        <div className="flex items-center gap-1.5 overflow-x-auto text-[11px] font-mono">
          {stats.type_counts.feat && (
            <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              🚀 {stats.type_counts.feat} feats
            </span>
          )}
          {stats.type_counts.fix && (
            <span className="px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-400 border border-amber-500/20">
              🛠️ {stats.type_counts.fix} fixes
            </span>
          )}
          {stats.type_counts.perf && (
            <span className="px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              ⚡ {stats.type_counts.perf} perfs
            </span>
          )}
          {stats.type_counts.docs && (
            <span className="px-2 py-0.5 rounded-md bg-violet-500/10 text-violet-400 border border-violet-500/20">
              📚 {stats.type_counts.docs} docs
            </span>
          )}
        </div>
      </div>

      {/* VIEW 1: TIMELINE */}
      {activeSubTab === 'TIMELINE' && (
        <div className="flex flex-col gap-4">
          {/* Search & Filter bar */}
          <div className="flex flex-col md:flex-row items-stretch md:items-center gap-2.5 bg-slate-900/90 border border-slate-800 p-3 rounded-xl">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('updates_search_placeholder')}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-200"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Type filters */}
            <div className="flex items-center gap-1 overflow-x-auto shrink-0">
              {[
                { id: 'ALL', label: t('updates_filter_all') },
                { id: 'feat', label: t('updates_filter_feat') },
                { id: 'fix', label: t('updates_filter_fix') },
                { id: 'perf', label: t('updates_filter_perf') },
                { id: 'refactor', label: t('updates_filter_refactor') },
                { id: 'docs', label: t('updates_filter_docs') },
                { id: 'build', label: t('updates_filter_build') },
              ].map((filter) => (
                <button
                  type="button"
                  key={filter.id}
                  onClick={() => setSelectedType(filter.id)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-semibold whitespace-nowrap transition ${
                    selectedType === filter.id
                      ? 'bg-amber-500 text-slate-950'
                      : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            {/* Scope filter dropdown */}
            {top_scopes.length > 0 && (
              <div className="flex items-center gap-1 shrink-0">
                <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" />
                <select
                  value={selectedScope}
                  onChange={(e) => setSelectedScope(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-amber-500"
                >
                  <option value="ALL">Module: Tất cả</option>
                  {top_scopes.map((s) => (
                    <option key={s.scope} value={s.scope}>
                      {s.scope} ({s.count})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Timeline List */}
          {Object.keys(groupedCommits).length === 0 ? (
            <div className="bg-slate-900/60 border border-slate-800 p-8 rounded-xl text-center text-slate-400 text-xs font-mono">
              {t('updates_no_commits_match')}
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(groupedCommits).map(([day, commitsOnDay]) => (
                <div key={day} className="relative pl-6 before:absolute before:left-2.5 before:top-3 before:bottom-0 before:w-0.5 before:bg-slate-800">
                  {/* Date badge */}
                  <div className="sticky top-2 z-10 -ml-6 mb-3 inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-slate-900/95 px-3 py-1 text-xs font-mono font-bold text-amber-300 shadow-md backdrop-blur-md">
                    <Calendar className="w-3.5 h-3.5 text-amber-400" />
                    <span>{day}</span>
                    <span className="text-[10px] text-slate-400 font-normal">
                      ({commitsOnDay.length} commits)
                    </span>
                  </div>

                  {/* Commits cards */}
                  <div className="space-y-2.5">
                    {commitsOnDay.map((c) => {
                      const badge = getTypeBadge(c.type);
                      const isCopied = copiedHash === c.hash;

                      return (
                        <div
                          key={c.hash}
                          className="group relative rounded-xl border border-slate-800/80 bg-slate-900/70 p-3.5 shadow-sm transition hover:border-slate-700 hover:bg-slate-900 hover:shadow-md"
                        >
                          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                            {/* Left: Type, Scope, Message */}
                            <div className="flex items-start gap-2.5 min-w-0 flex-1">
                              {/* Type Badge */}
                              <span
                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-mono font-bold shrink-0 ${badge.className}`}
                              >
                                {badge.icon}
                                <span>{badge.label}</span>
                              </span>

                              {/* Scope Badge */}
                              {c.scope && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-slate-800 text-sky-300 border border-sky-500/20 text-[10px] font-mono shrink-0">
                                  {c.scope}
                                </span>
                              )}

                              {/* Commit Description */}
                              <div className="min-w-0 flex-1">
                                <div className="text-xs font-semibold text-slate-100 leading-snug break-words">
                                  {c.description || c.subject}
                                </div>
                                {c.ref_names && (
                                  <div className="mt-1 flex items-center gap-1 flex-wrap">
                                    <span className="text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30 px-1.5 py-0.2 rounded">
                                      🏷️ {c.ref_names}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Right: Hash, copy, stats, author */}
                            <div className="flex items-center gap-2 shrink-0 self-end sm:self-start">
                              {/* File stats */}
                              {c.stats && (c.stats.insertions > 0 || c.stats.deletions > 0) && (
                                <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
                                  <span className="text-emerald-400">+{c.stats.insertions}</span>
                                  {' / '}
                                  <span className="text-rose-400">-{c.stats.deletions}</span>
                                </span>
                              )}

                              {/* SHA Hash & Copy */}
                              <button
                                type="button"
                                onClick={() => handleCopyHash(c.hash)}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-[11px] font-mono text-amber-400 hover:bg-slate-800 transition"
                                title={isCopied ? t('updates_copied') : t('updates_copy_hash')}
                              >
                                {isCopied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                <span>{c.short_hash}</span>
                              </button>

                              {/* External Link */}
                              <a
                                href={c.github_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="p-1 rounded bg-slate-950 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition"
                                title={t('updates_view_on_github')}
                              >
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            </div>
                          </div>

                          {/* Footer Info: Author & Time */}
                          <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                            <div className="flex items-center gap-1.5">
                              <span className="w-4 h-4 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[9px] font-bold text-amber-300">
                                {c.author ? c.author.charAt(0).toUpperCase() : 'U'}
                              </span>
                              <span>{c.author}</span>
                            </div>
                            <div>{formatSystemDateTime(c.date)}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* VIEW 2: MILESTONE ROADMAP */}
      {activeSubTab === 'ROADMAP' && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {milestones.map((m, index) => (
              <div
                key={m.id}
                className="bg-slate-900 border border-slate-800 hover:border-amber-500/40 p-4 rounded-2xl shadow-xl transition flex flex-col justify-between relative overflow-hidden group"
              >
                {/* Milestone Step Indicator */}
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs font-black font-mono text-amber-300">
                      {milestones.length - index}
                    </span>
                    <span className="font-mono text-xs font-bold text-sky-400 bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 rounded">
                      {m.tag}
                    </span>
                  </div>

                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3" />
                    {t('updates_milestone_completed')}
                  </span>
                </div>

                <div>
                  <h3 className="text-sm font-bold text-slate-100 group-hover:text-amber-300 transition">
                    {m.title}
                  </h3>
                  <div className="text-[10px] font-mono text-slate-400 mt-0.5 flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    {m.date}
                  </div>
                  <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                    {m.description}
                  </p>

                  {/* Highlights list */}
                  {m.highlights && m.highlights.length > 0 && (
                    <div className="mt-3 space-y-1 bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/80">
                      <div className="text-[10px] font-semibold uppercase text-slate-400 tracking-wider">
                        ✨ Điểm nổi bật:
                      </div>
                      {m.highlights.map((h, i) => (
                        <div key={i} className="text-xs text-slate-300 flex items-start gap-1.5">
                          <span className="text-amber-400 font-bold">•</span>
                          <span>{h}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* VIEW 3: VELOCITY & ANALYTICS */}
      {activeSubTab === 'ANALYTICS' && (
        <div className="flex flex-col gap-5">
          {/* Velocity Chart */}
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-amber-300 flex items-center gap-2">
                <Flame className="w-4 h-4 text-amber-400" />
                {t('updates_velocity_chart_title')}
              </h3>
              <span className="text-[10px] font-mono text-slate-400">
                {daily_velocity.length} ngày ghi nhận hoạt động
              </span>
            </div>

            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={daily_velocity} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#94a3b8', fontSize: 10 }}
                    angle={-30}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#020617',
                      borderColor: '#334155',
                      borderRadius: '0.75rem',
                      fontSize: '11px',
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />
                  <Bar dataKey="feat" name="Features (feat)" fill="#10b981" stackId="a" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="fix" name="Fixes (fix)" fill="#f59e0b" stackId="a" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="perf" name="Perf (perf)" fill="#06b6d4" stackId="a" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="other" name="Chore/Docs/Build" fill="#64748b" stackId="a" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Breakdown cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Type Distribution */}
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl shadow-xl">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3 flex items-center gap-2">
                <Code2 className="w-4 h-4 text-emerald-400" />
                {t('updates_type_distribution_title')}
              </h3>

              <div className="space-y-2">
                {Object.entries(stats.type_counts)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => {
                    const pct = Math.round((count / stats.total_commits) * 100);
                    const badge = getTypeBadge(type);

                    return (
                      <div key={type} className="space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono flex items-center gap-1 text-slate-200">
                            {badge.icon}
                            {badge.label}
                          </span>
                          <span className="font-mono text-slate-400">
                            {count} ({pct}%)
                          </span>
                        </div>
                        <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                          <div
                            className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>

            {/* Top Functional Scopes */}
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-2xl shadow-xl">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3 flex items-center gap-2">
                <Layers className="w-4 h-4 text-sky-400" />
                {t('updates_top_modules_title')}
              </h3>

              <div className="flex flex-wrap gap-2">
                {top_scopes.map((s) => (
                  <div
                    key={s.scope}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono hover:border-slate-700 transition"
                  >
                    <span className="text-sky-300 font-bold">{s.scope}</span>
                    <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-400 text-[10px]">
                      {s.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* VIEW 4: CHANGELOG RAW */}
      {activeSubTab === 'CHANGELOG' && (
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-xl">
          <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-3">
            <div className="text-xs font-bold uppercase text-amber-300 flex items-center gap-2">
              <FileCode className="w-4 h-4" />
              CHANGELOG.md (Keep a Changelog format)
            </div>
            <a
              href={`${repo.url}/blob/main/CHANGELOG.md`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-sky-400 hover:text-sky-300 inline-flex items-center gap-1 font-mono"
            >
              <span>View file</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <pre className="text-xs font-mono text-slate-300 bg-slate-950 p-4 rounded-xl border border-slate-800 overflow-x-auto leading-relaxed whitespace-pre-wrap">
            {changelog_raw || '# Changelog\n\nNo changelog content available.'}
          </pre>
        </div>
      )}

      {/* MODAL: 1-CLICK SYSTEM UPDATE */}
      {showUpdateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-950/80 backdrop-blur-md animate-fade-in">
          <div className="flex flex-col w-full max-w-2xl max-h-[90vh] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/60">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500/20 to-emerald-500/20 border border-amber-500/30 text-amber-400">
                  <Rocket className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm sm:text-base font-black text-amber-300 tracking-wide">
                    {t('updates_modal_title')}
                  </h3>
                  <p className="text-[11px] text-slate-400 font-mono">
                    GitHub: {repo.owner}/{repo.name} ({repo.branch})
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (!isUpdating) setShowUpdateModal(false);
                }}
                disabled={isUpdating}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition disabled:opacity-30"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-4 sm:p-5 flex flex-col gap-4">
              {/* Version Comparison Card */}
              <div className="grid grid-cols-2 gap-3 p-3.5 bg-slate-950/70 border border-slate-800 rounded-xl font-mono text-xs">
                <div className="flex flex-col gap-1">
                  <span className="text-slate-400 text-[10px] uppercase font-sans font-bold">Phiên bản cục bộ</span>
                  <div className="flex items-center gap-1.5 text-amber-300 font-bold">
                    <Tag className="w-3.5 h-3.5 text-amber-400" />
                    <span>{updateStatus?.local_commit_short || repo.head_hash}</span>
                  </div>
                  <span className="text-[11px] text-slate-400 truncate">
                    {updateStatus?.local_commit_message || 'Bản chạy hiện tại'}
                  </span>
                </div>

                <div className="flex flex-col gap-1 border-l border-slate-800 pl-3">
                  <span className="text-slate-400 text-[10px] uppercase font-sans font-bold">Bản mới trên GitHub</span>
                  <div className="flex items-center gap-1.5 text-emerald-300 font-bold">
                    <ArrowDownCircle className="w-3.5 h-3.5 text-emerald-400" />
                    <span>{updateStatus?.remote_commit_short || repo.current_tag}</span>
                  </div>
                  <span className="text-[11px] text-slate-400 truncate">
                    {updateStatus?.remote_commit_message || 'Đang đồng bộ...'}
                  </span>
                </div>
              </div>

              {/* Update Status Summary Badges */}
              <div className="flex items-center gap-2 flex-wrap text-xs">
                {updateStatus?.update_available ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 font-bold">
                    <Check className="w-3.5 h-3.5" /> Có {updateStatus.commits_behind} commit mới
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-300">
                    <Check className="w-3.5 h-3.5 text-emerald-400" /> {t('updates_system_up_to_date')}
                  </span>
                )}

                {updateStatus?.has_dependency_changes && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-300">
                    <Box className="w-3.5 h-3.5" /> Có thay đổi thư viện Python (uv sync)
                  </span>
                )}

                {updateStatus?.has_frontend_changes && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-sky-500/10 border border-sky-500/30 text-sky-300">
                    <Sparkles className="w-3.5 h-3.5" /> Có cập nhật giao diện (npm build)
                  </span>
                )}
              </div>

              {/* Commits preview list */}
              {updateStatus?.new_commits && updateStatus.new_commits.length > 0 && (
                <div className="flex flex-col gap-2">
                  <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                    Các thay đổi mới sẽ áp dụng ({updateStatus.new_commits.length} commits):
                  </span>
                  <div className="max-h-36 overflow-y-auto flex flex-col gap-1.5 pr-1">
                    {updateStatus.new_commits.map((c) => (
                      <div
                        key={c.hash}
                        className="flex items-center justify-between gap-2 p-2 rounded-lg bg-slate-950/50 border border-slate-800/80 text-xs font-mono"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-amber-300 font-bold">
                            {c.short_hash}
                          </span>
                          <span className="text-slate-200 truncate">{c.message}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 shrink-0">{c.author}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Terminal Logs Window */}
              {(isUpdating || updateLogs.length > 0) && (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span className="font-bold flex items-center gap-1.5">
                      <Terminal className="w-3.5 h-3.5 text-amber-400" />
                      {t('updates_logs_title')}
                    </span>
                    {isUpdating && (
                      <span className="text-amber-400 flex items-center gap-1 animate-pulse font-mono text-[11px]">
                        <RefreshCw className="w-3 h-3 animate-spin" /> Đang cập nhật...
                      </span>
                    )}
                  </div>
                  <div className="h-44 overflow-y-auto bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-xs text-emerald-400 flex flex-col gap-1 select-text leading-relaxed">
                    {updateLogs.map((log, i) => (
                      <div key={i} className="whitespace-pre-wrap break-all">
                        {log}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Feedback Alert in Modal */}
              {updateSuccess && (
                <div className="p-3.5 bg-emerald-950/80 border border-emerald-500/40 rounded-xl text-emerald-300 text-xs font-medium flex items-center gap-2.5">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                  <div>
                    <div className="font-bold">Cập nhật thành công!</div>
                    <div className="text-[11px] text-emerald-200/80">
                      Hệ thống và các dịch vụ đã được khởi động lại. Tự động tải lại trang sau {countdown ?? 5}s...
                    </div>
                  </div>
                </div>
              )}

              {updateError && (
                <div className="p-3.5 bg-red-950/80 border border-red-500/40 rounded-xl text-red-300 text-xs font-medium flex items-center gap-2.5">
                  <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
                  <div>
                    <div className="font-bold">Cập nhật thất bại:</div>
                    <div className="text-[11px] text-red-200/80">{updateError}</div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between p-4 border-t border-slate-800 bg-slate-950/60 gap-3">
              <button
                type="button"
                onClick={fetchUpdateStatus}
                disabled={isUpdating || isCheckingUpdate}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isCheckingUpdate ? 'animate-spin' : ''}`} />
                <span>Kiểm tra lại</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowUpdateModal(false)}
                  disabled={isUpdating}
                  className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-800 transition disabled:opacity-30"
                >
                  Đóng
                </button>

                <button
                  type="button"
                  onClick={handleStartUpdate}
                  disabled={isUpdating}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-black text-xs shadow-lg shadow-emerald-500/20 transition active:scale-95 disabled:opacity-50"
                >
                  <Rocket className={`w-4 h-4 ${isUpdating ? 'animate-bounce' : ''}`} />
                  <span>{isUpdating ? t('updates_updating_in_progress') : t('updates_btn_start_update')}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
