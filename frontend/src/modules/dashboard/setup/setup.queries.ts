import { useQuery } from "@tanstack/react-query";
import { authSelectors, useAuthStore } from "@/modules/auth/auth.store";
import { dashboardQueries } from "@/modules/dashboard/dashboard.queries";

const DEFAULT_REFETCH_INTERVAL_MS = 5_000;

export function useSetupQueries() {
  const accessToken = useAuthStore(authSelectors.accessToken);

  const serversQuery = useQuery({
    ...dashboardQueries.servers(accessToken),
    refetchInterval: DEFAULT_REFETCH_INTERVAL_MS,
  });

  const databasesQuery = useQuery({
    ...dashboardQueries.databases(accessToken),
    refetchInterval: DEFAULT_REFETCH_INTERVAL_MS,
  });

  return {
    accessToken,
    serversQuery,
    databasesQuery,
    serversCount: serversQuery.data?.length ?? 0,
    databasesCount: databasesQuery.data?.length ?? 0,
  };
}
