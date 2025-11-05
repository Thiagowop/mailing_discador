# Integração 3C Plus – Visão Rápida

Scripts e utilitários para extrair mailings do banco **Candiotto_std** e atualizar campanhas no discador 3C Plus.

## Como usar

1. Copie `.env.template` para `.env` e preencha credenciais de banco e API.  
   - Defina as campanhas alvo em `THREECPLUS_TARGET_CAMPAIGNS` (separadas por vírgula).
2. Execute `fluxo_completo.bat` para rodar extração + atualização automática **ou** abra o menu `pipeline_fluxo.bat`.
3. Consulte os logs em `logs/3cplus.log` / `logs/error.log` para diagnóstico.

## Documentação completa

Todos os detalhes técnicos, fluxos, endpoints e troubleshooting estão em `docs/integracao_3cplus.md`.
