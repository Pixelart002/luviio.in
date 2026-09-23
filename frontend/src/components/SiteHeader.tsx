import { FormEvent, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Search, ShoppingCart, UserRound, Menu, X, ChevronDown } from 'lucide-react'
import { cartApi } from '../api/client'

export function SiteHeader() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cartCount, setCartCount] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()

  const refreshCart = () => {
    cartApi.get().then(cart => setCartCount(Number(cart.item_count ?? cart.items?.reduce((sum, item) => sum + item.quantity, 0) ?? 0))).catch(() => setCartCount(0))
  }

  useEffect(() => {
    refreshCart()
    const handler = () => refreshCart()
    window.addEventListener('luviio:cart-changed', handler)
    return () => window.removeEventListener('luviio:cart-changed', handler)
  }, [location.pathname])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const value = query.trim()
    navigate(value ? `/shop?search=${encodeURIComponent(value)}` : '/shop')
    setOpen(false)
  }

  return <>
    <div className="announcement">Trade pricing available on bulk orders <span>·</span> Free delivery above ₹1,499</div>
    <header className="header">
      <Link to="/" className="brand" aria-label="Luviio home"><span className="brand-mark">L</span><span>luviio<span className="brand-dot">.</span></span></Link>
      <form className="search" onSubmit={submit}>
        <Search size={18}/><input aria-label="Search products" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search pipes, taps, tools..."/><kbd>⌘ K</kbd>
      </form>
      <nav className="desktop-nav" aria-label="Primary navigation"><Link to="/shop">Shop</Link><Link to="/shop?category=plumbing">Plumbing</Link><Link to="/shop?category=sanitation">Sanitation</Link><Link to="/account">Account</Link></nav>
      <div className="header-actions">
        <Link to="/account" aria-label="Account"><UserRound size={20}/></Link>
        <Link to="/cart" aria-label={`Cart, ${cartCount} items`} className="cart-link"><ShoppingCart size={20}/>{cartCount > 0 && <span>{cartCount > 99 ? '99+' : cartCount}</span>}</Link>
        <button className="mobile-menu" type="button" onClick={() => setOpen(v => !v)} aria-expanded={open} aria-label={open ? 'Close menu' : 'Open menu'}>{open ? <X/> : <Menu/>}</button>
      </div>
    </header>
    {open && <div className="mobile-nav">
      <Link to="/shop" onClick={() => setOpen(false)}>Shop <ChevronDown size={16}/></Link>
      <Link to="/shop?category=plumbing" onClick={() => setOpen(false)}>Plumbing</Link>
      <Link to="/shop?category=sanitation" onClick={() => setOpen(false)}>Sanitation</Link>
      <Link to="/account" onClick={() => setOpen(false)}>Account</Link>
    </div>}
  </>
}
