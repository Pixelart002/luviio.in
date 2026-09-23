import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './app/App'
import './styles/global.css'

const stripePublishableKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || import.meta.env.VITE_STRIPE_PK || import.meta.env.VITE_STRIPE_PUBLIC_KEY || import.meta.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY || import.meta.env.NEXT_PUBLIC_STRIPE_PK || import.meta.env.STRIPE_PUBLISHABLE_KEY || import.meta.env.STRIPE_PK
if (stripePublishableKey && !document.querySelector('script[src="https://js.stripe.com/v3/"]')) {
  const script = document.createElement('script')
  script.src = 'https://js.stripe.com/v3/'
  script.async = true
  document.head.appendChild(script)
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>)
