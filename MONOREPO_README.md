# Luviio Monorepo - Quick Start Guide

Welcome to the Luviio monorepo! This repository contains both the frontend (Next.js) and backend (FastAPI) applications for the Luviio Store.

## Quick Start

### Prerequisites

- **Node.js** (v18+)
- **Python** (v3.11+)
- **Git**

### Development Setup

#### 1. Clone the Repository

```bash
git clone https://github.com/Pixelart002/luviio.in.git
cd luviio.in
```

#### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file with your Supabase credentials
cat > .env << EOF
SB_URL=your_supabase_url
SB_SERVICE_ROLE_KEY=your_supabase_service_role_key
EOF

# Run the backend server
uvicorn main:app --reload --port 8000
```

The backend will be available at `http://localhost:8000/api/v1`.

#### 3. Frontend Setup (in a new terminal)

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local file
cp .env.local.example .env.local

# Run the development server
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## Project Structure

```
luviio.in/
├── frontend/              # Next.js application
│   ├── src/
│   │   ├── app/          # Next.js App Router
│   │   ├── components/   # React components
│   │   ├── hooks/        # Custom hooks (useAuth)
│   │   └── lib/          # Utilities (API client)
│   └── package.json
│
├── backend/              # FastAPI application
│   ├── app/
│   │   └── api/          # API routes
│   ├── core/             # Configuration
│   ├── models/           # Database models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   ├── main.py           # Entry point
│   └── requirements.txt
│
├── vercel.json           # Vercel deployment config
├── DEVOPS_SETUP.md       # Detailed DevOps guide
└── README.md             # Original README
```

## Key Features

### Frontend

- **Next.js 14** with TypeScript
- **Tailwind CSS** for styling
- **React Hooks** for state management
- **API Integration** with custom `useAuth` hook
- **Authentication Pages** (signup/login)

### Backend

- **FastAPI** for high-performance API
- **Supabase** for database and authentication
- **CORS Middleware** for cross-origin requests
- **Rate Limiting** with slowapi
- **JWT Authentication** support

## API Endpoints

### Authentication

- `POST /api/v1/users/signup` - Register a new user
- `POST /api/v1/users/login` - Authenticate a user
- `GET /api/v1/users/me` - Get current user profile
- `POST /api/v1/users/logout` - Logout user

## Environment Variables

### Frontend (.env.local)

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

### Backend (.env)

```env
SB_URL=your_supabase_url
SB_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

## Deployment

For detailed deployment instructions, see [DEVOPS_SETUP.md](./DEVOPS_SETUP.md).

### Quick Deploy to Vercel

1. Push your code to GitHub
2. Go to https://vercel.com/import
3. Select your repository
4. Set environment variables in Vercel dashboard
5. Click Deploy

## Development Workflow

### Adding New API Endpoints

1. Create a new file in `backend/app/api/v1/endpoints/`
2. Define your routes using FastAPI decorators
3. Include the router in `backend/app/api/router.py`
4. Update the frontend API client in `frontend/src/lib/api.ts`

### Adding New Frontend Pages

1. Create a new directory in `frontend/src/app/`
2. Add a `page.tsx` file
3. Use the `useAuth` hook for authentication state
4. Use the API client from `frontend/src/lib/api.ts` for backend calls

## Troubleshooting

### Backend won't start

- Ensure Python 3.11+ is installed
- Check that all dependencies are installed: `pip install -r requirements.txt`
- Verify environment variables are set in `.env`

### Frontend won't start

- Ensure Node.js 18+ is installed
- Delete `node_modules` and `package-lock.json`, then run `npm install`
- Check that `.env.local` is properly configured

### API calls failing

- Verify backend is running on `http://localhost:8000`
- Check `NEXT_PUBLIC_API_BASE_URL` in `.env.local`
- Look at browser console and backend logs for error messages

## Contributing

1. Create a new branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Commit: `git commit -m "Add your feature"`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

## Support

For issues or questions, please open an issue on GitHub or contact the development team.

## License

This project is private and proprietary to Luviio.

---

**Last Updated:** March 2026
