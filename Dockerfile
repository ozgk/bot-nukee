FROM python:3.11-slim

# Cria usuário com UID 1000 (padrão de segurança exigido pelo Hugging Face Spaces)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# Porta padrão de monitoramento do Hugging Face Spaces
EXPOSE 7860

CMD ["python", "bot.py"]
