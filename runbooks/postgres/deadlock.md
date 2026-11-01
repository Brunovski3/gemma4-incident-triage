# Deadlock entre transações

`postgres_deadlock` · **Componente:** PostgreSQL / Transações · **Severidade:** MEDIA

## Resumo rápido

Duas transações ficaram esperando uma pela outra: a A segura o registro 1 e quer o 2, a B segura o 2 e quer o 1. O Postgres detecta isso sozinho em cerca de um segundo e cancela uma delas para destravar a outra. Ou seja, o banco não fica travado; o que acontece é que uma operação da aplicação falha. Se acontece de vez em quando, é tolerável com retry; se é frequente, há um problema de desenho no código.

## Como aparece nos logs

- `ERROR:  deadlock detected`
- `DETAIL:  Process 1234 waits for ShareLock on transaction 5678; blocked by process 9012.`
- Na aplicação: `psycopg2.errors.DeadlockDetected` (código SQLSTATE `40P01`).

## Diagnóstico

1. **Leia o log completo do Postgres.** Logo depois do `DETAIL`, ele mostra as queries de cada processo envolvido. Com isso você descobre exatamente quais operações estão se cruzando.

2. **Com que frequência acontece?**
   ```sql
   SELECT datname, deadlocks FROM pg_stat_database WHERE datname = current_database();
   ```
   Acompanhe esse contador ao longo do tempo.

3. **Procure o padrão clássico no código:** duas rotinas que atualizam as mesmas tabelas ou registros em **ordem diferente**. Por exemplo, uma atualiza `pedidos` e depois `estoque`, enquanto a outra faz `estoque` e depois `pedidos`.

## Correção

- Padronize a ordem: todas as rotinas devem travar tabelas e registros sempre na mesma sequência. Em lotes, ordene os IDs antes de atualizar (`... WHERE id = ANY(...) ORDER BY id FOR UPDATE`).
- Encurte as transações: quanto menos tempo o lock fica preso, menor a chance de cruzamento.
- Crie índices nas chaves estrangeiras. Sem índice, operações em cascata travam mais linhas do que precisam.
- Na aplicação, trate o erro `40P01` com **retry** e um pequeno intervalo aleatório. Para deadlocks ocasionais, isso é a solução correta, e não um remendo.

## Prevenção

- Ative `log_lock_waits = on`, que registra esperas longas por lock antes de virarem deadlock.
- Alerte sobre o crescimento do contador de deadlocks, não sobre cada ocorrência.
