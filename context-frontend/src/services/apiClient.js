import axios from "axios";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  "/backend"
).replace(/\/+$/, "");

const REFRESH_ENDPOINT =
  import.meta.env.VITE_REFRESH_ENDPOINT || "/auth/refresh";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 15000,
});

// Separate client prevents refresh requests from triggering
// the same interceptors recursively.
const refreshClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 15000,
});

let refreshPromise = null;

function clearSession() {
  sessionStorage.removeItem("inferai_access_token");
  sessionStorage.removeItem("inferai_refresh_token");
  sessionStorage.removeItem("inferai_user");
}

function redirectToLogin() {
  clearSession();

  if (window.location.pathname !== "/") {
    window.location.replace("/");
  }
}

async function refreshAccessToken() {
  const refreshToken = sessionStorage.getItem("inferai_refresh_token");

  if (!refreshToken) {
    throw new Error("Refresh token is missing.");
  }

  const response = await refreshClient.post(REFRESH_ENDPOINT, {
    refresh_token: refreshToken,
  });

  const result = response.data;
  const tokens = result.tokens ?? result.data?.tokens ?? result.data ?? result;

  if (!tokens.access_token) {
    throw new Error("Refresh response has no access token.");
  }

  sessionStorage.setItem("inferai_access_token", tokens.access_token);

  // Preserve the existing refresh token if rotation is not enabled.
  if (tokens.refresh_token) {
    sessionStorage.setItem("inferai_refresh_token", tokens.refresh_token);
  }

  return tokens.access_token;
}

// Attach the latest access token to outgoing requests.
apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("inferai_access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

// Refresh once on 401, then retry the original request.
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (!error.response || !originalRequest) {
      return Promise.reject(error);
    }

    const requestUrl = originalRequest.url || "";
    const isRefreshRequest = requestUrl.includes(REFRESH_ENDPOINT);

    const isLoginRequest = requestUrl.includes("/auth/login");

    if (
      error.response.status !== 401 ||
      isRefreshRequest ||
      isLoginRequest ||
      originalRequest._retry
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }

      const newAccessToken = await refreshPromise;

      originalRequest.headers = originalRequest.headers || {};

      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;

      return apiClient(originalRequest);
    } catch (refreshError) {
      redirectToLogin();
      return Promise.reject(refreshError);
    }
  },
);

export default apiClient;
export { API_BASE_URL };
