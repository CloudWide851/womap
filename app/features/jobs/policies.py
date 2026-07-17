from dataclasses import dataclass
from typing import Literal


JobResourceClass = Literal["database", "cpu-io", "io"]
RecoveryMode = Literal["retry", "interrupt"]


@dataclass(frozen=True)
class JobPolicy:
    resource_class: JobResourceClass
    max_attempts: int
    recovery: RecoveryMode
    priority: int = 100


JOB_POLICIES: dict[str, JobPolicy] = {
    "import-sync": JobPolicy("io", 2, "retry"),
    "import-data": JobPolicy("cpu-io", 1, "interrupt"),
    "raster-derive": JobPolicy("cpu-io", 1, "interrupt"),
    "raster-export": JobPolicy("io", 2, "retry"),
    "workspace-export": JobPolicy("cpu-io", 2, "retry"),
    "workspace-import": JobPolicy("cpu-io", 1, "interrupt"),
    "spatial-analysis": JobPolicy("database", 2, "retry"),
    "spatial-analysis-export": JobPolicy("database", 2, "retry"),
    "vector-export": JobPolicy("database", 2, "retry"),
}


def job_policy(job_type: str) -> JobPolicy:
    try:
        return JOB_POLICIES[job_type]
    except KeyError as exc:
        raise ValueError("不支持的后台任务类型。") from exc


def new_job_runtime_fields(job_type: str) -> dict[str, object]:
    policy = job_policy(job_type)
    return {
        "priority": policy.priority,
        "resource_class": policy.resource_class,
        "max_attempts": policy.max_attempts,
    }
