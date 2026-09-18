-- First-class refund attempts and per-refund accounting.
-- This separates refund lifecycle/history from the aggregate payments.status field.
create table if not exists public.payment_refunds (
    id uuid primary key default gen_random_uuid(),
    payment_id uuid not null references public.payments(id) on delete restrict,
    order_id uuid not null references public.orders(id) on delete restrict,
    refund_attempt_number integer not null,
    payment_provider text not null,
    provider_payment_id text not null,
    provider_refund_id text,
    idempotency_key text not null,
    amount numeric not null check (amount > 0),
    amount_paise bigint not null check (amount_paise > 0),
    currency text not null default 'INR',
    status text not null check (status in ('requested','pending','succeeded','failed','canceled')),
    reason text,
    reference text,
    failure_code text,
    failure_message text,
    gateway_metadata jsonb not null default '{}'::jsonb,
    requested_at timestamptz not null default now(),
    processed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint payment_refunds_payment_attempt_uq unique (payment_id, refund_attempt_number),
    constraint payment_refunds_idempotency_uq unique (idempotency_key)
);

create unique index if not exists payment_refunds_provider_refund_uq
    on public.payment_refunds(payment_provider, provider_refund_id)
    where provider_refund_id is not null;

create index if not exists payment_refunds_order_created_idx
    on public.payment_refunds(order_id, created_at desc);

create index if not exists payment_refunds_payment_attempt_idx
    on public.payment_refunds(payment_id, refund_attempt_number desc, created_at desc);

create index if not exists payment_refunds_status_updated_idx
    on public.payment_refunds(status, updated_at desc);

alter table public.payment_refunds enable row level security;
alter table public.payment_refunds force row level security;
revoke all on table public.payment_refunds from public, anon, authenticated;
grant all on table public.payment_refunds to service_role;

-- payment_ledger must support multiple refund entries against one payment.
drop index if exists public.payment_ledger_provider_event_uq;
create unique index if not exists payment_ledger_provider_event_uq
    on public.payment_ledger(provider, provider_payment_id, entry_type)
    where entry_type <> 'payment_refunded';
create unique index if not exists payment_ledger_refund_event_uq
    on public.payment_ledger(provider, provider_payment_id, entry_type, reference)
    where entry_type = 'payment_refunded' and reference is not null;

create or replace function public.create_payment_refund_attempt(
    p_order_id uuid,
    p_provider text,
    p_provider_payment_id text,
    p_amount numeric,
    p_currency text default 'INR',
    p_idempotency_key text default null,
    p_reason text default null,
    p_reference text default null,
    p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog', 'public'
as $function$
declare
    v_provider text;
    v_provider_payment_id text;
    v_currency text;
    v_idempotency_key text;
    v_requested_key text;
    v_payment public.payments%rowtype;
    v_refund public.payment_refunds%rowtype;
    v_next_attempt integer;
    v_refunded numeric;
    v_reserved numeric;
    v_remaining numeric;
begin
    v_provider := lower(nullif(trim(p_provider), ''));
    v_provider_payment_id := nullif(trim(p_provider_payment_id), '');
    v_currency := upper(coalesce(nullif(trim(p_currency), ''), 'INR'));
    v_requested_key := nullif(trim(p_idempotency_key), '');

    if p_order_id is null
       or v_provider is null
       or v_provider_payment_id is null
       or p_amount is null
       or p_amount <= 0
       or v_requested_key is null then
        raise exception 'REFUND_ATTEMPT_DATA_INVALID';
    end if;

    select *
      into v_refund
      from public.payment_refunds
     where idempotency_key = v_requested_key
     for update;

    if found and v_refund.status in ('requested', 'pending', 'succeeded') then
        return jsonb_build_object(
            'id', v_refund.id, 'payment_id', v_refund.payment_id, 'order_id', v_refund.order_id,
            'refund_attempt_number', v_refund.refund_attempt_number,
            'provider_refund_id', v_refund.provider_refund_id,
            'idempotency_key', v_refund.idempotency_key,
            'amount', v_refund.amount, 'amount_paise', v_refund.amount_paise,
            'currency', v_refund.currency, 'status', v_refund.status
        );
    end if;

    select *
      into v_payment
      from public.payments
     where order_id = p_order_id
       and payment_provider = v_provider
       and provider_payment_id = v_provider_payment_id
     order by updated_at desc nulls last, created_at desc nulls last
     limit 1
     for update;

    if not found then
        raise exception 'PAYMENT_NOT_FOUND';
    end if;

    select coalesce(max(refund_attempt_number), 0) + 1
      into v_next_attempt
      from public.payment_refunds
     where payment_id = v_payment.id;

    if v_refund.status in ('failed', 'canceled') then
        v_idempotency_key := v_requested_key || ':' || v_next_attempt::text;
    else
        v_idempotency_key := v_requested_key;
    end if;

    select coalesce(sum(amount), 0)
      into v_refunded
      from public.payment_refunds
     where payment_id = v_payment.id and status = 'succeeded';

    select coalesce(sum(amount), 0)
      into v_reserved
      from public.payment_refunds
     where payment_id = v_payment.id and status in ('requested', 'pending');

    v_remaining := round(v_payment.amount, 2) - round(v_refunded, 2) - round(v_reserved, 2);

    if round(p_amount, 2) > round(v_remaining, 2) then
        raise exception 'REFUND_AMOUNT_EXCEEDS_REMAINING';
    end if;

    insert into public.payment_refunds(
        payment_id, order_id, refund_attempt_number, payment_provider,
        provider_payment_id, idempotency_key, amount, amount_paise,
        currency, status, reason, reference, gateway_metadata
    )
    values(
        v_payment.id, p_order_id, v_next_attempt, v_provider,
        v_provider_payment_id, v_idempotency_key, round(p_amount, 2),
        round(p_amount * 100)::bigint, v_currency, 'requested',
        nullif(trim(p_reason), ''), nullif(trim(p_reference), ''),
        coalesce(p_metadata, '{}'::jsonb)
    )
    returning * into v_refund;

    return jsonb_build_object(
        'id', v_refund.id, 'payment_id', v_refund.payment_id, 'order_id', v_refund.order_id,
        'refund_attempt_number', v_refund.refund_attempt_number,
        'provider_refund_id', v_refund.provider_refund_id,
        'idempotency_key', v_refund.idempotency_key,
        'amount', v_refund.amount, 'amount_paise', v_refund.amount_paise,
        'currency', v_refund.currency, 'status', v_refund.status
    );
end;
$function$;

create or replace function public.complete_payment_refund_attempt(
    p_refund_id uuid,
    p_status text,
    p_provider_refund_id text default null,
    p_failure_code text default null,
    p_failure_message text default null,
    p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog', 'public'
as $function$
declare
    v_refund public.payment_refunds%rowtype;
    v_payment public.payments%rowtype;
    v_total_refunded numeric;
    v_status text;
begin
    if p_refund_id is null then
        raise exception 'REFUND_ATTEMPT_ID_REQUIRED';
    end if;

    v_status := lower(nullif(trim(p_status), ''));
    if v_status not in ('pending', 'succeeded', 'failed', 'canceled') then
        raise exception 'INVALID_REFUND_ATTEMPT_STATUS';
    end if;

    select *
      into v_refund
      from public.payment_refunds
     where id = p_refund_id
     for update;

    if not found then
        raise exception 'REFUND_ATTEMPT_NOT_FOUND';
    end if;

    if v_refund.status in ('succeeded', 'failed', 'canceled')
       and v_refund.status = v_status then
        return jsonb_build_object(
            'id', v_refund.id,
            'status', v_refund.status,
            'provider_refund_id', v_refund.provider_refund_id
        );
    end if;

    if v_status in ('pending', 'succeeded')
       and nullif(trim(p_provider_refund_id), '') is null then
        raise exception 'PROVIDER_REFUND_ID_REQUIRED';
    end if;

    update public.payment_refunds
       set status = v_status,
           provider_refund_id = coalesce(nullif(trim(p_provider_refund_id), ''), provider_refund_id),
           failure_code = coalesce(nullif(trim(p_failure_code), ''), failure_code),
           failure_message = coalesce(nullif(trim(p_failure_message), ''), failure_message),
           gateway_metadata = coalesce(gateway_metadata, '{}'::jsonb) || coalesce(p_metadata, '{}'::jsonb),
           processed_at = case when v_status in ('succeeded', 'failed', 'canceled')
                               then coalesce(processed_at, now())
                               else processed_at end,
           updated_at = now()
     where id = p_refund_id
     returning * into v_refund;

    if v_status = 'succeeded' then
        select *
          into v_payment
          from public.payments
         where id = v_refund.payment_id
         for update;

        select coalesce(sum(amount), 0)
          into v_total_refunded
          from public.payment_refunds
         where payment_id = v_refund.payment_id
           and status = 'succeeded';

        if round(v_total_refunded, 2) >= round(v_payment.amount, 2) then
            update public.payments
               set status = 'refunded',
                   updated_at = now()
             where id = v_payment.id;
        end if;

        insert into public.payment_ledger(
            order_id, payment_id, provider, provider_payment_id, entry_type,
            direction, amount, amount_paise, currency, attempt_number,
            reference, metadata
        )
        values(
            v_refund.order_id, v_refund.payment_id, v_refund.payment_provider,
            v_refund.provider_payment_id, 'payment_refunded', 'debit',
            v_refund.amount, v_refund.amount_paise, v_refund.currency,
            v_refund.refund_attempt_number,
            coalesce(v_refund.provider_refund_id, v_refund.id::text),
            coalesce(v_refund.gateway_metadata, '{}'::jsonb) || jsonb_build_object(
                'source', 'payment_refund_attempt',
                'refund_attempt_id', v_refund.id,
                'refund_attempt_number', v_refund.refund_attempt_number
            )
        )
        on conflict do nothing;
    end if;

    return jsonb_build_object(
        'id', v_refund.id,
        'payment_id', v_refund.payment_id,
        'order_id', v_refund.order_id,
        'refund_attempt_number', v_refund.refund_attempt_number,
        'provider_refund_id', v_refund.provider_refund_id,
        'status', v_refund.status,
        'amount', v_refund.amount,
        'amount_paise', v_refund.amount_paise,
        'currency', v_refund.currency
    );
end;
$function$;

create or replace function public.record_payment_refund(
    p_order_id uuid, p_provider text, p_provider_payment_id text, p_amount numeric,
    p_currency text default 'INR', p_reference text default null,
    p_metadata jsonb default '{}'::jsonb
)
returns text
language plpgsql
security definer
set search_path to 'pg_catalog', 'public'
as $function$
declare
    v_attempt jsonb;
    v_id uuid;
begin
    v_attempt := public.create_payment_refund_attempt(
        p_order_id, p_provider, p_provider_payment_id, p_amount, p_currency,
        'legacy-refund:' || p_order_id::text || ':' || coalesce(p_reference, 'full'),
        'legacy', p_reference, coalesce(p_metadata, '{}'::jsonb)
    );
    v_id := (v_attempt->>'id')::uuid;

    perform public.complete_payment_refund_attempt(
        v_id, 'succeeded',
        coalesce(nullif(trim(p_reference), ''), 'legacy-' || v_id::text),
        null, null, coalesce(p_metadata, '{}'::jsonb)
    );
    return 'REFUNDED_ACCOUNTED';
exception when unique_violation then
    return 'REFUND_ALREADY_ACCOUNTED';
end;
$function$;

revoke execute on function public.create_payment_refund_attempt(uuid,text,text,numeric,text,text,text,text,jsonb)
    from public, anon, authenticated;
grant execute on function public.create_payment_refund_attempt(uuid,text,text,numeric,text,text,text,text,jsonb)
    to service_role;

revoke execute on function public.complete_payment_refund_attempt(uuid,text,text,text,text,jsonb)
    from public, anon, authenticated;
grant execute on function public.complete_payment_refund_attempt(uuid,text,text,text,text,jsonb)
    to service_role;

revoke execute on function public.record_payment_refund(uuid,text,text,numeric,text,text,jsonb)
    from public, anon, authenticated;
grant execute on function public.record_payment_refund(uuid,text,text,numeric,text,text,jsonb)
    to service_role;


create or replace function public.record_provider_refund_event(
    p_order_id uuid, p_provider text, p_provider_payment_id text,
    p_provider_refund_id text, p_amount numeric, p_currency text default 'INR',
    p_status text default 'succeeded', p_reason text default null,
    p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog', 'public'
as $function$
declare
    v_provider text := lower(nullif(trim(p_provider), ''));
    v_provider_payment_id text := nullif(trim(p_provider_payment_id), '');
    v_provider_refund_id text := nullif(trim(p_provider_refund_id), '');
    v_status text := lower(nullif(trim(p_status), ''));
    v_currency text := upper(coalesce(nullif(trim(p_currency), ''), 'INR'));
    v_payment public.payments%rowtype;
    v_refund public.payment_refunds%rowtype;
    v_attempt integer;
    v_total_refunded numeric;
begin
    if p_order_id is null or v_provider is null or v_provider_payment_id is null
       or v_provider_refund_id is null or p_amount is null or p_amount <= 0 then
        raise exception 'PROVIDER_REFUND_EVENT_DATA_INVALID';
    end if;
    if v_status not in ('pending', 'succeeded', 'failed', 'canceled') then
        raise exception 'INVALID_PROVIDER_REFUND_STATUS';
    end if;

    select * into v_payment
      from public.payments
     where order_id = p_order_id
       and payment_provider = v_provider
       and provider_payment_id = v_provider_payment_id
     order by updated_at desc nulls last, created_at desc nulls last
     limit 1 for update;
    if not found then
        raise exception 'PAYMENT_NOT_FOUND';
    end if;

    select * into v_refund
      from public.payment_refunds
     where payment_provider = v_provider
       and provider_refund_id = v_provider_refund_id
     for update;
    if found then
        return public.complete_payment_refund_attempt(
            v_refund.id, v_status, v_provider_refund_id, null, null,
            coalesce(p_metadata, '{}'::jsonb) || jsonb_build_object('source','provider_webhook')
        );
    end if;

    select coalesce(max(refund_attempt_number), 0) + 1 into v_attempt
      from public.payment_refunds where payment_id = v_payment.id;

    insert into public.payment_refunds(
        payment_id, order_id, refund_attempt_number, payment_provider,
        provider_payment_id, provider_refund_id, idempotency_key, amount,
        amount_paise, currency, status, reason, reference, gateway_metadata
    )
    values(
        v_payment.id, p_order_id, v_attempt, v_provider, v_provider_payment_id,
        v_provider_refund_id, 'provider-webhook:' || v_provider || ':' || v_provider_refund_id,
        round(p_amount, 2), round(p_amount * 100)::bigint, v_currency, v_status,
        nullif(trim(p_reason), ''), v_provider_refund_id,
        coalesce(p_metadata, '{}'::jsonb) || jsonb_build_object('source','provider_webhook')
    )
    returning * into v_refund;

    if v_status = 'succeeded' then
        select coalesce(sum(amount), 0) into v_total_refunded
          from public.payment_refunds
         where payment_id = v_payment.id and status = 'succeeded';

        if round(v_total_refunded, 2) >= round(v_payment.amount, 2) then
            update public.payments set status = 'refunded', updated_at = now()
             where id = v_payment.id;
        end if;

        insert into public.payment_ledger(
            order_id, payment_id, provider, provider_payment_id, entry_type,
            direction, amount, amount_paise, currency, attempt_number, reference, metadata
        )
        values(
            v_refund.order_id, v_refund.payment_id, v_refund.payment_provider,
            v_refund.provider_payment_id, 'payment_refunded', 'debit',
            v_refund.amount, v_refund.amount_paise, v_refund.currency,
            v_refund.refund_attempt_number, v_refund.provider_refund_id,
            coalesce(v_refund.gateway_metadata, '{}'::jsonb)
                || jsonb_build_object('source','provider_webhook','refund_attempt_id',v_refund.id)
        )
        on conflict do nothing;
    end if;

    return jsonb_build_object(
        'id', v_refund.id, 'payment_id', v_refund.payment_id, 'order_id', v_refund.order_id,
        'refund_attempt_number', v_refund.refund_attempt_number,
        'provider_refund_id', v_refund.provider_refund_id, 'status', v_refund.status,
        'amount', v_refund.amount, 'amount_paise', v_refund.amount_paise, 'currency', v_refund.currency
    );
end;
$function$;

revoke execute on function public.record_provider_refund_event(uuid,text,text,text,numeric,text,text,text,jsonb)
    from public, anon, authenticated;
grant execute on function public.record_provider_refund_event(uuid,text,text,text,numeric,text,text,text,jsonb)
    to service_role;
