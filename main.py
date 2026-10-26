import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import io
import datetime
import asyncio

# ================= KONFIGURASI =================
TOKEN = os.getenv("DISCORD_TOKEN") 
HARGA_PER_AKUN = 100 
# ===============================================

class RobloxStoreBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), help_command=None)
        self.db_file = "accounts.json"
        self.config_file = "config.json"

    async def setup_hook(self):
        if not os.path.exists(self.db_file):
            with open(self.db_file, "w") as f:
                json.dump([], f)
                
        if not os.path.exists(self.config_file):
            with open(self.config_file, "w") as f:
                json.dump({
                    "owner_id": None,
                    "buyer_role_id": None,
                    "panel_channel_id": None, 
                    "role_locked": False,
                    "ticket_count": 0,
                    "seller_mcrypt_id": None,
                    "seller_bx_id": None,
                    "seller_ame_id": None
                }, f, indent=4)

        bot.add_view(PanelView())
        await self.tree.sync()
        print("✅ Slash commands disync!")

    async def on_ready(self):
        print(f"✅ Login sebagai {self.user.name} ({self.user.id})")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Roblox Store | /stock"))
        self.update_panel_loop.start()

    @tasks.loop(seconds=30)
    async def update_panel_loop(self):
        await self.update_panel()

    async def update_panel(self):
        with open(self.config_file, "r") as f:
            config = json.load(f)
            
        channel_id = config.get("panel_channel_id")
        if not channel_id:
            return

        channel = self.get_channel(int(channel_id))
        if not channel:
            return

        with open(self.db_file, "r") as f:
            accounts = json.load(f)
            
        stok_mcrypt = len([a for a in accounts if a["status"] == "available" and a.get("seller") == "Mcrypt"])
        stok_bx = len([a for a in accounts if a["status"] == "available" and a.get("seller") == "Bx"])
        stok_ame = len([a for a in accounts if a["status"] == "available" and a.get("seller") == "Ame"])
        total_stok = stok_mcrypt + stok_bx + stok_ame

        now_utc = datetime.datetime.utcnow()
        now_wib = now_utc + datetime.timedelta(hours=7)
        
        hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][now_wib.weekday()]
        waktu_sekarang = now_wib.strftime(f"{hari}, %d %B %Y - %H:%M WIB")
        
        embed = discord.Embed(
            title="📦 **Informasi Stock Cookies Roblox**",
            description=(
                "⚠️ **BACA SEBELUM MEMBELI!**\n"
                "• Akun cookies buatan sendiri.\n"
                "• 100% data polosan.\n"
                "• Akun cookies tidak reg global.\n"
                "• Privasi 100% terjaga dan diatur oleh sistem End to delete.\n\n"
                "Silakan pahami terlebih dahulu sebelum melakukan pembelian!"
            ),
            color=0x5865F2 
        )
            
        embed.add_field(name="👤 **M.Crypt**", value=f"```fix\n{stok_mcrypt} Akun\n```", inline=True)
        embed.add_field(name="👤 **Bx**", value=f"```fix\n{stok_bx} Akun\n```", inline=True)
        embed.add_field(name="👤 **Ame**", value=f"```fix\n{stok_ame} Akun\n```", inline=True)
        
        embed.add_field(name="📊 **Total Stok**", value=f"`{total_stok} Akun`", inline=False)
        embed.add_field(name="💰 **Harga**", value=f"`{HARGA_PER_AKUN} Perak / Akun`", inline=False)
        embed.add_field(name="🕒 **Terakhir Diperbarui**", value=f"`{waktu_sekarang}`", inline=False)
        
        embed.set_footer(text="Klik tombol di bawah untuk membeli.", icon_url=self.user.display_avatar.url)
        embed.timestamp = now_wib

        view = PanelView()

        async for msg in channel.history(limit=20):
            if msg.author.id == self.user.id and msg.embeds and "Informasi Stock Cookies Roblox" in msg.embeds[0].title:
                await msg.edit(embed=embed, view=view)
                return
        await channel.send(embed=embed, view=view)

bot = RobloxStoreBot()

def get_seller_name(user_id, config):
    s_id = str(user_id)
    if config.get("seller_mcrypt_id") and s_id == str(config["seller_mcrypt_id"]): return "Mcrypt"
    if config.get("seller_bx_id") and s_id == str(config["seller_bx_id"]): return "Bx"
    if config.get("seller_ame_id") and s_id == str(config["seller_ame_id"]): return "Ame"
    return None

def is_owner(user_id, config):
    if not config.get("owner_id"): return False
    return str(user_id) == str(config["owner_id"])

def format_harga(harga):
    if harga >= 1000:
        formatted = f"{harga / 1000:.1f}".replace(".0", "")
        return f"{formatted}K"
    return str(harga)

class CloseTicketModal(discord.ui.Modal, title="Tutup Tiket"):
    reason = discord.ui.TextInput(
        label="Alasan Penutupan",
        placeholder="Contoh: Terima kasih telah order akun cookies disini!",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔒 Menutup tiket...", ephemeral=True)
        await asyncio.sleep(2)
        
        buyer = None
        for target, overwrite in interaction.channel.overwrites.items():
            if isinstance(target, discord.Member) and not target.bot and target.id != interaction.user.id:
                 buyer = target
                 break

        if buyer:
            try:
                await buyer.send(f"🔒 **Tiket Ditutup**\n\nAlasan: {self.reason.value}")
            except:
                pass

        await interaction.channel.delete()

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Tutup Tiket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        with open(bot.config_file, "r") as f:
            config = json.load(f)
            
        penjual = get_seller_name(interaction.user.id, config)
        if not penjual and not is_owner(interaction.user.id, config):
            return await interaction.response.send_message("🚫 Hanya Admin/Penjual yang bisa menutup tiket ini.", ephemeral=True)
        
        await interaction.response.send_modal(CloseTicketModal())

class BeliModal(discord.ui.Modal, title="Form Pembelian Akun Roblox"):
    jumlah = discord.ui.TextInput(
        label="Jumlah Akun",
        placeholder="Masukkan angka (Contoh: 1)",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not self.jumlah.value.isdigit():
            return await interaction.response.send_message("❌ Gagal! Kamu harus memasukkan angka murni.", ephemeral=True)
        
        jumlah_beli = int(self.jumlah.value)
        if jumlah_beli <= 0:
            return await interaction.response.send_message("❌ Gagal! Minimal beli 1 akun.", ephemeral=True)

        guild = interaction.guild
        buyer = interaction.user

        existing_ticket = None
        for ch in guild.text_channels:
            if ch.name.startswith("buy-cookies-") and ch.overwrites_for(buyer).view_channel:
                existing_ticket = ch
                break
                
        if existing_ticket:
            return await interaction.response.send_message(f"❌ Kamu masih punya tiket yang aktif di {existing_ticket.mention}.", ephemeral=True)

        with open(bot.db_file, "r") as f:
            accounts = json.load(f)
        stok_tersedia = len([a for a in accounts if a["status"] == "available"])

        if jumlah_beli > stok_tersedia:
            return await interaction.response.send_message(f"❌ Gagal! Stok tidak cukup. Sisa stok: **{stok_tersedia}**", ephemeral=True)

        await interaction.response.send_message("⏳ Memproses tiket...", ephemeral=True)

        with open(bot.config_file, "r") as f:
            config = json.load(f)
            
        buyer_role_id = config.get("buyer_role_id")
        
        ticket_count = config.get("ticket_count", 0) + 1
        config["ticket_count"] = ticket_count
        with open(bot.config_file, "w") as f:
            json.dump(config, f, indent=4)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            buyer: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        
        if config.get("owner_id"):
            owner_member = guild.get_member(int(config["owner_id"]))
            if owner_member: overwrites[owner_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            
        for seller_key in ["seller_mcrypt_id", "seller_bx_id", "seller_ame_id"]:
            if config.get(seller_key):
                seller_member = guild.get_member(int(config[seller_key]))
                if seller_member: overwrites[seller_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"buy-cookies-{ticket_count}",
            overwrites=overwrites
        )

        if buyer_role_id:
            role_buyer = guild.get_role(int(buyer_role_id))
            if role_buyer and role_buyer not in buyer.roles:
                try:
                    await buyer.add_roles(role_buyer)
                except:
                    pass

        embed_tiket = discord.Embed(
            title="🧾 Tiket Pembelian",
            description=f"Halo {buyer.mention}, terima kasih sudah memesan!\n\n"
                        f"📦 **Jumlah:** {jumlah_beli} Akun\n"
                        f"💰 **Total Harga:** {format_harga(jumlah_beli * HARGA_PER_AKUN)} Perak\n\n"
                        f"Silakan tunggu Admin/Penjual untuk memproses pesananmu.",
            color=0x2ecc71
        )
        
        view_tiket = TicketView()
        await ticket_channel.send(content=f"{buyer.mention}", embed=embed_tiket, view=view_tiket)
        
        try:
            await interaction.delete_original_response() 
            await interaction.followup.send(
                content=f"✅ Tiket berhasil dibuat! Silakan klik channel <#{ticket_channel.id}>. *(Hilang dalam 1 menit)*",
                ephemeral=True,
                delete_after=60.0
            )
        except:
            pass

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Beli Akun", emoji="🛒", style=discord.ButtonStyle.success, custom_id="beli_akun_btn")
    async def beli_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BeliModal())

# ================= COMMANDS =================

@bot.tree.command(name="setup", description="Set ADMIN/OWNER (HANYA BISA DILAKUKAN SEKALI)")
@app_commands.describe(user="Tag user yang jadi Owner/Admin utama")
async def setup_owner(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("🚫 Hanya Administrator server yang bisa melakukan setup awal.", ephemeral=True)

    with open(bot.config_file, "r") as f:
        config = json.load(f)

    if config["role_locked"]:
        return await interaction.response.send_message("🔒 Owner sudah di-set sebelumnya dan **tidak bisa diubah lagi**.", ephemeral=True)

    config["owner_id"] = user.id
    config["role_locked"] = True
    
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f"✅ Owner dikunci ke: {user.mention}", ephemeral=True)

@bot.tree.command(name="setseller", description="Set User Discord untuk masing-masing Penjual")
@app_commands.describe(penjual="Pilih penjual", user="Tag user Discord-nya")
@app_commands.choices(penjual=[
    app_commands.Choice(name="Mcrypt", value="seller_mcrypt_id"),
    app_commands.Choice(name="Bx", value="seller_bx_id"),
    app_commands.Choice(name="Ame", value="seller_ame_id")
])
async def set_seller(interaction: discord.Interaction, penjual: app_commands.Choice[str], user: discord.User):
    with open(bot.config_file, "r") as f:
        config = json.load(f)

    if not is_owner(interaction.user.id, config):
        return await interaction.response.send_message("🚫 Hanya Owner yang bisa melakukan setup penjual.", ephemeral=True)

    config[penjual.value] = user.id
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f"✅ Akun **{penjual.name}** berhasil di-set ke: {user.mention}", ephemeral=True)

@bot.tree.command(name="setrolebuyer", description="Set role yang otomatis didapat buyer saat beli")
@app_commands.describe(role="Role pembeli (contoh: Buyyer Kue)")
async def set_role_buyer(interaction: discord.Interaction, role: discord.Role):
    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    if not is_owner(interaction.user.id, config):
        return await interaction.response.send_message("🚫 Hanya Owner yang bisa set role buyer.", ephemeral=True)

    config["buyer_role_id"] = role.id
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f"✅ Role Buyer berhasil di-set ke: {role.mention}.", ephemeral=True)

@bot.tree.command(name="setchannel", description="Set channel panel stok")
@app_commands.describe(channel="Pilih channel untuk menampilkan panel stok")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    if not is_owner(interaction.user.id, config):
        return await interaction.response.send_message("🚫 Hanya Owner yang bisa set channel.", ephemeral=True)
        
    config["panel_channel_id"] = channel.id
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f"✅ Panel stok di-set ke {channel.mention}.", ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="tutup", description="Tutup tiket pembelian ini")
async def tutup_tiket(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("buy-cookies-"):
        return await interaction.response.send_message("❌ Command ini hanya bisa dipakai di dalam channel tiket.", ephemeral=True)

    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    penjual = get_seller_name(interaction.user.id, config)

    if not penjual and not is_owner(interaction.user.id, config):
        return await interaction.response.send_message("🚫 Hanya penjual/owner yang bisa menutup tiket.", ephemeral=True)

    await interaction.response.send_modal(CloseTicketModal())

@bot.tree.command(name="inputakun", description="Tambah akun Roblox via File .txt")
@app_commands.describe(
    penjual="Pilih penjual",
    file="Upload file .txt (Format per baris: user:pass:cookie)"
)
@app_commands.choices(penjual=[
    app_commands.Choice(name="Mcrypt", value="Mcrypt"),
    app_commands.Choice(name="Bx", value="Bx"),
    app_commands.Choice(name="Ame", value="Ame")
])
async def input_akun_file(interaction: discord.Interaction, penjual: app_commands.Choice[str], file: discord.Attachment):
    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    user_seller = get_seller_name(interaction.user.id, config)
    owner_check = is_owner(interaction.user.id, config)
    
    if not owner_check and not user_seller:
        return await interaction.response.send_message("❌ Kamu bukan penjual yang terdaftar!", ephemeral=True)
        
    if not owner_check and user_seller != penjual.value:
        return await interaction.response.send_message(f"❌ Kamu terdaftar sebagai {user_seller}, gabisa input ke stok {penjual.value}!", ephemeral=True)

    if not file.filename.endswith(".txt"):
        return await interaction.response.send_message("❌ Gagal! File harus berekstensi .txt", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    file_content = await file.read()
    text = file_content.decode('utf-8')

    lines = text.strip().split("\n")
    sukses = 0
    gagal = 0
    duplikat = 0

    with open(bot.db_file, "r") as f:
        accounts = json.load(f)

    existing_usernames = {acc["username"].lower() for acc in accounts if acc.get("seller") == penjual.value}

    for line in lines:
        line = line.strip()
        if not line: continue
        
        parts = line.split(":")
        if len(parts) < 3:
            gagal += 1
            continue

        username = parts[0].strip()
        password = parts[1].strip()
        cookies = ":".join(parts[2:]).strip()

        if username.lower() in existing_usernames:
            duplikat += 1
            continue

        accounts.append({
            "id": len(accounts) + 1,
            "username": username,
            "password": password,
            "cookies": cookies,
            "status": "available",
            "seller": penjual.value,
            "buyer": None,
            "reason": None,
            "gifted_at": None
        })
        
        existing_usernames.add(username.lower())
        sukses += 1

    with open(bot.db_file, "w") as f:
        json.dump(accounts, f, indent=4)

    embed = discord.Embed(title=f"📥 Input Akun {penjual.value} Selesai", color=0x2ecc71)
    embed.add_field(name="✅ Berhasil", value=f"{sukses}", inline=True)
    embed.add_field(name="❌ Gagal Format", value=f"{gagal}", inline=True)
    embed.add_field(name="⚠️ Duplikat", value=f"{duplikat}", inline=True)
    
    await interaction.followup.send(embed=embed, ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="giftakun", description="Kirim akun ke pembeli via DM setelah TF")
@app_commands.describe(user="Pembeli", jumlah="Jumlah akun", reason="Order ID / Alasan")
async def gift_akun(interaction: discord.Interaction, user: discord.User, jumlah: int, reason: str):
    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    penjual = get_seller_name(interaction.user.id, config)

    if not penjual and not is_owner(interaction.user.id, config):
        return await interaction.response.send_message("🚫 Kamu tidak punya akses untuk gift akun.", ephemeral=True)

    await interaction.response.defer(ephemeral=False)

    with open(bot.db_file, "r") as f:
        accounts = json.load(f)

    target_seller = penjual if penjual else "Mcrypt"

    available_accs = [a for a in accounts if a["status"] == "available" and a.get("seller") == target_seller]
    
    if len(available_accs) < jumlah:
        return await interaction.followup.send(f"❌ Stok kamu ({target_seller}) tidak cukup. Tersedia: **{len(available_accs)}**, diminta: **{jumlah}**")

    to_gift = available_accs[:jumlah]
    
    file_content = f"=== ROBLOX ACCOUNT DELIVERY ===\nSeller : {target_seller}\nBuyer  : {user.name} ({user.id})\nReason : {reason}\nJumlah : {jumlah}\nTanggal: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for i, acc in enumerate(to_gift):
        file_content += f"#{i+1}\nUsername : {acc['username']}\nPassword : {acc['password']}\nCookies  : {acc['cookies']}\n\n"
    file_content += "=== JANGAN BAGIKAN DATA INI ===\n"
    
    file_buffer = io.BytesIO(file_content.encode('utf-8'))
    file_discord = discord.File(fp=file_buffer, filename=f"roblox_accounts_{int(datetime.datetime.now().timestamp())}.txt")

    dm_embed = discord.Embed(
        title="🎁 Pesanan Akun Roblox Kamu",
        description=f"Terima kasih sudah membeli!\n\n📦 **Jumlah**: {jumlah} akun\n🧾 **Reason**: {reason}\n\nFile akun terlampir di bawah. **Segera ganti password & jangan bagikan data ini ke siapa pun.**",
        color=0x2ecc71
    )
    
    try:
        await user.send(embed=dm_embed, file=file_discord)
    except discord.Forbidden:
        return await interaction.followup.send(f"❌ Gagal kirim DM ke {user.mention}. Kemungkinan DM tertutup. Akun **tidak di-gift** (stok utuh).")

    gifted_ids = [a["id"] for a in to_gift]
    accounts = [a for a in accounts if a["id"] not in gifted_ids]

    with open(bot.db_file, "w") as f:
        json.dump(accounts, f, indent=4)

    sisa_stok = len([a for a in accounts if a["status"] == "available" and a.get("seller") == target_seller])
    
    res_embed = discord.Embed(title="✅ Gift Berhasil", color=0x2ecc71)
    res_embed.add_field(name="Penjual", value=target_seller, inline=True)
    res_embed.add_field(name="Penerima", value=user.mention, inline=True)
    res_embed.add_field(name="Jumlah", value=str(jumlah), inline=True)
    res_embed.add_field(name="Sisa Stok", value=str(sisa_stok), inline=True)
    
    await interaction.followup.send(embed=res_embed)
    await bot.update_panel()

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: DISCORD_TOKEN tidak ditemukan! Set di Environment Variables.")
    else:
        bot.run(TOKEN)
