begin;

-- Harden the order state machine at the database boundary as well as in the API.
-- COD:     pending -> processing -> paid -> shipped -> delivered
-- Online:  pending -> paid -> processing -> shipped -> delivered
create or replace function public.rpc_admin_update_order_status(
  p_order_id uuid,
  p_new_status text,
  p_tracking_number text default null,
  p_notes text default null
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $function$
declare
  v_order public.orders%rowtype;
  v_current_status text;
  v_new_status text := lower(trim(coalesce(p_new_status, '')));
  v_order_payment_method text;
  v_payment_method text;
  v_payment_status text;
  v_provider_payment_id text;
  v_settlement text;
  v_is_cod boolean;
begin
  select *
    into v_order
    from public.orders
   where id = p_order_id
   for update;

  if not found then
    return null;
  end if;

  v_current_status := lower(trim(coalesce(v_order.status, '')));
  v_order_payment_method := lower(trim(coalesce(v_order.payment_method, '')));

  select lower(trim(coalesce(payment_method, ''))),
         lower(trim(coalesce(status, ''))),
         nullif(trim(provider_payment_id), '')
    into v_payment_method, v_payment_status, v_provider_payment_id
    from public.payments
   where order_id = p_order_id
   order by updated_at desc nulls last, created_at desc nulls last
   limit 1
   for update;

  v_is_cod := coalesce(v_order_payment_method, v_payment_method) in ('cod', 'cash_on_delivery');

  -- Explicit transition hierarchy.
  if v_current_status = 'pending' then
    if v_new_status not in ('paid', 'processing', 'cancelled') then
      raise exception 'Invalid order transition: pending -> %', v_new_status;
    end if;
    if v_new_status = 'processing' and not v_is_cod then
      raise exception 'Only COD orders can move from pending to processing.';
    end if;
    if v_new_status = 'paid' and v_is_cod then
      raise exception 'COD orders must enter processing before payment is collected.';
    end if;
  elsif v_current_status = 'paid' then
    if v_new_status not in ('processing', 'shipped', 'refunded') then
      raise exception 'Invalid order transition: paid -> %', v_new_status;
    end if;
    if v_new_status = 'shipped' and not v_is_cod then
      raise exception 'Online orders must enter processing before shipping.';
    end if;
  elsif v_current_status = 'processing' then
    if v_new_status not in ('paid', 'shipped', 'refunded', 'cancelled') then
      raise exception 'Invalid order transition: processing -> %', v_new_status;
    end if;
    if v_new_status = 'paid' and not v_is_cod then
      raise exception 'Only COD orders can be marked paid from processing.';
    end if;
    if v_new_status = 'cancelled' and (not v_is_cod or coalesce(nullif(trim(v_order.provider_payment_id), ''), '') <> '') then
      raise exception 'Only unpaid COD orders can be cancelled while processing.';
    end if;
  elsif v_current_status = 'shipped' then
    if v_new_status not in ('delivered', 'refunded') then
      raise exception 'Invalid order transition: shipped -> %', v_new_status;
    end if;
  elsif v_current_status = 'delivered' then
    if v_new_status <> 'refunded' then
      raise exception 'Invalid order transition: delivered -> %', v_new_status;
    end if;
  else
    raise exception 'Order in terminal state cannot transition: % -> %', v_current_status, v_new_status;
  end if;

  -- Payment settlement is authoritative for COD -> paid.
  if v_new_status = 'paid' then
    if v_is_cod then
      v_settlement := public.settle_cod_payment(p_order_id, v_order.customer_id);
      if v_settlement not in ('SETTLED', 'ALREADY_SETTLED') then
        raise exception 'COD payment settlement failed: %', v_settlement;
      end if;
    elsif v_current_status <> 'paid' then
      raise exception 'PAID status requires provider payment settlement; direct status mutation is not allowed.';
    end if;
  end if;

  -- A shipment cannot be created without a real delivery reference.
  if v_new_status = 'shipped' then
    if nullif(trim(coalesce(p_tracking_number, v_order.tracking_number, '')), '') is null then
      raise exception 'Tracking number is required before shipping.';
    end if;

    if v_is_cod then
      select lower(trim(coalesce(status, ''))),
             nullif(trim(provider_payment_id), '')
        into v_payment_status, v_provider_payment_id
        from public.payments
       where order_id = p_order_id
       order by updated_at desc nulls last, created_at desc nulls last
       limit 1
       for update;

      if coalesce(v_payment_status, '') <> 'succeeded'
         or coalesce(v_provider_payment_id, '') = '' then
        raise exception 'COD order must be paid before shipping.';
      end if;
    end if;
  end if;

  update public.orders
     set status = v_new_status,
         tracking_number = coalesce(nullif(trim(p_tracking_number), ''), tracking_number),
         notes = case
                   when p_notes is not null
                   then coalesce(notes, '') || ' | ' || p_notes
                   else notes
                 end,
         updated_at = now(),
         refunded_at = case when v_new_status = 'refunded' then now() else refunded_at end,
         shipped_at = case when v_new_status = 'shipped' then now() else shipped_at end,
         delivered_at = case when v_new_status = 'delivered' then now() else delivered_at end,
         cancelled_at = case when v_new_status = 'cancelled' then now() else cancelled_at end,
         fulfilled_at = case when v_new_status = 'processing' then now() else fulfilled_at end
   where id = p_order_id
   returning *
   into v_order;

  return to_jsonb(v_order);
end;
$function$;

alter function public.rpc_admin_update_order_status(uuid, text, text, text)
  set search_path to pg_catalog, public;

commit;
