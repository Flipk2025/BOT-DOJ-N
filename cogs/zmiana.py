import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
from database import (
    set_duty_panel, get_duty_panel, get_all_duty_panels,
    is_user_on_duty, add_user_to_duty, remove_user_from_duty, get_on_duty_users
)

class DutyView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance

    @discord.ui.button(label="Wejdź na służbę", style=discord.ButtonStyle.success, custom_id="duty_on")
    async def duty_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild_id = interaction.guild.id

        if is_user_on_duty(user.id, guild_id):
            await interaction.response.send_message("Jesteś już na służbie!", ephemeral=True)
        else:
            add_user_to_duty(user.id, guild_id, datetime.datetime.utcnow())
            await interaction.response.send_message("Wszedłeś na służbę.", ephemeral=True)
            await self.cog.update_duty_list(interaction.guild)

    @discord.ui.button(label="Zejdź ze służby", style=discord.ButtonStyle.danger, custom_id="duty_off")
    async def duty_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        guild_id = interaction.guild.id

        if is_user_on_duty(user.id, guild_id):
            remove_user_from_duty(user.id, guild_id)
            await interaction.response.send_message("Zszedłeś ze służby.", ephemeral=True)
            await self.cog.update_duty_list(interaction.guild)
        else:
            await interaction.response.send_message("Nie jesteś na służbie!", ephemeral=True)

class zmiana(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_loop.start()
        # Rejestrujemy widok globalnie przy starcie bota
        # To ważne, aby przyciski działały po restarcie bota
        self.bot.add_view(DutyView(self))

    def cog_unload(self):
        self.update_loop.cancel()

    @tasks.loop(minutes=1)
    async def update_loop(self):
        await self.bot.wait_until_ready()
        all_panels = get_all_duty_panels()
        for panel_info in all_panels:
            guild = self.bot.get_guild(panel_info['guild_id'])
            if guild:
                await self.cog.update_duty_list(guild)

    async def update_duty_list(self, guild: discord.Guild):
        panel_info = get_duty_panel(guild.id)
        if not panel_info:
            return

        channel = guild.get_channel(panel_info['channel_id'])
        if not channel:
            # Kanał mógł zostać usunięty
            return

        try:
            message = await channel.fetch_message(panel_info['message_id'])
        except discord.NotFound:
            # Wiadomość została usunięta, można ją utworzyć ponownie lub zignorować
            return

        embed = discord.Embed(
            title="Aktywni na służbie",
            color=discord.Color.blue()
        )

        guild_users = get_on_duty_users(guild.id)
        if not guild_users:
            embed.description = "Nikt aktualnie nie jest na służbie."
        else:
            description = []
            now = datetime.datetime.utcnow()
            for user_row in guild_users:
                member = guild.get_member(user_row['user_id'])
                if member:
                    start_time = datetime.datetime.fromisoformat(user_row['start_time'])
                    duration = now - start_time
                    hours, remainder = divmod(int(duration.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
                    description.append(f"{member.display_name} - {time_str}")
            
            embed.description = "\n".join(description) if description else "Nikt aktualnie nie jest na służbie."

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
            # Zapisz informacje o panelu w bazie danych
            set_duty_panel(interaction.guild.id, channel.id, message.id)
            await interaction.followup.send(f"Panel służby został pomyślnie ustawiony na kanale {channel.mention}.")
        except discord.Forbidden:
            await interaction.followup.send("Nie mam uprawnień do wysyłania wiadomości na tym kanale.")
        except Exception as e:
            await interaction.followup.send(f"Wystąpił błąd: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(zmiana(bot))