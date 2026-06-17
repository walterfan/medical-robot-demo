"""Medical task model: typed tasks with a simulated processing duration."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    CHECK_PATIENT = "check_patient"
    ADMINISTER_MEDICATION = "administer_medication"
    MEASURE_VITALS = "measure_vitals"

    @property
    def label(self) -> str:
        return {
            TaskType.CHECK_PATIENT: "检查患者",
            TaskType.ADMINISTER_MEDICATION: "给药",
            TaskType.MEASURE_VITALS: "测量生命体征",
        }[self]


_task_ids = itertools.count(1)


@dataclass
class MedicalTask:
    """A single unit of simulated medical work assigned to a robot."""

    task_type: TaskType
    target: str
    duration: float = 1.0
    task_id: int = field(default_factory=lambda: next(_task_ids))

    def describe(self) -> str:
        return f"#{self.task_id} {self.task_type.label}({self.target}, {self.duration:.1f}s)"
