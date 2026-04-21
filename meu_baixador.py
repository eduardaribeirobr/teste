import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yt_dlp
import threading
import os
import re
import json

# ---------------------------------------------------------------------------
# Paleta de cores (tema escuro)
# ---------------------------------------------------------------------------
BG         = "#0d0d17"   # fundo geral
PANEL      = "#13131f"   # cabeçalho / painéis
CARD       = "#1a1a2e"   # cartões internos
INPUT_BG   = "#161628"   # fundo dos campos de texto
INPUT_DIS  = "#101020"   # campo desabilitado
BORDER     = "#252545"   # borda padrão
ACCENT     = "#6366f1"   # índigo — cor de destaque
ACCENT_H   = "#818cf8"   # hover do destaque
ACCENT_A   = "#4338ca"   # pressionado
SUCCESS    = "#4ade80"   # verde
ERROR      = "#f87171"   # vermelho
WARNING    = "#fbbf24"   # amarelo / laranja
DANGER     = "#dc2626"   # vermelho cancelar
DANGER_H   = "#ef4444"   # hover cancelar
TEXT       = "#e2e8f0"   # texto principal
MUTED      = "#94a3b8"   # texto secundário
DIM        = "#4a5568"   # texto desabilitado / inativo

# ---------------------------------------------------------------------------
# Config persistente
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.meu_baixador_config.json')


def carregar_config():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def salvar_config(dados):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_cfg = carregar_config()

# ---------------------------------------------------------------------------
# Variáveis globais
# ---------------------------------------------------------------------------
janela = None
progress_bar = None
status_label = None
download_button = None
cancel_button = None
titulo_entry = None
url_entry = None
pasta_label = None

g_info_dict = None
g_last_url = ""
g_download_count = 0
g_cancel_requested = False
g_pasta_download = _cfg.get(
    'pasta_download', os.path.join(os.path.expanduser('~'), 'Downloads')
)


class DownloadCancelado(Exception):
    pass


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def sanitizar_nome(nome):
    return re.sub(r'[\\/*?:"<>|]', "", nome).strip()


def limpar_titulo(titulo):
    padroes = [
        r'\s*[\(\[]\s*[Oo]fficial\s*[Mm]usic\s*[Vv]ideo\s*[\)\]]',
        r'\s*[\(\[]\s*[Oo]fficial\s*[Vv]ideo\s*[\)\]]',
        r'\s*[\(\[]\s*[Oo]fficial\s*[Aa]udio\s*[\)\]]',
        r'\s*[\(\[]\s*[Ll]yrics?\s*(?:[Vv]ideo)?\s*[\)\]]',
        r'\s*[\(\[]\s*[Aa]udio\s*[\)\]]',
        r'\s*[\(\[]\s*[Hh][Dd]\s*[\)\]]',
        r'\s*[\(\[]\s*4[Kk]\s*[\)\]]',
        r'\s*[\(\[]\s*[Cc]lip\s*[Oo]ficial\s*[\)\]]',
        r'\s*\|\s*.+$',
        r'\s*//\s*.+$',
    ]
    for p in padroes:
        titulo = re.sub(p, '', titulo)
    return titulo.strip()


def formatar_bytes(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB/s"
    return f"{n / 1_000:.0f} KB/s"


def formatar_eta(seg):
    if seg >= 60:
        return f"ETA {seg // 60}m{seg % 60:02d}s"
    return f"ETA {seg}s"


def exibir_pasta(caminho):
    return caminho if len(caminho) <= 48 else "…" + caminho[-45:]


# ---------------------------------------------------------------------------
# Lógica de UI
# ---------------------------------------------------------------------------

def resetar_ui():
    global g_last_url
    url_entry.delete(0, tk.END)
    titulo_entry.config(state="normal")
    titulo_entry.delete(0, tk.END)
    titulo_entry.config(state="disabled")
    download_button.config(state="disabled")
    cancel_button.config(state="disabled")
    status_label.config(text="Aguardando URL…", foreground=DIM)
    progress_bar.stop()
    progress_bar.config(mode='determinate', value=0)
    g_last_url = ""
    url_entry.focus()


def escolher_pasta():
    global g_pasta_download
    pasta = filedialog.askdirectory(
        initialdir=g_pasta_download, title="Escolha a pasta de destino"
    )
    if pasta:
        g_pasta_download = pasta
        pasta_label.config(text=exibir_pasta(pasta))
        salvar_config({'pasta_download': pasta})


def cancelar_download():
    global g_cancel_requested
    g_cancel_requested = True
    status_label.config(text="Cancelando…", foreground=WARNING)
    cancel_button.config(state="disabled")


# ---------------------------------------------------------------------------
# Thread: busca de informações
# ---------------------------------------------------------------------------

def executar_busca_automatica(url):
    janela.after(0, lambda: [
        status_label.config(text="Buscando informações…", foreground=ACCENT_H),
        progress_bar.config(mode='indeterminate'),
        progress_bar.start(10),
        download_button.config(state="disabled"),
    ])

    try:
        ydl_opts_busca = {
            'noplaylist': True,
            'quiet': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }
        with yt_dlp.YoutubeDL(ydl_opts_busca) as ydl:
            info = ydl.extract_info(url, download=False)

        global g_info_dict
        g_info_dict = info

        original = info.get('title', 'Título Desconhecido')
        for sep in (' - ', ' – '):
            parts = original.split(sep, 1)
            if len(parts) == 2:
                titulo = parts[1].strip()
                break
        else:
            titulo = original

        titulo = limpar_titulo(titulo)

        def atualizar():
            titulo_entry.config(state="normal")
            titulo_entry.delete(0, tk.END)
            titulo_entry.insert(0, titulo)
            download_button.config(state="normal")
            status_label.config(text="Pronto! Edite o nome se necessário.", foreground=SUCCESS)
            progress_bar.stop()
            progress_bar.config(mode='determinate', value=0)
            titulo_entry.focus_set()
            titulo_entry.icursor(tk.END)

        janela.after(0, atualizar)

    except Exception as e:
        def erro():
            progress_bar.stop()
            progress_bar.config(mode='determinate', value=0)
            status_label.config(text="Erro ao buscar URL. Verifique o link.", foreground=ERROR)
            messagebox.showerror(
                "Erro na Busca",
                f"Não foi possível obter informações da URL.\n"
                f"Verifique o link ou sua conexão.\n\nErro: {e}",
            )
        janela.after(0, erro)


# ---------------------------------------------------------------------------
# Hook de progresso
# ---------------------------------------------------------------------------

def download_hook(d):
    if g_cancel_requested:
        raise DownloadCancelado("Cancelado pelo usuário")

    if d['status'] == 'downloading':
        total  = d.get('total_bytes') or d.get('total_bytes_estimate')
        baixado = d.get('downloaded_bytes', 0)
        speed  = d.get('speed')
        eta    = d.get('eta')

        partes = []
        pct = None
        if total and baixado:
            pct = (baixado / total) * 100
            partes.append(f"{pct:.1f}%")
        if speed:
            partes.append(formatar_bytes(speed))
        if eta:
            partes.append(formatar_eta(eta))

        texto = "Baixando: " + "  •  ".join(partes) if partes else "Baixando…"

        def atualizar(p=pct, t=texto):
            if p is not None:
                progress_bar.config(value=p)
            status_label.config(text=t, foreground=ACCENT_H)

        janela.after(0, atualizar)

    elif d['status'] == 'processing':
        janela.after(0, lambda: [
            progress_bar.config(mode='indeterminate'),
            progress_bar.start(10),
            status_label.config(text="Convertendo para MP3…", foreground=ACCENT_H),
        ])

    elif d['status'] == 'finished':
        janela.after(0, lambda: [
            progress_bar.stop(),
            progress_bar.config(mode='determinate', value=100),
            status_label.config(text="Finalizando…", foreground=ACCENT_H),
        ])


# ---------------------------------------------------------------------------
# Thread: download
# ---------------------------------------------------------------------------

def executar_download(titulo_final):
    global g_download_count, g_cancel_requested

    g_cancel_requested = False

    janela.after(0, lambda: [
        status_label.config(text="Iniciando download…", foreground=ACCENT_H),
        download_button.config(state="disabled"),
        cancel_button.config(state="normal"),
        progress_bar.config(mode='determinate', value=0),
    ])

    sucesso  = False
    cancelado = False
    title_safe = sanitizar_nome(titulo_final)

    try:
        caminho_template = os.path.join(g_pasta_download, title_safe + '.%(ext)s')

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': caminho_template,
            'noplaylist': True,
            'progress_hooks': [download_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '0',  # VBR melhor qualidade (~220-260kbps)
            }],
            'postprocessor_args': {
                'ffmpegextractaudio': ['-compression_level', '9'],
            },
            'quiet': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'concurrent_fragment_downloads': 4,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([g_info_dict['webpage_url']])

        sucesso = True
        g_download_count += 1

        plural = 's' if g_download_count > 1 else ''
        titulo_janela = f"Meu Baixador MP3  •  {g_download_count} baixado{plural} nesta sessão"

        janela.after(0, lambda: [
            janela.title(titulo_janela),
            messagebox.showinfo(
                "Download Concluído",
                f"'{title_safe}.mp3' salvo em:\n{g_pasta_download}",
            ),
            resetar_ui(),
        ])

    except DownloadCancelado:
        cancelado = True
        try:
            for arq in os.listdir(g_pasta_download):
                if arq.startswith(title_safe) and arq.endswith(('.part', '.ytdl', '.tmp')):
                    os.remove(os.path.join(g_pasta_download, arq))
        except Exception:
            pass
        janela.after(0, lambda: [
            status_label.config(text="Download cancelado.", foreground=WARNING),
            progress_bar.stop(),
            progress_bar.config(mode='determinate', value=0),
            download_button.config(state="normal"),
            cancel_button.config(state="disabled"),
        ])

    except Exception as e:
        def tratar_erro(err=e):
            status_label.config(text="Erro durante o download.", foreground=ERROR)
            messagebox.showerror("Erro no Download", f"Ocorreu um erro:\n{err}")

        janela.after(0, tratar_erro)

    finally:
        if not sucesso and not cancelado:
            janela.after(0, lambda: [
                download_button.config(state="normal"),
                cancel_button.config(state="disabled"),
                progress_bar.stop(),
                progress_bar.config(mode='determinate', value=0),
            ])


# ---------------------------------------------------------------------------
# Detecção de URL
# ---------------------------------------------------------------------------

def verificar_e_buscar_url():
    global g_last_url
    url = url_entry.get().strip()
    if not url or url == g_last_url:
        return
    if 'youtube.com' in url or 'youtu.be' in url:
        g_last_url = url
        threading.Thread(
            target=executar_busca_automatica, args=(url,), daemon=True
        ).start()


def on_url_focus_out(event):
    verificar_e_buscar_url()


def on_url_enter(event):
    verificar_e_buscar_url()


def on_url_paste(event):
    janela.after(100, verificar_e_buscar_url)


def on_titulo_enter(event):
    if str(download_button['state']) == 'normal':
        on_baixar_clicado()


def on_baixar_clicado():
    titulo_final = titulo_entry.get().strip()
    if not titulo_final:
        messagebox.showwarning("Aviso", "O campo 'Nome da Música' não pode estar vazio.")
        return
    threading.Thread(
        target=executar_download, args=(titulo_final,), daemon=True
    ).start()


# ---------------------------------------------------------------------------
# Interface — tema escuro
# ---------------------------------------------------------------------------

def criar_interface():
    global janela, progress_bar, status_label, download_button, cancel_button
    global titulo_entry, url_entry, pasta_label

    janela = tk.Tk()
    janela.title("Meu Baixador MP3")
    janela.geometry("520x455")
    janela.resizable(False, False)
    janela.configure(bg=BG)

    # --- Estilos ttk ---
    style = ttk.Style(janela)
    style.theme_use('clam')

    # Remove o foco/borda padrão dos botões
    for nome in ("Primary.TButton", "Danger.TButton", "Ghost.TButton"):
        style.layout(nome, [
            ('Button.padding', {'sticky': 'nswe', 'children': [
                ('Button.label', {'sticky': 'nswe'})
            ]})
        ])

    style.configure("Primary.TButton",
        background=ACCENT, foreground="white",
        font=("Segoe UI", 10, "bold"),
        padding=(20, 12), borderwidth=0, focusthickness=0, relief='flat')
    style.map("Primary.TButton",
        background=[('disabled', CARD), ('pressed', ACCENT_A), ('active', ACCENT_H)],
        foreground=[('disabled', DIM)],
        relief=[('pressed', 'flat')])

    style.configure("Danger.TButton",
        background=DANGER, foreground="white",
        font=("Segoe UI", 10, "bold"),
        padding=(16, 12), borderwidth=0, focusthickness=0, relief='flat')
    style.map("Danger.TButton",
        background=[('disabled', CARD), ('pressed', '#991b1b'), ('active', DANGER_H)],
        foreground=[('disabled', DIM)],
        relief=[('pressed', 'flat')])

    style.configure("Ghost.TButton",
        background=CARD, foreground=MUTED,
        font=("Segoe UI", 9),
        padding=(10, 6), borderwidth=0, focusthickness=0, relief='flat')
    style.map("Ghost.TButton",
        background=[('active', BORDER), ('pressed', BORDER)],
        foreground=[('active', TEXT)],
        relief=[('pressed', 'flat')])

    style.configure("Accent.Horizontal.TProgressbar",
        troughcolor=CARD, background=ACCENT,
        thickness=6, borderwidth=0, troughrelief='flat')

    # -----------------------------------------------------------------------
    # CABEÇALHO
    # -----------------------------------------------------------------------
    header = tk.Frame(janela, bg=PANEL)
    header.pack(fill='x')

    hinner = tk.Frame(header, bg=PANEL)
    hinner.pack(fill='x', padx=22, pady=16)

    # Ícone de nota musical desenhado em canvas
    icon_canvas = tk.Canvas(hinner, width=36, height=36, bg=PANEL,
                            highlightthickness=0)
    icon_canvas.pack(side='left', padx=(0, 12))
    icon_canvas.create_oval(4, 4, 32, 32, fill=ACCENT, outline="")
    icon_canvas.create_text(18, 18, text="♫", fill="white",
                            font=("Segoe UI", 15, "bold"))

    title_col = tk.Frame(hinner, bg=PANEL)
    title_col.pack(side='left')
    tk.Label(title_col, text="Meu Baixador MP3", bg=PANEL, fg=TEXT,
             font=("Segoe UI", 13, "bold")).pack(anchor='w')
    tk.Label(title_col, text="YouTube  →  MP3", bg=PANEL, fg=MUTED,
             font=("Segoe UI", 9)).pack(anchor='w')

    # Linha de acento abaixo do cabeçalho
    tk.Frame(janela, bg=ACCENT, height=2).pack(fill='x')

    # -----------------------------------------------------------------------
    # ÁREA DE CONTEÚDO
    # -----------------------------------------------------------------------
    content = tk.Frame(janela, bg=BG)
    content.pack(fill='both', expand=True, padx=22, pady=20)

    # --- Helpers ---

    def badge(parent, numero):
        """Círculo colorido com número (indicador de passo)."""
        c = tk.Canvas(parent, width=22, height=22, bg=parent['bg'],
                      highlightthickness=0)
        c.create_oval(1, 1, 21, 21, fill=ACCENT, outline="")
        c.create_text(11, 11, text=str(numero), fill="white",
                      font=("Segoe UI", 8, "bold"))
        return c

    def step_row(parent, numero, texto):
        """Linha com badge + label descritivo."""
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x', pady=(0, 6))
        badge(row, numero).pack(side='left', padx=(0, 8))
        tk.Label(row, text=texto, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side='left')

    def campo_entry(parent, disabled=False):
        """
        Campo de texto escuro com borda que fica iluminada no foco.
        Retorna (frame_borda, entry).
        """
        state = 'disabled' if disabled else 'normal'
        borda = tk.Frame(parent, bg=BORDER)
        entry = tk.Entry(
            borda,
            bg=INPUT_BG,
            disabledbackground=INPUT_DIS,
            fg=TEXT,
            disabledforeground=DIM,
            insertbackground=TEXT,
            state=state,
            relief='flat',
            bd=0,
            font=('Segoe UI', 10),
        )
        entry.pack(fill='x', padx=10, pady=8)
        return borda, entry

    # -----------------------------------------------------------------------
    # PASSO 1 — URL
    # -----------------------------------------------------------------------
    step_row(content, 1, "Cole a URL do YouTube aqui")
    url_border, url_entry = campo_entry(content)
    url_border.pack(fill='x')

    url_entry.bind('<FocusIn>',  lambda e: url_border.config(bg=ACCENT))
    url_entry.bind('<FocusOut>', lambda e: url_border.config(bg=BORDER))
    url_entry.bind('<FocusOut>', on_url_focus_out, add=True)
    url_entry.bind('<Return>',   on_url_enter)
    url_entry.bind('<<Paste>>',  on_url_paste)

    # -----------------------------------------------------------------------
    # PASSO 2 — Nome da música
    # -----------------------------------------------------------------------
    tk.Frame(content, bg=BG, height=10).pack()
    step_row(content, 2, "Nome da Música  (edite se necessário)")
    titulo_border, titulo_entry = campo_entry(content, disabled=True)
    titulo_border.pack(fill='x')

    titulo_entry.bind('<FocusIn>',  lambda e: titulo_border.config(bg=ACCENT))
    titulo_entry.bind('<FocusOut>', lambda e: titulo_border.config(bg=BORDER))
    titulo_entry.bind('<Return>', on_titulo_enter)

    # -----------------------------------------------------------------------
    # PASSO 3 — Pasta de destino
    # -----------------------------------------------------------------------
    tk.Frame(content, bg=BG, height=10).pack()
    step_row(content, 3, "Salvar em")

    pasta_row = tk.Frame(content, bg=BG)
    pasta_row.pack(fill='x')

    pasta_box = tk.Frame(pasta_row, bg=BORDER)
    pasta_box.pack(side='left', fill='x', expand=True, padx=(0, 8))
    pasta_label = tk.Label(
        pasta_box,
        text=exibir_pasta(g_pasta_download),
        bg=INPUT_DIS, fg=MUTED,
        font=('Segoe UI', 10),
        anchor='w',
    )
    pasta_label.pack(fill='x', padx=10, pady=8)

    ttk.Button(pasta_row, text="Mudar pasta", style="Ghost.TButton",
               command=escolher_pasta).pack(side='right', ipady=3)

    # -----------------------------------------------------------------------
    # BOTÕES
    # -----------------------------------------------------------------------
    tk.Frame(content, bg=BG, height=14).pack()

    btn_row = tk.Frame(content, bg=BG)
    btn_row.pack(fill='x')

    download_button = ttk.Button(
        btn_row, text="⬇  Baixar MP3",
        state="disabled", style="Primary.TButton",
        command=on_baixar_clicado,
    )
    download_button.pack(side='left', fill='x', expand=True, padx=(0, 8))

    cancel_button = ttk.Button(
        btn_row, text="✕  Cancelar",
        state="disabled", style="Danger.TButton",
        command=cancelar_download,
    )
    cancel_button.pack(side='right')

    # -----------------------------------------------------------------------
    # BARRA DE PROGRESSO
    # -----------------------------------------------------------------------
    tk.Frame(content, bg=BG, height=12).pack()

    progress_bar = ttk.Progressbar(
        content, orient='horizontal', mode='determinate',
        style="Accent.Horizontal.TProgressbar",
    )
    progress_bar.pack(fill='x')

    # -----------------------------------------------------------------------
    # STATUS
    # -----------------------------------------------------------------------
    status_label = tk.Label(
        content,
        text="Aguardando URL…",
        bg=BG, fg=DIM,
        font=("Segoe UI", 9, "italic"),
    )
    status_label.pack(pady=(8, 0))

    url_entry.focus()
    janela.mainloop()


if __name__ == "__main__":
    criar_interface()
