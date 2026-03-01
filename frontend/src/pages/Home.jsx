import { Link } from 'react-router-dom';

export default function Home() {
    return (
        <div style={{ textAlign: 'center', marginTop: '50px', fontFamily: 'sans-serif' }}>
            <h1>Welcome to Luviio 🚀</h1>
            <p>Your secure production-ready app.</p>
            <div style={{ marginTop: '20px' }}>
                <Link to="/login" style={{ marginRight: '15px', padding: '10px 20px', background: '#007bff', color: 'white', textDecoration: 'none', borderRadius: '5px' }}>Login</Link>
                <Link to="/signup" style={{ padding: '10px 20px', background: '#28a745', color: 'white', textDecoration: 'none', borderRadius: '5px' }}>Sign Up</Link>
            </div>
        </div>
    );
}
