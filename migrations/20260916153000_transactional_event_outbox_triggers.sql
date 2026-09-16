-- Transactional event outbox: business mutation and event persistence share the same DB transaction.
-- Application event publishers remain compatibility shims; the database is the source of truth.

create or replace function public.enqueue_transactional_order_event()
returns trigger
language plpgsql
security definer
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_email text;
  v_payload jsonb;
begin
  v_email := coalesce(new.shipping_email, new.billing_email, '');

  if tg_op = 'INSERT' then
    v_payload := jsonb_build_object(
      'order', to_jsonb(new),
      'customer_email', v_email,
      'customer_id', coalesce(new.customer_id::text, '')
    );
    insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
    values(gen_random_uuid(),'OrderCreatedEvent',v_payload,'pending',0,now());
    return new;
  end if;

  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    if new.status = 'paid' then
      v_payload := jsonb_build_object('order',to_jsonb(new),'customer_email',v_email,'customer_id',coalesce(new.customer_id::text,''));
      insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
      values(gen_random_uuid(),'OrderPaidEvent',v_payload,'pending',0,now());
    elsif new.status = 'shipped' then
      v_payload := jsonb_build_object('order',to_jsonb(new),'customer_email',v_email,'customer_id',coalesce(new.customer_id::text,''),'tracking_number',new.tracking_number);
      insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
      values(gen_random_uuid(),'OrderShippedEvent',v_payload,'pending',0,now());
    elsif new.status in ('delivered','refunded','cancelled') then
      v_payload := jsonb_build_object('order',to_jsonb(new),'customer_id',coalesce(new.customer_id::text,''),'old_status',coalesce(old.status,''),'new_status',new.status);
      insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
      values(gen_random_uuid(),'OrderStatusChangedEvent',v_payload,'pending',0,now());
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_transactional_order_event_outbox on public.orders;
create trigger trg_transactional_order_event_outbox
after insert or update of status on public.orders
for each row execute function public.enqueue_transactional_order_event();

create or replace function public.enqueue_transactional_inventory_event()
returns trigger
language plpgsql
security definer
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_payload jsonb;
begin
  if tg_op = 'UPDATE'
     and new.stock is distinct from old.stock
     and new.stock <= coalesce(new.low_stock_threshold,10)
     and old.stock > coalesce(new.low_stock_threshold,10) then
    v_payload := jsonb_build_object(
      'product_id',new.id::text,
      'product_name',coalesce(new.name,''),
      'stock',coalesce(new.stock,0),
      'threshold',coalesce(new.low_stock_threshold,10)
    );
    insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
    values(gen_random_uuid(),'LowStockEvent',v_payload,'pending',0,now());
  end if;
  return new;
end;
$$;

drop trigger if exists trg_transactional_inventory_event_outbox on public.products;
create trigger trg_transactional_inventory_event_outbox
after update of stock on public.products
for each row execute function public.enqueue_transactional_inventory_event();

create or replace function public.enqueue_transactional_setting_event()
returns trigger
language plpgsql
security definer
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_actor text;
  v_payload jsonb;
  v_event_type text;
begin
  if tg_op = 'UPDATE' and new.value is distinct from old.value then
    v_actor := coalesce(nullif(current_setting('request.jwt.claim.sub', true),''),'system');
    v_event_type := case when new.value = new.default_value then 'SettingResetEvent' else 'SettingUpdatedEvent' end;

    if v_event_type = 'SettingResetEvent' then
      v_payload := jsonb_build_object('key',new.key,'restored_value',new.value,'reset_by',v_actor);
    else
      v_payload := jsonb_build_object(
        'key',new.key,
        'old_value',old.value,
        'new_value',new.value,
        'updated_by',v_actor,
        'reason','system_settings update'
      );
    end if;

    insert into public.event_outbox(id,event_type,payload,status,attempts,next_retry_at)
    values(gen_random_uuid(),v_event_type,v_payload,'pending',0,now());
  end if;
  return new;
end;
$$;

drop trigger if exists trg_transactional_setting_event_outbox on public.system_settings;
create trigger trg_transactional_setting_event_outbox
after update of value on public.system_settings
for each row execute function public.enqueue_transactional_setting_event();

grant execute on function public.enqueue_transactional_order_event() to service_role;
grant execute on function public.enqueue_transactional_inventory_event() to service_role;
grant execute on function public.enqueue_transactional_setting_event() to service_role;
