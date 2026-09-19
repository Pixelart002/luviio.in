# Product API Contract

## Canonical product fields

The Products domain uses stable snake_case field names at the HTTP boundary. Database and API names intentionally remain aligned so cart, checkout, orders and invoices do not require compatibility aliases.

| Field | Type | Create | Update | Notes |
|---|---|---:|---:|---|
| id | UUID | server | read-only | Product identifier |
| name | string | required | optional | 2-255 chars |
| slug | string | generated | optional | lowercase URL slug; backend enforces uniqueness |
| sku | string | optional | optional | Unique when supplied; max 100 chars |
| category_id | UUID/null | optional | optional | FK to categories |
| description | string/null | optional | optional | Full product description |
| short_description | string/null | optional | optional | Max 500 chars |
| price | decimal | required | optional | Selling price; must be > 0 |
| compare_price | decimal/null | optional | optional | Canonical API name retained for compatibility; UI label is MRP/Compare price. Must be greater than price |
| stock | integer | default 0 | optional | Must be >= 0 |
| low_stock_threshold | integer | default 10 | optional | Must be >= 0 |
| weight_grams | integer/null | optional | optional | Non-negative product weight |
| image_url | string/null | optional | optional | Primary image URL |
| images | string[] | optional | optional | API projection of product_images; max 10; first image is primary |
| attributes | object | optional | optional | Flexible product specifications |
| hsn_code | string | required | optional | 4-8 numeric digits; provider validation required |
| gst_percentage | integer | required | optional | 0-100; provider must confirm the selected rate |
| country_of_origin | string/null | optional | optional | 2-100 chars |
| seo_title | string/null | optional | optional | Max 70 chars |
| seo_description | string/null | optional | optional | Max 170 chars |
| seo_keywords | string/null | optional | optional | Max 500 chars |
| canonical_url | string/null | optional | optional | Max 2048 chars |
| is_active | boolean | default true | optional | Controls catalogue visibility |
| created_at | timestamp | server | read-only | Server timestamp |
| discount_amount | decimal | server | read-only | Generated from price/compare_price |
| discount_percentage | integer | server | read-only | Generated from price/compare_price |

## Tax rules

- Product GST is product-level, not a single global product tax field.
- hsn_code and gst_percentage are required for new products.
- HSN must be numeric and 4-8 digits at the API boundary.
- The configured HSN/GST provider validates the selected HSN/rate before create/update.
- Shipping tax remains calculated separately by the pricing engine.
- Existing legacy rows are not silently rewritten; invalid historical HSN values require product-by-product review.

The GST portal supports HSN lookup by trade/technical description and HSN code, and its current HSN guidance limits HSN input to a maximum of eight digits.

## API consistency fixes

- Product update now accepts slug and sku, matching the service logic.
- Product list now returns the fields required by the admin editor instead of omitting SKU, category ID, HSN, GST, SEO and inventory metadata.
- Database defaults for HSN/GST were removed so invalid demo defaults cannot silently populate new products.
- Database now enforces non-null HSN/GST and a 0-100 GST range for new writes.
- Database now rejects non-numeric HSN values for new writes while legacy invalid rows remain untouched.
- SKU uniqueness is enforced at database level when SKU is supplied.
