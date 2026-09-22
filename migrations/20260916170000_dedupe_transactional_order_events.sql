-- Prevent duplicate transactional order events from causing duplicate side effects.
-- Keep the earliest row for naturally-once order events and remove later technical duplicates.
with ranked as (
    select
        id,
        row_number() over (
            partition by event_type, (payload->'order'->>'id')
            order by created_at asc, id asc
        ) as rn
    from public.event_outbox
    where event_type in ('OrderCreatedEvent', 'OrderPaidEvent', 'OrderShippedEvent')
      and payload->'order'->>'id' is not null
)
delete from public.event_outbox e
using ranked r
where e.id = r.id
  and r.rn > 1;

create unique index if not exists uq_event_outbox_order_created
    on public.event_outbox (event_type, ((payload->'order'->>'id')))
    where event_type = 'OrderCreatedEvent'
      and payload->'order'->>'id' is not null;

create unique index if not exists uq_event_outbox_order_paid
    on public.event_outbox (event_type, ((payload->'order'->>'id')))
    where event_type = 'OrderPaidEvent'
      and payload->'order'->>'id' is not null;

create unique index if not exists uq_event_outbox_order_shipped
    on public.event_outbox (event_type, ((payload->'order'->>'id')))
    where event_type = 'OrderShippedEvent'
      and payload->'order'->>'id' is not null;

create or replace function public.enqueue_transactional_order_event()
returns trigger
language plpgsql
security definer
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_email text;
  v_payload jsonb;
  v_event_type text;
begin
  v_email := coalesce(new.shipping_email, new.billing_email, '');

  if tg_op = 'INSERT' then
    v_event_type := 'OrderCreatedEvent';
    v_payload := jsonb_build_object(
      'order', to_jsonb(new),
      'customer_email', v_email,
      'customer_id', coalesce(new.customer_id::text, '')
    );
    insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
    values(gen_random_uuid(),v_event_type,v_payload,'pending',0,now())
    on conflict do nothing;
    return new;
  end if;

  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    if new.status = 'paid' then
      v_event_type := 'OrderPaidEvent';
      v_payload := jsonb_build_object('order',to_jsonb(new),'customer_email',v_email,'customer_id',coalesce(new.customer_id::text,''));
    elsif new.status = 'shipped' then
      v_event_type := 'OrderShippedEvent';
      v_payload := jsonb_build_object('order',to_jsonb(new),'customer_email',v_email,'customer_id',coalesce(new.customer_id::text,''),'tracking_number',new.tracking_number);
    elsif new.status in ('delivered','refunded','cancelled') then
      v_payload := jsonb_build_object('order',to_jsonb(new),'customer_id',coalesce(new.customer_id::text,''),'old_status',coalesce(old.status,''),'new_status',new.status);
      insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
      values(gen_random_uuid(),'OrderStatusChangedEvent',v_payload,'pending',0,now());
      return new;
    else
      return new;
    end if;

    insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
    values(gen_random_uuid(),v_event_type,v_payload,'pending',0,now())
    on conflict do nothing;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_transactional_order_event_outbox on public.orders;
create trigger trg_transactional_order_event_outbox
after insert or update of status on public.orders
for each row execute function public.enqueue_transactional_order_event();
