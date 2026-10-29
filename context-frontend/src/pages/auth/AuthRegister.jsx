import { useState } from "react";
import { Link } from "react-router-dom";
import { registerUser } from "../../services/authService";
import "./AuthRegister.css";

export default function AuthRegister() {
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    confirm_password: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));

    setError("");
    setSuccess("");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (form.username.trim().length < 3 || form.username.trim().length > 30) {
      setError("Username must contain 3–30 characters.");
      return;
    }

    if (form.password.length < 8 || form.password.length > 128) {
      setError("Password must contain 8–128 characters.");
      return;
    }

    if (form.password !== form.confirm_password) {
      setError("Passwords do not match.");
      return;
    }

    try {
      setLoading(true);

      const result = await registerUser({
        ...form,
        username: form.username.trim(),
        email: form.email.trim(),
      });

      setSuccess(
        result.message || "Account created. Please verify your email.",
      );

      // Navigate to email verification after successful registration.
      window.location.href = `/verify-email?email=${encodeURIComponent(result.email || form.email.trim())}`;
    } catch (err) {
      const detail = err.response?.data?.detail;

      setError(
        typeof detail === "string"
          ? detail
          : detail?.message || "Registration failed. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="register-page">
      <div className="register-background" />

      <section className="register-card">
        <Link to="/login" className="register-back">
          ← Back to login
        </Link>

        <div className="register-brand">
          <div className="register-brand-icon">AI</div>
          <span>
            Context<span className="register-brand-accent">API</span>
          </span>
        </div>

        <p className="register-eyebrow">GET STARTED</p>
        <h1>Create your account</h1>
        <p className="register-description">
          Create your ContextAPI account to get started.
        </p>

        {error && (
          <div className="register-message register-error" role="alert">
            {error}
          </div>
        )}

        {success && (
          <div className="register-message register-success" role="status">
            {success}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            name="username"
            type="text"
            placeholder="Choose a username"
            value={form.username}
            onChange={handleChange}
            minLength={3}
            maxLength={30}
            autoComplete="username"
            required
          />

          <label htmlFor="email">Email address</label>
          <input
            id="email"
            name="email"
            type="email"
            placeholder="you@company.com"
            value={form.email}
            onChange={handleChange}
            autoComplete="email"
            required
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            placeholder="Create a password"
            value={form.password}
            onChange={handleChange}
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            required
          />

          <label htmlFor="confirm_password">Confirm password</label>
          <input
            id="confirm_password"
            name="confirm_password"
            type={showPassword ? "text" : "password"}
            placeholder="Enter your password again"
            value={form.confirm_password}
            onChange={handleChange}
            autoComplete="new-password"
            required
          />

          <label className="register-show-password">
            <input
              type="checkbox"
              checked={showPassword}
              onChange={(event) => setShowPassword(event.target.checked)}
            />
            Show passwords
          </label>

          <button className="register-submit" type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Create Account"}
            {!loading && <span aria-hidden="true"> →</span>}
          </button>
        </form>

        <p className="register-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>

        <p className="register-security">
          Protected access · Secure authentication
        </p>
      </section>
    </main>
  );
}
