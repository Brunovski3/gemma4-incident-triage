# Prometheus com configuração inválida

`prometheus_config_invalida` · **Componente:** Prometheus / Configuração · **Severidade:** MEDIA

## Resumo rápido

Alguém alterou o `prometheus.yml` e o Prometheus não conseguiu carregar o arquivo. O efeito depende do momento: num **reload**, ele recusa a configuração nova e continua rodando com a antiga (por isso a severidade é média, mas a mudança que você queria não está valendo); numa **inicialização**, ele simplesmente não sobe, e aí o monitoramento inteiro fica cego. O motivo vem escrito no próprio erro: indentação, campo com nome errado ou valor de duração inválido.

## Como aparece nos logs

- `level=error msg="Error loading config (--config.file=/etc/prometheus/prometheus.yml)" err="parsing YAML file ...: not a valid duration string: \"invalid_time_duration\""`
- `msg="Error reloading config" err="couldn't load configuration ..."`
- No Prometheus 3.x, o mesmo erro em outro formato: `time=... level=ERROR source=main.go:... msg="Error loading config ..."`
- Na interface, a página **Status → Configuration** continua mostrando a configuração antiga.

## Diagnóstico

1. **Leia o `err=` até o fim.** Ele diz a linha ou o campo problemático:
   - `not a valid duration string`: um tempo escrito errado. Durações usam unidade colada ao número (`15s`, `1m`, `2h`), nunca `15`, `1 minute` ou `30seg`.
   - `did not find expected key` ou `yaml: line N`: indentação ou estrutura do YAML.
   - `field X not found`: nome de campo digitado errado (por exemplo, `scrape_intervall`).
   - `scrape timeout greater than scrape interval`: o `scrape_timeout` precisa ser menor ou igual ao `scrape_interval`.

2. **Valide o arquivo fora do Prometheus:**
   ```bash
   promtool check config /etc/prometheus/prometheus.yml
   ```
   No Kubernetes, rode o `promtool` de dentro do pod ou localmente com o ConfigMap exportado.

3. **Foi reload ou restart?** Se o processo está de pé, só a mudança nova falhou. Se o pod está em CrashLoopBackOff, a configuração quebrada impede a subida.

## Correção

- Corrija o trecho indicado no erro e valide de novo com `promtool check config`.
- Aplique a configuração (atualize o ConfigMap) e peça o reload: `curl -X POST http://prometheus:9090/-/reload` (exige `--web.enable-lifecycle`) ou reinicie o pod.
- Confirme na página **Status → Configuration** que a configuração nova está valendo.

## Prevenção

- Rode `promtool check config` (e `promtool check rules` para as regras) no CI, antes de qualquer mudança chegar ao cluster.
- Alerte sobre falha de reload: a métrica `prometheus_config_last_reload_successful` fica em `0` quando o último reload falhou.
- Versione a configuração do Prometheus como código, com revisão.
