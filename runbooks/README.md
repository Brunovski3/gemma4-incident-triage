# Runbooks de incidentes de infraestrutura

Manuais referenciados pelo modelo de triagem (campo `runbook` do JSON). Cada arquivo segue a mesma estrutura: **Resumo rápido**, **Como aparece nos logs**, **Diagnóstico**, **Correção** e **Prevenção**.

São rascunhos: revise os comandos e adapte ao seu ambiente (nomes de serviços, caminhos de volume, ferramentas de migração) antes de usar em produção.

| Componente | Incidente | Severidade |
|---|---|---|
| Traefik | [Backend indisponível (502)](traefik/backend-indisponivel.md) | ALTA |
| Traefik | [Timeout do backend (504)](traefik/timeout-backend.md) | MEDIA |
| Traefik | [Falha no certificado ACME](traefik/certificado-acme.md) | ALTA |
| Traefik | [Certificado expirado na CA interna](traefik/certificado-expirado.md) | ALTA |
| Traefik | [CA interna não confiável](traefik/ca-nao-confiavel.md) | ALTA |
| Traefik | [Middleware inexistente](traefik/middleware-inexistente.md) | MEDIA |
| Traefik | [Sem permissão RBAC no Kubernetes](traefik/rbac-sem-permissao.md) | ALTA |
| Docker | [Container OOMKilled](docker/oom-killed.md) | ALTA |
| Docker | [Porta em uso](docker/porta-em-uso.md) | MEDIA |
| Docker | [Disco cheio](docker/disco-cheio.md) | CRITICA |
| Docker | [Falha no pull da imagem](docker/falha-pull-imagem.md) | MEDIA |
| Docker | [Container unhealthy](docker/container-unhealthy.md) | ALTA |
| Docker Swarm | [Recursos insuficientes](swarm/recursos-insuficientes.md) | ALTA |
| Docker Swarm | [Nó indisponível](swarm/no-indisponivel.md) | ALTA |
| PostgreSQL | [Conexões esgotadas](postgres/conexoes-esgotadas.md) | ALTA |
| PostgreSQL | [Pool da aplicação esgotado](postgres/pool-esgotado.md) | ALTA |
| PostgreSQL | [Falha de autenticação](postgres/falha-autenticacao.md) | MEDIA |
| PostgreSQL | [Deadlock](postgres/deadlock.md) | MEDIA |
| PostgreSQL | [Conexão recusada](postgres/conexao-recusada.md) | CRITICA |
| PostgreSQL | [Tabela inexistente](postgres/relacao-inexistente.md) | MEDIA |
| PostgreSQL | [Disco cheio](postgres/disco-cheio.md) | CRITICA |
| PostgreSQL | [Database inexistente](postgres/banco-inexistente.md) | ALTA |
| Kubernetes | [CrashLoopBackOff](kubernetes/crashloopbackoff.md) | ALTA |
| Kubernetes | [ImagePullBackOff](kubernetes/image-pull-backoff.md) | ALTA |
| Kubernetes | [OOMKilled](kubernetes/oomkilled.md) | ALTA |
| Kubernetes | [Pending por recursos](kubernetes/pending-recursos.md) | ALTA |
| Kubernetes | [PVC não vinculado](kubernetes/pvc-nao-vinculado.md) | ALTA |
| Kubernetes | [Probe falhando](kubernetes/probe-falhando.md) | MEDIA |
| Kubernetes | [Nó NotReady](kubernetes/no-notready.md) | CRITICA |
| Authentik | [Redis indisponível](authentik/redis-indisponivel.md) | ALTA |
| Authentik | [Banco indisponível](authentik/banco-indisponivel.md) | CRITICA |
| Authentik | [Outpost sem provider](authentik/outpost-sem-provider.md) | MEDIA |
| Authentik | [SMTP indisponível](authentik/smtp-indisponivel.md) | MEDIA |
| Prometheus | [Configuração inválida](prometheus/config-invalida.md) | MEDIA |
