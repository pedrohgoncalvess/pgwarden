import { createRootRoute, createRoute, createRouter, redirect } from "@tanstack/react-router";
import { AppShell } from "@/app/app-shell";
import { AuthLoginPage } from "@/modules/auth/auth.login.page";
import { AuthRegisterPage } from "@/modules/auth/auth.register.page";
import { isSessionExpired, useAuthStore } from "@/modules/auth/auth.store";
import { DashboardPage } from "@/modules/dashboard/dashboard.page";
import { DashboardSetupDatabasesPage } from "@/modules/dashboard/setup/setup.databases.page";
import { DashboardSetupServersPage } from "@/modules/dashboard/setup/setup.servers.page";

const rootRoute = createRootRoute({
  component: AppShell,
});

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardPage,
  validateSearch: (search: Record<string, unknown>) => {
    const parsedSearch: { serverId?: string; dbId?: string } = {};
    if (typeof search.serverId === "string") {
      parsedSearch.serverId = search.serverId;
    }
    if (typeof search.dbId === "string") {
      parsedSearch.dbId = search.dbId;
    }
    return parsedSearch;
  },
  beforeLoad: () => {
    const authState = useAuthStore.getState();
    const session = authState.session;
    if (!session || isSessionExpired(session)) {
      authState.clearSession();
      throw redirect({ to: "/login" });
    }
  },
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: AuthLoginPage,
  beforeLoad: () => {
    const authState = useAuthStore.getState();
    const session = authState.session;
    if (session && !isSessionExpired(session)) {
      throw redirect({ to: "/" });
    }
    if (session && isSessionExpired(session)) {
      authState.clearSession();
    }
  },
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/register",
  component: AuthRegisterPage,
  beforeLoad: () => {
    const authState = useAuthStore.getState();
    const session = authState.session;
    if (session && !isSessionExpired(session)) {
      throw redirect({ to: "/" });
    }
    if (session && isSessionExpired(session)) {
      authState.clearSession();
    }
  },
});

const setupServersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/setup/servers",
  component: DashboardSetupServersPage,
  beforeLoad: () => {
    const authState = useAuthStore.getState();
    const session = authState.session;
    if (!session || isSessionExpired(session)) {
      authState.clearSession();
      throw redirect({ to: "/login" });
    }
  },
});

const setupDatabasesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/setup/databases",
  component: DashboardSetupDatabasesPage,
  beforeLoad: () => {
    const authState = useAuthStore.getState();
    const session = authState.session;
    if (!session || isSessionExpired(session)) {
      authState.clearSession();
      throw redirect({ to: "/login" });
    }
  },
});

const routeTree = rootRoute.addChildren([
  dashboardRoute,
  loginRoute,
  registerRoute,
  setupServersRoute,
  setupDatabasesRoute,
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
