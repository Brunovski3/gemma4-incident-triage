# Certificado expirado na CA interna

`traefik_certificado_expirado` · **Componente:** Traefik / PKI · **Severidade:** ALTA

## Resumo rápido

O Traefik tentou falar via TLS com um serviço interno (um backend HTTPS, um forwardAuth ou um health check) e o certificado do outro lado venceu. Como a CA é interna, ninguém renova isso automaticamente por padrão: alguém emitiu o certificado há um ou dois anos e esqueceu.

## Como aparece nos logs

- `x509: certificate has expired or is not yet valid: current time 2026-10-31T12:00:00Z is after 2026-10-01T00:00:00Z`
- Costuma vir junto de `500 Internal Server Error` no access log, ou de `Health check failed` se for o health check que quebrou.
- Repare nas duas datas da mensagem: a segunda é quando o certificado venceu.

## Diagnóstico

1. **Confirme qual certificado venceu.** A mensagem traz o host. Inspecione direto:
   ```bash
   openssl s_client -connect auth.interno.local:443 -servername auth.interno.local </dev/null 2>/dev/null \
     | openssl x509 -noout -subject -issuer -dates
   ```
   O `notAfter` mostra a data de expiração e o `issuer` confirma que é a CA interna.

2. **Descarte problema de relógio.** Se a mensagem diz "not yet valid" ou as datas parecem absurdas, o relógio de algum dos lados pode estar errado:
   ```bash
   timedatectl status
   ```
   Um servidor com NTP parado causa exatamente esse erro com certificado válido.

3. **Descubra quem emitiu e como.** step-ca, Vault PKI, AD CS ou um `openssl` manual? Isso define como renovar.

## Correção

- Emita um certificado novo pela CA interna para o mesmo nome (com os mesmos SANs) e substitua no serviço de destino.
- Reinicie ou recarregue o serviço para ele carregar o certificado novo. Muitos só leem o arquivo na inicialização.
- Se o problema era relógio, corrija o NTP (`timedatectl set-ntp true`) e o erro some sozinho.

## Prevenção

- Esse é o tipo de incidente que se resolve de vez com automação: use certificados de vida curta com renovação automática (step-ca com ACME, cert-manager no Kubernetes ou o próprio Vault).
- Enquanto não automatizar, monitore a validade de todo endpoint TLS interno e alerte com 30 dias de antecedência.
- Mantenha um inventário de onde cada certificado interno está instalado. Metade do tempo desse incidente é descobrir onde está o arquivo.
