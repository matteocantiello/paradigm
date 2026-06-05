import { create } from "zustand";

export type RightPanelTab = "events" | "knowledge" | "draft" | "experiments";

interface UiState {
  sidebarOpen: boolean;
  theme: "dark" | "light";
  rightPanelTab: RightPanelTab;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleTheme: () => void;
  setRightPanelTab: (tab: RightPanelTab) => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  theme: "dark",
  rightPanelTab: "events",
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      return { theme: next };
    }),
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
}));
