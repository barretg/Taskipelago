"""
Boolean prereq expression parser for Taskipelago.

Grammar:
    expr     := or_expr
    or_expr  := and_expr ('||' and_expr)*
    and_expr := atom ('&&' atom | ',' atom)*
    atom     := INTEGER | INTEGER*INTEGER | NAME | NAME*INTEGER | NAME-INTEGER | '(' expr ')'

    INTEGER   - 1-based task/item index
    INDEX*Y   - item prereqs only: the first Y copies of item INDEX (a row with count > 1)
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
    ("item_copies", idx, y)     - first y copies of item idx (0-based); expanded to an AND of
                                  YAML indices by _translate_prereq_indices before generation

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

# Everything above plus the numeric-expression constants (defined below): none of
# these may be used as a region, progressive group or item name.
RESERVED_NAMES = {
    "prev", "sequential",
    "n_tasks", "n_tasks_unlocked", "n_tasks_locked", "n_tasks_completed",
}

# Region and group names never contain digits, so a trailing -N / *N suffix is
# unambiguous whatever other characters the name holds (v1.1 F8).
NAME_DASH_RE = _re.compile(r'^(\D+)-(\d+)$')
NAME_STAR_RE = _re.compile(r'^(\D+)\*(\d+)$')


# ---------------------------------------------------------------------------
# Numeric expression sub-grammar (clicker mode)
# ---------------------------------------------------------------------------
# Grammar:
#   num_expr := num_term (('+' | '-') num_term)*
#   num_term := num_unary (('*' | '/') num_unary)*
#   num_unary := ('-' | '+')? num_atom
#   num_atom := NUMBER | CONSTANT | '(' num_expr ')'
#
# AST is plain JSON-serializable data so it can ship in slot_data and be
# re-evaluated on the client by web-client/js/shared/num_expr.js:
#   {"num": 1.5}
#   {"const": "N_TASKS"}
#   {"op": "+", "l": <node>, "r": <node>}      op in + - * /
# ---------------------------------------------------------------------------

#: Every constant a numeric expression may reference.
NUM_CONSTANTS = ("N_TASKS", "N_TASKS_UNLOCKED", "N_TASKS_LOCKED", "N_TASKS_COMPLETED")
#: Constants that change during play; only clicker numeric fields may use them.
LIVE_NUM_CONSTANTS = ("N_TASKS_UNLOCKED", "N_TASKS_LOCKED", "N_TASKS_COMPLETED")

_NUM_TOKEN_RE = _re.compile(r'\s*(?:(\d+\.\d*|\.\d+|\d+)|([A-Za-z_][A-Za-z0-9_]*)|([-+*/()]))')


def _num_lit(text: str):
    """Number literals keep an int form when integral, so the JSON AST matches
    the JavaScript port byte for byte."""
    v = float(text)
    return int(v) if v.is_integer() else v


def _num_tokenize(text: str, label: str, loc: str) -> list:
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        m = _NUM_TOKEN_RE.match(text, i)
        if not m or m.end() == i:
            raise Exception(
                f"Taskipelago: unexpected character '{text[i]}' in {label}{loc}."
            )
        if m.group(1) is not None:
            tokens.append(("num", _num_lit(m.group(1))))
        elif m.group(2) is not None:
            tokens.append(("name", m.group(2)))
        else:
            tokens.append(("sym", m.group(3)))
        i = m.end()
    return tokens


def parse_num_expr(text: str, label: str = "numeric expression", location_label: str | None = None,
                   allow_live: bool = True) -> dict:
    """
    Parse a numeric expression into a JSON-serializable AST.
    allow_live=False rejects the constants that change during play.
    Raises Exception (Taskipelago: ...) on any syntax or constant error.
    """
    loc = f" on {location_label}" if location_label else ""
    src = str(text or "").strip()
    if not src:
        raise Exception(f"Taskipelago: empty {label}{loc}.")
    tokens = _num_tokenize(src, label, loc)
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def sym(s):
        t = peek()
        return t is not None and t[0] == "sym" and t[1] == s

    def parse_expr():
        node = parse_term()
        while sym("+") or sym("-"):
            op = tokens[pos[0]][1]
            pos[0] += 1
            node = {"op": op, "l": node, "r": parse_term()}
        return node

    def parse_term():
        node = parse_unary()
        while sym("*") or sym("/"):
            op = tokens[pos[0]][1]
            pos[0] += 1
            node = {"op": op, "l": node, "r": parse_unary()}
        return node

    def parse_unary():
        if sym("-"):
            pos[0] += 1
            return {"op": "-", "l": {"num": 0}, "r": parse_unary()}
        if sym("+"):
            pos[0] += 1
            return parse_unary()
        return parse_atom()

    def parse_atom():
        t = peek()
        if t is None:
            raise Exception(f"Taskipelago: unexpected end of {label}{loc}.")
        if t[0] == "num":
            pos[0] += 1
            return {"num": t[1]}
        if t[0] == "name":
            pos[0] += 1
            name = t[1]
            if name not in NUM_CONSTANTS:
                raise Exception(
                    f"Taskipelago: unknown name '{name}' in {label}{loc} "
                    f"(valid constants: {', '.join(NUM_CONSTANTS)})."
                )
            if not allow_live and name in LIVE_NUM_CONSTANTS:
                raise Exception(
                    f"Taskipelago: '{name}' changes during play and cannot be used "
                    f"in {label}{loc}; only N_TASKS is allowed there."
                )
            return {"const": name}
        if t[1] == "(":
            pos[0] += 1
            node = parse_expr()
            if not sym(")"):
                raise Exception(f"Taskipelago: missing ')' in {label}{loc}.")
            pos[0] += 1
            return node
        raise Exception(f"Taskipelago: unexpected token '{t[1]}' in {label}{loc}.")

    result = parse_expr()
    if pos[0] != len(tokens):
        raise Exception(
            f"Taskipelago: unexpected token '{tokens[pos[0]][1]}' in {label}{loc}."
        )
    return result


def num_expr_constants(node) -> set:
    """Every constant name referenced by a numeric-expression AST."""
    if not isinstance(node, dict):
        return set()
    if "const" in node:
        return {node["const"]}
    if "op" in node:
        return num_expr_constants(node["l"]) | num_expr_constants(node["r"])
    return set()


def num_expr_is_static(node) -> bool:
    """True if the expression never changes during play (no live constants)."""
    return not (num_expr_constants(node) & set(LIVE_NUM_CONSTANTS))


def eval_num_expr(node, bindings: dict, label: str = "numeric expression",
                  location_label: str | None = None) -> float:
    """Evaluate a numeric-expression AST with {constant: value} bindings."""
    loc = f" on {location_label}" if location_label else ""
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return float(node)
    if not isinstance(node, dict):
        raise Exception(f"Taskipelago: malformed {label}{loc}.")
    if "num" in node:
        return float(node["num"])
    if "const" in node:
        name = node["const"]
        if name not in bindings:
            raise Exception(f"Taskipelago: '{name}' has no value in {label}{loc}.")
        return float(bindings[name])
    op = node.get("op")
    left = eval_num_expr(node["l"], bindings, label, location_label)
    right = eval_num_expr(node["r"], bindings, label, location_label)
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        if right == 0:
            raise Exception(f"Taskipelago: division by zero in {label}{loc}.")
        return left / right
    raise Exception(f"Taskipelago: malformed {label}{loc}.")


def fold_num_expr(node, n_tasks: int, label: str = "numeric expression",
                  location_label: str | None = None) -> float:
    """Evaluate a static (N_TASKS-only) expression to a number."""
    return eval_num_expr(node, {"N_TASKS": n_tasks}, label, location_label)


def num_expr_to_int(value: float) -> int:
    """Integer-required fields round up, minimum 1 (matches the N% rounding rule)."""
    return max(1, int(_math.ceil(value - 1e-9)))


def num_expr_to_json(node):
    """The AST as it ships in slot_data: a plain number when it is a constant fold."""
    if isinstance(node, dict) and "num" in node:
        return node["num"]
    return node


def split_name_suffix(tok: str, known_names=None) -> Tuple[str, "int | dict | None", str]:
    """
    Split a name token into (base, n, mode); mode is "dash", "star" or "none".

    A bare integer suffix ("chores-75", "grp*5") takes the original path and
    returns an int. A suffix that references N_TASKS ("chores-N_TASKS",
    "grp*N_TASKS/2") returns a numeric-expression AST instead; the caller folds
    it to an integer. Only suffixes that mention a constant take that path, so
    every token that parsed before parses identically.
    known_names, when given, restricts which prefixes may be split off, which
    disambiguates names that themselves contain '-'.
    """
    m = NAME_DASH_RE.match(tok)
    if m and (known_names is None or m.group(1) in known_names):
        return m.group(1), int(m.group(2)), "dash"
    m2 = NAME_STAR_RE.match(tok)
    if m2 and (known_names is None or m2.group(1) in known_names):
        return m2.group(1), int(m2.group(2)), "star"
    if "N" in tok:  # every constant starts with N; cheap prefilter
        for i, ch in enumerate(tok):
            if i == 0 or ch not in "-*":
                continue
            base, rest = tok[:i], tok[i + 1:]
            if not rest:
                continue
            if known_names is not None and base not in known_names:
                continue
            try:
                ast = parse_num_expr(rest, allow_live=True)
            except Exception:
                continue
            consts = num_expr_constants(ast)
            if not consts:
                continue  # a plain number is not a valid suffix here
            live = sorted(consts & set(LIVE_NUM_CONSTANTS))
            if live:
                raise Exception(
                    f"Taskipelago: '{live[0]}' changes during play and cannot be used in "
                    f"'{tok}'; only N_TASKS is allowed in a prereq, goal or cost suffix."
                )
            return base, ast, ("dash" if ch == "-" else "star")
    if m:
        return m.group(1), int(m.group(2)), "dash"
    if m2:
        return m2.group(1), int(m2.group(2)), "star"
    return tok, None, "none"


def resolve_suffix_int(suffix, n_tasks: int, label: str, loc: str) -> "int | None":
    """Fold a split_name_suffix result to an integer (expressions round up, min 1)."""
    if suffix is None or isinstance(suffix, int):
        return suffix
    return num_expr_to_int(fold_num_expr(suffix, n_tasks, label, loc))


def parse_prereq(
    text: str,
    n_tasks: int,
    task_index: int,
    label: str,
    known_groups=None,
    known_regions=None,
    location_label: str | None = None,
    n_tasks_const: int | None = None,
) -> Node | None:
    """
    Parse a prereq expression string into an AST.
    Returns None if the expression is empty.
    Raises Exception on syntax or range errors.
    All integer leaf values are 0-based task/item indices.
    known_groups: set of valid group names (or None)
    known_regions: set of valid region names (or None)
    location_label: if given, used in error messages instead of "task {task_index+1}"
                     (e.g. "region 'chores'") - for non-task callers like region prereqs.
    n_tasks_const: value bound to N_TASKS in -N / *N suffix expressions; defaults to
                     n_tasks (which is the item count for item prereqs).
    """
    text = text.strip()
    if not text:
        return None

    loc = location_label or f"task {task_index + 1}"

    tokens = _tokenize(text, task_index, label, location_label)
    if not tokens:
        return None

    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume(expected=None):
        tok = tokens[pos[0]]
        if expected is not None and tok != expected:
            raise Exception(
                f"Taskipelago: expected '{expected}' but got '{_tok_text(tok)}' "
                f"in {label} on {loc}."
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
                f"Taskipelago: unexpected end of {label} expression on {loc}."
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
                    f"Taskipelago: {label} index '{idx_1}' on {loc} "
                    f"is out of range (1..{n_tasks})."
                )
            return idx_1 - 1  # 0-based
        if isinstance(tok, tuple) and tok[0] == "copies":
            consume()
            _, idx_1, y = tok
            if label != "item prereq":
                raise Exception(
                    f"Taskipelago: '{idx_1}*{y}' copy counts can only be used in item prereqs "
                    f"(used in {label} on {loc})."
                )
            if idx_1 < 1 or idx_1 > n_tasks:
                raise Exception(
                    f"Taskipelago: {label} index '{idx_1}' on {loc} "
                    f"is out of range (1..{n_tasks})."
                )
            if y < 1:
                raise Exception(
                    f"Taskipelago: copy count in '{idx_1}*{y}' on {loc} must be at least 1."
                )
            return ("item_copies", idx_1 - 1, y)
        if isinstance(tok, str) and tok not in ("&&", "||", "(", ")", ","):
            consume()
            if tok in RESERVED_WORDS:
                if label != "task prereq":
                    raise Exception(
                        f"Taskipelago: '{tok}' can only be used in task prereqs "
                        f"(used in {label} on {loc})."
                    )
                if tok == "prev":
                    if task_index < 1:
                        raise Exception(
                            f"Taskipelago: 'prev' used on {loc} "
                            f"but there is no previous task."
                        )
                    return task_index - 1
                return ("seq_flag",)
            _known = set()
            if known_groups:
                _known |= set(known_groups)
            if known_regions:
                _known |= set(known_regions)
            base, suffix, mode = split_name_suffix(tok, _known or None)
            suffix = resolve_suffix_int(
                suffix, n_tasks if n_tasks_const is None else n_tasks_const, label, loc
            )
            if known_groups is not None and base in known_groups:
                if mode == "star":
                    return ("group_count", base, suffix)
                return ("group_ref", base, suffix)
            if known_regions is not None and base in known_regions:
                if mode == "star":
                    return ("region_abs", base, suffix)
                return ("region_ref", base, suffix)
            raise Exception(
                f"Taskipelago: unknown name '{base}' in {label} on {loc}."
            )
        raise Exception(
            f"Taskipelago: unexpected token '{tok}' in {label} on {loc}."
        )

    result = parse_expr()

    if pos[0] != len(tokens):
        raise Exception(
            f"Taskipelago: unexpected token '{_tok_text(tokens[pos[0]])}' in {label} on {loc}."
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
    if op in ("group_count", "region_abs", "seq_flag", "item_copies"):
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
    if op == "item_copies":
        _, idx, y = node
        return ("atom", f"{idx + 1}*{y}")
    raise ValueError(f"Cannot serialize AST op: {op}")


def _tok_text(tok) -> str:
    """Token as written, for error messages (copies tokens back to INDEX*Y)."""
    if isinstance(tok, tuple) and tok[0] == "copies":
        return f"{tok[1]}*{tok[2]}"
    return str(tok)


def _tokenize(text: str, task_index: int, label: str, location_label: str | None = None) -> list:
    """
    Convert expression string into a flat list of tokens:
    integers, strings (named refs), '(', ')', '&&', '||', ','
    """
    loc = location_label or f"task {task_index + 1}"
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
            # INDEX*Y copy count (no spaces around '*')
            if j < len(text) and text[j] == '*':
                k = j + 1
                while k < len(text) and text[k].isdigit():
                    k += 1
                if k > j + 1:
                    tokens.append(("copies", int(text[i:j]), int(text[j+1:k])))
                    i = k
                    continue
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
            f"Taskipelago: unexpected character '{c}' in {label} on {loc}."
        )

    return tokens


def collect_leaves(node: Node | None) -> List[int]:
    """Return all 0-based task/item indices (int leaves) referenced in an AST node."""
    if node is None:
        return []
    if isinstance(node, int):
        return [node]
    op = node[0]
    if op == "item_copies":
        return [node[1]]
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
    if op in ("group_ref", "group_count", "region_ref", "region_abs", "group", "region", "item_copies"):
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
    if op in ("group", "group_count", "region_ref", "region_abs", "region", "seq_flag", "item_copies"):
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
    if op in ("group", "group_ref", "region_ref", "region_abs", "region", "seq_flag", "item_copies"):
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
    if op in ("region", "region_abs", "group_ref", "group_count", "group", "seq_flag", "item_copies"):
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
    if op in ("region", "region_ref", "group_ref", "group_count", "group", "seq_flag", "item_copies"):
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
    if op == "item_copies":
        # Normally expanded before parsing; a lone copy list only knows its first copy here.
        return state.has(item_names[node[1]], player)
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
    n_tasks: int | None = None,
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

    tokens = _tokenize_cost(text, item_names_ordered, n_tasks)
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


_COST_SUFFIX_CHARS = set("0123456789._+-*/ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def _read_count_suffix(text: str, start: int, n_tasks: int | None) -> "Tuple[int, int] | None":
    """
    Read the count after a '*' at position `start` (the '*' itself).
    Returns (count, next_index), or None when there is no count there.
    Accepts a bare integer (the original grammar) or an N_TASKS expression.
    """
    k = start + 1
    while k < len(text) and text[k].isdigit():
        k += 1
    digits_end = k
    j = start + 1
    while j < len(text) and text[j] in _COST_SUFFIX_CHARS:
        j += 1
    if j > digits_end and "N" in text[start + 1:j]:
        try:
            ast = parse_num_expr(text[start + 1:j], "cost count", None, allow_live=True)
        except Exception:
            ast = None
        if ast is not None and num_expr_constants(ast):
            live = sorted(num_expr_constants(ast) & set(LIVE_NUM_CONSTANTS))
            if live:
                raise Exception(
                    f"Taskipelago: '{live[0]}' changes during play and cannot be used in a "
                    f"cost expression; only N_TASKS is allowed there."
                )
            return num_expr_to_int(fold_num_expr(ast, n_tasks or 0, "cost count")), j
    if digits_end > start + 1:
        return int(text[start + 1:digits_end]), digits_end
    return None


def _tokenize_cost(text: str, item_names_ordered: "list[str] | None", n_tasks: int | None = None) -> list:
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
                got = _read_count_suffix(text, j, n_tasks)
                if got is not None:
                    count, j = got
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
                got = _read_count_suffix(text, j, n_tasks)
                if got is not None:
                    count, j = got
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
    if op in ("group_ref", "group_count", "region_ref", "region_abs", "group", "region", "seq_flag", "item_copies"):
        return False
    if op == "or":
        return True
    _, children = node
    return any(_has_or(child) for child in children)
