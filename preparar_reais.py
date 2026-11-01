"""
Transforma os logs brutos do chaos lab (logs_raw/) em janelas rotuladas para TESTE real.

Entrada (um arquivo por serviço, como coletado do minikube):
    logs_raw/traefik/traefik.log        kubectl logs (console do Traefik v3, com cores ANSI)
    logs_raw/postgres/postgres.log      kubectl logs (initdb + log do PostgreSQL)
    logs_raw/authentik/authentik.log    kubectl logs (JSON do Authentik)
    logs_raw/prometheus/prometheus.log  kubectl logs (logfmt do Prometheus)
    logs_raw/k8s/events.log             kubectl get events -o json

Saída:
    reais/teste_real.jsonl   mesmo formato do data/teste.jsonl, com meta.variante = "real"

Os logs reais NUNCA entram no treino: eles medem se o modelo funciona fora do sintético.
Os rótulos (causa raiz) são definidos pelas REGRAS abaixo, escritas a partir da análise
manual de cada incidente do lab. Ao coletar incidentes novos, acrescente uma regra.

Uso:
    python preparar_reais.py
"""

import json
import random
import re
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gerar_dataset import CATALOGO, FATOS, SEM_ERRO, link_runbook, montar_prompt

PASTA = Path("logs_raw")
SAIDA = Path("reais/teste_real.jsonl")
MAX_LINHAS = 20            # linhas por janela
MAX_CHARS = 4000           # ~1.500 tokens: cabe no MAX_SEQ_LENGTH de 2048 com o prompt
MAX_CHARS_LINHA = 300      # dumps gigantes (config do Traefik) são cortados, como faria um coletor
MAX_JANELAS_POR_GRUPO = 6  # evita que um incidente repetitivo domine a métrica
ANO = 2026

RE_ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ---------------------------------------------------------------------------
# Leitura: cada serviço vira uma lista de (timestamp, linha_original)
# ---------------------------------------------------------------------------
def ts_de_linha(linha_limpa):
    """Extrai o horário dos formatos presentes no lab (None quando a linha não tem horário)."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.\d+)?", linha_limpa)
    if m:
        return datetime.fromisoformat(f"{m.group(1)} {m.group(2)}{(m.group(3) or '')[:7]}")
    m = re.match(r"[IWEF](\d{2})(\d{2}) (\d{2}:\d{2}:\d{2}\.\d+)", linha_limpa)          # klog
    if m:
        return datetime.fromisoformat(f"{ANO}-{m.group(1)}-{m.group(2)} {m.group(3)[:15]}")
    m = re.search(r"\bts=(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}\.\d+)", linha_limpa)     # Prometheus
    if m:
        return datetime.fromisoformat(f"{m.group(1)} {m.group(2)}")
    m = re.search(r'"timestamp": (\d{10}\.\d+)', linha_limpa)                           # Authentik
    if m:
        return datetime.fromtimestamp(float(m.group(1)), tz=timezone.utc).replace(tzinfo=None)
    return None


def cortar(linha):
    return linha if len(linha) <= MAX_CHARS_LINHA else linha[:MAX_CHARS_LINHA] + " …(truncado)"


def ler_texto(caminho):
    """Lê um log de texto mantendo a linha original (inclusive ANSI); linhas sem horário herdam o anterior."""
    linhas, ultimo = [], None
    for bruta in caminho.read_text(errors="replace").splitlines():
        ts = ts_de_linha(RE_ANSI.sub("", bruta)) or ultimo
        ultimo = ts
        linhas.append((ts, cortar(bruta)))
    return linhas


def ler_eventos(caminho):
    """kubectl get events -o json (objetos concatenados) -> linhas no formato da tabela do kubectl."""
    texto, dec, i, eventos = caminho.read_text(), json.JSONDecoder(), 0, {}
    while i < len(texto):
        while i < len(texto) and texto[i].isspace():
            i += 1
        if i >= len(texto):
            break
        obj, i = dec.raw_decode(texto, i)
        eventos[obj["metadata"]["uid"]] = obj                 # deduplica coletas repetidas
    eventos = sorted(eventos.values(), key=lambda e: e["lastTimestamp"] or "")
    fim = datetime.fromisoformat(eventos[-1]["lastTimestamp"].rstrip("Z"))
    linhas = []
    for e in eventos:
        ts = datetime.fromisoformat(e["lastTimestamp"].rstrip("Z"))
        seg = int((fim - ts).total_seconds())
        idade = f"{seg}s" if seg < 120 else f"{seg // 60}m"
        obj = f"{e['involvedObject']['kind'].lower()}/{e['involvedObject']['name']}"
        linhas.append((ts, f"{idade:<7} {e['type']:<8} {e['reason']:<20} {obj:<38} {e['message']}"))
    return linhas


# ---------------------------------------------------------------------------
# Regras de rótulo (causa raiz), na ordem de prioridade
# ---------------------------------------------------------------------------
def rotular(texto):
    """Devolve (codigo, valores) para a janela; codigo None = sem falha de infraestrutura."""
    t = RE_ANSI.sub("", texto)
    if m := re.search(r'database \\?"([\w-]+)\\?" does not exist', t):
        return "postgres_banco_inexistente", {"banco": m.group(1)}
    if m := re.search(r'is forbidden: User \\?"(system:serviceaccount:[\w:-]+)\\?"', t):
        return "traefik_rbac_sem_permissao", {"sa": m.group(1)}
    if m := re.search(r"Error (?:loading|reloading) config \(--config\.file=\\?\"?([^)\"\\]+)", t):
        return "prometheus_config_invalida", {"prom_cfg": m.group(1)}
    if m := re.search(r'relation "([\w.]+)" does not exist', t):
        return "postgres_relacao_inexistente", {"tabela": m.group(1)}
    if "PostgreSQL connection failed" in t and "Connection refused" in t:
        return "authentik_banco_indisponivel", {}
    if m := re.search(r"Back-off restarting failed container ([\w-]+) in pod ([\w-]+)_", t):
        return "k8s_crashloopbackoff", {"app": m.group(1), "pod": m.group(2)}
    return None, {}


def resposta_para(codigo, valores):
    if codigo is None:
        return SEM_ERRO, {}
    info = CATALOGO[codigo]
    campos = {f for _, f, _, _ in string.Formatter().parse(info["causa"]) if f}
    faltando = campos - valores.keys()
    assert not faltando, f"{codigo}: a regra não extraiu {faltando}"
    fatos = {k: v.format(**valores) for k, v in FATOS.get(codigo, {}).items()}
    return {"severidade": info["severidade"], "componente_afetado": info["componente"],
            "causa_raiz": info["causa"].format(**valores), "runbook": link_runbook(codigo)}, fatos


# ---------------------------------------------------------------------------
# Janelas
# ---------------------------------------------------------------------------
def segmentos(linhas):
    """Separa execuções diferentes concatenadas no mesmo arquivo (ex.: o pod reiniciou e o log
    da execução seguinte foi anexado): o horário volta para trás ou salta mais de 10 minutos."""
    atual, anterior = [], None
    for ts, linha in linhas:
        if atual and ts and anterior and (ts < anterior - timedelta(seconds=1) or ts - anterior > timedelta(minutes=10)):
            yield atual
            atual = []
        atual.append((ts, linha))
        anterior = ts or anterior
    if atual:
        yield atual


def janelas(linhas):
    """Fatia cada segmento em blocos de tamanho parecido (até MAX_LINHAS linhas e MAX_CHARS
    caracteres), para não sobrar uma janela de uma linha só no final."""
    for seg in segmentos(linhas):
        n = len(seg)
        k = -(-n // MAX_LINHAS)                       # teto de n / MAX_LINHAS
        alvo = -(-n // k)
        bloco, tamanho = [], 0
        for _, linha in seg:
            if bloco and (len(bloco) >= alvo or tamanho + len(linha) > MAX_CHARS):
                yield bloco
                bloco, tamanho = [], 0
            bloco.append(linha)
            tamanho += len(linha) + 1
        if bloco:
            yield bloco


def assinatura(texto):
    """Normaliza números e hashes para descartar janelas praticamente idênticas."""
    return re.sub(r"[0-9a-f]{6,}|\d+", "#", RE_ANSI.sub("", texto))


def exemplo(texto, fonte, cascata=False):
    codigo, valores = rotular(texto)
    resposta, fatos = resposta_para(codigo, valores)
    return {"conversations": [{"role": "user", "content": montar_prompt(texto)},
                              {"role": "assistant", "content": json.dumps(resposta, ensure_ascii=False)}],
            "meta": {"codigo": codigo, "variante": "real", "cascata": cascata, "fatos": fatos or None,
                     "fonte": fonte}}


def com_prefixo(linhas, prefixo):
    """Simula `kubectl logs --prefix`: [pod/<nome>/<container>] linha."""
    return [(ts, f"[{prefixo}] {linha}") for ts, linha in linhas]


def main():
    fontes = {
        "traefik": ler_texto(PASTA / "traefik/traefik.log"),
        "postgres": ler_texto(PASTA / "postgres/postgres.log"),
        "authentik": ler_texto(PASTA / "authentik/authentik.log"),
        "prometheus": ler_texto(PASTA / "prometheus/prometheus.log"),
        "events": ler_eventos(PASTA / "k8s/events.log"),
    }

    candidatos = []
    for nome, linhas in fontes.items():
        for bloco in janelas([l for l in linhas if RE_ANSI.sub("", l[1]).strip()]):
            candidatos.append(exemplo("\n".join(bloco), nome))

    # Cascata real: Postgres sem o database + Authentik em retry + pod em BackOff, intercalados no tempo
    pods = {"authentik": "pod/authentik-84ff44596f-ckttt/authentik", "postgres": "pod/postgres-67c57d5c6c-qsq69/postgres"}
    misturado = sorted(com_prefixo(fontes["authentik"], pods["authentik"])
                       + com_prefixo(fontes["postgres"], pods["postgres"]) + fontes["events"],
                       key=lambda x: x[0] or datetime.min)
    inicio = datetime(ANO, 11, 1, 2, 15, 15)
    trecho = [l for l in misturado if l[0] and inicio <= l[0] <= inicio + timedelta(minutes=2)]
    rng = random.Random(7)
    for bloco in janelas(trecho):
        # mantém só blocos com mais de uma fonte (é isso que caracteriza a cascata)
        if sum(any(l.startswith(f"[{p}]") for l in bloco) for p in pods.values()) + \
           any(not l.startswith("[") for l in bloco) >= 2:
            candidatos.append(exemplo("\n".join(bloco), "cascata", cascata=True))

    # Deduplica e limita janelas por (fonte, rótulo)
    vistos, grupos = set(), {}
    for ex in candidatos:
        chave = assinatura(ex["conversations"][0]["content"])
        if chave in vistos:
            continue
        vistos.add(chave)
        grupos.setdefault((ex["meta"]["fonte"], ex["meta"]["codigo"]), []).append(ex)
    final = []
    for (fonte, codigo), exs in sorted(grupos.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        if len(exs) > MAX_JANELAS_POR_GRUPO:
            passo = len(exs) / MAX_JANELAS_POR_GRUPO
            exs = [exs[int(i * passo)] for i in range(MAX_JANELAS_POR_GRUPO)]
        final += exs
        print(f"  {fonte:<11} {str(codigo):<32} {len(exs):>2} janela(s)")

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with SAIDA.open("w", encoding="utf-8") as f:
        for ex in final:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"{len(final)} janelas reais -> {SAIDA}")


if __name__ == "__main__":
    main()
