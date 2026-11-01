# Router referencia um middleware que não existe

`traefik_middleware_inexistente` · **Componente:** Traefik / Roteamento · **Severidade:** MEDIA

## Resumo rápido

Um router aponta para um middleware (autenticação, CORS, rate limit) que o Traefik não encontrou. Quando isso acontece, o Traefik **desativa o router inteiro**, então a rota passa a responder 404. É quase sempre um problema de nome: um erro de digitação ou o sufixo do provider errado.

## Como aparece nos logs

- `middleware "auth@docker" does not exist`, com `routerName=api@docker` e o `entryPointName`.
- Do lado do usuário: 404 numa rota que funcionava, logo depois de um deploy.

## Diagnóstico

1. **Leia o nome completo do middleware na mensagem, incluindo o sufixo.** O sufixo diz onde o Traefik procurou:
   - `@docker`: nas labels de algum container.
   - `@file`: nos arquivos de configuração dinâmica.
   - `@kubernetescrd`: nos recursos `Middleware` do Kubernetes.

2. **Liste o que existe de fato.** Pela API ou dashboard do Traefik:
   ```bash
   curl -s http://localhost:8080/api/http/middlewares | jq -r '.[].name'
   ```
   Compare com o nome que o router pede. É comum o middleware existir como `auth@file` e o router pedir `auth@docker`.

3. **Middleware definido em outro container?** Com o provider Docker, um middleware declarado nas labels do container X só existe enquanto X está rodando. Se X caiu ou foi removido, todo router que usa aquele middleware cai junto.

## Correção

- Corrija o nome ou o sufixo na label do router (`traefik.http.routers.<nome>.middlewares=auth@file`).
- Se o middleware vivia num container que saiu, suba esse container de novo ou mova a definição para um lugar estável.
- Depois de corrigir, confira se o router voltou a aparecer como habilitado no dashboard.

## Prevenção

- Defina middlewares compartilhados (autenticação, headers de segurança, CORS) no file provider, e não nas labels de um container qualquer. Assim eles não somem quando um serviço é removido.
- Padronize os nomes e documente quais middlewares existem.
- Se possível, valide a configuração no CI antes do deploy.
