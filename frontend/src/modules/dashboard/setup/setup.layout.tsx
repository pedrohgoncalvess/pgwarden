import type { ReactNode } from "react";

type SetupLayoutProps = {
  step: string;
  title: string;
  children: ReactNode;
};

export function SetupLayout({ step, title, children }: SetupLayoutProps) {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-2 pb-6">
      <header className="mb-2 border-b border-border pb-6">
        <p className="sf-label font-mono text-accent-amber">{step}</p>
        <h1 className="mt-2 font-display text-3xl tracking-wide text-accent-cyan">{title}</h1>
      </header>
      {children}
    </div>
  );
}
