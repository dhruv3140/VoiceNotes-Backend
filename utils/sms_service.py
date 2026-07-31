import os
import httpx
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL", "https://api.sms-gate.app:443/3rdparty/v1")
SMS_GATEWAY_USERNAME = os.getenv("SMS_GATEWAY_USERNAME")
SMS_GATEWAY_PASSWORD = os.getenv("SMS_GATEWAY_PASSWORD")
SMS_GATEWAY_DEVICE_ID = os.getenv("SMS_GATEWAY_DEVICE_ID")

async def send_sms_via_gateway(phone_number: str, message_text: str):
    url = f"{SMS_GATEWAY_URL}/messages"
    
    payload = {
        "textMessage": {
            "text": message_text
        },
        "phoneNumbers": [phone_number]
    }
    
    if SMS_GATEWAY_DEVICE_ID:
        payload["deviceId"] = SMS_GATEWAY_DEVICE_ID

    headers = {
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                auth=(SMS_GATEWAY_USERNAME, SMS_GATEWAY_PASSWORD),
                timeout=10.0
            )
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"SMS Gateway error: {response.text}"
                )
                
        except httpx.RequestError as e:
            print("SMS Gateway Exception:", repr(e))
            raise HTTPException(
                status_code=503,
                detail=f"Failed to connect to SMS Gateway: {repr(e)}"
            )
