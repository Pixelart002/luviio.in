# Database Guide

Supabase access is server-side and belongs in repositories. Keep row-level security enabled for exposed tables and scope user-owned queries by the authenticated user id.

## Rules

- Never expose `SB_SERVICE_ROLE_KEY`.
- Never use `select *` for sensitive data.
- Use explicit columns and validated filters.
- Keep schema changes in reviewed migrations.
- Add indexes for proven high-volume access patterns.
- Test RLS for anonymous, authenticated and admin roles.

Settings are operational configuration, not a replacement for orders, products, users or payment records. See `docs/SETTINGS.md` for the settings contract.
