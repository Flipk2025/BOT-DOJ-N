import discord
from discord.ext import commands
from discord import app_commands

class WezwijRada(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@app_commands.command(
		name="wezwij-rada",
		description="Wezwij członka do Rady Departamentu"
	)
	@app_commands.describe(member="Osoba, którą chcesz wezwać")
	async def wezwij_rada(self, interaction: discord.Interaction, member: discord.Member):
		allowed_role_id = 1334881150925275194
		if allowed_role_id not in [role.id for role in interaction.user.roles]:
			await interaction.response.send_message(
				"Nie posiadasz uprawnień do użycia tej komendy.",
				ephemeral=True
			)
			return

		target_channel = self.bot.get_channel(1364172834183708693)
		if target_channel is None:
			await interaction.response.send_message(
				"Nie znaleziono kanału dla Rady Departamentu.", ephemeral=True)
			return

		waiting_channel = self.bot.get_channel(1364176400466317417)
		if waiting_channel is None:
			await interaction.response.send_message(
				"Nie znaleziono kanału Poczekalnia do zarządu.",
				ephemeral=True)
			return

		embed = discord.Embed(
			title="📨┆Zostałeś wezwany do Rady Departamentu!!",
			description=(
				f"{member.mention} - Zostałeś wezwany jako osoba potrzebna do Rady Departamentu!!\n\n"
				"Po zobaczeniu tej informacji prosimy niezwłoczenie udać się na kanał wyznaczony poniżej. "
				"Wszystkie informacje dostaniesz po przeniesieniu na kanał Rady."
			),
			color=discord.Color.from_rgb(255, 255, 255)
		)
		embed.set_thumbnail(url="attachment://bot-logo.png")
		embed.add_field(
			name="Kanał na który prosimy się udać",
			value=f"{waiting_channel.mention}",
			inline=False
		)

		file = discord.File("bot-logo.png", filename="bot-logo.png")
		await target_channel.send(
			f"{member.mention}, prosimy udać się na kanał poczekalni przed Radą Departamentu.",
			embed=embed,
			file=file
		)

		await interaction.response.send_message(
			f"Wezwanie wysłane na kanał {target_channel.mention}.",
			ephemeral=True
		)

async def setup(bot: commands.Bot):
	await bot.add_cog(WezwijRada(bot))
