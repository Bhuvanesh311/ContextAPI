import secrets
import string
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

def generate_otp(length:int =6)->str:
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))

def get_next_user_sequence(db:Session)->int :
    result =db.execute(
        text(" SELECT nextval('user_sequence')")
    )
    return result.scalar_one()


def generate_user_id(sequence: int)-> str:
    return f"USR{sequence:06d}"


def generate_tenant_id(sequence: int)-> str:
    """A new user gets a personal tenant that shares the user's sequence number."""
    return f"TEN{sequence:06d}"


def normalize_email(email:str)->str:
    return email.strip().lower()

def normalize_username(username: str)->str:
    return username.strip().lower()



def validate_password_strength(password: str)-> None :
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")

    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")

    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number.")

    if not re.search(r"[!@#$%^&*()_\-+=\[{\]};:'\",.<>/?\\|`~]", password):
        raise ValueError("Password must contain at least one special character.")


def mask_email(email: str)->str:
    email = normalize_email(email)

    local_part, domain = email.split("@")

    if len(local_part) <= 2:
        masked_local = local_part[0] + "*"
    else:
        masked_local = local_part[:2] + "*" * (len(local_part) - 2)

    return f"{masked_local}@{domain}"