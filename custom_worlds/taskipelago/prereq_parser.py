"""
Boolean prereq expression parser for Taskipelago.

Grammar:
    expr     := or_expr
    or_expr  := and_expr ('||' and_expr)*
    and_expr := atom ('&&' atom | ',' atom)*
    atom     := INTEGER | NAME | NAME*INTEGER | NAME-INTEGER | '(' expr ')'

    INTEGER   - 1-based task/item index
    NAME      - group or region reference (resolved against known_groups / known_regions)
    NAME*N    - group count mode (N items from group) or region absolute count (N tasks)
    NAME-N    - group ordering mode (N-th position) or region percentage (N%)

    "prev" and "sequential" are reserved keywords, valid only in task prereqs
    (label == "task prereq"):
      prev       - resolves to the task immediately before this one (this task's
                   0-based index minus 1).
      sequential - no-op at evaluation time; marks a task (with count > 1) so that
                   every duplicate copy after the first automatically depends on
                   the copy before it, resolved at generation time.

Output AST nodes:
    int                         - leaf: task/item index (0-based)
    ("and", [node, ...])        - all children must be satisfied
    ("or",  [node, ...])        - at least one child must be satisfied
    ("group_ref", name, n)      - progressive group ordering ref; n is position int or None
    ("group_count", name, n)    - progressive group count mode ref; n is required count
    ("region_ref", name, pct)   - region percentage ref; pct is int or None (unresolved)
    ("region_abs", name, n)     - region absolute count ref; n is required task count
    ("group", name, count)      - resolved ordering group ref (count is threshold int)
    ("region", name, pct)       - resolved region percentage ref (pct is int)
    ("seq_flag",)               - "sequential" marker; always true, carries no dependency

group_count and region_abs nodes are already resolved (count embedded) and pass through
resolve_ast_refs unchanged.

A single-child "and" or "or" is simplified to just the child.
"""
from __future__ import annotations
import math as _math
import re as _re
from typing import List, Tuple, Union

# AST node type
Node = Union[int, Tuple]

# Bare words that cannot be used as region or progressive group names.
RESERVED_WORDS = {"prev", "sequential"}


def parse_prereq(
    text: str,
    n_tasks: int,
    task_index: int,
    label: str,
    known_groups=None,
    known_regions=None,
) -> Node | None:
    """
    Parse a prereq expression string into an AST.
    Returns None if the expression is empty.
    Raises Exception on syntax or range errors.
    All integer leaf values are 0-based task/item indices.
    known_groups: set of valid group names (or None)
    known_regions: set of valid region names (or None)
    """
    text = text.strip()
    if not text:
        return None

    tokens = _tokenize(text, task_index, label)
    if not tokens:
        return None

    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume(expected=None):
        tok = tokens[pos[0]]
        if expected is not None and tok != expected:
            raise Exception(
                f"Taskipelago: expected '{expected}' but got '{tok}' "
                f"in {label} on task {task_index + 1}."
            )
        pos[0] += 1
        return tok

    def parse_expr():
        return parse_or()

    def parse_or():
        left = parse_and()
        nodes = [left]
        while peek() == "||":
            consume("||")
            nodes.append(parse_and())
        return _simplify("or", nodes)

    def parse_and():
        left = parse_atom()
        nodes = [left]
        while peek() in ("&&", ","):
            consume()
            nodes.append(parse_atom())
        return _simplify("and", nodes)

    def parse_atom():
        tok = peek()
        if tok is None:
            raise Exception(
                f"Taskipelago: unexpected end of {label} expression on task {task_index + 1}."
            )
        if tok == "(":
            consume("(")
            node = parse_expr()
            consume(")")
            return node
        if isinstance(tok, int):
            consume()
            idx_1 = tok
            if idx_1 < 1 or idx_1 > n_tasks:
                raise Exception(
                    f"Taskipelago: {label} index '{idx_1}' on task {task_index + 1} "
                    f"is out of range (1..{n_tasks})."
                )
            return idx_1 - 1  # 0-based
        if isinstance(tok, str) and tok not in ("&&", "||", "(", ")", ","):
            consume()
            if tok in RESERVED_WORDS:
                if label != "task prereq":
                    raise Exception(
                        f"Taskipelago: '{tok}' can only be used in task prereqs "
                        f"(used in {label} on task {task_index + 1})."
                    )
                if tok == "prev":
                    if task_index < 1:
                        raise Exception(
                            f"Taskipelago: 'prev' used on task {task_index + 1} "
                            f"but there is no previous task."
                        )
                    return task_index - 1
                return ("seq_flag",)
            m_dash = _re.match(r'^(.+[a-zA-Z_])-(\d+)$', tok)
            m_star = _re.match(r'^(.+[a-zA-Z_])\*(\d+)$', tok)
            if m_dash:
                base, suffix, mode = m_dash.group(1), int(m_dash.group(2)), "dash"
            elif m_star:
                base, suffix, mode = m_star.group(1), int(m_star.group(2)), "star"
            else:
                base, suffix, mode = tok, None, "none"
            if known_groups is not None and base in known_groups:
                if mode == "star":
                    return ("group_count", base, suffix)
                return ("group_ref", base, suffix)
            if known_regions is not None and base in known_regions:
                if mode == "star":
                    return ("region_abs", base, suffix)
                return ("region_ref", base, suffix)
            raise Exception(
                f"Taskipelago: unknown name '{base}' in {label} on task {task_index + 1}."
            )
        raise Exception(
            f"Taskipelago: unexpected token '{tok}' in {label} on task {task_index + 1}."
        )

    result = parse_expr()

    if pos[0] != len(tokens):
        raise Exception(
            f"Taskipelago: unexpected token '{tokens[pos[0]]}' in {label} on task {task_index + 1}."
        )

    return result


def resolve_ast_refs(node: Node | None, group_thresh: dict, region_pct: dict) -> Node | None:
    """Replace group_ref/region_ref nodes with resolved group/region nodes.
    group_count and region_abs nodes are already resolved and passed through unchanged."""
    if node is None or isinstance(node, int):
        return node
    op = node[0]
    if op == "group_ref":
        _, name, _ = node
        return ("group", name, group_thresh[name])
    if op == "region_ref":
        _, name, _ = node
        return ("region", name, region_pct[name])
    if op in ("group_count", "region_abs", "seq_flag"):
        return node  # already resolved / no children
    tag, children = node
    return (tag, [resolve_ast_refs(c, group_thresh, region_pct) for c in children])


def _simplify(op: str, nodes: list) -> Node:
    if len(nodes) == 1:
        return nodes[0]
    return (op, nodes)


def ast_to_text(node: Node | None) -> str:
    """
    Serialize an unresolved task-prereq AST (as produced by parse_prereq before
    resolve_ast_refs) back into expression text using only tokens every prereq
    parser understands (integers, NAME/NAME-N/NAME*N, &&, ||, parens). Used to
    rewrite 'prev'/'sequential' keyword usage into plain text, since the
    client-side runtime evaluators don't know those keywords.
    seq_flag nodes are constant-true and are folded away.
    """
    kind, text = _fold_to_text(node)
    return "" if kind == "true" else text


def _fold_to_text(node: Node | None) -> Tuple[str, str]:
    """Return (kind, text). kind is 'true', 'and', 'or', or 'atom'."""
    if node is None:
        return ("true", "")
    if isinstance(node, int):
        return ("atom", str(node + 1))
    op = node[0]
    if op == "seq_flag":
        return ("true", "")
    if op == "and":
        parts = [p for p in (_fold_to_text(c) for c in node[1]) if p[0] != "true"]
        if not parts:
            return ("true", "")
        rendered = [f"({t})" if k == "or" else t for k, t in parts]
        return ("and", " && ".join(rendered))
    if op == "or":
        parts = [_fold_to_text(c) for c in node[1]]
        if any(k == "true" for k, _ in parts):
            return ("true", "")
        return ("or", " || ".join(t for _, t in parts))
    if op == "group_ref":
        _, name, n = node
        return ("atom", f"{name}-{n}" if n is not None else name)
    if op == "group_count":
        _, name, n = node
        return ("atom", f"{name}*{n}")
    if op == "region_ref":
        _, name, pct = node
        return ("atom", f"{name}-{pct}" if pct is not None else name)
    if op == "region_abs":
        _, name, n = node
        return ("atom", f"{name}*{n}")
    raise ValueError(f"Cannot serialize AST op: {op}")


def _tokenize(text: str, task_index: int, label: str) -> list:
    """
    Convert expression string into a flat list of tokens:
    integers, strings (named refs), '(', ')', '&&', '||', ','
    """
    tokens = []
    i = 0
    while i < len(text):
        c = text[i]

        if c.isspace():
            i += 1
            continue

        if c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            tokens.append(int(text[i:j]))
            i = j
            continue

        if text[i:i+2] == "&&":
            tokens.append("&&")
            i += 2
            continue

        if text[i:i+2] == "||":
            tokens.append("||")
            i += 2
            continue

        if c in ("(", ")", ","):
            tokens.append(c)
            i += 1
            continue

        if c.isalpha() or c == '_':
            j = i
            while j < len(text):
                ch = text[j]
                if ch.isspace() or ch in ("(", ")", ","):
                    break
                if text[j:j+2] in ("&&", "||"):
                    break
                j += 1
            tokens.append(text[i:j])
            i = j
            continue

        raise Exception(
            f"Taskipelago: unexpected character '{c}' in {label} on task {task_index + 1}."
        )

    return tokens


def collect_leaves(node: Node | None) -> List[int]:
    """Return all 0-based task/item indices (int leaves) referenced in an AST node."""
    if node is None:
        return []
    if isinstance(node, int):
        return [node]
    op = node[0]
    if op in ("group_ref", "group_count", "region_ref", "region_abs", "group", "region", "seq_flag"):
        return []
    _, children = node
    result = []
    for child in children:
        result.extend(collect_leaves(child))
    return result


def has_seq_flag(node: Node | None) -> bool:
    """Return True if a 'sequential' keyword marker exists anywhere in the AST."""
    if node is None or isinstance(node, int):
        return False
    op = node[0]
    if op == "seq_flag":
        return True
    if op in ("group_ref", "group_count", "region_ref", "region_abs", "group", "region"):
        return False
    _, children = node
    return any(has_seq_flag(child) for child in children)


def collect_group_refs(node: Node | None) -> List[Tuple]:
    """Return list of (name, n_or_None) for all group_ref (ordering mode) leaves."""
    if node is None or isinstance(node, int):
        return []
    op = node[0]
    if op == "group_ref":
        return [(node[1], node[2])]
    if op in ("group", "group_count", "region_ref", "region_abs", "region", "seq_flag"):
        return []
    _, children = node
    result = []
    for child in children:
        result.extend(collect_group_refs(child))
    return result


def collect_group_count_refs(node: Node | None) -> List[Tuple]:
    """Return list of (name, count) for all group_count (count mode) leaves."""
    if node is None or isinstance(node, int):
        return []
    op = node[0]
    if op == "group_count":
        return [(node[1], node[2])]
    if op in ("group", "group_ref", "region_ref", "region_abs", "region", "seq_flag"):
        return []
    _, children = node
    result = []
    for child in children:
        result.extend(collect_group_count_refs(child))
    return result


def collect_region_refs(node: Node | None) -> List[Tuple]:
    """Return list of (name, pct_or_None) for all region_ref (percentage mode) leaves."""
    if node is None or isinstance(node, int):
        return []
    op = node[0]
    if op == "region_ref":
        return [(node[1], node[2])]
    if op in ("region", "region_abs", "group_ref", "group_count", "group", "seq_flag"):
        return []
    _, children = node
    result = []
    for child in children:
        result.extend(collect_region_refs(child))
    return result


def collect_region_abs_refs(node: Node | None) -> List[Tuple]:
    """Return list of (name, count) for all region_abs (absolute count) leaves."""
    if node is None or isinstance(node, int):
        return []
    op = node[0]
    if op == "region_abs":
        return [(node[1], node[2])]
    if op in ("region", "region_ref", "group_ref", "group_count", "group", "seq_flag"):
        return []
    _, children = node
    result = []
    for child in children:
        result.extend(collect_region_abs_refs(child))
    return result


def eval_node(
    node: Node | None,
    state,
    player: int,
    item_names: List[str],
    group_items: dict = None,
    region_tokens: dict = None,
) -> bool:
    """
    Evaluate an AST node against a CollectionState.
    item_names: list of item name strings indexed by 0-based task/item index.
    group_items: dict {group_name: [item_name, ...]}
    region_tokens: dict {region_name: [token_item_name, ...]}
    """
    if node is None:
        return True
    if isinstance(node, int):
        return state.has(item_names[node], player)
    op = node[0]
    if op == "and":
        return all(eval_node(c, state, player, item_names, group_items, region_tokens) for c in node[1])
    if op == "or":
        return any(eval_node(c, state, player, item_names, group_items, region_tokens) for c in node[1])
    if op == "group":
        _, name, count = node
        return state.has_from_list(group_items[name], player, count)
    if op == "group_count":
        _, name, count = node
        return state.has_from_list(group_items[name], player, count)
    if op == "region":
        _, name, pct = node
        tokens = region_tokens[name]
        return state.has_from_list(tokens, player, _math.ceil(len(tokens) * pct / 100))
    if op == "region_abs":
        _, name, n = node
        tokens = region_tokens[name]
        return state.has_from_list(tokens, player, n)
    if op == "seq_flag":
        return True
    raise ValueError(f"Unknown AST op: {op}")


# ---------------------------------------------------------------------------
# Cost expression parser
# ---------------------------------------------------------------------------
# Grammar:
#   cost_expr := cost_or
#   cost_or   := cost_and ('||' cost_and)*
#   cost_and  := cost_atom ('&&' cost_atom | ',' cost_atom)*
#   cost_atom := '"Name"*N' | '"Name"' | 'idx*N' | 'idx' | '(' cost_expr ')'
#
#   Bare "Name" or idx (no *N) defaults to count=1.
#
# AST output nodes:
#   ("cost_group", name: str, count: int)  - spend N of consumable named 'name'
#   ("and", [...])
#   ("or",  [...])
# ---------------------------------------------------------------------------

def parse_cost_expr(
    text: str,
    consumable_names: "set[str]",
    item_names_ordered: "list[str] | None" = None,
) -> "Node | None":
    """
    Parse a task cost expression.
    consumable_names: set of valid consumable item name strings.
    item_names_ordered: 1-based list of all item names (index 0 = item 1) for resolving
                        numeric index references (e.g. '2-3' means 3 of item 2).
    Returns an AST or None if the expression is empty.
    """
    text = text.strip()
    if not text:
        return None

    tokens = _tokenize_cost(text, item_names_ordered)
    if not tokens:
        return None

    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume(expected=None):
        tok = tokens[pos[0]]
        if expected is not None and tok != expected:
            raise Exception(
                f"Taskipelago: cost expression expected '{expected}' but got '{tok!r}'."
            )
        pos[0] += 1
        return tok

    def parse_or():
        left = parse_and()
        nodes = [left]
        while peek() == "||":
            consume("||")
            nodes.append(parse_and())
        return _simplify("or", nodes)

    def parse_and():
        left = parse_atom()
        nodes = [left]
        while peek() in ("&&", ","):
            consume()
            nodes.append(parse_atom())
        return _simplify("and", nodes)

    def parse_atom():
        tok = peek()
        if tok is None:
            raise Exception("Taskipelago: unexpected end of cost expression.")
        if tok == "(":
            consume("(")
            node = parse_or()
            consume(")")
            return node
        if isinstance(tok, tuple) and tok[0] == "cost_item":
            consume()
            _, name, count = tok
            if name not in consumable_names:
                raise Exception(
                    f"Taskipelago: '{name}' in cost expression is not a known consumable item name."
                )
            if count < 1:
                raise Exception(
                    f"Taskipelago: cost count for '{name}' must be at least 1."
                )
            return ("cost_group", name, count)
        raise Exception(
            f"Taskipelago: unexpected token {tok!r} in cost expression."
        )

    result = parse_or()
    if pos[0] != len(tokens):
        raise Exception(
            f"Taskipelago: unexpected trailing token {tokens[pos[0]]!r} in cost expression."
        )
    return result


def _tokenize_cost(text: str, item_names_ordered: "list[str] | None") -> list:
    """Tokenize a cost expression into a flat token list."""
    tokens = []
    i = 0
    while i < len(text):
        c = text[i]

        if c.isspace():
            i += 1
            continue

        if text[i:i+2] == "&&":
            tokens.append("&&")
            i += 2
            continue

        if text[i:i+2] == "||":
            tokens.append("||")
            i += 2
            continue

        if c in ("(", ")", ","):
            tokens.append(c)
            i += 1
            continue

        # Quoted name: "Name"*N or "Name" (bare = cost 1)
        if c == '"':
            j = i + 1
            while j < len(text) and text[j] != '"':
                j += 1
            if j >= len(text):
                raise Exception("Taskipelago: unclosed quote in cost expression.")
            name = text[i+1:j]
            j += 1  # skip closing quote
            count = 1
            if j < len(text) and text[j] == '*':
                k = j + 1
                while k < len(text) and text[k].isdigit():
                    k += 1
                if k > j + 1:
                    count = int(text[j+1:k])
                    j = k
            tokens.append(("cost_item", name, count))
            i = j
            continue

        # Numeric index: idx*N (1-based item index followed by count)
        if c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            idx_1 = int(text[i:j])
            count = 1
            if j < len(text) and text[j] == '*':
                k = j + 1
                while k < len(text) and text[k].isdigit():
                    k += 1
                if k > j + 1:
                    count = int(text[j+1:k])
                    j = k
            # Resolve index to item name
            if item_names_ordered and 1 <= idx_1 <= len(item_names_ordered):
                name = item_names_ordered[idx_1 - 1]
            else:
                name = str(idx_1)  # leave as string; validator will catch it
            tokens.append(("cost_item", name, count))
            i = j
            continue

        raise Exception(
            f"Taskipelago: unexpected character '{c}' in cost expression."
        )

    return tokens


def collect_cost_groups(node: "Node | None") -> "list[tuple[str, int]]":
    """Return list of (name, count) for all cost_group leaves in a cost AST."""
    if node is None:
        return []
    if isinstance(node, int):
        return []
    op = node[0]
    if op == "cost_group":
        return [(node[1], node[2])]
    if op in ("and", "or"):
        result = []
        for child in node[1]:
            result.extend(collect_cost_groups(child))
        return result
    return []


def collect_cost_groups_per_branch(node: "Node | None") -> "list[list[tuple[str, int]]]":
    """
    Return a list of branches. Each branch is a flat list of (name, count) AND requirements.
    For a pure AND tree: returns one branch.
    For an OR tree: returns one branch per OR child.
    Mixed trees are flattened conservatively (OR at the top level only).
    """
    if node is None:
        return [[]]
    op = node[0] if isinstance(node, tuple) else None
    if op == "or":
        branches = []
        for child in node[1]:
            branches.extend(collect_cost_groups_per_branch(child))
        return branches
    # AND or leaf: flatten into a single branch
    return [collect_cost_groups(node)]


def eval_cost_node(
    node: "Node | None",
    available: "dict[str, int]",
) -> bool:
    """
    Evaluate a cost AST against available consumable counts.
    available: dict {name -> remaining_count}
    Returns True if the cost can be satisfied with available resources.
    """
    if node is None:
        return True
    op = node[0]
    if op == "cost_group":
        _, name, count = node
        return available.get(name, 0) >= count
    if op == "and":
        # AND: check all, but track running deduction to avoid double-counting
        remaining = dict(available)
        for child in node[1]:
            if not _eval_cost_and_deduct(child, remaining):
                return False
        return True
    if op == "or":
        return any(eval_cost_node(child, available) for child in node[1])
    return True


def _eval_cost_and_deduct(node: "Node | None", remaining: dict) -> bool:
    """Evaluate and deduct from 'remaining' in-place for AND evaluation."""
    if node is None:
        return True
    op = node[0]
    if op == "cost_group":
        _, name, count = node
        if remaining.get(name, 0) < count:
            return False
        remaining[name] = remaining.get(name, 0) - count
        return True
    if op == "and":
        for child in node[1]:
            if not _eval_cost_and_deduct(child, remaining):
                return False
        return True
    if op == "or":
        # For nested OR inside AND: evaluate without deducting (conservative)
        return eval_cost_node(node, remaining)
    return True


def _has_or(node: Node | None) -> bool:
    """Return True if any OR node exists in the AST."""
    if node is None or isinstance(node, int):
        return False
    op = node[0]
    if op in ("group_ref", "group_count", "region_ref", "region_abs", "group", "region", "seq_flag"):
        return False
    if op == "or":
        return True
    _, children = node
    return any(_has_or(child) for child in children)
