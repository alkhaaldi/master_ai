"""
Task State Machine for Master AI background operations (Tier2 #8).

Each background operation (radar refresh, Bridge polling, news fetch, etc.)
is registered as a typed task with lifecycle tracking.

Task States: PENDING -> RUNNING -> COMPLETED / FAILED / CANCELLED

Usage:
    tm = TaskManager.instance()
    task = tm.create_task(TaskType.RADAR_REFRESH)
    tm.start_task(task.task_id)
    tm.update_progress(task.task_id, "45/128 stocks")
    tm.complete_task(task.task_id, result="128 stocks analyzed")
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger("task_manager")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    RADAR_REFRESH = "radar_refresh"
    BRIDGE_POLL = "bridge_poll"
    DAILY_SNAPSHOT = "daily_snapshot"
    NEWS_FETCH = "news_fetch"
    SIGNAL_ALERT = "signal_alert"
    PATTERN_LEARNING = "pattern_learning"
    NIGHTLY_DIGEST = "nightly_digest"
    WEEKLY_INSIGHT = "weekly_insight"
    MORNING_REPORT = "morning_report"
    TG_COMMAND = "tg_command"
    LLM_QUERY = "llm_query"


@dataclass
class TaskState:
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return int((end - self.started_at) * 1000)

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    def to_status_line(self) -> str:
        """One-line status for Telegram /status command."""
        icons = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🟢",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "🔴",
            TaskStatus.CANCELLED: "⚪",
        }
        icon = icons.get(self.status, "❓")
        line = f"{icon} {self.task_type.value}: {self.status.value}"
        if self.progress:
            line += f" ({self.progress})"
        if self.duration_ms is not None and self.is_terminal:
            line += f" [{self.duration_ms}ms]"
        if self.error:
            line += f" — {self.error[:80]}"
        return line

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class TaskManager:
    """Singleton task manager. Tracks all background operations."""

    _instance = None

    @classmethod
    def instance(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}
        self._counter = 0
        self._max_history = 50

    def create_task(self, task_type: TaskType, metadata: Optional[Dict] = None) -> TaskState:
        self._counter += 1
        task_id = f"{task_type.value}_{self._counter}_{int(time.time())}"
        task = TaskState(task_id=task_id, task_type=task_type, metadata=metadata or {})
        self._tasks[task_id] = task
        self._cleanup_old_tasks()
        return task

    def start_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

    def update_progress(self, task_id: str, progress: str) -> None:
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.progress = progress

    def complete_task(self, task_id: str, result: Optional[str] = None) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.result = result

    def fail_task(self, task_id: str, error: str) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.error = error

    def cancel_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()

    def get_running_tasks(self) -> list:
        return [t for t in self._tasks.values() if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)]

    def get_status_summary(self) -> str:
        """Full status for /status command or dashboard."""
        running = self.get_running_tasks()
        if not running:
            return "No active tasks"
        return "\n".join(t.to_status_line() for t in running)

    def get_recent_tasks(self, n: int = 10) -> list:
        all_tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return all_tasks[:n]

    def _cleanup_old_tasks(self) -> None:
        terminal = [t for t in self._tasks.values() if t.is_terminal]
        if len(terminal) > self._max_history:
            terminal.sort(key=lambda t: t.completed_at or 0)
            for t in terminal[:len(terminal) - self._max_history]:
                del self._tasks[t.task_id]
