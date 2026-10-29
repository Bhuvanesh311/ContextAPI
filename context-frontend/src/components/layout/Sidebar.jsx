import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FolderKanban,
  BookOpen,
  AppWindow,
  FileText,
  CloudUpload,
  ChartNoAxesColumn,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";

import "./Sidebar.css";

const sections = [
  {
    label: "WORKSPACE",
    items: [
      { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
      { label: "Projects", to: "/projects", icon: FolderKanban },
      { label: "Knowledge", to: "/knowledge", icon: BookOpen },
      {
        label: "Target Applications",
        to: "/target-applications",
        icon: AppWindow,
      },
    ],
  },
  {
    label: "INSIGHTS",
    items: [
      { label: "Reports", to: "/reports", icon: ChartNoAxesColumn },
      { label: "Settings", to: "/settings", icon: Settings },
    ],
  },
];

export default function Sidebar({ collapsed, onToggle }) {
  return (
    <aside className={`infer-sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <div className="sidebar-brand-row">
        <NavLink
          to="/dashboard"
          className="sidebar-brand"
          aria-label="ContextAPI dashboard"
        >
          <img
            src="/images/inferai-orbital-mark.png"
            alt="ContextAPI orbital logo"
          />

          {!collapsed && (
            <span>
              Context<span className="brand-ai">API</span>
            </span>
          )}
        </NavLink>

        <button
          type="button"
          className="sidebar-collapse"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpen size={18} />
          ) : (
            <PanelLeftClose size={18} />
          )}
        </button>
      </div>

      <nav className="sidebar-navigation" aria-label="Main navigation">
        {sections.map((section) => (
          <section className="sidebar-group" key={section.label}>
            {!collapsed && (
              <p className="sidebar-group-label">{section.label}</p>
            )}

            {section.items.map(({ label, to, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                title={collapsed ? label : undefined}
                className={({ isActive }) =>
                  `sidebar-link ${isActive ? "active" : ""}`
                }
              >
                <Icon size={19} strokeWidth={1.8} />
                {!collapsed && <span>{label}</span>}
              </NavLink>
            ))}
          </section>
        ))}
      </nav>

      {!collapsed && (
        <div className="sidebar-promo">
          <div className="promo-orb">
            <img src="/images/inferai-orbital-mark.png" alt="" />
          </div>

          <p>Knowledge flows further with AI.</p>
          <span>YOUR ENTERPRISE, CONNECTED</span>
        </div>
      )}

      <div className="sidebar-bottom">
        <span className="status-dot" />
        {!collapsed && <span>Workspace ready</span>}
      </div>
    </aside>
  );
}
