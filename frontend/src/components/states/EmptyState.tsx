export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div data-testid="empty-state" className="rounded-card bg-surface px-6 py-10 text-center text-ink-muted">
      {children}
    </div>
  );
}
