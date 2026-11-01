# Tabela não existe no banco

`postgres_relacao_inexistente` · **Componente:** PostgreSQL / Schema · **Severidade:** MEDIA

## Resumo rápido

A aplicação consultou uma tabela que o banco não conhece. Em 9 de cada 10 casos é uma **migração que não rodou**: o código novo foi publicado, mas o schema do banco continua na versão anterior. Os outros casos são banco errado, schema errado ou diferença de maiúsculas no nome.

## Como aparece nos logs

- `ERROR:  relation "pedidos" does not exist at character 15`, seguido do `STATEMENT` com a query.
- SQLAlchemy: `psycopg2.errors.UndefinedTable: relation "pedidos" does not exist`
- Prisma: `The table public.pedidos does not exist in the current database.`

## Diagnóstico

1. **A tabela existe em algum lugar?**
   ```sql
   SELECT table_schema, table_name FROM information_schema.tables WHERE table_name ILIKE 'pedidos';
   ```
   - Não existe: é migração pendente.
   - Existe em outro schema: problema de `search_path`.
   - Existe como `Pedidos`: foi criada com aspas e agora diferencia maiúsculas.

2. **A aplicação está no banco certo?**
   ```sql
   SELECT current_database(), current_schema();
   SHOW search_path;
   ```
   Apontar produção para o banco de homologação (ou o contrário) é mais comum do que parece.

3. **Qual a última migração aplicada?** Depende da ferramenta:
   ```sql
   SELECT * FROM alembic_version;                                -- Alembic
   SELECT version, success FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5;  -- Flyway
   SELECT migration_name, finished_at FROM _prisma_migrations ORDER BY finished_at DESC LIMIT 5;  -- Prisma
   ```
   Compare com as migrações que existem no repositório.

## Correção

- Migração pendente: rode as migrações (`alembic upgrade head`, `prisma migrate deploy`, `flyway migrate`).
- Migração que falhou no meio: veja o erro dela antes de rodar de novo. Algumas ferramentas exigem marcar a migração como resolvida manualmente.
- Schema errado: ajuste o `search_path` do usuário (`ALTER ROLE app SET search_path = app, public;`) ou qualifique o nome na query.
- Banco errado: corrija a string de conexão.

## Prevenção

- Faça a migração ser uma etapa obrigatória do deploy, rodando **antes** da nova versão da aplicação subir.
- Escreva migrações compatíveis com a versão anterior do código (adicione colunas e tabelas antes de usá-las; remova só no deploy seguinte). Isso permite rollback sem quebrar.
