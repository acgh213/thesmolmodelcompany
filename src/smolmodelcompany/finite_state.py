"""Model-free finite-state tracking and shortest-plan references for R03.3.

The task generator and reference functions are intentionally separate. Tracking
compares a final state; planning compares shortest-path length so equivalent
shortest plans are accepted without leaking a generator tie-break rule.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
import random
from typing import Any, Iterable, Mapping, Sequence

from .episode import Episode

State = tuple[tuple[str, int], ...]
Action = Mapping[str, Any]


def freeze_state(values: Mapping[str, int]) -> State:
    if not values or any(value not in (0, 1) for value in values.values()):
        raise ValueError("state must contain binary values")
    return tuple(sorted((str(key), int(value)) for key, value in values.items()))


def thaw_state(state: State) -> dict[str, int]:
    return dict(state)


def _apply_tracking_generator(state: dict[str, int], action: Action) -> None:
    variable = action["variable"]
    kind = action["kind"]
    if variable not in state:
        raise ValueError(f"unknown variable: {variable}")
    if kind == "flip":
        state[variable] = 1 - state[variable]
    elif kind == "set":
        state[variable] = int(action["value"])
    else:
        raise ValueError(f"unknown action kind: {kind}")


def tracking_generate(initial: State, trace: Sequence[Action]) -> State:
    state = thaw_state(initial)
    for action in trace:
        _apply_tracking_generator(state, action)
    return freeze_state(state)


def _apply_tracking_reference(state: State, action: Action) -> State:
    current = dict(state)
    variable = action["variable"]
    if variable not in current:
        raise ValueError(f"unknown variable: {variable}")
    if action["kind"] == "flip":
        return freeze_state({**current, variable: 1 - current[variable]})
    if action["kind"] == "set":
        value = action["value"]
        if value not in (0, 1):
            raise ValueError("set action must be binary")
        return freeze_state({**current, variable: value})
    raise ValueError(f"unknown action kind: {action['kind']}")


def tracking_reference(initial: State, trace: Sequence[Action]) -> State:
    state = initial
    for action in trace:
        state = _apply_tracking_reference(state, action)
    return state


def _planning_successor_reference(state: State, action: Action) -> State:
    """Reference-only transition used by BFS; never calls tracking_reference."""
    current = dict(state)
    variable = action["variable"]
    if variable not in current:
        raise ValueError(f"unknown variable: {variable}")
    if action["kind"] == "flip":
        current[variable] = 1 - current[variable]
    elif action["kind"] == "set" and action["value"] in (0, 1):
        current[variable] = action["value"]
    else:
        raise ValueError(f"invalid planning action: {action}")
    return freeze_state(current)


def _planning_successor_generator(state: State, action: Action) -> State:
    """Generator-side transition kept separate from the BFS reference."""
    current = thaw_state(state)
    if action["variable"] not in current:
        raise ValueError(f"unknown variable: {action['variable']}")
    if action["kind"] == "flip":
        current[action["variable"]] ^= 1
    elif action["kind"] == "set":
        current[action["variable"]] = int(action["value"])
    else:
        raise ValueError(f"invalid planning action: {action}")
    return freeze_state(current)


def _successors(state: State, actions: Sequence[Action]) -> Iterable[tuple[str, State]]:
    for action in actions:
        yield str(action["name"]), _planning_successor_reference(state, action)


def planning_reference(initial: State, goal: State, actions: Sequence[Action], max_horizon: int = 4) -> int | None:
    """Return shortest reachable plan length, independent of action ordering."""
    if initial == goal:
        return 0
    queue: deque[tuple[State, int]] = deque([(initial, 0)])
    seen = {initial}
    while queue:
        state, depth = queue.popleft()
        if depth >= max_horizon:
            continue
        for _, successor in _successors(state, actions):
            if successor in seen:
                continue
            if successor == goal:
                return depth + 1
            seen.add(successor)
            queue.append((successor, depth + 1))
    return None


def _planning_generate(initial: State, goal: State, actions: Sequence[Action], horizon: int) -> int | None:
    """Generate a shortest length with an independent depth-limited search."""
    def search(state: State, remaining: int) -> int | None:
        if state == goal:
            return 0
        if remaining == 0:
            return None
        lengths = []
        for action in actions:
            candidate = search(_planning_successor_generator(state, action), remaining - 1)
            if candidate is not None:
                lengths.append(candidate + 1)
        return min(lengths) if lengths else None

    return search(initial, horizon)


@dataclass(frozen=True, slots=True)
class FiniteStateTask:
    seed: int
    kind: str
    initial: State
    trace: tuple[Action, ...] = ()
    goal: State | None = None
    actions: tuple[Action, ...] = ()
    answer: Any = None


def _catalog(variables: Sequence[str]) -> tuple[Action, ...]:
    actions: list[Action] = []
    for variable in variables:
        actions.append({"name": f"flip_{variable}", "kind": "flip", "variable": variable})
        for value in (0, 1):
            actions.append({"name": f"set_{variable}_{value}", "kind": "set", "variable": variable, "value": value})
    return tuple(actions)


def generate_tracking_task(seed: int, horizon: int = 4) -> FiniteStateTask:
    rng = random.Random(seed)
    variables = ("x", "y")
    initial = freeze_state({name: rng.randrange(2) for name in variables})
    catalog = _catalog(variables)
    trace = tuple(catalog[rng.randrange(len(catalog))] for _ in range(horizon))
    answer = tracking_generate(initial, trace)
    return FiniteStateTask(seed, "tracking", initial, trace=trace, actions=catalog, answer=answer)


def generate_planning_task(seed: int, max_horizon: int = 4) -> FiniteStateTask:
    rng = random.Random(seed)
    variables = ("x", "y")
    actions = _catalog(variables)
    initial = freeze_state({name: rng.randrange(2) for name in variables})
    goal_values = dict(initial)
    for changed in variables:
        if rng.randrange(2):
            goal_values[changed] = 1 - goal_values[changed]
    if goal_values == dict(initial):
        changed = rng.choice(variables)
        goal_values[changed] = 1 - goal_values[changed]
    goal = freeze_state(goal_values)
    answer = _planning_generate(initial, goal, actions, max_horizon)
    if answer is None:
        raise ValueError("generated planning task exceeded its horizon")
    return FiniteStateTask(seed, "planning", initial, goal=goal, actions=actions, answer=answer)


def task_episode(task: FiniteStateTask, split: str = "development") -> Episode:
    if task.kind == "tracking":
        visible = {"kind": task.kind, "initial": dict(task.initial), "trace": list(task.trace)}
        answer = dict(task.answer)
        latent = {"kind": task.kind, "actions": list(task.actions)}
    else:
        visible = {
            "kind": task.kind,
            "initial": dict(task.initial),
            "goal": dict(task.goal or ()),
            "actions": list(task.actions),
        }
        answer = {"shortest_length": task.answer}
        latent = {"kind": task.kind, "actions": list(task.actions)}
    return Episode(
        protocol_version="r03-v1",
        family="finite-state",
        split=split,
        seed=task.seed,
        input_state={"task": visible},
        rendered_input=visible,
        support=[],
        query={"instruction": "solve the finite-state task"},
        answer=answer,
        latent_program=latent,
        structure_signature=f"finite-state:{task.kind}:v1",
        presentation_variant={"format": "canonical-json"},
        difficulty={"horizon": 4},
        provenance={"generator": "finite-state-v1"},
    )



def _assert_tracking_answer(task: FiniteStateTask) -> None:
    if task.kind != "tracking":
        raise ValueError("tracking answer requested for non-tracking task")
    generated = tracking_generate(task.initial, task.trace)
    referenced = tracking_reference(task.initial, task.trace)
    if generated != referenced or generated != task.answer:
        raise AssertionError("tracking generator/reference disagree")



def _assert_planning_answer(task: FiniteStateTask) -> None:
    if task.kind != "planning" or task.goal is None:
        raise ValueError("planning answer requested for non-planning task")
    generated = _planning_generate(task.initial, task.goal, task.actions, 4)
    referenced = planning_reference(task.initial, task.goal, task.actions, 4)
    if generated != referenced or generated != task.answer:
        raise AssertionError("planning generator/reference disagree")



def validate_task(task: FiniteStateTask) -> None:
    """Cross-check the generated task without using the episode answer oracle."""
    if task.kind == "tracking":
        _assert_tracking_answer(task)
    elif task.kind == "planning":
        _assert_planning_answer(task)
    else:
        raise ValueError(f"unknown task kind: {task.kind}")


def generate_episode(seed: int, kind: str = "tracking") -> Episode:
    task = generate_tracking_task(seed) if kind == "tracking" else generate_planning_task(seed)
    return task_episode(task)


def _all_states() -> tuple[State, ...]:
    return tuple(
        freeze_state({"x": first & 1, "y": (first >> 1) & 1})
        for first in range(4)
    )


def small_state_audit() -> list[dict[str, Any]]:
    """Exhaustively compare 6,220 traces: 4 states × 6 actions^(0..4)."""
    actions = _catalog(("x", "y"))
    failures: list[dict[str, Any]] = []
    for initial in _all_states():
        for length in range(5):
            for trace in product(actions, repeat=length):
                generated = tracking_generate(initial, trace)
                referenced = tracking_reference(initial, trace)
                if generated != referenced:
                    failures.append({"initial": initial, "trace": trace})
    return failures


def small_planning_audit() -> list[dict[str, Any]]:
    """Compare independent solvers over 32 pairs: two catalogs × 16 states."""
    catalogs = (_catalog(("x", "y")), (_catalog(("x", "y"))[0],))
    failures: list[dict[str, Any]] = []
    for actions in catalogs:
        for initial in _all_states():
            for goal in _all_states():
                generated = _planning_generate(initial, goal, actions, 4)
                referenced = planning_reference(initial, goal, actions, 4)
                if generated != referenced:
                    failures.append({"initial": initial, "goal": goal, "generated": generated, "referenced": referenced})
    return failures
