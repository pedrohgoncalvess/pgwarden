import { queryOptions } from "@tanstack/react-query";
import { getDatabaseSchema, listDatabases, listServers } from "@/modules/dashboard/dashboard.api";

const DASHBOARD_QUERY_KEY = ["dashboard"] as const;

const dashboardKeys = {
  all: () => DASHBOARD_QUERY_KEY,
  servers: (authState: "authenticated" | "anonymous") =>
    [...dashboardKeys.all(), "servers", authState] as const,
  databases: (authState: "authenticated" | "anonymous") =>
    [...dashboardKeys.all(), "databases", authState] as const,
  schema: (databaseId: string, authState: "authenticated" | "anonymous") =>
    [...dashboardKeys.all(), "schema", databaseId, authState] as const,
};

export const dashboardQueries = {
  servers: (token: string | null) =>
    queryOptions({
      queryKey: dashboardKeys.servers(token ? "authenticated" : "anonymous"),
      queryFn: () => listServers(token ?? undefined),
    }),
  databases: (token: string | null) =>
    queryOptions({
      queryKey: dashboardKeys.databases(token ? "authenticated" : "anonymous"),
      queryFn: () => listDatabases(token ?? undefined),
    }),
  schema: (databaseId: string, token: string | null) =>
    queryOptions({
      queryKey: dashboardKeys.schema(databaseId, token ? "authenticated" : "anonymous"),
      queryFn: () => getDatabaseSchema(databaseId, token ?? undefined),
      staleTime: 30_000,
    }),
};
