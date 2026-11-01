# Pods presos em Pending por falta de recursos

`k8s_pending_recursos` · **Componente:** Kubernetes / Scheduler · **Severidade:** ALTA

## Resumo rápido

O scheduler não encontrou nenhum nó com CPU ou memória suficientes para o pod. Como no Swarm, o que conta são os **requests** declarados, não o uso real: um cluster pode estar com uso baixo e mesmo assim "cheio" se os requests estiverem inflados.

## Como aparece nos logs

- `kubectl get pods`: status `Pending` por vários minutos.
- Evento `FailedScheduling`: `0/3 nodes are available: 3 Insufficient cpu.` (ou `Insufficient memory`).
- kube-scheduler: `"Unable to schedule pod; no fit; waiting" ... Insufficient memory`
- O deployment fica com réplicas faltando (`0/3`).

## Diagnóstico

1. **Leia a mensagem do evento inteira.** Ela diz quantos nós foram avaliados e por que cada grupo foi descartado. Às vezes não é recurso: `node(s) had untolerated taint` ou `didn't match Pod's node affinity` mostram que o problema é regra de posicionamento.

2. **Quanto o pod pede?**
   ```bash
   kubectl get deploy -n producao api -o jsonpath='{.spec.template.spec.containers[*].resources}'
   ```

3. **Quanto sobra em cada nó?**
   ```bash
   kubectl describe nodes | grep -A8 'Allocated resources'
   ```
   Compare os requests alocados com a capacidade de cada nó.

4. **Algum nó está fora do jogo?** Nós com `SchedulingDisabled` (cordon) não recebem pods. Às vezes um drain de manutenção não foi revertido.

## Correção

- Requests exagerados: reduza para o consumo real medido.
- Nó em cordon esquecido: `kubectl uncordon nome-do-no`.
- Cluster cheio de verdade: adicione nós (ou deixe o Cluster Autoscaler fazer isso, se estiver configurado).
- Prioridade: se for um serviço crítico, uma `PriorityClass` maior permite que ele desaloque pods menos importantes.

## Prevenção

- Revise os requests periodicamente com base em métricas.
- Use `ResourceQuota` por namespace, para um time não consumir o cluster inteiro.
- Configure o Cluster Autoscaler em ambientes de nuvem.
