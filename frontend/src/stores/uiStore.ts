import { create } from "zustand";

interface UiState {
  sidebarOpen: boolean;
  theme: "dark" | "light";
  eventLogVisible: boolean;
  rightPanelTab: "events" | "knowledge";
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleTheme: () => void;
  setEventLogVisible: (v: boolean) => void;
  setRightPanelTab: (tab: "events" | "knowledge") => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  theme: "dark",
  eventLogVisible: true,
  rightPanelTab: "events",
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      return { theme: next };
    }),
  setEventLogVisible: (v) => set({ eventLogVisible: v }),
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
}));
