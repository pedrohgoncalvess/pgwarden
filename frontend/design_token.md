# Sistema de Design e Tokens: pgwarden

## 1. Diretrizes de UI/UX (Obrigatório para o Agente)
Você é o agente responsável por gerar o frontend do **pgwarden**, um monitorador de bancos de dados PostgreSQL construído em Svelte e Tailwind CSS. 
Sempre que gerar ou modificar componentes, siga estas regras estritas de design:

- **Estética:** Utilitária, densa em informação, técnica e moderna. Evite o visual "AI slop" (sem bordas excessivamente arredondadas, sem sombras difusas, sem uso desnecessário de espaços vazios).
- **Dark Mode First:** A interface é focada em ambientes de monitoramento. Utilize alto contraste.
- **Tipografia:** Use `font-sans` para a interface (botões, labels) e `font-mono` OBRIGATORIAMENTE para dados tabulares, logs, queries SQL e métricas numéricas.
- **Componentes:**
  - Telas de login devem ser minimalistas e centralizadas.
  - Painéis de gráficos devem ter bordas finas e fundos sólidos.
  - Streams de dados devem maximizar a área de leitura, preferindo separações por opacidade/zebrado sutil ao invés de bordas internas pesadas.

## 2. Configuração do Tailwind (tailwind.config.js)
Injete estas extensões no arquivo de configuração do Tailwind. Use sempre essas classes utilitárias para garantir a consistência visual.

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        // Brand: Verde Azulado (Postgres Blue + Guardian Green)
        brand: {
          50: '#f0fdfa',
          500: '#14b8a6',
          600: '#0d9488', // Primária interativa (Botões principais)
          700: '#0f766e', // Hover
          900: '#134e4a', // Fundo de destaques
        },
        // Surfaces: Neutros baseados em Slate para profundidade técnica
        surface: {
          bg: '#0f172a',      // Fundo da aplicação
          panel: '#1e293b',   // Fundo de cards/modais
          border: '#334155',  // Divisórias e bordas de tabelas
        },
        // Status Semânticos
        status: {
          healthy: '#10b981', // Verde: Tudo OK
          warning: '#f59e0b', // Âmbar: Alertas/Locks
          danger: '#ef4444',  // Vermelho: Erros críticos/Quedas
          info: '#3b82f6',    // Azul: Informações neutras
        },
        // Cores Categóricas para Gráficos
        chart: {
          1: '#0d9488', // Teal
          2: '#8b5cf6', // Violet
          3: '#ec4899', // Pink
          4: '#eab308', // Yellow
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'panel': '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)',
        'floating': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)',
      },
      borderRadius: {
        'sm': '2px', // Minimalista
        'md': '4px', // Padrão para botões e inputs
        'lg': '8px', // Padrão para cards e modais
      }
    },
  },
  plugins: [],
}

```

## 3. Exemplos de Mapeamento de Classes (Tailwind)

Quando criar componentes em Svelte, utilize a seguinte lógica estrutural:

* **Fundo da Tela:** `bg-surface-bg text-slate-100`
* **Painel/Card:** `bg-surface-panel border border-surface-border rounded-lg shadow-panel`
* **Botão Primário:** `bg-brand-600 hover:bg-brand-700 text-white rounded-md px-4 py-2 font-medium transition-colors`
* **Input de Texto:** `bg-surface-bg border border-surface-border rounded-md px-3 py-2 focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none`
* **Linha de Log (Erro):** `font-mono text-sm text-status-danger`
* **Métrica KPI:** `font-mono text-2xl font-bold`