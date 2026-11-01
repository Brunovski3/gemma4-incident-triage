# Pod em CrashLoopBackOff

`k8s_crashloopbackoff` · **Componente:** Kubernetes / Pod · **Severidade:** ALTA

## Resumo rápido

O container sobe, morre logo em seguida e o Kubernetes tenta de novo, esperando cada vez mais entre as tentativas (10s, 20s, 40s... até 5 minutos). O CrashLoopBackOff não é a causa, é o sintoma: algo dentro do container está fazendo o processo sair. A resposta quase sempre está nos logs da execução **anterior**, a que morreu.

## Como aparece nos logs

- `kubectl get pods`: status `CrashLoopBackOff` com o contador de `RESTARTS` subindo.
- Evento: `Back-off restarting failed container api in pod api-xxx`
- kubelet: `Error syncing pod, skipping ... with CrashLoopBackOff: "back-off 5m0s restarting failed container=api ..."`
- Alertmanager: `KubePodCrashLooping`

## Diagnóstico

1. **Veja os logs da execução que morreu:**
   ```bash
   kubectl logs -n producao api-xxx --previous
   ```
   Sem o `--previous`, você vê o container novo, que provavelmente ainda não logou nada.

2. **Leia o código de saída:**
   ```bash
   kubectl describe pod -n producao api-xxx
   ```
   Em `Last State: Terminated`, olhe `Reason` e `Exit Code`:
   - `1` ou outro número baixo: erro da aplicação (exceção, configuração inválida).
   - `137`: morto por kill. Com `Reason: OOMKilled`, siga o runbook de OOMKilled.
   - `139`: segmentation fault.
   - `127`: comando não encontrado (erro no `command`/`entrypoint` ou na imagem).

3. **Causas mais comuns na prática:**
   - Variável de ambiente, ConfigMap ou Secret faltando (o app lê a configuração e aborta).
   - Dependência fora do ar na inicialização (banco, fila), e o app não sabe esperar.
   - Liveness probe matando o container antes de ele terminar de subir. Nesse caso os eventos mostram `Liveness probe failed` antes de cada reinício.

## Correção

- Erro de configuração: corrija o ConfigMap ou Secret e reinicie (`kubectl rollout restart deployment/api -n producao`).
- Imagem ou comando quebrado: volte para a versão anterior (`kubectl rollout undo deployment/api -n producao`) enquanto corrige.
- Probe agressiva: veja o runbook de probe falhando; use `startupProbe` para apps lentos.

## Prevenção

- Valide configurações no CI (o app deveria ter um modo "checar configuração e sair").
- Faça o app esperar as dependências com retry, em vez de morrer na primeira falha.
- Use deploys graduais: com `maxUnavailable: 0`, uma versão quebrada não derruba as réplicas antigas.
