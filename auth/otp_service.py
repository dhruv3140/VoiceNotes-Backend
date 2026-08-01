import os
import requests
from dotenv import load_dotenv
from utils.sms_service import send_sms_via_gateway

load_dotenv(override=True)
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

async def send_email_otp(to_email: str, otp: str):
    print(f"Email OTP for {to_email}: {otp}")
    
    if not BREVO_API_KEY:
        print("Error: BREVO_API_KEY is missing in environment variables.")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    
    payload = {
        "sender": {
            "name": "Smart Notes",
            "email": "dhruvsinghal166@gmail.com" 
        },
        "to": [
            {
                "email": to_email
            }
        ],
        "subject": "Your Smart Notes OTP",
        "htmlContent": f"""
            <div style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Welcome to Smart Notes!</h2>
                <p>Your OTP for verification is:</p>
                <h1 style="color: #4F46E5; letter-spacing: 2px;">{otp}</h1>
                <p>This OTP is valid for 5 minutes.</p>
            </div>
        """
    }
    
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201, 202]:
            print("Email sent successfully via Brevo:", response.json())
        else:
            print("Brevo API Error:", response.text)
    except Exception as e:
        print("Email sending failed:", e)

async def send_sms_otp(mobile: str, otp: str, name: str = "User"):
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