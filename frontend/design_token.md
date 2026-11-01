# PGWarden — UI e UX

A fonte executável dos tokens é `src/routes/layout.css`, usando `@theme` do Tailwind 4. Não criar uma segunda configuração de cores em `tailwind.config.js`.

## Linguagem visual

- Dark mode técnico, com superfícies neutras e teal para ações e seleção.
- Fundo `background`, painéis `surface-container-low`/`surface-container`, elementos elevados `surface-container-high`.
- Texto principal `on-surface`, auxiliar `on-surface-variant`, divisórias `outline-variant`.
- Estados `status-healthy`, `status-warning`, `status-danger`, `status-info`; sempre acompanhar cor com texto ou ícone.
- Inter para interface, JetBrains Mono para SQL, logs e números. Usar números tabulares em tabelas.
- Espaçamento em múltiplos de 4 px; painéis com raio de 8 px, campos e botões com 5 px.
- Fundos sólidos. Evitar blur, gradientes decorativos e sombras em cards. Sombras são reservadas a painéis flutuantes.

## Estrutura

- O layout autenticado controla sidebar, contexto e tabs. `src/lib/navigation.ts` define os destinos e preserva a seção ao trocar de banco.
- Sete destinos: Overview, Activity, Analytics, Schema, Alerts, Jobs e Settings. Documentação/tags ficam em Schema; execuções, histórico, jobs de servidor/banco e serviços ficam em Jobs. Settings concentra conexões, servidores, projetos, acesso e conta.
- URLs seguem o menu: `/jobs`, `/jobs/server`, `/jobs/database`, `/jobs/services`, `/settings/servers`, `/schema/[database_id]/documentation` e `/schema/tags/[server_id]`. Os paths antigos redirecionam no servidor, preservando a query string; `src/lib/routePaths.ts` centraliza esse mapeamento.
- Contexto servidor/banco no topo. A sidebar recolhe no desktop e vira drawer no mobile.
- Headers de páginas usam `app-page-header`; nunca calcular largura com `16rem` fixos. A geometria vem de `--sidebar-width`, `--toolbar-height` e `--page-tabs-height`.
- As ações específicas de cada tela continuam no header da página. A navegação interna usa tabs horizontais.
- Todos os dropdowns usam `src/lib/components/Select.svelte`, com `options`, `bind:value` e `onchange(value)`. O callback recebe o valor, não um evento HTML. Usar `aria-label` descritivo; o menu usa Popover API para escapar de clipping e respeita o teclado e o foco. Não introduzir selects nativos nas telas.
- Usar `glass-panel`/`settings-card`, `input-technical`, `btn-primary`, `btn-secondary` e `modal-overlay` compartilhados; não redefinir esses seletores em cada tela.

## Interação e acessibilidade

- Todos os controles booleanos usam o toggle compartilhado de `src/lib/styles/toggle.css`: manter `input type="checkbox" role="switch"`, com label ou `aria-label`. O estilo é global, inclusive para novos campos. Não adicionar dimensões ou cores locais aos toggles. Preservar `bind:checked`, `bind:group`, callbacks e `disabled` nativos.
- Exibir foco visível e permitir navegação por teclado. `Ctrl/Cmd+K` abre busca; Escape fecha drawer/notificações.
- Preservar conteúdo durante atualizações; distinguir ausência de dados, carregamento inicial, erro e reconexão.
- Não inferir saúde da existência de um banco selecionado. Informar estado do stream e última atualização.
- Animações curtas: 120 ms para cor/foco e 180 ms para painéis. Preferir transform/opacity. Respeitar `prefers-reduced-motion`.
- Atualizações de métricas não devem disparar animações de entrada nem reorganizar toda a tela.

## Dados e performance

- Analytics, Time travel e histórico de Jobs abrem nas últimas 24 horas. Intervalos explícitos em links e períodos maiores escolhidos pelo usuário são preservados. `src/lib/timeRange.ts` centraliza o padrão.

- Catálogo de servidores/bancos: deduplicação de chamadas concorrentes e cache de 15 s, isolado por sessão e invalidado após mutações bem-sucedidas.
- Não armazenar métricas ou respostas de autenticação nesse cache. Não usar cache compartilhado entre usuários no SSR.
- Streams da Overview, Activity e Live Runs fecham quando a aba fica oculta e reconectam ao retornar.
- Consultas da Overview e Schema podem ser canceladas; respostas antigas não devem sobrescrever a seleção atual.
- Notificações fechadas solicitam um item para obter os contadores; a listagem completa carrega ao abrir. Polling pausa em aba oculta.
- Activity renderiza 100 linhas inicialmente e permite ampliar. Paginação no servidor e virtualização de diagramas devem ser guiadas por profiling com volumes reais.

## Validação

Executar `npm run check`, `npm test` e `npm run build`. Conferir visualmente desktop expandido/recolhido e mobile, troca de contexto, foco, filtros, notificações, estados de erro e reconexão.

Para comparar performance, usar o mesmo ambiente, volume de dados e sequência de navegação. Registrar requests, bytes transferidos, INP, CLS e memória após uma sessão prolongada. Metas propostas: INP ≤ 200 ms e CLS ≤ 0,1; resultados de produção precisam ser medidos, não inferidos do build.
