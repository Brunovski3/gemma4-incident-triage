# Traefik não consegue emitir certificado pelo Let's Encrypt

`traefik_certificado_acme` · **Componente:** Traefik / ACME · **Severidade:** ALTA

## Resumo rápido

O Traefik pediu um certificado e o Let's Encrypt recusou. Enquanto isso não se resolve, o domínio fica com o certificado padrão do Traefik (aquele "TRAEFIK DEFAULT CERT") e o navegador mostra alerta de segurança. Quase sempre a causa está em uma de três coisas: limite de requisições, porta bloqueada ou DNS apontando para o lugar errado.

## Como aparece nos logs

- `Unable to obtain ACME certificate for domains "api.exemplo.com"`, seguido do motivo:
  - `urn:ietf:params:acme:error:rateLimited`: estourou o limite de emissões.
  - `urn:ietf:params:acme:error:connection ... Timeout during connect (likely firewall problem)`: o Let's Encrypt não conseguiu chegar até você.
  - `urn:ietf:params:acme:error:unauthorized ... Invalid response from http://.../.well-known/acme-challenge/...: 404`: chegou, mas não encontrou a resposta do desafio.

## Diagnóstico

1. **Leia o motivo no final da mensagem.** Ele diz exatamente qual dos três casos é.

2. **Rate limit:** o Let's Encrypt limita certificados repetidos para o mesmo conjunto de domínios (5 por semana) e o total por domínio registrado (50 por semana). Isso costuma acontecer quando alguém apaga o `acme.json` e reinicia o Traefik várias vezes tentando resolver outra coisa.

3. **Timeout de conexão:** o desafio HTTP-01 precisa da porta 80 aberta para a internet. Teste de fora da sua rede:
   ```bash
   curl -I http://api.exemplo.com/.well-known/acme-challenge/teste
   ```
   Se der timeout, olhe o firewall, o security group da nuvem e o redirecionamento de porta no roteador.

4. **Erro 403/404 no desafio:** confira para onde o DNS aponta:
   ```bash
   dig +short api.exemplo.com
   ```
   Se o IP não é do seu servidor, o Let's Encrypt está batendo na porta de outra pessoa. Outra causa comum: um middleware de redirect ou de autenticação interceptando o caminho `/.well-known/acme-challenge/`.

## Correção

- Rate limit: espere o período do limite passar e **não apague o `acme.json`**. Para testar configuração, aponte o `caServer` para o ambiente de staging (`https://acme-staging-v02.api.letsencrypt.org/directory`), que tem limites bem maiores.
- Porta bloqueada: libere a 80/tcp para a internet ou troque para o desafio DNS-01 (útil quando o servidor não é público).
- DNS errado: corrija o registro e espere a propagação antes de tentar de novo.
- Confira as permissões do `acme.json`: precisa ser `600`, senão o Traefik se recusa a usar o arquivo.

## Prevenção

- Monitore a validade dos certificados (o `probe_ssl_earliest_cert_expiry` do blackbox exporter resolve) e alerte com 14 dias de antecedência.
- Guarde o `acme.json` num volume persistente. Se ele some a cada deploy, você vai bater no rate limit.
- Use staging em qualquer ambiente de teste.
