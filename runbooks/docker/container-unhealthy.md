# Container falhou no healthcheck

`docker_container_unhealthy` · **Componente:** Docker / Healthcheck · **Severidade:** ALTA

## Resumo rápido

O container está rodando, mas o healthcheck dele falhou várias vezes seguidas e o Docker marcou como `unhealthy`. No compose, quem depende dele com `condition: service_healthy` nem sobe. Às vezes o app está de fato quebrado; às vezes o problema é o próprio healthcheck.

## Como aparece nos logs

- `dependency failed to start: container api-1 is unhealthy`
- `container health_status: unhealthy ... name=api-1` (eventos do Docker)
- No `docker ps`: `Up 5 minutes (unhealthy)`

## Diagnóstico

1. **Veja o que o healthcheck respondeu:**
   ```bash
   docker inspect api-1 --format '{{json .State.Health}}' | jq '.Log[-3:]'
   ```
   Isso mostra as últimas tentativas com o código de saída e a saída do comando. Geralmente a resposta está aqui.

2. **Rode o comando do healthcheck na mão, de dentro do container:**
   ```bash
   docker exec api-1 sh -c 'curl -fsS http://localhost:8080/health'
   ```
   Fique atento a `curl: not found`: imagens enxutas (alpine, distroless) muitas vezes não têm `curl`, e o healthcheck falha sempre, com o app perfeitamente saudável.

3. **O app demora para subir?** Se o healthcheck começa antes de o app terminar de iniciar (migrações, cache aquecendo), ele falha nas primeiras tentativas e o container é marcado como unhealthy.

4. **O endpoint de health depende de outra coisa?** Se o `/health` testa o banco e o banco caiu, o container fica unhealthy por causa do banco. Nesse caso o problema real está no banco.

## Correção

- Ferramenta ausente na imagem: use o que existe (`wget -qO-` no alpine) ou um pequeno script na linguagem do próprio app.
- App lento para subir: aumente o `start_period` do healthcheck.
- Falha real do app: resolva a causa nos logs (`docker logs api-1`).
- Dependência fora do ar: siga o runbook da dependência.

## Prevenção

- Teste o healthcheck localmente sempre que mudar a imagem base.
- Configure o `start_period` de acordo com o tempo real de inicialização.
- Mantenha o healthcheck simples: ele deve responder "este processo está funcionando?", sem testar em cascata todas as dependências.
