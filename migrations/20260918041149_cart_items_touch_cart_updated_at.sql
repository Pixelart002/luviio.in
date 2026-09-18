create or replace function public.touch_cart_updated_at_from_items()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $$
begin
  update public.carts
     set updated_at = now()
   where id = coalesce(new.cart_id, old.cart_id);
  return coalesce(new, old);
end;
$$;

revoke all on function public.touch_cart_updated_at_from_items() from public, anon, authenticated;
grant execute on function public.touch_cart_updated_at_from_items() to service_role;

drop trigger if exists trg_cart_items_touch_cart_updated_at on public.cart_items;

create trigger trg_cart_items_touch_cart_updated_at
after insert or update or delete on public.cart_items
for each row
execute function public.touch_cart_updated_at_from_items();
