# Traefik devolvendo 504: o backend demora demais

`traefik_timeout_backend` · **Componente:** Traefik / Upstream · **Severidade:** MEDIA

## Resumo rápido

Diferente do 502, aqui o serviço até aceitou a conexão, mas não respondeu a tempo. Na maioria das vezes, o app está lento por causa de algo atrás dele: banco travado, chamada externa pendurada ou falta de CPU.

## Como aparece nos logs

- Access log com status `504` e duração alta e redonda (`30001ms`, `60000ms`). Esse número redondo é o timeout estourando.
- `504 Gateway Timeout error` com `net/http: timeout awaiting response headers`
- Variação: `read tcp ...: i/o timeout`

## Diagnóstico

1. **É uma rota ou todas?** Filtre o access log pelo status 504 e veja os caminhos. Se for só `/v1/relatorios`, o problema é aquela operação. Se for tudo, o serviço inteiro está engasgado.

2. **Como o app está de recursos?**
   ```bash
   docker stats --no-stream api-1
   ```
   CPU colada em 100% ou memória no limite explicam lentidão generalizada.

3. **O banco está segurando?** Muita lentidão vem de query presa. No Postgres:
   ```sql
   SELECT pid, now() - query_start AS duracao, state, left(query, 80)
   FROM pg_stat_activity
   WHERE state <> 'idle'
   ORDER BY duracao DESC
   LIMIT 10;
   ```

4. **Qual timeout está estourando?** Confira se existe um `forwardingTimeouts.responseHeaderTimeout` no `serversTransport` do Traefik. O padrão é sem limite, então, se há 504 com esse erro, alguém configurou um valor.

## Correção

- Query lenta: crie o índice que falta ou otimize a consulta. Isso resolve a maioria dos casos.
- Falta de recurso: aumente CPU/memória do container ou escale réplicas.
- Operação legitimamente longa (relatório, exportação): transforme em tarefa assíncrona. O cliente recebe um "estou processando" e busca o resultado depois.
- Só aumente o timeout do Traefik se tiver certeza de que a demora é esperada. Aumentar timeout para esconder lentidão só empurra o problema.

## Prevenção

- Monitore a latência p95/p99 por rota, não só a média.
- Defina timeouts também dentro do app (chamadas HTTP externas, queries), para ele falhar rápido em vez de pendurar.
- Ative `log_min_duration_statement` no Postgres para pegar queries lentas antes que virem 504.
