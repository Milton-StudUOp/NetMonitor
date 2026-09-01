# Política de segurança

## Segredos

Passwords de bancos e SMTP, tokens de Telegram/WhatsApp e demais credenciais persistidas são protegidos com Fernet usando uma chave derivada de `SECRET_KEY`.

- Use uma `SECRET_KEY` longa, aleatória e estável.
- Alterar a chave invalida os segredos já criptografados.
- Nunca publique `.env`, `.active-database`, bancos locais, certificados ou inventários reais.
- APIs retornam apenas indicadores como `password_configured` e `secrets_configured`.
- Backups não incluem passwords, tokens nem comunidades SNMP.

Exemplo de geração de chave:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Descoberta e monitoramento

Use ICMP, TCP e SNMP somente em redes para as quais exista autorização. Restrinja o acesso administrativo ao NetMonitor e publique a interface atrás de HTTPS e autenticação antes de expô-la fora de uma rede confiável.

## SVG personalizado

Uploads aceitam SVG e PNG até 512 KB. SVG contendo `script`, URI `javascript:` ou declaração de entidade é rejeitado. Recomenda-se revisar visualmente ativos personalizados antes do uso.

## SQL e bancos

- Fontes de dados aceitam uma única instrução iniciada por `SELECT`.
- Resultados são limitados a 100 linhas.
- Use utilizadores de banco com privilégio mínimo.
- A promoção a banco principal exige destino vazio e validação por tabela.
- O SQL Server também exige Microsoft ODBC Driver 18 instalado no sistema operacional.

## Comunicação externa

Telegram e WhatsApp enviam dados ao provider configurado. Não inclua dados sensíveis desnecessários nas mensagens. Para WhatsApp, use somente API oficial ou provider contratualmente autorizado; automação de WhatsApp Web não é suportada.

## Relato de vulnerabilidades

Não publique detalhes exploráveis numa issue. Utilize Security Advisories privados do GitHub ou o canal privado definido pelo mantenedor. Inclua versão, impacto, passos mínimos de reprodução e proposta de mitigação.
