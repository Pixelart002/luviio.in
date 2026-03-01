import axios from 'axios';

export const api = axios.create({
    // VITE_BACKEND_URL hum baad me set karenge
    baseURL: import.meta.env.VITE_BACKEND_URL || 'http://localhost:5000/api',
    withCredentials: true, // Cookies frontend se backend bhejne ke liye VERY IMPORTANT
});
