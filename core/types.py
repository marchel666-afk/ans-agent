from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class TaskMode(str, Enum):
    CHAT = "chat"
    AGENT = "agent"
    AUTOPILOT = "autopilot"
    BEST_OF_N = "best_of_n"

@dataclass
class ModelCandidate:
    provider: str
    model: str
    roles: set[str] = field(default_factory=set)
    free: bool = False
    tool_capable: bool = False
    priority: int = 100

@dataclass
class AgentState:
    task: str
    mode: TaskMode = TaskMode.AGENT
    plan: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 30
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
