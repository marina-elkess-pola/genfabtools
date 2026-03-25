import { Navigate, useLocation } from 'react-router-dom';

export default function ProtectedRoute({ children }) {
    const location = useLocation();
    const token = localStorage.getItem('token');

    if (!token) {
        localStorage.setItem('postAuthRedirect', location.pathname);
        return <Navigate to="/login" replace />;
    }

    return children;
}
