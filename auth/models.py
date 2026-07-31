from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from .database import Base
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    mobile = Column(String, unique=True, index=True, nullable=True)

    hashed_password = Column(String, nullable=True)

    google_id = Column(String, unique=True, nullable=True)
    auth_provider = Column(String, default="email")

    is_email_verified = Column(String, default="false")
    is_mobile_verified = Column(String, default="false")

    otp_code = Column(String, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)

    email_otp = Column(String, nullable=True)
    email_otp_expires_at = Column(DateTime, nullable=True)

    reset_otp = Column(String, nullable=True)
    reset_otp_expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)    