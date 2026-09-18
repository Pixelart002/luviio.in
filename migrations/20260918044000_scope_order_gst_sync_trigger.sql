drop trigger if exists trg_sync_order_gst_split_after_update on public.order_items;

create trigger trg_sync_order_gst_split_after_update
after update of subtotal, unit_price, quantity, gst_percentage, tax_amount, order_id
on public.order_items
referencing old table as old_rows new table as new_rows
for each statement
execute function public.sync_order_gst_split_after_update();

drop trigger if exists trg_sync_order_gst_split_after_insert on public.order_items;
create trigger trg_sync_order_gst_split_after_insert
after insert on public.order_items
referencing new table as new_rows
for each statement
execute function public.sync_order_gst_split_after_insert();

drop trigger if exists trg_sync_order_gst_split_after_delete on public.order_items;
create trigger trg_sync_order_gst_split_after_delete
after delete on public.order_items
referencing old table as old_rows
for each statement
execute function public.sync_order_gst_split_after_delete();
