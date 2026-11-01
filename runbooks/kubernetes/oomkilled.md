# Container OOMKilled no Kubernetes

`k8s_oomkilled` · **Componente:** Kubernetes / Memória · **Severidade:** ALTA

## Resumo rápido

O container passou do `limits.memory` e o kernel matou o processo (exit 137). O Kubernetes reinicia o container, e se isso se repete, o pod entra em CrashLoopBackOff. Não confunda com **eviction**: na eviction é o nó que está sem memória e o kubelet remove pods; no OOMKilled é o container que estourou o próprio limite.

## Como aparece nos logs

- `kubectl get pods`: status `OOMKilled` (por alguns instantes) e `RESTARTS` subindo.
- `kubectl describe pod`: `Last State: Terminated`, `Reason: OOMKilled`, `Exit Code: 137`.
- Alertmanager: `KubernetesContainerOomKiller`

## Diagnóstico

1. **Confirme o motivo e veja o limite:**
   ```bash
   kubectl describe pod -n producao api-xxx | grep -A6 -E 'Last State|Limits'
   ```

2. **Quanto ele usa normalmente?**
   ```bash
   kubectl top pod -n producao api-xxx --containers
   ```
   Se o uso normal já fica perto do limite, o limite está subdimensionado. Se o uso cresce aos poucos até estourar, é vazamento.

3. **Runtime respeita o limite?** Runtimes como JVM e Node têm a própria noção de memória máxima. Uma JVM configurada para usar 2 GB de heap dentro de um container com limite de 1 GB vai ser morta sempre.

## Correção

- Limite apertado: aumente o `limits.memory` (e ajuste o `requests.memory` para algo próximo, para o scheduler reservar o espaço de verdade).
- Runtime: alinhe com o limite do container (`-XX:MaxRAMPercentage=75` na JVM, `--max-old-space-size` no Node).
- Vazamento: aumentar o limite só ganha tempo. Investigue com profiling e, enquanto isso, mantenha réplicas suficientes para os reinícios não derrubarem o serviço.

## Prevenção

- Defina `requests` e `limits` de memória com base em consumo medido. O VPA em modo de recomendação ajuda a descobrir os valores.
- Alerte quando o uso passar de 80% do limite.
- Mantenha pelo menos 2 réplicas para serviços importantes, para um OOM não virar indisponibilidade.
