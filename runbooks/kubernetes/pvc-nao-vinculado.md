# PVC em Pending: volume não provisionado

`k8s_pvc_nao_vinculado` · **Componente:** Kubernetes / Armazenamento · **Severidade:** ALTA

## Resumo rápido

O pod precisa de um volume persistente (PVC), e o volume não foi criado ou vinculado. O pod fica em Pending até isso se resolver. As causas mais comuns são um StorageClass que não existe (erro de nome), um provisionador que não está funcionando ou uma cota de armazenamento esgotada.

## Como aparece nos logs

- Evento do pod: `0/3 nodes are available: pod has unbound immediate PersistentVolumeClaims.`
- `kubectl get pvc`: o PVC em `Pending`.
- Evento do PVC: `ProvisioningFailed: storageclass.storage.k8s.io "ebs-sc" not found`
- kube-controller-manager: `"Error provisioning volume" PVC="producao/data-api-0" ...`

## Diagnóstico

1. **O motivo está nos eventos do PVC:**
   ```bash
   kubectl describe pvc -n producao data-api-0
   ```

2. **O StorageClass existe?**
   ```bash
   kubectl get storageclass
   ```
   Compare com o `storageClassName` do PVC. Um manifest copiado de outro cluster (AWS para on-premises, por exemplo) costuma trazer um nome que não existe no cluster novo.

3. **O provisionador está rodando?** Cada StorageClass aponta para um provisionador (`ebs.csi.aws.com`, `rancher.io/local-path`, `driver.longhorn.io`). Confira se os pods dele estão saudáveis:
   ```bash
   kubectl get pods -A | grep -i -E 'csi|provisioner|longhorn'
   ```
   E veja os logs do controller do CSI.

4. **Um caso que não é erro:** com `volumeBindingMode: WaitForFirstConsumer`, o PVC fica em Pending até um pod que o use ser agendado. Isso é normal; só vira problema se o pod também estiver preso.

## Correção

- Nome errado: corrija o `storageClassName` (em StatefulSets, é preciso recriar o PVC, porque esse campo não pode ser alterado).
- Sem StorageClass padrão: marque um como padrão com a anotação `storageclass.kubernetes.io/is-default-class: "true"`.
- Provisionador com problema: resolva pelos logs dele (credenciais na nuvem, nó de storage fora do ar).
- Cota esgotada: aumente a cota na nuvem ou libere volumes órfãos.

## Prevenção

- Defina um StorageClass padrão em todo cluster.
- Parametrize o `storageClassName` nos charts por ambiente.
- Monitore os PVCs em Pending por mais de alguns minutos.
