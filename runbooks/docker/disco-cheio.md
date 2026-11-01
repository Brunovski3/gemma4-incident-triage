# Disco do Docker cheio

`docker_disco_cheio` · **Componente:** Docker / Armazenamento · **Severidade:** CRITICA

## Resumo rápido

O disco onde o Docker guarda tudo (normalmente `/var/lib/docker`) encheu. A partir daí nada funciona direito: builds falham, containers não sobem e os que estão rodando podem quebrar ao tentar escrever. Na maioria das vezes os culpados são imagens antigas, cache de build ou logs de container crescendo sem limite.

## Como aparece nos logs

- `no space left on device`, em mensagens como:
  - `failed to register layer: write /var/lib/docker/overlay2/...`
  - `write /var/lib/docker/containers/<id>/<id>-json.log: no space left on device`
  - `failed to solve: ... mkdir /var/lib/docker/overlay2/...-init: no space left on device`

## Diagnóstico

1. **Confirme o espaço:**
   ```bash
   df -h /var/lib/docker
   ```

2. **Veja o que o Docker está ocupando:**
   ```bash
   docker system df
   ```
   A coluna `RECLAIMABLE` mostra quanto dá para liberar com segurança.

3. **Procure logs gigantes.** É o vilão mais comum e o mais esquecido:
   ```bash
   sudo du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail
   ```
   Um container que loga muito, sem rotação, pode ocupar dezenas de GB sozinho.

## Correção

Libere espaço do mais seguro para o mais arriscado:

1. Cache de build: `docker builder prune -f`
2. Containers parados: `docker container prune -f`
3. Imagens sem uso: `docker image prune -a -f` (vai ser preciso baixar de novo as imagens que não estão em uso)
4. Log gigante de um container em execução: zere sem apagar o arquivo:
   ```bash
   sudo truncate -s 0 $(docker inspect --format='{{.LogPath}}' nome-do-container)
   ```

**Cuidado com `docker volume prune` e com `docker system prune --volumes`.** Volumes guardam dados de verdade (bancos, uploads). Só rode isso se tiver certeza de que nenhum volume sem uso no momento é importante.

## Prevenção

- Configure rotação de logs para todos os containers em `/etc/docker/daemon.json`:
  ```json
  { "log-driver": "json-file", "log-opts": { "max-size": "50m", "max-file": "3" } }
  ```
  Depois reinicie o Docker. A regra só vale para containers criados a partir daí.
- Agende uma limpeza periódica de cache de build e imagens antigas.
- Alerte com 80% de uso do disco, não com 100%.
