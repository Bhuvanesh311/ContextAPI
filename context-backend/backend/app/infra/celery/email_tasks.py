from pathlib import Path
import asyncio
from passlib import context
from app.infra.celery.app import celery_app
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from app.core.config import settings


conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)

TEMPLATE_DIR = Path(__file__).parent.parent / "email"
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
)
def render_template(template_name: str, context: dict) -> str:
    template = env.get_template(template_name)
    return template.render(**context)


def _send_email(*,subject: str,recipient: str,template_name: str,context: dict,) -> None:
    context["current_year"] = datetime.now().year
    html = render_template(template_name, context)
    message = MessageSchema(
        subject=subject,
        recipients=[recipient],
        body=html,
        subtype=MessageType.html,
    )
    asyncio.run(FastMail(conf).send_message(message))
    

@celery_app.task
def send_verification_email(email: str,username: str,otp: str,):

    _send_email(
        subject="Verify your ContextAPI account",
        recipient=email,
        template_name="verify_email.html",
        context={
            "username": username,
            "otp": otp,
        },
    )


@celery_app.task
def send_password_reset_email(email: str,username: str,otp: str,):

    _send_email(
        subject="Reset your ContextAPI password",
        recipient=email,
        template_name="password_reset.html",
        context={
            "username": username,
            "otp": otp,
        },
    )

@celery_app.task
def send_password_changed_email(email: str,username: str,):

    _send_email(
        subject="Your password has been changed",
        recipient=email,
        template_name="password_changed.html",
        context={
            "username": username,
        },
    )

@celery_app.task
def send_welcome_email(email: str,username: str,):

    _send_email(
        subject="Welcome to ContextAPI",
        recipient=email,
        template_name="welcome.html",
        context={
            "username": username,
        },
    )

@celery_app.task
def send_account_locked_email(email: str,username: str,):

    _send_email(
        subject="Your ContextAPI account has been temporarily locked",
        recipient=email,
        template_name="account_locked.html",
        context={
            "username": username,
        },
    )