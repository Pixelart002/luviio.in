create table if not exists public.product_specifications (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id) on delete cascade,
  specification_code text not null check (specification_code = lower(specification_code) and specification_code ~ '^[a-z][a-z0-9_]*$'),
  value_text text,
  value_numeric numeric,
  unit_code text,
  position integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint product_specifications_value_chk check (value_text is not null or value_numeric is not null)
);
create index if not exists idx_product_specifications_product on public.product_specifications(product_id, position);
alter table public.product_specifications enable row level security;

create table if not exists public.product_seo (
  product_id uuid primary key references public.products(id) on delete cascade,
  title text,
  description text,
  canonical_url text,
  robots_index boolean not null default true,
  robots_follow boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint product_seo_title_length_chk check (title is null or char_length(title) between 1 and 70),
  constraint product_seo_description_length_chk check (description is null or char_length(description) between 1 and 170),
  constraint product_seo_canonical_length_chk check (canonical_url is null or char_length(canonical_url) <= 2048)
);
alter table public.product_seo enable row level security;

insert into public.product_seo(product_id, title, description)
select id, seo_title, seo_description from public.products
where seo_title is not null or seo_description is not null
on conflict (product_id) do update set title=excluded.title, description=excluded.description;

insert into public.product_specifications(product_id, specification_code, value_text, position)
select p.id, lower(regexp_replace(e.key, '[^a-zA-Z0-9]+', '_', 'g')), e.value,
       row_number() over (partition by p.id order by e.key)-1
from public.products p
cross join lateral jsonb_each_text(coalesce(p.attributes, '{}'::jsonb)) e
where jsonb_typeof(coalesce(p.attributes, '{}'::jsonb)) = 'object'
on conflict do nothing;