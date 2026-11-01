# Swarm sem nó com recursos para agendar o serviço

`swarm_recursos_insuficientes` · **Componente:** Docker Swarm / Scheduler · **Severidade:** ALTA

## Resumo rápido

O Swarm quer criar uma tarefa do serviço, mas nenhum nó tem a CPU ou a memória **reservadas** que o serviço pede. A tarefa fica parada em `Pending` para sempre. Um detalhe importante: o Swarm olha as **reservas** declaradas, não o uso real. Um nó pode estar ocioso e ainda assim "sem espaço" se as reservas de outros serviços já ocuparam tudo.

## Como aparece nos logs

- `no suitable node (insufficient resources on 3 nodes)`
- No `docker service ps`: tarefas em `Pending` há vários minutos.
- No deploy: `overall progress: 0 out of 3 tasks` travado.

## Diagnóstico

1. **Veja o erro completo das tarefas:**
   ```bash
   docker service ps --no-trunc nome-do-servico
   ```

2. **Quanto o serviço reserva?**
   ```bash
   docker service inspect nome-do-servico --format '{{json .Spec.TaskTemplate.Resources}}' | jq
   ```
   Uma reserva de 4 GB num cluster com nós de 4 GB nunca vai caber, porque sempre sobra um pouco para o sistema.

3. **Quantos nós estão disponíveis?**
   ```bash
   docker node ls
   ```
   Nós com `AVAILABILITY` em `Drain` ou `Pause` não recebem tarefas. Às vezes alguém drenou um nó para manutenção e esqueceu de reativar.

4. **Existe restrição de posicionamento?** Uma constraint como `node.labels.tipo == banco` limita onde o serviço pode rodar. Se só um nó tem essa label e ele está cheio, o serviço não sobe.

## Correção

- Reserva exagerada: diminua para o que o serviço realmente usa (`deploy.resources.reservations`).
- Nó drenado por engano: `docker node update --availability active nome-do-no`.
- Cluster realmente cheio: adicione um nó ou reduza o número de réplicas de algo menos importante.
- Constraint restritiva demais: rotule mais nós ou flexibilize a regra.

## Prevenção

- Defina reservas com base no consumo medido, não por estimativa.
- Acompanhe a soma das reservas contra a capacidade total do cluster e planeje crescimento antes de chegar no limite.
- Documente drenagens de manutenção e use um checklist para reativar o nó.
