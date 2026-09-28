import os
import sys

# Garante suporte a UTF-8 e emojis no console do Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Obtém o token do Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Configuração dos Intents
# IMPORTANTE: message_content = True é obrigatório no discord.py 2.0+ para comandos com prefixo!
intents = discord.Intents.default()
intents.message_content = True


async def handle_ping(request):
    """Página de status que mantém o container ativo no Hugging Face Spaces / Render."""
    html = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Bot Nuke Status</title>
        <style>
            body { font-family: system-ui, sans-serif; background: #0f1117; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .card { background: #1a1d26; padding: 2.5rem; border-radius: 14px; text-align: center; border: 1px solid #ff4500; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            h1 { color: #ff4500; margin: 0 0 10px 0; font-size: 2rem; }
            p { color: #a0aec0; margin: 5px 0 20px 0; }
            .status { background: #1c4532; color: #68d391; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 14px; display: inline-block; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🧨 Bot Nuke</h1>
            <p>O bot está online e operacional no Discord.</p>
            <div class="status">● ONLINE 24/7</div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def start_web_server():
    """Inicia o mini servidor web na porta 7860 para monitoramento 24/7."""
    try:
        app = web.Application()
        app.router.add_get("/", handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 7860))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"🌐 Servidor web keep-alive ativo na porta {port}")
    except Exception as e:
        print(f"[AVISO] Não foi possível iniciar o servidor web: {e}")


class NukeBot(commands.Bot):
    async def setup_hook(self):
        # Inicia o servidor web em segundo plano para o Hugging Face
        await start_web_server()


# Inicialização do Bot com prefixo '!'
bot = NukeBot(command_prefix="!", intents=intents, help_command=None)


def get_current_brazil_time_str() -> str:
    """
    Retorna o horário atual no fuso horário do Brasil (America/Sao_Paulo)
    formatado como DD/MM/AAAA HH:MM.
    """
    try:
        import pytz
        tz = pytz.timezone("America/Sao_Paulo")
        now = datetime.now(tz)
    except Exception:
        # Fallback usando UTC-3 padrão caso pytz não esteja disponível
        tz = timezone(timedelta(hours=-3))
        now = datetime.now(tz)
    
    return now.strftime("%d/%m/%Y %H:%M")


@bot.event
async def on_ready():
    """Evento disparado quando o bot se conecta com sucesso ao Discord."""
    print("=" * 50)
    print(f"🔥 Bot Conectado com Sucesso!")
    print(f"🤖 Nome: {bot.user.name}#{bot.user.discriminator}")
    print(f"🆔 ID: {bot.user.id}")
    print(f"🌐 Servidores Conectados: {len(bot.guilds)}")
    print(f"⚡ Prefixo de comandos: '!' (Ex: !nuke)")
    print("=" * 50)


@bot.command(name="nuke")
@commands.guild_only()
@commands.cooldown(rate=1, per=10.0, type=commands.BucketType.user)
async def nuke(ctx: commands.Context):
    """
    Comando !nuke seguro:
    1. Verifica permissões do usuário (Gerenciar Canais ou Administrador).
    2. Valida o tipo de canal (apenas canais de texto convencionais).
    3. Confirma se o bot tem permissão de Gerenciar Canais.
    4. Salva todas as propriedades do canal atual.
    5. Recria o canal antes de deletar o antigo (evita perda do canal em caso de erro).
    6. Deleta SOMENTE o canal atual.
    7. Restaura a posição exata.
    8. Envia o embed com a menção ao usuário, data em America/Sao_Paulo e o GIF anexado.
    """

    # 1. VERIFICAÇÃO DE PERMISSÃO DO USUÁRIO
    user_perms = ctx.channel.permissions_for(ctx.author)
    if not (user_perms.manage_channels or user_perms.administrator):
        await ctx.send("❌ **Acesso negado:** Você precisa da permissão de **Gerenciar Canais** ou **Administrador** para usar este comando.")
        return

    # 2. VERIFICAÇÃO DO TIPO DE CANAL
    # Garante que funciona APENAS em canais de texto padrão (nunca categorias, voz, fóruns ou tópicos)
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("❌ **Operação inválida:** O comando `!nuke` só pode ser executado em canais de texto comuns.")
        return

    old_channel: discord.TextChannel = ctx.channel

    # 3. VERIFICAÇÃO DE PERMISSÕES DO BOT
    bot_member = ctx.guild.me
    bot_channel_perms = old_channel.permissions_for(bot_member)

    if not (bot_member.guild_permissions.manage_channels and bot_channel_perms.manage_channels):
        await ctx.send("❌ **Permissão insuficiente:** O bot precisa da permissão de **Gerenciar Canais** no servidor e neste canal para executar o comando.")
        return

    # 4. SALVAMENTO DAS INFORMAÇÕES DO CANAL ATUAL
    channel_name = old_channel.name
    channel_category = old_channel.category
    channel_position = old_channel.position
    channel_overwrites = old_channel.overwrites
    channel_topic = old_channel.topic
    channel_slowmode = old_channel.slowmode_delay
    channel_nsfw = old_channel.nsfw

    # 5. RECIAÇÃO SEGURA DO CANAL
    # Criamos o novo canal ANTES de deletar o antigo para evitar que o canal seja
    # apagado sem conseguir ser recriado (caso ocorra erro de API, limite de canais, etc).
    try:
        new_channel = await old_channel.clone(
            name=channel_name,
            reason=f"Nuke solicitado por {ctx.author} ({ctx.author.id})"
        )
    except Exception as clone_error:
        # Fallback: se o clone direto falhar, tenta criação explícita
        try:
            new_channel = await ctx.guild.create_text_channel(
                name=channel_name,
                category=channel_category,
                topic=channel_topic,
                slowmode_delay=channel_slowmode,
                nsfw=channel_nsfw,
                overwrites=channel_overwrites,
                position=channel_position,
                reason=f"Nuke solicitado por {ctx.author} ({ctx.author.id})"
            )
        except Exception as create_error:
            # Em caso de falha na criação, o canal original é 100% PRESERVADO
            await ctx.send(f"❌ **Falha ao recriar o canal:** {create_error}\nO canal original **não** foi apagado por questões de segurança.")
            return

    # 6. DELEÇÃO DO CANAL ANTIGO (SOMENTE o canal atual)
    try:
        await old_channel.delete(reason=f"Canal nukado por {ctx.author} ({ctx.author.id})")
    except Exception as delete_error:
        print(f"[AVISO] Não foi possível deletar o canal antigo: {delete_error}")

    # 7. SINCRONIZAÇÃO DA POSIÇÃO EXATA DO NOVO CANAL
    try:
        await new_channel.edit(position=channel_position)
    except Exception as pos_error:
        print(f"[AVISO] Não foi possível reposicionar o novo canal: {pos_error}")

    # 8. CONSTRUÇÃO DO EMBED NO NOVO CANAL
    # Horário de São Paulo formatado DD/MM/AAAA HH:MM
    data_formatada = get_current_brazil_time_str()

    # Cor laranja/vermelha quente estilo explosão (#FF4500)
    embed = discord.Embed(
        title="🧨 Canal Nukado!",
        description=f"Este canal foi recriado por {ctx.author.mention}",
        color=discord.Color.from_rgb(255, 69, 0)
    )
    embed.set_footer(text=f"Executado em {data_formatada}")

    # 9. ANEXO DO GIF DE EXPLOSÃO NUCLEAR
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gif_path = os.path.join(base_dir, "nuke.gif")

    if os.path.exists(gif_path):
        gif_file = discord.File(gif_path, filename="nuke.gif")
        embed.set_image(url="attachment://nuke.gif")
        await new_channel.send(embed=embed, file=gif_file)
    else:
        # Se o arquivo nuke.gif não estiver na pasta, envia o embed sem imagem
        await new_channel.send(embed=embed)


@nuke.error
async def nuke_error(ctx: commands.Context, error: commands.CommandError):
    """Tratamento de erros específicos do comando !nuke."""
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ **Cooldown:** Aguarde **{error.retry_after:.1f} segundos** antes de usar `!nuke` novamente.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ **Acesso negado:** Você precisa da permissão de **Gerenciar Canais** ou **Administrador**.")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("❌ Este comando só pode ser utilizado dentro de um servidor Discord.")
    else:
        print(f"[ERRO no !nuke]: {error}", file=sys.stderr)
        try:
            await ctx.send(f"❌ Ocorreu um erro ao processar o comando: `{error}`")
        except Exception:
            pass


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Tratamento global de erros para comandos não encontrados ou exceções."""
    if isinstance(error, commands.CommandNotFound):
        # Ignora silenciosamente comandos inexistentes digitados com !
        return
    if isinstance(error, (commands.CommandOnCooldown, commands.MissingPermissions, commands.NoPrivateMessage)):
        # Já tratados pelo handler específico do comando
        return
    print(f"[ERRO GLOBAL]: {error}", file=sys.stderr)


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN.strip() == "" or DISCORD_TOKEN == "SEU_TOKEN_AQUI":
        print("\n" + "!" * 60)
        print("ERRO: O DISCORD_TOKEN não foi configurado!")
        print("1. Abra o arquivo '.env' na pasta do bot.")
        print("2. Adicione seu token na linha: DISCORD_TOKEN=seu_token_aqui")
        print("3. Salve o arquivo e inicie o bot novamente.")
        print("!" * 60 + "\n")
        sys.exit(1)

    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("\n❌ ERRO: O token do Discord fornecido no arquivo .env é inválido!")
        print("Verifique o token copiado no Discord Developer Portal.\n")
    except Exception as e:
        print(f"\n❌ Erro ao iniciar o bot: {e}\n")
