from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr,Field, model_validator


# Common Response Schemas


class UserResponse(BaseModel):
    user_id: str
    email: EmailStr
    username: str
    role: str
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


# Register Schemas

class RegisterRequest(BaseModel):
    email: EmailStr

    username: str = Field(
        min_length=3,
        max_length=30,
        description="Unique username"
    )

    password: str = Field(
        min_length=8,
        max_length=128,
        description="User password"
    )

    confirm_password: str

    model_config = ConfigDict(json_schema_extra={"example": {
        "email": "you@example.com",
        "username": "tester1",
        "password": "Strong#Pass123",
        "confirm_password": "Strong#Pass123",
    }})

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class RegisterResponse(BaseModel):
    message: str
    user_id: str
    email: EmailStr



# Email Verification Schemas

class VerifyEmailRequest(BaseModel):
    email: EmailStr

    otp: str = Field(
        min_length=6,
        max_length=6,
        description="6-digit email verification OTP"
    )

    model_config = ConfigDict(json_schema_extra={"example": {"email": "you@example.com", "otp": "123456"}})

class ResendVerificationOTPRequest(BaseModel):
    email: EmailStr

# Login Schemas
class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128
    )

    model_config = ConfigDict(json_schema_extra={"example": {"email": "you@example.com", "password": "Strong#Pass123"}})


class LoginResponse(BaseModel):
    message: str
    tokens: TokenResponse
    user: UserResponse



 
# Refresh Token Schemas
class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    message: str
    tokens: TokenResponse


# Logout Schemas
class LogoutRequest(BaseModel):
    refresh_token: str


 
# Forgot Password Schemas
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


 
# Verify Reset OTP Schemas
class VerifyResetOTPRequest(BaseModel):
    email: EmailStr

    otp: str = Field(
        min_length=6,
        max_length=6,
        description="6-digit password reset OTP"
    )

class ResendResetOTPRequest(BaseModel):
    email: EmailStr


# Reset Password Schemas
class ResetPasswordRequest(BaseModel):
    email: EmailStr

    otp: str = Field(
        min_length=6,
        max_length=6
    )

    new_password: str = Field(
        min_length=8,
        max_length=128
    )

    confirm_password: str

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


# Change Password Schemas
class ChangePasswordRequest(BaseModel):
    old_password: str

    new_password: str = Field(
        min_length=8,
        max_length=128
    )

    confirm_password: str

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
    

