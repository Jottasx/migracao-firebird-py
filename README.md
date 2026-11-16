# Utilitário de Migração Firebird 2.5 para 5.0 (Fortes Tecnologia) - Edição GUI

Solução automatizada desenvolvida em **Python 3.8** com interface gráfica nativa em **Tkinter** (empacotada como executável standalone) para a migração assistida, performática e segura de bases de dados dos sistemas Fortes (**AC, Ponto, AG, Patrio, Cargas e Frota**) do Firebird 2.5 para o Firebird 5.0.

---

## 🚀 Principais Funcionalidades

* **Interface Gráfica Intuitiva e Desacoplada:** Painel em Tkinter com execução em background thread (`threading.Thread` + filas *thread-safe* `queue.Queue`), garantindo responsividade contínua da janela durante toda a operação sem congelamentos (*Não Respondendo*).
* **Fila Dinâmica com Indicadores Visuais:** Gestão de múltiplas bases na mesma sessão (com suporte a seleção múltipla de arquivos) e sinalização visual de estado por linha:
  * ⚪ **Branco:** Na Fila / Aguardando;
  * 🟡 **Amarelo:** Em processamento (Extração de Backup / Restauração);
  * 🟢 **Verde / Negrito:** Concluído com sucesso;
  * 🔴 **Vermelho:** Erro na operação.
* **Monitor GBAK em Tempo Real:** Terminal dedicado com leitura direta de pipe em memória (`subprocess.Popen` com buffer de 64 KB) que exibe o fluxo do `gbak -v` (tabelas lidas, contagem de registros, restauração de índices e metadados).
* **Sistema de Auditoria e Log Centralizado (`.txt`):**
  * Geração automática de arquivo único de log com carimbo de execução em `C:\Fortes\Logs\Migracao_FB25_FB50_yyyyMMdd_HHmmss.txt`.
  * **Persistência total do GBAK:** Grava 100% dos metadados e saídas de tabelas no arquivo de texto com escrita bufferizada de alta performance para resguardo técnico e auditoria contra corrupções pré-existentes na base do cliente.
  * Botão de acesso rápido **`Ver Log (.txt)`** habilitado ao término da rotina para abertura direta no Bloco de Notas.
* **Desinstalação Segura e Resiliente de Serviços Legados:**
  * Remoção primária via utilitário nativo (`instsvc.exe stop/remove -name Fortes_FB2_5`).
  * Varredura e tratamento com tolerância a variações de maiúsculas/minúsculas e sufixos nos serviços `FirebirdServer` e `FirebirdGuardian`.
  * Exclusão limpa via Service Control Manager nativo do Windows (`sc stop` / `sc delete`), garantindo compatibilidade universal desde o Windows Server 2008 R2 até o Server 2025.
* **Manutenção da Porta Unificada (53052):**
  * Backups extraídos diretamente pelo motor do FB 2.5 escutando na porta `53052`.
  * Serviços do FB 2.5 são encerrados/desregistrados e o FB 5.0 assume a mesma porta `53052` (`firebird.conf`).
  * Restauração com tamanho de página otimizado para o padrão moderno (`-p 8192`) e ODS atualizada (ODS 13.x).
  * **Zero reconfiguração em terminais:** Arquivos `.INI` e atalhos nas estações permanecem 100% inalterados.
* **Validação Preventiva de ODS:** Inspeciona os bytes de cabeçalho da base `.fdb` (offset `0x12` / byte `18`) ao adicionar o banco à fila, alertando o operador caso a base já tenha sido migrada previamente para Firebird 5.0.
* **Regra de Firewall Automatizada:** Criação/validação automática de regra de entrada para tráfego TCP na porta `53052` no Firewall do Windows (`netsh advfirewall`).
* **Preservação Padronizada da Base Legada:** A base original do FB 2.5 é renomeada e mantida como salvaguarda na própria pasta do sistema seguindo o padrão oficial:
  * Exemplo: `Backup_AC_25_05_2026_FB_2_5.fdb` (com tratamento de sufixo com hora para execuções múltiplas no mesmo dia).

---

## 📁 Estrutura de Pastas e Arquivos (Distribuição)

```text
MigradorFirebird/
│
├── MigradorFirebird.exe        # Executável principal (com elevação UAC embutida)
├── _internal/                  # Runtime Python 3.8 e bibliotecas gráficas Tkinter
└── Binarios/
    └── Firebird_5_0.zip        # Pacote com os binários portáteis do Firebird 5.0