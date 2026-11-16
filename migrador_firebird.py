# -*- coding: utf-8 -*-
"""
Migrador Firebird 2.5 para 5.0 (Fortes Tecnologia) - Versão Python (Tkinter)
Sistemas suportados: AC, Ponto, AG, Patrio, Cargas e Frota.
Compatível com Python 3.7 / 3.8 (Windows Server 2008 / 2008 R2 / 2012 R2 / 2016+)
"""

import os
import re
import sys
import time
import shutil
import zipfile
import queue
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def obter_diretorio_base():
    """Retorna o diretório do script ou do executável gerado pelo PyInstaller."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class MigradorFirebirdApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Migrador Firebird 2.5 -> 5.0 (Fortes Tecnologia)")
        self.root.geometry("820x775")
        self.root.resizable(False, False)
        self.centralizar_janela(820, 775)

        self.script_dir = obter_diretorio_base()

        # Configuração de Diretório e Log Único
        self.diretorio_logs = r"C:\Fortes\Logs"
        os.makedirs(self.diretorio_logs, exist_ok=True)
        data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.caminho_arquivo_log = os.path.join(
            self.diretorio_logs, f"Migracao_FB25_FB50_{data_hora}.txt"
        )

        # Filas Thread-Safe para comunicação entre Worker e UI
        self.log_queue = queue.Queue()
        self.gbak_queue = queue.Queue()
        self.item_updates = queue.Queue()
        self.status_text = ""
        self.progress = 0
        self.max_progress = 100
        self.concluido = False
        self.erro = None
        self.em_execucao = False

        self.configurar_estilos()
        self.construir_interface()

    def centralizar_janela(self, largura, altura):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (largura // 2)
        y = (self.root.winfo_screenheight() // 2) - (altura // 2)
        self.root.geometry(f"{largura}x{altura}+{x}+{y}")

    def configurar_estilos(self):
        self.style = ttk.Style()
        # Usa tema nativo do Windows ('vista' ou 'winnative' no Server 2008/2012)
        for tema in ("vista", "winnative", "clam"):
            if tema in self.style.theme_names():
                self.style.theme_use(tema)
                break

        # Correção oficial para o bug do Tkinter/Tk 8.6 onde tag_configure
        # ignora background/foreground nos temas 'vista' e 'winnative'
        def fixed_map(option):
            return [
                elm for elm in self.style.map("Treeview", query_opt=option)
                if elm[:2] != ("!disabled", "!selected")
            ]

        self.style.map(
            "Treeview",
            foreground=fixed_map("foreground"),
            background=fixed_map("background"),
        )

        self.font_padrao = ("Segoe UI", 9)
        self.font_titulo = ("Segoe UI", 10, "bold")
        self.font_gbak = ("Consolas", 8)

        self.style.configure("Treeview", font=self.font_padrao, rowheight=22)
        self.style.configure("Treeview.Heading", font=self.font_padrao)

    def construir_interface(self):
        # 1. Seção: Fila de Bancos
        grp_bancos = tk.LabelFrame(
            self.root, text="Fila de Bancos Selecionados para Migração", font=self.font_padrao
        )
        grp_bancos.place(x=15, y=10, width=790, height=160)

        # Tabela (Treeview) + Scrollbar
        frame_lista = tk.Frame(grp_bancos)
        frame_lista.place(x=15, y=10, width=630, height=125)

        colunas = ("sistema", "status", "caminho")
        self.lista_bancos = ttk.Treeview(
            frame_lista, columns=colunas, show="headings", selectmode="extended"
        )
        self.lista_bancos.heading("sistema", text="Sistema", anchor="w")
        self.lista_bancos.heading("status", text="Status", anchor="w")
        self.lista_bancos.heading("caminho", text="Caminho do Banco (.FDB)", anchor="w")

        self.lista_bancos.column("sistema", width=75, minwidth=75, stretch=False)
        self.lista_bancos.column("status", width=135, minwidth=135, stretch=False)
        self.lista_bancos.column("caminho", width=400, minwidth=200, stretch=True)

        scroll_lista = ttk.Scrollbar(frame_lista, orient="vertical", command=self.lista_bancos.yview)
        self.lista_bancos.configure(yscrollcommand=scroll_lista.set)

        self.lista_bancos.pack(side="left", fill="both", expand=True)
        scroll_lista.pack(side="right", fill="y")

        # Cores por status na tabela (Tags)
        self.lista_bancos.tag_configure("Processando", background="#FFF9C4", foreground="#644600")
        self.lista_bancos.tag_configure(
            "Concluido", background="#C8E6C9", foreground="#1B5E20", font=("Segoe UI", 9, "bold")
        )
        self.lista_bancos.tag_configure("Erro", background="#FFCDD2", foreground="#B71C1C")
        self.lista_bancos.tag_configure("Normal", background="#FFFFFF", foreground="#000000")

        # Botões da Fila
        self.btn_adicionar = tk.Button(
            grp_bancos, text="Adicionar...", font=self.font_padrao, command=self.adicionar_banco
        )
        self.btn_adicionar.place(x=655, y=10, width=115, height=30)

        self.btn_remover = tk.Button(
            grp_bancos, text="Remover", font=self.font_padrao, command=self.remover_banco
        )
        self.btn_remover.place(x=655, y=44, width=115, height=30)

        self.btn_iniciar = tk.Button(
            grp_bancos,
            text="INICIAR",
            font=self.font_titulo,
            bg="#2E7D32",
            fg="#FFFFFF",
            activebackground="#1B5E20",
            activeforeground="#FFFFFF",
            relief="flat",
            command=self.iniciar_migracao,
        )
        self.btn_iniciar.place(x=655, y=84, width=115, height=51)

        # 2. Seção: Progresso e Etapa Atual
        grp_progresso = tk.LabelFrame(
            self.root, text="Status da Operação", font=self.font_padrao
        )
        grp_progresso.place(x=15, y=175, width=790, height=85)

        self.lbl_status = tk.Label(
            grp_progresso,
            text="Aguardando seleção de bases para iniciar...",
            font=self.font_titulo,
            anchor="w",
        )
        self.lbl_status.place(x=15, y=8, width=630, height=22)

        self.btn_abrir_log = tk.Button(
            grp_progresso,
            text="Ver Log (.txt)",
            font=self.font_padrao,
            state="disabled",
            command=self.abrir_log,
        )
        self.btn_abrir_log.place(x=655, y=6, width=115, height=25)

        self.progress_bar = ttk.Progressbar(
            grp_progresso, orient="horizontal", mode="determinate"
        )
        self.progress_bar.place(x=15, y=36, width=755, height=22)

        # 3. Seção: Monitor em Tempo Real do GBAK
        grp_gbak = tk.LabelFrame(
            self.root,
            text="Acompanhamento do GBAK em Tempo Real (Tabelas e Índices)",
            font=self.font_padrao,
        )
        grp_gbak.place(x=15, y=265, width=790, height=210)

        frame_gbak = tk.Frame(grp_gbak)
        frame_gbak.place(x=15, y=10, width=755, height=175)

        self.txt_gbak = tk.Text(
            frame_gbak,
            bg="#141419",
            fg="#00FFFF",
            font=self.font_gbak,
            state="disabled",
            wrap="none",
        )
        scroll_gbak = ttk.Scrollbar(frame_gbak, orient="vertical", command=self.txt_gbak.yview)
        self.txt_gbak.configure(yscrollcommand=scroll_gbak.set)
        self.txt_gbak.pack(side="left", fill="both", expand=True)
        scroll_gbak.pack(side="right", fill="y")

        # 4. Seção: Log Geral do Sistema
        grp_logs = tk.LabelFrame(
            self.root, text="Log Geral de Operações", font=self.font_padrao
        )
        grp_logs.place(x=15, y=480, width=790, height=220)

        frame_logs = tk.Frame(grp_logs)
        frame_logs.place(x=15, y=10, width=755, height=185)

        self.txt_logs = tk.Text(
            frame_logs,
            bg="#000000",
            fg="#D3D3D3",
            font=self.font_gbak,
            state="disabled",
            wrap="word",
        )
        scroll_logs = ttk.Scrollbar(frame_logs, orient="vertical", command=self.txt_logs.yview)
        self.txt_logs.configure(yscrollcommand=scroll_logs.set)
        self.txt_logs.pack(side="left", fill="both", expand=True)
        scroll_logs.pack(side="right", fill="y")

        # 5. Rodapé: Créditos
        lbl_creditos = tk.Label(
            self.root,
            text="Desenvolvido por Pedro Mesquita (pedromesquita@fortestecnologia.com.br)",
            font=("Segoe UI", 8, "italic"),
            fg="gray",
            anchor="e",
        )
        lbl_creditos.place(x=15, y=708, width=790, height=20)

    # --- EVENTOS DA INTERFACE ---
    def abrir_log(self):
        if os.path.exists(self.caminho_arquivo_log):
            subprocess.Popen(["notepad.exe", self.caminho_arquivo_log])

    def detectar_sistema(self, caminho):
        nome = os.path.splitext(os.path.basename(caminho))[0]
        minusculo = caminho.lower()

        if "ponto" in nome.lower() or "\\ponto\\" in minusculo:
            return "Ponto"
        elif "patrio" in nome.lower() or "\\patrio\\" in minusculo:
            return "Patrio"
        elif "cargas" in nome.lower() or "\\cargas\\" in minusculo:
            return "Cargas"
        elif "frota" in nome.lower() or "\\frota\\" in minusculo:
            return "Frota"
        elif re.search(r"(^|_)AG($|_)", nome, re.IGNORECASE) or "\\ag\\" in minusculo:
            return "AG"
        return "AC"

    def adicionar_banco(self):
        dir_inicial = r"C:\Fortes" if os.path.exists(r"C:\Fortes") else "C:\\"
        caminhos = filedialog.askopenfilenames(
            title="Selecione a base Firebird (.FDB)",
            initialdir=dir_inicial,
            filetypes=[("Banco Firebird (*.fdb)", "*.fdb"), ("Todos os Arquivos (*.*)", "*.*")],
        )

        for caminho in caminhos:
            caminho_norm = os.path.normpath(caminho)
            sistema = self.detectar_sistema(caminho_norm)

            # Validação preventiva de ODS (Byte 18 do cabeçalho do Firebird)
            try:
                with open(caminho_norm, "rb") as f:
                    buf = f.read(32)
                    if len(buf) >= 19 and buf[18] >= 13:
                        res = messagebox.askyesno(
                            "Aviso",
                            f"A base de dados selecionada ({os.path.basename(caminho_norm)}) já está no formato "
                            f"do Firebird 5.0 (ODS {buf[18]}).\nDeseja incluí-la mesmo assim?",
                            icon="warning",
                        )
                        if not res:
                            continue
            except Exception:
                pass

            self.lista_bancos.insert(
                "", "end", values=(sistema, "Aguardando...", caminho_norm), tags=("Normal",)
            )

    def remover_banco(self):
        for item_id in self.lista_bancos.selection():
            self.lista_bancos.delete(item_id)

    def iniciar_migracao(self):
        itens = self.lista_bancos.get_children()
        if not itens:
            messagebox.showwarning(
                "Atenção", "Selecione pelo menos uma base na fila antes de iniciar."
            )
            return

        confirmar = messagebox.askyesno(
            "Confirmar Início",
            f"Deseja iniciar a migração de {len(itens)} base(s)?\n"
            "Certifique-se de que os sistemas estão fechados nos terminais.",
        )
        if not confirmar:
            return

        self.btn_adicionar.config(state="disabled")
        self.btn_remover.config(state="disabled")
        self.btn_iniciar.config(state="disabled")
        self.btn_abrir_log.config(state="disabled")

        self.limpar_texto(self.txt_logs)
        self.limpar_texto(self.txt_gbak)

        fila = []
        for item_id in itens:
            valores = list(self.lista_bancos.item(item_id, "values"))
            sistema = valores[0]
            caminho = valores[2]
            diretorio = os.path.dirname(caminho)

            self.lista_bancos.item(item_id, values=(sistema, "Na Fila", caminho), tags=("Normal",))

            fila.append({
                "item_id": item_id,
                "sistema": sistema,
                "banco_origem": caminho,
                "diretorio": diretorio,
                "arquivo_backup_temp": os.path.join(diretorio, f"temp_migracao_{sistema}.fbk"),
                "arquivo_banco_novo": os.path.join(diretorio, f"temp_fb50_{sistema}.fdb"),
                "arquivo_banco_final": os.path.join(diretorio, f"{sistema}.fdb"),
            })

        self.concluido = False
        self.erro = None
        self.progress = 0
        # 1 (Preparo FB5) + N (Backups) + 1 (Transição Motores) + N (Restaurações)
        self.max_progress = 2 + (len(fila) * 2)
        self.status_text = "Iniciando checagens de ambiente..."
        self.em_execucao = True

        # Inicia a thread de trabalho em segundo plano
        worker_thread = threading.Thread(target=self.worker_migracao, args=(fila,), daemon=True)
        worker_thread.start()

        # Inicia o loop de atualização da UI a cada 150ms (equivalente ao Timer do WinForms)
        self.root.after(150, self.atualizar_ui_timer)

    def limpar_texto(self, widget):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.config(state="disabled")

    def append_texto(self, widget, texto, limitar_tamanho=False):
        widget.config(state="normal")
        if limitar_tamanho:
            conteudo = widget.get("1.0", "end-1c")
            if len(conteudo) > 30000:
                widget.delete("1.0", "end")
                widget.insert("end", conteudo[-15000:])
        widget.insert("end", texto)
        widget.see("end")
        widget.config(state="disabled")

    def atualizar_ui_timer(self):
        if self.status_text:
            self.lbl_status.config(text=self.status_text)

        self.progress_bar["maximum"] = self.max_progress
        self.progress_bar["value"] = min(self.progress, self.max_progress)

        # 1. Drena logs gerais
        logs_lote = []
        while not self.log_queue.empty():
            try:
                logs_lote.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if logs_lote:
            self.append_texto(self.txt_logs, "\n".join(logs_lote) + "\n")

        # 2. Drena saída do GBAK
        gbak_lote = []
        while not self.gbak_queue.empty():
            try:
                gbak_lote.append(self.gbak_queue.get_nowait())
            except queue.Empty:
                break
        if gbak_lote:
            self.append_texto(self.txt_gbak, "\n".join(gbak_lote) + "\n", limitar_tamanho=True)

        # 3. Drena atualizações de status da tabela
        while not self.item_updates.empty():
            try:
                up = self.item_updates.get_nowait()
                item_id = up["item_id"]
                if self.lista_bancos.exists(item_id):
                    vals = list(self.lista_bancos.item(item_id, "values"))
                    vals[1] = up["status"]
                    self.lista_bancos.item(item_id, values=vals, tags=(up["tipo"],))
            except queue.Empty:
                break

        if self.concluido:
            self.em_execucao = False
            self.btn_adicionar.config(state="normal")
            self.btn_remover.config(state="normal")
            self.btn_iniciar.config(state="normal")
            if os.path.exists(self.caminho_arquivo_log):
                self.btn_abrir_log.config(state="normal")

            if self.erro:
                messagebox.showerror("Erro", f"A migração falhou:\n{self.erro}")
            else:
                messagebox.showinfo(
                    "Sucesso",
                    f"Processo de migração concluído com sucesso!\nArquivo de log gerado em:\n{self.caminho_arquivo_log}",
                )
        else:
            self.root.after(150, self.atualizar_ui_timer)

    # --- ROTINAS DO WORKER (THREAD SECUNDÁRIA) ---
    def log(self, txt):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entrada = f"[{timestamp}] {txt}"
        self.log_queue.put(entrada)
        try:
            with open(self.caminho_arquivo_log, "a", encoding="utf-8") as f:
                f.write(entrada + "\n")
        except Exception:
            pass

    def executar_comando_oculto(self, cmd_lista):
        """Executa comandos do Windows sem piscar janela preta do CMD."""
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return subprocess.run(
            cmd_lista,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            text=True,
            encoding="mbcs",  # Encoding nativo do Windows (CP1252)
            errors="replace",
        )

    def executar_gbak_com_monitor(self, executavel, args_lista, tipo_operacao, nome_sistema):
        self.log(f"Iniciando execução do GBAK ({tipo_operacao}) para {nome_sistema}...")

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        cmd = [executavel] + args_lista
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo,
            bufsize=65536,  # Buffer de 64KB para leitura em alta velocidade
            universal_newlines=True,
            encoding="mbcs",
            errors="replace",
        )

        # Abre o arquivo de log UMA ÚNICA VEZ com buffer de 64KB (elimina gargalo de disco/antivírus)
        with open(self.caminho_arquivo_log, "a", encoding="utf-8", buffering=65536) as log_file:
            ultimo_envio_ui = time.monotonic()
            lote_ui = []

            for linha in proc.stdout:
                linha_limpa = linha.rstrip("\r\n")
                if not linha_limpa:
                    continue

                # Grava direto no buffer em memória (flush automático a cada 64KB)
                log_file.write(f"[GBAK] {linha_limpa}\n")
                lote_ui.append(linha_limpa)

                # Envia para a tela em blocos a cada 150ms (mantém apenas as últimas 200 linhas do lote)
                agora = time.monotonic()
                if agora - ultimo_envio_ui >= 0.15:
                    if lote_ui:
                        self.gbak_queue.put("\n".join(lote_ui[-200:]))
                        lote_ui.clear()
                    ultimo_envio_ui = agora

            # Envia o restante residual para a tela
            if lote_ui:
                self.gbak_queue.put("\n".join(lote_ui[-200:]))

        proc.stdout.close()
        exit_code = proc.wait()
        self.log(f"Finalizado GBAK ({tipo_operacao}) para {nome_sistema} com código de saída: {exit_code}")
        return exit_code

    def parar_e_desinstalar_servicos_fb25(self, pasta_fb25):
        self.log("Procurando variações dos serviços Firebird 2.5 da Fortes...")

        inst_svc25 = os.path.join(pasta_fb25, "bin", "instsvc.exe")
        instancia = "Fortes_FB2_5"

        if os.path.exists(inst_svc25):
            self.log("Executando parada e desinstalação via instsvc.exe...")
            self.executar_comando_oculto([inst_svc25, "stop", "-name", instancia])
            self.executar_comando_oculto([inst_svc25, "remove", "-name", instancia])

        # Lista todos os serviços via 'sc query' (compatível com Windows Server 2008 até 2025)
        res = self.executar_comando_oculto(["sc", "query", "type=", "service", "state=", "all"])
        nomes_servicos = re.findall(r"SERVICE_NAME:\s*(.+)", res.stdout)

        for nome_svc in nomes_servicos:
            nome_svc = nome_svc.strip()
            nome_lower = nome_svc.lower()
            if ("firebird" in nome_lower and "fortes" in nome_lower and "fb2" in nome_lower) or (
                "fortes_fb2_5" in nome_lower
            ):
                self.log(f"Processando serviço: {nome_svc}")
                self.executar_comando_oculto(["sc", "stop", nome_svc])
                time.sleep(2)
                del_res = self.executar_comando_oculto(["sc", "delete", nome_svc])
                if del_res.returncode == 0:
                    self.log(f"Serviço {nome_svc} removido com sucesso.")
                else:
                    self.log(f"Aviso ao remover {nome_svc}: {del_res.stdout.strip()}")

    def verificar_servico_rodando(self, nome_servico):
        res = self.executar_comando_oculto(["sc", "query", nome_servico])
        return "RUNNING" in res.stdout

    def worker_migracao(self, fila):
        try:
            usuario_win = os.environ.get("USERNAME", "Desconhecido")
            computador = os.environ.get("COMPUTERNAME", "Local")

            self.log("==========================================================")
            self.log("INÍCIO DO PROCESSO DE MIGRAÇÃO: FB 2.5 -> FB 5.0")
            self.log(f"Usuário Atual: {usuario_win} em {computador}")
            self.log(f"Arquivo de Registro: {self.caminho_arquivo_log}")
            self.log("==========================================================")

            pasta_destino_fb50 = r"C:\Fortes\Firebird\Firebird_5_0"
            pasta_destino_fb25 = r"C:\Fortes\Firebird\Firebird_2_5"
            zip_origem_fb50 = os.path.join(self.script_dir, "Binarios", "Firebird_5_0.zip")

            caminho_fb25_gbak = os.path.join(pasta_destino_fb25, "bin", "gbak.exe")
            caminho_fb50_gbak = os.path.join(pasta_destino_fb50, "gbak.exe")
            caminho_fb50_instsvc = os.path.join(pasta_destino_fb50, "instsvc.exe")
            caminho_fb50_instreg = os.path.join(pasta_destino_fb50, "instreg.exe")

            porta_padrao = "53052"
            usuario_fb = "SYSDBA"
            senha_fb = "masterkey"
            nome_instancia_fb50 = "Fortes_FB5_0"
            servico_fb50_server = f"FirebirdServer{nome_instancia_fb50}"

            # 1. Configuração do FB 5.0
            self.status_text = "Etapa 1: Preparando o Firebird 5.0..."
            self.log("Checando binários do Firebird 5.0...")

            if not os.path.exists(caminho_fb50_gbak):
                if not os.path.exists(zip_origem_fb50):
                    raise FileNotFoundError(f"Pacote ZIP não encontrado em: {zip_origem_fb50}")
                self.log(f"Extraindo binários para {pasta_destino_fb50}...")
                os.makedirs(pasta_destino_fb50, exist_ok=True)
                with zipfile.ZipFile(zip_origem_fb50, "r") as zip_ref:
                    zip_ref.extractall(pasta_destino_fb50)
                self.log("Extração finalizada com sucesso.")

            if os.path.exists(caminho_fb50_instreg):
                self.executar_comando_oculto([caminho_fb50_instreg, "install", pasta_destino_fb50])

            # Verifica se serviço FB 5.0 já existe
            check_svc = self.executar_comando_oculto(["sc", "query", servico_fb50_server])
            if check_svc.returncode != 0:
                self.log(f"Registrando serviço do Firebird 5.0 ({nome_instancia_fb50})...")
                self.executar_comando_oculto(
                    [caminho_fb50_instsvc, "install", "-auto", "-name", nome_instancia_fb50]
                )
                time.sleep(2)

            self.log(f"Garantindo regra de porta {porta_padrao} no Firewall do Windows...")
            nome_regra = f"Firebird Fortes (Porta {porta_padrao})"
            self.executar_comando_oculto(
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={nome_regra}"]
            )
            self.executar_comando_oculto([
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={nome_regra}", "dir=in", "action=allow",
                "protocol=TCP", f"localport={porta_padrao}", "profile=any"
            ])
            self.log(f"Firewall liberado para a porta {porta_padrao}.")
            self.progress += 1

            # 2. Backups via FB 2.5
            self.log("Reiniciando Firebird 2.5 para fechar conexões ativas...")
            res_svcs = self.executar_comando_oculto(["sc", "query", "type=", "service", "state=", "all"])
            for svc in re.findall(r"SERVICE_NAME:\s*(.+)", res_svcs.stdout):
                svc = svc.strip()
                if ("firebird" in svc.lower() and "2_5" in svc.lower()) or "fortes_fb2_5" in svc.lower():
                    self.executar_comando_oculto(["sc", "stop", svc])
                    time.sleep(2)
                    self.executar_comando_oculto(["sc", "start", svc])
                    time.sleep(2)

            for item in fila:
                sistema = item["sistema"]
                self.status_text = f"Extraindo backup do sistema: {sistema}..."
                self.log(f"Iniciando processo de backup da base: {item['banco_origem']}")
                self.item_updates.put({
                    "item_id": item["item_id"],
                    "status": "Extraindo Backup...",
                    "tipo": "Processando",
                })

                conexao_fb25 = f"localhost/{porta_padrao}:{item['banco_origem']}"
                args_gbak = [
                    "-b", "-v", "-g",
                    conexao_fb25,
                    item["arquivo_backup_temp"],
                    "-user", usuario_fb,
                    "-password", senha_fb,
                ]

                exit_code = self.executar_gbak_com_monitor(
                    caminho_fb25_gbak, args_gbak, "BACKUP", sistema
                )

                if exit_code != 0 or not os.path.exists(item["arquivo_backup_temp"]):
                    self.item_updates.put({
                        "item_id": item["item_id"],
                        "status": "Erro no Backup",
                        "tipo": "Erro",
                    })
                    raise RuntimeError(
                        f"Falha crítica ao extrair backup da base {sistema}. Código de saída do GBAK: {exit_code}."
                    )

                self.log(f"Backup do {sistema} finalizado com sucesso no arquivo {item['arquivo_backup_temp']}.")
                self.item_updates.put({
                    "item_id": item["item_id"],
                    "status": "Backup Concluído",
                    "tipo": "Processando",
                })
                self.progress += 1

            # 3. Transição de Motores
            self.status_text = f"Realizando transição de motores na porta {porta_padrao}..."
            self.parar_e_desinstalar_servicos_fb25(pasta_destino_fb25)

            self.log(f"Iniciando serviço do Firebird 5.0 na porta {porta_padrao}...")
            self.executar_comando_oculto(["sc", "start", servico_fb50_server])
            time.sleep(3)

            if not self.verificar_servico_rodando(servico_fb50_server):
                raise RuntimeError(
                    f"O serviço Firebird 5.0 não conseguiu iniciar na porta {porta_padrao}."
                )

            self.log(f"Firebird 5.0 operacional e escutando na porta {porta_padrao}.")
            self.progress += 1

            # 4. Restaurações via FB 5.0
            for item in fila:
                sistema = item["sistema"]
                self.status_text = f"Restaurando base do sistema: {sistema}..."
                self.log(f"Iniciando restauração da base {sistema} (ODS 13.x, Page Size 8192)...")
                self.item_updates.put({
                    "item_id": item["item_id"],
                    "status": "Restaurando...",
                    "tipo": "Processando",
                })

                if os.path.exists(item["arquivo_banco_novo"]):
                    os.remove(item["arquivo_banco_novo"])

                conexao_fb50 = f"localhost/{porta_padrao}:{item['arquivo_banco_novo']}"
                args_restore = [
                    "-c", "-v", "-p", "8192",
                    item["arquivo_backup_temp"],
                    conexao_fb50,
                    "-user", usuario_fb,
                    "-password", senha_fb,
                ]

                exit_code = self.executar_gbak_com_monitor(
                    caminho_fb50_gbak, args_restore, "RESTORE", sistema
                )

                if exit_code != 0 or not os.path.exists(item["arquivo_banco_novo"]):
                    self.item_updates.put({
                        "item_id": item["item_id"],
                        "status": "Erro no Restore",
                        "tipo": "Erro",
                    })
                    raise RuntimeError(
                        f"Falha crítica ao restaurar {sistema} no Firebird 5.0. Código de saída do GBAK: {exit_code}."
                    )

                if os.path.exists(item["arquivo_backup_temp"]):
                    os.remove(item["arquivo_backup_temp"])

                # Preservação da base legado
                if os.path.exists(item["arquivo_banco_final"]):
                    data_fmt = datetime.now().strftime("%d_%m_%Y")
                    dir_banco = item["diretorio"]
                    nome_bkp_padrao = f"Backup_{sistema}_{data_fmt}_FB_2_5.fdb"
                    caminho_bkp_final = os.path.join(dir_banco, nome_bkp_padrao)

                    if os.path.exists(caminho_bkp_final):
                        hora_fmt = datetime.now().strftime("%H%M%S")
                        nome_bkp_padrao = f"Backup_{sistema}_{data_fmt}_{hora_fmt}_FB_2_5.fdb"
                        caminho_bkp_final = os.path.join(dir_banco, nome_bkp_padrao)

                    os.rename(item["arquivo_banco_final"], caminho_bkp_final)
                    self.log(f"Base legado de segurança preservada como: {nome_bkp_padrao}")

                shutil.move(item["arquivo_banco_novo"], item["arquivo_banco_final"])
                self.log(f"Base {sistema} migrada com sucesso disponível em: {item['arquivo_banco_final']}")

                self.item_updates.put({
                    "item_id": item["item_id"],
                    "status": "Concluído [OK]",
                    "tipo": "Concluido",
                })
                self.progress += 1

            self.progress = self.max_progress
            self.status_text = "Migração concluída com sucesso!"
            self.log("==========================================================")
            self.log("MIGRAÇÃO FINALIZADA COM SUCESSO.")
            self.log("==========================================================")

        except Exception as e:
            self.erro = str(e)
            self.log(f"[FALHA CRÍTICA] {self.erro}")
            self.status_text = "Erro durante o processamento."
        finally:
            self.concluido = True


if __name__ == "__main__":
    root = tk.Tk()
    app = MigradorFirebirdApp(root)
    root.mainloop()