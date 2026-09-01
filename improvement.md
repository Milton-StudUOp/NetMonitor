# Estado da implementação premium

Este documento substitui a especificação inicial e registra a situação efetiva da branch `premium`.

## Critérios de aceitação

| Requisito | Estado | Implementação |
|---|---|---|
| Descobrir IP, intervalo e CIDR | Concluído | `/api/discovery/scan` |
| ICMP e portas TCP configuráveis | Concluído | Limites de segurança aplicados |
| SNMPv2c e SNMPv3 | Concluído | SysName, SysDescr e até 128 interfaces |
| Selecionar e editar antes de importar | Concluído | Tela Descoberta |
| Não persistir credenciais da descoberta | Concluído | Credenciais existem somente na requisição |
| Biblioteca de ícones | Concluído | Nativos + SVG/PNG personalizado |
| Ícone refletido em todas as vistas | Concluído | Campo central `devices.icon_id` |
| Layout persistente | Concluído | `topology_positions`, sem dependência de localStorage |
| Múltiplas conexões de banco | Concluído | SQLite/PostgreSQL/MySQL/MSSQL/Oracle |
| Escolher banco principal | Concluído | Migração, validação e ativação após restart |
| Fontes SQL externas | Concluído | SELECT parametrizado e limitado |
| Email, Telegram e WhatsApp | Concluído | Credenciais criptografadas e teste individual |
| Regras de notificação | Concluído | Eventos, severidade, canais, recuperação e lembrete |
| Deduplicação | Concluído | Alerta ativo + `notification_deliveries` |
| Persistência após reinício | Concluído | Banco como fonte de verdade e autoload |
| Retenção e thresholds operacionais | Concluído | Recarregados no motor de monitoramento |
| Export e import | Concluído | Inventário, topologia, redundância, regras e preferências |
| Segredos fora do backup/API | Concluído | Respostas mascaradas e export sem credenciais |
| Audit log | Concluído | Operações administrativas relevantes |

## Decisões arquiteturais

- SQLite permanece o fallback local.
- A promoção de banco nunca apaga a origem.
- O destino deve estar vazio para evitar merge destrutivo.
- A troca de engine requer reinício do backend.
- `SECRET_KEY` protege tokens, passwords e a seleção do banco principal.
- WhatsApp depende de API oficial ou provider configurável; WhatsApp Web não é utilizado.
- O frontend só confirma alterações depois de sucesso do backend.

## Validação automatizada

A suíte em `backend/tests/test_platform.py` cobre:

- ausência de segredos nas respostas;
- bloqueio de SQL destrutivo;
- execução de fonte somente leitura;
- backup/restore com gateway, link e layout;
- migração integral para novo banco principal;
- criptografia do arquivo de ativação.

Execute:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run build
```

## Operação recomendada

Antes de produção, configure autenticação/reverse proxy, HTTPS, uma `SECRET_KEY` exclusiva, PostgreSQL com TLS, backups nativos e utilizadores de privilégio mínimo. Consulte [SECURITY.md](SECURITY.md), [arquitetura](docs/ARCHITECTURE.md) e [bancos](docs/DATABASES.md).
