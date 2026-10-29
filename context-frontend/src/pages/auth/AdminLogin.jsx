import { useState } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Eye,
  EyeOff,
  Mail,
  LockKeyhole,
  ShieldCheck,
  UserRound,
  UserPlus,
  KeyRound,
} from "lucide-react";

import {
  loginAdmin,
  registerUser,
  verifyEmail,
  resendVerificationOTP,
  forgotPassword,
  resetPassword,
} from "../../services/authService";

import "./AdminLogin.css";

// Orbital mark + live text, so the product name is never baked into an image.
function BrandWordmark({ className = "" }) {
  return (
    <span className={`brand-wordmark ${className}`} role="img" aria-label="ContextAPI">
      <img src="/images/inferai-orbital-mark.png" alt="" />
      <span className="brand-wordmark-text">
        <span className="brand-wordmark-name">
          Context<em>API</em>
        </span>
        <small>Enterprise AI Assistant</small>
      </span>
    </span>
  );
}

export default function AdminLogin() {
  const [view, setView] = useState("login");

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otp, setOtp] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  function switchView(nextView) {
    setView(nextView);
    setError("");
    setMessage("");
    setOtp("");
    setPassword("");
    setConfirmPassword("");
    setShowPassword(false);
  }

  function getErrorMessage(err, fallback) {
    const detail = err.response?.data?.detail;

    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;

    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg).join(", ");
    }

    return fallback;
  }

  async function handleLogin(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (!email.trim() || !password) {
      setError("Enter your email address and password.");
      return;
    }

    setLoading(true);

    try {
      const data = await loginAdmin(email.trim(), password);

      if (data?.user?.role?.toUpperCase() !== "USER") {
        setError("This account does not have the required access.");
        return;
      }

      if (!data?.tokens?.access_token || !data?.tokens?.refresh_token) {
        setError("The server returned an incomplete login response.");
        return;
      }

      sessionStorage.setItem("inferai_access_token", data.tokens.access_token);

      sessionStorage.setItem(
        "inferai_refresh_token",
        data.tokens.refresh_token,
      );

      sessionStorage.setItem("inferai_user", JSON.stringify(data.user));

      window.location.assign("/dashboard");
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "Unable to sign in. Check your details and try again.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (username.trim().length < 3 || username.trim().length > 30) {
      setError("Username must contain 3–30 characters.");
      return;
    }

    if (password.length < 8 || password.length > 128) {
      setError("Password must contain 8–128 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      const result = await registerUser({
        username: username.trim(),
        email: email.trim(),
        password,
        confirm_password: confirmPassword,
      });

      setEmail(result.email || email.trim());
      setPassword("");
      setConfirmPassword("");
      setView("verify-email");
      setMessage(
        result.message ||
          "Account created. Check your email for the verification code.",
      );
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "Unable to create your account. Please try again.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyEmail(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (!/^\d{6}$/.test(otp)) {
      setError("Enter the 6-digit verification code.");
      return;
    }

    setLoading(true);

    try {
      const result = await verifyEmail(email.trim(), otp);
      setView("login");
      setOtp("");
      setPassword("");
      setMessage(result.message || "Email verified. You can now sign in.");
    } catch (err) {
      setError(
        getErrorMessage(err, "Email verification failed. Check the code."),
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleResendOTP() {
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const result = await resendVerificationOTP(email.trim());
      setMessage(
        result.message || "A new verification code has been requested.",
      );
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "Unable to resend the code. Please try again later.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleForgotPassword(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (!email.trim()) {
      setError("Enter your email address.");
      return;
    }

    setLoading(true);

    try {
      const result = await forgotPassword(email.trim());
      setView("reset-password");
      setOtp("");
      setPassword("");
      setConfirmPassword("");
      setMessage(
        result.message ||
          "If the request succeeds, check your email for the reset code.",
      );
    } catch (err) {
      setError(getErrorMessage(err, "Unable to request a password reset."));
    } finally {
      setLoading(false);
    }
  }

  async function handleResetPassword(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (!/^\d{6}$/.test(otp)) {
      setError("Enter the 6-digit reset code.");
      return;
    }

    if (password.length < 8 || password.length > 128) {
      setError("Password must contain 8–128 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      const result = await resetPassword({
        email: email.trim(),
        otp,
        new_password: password,
        confirm_password: confirmPassword,
      });

      setView("login");
      setOtp("");
      setPassword("");
      setConfirmPassword("");
      setMessage(
        result.message || "Password reset successfully. Please sign in.",
      );
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "Unable to reset your password. Check the code and try again.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  const titles = {
    login: {
      badge: "ADMINISTRATOR ACCESS",
      title: "Welcome Back",
      description: "Sign in to your ContextAPI workspace.",
    },
    register: {
      badge: "JOIN CONTEXTAPI",
      title: "Create Account",
      description: "Create your account to get started.",
    },
    "verify-email": {
      badge: "EMAIL VERIFICATION",
      title: "Verify Your Email",
      description: "Enter the 6-digit code sent to your email.",
    },
    "forgot-password": {
      badge: "ACCOUNT RECOVERY",
      title: "Forgot Password?",
      description: "Enter your email to request a reset code.",
    },
    "reset-password": {
      badge: "SECURE YOUR ACCOUNT",
      title: "Reset Password",
      description: "Enter your reset code and choose a new password.",
    },
  };

  const heading = titles[view];

  return (
    <main className="login-page">
      <section className="login-visual">
        <div className="visual-overlay" />

        <div className="visual-brand">
          <BrandWordmark className="brand-logo" />
        </div>

        <div className="visual-copy">
          <span className="eyebrow">INTELLIGENCE, REIMAGINED</span>
          <h1>
            Knowledge
            <br />
            Flows Further
            <br />
            with AI
          </h1>
          <p>
            Secure <span>•</span> Intelligent <span>•</span> Simplified
          </p>
        </div>

        <div className="visual-footer">
          <ShieldCheck size={17} />
          <span>Enterprise AI Assistant</span>
        </div>
      </section>

      <section className="login-workspace">
        <div className={`login-card auth-card auth-view-${view}`}>
          <div className="mobile-brand">
            <BrandWordmark />
          </div>

          {view !== "login" && (
            <button
              type="button"
              className="auth-back-button"
              onClick={() => switchView("login")}
            >
              <ArrowLeft size={16} />
              Back to Sign In
            </button>
          )}

          <div className="card-heading">
            <span className="admin-badge">
              {view === "register" ? (
                <UserPlus size={15} />
              ) : view === "forgot-password" || view === "reset-password" ? (
                <KeyRound size={15} />
              ) : view === "verify-email" ? (
                <Mail size={15} />
              ) : (
                <ShieldCheck size={15} />
              )}
              {heading.badge}
            </span>

            <h2>{heading.title}</h2>
            <p>{heading.description}</p>
          </div>

          {message && (
            <div className="auth-message auth-success" role="status">
              {message}
            </div>
          )}

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          {view === "login" && (
            <form onSubmit={handleLogin}>
              <div className="field-group">
                <label htmlFor="login-email">Email Address</label>
                <div className="input-shell">
                  <Mail size={19} />
                  <input
                    id="login-email"
                    type="email"
                    autoComplete="username"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="login-password">Password</label>
                <div className="input-shell">
                  <LockKeyhole size={19} />
                  <input
                    id="login-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                  >
                    {showPassword ? <EyeOff size={19} /> : <Eye size={19} />}
                  </button>
                </div>
              </div>

              <div className="form-options">
                <label className="remember-option">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                  />
                  <span>Remember me</span>
                </label>
                <button
                  type="button"
                  className="auth-text-link"
                  onClick={() => switchView("forgot-password")}
                >
                  Forgot password?
                </button>
              </div>

              <button
                className="sign-in-button"
                type="submit"
                disabled={loading}
              >
                <span>{loading ? "Signing in..." : "Sign In"}</span>
                {!loading && <ArrowRight size={19} />}
              </button>
            </form>
          )}

          {view === "register" && (
            <form onSubmit={handleRegister}>
              <div className="field-group">
                <label htmlFor="register-username">Username</label>
                <div className="input-shell">
                  <UserRound size={19} />
                  <input
                    id="register-username"
                    type="text"
                    autoComplete="username"
                    placeholder="Choose a username"
                    value={username}
                    minLength={3}
                    maxLength={30}
                    onChange={(event) => setUsername(event.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="register-email">Email Address</label>
                <div className="input-shell">
                  <Mail size={19} />
                  <input
                    id="register-email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="register-password">Password</label>
                <div className="input-shell">
                  <LockKeyhole size={19} />
                  <input
                    id="register-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="Create a password"
                    minLength={8}
                    maxLength={128}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                  >
                    {showPassword ? <EyeOff size={19} /> : <Eye size={19} />}
                  </button>
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="register-confirm-password">
                  Confirm Password
                </label>
                <div className="input-shell">
                  <LockKeyhole size={19} />
                  <input
                    id="register-confirm-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="Re-enter your password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    required
                  />
                </div>
              </div>

              <button
                className="sign-in-button"
                type="submit"
                disabled={loading}
              >
                <span>
                  {loading ? "Creating account..." : "Create Account"}
                </span>
                {!loading && <ArrowRight size={19} />}
              </button>
            </form>
          )}

          {view === "verify-email" && (
            <form onSubmit={handleVerifyEmail}>
              <div className="field-group">
                <label htmlFor="verify-otp">6-Digit Verification Code</label>
                <div className="input-shell">
                  <KeyRound size={19} />
                  <input
                    id="verify-otp"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="Enter 6-digit code"
                    maxLength={6}
                    value={otp}
                    onChange={(event) =>
                      setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    required
                  />
                </div>
              </div>

              <button
                className="sign-in-button"
                type="submit"
                disabled={loading}
              >
                <span>{loading ? "Verifying..." : "Verify Email"}</span>
                {!loading && <ArrowRight size={19} />}
              </button>

              <button
                type="button"
                className="auth-secondary-button"
                onClick={handleResendOTP}
                disabled={loading}
              >
                Resend verification code
              </button>
            </form>
          )}

          {view === "forgot-password" && (
            <form onSubmit={handleForgotPassword}>
              <div className="field-group">
                <label htmlFor="forgot-email">Email Address</label>
                <div className="input-shell">
                  <Mail size={19} />
                  <input
                    id="forgot-email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
              </div>

              <button
                className="sign-in-button"
                type="submit"
                disabled={loading}
              >
                <span>{loading ? "Sending code..." : "Send Reset Code"}</span>
                {!loading && <ArrowRight size={19} />}
              </button>
            </form>
          )}

          {view === "reset-password" && (
            <form onSubmit={handleResetPassword}>
              <div className="field-group">
                <label htmlFor="reset-otp">6-Digit Reset Code</label>
                <div className="input-shell">
                  <KeyRound size={19} />
                  <input
                    id="reset-otp"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="Enter 6-digit code"
                    maxLength={6}
                    value={otp}
                    onChange={(event) =>
                      setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    required
                  />
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="reset-password">New Password</label>
                <div className="input-shell">
                  <LockKeyhole size={19} />
                  <input
                    id="reset-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="Enter new password"
                    minLength={8}
                    maxLength={128}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                  >
                    {showPassword ? <EyeOff size={19} /> : <Eye size={19} />}
                  </button>
                </div>
              </div>

              <div className="field-group">
                <label htmlFor="reset-confirm-password">
                  Confirm New Password
                </label>
                <div className="input-shell">
                  <LockKeyhole size={19} />
                  <input
                    id="reset-confirm-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="Re-enter new password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    required
                  />
                </div>
              </div>

              <button
                className="sign-in-button"
                type="submit"
                disabled={loading}
              >
                <span>{loading ? "Resetting..." : "Reset Password"}</span>
                {!loading && <ArrowRight size={19} />}
              </button>
            </form>
          )}

          {view === "login" && (
            <>
              <div className="security-note">
                <ShieldCheck size={16} />
                <span>Your connection is protected</span>
              </div>

              <div className="create-account">
                <span>Don't have an account?</span>
                <button
                  type="button"
                  className="auth-text-link"
                  onClick={() => switchView("register")}
                >
                  Create Account
                </button>
              </div>

              <p className="login-caption">
                Access is restricted to authorized administrators.
              </p>
            </>
          )}

          {view === "register" && (
            <p className="auth-bottom-note">
              Already have an account?{" "}
              <button
                type="button"
                className="auth-text-link"
                onClick={() => switchView("login")}
              >
                Sign In
              </button>
            </p>
          )}

          {view === "forgot-password" && (
            <p className="auth-bottom-note">
              Remember your password?{" "}
              <button
                type="button"
                className="auth-text-link"
                onClick={() => switchView("login")}
              >
                Sign In
              </button>
            </p>
          )}

          {view === "verify-email" && (
            <p className="auth-bottom-note">
              Verified already?{" "}
              <button
                type="button"
                className="auth-text-link"
                onClick={() => switchView("login")}
              >
                Sign In
              </button>
            </p>
          )}

          {view === "reset-password" && (
            <p className="auth-bottom-note">
              Want to try again?{" "}
              <button
                type="button"
                className="auth-text-link"
                onClick={() => switchView("forgot-password")}
              >
                Request another code
              </button>
            </p>
          )}
        </div>

        <footer className="workspace-footer">
          CONTEXTAPI <span>•</span> ENTERPRISE AI ASSISTANT
        </footer>
      </section>
    </main>
  );
}
