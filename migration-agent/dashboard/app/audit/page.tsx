export default function AuditPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>
      <p className="text-muted-foreground text-sm">
        Immutable append-only log. All agent actions and state transitions recorded here.
      </p>
      <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
        Audit entries will appear here as the agent runs.
      </div>
    </div>
  );
}
