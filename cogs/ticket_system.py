import discord
from discord import app_commands
from discord.ext import commands

# Stałe role
VIEWER_ROLE_ID = 1334881150858035290  # dostęp tylko, bez pisania
WRITER_ROLE_ID = 1334881150925275194  # dostęp i pisanie

# Kanały i kategorie
TICKET_CHANNEL_ID = 1334881151935840325  # ID kanału z formularzem
TICKET_CATEGORY_ID = 1334881156574871582  # ID kategorii dla ticketów

# Konfiguracja typów ticketów
TICKET_TYPES = {
	"ranga": {
		"label": "Wniosek o przyznanie rangi",
		"handler_roles": [1342200180052590642],  # pingowane
		"viewer_roles": [1334881150828806188], # tylko dostęp
		"fields": [
			("Imię i nazwisko (IC)", "np. John Doe", True),
			("Numer SSN", "np. 54175", True),
			("Ranga do dodania", "np. Właściciel Firmy, LSPD, USMS, Adwokat, DOJ", True),
			("Numer odznaki/legitymacni (Jeśli dotyczy)", "Napisz swój nr. odznaki/legitymacji jeśli masz", False),
			("Inne uwagi", "POLE NIEOBOWIĄSKOWE", False)
		]
	},
	"dane": {
		"label": "Zmiana Danych",
		"handler_roles": [1368498015702351954],  # pingowane
		"viewer_roles": [],                      # tylko dostęp
		"fields": [
			("Imię i nazwisko (IC)", "np. John Doe", True),
			("Numer SSN", "np. 54175", True),
			("Data urodzenia", "np. 20-02-1997", True),
			("Wnioskowene Imię i naziwsko", "np. John Smith", True),
			("Powód zmiany", "Opisz co jest powodem zmiany danych", True),
			("Inne uwagi", "POLE NIEOBOWIĄSKOWE", False)
		]
	},
	"pozew": {
		"label": "Złóż pozew do Sądu",
		"handler_roles": [1334888295154319522],
		"viewer_roles": [1334892405035372564],
		"fields": [
			("Imię i nazwisko (IC)", "np. John Doe", True),
			("Numer SSN", "np. 54175", True),
			("Data urodzenia", "np. 20-02-1997", True),
			("Link do pozwu", "MUSI BYĆ W GOOGLE DOCS", True)
		]
	},
	"prawo": {
		"label": "Pomoc Prawna",
		"handler_roles": [1334888295154319522],
		"viewer_roles": [],
		"fields": [
			("Imię i nazwisko (IC)", "np. John Doe", True),
			("Numer SSN", "np. 54175", True),
			("Data urodzenia", "np. 20-02-1997", True),
			("Opis sprawy", "Opisz sprawę", True)
		]
	},
	"prokuratura": {
		"label": "Sprawa do prokuratury",
		"handler_roles": [1359162624889065512],
		"viewer_roles": [1334891241002893312],
		"fields": [
			("Imię i nazwisko (IC)", "np. John Doe", True),
			("Numer SSN", "np. 54175", True),
			("Data urodzenia", "np. 20-02-1997", True),
			("Opis sprawy", "Opisz jaką masz sprawę do prokuratury", True),
			("Inne uwagi/Załączniki", "POLE NIEOBOWIĄSKOWE", False)
		]
	},
	"zarzad": {
		"label": "Prośba o rozmowę z zarządem",
		"handler_roles": [1342200180052590642],
		"viewer_roles": [1334881150925275194],
		"fields": [
			("Imię i nazwisko (IC)", "np. John Doe", True),
			("Cel rozmowy", "W jakiej sprawie chcesz rozmawiać?", True)
		]
	},
	"skarga": {
		"label": "Skarga na urzędnika/funkcjonariusza",
		"handler_roles": [1359162624889065512],
		"viewer_roles": [1334892405035372564, 1334891241002893312],
		"fields": [
			("Imię i nazwisko (IC)", "np. John Doe", True),
			("Numer SSN", "np. 54175", True),
			("Dane funkcjonariusza/urzędnika", "np. Samuel King", True),
			("Nr. odznaki/legitymaci i Jednoska/Wydział", "np. 145 - LSPD, 14 - FIB, 31 - DOJ", True),
			("Powód skargi", "Opisz co jest powodem skargi", True),
			("Załączniki (Opcjonalnie)", "np. nagrania itp.", True)
		]
	},
	"inne": {
		"label": "Inna sprawa",
		"handler_roles": [1334881150828806188],
		"viewer_roles": [],
			"fields": [
				("Imię i nazwisko (IC)", "np. John Doe", True),
				("Opis", "Napisz w czym możemy pomóc", True)
			]
	}
}

class TicketSystem(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@commands.Cog.listener()
	async def on_ready(self):
		print("TicketSystem cog załadowany.")
		await self.send_ticket_message()

	async def send_ticket_message(self):
		channel = self.bot.get_channel(TICKET_CHANNEL_ID)
		if channel is None:
			return
		existing = [msg async for msg in channel.history(limit=10)]
		if any(msg.author == self.bot.user for msg in existing):
			return

		view = TicketDropdownView()
		embed = discord.Embed(
			title="🎫 Otwórz zgłoszenie",
			description="Wybierz temat, a następnie wypełnij formularz zgłoszenia.",
			color=discord.Color.blurple()
		)
		await channel.send(embed=embed, view=view)

class TicketDropdown(discord.ui.Select):
	def __init__(self):
		options = [discord.SelectOption(label=data["label"], value=key)
				   for key, data in TICKET_TYPES.items()]
		super().__init__(placeholder="Wybierz temat zgłoszenia...", min_values=1, max_values=1, options=options)

	async def callback(self, interaction: discord.Interaction):
		topic_key = self.values[0]
		modal = TicketModal(topic_key)
		await interaction.response.send_modal(modal)

class TicketDropdownView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=None)
		self.add_item(TicketDropdown())

class TicketModal(discord.ui.Modal):
	def __init__(self, topic_key):
		title = f"{TICKET_TYPES[topic_key]['label'][:45]}"  # Ograniczenie do 45 znaków
		super().__init__(title=title)
		self.topic_key = topic_key
		self.inputs = []
		for i, (label, placeholder, required) in enumerate(TICKET_TYPES[topic_key]["fields"]):
			if i >= 5:
				break  # Discord nie pozwala na więcej niż 5 pól w modalu
			inp = discord.ui.TextInput(label=label, placeholder=placeholder, required=required)
			self.inputs.append(inp)
			self.add_item(inp)

	async def on_submit(self, interaction: discord.Interaction):
		guild = interaction.guild
		category = guild.get_channel(TICKET_CATEGORY_ID)
		cfg = TICKET_TYPES[self.topic_key]

		# Budowanie overwrite permissions
		overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
		# Zawsze dodaj role VIEWER_ROLE_ID (tylko czytanie) i WRITER_ROLE_ID
		overwrites[guild.get_role(VIEWER_ROLE_ID)] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
		overwrites[guild.get_role(WRITER_ROLE_ID)] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
		# Role handler:
		for role_id in cfg['handler_roles']:
			overwrites[guild.get_role(role_id)] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
		# Role viewer:
		for role_id in cfg['viewer_roles']:
			overwrites[guild.get_role(role_id)] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
		# Użytkownik:
		overwrites[interaction.user] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

		# Tworzenie kanału ticket
		channel_name = f"ticket-{interaction.user.name}".replace(" ", "-").lower()
		ticket_channel = await guild.create_text_channel(
			name=channel_name,
			category=category,
			overwrites=overwrites,
			topic=f"{cfg['label']} zgłoszenie od {interaction.user.name}"
		)

		# Przygotowanie embed i view kontrolnego
		embed_desc = "\n".join(f"**{inp.label}:** {inp.value}" for inp in self.inputs)
		view = TicketControlView(cfg['handler_roles'] + [WRITER_ROLE_ID])
		embed = discord.Embed(
			title="📩 Nowe zgłoszenie",
			description=embed_desc,
			color=discord.Color.green()
		)
		mentions = f"{interaction.user.mention} | " + " ".join(f"<@&{rid}>" for rid in cfg['handler_roles'])
		await ticket_channel.send(content=mentions, embed=embed, view=view)
		await interaction.response.send_message(f"✅ Zgłoszenie utworzone: {ticket_channel.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
	def __init__(self, allowed_roles):
		super().__init__(timeout=None)
		self.allowed_roles = allowed_roles
		self.claimed_by = None

	@discord.ui.button(label="Przejmij zgłoszenie", style=discord.ButtonStyle.success)
	async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
		if not any(role.id in self.allowed_roles for role in interaction.user.roles):
			await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
			return
		if self.claimed_by:
			await interaction.response.send_message(f"Już przejęte przez {self.claimed_by.mention}.", ephemeral=True)
			return
		self.claimed_by = interaction.user
		button.disabled = True
		button.label = f"Przejęte przez {interaction.user.display_name}"
		await interaction.response.edit_message(view=self)
		await interaction.followup.send(f"Zgłoszenie przejął: {interaction.user.mention}", ephemeral=False)

	@discord.ui.button(label="Zamknij zgłoszenie", style=discord.ButtonStyle.danger)
	async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
		if not any(role.id in self.allowed_roles for role in interaction.user.roles):
			await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
			return
		await interaction.channel.delete()

async def setup(bot):
	await bot.add_cog(TicketSystem(bot))