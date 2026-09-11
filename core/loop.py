from dataclasses import dataclass
from typing import Callable
from .router import ModelRouter
from .types import AgentState, TaskMode

@dataclass
class StepResult:
    output: str
    done: bool = False
    passed: bool = False

Planner = Callable[[AgentState, str], list[str]]
Executor = Callable[[AgentState, str], StepResult]
Reviewer = Callable[[AgentState, str], StepResult]

class AgentLoop:
    def __init__(self, router: ModelRouter | None = None, max_iterations: int = 30) -> None:
        self.router = router or ModelRouter()
        self.max_iterations = max_iterations

    def run(self, state: AgentState, planner: Planner, executor: Executor, reviewer: Reviewer) -> AgentState:
        state.max_iterations = min(state.max_iterations, self.max_iterations)
        state.status = "running"
        if not state.plan:
            state.plan = planner(state, state.task)

        while state.iteration < state.max_iterations and state.plan:
            step = state.plan[0]
            state.iteration += 1
            result = executor(state, step)
            state.observations.append(result.output)
            if result.done:
                state.completed.append(step)
                state.plan.pop(0)
                continue

            review = reviewer(state, result.output)
            state.observations.append(review.output)
            if review.passed:
                state.completed.append(step)
                state.plan.pop(0)

        state.status = "completed" if not state.plan else "max_iterations"
        return state

    def best_of_n(self, state: AgentState, candidates: list[Callable[[AgentState, str], str]], judge: Callable[[AgentState, list[str]], str]) -> str:
        outputs = [fn(state, state.task) for fn in candidates]
        return judge(state, outputs)
