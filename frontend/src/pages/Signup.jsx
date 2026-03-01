import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { supabase } from '../api/supabase';

export default function Signup() {
    const [formData, setFormData] = useState({ name: '', email: '', password: '' });
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        
        // Supabase ka built-in secure signup
        const { data, error } = await supabase.auth.signUp({
            email: formData.email,
            password: formData.password,
            options: {
                data: { name: formData.name } // Name save karne ke liye
            }
        });

        if (error) {
            setError(error.message);
        } else {
            alert("Signup successful! You can now login.");
            navigate('/login');
        }
        setLoading(false);
    };

    return (
        <div style={{ maxWidth: '300px', margin: '50px auto', fontFamily: 'sans-serif' }}>
            <h2>Sign Up</h2>
            {error && <p style={{ color: 'red' }}>{error}</p>}
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <input type="text" placeholder="Name" required onChange={(e) => setFormData({...formData, name: e.target.value})} />
                <input type="email" placeholder="Email" required onChange={(e) => setFormData({...formData, email: e.target.value})} />
                <input type="password" placeholder="Password" required onChange={(e) => setFormData({...formData, password: e.target.value})} />
                <button type="submit" disabled={loading} style={{ padding: '10px', background: '#28a745', color: 'white', border: 'none', borderRadius: '5px' }}>
                    {loading ? 'Signing up...' : 'Register'}
                </button>
            </form>
            <p>Already have an account? <Link to="/login">Login</Link></p>
        </div>
    );
}
