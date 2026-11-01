# O database não existe no PostgreSQL

`postgres_banco_inexistente` · **Componente:** PostgreSQL / Banco de dados · **Severidade:** ALTA

## Resumo rápido

O PostgreSQL está no ar e aceitando conexões, mas o **database** que a aplicação pede nunca foi criado. Não confunda com o Postgres fora do ar: aqui ele responde, só que responde "esse banco não existe". Quase sempre o problema está na inicialização: o volume já tinha dados de uma execução anterior (e o script de criação não roda de novo), a variável `POSTGRES_DB` não foi definida, ou o nome do banco na aplicação é diferente do nome criado.

## Como aparece nos logs

- No Postgres, repetido a cada tentativa: `FATAL:  database "authentik" does not exist`
- Na aplicação, em loop: `PostgreSQL connection failed, retrying... (connection failed: FATAL:  database "authentik" does not exist)`, ou `OperationalError ... database "app" does not exist`.
- No Kubernetes, o pod da aplicação acaba em BackOff, porque o processo desiste e sai.
- Pode aparecer um `Connection refused` no meio, se o Postgres reiniciar. Isso é passageiro: a causa raiz continua sendo o banco inexistente.

## Diagnóstico

1. **Quais bancos existem?**
   ```bash
   kubectl exec -n chaos-lab deploy/postgres -- psql -U postgres -c '\l'
   ```
   (Com compose: `docker compose exec db psql -U postgres -c '\l'`.)

2. **O que a aplicação pede?** Compare com a configuração dela. No Authentik é `AUTHENTIK_POSTGRESQL__NAME`; em outras, procure `DB_NAME`, `DATABASE_URL` ou equivalente. Um `authentik` contra um `authentik_db` já explica tudo.

3. **O volume é antigo?** A imagem oficial do Postgres só cria o banco do `POSTGRES_DB` e roda os scripts de `/docker-entrypoint-initdb.d/` **na primeira inicialização, com o diretório de dados vazio**. Se o volume já existia, nada disso roda. O log mostra a pista: com volume novo aparece toda a saída do `initdb`; com volume reaproveitado, o Postgres sobe direto.

4. **O `POSTGRES_DB` está definido?** Confira as variáveis do container do Postgres. Sem ela, só existe o banco `postgres`.

## Correção

- Crie o banco que falta, com o dono certo:
  ```bash
  kubectl exec -n chaos-lab deploy/postgres -- psql -U postgres -c 'CREATE DATABASE authentik OWNER authentik;'
  ```
  A aplicação está em retry e conecta sozinha na próxima tentativa; no Kubernetes, o pod sai do BackOff no próximo reinício.
- Se o nome estava errado na aplicação, corrija a variável e reinicie a aplicação.
- Em ambiente descartável (como um lab), outra opção é apagar o volume e deixar o `initdb` rodar do zero, já com o `POSTGRES_DB` correto. **Nunca faça isso com dados que importam.**

## Prevenção

- Defina `POSTGRES_DB` explicitamente nos manifests e mantenha o mesmo nome na configuração da aplicação (de preferência vindo da mesma variável ou Secret).
- Não dependa do `initdb` para criar bancos em volumes que sobrevivem a recriações: use um Job de inicialização idempotente (`CREATE DATABASE ... ` só se não existir) ou a migração da própria aplicação.
- Faça a aplicação logar com clareza qual banco tentou abrir; isso encurta muito o diagnóstico.
