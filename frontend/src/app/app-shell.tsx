import { useEffect } from "react";
import { Outlet, Link, useNavigate } from "@tanstack/react-router";
import { cn } from "@/lib/cn";
import {
  authSelectors,
  getAccessTokenExpiresAtMs,
  isSessionExpired,
  useAuthStore,
} from "@/modules/auth/auth.store";

const navLinkClassName = cn(
  "sf-label font-mono text-foreground/90 transition-colors",
  "hover:text-primary"
);

export function AppShell() {
  const navigate = useNavigate();
  const session = useAuthStore(authSelectors.session);
  const isAuthenticated = useAuthStore(authSelectors.isAuthenticated);
  const clearSession = useAuthStore(authSelectors.clearSession);

  useEffect(() => {
    if (!session) {
      return;
    }

    if (isSessionExpired(session)) {
      clearSession();
      void navigate({ to: "/login" });
      return;
    }

    const expiresAtMs = getAccessTokenExpiresAtMs(session);
    const timeoutMs = Math.max(expiresAtMs - Date.now(), 0);
    const timeoutId = window.setTimeout(() => {
      clearSession();
      void navigate({ to: "/login" });
    }, timeoutMs);

    return () => window.clearTimeout(timeoutId);
  }, [session, clearSession, navigate]);

  const handleLogout = async () => {
    clearSession();
    await navigate({ to: "/login" });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card/70 backdrop-blur">
        <div className="container flex w-full items-center justify-between gap-4 py-3">
          <div className="flex items-center gap-6">
            <span className="font-display text-sm tracking-hud text-accent-amber">PGWARDEN</span>
            {isAuthenticated ? (
              <>
                <Link className={navLinkClassName} to="/">
                  Dashboard
                </Link>
                <Link className={navLinkClassName} to="/setup/servers">
                  Servers
                </Link>
                <Link className={navLinkClassName} to="/setup/databases">
                  Databases
                </Link>
              </>
            ) : null}
            {!isAuthenticated ? (
              <>
                <Link className={navLinkClassName} to="/login">
                  Login
                </Link>
                <Link className={navLinkClassName} to="/register">
                  Register
                </Link>
              </>
            ) : null}
          </div>

          {isAuthenticated ? (
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md border border-border px-3 py-1.5 font-mono text-xs uppercase tracking-hud text-foreground/90 transition hover:border-borderStrong hover:bg-muted/60"
            >
              Logout
            </button>
          ) : null}
        </div>
      </header>
      <main className="container py-6">
        <Outlet />
      </main>
    </div>
  );
}