import { create, type StateCreator } from "zustand";

type QueryTableSlice = {
  search: string;
  setSearch: (value: string) => void;
};

type DashboardUiSlice = {
  rowEstimate: number;
  setRowEstimate: (value: number) => void;
};

export type DashboardStore = QueryTableSlice & DashboardUiSlice;

const createQueryTableSlice: StateCreator<DashboardStore, [], [], QueryTableSlice> = (set) => ({
  search: "",
  setSearch: (search) => set((state) => (state.search === search ? state : { search })),
});

const createDashboardUiSlice: StateCreator<DashboardStore, [], [], DashboardUiSlice> = (set) => ({
  rowEstimate: 44,
  setRowEstimate: (rowEstimate) =>
    set((state) => (state.rowEstimate === rowEstimate ? state : { rowEstimate })),
});

export const useDashboardStore = create<DashboardStore>()((...args) => ({
  ...createQueryTableSlice(...args),
  ...createDashboardUiSlice(...args),
}));

export const dashboardSelectors = {
  search: (state: DashboardStore) => state.search,
  setSearch: (state: DashboardStore) => state.setSearch,
  rowEstimate: (state: DashboardStore) => state.rowEstimate,
};
