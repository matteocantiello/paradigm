import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Dashboard } from "@/pages/Dashboard";
import { ResearchPage } from "@/pages/ResearchPage";
import { SessionPage } from "@/pages/SessionPage";
import ReplayPage from "@/pages/ReplayPage";
import { PapersPage } from "@/pages/PapersPage";
import { AgentsPage } from "@/pages/AgentsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { AboutPage } from "@/pages/AboutPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Dashboard />} />
              <Route path="research" element={<ResearchPage />} />
              <Route path="session/:id" element={<SessionPage />} />
              <Route path="replay/:id" element={<ReplayPage />} />
              <Route path="papers" element={<PapersPage />} />
              <Route path="agents" element={<AgentsPage />} />
              <Route path="about" element={<AboutPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route
                path="*"
                element={
                  <div className="flex flex-col items-center justify-center py-24 text-center">
                    <h1 className="text-4xl font-bold mb-2">404</h1>
                    <p className="text-muted-foreground mb-4">Page not found</p>
                    <Link
                      to="/"
                      className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      Back to Dashboard
                    </Link>
                  </div>
                }
              />
            </Route>
          </Routes>
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
