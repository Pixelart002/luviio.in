import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/axios';

export default function Dashboard() {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        const fetchUser = async () => {
            try {
                const res = await api.get('/auth/me');
                setUser(res.data.user);
            } catch (err) {
                navigate('/login'); // Token nahi hai ya expire ho gaya toh wapas login pe
            } finally {
                setLoading(false);
            }
        };
        fetchUser();
    }, [navigate]);

    const handleLogout = async () => {
        try {
            await api.post('/auth/logout');
            navigate('/login');
        } catch (err) {
            console.error("Logout failed", err);
        }
    };

    if (loading) return <h2>Loading...</h2>;

    return (
        <div style={{ padding: '50px', fontFamily: 'sans-serif' }}>
            <h1>Dashboard 🛡️</h1>
            <h3>Welcome back, {user?.name || user?.email}!</h3>
            <p>This is a protected route. Only logged-in users can see this.</p>
            <button onClick={handleLogout} style={{ padding: '10px 20px', background: '#dc3545', color: 'white', border: 'none', borderRadius: '5px' }}>Logout</button>
        </div>
    );
}
