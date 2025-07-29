import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import database
import logging
import pytz
import asyncio

logger = logging.getLogger('bot')

# Zmienna dla roli uprawnionej do odwoływania ze służby
ODWOLAJ_ROLE_ID = 1396940700112781448  # UZUPEŁNIJ ID ROLI

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

    import asyncio

# ... (reszta importów)

# ... (reszta kodu)

    @tasks.loop(minutes=5)  # Zwiększono interwał do 5 minut
    async def update_loop(self):
        await self.bot.wait_until_ready()
        all_panels = database.get_all_duty_panels()
        for panel_info in all_panels:
            guild = self.bot.get_guild(panel_info['guild_id'])
            if guild:
                await self.update_duty_panels(guild)
            await asyncio.sleep(0) # Dodano sleep, aby oddać kontrolę pętli zdarzeń

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
            await active_message.edit(embed=active_embed) # Usunięto view=DutyView(self)
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

    @app_commands.command(name="setup_zmiana", description="Ustawia panel do zarządzania zmianą na danym kanale.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_zmiana(self, interaction: discord.Interaction, channel: discord.TextChannel):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return
            
        active_embed = discord.Embed(title="Aktywni na służbie", description="Nikt aktualnie nie jest na służbie.", color=discord.Color.blue())
        view = DutyView(self)
        try:
            active_message = await channel.send(embed=active_embed, view=view)
            summary_embed = discord.Embed(title="Podsumowanie godzin służby", description="Brak zarejestrowanych godzin służby.", color=discord.Color.green())
            summary_message = await channel.send(embed=summary_embed)
        except discord.Forbidden:
            await interaction.followup.send("Nie mam uprawnień do wysyłania wiadomości na tym kanale.", ephemeral=True)
            return

        database.set_duty_panel(interaction.guild.id, channel.id, active_message.id, summary_message.id)
        await interaction.followup.send(f"Panel służby został pomyślnie ustawiony na kanale {channel.mention}.", ephemeral=True)

    @app_commands.command(name="setup_logi_sluzby", description="Ustawia kanał, na który będą wysyłane logi wejść i zejść ze służby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_logi_sluzby(self, interaction: discord.Interaction, channel: discord.TextChannel):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return
            
        database.set_duty_log_channel(interaction.guild.id, channel.id)
        await interaction.followup.send(f"Kanał logów służby został ustawiony na {channel.mention}.", ephemeral=True)

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

    @app_commands.command(name="reset_godzin", description="Resetuje sumę godzin służby dla wszystkich użytkowników.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_godzin(self, interaction: discord.Interaction):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return

        guild_id = interaction.guild.id
        database.reset_all_total_duty_seconds(guild_id)
        database.log_duty_event(guild_id, interaction.user.id, "Użyto komendy reset_godzin")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send("Suma godzin służby została zresetowana dla wszystkich użytkowników.", ephemeral=True)

    @app_commands.command(name="ustaw_godziny_osoby", description="Ustawia godziny służby dla konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return

        guild_id = interaction.guild.id
        total_seconds = (hours * 3600) + (minutes * 60)
        database.set_user_total_duty_seconds(user.id, guild_id, total_seconds)
        database.log_duty_event(guild_id, interaction.user.id, "Ustawiono godziny służby", f"Użytkownik: {user.display_name}, Godziny: {hours}h {minutes}m")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Ustawiono {hours}h {minutes}m służby dla {user.mention}.", ephemeral=True)

    @app_commands.command(name="dodaj_godziny_osoby", description="Dodaje godziny służby do konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return

        guild_id = interaction.guild.id
        seconds_to_add = (hours * 3600) + (minutes * 60)
        database.adjust_user_total_duty_seconds(user.id, guild_id, seconds_to_add)
        database.log_duty_event(guild_id, interaction.user.id, "Dodano godziny służby", f"Użytkownik: {user.display_name}, Dodano: {hours}h {minutes}m")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Dodano {hours}h {minutes}m służby dla {user.mention}.", ephemeral=True)

    @app_commands.command(name="odejmij_godziny_osoby", description="Odejmuje godziny służby od konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return

        guild_id = interaction.guild.id
        seconds_to_remove = -((hours * 3600) + (minutes * 60))
        database.adjust_user_total_duty_seconds(user.id, guild_id, seconds_to_remove)
        database.log_duty_event(guild_id, interaction.user.id, "Odjęto godziny służby", f"Użytkownik: {user.display_name}, Odjęto: {hours}h {minutes}m")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Odjęto {hours}h {minutes}m służby od {user.mention}.", ephemeral=True)

    @app_commands.command(name="resetuj_godziny_osoby", description="Resetuje godziny służby dla konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_person_hours(self, interaction: discord.Interaction, user: discord.Member):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return

        guild_id = interaction.guild.id
        database.reset_user_total_duty_seconds(user.id, guild_id)
        database.log_duty_event(guild_id, interaction.user.id, "Zresetowano godziny służby osoby", f"Użytkownik: {user.display_name}")
        await self.update_duty_panels(interaction.guild)
        await interaction.followup.send(f"Zresetowano godziny służby dla {user.mention}.", ephemeral=True)

    @app_commands.command(name="pokaz_logi_sluzby", description="Pokazuje ostatnie logi zdarzeń służby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def show_duty_logs(self, interaction: discord.Interaction, limit: int = 10):
        can_followup = await handle_interaction_error(interaction)
        if not can_followup:
            return

        guild_id = interaction.guild.id
        logs = database.get_duty_logs(guild_id, limit)
        if not logs:
            await interaction.followup.send("Brak logów służby.", ephemeral=True)
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
        if len(log_message) > 4000:
             log_message = log_message[:3990] + "..."

        embed = discord.Embed(title="Logi Służby", description=f"```\n{log_message}\n```", color=discord.Color.orange())
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(zmiana(bot))