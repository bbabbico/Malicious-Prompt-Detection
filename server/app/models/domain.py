from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text, Index, JSON
from sqlalchemy.sql import func
from app.core.database import Base

class User(Base):
    __tablename__ = "USERS"

    user_id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    daily_quota = Column(Integer, default=1000)
    tps_limit = Column(Integer, default=10)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class APIKey(Base):
    __tablename__ = "API_KEYS"

    key_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("USERS.user_id"), nullable=False)
    key_name = Column(String(100))
    key_prefix = Column(String(10))
    key_hash = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DetectionLog(Base):
    __tablename__ = "DETECTION_LOGS"

    log_id = Column(Integer, primary_key=True, index=True)
    key_id = Column(Integer, ForeignKey("API_KEYS.key_id"), nullable=False)
    raw_prompt = Column(Text, nullable=False)
    used_track = Column(String(50)) # e.g., 'small', 'large'
    risk_score_pct = Column(Float)
    action_taken = Column(String(50)) # e.g., 'allowed', 'blocked'
    process_time_ms = Column(Integer)
    xai_highlights = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_key_created", "key_id", "created_at"),
    )
