# Outpost do Authentik sem provider

`authentik_outpost_sem_provider` · **Componente:** Authentik / Outpost · **Severidade:** MEDIA

## Resumo rápido

O outpost (o proxy que o Authentik coloca na frente das aplicações) subiu, mas não tem um provider configurado para atender aquela aplicação. O resultado é que o login via proxy daquela aplicação para de funcionar. Normalmente alguém removeu o provider, trocou a aplicação de outpost, ou o domínio configurado no provider não bate com o domínio acessado.

## Como aparece nos logs

- `"event": "No providers assigned to this outpost, check outpost configuration"` (logger `authentik.outpost.proxyv2`)
- `"event": "Failed to get provider", "error": "404 Not Found"`
- `"event": "No provider found for host", "host": "app.exemplo.com"`
- Do lado do usuário: erro ou 502 ao abrir a aplicação protegida.

## Diagnóstico

1. **O outpost tem providers?** No painel admin do Authentik, abra **Aplicações → Outposts** e edite o outpost. Confira se a aplicação/provider desejado está na lista de selecionados.

2. **O provider ainda existe?** Em **Aplicações → Providers**, veja se ele não foi apagado ou desvinculado da aplicação. Um 404 na busca do provider é sinal disso.

3. **Domínio bate?** Para `No provider found for host`, compare o host do log com o **External host** configurado no proxy provider. `https://app.exemplo.com` e `https://www.app.exemplo.com` são hosts diferentes.

4. **O token é do outpost certo?** Para outposts implantados manualmente (fora do embedded), o `AUTHENTIK_TOKEN` define qual outpost aquele container representa. Um token copiado de outro outpost faz o container carregar a configuração errada.

## Correção

- Provider fora da lista: adicione-o ao outpost e salve. O outpost recarrega a configuração sozinho em alguns segundos.
- Provider apagado: recrie o provider, vincule à aplicação e ao outpost.
- External host divergente: corrija o valor no provider para o domínio real de acesso.
- Token errado: gere o token do outpost correto no painel e atualize o container.

## Prevenção

- Gerencie a configuração do Authentik como código (blueprints), para mudanças passarem por revisão.
- Depois de mexer em providers ou outposts, teste o login das aplicações afetadas.
