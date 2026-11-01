"""
Gerador v6 de dataset sintético: Agente de Triagem de Incidentes de infraestrutura
(Traefik, Docker/Swarm, Kubernetes, PostgreSQL, Authentik) -> JSON com severidade,
componente afetado, causa raiz e runbook (.md) recomendado.

v6: três classes vindas do chaos lab (database inexistente no PostgreSQL, Traefik sem
permissão RBAC no Kubernetes, Prometheus com configuração inválida), formatos reais do
Traefik v3 (caller) e do Authentik (timestamp epoch) e ruído de inicialização real.
Os logs reais do lab ficam só no teste (reais/teste_real.jsonl, gerado por preparar_reais.py).

v5 (correções sobre a v4):
  - Kubernetes e Authentik reescritos com formatos reais: kubectl get events/pods/nodes,
    describe, klog (kubelet, scheduler, controller), Alertmanager com o texto padrão
    do kube-prometheus e logs JSON (structlog) do Authentik.
  - Sem dicas embutidas nos logs: hard negatives não se "explicam" e as variantes
    inéditas (alertas) não repetem a causa raiz.
  - Bugs corrigidos: chaves duplas em ALERTS, JSON inválido no PVC, timestamp fixo no
    Celery, CrashLoopBackOff rotulado errado, motivo FailedMount em pull de imagem,
    "panic" no ruído normal.
  - Removido o split teste_livre (o modelo nunca vê a resposta de referência, então
    mudar a redação dela não media generalização). Os `fatos` agora alimentam a métrica
    de grounding da avaliação no notebook.
  - Mais dados (3.600 de treino) para 31 classes.

Saídas:
    data/treino.jsonl, data/teste.jsonl  -> {"conversations": [...], "meta": {...}}
    runbooks/<pasta>/<erro>.md           -> esqueletos dos manuais (não sobrescreve os existentes)
"""

import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

N_TREINO = 4000
N_TESTE = 300
PROP_SEM_ERRO = 0.15            # exemplos sem nenhum erro de infraestrutura
PROP_CASCATA = 0.6              # chance de cascata quando o erro permite
PROP_INEDITA_NO_TESTE = 0.5     # metade do teste usa formulações nunca vistas no treino

# Prefixo do link do runbook. Ajuste para o formato que o seu MCP Server expõe,
# ex.: "runbook://" ou "https://github.com/SEU_USUARIO/runbooks/blob/main/"
RUNBOOK_PREFIXO = "runbooks/"

# ---------------------------------------------------------------------------
# Prompt: o MESMO texto é usado no treino e na inferência
# ---------------------------------------------------------------------------
INSTRUCAO = (
    "Você é um agente de triagem de incidentes de infraestrutura "
    "(Traefik, Docker/Swarm, Kubernetes, PostgreSQL, Authentik). "
    "Considere apenas falhas de infraestrutura: avisos, erros de cliente (4xx) e erros de regra de negócio não contam. "
    "Se houver vários erros encadeados, aponte a causa raiz. "
    "Responda APENAS com um JSON com as chaves: severidade, componente_afetado, causa_raiz, runbook."
)


def montar_prompt(logs: str) -> str:
    return f"{INSTRUCAO}\n\nLogs:\n```\n{logs}\n```"


# ---------------------------------------------------------------------------
# Valores aleatórios
# ---------------------------------------------------------------------------
APPS = ["api", "web", "worker", "billing", "auth", "pedidos", "checkout"]
TABELAS = ["pedidos", "clientes", "pagamentos", "itens_pedido", "produtos"]
USER_AGENTS = ["Mozilla/5.0", "okhttp/4.12.0", "kube-probe/1.29", "curl/8.5.0", "python-requests/2.32"]


def hexid(n=12):
    return "".join(random.choice("0123456789abcdef") for _ in range(n))


def ip_interno():
    return f"172.{random.randint(16, 31)}.0.{random.randint(2, 30)}"


def ip_externo():
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


def dominio():
    return random.choice(["api", "app", "painel", "pedidos"]) + "." + random.choice(
        ["exemplo.com", "minhaempresa.com.br", "loja.dev"])


def caminho_http():
    return random.choice([
        f"/v1/pedidos/{random.randint(1, 9999)}", "/v1/usuarios/me", "/health", "/login",
        f"/v1/produtos?page={random.randint(1, 30)}", "/v1/checkout", "/metrics",
    ])


class Ctx:
    """Estado de um exemplo: relógio crescente e nomes coerentes entre as linhas."""

    def __init__(self):
        self.t = datetime(2026, random.randint(1, 12), random.randint(1, 28),
                          random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))
        self.app = random.choice(APPS)
        self.app_ip = ip_interno()
        self.db_ip = ip_interno()
        self.user = random.choice(["app", "api_user", "relatorios"])
        self.db = random.choice(["app", "loja", "producao"])
        self.pg_estilo = random.randrange(3)
        self.inicio = self.t
        self.uptime = random.uniform(10_000, 900_000)     # segundos desde o boot (dmesg)        # log_line_prefix diferente por "servidor"
        self.imagem = f"registry.{random.choice(['exemplo.com', 'interno.local'])}/{self.app}:" \
                      f"{random.randint(1, 3)}.{random.randint(0, 20)}.{random.randint(0, 9)}"
        self.dominio = dominio()
        self.porta = random.choice([80, 443, 5432, 8080, 3000, 6379])
        self.tabela = random.choice(TABELAS)
        self.mw = random.choice(["auth", "ratelimit", "cors", "redirect-https"])
        self.no = random.choice(["worker", "node", "swarm-worker", "docker"]) + f"-0{random.randint(1, 6)}"
        self.n_nos = random.randint(2, 5)
        # Contexto Kubernetes (nomes coerentes entre as linhas)
        self.ns = random.choice(NS_K8S)
        self.deploy = self.app
        self.pod = f"{self.deploy}-{hexid(5)}-{hexid(5)}"
        self.no_k8s = random.choice(["node", "worker", "pool", "k8s"]) + f"-{random.randint(1, 6)}"
        self.uid = f"{hexid(8)}-{hexid(4)}-{hexid(4)}-{hexid(4)}-{hexid(12)}"
        self.pvc = f"data-{self.app}-0"
        self.sc = random.choice(["local-path", "ebs-sc", "longhorn", "nfs-client"])
        # Classes vindas do chaos lab (v6)
        self.banco = random.choice(["authentik", "app", "loja", "keycloak", "grafana", "producao", "n8n"])
        self.sa = f"system:serviceaccount:{self.ns}:{random.choice(['default', 'traefik', 'ingress'])}"
        self.prom_cfg = random.choice(["/etc/prometheus/prometheus.yml", "/etc/prometheus/config/prometheus.yaml",
                                       "/config/prometheus.yml"])

    def _avanca(self):
        self.t += timedelta(microseconds=random.randint(5_000, 3_000_000))
        return self.t

    def iso(self):
        return self._avanca().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def v3(self):
        return self._avanca().strftime("%Y-%m-%dT%H:%M:%SZ")

    def clf(self):
        # Offset "+0000" fixo: o log do Traefik em produção já vem em UTC com esse
        # sufixo e não há informação de timezone no restante do dataset para variar.
        return self._avanca().strftime("%d/%b/%Y:%H:%M:%S +0000")

    def pg_ts(self):
        """Timestamp 'AAAA-MM-DD HH:MM:SS.mmm UTC' sem prefixo de log_line_prefix
        (para serviços que NÃO são o PostgreSQL, ex.: PgBouncer)."""
        t = self._avanca()
        return t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d} UTC"

    def k_ts(self):
        """Timestamp do kubectl/events: 'AAAA-MM-DDTHH:MM:SSZ' (segundos, sem microssegundos)."""
        return self._avanca().strftime("%Y-%m-%dT%H:%M:%SZ")

    def k_run(self):
        """Identificador de container runtime no formato kubectl (hex de 64)."""
        return hexid(64)

    def dmesg(self):
        t = self._avanca()
        return f"[{self.uptime + (t - self.inicio).total_seconds():.6f}]"

    def pid(self):
        return random.randint(30, 99999)

    def pg(self, nivel, msg, pid=None):
        t = self._avanca()
        ts = t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d} UTC"
        pid = pid or self.pid()
        if self.pg_estilo == 0:
            pre = f"{ts} [{pid}] "
        elif self.pg_estilo == 1:
            pre = f"{ts} [{pid}] {self.user}@{self.db} "
        else:
            pre = f"{ts} [{pid}]: [{random.randint(1, 9)}-1] user={self.user},db={self.db} "
        return ("db", f"{pre}{nivel}:  {msg}")


def acesso(c, status, alvo=None, dur=None):
    """Linha de access log do Traefik (formato CLF)."""
    return ("traefik",
            f'{ip_externo()} - - [{c.clf()}] "{random.choice(["GET", "POST", "PUT", "DELETE"])} {caminho_http()} '
            f'HTTP/{random.choice(["1.1", "2.0"])}" {status} {random.randint(0, 9000)} "-" "{random.choice(USER_AGENTS)}" '
            f'{random.randint(1, 99999)} "{c.app}@docker" "http://{alvo or c.app_ip}:8080" '
            f'{dur if dur is not None else random.randint(1, 400)}ms')


def t_logfmt(c, nivel, msg, **campos):
    extra = "".join(f' {k}="{v}"' if " " in str(v) or '"' in str(v) else f" {k}={v}" for k, v in campos.items())
    return ("traefik", f'time="{c.iso()}" level={nivel} msg="{msg}"{extra}')


def t_json(c, nivel, msg, **campos):
    d = {"level": nivel, **campos, "time": c.iso(), "message": msg}
    return ("traefik", json.dumps(d, ensure_ascii=False, separators=(",", ":")))


CALLERS_TRAEFIK = ["pkg/server/configurationwatcher.go", "pkg/proxy/httputil/proxy.go", "pkg/provider/acme/provider.go",
                   "pkg/server/router/router.go", "pkg/healthcheck/healthcheck.go", "pkg/provider/kubernetes/crd/kubernetes.go"]


def t_v3(c, nivel, msg, **campos):
    """Formato do console do Traefik v3: '<ts> NIV github.com/traefik/traefik/v3/<arquivo>:<linha> > msg k=v'."""
    extra = "".join(f' {k}="{v}"' if " " in str(v) else f" {k}={v}" for k, v in campos.items())
    caller = f"github.com/traefik/traefik/v3/{random.choice(CALLERS_TRAEFIK)}:{random.randint(40, 620)}"
    return ("traefik", f"{c.v3()} {nivel} {caller} > {msg}{extra}")


# ---------------------------------------------------------------------------
# Ruído: linhas normais e "hard negatives" (parecem erro, mas não são de infra)
# Cada função devolve (origem, texto). Origens: traefik, db, app, host
# ---------------------------------------------------------------------------
def ruido_traefik(c, dificil):
    if dificil:
        return random.choice([
            lambda: t_v3(c, "DBG", "No default certificate, fallback to the internal generated certificate",
                         tlsStoreName="default"),
            lambda: t_v3(c, "INF", "Stats collection is disabled."),
            lambda: acesso(c, random.choice([400, 401, 403, 404, 422, 429, 499])),
            lambda: t_logfmt(c, "error", "Error while Peeking first byte: read tcp 172.18.0.2:443->"
                             f"{ip_externo()}:{random.randint(1024, 65000)}: read: connection reset by peer"),
            lambda: t_v3(c, "DBG", f"http: TLS handshake error from {ip_externo()}:{random.randint(1024, 65000)}: EOF"),
            lambda: t_logfmt(c, "warning", f"Could not find network named 'proxy' for container '/{c.app}-1'. "
                             "Maybe you're missing the project's prefix in the label? Defaulting to first available network."),
            lambda: t_json(c, "warn", "Request rate limited", routerName=f"{c.app}@docker", clientIP=ip_externo()),
        ])()
    return random.choice([
        lambda: acesso(c, random.choice([200, 200, 200, 201, 204, 301, 304])),
        lambda: acesso(c, 200, dur=random.randint(1, 20)),
        lambda: t_logfmt(c, "info", "Configuration loaded from file: /etc/traefik/traefik.yml"),
        lambda: t_json(c, "debug", f"Adding route for {dominio()} with TLS options default", entryPointName="websecure"),
        lambda: t_v3(c, "INF", "Starting provider *docker.Provider"),
        lambda: t_v3(c, "INF", "Starting provider *crd.Provider"),
        lambda: t_v3(c, "INF", "Creating in-cluster Provider client", providerName="kubernetescrd"),
        lambda: t_v3(c, "DBG", "Starting TCP Server", entryPointName=random.choice(["web", "websecure", "traefik"])),
    ])()


def ruido_docker(c, dificil):
    if dificil:
        return random.choice([
            lambda: ("host", f'time="{c.iso()}" level=warning msg="Your kernel does not support swap limit '
                             f'capabilities or the cgroup is not mounted. Memory limited without swap."'),
            lambda: ("host", f"WARN[0000] /home/deploy/{c.app}/docker-compose.yml: the attribute `version` is "
                             "obsolete, it will be ignored, please remove it to avoid potential confusion"),
            lambda: ("host", f"migrate-1 exited with code 0"),
            lambda: ("host", f'time="{c.iso()}" level=warning msg="failed to retrieve runc version: '
                             f'unknown output format"'),
        ])()
    return random.choice([
        lambda: ("host", f'time="{c.iso()}" level=info msg="Container {hexid(64)} started" module=libcontainerd'),
        lambda: ("host", f" Container {c.app}-1  Started"),
        lambda: ("host", f" Container {c.app}-1  Running"),
        lambda: ("host", f'time="{c.iso()}" level=info msg="Loading containers: done."'),
    ])()


def ruido_app(c, dificil):
    if dificil:
        return random.choice([
            lambda: ("app", f"WARNING  Tentativa {random.randint(1, 3)}/3 falhou ao chamar o gateway de pagamento, "
                            f"repetindo em {random.randint(1, 5)}s"),
            lambda: ("app", f'ERROR  Validação falhou: campo "email" inválido (HTTP 422)'),
            lambda: ("app", f"ERROR [checkout] payment declined for order {random.randint(1000, 99999)} (card_declined)"),
            lambda: ("app", f"ERROR Login falhou para o usuário {random.randint(100, 9999)}: senha incorreta (401)"),
            lambda: ("app", f"WARN slow request {caminho_http()} took {random.randint(1500, 5000)}ms"),
        ])()
    return random.choice([
        lambda: ("app", f'INFO:     {ip_interno()}:{random.randint(30000, 60000)} - "GET /health HTTP/1.1" 200 OK'),
        lambda: ("app", f"[{c.iso()}] INFO Worker iniciado pid={random.randint(10, 999)}"),
        lambda: ("app", f"DEBUG cache hit key={hexid(8)}"),
        lambda: ("app", f"INFO pedido {random.randint(1000, 99999)} processado em {random.randint(5, 900)}ms"),
    ])()


def ruido_postgres(c, dificil):
    if dificil:
        t = random.choice(TABELAS)
        return random.choice([
            lambda: c.pg("LOG", f"duration: {random.uniform(1000, 9000):.3f} ms  statement: SELECT * FROM {t} "
                                f"WHERE criado_em > now() - interval '30 days'"),
            lambda: c.pg("WARNING", "there is already a transaction in progress"),
            lambda: c.pg("LOG", "could not receive data from client: Connection reset by peer"),
            lambda: c.pg("ERROR", f'duplicate key value violates unique constraint "{t}_pkey"'),
            lambda: c.pg("ERROR", "canceling statement due to user request"),
            lambda: ("db", 'initdb: warning: enabling "trust" authentication for local connections'),
            lambda: c.pg("LOG", "received fast shutdown request"),
            lambda: c.pg("LOG", 'background worker "logical replication launcher" (PID 54) exited with exit code 1'),
        ])()
    return random.choice([
        lambda: c.pg("LOG", "checkpoint starting: time"),
        lambda: c.pg("LOG", f"checkpoint complete: wrote {random.randint(1, 900)} buffers "
                            f"({random.random():.1f}%); 0 WAL file(s) added"),
        lambda: c.pg("LOG", "database system is ready to accept connections"),
        lambda: c.pg("LOG", f'automatic vacuum of table "{c.db}.public.{random.choice(TABELAS)}"'),
        lambda: c.pg("LOG", f"connection authorized: user={c.user} database={c.db} application_name={c.app}"),
        lambda: ("db", random.choice(["creating subdirectories ... ok", "running bootstrap script ... ok",
                                      "PostgreSQL init process complete; ready for start up."])),
        lambda: c.pg("LOG", 'listening on IPv4 address "0.0.0.0", port 5432'),
    ])()


def ruido(c, foco, p_dificil):
    servico = foco if random.random() < 0.6 else random.choice(list(RUIDOS))
    origem, texto = RUIDOS[servico](c, random.random() < p_dificil)
    sorteio = random.random()
    if sorteio < 0.04:
        return ("host", "")                                              # linha vazia
    if sorteio < 0.10:
        return (origem, texto[: random.randint(15, max(16, len(texto)))])  # linha cortada
    return (origem, texto)


# ---------------------------------------------------------------------------
# Erros: cada variante devolve (linhas, evidencia). A ÚLTIMA variante é exclusiva do teste.
# Todas as variantes de um erro mostram os dados citados na causa raiz (domínio, app, porta...).
# ---------------------------------------------------------------------------
def agora_e_validade(c):
    exp = c.t - timedelta(days=random.randint(1, 40))
    return c.t.strftime("%Y-%m-%dT%H:%M:%SZ"), exp.strftime("%Y-%m-%dT%H:%M:%SZ")


# ----- Traefik
def t502_a(c):
    l1 = acesso(c, 502, dur=random.randint(0, 3))
    l2 = t_logfmt(c, "error", "502 Bad Gateway error", error=f"dial tcp {c.app_ip}:8080: connect: connection refused")
    return [l1, l2]


def t502_b(c):
    l1 = t_json(c, "error", "502 Bad Gateway error", error=f"dial tcp {c.app_ip}:8080: connect: connection refused")
    return [l1, acesso(c, 502, dur=1)]


def t502_inedita(c):
    l1 = acesso(c, 502, dur=random.randint(1, 5))
    l2 = t_v3(c, "ERR", "502 Bad Gateway", error=f"dial tcp {c.app_ip}:8080: connect: no route to host")
    return [l1, l2]


def t504_a(c):
    l1 = acesso(c, 504, dur=30000 + random.randint(0, 9))
    l2 = t_logfmt(c, "error", "504 Gateway Timeout error", error="net/http: timeout awaiting response headers")
    return [l1, l2]


def t504_b(c):
    l1 = t_json(c, "error", "504 Gateway Timeout error", routerName=f"{c.app}@docker",
                error="net/http: timeout awaiting response headers")
    return [l1]


def t504_inedita(c):
    l1 = acesso(c, 504, dur=60000 + random.randint(0, 9))
    l2 = t_v3(c, "ERR", "504 Gateway Timeout", error=f"read tcp 172.18.0.2:{random.randint(30000, 60000)}->"
                                                      f"{c.app_ip}:8080: i/o timeout")
    return [l1, l2]


def acme_a(c):
    l1 = t_logfmt(c, "error", f'Unable to obtain ACME certificate for domains \\"{c.dominio}\\"',
                  providerName="letsencrypt.acme",
                  error="acme: error: 429 :: POST :: https://acme-v02.api.letsencrypt.org/acme/new-order :: "
                        "urn:ietf:params:acme:error:rateLimited :: too many certificates already issued")
    return [l1]


def acme_b(c):
    l1 = t_json(c, "error", f'Unable to obtain ACME certificate for domains "{c.dominio}"', providerName="letsencrypt.acme",
                error=f"acme: error: 400 :: urn:ietf:params:acme:error:connection :: {c.dominio}: Timeout during "
                      "connect (likely firewall problem)")
    return [l1]


def acme_inedita(c):
    d = c.dominio
    l1 = t_v3(c, "ERR", "Unable to obtain ACME certificate for domains", providerName="letsencrypt.acme",
              error=f"unable to generate a certificate for the domains [{d}]: error: one or more domains had a "
                    f"problem:\\n[{d}] invalid authorization: acme: error: 403 :: urn:ietf:params:acme:error:unauthorized "
                    f":: Invalid response from http://{d}/.well-known/acme-challenge/{hexid(20)}: 404")
    return [l1]


def cert_exp_a(c):
    agora, exp = agora_e_validade(c)
    l1 = t_logfmt(c, "error", f"Error calling https://{c.dominio}/verify", middlewareType="ForwardAuth",
                  error=f'Get \\"https://{c.dominio}/verify\\": tls: failed to verify certificate: x509: certificate has '
                        f"expired or is not yet valid: current time {agora} is after {exp}")
    return [l1, acesso(c, 500)]


def cert_exp_b(c):
    agora, exp = agora_e_validade(c)
    l1 = acesso(c, 500)
    l2 = t_json(c, "error", "500 Internal Server Error", url=f"https://{c.dominio}:8443",
                error=f"tls: failed to verify certificate: x509: certificate has expired or is not yet valid: "
                      f"current time {agora} is after {exp}")
    return [l1, l2]


def cert_exp_inedita(c):
    agora, exp = agora_e_validade(c)
    l1 = t_v3(c, "ERR", "Health check failed.", targetURL=f"https://{c.dominio}:8443/health",
              error=f'Get "https://{c.dominio}:8443/health": x509: certificate has expired or is not yet valid: '
                    f"current time {agora} is after {exp}")
    return [l1]


def ca_a(c):
    l1 = t_logfmt(c, "error", f"Error calling https://{c.dominio}/verify", middlewareType="ForwardAuth",
                  error=f'Get \\"https://{c.dominio}/verify\\": tls: failed to verify certificate: x509: certificate '
                        "signed by unknown authority")
    return [l1, acesso(c, 500)]


def ca_b(c):
    l1 = acesso(c, 500)
    l2 = t_json(c, "error", "500 Internal Server Error", url=f"https://{c.dominio}:8443",
                error="tls: failed to verify certificate: x509: certificate signed by unknown authority")
    return [l1, l2]


def ca_inedita(c):
    l1 = t_v3(c, "ERR", "500 Internal Server Error", url=f"https://{c.dominio}:8443",
              error='tls: failed to verify certificate: x509: certificate signed by unknown authority (possibly '
                    'because of "crypto/rsa: verification error" while trying to verify candidate authority '
                    'certificate "CA Interna")')
    return [l1]


def mw_a(c):
    l1 = t_json(c, "error", "", entryPointName="websecure", routerName=f"{c.app}@docker",
                error=f'middleware "{c.mw}@docker" does not exist')
    return [l1]


def mw_b(c):
    l1 = t_logfmt(c, "error", f'middleware \\"{c.mw}@docker\\" does not exist', entryPointName="websecure",
                  routerName=f"{c.app}@docker")
    return [l1]


def mw_inedita(c):
    l1 = ("traefik", f'{c.v3()} ERR error="middleware \\"{c.mw}@file\\" does not exist" '
                     f"entryPointName=web routerName={c.app}@docker")
    return [l1]


# ----- Docker
def oom_a(c):
    proc = random.choice(["node", "python", "java", "gunicorn"])
    l1 = ("host", f"{c.dmesg()} Out of memory: Killed process {c.pid()} ({proc}) "
                  f"total-vm:{random.randint(2, 9)}000000kB, anon-rss:{random.randint(1, 4)}000000kB")
    l2 = ("host", f"{c.app}-1 exited with code 137")
    return [l1, l2]


def oom_b(c):
    linhas = [("host", f'"Name": "/{c.app}-1",'), ("host", '"State": {'), ("host", '    "Status": "exited",'),
              ("host", '    "OOMKilled": true,'), ("host", '    "ExitCode": 137,')]
    return linhas


def oom_inedita(c):
    proc = random.choice(["node", "python", "java"])
    l1 = ("host", f"{c.dmesg()} Memory cgroup out of memory: Killed process {c.pid()} ({proc}) "
                  f"total-vm:{random.randint(2, 9)}000000kB, oom_score_adj:0")
    l2 = ("host", f"{c.app}-1 exited with code 137")
    return [l1, l2]


def porta_a(c):
    l0 = ("host", f" Container {c.app}-1  Starting")
    l1 = ("host", f"Error response from daemon: driver failed programming external connectivity on endpoint "
                  f"{c.app}-1 ({hexid(64)}): Bind for 0.0.0.0:{c.porta} failed: port is already allocated")
    return [l0, l1]


def porta_b(c):
    l0 = ("host", f" Container {c.app}-1  Starting")
    l1 = ("host", f"Error response from daemon: Ports are not available: exposing port TCP 0.0.0.0:{c.porta} -> "
                  f"0.0.0.0:0: listen tcp 0.0.0.0:{c.porta}: bind: address already in use")
    return [l0, l1]


def porta_inedita(c):
    l1 = ("host", f"Error response from daemon: driver failed programming external connectivity on endpoint "
                  f"{c.app}-1: Error starting userland proxy: listen tcp4 0.0.0.0:{c.porta}: bind: address already in use")
    return [l1]


def disco_docker_a(c):
    l1 = ("host", f"failed to register layer: write /var/lib/docker/overlay2/{hexid(64)}/diff/usr/lib/"
                  f"{hexid(6)}.so: no space left on device")
    return [l1]


def disco_docker_b(c):
    h = hexid(64)
    l1 = ("host", f"Error response from daemon: write /var/lib/docker/containers/{h}/{h}-json.log: no space left on device")
    return [l1]


def disco_docker_inedita(c):
    h = hexid(25)
    l1 = ("host", f"ERROR: failed to solve: failed to prepare {h} as {hexid(25)}: mkdir "
                  f"/var/lib/docker/overlay2/{h}-init: no space left on device")
    return [l1]


def pull_a(c):
    l0 = ("host", f" {c.app} Pulling")
    l1 = ("host", f"Error response from daemon: manifest for {c.imagem} not found: manifest unknown: manifest unknown")
    return [l0, l1]


def pull_b(c):
    l1 = ("host", f"Error response from daemon: pull access denied for {c.imagem.split(':')[0]}, repository does "
                  f"not exist or may require 'docker login': denied: requested access to the resource is denied")
    return [l1]


def pull_inedita(c):
    repo, tag = c.imagem.split(":")
    host, nome = repo.split("/", 1)
    l1 = ("host", f'Error response from daemon: Head "https://{host}/v2/{nome}/manifests/{tag}": '
                  "unauthorized: authentication required")
    return [l1]


def unhealthy_a(c):
    linhas = [("host", f" Container {c.app}-1  Waiting"), ("host", f" Container {c.app}-1  Error"),
              ("host", f"dependency failed to start: container {c.app}-1 is unhealthy")]
    return linhas


def unhealthy_b(c):
    l1 = ("host", f"{c.iso()} container health_status: unhealthy {hexid(64)} (image={c.imagem}, name={c.app}-1)")
    return [l1]


def unhealthy_inedita(c):
    l1 = ("host", f'{hexid(12)}   {c.imagem}   "python app.py"   {random.randint(2, 50)} minutes ago   '
                  f"Up {random.randint(2, 50)} minutes (unhealthy)   0.0.0.0:8080->8080/tcp   {c.app}-1")
    return [l1]


# ----- Docker Swarm
def swarm_rec_a(c):
    l1 = ("host", f"{hexid(12)}   {c.app}.{random.randint(1, 3)}   {c.imagem}            Running   Pending "
                  f"{random.randint(1, 9)} minutes ago   \"no suitable node (insufficient resources on {c.n_nos} nodes)\"")
    return [l1]


def swarm_rec_b(c):
    l1 = ("host", f'time="{c.iso()}" level=warning msg="task {c.app}.{random.randint(1, 3)} could not be scheduled: '
                  f'no suitable node (insufficient resources on {c.n_nos} nodes)" module=scheduler')
    return [l1]


def swarm_rec_inedita(c):
    total = random.randint(2, 4)
    linhas = [("host", f"{c.app}"), ("host", f"overall progress: 0 out of {total} tasks"),
              ("host", f"1/{total}: no suitable node (insufficient resources on {c.n_nos} nodes)")]
    return linhas


def swarm_no_a(c):
    l1 = ("host", f"{hexid(25)}     {c.no}   Down      Active                          26.1.{random.randint(0, 5)}")
    return [l1]


def swarm_no_b(c):
    linhas = [("host", f'        "Hostname": "{c.no}",'), ("host", '    "Status": {'),
              ("host", '        "State": "down",'), ("host", '        "Message": "heartbeat failure",')]
    return linhas


def swarm_no_inedita(c):
    l1 = ("host", f"{hexid(12)}    \\_ {c.app}.{random.randint(1, 3)}   {c.imagem}   {c.no}   Shutdown   "
                  f"Orphaned {random.randint(1, 9)} minutes ago")
    return [l1]


# ----- PostgreSQL
def conexoes_a(c):
    l1 = c.pg("FATAL", "sorry, too many clients already")
    return [l1]


def conexoes_b(c):
    l1 = c.pg("FATAL", "remaining connection slots are reserved for non-replication superuser connections")
    return [l1]


def conexoes_inedita(c):
    l1 = c.pg("FATAL", "desculpe, muitos clientes conectados")
    return [l1]


def pool_a(c):
    l1 = ("app", f"sqlalchemy.exc.TimeoutError: QueuePool limit of size {random.choice([5, 10, 20])} overflow "
                 f"{random.choice([10, 20])} reached, connection timed out, timeout 30.00 "
                 "(Background on this error at: https://sqlalche.me/e/20/3o7r)")
    return [l1]


def pool_b(c):
    total = random.choice([10, 20, 30])
    l1 = ("app", f"java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, request "
                 f"timed out after 30000ms (total={total}, active={total}, idle=0, waiting={random.randint(5, 80)})")
    return [l1]


def pool_inedita(c):
    l1 = ("db", f"{c.pg_ts()} [{c.pid()}] WARNING C-0x{hexid(12)}: (nodb)/(nouser)@{c.app_ip}:"
                f"{random.randint(30000, 60000)} pooler error: no more connections allowed (max_client_conn)")
    return [l1]


def auth_a(c):
    pid = c.pid()
    l1 = c.pg("FATAL", f'password authentication failed for user "{c.user}"', pid)
    l2 = c.pg("DETAIL", f'Connection matched pg_hba.conf line {random.randint(80, 120)}: '
                        f'"host all all all scram-sha-256"', pid)
    return [l1, l2]


def auth_b(c):
    l1 = c.pg("FATAL", f'no pg_hba.conf entry for host "{c.app_ip}", user "{c.user}", database "{c.db}", no encryption')
    return [l1]


def auth_inedita(c):
    l1 = ("app", f'org.postgresql.util.PSQLException: FATAL: password authentication failed for user "{c.user}"')
    l2 = ("app", "\tat org.postgresql.core.v3.ConnectionFactoryImpl.doAuthentication(ConnectionFactoryImpl.java:693)")
    return [l1, l2]


def deadlock_a(c):
    pid = c.pid()
    l1 = c.pg("ERROR", "deadlock detected", pid)
    l2 = c.pg("DETAIL", f"Process {pid} waits for ShareLock on transaction {random.randint(10000, 99999)}; "
                        f"blocked by process {c.pid()}.", pid)
    l3 = c.pg("HINT", "See server log for query details.", pid)
    return [l1, l2, l3]


def deadlock_b(c):
    l1 = ("app", "psycopg2.errors.DeadlockDetected: deadlock detected")
    l2 = ("app", f"DETAIL:  Process {c.pid()} waits for ShareLock on transaction {random.randint(10000, 99999)}; "
                 f"blocked by process {c.pid()}.")
    return [l1, l2]


def deadlock_inedita(c):
    pid = c.pid()
    l1 = c.pg("ERRO", "impasse detectado", pid)
    l2 = c.pg("DETALHE", f"Processo {pid} espera por ShareLock na transação {random.randint(10000, 99999)}; "
                         f"bloqueado pelo processo {c.pid()}.", pid)
    return [l1, l2]


def recusada_a(c):
    l1 = ("app", "Traceback (most recent call last):")
    l2 = ("app", '  File "/app/db.py", line 42, in conectar')
    l3 = ("app", f'psycopg2.OperationalError: connection to server at "db" ({c.db_ip}), port 5432 failed: '
                 "Connection refused")
    l4 = ("app", "\tIs the server running on that host and accepting TCP/IP connections?")
    return [l1, l2, l3, l4]


def recusada_b(c):
    l1 = ("app", f"Error: connect ECONNREFUSED {c.db_ip}:5432")
    l2 = ("app", "    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1555:16)")
    return [l1, l2]


def recusada_inedita(c):
    l1 = ("app", "org.postgresql.util.PSQLException: Connection to db:5432 refused. Check that the hostname and port "
                 "are correct and that the postmaster is accepting TCP/IP connections.")
    return [l1]


def relacao_a(c):
    pid = c.pid()
    l1 = c.pg("ERROR", f'relation "{c.tabela}" does not exist at character {random.randint(14, 40)}', pid)
    l2 = c.pg("STATEMENT", f"SELECT * FROM {c.tabela} WHERE id = ${random.randint(1, 3)}", pid)
    return [l1, l2]


def relacao_b(c):
    l1 = ("app", f'sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedTable) relation "{c.tabela}" does not exist')
    return [l1]


def relacao_inedita(c):
    l1 = ("app", f"Invalid `prisma.{c.tabela}.findMany()` invocation:")
    l2 = ("app", f"The table `public.{c.tabela}` does not exist in the current database.")
    return [l1, l2]


def disco_pg_a(c):
    l1 = c.pg("PANIC", f'could not write to file "pg_wal/xlogtemp.{c.pid()}": No space left on device')
    return [l1]


def disco_pg_b(c):
    l1 = c.pg("ERROR", f'could not write to file "base/pgsql_tmp/pgsql_tmp{c.pid()}.0": No space left on device')
    return [l1]


def disco_pg_inedita(c):
    pid = c.pid()
    l1 = c.pg("ERROR", f'could not extend file "base/16384/{random.randint(1000, 99999)}": No space left on device', pid)
    l2 = c.pg("HINT", "Check free disk space.", pid)
    return [l1, l2]


# ---------------------------------------------------------------------------
# Kubernetes: formatos reais (kubectl get events/pods/nodes, describe, klog do
# kubelet/scheduler/controller e notificações do Alertmanager com o texto padrão
# do kube-prometheus). A ÚLTIMA variante de cada erro é exclusiva do teste.
# ---------------------------------------------------------------------------
NS_K8S = ["producao", "app", "pagamentos", "default", "api"]


def k_idade():
    return random.choice([f"{random.randint(5, 59)}s", f"{random.randint(1, 59)}m", f"{random.randint(1, 23)}h"])


def evento(tipo, motivo, objeto, msg):
    """Linha de `kubectl get events`: LAST SEEN, TYPE, REASON, OBJECT, MESSAGE."""
    return ("host", f"{k_idade():<7} {tipo:<8} {motivo:<20} {objeto:<38} {msg}")


def linha_pod(nome, ready, status, restarts, idade):
    """Linha de `kubectl get pods`: NAME, READY, STATUS, RESTARTS, AGE."""
    return ("host", f"{nome:<34} {ready:<6} {status:<18} {restarts:<9} {idade}")


def klog(c, nivel, arquivo, msg):
    """Formato klog (kubelet, kube-scheduler, kube-controller-manager)."""
    t = c._avanca()
    return ("host", f"{nivel}{t.strftime('%m%d %H:%M:%S.%f')} {random.randint(1, 9999):>7} {arquivo}] {msg}")


def alerta(nome, rotulo, descricao, severidade="warning"):
    """Notificação do Alertmanager (cabeçalho + descrição da regra)."""
    return [("host", f"[FIRING:1] {nome} ({rotulo} {severidade})"),
            ("host", f"description: {descricao}")]


def k8s_ruido(c, dificil):
    """Hard negatives: Job Completed, nó em drain (SchedulingDisabled), pod sendo
    trocado num rollout e o aviso do HPA sem métricas no startup NÃO são incidente."""
    if dificil:
        return random.choice([
            lambda: linha_pod(f"backup-{random.randint(28000000, 28999999)}-{hexid(5)}", "0/1", "Completed", "0",
                              f"{random.randint(1, 59)}m"),
            lambda: evento("Normal", "ScalingReplicaSet", f"deployment/{c.deploy}",
                           f"Scaled up replica set {c.deploy}-{hexid(10)} to {random.randint(2, 6)}"),
            lambda: evento("Normal", "NodeNotSchedulable", f"node/{c.no_k8s}",
                           f"Node {c.no_k8s} status is now: NodeNotSchedulable"),
            lambda: evento("Normal", "Killing", f"pod/{c.deploy}-{hexid(10)}-{hexid(5)}", f"Stopping container {c.app}"),
            lambda: evento("Warning", "FailedGetResourceMetric", f"horizontalpodautoscaler/{c.deploy}",
                           "failed to get cpu utilization: unable to get metrics for resource cpu: "
                           "no metrics returned from resource metrics API"),
        ])()
    return random.choice([
        lambda: evento("Normal", "Scheduled", f"pod/{c.pod}", f"Successfully assigned {c.ns}/{c.pod} to {c.no_k8s}"),
        lambda: evento("Normal", "Pulled", f"pod/{c.pod}", f'Container image "{c.imagem}" already present on machine'),
        lambda: evento("Normal", "Started", f"pod/{c.pod}", f"Started container {c.app}"),
        lambda: linha_pod(c.pod, "1/1", "Running", "0", f"{random.randint(1, 90)}d"),
        lambda: ("host", f'deployment "{c.deploy}" successfully rolled out'),
    ])()


# ---------------------------------------------------------------------------
# Authentik: logs JSON (structlog) do server/worker e dos outposts em Go
# ---------------------------------------------------------------------------
USUARIOS_SSO = ["admin", "maria", "joao", "ana.souza", "svc-ci"]


def ak(c, level, logger, event, **extra):
    """Log JSON do Authentik (structlog): event, level, logger, timestamp em epoch e depois os extras."""
    d = {"event": event, "level": level, "logger": logger, "timestamp": c._avanca().timestamp(), **extra}
    return ("authentik", json.dumps(d, ensure_ascii=False))


def authentik_ruido(c, dificil):
    """Hard negatives de SSO: senha errada, política negando acesso e client OAuth
    inválido são problema de usuário/configuração de app, não de infraestrutura."""
    if dificil:
        return random.choice([
            lambda: ak(c, "warning", "authentik.stages.password.stage", "Invalid credentials",
                       username=random.choice(USUARIOS_SSO)),
            lambda: ak(c, "info", "authentik.policies.engine", "Policy denied access",
                       user=random.choice(USUARIOS_SSO), application=c.app),
            lambda: ak(c, "warning", "authentik.providers.oauth2.views.token", "invalid_client",
                       client_id=hexid(40)),
            lambda: ak(c, "info", "authentik.asgi", "/application/o/token/", method="POST", status=401,
                       host=c.dominio, runtime=random.randint(5, 90)),
        ])()
    return random.choice([
        lambda: ak(c, "info", "authentik.asgi", "/api/v3/outposts/instances/", method="GET", status=200,
                   host=c.dominio, runtime=random.randint(5, 90)),
        lambda: ak(c, "info", "authentik.root.celery", "Task finished",
                   task_name=random.choice(["outpost_controller", "clean_expired_models", "blueprints_discovery"]),
                   state="SUCCESS"),
        lambda: ak(c, "info", "authentik.stages.user_login.stage", "Successful login",
                   user=random.choice(USUARIOS_SSO)),
    ])()


def prom(c, nivel, msg, caller="main.go", **campos):
    """Log do Prometheus 2.x em logfmt."""
    extra = "".join(f' {k}="{v}"' if " " in str(v) else f" {k}={v}" for k, v in campos.items())
    ts = c._avanca().strftime("%Y-%m-%dT%H:%M:%S.") + f"{c.t.microsecond // 1000:03d}Z"
    return ("prometheus", f'ts={ts} caller={caller}:{random.randint(100, 1300)} level={nivel} msg="{msg}"{extra}')


def ruido_prometheus(c, dificil):
    """Hard negatives: cliente que fechou a conexão e alvo lento no scrape não derrubam o Prometheus."""
    if dificil:
        return random.choice([
            lambda: prom(c, "warn", "Error writing response", caller="web.go", component="web", err="write: broken pipe"),
            lambda: prom(c, "warn", "Error on ingesting out-of-order samples", caller="scrape.go",
                         component="scrape manager", num_dropped=random.randint(1, 40)),
        ])()
    return random.choice([
        lambda: prom(c, "info", "Server is ready to receive web requests."),
        lambda: prom(c, "info", "TSDB started"),
        lambda: prom(c, "info", "Completed loading of configuration file", filename=c.prom_cfg,
                     totalDuration=f"{random.uniform(0.5, 9):.3f}ms"),
        lambda: prom(c, "info", "Starting rule manager...", caller="manager.go", component="rule manager"),
        lambda: prom(c, "info", "Head GC completed", caller="head.go", component="tsdb",
                     duration=f"{random.uniform(1, 30):.3f}ms"),
    ])()


RUIDOS = {"traefik": ruido_traefik, "docker": ruido_docker, "app": ruido_app, "prometheus": ruido_prometheus,
          "postgres": ruido_postgres, "k8s": k8s_ruido, "authentik": authentik_ruido}


# ----- k8s: CrashLoopBackOff
def k8s_crash_a(c):
    return [linha_pod(c.pod, "0/1", "CrashLoopBackOff", str(random.randint(3, 40)), f"{random.randint(5, 90)}m"),
            evento("Warning", "BackOff", f"pod/{c.pod}",
                   f"Back-off restarting failed container {c.app} in pod {c.pod}_{c.ns}({c.uid})")]


def k8s_crash_b(c):
    espera = random.choice(["40s", "1m20s", "2m40s", "5m0s"])
    return [klog(c, "E", "pod_workers.go:1298",
                 f'"Error syncing pod, skipping" err="failed to \\"StartContainer\\" for \\"{c.app}\\" with '
                 f'CrashLoopBackOff: \\"back-off {espera} restarting failed container={c.app} '
                 f'pod={c.pod}_{c.ns}({c.uid})\\"" pod="{c.ns}/{c.pod}" podUID="{c.uid}"')]


def k8s_crash_inedita(c):
    return alerta("KubePodCrashLooping", f"{c.ns}/{c.pod}",
                  f'Pod {c.ns}/{c.pod} ({c.app}) is in waiting state (reason: "CrashLoopBackOff").')


# ----- k8s: ImagePullBackOff
def k8s_pull_a(c):
    return [evento("Warning", "Failed", f"pod/{c.pod}",
                   f'Failed to pull image "{c.imagem}": rpc error: code = NotFound desc = failed to pull and unpack '
                   f'image "{c.imagem}": failed to resolve reference "{c.imagem}": {c.imagem}: not found'),
            linha_pod(c.pod, "0/1", "ImagePullBackOff", "0", f"{random.randint(1, 30)}m")]


def k8s_pull_b(c):
    return [klog(c, "E", "pod_workers.go:1298",
                 f'"Error syncing pod, skipping" err="failed to \\"StartContainer\\" for \\"{c.app}\\" with '
                 f'ImagePullBackOff: \\"Back-off pulling image {c.imagem}\\"" pod="{c.ns}/{c.pod}" podUID="{c.uid}"')]


def k8s_pull_inedita(c):
    return alerta("KubeContainerWaiting", f"{c.ns}/{c.pod}",
                  f"pod/{c.pod} in namespace {c.ns} on container {c.app} has been in waiting state for longer "
                  f'than 1 hour. (reason: "ImagePullBackOff").')


# ----- k8s: OOMKilled
def k8s_oom_a(c):
    n = random.randint(1, 20)
    status = {"name": c.app, "lastState": {"terminated": {"exitCode": 137, "reason": "OOMKilled",
                                                          "finishedAt": c.k_ts()}}, "restartCount": n}
    return [linha_pod(c.pod, "0/1", "OOMKilled", str(n), f"{random.randint(2, 60)}m"),
            ("host", json.dumps(status, separators=(",", ":")))]


def k8s_oom_b(c):
    return [("host", f"Name:             {c.pod}"), ("host", f"Namespace:        {c.ns}"), ("host", "Containers:"),
            ("host", f"  {c.app}:"), ("host", "    State:          Running"),
            ("host", "    Last State:     Terminated"), ("host", "      Reason:       OOMKilled"),
            ("host", "      Exit Code:    137")]


def k8s_oom_inedita(c):
    return alerta("KubernetesContainerOomKiller", f"{c.ns}/{c.pod}",
                  f"Container {c.app} in pod {c.ns}/{c.pod} has been OOMKilled {random.randint(1, 6)} times "
                  "in the last 10 minutes.")


# ----- k8s: Pending por falta de recursos
def k8s_pending_a(c):
    n = c.n_nos
    return [evento("Warning", "FailedScheduling", f"pod/{c.pod}",
                   f"0/{n} nodes are available: {n} Insufficient cpu. preemption: 0/{n} nodes are available: "
                   f"{n} No preemption victims found for incoming pod."),
            linha_pod(c.pod, "0/1", "Pending", "0", f"{random.randint(1, 40)}m")]


def k8s_pending_b(c):
    n, r = c.n_nos, random.randint(2, 5)
    return [("host", f"{c.deploy:<20} 0/{r}     {r}            0           {random.randint(5, 59)}m"),
            evento("Warning", "FailedScheduling", f"pod/{c.pod}",
                   f"0/{n} nodes are available: {n} Insufficient memory. preemption: 0/{n} nodes are available: "
                   f"{n} No preemption victims found for incoming pod.")]


def k8s_pending_inedita(c):
    n = c.n_nos
    return [klog(c, "I", "schedule_one.go:1004",
                 f'"Unable to schedule pod; no fit; waiting" pod="{c.ns}/{c.pod}" err="0/{n} nodes are available: '
                 f"{n} Insufficient memory, {n} Insufficient cpu. preemption: 0/{n} nodes are available: "
                 f'{n} No preemption victims found for incoming pod."')]


# ----- k8s: PVC não vinculado
def k8s_pvc_a(c):
    n = c.n_nos
    return [evento("Warning", "FailedScheduling", f"pod/{c.pod}",
                   f"0/{n} nodes are available: pod has unbound immediate PersistentVolumeClaims. preemption: "
                   f"0/{n} nodes are available: {n} Preemption is not helpful for scheduling."),
            ("host", f"{c.pvc:<26} Pending                                      {c.sc:<12} {random.randint(1, 59)}m")]


def k8s_pvc_b(c):
    return [evento("Warning", "ProvisioningFailed", f"persistentvolumeclaim/{c.pvc}",
                   f'storageclass.storage.k8s.io "{c.sc}" not found')]


def k8s_pvc_inedita(c):
    return [klog(c, "E", "pv_controller.go:1578",
                 f'"Error provisioning volume" PVC="{c.ns}/{c.pvc}" err="failed to provision volume with '
                 f'StorageClass \\"{c.sc}\\": rpc error: code = ResourceExhausted desc = volume quota exceeded"')]


# ----- k8s: probe falhando
def k8s_probe_a(c):
    k = random.randint(5, 40)
    return [linha_pod(c.pod, "0/1", "Running", str(random.randint(1, 9)), f"{random.randint(10, 90)}m"),
            ("host", f"  Warning  Unhealthy  {random.randint(1, 9)}m (x{k} over {k // 2 + 1}m)  kubelet  "
                     "Liveness probe failed: HTTP probe failed with statuscode: 503")]


def k8s_probe_b(c):
    return [evento("Warning", "Unhealthy", f"pod/{c.pod}",
                   f'Readiness probe failed: Get "http://{c.app_ip}:8080/ready": dial tcp {c.app_ip}:8080: '
                   "connect: connection refused")]


def k8s_probe_inedita(c):
    return [klog(c, "I", "prober.go:107",
                 f'"Probe failed" probeType="Liveness" pod="{c.ns}/{c.pod}" podUID="{c.uid}" '
                 f'containerName="{c.app}" probeResult="failure" output="HTTP probe failed with statuscode: 500"')]


# ----- k8s: nó NotReady
def k8s_no_a(c):
    return [("host", f"{c.no_k8s:<14} NotReady   <none>   {random.randint(10, 400)}d   v1.29.{random.randint(1, 9)}"),
            evento("Normal", "NodeNotReady", f"node/{c.no_k8s}", f"Node {c.no_k8s} status is now: NodeNotReady")]


def k8s_no_b(c):
    return [("host", f"Name:               {c.no_k8s}"), ("host", "Conditions:"),
            ("host", "  Type             Status    Reason              Message"),
            ("host", "  MemoryPressure   Unknown   NodeStatusUnknown   Kubelet stopped posting node status."),
            ("host", "  Ready            Unknown   NodeStatusUnknown   Kubelet stopped posting node status.")]


def k8s_no_inedita(c):
    return alerta("KubeNodeNotReady", c.no_k8s, f"{c.no_k8s} has been unready for more than 15 minutes.")


# ----- Authentik: Redis
def ak_redis_a(c):
    return [ak(c, "info", "authentik.lifecycle.wait_for_db", "Redis Connection failed, retrying...",
               redis_error="Error 111 connecting to redis:6379. Connection refused.")]


def ak_redis_b(c):
    return [("authentik", '  File "/authentik/root/celery.py", line 64, in worker_ready'),
            ("authentik", "redis.exceptions.ConnectionError: Error 111 connecting to redis:6379. Connection refused.")]


def ak_redis_inedita(c):
    ts = c._avanca().strftime("%Y-%m-%d %H:%M:%S,") + f"{c.t.microsecond // 1000:03d}"
    return [("authentik", f"[{ts}: ERROR/MainProcess] consumer: Cannot connect to redis://redis:6379/0: "
                          "Error 111 connecting to redis:6379. Connection refused.."),
            ("authentik", f"Trying again in {random.choice(['2.00', '4.00', '6.00'])} seconds... "
                          f"({random.randint(1, 9)}/100)")]


# ----- Authentik: banco
def ak_db_a(c):
    return [ak(c, "info", "authentik.lifecycle.wait_for_db",
               f'PostgreSQL connection failed, retrying... (connection to server at "postgresql" ({c.db_ip}), '
               "port 5432 failed: Connection refused)")]


def ak_db_b(c):
    return [("authentik", '  File "/authentik/root/db/base.py", line 13, in get_new_connection'),
            ("authentik", f'django.db.utils.OperationalError: connection failed: connection to server at '
                          f'"{c.db_ip}", port 5432 failed: Connection refused')]


def ak_db_inedita(c):
    return [("authentik", "Traceback (most recent call last):"),
            ("authentik", '  File "/authentik/lifecycle/migrate.py", line 98, in run_migrations'),
            ("authentik", f'psycopg.OperationalError: connection failed: connection to server at "{c.db_ip}", '
                          "port 5432 failed: could not receive data from server: Connection refused")]


# ----- Authentik: outpost sem provider
def ak_outpost_a(c):
    return [ak(c, "warning", "authentik.outpost.proxyv2",
               "No providers assigned to this outpost, check outpost configuration")]


def ak_outpost_b(c):
    return [ak(c, "error", "authentik.outpost.proxyv2", "Failed to get provider",
               provider=f"{c.app}-proxy", error="404 Not Found")]


def ak_outpost_inedita(c):
    return [ak(c, "warning", "authentik.outpost.proxyv2", "No provider found for host", host=c.dominio)]


# ----- Authentik: SMTP
def ak_smtp_a(c):
    return [ak(c, "warning", "authentik.stages.email.tasks", "Failed to send email",
               error="[Errno 111] Connection refused")]


def ak_smtp_b(c):
    return [ak(c, "warning", "authentik.stages.email.tasks", "Failed to send email", error="timed out")]


def ak_smtp_inedita(c):
    return [("authentik", '  File "/authentik/stages/email/tasks.py", line 109, in send_mail'),
            ("authentik", "smtplib.SMTPServerDisconnected: Connection unexpectedly closed")]


# ---------------------------------------------------------------------------
# Classes vindas do chaos lab (v6). Inspiradas nos incidentes reais, mas com nomes,
# versões e formulações diferentes: os logs reais ficam só no teste (reais/teste_real.jsonl).
# ---------------------------------------------------------------------------
# ----- PostgreSQL: database não existe
def banco_inex_a(c):
    return [c.pg("FATAL", f'database "{c.banco}" does not exist') for _ in range(random.randint(2, 5))]


def banco_inex_b(c):
    return random.choice([
        lambda: [("app", f'django.db.utils.OperationalError: connection failed: connection to server at '
                         f'"{c.db_ip}", port 5432 failed: FATAL:  database "{c.banco}" does not exist')],
        lambda: [("app", f'error: database "{c.banco}" does not exist'),
                 ("app", "    at Parser.parseErrorMessage (/app/node_modules/pg-protocol/dist/parser.js:287:98)")],
        lambda: [("app", f'org.postgresql.util.PSQLException: FATAL: database "{c.banco}" does not exist')],
    ])()


def banco_inex_inedita(c):
    return [c.pg("FATAL", f'banco de dados "{c.banco}" não existe') for _ in range(random.randint(2, 4))]


# ----- Traefik: provider Kubernetes sem permissão (RBAC)
RECURSOS_RBAC = [("v1", "Service", "services", '""'), ("v1", "Endpoints", "endpoints", '""'),
                 ("v1", "Secret", "secrets", '""'), ("v1", "Ingress", "ingresses", '"networking.k8s.io"'),
                 ("v1alpha1", "IngressRoute", "ingressroutes", '"traefik.io"'),
                 ("v1alpha1", "Middleware", "middlewares", '"traefik.io"'),
                 ("v1alpha1", "TLSOption", "tlsoptions", '"traefik.io"')]


def rbac_a(c):
    """klog do client-go embutido no Traefik (formato real), com recursos e versões variados."""
    v = f"v0.{random.randint(26, 31)}.{random.randint(0, 9)}"
    linhas = []
    for ver, kind, plural, grupo in random.sample(RECURSOS_RBAC, random.randint(2, 4)):
        recurso = f"{plural}.{grupo.strip(chr(34))}" if grupo != '""' else plural
        msg = (f'{recurso} is forbidden: User "{c.sa}" cannot list resource "{plural}" in API group {grupo} '
               "at the cluster scope")
        linhas.append(klog(c, "W", "reflector.go:539", f"k8s.io/client-go@{v}/tools/cache/reflector.go:229: "
                                                       f"failed to list *{ver}.{kind}: {msg}"))
    return [(("traefik",) + l[1:]) for l in linhas]


def rbac_b(c):
    """Traefik v2 (logfmt) falhando ao iniciar o provider Kubernetes Ingress."""
    return [t_logfmt(c, "error", "Error while starting provider", providerName="kubernetes",
                     error=f'ingresses.networking.k8s.io is forbidden: User \\"{c.sa}\\" cannot list resource '
                           f'\\"ingresses\\" in API group \\"networking.k8s.io\\" at the cluster scope')]


def rbac_inedita(c):
    return [("host", f"$ kubectl auth can-i list ingressroutes.traefik.io --as={c.sa}"), ("host", "no"),
            ("host", f"$ kubectl auth can-i watch services --as={c.sa} -A"), ("host", "no")]


# ----- Prometheus: configuração inválida
ERROS_YAML = ['yaml: line {n}: did not find expected key', 'not a valid duration string: \\"{d}\\"',
              'yaml: unmarshal errors:\\n  line {n}: field scrape_intervall not found in type config.ScrapeConfig']


def prom_cfg_a(c):
    err = random.choice(ERROS_YAML).format(n=random.randint(3, 60), d=random.choice(["15", "1 minute", "30seg"]))
    return [prom(c, "error", f"Error loading config (--config.file={c.prom_cfg})", file=c.prom_cfg,
                 err=f"parsing YAML file {c.prom_cfg}: {err}")]


def prom_cfg_b(c):
    job = random.choice(["node", "traefik", "postgres", "kubernetes-pods"])
    return [prom(c, "error", "Error reloading config", caller="main.go",
                 err=f'couldn\'t load configuration (--config.file=\\"{c.prom_cfg}\\"): parsing YAML file {c.prom_cfg}: '
                     f'scrape timeout greater than scrape interval for scrape config with job name \\"{job}\\"')]


def prom_cfg_inedita(c):
    ts = c._avanca().strftime("%Y-%m-%dT%H:%M:%S.") + f"{c.t.microsecond // 1000:03d}Z"
    return [("prometheus", f'time={ts} level=ERROR source=main.go:{random.randint(500, 700)} '
                           f'msg="Error loading config (--config.file={c.prom_cfg})" file={c.prom_cfg} '
                           f'err="parsing YAML file {c.prom_cfg}: unknown fields in scrape_config: scrape_intervall"')]


# ---------------------------------------------------------------------------
# Catálogo: código -> severidade, componente, causa raiz (template com dados do log), variantes
# ---------------------------------------------------------------------------
def erro(pasta, foco, severidade, componente, causa, *variantes):
    return {"pasta": pasta, "foco": foco, "severidade": severidade, "componente": componente,
            "causa": causa, "variantes": list(variantes)}


CATALOGO = {
    "traefik_backend_indisponivel": erro("traefik", "traefik", "ALTA", "Traefik / Upstream",
        "Backend {app} ({app_ip}:8080) inacessível: o Traefik não consegue abrir conexão com o serviço.",
        t502_a, t502_b, t502_inedita),
    "traefik_timeout_backend": erro("traefik", "traefik", "MEDIA", "Traefik / Upstream",
        "Backend {app} não respondeu dentro do tempo limite do Traefik.", t504_a, t504_b, t504_inedita),
    "traefik_certificado_acme": erro("traefik", "traefik", "ALTA", "Traefik / ACME",
        "Traefik não conseguiu emitir o certificado TLS de {dominio} via ACME/Let's Encrypt.",
        acme_a, acme_b, acme_inedita),
    "traefik_certificado_expirado": erro("traefik", "traefik", "ALTA", "Traefik / PKI",
        "Certificado TLS de {dominio} expirado na CA interna.", cert_exp_a, cert_exp_b, cert_exp_inedita),
    "traefik_ca_nao_confiavel": erro("traefik", "traefik", "ALTA", "Traefik / PKI",
        "Certificado de {dominio} assinado por uma CA que o Traefik não reconhece (CA interna fora do trust store).",
        ca_a, ca_b, ca_inedita),
    "traefik_middleware_inexistente": erro("traefik", "traefik", "MEDIA", "Traefik / Roteamento",
        "Router {app}@docker referencia o middleware {mw}, que não existe.", mw_a, mw_b, mw_inedita),
    "docker_oom_killed": erro("docker", "docker", "ALTA", "Docker / Container",
        "Container {app} excedeu o limite de memória e foi encerrado pelo kernel (OOMKilled, exit 137).",
        oom_a, oom_b, oom_inedita),
    "docker_porta_em_uso": erro("docker", "docker", "MEDIA", "Docker / Rede",
        "Porta {porta} do host já está ocupada; o container {app} não conseguiu publicá-la.",
        porta_a, porta_b, porta_inedita),
    "docker_disco_cheio": erro("docker", "docker", "CRITICA", "Docker / Armazenamento",
        "Disco do host cheio em /var/lib/docker.", disco_docker_a, disco_docker_b, disco_docker_inedita),
    "docker_falha_pull_imagem": erro("docker", "docker", "MEDIA", "Docker / Registry",
        "Falha ao baixar a imagem de {app} do registry (tag inexistente ou falta de autenticação).",
        pull_a, pull_b, pull_inedita),
    "docker_container_unhealthy": erro("docker", "docker", "ALTA", "Docker / Healthcheck",
        "Container {app} falhou no healthcheck e ficou unhealthy.", unhealthy_a, unhealthy_b, unhealthy_inedita),
    "swarm_recursos_insuficientes": erro("swarm", "docker", "ALTA", "Docker Swarm / Scheduler",
        "Nenhum nó do Swarm tem CPU/memória livre para agendar o serviço {app}.",
        swarm_rec_a, swarm_rec_b, swarm_rec_inedita),
    "swarm_no_indisponivel": erro("swarm", "docker", "ALTA", "Docker Swarm / Nó",
        "Nó {no} do Swarm está Down; as tarefas dele precisam ser reagendadas.",
        swarm_no_a, swarm_no_b, swarm_no_inedita),
    "postgres_conexoes_esgotadas": erro("postgres", "postgres", "ALTA", "PostgreSQL / Conexões",
        "PostgreSQL atingiu max_connections e está recusando novas conexões.", conexoes_a, conexoes_b, conexoes_inedita),
    "postgres_pool_esgotado": erro("postgres", "app", "ALTA", "PostgreSQL / Pool de conexões",
        "Pool de conexões esgotado: requisições esperam por conexão livre até dar timeout.", pool_a, pool_b, pool_inedita),
    "postgres_falha_autenticacao": erro("postgres", "postgres", "MEDIA", "PostgreSQL / Autenticação",
        "Falha de autenticação do usuário {user} no PostgreSQL (senha ou regra do pg_hba.conf).",
        auth_a, auth_b, auth_inedita),
    "postgres_deadlock": erro("postgres", "postgres", "MEDIA", "PostgreSQL / Transações",
        "Deadlock entre transações concorrentes no PostgreSQL.", deadlock_a, deadlock_b, deadlock_inedita),
    "postgres_conexao_recusada": erro("postgres", "app", "CRITICA", "PostgreSQL / Disponibilidade",
        "Aplicação não consegue abrir conexão com o PostgreSQL na porta 5432 (serviço fora do ar ou rede).",
        recusada_a, recusada_b, recusada_inedita),
    "postgres_relacao_inexistente": erro("postgres", "postgres", "MEDIA", "PostgreSQL / Schema",
        "Tabela {tabela} não existe no banco (migração pendente ou schema errado).",
        relacao_a, relacao_b, relacao_inedita),
    "postgres_disco_cheio": erro("postgres", "postgres", "CRITICA", "PostgreSQL / Armazenamento",
        "Disco do PostgreSQL cheio: o banco não consegue gravar dados nem WAL.", disco_pg_a, disco_pg_b, disco_pg_inedita),
    # ----- Kubernetes
    "k8s_crashloopbackoff": erro("kubernetes", "k8s", "ALTA", "Kubernetes / Pod",
        "Container {app} do pod {pod} entra em CrashLoopBackOff (sai logo após subir e reinicia em backoff).",
        k8s_crash_a, k8s_crash_b, k8s_crash_inedita),
    "k8s_image_pull_backoff": erro("kubernetes", "k8s", "ALTA", "Kubernetes / Registry",
        "Pod {pod} em ImagePullBackOff: não foi possível baixar a imagem do container {app} (tag inexistente, registry inacessível ou credencial ausente).",
        k8s_pull_a, k8s_pull_b, k8s_pull_inedita),
    "k8s_oomkilled": erro("kubernetes", "k8s", "ALTA", "Kubernetes / Memória",
        "Container {app} do pod {pod} excedeu o limite de memória e foi morto pelo kernel (OOMKilled, exit 137).",
        k8s_oom_a, k8s_oom_b, k8s_oom_inedita),
    "k8s_pending_recursos": erro("kubernetes", "k8s", "ALTA", "Kubernetes / Scheduler",
        "Pods de {deploy} ficam Pending: nenhum nó tem CPU/memória livre (Insufficient cpu/memory).",
        k8s_pending_a, k8s_pending_b, k8s_pending_inedita),
    "k8s_pvc_nao_vinculado": erro("kubernetes", "k8s", "ALTA", "Kubernetes / Armazenamento",
        "PVC {pvc} está Pending: o StorageClass {sc} não provisionou um PersistentVolume para o pod vincular.",
        k8s_pvc_a, k8s_pvc_b, k8s_pvc_inedita),
    "k8s_probe_falhando": erro("kubernetes", "k8s", "MEDIA", "Kubernetes / Healthcheck",
        "Probe do pod {pod} falha repetidamente; o kubelet reinicia o container ou tira o pod do balanceamento.",
        k8s_probe_a, k8s_probe_b, k8s_probe_inedita),
    "k8s_no_notready": erro("kubernetes", "k8s", "CRITICA", "Kubernetes / Nó",
        "Nó {no_k8s} está NotReady (parou de reportar ao control-plane); pods precisam ser reagendados.",
        k8s_no_a, k8s_no_b, k8s_no_inedita),
    # ----- Authentik
    "authentik_redis_indisponivel": erro("authentik", "authentik", "ALTA", "Authentik / Cache",
        "Authentik não consegue se conectar ao Redis (sessões, cache e fila do Celery dependem dele).",
        ak_redis_a, ak_redis_b, ak_redis_inedita),
    "authentik_banco_indisponivel": erro("authentik", "authentik", "CRITICA", "Authentik / Banco de dados",
        "Authentik não consegue abrir conexão com o PostgreSQL (autenticação e configuração dependem dele).",
        ak_db_a, ak_db_b, ak_db_inedita),
    "authentik_outpost_sem_provider": erro("authentik", "authentik", "MEDIA", "Authentik / Outpost",
        "Outpost do Authentik não encontra o provider configurado (404 na API); proxy não sobe.",
        ak_outpost_a, ak_outpost_b, ak_outpost_inedita),
    # ----- Vindas do chaos lab (v6)
    "postgres_banco_inexistente": erro("postgres", "postgres", "ALTA", "PostgreSQL / Banco de dados",
        "O database {banco} não existe no PostgreSQL: o servidor está no ar, mas o banco não foi criado "
        "(POSTGRES_DB ou script de inicialização).", banco_inex_a, banco_inex_b, banco_inex_inedita),
    "traefik_rbac_sem_permissao": erro("traefik", "traefik", "ALTA", "Traefik / Provider Kubernetes",
        "A ServiceAccount {sa} do Traefik não tem permissão (RBAC) para listar recursos do cluster; "
        "o provider Kubernetes não consegue descobrir as rotas.", rbac_a, rbac_b, rbac_inedita),
    "prometheus_config_invalida": erro("prometheus", "prometheus", "MEDIA", "Prometheus / Configuração",
        "Prometheus não conseguiu carregar {prom_cfg}: o YAML tem erro de sintaxe ou validação e a "
        "configuração nova não foi aplicada.", prom_cfg_a, prom_cfg_b, prom_cfg_inedita),
    "authentik_smtp_indisponivel": erro("authentik", "authentik", "MEDIA", "Authentik / E-mail",
        "Authentik não consegue enviar e-mails pelo SMTP (recuperação de senha e validação falham).",
        ak_smtp_a, ak_smtp_b, ak_smtp_inedita),
}

# ---------------------------------------------------------------------------
# Cascatas: consequências que aparecem DEPOIS da causa raiz (o rótulo continua sendo a raiz)
# ---------------------------------------------------------------------------
def cons_app_recusa(c):
    return recusada_a(c)


def cons_traefik_502(c):
    return t502_a(c)


def cons_traefik_504(c):
    return t504_a(c)


def cons_traefik_500(c):
    return [acesso(c, 500) for _ in range(random.randint(1, 3))]


def cons_unhealthy(c):
    return unhealthy_a(c)


def cons_app_too_many(c):
    return [("app", f'sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "db" '
                    f"({c.db_ip}), port 5432 failed: FATAL:  sorry, too many clients already")]


def cons_k8s_503(c):
    """Pod fora do serviço -> Traefik balanceia para endpoint morto."""
    return [acesso(c, 503) for _ in range(random.randint(1, 2))]


def cons_k8s_taint_eviction(c):
    """Nó NotReady -> o controller marca os pods do nó para remoção."""
    return [evento("Normal", "TaintManagerEviction", f"pod/{c.pod}", f"Marking for deletion Pod {c.ns}/{c.pod}")]


def cons_k8s_backoff(c):
    """Reinícios em sequência -> BackOff (consequência, não a raiz)."""
    return [evento("Warning", "BackOff", f"pod/{c.pod}",
                   f"Back-off restarting failed container {c.app} in pod {c.pod}_{c.ns}({c.uid})")]


def cons_authentik_502(c):
    """Outpost sem provider -> login quebra -> 502 no Traefik."""
    return t502_a(c)


def cons_ak_banco_inexistente(c):
    return [ak(c, "info", "authentik.lib.config", "PostgreSQL connection failed, retrying... (connection failed: "
               f'FATAL:  database "{c.banco}" does not exist)') for _ in range(random.randint(1, 3))]


CASCATAS = {
    "postgres_banco_inexistente": [cons_ak_banco_inexistente, cons_k8s_backoff],
    "postgres_disco_cheio": [cons_app_recusa, cons_traefik_502],
    "docker_oom_killed": [cons_traefik_502, cons_unhealthy],
    "postgres_conexoes_esgotadas": [cons_app_too_many, cons_traefik_500],
    "postgres_pool_esgotado": [cons_traefik_504],
    "postgres_falha_autenticacao": [cons_unhealthy],
    "postgres_relacao_inexistente": [cons_traefik_500],
    "swarm_no_indisponivel": [cons_traefik_502],
    "k8s_oomkilled": [cons_k8s_backoff, cons_k8s_503],
    "k8s_probe_falhando": [cons_k8s_backoff, cons_k8s_503],
    "k8s_no_notready": [cons_k8s_taint_eviction, cons_k8s_503],
    "k8s_crashloopbackoff": [cons_k8s_503],
    "authentik_outpost_sem_provider": [cons_authentik_502],
    "authentik_banco_indisponivel": [cons_authentik_502],
}

# ---------------------------------------------------------------------------
# Renderização: prefixos do docker compose e cores ANSI em TODAS as linhas
# ---------------------------------------------------------------------------
RE_NIVEL = re.compile(r"\b(INFO|INF|WARN(?:ING)?|WRN|ERROR|ERRO|ERR|FATAL|PANIC|DEBUG|DBG|LOG|DETAIL|DETALHE|HINT)\b")
RE_LEVEL = re.compile(r"level=(\w+)")
COR_NIVEL = {"INFO": "32", "INF": "32", "LOG": "32", "DEBUG": "90", "DBG": "90", "WARN": "33", "WARNING": "33",
             "WRN": "33", "DETAIL": "36", "DETALHE": "36", "HINT": "36"}


def cor(texto, codigo):
    return f"\x1b[{codigo}m{texto}\x1b[0m"


def colorir_nivel(texto):
    texto = RE_LEVEL.sub(lambda m: "level=" + cor(m.group(1), COR_NIVEL.get(m.group(1).upper(), "31")), texto, count=1)
    return RE_NIVEL.sub(lambda m: cor(m.group(1), COR_NIVEL.get(m.group(1), "31")), texto, count=1)


def renderizar(c, linhas):
    modo_compose = random.random() < 0.5
    colorido = random.random() < (0.6 if modo_compose else 0.2)
    nomes = {"traefik": "traefik", "db": random.choice(["db", "postgres"]), "app": c.app,
             "authentik": random.choice(["authentik-server", "authentik-worker"]), "prometheus": "prometheus"}
    cores = dict(zip(nomes, random.sample(["36", "33", "32", "35", "34", "31"], len(nomes))))
    largura = max(len(n) for n in nomes.values()) + 2

    saida = []
    for origem, texto in linhas:
        if colorido and texto:
            texto = colorir_nivel(texto)
        if modo_compose and origem in nomes:
            prefixo = f"{nomes[origem]}-1".ljust(largura) + " | "
            texto = (cor(prefixo, cores[origem]) if colorido else prefixo) + texto
        saida.append(texto)
    return "\n".join(saida)


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------
def arquivo_runbook(codigo):
    pasta = CATALOGO[codigo]["pasta"]
    prefixo = {"kubernetes": "k8s_"}.get(pasta, f"{pasta}_")
    return f"{pasta}/{codigo.removeprefix(prefixo).replace('_', '-')}.md"


def link_runbook(codigo):
    return RUNBOOK_PREFIXO + arquivo_runbook(codigo)


# ---------------------------------------------------------------------------
# Fatos: para cada código, quais atributos do Ctx aparecem NO LOG (as variantes
# os citam). `checar()` usa isto para garantir que todo dado citado na causa
# raiz realmente existe no log do exemplo.
# ---------------------------------------------------------------------------
FATOS = {
    "traefik_backend_indisponivel": {"app": "{app}", "ip": "{app_ip}"},
    "traefik_timeout_backend": {"app": "{app}"},
    "traefik_certificado_acme": {"dominio": "{dominio}"},
    "traefik_certificado_expirado": {"dominio": "{dominio}"},
    "traefik_ca_nao_confiavel": {"dominio": "{dominio}"},
    "traefik_middleware_inexistente": {"middleware": "{mw}", "app": "{app}"},
    "docker_oom_killed": {"container": "{app}"},
    "docker_porta_em_uso": {"porta": "{porta}", "container": "{app}"},
    "docker_disco_cheio": {},
    "docker_falha_pull_imagem": {"container": "{app}"},
    "docker_container_unhealthy": {"container": "{app}"},
    "swarm_recursos_insuficientes": {"servico": "{app}"},
    "swarm_no_indisponivel": {"no": "{no}"},
    "postgres_conexoes_esgotadas": {},
    "postgres_pool_esgotado": {},
    "postgres_falha_autenticacao": {"usuario": "{user}"},
    "postgres_deadlock": {},
    "postgres_conexao_recusada": {},
    "postgres_relacao_inexistente": {"tabela": "{tabela}"},
    "postgres_disco_cheio": {},
    "k8s_crashloopbackoff": {"pod": "{pod}", "container": "{app}"},
    "k8s_image_pull_backoff": {"pod": "{pod}", "container": "{app}"},
    "k8s_oomkilled": {"pod": "{pod}", "container": "{app}"},
    "k8s_pending_recursos": {"deployment": "{deploy}"},
    "k8s_pvc_nao_vinculado": {"pvc": "{pvc}", "storageclass": "{sc}"},
    "k8s_probe_falhando": {"pod": "{pod}"},
    "k8s_no_notready": {"no": "{no_k8s}"},
    "authentik_redis_indisponivel": {},
    "authentik_banco_indisponivel": {},
    "authentik_outpost_sem_provider": {},
    "authentik_smtp_indisponivel": {},
    "postgres_banco_inexistente": {"banco": "{banco}"},
    "traefik_rbac_sem_permissao": {"serviceaccount": "{sa}"},
    "prometheus_config_invalida": {"arquivo": "{prom_cfg}"},
}


def checar(caminhos, limite=None):
    """Teste automatizado do dataset: para cada exemplo com erro, todo fato citado
    na causa raiz precisa aparecer no log E na resposta. Devolve (erros, checados)."""
    checados = erros = 0
    for caminho in caminhos:
        with open(caminho, encoding="utf-8") as f:
            for num, linha in enumerate(f, 1):
                ex = json.loads(linha)
                meta = ex["meta"]
                if not meta["codigo"]:
                    continue
                log = re.sub(r"\x1b\[[0-9;]*m", "", ex["conversations"][0]["content"])
                resp = json.loads(ex["conversations"][1]["content"])
                causa = resp["causa_raiz"]
                checados += 1
                for nome, valor in meta["fatos"].items():
                    if valor not in causa:
                        erros += 1
                        print(f"[FALTA NA CAUSA] {caminho.name}:{num} {meta['codigo']}: {nome}={valor}")
                    elif valor not in log:
                        erros += 1
                        print(f"[FALTA NO LOG] {caminho.name}:{num} {meta['codigo']}: {nome}={valor}")
                if limite and erros >= limite:
                    return erros, checados
    return erros, checados


SEM_ERRO = {"severidade": "NENHUMA", "componente_afetado": None,
            "causa_raiz": "Nenhuma falha de infraestrutura encontrada nos logs.", "runbook": None}


def gerar_exemplo(split):
    c = Ctx()
    meta = {"codigo": None, "variante": None, "cascata": False, "fatos": {}}

    if random.random() < PROP_SEM_ERRO:
        foco = random.choice(list(RUIDOS))
        linhas = [ruido(c, foco, p_dificil=0.45) for _ in range(random.randint(6, 22))]
        resposta = dict(SEM_ERRO)
    else:
        codigo = random.choice(list(CATALOGO))
        info = CATALOGO[codigo]
        if split == "teste" and random.random() < PROP_INEDITA_NO_TESTE:
            variante, meta["variante"] = info["variantes"][-1], "inedita"
        else:
            variante, meta["variante"] = random.choice(info["variantes"][:-1]), "vista"
        meta["codigo"] = codigo

        linhas = [ruido(c, info["foco"], 0.25) for _ in range(random.randint(3, 12))]
        linhas_erro = variante(c)
        linhas += linhas_erro

        # Cascata só com variantes vistas, para não "entregar" a resposta das inéditas
        if codigo in CASCATAS and meta["variante"] == "vista" and random.random() < PROP_CASCATA:
            meta["cascata"] = True
            for consequencia in CASCATAS[codigo]:
                linhas += [ruido(c, info["foco"], 0.25) for _ in range(random.randint(0, 3))]
                linhas += consequencia(c)

        linhas += [ruido(c, info["foco"], 0.25) for _ in range(random.randint(0, 8))]
        causa = info["causa"].format(**vars(c))
        resposta = {
            "severidade": info["severidade"],
            "componente_afetado": info["componente"],
            "causa_raiz": causa,
            "runbook": link_runbook(codigo),
        }
        # Fatos do log citados na causa raiz: usados pelo teste automatizado (`checar`)
        # e pela métrica de grounding do notebook (a causa raiz do MODELO cita esses valores?).
        fatos = {k: v for k, v in FATOS.get(codigo, {}).items() if v}
        meta["fatos"] = {k: v.format(**vars(c)) if isinstance(v, str) else v for k, v in fatos.items()}

    return {
        "conversations": [
            {"role": "user", "content": montar_prompt(renderizar(c, linhas))},
            {"role": "assistant", "content": json.dumps(resposta, ensure_ascii=False)},
        ],
        "meta": meta,
    }


def salvar(caminho, n, split, seed, ja_vistos=None):
    """Gera `n` exemplos com dedup: nenhum prompt se repete DENTRO do arquivo nem
    entre arquivos do mesmo `ja_vistos` (treino e teste sem colisões)."""
    random.seed(seed)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    ja_vistos = ja_vistos if ja_vistos is not None else set()
    gerados = 0
    tentativas = 0
    with caminho.open("w", encoding="utf-8") as f:
        while gerados < n:
            tentativas += 1
            assert tentativas < n * 50, f"dedup travou em {caminho} ({gerados}/{n})"
            ex = gerar_exemplo(split)
            chave = ex["conversations"][0]["content"]
            if chave in ja_vistos:
                continue
            ja_vistos.add(chave)
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
            gerados += 1
    print(f"{n} exemplos -> {caminho} (dedup: {tentativas} tentativas)")


def gerar_runbooks():
    for codigo, info in CATALOGO.items():
        arq = Path("runbooks") / arquivo_runbook(codigo)
        if arq.exists():
            continue
        arq.parent.mkdir(parents=True, exist_ok=True)
        causa = re.sub(r"\{\w+\}", "<valor>", info["causa"])
        arq.write_text(
            f"# {codigo}\n\n**Componente:** {info['componente']}  \n**Severidade:** {info['severidade']}\n\n"
            f"## Causa raiz típica\n{causa}\n\n## Diagnóstico\n- TODO\n\n## Correção\n- TODO\n\n"
            f"## Prevenção\n- TODO\n",
            encoding="utf-8",
        )
    print(f"{len(CATALOGO)} runbooks em ./runbooks/")


if __name__ == "__main__":
    vistos = set()
    salvar(Path("data/treino.jsonl"), N_TREINO, "treino", seed=42, ja_vistos=vistos)
    salvar(Path("data/teste.jsonl"), N_TESTE, "teste", seed=4242, ja_vistos=vistos)
    erros, checados = checar([Path("data/treino.jsonl"), Path("data/teste.jsonl")])
    assert erros == 0, f"{erros} fatos sem grounding em {checados} exemplos com erro"
    print(f"checar(): {checados} exemplos com erro, todos os fatos citados estão no log")
    gerar_runbooks()
