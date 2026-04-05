"""
Logic rules for Taskipelago.

Each task has two locations:
  - Task {i} (Complete): gated by task_prereqs (other tasks' completion tokens)
                         and reward_prereqs (previously received reward items).
  - Task {i} (Reward):   gated by all of the above PLUS this task's own completion token.

The RuleBuilder API (0.6.7+) is used so Universal Tracker can explain rules.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from . import TaskipelagoWorld


def set_rules(world: "TaskipelagoWorld") -> None:
    player = world.player
    n = len(world._tasks)

    # Try to use RuleBuilder if available (AP 0.6.7+), fall back to lambdas.
    try:
        from RuleBuilder import RuleBuilder
        _set_rules_builder(world, player, n)
    except ImportError:
        _set_rules_lambda(world, player, n)


def _set_rules_builder(world: "TaskipelagoWorld", player: int, n: int) -> None:
    """Set rules using the 0.6.7 RuleBuilder for Universal Tracker compatibility."""
    from RuleBuilder import RuleBuilder

    for i in range(n):
        token_reqs: List[int] = world._parsed_prereqs[i] if i < len(world._parsed_prereqs) else []
        reward_reqs: List[int] = (
            world._parsed_reward_prereqs[i]
            if i < len(world._parsed_reward_prereqs)
            else []
        )

        # Build the shared base rule (prereqs for completing the task)
        req_tokens = [f"Task Complete {j + 1}" for j in token_reqs]
        req_rewards = [world._reward_display_names[j] for j in reward_reqs]
        all_prereqs = req_tokens + req_rewards

        # --- Complete location ---
        if all_prereqs:
            complete_loc = world.multiworld.get_location(world._complete_location_names[i], player)
            rb = RuleBuilder(player)
            for name in all_prereqs:
                rb.has(name)
            complete_loc.access_rule = rb.build()

        # --- Reward location: needs own completion token + same prereqs ---
        reward_loc = world.multiworld.get_location(world._reward_location_names[i], player)
        rb = RuleBuilder(player)
        rb.has(f"Task Complete {i + 1}")
        for name in all_prereqs:
            rb.has(name)
        reward_loc.access_rule = rb.build()


def _set_rules_lambda(world: "TaskipelagoWorld", player: int, n: int) -> None:
    """Fallback rule-setting using plain lambdas (compatible with AP < 0.6.7)."""
    for i in range(n):
        token_reqs: List[int] = world._parsed_prereqs[i] if i < len(world._parsed_prereqs) else []
        reward_reqs: List[int] = (
            world._parsed_reward_prereqs[i]
            if i < len(world._parsed_reward_prereqs)
            else []
        )

        req_tokens = tuple(f"Task Complete {j + 1}" for j in token_reqs)
        req_rewards = tuple(world._reward_display_names[j] for j in reward_reqs)

        # --- Complete location ---
        if req_tokens or req_rewards:
            complete_loc = world.multiworld.get_location(world._complete_location_names[i], player)

            def complete_rule(
                state,
                rt=req_tokens,
                rr=req_rewards,
                p=player,
            ) -> bool:
                return all(state.has(name, p) for name in rt) and all(
                    state.has(name, p) for name in rr
                )

            complete_loc.access_rule = complete_rule

        # --- Reward location ---
        reward_loc = world.multiworld.get_location(world._reward_location_names[i], player)
        my_token = f"Task Complete {i + 1}"

        def reward_rule(
            state,
            mt=my_token,
            rt=req_tokens,
            rr=req_rewards,
            p=player,
        ) -> bool:
            return (
                state.has(mt, p)
                and all(state.has(name, p) for name in rt)
                and all(state.has(name, p) for name in rr)
            )

        reward_loc.access_rule = reward_rule