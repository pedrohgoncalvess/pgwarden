# Fontes de consultas e análise

O pgwarden mantém duas coletas independentes. `native_query_collector` coleta
`pg_stat_activity`, com sessões, esperas e amostras de execução.
`query_workload_collector` coleta `pg_stat_statements`, com SQL representativo e
estatísticas acumuladas. Pausar uma coleta não pausa a outra.

```yaml
collector:
  query_workload_collector:
    interval: 60  # segundos: 60 = minuto; 3600 = hora; 86400 = dia
    enabled: false  # habilite explicitamente após configurar a extensão
  native_query_collector:
    interval: 0.5
    enabled: true
```

Statements vem desativado por padrão, com intervalo de 60 segundos. Em Jobs → Database, o mesmo coletor pode
ser ativado/pausado e configurado em segundos, minutos, horas ou dias, usando os
controles existentes. A configuração YAML global é aplicada no bootstrap;
alterações feitas pela interface usam o agendamento existente no banco.

Após três falhas consecutivas por extensão/view ausente ou extensão sem preload,
o coletor é pausado automaticamente. O contador e o aviso ficam persistidos na
configuração, e o aviso aparece em Jobs → Database e no log. Uma coleta bem-sucedida
zera o contador. Falhas de conexão ou permissão não acionam essa desativação.
O bootstrap preserva a pausa automática mesmo se o YAML ainda tiver `enabled: true`.
Depois de corrigir a instalação, reative explicitamente em Jobs → Database para
limpar o aviso e iniciar uma nova sequência de tentativas.

A extensão deve estar instalada/configurada no PostgreSQL monitorado, com acesso
às estatísticas e textos para o usuário de coleta. Ausência da extensão ou falta
de permissão não interrompem os demais coletores. Os campos fixos exigem
PostgreSQL 14+; `statement_data` armazena em JSON textual todos os campos
retornados pela versão instalada, inclusive planejamento, execução, linhas,
blocos, temporários, WAL, JIT e novos campos quando presentes. Não há criação
automática da extensão nem reset de estatísticas.

## Catálogo, parsers e identidade

Os textos das duas fontes alimentam os mesmos parsers de tabelas e colunas e o
catálogo `analytics.query`. A identidade compartilhada é banco monitorado +
`query_id` não nulo/não zero. Literais de activity e parâmetros `$1` de statements
podem pertencer à mesma identidade. Sem identificador, o catálogo usa texto exato;
textos apenas parecidos não vinculam fontes com identificadores diferentes.

`pg_query_id`, `seen_activity` e `seen_statements` registram o vínculo e a origem.
Os textos e hashes observados permanecem nas métricas originais. Histórico e
contexto aceitam tanto hashes existentes quanto `pg:<query_id>`; a API usa string
para IDs PostgreSQL na listagem de consultas, evitando perda de precisão no JS.
Identificadores do PostgreSQL não são garantidos entre upgrades de versão major;
o vínculo é local ao banco monitorado, não uma identidade global entre servidores.

## Mescla das métricas

Listagem de consultas e usos por tabela/coluna incluem statements mesmo quando
activity está vazia. As respostas informam `sources`, `metrics_source`,
`activity_executions` e `statements_calls`. Contadores statements são separados
por banco, query ID, usuário e nível de execução antes de calcular diferenças.
As listagens agregadas contam apenas nível superior, evitando contar novamente
SQL interno de uma rotina.

Quando há deltas válidos na janela, chamadas e tempo acumulado vêm de statements.
Observações de activity continuam disponíveis separadamente; não são somadas às
chamadas. Aplicação/estado são atributos de sessão: filtrar por eles usa somente
activity. O primeiro snapshot estabelece a base; deltas que atravessam o começo
da janela, resets globais/por entrada, evicções ou reduções de contadores são
descartados. Assim, chamadas representam os intervalos válidos observados, não
uma garantia de cobertura completa da janela. SQL sem intervalo válido aparece
no catálogo, com métricas indisponíveis ou com evidência de activity.

Máximo/mínimo de uma execução não podem ser derivados de diferenças de
contadores acumulados: esses campos ficam indisponíveis na agregação statements.
Os valores brutos da extensão continuam disponíveis no histórico em
`statement_data`. O histórico identifica cada origem e preserva o usuário e nível
de execução dos snapshots.

Overview, streaming de sessões e timeline de atividade continuam baseados em
activity. Um snapshot statements não cria sessão, PID, espera, ponto de atividade
ou evento de execução individual. Sem activity, a análise usa SQL, schema,
índices e manutenção de tabelas; não atribui CPU, locks ou regressão de uma
execução ao instante de coleta do snapshot.

Na análise detalhada, os snapshots de statements ficam em uma lista própria,
separada da timeline de activity. A seleção de um snapshot preserva usuário e
nível de execução e permite inspecionar os campos coletados e o contexto de
tabelas/índices. Contagens de sessões ficam indisponíveis nessa origem.

## Atualização

Aplicar `20261101_01_query-sources` no armazenamento PostgreSQL e, quando usado,
no SQLite do coletor antes de atualizar os serviços.
Aplicar também `20261102_01_workload-auto-disable`, que pausa a coleta de statements
existente e define o novo padrão. Reative explicitamente se desejar utilizá-la.
Reiniciar coletor e sender; o sender atualiza seu trigger de captura para incluir
as novas colunas.
Snapshots antigos sem texto permanecem válidos como métricas, mas não fornecem
SQL para os parsers. O próximo snapshot preenche essa lacuna.

O rollback PostgreSQL restaura a unicidade antiga por texto. Se o mesmo SQL
passou a ter identidades PostgreSQL distintas, essa restrição pode impedir o
rollback; resolva essas identidades conscientemente antes de voltar a versão,
sem apagar histórico automaticamente.
