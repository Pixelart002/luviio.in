import jwt from 'jsonwebtoken';

// Access Token Generate Karna
export const generateAccessToken = (userId) => {
    return jwt.sign({ id: userId }, process.env.ACCESS_TOKEN_SECRET, {
        expiresIn: process.env.ACCESS_TOKEN_EXPIRY
    });
};

// Refresh Token Generate Karna
export const generateRefreshToken = (userId) => {
    return jwt.sign({ id: userId }, process.env.REFRESH_TOKEN_SECRET, {
        expiresIn: process.env.REFRESH_TOKEN_EXPIRY
    });
};

// Cookie Options - Secure & Production Ready
export const cookieOptions = {
    httpOnly: true, // Client-side JS isko read nahi kar sakta (XSS protection)
    secure: process.env.NODE_ENV === 'production', // Prod me sirf HTTPS pe chalega
    sameSite: 'lax', // CSRF protection ke liye 'lax' best hai general use ke liye
};