import os
import smtplib
import requests
from email.message import EmailMessage
from dotenv import load_dotenv
from utils.sms_service import send_sms_via_gateway
async def send_email_otp(to_email: str, otp: str):
    load_dotenv(override=True)
    email_user = os.getenv("EMAIL_USER", "").strip()
    email_password = os.getenv("EMAIL_PASSWORD", "").strip()
    email_host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    email_port = int(os.getenv("EMAIL_PORT", 587))

    print(f"Email OTP for {to_email}: {otp}")
    print("EMAIL_USER:", email_user)
    print("EMAIL_PASSWORD LENGTH:", len(email_password) if email_password else 0)

    if not email_user or not email_password:
        raise ValueError("EMAIL_USER or EMAIL_PASSWORD environment variable is missing in the backend .env file.")

    msg = EmailMessage()
    msg["Subject"] = "Your Smart Notes OTP" 
    msg["From"] = email_user
    msg["To"] = to_email
    msg.set_content(f"Your Smart Notes OTP is: {otp}")
    try:
        with smtplib.SMTP(email_host, email_port) as server:
            server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
        print("Email sent successfully")
    except Exception as e:
        print("Email sending failed:", e)
        raise e
async def send_sms_otp(mobile: str, otp: str, name: str = "User"):
    """
    Sends the OTP via SMS using your Android SMS Gateway service.
    """
    # Clean up phone number: remove any spaces or dashes
    cleaned_mobile = mobile.strip().replace(" ", "").replace("-", "")
    
    # If standard 10-digit Indian number without country code, prepend +91
    if len(cleaned_mobile) == 10 and cleaned_mobile.isdigit():
        formatted_mobile = f"+91{cleaned_mobile}"
    elif not cleaned_mobile.startswith("+"):
        formatted_mobile = f"+{cleaned_mobile}"
    else:
        formatted_mobile = cleaned_mobile

    message_text = f" Hi {name} , Your Smart Notes OTP is: {otp}"
    print(f"SMS OTP for {formatted_mobile}: {otp}")

    try:
        response = await send_sms_via_gateway(formatted_mobile, message_text)
        print("SMS response via Android Gateway:", response)
    except Exception as e:
        print("SMS sending failed:", e)