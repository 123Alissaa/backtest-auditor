"""Prepare strategy source for the LLM without giving away the answer.

Our sample strategies carry hints for humans ("# BUG: ...", docstrings that say
"Broken (lookahead)", PLANTED_BUG, NAME = "lookahead"). If Nemotron could read
those, "the AI found the bug" would be fake. We blank them out but keep every
line in place, so line numbers in the plan still match the original file.
"""
import ast
import io
import tokenize

HIDDEN_NAMES = {"PLANTED_BUG", "NAME"}


def _docstring_nodes(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                yield first


def strip_hints(source: str) -> str:
    lines = source.splitlines()
    tree = ast.parse(source)
    blank: set[int] = set()  # 1-based line numbers to empty out

    for node in _docstring_nodes(tree):
        blank.update(range(node.lineno, node.end_lineno + 1))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in HIDDEN_NAMES for t in node.targets):
            blank.update(range(node.lineno, node.end_lineno + 1))

    # Cut comments off at their column (tokenize knows a '#' inside a string isn't a comment).
    cuts: dict[int, int] = {}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            cuts[tok.start[0]] = tok.start[1]

    out = []
    for i, line in enumerate(lines, start=1):
        if i in blank:
            out.append("")
        elif i in cuts:
            out.append(line[: cuts[i]].rstrip())
        else:
            out.append(line)
    return "\n".join(out)


def numbered(source: str) -> str:
    """Prefix each line with its 1-based number, the format the LLM sees and cites."""
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(source.splitlines(), start=1))
