# Contribuindo

## Fluxo

1. Crie uma branch a partir de `premium` para funcionalidades premium ou de `main` para a edição gratuita.
2. Não inclua credenciais, `.env`, `.active-database`, bancos, logs ou dados reais.
3. Preserve compatibilidade entre SQLite e PostgreSQL sempre que alterar modelos.
4. Adicione validação Pydantic, tratamento controlado de erros e audit log para operações administrativas.
5. Atualize a documentação afetada.

## Validação obrigatória

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall app
.\venv\Scripts\python.exe -c "from sqlalchemy.orm import configure_mappers; import app.models; configure_mappers()"

cd ..\frontend
npm ci
npm run build
```

## Banco e migrações

Novas tabelas são criadas por `Base.metadata.create_all`. Alterações em tabelas existentes devem ser adicionadas a `schema_migrations.py` e testadas sobre uma base já existente. Mudanças no processo de promoção precisam testar:

- destino vazio;
- relações entre devices, interfaces e links;
- contagem por tabela;
- ausência de URL ou password em respostas e logs;
- preservação do banco de origem.

## Pull request

Descreva problema, solução, riscos, migração necessária e comandos executados. Para alterações visuais, inclua capturas sem endereços ou nomes reais.

## Segurança

Vulnerabilidades não devem ser discutidas publicamente antes de correção coordenada. Consulte [SECURITY.md](SECURITY.md).
