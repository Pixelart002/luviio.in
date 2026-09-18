create or replace function public.admin_dashboard_metrics()
returns jsonb
language sql
security definer
set search_path = pg_catalog, public
as $function$
with order_metrics as (
  select
    count(*)::bigint as orders,
    count(*) filter (where status = 'pending')::bigint as pending_orders,
    coalesce(
      sum(total_amount) filter (
        where status in ('paid','processing','shipped','delivered')
      ),
      0
    )::numeric as revenue
  from public.orders
),
product_metrics as (
  select count(*) filter (where is_active = true)::bigint as products
  from public.products
),
user_metrics as (
  select count(*)::bigint as users
  from public.users
)
select jsonb_build_object(
  'products', product_metrics.products,
  'orders', order_metrics.orders,
  'pending_orders', order_metrics.pending_orders,
  'users', user_metrics.users,
  'revenue', order_metrics.revenue
)
from order_metrics, product_metrics, user_metrics;
$function$;

revoke all on function public.admin_dashboard_metrics() from public, anon, authenticated;
grant execute on function public.admin_dashboard_metrics() to service_role;
