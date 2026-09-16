alter table public.settings_audit_log
    alter column changed_by drop not null;
