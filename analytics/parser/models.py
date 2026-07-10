from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnMeta:
    id: int
    name: str
    fk_table_id: int | None = None
    fk_column_id: int | None = None


@dataclass(frozen=True)
class TableMeta:
    id: int
    schema_name: str
    name: str
    columns: tuple[ColumnMeta, ...] = ()


@dataclass
class TableHit:
    schema_name: str
    table_name: str
    alias: str | None = None
    is_foreign: bool = False


@dataclass
class ColumnHit:
    schema_name: str
    table_name: str
    column_name: str
    is_selected: bool = False
    is_condition: bool = False
    is_condition_foreign: bool = False


@dataclass
class ParsedQuery:
    tables: list[TableHit] = field(default_factory=list)
    columns: list[ColumnHit] = field(default_factory=list)
