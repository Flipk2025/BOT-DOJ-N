import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import database
import logging
import pytz

logger = logging.getLogger('bot')

# Zmienna dla roli uprawnionej do odwoływania ze służby
ODWOLAJ_ROLE_ID = 123456789012345678  # UZUPEŁNIJ ID ROLI

async def handle_interaction_error(interaction: discord.Interaction):
    """Centralna funkcja do obsługi wygasłych interakcji."""
    try:
        await interaction.response.defer(ephemeral=True)
        return True
    except discord.errors.NotFound:
        logger.warning(f"Interaction {interaction.id} not found (likely expired). Command will not send a followup.")
        return False

class DutyView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance

    @discord.ui.button(label="Wejdź na służbę", style=discord.ButtonStyle.success, custom_id="duty_on")
    async def duty_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        can_followup = await handle_interaction_error(interaction)
        user = interaction.user
        guild = interaction.guild

        if database.is_user_on_duty(user.id, guild.id):
            if can_followup:
                await interaction.followup.send("Jesteś już na służbie!", ephemeral=True)
            return

        start_time = datetime.datetime.utcnow()
        log_message = await self.cog.send_duty_log(guild, user, "on", start_time)
        log_message_id = log_message.id if log_message else None

        database.add_user_to_duty(user.id, guild.id, start_time, log_message_id)
        if can_followup:
            await interaction.followup.send("Wszedłeś na służbę.", ephemeral=True)
        database.log_duty_event(guild.id, user.id, "Wszedł na służbę")
        await self.cog.update_duty_panels(guild)

    @discord.ui.button(label="Zejdź ze służby", style=discord.ButtonStyle.danger, custom_id="duty_off")
    async def duty_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        can_followup = await handle_interaction_error(interaction)
        user = interaction.user
        guild = interaction.guild

        duty_entry = database.get_user_duty_entry(user.id, guild.id)
        if not duty_entry:
            if can_followup:
                await interaction.followup.send("Nie jesteś na służbie!", ephemeral=True)
            return

        start_time = datetime.datetime.fromisoformat(duty_entry['start_time'])
        duration_seconds = (datetime.datetime.utcnow() - start_time).total_seconds()
        database.adjust_user_total_duty_seconds(user.id, guild.id, int(duration_seconds))
        
        await self.cog.send_duty_log(guild, user, "off", start_time, duty_entry['log_message_id'])

        database.remove_user_from_duty(user.id, guild.id)
        if can_followup:
            await interaction.followup.send("Zszedłeś ze służby.", ephemeral=True)
        database.log_duty_event(guild.id, user.id, "Zszedł ze służby", f"Czas trwania: {int(duration_seconds)}s")
        await self.cog.update_duty_panels(guild)

class zmiana(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poland_tz = pytz.timezone('Europe/Warsaw')
        self.update_loop.start()
        self.bot.add_view(DutyView(self))

    def cog_unload(self):
        self.update_loop.cancel()

    async def send_duty_log(self, guild: discord.Guild, user: discord.Member, event_type: str, start_time: datetime.datetime, log_message_id: int = None, odwolal: discord.Member = None):
        panel_info = database.get_duty_panel(guild.id)
        if not panel_info or not panel_info['log_channel_id']:
            return None

        log_channel = guild.get_channel(panel_info['log_channel_id'])
        if not log_channel:
            return None

        start_timestamp = f"<t:{int(start_time.timestamp())}:F>"

        if event_type == "on":
            embed = discord.Embed(
                title="🟢 Służba w toku...",
                description=f"**Użytkownik:** {user.mention} ({user.display_name})",
                color=discord.Color.green()
            )
            embed.add_field(name="Czas wejścia", value=start_timestamp, inline=False)
            try:
                message = await log_channel.send(embed=embed)
                return message
            except discord.Forbidden:
                logger.warning(f"Brak uprawnień do wysyłania wiadomości na kanale logów służby (ID: {log_channel.id})")
                return None

        elif event_type == "off" and log_message_id:
            try:
                message = await log_channel.fetch_message(log_message_id)
                end_time = datetime.datetime.utcnow()
                end_timestamp = f"<t:{int(end_time.timestamp())}:F>"
                duration_seconds = (end_time - start_time).total_seconds()
                total_seconds_user = database.get_user_total_duty_seconds(user.id, guild.id)

                h, rem = divmod(duration_seconds, 3600)
                m, s = divmod(rem, 60)
                duration_str = f"{int(h)}h {int(m)}m {int(s)}s"

                th, trem = divmod(total_seconds_user, 3600)
                tm, ts = divmod(trem, 60)
                total_duration_str = f"{int(th)}h {int(tm)}m"

                embed = message.embeds[0]
                embed.title = "✅ Służba zakończona"
                embed.color = discord.Color.greyple()
                embed.clear_fields()
                embed.add_field(name="Czas wejścia", value=start_timestamp, inline=False)
                embed.add_field(name="Czas zejścia", value=end_timestamp, inline=False)
                embed.add_field(name="Czas trwania służby", value=duration_str, inline=True)
                embed.add_field(name="Łączny czas na służbie", value=total_duration_str, inline=True)
                if odwolal:
                    embed.add_field(name="Odwołany przez", value=odwolal.mention, inline=False)
                
                await message.edit(embed=embed)
                return message
            except discord.NotFound:
                logger.warning(f"Nie znaleziono wiadomości logu (ID: {log_message_id}) do edycji.")
                return None
            except discord.Forbidden:
                logger.warning(f"Brak uprawnień do edycji wiadomości na kanale logów służby (ID: {log_channel.id})")
                return None
        return None

    @tasks.loop(minutes=1)
    async def update_loop(self):
        await self.bot.wait_until_ready()
        all_panels = database.get_all_duty_panels()
        for panel_info in all_panels:
            guild = self.bot.get_guild(panel_info['guild_id'])
            if guild:
                await self.update_duty_panels(guild)

    async def update_duty_panels(self, guild: discord.Guild):
        panel_info = database.get_duty_panel(guild.id)
        if not panel_info or not panel_info['channel_id']:
            return

        channel = guild.get_channel(panel_info['channel_id'])
        if not channel:
            return

        active_embed = discord.Embed(title="Aktywni na służbie", color=discord.Color.blue())
        guild_users_on_duty = database.get_on_duty_users(guild.id)
        if not guild_users_on_duty:
            active_description = "Nikt aktualnie nie jest na służbie."
        else:
            active_lines = []
            now = datetime.datetime.utcnow()
            for user_row in guild_users_on_duty:
                member = guild.get_member(user_row['user_id'])
                if member:
                    start_time = datetime.datetime.fromisoformat(user_row['start_time'])
                    duration = now - start_time
                    h, rem = divmod(duration.total_seconds(), 3600)
                    m, s = divmod(rem, 60)
                    active_lines.append(f"{member.display_name} - {int(h):02}:{int(m):02}")
            active_description = "\n".join(active_lines)
        active_embed.description = active_description

        try:
            active_message = await channel.fetch_message(panel_info['active_message_id'])
            await active_message.edit(embed=active_embed, view=DutyView(self))
        except discord.NotFound:
            pass

        summary_embed = discord.Embed(title="Podsumowanie godzin służby", color=discord.Color.green())
        all_total_duty = database.get_all_total_duty_seconds(guild.id)
        
        sorted_duty = sorted(all_total_duty, key=lambda x: x['total_duty_seconds'], reverse=True)

        if not sorted_duty:
            total_description = "Brak zarejestrowanych godzin służby."
        else:
            total_lines = []
            for user_row in sorted_duty:
                member = guild.get_member(user_row['user_id'])
                if member:
                    total_seconds = user_row['total_duty_seconds']
                    h, rem = divmod(total_seconds, 3600)
                    m, s = divmod(rem, 60)
                    total_lines.append(f"{member.display_name}: {int(h):02}h {int(m):02}m")
            total_description = "\n".join(total_lines)
        summary_embed.description = total_description

        try:
            summary_message = await channel.fetch_message(panel_info['summary_message_id'])
            await summary_message.edit(embed=summary_embed)
        except discord.NotFound:
            pass

    @app_commands.command(name="odwolaj_ze_sluzby", description="Odwołuje użytkownika ze służby.")
    @app_commands.describe(uzytkownik="Osoba do odwołania ze służby")
    async def odwolaj_ze_sluzby(self, interaction: discord.Interaction, uzytkownik: discord.Member):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return

        if ODWOLAJ_ROLE_ID not in [r.id for r in interaction.user.roles]:
            await interaction.followup.send("Nie masz uprawnień do używania tej komendy.", ephemeral=True)
            return

        duty_entry = database.get_user_duty_entry(uzytkownik.id, interaction.guild.id)
        if not duty_entry:
            await interaction.followup.send(f"{uzytkownik.mention} nie jest na służbie.", ephemeral=True)
            return

        start_time = datetime.datetime.fromisoformat(duty_entry['start_time'])
        duration_seconds = (datetime.datetime.utcnow() - start_time).total_seconds()
        database.adjust_user_total_duty_seconds(uzytkownik.id, interaction.guild.id, int(duration_seconds))
        
        await self.send_duty_log(interaction.guild, uzytkownik, "off", start_time, duty_entry['log_message_id'], odwolal=interaction.user)

        database.remove_user_from_duty(uzytkownik.id, interaction.guild.id)
        database.log_duty_event(interaction.guild.id, uzytkownik.id, "Odwołany ze służby", f"Przez: {interaction.user.name}")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Pomyślnie odwołano {uzytkownik.mention} ze służby.", ephemeral=True)

    # ... (reszta komend) ...

async def setup(bot: commands.Bot):
    await bot.add_cog(zmiana(bot))