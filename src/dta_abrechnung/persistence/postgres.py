from __future__ import annotations


AUDIT_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION audit_row_change() RETURNS trigger AS $$
DECLARE
    actor_id text := current_setting('app.audit.actor_id', true);
    actor_type text := current_setting('app.audit.actor_type', true);
    request_id text := current_setting('app.audit.request_id', true);
    tenant_id text := current_setting('app.current_tenant', true);
    reason text := current_setting('app.audit.reason', true);
    legal_basis text := current_setting('app.audit.legal_basis', true);
    before_data jsonb := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END;
    after_data jsonb := CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END;
    changed_fields_data jsonb;
    row_identifier text;
BEGIN
    row_identifier := COALESCE(
        after_data ->> 'id',
        before_data ->> 'id',
        after_data ->> 'snapshot_id',
        before_data ->> 'snapshot_id',
        'unknown'
    );
    changed_fields_data := CASE TG_OP
        WHEN 'INSERT' THEN (
            SELECT COALESCE(jsonb_agg(key ORDER BY key), '[]'::jsonb)
            FROM jsonb_object_keys(after_data) AS key
        )
        WHEN 'DELETE' THEN (
            SELECT COALESCE(jsonb_agg(key ORDER BY key), '[]'::jsonb)
            FROM jsonb_object_keys(before_data) AS key
        )
        ELSE (
            SELECT COALESCE(jsonb_agg(key ORDER BY key), '[]'::jsonb)
            FROM (
                SELECT key
                FROM jsonb_object_keys(COALESCE(before_data, '{}'::jsonb) || COALESCE(after_data, '{}'::jsonb)) AS key
                WHERE COALESCE(before_data -> key, 'null'::jsonb) IS DISTINCT FROM COALESCE(after_data -> key, 'null'::jsonb)
            ) AS changed
        )
    END;
    INSERT INTO audit_ledger (
        event_id,
        occurred_at,
        table_name,
        row_pk,
        actor_id,
        actor_type,
        operation,
        request_id,
        tenant_id,
        reason,
        legal_basis,
        changed_fields,
        before_state,
        after_state,
        sensitive_read_target
    )
    VALUES (
        md5(random()::text || clock_timestamp()::text),
        now(),
        TG_TABLE_NAME,
        row_identifier,
        COALESCE(actor_id, 'postgres-trigger'),
        COALESCE(actor_type, 'system')::actor_type,
        CASE TG_OP
            WHEN 'INSERT' THEN 'insert'::audit_operation
            WHEN 'UPDATE' THEN 'update'::audit_operation
            ELSE 'delete'::audit_operation
        END,
        COALESCE(request_id, 'unknown'),
        tenant_id,
        NULLIF(reason, ''),
        NULLIF(legal_basis, ''),
        changed_fields_data,
        before_data,
        after_data,
        NULL
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
"""


def create_audit_trigger_sql(table_name: str) -> str:
    return f"""
    DROP TRIGGER IF EXISTS trg_audit_{table_name} ON {table_name};
    CREATE TRIGGER trg_audit_{table_name}
    AFTER INSERT OR UPDATE OR DELETE ON {table_name}
    FOR EACH ROW EXECUTE FUNCTION audit_row_change();
    """


def create_tenant_rls_sql(table_name: str) -> str:
    return f"""
    ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name};
    CREATE POLICY {table_name}_tenant_isolation ON {table_name}
    USING (tenant_id = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true));
    """
