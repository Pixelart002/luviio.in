begin;

-- jsonb_populate_record preserves an explicit JSON null instead of applying
-- the column default. Checkout intentionally sends a nullable/optional
-- reverse_charge field, so normalize it before the NOT NULL constraint is
-- checked. This also protects future service/RPC callers from the same drift.
create or replace function public.normalize_order_reverse_charge()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
begin
  new.reverse_charge := coalesce(new.reverse_charge, false);
  return new;
end;
$$;

drop trigger if exists trg_normalize_order_reverse_charge on public.orders;
create trigger trg_normalize_order_reverse_charge
before insert on public.orders
for each row
execute function public.normalize_order_reverse_charge();

revoke all on function public.normalize_order_reverse_charge() from public, anon, authenticated;
grant execute on function public.normalize_order_reverse_charge() to service_role;

commit;
