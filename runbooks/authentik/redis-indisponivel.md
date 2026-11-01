# Authentik sem conexão com o Redis

`authentik_redis_indisponivel` · **Componente:** Authentik / Cache · **Severidade:** ALTA

## Resumo rápido

O Authentik não consegue falar com o Redis. Nas versões que dependem dele, o Redis guarda cache, sessões e a fila de tarefas do worker (Celery). Sem ele, o server pode nem terminar de subir e o worker para de processar tarefas, como envio de e-mail e sincronização dos outposts.

> As versões mais recentes do Authentik estão reduzindo ou removendo a dependência do Redis. Antes de seguir, confira nas notas da versão que você usa se o Redis ainda faz parte da instalação.

## Como aparece nos logs

- `"event": "Redis Connection failed, retrying..."` (logger `authentik.lifecycle.wait_for_db`)
- `redis.exceptions.ConnectionError: Error 111 connecting to redis:6379. Connection refused.`
- Worker: `consumer: Cannot connect to redis://redis:6379/0: Error 111 ...` com `Trying again in 2.00 seconds...`

## Diagnóstico

1. **O Redis está rodando?**
   ```bash
   docker compose ps redis
   docker compose logs --tail 50 redis
   ```

2. **Ele responde?**
   ```bash
   docker compose exec redis redis-cli ping
   ```
   O esperado é `PONG`.

3. **Erros típicos nos logs do Redis:**
   - `MISCONF Redis is configured to save RDB snapshots, but it's currently unable to persist to disk`: disco cheio ou sem permissão no volume. O Redis passa a recusar escritas.
   - `OOM command not allowed when used memory > 'maxmemory'`: atingiu o limite de memória.

4. **O Authentik procura no lugar certo?** Confira `AUTHENTIK_REDIS__HOST` no `.env`. No compose padrão, o valor é o nome do serviço (`redis`).

## Correção

- Container parado: `docker compose up -d redis` e, depois, reinicie o server e o worker do Authentik.
- Disco cheio: libere espaço no volume do Redis (veja o runbook de disco cheio do Docker).
- Memória: aumente o `maxmemory` ou o limite do container.
- Host errado: corrija a variável e recrie os containers do Authentik.

## Prevenção

- Configure healthcheck no Redis (`redis-cli ping`) e `depends_on` com `condition: service_healthy` no server e no worker.
- Monitore memória e disco do Redis.
