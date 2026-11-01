# Falha ao baixar a imagem do registry

`docker_falha_pull_imagem` · **Componente:** Docker / Registry · **Severidade:** MEDIA

## Resumo rápido

O Docker tentou baixar a imagem e não conseguiu. O serviço não sobe, ou continua na versão antiga se for um deploy. As causas se dividem em dois grupos: a imagem não existe com aquele nome ou tag, ou você não tem permissão para baixar.

## Como aparece nos logs

- `manifest for registry.exemplo.com/api:1.4.2 not found: manifest unknown`: a tag não existe.
- `pull access denied for ..., repository does not exist or may require 'docker login'`: sem acesso, ou o nome está errado.
- `unauthorized: authentication required`: credencial ausente ou expirada.

## Diagnóstico

1. **A tag existe?**
   ```bash
   docker manifest inspect registry.exemplo.com/api:1.4.2 > /dev/null && echo existe
   ```
   Se não existe, confira se o pipeline de CI realmente publicou essa versão. É comum o deploy rodar antes do push terminar, ou o build ter falhado sem ninguém ver.

2. **O nome está certo?** Confira registry, caminho e tag letra por letra. `api:1.4.2` e `api:v1.4.2` são imagens diferentes.

3. **A credencial está válida?**
   ```bash
   docker login registry.exemplo.com
   ```
   Tokens de registry (GitLab, GitHub, ECR) expiram. O ECR, por exemplo, gera tokens que valem só 12 horas.

4. **Arquitetura:** a mensagem `no matching manifest for linux/arm64` significa que a imagem só foi gerada para outra arquitetura, comum ao misturar servidores ARM e x86.

## Correção

- Tag inexistente: publique a imagem (rode o pipeline de novo) ou corrija a tag no compose.
- Sem acesso: faça `docker login` com uma credencial válida. Em servidor, prefira um token de deploy só de leitura, e não a sua credencial pessoal.
- Arquitetura: gere a imagem multi-arquitetura (`docker buildx build --platform linux/amd64,linux/arm64`).

## Prevenção

- Faça o deploy apenas depois de o CI confirmar o push da imagem.
- Prefira tags imutáveis (a versão ou o hash do commit) em vez de `latest`. Assim você sabe exatamente o que está rodando.
- Use um credential helper ou um token de longa duração com permissão mínima nos servidores.
