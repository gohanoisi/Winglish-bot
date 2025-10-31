import discord

def main_menu_view():
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="英単語", style=discord.ButtonStyle.primary, custom_id="menu:vocab"))
    v.add_item(discord.ui.Button(label="英文解釈", style=discord.ButtonStyle.primary, custom_id="menu:svocm"))
    v.add_item(discord.ui.Button(label="長文読解", style=discord.ButtonStyle.primary, custom_id="menu:reading"))
    return v

def info_embed(title: str, desc: str) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=0x2b90d9)
    return e
