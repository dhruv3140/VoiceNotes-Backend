import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from .database import get_db
from . import rate_limit
from .models import User, Folder
from .otp_service import send_email_otp, send_sms_otp
from .schemas import (
    EmailOtpRequest,
    VerifyEmailOtp,
    FolderCreate,
    UserRegister,
    UserLogin,
    MobileOtpRequest,
    VerifyMobileOtp,
    GoogleLoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    PasswordLoginRequest,
    LoginOtpRequest,
    VerifyLoginOtpRequest,
)
from .security import (
    get_password_hash,
    verify_password,
    hash_password,
    create_access_token,
    get_current_user,
)

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

router = APIRouter(prefix="/auth", tags=["Auth"])

OTP_VALIDITY_MINUTES = 5


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def otp_expiry():
    return utc_now() + timedelta(minutes=OTP_VALIDITY_MINUTES)


def otp_is_valid(otp, expires_at, submitted_otp):
    if not rate_limit.otps_match(otp, submitted_otp) or expires_at is None:
        return False

    # Handle both timezone-aware and timezone-naive database datetimes.
    now = datetime.now(timezone.utc)

    if expires_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    else:
        now = now.astimezone(expires_at.tzinfo)

    return expires_at > now



def ensure_otp(db, user, otp_attr, exp_attr, submitted, detail):
    """Check an OTP with attempt limiting. Locks out and clears the OTP after repeated failures."""
    key = f"verify:{user.id}"
    rate_limit.check_verify_allowed(key)

    if not otp_is_valid(getattr(user, otp_attr), getattr(user, exp_attr), submitted):
        if rate_limit.record_verify_failure(key):
            setattr(user, otp_attr, None)
            setattr(user, exp_attr, None)
            db.commit()
        raise HTTPException(status_code=400, detail=detail)

    rate_limit.record_verify_success(key)


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
        },
    }


def find_user_by_identifier(identifier: str, db: Session):
    identifier = identifier.strip()

    if "@" in identifier:
        return db.query(User).filter(User.email == identifier).first()

    return db.query(User).filter(User.mobile == identifier).first()


@router.post("/register")
async def register(data: UserRegister, db: Session = Depends(get_db)):
    rate_limit.check_send_allowed(f"send:{data.email}")
    otp = str(rate_limit.generate_otp())

    user = db.query(User).filter(User.email == data.email).first()

    if user and user.is_email_verified == "true":
        raise HTTPException(
            status_code=400,
            detail="Email already registered. Please login.",
        )

    if not user:
        user = User(
            name=data.name,
            email=data.email,
            hashed_password=get_password_hash(data.password),
            auth_provider="email_password_otp",
            is_email_verified="false",
        )
        db.add(user)
    else:
        user.name = data.name
        user.hashed_password = get_password_hash(data.password)
        user.auth_provider = "email_password_otp"
        user.is_email_verified = "false"

    user.email_otp = otp
    user.email_otp_expires_at = otp_expiry()

    db.commit()

    try:
        await send_email_otp(data.email, otp)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send verification email: {str(e)}",
        )

    return {
        "success": True,
        "message": "OTP sent to your email. Verify OTP to complete registration.",
        "email": data.email,
    }


@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not db_user.hashed_password:
        raise HTTPException(
            status_code=401,
            detail="Please login using Google or OTP",
        )

    if not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return create_user_response(db_user)


@router.post("/mobile/send-otp")
async def send_mobile_otp(
    data: MobileOtpRequest,
    db: Session = Depends(get_db),
):
    rate_limit.check_send_allowed(f"send:{data.mobile}")
    otp = str(rate_limit.generate_otp())

    user = db.query(User).filter(User.mobile == data.mobile).first()

    if user and user.is_mobile_verified == "true":
        raise HTTPException(
            status_code=400,
            detail="Mobile number already registered. Please login.",
        )

    if not user:
        user = User(
            name=data.name,
            mobile=data.mobile,
            auth_provider="mobile",
            is_mobile_verified="false",
        )
        db.add(user)
    else:
        user.name = data.name
        user.auth_provider = "mobile"
        user.is_mobile_verified = "false"

    user.otp_code = otp
    user.otp_expires_at = otp_expiry()

    db.commit()

    try:
        await send_sms_otp(data.mobile, otp)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send mobile OTP: {str(e)}",
        )

    return {
        "success": True,
        "message": "OTP sent successfully.",
    }


@router.post("/email/send-otp")
async def send_email_register_otp(
    data: EmailOtpRequest,
    db: Session = Depends(get_db),
):
    rate_limit.check_send_allowed(f"send:{data.email}")
    otp = str(rate_limit.generate_otp())

    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        user = User(
            name=data.name,
            email=data.email,
            auth_provider="email_otp",
            is_email_verified="false",
        )
        db.add(user)
    else:
        user.name = data.name

    user.email_otp = otp
    user.email_otp_expires_at = otp_expiry()

    db.commit()

    try:
        await send_email_otp(data.email, otp)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send OTP email: {str(e)}",
        )

    return {
        "success": True,
        "message": "Email OTP sent successfully",
    }


@router.post("/email/verify-otp")
async def verify_email_register_otp(
    data: VerifyEmailOtp,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    ensure_otp(db, user, "email_otp", "email_otp_expires_at", data.otp,
        "Invalid or expired OTP. Please request a new OTP.")

    user.email_otp = None
    user.email_otp_expires_at = None
    user.is_email_verified = "true"
    user.auth_provider = "email_otp"

    db.commit()
    db.refresh(user)

    return create_user_response(user)


@router.post("/mobile/verify-otp")
def verify_mobile_otp(
    data: VerifyMobileOtp,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.mobile == data.mobile).first()

    if not user:
        raise HTTPException(status_code=404, detail="Mobile number not found")

    ensure_otp(db, user, "otp_code", "otp_expires_at", data.otp,
        "Invalid or expired OTP. Please request a new OTP.")

    user.otp_code = None
    user.otp_expires_at = None
    user.is_mobile_verified = "true"
    user.auth_provider = "mobile_otp"

    db.commit()
    db.refresh(user)

    return create_user_response(user)


@router.post("/google")
def google_auth(
    data: GoogleLoginRequest,
    db: Session = Depends(get_db),
):
    try:
        idinfo = id_token.verify_oauth2_token(
            data.token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )

        email = idinfo.get("email")
        google_id = idinfo.get("sub")
        name = idinfo.get("name")

        if not email:
            raise HTTPException(
                status_code=400,
                detail="Google email not found",
            )

        user = db.query(User).filter(User.email == email).first()

        if not user:
            user = User(
                name=name,
                email=email,
                google_id=google_id,
                auth_provider="google",
                is_email_verified="true",
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
async def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    rate_limit.check_send_allowed(f"send:{data.email}")
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    otp = str(rate_limit.generate_otp())

    user.reset_otp = otp
    user.reset_otp_expires_at = otp_expiry()

    db.commit()

    try:
        await send_email_otp(data.email, otp)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send reset email: {str(e)}",
        )

    return {
        "success": True,
        "message": "Reset OTP sent successfully to your email.",
    }


@router.post("/login/password")
def login_with_password(
    data: PasswordLoginRequest,
    db: Session = Depends(get_db),
):
    if "@" not in data.identifier:
        raise HTTPException(status_code=400, detail="Enter valid email")

    user = db.query(User).filter(User.email == data.identifier).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Password login is not available for this account. Use OTP or Google login.",
        )

    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    if user.email and user.is_email_verified != "true":
        raise HTTPException(status_code=400, detail="Email not verified")

    if user.mobile and user.is_mobile_verified != "true":
        raise HTTPException(status_code=400, detail="Mobile not verified")

    return create_user_response(user)


@router.post("/login/send-otp")
async def send_login_otp(
    data: LoginOtpRequest,
    db: Session = Depends(get_db),
):
    user = find_user_by_identifier(data.identifier, db)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please register first.",
        )

    if "@" in data.identifier:
        if user.is_email_verified != "true":
            raise HTTPException(status_code=400, detail="Email not verified")
    else:
        if user.is_mobile_verified != "true":
            raise HTTPException(status_code=400, detail="Mobile not verified")

    rate_limit.check_send_allowed(f"send:{user.id}")
    otp = str(rate_limit.generate_otp())

    user.otp_code = otp
    user.otp_expires_at = otp_expiry()

    db.commit()

    try:
        if "@" in data.identifier:
            await send_email_otp(user.email, otp)
        else:
            await send_sms_otp(user.mobile, otp, user.name)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send login OTP: {str(e)}",
        )

    return {
        "success": True,
        "message": "OTP sent successfully",
    }


@router.post("/login/verify-otp")
def verify_login_otp(
    data: VerifyLoginOtpRequest,
    db: Session = Depends(get_db),
):
    user = find_user_by_identifier(data.identifier, db)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ensure_otp(db, user, "otp_code", "otp_expires_at", data.otp,
        "Invalid or expired OTP. Please request a new OTP.")

    user.otp_code = None
    user.otp_expires_at = None

    db.commit()
    db.refresh(user)

    return create_user_response(user)


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    ensure_otp(db, user, "reset_otp", "reset_otp_expires_at", data.otp,
        "Invalid or expired reset OTP. Please request a new OTP.")

    user.hashed_password = hash_password(data.new_password)
    user.reset_otp = None
    user.reset_otp_expires_at = None

    db.commit()

    return {
        "success": True,
        "message": "Password reset successfully",
    }


@router.post("/folders")
def create_folder(
    data: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = Folder(
        name=data.name.strip(),
        user_id=current_user.id,
    )

    db.add(folder)
    db.commit()
    db.refresh(folder)

    return {
        "success": True,
        "folder": {
            "id": folder.id,
            "name": folder.name,
        },
    }


@router.get("/folders")
def get_folders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folders = db.query(Folder).filter(
        Folder.user_id == current_user.id
    ).all()

    return {
        "success": True,
        "folders": [
            {
                "id": folder.id,
                "name": folder.name,
            }
            for folder in folders
        ],
    }


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.user_id == current_user.id,
    ).first()

    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    db.delete(folder)
    db.commit()

    return {
        "success": True,
        "message": "Folder deleted",
    }


@router.put("/folders/{folder_id}")
def rename_folder(
    folder_id: int,
    data: FolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.user_id == current_user.id,
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
            "name": folder.name,
        },
    }