# Bancos de dados

## SQLite padrão

Sem seleção administrativa nem `DATABASE_URL` externo, o backend usa:

```text
backend/network_monitor.db
```

SQLite é adequado para laboratório, demonstração e instalações pequenas com uma única instância do backend.

## Banco principal selecionável

Conexões cadastradas em **Configurações → Bases de dados** podem ser promovidas com **Usar como principal**. A seleção não troca o engine durante uma requisição ativa; ela é preparada e aplicada no próximo reinício.

### Fluxo de promoção

1. conexão habilitada e testada;
2. criação do esquema no destino;
3. recusa se houver tabelas de aplicação já preenchidas;
4. cópia transacional na ordem de dependências;
5. restauração das referências circulares entre devices e links;
6. comparação das contagens de todas as tabelas;
7. gravação criptografada em `backend/.active-database`;
8. reinício manual do backend.

O arquivo está no `.gitignore` e não contém URL em texto simples. A criptografia depende de `SECRET_KEY`.

## Drivers

| Tipo | Driver SQLAlchemy/Python | Observação |
|---|---|---|
| SQLite | `aiosqlite` | Incluído |
| PostgreSQL | `asyncpg` | Incluído e recomendado para produção |
| MySQL/MariaDB | `asyncmy` | Incluído nas dependências premium |
| SQL Server | `aioodbc` | Requer Microsoft ODBC Driver 18 no host |
| Oracle | `oracledb` | Thin mode quando suportado pelo servidor |

Depois de alterar dependências:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Docker

O `docker-compose.yml` define PostgreSQL como banco principal por `DATABASE_URL`. Essa variável continua sendo o fallback quando não existe uma seleção em `.active-database`.

Para preservar uma seleção feita pela interface em containers, monte o diretório do backend ou um volume que inclua `/app/.active-database`. O compose de desenvolvimento já monta `./backend:/app`.

## Fontes de dados

Uma conexão também pode alimentar uma fonte SQL. Isso não muda o banco principal. Fontes são consultas explicitamente criadas para dashboard, correlação ou monitoramento futuro.

Regras de segurança:

- somente `SELECT`;
- uma única instrução;
- parâmetros separados;
- limite externo de 100 linhas;
- utilizador remoto com permissão de leitura.

## Recuperação

O banco anterior não é removido. Se o novo banco não iniciar, pare o backend, mova `backend/.active-database` para um local seguro e inicie novamente; o sistema retornará ao `DATABASE_URL` ou ao SQLite padrão. Não apague o arquivo antes de guardar uma cópia, pois ele identifica a seleção ativa.

## Produção

- Prefira PostgreSQL.
- Use TLS e credenciais de privilégio mínimo.
- Faça backup nativo do banco além do export de configuração.
- Não compartilhe o mesmo SQLite entre múltiplas instâncias.
- Mantenha `SECRET_KEY` fora da imagem e estável entre reinícios.
