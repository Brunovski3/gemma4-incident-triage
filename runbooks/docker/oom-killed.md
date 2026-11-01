# Container morto por falta de memória (OOMKilled)

`docker_oom_killed` · **Componente:** Docker / Container · **Severidade:** ALTA

## Resumo rápido

O container passou do limite de memória e o kernel matou o processo. O sinal clássico é o **exit code 137** (128 + 9, o SIGKILL). O app não recebe aviso nenhum: ele simplesmente some, por isso os logs da aplicação costumam parar no meio de uma linha, sem erro nenhum.

## Como aparece nos logs

- `api-1 exited with code 137`
- No kernel: `Out of memory: Killed process 4242 (node)` ou `Memory cgroup out of memory: Killed process ...`
- No `docker inspect`: `"OOMKilled": true`

## Diagnóstico

1. **Confirme que foi OOM, e não outro kill:**
   ```bash
   docker inspect api-1 --format '{{.State.OOMKilled}} {{.State.ExitCode}}'
   ```
   `true 137` fecha o diagnóstico. Um `false 137` significa que alguém (ou algum orquestrador) mandou um kill por outro motivo.

2. **Qual era o limite?**
   ```bash
   docker inspect api-1 --format '{{.HostConfig.Memory}}'
   ```
   O valor vem em bytes. Um `0` significa sem limite: nesse caso foi o **host inteiro** que ficou sem memória, e o kernel escolheu esse processo para matar. Isso é mais grave, porque qualquer outro serviço podia ter sido a vítima.

3. **Veja o consumo ao longo do tempo:**
   ```bash
   docker stats api-1
   ```
   Memória subindo devagar e sem parar indica vazamento. Picos repentinos apontam para uma requisição específica (um upload grande, um relatório que carrega tudo na memória).

4. **No host, confira o histórico:**
   ```bash
   dmesg -T | grep -i -E 'killed process|out of memory'
   ```

## Correção

- Se o limite era apertado demais para a carga normal, aumente (`mem_limit` no compose ou `deploy.resources.limits.memory`).
- Se é vazamento, aumentar o limite só adia o próximo crash. Reinicie para estabilizar e investigue o código.
- Ajuste o runtime para respeitar o limite do container:
  - Java: `-XX:MaxRAMPercentage=75`
  - Node: `--max-old-space-size` um pouco abaixo do limite
  - Gunicorn/Uvicorn: menos workers (cada um carrega uma cópia do app)

## Prevenção

- Todo container de produção deveria ter limite de memória. Sem limite, um serviço com vazamento derruba o host inteiro.
- Alerte quando o uso passar de 80% do limite, antes do kill.
- Use `restart: unless-stopped` para o serviço voltar sozinho enquanto vocês investigam.
