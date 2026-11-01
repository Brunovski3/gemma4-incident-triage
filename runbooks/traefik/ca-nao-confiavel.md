# Traefik não confia na CA interna

`traefik_ca_nao_confiavel` · **Componente:** Traefik / PKI · **Severidade:** ALTA

## Resumo rápido

O serviço interno apresentou um certificado assinado pela CA da empresa, mas o Traefik não tem essa CA na lista de autoridades em que confia. Ele recusa a conexão por segurança. Isso costuma aparecer depois de trocar um backend de HTTP para HTTPS, renovar o certificado com uma CA nova ou atualizar a imagem do Traefik.

## Como aparece nos logs

- `tls: failed to verify certificate: x509: certificate signed by unknown authority`
- Às vezes com o detalhe `while trying to verify candidate authority certificate "CA Interna"`, que mostra qual CA ele não reconheceu.
- No access log, as requisições para aquele serviço saem com `500`.

## Diagnóstico

1. **Veja a cadeia que o serviço apresenta:**
   ```bash
   openssl s_client -connect auth.interno.local:443 -servername auth.interno.local -showcerts </dev/null
   ```
   Confira se ele manda o certificado intermediário junto. Um servidor que envia só o certificado final (sem o `fullchain`) causa esse erro mesmo com a CA raiz configurada.

2. **Teste a cadeia contra a sua CA:**
   ```bash
   openssl verify -CAfile ca-interna.pem certificado-do-servico.pem
   ```
   Se der `OK` aqui, o certificado está certo e o que falta é o Traefik conhecer a CA.

3. **Confira a configuração do Traefik:** procure um `serversTransport` com `rootCAs` apontando para o arquivo da CA, e se o router do serviço usa esse transport.

## Correção

- Adicione a CA interna ao `serversTransport` usado pelo serviço:
  ```yaml
  http:
    serversTransports:
      ca-interna:
        rootCAs:
          - /etc/traefik/certs/ca-interna.pem
  ```
  E aponte o serviço para ele (label `traefik.http.services.<nome>.loadbalancer.serverstransport=ca-interna@file`).
- No forwardAuth, use a opção `tls.ca` do middleware.
- Se o servidor não envia o intermediário, configure-o para servir o `fullchain`.
- **Não use `insecureSkipVerify: true` em produção.** Ele faz o erro sumir porque desliga a verificação, ou seja, a conexão continua cifrada mas sem garantia de com quem você está falando.

## Prevenção

- Distribua a CA interna em um lugar só (uma imagem base ou um volume compartilhado) em vez de copiar à mão para cada serviço.
- Quando a CA for rotacionada, publique a nova antes de começar a emitir certificados com ela, e mantenha as duas válidas durante a transição.
