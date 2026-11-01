# Porta do host já está em uso

`docker_porta_em_uso` · **Componente:** Docker / Rede · **Severidade:** MEDIA

## Resumo rápido

O container tentou publicar uma porta no host (por exemplo, `5432:5432`) e outra coisa já está ocupando essa porta. Pode ser outro container, um serviço instalado direto no servidor (um Postgres ou um Nginx esquecido) ou um resto de um container que não foi limpo direito.

## Como aparece nos logs

- `Bind for 0.0.0.0:5432 failed: port is already allocated`
- `listen tcp 0.0.0.0:80: bind: address already in use`
- `Error starting userland proxy: listen tcp4 0.0.0.0:8080: bind: address already in use`

## Diagnóstico

1. **Quem está usando a porta no host?**
   ```bash
   sudo ss -ltnp 'sport = :5432'
   ```
   A coluna de processo mostra o culpado. Se aparecer `docker-proxy`, é outro container.

2. **Se for container, qual?**
   ```bash
   docker ps --filter publish=5432
   ```

3. **Sobrou algo de um compose antigo?** Containers de um projeto renomeado ou de uma pasta diferente continuam rodando e segurando a porta:
   ```bash
   docker ps -a --format '{{.Names}}\t{{.Ports}}'
   ```

## Correção

- Serviço do sistema ocupando a porta (por exemplo, um Postgres instalado via apt): pare e desabilite (`sudo systemctl disable --now postgresql`), ou mude a porta publicada do container.
- Container antigo: remova (`docker rm -f nome`) ou rode `docker compose down --remove-orphans` no projeto antigo.
- Se nada aparece usando a porta mas o erro continua, é um `docker-proxy` órfão. Reiniciar o daemon do Docker costuma limpar (`sudo systemctl restart docker`). Lembre que isso reinicia todos os containers do host.

## Prevenção

- Só publique portas que realmente precisam ser acessadas de fora. Banco e cache normalmente só precisam ser alcançados pelos outros containers, pela rede interna do Docker, sem `ports:` nenhum.
- Mantenha um registro de quais portas cada projeto usa no servidor.
