
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FindingSeverity(StrEnum):

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True)
class SecurityFinding:

    code: str
    title: str
    message: str
    severity: FindingSeverity
    phase: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class FindingsCollection:

    findings: list[SecurityFinding] = field(default_factory=list)

    def add(self, finding: SecurityFinding) -> None:
        
        self.findings.append(finding)

    def extend(self, findings: list[SecurityFinding]) -> None:
        
        self.findings.extend(findings)

    def has_errors(self) -> bool:
        
        return any(
            finding.severity in {
                FindingSeverity.HIGH,
                FindingSeverity.CRITICAL,
            }
            for finding in self.findings
        )

    def has_findings(self) -> bool:
        
        return bool(self.findings)

    def clear(self) -> None:
       
        self.findings.clear()

    def __len__(self) -> int:
        return len(self.findings)

    def __iter__(self):
        return iter(self.findings)