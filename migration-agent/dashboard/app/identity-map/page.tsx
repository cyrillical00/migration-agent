export default function IdentityMapPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Identity Map</h1>
      <p className="text-muted-foreground text-sm">
        LLM-proposed, human-confirmed identity mappings. Available after Step 3.
      </p>
      <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
        Identity mapping runs in Phase 2.
      </div>
    </div>
  );
}
