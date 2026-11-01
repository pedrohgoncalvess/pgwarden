Analytics
=========

Recomendações de índices
------------------------

O advisor reavalia os filtros das consultas observadas contra o catálogo atual.
Compara as chaves de índices B-tree compostos, separa igualdade de intervalo e
não usa colunas de `INCLUDE` como chaves de busca. Cobertura suficiente suprime
a sugestão; cobertura parcial aponta os índices a revisar. Índices parciais,
expressões, opclasses, índices sem validade confirmada e SQL que a heurística
não compreende exigem investigação, sem DDL sugerido. A avaliação cobre filtros;
ordenação, joins e outras formas complexas precisam de validação do plano.

Consultas que diferem apenas em literais contam como um padrão. Candidatos
compartilháveis da mesma tabela são relacionados como alternativas; não há
criação, substituição ou remoção automática. Recomendações antigas de índices
que deixaram de ser observadas são marcadas como resolvidas no próximo refresh.

O coletor registra inserts, updates, deletes, HOT updates e o reset das
estatísticas. Taxas usam diferenças entre snapshots e exigem pelo menos uma hora
de observação válida. Intervalos com reset ou redução dos contadores são
descartados. Quantidade/tamanho dos índices e proporção de HOT updates aparecem
nas evidências. Essas métricas indicam pressão de escrita, não um custo exato
de manutenção do índice candidato.

Quando `pg_stat_statements` estiver disponível, o coletor de consultas nativas
também grava snapshots opcionais de chamadas, tempo de execução e blocos
lidos/acessados, identificados por query ID, usuário e nível de execução.
Essa coleta faz no máximo uma tentativa por minuto por banco, independentemente
da frequência da amostragem de consultas ativas.
A extensão não é habilitada automaticamente; sua ausência ou falta de permissão
mantém a coleta habitual funcionando. A consulta opcional usa os campos de
`pg_stat_statements` disponíveis no PostgreSQL 14 ou superior. O advisor utiliza
apenas execuções de nível superior e descarta intervalos com reset detectado,
redução de contadores ou mudança no contador de evicções (`dealloc`).

Prioridade e confiança são separadas: quantidade de padrões nunca torna um
candidato crítico. Um aviso exige pelo menos 100 chamadas, 60 segundos de tempo
acumulado, 5% do tempo observado, uma hora de observação, dados recentes e pressão
de escrita conhecida abaixo do limiar. Esses limiares são heurísticos, não uma
previsão de ganho. Sem evidência suficiente, a recomendação é informativa e pede
validação com planos representativos. O workload associado depende de a consulta
ter sido capturada pela amostragem de consultas nativas; essa amostragem não é
usada como frequência de execução. Sobreposição entre candidatos pode fazer o
mesmo workload aparecer em mais de uma recomendação; seus valores não devem ser
somados como economias independentes.

Configuração do processo Analytics:

- `INDEX_ADVISOR_WINDOW_DAYS`: janela de 1 a 30 dias (padrão: 7).
- `INDEX_ADVISOR_WRITE_HEAVY_PER_SECOND`: limiar de operações de escrita por
  segundo (padrão: 10).

Aplicar a migration `20261031_02_index-advisor` no armazenamento PostgreSQL e,
quando utilizado, no SQLite do coletor antes de atualizar os serviços. Métricas
históricas sem os novos contadores não produzem taxas de escrita. Índices antigos
dependem da próxima coleta de schema para confirmar sua validade.

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
