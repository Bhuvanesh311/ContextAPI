import apiClient from "./apiClient";

export const loginAdmin = async (email, password) => {
  const response = await apiClient.post("/auth/login", {
    email,
    password,
  });
  return response.data;
};

export const registerUser = async (formData) => {
  const response = await apiClient.post("/auth/register", {
    email: formData.email,
    username: formData.username,
    password: formData.password,
    confirm_password: formData.confirm_password,
  });
  return response.data;
};

export const verifyEmail = async (email, otp) => {
  const response = await apiClient.post("/auth/verify-email", {
    email,
    otp,
  });
  return response.data;
};

export const resendVerificationOTP = async (email) => {
  const response = await apiClient.post("/auth/resend-verification-otp", {
    email,
  });
  return response.data;
};

export const forgotPassword = async (email) => {
  const response = await apiClient.post("/auth/forgot-password", {
    email,
  });
  return response.data;
};

export const resetPassword = async ({
  email,
  otp,
  new_password,
  confirm_password,
}) => {
  const response = await apiClient.post("/auth/reset-password", {
    email,
    otp,
    new_password,
    confirm_password,
  });
  return response.data;
};
