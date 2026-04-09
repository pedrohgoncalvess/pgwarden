import type { QueryRowSample } from "@/modules/dashboard/dashboard.metrics-sse";
import {
  formatMs,
  formatPct,
  type QueryCategoryFilter,
} from "@/modules/dashboard/dashboard.performance-stream";

type PerformanceQueryTableProps = {
  rows: QueryRowSample[];
  querySearch: string;
  onQuerySearchChange: (value: string) => void;
  queryCategory: QueryCategoryFilter;
  onQueryCategoryChange: (value: QueryCategoryFilter) => void;
};

function FilterButton({
  label,
  value,
  activeValue,
  onClick,
}: {
  label: string;
  value: QueryCategoryFilter;
  activeValue: QueryCategoryFilter;
  onClick: (value: QueryCategoryFilter) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(value)}
      className={`rounded-md border px-2 py-1 text-xs ${
        activeValue === value
          ? "border-borderStrong bg-muted/50 text-foreground"
          : "border-border text-muted-foreground"
      }`}
    >
      {label}
    </button>
  );
}

export function PerformanceQueryTable({
  rows,
  querySearch,
  onQuerySearchChange,
  queryCategory,
  onQueryCategoryChange,
}: PerformanceQueryTableProps) {
  return (
    <div className="mt-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <FilterButton label="All" value="all" activeValue={queryCategory} onClick={onQueryCategoryChange} />
          <FilterButton
            label="SELECT"
            value="select"
            activeValue={queryCategory}
            onClick={onQueryCategoryChange}
          />
          <FilterButton
            label="INSERT/UPDATE/DELETE"
            value="write"
            activeValue={queryCategory}
            onClick={onQueryCategoryChange}
          />
          <FilterButton label="DDL" value="ddl" activeValue={queryCategory} onClick={onQueryCategoryChange} />
        </div>
        <input
          className="app-input h-9 w-full max-w-[280px] py-1"
          placeholder="Search query/role..."
          value={querySearch}
          onChange={(event) => onQuerySearchChange(event.target.value)}
        />
      </div>

      <div className="max-h-[300px] overflow-auto rounded-md border border-border bg-background/25">
        <table className="min-w-full table-fixed border-collapse">
          <colgroup>
            <col className="w-[44%]" />
            <col className="w-[14%]" />
            <col className="w-[11%]" />
            <col className="w-[11%]" />
            <col className="w-[10%]" />
            <col className="w-[10%]" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-muted/70 backdrop-blur-sm">
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="truncate px-2 py-2">Query</th>
              <th className="truncate px-2 py-2">Role</th>
              <th className="truncate px-2 py-2 text-right">Avg Time (ms)</th>
              <th className="truncate px-2 py-2 text-right">Calls / Min</th>
              <th className="truncate px-2 py-2 text-right">% of All I/O</th>
              <th className="truncate px-2 py-2 text-right">% of Runtime</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-border/60 text-sm last:border-b-0">
                <td className="max-w-[460px] truncate px-2 py-2 text-foreground">{row.query}</td>
                <td className="px-2 py-2 text-muted-foreground">{row.role}</td>
                <td className="px-2 py-2 text-right text-foreground">{formatMs(row.avgMs)}</td>
                <td className="px-2 py-2 text-right text-foreground">{row.callsPerMin.toFixed(2)}</td>
                <td className="px-2 py-2 text-right text-foreground">{formatPct(row.ioPercent)}</td>
                <td className="px-2 py-2 text-right text-foreground">{formatPct(row.runtimePercent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 ? (
          <p className="px-3 py-3 text-sm text-muted-foreground">No query samples for selected filters.</p>
        ) : null}
      </div>
    </div>
  );
}
