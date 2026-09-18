create or replace function public.fn_assign_payment_attempt_number()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $function$
begin
  -- payments has one durable header per order. Initial creation is always
  -- attempt #1; retries reuse/update that payment row rather than inserting
  -- another header, so scanning COUNT(*) here is unnecessary work.
  if new.attempt_number is null then
    new.attempt_number := 1;
  end if;
  return new;
end;
$function$;
