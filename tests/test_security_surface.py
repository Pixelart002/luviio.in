from pathlib import Path


MIGRATION = Path("migrations/20260916233000_harden_public_schema_and_client_mutations.sql")


def test_public_schema_and_client_mutation_hardening_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in sql
    assert "REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC" in sql
    assert "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role" in sql
    assert "REVOKE INSERT, UPDATE, DELETE ON TABLE public.users FROM anon, authenticated" in sql
    assert "DROP POLICY IF EXISTS users_update_own ON public.users" in sql
    assert "REVOKE INSERT, UPDATE, DELETE ON TABLE public.orders FROM anon, authenticated" in sql
    assert "DROP POLICY IF EXISTS orders_insert_own ON public.orders" in sql
    assert "DROP POLICY IF EXISTS orders_update_own ON public.orders" in sql
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC" in sql
    assert "SET search_path TO pg_catalog, public" in sql
