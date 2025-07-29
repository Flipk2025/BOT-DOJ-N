import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import database # Importujemy cały moduł database
import logging
import pytz

logger = logging.getLogger('bot') # Używamy istniejącego loggera

class DutyView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance

    @discord.ui.button(label="Wejdź na służbę", style=discord.ButtonStyle.success, custom_id="duty_on")
    async def duty_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"DEBUG: Entering duty_on for user {interaction.user.id}")
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f"DEBUG: Błąd defer w duty_on dla {interaction.user.id}: {e}")
            await interaction.followup.send("Wystąpił błąd podczas przetwarzania. Spróbuj ponownie.", ephemeral=True)
            return

        user = interaction.user
        guild_id = interaction.guild.id

        if database.is_user_on_duty(user.id, guild_id):
            await interaction.followup.send("Jesteś już na służbie!", ephemeral=True)
            database.log_duty_event(guild_id, user.id, "Próba wejścia na służbę (już na służbie)")
        else:
            start_time = datetime.datetime.utcnow()
            database.add_user_to_duty(user.id, guild_id, start_time)
            await interaction.followup.send("Wszedłeś na służbę.", ephemeral=True)
            database.log_duty_event(guild_id, user.id, "Wszedł na służbę")
            await self.cog.send_duty_log(interaction.guild, user, "on")
            await self.cog.update_duty_panels(interaction.guild)

    @discord.ui.button(label="Zejdź ze służby", style=discord.ButtonStyle.danger, custom_id="duty_off")
    async def duty_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"DEBUG: Entering duty_off for user {interaction.user.id}")
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f"DEBUG: Błąd defer w duty_off dla {interaction.user.id}: {e}")
            await interaction.followup.send("Wystąpił błąd podczas przetwarzania. Spróbuj ponownie.", ephemeral=True)
            return

        user = interaction.user
        guild_id = interaction.guild.id

        try:
            if database.is_user_on_duty(user.id, guild_id):
                user_data = database.get_on_duty_users(guild_id)
                user_on_duty_entry = next((u for u in user_data if u['user_id'] == user.id), None)

                duration_seconds = 0
                if user_on_duty_entry:
                    start_time = datetime.datetime.fromisoformat(user_on_duty_entry['start_time'])
                    duration_seconds = (datetime.datetime.utcnow() - start_time).total_seconds()
                    database.adjust_user_total_duty_seconds(user.id, guild_id, duration_seconds)
                    database.log_duty_event(guild_id, user.id, "Zszedł ze służby", f"Czas trwania: {int(duration_seconds)}s")
                else:
                    database.log_duty_event(guild_id, user.id, "Błąd zejścia ze służby", "Użytkownik nie znaleziony w active_duty_users mimo is_user_on_duty")

                database.remove_user_from_duty(user.id, guild_id)
                await interaction.followup.send("Zszedłeś ze służby.", ephemeral=True)
                await self.cog.send_duty_log(interaction.guild, user, "off", duration_seconds)
                await self.cog.update_duty_panels(interaction.guild)
            else:
                await interaction.followup.send("Nie jesteś na służbie!", ephemeral=True)
                database.log_duty_event(guild_id, user.id, "Próba zejścia ze służby (nie na służbie)")
        except Exception as e:
            await interaction.followup.send("Wystąpił błąd podczas próby zejścia ze służby.", ephemeral=True)
            database.log_duty_event(guild_id, user.id, "Krytyczny błąd zejścia ze służby", f"Błąd: {e}")
            logger.error(f"Krytyczny błąd w duty_off dla użytkownika {user.id}: {e}")

class zmiana(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poland_tz = pytz.timezone('Europe/Warsaw')
        self.update_loop.start()
        self.bot.add_view(DutyView(self))

    def cog_unload(self):
        self.update_loop.cancel()

    async def send_duty_log(self, guild: discord.Guild, user: discord.Member, event_type: str, duration_seconds: int = 0):
        panel_info = database.get_duty_panel(guild.id)
        if not panel_info or not panel_info['log_channel_id']:
            return

        log_channel = guild.get_channel(panel_info['log_channel_id'])
        if not log_channel:
            return

        now_utc = datetime.datetime.utcnow()
        now_poland = now_utc.astimezone(self.poland_tz)
        timestamp = f"<t:{int(now_utc.timestamp())}:F>"

        if event_type == "on":
            embed = discord.Embed(
                title="🟢 Wejście na służbę",
                description=f"**Użytkownik:** {user.mention} ({user.display_name})\n**Czas:** {timestamp}",
                color=discord.Color.green()
            )
        elif event_type == "off":
            total_seconds_user = database.get_user_total_duty_seconds(user.id, guild.id)
            
            # Formatowanie czasu trwania ostatniej służby
            h, rem = divmod(duration_seconds, 3600)
            m, s = divmod(rem, 60)
            duration_str = f"{int(h)}h {int(m)}m {int(s)}s"

            # Formatowanie łącznego czasu służby
            th, trem = divmod(total_seconds_user, 3600)
            tm, ts = divmod(trem, 60)
            total_duration_str = f"{int(th)}h {int(tm)}m"

            embed = discord.Embed(
                title="🔴 Zejście ze służby",
                description=f"**Użytkownik:** {user.mention} ({user.display_name})\n**Czas:** {timestamp}",
                color=discord.Color.red()
            )
            embed.add_field(name="Czas ostatniej służby", value=duration_str, inline=False)
            embed.add_field(name="Łączny czas na służbie", value=total_duration_str, inline=False)
        
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Brak uprawnień do wysyłania wiadomości na kanale logów służby (ID: {log_channel.id})")

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
        if not panel_info:
            return

        channel = guild.get_channel(panel_info['channel_id'])
        if not channel:
            return

        # --- Aktualizacja panelu aktywnych ---
        active_embed = discord.Embed(
            title="Aktywni na służbie",
            color=discord.Color.blue()
        )
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
                    total_minutes = int(duration.total_seconds() / 60)
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    time_str = f"{hours:02}:{minutes:02}"
                    active_lines.append(f"{member.display_name} - {time_str}")
            active_description = "\n".join(active_lines)
        active_embed.description = active_description

        try:
            active_message = await channel.fetch_message(panel_info['active_message_id'])
            await active_message.edit(embed=active_embed, view=DutyView(self))
        except discord.NotFound:
            pass

        # --- Aktualizacja panelu podsumowania godzin ---
        summary_embed = discord.Embed(
            title="Podsumowanie godzin służby",
            color=discord.Color.green()
        )
        all_total_duty = database.get_all_total_duty_seconds(guild.id)
        if not all_total_duty:
            total_description = "Brak zarejestrowanych godzin służby."
        else:
            total_lines = []
            for user_row in all_total_duty:
                member = guild.get_member(user_row['user_id'])
                if member:
                    total_seconds = user_row['total_duty_seconds']
                    total_minutes = int(total_seconds / 60)
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    total_lines.append(f"{member.display_name}: {hours:02}h {minutes:02}m")
            total_description = "\n".join(total_lines)
        summary_embed.description = total_description

        try:
            summary_message = await channel.fetch_message(panel_info['summary_message_id'])
            await summary_message.edit(embed=summary_embed)
        except discord.NotFound:
            pass

    @app_commands.command(name="setup_zmiana", description="Ustawia panel do zarządzania zmianą na danym kanale.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_zmiana(self, interaction: discord.Interaction, channel: discord.TextChannel):
        logger.info(f"DEBUG: Entering setup_zmiana for user {interaction.user.id}")
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f"DEBUG: Błąd defer w setup_zmiana dla {interaction.user.id}: {e}")
            await interaction.followup.send("Wystąpił błąd podczas przetwarzania. Spróbuj ponownie.", ephemeral=True)
            return

        active_embed = discord.Embed(
            title="Aktywni na służbie",
            description="Nikt aktualnie nie jest na służbie.",
            color=discord.Color.blue()
        )
        view = DutyView(self)
        try:
            active_message = await channel.send(embed=active_embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send("Nie mam uprawnień do wysyłania wiadomości na tym kanale.")
            database.log_duty_event(interaction.guild.id, interaction.user.id, "Błąd użycia setup_zmiana", f"Brak uprawnień na kanale: {channel.name}")
            return

        summary_embed = discord.Embed(
            title="Podsumowanie godzin służby",
            description="Brak zarejestrowanych godzin służby.",
            color=discord.Color.green()
        )
        try:
            summary_message = await channel.send(embed=summary_embed)
        except discord.Forbidden:
            await interaction.followup.send("Nie mam uprawnień do wysyłania wiadomości na tym kanale.")
            database.log_duty_event(interaction.guild.id, interaction.user.id, "Błąd użycia setup_zmiana", f"Brak uprawnień na kanale: {channel.name}")
            await active_message.delete()
            return

        database.set_duty_panel(interaction.guild.id, channel.id, active_message.id, summary_message.id)
        database.log_duty_event(interaction.guild.id, interaction.user.id, "Użyto komendy setup_zmiana", f"Kanał: {channel.name}")
        await interaction.followup.send(f"Panel służby został pomyślnie ustawiony na kanale {channel.mention}. (Dwie wiadomości)")

    @app_commands.command(name="setup_logi_sluzby", description="Ustawia kanał, na który będą wysyłane logi wejść i zejść ze służby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_logi_sluzby(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        database.set_duty_log_channel(guild_id, channel.id)
        database.log_duty_event(guild_id, interaction.user.id, "Ustawiono kanał logów służby", f"Kanał: {channel.name}")
        await interaction.followup.send(f"Kanał logów służby został ustawiony na {channel.mention}.")

    @app_commands.command(name="reset_godzin", description="Resetuje sumę godzin służby dla wszystkich użytkowników.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_godzin(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        database.reset_all_total_duty_seconds(guild_id)
        database.log_duty_event(guild_id, interaction.user.id, "Użyto komendy reset_godzin")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send("Suma godzin służby została zresetowana dla wszystkich użytkowników.")

    @app_commands.command(name="ustaw_godziny_osoby", description="Ustawia godziny służby dla konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        total_seconds = (hours * 3600) + (minutes * 60)
        database.set_user_total_duty_seconds(user.id, guild_id, total_seconds)
        database.log_duty_event(guild_id, interaction.user.id, "Ustawiono godziny służby", f"Użytkownik: {user.display_name}, Godziny: {hours}h {minutes}m")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Ustawiono {hours}h {minutes}m służby dla {user.mention}.")

    @app_commands.command(name="dodaj_godziny_osoby", description="Dodaje godziny służby do konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        seconds_to_add = (hours * 3600) + (minutes * 60)
        database.adjust_user_total_duty_seconds(user.id, guild_id, seconds_to_add)
        database.log_duty_event(guild_id, interaction.user.id, "Dodano godziny służby", f"Użytkownik: {user.display_name}, Dodano: {hours}h {minutes}m")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Dodano {hours}h {minutes}m służby dla {user.mention}.")

    @app_commands.command(name="odejmij_godziny_osoby", description="Odejmuje godziny służby od konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        seconds_to_remove = -((hours * 3600) + (minutes * 60))
        database.adjust_user_total_duty_seconds(user.id, guild_id, seconds_to_remove)
        database.log_duty_event(guild_id, interaction.user.id, "Odjęto godziny służby", f"Użytkownik: {user.display_name}, Odjęto: {hours}h {minutes}m")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Odjęto {hours}h {minutes}m służby od {user.mention}.")

    @app_commands.command(name="resetuj_godziny_osoby", description="Resetuje godziny służby dla konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_person_hours(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        database.reset_user_total_duty_seconds(user.id, guild_id)
        database.log_duty_event(guild_id, interaction.user.id, "Zresetowano godziny służby osoby", f"Użytkownik: {user.display_name}")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Zresetowano godziny służby dla {user.mention}.")

    @app_commands.command(name="pokaz_logi_sluzby", description="Pokazuje ostatnie logi zdarzeń służby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def show_duty_logs(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        database.log_duty_event(guild_id, interaction.user.id, "Użyto komendy pokaz_logi_sluzby", f"Limit: {limit}")
        logs = database.get_duty_logs(guild_id, limit)

        if not logs:
            await interaction.followup.send("Brak logów służby.")
            return

        log_lines = []
        for log_entry in logs:
            timestamp = datetime.datetime.fromisoformat(log_entry['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
            user = self.bot.get_user(log_entry['user_id'])
            username = user.display_name if user else f"ID: {log_entry['user_id']}"
            action = log_entry['action']
            details = f" ({log_entry['details']})" if log_entry['details'] else ""
            log_lines.append(f"[{timestamp}] {username}: {action}{details}")
        
        log_message = "\n".join(log_lines)
        if len(log_message) > 2000:
            log_message = log_message[:1990] + "... (skrócono)"

        embed = discord.Embed(
            title="Logi Służby",
            description=f"```\n{log_message}\n```",
            color=discord.Color.orange()
        )
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(zmiana(bot))
