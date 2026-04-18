export default function InventoryPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Inventory</h1>
      <p className="text-muted-foreground text-sm">
        Source and target entity inventory. Available after Step 2 (discovery) runs.
      </p>
      <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
        Run Phase 1 discovery to populate this view.
      </div>
    </div>
  );
}
