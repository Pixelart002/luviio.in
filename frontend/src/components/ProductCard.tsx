import { Link } from 'react-router-dom'
import { Plus, ArrowUpRight } from 'lucide-react'
import type { Product } from '../types'

export function ProductCard({ product, onAdd, adding = false }: { product: Product; onAdd?: (id: string) => void | Promise<void>; adding?: boolean }) {
  return <article className="product-card">
    <Link to={`/product/${product.slug}`} className="product-image" aria-label={product.name}>
      {product.image ? <img loading="lazy" src={product.image} alt={product.name}/> : <span className="image-placeholder">{product.category?.slice(0, 1) || 'L'}</span>}
      <span className="image-arrow"><ArrowUpRight size={16}/></span>
    </Link>
    <div className="product-info">
      <p className="eyebrow">{product.category || 'Hardware'}</p>
      <Link to={`/product/${product.slug}`}><h3>{product.name}</h3></Link>
      <div className="product-bottom">
        <strong>₹{product.price.toLocaleString('en-IN')}</strong>
        <button type="button" disabled={adding} onClick={() => onAdd?.(product.id)} aria-label={`Add ${product.name} to cart`}>{adding ? '…' : <Plus size={18}/>}</button>
      </div>
    </div>
  </article>
}
