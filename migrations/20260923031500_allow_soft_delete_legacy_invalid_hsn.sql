alter table public.products
  drop constraint if exists products_hsn_code_format_chk;

alter table public.products
  add constraint products_hsn_code_format_chk
  check (
    not is_active
    or hsn_code is null
    or hsn_code ~ '^[0-9]{4,8}$'
  ) not valid;
