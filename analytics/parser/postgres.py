from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import sqlparse
from sqlparse import tokens as T

from analytics.parser.models import ColumnHit, ColumnMeta, ParsedQuery, TableHit, TableMeta


CLAUSE_END = {
    "WHERE",
    "GROUP BY",
    "HAVING",
    "ORDER BY",
    "LIMIT",
    "OFFSET",
    "FETCH",
    "FOR",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "RETURNING",
}
JOIN_KEYWORDS = {
    "JOIN",
    "INNER JOIN",
    "LEFT JOIN",
    "LEFT OUTER JOIN",
    "RIGHT JOIN",
    "RIGHT OUTER JOIN",
    "FULL JOIN",
    "FULL OUTER JOIN",
    "CROSS JOIN",
}
TABLE_STOP = CLAUSE_END | {"ON", "USING", "JOIN"} | JOIN_KEYWORDS
EXPR_STOP_WORDS = {
    "AS",
    "AND",
    "OR",
    "IN",
    "IS",
    "NULL",
    "NOT",
    "LIKE",
    "ILIKE",
    "BETWEEN",
    "TRUE",
    "FALSE",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
}


@dataclass(frozen=True)
class SqlToken:
    value: str
    upper: str
    ttype: object


@dataclass
class TableRef:
    schema_name: str
    table_name: str
    alias: str | None
    meta: TableMeta | None


@dataclass(frozen=True)
class ColumnRef:
    qualifier: str | None
    column_name: str
    table_ref: TableRef | None
    column_meta: ColumnMeta | None


class QueryParser:
    def __init__(self, metadata: Iterable[TableMeta], default_schema: str = "public"):
        self.default_schema = default_schema
        self.metadata = list(metadata)
        self.tables_by_name = {
            (table.schema_name.lower(), table.name.lower()): table for table in self.metadata
        }
        self.tables_by_unqualified = {}
        for table in self.metadata:
            self.tables_by_unqualified.setdefault(table.name.lower(), []).append(table)

    def parse(self, sql: str) -> ParsedQuery:
        parsed = ParsedQuery()
        for statement in sqlparse.parse(sql):
            tokens = self._tokens(statement)
            if not tokens:
                continue
            self._parse_statement(tokens, parsed)
        parsed.tables = sorted(
            parsed.tables,
            key=lambda item: (item.schema_name, item.table_name, item.alias or ""),
        )
        parsed.columns = sorted(
            parsed.columns,
            key=lambda item: (item.schema_name, item.table_name, item.column_name),
        )
        return parsed

    def _parse_statement(self, tokens: list[SqlToken], parsed: ParsedQuery):
        cte_names = self._parse_ctes(tokens, parsed)
        select_range = self._clause_range(tokens, "SELECT", {"FROM"})
        from_range = self._clause_range(tokens, "FROM", CLAUSE_END)
        if not from_range:
            return

        table_refs = self._parse_table_refs(tokens[from_range[0] : from_range[1]], cte_names, parsed)
        aliases = self._alias_map(table_refs)
        table_hits = self._table_hits(table_refs)
        for key, hit in table_hits.items():
            self._merge_table(parsed, key, hit)

        if select_range:
            self._parse_select_columns(tokens[select_range[0] : select_range[1]], table_refs, aliases, parsed)

        for start, end in self._condition_ranges(tokens):
            self._mark_condition_columns(tokens[start:end], table_refs, aliases, parsed, is_join=False)

        for start, end in self._join_on_ranges(tokens):
            self._mark_condition_columns(tokens[start:end], table_refs, aliases, parsed, is_join=True)

    def _tokens(self, statement) -> list[SqlToken]:
        result = []
        for token in statement.flatten():
            if token.is_whitespace or token.ttype in T.Comment:
                continue
            value = token.value
            if not value:
                continue
            result.append(SqlToken(value=value, upper=value.upper(), ttype=token.ttype))
        return result

    def _parse_ctes(self, tokens: list[SqlToken], parsed: ParsedQuery) -> set[str]:
        cte_names: set[str] = set()
        if not tokens or tokens[0].upper != "WITH":
            return cte_names
        i = 1
        while i < len(tokens):
            if tokens[i].upper == "RECURSIVE":
                i += 1
                continue
            parts, i = self._read_identifier(tokens, i)
            if not parts:
                break
            cte_names.add(parts[-1].lower())
            if i < len(tokens) and tokens[i].upper == "AS":
                i += 1
            if i < len(tokens) and tokens[i].value == "(":
                sub_tokens, i = self._read_parenthesized(tokens, i)
                self._parse_statement(sub_tokens, parsed)
            if i < len(tokens) and tokens[i].value == ",":
                i += 1
                continue
            break
        return cte_names

    def _clause_range(
        self,
        tokens: list[SqlToken],
        start_keyword: str,
        end_keywords: set[str],
    ) -> tuple[int, int] | None:
        depth = 0
        start = None
        for i, token in enumerate(tokens):
            depth = self._updated_depth(depth, token, before=True)
            if depth == 0 and start is None and token.upper == start_keyword:
                start = i + 1
            elif depth == 0 and start is not None and token.upper in end_keywords:
                return start, i
            depth = self._updated_depth(depth, token, before=False)
        if start is not None:
            return start, len(tokens)
        return None

    def _condition_ranges(self, tokens: list[SqlToken]) -> list[tuple[int, int]]:
        ranges = []
        for keyword in ("WHERE", "HAVING"):
            item = self._clause_range(tokens, keyword, CLAUSE_END - {keyword})
            if item:
                ranges.append(item)
        return ranges

    def _join_on_ranges(self, tokens: list[SqlToken]) -> list[tuple[int, int]]:
        ranges = []
        depth = 0
        i = 0
        while i < len(tokens):
            token = tokens[i]
            depth = self._updated_depth(depth, token, before=True)
            if depth == 0 and token.upper == "ON":
                start = i + 1
                j = start
                inner_depth = 0
                while j < len(tokens):
                    current = tokens[j]
                    inner_depth = self._updated_depth(inner_depth, current, before=True)
                    if inner_depth == 0 and (current.upper in JOIN_KEYWORDS or current.upper in CLAUSE_END):
                        break
                    inner_depth = self._updated_depth(inner_depth, current, before=False)
                    j += 1
                ranges.append((start, j))
                i = j
                continue
            depth = self._updated_depth(depth, token, before=False)
            i += 1
        return ranges

    def _parse_table_refs(
        self,
        tokens: list[SqlToken],
        cte_names: set[str],
        parsed: ParsedQuery,
    ) -> list[TableRef]:
        refs: list[TableRef] = []
        i = 0
        expecting_table = True
        while i < len(tokens):
            token = tokens[i]
            if token.value == "," or token.upper in JOIN_KEYWORDS:
                expecting_table = True
                i += 1
                continue
            if token.upper in {"ON", "USING"}:
                expecting_table = False
                i += 1
                continue
            if not expecting_table:
                i += 1
                continue
            if token.upper in {"LATERAL", "ONLY"}:
                i += 1
                continue
            if token.value == "(":
                sub_tokens, i = self._read_parenthesized(tokens, i)
                self._parse_statement(sub_tokens, parsed)
                _, i = self._read_optional_alias(tokens, i)
                expecting_table = False
                continue
            parts, next_i = self._read_identifier(tokens, i)
            if not parts:
                i += 1
                continue
            if next_i < len(tokens) and tokens[next_i].value == "(":
                _, i = self._read_parenthesized(tokens, next_i)
                _, i = self._read_optional_alias(tokens, i)
                expecting_table = False
                continue
            table_name = parts[-1]
            schema_name = parts[-2] if len(parts) >= 2 else self.default_schema
            alias, i = self._read_optional_alias(tokens, next_i)
            if table_name.lower() not in cte_names:
                meta = self._find_table(schema_name, table_name)
                if meta is not None:
                    schema_name = meta.schema_name
                    table_name = meta.name
                refs.append(TableRef(schema_name=schema_name, table_name=table_name, alias=alias, meta=meta))
            expecting_table = False
        return refs

    def _parse_select_columns(
        self,
        tokens: list[SqlToken],
        table_refs: list[TableRef],
        aliases: dict[str, TableRef],
        parsed: ParsedQuery,
    ):
        for expr in self._split_top_level(tokens, ","):
            trimmed = self._trim_alias(expr)
            star = self._star_qualifier(trimmed)
            if star is not False:
                for ref in self._refs_for_star(star, table_refs, aliases):
                    for column in ref.meta.columns if ref.meta else ():
                        self._merge_column(parsed, ref, column, is_selected=True)
                continue
            for ref in self._column_refs(trimmed, table_refs, aliases):
                self._merge_column(parsed, ref.table_ref, ref.column_meta, ref.column_name, is_selected=True)

    def _mark_condition_columns(
        self,
        tokens: list[SqlToken],
        table_refs: list[TableRef],
        aliases: dict[str, TableRef],
        parsed: ParsedQuery,
        is_join: bool,
    ):
        refs = self._column_refs(tokens, table_refs, aliases)
        foreign_refs: set[tuple[str, str, str]] = set()
        foreign_tables: set[tuple[str, str, str | None]] = set()
        if is_join:
            for left, right in self._equality_pairs(tokens, table_refs, aliases):
                if self._is_foreign_pair(left, right):
                    for item in (left, right):
                        if item.table_ref:
                            foreign_refs.add(self._column_key(item.table_ref, item.column_name))
                            foreign_tables.add(self._table_key(item.table_ref))
        for ref in refs:
            self._merge_column(
                parsed,
                ref.table_ref,
                ref.column_meta,
                ref.column_name,
                is_condition=True,
                is_condition_foreign=self._column_key(ref.table_ref, ref.column_name) in foreign_refs
                if ref.table_ref
                else False,
            )
        for key, hit in list(self._table_hits(table_refs).items()):
            if key in foreign_tables:
                hit.is_foreign = True
                self._merge_table(parsed, key, hit)

    def _column_refs(
        self,
        tokens: list[SqlToken],
        table_refs: list[TableRef],
        aliases: dict[str, TableRef],
    ) -> list[ColumnRef]:
        refs: list[ColumnRef] = []
        i = 0
        while i < len(tokens):
            if not self._is_identifier_token(tokens[i]):
                i += 1
                continue
            parts, next_i = self._read_identifier(tokens, i)
            if not parts:
                i += 1
                continue
            if next_i < len(tokens) and tokens[next_i].value == "(":
                i = next_i + 1
                continue
            if len(parts) >= 3:
                table_ref = self._resolve_table(parts[-2], table_refs, aliases, schema=parts[-3])
                refs.extend(self._resolve_column(parts[-1], table_ref, table_refs))
            elif len(parts) == 2:
                table_ref = self._resolve_table(parts[0], table_refs, aliases)
                refs.extend(self._resolve_column(parts[1], table_ref, table_refs))
            elif parts[0].upper() not in EXPR_STOP_WORDS and parts[0] not in aliases:
                refs.extend(self._resolve_column(parts[0], None, table_refs))
            i = max(next_i, i + 1)
        return refs

    def _equality_pairs(
        self,
        tokens: list[SqlToken],
        table_refs: list[TableRef],
        aliases: dict[str, TableRef],
    ) -> list[tuple[ColumnRef, ColumnRef]]:
        pairs = []
        parts = self._split_top_level(tokens, "AND")
        for part in parts:
            eq_indexes = [i for i, token in enumerate(part) if token.value == "="]
            for eq_i in eq_indexes:
                left_refs = self._column_refs(part[:eq_i], table_refs, aliases)
                right_refs = self._column_refs(part[eq_i + 1 :], table_refs, aliases)
                if left_refs and right_refs:
                    pairs.append((left_refs[-1], right_refs[0]))
        return pairs

    def _is_foreign_pair(self, left: ColumnRef, right: ColumnRef) -> bool:
        if not left.column_meta or not right.column_meta:
            return False
        return (
            left.column_meta.fk_column_id == right.column_meta.id
            or right.column_meta.fk_column_id == left.column_meta.id
        )

    def _resolve_column(
        self,
        column_name: str,
        table_ref: TableRef | None,
        table_refs: list[TableRef],
    ) -> list[ColumnRef]:
        candidates = [table_ref] if table_ref else table_refs
        matched = []
        for ref in candidates:
            if ref is None or ref.meta is None:
                continue
            column = self._find_column(ref.meta, column_name)
            if column:
                matched.append(ColumnRef(ref.alias, column.name, ref, column))
        if matched:
            return matched if table_ref else matched[:1] if len(matched) == 1 else matched
        if table_ref:
            return [ColumnRef(table_ref.alias, column_name, table_ref, None)]
        return []

    def _resolve_table(
        self,
        qualifier: str,
        table_refs: list[TableRef],
        aliases: dict[str, TableRef],
        schema: str | None = None,
    ) -> TableRef | None:
        normalized = qualifier.lower()
        if normalized in aliases:
            ref = aliases[normalized]
            if schema is None or ref.schema_name.lower() == schema.lower():
                return ref
        for ref in table_refs:
            if ref.table_name.lower() == normalized and (schema is None or ref.schema_name.lower() == schema.lower()):
                return ref
        return None

    def _refs_for_star(
        self,
        qualifier: str | None,
        table_refs: list[TableRef],
        aliases: dict[str, TableRef],
    ) -> list[TableRef]:
        if qualifier is None:
            return [ref for ref in table_refs if ref.meta is not None]
        ref = self._resolve_table(qualifier, table_refs, aliases)
        return [ref] if ref and ref.meta else []

    def _star_qualifier(self, tokens: list[SqlToken]) -> str | None | bool:
        if len(tokens) == 1 and tokens[0].value == "*":
            return None
        if len(tokens) >= 3 and tokens[-1].value == "*" and tokens[-2].value == ".":
            return self._clean_identifier(tokens[-3].value)
        return False

    def _trim_alias(self, tokens: list[SqlToken]) -> list[SqlToken]:
        depth = 0
        for i, token in enumerate(tokens):
            depth = self._updated_depth(depth, token, before=True)
            if depth == 0 and token.upper == "AS":
                return tokens[:i]
            depth = self._updated_depth(depth, token, before=False)
        return tokens

    def _read_optional_alias(self, tokens: list[SqlToken], i: int) -> tuple[str | None, int]:
        if i < len(tokens) and tokens[i].upper == "AS":
            i += 1
        if i < len(tokens) and self._is_identifier_token(tokens[i]) and tokens[i].upper not in TABLE_STOP:
            return self._clean_identifier(tokens[i].value), i + 1
        return None, i

    def _read_identifier(self, tokens: list[SqlToken], i: int) -> tuple[list[str], int]:
        parts: list[str] = []
        expect_part = True
        while i < len(tokens):
            token = tokens[i]
            if token.value == ".":
                expect_part = True
                i += 1
                continue
            if not expect_part or not self._is_identifier_token(token):
                break
            if token.upper in TABLE_STOP or token.upper in EXPR_STOP_WORDS:
                break
            parts.append(self._clean_identifier(token.value))
            expect_part = False
            i += 1
            if i >= len(tokens) or tokens[i].value != ".":
                break
        return parts, i

    def _read_parenthesized(self, tokens: list[SqlToken], i: int) -> tuple[list[SqlToken], int]:
        depth = 0
        start = i + 1
        while i < len(tokens):
            if tokens[i].value == "(":
                depth += 1
            elif tokens[i].value == ")":
                depth -= 1
                if depth == 0:
                    return tokens[start:i], i + 1
            i += 1
        return tokens[start:], len(tokens)

    def _split_top_level(self, tokens: list[SqlToken], separator: str) -> list[list[SqlToken]]:
        parts: list[list[SqlToken]] = []
        depth = 0
        start = 0
        for i, token in enumerate(tokens):
            depth = self._updated_depth(depth, token, before=True)
            if depth == 0 and (token.value == separator or token.upper == separator):
                parts.append(tokens[start:i])
                start = i + 1
            depth = self._updated_depth(depth, token, before=False)
        parts.append(tokens[start:])
        return [part for part in parts if part]

    def _alias_map(self, table_refs: list[TableRef]) -> dict[str, TableRef]:
        aliases = {}
        for ref in table_refs:
            aliases[ref.table_name.lower()] = ref
            aliases[f"{ref.schema_name.lower()}.{ref.table_name.lower()}"] = ref
            if ref.alias:
                aliases[ref.alias.lower()] = ref
        return aliases

    def _table_hits(self, table_refs: list[TableRef]) -> dict[tuple[str, str, str | None], TableHit]:
        return {
            self._table_key(ref): TableHit(
                schema_name=ref.schema_name,
                table_name=ref.table_name,
                alias=ref.alias,
            )
            for ref in table_refs
        }

    def _merge_table(self, parsed: ParsedQuery, key: tuple[str, str, str | None], hit: TableHit):
        for existing in parsed.tables:
            if (existing.schema_name, existing.table_name, existing.alias) == key:
                existing.is_foreign = existing.is_foreign or hit.is_foreign
                return
        parsed.tables.append(hit)

    def _merge_column(
        self,
        parsed: ParsedQuery,
        table_ref: TableRef | None,
        column_meta: ColumnMeta | None,
        column_name: str | None = None,
        is_selected: bool = False,
        is_condition: bool = False,
        is_condition_foreign: bool = False,
    ):
        if table_ref is None:
            return
        name = column_meta.name if column_meta else column_name
        if not name:
            return
        key = (table_ref.schema_name, table_ref.table_name, name)
        for existing in parsed.columns:
            if (existing.schema_name, existing.table_name, existing.column_name) == key:
                existing.is_selected = existing.is_selected or is_selected
                existing.is_condition = existing.is_condition or is_condition
                existing.is_condition_foreign = existing.is_condition_foreign or is_condition_foreign
                return
        parsed.columns.append(
            ColumnHit(
                schema_name=table_ref.schema_name,
                table_name=table_ref.table_name,
                column_name=name,
                is_selected=is_selected,
                is_condition=is_condition,
                is_condition_foreign=is_condition_foreign,
            )
        )

    def _find_table(self, schema_name: str, table_name: str) -> TableMeta | None:
        table = self.tables_by_name.get((schema_name.lower(), table_name.lower()))
        if table:
            return table
        candidates = self.tables_by_unqualified.get(table_name.lower(), [])
        return candidates[0] if len(candidates) == 1 else None

    def _find_column(self, table: TableMeta, column_name: str) -> ColumnMeta | None:
        for column in table.columns:
            if column.name.lower() == column_name.lower():
                return column
        return None

    def _table_key(self, ref: TableRef) -> tuple[str, str, str | None]:
        return (ref.schema_name, ref.table_name, ref.alias)

    def _column_key(self, ref: TableRef, column_name: str) -> tuple[str, str, str]:
        return (ref.schema_name, ref.table_name, column_name)

    def _updated_depth(self, depth: int, token: SqlToken, before: bool) -> int:
        if before and token.value == ")":
            return max(0, depth - 1)
        if not before and token.value == "(":
            return depth + 1
        return depth

    def _is_identifier_token(self, token: SqlToken) -> bool:
        if token.value.startswith('"') and token.value.endswith('"'):
            return True
        return token.ttype in T.Name or token.ttype in T.String.Symbol or token.ttype in T.Keyword

    def _clean_identifier(self, value: str) -> str:
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1].replace('""', '"')
        return value


def parse_postgres_query(
    sql: str,
    metadata: Iterable[TableMeta],
    default_schema: str = "public",
) -> ParsedQuery:
    return QueryParser(metadata, default_schema=default_schema).parse(sql)
