import type { ReactNode } from "react";

type SetupModalProps = {
  title: string;
  description: string;
  onClose: () => void;
  children: ReactNode;
};

export function SetupModal({ title, description, onClose, children }: SetupModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-xl border border-borderStrong bg-card/95 p-5 shadow-panel"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-foreground">{title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          </div>
          <button
            type="button"
            className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition hover:border-borderStrong hover:text-foreground"
            onClick={onClose}
          >
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
