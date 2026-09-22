alter table public.products
  add column if not exists seo_title text,
  add column if not exists seo_description text,
  add column if not exists seo_keywords text,
  add column if not exists canonical_url text;

alter table public.products
  add constraint products_seo_title_length_chk check (seo_title is null or char_length(seo_title) between 1 and 70),
  add constraint products_seo_description_length_chk check (seo_description is null or char_length(seo_description) between 1 and 170),
  add constraint products_seo_keywords_length_chk check (seo_keywords is null or char_length(seo_keywords) <= 500),
  add constraint products_canonical_url_length_chk check (canonical_url is null or char_length(canonical_url) <= 2048);
