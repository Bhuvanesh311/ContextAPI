export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "/backend";

const REFRESH_ENDPOINT =
  import.meta.env.VITE_REFRESH_ENDPOINT || "/auth/refresh";

export const getAccessToken = () =>
  sessionStorage.getItem("inferai_access_token");

export const getRefreshToken = () =>
  sessionStorage.getItem("inferai_refresh_token");

let refreshPromise = null;

async function refreshAccessToken() {
  const refreshToken = getRefreshToken();

  if (!refreshToken) {
    throw new Error("No refresh token available");
  }

  const response = await fetch(`${API_BASE_URL}${REFRESH_ENDPOINT}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  const result = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(result.detail || result.message || "Token refresh failed");
  }

  const tokens = result.tokens ?? result.data?.tokens ?? result.data ?? result;

  if (!tokens?.access_token) {
    throw new Error("Access token missing from refresh response");
  }

  sessionStorage.setItem("inferai_access_token", tokens.access_token);

  if (tokens.refresh_token) {
    sessionStorage.setItem("inferai_refresh_token", tokens.refresh_token);
  }

  return tokens.access_token;
}

// Share one refresh operation among concurrent requests.
function sharedRefresh() {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}

export function clearSessionAndRedirect() {
  sessionStorage.removeItem("inferai_access_token");
  sessionStorage.removeItem("inferai_refresh_token");
  sessionStorage.removeItem("inferai_user");

  window.location.assign("/");
}

async function makeRequest(path, options = {}, token = getAccessToken()) {
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else {
    headers.delete("Authorization");
  }

  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
}

export async function apiFetch(path, options = {}) {
  const accessTokenUsed = getAccessToken();

  let response = await makeRequest(path, options, accessTokenUsed);

  if (response.status !== 401) {
    return response;
  }

  // Another request may already have refreshed the access token.
  const latestAccessToken = getAccessToken();

  if (latestAccessToken && latestAccessToken !== accessTokenUsed) {
    response = await makeRequest(path, options, latestAccessToken);

    if (response.status !== 401) {
      return response;
    }
  }

  try {
    const newAccessToken = await sharedRefresh();

    response = await makeRequest(path, options, newAccessToken);

    if (response.status === 401) {
      clearSessionAndRedirect();
    }

    return response;
  } catch (error) {
    console.error("Authentication refresh failed:", error);
    clearSessionAndRedirect();
    throw error;
  }
}

/**
 * Gets a new access token after a 401 (for callers that cannot use apiFetch,
 * such as XHR uploads). Clears the session and redirects to login on failure.
 */
export async function refreshAfterUnauthorized() {
  try {
    return await sharedRefresh();
  } catch (error) {
    clearSessionAndRedirect();
    throw error;
  }
}

export default apiFetch;
