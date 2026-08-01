import os
import random
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))
from .otp_service import send_email_otp, send_sms_otp
from .schemas import EmailOtpRequest, VerifyEmailOtp
from .security import get_password_hash, verify_password 
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv

load_dotenv()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


from .database import get_db
from .models import User, Folder
from .schemas import FolderCreate
from .security import get_current_user
from .schemas import (
    UserRegister,
    UserLogin,
    MobileOtpRequest,
    VerifyMobileOtp,
    GoogleLoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    PasswordLoginRequest,
    LoginOtpRequest,
    VerifyLoginOtpRequest
)
from .security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


def create_user_response(user: User):
    token = create_access_token({
        "user_id": user.id,
        "email": user.email,
        "mobile": user.mobile,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "mobile": user.mobile,
            "auth_provider": user.auth_provider,
        }
    }


def find_user_by_identifier(identifier: str, db: Session):
    identifier = identifier.strip()

    if "@" in identifier:
        return db.query(User).filter(User.email == identifier).first()

    return db.query(User).filter(User.mobile == identifier).first()

@router.post("/register")
async def register(data: UserRegister, db: Session = Depends(get_db)):
    otp = str(random.randint(100000, 999999))
    # expiry = datetime.now(IST) + timedelta(minutes=5)

    user = db.query(User).filter(User.email == data.email).first()

    if user and user.is_email_verified == "true":
        raise HTTPException(status_code=400, detail="Email already registered. Please login.")

    if not user:
        user = User(
            name=data.name,
            email=data.email,
            hashed_password=get_password_hash(data.password),
            auth_provider="email_password_otp",
            is_email_verified="false"
        )
        db.add(user)
    else:
        user.name = data.name
        user.hashed_password = get_password_hash(data.password)
        user.auth_provider = "email_password_otp"
        user.is_email_verified = "false"

    user.email_otp = otp
    # user.email_otp_expires_at = expiry

    db.commit()

    try:
        await send_email_otp(data.email, otp)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send verification email: {str(e)}. Please check your SMTP configuration in the backend .env file."
        )

    return {
        "success": True,
        "message": "OTP sent to your email. Verify OTP to complete registration.",
        "email": data.email
    }


@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not db_user.hashed_password:
        raise HTTPException(status_code=401, detail="Please login using Google or OTP")

    if not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return create_user_response(db_user)


@router.post("/mobile/send-otp")
async def send_mobile_otp(data: MobileOtpRequest, db: Session = Depends(get_db)):
    otp = str(random.randint(100000, 999999))
    # expiry = datetime.now(IST) + timedelta(minutes=5)

    user = db.query(User).filter(User.mobile == data.mobile).first()

    if user and user.is_mobile_verified == "true":
        raise HTTPException(status_code=400, detail="Mobile number already registered. Please login.")

    if not user:
        user = User(
            name=data.name,
            mobile=data.mobile,
            auth_provider="mobile",
            is_mobile_verified="false"
        )
        db.add(user)
    else:
        user.name = data.name
        user.auth_provider = "mobile"
        user.is_mobile_verified = "false"

    user.otp_code = otp
    # 
    # user.otp_expires_at = expiry

    db.commit()

    await send_sms_otp(data.mobile, otp)

    return {
        "success": True,
        "message": "OTP sent successfully."
    }


@router.post("/email/send-otp")
async def send_email_register_otp(data: EmailOtpRequest, db: Session = Depends(get_db)):
    otp = str(random.randint(100000, 999999))
    # expiry = datetime.now(IST) + timedelta(minutes=5)

    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        user = User(
            name=data.name,
            email=data.email,
            auth_provider="email_otp",
            is_email_verified="false"
        )
        db.add(user)
    else:
        user.name = data.name

    user.email_otp = otp
    # 
    # user.email_otp_expires_at = expiry

    db.commit()

    try:
        await send_email_otp(data.email, otp)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send OTP email: {str(e)}. Please check your SMTP configuration in the backend .env file."
        )

    return {
        "success": True,
        "message": "Email OTP sent successfully"
    }


@router.post("/email/verify-otp")
async def verify_email_register_otp(data: VerifyEmailOtp, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    if not user.email_otp or user.email_otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # if not user.email_otp_expires_at or user.email_otp_expires_at < datetime.now(IST):
    #     raise HTTPException(status_code=400, detail="OTP expired")

    user.email_otp = None
    user.email_otp_expires_at = None
    user.is_email_verified = "true"
    user.auth_provider = "email_otp"

    db.commit()
    db.refresh(user)

    return create_user_response(user)


@router.post("/mobile/verify-otp")
def verify_mobile_otp(data: VerifyMobileOtp, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.mobile == data.mobile).first()

    if not user:
        raise HTTPException(status_code=404, detail="Mobile number not found")

    if user.otp_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # Fix: Handle naive vs aware datetime comparison safely
    # if user.otp_expires_at:
    #     db_expiry = user.otp_expires_at
    #     if db_expiry.tzinfo is None:
    #         db_expiry = db_expiry.replace(tzinfo=IST)
        
        # if db_expiry < datetime.now(IST):
        #     raise HTTPException(status_code=400, detail="OTP expired")

    user.otp_code = None
    user.otp_expires_at = None
    user.is_mobile_verified = "true"
    user.auth_provider = "mobile_otp"

    db.commit()
    db.refresh(user)

    return create_user_response(user)


@router.post("/google")
def google_auth(data: GoogleLoginRequest,  db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            data.token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )

        google_id = idinfo.get("sub")
        email = idinfo.get("email")
        name = idinfo.get("name")

        if not email:
            raise HTTPException(status_code=400, detail="Google email not found")

        user = db.query(User).filter(User.email == email).first()

        if not user:
            user = User(
                name=name,
                email=email,
                google_id=google_id,
                auth_provider="google",
                is_email_verified="true"
            )
            db.add(user)

        else:
            user.google_id = google_id
            user.auth_provider = "google"
            user.is_email_verified = "true"

            if not user.name:
                user.name = name

        db.commit()
        db.refresh(user)

        return create_user_response(user)

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    otp = str(random.randint(100000, 999999))

    user.reset_otp = otp
    #user.reset_otp_expires_at = datetime.utcnow() + timedelta(minutes=5)

    db.commit()

    try:
        send_email_otp(data.email, otp)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send reset email: {str(e)}. Please check your SMTP configuration in the backend .env file."
        )

    return {
        "success": True,
        "message": "Reset OTP sent successfully to your email."
    }

@router.post("/login/password")
def login_with_password(data: PasswordLoginRequest, db: Session = Depends(get_db)):
    if "@" not in data.identifier:
        raise HTTPException(status_code=400, detail="Enter valid email")

    user = db.query(User).filter(User.email == data.identifier).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Password login is not available for this account. Use OTP or Google login."
        )

    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    if user.email and user.is_email_verified != "true":
        raise HTTPException(status_code=400, detail="Email not verified")

    if user.mobile and user.is_mobile_verified != "true":
        raise HTTPException(status_code=400, detail="Mobile not verified")

    return create_user_response(user)


@router.post("/login/send-otp")
async def send_login_otp(data: LoginOtpRequest, db: Session = Depends(get_db)):
    user = find_user_by_identifier(data.identifier, db)

    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please register first.")

    otp = str(random.randint(100000, 999999))
    #expiry = datetime.utcnow() + timedelta(minutes=5)

    user.otp_code = otp
    #user.otp_expires_at = expiry

    db.commit()

    if "@" in data.identifier:
        if user.is_email_verified != "true":
            raise HTTPException(status_code=400, detail="Email not verified")

        try:
            send_email_otp(user.email, otp)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send login OTP email: {str(e)}. Please check your SMTP configuration in the backend .env file."
            )

    else:
        if user.is_mobile_verified != "true":
            raise HTTPException(status_code=400, detail="Mobile not verified")

        await send_sms_otp(user.mobile, otp, user.name)

    return {
        "success": True,
        "message": "OTP sent successfully"
    }


@router.post("/login/verify-otp")
def verify_login_otp(data: VerifyLoginOtpRequest, db: Session = Depends(get_db)):
    user = find_user_by_identifier(data.identifier, db)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.otp_code or user.otp_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # if not user.otp_expires_at or user.otp_expires_at < datetime.utcnow():
    #     raise HTTPException(status_code=400, detail="OTP expired")

    user.otp_code = None
    user.otp_expires_at = None

    db.commit()
    db.refresh(user)

    return create_user_response(user)


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    if user.reset_otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if user.reset_otp_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")

    user.hashed_password = hash_password(data.new_password)
    user.reset_otp = None
    user.reset_otp_expires_at = None

    db.commit()

    return {
        "success": True,
        "message": "Password reset successfully"
    }

@router.post("/folders")
def create_folder(
    data: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder = Folder(
        name=data.name.strip(),
        user_id=current_user.id
    )

    db.add(folder)
    db.commit()
    db.refresh(folder)

    return {
        "success": True,
        "folder": {
            "id": folder.id,
            "name": folder.name
        }
    }


@router.get("/folders")
def get_folders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folders = db.query(Folder).filter(Folder.user_id == current_user.id).all()

    return {
        "success": True,
        "folders": [
            {
                "id": folder.id,
                "name": folder.name
            }
            for folder in folders
        ]
    }


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.user_id == current_user.id
    ).first()

    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    db.delete(folder)
    db.commit()

    return {
        "success": True,
        "message": "Folder deleted"
    }

@router.put("/folders/{folder_id}")
def rename_folder(
    folder_id: int,
    data: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.user_id == current_user.id
    ).first()

    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    folder.name = data.name.strip()
    db.commit()
    db.refresh(folder)

    return {
        "success": True,
        "folder": {
            "id": folder.id,
            "name": folder.name
        }
    }