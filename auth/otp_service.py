import os
import resend
from dotenv import load_dotenv
from utils.sms_service import send_sms_via_gateway

load_dotenv(override=True)
resend.api_key = os.getenv("RESEND_API_KEY")

async def send_email_otp(to_email: str, otp: str):
    print(f"Email OTP for {to_email}: {otp}")
    
    if not resend.api_key:
        print("Error: RESEND_API_KEY is missing in environment variables.")
        return

    try:
        params = {
            "from": "Smart Notes <onboarding@resend.dev>",  # Free tier ke liye default domain
            "to": [to_email],
            "subject": "Your Smart Notes OTP",
            "html": f"""
                <div style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>Welcome to Smart Notes!</h2>
                    <p>Your OTP for verification is:</p>
                    <h1 style="color: #4F46E5; letter-spacing: 2px;">{otp}</h1>
                    <p>This OTP is valid for 5 minutes.</p>
                </div>
            """
        }
        
        response = await resend.Emails.send(params)
        print("Email sent successfully via Resend:", response)
    except Exception as e:
        print("Resend Email sending failed:", e)

async def send_sms_otp(mobile: str, otp: str, name: str = "User"):
    """
    Sends the OTP via SMS using your Android SMS Gateway service.
    """
    cleaned_mobile = mobile.strip().replace(" ", "").replace("-", "")
    
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
