# PostgreSQL atingiu o limite de conexões

`postgres_conexoes_esgotadas` · **Componente:** PostgreSQL / Conexões · **Severidade:** ALTA

## Resumo rápido

O banco chegou ao `max_connections` e está recusando conexões novas. Quase nunca a solução é só aumentar esse número: cada conexão do Postgres é um processo com memória própria. O que costuma acontecer é que as aplicações abrem mais conexões do que precisam, ou deixam conexões abertas e paradas.

## Como aparece nos logs

- `FATAL:  sorry, too many clients already`
- `FATAL:  remaining connection slots are reserved for non-replication superuser connections`, que significa que só restaram as vagas reservadas para administradores.
- Nas aplicações, erros de conexão logo em seguida (é comum ver junto 500 no Traefik).

## Diagnóstico

1. **Quantas conexões, e em que estado?** Conecte como superusuário, que tem vagas reservadas:
   ```sql
   SHOW max_connections;
   SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY 2 DESC;
   ```
   Muitas conexões em `idle` são normais com pool. Muitas em `idle in transaction` são um problema: alguém abriu uma transação e não fechou.

2. **Quem está ocupando?**
   ```sql
   SELECT usename, application_name, client_addr, count(*)
   FROM pg_stat_activity
   GROUP BY 1, 2, 3
   ORDER BY 4 DESC;
   ```
   Normalmente um único serviço concentra a maioria.

3. **Faça a conta do pool:** some o tamanho do pool de cada aplicação vezes o número de réplicas. Cinco réplicas com pool de 20 já são 100 conexões, que é o padrão do `max_connections`.

## Correção

- Para aliviar na hora, encerre as conexões presas em transação há muito tempo:
  ```sql
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE state = 'idle in transaction'
    AND now() - state_change > interval '10 minutes';
  ```
  Isso derruba a transação daquela conexão; a aplicação vai receber erro e precisa saber reconectar.
- Reduza o pool das aplicações que exageram.
- Para muitas réplicas ou serverless, coloque um **PgBouncer** na frente em modo `transaction`. Ele permite milhares de clientes com poucas dezenas de conexões reais.
- Aumentar o `max_connections` exige reiniciar o banco e consome memória. Use como último recurso, não como primeira resposta.

## Prevenção

- Configure `idle_in_transaction_session_timeout` (por exemplo, `'5min'`) para o próprio Postgres derrubar transações esquecidas.
- Documente o orçamento de conexões: quanto cada serviço pode usar.
- Alerte com 80% do `max_connections`.
