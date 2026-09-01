# NetMonitor Premium

Plataforma de monitoramento de infraestrutura de rede com descoberta automática, topologia persistente, análise de redundância, alertas multicanal e banco de dados selecionável pelo administrador.

> A branch `main` representa a edição gratuita. O desenvolvimento avançado está na branch `premium`.

## Funcionalidades

- Monitoramento ICMP, TCP, HTTP/HTTPS e SNMP.
- Descoberta por IP, intervalo ou CIDR, com SNMPv2c e SNMPv3.
- Identificação de hostname, descrição SNMP, fabricante, modelo e interfaces.
- Importação seletiva dos equipamentos descobertos.
- Gateway associado e criação automática do enlace principal.
- Topologia automática ou livre, com posições persistidas no backend.
- Biblioteca de ícones nativos e upload de SVG/PNG sanitizado.
- Redundância por enlaces ou diretamente por equipamentos.
- Estados normal, degradado e crítico com diagnóstico de dependências.
- Email SMTP, Telegram e WhatsApp por API oficial/provider.
- Regras, deduplicação, lembretes e notificações de recuperação.
- SQLite padrão e promoção de SQLite, PostgreSQL, MySQL, SQL Server ou Oracle a banco principal.
- Migração validada antes da troca do banco principal.
- Fontes SQL externas somente leitura, limitadas a 100 registros.
- Backup e restauração de inventário, topologia, redundância, regras e preferências.
- Criptografia de passwords e tokens e trilha de auditoria.

## Início rápido local

Requisitos: Python 3.12+, Node.js 20+ e npm 10+.

```powershell
git clone https://github.com/Milton-StudUOp/NetMonitor.git
cd NetMonitor
git switch premium

cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8080
```

Em outro terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Acesse:

- Interface: <http://localhost:3000>
- API: <http://localhost:8080>
- Swagger: <http://localhost:8080/docs>
- Health check: <http://localhost:8080/health>

## Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Troque `POSTGRES_PASSWORD` e `SECRET_KEY` antes de iniciar. No Docker, PostgreSQL é o banco principal inicial e os volumes `pgdata` e `redisdata` garantem persistência.

## Banco principal

Sem configuração adicional, o desenvolvimento local usa `backend/network_monitor.db` (SQLite). A tela **Configurações → Bases de dados** permite cadastrar outra conexão e escolher **Usar como principal**.

O processo de promoção:

1. testa o destino;
2. exige banco vazio;
3. cria o esquema;
4. migra todos os registros em transação;
5. valida contagens por tabela;
6. grava a seleção em arquivo local criptografado;
7. solicita reinício do backend.

O banco anterior não é apagado. Se o banco promovido falhar no startup, o backend retorna automaticamente ao anterior. Consulte [Migração de banco](docs/DATABASES.md).

## Descoberta de rede

Em **Descoberta**, informe um dos formatos:

```text
192.168.1.15
192.168.1.10-192.168.1.100
192.168.1.0/24
```

O limite é de 1.024 hosts por pesquisa e 64 portas por alvo. Credenciais usadas na descoberta não são persistidas. Execute varreduras apenas em redes autorizadas.

## Topologia e ícones

- **Automático** recalcula a hierarquia.
- **Livre** permite arrastar os equipamentos e persiste as coordenadas no banco.
- **Reorganizar** recalcula e grava uma nova disposição.
- **Guardar vista** cria uma cópia nomeada das posições, modo, zoom e enquadramento atuais.
- **Recuperar** restaura uma vista guardada caso a topologia seja desorganizada.
- O ícone é escolhido em **Equipamentos → Editar → Ícone do equipamento**.
- Ícones próprios são carregados em **Configurações → Ícones**.

## Backup

Em **Configurações → Sistema & Backup**:

- **Exportar configuração** gera JSON versionado.
- **Importar backup** restaura ícones, equipamentos, interfaces, links, redundâncias, posições, regras e preferências.

Passwords, tokens e comunidades SNMP nunca são exportados.

## Testes

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall app

cd ..\frontend
npm run build
```
## Documentação

- [Arquitetura e persistência](docs/ARCHITECTURE.md)
- [Bancos e migração](docs/DATABASES.md)
- [Segurança](SECURITY.md)
- [Contribuição](CONTRIBUTING.md)
- [Estado da especificação premium](improvement.md)

## Licença

A edição gratuita publicada na branch `main` é distribuída sob a [licença MIT](LICENSE). Confirme os termos aplicáveis à branch premium antes de redistribuí-la.
