# Aplicação não consegue conectar ao PostgreSQL

`postgres_conexao_recusada` · **Componente:** PostgreSQL / Disponibilidade · **Severidade:** CRITICA

## Resumo rápido

A aplicação tentou abrir uma conexão e ninguém atendeu na porta 5432. Isso quase sempre significa que o Postgres não está rodando, ou não está ouvindo onde a aplicação procura. É crítico porque tudo que depende do banco para junto. E atenção: muitas vezes esse erro é só a consequência; a causa raiz está no motivo de o Postgres ter caído (disco cheio, falta de memória).

## Como aparece nos logs

- Python: `psycopg2.OperationalError: connection to server at "db" (172.18.0.3), port 5432 failed: Connection refused`
- Node: `Error: connect ECONNREFUSED 172.18.0.3:5432`
- Java: `PSQLException: Connection to db:5432 refused`
- Em cascata: 502 no Traefik e containers ficando unhealthy.

## Diagnóstico

1. **O Postgres está de pé?**
   ```bash
   docker compose ps db
   docker logs --tail 100 db-1
   ```
   Se ele caiu, os logs dele explicam o motivo. Procure `PANIC`, `No space left on device` ou `out of memory`.

2. **Ele aceita conexões?**
   ```bash
   docker compose exec db pg_isready
   ```

3. **A aplicação procura no lugar certo?** Confira host e porta na configuração da aplicação. Em compose, o host deve ser o nome do serviço (`db`), não `localhost`: dentro de um container, `localhost` é o próprio container da aplicação.

4. **O Postgres ouve na rede?** Se ele foi instalado fora de container, confira o `listen_addresses` no `postgresql.conf`. O padrão `localhost` recusa conexões vindas de outras máquinas e containers.

## Correção

- Postgres caído: resolva a causa nos logs dele (veja o runbook de disco cheio do Postgres, se for o caso) e suba de novo.
- Host errado na aplicação: corrija a variável de conexão e reinicie a aplicação.
- `listen_addresses`: ajuste para o IP ou `'*'` (com o `pg_hba.conf` restringindo o acesso) e reinicie o Postgres.

## Prevenção

- No compose, use `depends_on` com `condition: service_healthy` e um healthcheck com `pg_isready`, para a aplicação não subir antes do banco.
- Faça a aplicação tentar reconectar com intervalos crescentes, em vez de morrer no primeiro erro.
- Monitore o Postgres diretamente, não só pelos erros das aplicações.
