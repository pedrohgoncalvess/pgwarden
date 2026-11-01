"""Conservative index coverage checks; unsupported SQL requires plan review."""

import re
from dataclasses import dataclass

import sqlparse
from sqlparse.sql import Comparison, Identifier, Where
from sqlparse.tokens import Keyword, Literal, Name, Operator, Punctuation


IDENT = r'(?:"(?:[^"]|"")+"|[a-zA-Z_][a-zA-Z_0-9$]*)'


def identifier(value: str) -> str:
    return value[1:-1].replace('""', '"') if value.startswith('"') else value.lower()


def quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


@dataclass(frozen=True)
class IndexShape:
    name: str
    keys: tuple[str, ...]
    certain: bool


def index_shape(name: str, definition: str, kind: str = "btree") -> IndexShape:
    # Only simple default B-tree keys can establish coverage. Partial indexes,
    # expressions, collations and operator classes need planner validation.
    match = re.search(r'\bON\s+(?:ONLY\s+)?' + IDENT + r'(?:\.' + IDENT +
                      r')?\s+(?:USING\s+\w+\s*)?\((.*?)\)(.*)$', definition, re.I | re.S)
    if not match or kind != "btree":
        return IndexShape(name, (), False)
    keys = []
    for part in match[1].split(','):
        key = re.fullmatch(r'\s*(' + IDENT + r')(?:\s+(?:ASC|DESC))?(?:\s+NULLS\s+(?:FIRST|LAST))?\s*', part, re.I)
        if not key:
            return IndexShape(name, (), False)
        keys.append(identifier(key[1]))
    tail = match[2].strip().rstrip(';').strip()
    # INCLUDE columns are payload, never search keys.
    if tail and not re.fullmatch(r'INCLUDE\s*\(\s*' + IDENT + r'(?:\s*,\s*' + IDENT + r')*\s*\)', tail, re.I):
        return IndexShape(name, tuple(keys), False)
    return IndexShape(name, tuple(keys), True)


def predicate_roles(sql: str, column_names: set[str]) -> tuple[set[str], set[str], bool]:
    """Recognize AND-connected simple comparisons in a single-table SELECT.

    Joins, OR, subqueries, functions and unresolved predicates remain uncertain.
    This intentionally does not infer equality from the existing column-hit flags.
    """
    statements = sqlparse.parse(sql)
    if len(statements) != 1 or statements[0].get_type() != 'SELECT':
        return set(), set(), False
    statement = statements[0]
    if sum(t.ttype is Keyword.DML and t.normalized == 'SELECT' for t in statement.flatten()) != 1:
        return set(), set(), False
    if sum(t.ttype is Keyword and t.normalized == 'FROM' for t in statement.tokens) != 1:
        return set(), set(), False
    if any(t.ttype is Keyword and ('JOIN' in t.normalized or t.normalized in {'UNION', 'INTERSECT', 'EXCEPT'})
           for t in statement.flatten()):
        return set(), set(), False
    # A comma-separated FROM list or CTE must not be treated as one table.
    from_index = next(i for i, t in enumerate(statement.tokens) if t.ttype is Keyword and t.normalized == 'FROM')
    source = next((t for t in statement.tokens[from_index + 1:] if not t.is_whitespace), None)
    if not isinstance(source, Identifier) or any(t.value == '(' for t in source.flatten()):
        return set(), set(), False
    where = next((t for t in statement.tokens if isinstance(t, Where)), None)
    if where is None:
        return set(), set(), False
    equality, ranges = set(), set()
    expect_comparison = True
    for token in where.tokens[1:]:
        if token.is_whitespace or token.ttype is Punctuation and token.value == ';':
            continue
        if not expect_comparison and token.ttype is Keyword and token.normalized == 'AND':
            expect_comparison = True
            continue
        if not expect_comparison or not isinstance(token, Comparison):
            return equality, ranges, False
        parts = [t for t in token.tokens if not t.is_whitespace]
        if len(parts) != 3 or not isinstance(parts[0], Identifier) or parts[1].ttype not in Operator.Comparison:
            return equality, ranges, False
        left, operator, right = parts
        column = re.fullmatch(r'(?:' + IDENT + r'\.)?(' + IDENT + r')', left.value)
        if not column:
            return equality, ranges, False
        name = identifier(column[1])
        if name not in column_names or not (right.ttype in Literal or right.ttype in Name.Placeholder):
            return equality, ranges, False
        if operator.value == '=':
            equality.add(name)
        elif operator.value in {'>', '>=', '<', '<='}:
            ranges.add(name)
        else:
            return equality, ranges, False
        expect_comparison = False
    return equality, ranges, not expect_comparison and equality | ranges == column_names


def coverage(shapes: list[IndexShape], equality: set[str], ranges: set[str], understood: bool) -> tuple[str, list[str]]:
    """Return covered/partial/uncertain/missing and relevant index names."""
    partial = []
    for shape in shapes:
        if not shape.certain or not understood:
            continue
        remaining = equality | ranges
        for key in shape.keys:
            if key in equality:
                remaining = remaining - {key}
            elif key in ranges:
                remaining = remaining - {key}
                break
            else:
                break
        if not remaining:
            return 'covered', [shape.name]
        if shape.keys and shape.keys[0] in equality | ranges:
            partial.append(shape.name)
    if partial:
        return 'partial', partial
    if not understood or any(not shape.certain for shape in shapes):
        return 'uncertain', [shape.name for shape in shapes]
    return 'missing', []
