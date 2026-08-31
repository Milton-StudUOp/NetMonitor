# Política de segurança

## Dados que nunca devem ser publicados

- Arquivos `.env` reais.
- Senhas de banco, SMTP ou Redis.
- Tokens de Telegram, Teams ou outros webhooks.
- Chaves privadas e certificados.
- Bancos SQLite e inventários reais de rede.
- Comunidades SNMP privadas.

Use apenas valores fictícios nos arquivos `.env.example`.

## Relato de vulnerabilidades

Não publique detalhes exploráveis em uma issue aberta. Use o recurso privado
de Security Advisories do GitHub no repositório que hospedar este projeto.
