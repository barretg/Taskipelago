from __future__ import annotations
from typing import TYPE_CHECKING, List
from .prereq_parser import Node, eval_node, _has_or, collect_leaves

try:
    from RuleBuilder import RuleBuilder as _RuleBuilder
    _HAS_RULE_BUILDER = True
except ImportError:
    _RuleBuilder = None
    _HAS_RULE_BUILDER = False

if TYPE_CHECKING:
    from . import TaskipelagoWorld


def set_rules(world: "TaskipelagoWorld") -> None:
    player = world.player
    n = len(world._tasks)
    if _HAS_RULE_BUILDER:
        _set_rules_builder(world, player, n)
    else:
        _set_rules_lambda(world, player, n)


def _set_rules_builder(world: "TaskipelagoWorld", player: int, n: int) -> None:
    # Fall back to lambdas if any OR nodes exist, progressive reqs, or region reqs exist
    # (RuleBuilder has no has_from_list support).
    has_prog = any(reqs for reqs in world._task_progressive_reqs)
    has_region = any(reqs for reqs in world._task_region_reqs)
    if has_prog or has_region or any(_has_or(ast) for ast in world._parsed_prereqs + world._parsed_reward_prereqs):
        _set_rules_lambda(world, player, n)
        return

    for i in range(n):
        token_ast = world._parsed_prereqs[i]
        reward_ast = world._parsed_reward_prereqs[i]

        req_tokens = [world._token_item_names[j] for j in collect_leaves(token_ast)]
        req_rewards = [world._reward_display_names[j] for j in collect_leaves(reward_ast)]
        all_prereqs = req_tokens + req_rewards

        if all_prereqs:
            complete_loc = world.multiworld.get_location(world._complete_location_names[i], player)
            rb = _RuleBuilder(player)
            for name in all_prereqs:
                rb.has(name)
            complete_loc.access_rule = rb.build()

        reward_loc = world.multiworld.get_location(world._reward_location_names[i], player)
        rb = _RuleBuilder(player)
        rb.has(world._token_item_names[i])
        for name in all_prereqs:
            rb.has(name)
        reward_loc.access_rule = rb.build()


def _set_rules_lambda(world: "TaskipelagoWorld", player: int, n: int) -> None:
    token_names = world._token_item_names
    reward_names = world._reward_display_names
    group_items = world._group_item_display_names       # Dict[str, List[str]]
    region_tokens = world._region_token_names           # Dict[str, List[str]]

    for i in range(n):
        token_ast = world._parsed_prereqs[i]
        reward_ast = world._parsed_reward_prereqs[i]

        if token_ast is not None or reward_ast is not None:
            complete_loc = world.multiworld.get_location(world._complete_location_names[i], player)

            def complete_rule(state, ta=token_ast, ra=reward_ast,
                              p=player, tn=token_names, rn=reward_names,
                              gi=group_items, rt=region_tokens) -> bool:
                return (
                    eval_node(ta, state, p, tn, gi, rt)
                    and eval_node(ra, state, p, rn, gi, rt)
                )

            complete_loc.access_rule = complete_rule

        reward_loc = world.multiworld.get_location(world._reward_location_names[i], player)
        my_token = world._token_item_names[i]

        def reward_rule(state, mt=my_token, ta=token_ast, ra=reward_ast,
                        p=player, tn=token_names, rn=reward_names,
                        gi=group_items, rt=region_tokens) -> bool:
            return (
                state.has(mt, p)
                and eval_node(ta, state, p, tn, gi, rt)
                and eval_node(ra, state, p, rn, gi, rt)
            )

        reward_loc.access_rule = reward_rule
