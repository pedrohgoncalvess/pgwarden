import { expose } from "comlink";

type Point = {
  timestamp: number;
  value: number;
};

type AggregateInput = {
  points: Point[];
  maxPoints?: number;
};

const api = {
  aggregateSeries(input: AggregateInput) {
    const maxPoints = input.maxPoints ?? 1_000;
    if (input.points.length <= maxPoints) {
      return input.points;
    }

    const bucketSize = Math.ceil(input.points.length / maxPoints);
    const output: Point[] = [];
    for (let i = 0; i < input.points.length; i += bucketSize) {
      const bucket = input.points.slice(i, i + bucketSize);
      const avg =
        bucket.reduce((sum, point) => sum + point.value, 0) / Math.max(bucket.length, 1);
      output.push({
        timestamp: bucket[0]?.timestamp ?? Date.now(),
        value: Number(avg.toFixed(2)),
      });
    }
    return output;
  },
};

expose(api);

export type MetricsWorkerApi = typeof api;
