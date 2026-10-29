import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import AdminLogin from "./pages/auth/AdminLogin";
import AuthRegister from "./pages/auth/AuthRegister";
import AppLayout from "./components/layout/AppLayout";
import Dashboard from "./pages/dashboard/Dashboard";
import Projects from "./pages/projects/Projects";
import CreateProject from "./pages/projects/CreateProject";
import ProjectView from "./pages/projects/ProjectView";
import Knowledge from "./pages/knowledge/Knowledge";
import Settings from "./pages/settings/Settings";
import TargetApplications from "./pages/targetapplication/TargetApplications";
import Reports from "./pages/reports/Reports";
import SearchPage from "./pages/search/Search";

function ProtectedAdminRoute({ children }) {
  const user = sessionStorage.getItem("inferai_user");
  const token = sessionStorage.getItem("inferai_access_token");

  if (!user || !token) {
    return <Navigate to="/" replace />;
  }

  try {
    const currentUser = JSON.parse(user);

    if (currentUser.role?.toUpperCase() !== "USER") {
      sessionStorage.clear();
      return <Navigate to="/" replace />;
    }

    return children;
  } catch {
    sessionStorage.clear();
    return <Navigate to="/" replace />;
  }
}

function ForgotPassword() {
  return (
    <main style={{ padding: 40 }}>
      <h1>Forgot Password</h1>
      <p>We will connect this page to your password-reset APIs next.</p>
      <a href="/">Back to login</a>
    </main>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public authentication routes */}
        <Route path="/" element={<AdminLogin />} />
        <Route path="/login" element={<AdminLogin />} />
        <Route path="/register" element={<AuthRegister />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />

        {/* Protected application routes with shared sidebar */}
        <Route
          element={
            <ProtectedAdminRoute>
              <AppLayout />
            </ProtectedAdminRoute>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/create" element={<CreateProject />} />
          <Route path="/projects/:projectId" element={<ProjectView />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/target-applications" element={<TargetApplications />} />
          <Route path="/reports" element={<Reports />} />
          {/* Add your existing application pages here. */}
        </Route>

        {/* Unknown routes */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
