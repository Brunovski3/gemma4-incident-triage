# Authentik sem conexão com o PostgreSQL

`authentik_banco_indisponivel` · **Componente:** Authentik / Banco de dados · **Severidade:** CRITICA

## Resumo rápido

O Authentik guarda tudo no PostgreSQL: usuários, fluxos, providers e configuração. Sem banco, não existe login em nenhuma aplicação que use SSO, por isso a severidade é crítica. Na prática, ou o Postgres caiu, ou o Authentik está procurando o banco no lugar errado ou com a senha errada.

## Como aparece nos logs

- `"event": "PostgreSQL connection failed, retrying... (connection to server at \"postgresql\" (172.18.0.3), port 5432 failed: Connection refused)"`
- `django.db.utils.OperationalError: connection failed: connection to server at "172.18.0.3", port 5432 failed: Connection refused`
- `psycopg.OperationalError: connection failed: ...`, por exemplo durante as migrações no startup.
- Em cascata: 502 no Traefik para o domínio do Authentik.

## Diagnóstico

1. **O Postgres do Authentik está de pé?**
   ```bash
   docker compose ps postgresql
   docker compose logs --tail 100 postgresql
   ```

2. **Uma pegadinha clássica do Authentik: atualização de versão do Postgres.** Se alguém atualizou o compose e a imagem do Postgres subiu de versão principal (por exemplo, de 12 para 16), o Postgres novo se recusa a abrir os dados antigos e o log mostra algo como `database files are incompatible with server`. Os dados não estão perdidos, mas precisam ser migrados.

3. **Senha e host:** confira `AUTHENTIK_POSTGRESQL__HOST`, `__USER`, `__NAME` e `__PASSWORD` no `.env`. Se a senha do banco (`PG_PASS`) mudou depois da primeira inicialização, o volume continua com a senha antiga: trocar a variável não altera a senha de um banco já criado.

## Correção

- Postgres parado por outro motivo: resolva pelos logs dele (veja os runbooks do PostgreSQL) e suba de novo.
- Versão incompatível: volte a tag da imagem para a versão anterior para restaurar o serviço imediatamente. Depois, planeje a migração com `pg_dump` e restore (ou `pg_upgrade`) seguindo o guia de atualização do Authentik.
- Senha divergente: alinhe a variável com a senha real do banco (ou altere a senha dentro do Postgres) e recrie o server e o worker.

## Prevenção

- Fixe a versão exata da imagem do Postgres no compose e leia as notas de atualização do Authentik antes de mudar.
- Faça backup do banco antes de qualquer atualização.
- Configure healthcheck no Postgres com `depends_on: condition: service_healthy`.
