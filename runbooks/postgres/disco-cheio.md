# Disco do PostgreSQL cheio

`postgres_disco_cheio` · **Componente:** PostgreSQL / Armazenamento · **Severidade:** CRITICA

## Resumo rápido

O volume do Postgres encheu. Se faltou espaço para gravar o WAL, o banco entra em `PANIC` e **para**. Por isso esse incidente é crítico e costuma derrubar tudo em cascata. Calma antes de sair apagando coisas: a regra número um aqui é **nunca apagar arquivos da pasta `pg_wal` na mão**. Isso corrompe o banco.

## Como aparece nos logs

- `PANIC:  could not write to file "pg_wal/xlogtemp.123": No space left on device`: o banco parou.
- `ERROR:  could not extend file "base/16384/2619": No space left on device`, com `HINT: Check free disk space.`
- `could not write to file "base/pgsql_tmp/...": No space left on device`: uma query gerou arquivos temporários enormes.
- Em seguida, as aplicações recebendo `Connection refused`.

## Diagnóstico

1. **Onde está o espaço?**
   ```bash
   df -h
   sudo du -sh /var/lib/postgresql/data/{base,pg_wal}
   ```
   (Em container, ajuste o caminho para o volume montado.)

2. **`pg_wal` enorme?** O WAL deveria ser reciclado. Quando ele cresce sem parar, quase sempre é um destes casos:
   - **Slot de replicação abandonado**, segurando WAL para uma réplica que não existe mais:
     ```sql
     SELECT slot_name, active,
            pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retido
     FROM pg_replication_slots;
     ```
   - **`archive_command` falhando**: o Postgres não descarta o WAL enquanto não consegue arquivar. Procure erros de archive nos logs.

3. **`base` enorme?** Pode ser crescimento real dos dados ou inchaço (bloat) de tabelas com muito UPDATE/DELETE sem vacuum.

4. **`pgsql_tmp` enorme?** Alguma query com sort ou join gigante está despejando arquivos temporários no disco.

## Correção

1. **Primeiro, ganhe espaço sem tocar no banco:** expanda o volume (na nuvem costuma ser rápido) ou libere espaço de outras coisas no mesmo disco (logs antigos, backups locais).
2. Slot abandonado: remova o slot, e o WAL é liberado no próximo checkpoint:
   ```sql
   SELECT pg_drop_replication_slot('nome_do_slot');
   ```
   Confirme antes que nenhuma réplica ativa usa esse slot.
3. Archive falhando: corrija o destino do arquivamento (permissão, bucket, credencial).
4. Arquivos temporários: identifique e cancele a query responsável (`pg_cancel_backend(pid)`).
5. Com espaço livre, suba o Postgres. Ele faz a recuperação sozinho a partir do WAL.

## Prevenção

- Alerte com 80% de uso do disco.
- Configure `max_slot_wal_keep_size` (Postgres 13+) para um slot esquecido nunca encher o disco.
- Configure `temp_file_limit` para uma query sozinha não consumir o disco inteiro.
- Monitore a falha de archive e os slots inativos.
