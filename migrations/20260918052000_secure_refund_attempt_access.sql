drop policy if exists payment_refunds_deny_anon on public.payment_refunds;
drop policy if exists payment_refunds_deny_authenticated on public.payment_refunds;

create policy payment_refunds_deny_anon
    on public.payment_refunds
    for all
    to anon
    using (false)
    with check (false);

create policy payment_refunds_deny_authenticated
    on public.payment_refunds
    for all
    to authenticated
    using (false)
    with check (false);
