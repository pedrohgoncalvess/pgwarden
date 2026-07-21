# PGWarden Notifier — Mapeamento de Observabilidade e Thresholds

Este documento mapeia **todos os processos do PGWarden que produzem dados
observáveis** e define os tipos de regra e thresholds de alerta para cada um.
Tudo é configurável pelo usuário — via YAML (seção `notifier:`) ou via
API/frontend (tabelas `notifier.*`).

## Canais de notificação

Todos os canais são simples (credencial única, sem OAuth). As credenciais são
armazenadas **criptografadas** (Fernet, coluna `credentials` de
`notifier.channel`) e podem ser definidas no YAML com interpolação `${ENV_VAR}`
ou via API/frontend:

| Canal | Integração | Campos de `credentials` |
|---|---|---|
| Slack | Incoming Webhook (`POST {"text": ...}`) | `webhook_url` |
| Discord | Webhook de canal (`POST` com embeds) | `webhook_url` |
| Teams | Incoming Webhook / Workflows (`POST` MessageCard) | `webhook_url` |
| Email | SMTP | `host`, `port`, `username`, `password`, `from`, `to` |

## Modelo de regras

- `notifier.rule` — definição central: `interval_seconds`, `cooldown_seconds`,
  `window_minutes`, `enabled` — **cada regra tem seu próprio agendamento**.
- Tabelas de escopo (`rule_server`, `rule_database`, `rule_table`,
  `rule_index`) apontam para a regra central e para a entidade em `metadata.*` /
  `collector.server`, com `type`, `warning`, `critical`, `direction`.
  `entity_id` NULL = todas as entidades do escopo — é o que permite regras
  diferentes para servidores/bancos/tabelas distintos.
- `notifier.notification` — alertas disparados (`message`, `hidden`,
  `created_at`, `params`), exibidos no frontend. `params` (JSONB) leva `path`
  relativo para a página relevante (ex.: `/analytics/{database_id}/index` para
  hit rate de índice), ids das entidades, severidade, valor e o filtro de
  tempo `from`/`to` da janela avaliada.

## Tipos por escopo e thresholds default

### Server (`notifier.rule_server` → `collector.server`)

| `type` | Fonte | Métrica | Direção | Warning | Critical |
|---|---|---|---|---|---|
| `cpu_percent` | `metric.cpu` | `cpu_percent` (última amostra) | acima | 85 | 95 |
| `ram_percent` | `metric.ram` | `percent` (última amostra) | acima | 90 | 95 |
| `disk_percent` | `metric.disk` | `percent` por mount point | acima | 90 | 97 |

### Database (`notifier.rule_database` → `metadata.database`)

| `type` | Fonte | Métrica | Direção | Warning | Critical |
|---|---|---|---|---|---|
| `growth_percent` | `metric.database_stat` | crescimento % de `db_size_bytes` na janela | acima | 10 | 25 |
| `cache_hit_ratio` | `metric.database_stat` | `blks_hit / (blks_hit + blks_read)` na janela | **abaixo** | 0.95 | 0.90 |
| `deadlocks` | `metric.database_stat` | delta de `deadlocks` na janela | acima | 1 | 5 |
| `tup_updated` | `metric.database_stat` | delta de `tup_updated` na janela | acima | 100k | 1M |
| `tup_deleted` | `metric.database_stat` | delta de `tup_deleted` na janela | acima | 100k | 1M |
| `long_query_ms` | `metric.native_query` | `query_duration_ms` de queries ativas | acima | 30s | 2min |
| `waiting_sessions` | `metric.session` | sessões com `wait_event_type` não nulo | acima | 5 | 20 |
| `blocked_locks` | `metric.lock` | locks com `is_granted = false` | acima | 1 | 5 |
| `table_created` | `metadata.table` | `created_at` na janela | acima | 1 | 10 |
| `table_dropped` | `metadata.table` | `deleted_at` na janela | acima | 1 | 5 |
| `index_created` | `metadata.index` | `created_at` na janela | acima | 1 | 10 |
| `index_dropped` | `metadata.index` | `deleted_at` na janela | acima | 1 | 5 |

### Table (`notifier.rule_table` → `metadata.table`)

| `type` | Fonte | Métrica | Direção | Warning | Critical |
|---|---|---|---|---|---|
| `growth_percent` | `metric.table` | crescimento % de `table_size_bytes` na janela | acima | 20 | 50 |
| `dead_tuples` | `metric.table` | `n_dead_tup` (última amostra) | acima | 10k | 100k |
| `dead_tuple_ratio` | `metric.table` | `n_dead_tup / (n_live_tup + n_dead_tup)` | acima | 0.2 | 0.5 |
| `column_added` | `metadata.column` | `created_at` na janela | acima | 1 | 5 |
| `update_delete_queries` | — | **TODO** — depende do analytics (parse de queries UPDATE/DELETE por tabela) | — | — | — |
| `bloating` | — | **TODO** — estimativa de bloat por tabela | — | — | — |

### Index (`notifier.rule_index` → `metadata.index`)

| `type` | Fonte | Métrica | Direção | Warning | Critical |
|---|---|---|---|---|---|
| `hit_rate` | `metric.index` | `blks_hit / (blks_hit + blks_read)` na janela | **abaixo** | 0.90 | 0.80 |

## Mapeados, mas ainda não implementados (futuro)

| Processo | Fonte | Observação |
|---|---|---|
| Queries UPDATE/DELETE por tabela | `analytics.query_table_hit` | Tipo `update_delete_queries` já reservado no schema; depende do analytics. |
| Bloat por tabela | estimativa via `pg_stat_user_tables` + `pgstattuple` | Tipo `bloating` já reservado no schema. |
| Findings do analytics | `analytics.query_analysis_finding` | Tabelas ainda **sem migration** (existem só como modelos SQLAlchemy). Quando existirem, o notifier pode apenas retransmitir findings `critical`. |
| Taxa de I/O | `metric.io` | Contadores cumulativos; exige derivar rate entre amostras e baseline histórico. |
| Saúde do collector | `collector.run` / `metadata.database.last_seen_at` | Alertar quando coletas falham ou um banco fica stale. |
| Rollback ratio | `metric.database_stat` | `xact_rollback / (xact_commit + xact_rollback)` acima de threshold. |

## Configuração

Exemplo completo em [config.yaml.example](config.yaml.example) e na seção
`notifier:` do `config.yaml` da raiz. Regras e canais são sincronizados para o
banco no startup e relidos a cada ciclo — mudanças via API/frontend valem sem
restart. Se `notifier.rule` estiver vazia, uma regra `default` com todos os
tipos acima (entidade NULL = todos) é semeada automaticamente.
