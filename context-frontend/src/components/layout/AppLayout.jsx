import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";
import FloatingAssistant from "../assistant/FloatingAssistant";
import "./AppLayout.css";

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);

  const handleSidebarToggle = () => {
    setCollapsed((previous) => !previous);
  };

  return (
    <div className={`infer-app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <Sidebar collapsed={collapsed} onToggle={handleSidebarToggle} />

      <Header />

      <div className="infer-app-content">
        <Outlet />
      </div>

      <FloatingAssistant />
    </div>
  );
}
