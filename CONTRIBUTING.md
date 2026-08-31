# Contribuindo

Obrigado por contribuir com o Network Monitor.

## Fluxo recomendado

1. Crie um fork e uma branch a partir de `main`.
2. Não inclua `.env`, credenciais, bancos locais, logs ou dados reais de rede.
3. Mantenha alterações pequenas e documente decisões relevantes.
4. Execute as validações antes de abrir o pull request:

```bash
cd backend
python -m compileall app

cd ../frontend
npm ci
npm run build
```

5. Descreva no pull request o problema, a solução e como ela foi testada.

## Segurança

Não abra issues públicas contendo senhas, tokens, comunidades SNMP privadas,
endereços sensíveis ou dados de produção. Consulte [SECURITY.md](SECURITY.md).
