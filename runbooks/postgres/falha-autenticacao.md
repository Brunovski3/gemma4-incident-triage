# Falha de autenticação no PostgreSQL

`postgres_falha_autenticacao` · **Componente:** PostgreSQL / Autenticação · **Severidade:** MEDIA

## Resumo rápido

O Postgres recusou o login. Ou a senha não confere, ou o `pg_hba.conf` não tem uma regra que permita aquela combinação de host, banco e usuário. É muito comum logo depois de uma rotação de senha em que o banco foi atualizado e a aplicação não (ou o contrário).

## Como aparece nos logs

- `FATAL:  password authentication failed for user "app"`, geralmente seguido de um `DETAIL: Connection matched pg_hba.conf line 99` que mostra qual regra foi usada.
- `FATAL:  no pg_hba.conf entry for host "172.18.0.5", user "app", database "app", no encryption`: nenhuma regra permite essa conexão.
- No lado da aplicação: `PSQLException: FATAL: password authentication failed`.

## Diagnóstico

1. **Qual das duas mensagens?** Elas têm causas diferentes:
   - `password authentication failed`: a regra existe, mas a senha não bate.
   - `no pg_hba.conf entry`: o problema é a regra de acesso, não a senha.

2. **Senha não bate:** houve rotação recente? Confira se a aplicação recebeu a senha nova (variável de ambiente, secret do Kubernetes, cofre). Muitas aplicações só leem a senha na inicialização e precisam ser reiniciadas.

3. **Método de criptografia:** se o `pg_hba.conf` exige `scram-sha-256` mas a senha do usuário foi gravada em `md5` (comum em bancos migrados de versões antigas), o login falha mesmo com a senha certa. Para conferir, como superusuário:
   ```sql
   SELECT rolname, left(rolpassword, 14) FROM pg_authid WHERE rolname = 'app';
   ```
   Se começar com `md5`, a senha precisa ser redefinida com `password_encryption = 'scram-sha-256'`.

4. **Sem regra no pg_hba:** compare o host, o banco e o usuário da mensagem com as regras do arquivo. IPs de containers mudam quando a rede Docker é recriada, e uma regra fixa por IP pode parar de servir.

## Correção

- Senha divergente: alinhe a senha no banco e na aplicação e reinicie a aplicação. Defina a senha pelo `psql` com `\password app`, que não deixa a senha no histórico. **Nunca cole senhas em tickets, chats ou logs.**
- Regra ausente: adicione a linha no `pg_hba.conf` (prefira uma faixa de rede a um IP fixo) e recarregue sem reiniciar:
  ```sql
  SELECT pg_reload_conf();
  ```

## Prevenção

- Guarde credenciais num cofre (Vault, secrets do Kubernetes, Docker secrets) e faça a rotação de forma coordenada: atualize o banco e a aplicação na mesma janela.
- Monitore a taxa de falhas de autenticação. Um pico pode ser configuração errada, mas também pode ser tentativa de invasão.
