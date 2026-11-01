# Nó do Swarm está Down

`swarm_no_indisponivel` · **Componente:** Docker Swarm / Nó · **Severidade:** ALTA

## Resumo rápido

Um nó parou de responder ao cluster. O Swarm tenta reagendar as tarefas dele em outros nós, mas só consegue se houver capacidade sobrando. Se o nó perdido for um **manager**, existe um risco extra: perder o quórum e travar o cluster inteiro.

## Como aparece nos logs

- No `docker node ls`: o nó aparece com `STATUS` `Down`.
- No `docker node inspect`: `"State": "down"` com `"Message": "heartbeat failure"`.
- No `docker service ps`: tarefas `Shutdown` com `Orphaned`, que estavam no nó perdido.

## Diagnóstico

1. **Qual nó e qual papel?**
   ```bash
   docker node ls
   ```
   A coluna `MANAGER STATUS` mostra se é manager. Se for, confira quantos managers sobraram: com 3 managers, dá para perder 1; com 2 restantes de 3, ainda há quórum; com só 1 de 3, o cluster para de aceitar mudanças.

2. **O servidor está vivo?** Tente o SSH. Se não responder, o problema é a máquina (desligou, travou, rede caiu), e a resolução passa pela nuvem ou pelo hypervisor.

3. **Se o SSH funciona, veja o Docker:**
   ```bash
   sudo systemctl status docker
   sudo journalctl -u docker --since "30 min ago" | tail -50
   df -h /var/lib/docker
   free -h
   ```
   Disco cheio e falta de memória são as causas mais comuns de um daemon travado.

4. **Rede entre os nós:** o Swarm precisa das portas 2377/tcp (gerência), 7946/tcp e udp (comunicação entre nós) e 4789/udp (rede overlay). Uma regra de firewall nova pode isolar o nó.

## Correção

- Daemon travado: `sudo systemctl restart docker`. Em geral o nó volta para `Ready` em alguns segundos.
- Disco ou memória: libere recursos (veja os runbooks de disco cheio e OOM) e reinicie o Docker.
- Firewall: libere as portas acima entre os nós.
- Máquina perdida de vez: remova o nó do cluster (`docker node rm --force nome`) e adicione uma máquina nova com o token de join.

## Prevenção

- Use 3 managers (ou 5 em clusters maiores). Um número ímpar garante o quórum.
- Mantenha folga de capacidade para absorver a perda de um nó sem deixar tarefas em Pending.
- Monitore disco, memória e o status dos nós, não só os serviços.
