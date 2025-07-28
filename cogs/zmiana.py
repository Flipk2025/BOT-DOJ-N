import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import database # Zmieniono import

class DutyView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance

    @discord.ui.button(label="Wejdź na służbę", style=discord.ButtonStyle.success, custom_id="duty_on")
    async def duty_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild_id = interaction.guild.id

        if database.is_user_on_duty(user.id, guild_id):
            await interaction.response.send_message("Jesteś już na służbie!", ephemeral=True)
            database.log_duty_event(guild_id, user.id, "Próba wejścia na służbę (już na służbie)")
        else:
            database.add_user_to_duty(user.id, guild_id, datetime.datetime.utcnow())
            await interaction.response.send_message("Wszedłeś na służbę.", ephemeral=True)
            database.log_duty_event(guild_id, user.id, "Wszedł na służbę")
            await self.cog.update_duty_list(interaction.guild)

    @discord.ui.button(label="Zejdź ze służby", style=discord.ButtonStyle.danger, custom_id="duty_off")
    async def duty_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild_id = interaction.guild.id

        if database.is_user_on_duty(user.id, guild_id):
            # Oblicz czas trwania służby i dodaj do sumy
            user_data = next((u for u in database.get_on_duty_users(guild_id) if u['user_id'] == user.id), None)
            if user_data:
                start_time = datetime.datetime.fromisoformat(user_data['start_time'])
                duration_seconds = (datetime.datetime.utcnow() - start_time).total_seconds()
                database.adjust_user_total_duty_seconds(user.id, guild_id, duration_seconds)
                database.log_duty_event(guild_id, user.id, "Zszedł ze służby", f"Czas trwania: {int(duration_seconds)}s")

            database.remove_user_from_duty(user.id, guild_id)
            await interaction.response.send_message("Zszedłeś ze służby.", ephemeral=True)
            await self.cog.update_duty_list(interaction.guild)
        else:
            await interaction.response.send_message("Nie jesteś na służbie!", ephemeral=True)
            database.log_duty_event(guild_id, user.id, "Próba zejścia ze służby (nie na służbie)")

class zmiana(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_loop.start()
        self.bot.add_view(DutyView(self))

    def cog_unload(self):
        self.update_loop.cancel()

    @tasks.loop(minutes=1)
    async def update_loop(self):
        await self.bot.wait_until_ready()
        all_panels = database.get_all_duty_panels()
        for panel_info in all_panels:
            guild = self.bot.get_guild(panel_info['guild_id'])
            if guild:
                await self.update_duty_list(guild)

    async def update_duty_list(self, guild: discord.Guild):
        panel_info = database.get_duty_panel(guild.id)
        if not panel_info:
            return

        channel = guild.get_channel(panel_info['channel_id'])
        if not channel:
            return

        try:
            message = await channel.fetch_message(panel_info['message_id'])
        except discord.NotFound:
            return

        embed = discord.Embed(
            title="Aktywni na służbie",
            color=discord.Color.blue()
        )

        # Aktywni na służbie
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
        
        embed.add_field(name="__Aktywni:__", value=active_description, inline=False)

        # Podsumowanie godzin
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

        embed.add_field(name="__Podsumowanie godzin:__", value=total_description, inline=False)

        await message.edit(embed=embed)

    @app_commands.command(name="setup_zmiana", description="Ustawia panel do zarządzania zmianą na danym kanale.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_zmiana(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Ustawia panel służby na określonym kanale."""
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="Aktywni na służbie",
            description="Nikt aktualnie nie jest na służbie.",
            color=discord.Color.blue()
        )
        view = DutyView(self)
        
        try:
            message = await channel.send(embed=embed, view=view)
            database.set_duty_panel(interaction.guild.id, channel.id, message.id)
            database.log_duty_event(interaction.guild.id, interaction.user.id, "Użyto komendy setup_zmiana", f"Kanał: {channel.name}")
            await interaction.followup.send(f"Panel służby został pomyślnie ustawiony na kanale {channel.mention}.")
        except discord.Forbidden:
            await interaction.followup.send("Nie mam uprawnień do wysyłania wiadomości na tym kanale.")
            database.log_duty_event(interaction.guild.id, interaction.user.id, "Błąd użycia setup_zmiana", f"Brak uprawnień na kanale: {channel.name}")
        except Exception as e:
            await interaction.followup.send(f"Wystąpił błąd: {e}")
            database.log_duty_event(interaction.guild.id, interaction.user.id, "Błąd użycia setup_zmiana", f"Błąd: {e}")

    @app_commands.command(name="reset_godzin", description="Resetuje sumę godzin służby dla wszystkich użytkowników.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_godzin(self, interaction: discord.Interaction):
        """Resetuje sumę godzin służby dla wszystkich użytkowników na serwerze."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        database.reset_all_total_duty_seconds(guild_id)
        database.log_duty_event(guild_id, interaction.user.id, "Użyto komendy reset_godzin")
        await self.update_duty_list(interaction.guild)
        await interaction.followup.send("Suma godzin służby została zresetowana dla wszystkich użytkowników.")

    @app_commands.command(name="ustaw_godziny_osoby", description="Ustawia godziny służby dla konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        """Ustawia godziny służby dla konkretnej osoby."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        total_seconds = (hours * 3600) + (minutes * 60)
        database.set_user_total_duty_seconds(user.id, guild_id, total_seconds)
        database.log_duty_event(guild_id, interaction.user.id, "Ustawiono godziny służby", f"Użytkownik: {user.display_name}, Godziny: {hours}h {minutes}m")
        await self.update_duty_list(interaction.guild)
        await interaction.followup.send(f"Ustawiono {hours}h {minutes}m służby dla {user.mention}.")

    @app_commands.command(name="dodaj_godziny_osoby", description="Dodaje godziny służby do konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        """Dodaje godziny służby do konkretnej osoby."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        seconds_to_add = (hours * 3600) + (minutes * 60)
        database.adjust_user_total_duty_seconds(user.id, guild_id, seconds_to_add)
        database.log_duty_event(guild_id, interaction.user.id, "Dodano godziny służby", f"Użytkownik: {user.display_name}, Dodano: {hours}h {minutes}m")
        await self.update_duty_list(interaction.guild)
        await interaction.followup.send(f"Dodano {hours}h {minutes}m służby dla {user.mention}.")

    @app_commands.command(name="odejmij_godziny_osoby", description="Odejmuje godziny służby od konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_person_hours(self, interaction: discord.Interaction, user: discord.Member, hours: int, minutes: int):
        """Odejmuje godziny służby od konkretnej osoby.""" 
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        seconds_to_remove = -((hours * 3600) + (minutes * 60)) # Ujemna wartość do odjęcia
        database.adjust_user_total_duty_seconds(user.id, guild_id, seconds_to_remove)
        database.log_duty_event(guild_id, interaction.user.id, "Odjęto godziny służby", f"Użytkownik: {user.display_name}, Odjęto: {hours}h {minutes}m")
        await self.update_duty_list(interaction.guild)
        await interaction.followup.send(f"Odjęto {hours}h {minutes}m służby od {user.mention}.")

    @app_commands.command(name="resetuj_godziny_osoby", description="Resetuje godziny służby dla konkretnej osoby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_person_hours(self, interaction: discord.Interaction, user: discord.Member):
        """Resetuje godziny służby dla konkretnej osoby."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        database.reset_user_total_duty_seconds(user.id, guild_id)
        database.log_duty_event(guild_id, interaction.user.id, "Zresetowano godziny służby osoby", f"Użytkownik: {user.display_name}")
        await self.update_duty_list(interaction.guild)
        await interaction.followup.send(f"Zresetowano godziny służby dla {user.mention}.")

    @app_commands.command(name="pokaz_logi_sluzby", description="Pokazuje ostatnie logi zdarzeń służby.")
    @app_commands.checks.has_permissions(administrator=True)
    async def show_duty_logs(self, interaction: discord.Interaction, limit: int = 10):
        """Pokazuje ostatnie logi zdarzeń służby."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        # log_duty_event(guild_id, interaction.user.id, "Użyto komendy pokaz_logi_sluzby", f"Limit: {limit}") # Ta linia loguje użycie komendy, ale nie powinna być tutaj, bo loguje przed pobraniem logów
        database.log_duty_event(guild_id, interaction.user.id, "Użyto komendy pokaz_logi_sluzby", f"Limit: {limit}") # Poprawione logowanie
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