# NetMonitor Free

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Plataforma gratuita e open source para monitoramento de equipamentos, enlaces e redundância de rede em tempo real.

## Recursos

- Monitoramento ICMP de equipamentos e enlaces.
- Topologia interativa com layout automático e livre.
- Associação automática entre equipamento, gateway e enlace principal.
- Redundância por enlaces ou diretamente por equipamentos.
- Detecção de estados normal, degradado e crítico.
- Alertas com diagnóstico de causa provável.
- Histórico, relatórios, WebSocket e dashboard em tempo real.
- Verificações ICMP, TCP, HTTP, HTTPS e SNMP.
- Notificações opcionais por e-mail, Microsoft Teams e Telegram.
- Backend FastAPI e frontend React/Vite.

## Requisitos

### Com Docker

- Docker Engine 24+
- Docker Compose v2

### Desenvolvimento local

- Python 3.12+
- Node.js 20+
- npm 10+

O desenvolvimento local usa SQLite por padrão. PostgreSQL/TimescaleDB e Redis são usados no ambiente Docker.

## Execução com Docker

```bash
git clone https://github.com/OWNER/REPOSITORY.git
cd REPOSITORY
cp .env.example .env
docker compose up -d --build
```

Edite `.env` e troque, no mínimo, `POSTGRES_PASSWORD` e `SECRET_KEY` antes de subir os contêineres.

Serviços:

- Dashboard: <http://localhost:3000>
- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- WebSocket: `ws://localhost:8000/ws/monitoring`

## Desenvolvimento local

### Backend

```bash
cd backend
python -m venv venv
```

Ativação no Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

Ativação no Linux/macOS:

```bash
source venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

No PowerShell, use `Copy-Item .env.example .env` no lugar de `cp` se necessário.

### Frontend

Em outro terminal:

```bash
cd frontend
npm ci
npm run dev
```

Acesse <http://localhost:3000>. O Vite encaminha API e WebSocket para o backend local na porta `8080`.

## Validação antes do commit

```bash
cd backend
python -m compileall app
python -c "from sqlalchemy.orm import configure_mappers; import app.models; configure_mappers()"

cd ../frontend
npm ci
npm run build
```

O mesmo fluxo é executado automaticamente pelo GitHub Actions.

## Estrutura

```text
.
├── backend/                 API FastAPI, modelos e monitoramento
│   ├── alembic/             Estrutura de migrações
│   └── app/
│       ├── api/             Endpoints REST e WebSocket
│       ├── models/          Modelos SQLAlchemy
│       ├── schemas/         Contratos Pydantic
│       ├── services/        ICMP, SNMP, redundância e alertas
│       └── utils/
├── frontend/                Interface React/Vite
│   └── src/
│       ├── components/
│       ├── hooks/
│       └── pages/
├── docker-compose.yml
├── improvement.md            Notas e especificações de evolução
└── .github/workflows/ci.yml
```

## Segurança e privacidade

Não publique inventários reais, bancos SQLite, arquivos `.env`, comunidades SNMP privadas, tokens, webhooks ou credenciais. Consulte [SECURITY.md](SECURITY.md).

O monitoramento ICMP/SNMP deve ser executado somente em redes e equipamentos para os quais você possui autorização.

## Contribuição

Contribuições são bem-vindas. Leia [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir um pull request.

## Licença

Distribuído gratuitamente sob a [licença MIT](LICENSE).
