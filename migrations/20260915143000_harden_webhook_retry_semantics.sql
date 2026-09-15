-- P0 payment reliability: failed webhook processing must remain retryable.
-- A processed event is immutable/idempotent; pending/failed events may be reclaimed.
create or replace function public.claim_webhook_event(
    p_event_id text,
    p_event_type text,
    p_pi_id text
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_catalog
as $function$
declare
    claimed boolean;
begin
    insert into public.webhook_events_ledger (
        event_id,
        event_type,
        stripe_payment_intent_id,
        status
    )
    values (
        p_event_id,
        p_event_type,
        p_pi_id,
        'pending'
    )
    on conflict (event_id) do update
    set event_type = excluded.event_type,
        stripe_payment_intent_id = excluded.stripe_payment_intent_id,
        status = 'pending',
        processed_at = null
    where public.webhook_events_ledger.status <> 'processed'
    returning true into claimed;

    return coalesce(claimed, false);
end;
$function$;

revoke execute on function public.claim_webhook_event(text, text, text) from public, anon, authenticated;
grant execute on function public.claim_webhook_event(text, text, text) to service_role;
