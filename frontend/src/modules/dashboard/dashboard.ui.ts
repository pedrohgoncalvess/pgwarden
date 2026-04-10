export function formatApiError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    if (error.message.includes("Load failed") || error.message.includes("Failed to fetch")) {
      return "Could not reach the API. Check if backend is running and ENCRYPTION_KEY is configured.";
    }
    return error.message;
  }
  return fallback;
}

export function statusBadgeClass(status: string) {
  switch (status) {
    case "healthy":
      return "text-emerald-300 border-emerald-500/40 bg-emerald-500/15";
    case "pending":
      return "text-amber-300 border-amber-500/40 bg-amber-500/15";
    default:
      return "text-rose-300 border-rose-500/40 bg-rose-500/15";
  }
}
