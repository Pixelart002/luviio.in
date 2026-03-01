import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../api/supabase';

export default function Dashboard() {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        const checkUser = async () => {
            const { data: { session } } = await supabase.auth.getSession();
            
            if (!session) {
                navigate('/login');
            } else {
                setUser(session.user);
            }
            setLoading(false);
        };
        
        checkUser();
    }, [navigate]);

    const handleLogout = async () => {
        await supabase.auth.signOut();
        navigate('/login');
    };

    if (loading) return <h2>Loading...</h2>;

    return (
        <div style={{ padding: '50px', fontFamily: 'sans-serif' }}>
            <h1>Dashboard 🛡️</h1>
            <h3>Welcome back, {user?.user_metadata?.name || user?.email}!</h3>
            <p>You are logged in directly via Supabase inside React.</p>
            <button onClick={handleLogout} style={{ padding: '10px 20px', background: '#dc3545', color: 'white', border: 'none', borderRadius: '5px' }}>Logout</button>
        </div>
    );
}
