export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div data-testid="empty-state" className="rounded-card bg-surface px-4 py-8 text-center text-ink-muted">
      {children}
    </div>
  );
}
