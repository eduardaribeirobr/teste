@echo off
chcp 65001 >nul

REM Verifica se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    echo Instale o Python em https://www.python.org/downloads/
    echo Marque a opcao "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

REM Verifica/instala/atualiza yt-dlp automaticamente
python -c "import yt_dlp" >nul 2>&1
if errorlevel 1 (
    echo Instalando yt-dlp...
    python -m pip install yt-dlp --quiet
    if errorlevel 1 (
        echo ERRO: Nao foi possivel instalar yt-dlp.
        echo Execute manualmente: pip install yt-dlp
        pause
        exit /b 1
    )
) else (
    python -m pip install -U yt-dlp --quiet
)

REM Inicia sem janela de console
start "" pythonw "%~dp0meu_baixador.py"
