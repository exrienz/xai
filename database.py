"""
Database models and initialization for async job processing.
Stores multi-agent AI responses with unique URLs and 30-day retention.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

from sqlalchemy import (
    String, Text, DateTime, Enum as SQLEnum, Index,
    create_engine, select, delete
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker, AsyncAttrs
)


class JobStatus(str, Enum):
    """Status of an async job"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models"""
    pass


class AsyncJob(Base):
    """
    Represents an async multi-agent AI request job.
    Each job has a unique URL slug and stores the final aggregated response.
    """
    __tablename__ = "async_jobs"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Unique URL slug for public access (e.g., "a1b2c3d4e5f6")
    url_slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # User's question
    question: Mapped[str] = mapped_column(Text, nullable=False)

    # Job status
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, native_enum=False, length=20),
        nullable=False,
        default=JobStatus.QUEUED,
        index=True
    )

    # Response content (stored when completed)
    response_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Error message (stored when failed)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Conversation ID (if follow-up is enabled)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<AsyncJob(id={self.id}, slug={self.url_slug}, status={self.status})>"

    def is_expired(self) -> bool:
        """Check if this job has expired (past 30 day retention)"""
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON responses"""
        return {
            "id": self.id,
            "url_slug": self.url_slug,
            "question": self.question,
            "status": self.status.value,
            "response_content": self.response_content,
            "error_message": self.error_message,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./xai_async_jobs.db"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    pool_pre_ping=True,
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncSession:
    """Dependency for getting async database session"""
    async with async_session_factory() as session:
        yield session


def generate_url_slug(length: int = 12) -> str:
    """
    Generate a cryptographically secure random URL slug.
    Uses URL-safe base64 encoding (alphanumeric + - and _).

    Args:
        length: Length of the slug (default 12 chars = ~72 bits of entropy)

    Returns:
        URL-safe random string
    """
    return secrets.token_urlsafe(length)[:length]


async def create_async_job(
    session: AsyncSession,
    question: str,
    retention_days: int = 30
) -> AsyncJob:
    """
    Create a new async job with a unique URL slug.

    Args:
        session: Database session
        question: User's question
        retention_days: Number of days before expiration (default 30)

    Returns:
        Created AsyncJob instance
    """
    # Generate unique slug (retry if collision, though extremely unlikely)
    max_retries = 5
    for _ in range(max_retries):
        url_slug = generate_url_slug()

        # Check if slug already exists
        stmt = select(AsyncJob).where(AsyncJob.url_slug == url_slug)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            break
    else:
        raise RuntimeError("Failed to generate unique URL slug after multiple attempts")

    # Create job
    job = AsyncJob(
        url_slug=url_slug,
        question=question,
        status=JobStatus.QUEUED,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=retention_days),
        last_updated=datetime.utcnow(),
    )

    session.add(job)
    await session.commit()
    await session.refresh(job)

    return job


async def get_job_by_slug(session: AsyncSession, url_slug: str) -> Optional[AsyncJob]:
    """
    Retrieve a job by its URL slug.

    Args:
        session: Database session
        url_slug: URL slug to look up

    Returns:
        AsyncJob instance or None if not found
    """
    stmt = select(AsyncJob).where(AsyncJob.url_slug == url_slug)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_job_status(
    session: AsyncSession,
    job_id: int,
    status: JobStatus,
    response_content: Optional[str] = None,
    error_message: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Optional[AsyncJob]:
    """
    Update job status and related fields.

    Args:
        session: Database session
        job_id: Job ID to update
        status: New status
        response_content: Response content (for completed jobs)
        error_message: Error message (for failed jobs)
        conversation_id: Conversation ID (if follow-up enabled)

    Returns:
        Updated AsyncJob instance or None if not found
    """
    stmt = select(AsyncJob).where(AsyncJob.id == job_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        return None

    job.status = status
    job.last_updated = datetime.utcnow()

    if status == JobStatus.RUNNING and not job.started_at:
        job.started_at = datetime.utcnow()

    if status == JobStatus.COMPLETED:
        job.completed_at = datetime.utcnow()
        if response_content is not None:
            job.response_content = response_content
        if conversation_id is not None:
            job.conversation_id = conversation_id

    if status == JobStatus.FAILED:
        job.completed_at = datetime.utcnow()
        if error_message is not None:
            job.error_message = error_message

    await session.commit()
    await session.refresh(job)

    return job


async def cleanup_expired_jobs(session: AsyncSession) -> int:
    """
    Delete expired jobs (past 30-day retention).

    Args:
        session: Database session

    Returns:
        Number of jobs deleted
    """
    now = datetime.utcnow()
    stmt = delete(AsyncJob).where(AsyncJob.expires_at < now)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def get_job_stats(session: AsyncSession) -> dict:
    """
    Get statistics about jobs for monitoring.

    Returns:
        Dictionary with job counts by status
    """
    stats = {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "total": 0,
    }

    for status in JobStatus:
        stmt = select(AsyncJob).where(AsyncJob.status == status)
        result = await session.execute(stmt)
        count = len(result.scalars().all())
        stats[status.value] = count
        stats["total"] += count

    return stats
