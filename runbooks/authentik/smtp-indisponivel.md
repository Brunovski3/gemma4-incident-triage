# Authentik não consegue enviar e-mails

`authentik_smtp_indisponivel` · **Componente:** Authentik / E-mail · **Severidade:** MEDIA

## Resumo rápido

O worker do Authentik tentou enviar um e-mail e o servidor SMTP não aceitou. Login normal continua funcionando, mas tudo que depende de e-mail para: recuperação de senha, verificação de cadastro, convites e notificações. O usuário costuma relatar "pedi para redefinir a senha e o e-mail nunca chegou".

## Como aparece nos logs

- `"event": "Failed to send email", "error": "[Errno 111] Connection refused"` (logger `authentik.stages.email.tasks`)
- `"event": "Failed to send email", "error": "timed out"`
- `smtplib.SMTPServerDisconnected: Connection unexpectedly closed`

## Diagnóstico

1. **Teste o envio direto pelo Authentik:**
   ```bash
   docker compose exec worker ak test_email seu-email@exemplo.com
   ```
   O comando mostra o erro exato da conexão com o SMTP.

2. **Confira a configuração** no `.env`: `AUTHENTIK_EMAIL__HOST`, `__PORT`, `__USERNAME`, `__USE_TLS`, `__USE_SSL` e `__FROM`.

3. **Porta e criptografia combinam?** É a causa mais comum:
   - Porta **587**: use `USE_TLS=true` e `USE_SSL=false` (STARTTLS).
   - Porta **465**: use `USE_SSL=true` e `USE_TLS=false`.
   Inverter os dois dá exatamente o `Connection unexpectedly closed` ou timeout.

4. **O servidor alcança o SMTP?** Muitos provedores de nuvem bloqueiam a saída na porta 25 e, às vezes, na 587. Teste de dentro do container:
   ```bash
   docker compose exec worker python -c "import socket; socket.create_connection(('smtp.exemplo.com', 587), 5); print('ok')"
   ```

5. **Credencial:** provedores como Google e Microsoft exigem senha de aplicativo ou OAuth, e recusam a senha normal da conta.

## Correção

- Ajuste a combinação de porta e TLS/SSL e recrie o worker.
- Saída bloqueada: libere a porta no firewall ou use um serviço de envio que aceite outra porta (muitos aceitam 2525).
- Credencial: gere uma senha de aplicativo ou uma chave de API do serviço de envio. Guarde no `.env` ou num cofre, nunca em chat ou ticket.

## Prevenção

- Rode o `ak test_email` depois de qualquer mudança na configuração de e-mail.
- Monitore a contagem de "Failed to send email" nos logs do worker.
- Use um serviço transacional (SES, SendGrid, Postmark ou similar) em vez de uma caixa de e-mail pessoal.
