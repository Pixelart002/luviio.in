begin;

alter table public.orders
  add column if not exists shipping_tax_amount numeric not null default 0;

alter table public.orders
  add constraint orders_shipping_tax_amount_nonnegative
  check (shipping_tax_amount >= 0);

create or replace function public.create_invoice_snapshot_for_order(p_order_id uuid)
returns uuid
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_order public.orders%rowtype;
  v_invoice_id uuid;
  v_seller_name text;
  v_seller_addr1 text;
  v_seller_addr2 text;
  v_seller_city text;
  v_seller_district text;
  v_seller_state text;
  v_seller_state_code text;
  v_seller_pincode text;
  v_seller_country text;
  v_seller_pan text;
  v_seller_gstin text;
  v_seller_email text;
  v_seller_website text;
  v_signatory_name text;
  v_signatory_designation text;
  v_gstin_registered boolean;
  v_line_no integer;
  v_total_item_value numeric := 0;
  v_shipping numeric := 0;
  v_remaining_shipping numeric := 0;
  v_remaining_shipping_tax numeric := 0;
  v_group_value numeric;
  v_group_rate numeric;
  v_allocated_shipping numeric;
  v_allocated_tax numeric;
  v_group_count integer;
  v_group_index integer := 0;
begin
  select * into v_order from public.orders where id = p_order_id for update;
  if not found then raise exception 'ORDER_NOT_FOUND:%', p_order_id; end if;
  if v_order.status <> 'paid' then return null; end if;
  if v_order.invoice_number is null or btrim(v_order.invoice_number) = '' then raise exception 'INVOICE_NUMBER_MISSING:%', p_order_id; end if;

  select id into v_invoice_id from public.invoices where order_id = p_order_id;
  if v_invoice_id is not null then return v_invoice_id; end if;

  select coalesce(value #>> '{}','') into v_seller_name from public.system_settings where key = 'business_legal_name';
  select coalesce(value #>> '{}','') into v_seller_addr1 from public.system_settings where key = 'seller_address_line1';
  select coalesce(value #>> '{}','') into v_seller_addr2 from public.system_settings where key = 'seller_address_line2';
  select coalesce(value #>> '{}','') into v_seller_city from public.system_settings where key = 'seller_city';
  select coalesce(value #>> '{}','') into v_seller_district from public.system_settings where key = 'seller_district';
  select coalesce(value #>> '{}','') into v_seller_state from public.system_settings where key = 'seller_state';
  select coalesce(value #>> '{}','') into v_seller_state_code from public.system_settings where key = 'seller_state_code';
  select coalesce(value #>> '{}','') into v_seller_pincode from public.system_settings where key = 'seller_pincode';
  select coalesce(value #>> '{}','') into v_seller_country from public.system_settings where key = 'seller_country';
  select coalesce(value #>> '{}','') into v_seller_pan from public.system_settings where key = 'seller_pan';
  select coalesce(value #>> '{}','') into v_seller_gstin from public.system_settings where key = 'seller_gstin';
  select coalesce(value #>> '{}','') into v_seller_email from public.system_settings where key = 'business_email';
  select coalesce(value #>> '{}','') into v_seller_website from public.system_settings where key = 'business_website';
  select coalesce(value #>> '{}','') into v_signatory_name from public.system_settings where key = 'business_authorised_signatory_name';
  select coalesce(value #>> '{}','') into v_signatory_designation from public.system_settings where key = 'business_authorised_signatory_designation';
  select coalesce((value #>> '{}')::boolean, false) into v_gstin_registered from public.system_settings where key = 'seller_gst_registered';

  if btrim(coalesce(v_seller_name,'')) = '' or btrim(coalesce(v_seller_addr1,'')) = '' or btrim(coalesce(v_seller_city,'')) = '' or btrim(coalesce(v_seller_state,'')) = '' or btrim(coalesce(v_seller_pincode,'')) = '' or btrim(coalesce(v_seller_country,'')) = '' then
    raise exception 'SELLER_CONFIGURATION_INCOMPLETE: legal name, address, city, state, pincode and country are required before invoice creation';
  end if;
  if v_gstin_registered and btrim(coalesce(v_seller_gstin,'')) = '' then
    raise exception 'SELLER_CONFIGURATION_INCOMPLETE: GSTIN is required when seller_gst_registered=true';
  end if;

  insert into public.invoices(order_id, invoice_number, status, issued_at, currency, tax_type, seller_snapshot, billing_snapshot, shipping_snapshot, totals_snapshot)
  values (
    v_order.id, v_order.invoice_number, 'issued', coalesce(v_order.paid_at, v_order.created_at, now()), coalesce(v_order.currency, 'INR'), coalesce(v_order.tax_type, 'IGST'),
    jsonb_strip_nulls(jsonb_build_object(
      'legal_name',v_seller_name,'address_1',v_seller_addr1,'address_2',nullif(v_seller_addr2,''),'city',v_seller_city,'district',nullif(v_seller_district,''),
      'state',v_seller_state,'state_code',v_seller_state_code,'pincode',v_seller_pincode,'country',v_seller_country,'pan',nullif(v_seller_pan,''),
      'gstin',nullif(v_seller_gstin,''),'gst_registered',v_gstin_registered,'email',nullif(v_seller_email,''),'website',nullif(v_seller_website,''),
      'authorised_signatory_name',nullif(v_signatory_name,''),'authorised_signatory_designation',nullif(v_signatory_designation,'')
    )),
    jsonb_build_object('name',v_order.billing_name,'phone',v_order.billing_phone,'email',v_order.billing_email,'company_name',v_order.billing_company_name,'gstin',v_order.billing_gstin,'line1',v_order.billing_line1,'line2',v_order.billing_line2,'landmark',v_order.billing_landmark,'city',v_order.billing_city,'state',v_order.billing_state,'postal_code',v_order.billing_postal_code,'country',v_order.billing_country),
    jsonb_build_object('name',v_order.shipping_name,'phone',v_order.shipping_phone,'email',v_order.shipping_email,'company_name',v_order.shipping_company_name,'gstin',v_order.shipping_gstin,'line1',v_order.shipping_line1,'line2',v_order.shipping_line2,'landmark',v_order.shipping_landmark,'city',v_order.shipping_city,'state',v_order.shipping_state,'postal_code',v_order.shipping_postal_code,'country',v_order.shipping_country),
    jsonb_build_object(
      'subtotal',coalesce(v_order.subtotal,0),
      'discount_amount',coalesce(v_order.discount_amount,0),
      'shipping_cost',coalesce(v_order.shipping_cost,0),
      'shipping_tax_amount',coalesce(v_order.shipping_tax_amount,0),
      'tax_amount',coalesce(v_order.tax_amount,0),
      'total_amount',coalesce(v_order.total_amount,0),
      'currency',coalesce(v_order.currency,'INR'),
      'tax_type',coalesce(v_order.tax_type,'IGST')
    )
  ) returning id into v_invoice_id;

  select coalesce(sum(round(coalesce(oi.subtotal,(oi.unit_price*oi.quantity)-coalesce(oi.discount_amount,0)),2)),0)
    into v_total_item_value
  from public.order_items oi where oi.order_id = v_order.id;

  insert into public.invoice_items(invoice_id,line_no,product_id,product_name,sku,hsn_code,quantity,unit_price,discount_amount,taxable_value,gst_percentage,cgst_amount,sgst_amount,igst_amount,tax_amount,line_total,metadata)
  select v_invoice_id,row_number() over(order by oi.id),oi.product_id,coalesce(oi.product_name,p.name,'Product'),p.sku,coalesce(oi.hsn_code,p.hsn_code),oi.quantity,round(coalesce(oi.unit_price,0),2),round(coalesce(oi.discount_amount,0),2),round(coalesce(oi.subtotal,(oi.unit_price*oi.quantity)-coalesce(oi.discount_amount,0)),2),coalesce(oi.gst_percentage,p.gst_percentage,0),
    case when upper(coalesce(v_order.tax_type,'IGST')) in ('CGST_SGST','CGST+SGST','CGST/SGST') then round(coalesce(oi.tax_amount,0)/2,2) else 0 end,
    case when upper(coalesce(v_order.tax_type,'IGST')) in ('CGST_SGST','CGST+SGST','CGST/SGST') then round(coalesce(oi.tax_amount,0)-round(coalesce(oi.tax_amount,0)/2,2),2) else 0 end,
    case when upper(coalesce(v_order.tax_type,'IGST')) not in ('CGST_SGST','CGST+SGST','CGST/SGST') then round(coalesce(oi.tax_amount,0),2) else 0 end,
    round(coalesce(oi.tax_amount,0),2),round(coalesce(oi.subtotal,(oi.unit_price*oi.quantity)-coalesce(oi.discount_amount,0))+coalesce(oi.tax_amount,0),2),jsonb_build_object('source_order_item_id',oi.id)
  from public.order_items oi left join public.products p on p.id=oi.product_id where oi.order_id=v_order.id;

  v_shipping := round(coalesce(v_order.shipping_cost,0),2);
  v_remaining_shipping := v_shipping;
  v_remaining_shipping_tax := round(coalesce(v_order.shipping_tax_amount,0),2);

  if v_shipping > 0 and v_total_item_value > 0 then
    select count(*) into v_group_count
    from (
      select coalesce(oi.gst_percentage,p.gst_percentage,0) as rate
      from public.order_items oi left join public.products p on p.id=oi.product_id
      where oi.order_id=v_order.id
      group by coalesce(oi.gst_percentage,p.gst_percentage,0)
    ) g;

    for v_group_index in 1..v_group_count loop
      select rate, group_value into v_group_rate, v_group_value
      from (
        select coalesce(oi.gst_percentage,p.gst_percentage,0) as rate,
               sum(round(coalesce(oi.subtotal,(oi.unit_price*oi.quantity)-coalesce(oi.discount_amount,0)),2)) as group_value,
               row_number() over(order by coalesce(oi.gst_percentage,p.gst_percentage,0)) as rn
        from public.order_items oi left join public.products p on p.id=oi.product_id
        where oi.order_id=v_order.id
        group by coalesce(oi.gst_percentage,p.gst_percentage,0)
      ) groups
      where rn=v_group_index;

      if v_group_index = v_group_count then
        v_allocated_shipping := v_remaining_shipping;
        v_allocated_tax := v_remaining_shipping_tax;
      else
        v_allocated_shipping := round(v_shipping * v_group_value / v_total_item_value, 2);
        v_allocated_tax := round(v_allocated_shipping * v_group_rate / 100, 2);
        v_remaining_shipping := v_remaining_shipping - v_allocated_shipping;
        v_remaining_shipping_tax := v_remaining_shipping_tax - v_allocated_tax;
      end if;

      insert into public.invoice_items(
        invoice_id,line_no,product_id,product_name,sku,hsn_code,quantity,unit_price,
        discount_amount,taxable_value,gst_percentage,cgst_amount,sgst_amount,igst_amount,
        tax_amount,line_total,metadata
      )
      values (
        v_invoice_id,
        (select coalesce(max(line_no),0)+1 from public.invoice_items where invoice_id=v_invoice_id),
        null,
        'Shipping Charges',
        null,
        '9965',
        1,
        v_allocated_shipping,
        0,
        v_allocated_shipping,
        v_group_rate,
        case when upper(coalesce(v_order.tax_type,'IGST')) in ('CGST_SGST','CGST+SGST','CGST/SGST') then round(v_allocated_tax/2,2) else 0 end,
        case when upper(coalesce(v_order.tax_type,'IGST')) in ('CGST_SGST','CGST+SGST','CGST/SGST') then v_allocated_tax-round(v_allocated_tax/2,2) else 0 end,
        case when upper(coalesce(v_order.tax_type,'IGST')) not in ('CGST_SGST','CGST+SGST','CGST/SGST') then v_allocated_tax else 0 end,
        v_allocated_tax,
        v_allocated_shipping+v_allocated_tax,
        jsonb_build_object('kind','shipping','gst_allocation','allocated_by_taxable_line_value')
      );
    end loop;
  end if;

  return v_invoice_id;
end;
$$;

commit;
