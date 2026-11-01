# Pod em ImagePullBackOff

`k8s_image_pull_backoff` · **Componente:** Kubernetes / Registry · **Severidade:** ALTA

## Resumo rápido

O nó não conseguiu baixar a imagem do container. O pod nunca chega a rodar. As causas são as mesmas do Docker, só que vistas pelo nó: a tag não existe, falta credencial (`imagePullSecrets`), ou o nó não alcança o registry.

## Como aparece nos logs

- `kubectl get pods`: `ErrImagePull` e depois `ImagePullBackOff`.
- Evento: `Failed to pull image "registry.exemplo.com/api:1.4.2": rpc error: code = NotFound desc = ... not found`
- kubelet: `... with ImagePullBackOff: "Back-off pulling image ..."`
- Alertmanager: `KubeContainerWaiting` com `reason: "ImagePullBackOff"`

## Diagnóstico

1. **A mensagem exata está nos eventos do pod:**
   ```bash
   kubectl describe pod -n producao api-xxx | sed -n '/Events/,$p'
   ```
   - `not found` / `manifest unknown`: a tag não existe.
   - `unauthorized` / `authentication required`: problema de credencial.
   - `i/o timeout` / `no such host`: o nó não alcança o registry.
   - `429 Too Many Requests`: limite de downloads do Docker Hub para contas anônimas.

2. **Credencial:** confira se o pod (ou a ServiceAccount dele) tem o `imagePullSecrets` e se o secret existe **no mesmo namespace**:
   ```bash
   kubectl get pod -n producao api-xxx -o jsonpath='{.spec.imagePullSecrets}'
   kubectl get secret -n producao
   ```
   Um secret criado em `default` não vale para pods de `producao`.

3. **Rede:** teste a partir de um nó, ou de um pod de debug, se o registry responde.

## Correção

- Tag errada ou ausente: corrija a imagem no Deployment ou publique a versão que falta.
- Secret ausente ou expirado: recrie o secret do tipo `docker-registry` no namespace certo e referencie no pod ou na ServiceAccount.
- Docker Hub limitando: autentique os pulls ou use um mirror/cache de registry.
- Rede: libere a saída dos nós para o registry (firewall, proxy, DNS).

## Prevenção

- Use tags imutáveis ou digest (`@sha256:...`) nos manifests.
- Coloque o `imagePullSecrets` na ServiceAccount padrão do namespace, para não depender de cada Deployment lembrar.
- Para imagens públicas muito usadas, mantenha um mirror interno.
