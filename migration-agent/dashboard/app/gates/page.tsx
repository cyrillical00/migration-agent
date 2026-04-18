export default function GatesPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Gate Approvals</h1>
      <p className="text-muted-foreground text-sm">
        Seven gates (1-7). Each records approver, decision, and artifacts. No gate is skippable.
      </p>
      <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
        Gate decisions will appear here as phases progress.
      </div>
    </div>
  );
}
