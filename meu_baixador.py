import tkinter as tk
from tkinter import ttk, messagebox, font, filedialog
import yt_dlp
import threading
import os
import re
import json

# --- Config persistente (salva pasta de destino) ---
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

# --- Variáveis globais ---
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
g_pasta_download = _cfg.get('pasta_download', os.path.join(os.path.expanduser('~'), 'Downloads'))


class DownloadCancelado(Exception):
    pass


# --- Utilitários ---

def sanitizar_nome(nome):
    return re.sub(r'[\\/*?:"<>|]', "", nome).strip()


def limpar_titulo(titulo):
    """Remove sufixos comuns do YouTube que poluem o nome do arquivo."""
    padroes = [
        r'\s*[\(\[]\s*[Oo]fficial\s*[Mm]usic\s*[Vv]ideo\s*[\)\]]',
        r'\s*[\(\[]\s*[Oo]fficial\s*[Vv]ideo\s*[\)\]]',
        r'\s*[\(\[]\s*[Oo]fficial\s*[Aa]udio\s*[\)\]]',
        r'\s*[\(\[]\s*[Ll]yrics?\s*(?:[Vv]ideo)?\s*[\)\]]',
        r'\s*[\(\[]\s*[Aa]udio\s*[\)\]]',
        r'\s*[\(\[]\s*[Hh][Dd]\s*[\)\]]',
        r'\s*[\(\[]\s*4[Kk]\s*[\)\]]',
        r'\s*[\(\[]\s*[Cc]lip\s*[Oo]ficial\s*[\)\]]',
        r'\s*\|\s*.+$',          # "Título | Nome do Canal"
        r'\s*//\s*.+$',          # "Título // subtítulo"
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


# --- Reset UI ---

def resetar_ui():
    global g_last_url
    url_entry.delete(0, tk.END)
    titulo_entry.config(state="normal")
    titulo_entry.delete(0, tk.END)
    titulo_entry.config(state="disabled")
    download_button.config(state="disabled")
    cancel_button.config(state="disabled")
    status_label.config(text="Aguardando URL…", foreground="gray")
    progress_bar.stop()
    progress_bar.config(mode='determinate', value=0)
    g_last_url = ""
    url_entry.focus()


# --- Pasta de destino ---

def escolher_pasta():
    global g_pasta_download
    pasta = filedialog.askdirectory(initialdir=g_pasta_download, title="Escolha a pasta de destino")
    if pasta:
        g_pasta_download = pasta
        pasta_label.config(text=exibir_pasta(pasta))
        salvar_config({'pasta_download': pasta})


# --- Cancelar download ---

def cancelar_download():
    global g_cancel_requested
    g_cancel_requested = True
    status_label.config(text="Cancelando…", foreground="orange")
    cancel_button.config(state="disabled")


# --- Thread: busca informações ---

def executar_busca_automatica(url):
    janela.after(0, lambda: [
        status_label.config(text="Buscando informações…", foreground="#007acc"),
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
            status_label.config(text="Pronto! Edite o nome se necessário.", foreground="green")
            progress_bar.stop()
            progress_bar.config(mode='determinate', value=0)
            titulo_entry.focus_set()
            titulo_entry.icursor(tk.END)

        janela.after(0, atualizar)

    except Exception as e:
        def erro():
            progress_bar.stop()
            progress_bar.config(mode='determinate', value=0)
            status_label.config(text="Erro ao buscar URL. Verifique o link.", foreground="red")
            messagebox.showerror("Erro na Busca",
                f"Não foi possível obter informações da URL.\n"
                f"Verifique o link ou sua conexão.\n\nErro: {e}")
        janela.after(0, erro)


# --- Hook de progresso ---

def download_hook(d):
    if g_cancel_requested:
        raise DownloadCancelado("Cancelado pelo usuário")

    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        baixado = d.get('downloaded_bytes', 0)
        speed = d.get('speed')
        eta = d.get('eta')

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
            status_label.config(text=t, foreground="#007acc")

        janela.after(0, atualizar)

    elif d['status'] == 'processing':
        janela.after(0, lambda: [
            progress_bar.config(mode='indeterminate'),
            progress_bar.start(10),
            status_label.config(text="Convertendo para MP3…", foreground="#007acc"),
        ])

    elif d['status'] == 'finished':
        janela.after(0, lambda: [
            progress_bar.stop(),
            progress_bar.config(mode='determinate', value=100),
            status_label.config(text="Finalizando…", foreground="#007acc"),
        ])


# --- Thread: download ---

def executar_download(titulo_final):
    global g_download_count, g_cancel_requested

    g_cancel_requested = False

    janela.after(0, lambda: [
        status_label.config(text="Iniciando download…", foreground="#007acc"),
        download_button.config(state="disabled"),
        cancel_button.config(state="normal"),
        progress_bar.config(mode='determinate', value=0),
    ])

    sucesso = False
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
                'preferredquality': '192',
            }],
            'quiet': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([g_info_dict['webpage_url']])

        sucesso = True
        g_download_count += 1

        plural = 's' if g_download_count > 1 else ''
        titulo_janela = f"Meu Baixador MP3  •  {g_download_count} baixado{plural} nesta sessão"

        janela.after(0, lambda: [
            janela.title(titulo_janela),
            messagebox.showinfo("Download Concluído",
                f"'{title_safe}.mp3' salvo em:\n{g_pasta_download}"),
            resetar_ui(),
        ])

    except DownloadCancelado:
        cancelado = True
        # Limpa arquivos parciais
        try:
            for arq in os.listdir(g_pasta_download):
                if arq.startswith(title_safe) and arq.endswith(('.part', '.ytdl', '.tmp')):
                    os.remove(os.path.join(g_pasta_download, arq))
        except Exception:
            pass
        janela.after(0, lambda: [
            status_label.config(text="Download cancelado.", foreground="orange"),
            progress_bar.stop(),
            progress_bar.config(mode='determinate', value=0),
            download_button.config(state="normal"),
            cancel_button.config(state="disabled"),
        ])

    except Exception as e:
        def tratar_erro(err=e):
            status_label.config(text="Erro durante o download.", foreground="red")
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


# --- Detecção de URL ---

def verificar_e_buscar_url():
    global g_last_url
    url = url_entry.get().strip()
    if not url or url == g_last_url:
        return
    if 'youtube.com' in url or 'youtu.be' in url:
        g_last_url = url
        threading.Thread(target=executar_busca_automatica, args=(url,), daemon=True).start()


def on_url_focus_out(event):
    verificar_e_buscar_url()


def on_url_enter(event):
    verificar_e_buscar_url()


def on_url_paste(event):
    # <<Paste>> dispara antes de inserir no widget; aguarda 100 ms
    janela.after(100, verificar_e_buscar_url)


def on_titulo_enter(event):
    if str(download_button['state']) == 'normal':
        on_baixar_clicado()


# --- Botão Baixar ---

def on_baixar_clicado():
    titulo_final = titulo_entry.get().strip()
    if not titulo_final:
        messagebox.showwarning("Aviso", "O campo 'Nome da Música' não pode estar vazio.")
        return
    threading.Thread(target=executar_download, args=(titulo_final,), daemon=True).start()


# --- Interface ---

def criar_interface():
    global janela, progress_bar, status_label, download_button, cancel_button
    global titulo_entry, url_entry, pasta_label

    janela = tk.Tk()
    janela.title("Meu Baixador MP3")
    janela.geometry("530x390")
    janela.resizable(False, False)

    style = ttk.Style(janela)
    style.theme_use('clam')

    default_font = font.nametofont("TkDefaultFont")
    default_font.configure(family="Segoe UI", size=10)
    janela.option_add("*Font", default_font)

    style.configure("TButton", padding=6, relief="flat",
                    background="#007acc", foreground="white")
    style.map("TButton",
        foreground=[('disabled', '#aaaaaa'), ('pressed', 'white'), ('active', 'white')],
        background=[('disabled', '#cccccc'), ('pressed', '!disabled', '#005f9e'),
                    ('active', '#0098ff')])

    style.configure("Cancel.TButton", padding=6, relief="flat",
                    background="#c0392b", foreground="white")
    style.map("Cancel.TButton",
        foreground=[('disabled', '#aaaaaa'), ('active', 'white')],
        background=[('disabled', '#cccccc'), ('pressed', '!disabled', '#922b21'),
                    ('active', '#e74c3c')])

    style.configure("Folder.TButton", padding=4, relief="flat",
                    background="#555555", foreground="white")
    style.map("Folder.TButton",
        background=[('active', '#777777')])

    style.configure("TProgressbar", thickness=14,
                    troughcolor='#e0e0e0', background='#007acc')

    frame = ttk.Frame(janela, padding="20")
    frame.pack(expand=True, fill="both")

    # --- URL ---
    ttk.Label(frame, text="1. Cole a URL do YouTube aqui:").pack(anchor="w")
    url_entry = ttk.Entry(frame, width=70)
    url_entry.pack(pady=(4, 0), ipady=5, fill="x")

    # --- Nome ---
    ttk.Label(frame, text="2. Nome da Música (edite se necessário):").pack(
        anchor="w", pady=(14, 0))
    titulo_entry = ttk.Entry(frame, width=70, state="disabled")
    titulo_entry.pack(pady=(4, 0), ipady=5, fill="x")

    # --- Pasta destino ---
    pasta_frame = ttk.Frame(frame)
    pasta_frame.pack(fill="x", pady=(12, 0))
    ttk.Label(pasta_frame, text="3. Salvar em:").pack(side="left")
    ttk.Button(pasta_frame, text="Mudar pasta", style="Folder.TButton",
               command=escolher_pasta).pack(side="right")
    pasta_label = ttk.Label(pasta_frame, text=exibir_pasta(g_pasta_download),
                            foreground="#555555")
    pasta_label.pack(side="left", padx=(8, 0))

    # --- Botões ---
    botoes_frame = ttk.Frame(frame)
    botoes_frame.pack(fill="x", pady=(14, 0))
    download_button = ttk.Button(botoes_frame, text="Baixar MP3",
                                 state="disabled", command=on_baixar_clicado)
    download_button.pack(side="left", expand=True, fill="x", ipady=8, padx=(0, 6))
    cancel_button = ttk.Button(botoes_frame, text="Cancelar",
                               state="disabled", style="Cancel.TButton",
                               command=cancelar_download)
    cancel_button.pack(side="left", ipady=8, ipadx=10)

    # --- Progresso ---
    progress_bar = ttk.Progressbar(frame, orient='horizontal', mode='determinate')
    progress_bar.pack(pady=(14, 4), fill='x', ipady=2)

    status_label = ttk.Label(frame, text="Aguardando URL…",
                             foreground="gray", font=("Segoe UI", 9, "italic"))
    status_label.pack()

    # --- Bindings ---
    url_entry.bind("<FocusOut>", on_url_focus_out)
    url_entry.bind("<Return>", on_url_enter)
    url_entry.bind("<<Paste>>", on_url_paste)
    titulo_entry.bind("<Return>", on_titulo_enter)
    url_entry.focus()

    janela.mainloop()


if __name__ == "__main__":
    criar_interface()
