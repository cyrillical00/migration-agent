# Supabase DR Drill Procedure

Quarterly drill. Phase 0 exit criterion: must complete successfully before Phase 1 starts.

**Owner**: IT Lead (confirm name before first run; see QUESTIONS.md).
**Frequency**: Quarterly. Calendar invite to owner on completion.
**Duration**: ~2 hours.

## What this tests

- PITR restore path is functional.
- Nightly logical dump is intact and importable.
- Audit log stream (GCS write-once bucket) is accessible and complete.
- Recovery time from total state store loss is within tolerance.

## Steps

### 1. Confirm PITR is enabled

In the Supabase dashboard, verify Point-in-Time Recovery is enabled on the production project. Confirm backup retention is set to at least 7 days.

### 2. Create a restore target

Provision a fresh Supabase project (call it `migration-agent-dr-drill-YYYY-QN`). This is temporary; delete after drill.

### 3. Initiate PITR restore

In the Supabase dashboard, restore the production project to a point 1 hour in the past onto the drill project. Record start time.

### 4. Verify schema and row counts

Connect to the drill project. Run:

```sql
-- Check all 13 tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Spot-check row counts against production
SELECT 'audit_log' AS tbl, count(*) FROM audit_log
UNION ALL SELECT 'source_inventory', count(*) FROM source_inventory
UNION ALL SELECT 'migration_job', count(*) FROM migration_job;
```

Compare counts to production export from the restore timestamp.

### 5. Verify audit log immutability trigger

```sql
-- Should fail with "append-only" error
UPDATE audit_log SET result = 'tampered' WHERE id = (SELECT id FROM audit_log LIMIT 1);
```

### 6. Verify GCS audit log stream

Pull the last 24 hours of audit log objects from the GCS write-once bucket. Confirm no gaps in the sequence. Confirm the bucket's object lock is set (WORM).

### 7. Test logical dump restore

Retrieve the most recent nightly logical dump from GCS. Restore it into a local Postgres:

```bash
pg_restore -d postgresql://localhost/drill_restore path/to/dump.pgdump
```

Verify row counts match the dump manifest.

### 8. Record results

Fill in the drill report template and attach to the relevant gate decision record. Required fields:

- Date and time of drill
- Restore target project name
- PITR timestamp used
- Row count comparison (pass/fail)
- Trigger check (pass/fail)
- GCS stream check (pass/fail)
- Logical dump restore (pass/fail)
- Time to restore (minutes)
- Issues found
- Owner signature

### 9. Tear down drill project

Delete the `migration-agent-dr-drill-*` Supabase project. Confirm deletion.

## Pass criteria

All checks pass. Any failure blocks Phase 0 completion. Failures go into QUESTIONS.md.

## Scheduling

After each successful drill, schedule the next one 90 days out. Owner sends calendar invite to CTO and IT lead.
