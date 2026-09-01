# Arquitetura e persistência

## Componentes

```text
React/Vite
   │ REST + WebSocket
FastAPI
   ├── APIs administrativas
   ├── motor de monitoramento
   ├── redundância e alertas
   ├── notificações
   └── SQLAlchemy assíncrono
          └── banco principal selecionado
```

O frontend só considera uma alteração persistida depois da resposta de sucesso da API. Equipamentos, links, posições, regras, integrações e preferências têm o banco principal como fonte de verdade.

## Inicialização

1. `config.py` carrega ambiente e `.env`.
2. `db_bootstrap.py` verifica a seleção criptografada do banco principal.
3. `database.py` cria o engine assíncrono.
4. O lifespan cria tabelas e aplica compatibilidade de schema.
5. Preferências persistidas são carregadas no motor.
6. O monitoramento periódico é iniciado.
7. Frontend carrega dashboard, topologia e configurações pelas APIs.

Se a criação/validação do schema no banco selecionado falhar, o startup autentica no banco anterior registrado, troca o engine e reconfigura a mesma `async_session_factory`; serviços já importados passam a usar o bind recuperado.

## Persistência

São persistidos:

- equipamentos, interfaces e monitoramento;
- gateways e enlaces automáticos/manuais;
- grupos de redundância;
- layout da topologia;
- vistas nomeadas da topologia, incluindo posições e viewport;
- ícones nativos e personalizados;
- conexões de banco e fontes SQL;
- integrações e regras de notificação;
- controle de deduplicação/lembretes;
- preferências gerais e audit log.

O frontend não usa `localStorage` como fonte de configuração da topologia.

## Monitoramento

O motor lê intervalo, retenção e thresholds do registro `system_settings/general`. Alterações feitas na interface são recarregadas sem reiniciar. A máquina de estados exige falhas e sucessos consecutivos conforme configurado.

Uma limpeza horária remove resultados antigos e alertas já resolvidos que ultrapassaram a retenção. Alertas ativos não são removidos.

## Notificações

O alert engine deduplica pelo alvo enquanto o alerta estiver ativo. Regras definem evento, severidade, canais, destinatários, lembrete e recuperação. A tabela `notification_deliveries` registra último envio e quantidade, evitando repetição contínua.

## Backup

O formato atual é `netmonitor-config`, versão 1. IDs do arquivo são remapeados durante restore para preservar relações mesmo quando o destino já contém registros. Segredos são excluídos.

## Limites deliberados

- Descoberta: 1.024 hosts e 64 portas por varredura.
- SNMP: até 128 interfaces por equipamento descoberto.
- Fonte SQL: uma instrução `SELECT`, até 10.000 caracteres e 100 linhas retornadas.
- Ícone personalizado: 512 KB, SVG ou PNG.
