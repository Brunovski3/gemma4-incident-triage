# Traefik sem permissão RBAC no Kubernetes

`traefik_rbac_sem_permissao` · **Componente:** Traefik / Provider Kubernetes · **Severidade:** ALTA

## Resumo rápido

O Traefik está rodando, mas a ServiceAccount que ele usa não tem permissão para ler os recursos do cluster (Services, Endpoints, Secrets, IngressRoutes, Middlewares). Sem conseguir listar nada, o provider Kubernetes não descobre nenhuma rota, e todo tráfego que deveria passar por ele recebe 404. O erro mais comum é instalar o Traefik com manifests próprios e esquecer o `ClusterRole` e o `ClusterRoleBinding`, ou rodar o pod com a ServiceAccount `default` do namespace.

## Como aparece nos logs

- Linhas do client-go (klog) repetidas para cada tipo de recurso, a cada poucos segundos:
  `failed to list *v1alpha1.IngressRoute: ingressroutes.traefik.io is forbidden: User "system:serviceaccount:chaos-lab:default" cannot list resource "ingressroutes" in API group "traefik.io" at the cluster scope`
- Pares `W... failed to list` e `E... Failed to watch` para o mesmo recurso.
- O nome da ServiceAccount aparece no `User "system:serviceaccount:<namespace>:<nome>"`. Se for `default`, o pod não está usando a ServiceAccount do Traefik.

## Diagnóstico

1. **Qual ServiceAccount o pod usa?**
   ```bash
   kubectl get pod -n chaos-lab -l app=traefik -o jsonpath='{.items[0].spec.serviceAccountName}'
   ```

2. **Ela tem permissão?** Teste como se fosse ela:
   ```bash
   kubectl auth can-i list ingressroutes.traefik.io --as=system:serviceaccount:chaos-lab:default -A
   kubectl auth can-i watch services --as=system:serviceaccount:chaos-lab:default -A
   ```
   `no` confirma o problema.

3. **Existe um ClusterRole para o Traefik e ele está vinculado?**
   ```bash
   kubectl get clusterrole,clusterrolebinding | grep -i traefik
   kubectl describe clusterrolebinding traefik
   ```
   Confira se o `subjects` do binding aponta para a ServiceAccount e o namespace certos. Um binding para `traefik` no namespace `kube-system` não vale para um pod em `chaos-lab`.

## Correção

- Crie (ou corrija) a ServiceAccount, o ClusterRole e o ClusterRoleBinding do Traefik. O jeito mais seguro é usar o RBAC publicado pelo próprio projeto para a sua versão (o Helm chart oficial já cria tudo).
- Aponte o Deployment para a ServiceAccount certa (`spec.template.spec.serviceAccountName: traefik`) e faça o rollout.
- Se a ideia é o Traefik enxergar só um namespace, use `Role` e `RoleBinding` e restrinja o provider com a opção `namespaces`; senão, ele continua tentando listar no cluster inteiro e continua recebendo `forbidden`.
- Depois da correção, os erros param em segundos e as rotas aparecem no dashboard.

## Prevenção

- Instale o Traefik pelo Helm chart oficial ou mantenha o RBAC versionado junto com o Deployment.
- Nunca use a ServiceAccount `default` para componentes que conversam com a API do Kubernetes.
- Inclua um `kubectl auth can-i` no checklist de deploy de qualquer controller.
