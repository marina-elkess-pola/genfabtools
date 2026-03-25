import React from 'react';

export default class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        this.setState({ errorInfo });
        console.error('ErrorBoundary caught:', error, errorInfo);
    }

    render() {
        if (!this.state.hasError) {
            return this.props.children;
        }

        return (
            <div className="min-h-[60vh] flex items-center justify-center px-6">
                <div className="max-w-md w-full rounded-xl border border-slate-200 bg-white p-8 shadow-sm text-center">
                    <div className="mx-auto w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mb-4">
                        <svg className="w-6 h-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                        </svg>
                    </div>

                    <h2 className="text-xl font-bold text-slate-900">Something went wrong</h2>
                    <p className="mt-2 text-sm text-slate-500">An unexpected error occurred. Please try refreshing the page.</p>

                    <div className="mt-6 flex flex-wrap justify-center gap-3">
                        <button
                            onClick={() => window.location.reload()}
                            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-slate-800 transition"
                        >
                            Refresh
                        </button>
                        <a
                            href="/"
                            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 text-slate-700 px-5 py-2.5 text-sm font-semibold hover:bg-slate-50 transition"
                        >
                            Go Home
                        </a>
                    </div>

                    {import.meta.env.DEV && this.state.error && (
                        <details className="mt-6 text-left">
                            <summary className="cursor-pointer text-xs font-medium text-slate-400 hover:text-slate-600">
                                Error details (dev only)
                            </summary>
                            <pre className="mt-2 rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs text-red-700 overflow-auto max-h-60 whitespace-pre-wrap">
                                {this.state.error.toString()}
                                {this.state.errorInfo?.componentStack}
                            </pre>
                        </details>
                    )}
                </div>
            </div>
        );
    }
}
