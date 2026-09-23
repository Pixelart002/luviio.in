# Product API Contract

## Scope

LUVIIO sells hardware. The Product API therefore models a hardware catalogue instead of copying every marketplace-specific attribute. Common hardware fields are relational; category-specific hardware properties are stored in the relational `product_specifications` table and projected as `specifications` in read responses.

Operational metadata such as SEO settings, low-stock thresholds and calculated discounts are owned by their respective services and are not accepted by the Product API.

## Canonical product fields

Stable snake_case names are used at the HTTP boundary.

| Field | Type | Create | Update | Notes |
|---|---|---:|---:|---|
| id | UUID | server | read-only | Product identifier |
| name | string | required | optional | 2-255 chars |
| slug | string | generated | optional | Lowercase unique URL slug |
| sku | string | optional | optional | Seller/inventory identifier; max 100 chars |
| category_id | UUID/null | optional | optional | Hardware category |
| description | string/null | optional | optional | Full customer-facing description |
| short_description | string/null | optional | optional | Max 500 chars |
| brand | string/null | optional | optional | Hardware brand |
| manufacturer | string/null | optional | optional | Manufacturer |
| model_number | string/null | optional | optional | Manufacturer model |
| gtin | string/null | optional | optional | External product identifier when available |
| ean | string/null | optional | optional | EAN when available |
| part_number | string/null | optional | optional | Manufacturer/supplier part number |
| key_features | string[] | optional | optional | Customer-facing hardware features |
| material | string/null | optional | optional | e.g. Stainless Steel |
| finish | string/null | optional | optional | e.g. Polished |
| color | string/null | optional | optional | Product color |
| size | string/null | optional | optional | Product size |
| dimensions | string/null | optional | optional | Product dimensions |
| warranty | string/null | optional | optional | Warranty information |
| price | decimal | required | optional | Selling price; > 0 |
| compare_price | decimal/null | optional | optional | MRP/compare-at price; must exceed price |
| stock | integer | default 0 | optional | Available stock; >= 0 |
| measurement_type | string/null | optional | optional | One selected measurement type from the DB measurement master |\n| measurement_value | decimal/null | optional | optional | Value for the selected measurement type |\n| measurement_unit | string/null | optional | optional | Unit attached to the selected measurement type; backend validates the pair |\n| image_url | string/null | optional | optional | Primary image URL |
| images | string[] | optional | optional | Up to 10 images; first is primary |
| hsn_code | string | required | optional | 4-8 numeric digits |
| gst_percentage | integer | required | optional | 0-100; provider validated |
| country_of_origin | string/null | optional | optional | Country of origin |
| is_active | boolean | default true | optional | Catalogue visibility |

## Measurement scales

The admin selects at most one product measurement type at a time. Active measurement types and their units are loaded from the database measurement master at runtime; units are not hardcoded in the frontend. The backend validates that the selected unit belongs to the selected type.

## Hardware specifications

Common fields are first-class API fields. Category-specific fields are stored in relational `product_specifications` rows and projected as `specifications` in read responses.

Examples:

- Drainage: outlet_size, installation_type, shape, grade.
- Hinges: hinge_type, load_capacity, screw_type.
- Handles/hangers: mounting_type, load_capacity.
- Pipes/fittings: diameter, connection_type, thread_type, pressure_rating.

This prevents the core products table/API from becoming a large collection of nullable Amazon-style fields.

## Tax and HSN/GST

- `hsn_code` and `gst_percentage` are required for new products.
- HSN must contain 4-8 numeric digits.
- The configured taxonomy provider is used for HSN search/lookup and selected-rate validation.
- Admin HSN lookup returns provider GST rates so the UI can auto-fill/suggest the GST rate.
- The backend validates the selected HSN/GST combination again before saving.
- Shipping tax remains separate and is calculated by the pricing engine.
- Existing legacy rows are not silently rewritten; invalid historical HSN values require product-by-product review.

## Removed from the Product API contract

These remain in the database or owning subsystem where needed, but are not Product API fields:

- SEO title/description/keywords
- canonical URL
- low-stock threshold
- calculated discount amount/percentage
- server-created timestamp

## API consistency

- Product update supports slug and SKU.
- Structured hardware fields are stored relationally without adding a generic JSON/JSONB product field.
- Public responses project structured hardware fields and category-specific relational specifications; the legacy generic `attributes` JSONB field is removed.
- HSN/GST validation remains fail-closed when taxonomy enforcement is enabled.
- Database-level HSN/GST constraints continue to protect new writes.
