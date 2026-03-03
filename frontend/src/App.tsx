import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Dashboard } from "@/pages/Dashboard";
import { ResearchPage } from "@/pages/ResearchPage";
import { SessionPage } from "@/pages/SessionPage";
import { PapersPage } from "@/pages/PapersPage";
import { AgentsPage } from "@/pages/AgentsPage";

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
              <Route path="papers" element={<PapersPage />} />
              <Route path="agents" element={<AgentsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
