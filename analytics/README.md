Analytics
=========

Modulo responsavel por derivar informacoes estruturadas das queries coletadas em
`metric.native_query`.

O entrypoint principal e `analytics/main.py`. Ele consome `metric.native_query`,
cria registros unicos em `analytics.query` (distincao por texto da query) e grava
os hits estruturados em `analytics.query_table_hit` e
`analytics.query_column_hit`.

As tabelas de analytics mantem apenas a referencia de `query_id` para
`analytics.query` (que por sua vez guarda `database_id`) e registram:

- `query`: query unica, com `database_id`, texto, hash e metadados da coleta
  (`user_name`, `application_name`).
- `query_table_hit`: nome do schema/tabela, alias e se a tabela e usada em
  condicao de join/foreign (`is_foreign`).
- `query_column_hit`: nome do schema/tabela/coluna e flags indicando se a
  coluna aparece em select (`is_selected`), em condicoes comuns (`is_condition`)
  ou em condicoes de join/foreign (`is_condition_foreign`).
