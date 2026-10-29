

# Email Verification OTP
EMAIL_VERIFY_OTP_PREFIX = "email_verify"

# Password Reset OTP
PASSWORD_RESET_OTP_PREFIX = "password_reset"

# Login Rate Limiting
LOGIN_RATE_LIMIT_PREFIX = "login_rate_limit"

# JWT Blacklisted Refresh Tokens
TOKEN_BLACKLIST_PREFIX = "token_blacklist"



# OTP expires in 5 minutes
EMAIL_VERIFY_OTP_TTL = 300

# Password reset OTP expires in 5 minutes
PASSWORD_RESET_OTP_TTL = 300

# Login attempts expire after 15 minutes
LOGIN_RATE_LIMIT_TTL = 900

# Blacklisted refresh tokens expire after 7 days
TOKEN_BLACKLIST_TTL = 604800


# Verification OTP Resend Cooldown
EMAIL_VERIFY_RESEND_PREFIX = "email_verify_resend"
EMAIL_VERIFY_RESEND_TTL = 60



# Password Reset OTP Resend Cooldown
PASSWORD_RESET_RESEND_PREFIX = "password_reset_resend"
PASSWORD_RESET_RESEND_TTL = 60