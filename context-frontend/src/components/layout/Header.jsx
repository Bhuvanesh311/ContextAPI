import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Search, Sun, Moon, Bell, ChevronDown, LogOut } from "lucide-react";
import "./Header.css";

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();

  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("inferai-theme") || "light";
    } catch {
      return "light";
    }
  });

  const [search, setSearch] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);

  let user = {};

  try {
    user = JSON.parse(sessionStorage.getItem("inferai_user") || "{}");
  } catch {
    user = {};
  }

  const displayName =
    user.username || user.name || user.email?.split("@")[0] || "Workspace User";

  useEffect(() => {
    document.documentElement.dataset.inferaiTheme = theme;

    try {
      localStorage.setItem("inferai-theme", theme);
    } catch {
      // Continue using the current theme if storage is unavailable.
    }
  }, [theme]);

  // Keep the Header synchronized with theme changes from Settings.
  useEffect(() => {
    function handleThemeChange(event) {
      const nextTheme = event.detail?.theme;

      if (nextTheme === "light" || nextTheme === "dark") {
        setTheme(nextTheme);
      }
    }

    window.addEventListener("inferai-theme-change", handleThemeChange);

    return () => {
      window.removeEventListener("inferai-theme-change", handleThemeChange);
    };
  }, []);

  useEffect(() => {
    setSearch("");
    setProfileOpen(false);
  }, [location.pathname]);

  function handleSearch(event) {
    event.preventDefault();

    const query = search.trim();

    if (!query) return;

   navigate(`/search?q=${encodeURIComponent(query)}`, {
     state: {
       from: `${location.pathname}${location.search}${location.hash}`,
     },
   });
  }

  function handleThemeToggle() {
    const nextTheme = theme === "light" ? "dark" : "light";

    setTheme(nextTheme);
    document.documentElement.dataset.inferaiTheme = nextTheme;

    try {
      localStorage.setItem("inferai-theme", nextTheme);
    } catch {
      // Keep the selected theme in React state.
    }

    window.dispatchEvent(
      new CustomEvent("inferai-theme-change", {
        detail: { theme: nextTheme },
      }),
    );
  }

  function handleLogout() {
    sessionStorage.removeItem("inferai_user");
    sessionStorage.removeItem("inferai_access_token");
    sessionStorage.removeItem("inferai_refresh_token");

    setProfileOpen(false);
    navigate("/", { replace: true });
  }

  return (
    <header className="infer-global-header">
      <form className="global-search" onSubmit={handleSearch}>
        <Search size={20} />

        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search projects, documents, or ask anything..."
          aria-label="Search ContextAPI"
        />

        <kbd>Ctrl K</kbd>
      </form>

      <div className="global-header-actions">
        <button
          className="global-icon-button"
          type="button"
          onClick={handleThemeToggle}
          aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
        >
          {theme === "light" ? <Moon size={21} /> : <Sun size={21} />}
        </button>

        <button
          className="global-icon-button notification-button"
          type="button"
          aria-label="Notifications"
          title="Notifications"
        >
          <Bell size={21} />
          <span className="notification-dot" />
        </button>

        <button
          className="global-profile"
          type="button"
          onClick={() => setProfileOpen((open) => !open)}
          aria-expanded={profileOpen}
          aria-label="Open account menu"
        >
          <span className="global-avatar">
            {displayName.slice(0, 2).toUpperCase()}
          </span>

          <span className="global-profile-copy">
            <strong>{displayName}</strong>
            <small>{user.role || "USER"}</small>
          </span>

          <ChevronDown size={17} />
        </button>

        {profileOpen && (
          <div className="global-profile-menu">
            <div className="profile-menu-heading">
              <strong>{displayName}</strong>
              <small>{user.email || ""}</small>
            </div>

            <button
              type="button"
              onClick={() => {
                setProfileOpen(false);
                navigate("/settings");
              }}
            >
              Account settings
            </button>

            <button type="button" onClick={handleLogout}>
              <LogOut size={16} />
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
