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
if DISCORD_TOKEN:
    DISCORD_TOKEN = DISCORD_TOKEN.strip().strip('"').strip("'")

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
    print(f"⚡ Prefixo de comandos: '!' (Ex: !nuke, !painel)")
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
# ==============================================================================
# SISTEMA DO PAINEL INTERATIVO DE POSTAGEM E MATERIAIS (!painel)
# ==============================================================================

ARQUIVOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquivos")
os.makedirs(ARQUIVOS_DIR, exist_ok=True)


def get_available_files() -> list:
    """Retorna a lista de arquivos presentes na pasta 'arquivos/'."""
    if not os.path.exists(ARQUIVOS_DIR):
        return []
    files = []
    for f in sorted(os.listdir(ARQUIVOS_DIR)):
        full_path = os.path.join(ARQUIVOS_DIR, f)
        if os.path.isfile(full_path) and not f.startswith("."):
            files.append(f)
    return files


def format_file_size(size_in_bytes: int) -> str:
    """Formata o tamanho do arquivo em B, KB ou MB."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    else:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"


def parse_color_choice(color_input: str) -> discord.Color:
    """Converte nome de cor ou código hexadecimal em discord.Color."""
    if not color_input:
        return discord.Color.from_rgb(88, 101, 242)

    val = color_input.strip().lower()
    color_map = {
        "azul": discord.Color.blue(),
        "blue": discord.Color.blue(),
        "roxo": discord.Color.purple(),
        "purple": discord.Color.purple(),
        "verde": discord.Color.green(),
        "green": discord.Color.green(),
        "vermelho": discord.Color.red(),
        "red": discord.Color.red(),
        "laranja": discord.Color.orange(),
        "orange": discord.Color.orange(),
        "dourado": discord.Color.gold(),
        "amarelo": discord.Color.gold(),
        "gold": discord.Color.gold(),
        "preto": discord.Color.dark_theme(),
        "escuro": discord.Color.dark_theme(),
        "blurple": discord.Color.blurple(),
    }
    if val in color_map:
        return color_map[val]

    hex_val = val.replace("#", "")
    if len(hex_val) == 6:
        try:
            return discord.Color(int(hex_val, 16))
        except ValueError:
            pass
    return discord.Color.from_rgb(88, 101, 242)


class EditarTextoModal(discord.ui.Modal, title="✏️ Configurar Post / Embed"):
    def __init__(self, view_ref):
        super().__init__()
        self.view_ref = view_ref

        self.titulo_input = discord.ui.TextInput(
            label="Título do Embed",
            placeholder="Ex: 📚 MÓDULO 1 - CURSO AVANÇADO",
            default=self.view_ref.titulo,
            max_length=256,
            required=True
        )
        self.add_item(self.titulo_input)

        self.descricao_input = discord.ui.TextInput(
            label="Descrição / Conteúdo",
            style=discord.TextStyle.paragraph,
            placeholder="Digite o texto detalhado da postagem...",
            default=self.view_ref.descricao,
            max_length=4000,
            required=True
        )
        self.add_item(self.descricao_input)

        self.webhook_input = discord.ui.TextInput(
            label="Nome do Webhook (Autor da postagem)",
            placeholder="Ex: Central de Conteúdos",
            default=self.view_ref.nome_webhook,
            max_length=80,
            required=False
        )
        self.add_item(self.webhook_input)

        self.cor_input = discord.ui.TextInput(
            label="Cor (azul, roxo, verde, vermelho, #HEX)",
            placeholder="Ex: roxo ou #5865F2",
            default=self.view_ref.cor_nome,
            max_length=20,
            required=False
        )
        self.add_item(self.cor_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.titulo = self.titulo_input.value.strip()
        self.view_ref.descricao = self.descricao_input.value.strip()
        self.view_ref.nome_webhook = self.webhook_input.value.strip() or "Central de Conteúdos"
        self.view_ref.cor_nome = self.cor_input.value.strip() or "roxo"
        self.view_ref.cor = parse_color_choice(self.view_ref.cor_nome)

        embed = self.view_ref.build_painel_embed()
        try:
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        except Exception:
            try:
                await interaction.message.edit(embed=embed, view=self.view_ref)
                await interaction.response.defer()
            except Exception:
                pass


class CanalSelect(discord.ui.ChannelSelect):
    def __init__(self, view_ref):
        self.view_ref = view_ref
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="📢 Selecione os canais de destino...",
            min_values=1,
            max_values=25,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.canais_selecionados = self.values
        embed = self.view_ref.build_painel_embed()
        await interaction.response.edit_message(embed=embed, view=self.view_ref)


class ArquivoSelect(discord.ui.Select):
    def __init__(self, view_ref, files: list):
        self.view_ref = view_ref
        options = []
        for fn in files[:25]:
            fp = os.path.join(ARQUIVOS_DIR, fn)
            size_str = format_file_size(os.path.getsize(fp)) if os.path.exists(fp) else "0 B"
            is_default = fn in self.view_ref.arquivos_selecionados
            options.append(
                discord.SelectOption(
                    label=fn[:100],
                    value=fn,
                    description=f"Tamanho: {size_str}",
                    default=is_default
                )
            )

        super().__init__(
            placeholder="📁 Selecione os arquivos para anexar...",
            min_values=0,
            max_values=len(options),
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.arquivos_selecionados = self.values
        embed = self.view_ref.build_painel_embed()
        await interaction.response.edit_message(embed=embed, view=self.view_ref)


class PainelView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=900)  # 15 minutos ativo
        self.author_id = author_id

        # Configurações padrão inspiradas na organização limpa
        self.titulo = "📚 CURSO APROVAÇÃO AVANÇADA"
        self.descricao = (
            "- COMO USAR INFO CC BY; Nt. PARTE 1\n\n"
            ">>> 1° O QUE É UM BIN, E COMO SE IDENTIFICA UMA BIN?\n\n"
            "💡 Faça o download dos arquivos anexados abaixo para acessar o material completo."
        )
        self.nome_webhook = "Central de Materiais"
        self.cor_nome = "roxo"
        self.cor = parse_color_choice(self.cor_nome)

        self.canais_selecionados = []
        self.arquivos_selecionados = []
        self.ultimo_status = "Aguardando configuração..."

        # Monta os componentes iniciais
        self.setup_components()

    def setup_components(self):
        self.clear_items()

        # Linha 0: Seletor de Canais
        self.add_item(CanalSelect(self))

        # Linha 1: Seletor de Arquivos (somente se houver arquivos disponíveis na pasta)
        files = get_available_files()
        if files:
            # Se a lista estiver vazia, pré-seleciona todos os arquivos por conveniência
            if not self.arquivos_selecionados:
                self.arquivos_selecionados = [f for f in files[:25] if f != "LEIAME.txt"] or files[:25]
            self.add_item(ArquivoSelect(self, files))

        # Linha 2: Botões de Ação
        btn_editar = discord.ui.Button(label="Editar Texto", emoji="✏️", style=discord.ButtonStyle.secondary, row=2)
        btn_editar.callback = self.on_editar_clicked
        self.add_item(btn_editar)

        btn_atualizar = discord.ui.Button(label="Atualizar Arquivos", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
        btn_atualizar.callback = self.on_atualizar_arquivos_clicked
        self.add_item(btn_atualizar)

        btn_previa = discord.ui.Button(label="Ver Prévia", emoji="👁️", style=discord.ButtonStyle.primary, row=2)
        btn_previa.callback = self.on_previa_clicked
        self.add_item(btn_previa)

        btn_disparar = discord.ui.Button(label="Disparar Post", emoji="🚀", style=discord.ButtonStyle.success, row=2)
        btn_disparar.callback = self.on_disparar_clicked
        self.add_item(btn_disparar)

        btn_fechar = discord.ui.Button(label="Fechar", emoji="❌", style=discord.ButtonStyle.danger, row=2)
        btn_fechar.callback = self.on_fechar_clicked
        self.add_item(btn_fechar)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id or interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("❌ Apenas quem abriu este painel pode interagir com ele.", ephemeral=True)
        return False

    def build_post_embed(self) -> discord.Embed:
        """Gera o embed formatado que será enviado aos canais finais."""
        embed = discord.Embed(
            title=self.titulo,
            description=self.descricao,
            color=self.cor
        )
        if self.arquivos_selecionados:
            files_list_str = "\n".join([f"• 📄 `{fn}`" for fn in self.arquivos_selecionados])
            embed.add_field(
                name="📦 Arquivos Anexados",
                value=files_list_str[:1024],
                inline=False
            )
        data_str = get_current_brazil_time_str()
        embed.set_footer(text=f"{self.nome_webhook} • Publicado em {data_str}")
        return embed

    def build_painel_embed(self) -> discord.Embed:
        """Gera a interface do painel de controle interativo."""
        embed = discord.Embed(
            title="⚙️ Painel de Postagem & Organização de Materiais",
            description="Configure as informações abaixo e clique em **Disparar Post** para publicar nos canais escolhidos.",
            color=discord.Color.from_rgb(88, 101, 242)
        )

        embed.add_field(name="📌 Título", value=f"`{self.titulo}`", inline=True)
        embed.add_field(name="🤖 Nome Webhook", value=f"`{self.nome_webhook}`", inline=True)
        embed.add_field(name="🎨 Cor Embed", value=f"`{self.cor_nome}`", inline=True)

        desc_resumo = self.descricao if len(self.descricao) <= 200 else self.descricao[:200] + "..."
        embed.add_field(name="📝 Prévia do Texto", value=f"```\n{desc_resumo}\n```", inline=False)

        # Canais selecionados
        if self.canais_selecionados:
            canais_str = ", ".join([f"<#{c.id}>" for c in self.canais_selecionados])
            embed.add_field(name=f"📢 Canais Alvo ({len(self.canais_selecionados)})", value=canais_str[:1024], inline=False)
        else:
            embed.add_field(name="📢 Canais Alvo", value="*Nenhum canal selecionado ainda (use o menu acima)*", inline=False)

        # Arquivos selecionados
        files = get_available_files()
        if not files:
            embed.add_field(
                name="📁 Arquivos na Pasta `arquivos/`",
                value="*Nenhum arquivo encontrado. Coloque seus PDFs/TXTs na pasta `arquivos/` e clique em 🔄 Atualizar Arquivos*",
                inline=False
            )
        else:
            if self.arquivos_selecionados:
                arq_str = ", ".join([f"`{fn}`" for fn in self.arquivos_selecionados])
                embed.add_field(name=f"📁 Arquivos Selecionados ({len(self.arquivos_selecionados)})", value=arq_str[:1024], inline=False)
            else:
                embed.add_field(name="📁 Arquivos Selecionados", value="*Nenhum selecionado (nenhum anexo será enviado)*", inline=False)

        embed.add_field(name="📊 Status", value=f"`{self.ultimo_status}`", inline=False)
        embed.set_footer(text="Use os menus e botões abaixo para gerenciar a publicação.")
        return embed

    async def on_editar_clicked(self, interaction: discord.Interaction):
        modal = EditarTextoModal(self)
        await interaction.response.send_modal(modal)

    async def on_atualizar_arquivos_clicked(self, interaction: discord.Interaction):
        files = get_available_files()
        self.arquivos_selecionados = [f for f in self.arquivos_selecionados if f in files]
        if not self.arquivos_selecionados and files:
            self.arquivos_selecionados = [f for f in files[:25] if f != "LEIAME.txt"] or files[:25]
        self.setup_components()
        embed = self.build_painel_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_previa_clicked(self, interaction: discord.Interaction):
        embed_previa = self.build_post_embed()
        info_arquivos = ""
        if self.arquivos_selecionados:
            info_arquivos = f"\n📎 **Arquivos anexados ({len(self.arquivos_selecionados)}):** " + ", ".join([f"`{f}`" for f in self.arquivos_selecionados])
        await interaction.response.send_message(
            content=f"👁️ **Prévia exclusiva de como o post ficará no canal:**{info_arquivos}",
            embed=embed_previa,
            ephemeral=True
        )

    async def on_disparar_clicked(self, interaction: discord.Interaction):
        if not self.canais_selecionados:
            await interaction.response.send_message(
                "❌ **Nenhum canal selecionado!** Selecione pelo menos 1 canal no menu de canais acima antes de disparar.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        embed_to_send = self.build_post_embed()
        enviados_sucesso = []
        falhas = []

        for canal_item in self.canais_selecionados:
            ch = canal_item
            if not isinstance(ch, discord.TextChannel):
                ch = interaction.guild.get_channel(canal_item.id)

            if not ch or not isinstance(ch, discord.TextChannel):
                falhas.append(f"<#{canal_item.id}> (canal inválido)")
                continue

            try:
                sucesso_webhook = False
                bot_member = interaction.guild.me
                channel_perms = ch.permissions_for(bot_member)

                # Prioriza envio via Webhook para identidade limpa
                if channel_perms.manage_webhooks:
                    try:
                        webhooks = await ch.webhooks()
                        webhook = discord.utils.get(webhooks, name=self.nome_webhook)
                        if not webhook:
                            webhook = discord.utils.find(lambda w: w.user == interaction.client.user, webhooks)
                            if not webhook:
                                webhook = await ch.create_webhook(name=self.nome_webhook, reason="Painel de materiais")

                        # Gera instâncias novas de discord.File para cada canal
                        files_payload = []
                        for fn in self.arquivos_selecionados:
                            fp = os.path.join(ARQUIVOS_DIR, fn)
                            if os.path.exists(fp):
                                files_payload.append(discord.File(fp, filename=fn))

                        avatar_url = interaction.client.user.display_avatar.url if interaction.client.user else None
                        await webhook.send(
                            embed=embed_to_send,
                            files=files_payload,
                            username=self.nome_webhook,
                            avatar_url=avatar_url
                        )
                        sucesso_webhook = True
                    except Exception as wh_err:
                        print(f"[Webhook fallback em #{ch.name}]: {wh_err}")
                        sucesso_webhook = False

                # Fallback: Envio pelo bot caso Webhooks falhem ou não tenham permissão
                if not sucesso_webhook:
                    files_payload = []
                    for fn in self.arquivos_selecionados:
                        fp = os.path.join(ARQUIVOS_DIR, fn)
                        if os.path.exists(fp):
                            files_payload.append(discord.File(fp, filename=fn))
                    await ch.send(embed=embed_to_send, files=files_payload)

                enviados_sucesso.append(ch.mention)
            except Exception as e:
                print(f"[Erro ao disparar para #{ch.name}]: {e}")
                falhas.append(f"{ch.mention} (`{e}`)")

        # Monta relatório do disparo
        msg_relatorio = "🚀 **Resultado do Disparo:**\n"
        if enviados_sucesso:
            msg_relatorio += f"✅ **Postado com sucesso em ({len(enviados_sucesso)}):** {', '.join(enviados_sucesso)}\n"
        if falhas:
            msg_relatorio += f"⚠️ **Falhas ({len(falhas)}):** {', '.join(falhas)}\n"

        self.ultimo_status = f"✅ Disparado para {len(enviados_sucesso)} canal(is) às {get_current_brazil_time_str()}"
        try:
            embed_atualizado = self.build_painel_embed()
            await interaction.message.edit(embed=embed_atualizado, view=self)
        except Exception:
            pass

        await interaction.followup.send(msg_relatorio, ephemeral=True)

    async def on_fechar_clicked(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        self.stop()
        embed = self.build_painel_embed()
        embed.title = "🔒 Painel Fechado"
        embed.description = "Este painel foi encerrado. Para abrir novamente, digite `!painel`."
        await interaction.response.edit_message(embed=embed, view=self)


@bot.command(name="painel")
@commands.guild_only()
async def painel(ctx: commands.Context):
    """
    Abre o painel interativo de postagens e envio de materiais para múltiplos canais.
    Permite anexar arquivos, escolher canais, editar textos e disparar via Webhook.
    """
    user_perms = ctx.author.guild_permissions
    if not (user_perms.administrator or user_perms.manage_guild or user_perms.manage_messages or user_perms.manage_channels):
        await ctx.send("❌ **Acesso negado:** Você precisa de permissão de Administrador ou Gerenciar Mensagens para abrir o painel.")
        return

    # Se o usuário enviou arquivos anexados junto com o comando !painel, salva automaticamente
    if ctx.message.attachments:
        salvos = []
        for att in ctx.message.attachments:
            caminho_salvar = os.path.join(ARQUIVOS_DIR, att.filename)
            try:
                await att.save(caminho_salvar)
                salvos.append(att.filename)
            except Exception as e:
                print(f"[Erro ao salvar anexo {att.filename}]: {e}")
        if salvos:
            print(f"[Painel] {len(salvos)} arquivo(s) salvo(s) via anexo do !painel: {salvos}")

    view = PainelView(author_id=ctx.author.id)
    embed = view.build_painel_embed()
    await ctx.send(embed=embed, view=view)


@painel.error
async def painel_error(ctx: commands.Context, error: commands.CommandError):
    """Tratamento de erros do comando !painel."""
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("❌ Este comando só pode ser utilizado dentro de um servidor Discord.")
    else:
        print(f"[ERRO no !painel]: {error}", file=sys.stderr)
        try:
            await ctx.send(f"❌ Ocorreu um erro ao abrir o painel: `{error}`")
        except Exception:
            pass


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
