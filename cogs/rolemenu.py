import discord
from discord.ext import commands
import traceback
import asyncio

class RoleMenuCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # ID ról do zarządzania
        self.role_ids = {
            "ping_rozprawy": 1370830123523379210,
            "zmiany_prawne": 1371009145796562974,
            "listy_goncze": 1371009146295685242,
        }

        # ID kanału, na który ma być wysłane menu ról
        self.role_menu_channel_id = 1371007466535649320

        # Dodaj persistent view przy starcie
        self.bot.add_view(RoleView(self.role_ids))

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✅ Moduł {self.__class__.__name__} jest gotowy!")
        await asyncio.sleep(5)
        await self.send_role_menu()

    async def send_role_menu(self):
        try:
            channel = self.bot.get_channel(self.role_menu_channel_id)
            if not channel:
                print(f"❌ Nie znaleziono kanału (ID: {self.role_menu_channel_id})")
                return

            # Sprawdź, czy menu już istnieje
            async for message in channel.history(limit=50):
                if message.author.id == self.bot.user.id and message.embeds:
                    if message.embeds[0].title == "Wybierz Powiadomienia":
                        print("✅ Menu ról już istnieje.")
                        return

            embed = discord.Embed(
                title="Wybierz Powiadomienia",
                description="Kliknij przycisk, aby otrzymać lub usunąć rolę.\n"
                            "Wybierz kategorie powiadomień, które Cię interesują.",
                color=discord.Color.blue()
            )
            embed.add_field(name="🔔 Ping Rozprawy", value="Powiadomienia o rozprawach", inline=False)
            embed.add_field(name="📜 Zmiany Prawne", value="Zmiany w prawie", inline=False)
            embed.add_field(name="🚨 Listy Gończe", value="Nowe listy gończe", inline=False)
            embed.set_footer(text="Kliknij ponownie, aby usunąć rolę")

            view = RoleView(self.role_ids)
            await channel.send(embed=embed, view=view)
            print("✅ Menu ról zostało wysłane.")
        except Exception as e:
            traceback.print_exc()

class RoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: str, emoji: str, style: discord.ButtonStyle):
        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            custom_id=f"role_button_{role_id}"
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await self.respond_safe(interaction, f"Nie znaleziono roli o ID {self.role_id}.", ephemeral=True)
            return

        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await self.respond_safe(interaction, f"✅ Usunięto rolę {role.mention}.", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await self.respond_safe(interaction, f"✅ Dodano rolę {role.mention}.", ephemeral=True)
        except discord.Forbidden:
            await self.respond_safe(interaction, "❌ Bot nie ma uprawnień do zarządzania rolami.", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await self.respond_safe(interaction, "❌ Wystąpił nieoczekiwany błąd.", ephemeral=True)

    async def respond_safe(self, interaction: discord.Interaction, message: str, ephemeral=True):
        try:
            await interaction.response.send_message(message, ephemeral=ephemeral)
        except discord.errors.HTTPException as e:
            if e.code == 40060:  # Interaction already acknowledged
                try:
                    await interaction.followup.send(message, ephemeral=ephemeral)
                except:
                    pass  # Ignoruj dalsze błędy

class RoleView(discord.ui.View):
    def __init__(self, role_ids: dict):
        super().__init__(timeout=None)

        self.add_item(RoleButton(
            role_id=role_ids["ping_rozprawy"],
            label="Ping Rozprawy",
            emoji="🔔",
            style=discord.ButtonStyle.primary
        ))

        self.add_item(RoleButton(
            role_id=role_ids["zmiany_prawne"],
            label="Zmiany Prawne",
            emoji="📜",
            style=discord.ButtonStyle.success
        ))

        self.add_item(RoleButton(
            role_id=role_ids["listy_goncze"],
            label="Listy Gończe",
            emoji="🚨",
            style=discord.ButtonStyle.danger
        ))

async def setup(bot: commands.Bot):
    await bot.add_cog(RoleMenuCog(bot))
