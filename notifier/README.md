# PGWarden Notifier

Módulo de alertas do PGWarden. Avalia regras de monitoramento sobre as métricas
coletadas e dispara alertas para **Slack, Discord, Microsoft Teams e Email
(SMTP)**.

Veja [THRESHOLDS.md](THRESHOLDS.md) para o mapeamento completo dos processos
observáveis, tipos de regra e thresholds default.

## Modelo de regras

- `notifier.rule` — tabela central com `interval_seconds`, `cooldown_seconds`,
  `window_minutes` e `enabled` **por regra** (nada é global).
- Tabelas de escopo apontam para a regra central e para a entidade monitorada,
  com `type`, `warning`, `critical` e `direction`:
  - `notifier.rule_server` → `collector.server` (`cpu_percent`, `ram_percent`, `disk_percent`)
  - `notifier.rule_database` → `metadata.database` (`growth_percent`, `cache_hit_ratio`, `deadlocks`, `tup_updated`, `tup_deleted`, `long_query_ms`, `waiting_sessions`, `blocked_locks`, `table_created`, `table_dropped`, `index_created`, `index_dropped`)
  - `notifier.rule_table` → `metadata.table` (`growth_percent`, `dead_tuples`, `dead_tuple_ratio`, `column_added`, `update_delete_queries`*, `bloating`*)
  - `notifier.rule_index` → `metadata.index` (`hit_rate`)

  *\* tipos reservados — implementação pendente (TODO, dependem do analytics).*

  `entity_id` NULL = aplica a todas as entidades do escopo. Isso permite regras
  diferentes para servidores/bancos/tabelas distintos (isolamento por regra).

## Seleção de entidades no YAML

Cada target aceita **lista explícita de nomes** ou **filtros** (a lista tem
precedência e ignora os filtros); omitindo ambos, vale para todas as entidades
do escopo:

```yaml
database:
  - type: cache_hit_ratio
    databases:                           # lista de nomes (ou database: nome)
      - postgres
      - app_db
table:
  - type: growth_percent
    tables:                              # mapping ou string db.schema.tabela
      - database: app_db
        schema: public
        table: users
      - app_db.audit.events
  - type: dead_tuple_ratio
    database: app_db                     # filtros (todos opcionais):
    schemas:                             # restringe schemas (omitir = todos)
      - public
      - audit
    table_regex: "^fact_"                # regex no nome da tabela
index:
  - type: hit_rate
    database: app_db
    tables:                              # todos os índices dessas tabelas
      - users
      - orders
    index_regex: "_pkey$"                # e/ou regex no nome do índice
```

Filtros e nomes são resolvidos para ids no sync de startup (re-resolvidos a
cada restart).

## Fluxo

1. No startup, a seção `notifier:` do YAML é sincronizada com o banco: canais
   (credenciais criptografadas com Fernet) e regras (nomes de entidades são
   resolvidos para ids). Se `notifier.rule` estiver vazia, uma regra `default`
   com todos os tipos e thresholds padrão é semeada.
2. O loop acorda no `interval` de cada regra (scheduling independente por
   regra), relê regras e canais do banco — alterações via API/frontend valem
   sem restart — e avalia cada target na sua `window_minutes`.
3. Alertas respeitam o `cooldown` da regra por target+entidade+severidade
   (escalonamento warning → critical dispara imediatamente).
4. Todo alerta disparado também é gravado em `notifier.notification`
   (`message`, `hidden`, `created_at`, `params`) para o notification center do
   frontend. O campo `params` (JSONB) carrega os dados de navegação:

```json
{
  "path": "/analytics/12/index",
  "scope": "index",
  "type": "hit_rate",
  "rule": "default",
  "entity": "users_email_idx",
  "entity_id": 99,
  "database_id": 12,
  "severity": "critical",
  "value": 0.75,
  "threshold": 0.8,
  "from": "2026-07-20T01:00:00+00:00",
  "to": "2026-07-20T02:00:00+00:00"
}
```

Paths por escopo: server → `/servers`, database →
`/overview/{database_id}`, table → `/analytics/{database_id}/data`, index →
`/analytics/{database_id}/index`. `from`/`to` = janela (`window_minutes`) da
avaliação que disparou o alerta.

## Credenciais

Nos YAMLs (`config.yaml`, `notifier.yaml` ou `notifier/config.yaml`), strings
suportam interpolação `${VAR}` e `${VAR:-default}` de variáveis de ambiente.

| Canal | Campos de `credentials` |
|---|---|
| slack | `webhook_url` |
| discord | `webhook_url` |
| teams | `webhook_url` |
| email | `host`, `port`, `username`, `password`, `from`, `to` (lista ou string separada por vírgula) |

Exemplo completo de regras em [config.yaml.example](config.yaml.example).

## Executar

```bash
uv run python -m notifier.main   # a partir da raiz do projeto (workspace uv)
```

Requer `ENCRYPTION_KEY` e as variáveis `DB_*` no `.env` da raiz.

## Testes

```bash
cd notifier && uv run pytest tests/
```
