# Probe falhando repetidamente

`k8s_probe_falhando` · **Componente:** Kubernetes / Healthcheck · **Severidade:** MEDIA

## Resumo rápido

O kubelet testa o container periodicamente. Se a **liveness** falha, ele reinicia o container. Se a **readiness** falha, ele tira o pod do balanceamento (o pod continua rodando, mas não recebe tráfego). Probe falhando sempre pode ser o app com problema de verdade, ou uma probe mal configurada derrubando um app saudável.

## Como aparece nos logs

- Evento `Unhealthy`: `Liveness probe failed: HTTP probe failed with statuscode: 503`, muitas vezes com `(x12 over 6m)`.
- `Readiness probe failed: Get "http://10.0.0.5:8080/ready": dial tcp ...: connect: connection refused`
- kubelet: `"Probe failed" probeType="Liveness" ... probeResult="failure"`
- O pod aparece `Running` mas com `READY 0/1`, ou com restarts subindo.

## Diagnóstico

1. **Qual probe e qual resposta?**
   ```bash
   kubectl describe pod -n producao api-xxx | sed -n '/Liveness\|Readiness/p;/Events/,$p'
   ```
   Veja a configuração (caminho, porta, `timeoutSeconds`, `periodSeconds`) e a mensagem do erro.

2. **Teste o endpoint por conta própria:**
   ```bash
   kubectl port-forward -n producao pod/api-xxx 8080:8080
   curl -i http://localhost:8080/health
   ```
   Se responde rápido e com 200, a probe é que está mal configurada.

3. **Pegadinhas comuns:**
   - `timeoutSeconds` padrão é **1 segundo**. Um endpoint que leva 1,2s sob carga falha a probe e reinicia o container justamente quando ele está mais ocupado.
   - Liveness testando dependências (banco, outra API): se o banco oscila, o Kubernetes reinicia todos os pods da aplicação ao mesmo tempo, o que piora tudo.
   - App lento para iniciar sem `startupProbe`: a liveness mata o container antes de ele terminar de subir.

## Correção

- Endpoint lento: aumente `timeoutSeconds` e `failureThreshold`.
- Inicialização lenta: adicione uma `startupProbe` com tolerância maior. A liveness só começa a valer depois que ela passa.
- Liveness dependente de terceiros: deixe a liveness verificar só o próprio processo; dependências ficam na readiness.
- Falha real: trate como incidente da aplicação e siga pelos logs.

## Prevenção

- Separe bem os papéis: liveness responde "o processo travou?", readiness responde "consigo atender agora?".
- Faça endpoints de health leves e rápidos.
- Reveja os valores de probe sempre que o tempo de inicialização da aplicação mudar.
