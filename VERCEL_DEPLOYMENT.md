# Vercel Deployment Guide for Luviio Monorepo

This guide explains how to properly deploy the Luviio monorepo to Vercel with both the Next.js frontend and FastAPI backend working together.

## Prerequisites

1. A Vercel account (https://vercel.com)
2. Your code pushed to GitHub
3. Supabase credentials (URL and Service Role Key)

## Step 1: Connect Your Repository to Vercel

1. Go to https://vercel.com/import
2. Click "Import Project"
3. Select "GitHub" and authorize Vercel to access your repositories
4. Find and select `Pixelart002/luviio.in`
5. Click "Import"

## Step 2: Configure Environment Variables

In the Vercel dashboard, go to **Settings → Environment Variables** and add the following:

### Required Variables

| Variable | Value | Scope |
|----------|-------|-------|
| `SB_URL` | Your Supabase project URL | Production |
| `SB_SERVICE_ROLE_KEY` | Your Supabase service role key | Production |
| `NEXT_PUBLIC_API_BASE_URL` | `https://your-vercel-app.vercel.app/api/v1` | Production |

**How to find these values:**

- **SB_URL**: From Supabase dashboard → Settings → API → Project URL
- **SB_SERVICE_ROLE_KEY**: From Supabase dashboard → Settings → API → Service Role Secret
- **NEXT_PUBLIC_API_BASE_URL**: Replace `your-vercel-app` with your actual Vercel project name

## Step 3: Deploy

1. After configuring environment variables, click "Deploy"
2. Vercel will automatically:
   - Detect the monorepo structure
   - Build the Next.js frontend
   - Build the FastAPI backend
   - Configure routing between them

## Step 4: Verify Deployment

Once deployment is complete:

1. Visit your Vercel app URL (e.g., `https://your-vercel-app.vercel.app`)
2. You should see the Luviio frontend
3. Test the signup endpoint by going to `/signup`
4. Test the API by visiting `/api/v1/` (you should see the health check response)

## Understanding the Routing

The `vercel.json` file configures how Vercel routes requests:

```json
{
  "routes": [
    {
      "src": "/api/v1/(.*)",
      "dest": "/backend/main.py"
    },
    {
      "src": "/(.*)",
      "dest": "/frontend/$1"
    }
  ]
}
```

This means:
- **Requests to `/api/v1/*`** → Routed to the FastAPI backend
- **All other requests** → Routed to the Next.js frontend

## Troubleshooting

### Issue: 404 Error on Frontend

**Cause**: The routing configuration isn't recognizing the frontend build.

**Solution**:
1. Check that the frontend build was successful in Vercel logs
2. Verify `NEXT_PUBLIC_API_BASE_URL` is set correctly
3. Clear browser cache and try again

### Issue: API Calls Returning 404

**Cause**: The backend isn't being deployed or the routing isn't working.

**Solution**:
1. Check Vercel deployment logs for Python build errors
2. Verify all environment variables are set (`SB_URL`, `SB_SERVICE_ROLE_KEY`)
3. Test the API directly: `https://your-vercel-app.vercel.app/api/v1/`
4. Check that `backend/main.py` exists and is properly formatted

### Issue: CORS Errors

**Cause**: The backend CORS configuration doesn't include the Vercel domain.

**Solution**:
1. Update `backend/main.py` to include your Vercel domain in `allow_origins`:
   ```python
   allow_origins=[
       "http://localhost:3000",
       "https://your-vercel-app.vercel.app",
       "https://luviio.in",
       "https://www.luviio.in"
   ]
   ```
2. Redeploy the backend

### Issue: Environment Variables Not Working

**Cause**: Variables not set in the correct scope.

**Solution**:
1. Go to Vercel Settings → Environment Variables
2. Ensure variables are set for "Production" scope
3. Redeploy the project after updating variables

## Local Development vs Production

### Development (Local)

```env
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

### Production (Vercel)

```env
# Set in Vercel dashboard
NEXT_PUBLIC_API_BASE_URL=https://your-vercel-app.vercel.app/api/v1
```

## File Structure for Vercel

Vercel expects this structure for monorepos:

```
luviio.in/
├── vercel.json                 # Deployment configuration
├── package.json                # Root package.json (optional but recommended)
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── requirements.txt         # Python dependencies
│   └── package.json            # Node.js metadata (for Vercel)
└── frontend/
    ├── package.json            # Next.js dependencies
    ├── next.config.js          # Next.js configuration
    └── src/                    # Next.js source code
```

## Redeploying

To redeploy after making changes:

1. Push your changes to GitHub
2. Vercel will automatically detect the changes and redeploy
3. You can also manually trigger a redeploy from the Vercel dashboard

## Custom Domain

To add a custom domain:

1. Go to Vercel dashboard → Settings → Domains
2. Add your domain (e.g., `luviio.in`)
3. Follow the DNS configuration instructions
4. Update `NEXT_PUBLIC_API_BASE_URL` to use your custom domain

## Performance Optimization

### Frontend Optimization

- Next.js automatically optimizes images and code splitting
- Vercel provides edge caching for static assets

### Backend Optimization

- FastAPI is already optimized for performance
- Consider adding database connection pooling for production
- Use Vercel's serverless functions for scalability

## Security Best Practices

1. **Never commit secrets**: Use Vercel environment variables, not `.env` files
2. **Use Service Role Key carefully**: This key has full database access
3. **Enable HTTPS**: Vercel provides free SSL certificates
4. **Validate all inputs**: Both frontend and backend should validate user input
5. **Rate limiting**: The backend includes rate limiting via `slowapi`

## Monitoring and Logs

### View Deployment Logs

1. Go to Vercel dashboard
2. Select your project
3. Click "Deployments"
4. Select the deployment to view logs

### View Runtime Logs

1. Go to Vercel dashboard
2. Select your project
3. Click "Logs"
4. View real-time logs for your application

## Next Steps

After successful deployment:

1. Test all authentication endpoints
2. Set up custom domain (optional)
3. Configure analytics and monitoring
4. Set up CI/CD pipeline for automated deployments
5. Plan database backups and disaster recovery

## Support

For issues:

1. Check Vercel documentation: https://vercel.com/docs
2. Check FastAPI documentation: https://fastapi.tiangolo.com/
3. Check Next.js documentation: https://nextjs.org/docs
4. Review deployment logs in Vercel dashboard

---

**Last Updated**: March 2026
