"""
Módulo de inferência, guardrails e avaliação do Agente de Triagem.
Compartilhado entre os notebooks de treino e teste.
"""
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch
from unsloth import FastModel

from gerar_dataset import montar_prompt

# Catálogo imutável: usado como guardrail para evitar alucinações de caminhos
RUNBOOKS_VALIDOS = {str(p) for p in Path("runbooks").rglob("*.md") if p.name != "README.md"}


def extrair_json(texto: str) -> Optional[Dict[str, Any]]:
    """Extrai o primeiro objeto JSON válido encontrado no texto gerado."""
    # Remove blocos markdown ```json ... ```
    texto_limpo = re.sub(r"```(?:json)?\n?(.*?)\n?```", r"\1", texto, flags=re.DOTALL)
    
    match = re.search(r"\{.*\}", texto_limpo, re.DOTALL)
    if not match:
        return None
        
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def analisar_logs(
    model, tokenizer, logs: str, prompt_pronto: bool = False, max_new_tokens: int = 300
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Executa a inferência do modelo para um trecho de log e retorna (JSON parseado, texto bruto)."""
    conteudo = logs if prompt_pronto else montar_prompt(logs)
    texto = tokenizer.apply_chat_template(
        [{"role": "user", "content": conteudo}], tokenize=False, add_generation_prompt=True
    )
    entrada = tokenizer(text=texto, return_tensors="pt", add_special_tokens=False).to("cuda")
    
    with torch.no_grad():
        saida = model.generate(
            **entrada, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tokenizer.eos_token_id
        )
        
    bruto = tokenizer.decode(saida[0][entrada["input_ids"].shape[1]:], skip_special_tokens=True)
    return extrair_json(bruto), bruto


def triagem(model, tokenizer, logs: str) -> Optional[Dict[str, Any]]:
    """Executa a triagem local e aplica o guardrail de runbooks."""
    resposta, _ = analisar_logs(model, tokenizer, logs)
    
    if resposta and resposta.get("runbook"):
        if resposta["runbook"] not in RUNBOOKS_VALIDOS:
            resposta["runbook_sugerido_invalido"] = resposta["runbook"]
            resposta["runbook"] = None
            
    return resposta


def escalar_para_modelo_maior(logs: str) -> Dict[str, Any]:
    """
    Placeholder para o fallback (FinOps).
    Em um ambiente real, esta função faria uma chamada HTTP para uma API 
    (ex: Azure OpenAI, AWS Bedrock, OpenAI) passando o log e a lista de RUNBOOKS_VALIDOS.
    """
    print("[FALLBACK] Incidente complexo ou JSON inválido. Acionando API do modelo maior...")
    
    # Simulação da resposta de um modelo maior (Ex: GPT-4o ou Claude 3.5)
    return {
        "severidade": "ALTA",
        "componente_afetado": "Desconhecido (Análise Fallback)",
        "causa_raiz": "Incidente complexo que exigiu escalonamento para modelo de maior capacidade.",
        "runbook": None,
        "novo_incidente": True,
        "origem": "fallback_api",
        "motivo_escalonamento": "Falha na triagem local (runbook alucinado ou JSON malformado)."
    }


def triagem_com_fallback(model, tokenizer, logs: str) -> Dict[str, Any]:
    """
    Executa a triagem com o modelo local. Se houver falha ou alucinação bloqueada 
    pelo guardrail, aciona o modelo fallback (maior).
    """
    # 1. Tenta resolver localmente (barato e rápido)
    resposta = triagem(model, tokenizer, logs)
    
    # 2. Define critérios de falha para acionar o fallback
    falhou_localmente = (
        resposta is None or  # JSON completamente inválido
        (resposta.get("severidade") != "NENHUMA" and resposta.get("runbook") is None) or  # Tem erro, mas não achou runbook (ou foi bloqueado)
        resposta.get("runbook_sugerido_invalido") is not None  # Guardrail interceptou uma alucinação
    )
    
    # 3. Aciona o fallback se necessário
    if falhou_localmente:
        return escalar_para_modelo_maior(logs)
        
    # Se deu certo localmente, apenas adiciona a origem para telemetria
    resposta["origem"] = "local"
    return resposta


def grupo_do_exemplo(meta: dict) -> str:
    if meta.get("variante") == "real":
        return f"real ({meta.get('fonte')})"
    if meta["codigo"] is None:
        return "sem_erro (falso positivo?)"
    if meta["cascata"]:
        return "cascata (causa raiz)"
    return f"formulacao_{meta['variante']}"


def avaliar(model, tokenizer, dados, n: int, titulo: str) -> dict:
    """Calcula as métricas de avaliação por grupo (JSON, runbook, severidade, grounding, etc)."""
    FastModel.for_inference(model)

    m = defaultdict(lambda: defaultdict(int))
    falhas = []
    
    for ex in dados.select(range(min(n, len(dados)))):
        esperado = json.loads(ex["conversations"][1]["content"])
        grupo = grupo_do_exemplo(ex["meta"])
        previsto, bruto = analisar_logs(model, tokenizer, ex["conversations"][0]["content"], prompt_pronto=True)
        
        for g in (grupo, "TOTAL"):
            m[g]["n"] += 1
            
        if previsto is None:
            falhas.append((grupo, esperado["runbook"], f"JSON inválido: {bruto[:80].replace(chr(10), ' ')}"))
            continue
            
        runbook = previsto.get("runbook")
        acertos = {
            "json": 1,
            "runbook": runbook == esperado["runbook"],
            "severidade": str(previsto.get("severidade", "")).upper() == esperado["severidade"],
            "componente": previsto.get("componente_afetado") == esperado["componente_afetado"],
            "inventado": bool(runbook) and runbook not in RUNBOOKS_VALIDOS,
        }
        
        fatos = [v for v in (ex["meta"].get("fatos") or {}).values() if v]
        citados = sum(str(v) in str(previsto.get("causa_raiz", "")) for v in fatos)
        
        for g in (grupo, "TOTAL"):
            for k, v in acertos.items():
                m[g][k] += v
            m[g]["fatos_total"] += len(fatos)
            m[g]["fatos_citados"] += citados
            
        if not acertos["runbook"]:
            falhas.append((grupo, esperado["runbook"], runbook))

    print(f"\n=== {titulo} ===")
    print(f"{'grupo':30} {'n':>4} {'json':>6} {'runbook':>8} {'sever.':>7} {'compon.':>8} {'grounding':>10} {'inventado':>10}")
    
    for g, v in sorted(m.items()):
        n_g = v["n"]
        grounding = f"{v['fatos_citados'] / v['fatos_total']:.0%}" if v["fatos_total"] else "-"
        print(f"{g:30} {n_g:>4} {v['json'] / n_g:>6.0%} {v['runbook'] / n_g:>8.0%} {v['severidade'] / n_g:>7.0%} "
              f"{v['componente'] / n_g:>8.0%} {grounding:>10} {v['inventado'] / n_g:>10.0%}")
              
    if falhas:
        print("\nExemplos de erro:")
        for f in falhas[:10]:
            print("  ", f)
            
    return m

