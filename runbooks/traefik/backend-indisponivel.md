# Traefik devolvendo 502: o backend não atende

`traefik_backend_indisponivel` · **Componente:** Traefik / Upstream · **Severidade:** ALTA

## Resumo rápido

Um 502 quase nunca é culpa do Traefik. Ele só está avisando que tentou entregar a requisição para o serviço e ninguém atendeu do outro lado. O trabalho aqui é descobrir por que o serviço não está aceitando conexão.

## Como aparece nos logs

- Access log com status `502` e tempo de resposta quase zero (1 a 3 ms). Ele nem chegou a esperar.
- `502 Bad Gateway error` com `dial tcp 172.18.0.7:8080: connect: connection refused`
- Variação: `connect: no route to host`, que aponta mais para rede do que para o serviço em si.

## Diagnóstico

1. **O container está de pé?** Comece pelo óbvio:
   ```bash
   docker compose ps
   docker ps -a --filter name=api
   ```
   Se ele estiver reiniciando em loop, o problema real está nos logs dele (`docker logs --tail 100 api-1`), não no Traefik.

2. **A porta bate?** O Traefik usa a porta da label `traefik.http.services.<nome>.loadbalancer.server.port`. Se o app mudou de 8080 para 3000 e ninguém atualizou a label, dá exatamente esse erro.
   ```bash
   docker inspect api-1 --format '{{json .Config.Labels}}' | jq
   ```

3. **O app escuta em 0.0.0.0?** Um clássico: o processo sobe ouvindo só em `127.0.0.1`, que dentro do container significa "ninguém de fora me alcança".
   ```bash
   docker exec api-1 sh -c 'ss -ltn || netstat -ltn'
   ```

4. **Estão na mesma rede?** Com `no route to host`, confira se o Traefik e o serviço compartilham uma rede Docker:
   ```bash
   docker network inspect proxy --format '{{range .Containers}}{{.Name}} {{end}}'
   ```
   Se o container estiver em mais de uma rede, defina `traefik.docker.network=proxy` para o Traefik não escolher a errada.

## Correção

- Container parado ou em loop: resolva a causa nos logs dele e suba de novo (`docker compose up -d api`).
- Porta errada: ajuste a label e recrie o container.
- Bind em localhost: configure o app para ouvir em `0.0.0.0` (no Uvicorn, `--host 0.0.0.0`; no Node, `app.listen(8080, '0.0.0.0')`).
- Rede: conecte o container à rede do proxy ou fixe `traefik.docker.network`.

## Prevenção

- Configure `restart: unless-stopped` e um healthcheck no serviço.
- Use o healthcheck do próprio Traefik (`loadbalancer.healthcheck.path`), para ele tirar instâncias mortas do balanceamento.
- Alerte sobre a taxa de 5xx por router, não sobre cada erro isolado.

## Quando escalar

Se o serviço responde normalmente quando você testa de dentro da rede (`docker exec traefik wget -qO- http://api:8080/health`) e o 502 continua, aí sim vale olhar a configuração do Traefik com calma ou chamar quem cuida do proxy.
