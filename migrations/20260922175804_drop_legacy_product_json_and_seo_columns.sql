alter table public.products
  drop column if exists attributes,
  drop column if exists seo_title,
  drop column if exists seo_description,
  drop column if exists seo_keywords,
  drop column if exists canonical_url;