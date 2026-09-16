begin;

-- Persist tax-document context at invoice creation time. These fields are
-- copied from the immutable order snapshot and are protected from later edits.
alter table public.orders
  add column if not exists reverse_charge boolean not null default false;

alter table public.invoices
  add column if not exists place_of_supply_state_code text,
  add column if not exists reverse_charge boolean not null default false;

-- Backfill existing invoices before installing the new immutability guard.
update public.invoices i
set
  place_of_supply_state_code = o.place_of_supply_state_code,
  reverse_charge = coalesce(o.reverse_charge, false)
from public.orders o
where o.id = i.order_id;

create or replace function public.snapshot_invoice_tax_context()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_pos_code text;
  v_reverse_charge boolean;
begin
  select place_of_supply_state_code, coalesce(reverse_charge, false)
    into v_pos_code, v_reverse_charge
  from public.orders
  where id = new.order_id;

  if not found then
    raise exception 'INVOICE_ORDER_NOT_FOUND:%', new.order_id;
  end if;

  new.place_of_supply_state_code := v_pos_code;
  new.reverse_charge := v_reverse_charge;
  return new;
end;
$$;

drop trigger if exists trg_snapshot_invoice_tax_context on public.invoices;
create trigger trg_snapshot_invoice_tax_context
before insert on public.invoices
for each row execute function public.snapshot_invoice_tax_context();

create or replace function public.prevent_invoice_tax_context_mutation()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
begin
  if new.place_of_supply_state_code is distinct from old.place_of_supply_state_code
     or new.reverse_charge is distinct from old.reverse_charge then
    raise exception 'INVOICE_TAX_CONTEXT_IMMUTABLE';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_prevent_invoice_tax_context_mutation on public.invoices;
create trigger trg_prevent_invoice_tax_context_mutation
before update on public.invoices
for each row execute function public.prevent_invoice_tax_context_mutation();

commit;
