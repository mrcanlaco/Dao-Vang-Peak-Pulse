import React, { Component, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an unhandled error:', error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center p-8 gap-3 bg-slate-950 border border-red-500/30 rounded-xl m-4 text-center">
          <AlertTriangle className="w-10 h-10 text-red-400 animate-bounce" />
          <h3 className="text-sm font-bold text-slate-200 uppercase">
            {this.props.fallbackTitle || 'Đã xảy ra sự cố giao diện'}
          </h3>
          <p className="text-xs text-red-400 font-mono max-w-md">
            {this.state.error?.message || this.props.fallbackMessage || 'Không thể kết xuất thành phần này.'}
          </p>
          <button
            onClick={this.handleRetry}
            className="mt-2 px-4 py-2 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg text-xs font-bold flex items-center gap-2 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Thử tải lại (Retry)
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
