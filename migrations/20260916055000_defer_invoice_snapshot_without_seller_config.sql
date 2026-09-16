begin;

-- Payment settlement must not fail solely because statutory seller/invoice
-- configuration has not been completed yet. The order/payment ledger remains
-- authoritative; invoice generation is deferred until seller configuration
-- is complete. Unexpected invoice failures still propagate.
create or replace function public.trg_create_invoice_snapshot_after_paid()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
begin
  if new.status <> 'paid' then
    return new;
  end if;

  begin
    perform public.create_invoice_snapshot_for_order(new.id);
  exception
    when raise_exception then
      if sqlerrm like 'SELLER_CONFIGURATION_INCOMPLETE:%' then
        raise warning 'Invoice snapshot deferred for paid order %: %', new.id, sqlerrm;
      else
        raise;
      end if;
  end;

  return new;
end;
$$;

commit;
