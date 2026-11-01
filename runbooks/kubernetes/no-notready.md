# Nó do Kubernetes em NotReady

`k8s_no_notready` · **Componente:** Kubernetes / Nó · **Severidade:** CRITICA

## Resumo rápido

O nó parou de informar seu estado ao control-plane. Depois de cerca de 5 minutos (o `tolerationSeconds` padrão), os pods dele são marcados para remoção e recriados em outros nós, se houver espaço. Enquanto isso, o que rodava ali pode estar fora do ar. A causa costuma ser o kubelet ou o container runtime travado, pressão de recursos no nó ou rede.

## Como aparece nos logs

- `kubectl get nodes`: o nó com `STATUS` `NotReady`.
- Evento: `Node worker-2 status is now: NodeNotReady`
- `kubectl describe node`: condições em `Unknown` com `Kubelet stopped posting node status.`
- Alertmanager: `KubeNodeNotReady`
- Em seguida: eventos `TaintManagerEviction` nos pods do nó.

## Diagnóstico

1. **O que o cluster vê:**
   ```bash
   kubectl describe node worker-2 | sed -n '/Conditions/,/Addresses/p'
   ```
   `Unknown` em tudo significa que o kubelet sumiu. `MemoryPressure` ou `DiskPressure` em `True` mostram que o nó está vivo, mas sufocado.

2. **Entre no nó (SSH) e veja o kubelet e o runtime:**
   ```bash
   sudo systemctl status kubelet containerd
   sudo journalctl -u kubelet --since "30 min ago" | tail -50
   ```

3. **Recursos do nó:**
   ```bash
   df -h /var/lib/kubelet /var/lib/containerd
   free -h
   ```
   Disco cheio (por imagens ou logs) é uma das causas mais comuns.

4. **Rede até o API server:** o nó precisa alcançar o control-plane (normalmente a porta 6443). Uma mudança de firewall ou de rota isola o nó.

5. **Certificado do kubelet:** em clusters montados manualmente, o certificado do kubelet pode ter expirado. O `journalctl` mostra `x509` nesse caso.

## Correção

- Kubelet ou containerd travado: `sudo systemctl restart containerd kubelet`.
- Disco cheio: limpe imagens não usadas (`sudo crictl rmi --prune`) e logs antigos.
- Rede: restaure a conectividade com o API server.
- Nó irrecuperável: drene e remova (`kubectl drain worker-2 --ignore-daemonsets --delete-emptydir-data` e depois `kubectl delete node worker-2`), e suba um nó novo.

## Prevenção

- Configure limites de eviction do kubelet e reserve recursos para o sistema (`system-reserved`, `kube-reserved`).
- Garanta rotação automática do certificado do kubelet.
- Mantenha folga no cluster para absorver a perda de um nó.
- Monitore disco e memória dos nós, não só dos pods.
