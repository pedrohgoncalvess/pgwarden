import { wrap } from "comlink";
import type { MetricsWorkerApi } from "@/modules/dashboard/dashboard.metrics.worker";

export function createMetricsWorker() {
  const worker = new Worker(new URL("./dashboard.metrics.worker.ts", import.meta.url), {
    type: "module",
  });

  return {
    api: wrap<MetricsWorkerApi>(worker),
    terminate: () => worker.terminate(),
  };
}
