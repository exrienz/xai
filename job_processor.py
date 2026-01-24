"""
Background job processor for async multi-agent orchestration.
Handles job execution, status updates, and error handling.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    AsyncJob, JobStatus, get_job_by_slug, update_job_status,
    async_session_factory
)


# Configure logging
logger = logging.getLogger(__name__)


class JobProcessor:
    """Handles background processing of async multi-agent jobs"""

    def __init__(self, orchestrate_func):
        """
        Initialize job processor.

        Args:
            orchestrate_func: The orchestrate function to call for processing
        """
        self.orchestrate_func = orchestrate_func

    async def process_job(self, job_id: int, url_slug: str):
        """
        Process a single job in the background.

        This function:
        1. Updates job status to RUNNING
        2. Calls the orchestrate function
        3. Updates job status to COMPLETED or FAILED
        4. Stores the response or error message

        Args:
            job_id: Job ID to process
            url_slug: URL slug for logging
        """
        logger.info(f"Starting job processing: job_id={job_id}, slug={url_slug}")

        async with async_session_factory() as session:
            try:
                # Get job details
                stmt = "SELECT * FROM async_jobs WHERE id = :job_id"
                from sqlalchemy import text
                result = await session.execute(text(stmt), {"job_id": job_id})
                row = result.fetchone()

                if not row:
                    logger.error(f"Job not found: job_id={job_id}")
                    return

                # Get job using ORM
                job = await get_job_by_slug(session, url_slug)
                if not job:
                    logger.error(f"Job not found by slug: slug={url_slug}")
                    return

                question = job.question

                # Update status to RUNNING
                logger.info(f"Job {job_id} starting execution")
                await update_job_status(
                    session,
                    job_id,
                    JobStatus.RUNNING
                )

                # Execute the orchestration
                try:
                    result = await self.orchestrate_func(question)
                    logger.info(f"Job {job_id} completed successfully")

                    # Handle both old format (string) and new format (dict with response and conversation_id)
                    if isinstance(result, dict):
                        response_content = result.get("response", "")
                        conversation_id = result.get("conversation_id")
                    else:
                        # Backwards compatibility: if result is a string, use it directly
                        response_content = result
                        conversation_id = None

                    # Update status to COMPLETED with response and conversation_id
                    await update_job_status(
                        session,
                        job_id,
                        JobStatus.COMPLETED,
                        response_content=response_content,
                        conversation_id=conversation_id
                    )

                except Exception as orchestration_error:
                    # Orchestration failed
                    error_msg = str(orchestration_error)
                    logger.error(f"Job {job_id} orchestration failed: {error_msg}", exc_info=True)

                    # Update status to FAILED with error message
                    await update_job_status(
                        session,
                        job_id,
                        JobStatus.FAILED,
                        error_message=f"Orchestration error: {error_msg}"
                    )

            except Exception as e:
                # Unexpected error in job processing
                logger.error(f"Job {job_id} processing failed unexpectedly: {str(e)}", exc_info=True)

                try:
                    await update_job_status(
                        session,
                        job_id,
                        JobStatus.FAILED,
                        error_message=f"System error: {str(e)}"
                    )
                except Exception as update_error:
                    logger.error(f"Failed to update job status after error: {update_error}")

    async def retry_job(self, job_id: int, url_slug: str) -> bool:
        """
        Retry a failed job.

        Args:
            job_id: Job ID to retry
            url_slug: URL slug

        Returns:
            True if retry was initiated, False otherwise
        """
        async with async_session_factory() as session:
            job = await get_job_by_slug(session, url_slug)

            if not job:
                logger.warning(f"Cannot retry - job not found: slug={url_slug}")
                return False

            if job.status != JobStatus.FAILED:
                logger.warning(f"Cannot retry - job not in failed state: slug={url_slug}, status={job.status}")
                return False

            if job.is_expired():
                logger.warning(f"Cannot retry - job expired: slug={url_slug}")
                return False

            # Reset to QUEUED status
            logger.info(f"Retrying job: job_id={job_id}, slug={url_slug}")
            await update_job_status(
                session,
                job_id,
                JobStatus.QUEUED,
                error_message=None  # Clear previous error
            )

            # Process the job again
            # Note: We don't await here to avoid blocking
            asyncio.create_task(self.process_job(job_id, url_slug))

            return True
