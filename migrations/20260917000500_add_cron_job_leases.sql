begin;

-- Cross-worker lease table. API runs with 4 workers, so APScheduler exists in
-- each process. A database lease makes each registered job single-run across
-- all workers/instances while still allowing another worker to take over if
-- the current worker dies.
create table if not exists private.cron_job_leases (
  job_name text primary key,
  lease_token uuid not null,
  acquired_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index if not exists idx_cron_job_leases_expires_at
  on private.cron_job_leases (expires_at);

create or replace function private.acquire_cron_job_lease(
  p_job_name text,
  p_lease_seconds integer default 3600
)
returns uuid
language plpgsql
security definer
set search_path = private, pg_catalog, public
as $$
declare
  v_token uuid := gen_random_uuid();
begin
  if p_job_name is null or btrim(p_job_name) = '' then
    raise exception 'CRON_JOB_NAME_REQUIRED';
  end if;

  if p_lease_seconds < 30 or p_lease_seconds > 86400 then
    raise exception 'CRON_LEASE_SECONDS_OUT_OF_RANGE';
  end if;

  insert into private.cron_job_leases(job_name, lease_token, acquired_at, expires_at)
  values (p_job_name, v_token, now(), now() + make_interval(secs => p_lease_seconds))
  on conflict (job_name) do update
    set lease_token = excluded.lease_token,
        acquired_at = excluded.acquired_at,
        expires_at = excluded.expires_at
    where private.cron_job_leases.expires_at <= now();

  if exists (
    select 1
    from private.cron_job_leases
    where job_name = p_job_name
      and lease_token = v_token
  ) then
    return v_token;
  end if;

  return null;
end;
$$;

create or replace function private.release_cron_job_lease(
  p_job_name text,
  p_lease_token uuid
)
returns boolean
language sql
security definer
set search_path = private, pg_catalog, public
as $$
  delete from private.cron_job_leases
  where job_name = p_job_name
    and lease_token = p_lease_token
  returning true;
$$;

create or replace function public.acquire_cron_job_lease(
  p_job_name text,
  p_lease_seconds integer default 3600
)
returns uuid
language sql
security definer
set search_path = pg_catalog, private, public
as $$
  select private.acquire_cron_job_lease(p_job_name, p_lease_seconds);
$$;

create or replace function public.release_cron_job_lease(
  p_job_name text,
  p_lease_token uuid
)
returns boolean
language sql
security definer
set search_path = pg_catalog, private, public
as $$
  select private.release_cron_job_lease(p_job_name, p_lease_token);
$$;

revoke all on function public.acquire_cron_job_lease(text, integer) from public, anon, authenticated;
revoke all on function public.release_cron_job_lease(text, uuid) from public, anon, authenticated;
grant execute on function public.acquire_cron_job_lease(text, integer) to service_role;
grant execute on function public.release_cron_job_lease(text, uuid) to service_role;

commit;
