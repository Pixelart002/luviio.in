create or replace function public.touch_cart_updated_at_after_insert()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
declare
  v_cart_id uuid;
begin
  for v_cart_id in select distinct cart_id from new_rows where cart_id is not null loop
    update public.carts
       set updated_at = now()
     where id = v_cart_id;
  end loop;
  return null;
end;
$function$;

create or replace function public.touch_cart_updated_at_after_update()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
declare
  v_cart_id uuid;
begin
  for v_cart_id in
    select distinct cart_id
    from (
      select cart_id from new_rows
      union
      select cart_id from old_rows
    ) affected
    where cart_id is not null
  loop
    update public.carts
       set updated_at = now()
     where id = v_cart_id;
  end loop;
  return null;
end;
$function$;

create or replace function public.touch_cart_updated_at_after_delete()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
declare
  v_cart_id uuid;
begin
  for v_cart_id in select distinct cart_id from old_rows where cart_id is not null loop
    update public.carts
       set updated_at = now()
     where id = v_cart_id;
  end loop;
  return null;
end;
$function$;

revoke all on function public.touch_cart_updated_at_after_insert() from public, anon, authenticated;
revoke all on function public.touch_cart_updated_at_after_update() from public, anon, authenticated;
revoke all on function public.touch_cart_updated_at_after_delete() from public, anon, authenticated;
grant execute on function public.touch_cart_updated_at_after_insert() to service_role;
grant execute on function public.touch_cart_updated_at_after_update() to service_role;
grant execute on function public.touch_cart_updated_at_after_delete() to service_role;

drop trigger if exists trg_cart_items_touch_cart_updated_at on public.cart_items;
drop trigger if exists trg_cart_items_touch_cart_updated_at_insert on public.cart_items;
drop trigger if exists trg_cart_items_touch_cart_updated_at_update on public.cart_items;
drop trigger if exists trg_cart_items_touch_cart_updated_at_delete on public.cart_items;

create trigger trg_cart_items_touch_cart_updated_at_insert
after insert on public.cart_items
referencing new table as new_rows
for each statement
execute function public.touch_cart_updated_at_after_insert();

create trigger trg_cart_items_touch_cart_updated_at_update
after update on public.cart_items
referencing old table as old_rows new table as new_rows
for each statement
execute function public.touch_cart_updated_at_after_update();

create trigger trg_cart_items_touch_cart_updated_at_delete
after delete on public.cart_items
referencing old table as old_rows
for each statement
execute function public.touch_cart_updated_at_after_delete();
