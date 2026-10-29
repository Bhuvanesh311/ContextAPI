from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC

from app.knowledge.parsing.sandbox.limits import SandboxLimits


@dataclass(slots=True)
class SandboxHealth:

    limits: SandboxLimits

    started_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    last_activity: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    jobs_processed: int = 0

    failed: bool = False

    # Recording

    def record_job(self) -> None:
  

        self.jobs_processed += 1
        self.last_activity = datetime.now(UTC)

    def mark_failed(self) -> None:
 

        self.failed = True

    def reset(self) -> None:


        self.started_at = datetime.now(UTC)
        self.last_activity = self.started_at
        self.jobs_processed = 0
        self.failed = False

    # Status

    @property
    def uptime(self) -> timedelta:

        return datetime.now(UTC) - self.started_at

    @property
    def idle_time(self) -> timedelta:


        return datetime.now(UTC) - self.last_activity

    # Health

    def exceeded_job_limit(self) -> bool:

        return (
            self.jobs_processed >= self.limits.max_jobs
        )

    def exceeded_lifetime(self) -> bool:

        return (
            self.uptime >= self.limits.max_lifetime
        )

    def needs_recycle(self) -> bool:

        return (
            self.failed
            or self.exceeded_job_limit()
            or self.exceeded_lifetime()
        )

    def is_healthy(self) -> bool:


        return not self.needs_recycle()

    # Information

    def summary(self) -> dict:


        return {
            "healthy": self.is_healthy(),
            "failed": self.failed,
            "jobs_processed": self.jobs_processed,
            "uptime_seconds": int(
                self.uptime.total_seconds()
            ),
            "idle_seconds": int(
                self.idle_time.total_seconds()
            ),
            "needs_recycle": self.needs_recycle(),
        }
