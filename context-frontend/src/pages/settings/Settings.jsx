import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  UserRound,
  ShieldCheck,
  Palette,
  LockKeyhole,
  LogOut,
  Sun,
  Moon,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  LoaderCircle,
  X,
} from "lucide-react";

import "./Settings.css";
import { apiFetch } from "../../services/api";

export default function Settings() {
  const navigate = useNavigate();

  const [user] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem("inferai_user") || "{}");
    } catch {
      return {};
    }
  });

  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("inferai-theme") || "light";
    } catch {
      return "light";
    }
  });

  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState(null);

  const displayName =
    user.username || user.name || user.email?.split("@")[0] || "Workspace User";

  // Apply the same theme used by Header.jsx.
  useEffect(() => {
    document.documentElement.dataset.inferaiTheme = theme;

    try {
      localStorage.setItem("inferai-theme", theme);
    } catch {
      // Theme remains active for the current page.
    }

    window.dispatchEvent(
      new CustomEvent("inferai-theme-change", {
        detail: { theme },
      }),
    );
  }, [theme]);

  function changeTheme(nextTheme) {
    if (nextTheme !== "light" && nextTheme !== "dark") return;

    setTheme(nextTheme);
  }

  function openPasswordModal() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setShowPasswords(false);
    setPasswordMessage(null);
    setPasswordModalOpen(true);
  }

  function closePasswordModal() {
    if (savingPassword) return;

    setPasswordModalOpen(false);
    setPasswordMessage(null);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setShowPasswords(false);
  }

  // Close the modal with Escape.
  useEffect(() => {
    if (!passwordModalOpen) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape" && !savingPassword) {
        closePasswordModal();
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [passwordModalOpen, savingPassword]);

  async function handleChangePassword(event) {
    event.preventDefault();
    setPasswordMessage(null);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordMessage({
        type: "error",
        text: "Please complete all password fields.",
      });
      return;
    }

    if (newPassword.length < 8) {
      setPasswordMessage({
        type: "error",
        text: "Your new password must contain at least 8 characters.",
      });
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordMessage({
        type: "error",
        text: "Your new password and confirmation do not match.",
      });
      return;
    }

    if (currentPassword === newPassword) {
      setPasswordMessage({
        type: "error",
        text: "Choose a password different from your current password.",
      });
      return;
    }

    setSavingPassword(true);

    try {
      const response = await apiFetch("/auth/change-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          old_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        let message = `Unable to change password (${response.status}).`;

        if (Array.isArray(result.detail)) {
          message = result.detail
            .map((error) => {
              const field = Array.isArray(error.loc)
                ? error.loc.filter((part) => part !== "body").join(".")
                : "";

              const description =
                typeof error.msg === "string" ? error.msg : "Invalid value";

              return field ? `${field}: ${description}` : description;
            })
            .join(" | ");
        } else if (typeof result.detail === "string") {
          message = result.detail;
        } else if (typeof result.message === "string") {
          message = result.message;
        }

        throw new Error(message);
      }

      setPasswordMessage({
        type: "success",
        text: result.message || "Password changed successfully.",
      });

      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setShowPasswords(false);

      // Close only after the backend confirms success.
      window.setTimeout(() => {
        setPasswordModalOpen(false);
        setPasswordMessage(null);
      }, 1200);
    } catch (error) {
      setPasswordMessage({
        type: "error",
        text: error.message || "Unable to change your password.",
      });
    } finally {
      setSavingPassword(false);
    }
  }

  function handleSignOut() {
    sessionStorage.removeItem("inferai_user");
    sessionStorage.removeItem("inferai_access_token");
    sessionStorage.removeItem("inferai_refresh_token");

    navigate("/", { replace: true });
  }

  return (
    <main className="infer-account-settings">
      <header className="account-settings-heading">
        <div>
          <span className="account-settings-eyebrow">
            WORKSPACE PREFERENCES
          </span>

          <h1>Account Settings</h1>

          <p>Manage your account, security, and ContextAPI appearance.</p>
        </div>

        <div className="account-security-badge">
          <ShieldCheck size={17} />
          Account security
        </div>
      </header>

      <section className="account-settings-grid">
        <div className="account-settings-main">
          <article className="account-settings-card">
            <div className="account-section-heading">
              <span className="account-section-icon">
                <UserRound size={21} />
              </span>

              <div>
                <h2>Account information</h2>
                <p>Your current ContextAPI account details.</p>
              </div>
            </div>

            <div className="account-profile">
              <div className="account-profile-avatar">
                {displayName.slice(0, 2).toUpperCase()}
              </div>

              <div className="account-profile-details">
                <h3>{displayName}</h3>
                <p>{user.email || "Email not available"}</p>

                <span className="account-role">{user.role || "USER"}</span>
              </div>
            </div>

            <div className="account-info-row">
              <span>Username</span>
              <strong>{user.username || user.name || "Not available"}</strong>
            </div>

            <div className="account-info-row">
              <span>Email address</span>
              <strong>{user.email || "Not available"}</strong>
            </div>

            <div className="account-info-row">
              <span>Account role</span>
              <strong>{user.role || "USER"}</strong>
            </div>
          </article>

          <article className="account-settings-card">
            <div className="account-section-heading">
              <span className="account-section-icon">
                <LockKeyhole size={21} />
              </span>

              <div>
                <h2>Password & security</h2>
                <p>Protect your account with a secure password.</p>
              </div>
            </div>

            <div className="account-password-summary">
              <div>
                <strong>Account password</strong>
                <p>Change your password whenever you need to.</p>
              </div>

              <button
                type="button"
                className="account-primary-button"
                onClick={openPasswordModal}
              >
                <LockKeyhole size={17} />
                Change password
              </button>
            </div>
          </article>
        </div>

        <aside className="account-settings-side">
          <article className="account-settings-card">
            <div className="account-section-heading">
              <span className="account-section-icon">
                <Palette size={21} />
              </span>

              <div>
                <h2>Appearance</h2>
                <p>Personalize your workspace.</p>
              </div>
            </div>

            <div className="account-theme-options">
              <button
                type="button"
                className={`account-theme-option ${
                  theme === "light" ? "active" : ""
                }`}
                onClick={() => changeTheme("light")}
                aria-pressed={theme === "light"}
              >
                <Sun size={19} />

                <span className="account-theme-copy">
                  <strong>Light mode</strong>
                  <small>Bright and clean</small>
                </span>

                <span className="account-theme-radio" />
              </button>

              <button
                type="button"
                className={`account-theme-option ${
                  theme === "dark" ? "active" : ""
                }`}
                onClick={() => changeTheme("dark")}
                aria-pressed={theme === "dark"}
              >
                <Moon size={19} />

                <span className="account-theme-copy">
                  <strong>Dark mode</strong>
                  <small>Comfortable in low light</small>
                </span>

                <span className="account-theme-radio" />
              </button>
            </div>

            <p className="account-appearance-note">
              Your selection is saved in this browser and synchronized with the
              Header theme button.
            </p>
          </article>

          <article className="account-security-card">
            <span className="account-security-symbol">
              <ShieldCheck size={25} />
            </span>

            <h2>Keep your account secure</h2>

            <p>
              Use a unique password and sign out when using a shared computer.
            </p>
          </article>

          <article className="account-settings-card account-signout-card">
            <div className="account-section-heading">
              <span className="account-section-icon account-signout-icon">
                <LogOut size={21} />
              </span>

              <div>
                <h2>Sign out</h2>
                <p>End your current ContextAPI session.</p>
              </div>
            </div>

            <button
              type="button"
              className="account-signout-button"
              onClick={handleSignOut}
            >
              <LogOut size={17} />
              Sign out of ContextAPI
            </button>
          </article>
        </aside>
      </section>

      <footer className="account-settings-footer">
        CONTEXTAPI <span>•</span> ENTERPRISE AI ASSISTANT
      </footer>

      {passwordModalOpen && (
        <div
          className="account-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closePasswordModal();
            }
          }}
        >
          <section
            className="account-password-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="change-password-title"
          >
            <header className="account-modal-heading">
              <div className="account-modal-icon">
                <LockKeyhole size={22} />
              </div>

              <button
                type="button"
                className="account-modal-close"
                aria-label="Close dialog"
                disabled={savingPassword}
                onClick={closePasswordModal}
              >
                <X size={20} />
              </button>

              <h2 id="change-password-title">Change password</h2>

              <p>
                Enter your current password and choose a new secure password for
                your account.
              </p>
            </header>

            <form
              className="account-password-form"
              onSubmit={handleChangePassword}
            >
              <label>
                Current password
                <input
                  type={showPasswords ? "text" : "password"}
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  placeholder="Enter current password"
                  required
                />
              </label>

              <label>
                New password
                <input
                  type={showPasswords ? "text" : "password"}
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  placeholder="At least 8 characters"
                  minLength={8}
                  required
                />
              </label>

              <label>
                Confirm new password
                <input
                  type={showPasswords ? "text" : "password"}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="Re-enter new password"
                  minLength={8}
                  required
                />
              </label>

              <button
                type="button"
                className="account-show-password"
                onClick={() => setShowPasswords((value) => !value)}
              >
                {showPasswords ? <EyeOff size={16} /> : <Eye size={16} />}

                {showPasswords ? "Hide passwords" : "Show passwords"}
              </button>

              {passwordMessage && (
                <div
                  className={`account-password-message ${passwordMessage.type}`}
                  role="status"
                >
                  {passwordMessage.type === "success" ? (
                    <CheckCircle2 size={18} />
                  ) : (
                    <AlertCircle size={18} />
                  )}

                  <span>{passwordMessage.text}</span>
                </div>
              )}

              <div className="account-modal-actions">
                <button
                  type="button"
                  className="account-modal-cancel"
                  disabled={savingPassword}
                  onClick={closePasswordModal}
                >
                  Cancel
                </button>

                <button
                  className="account-primary-button"
                  type="submit"
                  disabled={savingPassword}
                >
                  {savingPassword ? (
                    <>
                      <LoaderCircle size={17} className="account-spinner" />
                      Updating...
                    </>
                  ) : (
                    <>
                      <LockKeyhole size={17} />
                      Update password
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
