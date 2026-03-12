# DevOps Setup Guide for Luviio Monorepo

This guide provides comprehensive instructions for setting up and deploying the Luviio monorepo on Vercel.

## Table of Contents

1. [Project Structure](#project-structure)
2. [Local Development Setup](#local-development-setup)
3. [Frontend Configuration](#frontend-configuration)
4. [Backend Configuration](#backend-configuration)
5. [Vercel Deployment](#vercel-deployment)
6. [Environment Variables](#environment-variables)
7. [Troubleshooting](#troubleshooting)

## Project Structure

The Luviio monorepo is organized as follows:

```
luviio.in/
├── frontend/                    # Next.js application
│   ├── src/
│   │   ├── app/                 # Next.js App Router
│   │   ├── components/          # React components
│   │   ├── hooks/               # Custom React hooks (including useAuth)
│   │   └── lib/                 # Utility functions (including API client)
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   └── .env.local.example       # Environment variables template
│
├── backend/                     # FastAPI application
│   ├── app/
│   │   └── api/                 # API routes
│   ├── core/                    # Core configurations
│   ├── models/                  # Database models
│   ├── schemas/                 # Pydantic schemas
│   ├── services/                # Business logic
│   ├── main.py                  # FastAPI entry point
│   └── requirements.txt         # Python dependencies
│
├── vercel.json                  # Vercel deployment configuration
├── DEVOPS_SETUP.md              # This file
└── devops_analysis.md           # Detailed analysis of DevOps structure
```

## Local Development Setup

### Prerequisites

- **Node.js** (v18+) and **npm** or **pnpm**
- **Python** (v3.11+)
- **Git**

### Backend Setup

1. Navigate to the backend directory:

```bash
cd backend
```

2. Create a Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install Python dependencies:

```bash
pip install -r requirements.txt
```

4. Set up environment variables:

Create a `.env` file in the `backend/` directory with the following variables:

```env
SB_URL=your_supabase_url
SB_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

5. Run the backend server:

```bash
uvicorn main:app --reload --port 8000
```

The backend API will be available at `http://localhost:8000/api/v1`.

### Frontend Setup

1. Navigate to the frontend directory:

```bash
cd frontend
```

2. Install Node.js dependencies:

```bash
npm install
# or
pnpm install
```

3. Set up environment variables:

Copy `.env.local.example` to `.env.local`:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` and set the API base URL:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

4. Run the frontend development server:

```bash
npm run dev
# or
pnpm dev
```

The frontend will be available at `http://localhost:3000`.

## Frontend Configuration

### API Integration

The frontend uses a custom API client located at `src/lib/api.ts` to communicate with the backend. The API base URL is configured via the `NEXT_PUBLIC_API_BASE_URL` environment variable.

#### Key API Functions

- **`signupUser(userData)`**: Register a new user
- **`loginUser(credentials)`**: Authenticate a user
- **`getCurrentUser(token)`**: Fetch the current user's profile
- **`logoutUser(token)`**: Logout the current user

### Authentication Hook

The `src/hooks/useAuth.ts` hook provides a convenient way to manage authentication state in React components:

```typescript
import { useAuth } from '@/hooks/useAuth';

export function MyComponent() {
  const { user, isLoading, error, signup, login, logout, isAuthenticated } = useAuth();

  // Use the hook to manage authentication
}
```

### Example: Using the Auth Hook

```typescript
import { useAuth } from '@/hooks/useAuth';

export function LoginForm() {
  const { login, isLoading, error } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await login(email, password);
      // Redirect to dashboard on success
    } catch (err) {
      // Error is handled by the hook
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {error && <div className="error">{error}</div>}
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      <button type="submit" disabled={isLoading}>
        {isLoading ? 'Logging in...' : 'Login'}
      </button>
    </form>
  );
}
```

## Backend Configuration

### FastAPI Setup

The backend is built with FastAPI and includes the following features:

- **CORS Middleware**: Configured to allow requests from the frontend
- **Rate Limiting**: Implemented using `slowapi` to prevent abuse
- **Supabase Integration**: For database and authentication
- **JWT Authentication**: For securing API endpoints

### API Routes

The API routes are organized in the `app/api/` directory:

- **`/api/v1/users/signup`**: POST - Register a new user
- **`/api/v1/users/login`**: POST - Authenticate a user (to be implemented)
- **`/api/v1/users/me`**: GET - Fetch the current user's profile (to be implemented)
- **`/api/v1/users/logout`**: POST - Logout the current user (to be implemented)

### CORS Configuration

The backend allows requests from the following origins:

- `http://localhost:3000` (local development)
- `https://luviio.in` (production)
- `https://www.luviio.in` (production with www)

To add more origins, update the `allow_origins` list in `backend/main.py`.

## Vercel Deployment

### Prerequisites

- A Vercel account (https://vercel.com)
- The Vercel CLI installed (`npm install -g vercel`)

### Deployment Steps

1. **Connect the Repository**

   - Push your code to GitHub
   - Go to https://vercel.com/import
   - Select your GitHub repository

2. **Configure Environment Variables**

   In the Vercel dashboard, set the following environment variables:

   - `SB_URL`: Your Supabase project URL
   - `SB_SERVICE_ROLE_KEY`: Your Supabase service role key
   - `NEXT_PUBLIC_API_BASE_URL`: The production API URL (e.g., `https://your-vercel-app.vercel.app/api/v1`)

3. **Deploy**

   - Click "Deploy"
   - Vercel will automatically build and deploy both the frontend and backend

### Vercel Configuration

The `vercel.json` file at the root of the repository defines the build and deployment configuration:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "backend/main.py",
      "use": "@vercel/python",
      "config": {
        "runtime": "python3.11"
      }
    },
    {
      "src": "frontend/package.json",
      "use": "@vercel/next"
    }
  ],
  "rewrites": [
    {
      "source": "/api/v1/(.*)",
      "destination": "/backend/main.py"
    },
    {
      "source": "/(.*)",
      "destination": "/frontend/$1"
    }
  ]
}
```

This configuration:

- Builds the backend using the Python runtime
- Builds the frontend using the Next.js runtime
- Routes requests starting with `/api/v1/` to the backend
- Routes all other requests to the frontend

## Environment Variables

### Frontend Environment Variables

Create a `.env.local` file in the `frontend/` directory:

```env
# API Base URL
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1  # Development
# NEXT_PUBLIC_API_BASE_URL=https://your-vercel-app.vercel.app/api/v1  # Production
```

### Backend Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Supabase Configuration
SB_URL=your_supabase_project_url
SB_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Optional: Other configurations
DEBUG=False
```

### Vercel Environment Variables

Set the following in the Vercel dashboard:

| Variable | Value | Scope |
|----------|-------|-------|
| `SB_URL` | Your Supabase URL | Production |
| `SB_SERVICE_ROLE_KEY` | Your Supabase Service Role Key | Production |
| `NEXT_PUBLIC_API_BASE_URL` | `https://your-vercel-app.vercel.app/api/v1` | Production |

## Troubleshooting

### Issue: Frontend cannot connect to backend API

**Solution:**

1. Verify that the `NEXT_PUBLIC_API_BASE_URL` environment variable is set correctly
2. Check that the backend is running and accessible
3. Ensure CORS is properly configured in the backend (`backend/main.py`)
4. Check browser console for specific error messages

### Issue: Vercel deployment fails

**Solution:**

1. Check the Vercel deployment logs for specific errors
2. Ensure all required environment variables are set in the Vercel dashboard
3. Verify that `vercel.json` is correctly configured
4. Check that all dependencies are listed in `requirements.txt` (backend) and `package.json` (frontend)

### Issue: CORS errors when making API requests

**Solution:**

1. Verify that the frontend origin is listed in the `allow_origins` in `backend/main.py`
2. Ensure that the request includes the `Content-Type: application/json` header
3. Check that cookies are being sent with requests if needed (set `allow_credentials=True`)

### Issue: Authentication token not persisting

**Solution:**

1. Verify that the token is being saved to `localStorage` in the `useAuth` hook
2. Check that the token is being sent in the `Authorization` header for subsequent requests
3. Ensure that the backend is properly validating and returning tokens

## Additional Resources

- [Vercel Documentation](https://vercel.com/docs)
- [Next.js Documentation](https://nextjs.org/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Supabase Documentation](https://supabase.com/docs)
- [React Hooks Documentation](https://react.dev/reference/react)

## Support

For issues or questions, please refer to the project's GitHub repository or contact the development team.
