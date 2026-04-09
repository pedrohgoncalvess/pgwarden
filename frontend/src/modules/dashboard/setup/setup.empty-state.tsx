import type { ReactNode } from "react";
import { Database, Orbit, Server } from "lucide-react";

type SetupEmptyStateProps = {
  title: string;
  description: string;
  action?: ReactNode;
  variant?: "dashboard" | "servers" | "databases";
};

function EmptyStateArtwork({ variant }: { variant: NonNullable<SetupEmptyStateProps["variant"]> }) {
  if (variant === "servers") {
    return (
      <div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-borderStrong/70 bg-muted/30">
        <Server size={30} className="text-accent-cyan" />
        <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-accent-amber" />
        <span className="absolute -left-2 top-1/2 h-px w-5 -translate-y-1/2 bg-accent-cyan/60" />
      </div>
    );
  }

  if (variant === "databases") {
    return (
      <div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-borderStrong/70 bg-muted/30">
        <Database size={30} className="text-accent-cyan" />
        <span className="absolute -bottom-1 -right-1 h-2.5 w-2.5 rounded-full bg-accent-amber" />
        <span className="absolute -left-2 top-1/2 h-px w-5 -translate-y-1/2 bg-accent-cyan/60" />
      </div>
    );
  }

  return (
    <div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-borderStrong/70 bg-muted/30">
      <Orbit size={30} className="text-accent-cyan" />
      <span className="absolute -left-2 top-1/2 h-px w-5 -translate-y-1/2 bg-accent-cyan/60" />
      <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-accent-amber" />
    </div>
  );
}

export function SetupEmptyState({
  title,
  description,
  action,
  variant = "dashboard",
}: SetupEmptyStateProps) {
  return (
    <div className="rounded-lg border border-dashed border-borderStrong/70 bg-background/20 p-8 text-center">
      <div className="mx-auto mb-5 flex justify-center">
        <EmptyStateArtwork variant={variant} />
      </div>
      <p className="text-lg font-semibold text-foreground">{title}</p>
      <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{description}</p>
      {action ? <div className="mt-6 flex justify-center">{action}</div> : null}
    </div>
  );
}
