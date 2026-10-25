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
                    "allowed_role_id": None, 
                    "buyer_role_id": None,
                    "panel_channel_id": None, 
                    "role_locked": False,
                }, f, indent=4)

        # Daftarin view tombol biar tetep idup pas bot restart
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
            stock = len([a for a in accounts if a["status"] == "available"])

        # Bikin format waktu WIB
        now_utc = datetime.datetime.utcnow()
        now_wib = now_utc + datetime.timedelta(hours=7)
        
        hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][now_wib.weekday()]
        waktu_sekarang = now_wib.strftime(f"{hari}, %d %B %Y - %H:%M WIB")
        
        embed = discord.Embed(
            title="📦 **Sisa Stock akun cookies roblox**",
            color=0x5865F2 
        )
            
        embed.add_field(
            name="📊 **Tersedia**", 
            value=f"```fix\n{stock} Akun\n```", 
            inline=False
        )

        embed.add_field(
            name="💰 **Harga**", 
            value=f"`{HARGA_PER_AKUN} Perak / Akun`", 
            inline=False
        )
        
        embed.add_field(
            name="🕒 **Terakhir Diperbarui**",
            value=f"`{waktu_sekarang}`",
            inline=False
        )
        
        embed.set_footer(text="Klik tombol di bawah untuk membeli.", icon_url=self.user.display_avatar.url)
        embed.timestamp = now_wib

        view = PanelView()

        # Cari & Edit panel lama biar ga spam chat
        async for msg in channel.history(limit=20):
            if msg.author.id == self.user.id and msg.embeds and "Sisa Stock akun cookies roblox" in msg.embeds[0].title:
                await msg.edit(embed=embed, view=view)
                return
        await channel.send(embed=embed, view=view)

bot = RobloxStoreBot()

# ================= HELPER CEK ROLE =================
def is_allowed(member: discord.Member):
    with open(bot.config_file, "r") as f:
        config = json.load(f)
    allowed_role_id = config.get("allowed_role_id")
    if not allowed_role_id:
        return False
    return discord.utils.get(member.roles, id=int(allowed_role_id)) is not None

# ================= INTERAKSI TOMBOL & FORM =================
class BeliModal(discord.ui.Modal, title="Form Pembelian Akun Roblox"):
    jumlah = discord.ui.TextInput(
        label="Jumlah Akun",
        placeholder="Masukkan angka (Contoh: 1)",
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Validasi input wajib angka
        if not self.jumlah.value.isdigit():
            return await interaction.response.send_message("❌ Gagal! Kamu harus memasukkan angka murni.", ephemeral=True)
        
        jumlah_beli = int(self.jumlah.value)
        if jumlah_beli <= 0:
            return await interaction.response.send_message("❌ Gagal! Minimal beli 1 akun.", ephemeral=True)

        # Cek stok
        with open(bot.db_file, "r") as f:
            accounts = json.load(f)
        stok_tersedia = len([a for a in accounts if a["status"] == "available"])

        if jumlah_beli > stok_tersedia:
            return await interaction.response.send_message(f"❌ Gagal! Stok tidak cukup. Sisa stok: **{stok_tersedia}**", ephemeral=True)

        await interaction.response.send_message("⏳ Sedang membuat tiket private...", ephemeral=True)

        guild = interaction.guild
        buyer = interaction.user

        with open(bot.config_file, "r") as f:
            config = json.load(f)
            
        penjual_role_id = int(config.get("allowed_role_id"))
        buyer_role_id = config.get("buyer_role_id")

        # Bikin Overwrites Permission Channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), # Orang lain gabisa liat
            buyer: discord.PermissionOverwrite(read_messages=True, send_messages=True), # Buyer bisa liat
            guild.get_role(penjual_role_id): discord.PermissionOverwrite(read_messages=True, send_messages=True), # Penjual bisa liat
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True) # Bot bisa liat
        }

        # Bikin Channel Tiket
        ticket_channel = await guild.create_text_channel(
            name=f"buy-cookies-{jumlah_beli}",
            overwrites=overwrites,
            category=interaction.channel.category
        )

        # --- AUTO KASIH ROLE BUYER (CEK DULU) ---
        if buyer_role_id:
            role_buyer = guild.get_role(int(buyer_role_id))
            if role_buyer:
                if role_buyer not in buyer.roles:
                    try:
                        await buyer.add_roles(role_buyer)
                        print(f"Role {role_buyer.name} diberikan ke {buyer.name}")
                    except Exception as e:
                        print(f"Gagal ngasih role buyer: {e}")
                else:
                    print(f"{buyer.name} udah punya role buyer, skip.")

        # Kirim pesan di dalam tiket
        embed_tiket = discord.Embed(
            title="🧾 Tiket Pembelian",
            description=f"Halo {buyer.mention}, terima kasih sudah memesan!\n\n"
                        f"📦 **Jumlah:** {jumlah_beli} Akun\n"
                        f"💰 **Total Harga:** {jumlah_beli * HARGA_PER_AKUN} Perak\n\n"
                        f"Silakan tunggu Admin/Penjual untuk memproses pesananmu.\n"
                        f"*(Admin akan mengirimkan akun setelah pembayaran dikonfirmasi).*",
            color=0x2ecc71
        )
        
        # Tombol Tutup Tiket (Cuma muncul di dalam channel tiket)
        view_tiket = discord.ui.View()
        view_tiket.add_item(discord.ui.Button(label="Tutup Tiket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn"))

        await ticket_channel.send(content=f"{buyer.mention} | <@&{penjual_role_id}>", embed=embed_tiket, view=view_tiket)
        
        # Kirim DM Notif ke Buyer
        try:
            await buyer.send(f"✅ Tiket pembelianmu sudah dibuat di server **{guild.name}**. Silakan cek channel {ticket_channel.mention}.")
        except:
            pass

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # CUMA TOMBOL BELI DI PANEL STOK
    @discord.ui.button(label="Beli Akun", emoji="🛒", style=discord.ButtonStyle.success, custom_id="beli_akun_btn")
    async def beli_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BeliModal())

# ================= COMMANDS =================

@bot.tree.command(name="setup", description="Set role penjual (HANYA BISA DILAKUKAN SEKALI)")
@app_commands.describe(role="Role yang diizinkan mengakses command penjual")
async def setup_role(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("🚫 Hanya Administrator server yang bisa melakukan setup awal.", ephemeral=True)

    with open(bot.config_file, "r") as f:
        config = json.load(f)

    if config["role_locked"]:
        return await interaction.response.send_message("🔒 Role penjual sudah di-set sebelumnya dan **tidak bisa diubah lagi**.", ephemeral=True)

    config["allowed_role_id"] = role.id
    config["role_locked"] = True
    
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    embed = discord.Embed(
        title="✅ Setup Penjual Berhasil",
        description=f"Role penjual dikunci ke: {role.mention}\n\n⚠️ **Role terkunci permanen.**",
        color=0x2ecc71
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="setrolebuyer", description="Set role yang otomatis didapat buyer saat beli")
@app_commands.describe(role="Role pembeli (contoh: Buyyer Kue)")
async def set_role_buyer(interaction: discord.Interaction, role: discord.Role):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)

    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    config["buyer_role_id"] = role.id
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f"✅ Role Buyer berhasil di-set ke: {role.mention}. Buyer baru akan otomatis dapat role ini.", ephemeral=True)

@bot.tree.command(name="setchannel", description="Set channel untuk info stok panel")
@app_commands.describe(channel="Pilih channel untuk menampilkan panel stok")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)
        
    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    config["panel_channel_id"] = channel.id
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f"✅ Panel stok berhasil dibuat di {channel.mention}.", ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="close", description="Tutup tiket pembelian ini")
async def close_ticket(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("buy-cookies-"):
        return await interaction.response.send_message("❌ Command ini hanya bisa dipakai di dalam channel tiket.", ephemeral=True)

    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Hanya penjual yang bisa menutup tiket manual lewat command ini.", ephemeral=True)

    await interaction.response.send_message("🔒 Menutup tiket...", ephemeral=True)
    await asyncio.sleep(2)
    
    # Cari buyer di dalam channel
    buyer = None
    for target, overwrite in interaction.channel.overwrites.items():
        if isinstance(target, discord.Member) and not target.bot and target.id != interaction.user.id:
             buyer = target
             break

    # Kirim DM ke buyer sebelum channel dihapus
    if buyer:
        try:
            await buyer.send(f"🔒 Tiket pembelianmu di server **{interaction.guild.name}** telah ditutup oleh Admin. Terima kasih!")
        except:
            pass

    await interaction.channel.delete()

@bot.tree.command(name="inputakun", description="Tambah akun Roblox (format: user:pass:cookie)")
@app_commands.describe(akun="Format: username:password:cookies")
async def input_akun(interaction: discord.Interaction, akun: str):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)

    lines = akun.strip().split("\n")
    sukses = 0
    gagal = 0

    with open(bot.db_file, "r") as f:
        accounts = json.load(f)

    for line in lines:
        parts = line.strip().split(":")
        if len(parts) < 3:
            gagal += 1
            continue

        username = parts[0].strip()
        password = parts[1].strip()
        cookies = ":".join(parts[2:]).strip()

        accounts.append({
            "id": len(accounts) + 1,
            "username": username,
            "password": password,
            "cookies": cookies,
            "status": "available",
            "buyer": None,
            "reason": None,
            "gifted_at": None
        })
        sukses += 1

    with open(bot.db_file, "w") as f:
        json.dump(accounts, f, indent=4)

    stock = len([a for a in accounts if a["status"] == "available"])
    
    embed = discord.Embed(title="📥 Input Akun Selesai", color=0x2ecc71)
    embed.add_field(name="✅ Berhasil", value=f"{sukses}", inline=True)
    embed.add_field(name="❌ Gagal", value=f"{gagal}", inline=True)
    embed.add_field(name="📦 Total Stok", value=f"{stock} akun", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="giftakun", description="Kirim akun ke pembeli via DM setelah TF")
@app_commands.describe(user="Pembeli", jumlah="Jumlah akun", reason="Order ID / Alasan")
async def gift_akun(interaction: discord.Interaction, user: discord.User, jumlah: int, reason: str):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    with open(bot.db_file, "r") as f:
        accounts = json.load(f)

    available_accs = [a for a in accounts if a["status"] == "available"]
    
    if len(available_accs) < jumlah:
        return await interaction.followup.send(f"❌ Stok tidak cukup. Tersedia: **{len(available_accs)}**, diminta: **{jumlah}**", ephemeral=True)

    to_gift = available_accs[:jumlah]
    
    file_content = f"=== ROBLOX ACCOUNT DELIVERY ===\nBuyer  : {user.name} ({user.id})\nReason : {reason}\nJumlah : {jumlah}\nTanggal: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
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
        return await interaction.followup.send(f"❌ Gagal kirim DM ke {user.mention}. Kemungkinan DM tertutup. Akun **tidak di-gift** (stok utuh).", ephemeral=True)

    for acc in accounts:
        if acc["id"] in [a["id"] for a in to_gift]:
            acc["status"] = "gifted"
            acc["buyer"] = str(user.id)
            acc["reason"] = reason
            acc["gifted_at"] = str(datetime.datetime.now())

    with open(bot.db_file, "w") as f:
        json.dump(accounts, f, indent=4)

    sisa_stok = len([a for a in accounts if a["status"] == "available"])
    res_embed = discord.Embed(title="✅ Gift Berhasil", color=0x2ecc71)
    res_embed.add_field(name="Penerima", value=user.mention, inline=True)
    res_embed.add_field(name="Jumlah", value=str(jumlah), inline=True)
    res_embed.add_field(name="Sisa Stok", value=str(sisa_stok), inline=True)
    
    await interaction.followup.send(embed=res_embed, ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="stock", description="Cek stok akun (Bisa diakses publik)")
async def cek_stock(interaction: discord.Interaction):
    with open(bot.db_file, "r") as f:
        accounts = json.load(f)
    stok = len([a for a in accounts if a["status"] == "available"])
    await interaction.response.send_message(f"📦 Stok saat ini: **{stok}** akun. Silakan cek channel panel untuk info detail.", ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: DISCORD_TOKEN tidak ditemukan! Set di Environment Variables.")
    else:
        bot.run(TOKEN)
