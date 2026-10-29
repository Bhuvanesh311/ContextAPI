from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class SandboxLimits:
 
    # CPU

    cpu_count: float

    # Memory

    memory_limit_mb: int

    # Processes

    max_processes: int

    # Execution

    execution_timeout: timedelta

    # Output

    max_output_size_mb: int

    # Worker Lifecycle

    max_jobs: int

    max_lifetime: timedelta

    # Filesystem

    readonly_input: bool

    readonly_rootfs: bool

    # Network

    network_enabled: bool


DEFAULT_SANDBOX_LIMITS = SandboxLimits(

    cpu_count=2.0,

    memory_limit_mb=2048,

    max_processes=128,

    execution_timeout=timedelta(minutes=5),

    max_output_size_mb=200,

    max_jobs=25,

    max_lifetime=timedelta(hours=12),

    readonly_input=True,

    readonly_rootfs=True,

    network_enabled=False,
)
