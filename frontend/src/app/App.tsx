import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, Download, Minus, Plus, ShieldCheck, Truck, Headphones, PackageCheck, Trash2 } from 'lucide-react'
import { authApi, cartApi, catalogApi, ordersApi, paymentsApi, userApi, type Address, type ApiCategory, type ApiProduct, type Cart, type Order } from '../api/client'
import { SiteHeader } from '../components/SiteHeader'
import { ProductCard } from '../components/ProductCard'
import type { Product } from '../types'

const money = (value: unknown) => {
  const amount = Number(value ?? 0)
  return Number.isFinite(amount) ? `₹${amount.toLocaleString('en-IN')}` : '₹0'
}

const toProduct = (p: ApiProduct): Product => ({
  ...p,
  price: Number(p.selling_price ?? p.price ?? 0),
  image: p.images?.[0] || p.image_url || undefined,
  category: p.category_name ?? p.category,
  description: p.short_description ?? p.description,
})

const addressLine1 = (address: Address) => address.line1 || address.address_line1 || ''
const addressLine2 = (address: Address) => address.line2 || address.address_line2 || ''
const readableError = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.'
const ErrorState = ({ message }: { message: string }) => <div className="error-state" role="alert">{message}</div>

function emitCartChanged() {
  window.dispatchEvent(new Event('luviio:cart-changed'))
}

function Home() {
  const [products, setProducts] = useState<Product[]>([])
  const [categories, setCategories] = useState<ApiCategory[]>([])
  const [error, setError] = useState('')
  const [adding, setAdding] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([catalogApi.products('page_size=4'), catalogApi.categories()])
      .then(([p, c]) => {
        if (!active) return
        setProducts(p.items.map(toProduct))
        setCategories(c)
      })
      .catch(e => active && setError(readableError(e)))
    return () => { active = false }
  }, [])

  const add = async (id: string) => {
    setAdding(id)
    try { await cartApi.add(id); emitCartChanged() } catch (e) { setError(readableError(e)) } finally { setAdding(null) }
  }

  return <>
    <section className="hero">
      <div className="hero-copy">
        <p className="eyebrow light">The hardware store, made easier</p>
        <h1>Build better.<br/><em>Fix faster.</em></h1>
        <p className="hero-text">Reliable plumbing, sanitation and hardware supplies for homes, pros and every project in between.</p>
        <div className="hero-actions">
          <Link className="button button-light" to="/shop">Explore products <ArrowRight size={17}/></Link>
          <Link className="text-link light" to="/shop?category=plumbing">Shop plumbing <ArrowRight size={15}/></Link>
        </div>
      </div>
      <div className="hero-art" aria-hidden="true">
        <div className="hero-shape shape-one"/><div className="hero-shape shape-two"/>
        <span className="hero-label">01 / 03<br/><b>Built for every fix</b></span>
      </div>
    </section>

    <section className="trust-row">
      <div><Truck/><span><b>Fast delivery</b><small>Across India</small></span></div>
      <div><ShieldCheck/><span><b>Genuine products</b><small>Quality assured</small></span></div>
      <div><Headphones/><span><b>Expert support</b><small>Here when you need us</small></span></div>
      <div><PackageCheck/><span><b>Bulk pricing</b><small>For every trade</small></span></div>
    </section>

    <section className="section">
      <div className="section-heading"><div><p className="eyebrow">Shop by need</p><h2>Everything for the job.</h2></div><Link className="text-link" to="/shop">View all <ArrowRight size={15}/></Link></div>
      {error && <ErrorState message={error}/>}
      <div className="category-grid">
        {categories.slice(0, 4).map((c, i) => <Link to={`/shop?category=${encodeURIComponent(c.slug || c.name)}`} className={`category-card category-${i + 1}`} key={c.id}><span>0{i + 1}</span><h3>{c.name}</h3><ArrowRight size={18}/></Link>)}
      </div>
    </section>

    <section className="section featured">
      <div className="section-heading"><div><p className="eyebrow">Popular picks</p><h2>Good gear, ready to go.</h2></div><Link className="text-link" to="/shop">See catalog <ArrowRight size={15}/></Link></div>
      <div className="product-grid">{products.map(p => <ProductCard key={p.id} product={p} onAdd={add} adding={adding === p.id}/>)}</div>
    </section>
  </>
}

function Shop() {
  const [params, setParams] = useSearchParams()
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const search = params.get('search') || ''
  const category = params.get('category') || ''
  const [query, setQuery] = useState(search)

  useEffect(() => { setQuery(search) }, [search])

  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    catalogApi.products(new URLSearchParams({ page_size: '40', ...(search && { search }), ...(category && { category }) }).toString())
      .then(p => active && setProducts(p.items.map(toProduct)))
      .catch(e => { if (active) { setProducts([]); setError(readableError(e)) } })
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [search, category])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const next = new URLSearchParams(params)
    query.trim() ? next.set('search', query.trim()) : next.delete('search')
    setParams(next)
  }

  return <section className="shop-page section">
    <div className="shop-header">
      <div><p className="eyebrow">Catalog / {category || 'All products'}</p><h1>{search ? `Results for “${search}”` : 'Shop all hardware'}</h1><p className="muted">Live products, prices and availability from the LUVIIO catalog.</p></div>
      <form className="catalog-search" onSubmit={submit}><input aria-label="Search catalog" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search products"/><button className="button button-dark" type="submit">Search</button></form>
    </div>
    {loading ? <div className="loading" aria-live="polite">Loading the catalog…</div> : error ? <ErrorState message={error}/> : products.length ? <div className="product-grid">{products.map(p => <ProductCard key={p.id} product={p} onAdd={async id => { try { await cartApi.add(id); emitCartChanged() } catch (e) { setError(readableError(e)) } }}/>)}</div> : <div className="empty-state large">No products found. Try another search or category.</div>}
  </section>
}

function ProductDetail() {
  const { slug = '' } = useParams()
  const [product, setProduct] = useState<Product | null>(null)
  const [error, setError] = useState('')
  const [added, setAdded] = useState(false)
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    let active = true
    catalogApi.product(slug).then(p => active && setProduct(toProduct(p))).catch(e => active && setError(readableError(e)))
    return () => { active = false }
  }, [slug])

  if (error) return <section className="placeholder section"><ErrorState message={error}/><Link className="button button-dark" to="/shop">Back to catalog</Link></section>
  if (!product) return <section className="placeholder section"><div className="loading">Loading product…</div></section>

  const add = async () => {
    setAdding(true)
    try { await cartApi.add(product.id); setAdded(true); emitCartChanged() } catch (e) { setError(readableError(e)) } finally { setAdding(false) }
  }

  return <section className="product-detail section">
    <Link className="text-link" to="/shop"><ArrowLeft size={15}/> Back to catalog</Link>
    <div className="detail-grid">
      <div className="detail-image">{product.image ? <img src={product.image} alt={product.name}/> : <span>{product.category?.slice(0, 1) || 'L'}</span>}</div>
      <div>
        <p className="eyebrow">{product.category || 'Hardware'}</p>
        <h1>{product.name}</h1>
        <p className="detail-price">{money(product.price)}</p>
        {product.compare_price && Number(product.compare_price) > product.price && <p className="compare-price">{money(product.compare_price)}</p>}
        <p className="muted">{product.description || 'Reliable hardware for professional and home projects.'}</p>
        <p className="stock">{product.stock_status || 'Availability verified at checkout'}</p>
        <button className="button button-dark" disabled={adding} onClick={add}>{added ? 'Added to cart' : adding ? 'Adding…' : 'Add to cart'} <Plus size={17}/></button>
        {error && <ErrorState message={error}/>}
      </div>
    </div>
  </section>
}

function CartPage() {
  const [cart, setCart] = useState<Cart | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    cartApi.get().then(setCart).catch(e => setError(readableError(e))).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const update = async (id: string, quantity: number) => {
    if (quantity < 1) return
    try { setCart(await cartApi.update(id, quantity)); emitCartChanged() } catch (e) { setError(readableError(e)) }
  }
  const remove = async (id: string) => {
    try { setCart(await cartApi.remove(id)); emitCartChanged() } catch (e) { setError(readableError(e)) }
  }

  if (loading) return <section className="section"><div className="loading">Loading your cart…</div></section>
  if (error) return <section className="placeholder section"><ErrorState message={`${error}. Please sign in to view your cart.`}/><Link className="button button-dark" to="/account">Sign in</Link></section>

  return <section className="cart-page section">
    <p className="eyebrow">Your basket</p><h1>Cart</h1>
    {!cart?.items?.length ? <div className="empty-state large">Your cart is empty. <Link to="/shop">Browse products</Link></div> :
      <div className="cart-list">
        {cart.items.map(item => <div className="cart-line" key={item.product_id}>
          <div className="cart-product">{item.product?.image_url && <img src={item.product.image_url} alt=""/>}<span>{item.product?.name || item.product_id}</span></div>
          <div className="quantity"><button aria-label="Decrease quantity" disabled={item.quantity <= 1} onClick={() => update(item.product_id, item.quantity - 1)}><Minus size={15}/></button><span>{item.quantity}</span><button aria-label="Increase quantity" onClick={() => update(item.product_id, item.quantity + 1)}><Plus size={15}/></button></div>
          <strong>{money(item.total ?? Number(item.unit_price ?? 0) * item.quantity)}</strong>
          <button aria-label={`Remove ${item.product?.name || 'item'}`} onClick={() => remove(item.product_id)}><Trash2 size={17}/></button>
        </div>)}
        <div className="cart-total"><span>Total</span><strong>{money(cart.total ?? cart.subtotal)}</strong></div>
        <Link className="button button-dark" to="/checkout">Continue to checkout <ArrowRight size={17}/></Link>
      </div>}
  </section>
}

function AddressForm({ onSaved }: { onSaved: (address: Address) => void }) {
  const [form, setForm] = useState({ full_name: '', phone: '', email: '', line1: '', line2: '', city: '', state: '', postal_code: '', country: 'IN', is_default: false })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setSaving(true); setError('')
    try { onSaved(await userApi.addAddress(form)) } catch (err) { setError(readableError(err)) } finally { setSaving(false) }
  }

  return <form className="address-form" onSubmit={submit}>
    <div className="form-grid">
      <label>Recipient name<input required value={form.full_name} onChange={e => setForm({...form, full_name: e.target.value})}/></label>
      <label>Phone<input required inputMode="tel" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})}/></label>
      <label>Email<input required type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})}/></label>
      <label>Address line 1<input required value={form.line1} onChange={e => setForm({...form, line1: e.target.value})}/></label>
      <label>Address line 2<input value={form.line2} onChange={e => setForm({...form, line2: e.target.value})}/></label>
      <label>City<input required value={form.city} onChange={e => setForm({...form, city: e.target.value})}/></label>
      <label>State<input required value={form.state} onChange={e => setForm({...form, state: e.target.value})}/></label>
      <label>PIN / Postal code<input required inputMode="numeric" value={form.postal_code} onChange={e => setForm({...form, postal_code: e.target.value})}/></label>
    </div>
    <label className="checkbox"><input type="checkbox" checked={form.is_default} onChange={e => setForm({...form, is_default: e.target.checked})}/> Make this my default address</label>
    {error && <ErrorState message={error}/>}
    <button className="button button-dark" disabled={saving}>{saving ? 'Saving…' : 'Save address'}</button>
  </form>
}

function Checkout() {
  const navigate = useNavigate()
  const [addresses, setAddresses] = useState<Address[]>([])
  const [selected, setSelected] = useState('')
  const [showAddressForm, setShowAddressForm] = useState(false)
  const [coupon, setCoupon] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [payment, setPayment] = useState<{ clientSecret: string; paymentIntentId: string; orderNumber?: string } | null>(null)
  const [cardReady, setCardReady] = useState(false)
  const [cardError, setCardError] = useState('')
  const cardElementRef = useRef<StripeCardElement | null>(null)

  const loadAddresses = useCallback(() => userApi.addresses().then(items => { setAddresses(items); setSelected(current => current || items.find(item => item.is_default)?.id || items[0]?.id || '') }).catch(e => setMessage(readableError(e))), [])
  useEffect(() => { loadAddresses() }, [loadAddresses])

  useEffect(() => {
    if (!payment?.clientSecret || !window.Stripe || !import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY) return
    const stripe = window.Stripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY)
    const elements = stripe.elements()
    const card = elements.create('card', { hidePostalCode: true })
    cardElementRef.current = card
    card.mount('#luviio-card-element')
    card.on('ready', () => setCardReady(true))
    card.on('change', event => setCardError(event.error?.message || ''))
    return () => { card.destroy(); cardElementRef.current = null; setCardReady(false) }
  }, [payment])

  const addAddress = (address: Address) => {
    setAddresses(items => [address, ...items])
    setSelected(address.id)
    setShowAddressForm(false)
  }

  const createPayment = async () => {
    if (!selected) { setMessage('Select or add a delivery address first.'); return }
    if (!import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || !window.Stripe) { setMessage('Online payment is not configured in this frontend deployment. Use COD or configure the Stripe publishable key.'); return }
    setSubmitting(true); setMessage(''); setCardError('')
    try {
      const result = await paymentsApi.createIntent({ shipping_address_id: selected, idempotency_key: crypto.randomUUID(), coupon_code: coupon.trim() || undefined, provider_key: 'stripe' })
      if (!result.client_secret || !result.payment_intent_id) throw new Error('Payment session was not returned by the backend.')
      setPayment({ clientSecret: result.client_secret, paymentIntentId: result.payment_intent_id, orderNumber: result.order_number })
    } catch (e) { setMessage(readableError(e)) } finally { setSubmitting(false) }
  }

  const confirmPayment = async () => {
    if (!payment || !window.Stripe || !import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY) return
    const stripe = window.Stripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY)
    setSubmitting(true)
    try {
      const card = cardElementRef.current
      if (!card) throw new Error('Payment card form is not ready.')
      const result = await stripe.confirmCardPayment(payment.clientSecret, { payment_method: { card } })
      if (result.error) {
        await paymentsApi.notifyFailed(payment.paymentIntentId, result.error.message || 'Payment failed', 'stripe').catch(() => undefined)
        throw new Error(result.error.message || 'Payment failed.')
      }
      const confirmed = await paymentsApi.confirm(payment.paymentIntentId, 'stripe')
      await cartApi.clear().catch(() => undefined)
      emitCartChanged()
      navigate(`/orders/${encodeURIComponent(confirmed.order_number || payment.orderNumber || '')}`)
    } catch (e) { setMessage(readableError(e)) } finally { setSubmitting(false) }
  }

  const placeCod = async () => {
    if (!selected) { setMessage('Select or add a delivery address first.'); return }
    setSubmitting(true); setMessage('')
    try {
      const result = await ordersApi.cod(selected, crypto.randomUUID(), coupon.trim() || undefined)
      await cartApi.clear().catch(() => undefined)
      emitCartChanged()
      navigate(`/orders/${encodeURIComponent(result.order_number || '')}`)
    } catch (e) { setMessage(readableError(e)) } finally { setSubmitting(false) }
  }

  return <section className="checkout-page section">
    <p className="eyebrow">Secure checkout</p><h1>Deliver it right.</h1>
    <p className="muted">Shipping, taxes, inventory and totals are confirmed by the LUVIIO backend.</p>
    <div className="checkout-panel">
      <div className="panel-heading"><h2>Delivery address</h2><button className="button button-outline" onClick={() => setShowAddressForm(v => !v)}>{showAddressForm ? 'Close' : 'Add address'}</button></div>
      {showAddressForm && <AddressForm onSaved={addAddress}/>}
      {addresses.length ? <div className="address-list">{addresses.map(address => <label className="address-option" key={address.id}><input type="radio" name="address" checked={selected === address.id} onChange={() => setSelected(address.id)}/><span><strong>{address.full_name || 'Delivery address'}</strong><br/>{addressLine1(address)}{addressLine2(address) ? `, ${addressLine2(address)}` : ''}<br/>{address.city}, {address.state} {address.postal_code}</span></label>)}</div> : !showAddressForm && <p className="muted">No saved addresses. Add a delivery address to continue.</p>}
      <label className="coupon-field">Coupon code<input value={coupon} onChange={e => setCoupon(e.target.value)} placeholder="Optional"/></label>
      {!payment ? <div className="checkout-actions"><button className="button button-dark" disabled={submitting || !selected} onClick={createPayment}>{submitting ? 'Preparing payment…' : 'Pay online'} <ArrowRight size={17}/></button><button className="button button-outline" disabled={submitting || !selected} onClick={placeCod}>Cash on delivery</button></div> :
        <div className="payment-box"><h2>Complete payment</h2><p className="muted">Enter your card details. Your payment is processed by Stripe.</p><div id="luviio-card-element" className="card-element"/>{cardError && <ErrorState message={cardError}/>}<button className="button button-dark" disabled={submitting || !cardReady || !!cardError} onClick={confirmPayment}>{submitting ? 'Processing…' : 'Confirm payment'} <Check size={17}/></button></div>}
      {message && <ErrorState message={message}/>}
    </div>
  </section>
}

function Orders() {
  const [orders, setOrders] = useState<Order[]>([])
  const [error, setError] = useState('')
  useEffect(() => { ordersApi.mine().then(response => setOrders(response.items || [])).catch(e => setError(readableError(e))) }, [])
  return <section className="orders-page section"><p className="eyebrow">Account / Orders</p><h1>Your orders.</h1>{error ? <ErrorState message={`${error}. Please sign in first.`}/> : orders.length ? <div className="order-list">{orders.map(order => <Link className="order-card" to={`/orders/${encodeURIComponent(order.order_number || '')}`} key={order.order_number || order.id}><div><strong>{order.order_number || order.id}</strong><p className="muted">{order.created_at ? new Date(order.created_at).toLocaleDateString('en-IN') : 'Recent order'}</p></div><span className="status-pill">{order.status || 'Processing'}</span><strong>{money(order.total)}</strong></Link>)}</div> : <div className="empty-state large">No orders yet. <Link to="/shop">Start shopping</Link></div>}</section>
}

function OrderDetail() {
  const { orderNumber = '' } = useParams()
  const [order, setOrder] = useState<Order | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  useEffect(() => { ordersApi.detail(orderNumber).then(setOrder).catch(e => setError(readableError(e))) }, [orderNumber])

  const invoice = async () => {
    setBusy(true)
    try {
      const blob = await ordersApi.invoice(orderNumber)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `Luviio-Invoice-${orderNumber}.pdf`; anchor.click(); URL.revokeObjectURL(url)
    } catch (e) { setNotice(readableError(e)) } finally { setBusy(false) }
  }

  const cancel = async () => {
    if (!window.confirm('Cancel this order?')) return
    setBusy(true)
    try { setOrder(await ordersApi.cancel(orderNumber)); setNotice('Order cancellation requested successfully.') } catch (e) { setNotice(readableError(e)) } finally { setBusy(false) }
  }

  if (error) return <section className="placeholder section"><ErrorState message={error}/><Link className="button button-dark" to="/orders">Back to orders</Link></section>
  if (!order) return <section className="section"><div className="loading">Loading order…</div></section>

  return <section className="order-detail section">
    <Link className="text-link" to="/orders"><ArrowLeft size={15}/> Orders</Link>
    <div className="order-detail-header"><div><p className="eyebrow">Order</p><h1>{order.order_number}</h1><span className="status-pill">{order.status || 'Processing'}</span></div><div className="order-actions"><button className="button button-outline" onClick={invoice} disabled={busy}><Download size={16}/> Invoice</button>{!['cancelled', 'delivered', 'completed'].includes(String(order.status).toLowerCase()) && <button className="button button-outline danger" onClick={cancel} disabled={busy}>Cancel order</button>}</div></div>
    <div className="order-detail-grid"><div className="order-items">{(order.items || []).map((item, i) => <div className="order-item" key={i}><span><strong>{item.product_name || 'Product'}</strong><small>Qty {item.quantity || 0}</small></span><strong>{money(item.total)}</strong></div>)}</div><aside className="order-summary"><span>Subtotal <strong>{money(order.subtotal)}</strong></span><span>Tax <strong>{money(order.tax)}</strong></span><span>Shipping <strong>{money(order.shipping)}</strong></span><span>Discount <strong>-{money(order.discount)}</strong></span><hr/><span>Total <strong>{money(order.total)}</strong></span></aside></div>
    {notice && <p className="form-message">{notice}</p>}
  </section>
}

function Account() {
  const navigate = useNavigate()
  const [session, setSession] = useState<{ authenticated: boolean; email?: string } | null>(null)
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [message, setMessage] = useState(''); const [loading, setLoading] = useState(true)
  useEffect(() => { authApi.session().then(setSession).catch(() => setSession({ authenticated: false })).finally(() => setLoading(false)) }, [])
  const submit = async (e: FormEvent) => { e.preventDefault(); setMessage(''); try { const result = await authApi.login({ email, password }); setSession({ authenticated: true, email: result.email || email }); setMessage('Signed in successfully.') } catch (e) { setMessage(readableError(e)) } }
  const logout = async () => { try { await authApi.logout() } finally { setSession({ authenticated: false }); navigate('/account') } }
  if (loading) return <section className="section"><div className="loading">Checking your session…</div></section>
  if (session?.authenticated) return <section className="placeholder section"><p className="eyebrow">Account</p><h1>Welcome back.</h1><p>{session.email}</p><div className="account-links"><Link className="button button-dark" to="/orders">View orders</Link><Link className="button button-outline" to="/checkout">Manage addresses</Link><button className="button button-outline" onClick={logout}>Sign out</button></div></section>
  return <section className="auth-page section"><p className="eyebrow">LUVIIO account</p><h1>Sign in to continue.</h1><form className="auth-form" onSubmit={submit}><label>Email<input required autoComplete="email" type="email" value={email} onChange={e => setEmail(e.target.value)}/></label><label>Password<input required autoComplete="current-password" type="password" value={password} onChange={e => setPassword(e.target.value)}/></label><button className="button button-dark" type="submit">Sign in <ArrowRight size={17}/></button>{message && <ErrorState message={message}/>}<p className="muted">New to Luviio? <Link to="/register">Create an account</Link></p></form></section>
}

function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ full_name: '', email: '', password: '' }); const [message, setMessage] = useState(''); const [loading, setLoading] = useState(false)
  const submit = async (event: FormEvent) => { event.preventDefault(); setLoading(true); setMessage(''); try { await authApi.register(form); navigate('/account', { state: { registered: true } }) } catch (e) { setMessage(readableError(e)) } finally { setLoading(false) } }
  return <section className="auth-page section"><p className="eyebrow">LUVIIO account</p><h1>Create your account.</h1><form className="auth-form" onSubmit={submit}><label>Full name<input required minLength={2} autoComplete="name" value={form.full_name} onChange={e => setForm({...form, full_name:e.target.value})}/></label><label>Email<input required autoComplete="email" type="email" value={form.email} onChange={e => setForm({...form, email:e.target.value})}/></label><label>Password<input required minLength={8} autoComplete="new-password" type="password" value={form.password} onChange={e => setForm({...form, password:e.target.value})}/></label><button className="button button-dark" disabled={loading}>{loading ? 'Creating…' : 'Create account'} <ArrowRight size={17}/></button>{message && <ErrorState message={message}/>}<p className="muted">Already have an account? <Link to="/account">Sign in</Link></p></form></section>
}

function Placeholder({ title, copy }: { title: string; copy: string }) { return <section className="placeholder section"><p className="eyebrow">Luviio</p><h1>{title}</h1><p>{copy}</p><Link className="button button-dark" to="/shop">Continue shopping <ArrowRight size={17}/></Link></section> }

export default function App() {
  return <>
    <SiteHeader/>
    <main>
      <Routes>
        <Route path="/" element={<Home/>}/>
        <Route path="/shop" element={<Shop/>}/>
        <Route path="/product/:slug" element={<ProductDetail/>}/>
        <Route path="/cart" element={<CartPage/>}/>
        <Route path="/checkout" element={<Checkout/>}/>
        <Route path="/orders" element={<Orders/>}/>
        <Route path="/orders/:orderNumber" element={<OrderDetail/>}/>
        <Route path="/account" element={<Account/>}/>
        <Route path="/register" element={<Register/>}/>
        <Route path="*" element={<Placeholder title="Page not found" copy="The page you’re looking for doesn’t exist."/>}/>
      </Routes>
    </main>
    <footer><div className="brand"><span className="brand-mark">L</span><span>luviio<span className="brand-dot">.</span></span></div><p>Hardware that works as hard as you do.</p><span>© 2026 Luviio.in</span></footer>
  </>
}
