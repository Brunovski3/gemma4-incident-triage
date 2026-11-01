# Pool de conexões da aplicação esgotado

`postgres_pool_esgotado` · **Componente:** PostgreSQL / Pool de conexões · **Severidade:** ALTA

## Resumo rápido

Não confunda com o banco cheio. Aqui o Postgres pode estar tranquilo: quem esgotou foi o **pool da aplicação**. Todas as conexões do pool estão emprestadas, e as requisições novas ficam na fila esperando uma conexão livre até estourar o timeout. Na prática, ou o pool é pequeno para a carga, ou as conexões estão demorando para voltar (queries lentas ou código que não devolve a conexão).

## Como aparece nos logs

- SQLAlchemy: `QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`
- HikariCP (Java): `HikariPool-1 - Connection is not available, request timed out after 30000ms (total=20, active=20, idle=0, waiting=37)`
- PgBouncer: `pooler error: no more connections allowed (max_client_conn)`
- Em seguida, é comum aparecer 504 no Traefik, porque as requisições ficam esperando.

## Diagnóstico

1. **Leia os números da mensagem.** No Hikari, `active=20, idle=0, waiting=37` diz tudo: o pool inteiro está ocupado e há 37 requisições na fila.

2. **O que essas conexões estão fazendo no banco?**
   ```sql
   SELECT state, now() - query_start AS duracao, left(query, 80)
   FROM pg_stat_activity
   WHERE application_name = 'nome-da-app'
   ORDER BY duracao DESC;
   ```
   - Queries `active` demoradas: o pool está ocupado com consultas lentas.
   - Muitas em `idle in transaction`: o código abre transação e não fecha.
   - Poucas conexões no banco e pool cheio na app: é **vazamento**, ou seja, o código pega a conexão e não devolve.

3. **Para caçar vazamento:**
   - Hikari: ative `leakDetectionThreshold` (por exemplo, 30000 ms). Ele loga o stack trace de quem segurou a conexão.
   - SQLAlchemy: procure sessões abertas fora de `with`/`try...finally`.

## Correção

- Query lenta: otimize (índice, paginação). Liberar a conexão mais rápido é o que mais ajuda.
- Vazamento: corrija o código para sempre devolver a conexão (context manager, `try-with-resources`).
- Pool pequeno para uma carga legítima: aumente, mas confira antes se o banco aguenta (veja o runbook de conexões esgotadas).
- PgBouncer: ajuste `max_client_conn` e `default_pool_size`.

## Prevenção

- Exponha as métricas do pool (ativas, ociosas, esperando). O Hikari e o SQLAlchemy têm isso pronto.
- Defina timeout nas queries (`statement_timeout`), para uma consulta presa não segurar a conexão para sempre.
- Mantenha transações curtas: nada de chamada HTTP externa no meio de uma transação aberta.
