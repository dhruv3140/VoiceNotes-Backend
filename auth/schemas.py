from pydantic import BaseModel, EmailStr
from typing import Optional

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class MobileOtpRequest(BaseModel):
    name: str
    mobile: str

class VerifyMobileOtp(BaseModel):
    mobile: str
    otp: str

class EmailOtpRequest(BaseModel):
    name: str
    email: EmailStr


class VerifyEmailOtp(BaseModel):
    email: EmailStr
    otp: str

class GoogleLoginRequest(BaseModel):
    token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class FolderCreate(BaseModel):
    name: str

class PasswordLoginRequest(BaseModel):
    identifier: str
    password: str


class LoginOtpRequest(BaseModel):
    identifier: str


class VerifyLoginOtpRequest(BaseModel):
    identifier: str
    otp: str
