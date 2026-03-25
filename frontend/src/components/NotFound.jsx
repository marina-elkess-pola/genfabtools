import { Link } from 'react-router-dom';

export default function NotFound() {
    return (
        <div className="min-h-[60vh] flex items-center justify-center px-6">
            <div className="text-center">
                <p className="text-6xl font-extrabold text-slate-200">404</p>
                <h1 className="mt-4 text-2xl font-bold text-slate-900">Page not found</h1>
                <p className="mt-2 text-sm text-slate-500">The page you're looking for doesn't exist or has been moved.</p>
                <div className="mt-6 flex flex-wrap justify-center gap-3">
                    <Link to="/" className="inline-flex items-center gap-2 rounded-lg bg-slate-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-slate-800 transition">
                        Go Home
                    </Link>
                    <Link to="/tools" className="inline-flex items-center gap-2 rounded-lg border border-slate-200 text-slate-700 px-5 py-2.5 text-sm font-semibold hover:bg-slate-50 transition">
                        Browse Tools
                    </Link>
                </div>
            </div>
        </div>
    );
}
