import discord
from discord import app_commands

from discord.ext import commands, tasks

import os
import time

import datetime

import sqlite3

import math

import asyncio

import functools

import json

import urllib.parse

import urllib.request

import random


import yt_dlp

intents = discord.Intents.default()

intents.message_content = True

intents.members = True

intents.presences = True

if hasattr(intents, 'polls'):
    intents.polls = True

intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ===== CHONG LOI BUTTON / INTERACTION =====
async def _safe_view_on_error(view, interaction: discord.Interaction, error: Exception, item):
    print(f"[BUTTON ERROR] {type(error).__name__}: {error}")
    try:
        message = "⚠️ Nút này vừa gặp lỗi. Hãy thử bấm lại hoặc mở lại bảng."
        if isinstance(error, discord.NotFound):
            message = "⚠️ Bảng này đã hết hạn hoặc tin nhắn không còn tồn tại. Hãy mở lại bảng."
        elif isinstance(error, discord.Forbidden):
            message = "⚠️ BirthdayTime không có đủ quyền để thực hiện thao tác này."
        elif isinstance(error, discord.HTTPException):
            message = "⚠️ Discord đang bận hoặc thao tác vừa hết hạn. Hãy thử lại."
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass
    except Exception as exc:
        print(f"[BUTTON ERROR HANDLER] {exc}")

discord.ui.View.on_error = _safe_view_on_error

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    original = getattr(error, "original", error)
    print(f"[COMMAND ERROR] {ctx.command}: {type(original).__name__}: {original}")
    try:
        if ctx.channel:
            await ctx.send("⚠️ Lệnh vừa gặp lỗi. Hãy thử lại sau.", delete_after=8)
    except (discord.Forbidden, discord.HTTPException):
        pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    original = getattr(error, "original", error)
    print(f"[SLASH ERROR] {type(original).__name__}: {original}")
    try:
        message = "⚠️ Lệnh vừa gặp lỗi. Hãy thử lại sau."
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass

db_conn = sqlite3.connect('database.db')

db_cursor = db_conn.cursor()

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS levels (\n        user_id INTEGER,\n        guild_id INTEGER,\n        xp INTEGER,\n        level INTEGER,\n        PRIMARY KEY (user_id, guild_id)\n    )\n')

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS level_roles (\n        guild_id INTEGER,\n        level INTEGER,\n        role_id INTEGER,\n        PRIMARY KEY (guild_id, level)\n    )\n')

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS server_level_channels (\n        guild_id INTEGER PRIMARY KEY,\n        channel_id INTEGER\n    )\n')

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS server_boost_roles (\n        guild_id INTEGER PRIMARY KEY,\n        role_id INTEGER\n    )\n')

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS polls (\n        message_id INTEGER PRIMARY KEY,\n        guild_id INTEGER,\n        channel_id INTEGER,\n        question TEXT,\n        options TEXT,\n        created_by INTEGER\n    )\n')

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS announcement_channels (\n        guild_id INTEGER PRIMARY KEY,\n        channel_id INTEGER\n    )\n')

db_conn.commit()

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS voice_channels (\n        guild_id INTEGER PRIMARY KEY,\n        channel_id INTEGER NOT NULL\n    )\n')

db_conn.commit()

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS self_role_config (\n        guild_id INTEGER PRIMARY KEY,\n        role_ids TEXT NOT NULL,\n        message TEXT NOT NULL\n    )\n')

db_conn.commit()

db_cursor.execute('\n    CREATE TABLE IF NOT EXISTS welcome_config (\n        guild_id INTEGER PRIMARY KEY,\n        channel_id INTEGER,\n        message TEXT NOT NULL,\n        gif_path TEXT\n    )\n')

db_conn.commit()

voice_keepalive_tasks = {}

async def keep_voice_connected(guild_id: int, channel_id: int):
    """Giữ bot trong voice channel và tự kết nối lại khi bị ngắt."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            guild = bot.get_guild(guild_id)
            if not guild:
                return
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                return
            voice = guild.voice_client
            if voice is None:
                await channel.connect(reconnect=True, timeout=30)
            elif not voice.is_connected():
                await voice.disconnect(force=True)
                await asyncio.sleep(2)
                await channel.connect(reconnect=True, timeout=30)
            elif voice.channel and voice.channel.id != channel_id:
                await voice.move_to(channel)
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f'⚠️  Treo call guild {guild_id}: {e}')
            await asyncio.sleep(5)

def start_voice_keepalive(guild_id: int, channel_id: int):
    old_task = voice_keepalive_tasks.get(guild_id)
    if old_task and (not old_task.done()):
        old_task.cancel()
    voice_keepalive_tasks[guild_id] = asyncio.create_task(keep_voice_connected(guild_id, channel_id))

def stop_voice_keepalive(guild_id: int):
    task = voice_keepalive_tasks.pop(guild_id, None)
    if task and (not task.done()):
        task.cancel()

afk_users = {}

user_birthdays = {}

server_congrats_channels = {}

server_boost_channels = {}

server_stats_channels = {}

WELCOME_CONFIG = {'channel_id': None, 'message': 'Chào mừng {name} đã gia nhập **{server}**!\n\n**Chào con vk:** {member}\n**Con vk là thành viên:** `{number}`\nNhững người hỗ trợ:<@1315601796424794173>,<@1073202800965713961>,<@1502755916334760169> & <@1466395005487812620>\nDev Web: <@999253748616548362>\nDev Bot: <@1548490039158251531>', 'gif_path': 'welcome_gif.gif'}

BOOST_CONFIG = {'channel_id': None, 'message': 'Cảm ơn {member} đã Boost máy chủ **{server}** để giúp server ngày càng phát triển hơn! 🚀💎', 'gif_path': 'boost_gif.gif'}

LEVEL_ROLE_MILESTONES = [1, 25, 50, 100, 200]

LEVELUP_CONFIG = {'message': 'Chúc mừng {member} đã đạt đến **Cấp độ {level} / 300**! 🌟{role_mention}', 'gif_path': 'levelup_gif.gif'}

SPECIAL_ADMIN_ID = 1548490039158251531

ALLOWED_GUILD_ID = 1503922700408586240

UNAUTHORIZED_GUILD_MESSAGE = '<a:emoji_44:1541290870966325318> Đây là đâu ?, BirthdayTime mới là nhà của t'

async def leave_unauthorized_guild(guild: discord.Guild):
    """Báo trong server không được phép rồi tự rời server."""
    if guild.id == ALLOWED_GUILD_ID:
        return
    try:
        channels = []
        if guild.system_channel is not None:
            channels.append(guild.system_channel)
        channels.extend((ch for ch in guild.text_channels if ch not in channels))
        for channel in channels:
            try:
                perms = channel.permissions_for(guild.me) if guild.me else None
                if perms is not None and (not perms.send_messages):
                    continue
                await channel.send(UNAUTHORIZED_GUILD_MESSAGE)
                break
            except (discord.Forbidden, discord.HTTPException):
                continue
    except Exception as e:
        print(f'⚠️  Lỗi gửi tin rời guild {guild.id}: {e}')
    await asyncio.sleep(0.5)
    try:
        await guild.leave()
        print(f'🚪 Đã tự động rời guild không được phép: {guild.id} ({guild.name})')
    except Exception as e:
        print(f'⚠️  Không thể rời guild {guild.id}: {e}')

async def enforce_guild_allowlist():
    for guild in list(bot.guilds):
        if guild.id != ALLOWED_GUILD_ID:
            await leave_unauthorized_guild(guild)

@bot.check
async def global_guild_check(ctx: commands.Context):
    if ctx.guild is None:
        return True
    if ctx.guild.id == ALLOWED_GUILD_ID:
        return True
    await leave_unauthorized_guild(ctx.guild)
    return False

async def global_slash_guild_check(interaction: discord.Interaction):
    if interaction.guild is None:
        return True
    if interaction.guild.id == ALLOWED_GUILD_ID:
        return True
    await leave_unauthorized_guild(interaction.guild)
    return False

bot.tree.interaction_check = global_slash_guild_check

@bot.event
async def on_guild_join(guild: discord.Guild):
    if guild.id != ALLOWED_GUILD_ID:
        await leave_unauthorized_guild(guild)

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

def add_standard_footer(embed: discord.Embed):
    now_vn = datetime.datetime.now(VN_TZ)
    embed.set_footer(text=f"by w.dec • 🇻🇳 {now_vn.strftime('%H:%M:%S %d/%m/%Y')}")
    embed.timestamp = now_vn
    return embed

def make_embed(*args, **kwargs):
    embed = discord.Embed(*args, **kwargs)
    add_standard_footer(embed)
    return embed

class BirthdayModal(discord.ui.Modal, title='<a:happybirthday:1548593066158465044> Đăng ký Ngày Sinh Nhật'):
    dob_input = discord.ui.TextInput(label='Ngày sinh (DD/MM/YYYY)', placeholder='25/12/2004', required=True, max_length=15)

    async def on_submit(self, interaction: discord.Interaction):
        user_birthdays[interaction.user.id] = self.dob_input.value.strip()
        await interaction.response.send_message('<a:verify:1548178353859596320> Đã lưu ngày sinh thành công!', ephemeral=True)

class BirthdayView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🎉 Nhập ngày sinh', style=discord.ButtonStyle.primary, custom_id='setup_birthday_btn')
    async def birthday_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayModal())


class AnnouncementModal(discord.ui.Modal, title='TAO THONG BAO PRO'):
    title_input = discord.ui.TextInput(label='Tiêu đề thông báo', placeholder='Ví dụ: 📢 Thông báo sự kiện mới', required=True, max_length=256)
    content_input = discord.ui.TextInput(label='Nội dung thông báo', placeholder='Nhập nội dung cần gửi... Có thể dùng @everyone hoặc @here nếu cần.', style=discord.TextStyle.paragraph, required=True, max_length=4000)
    media_input = discord.ui.TextInput(label='Ảnh / Video / Link (không bắt buộc)', placeholder='Dán URL ảnh, video hoặc đường dẫn website', required=False, max_length=1000)
    poll_question = discord.ui.TextInput(label='Câu hỏi bình chọn (không bắt buộc)', placeholder='Để trống nếu không muốn tạo bình chọn', required=False, max_length=256)
    poll_options = discord.ui.TextInput(label='Lựa chọn bình chọn', placeholder='Ví dụ: Có, Không, Chưa chắc, Tùy (cách nhau bằng dấu phẩy)', required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        db_cursor.execute('SELECT channel_id FROM announcement_channels WHERE guild_id = ?', (interaction.guild.id,))
        row = db_cursor.fetchone()
        if not row:
            await interaction.followup.send('<a:failed:1548973085741547580> Chưa cài kênh thông báo. Dùng `/setannouncement` trước.', ephemeral=True)
            return
        channel = interaction.guild.get_channel(row[0])
        if not channel:
            await interaction.followup.send('<a:failed:1548973085741547580> Không tìm thấy kênh thông báo. Hãy cài lại bằng `/setannouncement`.', ephemeral=True)
            return
        title = self.title_input.value.strip()
        content = self.content_input.value.strip()
        media_url = self.media_input.value.strip()
        question = self.poll_question.value.strip()
        options = [x.strip() for x in self.poll_options.value.split(',') if x.strip()]
        if question and (not 2 <= len(options) <= 4):
            await interaction.followup.send('<a:failed:1548973085741547580> Bình chọn phải có từ **2 đến 4 lựa chọn**, ngăn cách bằng dấu phẩy.', ephemeral=True)
            return
        if options and (not question):
            await interaction.followup.send('<a:failed:1548973085741547580> Bạn đã nhập lựa chọn nhưng chưa nhập câu hỏi bình chọn.', ephemeral=True)
            return
        if media_url and (not media_url.startswith(('http://', 'https://'))):
            await interaction.followup.send('<a:failed:1548973085741547580> Link ảnh/video phải bắt đầu bằng `http://` hoặc `https://`.', ephemeral=True)
            return
        role_id = 1515041455805304953
        embed = make_embed(title=title, description=content, color=discord.Color.from_rgb(0, 0, 0))
        add_standard_footer(embed)
        send_content = f'<@&{role_id}>'
        if media_url:
            lower_url = media_url.lower().split('?')[0]
            image_exts = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
            if lower_url.endswith(image_exts):
                embed.set_image(url=media_url)
            else:
                embed.add_field(name='🔗 Liên kết đính kèm', value=media_url, inline=False)
                send_content += f'\n{media_url}'
        try:
            await channel.send(content=send_content, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))
            if question:
                if not hasattr(discord, 'Poll'):
                    await interaction.followup.send('<a:verify:1548178353859596320> Đã gửi thông báo, nhưng Discord.py hiện tại chưa hỗ trợ bình chọn native.', ephemeral=True)
                    return
                poll = discord.Poll(question=question, duration=datetime.timedelta(days=7), allow_multiselect=False)
                for option in options:
                    poll.add_answer(text=option)
                await channel.send(poll=poll)
            await interaction.followup.send(f'<a:verify:1548178353859596320> Đã gửi thông báo thành công vào {channel.mention}' + (' kèm bình chọn.' if question else '.'), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send('<a:failed:1548973085741547580> Bot không có quyền gửi tin nhắn hoặc bình chọn vào kênh đó.', ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f'<a:failed:1548973085741547580> Discord từ chối gửi thông báo: `{e}`', ephemeral=True)

def is_admin_or_special(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator or interaction.user.id == SPECIAL_ADMIN_ID



@tasks.loop(hours=24)
async def check_birthdays():
    now = datetime.datetime.now()
    today_str = now.strftime('%d/%m')
    for guild in bot.guilds:
        if guild.id not in server_congrats_channels:
            continue
        channel = guild.get_channel(server_congrats_channels[guild.id])
        if not channel:
            continue
        for user_id, dob_str in user_birthdays.items():
            if dob_str.startswith(today_str):
                member = guild.get_member(user_id)
                if member:
                    embed = make_embed(title='<a:chcmng:1547243888639615097> CHÚC MỪNG SINH NHẬT! <a:birthday:1548993737915367424>', description=f' {member} Đã thêm tuổi mới nha! Chúc mem càng ngày tốt đẹp trong công việc và việc học nha! 🥳', color=discord.Color.pink())
                    if os.path.exists(BIRTHDAY_GIF_PATH):
                        await channel.send(embed=embed, file=discord.File(BIRTHDAY_GIF_PATH, filename='hb_gif.gif'))
                    else:
                        await channel.send(embed=embed)

MASOI_ROLE_INFO = {'Dân Làng': ('<:lang:1547587120825372752> Phe Dân Làng', 'Không có kỹ năng đặc biệt.'), 'Tiên Tri': ('<:lang:1547587120825372752> Phe Dân Làng', 'Mỗi đêm soi 1 người để biết có phải Ma Sói hay không.'), 'Bảo Vệ': ('<:lang:1547587120825372752> Phe Dân Làng', 'Mỗi đêm bảo vệ 1 người khỏi Ma Sói.'), 'Thợ Săn': ('<:lang:1547587120825372752> Phe Dân Làng', 'Vai đặc biệt của phe Dân.'), 'Cupid': ('<:lang:1547587120825372752> Phe Dân Làng', 'Ghép 2 người thành cặp tình yêu.'), 'Sói Thường': ('<:werewolf:1547564934299390082> Phe Ma Sói', 'Cùng phe Sói chọn người để cắn mỗi đêm.'), 'Sói Alpha': ('<:werewolf:1547564934299390082> Phe Ma Sói', 'Sói đặc biệt.'), 'Sói Con': ('<:werewolf:1547564934299390082> Phe Ma Sói', 'Sói đặc biệt, có cơ chế riêng khi bị loại.'), 'Sói Sát Thủ': ('<:werewolf:1547564934299390082> Phe Ma Sói', 'Sói đặc biệt có khả năng hạ mục tiêu.')}

MASOI_ROLE_EMOJI = {'Dân Làng': '<:villagers:1547581626379403355>', 'Tiên Tri': '<:prophesy:1547582737601404970>', 'Bảo Vệ': '<:protect:1547583282034770000>', 'Thợ Săn': '<:hunter:1547584512119021588>', 'Cupid': '<:Cupid:1547584816461906024>', 'Sói Thường': '<:codoc:1547585598058008576>', 'Sói Alpha': '<:alpha:1547585783517675623>', 'Sói Con': '<:tuat:1547586268412510229>', 'Sói Sát Thủ': '<:wolf:1547585086872887376>'}

MASOI_ROOMS = {}

def masoi_alive_winner(room):
    """Trả về phe thắng nếu đã đủ điều kiện; None nếu ván chưa kết thúc."""
    roles = room.get('roles', {})
    dead = set(room.get('dead', []))
    alive = [uid for uid in room.get('players', []) if uid not in dead]
    wolves = [uid for uid in alive if roles.get(uid) in {'Sói Thường', 'Sói Alpha', 'Sói Con', 'Sói Sát Thủ'}]
    villagers = [uid for uid in alive if roles.get(uid) not in {'Sói Thường', 'Sói Alpha', 'Sói Con', 'Sói Sát Thủ'}]
    if not wolves:
        return 'Dân Làng'
    if len(wolves) >= len(villagers):
        return 'Ma Sói'
    return None

async def masoi_finish_game(room, winner):
    if room.get('game_finished'):
        return False
    room['game_finished'] = True
    room['winner'] = winner
    old_task = room.get('phase_task')
    if old_task and (not old_task.done()):
        old_task.cancel()
    room['started'] = False
    room['phase'] = 'finished'
    return True

def masoi_roles_for_count(n):
    wolf_count = 2 if n <= 8 else 3 if n <= 12 else 4 if n <= 16 else 5 if n <= 20 else 6
    special = []
    if n >= 6:
        special += ['Tiên Tri', 'Bảo Vệ']
    if n >= 10:
        special += ['Thợ Săn', 'Cupid']
    if n >= 16:
        special += ['Sói Alpha']
    if n >= 19:
        special += ['Sói Con']
    if n >= 22:
        special += ['Sói Sát Thủ']
    wolves = ['Sói Thường'] * wolf_count
    if 'Sói Alpha' in special:
        wolves[0] = 'Sói Alpha'
        special.remove('Sói Alpha')
    if 'Sói Con' in special:
        wolves[1 if len(wolves) > 1 else 0] = 'Sói Con'
        special.remove('Sói Con')
    if 'Sói Sát Thủ' in special:
        wolves[2 if len(wolves) > 2 else 0] = 'Sói Sát Thủ'
        special.remove('Sói Sát Thủ')
    roles = wolves + special
    while len(roles) < n:
        roles.append('Dân Làng')
    return roles[:n]

async def masoi_set_chat_lock(room, locked: bool):
    guild = bot.get_guild(room['guild_id'])
    channel = guild.get_channel(room['channel_id']) if guild else None
    if not channel:
        return (False, 'Không tìm thấy kênh phòng.')
    failed = []
    for uid in room['players']:
        member = guild.get_member(uid)
        if not member:
            continue
        try:
            await channel.set_permissions(member, send_messages=False if locked else None, add_reactions=False if locked else None, reason='Ma Sói: khóa/mở chat người chơi')
        except discord.Forbidden:
            failed.append(member.display_name)
    room['chat_locked'] = locked
    if failed:
        return (False, 'Bot thiếu quyền quản lý quyền kênh hoặc không thể cập nhật: ' + ', '.join(failed[:5]))
    return (True, None)

def masoi_phase_embed(phase, seconds_left=None):
    if phase == 'day':
        title = '☀️  BAN NGÀY  •  THẢO LUẬN'
        color = discord.Color.gold()
        duration = '3 phút'
        status = '<:unlock:1548990393113116672> Chat đang mở'
        tip = 'Thảo luận, nghi ngờ và bỏ phiếu.'
    else:
        title = '🌙  BAN ĐÊM  •  IM LẶNG'
        color = discord.Color.dark_purple()
        duration = '2 phút'
        status = '<:lock:1548990424067080223> Chat đang khóa'
        tip = 'Không thể chat trong phòng. Hãy chờ đêm kết thúc.'
    embed = make_embed(title=title, color=color)
    if seconds_left is not None:
        m, s = divmod(max(0, int(seconds_left)), 60)
        embed.description = f'### <a:clock:1548984730765099088> Còn **{m:02d}:{s:02d}**\n{status}'
    else:
        embed.description = f'### <a:clock:1548984730765099088> Thời lượng **{duration}**\n{status}'
    embed.add_field(name='📜 Trạng thái', value=tip, inline=False)
    embed.add_field(name='☀️ Ngày', value='3:00', inline=True)
    embed.add_field(name='🌙 Đêm', value='2:00', inline=True)
    return embed

WEREWOLF_BITE_EMOJI = '<a:werewolf_rnj29zcw:1547492968691269662>'

WEREWOLF_ROLE_EMOJI = '<a:werewolf562516:1547493117786329098>'

async def masoi_remove_player_from_room(room, victim_id):
    """Ẩn người bị Ma Sói cắn khỏi kênh phòng, nhưng vẫn giữ họ trong dữ liệu ván."""
    guild = bot.get_guild(room.get('guild_id'))
    channel = guild.get_channel(room.get('channel_id')) if guild else None
    member = guild.get_member(victim_id) if guild else None
    if not channel or not member:
        return (False, 'Không tìm thấy người chơi hoặc kênh phòng.')
    try:
        await channel.set_permissions(member, view_channel=False, send_messages=False, add_reactions=False, reason='Ma Sói: người chơi bị cắn rời phòng')
        return (True, None)
    except discord.Forbidden:
        return (False, 'Bot thiếu quyền Manage Channels để cho người bị cắn rời phòng.')

async def masoi_resolve_night(room):
    """Xử lý mục tiêu bị Sói cắn khi đêm kết thúc."""
    if not room.get('started'):
        return None
    dead = set(room.setdefault('dead', []))
    roles = room.get('roles', {})
    wolf_roles = {'Sói Thường', 'Sói Alpha', 'Sói Con', 'Sói Sát Thủ'}
    votes = {}
    for uid, action in room.get('actions', {}).items():
        if action.get('phase') != 'night' or action.get('target') in dead:
            continue
        if roles.get(uid) not in wolf_roles:
            continue
        target = int(action.get('target'))
        if roles.get(target) in wolf_roles:
            continue
        votes[target] = votes.get(target, 0) + 1
    if not votes:
        return None
    victim_id = max(votes, key=votes.get)
    dead.add(victim_id)
    room['dead'] = list(dead)
    room.setdefault('actions', {})[victim_id] = {'role': roles.get(victim_id), 'phase': 'dead'}
    ok, err = await masoi_remove_player_from_room(room, victim_id)
    guild = bot.get_guild(room.get('guild_id'))
    try:
        victim_member = guild.get_member(victim_id) if guild else None
        if victim_member:
            await victim_member.send('<:dead:1547577908149747732> Bạn đã bị giết trong ván Ma Sói. Bạn không thể nhìn thấy tên của Ma Sói.')
    except discord.Forbidden:
        pass
    member = guild.get_member(victim_id) if guild else None
    victim_name = member.display_name if member else f'<@{victim_id}>'
    return {'victim_id': victim_id, 'victim_name': victim_name, 'ok': ok, 'err': err, 'votes': votes.get(victim_id, 0)}

def masoi_status_embed(room):
    """Bảng trạng thái sống/chết được gửi mỗi khi trời sáng."""
    guild = bot.get_guild(room.get('guild_id'))
    dead = set(room.get('dead', []))
    players = room.get('players', [])
    alive_lines = []
    dead_lines = []
    for index, uid in enumerate(players, 1):
        member = guild.get_member(uid) if guild else None
        mention = member.mention if member else f'<@{uid}>'
        if uid in dead:
            dead_lines.append(f'<:dead:1547577908149747732> {mention}')
        else:
            alive_lines.append(f'<:member:1547566263381794846>{mention}')
    alive_text = '\n'.join(alive_lines) if alive_lines else 'Không còn người sống'
    dead_text = '\n'.join(dead_lines) if dead_lines else 'Chưa có người chết'
    embed = make_embed(title='☀️ THÔNG BÁO BUỔI SÁNG', description='Danh sách người chơi sau đêm vừa qua:', color=discord.Color.gold())
    embed.add_field(name=f'<:banlmjdctoi:1506650381688766564> NGƯỜI CÒN SỐNG • {len(alive_lines)}', value=alive_text[:1024], inline=False)
    embed.add_field(name=f'<:emoji_38:1532983692237078548>NGƯỜI ĐÃ CHẾT • {len(dead_lines)}', value=dead_text[:1024], inline=False)
    return embed

async def masoi_phase_timer(room_id, phase, seconds):
    """Tự động chuyển Ngày/Đêm: đêm 2 phút, ngày 3 phút."""
    try:
        await asyncio.sleep(seconds)
        room = MASOI_ROOMS.get(room_id)
        if not room or not room.get('started') or room.get('phase') != phase:
            return
        night_result = None
        if phase == 'night':
            night_result = await masoi_resolve_night(room)
        winner = masoi_alive_winner(room)
        if winner:
            game_finished = await masoi_finish_game(room, winner)
            channel = bot.get_channel(room.get('channel_id'))
            if channel and game_finished:
                emoji = '<:werewolf:1547564934299390082>' if winner == 'Ma Sói' else '<:lang:1547587120825372752>'
                guild = bot.get_guild(room.get('guild_id'))
                names = []
                for uid in room.get('players', []):
                    role = room.get('roles', {}).get(uid)
                    wolf_roles = {'Sói Thường', 'Sói Alpha', 'Sói Con', 'Sói Sát Thủ'}
                    is_winner = winner == 'Ma Sói' and role in wolf_roles or (winner == 'Dân Làng' and role not in wolf_roles)
                    if is_winner:
                        member = guild.get_member(uid) if guild else None
                        names.append(member.mention if member else f'<@{uid}>')
                winner_lines = [f'<:member:1547566263381794846>{name}' for name in names[:25]]
                embed = make_embed(description='<a:chcmng:1547243888639615097> chúc mừng các member chiến thắng<a:699660goldcrown:1547563982393450556>\n' + ('\n'.join(winner_lines) if winner_lines else ''), color=discord.Color.from_rgb(0, 0, 0))
                await channel.send(embed=embed)
                if not room.get('coin_rewarded'):
                    room['coin_rewarded'] = True
                    guild = bot.get_guild(room.get('guild_id'))
                    winner_mentions = []
                    wolf_roles = {'Sói Thường', 'Sói Alpha', 'Sói Con', 'Sói Sát Thủ'}
                    for uid in room.get('players', []):
                        role = room.get('roles', {}).get(uid)
                        is_winner = winner == 'Ma Sói' and role in wolf_roles or (winner == 'Dân Làng' and role not in wolf_roles)
                        if is_winner:
                            baucua_change_coins(uid, GAME_WIN_REWARD)
                            member = guild.get_member(uid) if guild else None
                            winner_mentions.append(member.mention if member else f'<@{uid}>')
                    winner_label = f'<:werewolf:1547564934299390082> **Ma sói win**' if winner == 'Ma Sói' else f'<:villagers:1547581626379403355> **Dân làng win**'
                    await channel.send(embed=game_coin_reward_embed('MA SÓI', winner_mentions, GAME_WIN_REWARD, winner_label))
            return
        target_phase = 'day' if phase == 'night' else 'night'
        locked = target_phase == 'night'
        ok, err = await masoi_set_chat_lock(room, locked)
        room['phase'] = target_phase
        channel = bot.get_channel(room.get('channel_id'))
        if channel:
            if night_result:
                death_embed = make_embed(title=f'{WEREWOLF_BITE_EMOJI}  MA SÓI ĐÃ CẮN!', description=f"### <:dead:1547577908149747732> **{night_result['victim_name']}** đã bị Ma Sói cắn.\n{WEREWOLF_BITE_EMOJI} Người chơi này **đã rời khỏi phòng**.", color=discord.Color.red())
                if not night_result['ok']:
                    death_embed.add_field(name='⚠️ Lỗi quyền', value=night_result['err'][:1024], inline=False)
                await channel.send(embed=death_embed)
            if target_phase == 'day':
                await channel.send(embed=masoi_status_embed(room))
            embed = masoi_phase_embed(target_phase)
            embed.title = '☀️  TRỜI SÁNG!' if target_phase == 'day' else '🌙  ĐÊM XUỐNG!'
            if target_phase == 'day':
                embed.description = '### 🗣️ Chat đã mở\n**3 phút** thảo luận và bỏ phiếu.'
            else:
                embed.description = '### <:immom:1506650421677260901> Chat đã khóa\n**2 phút** ban đêm bắt đầu.'
            if not ok:
                embed.add_field(name='⚠️ Cảnh báo', value=err[:1024], inline=False)
            await channel.send(embed=embed)
        room['phase_task'] = asyncio.create_task(masoi_phase_timer(room_id, target_phase, 180 if target_phase == 'day' else 120))
    except asyncio.CancelledError:
        return

class MasoiRoleView(discord.ui.View):
    """Bảng điều khiển sau khi chia bài."""

    def __init__(self, room_id):
        super().__init__(timeout=None)
        self.room_id = room_id
        self.add_item(MasoiRevealRoleButton(room_id))
        self.add_item(MasoiDayButton(room_id))
        self.add_item(MasoiNightButton(room_id))

class MasoiDayButton(discord.ui.Button):

    def __init__(self, room_id):
        super().__init__(label='☀️ NGÀY • 3 PHÚT', style=discord.ButtonStyle.success, custom_id=f'masoi_day_{room_id}')
        self.room_id = room_id

    async def callback(self, interaction: discord.Interaction):
        room = MASOI_ROOMS.get(self.room_id)
        if not room or not room.get('started'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Ván chưa bắt đầu.', ephemeral=True)
        if interaction.user.id != room['host']:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ chủ phòng mới được chuyển sang ngày.', ephemeral=True)
        ok, err = await masoi_set_chat_lock(room, False)
        if not ok:
            return await interaction.response.send_message(f'<a:failed:1548973085741547580> {err}', ephemeral=True)
        room['phase'] = 'day'
        old_task = room.get('phase_task')
        if old_task and (not old_task.done()):
            old_task.cancel()
        room['phase_task'] = asyncio.create_task(masoi_phase_timer(self.room_id, 'day', 180))
        await interaction.response.send_message('☀️ **Trời sáng! Chat đã được mở.** Thời gian ban ngày: **3 phút**.', ephemeral=False)

class MasoiNightButton(discord.ui.Button):

    def __init__(self, room_id):
        super().__init__(label='🌙 ĐÊM • 2 PHÚT', style=discord.ButtonStyle.danger, custom_id=f'masoi_night_{room_id}')
        self.room_id = room_id

    async def callback(self, interaction: discord.Interaction):
        room = MASOI_ROOMS.get(self.room_id)
        if not room or not room.get('started'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Ván chưa bắt đầu.', ephemeral=True)
        if interaction.user.id != room['host']:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ chủ phòng mới được chuyển sang đêm.', ephemeral=True)
        ok, err = await masoi_set_chat_lock(room, True)
        if not ok:
            return await interaction.response.send_message(f'<a:failed:1548973085741547580> {err}', ephemeral=True)
        room['phase'] = 'night'
        old_task = room.get('phase_task')
        if old_task and (not old_task.done()):
            old_task.cancel()
        room['phase_task'] = asyncio.create_task(masoi_phase_timer(self.room_id, 'night', 120))
        await interaction.response.send_message('🌙 **Đêm xuống! Chat đã bị khóa.** Thời gian ban đêm: **2 phút**.', ephemeral=False)

def masoi_action_label(role, phase):
    if phase == 'day':
        return '🗳️ Bỏ phiếu loại người chơi'
    labels = {'Tiên Tri': '<:prophesy:1547582737601404970> Chọn người để soi', 'Bảo Vệ': '<:protect:1547583282034770000> Chọn người để bảo vệ', 'Thợ Săn': '<:emoji_75:1547988327104254012> Chọn người để ngắm', 'Cupid': '<:Cupid:1547584816461906024> Chọn người ghép đôi', 'Sói Thường': '<:codoc:1547585598058008576> Chọn người để cắn', 'Sói Alpha': '<:alpha:1547585783517675623> Chọn người để cắn', 'Sói Con': '<:emoji_33:1521139800902471782> Chọn người để cắn', 'Sói Sát Thủ': '<:wolf:1547585086872887376> Chọn người để hạ'}
    return labels.get(role, '🎯 Chọn mục tiêu')

class MasoiActionSelect(discord.ui.Select):

    def __init__(self, room_id, role, phase):
        self.room_id = room_id
        self.role = role
        self.phase = phase
        room = MASOI_ROOMS.get(room_id, {})
        guild = bot.get_guild(room.get('guild_id'))
        dead = set(room.get('dead', []))
        options = []
        wolf_roles = {'Sói Thường', 'Sói Alpha', 'Sói Con', 'Sói Sát Thủ'}
        for uid in room.get('players', []):
            if uid == getattr(getattr(guild, 'me', None), 'id', None) or uid in dead:
                continue
            if role in wolf_roles and room.get('roles', {}).get(uid) in wolf_roles:
                continue
            member = guild.get_member(uid) if guild else None
            name = member.display_name if member else f'Người chơi {uid}'
            options.append(discord.SelectOption(label=name[:100], value=str(uid), description='Chọn mục tiêu này'))
        options = options[:25]
        if not options:
            options = [discord.SelectOption(label='Chưa có mục tiêu', value='none')]
        super().__init__(placeholder=masoi_action_label(role, phase), options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        room = MASOI_ROOMS.get(self.room_id)
        if not room or not room.get('started'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Ván chưa bắt đầu hoặc đã kết thúc.', ephemeral=True)
        if interaction.user.id not in room.get('roles', {}):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Bạn không ở trong ván này.', ephemeral=True)
        if interaction.user.id in room.get('dead', []):
            return await interaction.response.send_message('<:dead:1547577908149747732> Bạn đã bị loại khỏi ván.', ephemeral=True)
        if room.get('phase') != self.phase:
            return await interaction.response.send_message('<a:clock:1548984730765099088> Giai đoạn đã thay đổi, hãy mở lại bảng chọn.', ephemeral=True)
        if self.values[0] == 'none':
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chưa có mục tiêu hợp lệ.', ephemeral=True)
        target_id = int(self.values[0])
        room.setdefault('actions', {})[interaction.user.id] = {'role': self.role, 'phase': self.phase, 'target': target_id}
        guild = bot.get_guild(room.get('guild_id'))
        target = guild.get_member(target_id) if guild else None
        target_name = target.display_name if target else f'<@{target_id}>'
        await interaction.response.send_message(f'<a:verify:1548178353859596320> **{masoi_action_label(self.role, self.phase)}**\n🎯 Mục tiêu: **{target_name}**\n🔒 Lựa chọn đã được ghi nhận riêng tư.', ephemeral=True)

class MasoiActionView(discord.ui.View):

    def __init__(self, room_id, role, phase):
        super().__init__(timeout=300)
        self.add_item(MasoiActionSelect(room_id, role, phase))

class MasoiRevealRoleButton(discord.ui.Button):

    def __init__(self, room_id):
        super().__init__(label='Xem vai của tôi', emoji='<:werewolf:1547564934299390082>', style=discord.ButtonStyle.primary, custom_id=f'masoi_reveal_{room_id}')
        self.room_id = room_id

    async def callback(self, interaction: discord.Interaction):
        room = MASOI_ROOMS.get(self.room_id)
        if not room or not room.get('started'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Ván chưa được chia bài hoặc đã kết thúc.', ephemeral=True)
        role = room['roles'].get(interaction.user.id)
        if not role:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Bạn không có trong ván Ma Sói này.', ephemeral=True)
        faction, ability = MASOI_ROLE_INFO[role]
        emoji = MASOI_ROLE_EMOJI.get(role, '🎭')
        phase = room.get('phase', 'night')
        embed = make_embed(title=f'{WEREWOLF_ROLE_EMOJI}  VAI BÍ MẬT CỦA BẠN  {WEREWOLF_BITE_EMOJI}', color=discord.Color.from_rgb(74, 42, 105))
        embed.description = f'# {WEREWOLF_ROLE_EMOJI}  {emoji} **{role}**  {WEREWOLF_BITE_EMOJI}\n### {faction}\n\n{WEREWOLF_ROLE_EMOJI}━━━━━━━━━━━━━━━━━━━━{WEREWOLF_BITE_EMOJI}'
        embed.add_field(name='📖 CHỨC NĂNG', value=ability, inline=False)
        embed.add_field(name='🎯 HÀNH ĐỘNG HIỆN TẠI', value=masoi_action_label(role, phase), inline=False)
        embed.add_field(name='<:lock:1548990424067080223> BẢO MẬT', value=f'{WEREWOLF_ROLE_EMOJI} **Chỉ bạn nhìn thấy bảng này.**\nNgười chơi khác không thể xem vai của bạn.', inline=False)
        await interaction.response.send_message(embed=embed, view=MasoiActionView(self.room_id, role, phase), ephemeral=True)

class MasoiJoinView(discord.ui.View):

    def __init__(self, room_id):
        super().__init__(timeout=3600)
        self.room_id = room_id

    @discord.ui.button(label='Tham gia', emoji='<:member:1547566263381794846>', style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = MASOI_ROOMS.get(self.room_id)
        if not room or room.get('started'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Phòng đã bắt đầu hoặc không còn tồn tại.', ephemeral=True)
        if interaction.user.id in room['players']:
            return await interaction.response.send_message('<a:verify:1548178353859596320> Bạn đã tham gia rồi!', ephemeral=True)
        if len(room['players']) >= room.get('max_players', 25):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Phòng đã đủ người.', ephemeral=True)
        room['players'].append(interaction.user.id)
        await interaction.response.edit_message(embed=masoi_lobby_embed(room), view=self)

    @discord.ui.button(label='Bắt đầu chia bài', emoji='<:werewolf:1547564934299390082>', style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = MASOI_ROOMS.get(self.room_id)
        if not room:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Không tìm thấy phòng.', ephemeral=True)
        if interaction.user.id != room['host']:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ chủ phòng mới được bắt đầu.', ephemeral=True)
        n = len(room['players'])
        if n < 6:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Cần ít nhất 6 người để bắt đầu.', ephemeral=True)
        roles = masoi_roles_for_count(n)
        random.shuffle(roles)
        room['roles'] = dict(zip(room['players'], roles))
        room['started'] = True
        room['phase'] = 'night'
        lock_ok, lock_err = await masoi_set_chat_lock(room, True)
        room['phase_task'] = asyncio.create_task(masoi_phase_timer(self.room_id, 'night', 120))
        embed = make_embed(title='<:werewolf:1547564934299390082>  MA SÓI  •  VÁN ĐÃ BẮT ĐẦU', description='### 🎭 BÀI ĐÃ ĐƯỢC CHIA\nMỗi người hãy bấm **<a:werewolf562516:1547493117786329098> Xem vai của tôi** để xem vai bí mật.\n\n### 🌙 ĐÊM ĐẦU TIÊN\nChat đã **khóa**. Đêm kéo dài **2:00** → sau đó tự động chuyển sang **☀️ Ngày 3:00**.\n\n> 🔐 **Tuyệt đối không tiết lộ vai của mình.**', color=discord.Color.from_rgb(54, 35, 76))
        embed.add_field(name='👥 Người chơi', value=str(n), inline=True)
        embed.add_field(name='<:werewolf:1547564934299390082> Ma Sói', value=str(sum((1 for r in roles if 'Sói' in r))), inline=True)
        embed.add_field(name='🎭 Vai đặc biệt', value=str(sum((1 for r in roles if r not in ('Dân Làng', 'Sói Thường')))), inline=True)
        embed.add_field(name='🌙 Giai đoạn', value='ĐÊM — chat đã khóa' if lock_ok else '⚠️ Đêm nhưng chưa khóa được chat', inline=True)
        embed.add_field(name='<a:clock:1548984730765099088> Thời gian', value='Đêm: **2 phút** • Ngày: **3 phút** • Tự động chuyển', inline=False)
        if lock_err:
            embed.add_field(name='⚠️ Lỗi quyền', value=lock_err[:1024], inline=False)
        await interaction.response.edit_message(embed=embed, view=MasoiRoleView(self.room_id))

def masoi_lobby_embed(room):
    players = room.get('players', [])
    guild = bot.get_guild(room.get('guild_id'))
    host_id = room.get('host')
    player_lines = []
    if guild:
        for uid in players:
            member = guild.get_member(uid)
            name = member.mention if member else f'<@{uid}>'
            player_lines.append(name + ('  <a:699660goldcrown:1547563982393450556>' if uid == host_id else ''))
    player_text = '\n'.join(player_lines) if player_lines else 'Chưa có người chơi'
    embed = make_embed(title='Phòng Ma Sói • <:werewolf:1547564934299390082>', description=f'Room:\n\n<:member:1547566263381794846>Người chơi\n{player_text}\n\n🌙 Khi bắt đầu\nĐêm 2:00 → Ngày 3:00 → tự động lặp', color=discord.Color.from_rgb(88, 61, 122))
    return embed

@bot.tree.command(name='masoi', description='Tạo phòng Ma Sói')
async def masoi_command(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
        if interaction.guild is None:
            return await interaction.followup.send('<a:failed:1548973085741547580> Lệnh `/masoi` chỉ dùng được trong server.')
        room_id = f'{interaction.guild_id}_{interaction.channel_id}_{interaction.id}'
        MASOI_ROOMS[room_id] = {'guild_id': interaction.guild_id, 'channel_id': interaction.channel_id, 'host': interaction.user.id, 'players': [interaction.user.id], 'started': False, 'roles': {}, 'room_name': 'Room', 'max_players': 25, 'password': None, 'chat_locked': False, 'phase': 'lobby', 'actions': {}, 'dead': [], 'game_finished': False, 'winner': None, 'coin_rewarded': False}
        room = MASOI_ROOMS[room_id]
        embed = masoi_lobby_embed(room)
        view = MasoiJoinView(room_id)
        await interaction.followup.send(embed=embed, view=view)
    except Exception as e:
        print(f'[MA SÓI] Lỗi tạo phòng: {type(e).__name__}: {e}')
        error_text = str(e).replace('`', "'")[:900]
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f'<a:failed:1548973085741547580> Không thể tạo phòng Ma Sói.\n`{error_text}`')
            else:
                await interaction.response.send_message(f'<a:failed:1548973085741547580> Không thể tạo phòng Ma Sói.\n`{error_text}`', ephemeral=True)
        except Exception as send_error:
            print(f'[MA SÓI] Không thể gửi lỗi về Discord: {send_error}')

MURDER_ROLE_INFO = {'Murder': ('<:emoji_74:1547988313439215686>', 'Murder', 'Phe Sát Nhân • Mỗi đêm chọn 1 người để giết.'), 'Thám tử': ('<:emoji_71:1547988235127365772>', 'Thám tử', 'Phe Dân • Mỗi đêm điều tra 1 người và nhận manh mối.'), 'Bác sĩ': ('<:emoji_73:1547988300235800606>', 'Bác sĩ', 'Phe Dân • Mỗi đêm chọn 1 người để chữa trị.'), 'Bảo vệ': ('<:protect:1547583282034770000>', 'Bảo vệ', 'Phe Dân • Mỗi đêm bảo vệ 1 người, kể cả chính mình.'), 'Người thường (thất nghiệp)': ('<:villagers:1547581626379403355>', 'Người thường (thất nghiệp)', 'Phe Dân • Vô năng (thất nghiệp), không có kỹ năng ban đêm.')}

MURDER_ROOMS = {}

DISCUSSION_SECONDS = 180

VOTE_SECONDS = 30

def murder_role_list(n):
    roles = ['Murder', 'Thám tử', 'Bác sĩ', 'Bảo vệ'] + ['Người thường (thất nghiệp)'] * max(1, n - 4)
    return roles[:n]

def murder_alive(room):
    return [uid for uid in room['players'] if uid not in room['dead']]

def murder_winner(room):
    alive = murder_alive(room)
    roles = room['roles']
    if not alive:
        return 'Không ai'
    if not any((roles.get(uid) == 'Murder' for uid in alive)):
        return 'Dân'
    murder_count = sum((1 for uid in alive if roles.get(uid) == 'Murder'))
    citizen_count = len(alive) - murder_count
    if murder_count >= citizen_count:
        return 'Murder'
    return None

def murder_member(room, uid):
    guild = bot.get_guild(room['guild_id'])
    return guild.get_member(uid) if guild else None

def murder_target_options(room, actor_id, action):
    ids = murder_alive(room)
    if action == 'guard':
        return ids
    return [uid for uid in ids if uid != actor_id]

class MurderTargetSelect(discord.ui.Select):

    def __init__(self, room_id, actor_id, action):
        self.room_id = room_id
        self.actor_id = actor_id
        self.action = action
        room = MURDER_ROOMS.get(room_id, {})
        targets = murder_target_options(room, actor_id, action)
        options = []
        for uid in targets[:25]:
            m = murder_member(room, uid)
            name = m.display_name if m else f'User {uid}'
            if action == 'investigate':
                desc = 'Điều tra người này'
            elif action == 'kill':
                desc = 'Chọn mục tiêu ám sát'
            elif action == 'doctor':
                desc = 'Chữa trị người này'
            else:
                desc = 'Bảo vệ người này'
            options.append(discord.SelectOption(label=name[:100], value=str(uid), description=desc[:100]))
        if not options:
            options = [discord.SelectOption(label='Không có mục tiêu', value='0')]
        super().__init__(placeholder='🎯 Chọn mục tiêu...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        room = MURDER_ROOMS.get(self.room_id)
        if not room or room.get('phase') != 'night':
            return await interaction.response.send_message('<a:failed:1548973085741547580> Ván đã chuyển sang giai đoạn khác.', ephemeral=True)
        if interaction.user.id != self.actor_id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Đây không phải bảng hành động của m.', ephemeral=True)
        if self.actor_id in room['dead']:
            return await interaction.response.send_message('<:dead:1547577908149747732> Bạn đã chết rồi.', ephemeral=True)
        target = int(self.values[0])
        if target == 0 or target not in murder_target_options(room, self.actor_id, self.action):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Mục tiêu không hợp lệ.', ephemeral=True)
        room['actions'][self.actor_id] = (self.action, target)
        target_member = murder_member(room, target)
        target_name = target_member.mention if target_member else f'<@{target}>'
        if self.action == 'kill':
            text = f'<:emoji_75:1547988327104254012> Đã chọn ám sát {target_name}.'
        elif self.action == 'investigate':
            is_murder = room['roles'].get(target) == 'Murder'
            clue = '<a:thongbao:1548169803540201582> Có dấu hiệu cho thấy người này thuộc phe Murder.' if is_murder else '<:__:1506650257272868865> Manh mối cho thấy người này không thuộc phe Murder.'
            room.setdefault('detective_clues', {})[self.actor_id] = clue
            text = f'<:__:1506650257272868865> Đã điều tra {target_name}.\n{clue}'
        elif self.action == 'doctor':
            text = f'<:emoji_73:1547988300235800606> Đã chọn chữa trị {target_name}.'
        else:
            text = f'<:protect:1547583282034770000> Đã chọn bảo vệ {target_name}.'
        await interaction.response.send_message(text, ephemeral=True)

class MurderActionView(discord.ui.View):

    def __init__(self, room_id, actor_id, action):
        super().__init__(timeout=125)
        self.add_item(MurderTargetSelect(room_id, actor_id, action))

class MurderBombCodeModal(discord.ui.Modal, title='💣 GỠ BOOM'):
    code_input = discord.ui.TextInput(label='Nhập mã gỡ boom', placeholder='Nhập đúng mã được hiển thị trên bảng...', min_length=4, max_length=8, required=True)

    def __init__(self, room_id: str, target_id: int, expected_code: str):
        super().__init__(timeout=35)
        self.room_id = room_id
        self.target_id = target_id
        self.expected_code = expected_code

    async def on_submit(self, interaction: discord.Interaction):
        room = MURDER_ROOMS.get(self.room_id)
        if not room or room.get('phase') != 'bomb' or room.get('game_finished'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Quả boom đã được xử lý.', ephemeral=True)
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message('💣 Đây không phải quả boom của m.', ephemeral=True)
        if room.get('bomb_status') != 'active':
            return await interaction.response.send_message('<a:failed:1548973085741547580> Boom không còn hoạt động.', ephemeral=True)
        entered = str(self.code_input.value).strip()
        if entered != self.expected_code:
            return await interaction.response.send_message('<a:failed:1548973085741547580> **Sai mã!** Boom vẫn còn hoạt động.', ephemeral=True)
        room['bomb_status'] = 'defused'
        room['bomb_code'] = None
        await interaction.response.send_message('🧯 **GỠ BOOM THÀNH CÔNG!** M sống sót.', ephemeral=True)
        await murder_continue_after_bomb(room)

class MurderBombView(discord.ui.View):

    def __init__(self, room_id, target_id, code):
        super().__init__(timeout=35)
        self.room_id = room_id
        self.target_id = target_id
        self.code = code

    @discord.ui.button(label='Nhập mã gỡ boom', emoji='🧯', style=discord.ButtonStyle.danger)
    async def defuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = MURDER_ROOMS.get(self.room_id)
        if not room or room.get('phase') != 'bomb':
            return await interaction.response.send_message('<a:failed:1548973085741547580> Quả boom đã được xử lý.', ephemeral=True)
        if interaction.user.id != self.target_id:
            return await interaction.response.send_message('💣 Đây không phải quả boom của m.', ephemeral=True)
        if room.get('bomb_status') != 'active':
            return await interaction.response.send_message('<a:failed:1548973085741547580> Boom không còn hoạt động.', ephemeral=True)
        await interaction.response.send_modal(MurderBombCodeModal(self.room_id, self.target_id, self.code))

class MurderLobbyView(discord.ui.View):

    def __init__(self, room_id):
        super().__init__(timeout=600)
        self.room_id = room_id

    @discord.ui.button(label='Tham gia', emoji='👤', style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = MURDER_ROOMS.get(self.room_id)
        if not room or room.get('started'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Phòng đã bắt đầu hoặc không còn tồn tại.', ephemeral=True)
        if interaction.user.id in room['players']:
            return await interaction.response.send_message('Bạn đã ở trong phòng rồi.', ephemeral=True)
        if len(room['players']) >= room['max_players']:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Phòng đã đủ 15 người.', ephemeral=True)
        room['players'].append(interaction.user.id)
        await interaction.response.edit_message(embed=murder_lobby_embed(room), view=self)

    @discord.ui.button(label='Bắt đầu', emoji='🔪', style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        room = MURDER_ROOMS.get(self.room_id)
        if not room:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Phòng không tồn tại.', ephemeral=True)
        if interaction.user.id != room['host']:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ chủ phòng mới được bắt đầu.', ephemeral=True)
        if len(room['players']) < 5:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Cần ít nhất **5 người** để chơi Murder.', ephemeral=True)
        await interaction.response.defer()
        roles = murder_role_list(len(room['players']))
        random.shuffle(roles)
        room['roles'] = dict(zip(room['players'], roles))
        room['started'] = True
        room['phase'] = 'night'
        room['dead'] = []
        room['actions'] = {}
        room['votes'] = {}
        room['round'] = 1
        room['detective_clues'] = {}
        room['detective_morning_reveal'] = None
        room['bomb_status'] = None
        room['phase_task'] = asyncio.create_task(murder_night_timer(self.room_id))
        await murder_lock_chat(room)
        await murder_send_roles(room)
        embed = murder_phase_embed(room, '🌙 ĐÊM 1', 'Vai đã được gửi riêng cho từng người. Hãy kiểm tra DM của bot.')
        await interaction.edit_original_response(embed=embed, view=None)

def murder_lobby_embed(room):
    guild = bot.get_guild(room['guild_id'])
    host_emoji = '<a:699660goldcrown:1547563982393450556>'
    member_emoji = '<:member:1547566263381794846>'
    start_emoji = '<:start:1547577950675669023>'
    title_emoji = '<:emoji_75:1547988327104254012>'
    host_lines = []
    player_lines = []
    for uid in room['players']:
        member = guild.get_member(uid) if guild else None
        mention = member.mention if member else f'<@{uid}>'
        if uid == room['host']:
            host_lines.append(f'{host_emoji} {mention}')
        else:
            player_lines.append(mention)
    host_text = '\n'.join(host_lines) if host_lines else 'Chưa có chủ phòng'
    player_text = '\n'.join(player_lines) if player_lines else 'Chưa có người chơi'
    description = f"**Room**\n\n**Chủ phòng:**\n{host_text}\n\n**Người chơi:**\n{player_text}\n\n{member_emoji} **Số người:** `{len(room['players'])}/15`\n{start_emoji} **Tối thiểu:** `5 người`\n\n{host_emoji} **Chủ phòng nhấn `Bắt đầu` để nhận vai.**"
    return make_embed(title=f'{title_emoji} Murder • Birthdaytime', description=description, color=discord.Color.from_rgb(0, 0, 0))

def murder_morning_status_embed(room, death_text=''):
    """Bảng thông báo buổi sáng theo kiểu Ma Sói: tách người sống/chết và kết quả đêm."""
    guild = bot.get_guild(room.get('guild_id'))
    dead = set(room.get('dead', []))
    players = room.get('players', [])
    alive_lines = []
    dead_lines = []
    for uid in players:
        member = guild.get_member(uid) if guild else None
        mention = member.mention if member else f'<@{uid}>'
        if uid in dead:
            dead_lines.append(f'<:dead:1547577908149747732> {mention}')
        else:
            alive_lines.append(f'<:member:1547566263381794846>{mention}')
    alive_text = '\n'.join(alive_lines) if alive_lines else 'Không còn người sống'
    dead_text = '\n'.join(dead_lines) if dead_lines else 'Chưa có người chết'
    embed = make_embed(title='🌄 Trời đã sáng đây là kết quả của tối qua:', description='<a:chcmng:1547243888639615097> **Người sống**\n' + (alive_text[:1024] if alive_lines else 'Không còn người sống') + '\n\n<:emoji_21:1508473905499603144> **Người chết**\n' + (dead_text[:1024] if dead_lines else 'Chưa có người chết') + '\n\n**Các mem có 3 phút để thảo luận**', color=discord.Color.from_rgb(0, 0, 0))
    add_standard_footer(embed)
    return embed

def murder_phase_embed(room, title, extra=''):
    alive_lines = []
    for uid in murder_alive(room):
        m = murder_member(room, uid)
        alive_lines.append(m.mention if m else f'<@{uid}>')
    dead_lines = []
    for uid in room['dead']:
        m = murder_member(room, uid)
        dead_lines.append(m.mention if m else f'<@{uid}>')
    desc = extra + '\n\n**<:emoji_21:1508473905499603144> Còn sống:** ' + (', '.join(alive_lines) or 'Không có')
    if dead_lines:
        desc += '\n**<:dead:1547577908149747732> Đã chết:** ' + ', '.join(dead_lines)
    return make_embed(title=title, description=desc, color=discord.Color.from_rgb(0, 0, 0))

async def murder_send_roles(room):
    for uid, role in room['roles'].items():
        m = murder_member(room, uid)
        if not m:
            continue
        emoji, name, info = MURDER_ROLE_INFO[role]
        embed = make_embed(title=f'{emoji} VAI CỦA M — MURDER', description=f'**Vai:** {emoji} **{name}**\n\n{info}\n\n<:lock:1548990424067080223> Đừng cho người khác biết vai của bạn.', color=discord.Color.from_rgb(0, 0, 0))
        try:
            await m.send(embed=embed)
            if role == 'Murder':
                await m.send('<:emoji_75:1547988327104254012> **ĐÊM:** Chọn 1 người để ám sát.', view=MurderActionView(room['room_id'], uid, 'kill'))
            elif role == 'Thám tử':
                await m.send('<:emoji_71:1547988235127365772> **ĐÊM:** Chọn 1 người để điều tra. Bạn sẽ nhận **1 manh mối**.', view=MurderActionView(room['room_id'], uid, 'investigate'))
            elif role == 'Bác sĩ':
                await m.send('<:emoji_73:1547988300235800606> **ĐÊM:** Chọn 1 người để chữa trị. Nếu đúng mục tiêu Murder chọn, người đó sống.', view=MurderActionView(room['room_id'], uid, 'doctor'))
            elif role == 'Bảo vệ':
                await m.send('<:protect:1547583282034770000> **ĐÊM:** Chọn 1 người để bảo vệ. Bạn có thể **tự bảo vệ chính mình**.', view=MurderActionView(room['room_id'], uid, 'guard'))
            else:
                await m.send('🌙 **Đêm nay:** Bạn  vô năng (thất nghiệp). Không có kỹ năng, hãy chờ sáng và tìm Murder.')
        except discord.Forbidden:
            print(f'[MURDER] Không thể DM role cho {uid}.')

async def murder_lock_chat(room):
    """Khóa chat của phòng Murder trong đêm. Admin/owner vẫn bị chặn bằng on_message."""
    channel = bot.get_channel(room['channel_id'])
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        await channel.set_permissions(channel.guild.default_role, send_messages=False, reason='Murder: khóa chat ban đêm')
        me = channel.guild.me
        if me:
            await channel.set_permissions(me, send_messages=True, reason='Murder: bot cần gửi thông báo ban đêm')
        room['chat_locked'] = True
    except (discord.Forbidden, discord.HTTPException) as e:
        room['chat_locked'] = False
        print(f'[MURDER] Không thể khóa chat {channel.id}: {e}')

async def murder_unlock_chat(room):
    channel = bot.get_channel(room['channel_id'])
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        await channel.set_permissions(channel.guild.default_role, send_messages=None, reason='Murder: mở khóa chat ban ngày')
        me = channel.guild.me
        if me:
            await channel.set_permissions(me, send_messages=None, reason='Murder: khôi phục quyền bot')
        room['chat_locked'] = False
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f'[MURDER] Không thể mở khóa chat {channel.id}: {e}')

async def murder_night_timer(room_id):
    await asyncio.sleep(120)
    room = MURDER_ROOMS.get(room_id)
    if not room or room.get('phase') != 'night' or room.get('game_finished'):
        return
    await murder_resolve_night(room)

async def murder_send_detective_morning(room):
    reveal = room.get('detective_morning_reveal')
    if not reveal:
        return
    detective_id, actor_id, action = reveal
    detective = murder_member(room, detective_id)
    actor = murder_member(room, actor_id)
    if not detective:
        return
    actor_name = actor.mention if actor else f'<@{actor_id}>'
    action_name = {'kill': '<:emoji_75:1547988327104254012> ám sát', 'doctor': '<:emoji_73:1547988300235800606> chữa trị', 'guard': '<:protect:1547583282034770000> bảo vệ', 'investigate': '<:__:1506650257272868865> điều tra'}.get(action, 'hành động bí mật')
    try:
        await detective.send(f'☀️ **MANH MỐI BUỔI SÁNG:** Tối qua, {actor_name} đã thực hiện hành động **{action_name}**.')
    except discord.Forbidden:
        pass

async def murder_start_bomb(room):
    alive = murder_alive(room)
    if not alive:
        return await murder_resolve_bomb(room, None)
    target = random.choice(alive)
    room['bomb_target'] = target
    room['bomb_status'] = 'active'
    room['bomb_code'] = f'{random.randint(1000, 99999999):08d}'
    room['phase'] = 'bomb'
    target_member = murder_member(room, target)
    channel = bot.get_channel(room['channel_id'])
    if channel:
        mention = target_member.mention if target_member else f'<@{target}>'
        await channel.send(embed=make_embed(title='💣 BOOM XUẤT HIỆN!', description=(f"💣 Một quả boom xuất hiện trước mặt {mention}!\n\nNgười này phải **gỡ boom trong 35 giây**.\n🔐 **Mã gỡ boom:** `{room['bomb_code']}`\nNhấn **Nhập mã gỡ boom** và nhập đúng mã trên.\nSai mã vẫn không làm mất boom. Không gỡ kịp → 💥 **boom nổ**.",), color=discord.Color.from_rgb(0, 0, 0)), view=MurderBombView(room['room_id'], target, room['bomb_code']))
    room['phase_task'] = asyncio.create_task(murder_bomb_timer(room['room_id']))

async def murder_bomb_timer(room_id):
    await asyncio.sleep(35)
    room = MURDER_ROOMS.get(room_id)
    if not room or room.get('phase') != 'bomb' or room.get('game_finished'):
        return
    if room.get('bomb_status') == 'defused':
        await murder_continue_after_bomb(room)
    else:
        await murder_resolve_bomb(room, room.get('bomb_target'))

async def murder_resolve_bomb(room, target):
    if target is not None and target in murder_alive(room):
        room['dead'].append(target)
        m = murder_member(room, target)
        death_text = f"💥 {(m.mention if m else f'<@{target}>')} **không gỡ được boom và đã nổ!**"
    else:
        death_text = '💥 Boom đã phát nổ.'
    winner = murder_winner(room)
    if winner:
        await murder_finish(room, winner, death_text)
        return
    channel = bot.get_channel(room['channel_id'])
    if channel:
        await channel.send(embed=murder_morning_status_embed(room, death_text))
    await murder_continue_after_bomb(room)

async def murder_continue_after_bomb(room):
    await murder_unlock_chat(room)
    room['phase'] = 'day'
    room['actions'] = {}
    room['votes'] = {}
    room['bomb_status'] = None
    channel = bot.get_channel(room['channel_id'])
    await murder_send_detective_morning(room)
    reveal = room.get('detective_morning_reveal')
    reveal_text = '<:__:1506650257272868865> Thám tử nhận được một manh mối riêng qua DM.' if reveal else '🔎 Đêm qua không có manh mối hành động đặc biệt.'
    room['detective_morning_reveal'] = None
    if channel:
        await channel.send(embed=murder_morning_status_embed(room, reveal_text))
        await channel.send(embed=murder_phase_embed(room, '☀️ NGÀY — THẢO LUẬN & BỎ PHIẾU', '🗳️ Thời gian thảo luận đã kết thúc. Hệ thống tự động mở bỏ phiếu Murder trong **30 giây**.'))
    room['phase_task'] = asyncio.create_task(murder_day_timer(room['room_id']))

async def murder_resolve_night(room):
    if room.get('phase') != 'night':
        return
    actions = room.get('actions', {})
    kill_target = None
    doctor_target = None
    guard_target = None
    detective_actor = None
    detective_target = None
    for uid, data in actions.items():
        action, target = data
        role = room['roles'].get(uid)
        if action == 'kill' and role == 'Murder':
            kill_target = target
        elif action == 'doctor' and role == 'Bác sĩ':
            doctor_target = target
        elif action == 'guard' and role == 'Bảo vệ':
            guard_target = target
        elif action == 'investigate' and role == 'Thám tử':
            detective_actor = uid
            detective_target = target
    protected = {x for x in (doctor_target, guard_target) if x is not None}
    killed = None
    if kill_target and kill_target not in protected and (kill_target in murder_alive(room)):
        room['dead'].append(kill_target)
        killed = kill_target
        victim_member = murder_member(room, kill_target)
        try:
            if victim_member:
                await victim_member.send('<:dead:1547577908149747732> Bạn đã bị giết trong ván Murder. Bạn không thể nhìn thấy tên của Murder .')
        except discord.Forbidden:
            pass
    room['detective_morning_reveal'] = None
    if detective_actor and detective_actor in murder_alive(room):
        candidates = [uid for uid in actions if uid != detective_actor and uid in murder_alive(room)]
        if candidates and random.random() < 0.65:
            actor_id = random.choice(candidates)
            action = actions[actor_id][0]
            room['detective_morning_reveal'] = (detective_actor, actor_id, action)
    winner = murder_winner(room)
    if winner:
        await murder_finish(room, winner)
        return
    await murder_start_bomb(room)

class MurderVoteButton(discord.ui.Button):

    def __init__(self, room_id, target_id):
        super().__init__(label='Bỏ phiếu', style=discord.ButtonStyle.danger)
        self.room_id = room_id
        self.target_id = target_id

    async def callback(self, interaction: discord.Interaction):
        room = MURDER_ROOMS.get(self.room_id)
        if not room or room.get('game_finished') or (not room.get('voting_open')):
            return await interaction.response.send_message('<a:clock:1548984730765099088> Đã hết thời gian bỏ phiếu.', ephemeral=True)
        if interaction.user.id not in murder_alive(room):
            return await interaction.response.send_message('<:dead:1547577908149747732> Người chết không được bỏ phiếu.', ephemeral=True)
        if self.target_id not in murder_alive(room) or self.target_id == interaction.user.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Mục tiêu không hợp lệ.', ephemeral=True)
        room.setdefault('votes', {})[interaction.user.id] = self.target_id
        await interaction.response.send_message('<a:verify:1548178353859596320> Đã ghi nhận phiếu bí mật.', ephemeral=True)

class MurderVoteView(discord.ui.View):

    def __init__(self, room_id):
        super().__init__(timeout=30)
        self.room_id = room_id
        room = MURDER_ROOMS.get(room_id, {})
        for uid in murder_alive(room):
            member = murder_member(room, uid)
            if member:
                self.add_item(MurderVoteButton(room_id, uid))

async def murder_day_timer(room_id):
    """3 phút thảo luận, 30 giây cuối là thời gian bỏ phiếu."""
    try:
        await asyncio.sleep(max(0, DISCUSSION_SECONDS - VOTE_SECONDS))
        room = MURDER_ROOMS.get(room_id)
        if not room or room.get('phase') != 'day' or room.get('game_finished'):
            return
        room['voting_open'] = True
        channel = bot.get_channel(room.get('channel_id'))
        if channel:
            await channel.send('🗳️ **ĐÃ MỞ BỎ PHIẾU!** Chọn người bị nghi là Murder — còn **30 giây**.', view=MurderVoteView(room_id))
        await asyncio.sleep(VOTE_SECONDS)
        room = MURDER_ROOMS.get(room_id)
        if not room or room.get('phase') != 'day' or room.get('game_finished'):
            return
        room['voting_open'] = False
        await murder_resolve_votes(room)
    except asyncio.CancelledError:
        return

async def murder_resolve_votes(room):
    counts = {}
    for voter, target in room.get('votes', {}).items():
        if voter in murder_alive(room) and target in murder_alive(room):
            counts[target] = counts.get(target, 0) + 1
    channel = bot.get_channel(room['channel_id'])
    if not counts:
        result_text = '⚖️ Không có phiếu hợp lệ, không ai bị loại.'
    else:
        highest = max(counts.values())
        top = [uid for uid, c in counts.items() if c == highest]
        if len(top) != 1:
            result_text = '⚖️ Hòa phiếu, không ai bị loại.'
        else:
            target = top[0]
            room['dead'].append(target)
            m = murder_member(room, target)
            role = room['roles'].get(target)
            emoji, name, _ = MURDER_ROLE_INFO[role]
            result_text = f"🗳️ {(m.mention if m else f'<@{target}>')} bị loại với **{highest} phiếu**.\n🎭 Vai của người này là **{emoji} {name}**."
    winner = murder_winner(room)
    if winner:
        await murder_finish(room, winner, result_text)
        return
    room['round'] += 1
    room['phase'] = 'night'
    room['actions'] = {}
    room['votes'] = {}
    room['detective_clues'] = {}
    await murder_lock_chat(room)
    if channel:
        await channel.send(embed=murder_phase_embed(room, f"🌙 ĐÊM {room['round']}", result_text + '\n\nCác vai có kỹ năng hãy kiểm tra DM để hành động.'))
    await murder_send_roles(room)
    room['phase_task'] = asyncio.create_task(murder_night_timer(room['room_id']))

async def murder_finish(room, winner, prefix=''):
    await murder_unlock_chat(room)
    room['game_finished'] = True
    room['phase'] = 'finished'
    task = room.get('phase_task')
    if task and (not task.done()) and (task is not asyncio.current_task()):
        task.cancel()
    channel = bot.get_channel(room['channel_id'])
    if winner == 'Dân':
        result = '<:villagers:1547581626379403355> **PHE DÂN THẮNG!** Murder đã bị loại.'
    elif winner == 'Murder':
        result = '<:emoji_75:1547988327104254012> **MURDER THẮNG!** Sát nhân đã sống sót đến thế cân bằng.'
    else:
        result = '<:dead:1547577908149747732> **KHÔNG AI THẮNG.**'
    role_lines = []
    for uid in room['players']:
        m = murder_member(room, uid)
        role = room['roles'].get(uid, '?')
        emoji, name, _ = MURDER_ROLE_INFO.get(role, ('🎭', role, ''))
        role_lines.append(f"{(m.mention if m else f'<@{uid}>')} — {emoji} {name}")
    if channel:
        await channel.send(embed=make_embed(title='🏁 MURDER • KẾT THÚC', description=(prefix + '\n\n' if prefix else '') + result + '\n\n**🎭 DANH SÁCH VAI**\n' + '\n'.join(role_lines), color=discord.Color.from_rgb(0, 0, 0)))
    if winner in {'Dân', 'Murder'} and (not room.get('coin_rewarded')):
        room['coin_rewarded'] = True
        winner_mentions = []
        for uid in room.get('players', []):
            role = room.get('roles', {}).get(uid)
            is_winner = winner == 'Murder' and role == 'Murder' or (winner == 'Dân' and role != 'Murder')
            if is_winner:
                baucua_change_coins(uid, GAME_WIN_REWARD)
                m = murder_member(room, uid)
                winner_mentions.append(m.mention if m else f'<@{uid}>')
        winner_label = '<:emoji_75:1547988327104254012> **Murder win**' if winner == 'Murder' else '<:villagers:1547581626379403355> **Người dân win**'
        if channel:
            await channel.send(embed=game_coin_reward_embed('MURDER', winner_mentions, GAME_WIN_REWARD, winner_label))

@bot.tree.command(name='murder', description='Tạo phòng game Murder 5–15 người')
async def murder_command(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message('<a:failed:1548973085741547580> Game Murder chỉ chơi trong server.', ephemeral=True)
    for room in MURDER_ROOMS.values():
        if room.get('guild_id') == interaction.guild_id and room.get('channel_id') == interaction.channel_id and (not room.get('game_finished')):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Kênh này đang có một phòng Murder rồi.', ephemeral=True)
    room_id = f'murder_{interaction.guild_id}_{interaction.channel_id}_{interaction.id}'
    MURDER_ROOMS[room_id] = {'room_id': room_id, 'guild_id': interaction.guild_id, 'channel_id': interaction.channel_id, 'host': interaction.user.id, 'players': [interaction.user.id], 'roles': {}, 'dead': [], 'actions': {}, 'votes': {}, 'started': False, 'phase': 'lobby', 'round': 0, 'max_players': 15, 'game_finished': False, 'phase_task': None, 'detective_clues': {}, 'detective_morning_reveal': None, 'bomb_target': None, 'bomb_status': None, 'bomb_code': None, 'chat_locked': False, 'voting_open': False}
    room = MURDER_ROOMS[room_id]
    await interaction.response.send_message(embed=murder_lobby_embed(room), view=MurderLobbyView(room_id))


# ============================================================
# ============================================================
# GAME MÌN — SOLO 2 NGƯỜI
# ============================================================
MINE_GAMES = {}

VERIFY_EMOJI = '<a:verify:1548178353859596320>'
FAILED_EMOJI = '<a:failed:1548973085741547580>'


class MineJoinButton(discord.ui.Button):
    def __init__(self, game_id: str):
        super().__init__(
            label="Tham gia",
            emoji="💣",
            style=discord.ButtonStyle.success,
            custom_id=f"mine_join_{game_id}",
        )
        self.game_id = game_id

    async def callback(self, interaction: discord.Interaction):
        game = MINE_GAMES.get(self.game_id)
        if not game or game.get("finished"):
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Ván Mìn này đã kết thúc.', ephemeral=True
            )

        if game.get("player2"):
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Ván này đã đủ người chơi.', ephemeral=True
            )

        if interaction.user.id != game["target_id"]:
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Ván này chỉ dành cho {game["target_mention"]}.',
                ephemeral=True,
            )

        if interaction.user.id == game["player1"]:
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Bạn không thể tham gia ván của chính mình.',
                ephemeral=True,
            )

        game["player2"] = interaction.user.id
        game["turn"] = game["player1"]
        game["started"] = True
        self.disabled = True

        # Chuyển từ bảng tham gia sang bảng chơi.
        game["view"] = MineView(self.game_id, started=True)

        embed = mine_game_embed(game, last_result=None)
        await interaction.response.edit_message(embed=embed, view=game["view"])


class MineCellButton(discord.ui.Button):
    def __init__(self, game_id: str, index: int, revealed=None):
        label = str(index + 1)
        style = discord.ButtonStyle.secondary
        emoji = None
        if revealed and index in revealed:
            label = ""
            emoji = discord.PartialEmoji.from_str(VERIFY_EMOJI)
            style = discord.ButtonStyle.success

        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            custom_id=f"mine_cell_{game_id}_{index}",
            row=index // 3,
        )
        self.game_id = game_id
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        game = MINE_GAMES.get(self.game_id)

        if not game or game.get("finished"):
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Ván Mìn đã kết thúc.', ephemeral=True
            )

        if not game.get("started"):
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Hãy chờ người chơi thứ 2 tham gia.', ephemeral=True
            )

        if interaction.user.id not in (game["player1"], game["player2"]):
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Bạn không tham gia ván Mìn này.', ephemeral=True
            )

        if interaction.user.id != game["turn"]:
            turn_member = interaction.guild.get_member(game["turn"])
            mention = turn_member.mention if turn_member else f'<@{game["turn"]}>'
            return await interaction.response.send_message(
                f'⏳ Chưa tới lượt bạn! Tới lượt {mention}.', ephemeral=True
            )

        if self.index in game["revealed"]:
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Ô này đã được chọn.', ephemeral=True
            )

        game["revealed"].add(self.index)
        player = interaction.user

        if self.index == game["mine"]:
            game["finished"] = True
            game["loser"] = player.id
            winner_id = game["player2"] if player.id == game["player1"] else game["player1"]
            game["winner"] = winner_id

            # Hiện kết quả: ô mìn là failed, các ô đã an toàn là verify.
            final_view = MineView(self.game_id, started=True, final=True)
            game["view"] = final_view

            # Người thắng nhận 500 coin, cộng trực tiếp vào cùng hệ thống coin của Bầu Cua/Murder/Ma Sói.
            baucua_change_coins(winner_id, 500)

            loser_mention = player.mention
            winner_mention = f'<@{winner_id}>'
            embed = make_embed(
                title="💥 GAME MÌN • KẾT THÚC",
                description=(
                    "**Chọn các ô dưới và hãy né mìn nha!**\n\n"
                    f"{loser_mention} đã chọn ô `{self.index + 1}` kết quả: {FAILED_EMOJI} `dính mìn`\n\n"
                    f"💥 **{loser_mention} đã dính mìn!**\n"
                    f"🏆 {winner_mention} là người còn lại trong ván.\n"
                    f"🪙 {winner_mention} nhận được **500 coin**!"
                ),
                color=discord.Color.red(),
            )
            await interaction.response.edit_message(embed=embed, view=final_view)
            return

        # Ô an toàn.
        self.label = ""
        self.emoji = discord.PartialEmoji.from_str(VERIFY_EMOJI)
        self.style = discord.ButtonStyle.success
        self.disabled = True

        next_turn = game["player2"] if player.id == game["player1"] else game["player1"]
        game["turn"] = next_turn

        embed = mine_game_embed(
            game,
            last_result=f"{player.mention} đã chọn ô `{self.index + 1}` kết quả: {VERIFY_EMOJI} `an toàn`",
        )
        await interaction.response.edit_message(embed=embed, view=game["view"])


class MineView(discord.ui.View):
    def __init__(self, game_id: str, started=False, final=False):
        super().__init__(timeout=None)
        self.game_id = game_id

        if not started:
            self.add_item(MineJoinButton(game_id))
            return

        game = MINE_GAMES.get(game_id, {})
        revealed = game.get("revealed", set())
        for index in range(9):
            button = MineCellButton(game_id, index, revealed=revealed)
            if final:
                button.disabled = True
                if index == game.get("mine"):
                    button.label = FAILED_EMOJI
                    button.style = discord.ButtonStyle.danger
                elif index in revealed:
                    button.label = VERIFY_EMOJI
                    button.style = discord.ButtonStyle.success
            self.add_item(button)


def mine_game_embed(game, last_result=None):
    turn_id = game.get("turn")
    turn_mention = f'<@{turn_id}>' if turn_id else game.get("target_mention", "@tag")

    description = (
        "**Chọn các ô dưới và hãy né mìn nha!**\n\n"
        f"Tới lượt của {turn_mention} hãy chọn ô để né mìn\n"
    )
    if last_result:
        description += f"\n{last_result}\n"

    return make_embed(
        title="💣 Game MÌN • BirthdayTime",
        description=description,
        color=discord.Color.from_rgb(0, 0, 0),
    )


@bot.tree.command(name="min", description="Mời một người solo game Mìn 9 ô")
@app_commands.describe(nguoi_choi="Người bạn muốn solo game Mìn")
async def nine_box_command(interaction: discord.Interaction, nguoi_choi: discord.Member):
    if interaction.guild is None:
        return await interaction.response.send_message(
            f'{FAILED_EMOJI} Game Mìn chỉ dùng trong server.', ephemeral=True
        )

    if nguoi_choi.bot:
        return await interaction.response.send_message(
            f'{FAILED_EMOJI} Không thể mời bot chơi Mìn.', ephemeral=True
        )

    if nguoi_choi.id == interaction.user.id:
        return await interaction.response.send_message(
            f'{FAILED_EMOJI} Bạn không thể solo với chính mình.', ephemeral=True
        )

    # Mỗi kênh chỉ có một ván Mìn đang hoạt động.
    for game in MINE_GAMES.values():
        if (
            game.get("guild_id") == interaction.guild_id
            and game.get("channel_id") == interaction.channel_id
            and not game.get("finished")
        ):
            return await interaction.response.send_message(
                f'{FAILED_EMOJI} Kênh này đang có một ván Mìn. Hãy chơi xong ván hiện tại trước.',
                ephemeral=True,
            )

    game_id = f"mine_{interaction.guild_id}_{interaction.channel_id}_{interaction.id}"
    game = {
        "guild_id": interaction.guild_id,
        "channel_id": interaction.channel_id,
        "player1": interaction.user.id,
        "player2": None,
        "target_id": nguoi_choi.id,
        "target_mention": nguoi_choi.mention,
        "mine": random.randrange(9),
        "revealed": set(),
        "finished": False,
        "started": False,
        "turn": None,
        "view": None,
    }
    view = MineView(game_id, started=False)
    game["view"] = view
    MINE_GAMES[game_id] = game

    embed = make_embed(
        title="💣Game MÌN • BirthdayTime",
        description=(
            f"**Hãy nhấn nút tham gia để solo với {nguoi_choi.mention}**\n\n"
            f"{interaction.user.mention} đang chờ {nguoi_choi.mention} tham gia."
        ),
        color=discord.Color.from_rgb(0, 0, 0),
    )
    await interaction.response.send_message(embed=embed, view=view)


# GAME SÂU ĂN TÁO — DISCORD BUTTON
# ============================================================
SNAKE_GAMES = {}


class SnakeControlButton(discord.ui.Button):
    def __init__(self, game, direction, emoji):
        super().__init__(
            label="",
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=0,
            custom_id=f"snake_{game.game_id}_move_{direction}",
        )
        self.game = game
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        await self.game.move(interaction, self.direction)


class SnakeView(discord.ui.View):
    def __init__(self, owner_id, game_id):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.game_id = game_id
        self.rows = 5
        self.cols = 6
        self.snake = [(2, 1), (2, 0)]
        self.direction = (0, 1)
        self.score = 0
        self.game_over = False
        self.apple = self._new_apple()

        # Chỉ dùng nút mũi tên để điều khiển; bàn chơi được hiển thị trong embed.
        self.add_item(SnakeControlButton(self, "up", "⬆️"))
        self.add_item(SnakeControlButton(self, "left", "⬅️"))
        self.add_item(SnakeControlButton(self, "down", "⬇️"))
        self.add_item(SnakeControlButton(self, "right", "➡️"))

    def _new_apple(self):
        free = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in self.snake
        ]
        return random.choice(free) if free else None

    def _board_text(self):
        rows = []
        for r in range(self.rows):
            cells = []
            for c in range(self.cols):
                pos = (r, c)
                if pos == self.snake[0]:
                    cells.append("🐍")
                elif pos in self.snake:
                    cells.append("🟩")
                elif pos == self.apple:
                    cells.append("🍎")
                else:
                    cells.append("⬜")
            rows.append(" ".join(cells))
        return "\n".join(rows)

    def _refresh_buttons(self):
        for item in self.children:
            if isinstance(item, SnakeControlButton):
                item.disabled = self.game_over

    def embed(self, status=""):
        title = "🐍 Sâu ăn táo" if not self.game_over else "🏆 🐍 Sâu ăn táo — KẾT THÚC"
        description = (
            "**Hãy bấm nút di chuyển để điều khiển Rắn**\n"
            f"**Điểm: {self.score}**\n\n"
            f"{self._board_text()}"
        )
        if not self.game_over:
            description += "\n\n          ⬆️\n   ⬅️  ⬇️  ➡️"
        if status:
            description += f"\n\n{status}"

        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.green() if not self.game_over else discord.Color.red(),
        )

    async def _check_owner(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ Đây không phải ván Sâu ăn táo của bạn!", ephemeral=True
            )
            return False
        return True

    async def move(self, interaction, direction):
        if not await self._check_owner(interaction):
            return
        if self.game_over:
            await interaction.response.send_message("❌ Ván đã kết thúc!", ephemeral=True)
            return

        directions = {
            "up": (-1, 0),
            "down": (1, 0),
            "left": (0, -1),
            "right": (0, 1),
        }
        new_direction = directions[direction]

        # Không cho quay đầu 180° trực tiếp.
        if (
            new_direction[0] == -self.direction[0]
            and new_direction[1] == -self.direction[1]
            and len(self.snake) > 1
        ):
            await interaction.response.send_message(
                "↩️ Không thể quay đầu 180° ngay lập tức!", ephemeral=True
            )
            return

        self.direction = new_direction
        head_r, head_c = self.snake[0]
        new_head = (head_r + new_direction[0], head_c + new_direction[1])

        # Đụng tường.
        if not (0 <= new_head[0] < self.rows and 0 <= new_head[1] < self.cols):
            self.game_over = True
            self._refresh_buttons()
            await interaction.response.edit_message(
                embed=self.embed("💥 Bạn đâm vào tường! **Bạn thua!**"), view=self
            )
            return

        # Đụng thân.
        if new_head in self.snake[:-1]:
            self.game_over = True
            self._refresh_buttons()
            await interaction.response.edit_message(
                embed=self.embed("💀 Bạn đâm vào thân mình! **Bạn thua!**"), view=self
            )
            return

        self.snake.insert(0, new_head)

        if new_head == self.apple:
            self.score += 1
            self.apple = self._new_apple()

            if self.apple is None:
                self.game_over = True
                # Hoàn thành game Rắn ăn mồi: thưởng 2.000 coin vào hệ thống coin chung.
                baucua_change_coins(self.owner_id, 2000)
                self._refresh_buttons()
                await interaction.response.edit_message(
                    embed=self.embed("🪙 Nhận **2.000 coin**"), view=self
                )
                return

            status = "🍎 Ăn được táo! +1 điểm!"
        else:
            self.snake.pop()
            status = ""

        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.embed(status), view=self)

    async def on_timeout(self):
        self.game_over = True
        self._refresh_buttons()
        SNAKE_GAMES.pop(self.game_id, None)


@bot.tree.command(name="snake", description="Chơi game Sâu ăn táo")
async def snake_command(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    old_game = SNAKE_GAMES.get(channel_id)
    if old_game and not old_game.game_over:
        await interaction.response.send_message(
            "🐍 Kênh này đang có một ván Sâu ăn táo! Hãy chơi xong ván hiện tại trước.",
            ephemeral=True,
        )
        return

    game_id = str(interaction.id)
    view = SnakeView(interaction.user.id, game_id)
    SNAKE_GAMES[channel_id] = view

    await interaction.response.send_message(
        embed=view.embed(),
        view=view,
    )


# ============================================================
# HỆ THỐNG COIN DÙNG CHUNG — LƯU BẰNG JSON
# Bầu Cua + Ma Sói + Murder dùng chung số dư. 
# ============================================================
COIN_FILE = 'coins.json'
COIN_DEFAULT = 1000

def _load_coins():
    if not os.path.exists(COIN_FILE):
        return {}
    try:
        with open(COIN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        print('❗ coins.json lỗi/không đọc được, tạo dữ liệu coin mới.')
        return {}

COINS = _load_coins()

def _save_coins():
    tmp_file = COIN_FILE + '.tmp'
    with open(tmp_file, 'w', encoding='utf-8') as f:
        json.dump(COINS, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, COIN_FILE)

def baucua_get_coins(user_id: int) -> int:
    if user_id == SPECIAL_ADMIN_ID:
        return 999999999999999999
    key = str(user_id)
    if key not in COINS:
        COINS[key] = COIN_DEFAULT
        _save_coins()
    return int(COINS[key])

def baucua_change_coins(user_id: int, amount: int):
    if user_id == SPECIAL_ADMIN_ID:
        return 999999999999999999
    key = str(user_id)
    current = baucua_get_coins(user_id)
    new_value = max(0, current + int(amount))
    COINS[key] = new_value
    _save_coins()
    return new_value

BAUCUA_EMOJIS = {
    'bau': discord.PartialEmoji(name='bau', id=1548524879748272250),
    'cua': discord.PartialEmoji(name='crab', id=1548515170203209728, animated=True),
    'tom': discord.PartialEmoji(name='tom', id=1548525583711871067),
    'ca': discord.PartialEmoji(name='fish', id=1548514999347974164, animated=True),
    'nai': discord.PartialEmoji(name='deer', id=1548514158994259978, animated=True),
    'ga': discord.PartialEmoji(name='rooster', id=1548514657889820762, animated=True),
}

BAUCUA_TITLE_EMOJI = discord.PartialEmoji(name='baucuatomca', id=1261790169011458139, animated=True)
GAME_WIN_REWARD = 50000
BAUCUA_ROUND_SECONDS = 30
CONFIRM_TIMEOUT = 300  # 5 phút

baucua_round = None


def coin_display(user_id: int) -> str:
    if user_id == SPECIAL_ADMIN_ID:
        return '∞'
    return f'{baucua_get_coins(user_id):,}'


def game_coin_reward_embed(game_name, winners, reward, winner_label):
    lines = [f'{mention} đã húp được **{reward:,}**<a:coin:1548707654459727964>' for mention in winners[:25]]
    description = f'{winner_label}\n' + ('\n'.join(lines) if lines else 'Không có người nhận thưởng.')
    return make_embed(title=f'<a:coin:1548707654459727964> {game_name} • THƯỞNG COIN', description=description, color=discord.Color.from_rgb(0, 0, 0))


class BauCuaBetModal(discord.ui.Modal, title='Đặt cược Bầu Cua'):
    amount = discord.ui.TextInput(
        label='Số coin muốn đặt',
        placeholder='Nhập số coin của mem dùng để cược! (tối đa 250.000)',
        required=True,
        max_length=12,
    )

    def __init__(self, choice: str):
        super().__init__()
        self.choice = choice

    async def on_submit(self, interaction: discord.Interaction):
        global baucua_round
        try:
            amount = int(str(self.amount.value).strip().replace(',', ''))
        except ValueError:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Số coin phải là số nguyên.', ephemeral=True)

        if amount <= 0 or amount > 250000:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Số cược phải từ **1** đến **250.000 coin**.', ephemeral=True)

        if not baucua_round or not baucua_round.get('open'):
            return await interaction.response.send_message('<a:failed:1548973085741547580> Hiện không có ván Bầu Cua đang mở.', ephemeral=True)

        uid = interaction.user.id
        infinite = uid == SPECIAL_ADMIN_ID
        balance = baucua_get_coins(uid)
        if not infinite and amount > balance:
            return await interaction.response.send_message(f'<a:failed:1548973085741547580> Bạn chỉ có **{balance:,} coin**.', ephemeral=True)

        if not infinite:
            baucua_change_coins(uid, -amount)

        baucua_round['bets'].append({
            'user_id': uid,
            'mention': interaction.user.mention,
            'choice': self.choice,
            'amount': amount,
            'infinite': infinite,
        })
        remaining = max(0, int(baucua_round.get('remaining', BAUCUA_ROUND_SECONDS)))
        await interaction.response.send_message(
            f'<a:verify:1548178353859596320> Đã đặt **{amount:,} coin** vào {BAUCUA_EMOJIS[self.choice]}. Còn **{remaining} giây**.',
            ephemeral=True,
        )


class BauCuaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for key, label, row in [
            ('nai', 'Nai', 0), ('bau', 'Bầu', 0), ('ga', 'Gà', 0),
            ('ca', 'Cá', 1), ('cua', 'Cua', 1), ('tom', 'Tôm', 1),
        ]:
            button = discord.ui.Button(
                label=label,
                emoji=BAUCUA_EMOJIS[key],
                custom_id=f'baucua_{key}',
                style=discord.ButtonStyle.secondary,
                row=row,
            )
            button.callback = self._make_callback(key)
            self.add_item(button)

    def _make_callback(self, choice):
        async def callback(interaction: discord.Interaction):
            global baucua_round
            if not baucua_round or not baucua_round.get('open'):
                return await interaction.response.send_message('<:lock:1548990424067080223> Ván đã đóng, không thể cược nữa.', ephemeral=True)
            await interaction.response.send_modal(BauCuaBetModal(choice))
        return callback

    def disable_all(self):
        for item in self.children:
            item.disabled = True


async def finish_baucua_round(channel, game_message=None, view=None):
    global baucua_round
    if not baucua_round or not baucua_round.get('open'):
        return

    round_data = baucua_round
    round_data['open'] = False
    round_data['remaining'] = 0

    result = [random.choice(list(BAUCUA_EMOJIS.keys())) for _ in range(3)]
    winners = []
    losers = []

    for bet in round_data['bets']:
        matches = result.count(bet['choice'])
        reward = bet['amount'] * matches
        if not bet['infinite'] and matches:
            # Hoàn tiền cược + tiền thắng.
            baucua_change_coins(bet['user_id'], bet['amount'] + reward)

        net = reward if matches else -bet['amount']
        bet_emoji = str(BAUCUA_EMOJIS[bet['choice']])
        if net > 0:
            winners.append(
                f"<@{bet['user_id']}> đã cược {bet_emoji} -> lụm được **{net:,}** coin"
            )
        else:
            losers.append(
                f"<@{bet['user_id']}> đã cược {bet_emoji} -> tạch **{abs(net):,}** coin"
            )

    if view is not None:
        view.disable_all()

    # 1) Đổi Embed đang cược thành trạng thái đã khóa.
    if game_message is not None:
        locked_embed = make_embed(
            title='🦀 Bầu cua • BirthdayTime',
            description=(
                'BirthdayTime nhà cái đến từ Châu Phi\n\n'
                'Bạn đã hết thời gian đặt cược.'
            ),
            color=discord.Color.from_rgb(0, 0, 0),
        )
        try:
            await game_message.edit(embed=locked_embed, view=view)
        except discord.HTTPException:
            pass

    # 2) Hiển thị 3 emoji loading trên cùng một dòng, rồi thay từng vị trí sau mỗi giây.
    loading_emoji = '<a:loading:1548997886098935848>'
    result_line = [loading_emoji, loading_emoji, loading_emoji]
    result_message = await channel.send('    '.join(result_line))

    for index, key in enumerate(result):
        await asyncio.sleep(1)
        result_line[index] = str(BAUCUA_EMOJIS[key])
        try:
            await result_message.edit(content='    '.join(result_line))
        except discord.HTTPException:
            pass

    # 3) Gửi Embed kết quả riêng.
    result_lines = ['**Kết quả:**']
    if winners:
        result_lines.extend(winners[:25])
    if losers:
        result_lines.extend(losers[:25])
    if not round_data['bets']:
        result_lines.append('Không có người đặt cược.')

    result_embed = make_embed(
        title='🦀 Bầu cua • BirthdayTime',
        description='\n'.join(result_lines),
        color=discord.Color.from_rgb(0, 0, 0),
    )
    await channel.send(embed=result_embed)
    baucua_round = None


@bot.tree.command(name='baucua', description='Mở ván Bầu Cua trong 30 giây')
async def baucua(interaction: discord.Interaction):
    global baucua_round
    if baucua_round and baucua_round.get('open'):
        return await interaction.response.send_message('<a:failed:1548973085741547580> Đang có một ván Bầu Cua diễn ra.', ephemeral=True)

    baucua_round = {'open': True, 'bets': [], 'remaining': BAUCUA_ROUND_SECONDS}
    view = BauCuaView()
    embed = make_embed(
        title='🦀 Bầu cua • BirthdayTime',
        description=(
            'BirthdayTime nhà cái đến từ Châu Phi\n\n'
            'Đặt cược bằng cách chọn một con\n'
            'Các mem có 30 giây đặt cược, hãy cẩn trọng trước khi cược!'
        ),
        color=discord.Color.from_rgb(0, 0, 0),
    )
    await interaction.response.send_message(embed=embed, view=view)
    game_message = await interaction.original_response()

    for remaining in range(BAUCUA_ROUND_SECONDS - 1, 0, -1):
        await asyncio.sleep(1)
        if not baucua_round or not baucua_round.get('open'):
            return
        baucua_round['remaining'] = remaining
        embed.description = (
            'BirthdayTime nhà cái đến từ Châu Phi\n\n'
            'Đặt cược bằng cách chọn một con\n'
            f'Các mem có {remaining} giây đặt cược, hãy cẩn trọng trước khi cược!'
        )
        try:
            await game_message.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    if baucua_round and baucua_round.get('open'):
        await finish_baucua_round(interaction.channel, game_message, view)


class GiveConfirmView(discord.ui.View):
    def __init__(self, ctx, member, amount):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.ctx = ctx
        self.member = member
        self.amount = amount
        self.done = False
        self.message = None

    async def on_timeout(self):
        if self.done:
            return
        self.done = True
        self.disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def disable_all(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label='Đồng ý', style=discord.ButtonStyle.success, emoji='<a:verify:1548178353859596320>')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ người dùng lệnh mới được xác nhận.', ephemeral=True)
        if self.done:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Yêu cầu này đã được xử lý.', ephemeral=True)
        if self.member.id == self.ctx.author.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Không thể tự give coin cho chính mình.', ephemeral=True)
        if self.amount <= 0:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Số coin không hợp lệ.', ephemeral=True)

        balance = baucua_get_coins(self.ctx.author.id)
        if self.ctx.author.id != SPECIAL_ADMIN_ID and balance < self.amount:
            self.done = True
            self.disable_all()
            return await interaction.response.edit_message(
                embed=make_embed(title='<a:failed:1548973085741547580> Give thất bại', description=f'Bạn chỉ còn **{balance:,}** coin.', color=discord.Color.red()),
                view=self,
            )

        self.done = True
        if self.ctx.author.id != SPECIAL_ADMIN_ID:
            baucua_change_coins(self.ctx.author.id, -self.amount)
        baucua_change_coins(self.member.id, self.amount)
        embed = make_embed(
            title='<a:verify:1548178353859596320> Give coin thành công',
            description=f'{self.ctx.author.mention} đã give **{self.amount:,}** coin cho {self.member.mention}.',
            color=discord.Color.from_rgb(0, 0, 0),
        )
        embed.add_field(name='Số dư người gửi', value=f'`{coin_display(self.ctx.author.id)}`', inline=True)
        embed.add_field(name='Số dư người nhận', value=f'`{coin_display(self.member.id)}`', inline=True)
        self.disable_all()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='Hủy', style=discord.ButtonStyle.danger, emoji='<a:failed:1548973085741547580>')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ người dùng lệnh mới được hủy.', ephemeral=True)
        if self.done:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Yêu cầu này đã được xử lý.', ephemeral=True)
        self.done = True
        self.disable_all()
        await interaction.response.edit_message(embed=make_embed(title='<a:failed:1548973085741547580> Đã hủy give', description='Giao dịch chưa được thực hiện.', color=discord.Color.from_rgb(0, 0, 0)), view=self)


class LixiConfirmView(discord.ui.View):
    def __init__(self, ctx, amount, recipients):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.ctx = ctx
        self.amount = amount
        self.recipients = recipients
        self.done = False
        self.message = None

    async def on_timeout(self):
        if self.done:
            return
        self.done = True
        self.disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def disable_all(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label='Đồng ý', style=discord.ButtonStyle.success, emoji='<a:verify:1548178353859596320>')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ người dùng lệnh mới được xác nhận.', ephemeral=True)
        if self.done:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Lì xì này đã được xử lý.', ephemeral=True)

        if self.ctx.author.id != SPECIAL_ADMIN_ID:
            balance = baucua_get_coins(self.ctx.author.id)
            total = self.amount * len(self.recipients)
            if balance < total:
                self.done = True
                self.disable_all()
                return await interaction.response.edit_message(
                    embed=make_embed(title='<a:failed:1548973085741547580> Lì xì thất bại', description=f'Cần **{total:,}** coin nhưng bạn chỉ có **{balance:,}** coin.', color=discord.Color.red()),
                    view=self,
                )

            baucua_change_coins(self.ctx.author.id, -total)

        for member in self.recipients:
            baucua_change_coins(member.id, self.amount)

        self.done = True
        self.disable_all()
        embed = make_embed(
            title='<a:verify:1548178353859596320> Lì xì thành công',
            description=f'{self.ctx.author.mention} đã lì xì **{self.amount:,}** coin cho **{len(self.recipients)}** thành viên.',
            color=discord.Color.from_rgb(0, 0, 0),
        )
        embed.add_field(name='Số dư người lì xì', value=f'`{coin_display(self.ctx.author.id)}`', inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='Hủy', style=discord.ButtonStyle.danger, emoji='<a:failed:1548973085741547580>')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ người dùng lệnh mới được hủy.', ephemeral=True)
        if self.done:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Lì xì này đã được xử lý.', ephemeral=True)
        self.done = True
        self.disable_all()
        await interaction.response.edit_message(embed=make_embed(title='<a:failed:1548973085741547580> Đã hủy lì xì', description='Không ai được cộng coin.', color=discord.Color.from_rgb(0, 0, 0)), view=self)


class AnXinConfirmView(discord.ui.View):
    def __init__(self, ctx, recipient, amount):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.ctx = ctx
        self.recipient = recipient
        self.amount = amount
        self.done = False
        self.message = None

    async def on_timeout(self):
        if self.done:
            return
        self.done = True
        self.disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def disable_all(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label='Đồng ý', style=discord.ButtonStyle.success, emoji='<a:verify:1548178353859596320>')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.recipient.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ người được ăn xin mới được xác nhận.', ephemeral=True)
        if self.done:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Yêu cầu này đã được xử lý.', ephemeral=True)

        balance = baucua_get_coins(self.recipient.id)
        if self.recipient.id != SPECIAL_ADMIN_ID and balance < self.amount:
            self.done = True
            self.disable_all()
            return await interaction.response.edit_message(
                embed=make_embed(title='<a:failed:1548973085741547580> Ăn xin thất bại', description=f'{self.recipient.mention} không đủ coin. Số dư: **{balance:,}**.', color=discord.Color.red()),
                view=self,
            )

        self.done = True
        if self.recipient.id != SPECIAL_ADMIN_ID:
            baucua_change_coins(self.recipient.id, -self.amount)
        baucua_change_coins(self.ctx.author.id, self.amount)
        self.disable_all()
        embed = make_embed(
            title='<a:verify:1548178353859596320> Ăn xin thành công',
            description=f'{self.recipient.mention} đã đồng ý cho {self.ctx.author.mention} **{self.amount:,}** coin.',
            color=discord.Color.from_rgb(0, 0, 0),
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='Từ chối', style=discord.ButtonStyle.danger, emoji='<a:failed:1548973085741547580>')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.recipient.id:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Chỉ người được ăn xin mới được từ chối.', ephemeral=True)
        if self.done:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Yêu cầu này đã được xử lý.', ephemeral=True)
        self.done = True
        self.disable_all()
        await interaction.response.edit_message(embed=make_embed(title='<a:failed:1548973085741547580> Đã từ chối', description=f'{self.recipient.mention} đã từ chối yêu cầu ăn xin.', color=discord.Color.from_rgb(0, 0, 0)), view=self)


@bot.command(name='coin')
async def coin_command(ctx):
    balance = coin_display(ctx.author.id)
    embed = make_embed(
        title='<a:coin:1548707654459727964>Coin • BirthdayTime',
        description=f'{ctx.author.mention} đang có **{balance} coin**.',
        color=discord.Color.from_rgb(0, 0, 0),
    )
    await ctx.send(embed=embed)


@bot.command(name='give')
async def give_command(ctx, member: discord.Member = None, amount: int = None):
    if member is None or amount is None:
        return await ctx.send('<a:failed:1548973085741547580> Dùng: `!give @member số_coin`')
    if member.bot:
        return await ctx.send('<a:failed:1548973085741547580> Không thể give coin cho bot.')
    if member.id == ctx.author.id:
        return await ctx.send('<a:failed:1548973085741547580> Không thể give coin cho chính mình.')
    if amount <= 0:
        return await ctx.send('<a:failed:1548973085741547580> Số coin phải lớn hơn 0.')
    if ctx.author.id != SPECIAL_ADMIN_ID and baucua_get_coins(ctx.author.id) < amount:
        return await ctx.send(f'<a:failed:1548973085741547580> Bạn chỉ có **{baucua_get_coins(ctx.author.id):,}** coin.')

    embed = make_embed(
        title='<a:coin:1548707654459727964> Xác nhận Give',
        description=f'{ctx.author.mention} muốn give **{amount:,}** coin cho {member.mention}.\n\nBấm **Đồng ý** hoặc **Hủy**. Yêu cầu hết hạn sau **5 phút**.',
        color=discord.Color.from_rgb(0, 0, 0),
    )
    view = GiveConfirmView(ctx, member, amount)
    view.message = await ctx.send(embed=embed, view=view)


@bot.command(name='lixi')
async def lixi_command(ctx, amount: int = None):
    if amount is None:
        return await ctx.send('<a:failed:1548973085741547580> Dùng: `!lixi số_coin`')
    if amount <= 0:
        return await ctx.send('<a:failed:1548973085741547580> Số coin phải lớn hơn 0.')

    recipients = [m for m in ctx.guild.members if not m.bot]
    if not recipients:
        return await ctx.send('<a:failed:1548973085741547580> Không có thành viên hợp lệ để lì xì.')

    total = amount * len(recipients)
    if ctx.author.id != SPECIAL_ADMIN_ID and baucua_get_coins(ctx.author.id) < total:
        return await ctx.send(f'<a:failed:1548973085741547580> Lì xì cho **{len(recipients)}** người cần **{total:,}** coin, bạn chỉ có **{baucua_get_coins(ctx.author.id):,}**.')

    embed = make_embed(
        title='<a:coin:1548707654459727964> Xác nhận Lì Xì',
        description=f'{ctx.author.mention} muốn lì xì **{amount:,} coin/người** cho **{len(recipients)}** thành viên.\n\nTổng: **{total:,} coin**\n\nBấm **Đồng ý** hoặc **Hủy**. Yêu cầu hết hạn sau **5 phút**.',
        color=discord.Color.from_rgb(0, 0, 0),
    )
    view = LixiConfirmView(ctx, amount, recipients)
    view.message = await ctx.send(embed=embed, view=view)


@bot.command(name='anxin')
async def anxin_command(ctx, member: discord.Member = None, amount: int = None):
    if member is None or amount is None:
        return await ctx.send('<a:failed:1548973085741547580> Dùng: `!anxin @member số_coin`')
    if member.bot:
        return await ctx.send('<a:failed:1548973085741547580> Không thể ăn xin bot.')
    if member.id == ctx.author.id:
        return await ctx.send('<a:failed:1548973085741547580> Không thể ăn xin chính mình.')
    if amount <= 0:
        return await ctx.send('<a:failed:1548973085741547580> Số coin phải lớn hơn 0.')
    if member.id != SPECIAL_ADMIN_ID and baucua_get_coins(member.id) < amount:
        return await ctx.send(f'<a:failed:1548973085741547580> {member.mention} hiện không đủ **{amount:,}** coin.')

    embed = make_embed(
        title='<a:pls:1549015325880619038> Có người đang ăn xin',
        description=f'{ctx.author.mention} đang xin **{amount:,} coin** từ {member.mention}.\n\n{member.mention} hãy chọn **Đồng ý** hoặc **Từ chối**. Yêu cầu hết hạn sau **5 phút**.',
        color=discord.Color.from_rgb(0, 0, 0),
    )
    view = AnXinConfirmView(ctx, member, amount)
    view.message = await ctx.send(embed=embed, view=view)


class NhanRoleModal(discord.ui.Modal, title='Nhận Role'):
    role_id = discord.ui.TextInput(
        label='ID Role',
        placeholder='Nhập ID role muốn nhận',
        required=True,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(str(self.role_id.value).strip())
        except ValueError:
            return await interaction.response.send_message('<a:failed:1548973085741547580> ID Role không hợp lệ.', ephemeral=True)

        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Lệnh này chỉ dùng trong server.', ephemeral=True)

        role = guild.get_role(role_id)
        if role is None:
            return await interaction.response.send_message('<a:failed:1548973085741547580> Không tìm thấy role này.', ephemeral=True)
        if role.is_default():
            return await interaction.response.send_message('<a:failed:1548973085741547580> Không thể nhận role @everyone.', ephemeral=True)

        bot_member = guild.me
        if bot_member is None or role >= bot_member.top_role:
            return await interaction.response.send_message(' Bot không thể cấp role này do thứ tự role.', ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message(f'ℹ<a:emoji_44:1541290870966325318> Bạn đã có {role.mention}.', ephemeral=True)

        try:
            await interaction.user.add_roles(role, reason=f'/nhanrole bởi {interaction.user}')
            await interaction.response.send_message(f'<a:verify:1548178353859596320> Bạn đã nhận {role.mention} thành công!', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message('<a:failed:1548973085741547580> Bot không có quyền cấp role này.', ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f'<a:failed:1548973085741547580> Discord báo lỗi: `{e}`', ephemeral=True)



# =========================
# GAME NỐI TỪ • BIRTHDAYTIME
# =========================
NOITU_GAMES = {}
NOITU_WORD_HISTORY = {}  # guild_id -> list[set[str]], tối đa 10 ván

NOITU_WORDS = [
    "chó con", "con mèo", "mèo mun", "mun đen", "đen đủi",
    "đủi ro", "ro bốt", "bốt điện", "điện thoại", "thoại ngữ",
    "ngữ văn", "văn học", "học sinh", "sinh nhật", "nhật ký",
    "ký tên", "tên tuổi", "tuổi trẻ", "trẻ con", "con cá",
    "cá vàng", "vàng bạc", "bạc hà", "hà nội", "nội dung",
    "dung dịch", "dịch bệnh", "bệnh viện", "viện trợ", "trợ giúp",
    "giúp đỡ", "đỡ đầu", "đầu bếp", "bếp núc", "núc ních",

    # Mở rộng kho từ nối
    "anh em", "em bé", "bé trai", "trai trẻ", "trẻ nhỏ", "nhỏ bé",
    "bé ngoan", "ngoan ngoãn", "ngoãn mục", "mục tiêu", "tiêu chuẩn",
    "chuẩn bị", "bị động", "động lực", "lực lượng", "lượng giác",
    "giác quan", "quan tâm", "tâm trạng", "trạng thái", "thái độ",
    "độ cao", "cao lớn", "lớn mạnh", "mạnh mẽ", "mẽ ngoài", "ngoài trời",
    "trời xanh", "xanh lá", "lá cây", "cây cối", "cối xay", "xay bột",
    "bột mì", "mì tôm", "tôm hùm", "hùm beo", "beo béo", "béo phì",
    "phì nhiêu", "nhiêu khê", "khê nồng", "nồng nhiệt", "nhiệt độ",
    "độ ẩm", "ẩm thực", "thực phẩm", "phẩm chất", "chất lượng",
    "lượng mưa", "mưa rào", "rào chắn", "chắn gió", "gió mùa", "mùa hè",
    "hè phố", "phố cổ", "cổ kính", "kính mắt", "mắt kính", "kính trọng",
    "trọng lượng", "lượng tử", "tử tế", "tế bào", "bào chữa", "chữa bệnh",
    "bệnh nhân", "nhân viên", "viên chức", "chức năng", "năng lực", "lực sĩ",
    "sĩ quan", "quan chức", "chức vụ", "vụ án", "án phạt", "phạt tiền",
    "tiền bạc", "bạc màu", "màu sắc", "sắc đẹp", "đẹp trai", "trai đẹp",
    "đẹp mắt", "mắt xanh", "xanh biển", "biển cả", "cả nhà", "nhà cửa",
    "cửa sổ", "sổ tay", "tay chân", "chân tay", "tay áo", "áo quần",
    "quần áo", "áo dài", "dài hạn", "hạn chế", "chế độ", "độ tuổi",
    "tuổi tác", "tác phẩm", "phẩm giá", "giá trị", "trị giá", "giá cả",
    "cả ngày", "ngày mai", "mai sau", "sau này", "này nọ", "nọ kia",
    "kia kìa", "kìa trời", "trời mưa", "mưa gió", "gió bão", "bão tố",
    "tố cáo", "cáo buộc", "buộc tội", "tội lỗi", "lỗi lầm", "lầm lỗi",
    "lỗi thời", "thời gian", "gian hàng", "hàng hóa", "hóa đơn", "đơn hàng",
    "hàng ngày", "ngày tháng", "tháng năm", "năm mới", "mới mẻ", "mẻ cá",
    "cá biển", "biển xanh", "xanh ngắt", "ngắt lời", "lời nói", "nói chuyện",
    "chuyện trò", "trò chơi", "chơi game", "game thủ", "thủ công", "công việc",
    "việc làm", "làm việc", "việc nhà", "nhà trường", "trường học", "học tập",
    "tập thể", "thể thao", "thao tác", "tác động", "động cơ", "cơ hội",
    "hội nhóm", "nhóm bạn", "bạn bè", "bè bạn", "bạn thân", "thân thiện",
    "thiện chí", "chí hướng", "hướng dẫn", "dẫn đường", "đường phố", "phố xá",
    "xá lợi", "lợi ích", "ích lợi", "lợi nhuận", "nhuận bút", "bút mực",
    "mực tím", "tím ngắt", "ngắt quãng", "quãng đường", "đường dài", "dài dòng",
    "dòng sông", "sông núi", "núi non", "non nước", "nước biển", "biển đảo",
    "đảo xa", "xa xôi", "xôi chè", "chè xanh", "xanh biếc", "biếc xanh",
    "xanh ngọc", "ngọc trai", "trai làng", "làng quê", "quê hương", "hương vị",
    "vị ngọt", "ngọt ngào", "ngào đường", "đường phố", "phố phường", "phường hội",
    "hội họp", "họp mặt", "mặt trời", "trời đất", "đất nước", "nước nhà",
    "nhà nước", "nước mắt", "mắt lệ", "lệ phí", "phí phạm", "phạm vi",
    "vi phạm", "phạm tội", "tội phạm", "phạm nhân", "nhân dân", "dân làng",
    "làng xóm", "xóm làng", "làng nghề", "nghề nghiệp", "nghiệp vụ", "vụ việc",
    "việc riêng", "riêng tư", "tư nhân", "nhân tạo", "tạo hình", "hình ảnh",
    "ảnh đẹp", "đẹp đẽ", "đẽo gọt", "gọt giũa", "giũa móng", "móng tay",
    "tay trái", "trái cây", "cây ăn", "ăn uống", "uống nước", "nước ngọt",
    "ngọt lịm", "lịm dần", "dần dần", "dần tới", "tới nơi", "nơi chốn",
    "chốn đông", "đông người", "người dân", "dân số", "số lượng", "lượng tiền",
    "tiền lương", "lương tâm", "tâm hồn", "hồn nhiên", "nhiên liệu", "liệu pháp",
    "pháp luật", "luật lệ", "lệ làng", "làng quê", "quê nhà", "nhà cửa",
    "cửa hàng", "hàng quán", "quán ăn", "ăn sáng", "sáng sớm", "sớm mai",
    "mai mốt", "mốt mới", "mới tinh", "tinh thần", "thần thái", "thái bình",
    "bình an", "an toàn", "toàn diện", "diện tích", "tích cực", "cực kỳ",
    "kỳ vọng", "vọng tưởng", "tưởng tượng", "tượng đài", "đài truyền", "truyền hình",
    "hình học", "học đường", "đường học", "học hỏi", "hỏi thăm", "thăm hỏi",
    "hỏi đáp", "đáp án", "án lệ", "lệ luật", "luật chơi", "chơi vui",
    "vui vẻ", "vẻ đẹp", "đẹp lòng", "lòng tốt", "tốt bụng", "bụng dạ",
    "dạ dày", "dày đặc", "đặc biệt", "biệt danh", "danh tiếng", "tiếng nói",
    "nói thật", "thật lòng", "lòng tin", "tin tưởng", "tưởng niệm", "niệm Phật",
    "Phật giáo", "giáo dục", "dục vọng", "vọng âm", "âm thanh", "thanh âm",
    "âm nhạc", "nhạc cụ", "cụ thể", "thể hiện", "hiện tại", "tại sao",
    "sao băng", "băng giá", "giá lạnh", "lạnh lẽo", "lẽ phải", "phải phép",
    "phép tính", "tính toán", "toán học", "học thuật", "thuật toán", "toán tử",
    "tử vi", "vi tính", "tính năng", "năng lượng", "lượng giác", "giác ngộ",
    "ngộ nhận", "nhận xét", "xét duyệt", "duyệt binh", "binh lính", "lính gác",
    "gác cổng", "cổng trường", "trường lớp", "lớp học", "học trò", "trò chuyện",
    "chuyện vui", "vui chơi", "chơi đùa", "đùa vui", "vui vẻ", "vẻ vang",
    "vang vọng", "vọng cổ", "cổ điển", "điển hình", "hình thức", "thức ăn",
    "ăn ngon", "ngon miệng", "miệng cười", "cười vui", "vui nhộn", "nhộn nhịp",
    "nhịp nhàng", "nhàng nhàng", "nhà giàu", "giàu có", "có ích", "ích kỷ",
    "kỷ luật", "luật pháp", "pháp nhân", "nhân lực", "lực học", "học bổng",
    "bổng lộc", "lộc tài", "tài năng", "năng khiếu", "khiếu nại", "nại nhân",
    "nhân chứng", "chứng minh", "minh bạch", "bạch kim", "kim cương", "cương vị",
    "vị trí", "trí tuệ", "tuệ giác", "giác đấu", "đấu tranh", "tranh luận",
    "luận văn", "văn bản", "bản đồ", "đồ ăn", "ăn mặc", "mặc định", "định hướng",
    "hướng nghiệp", "nghiệp đoàn", "đoàn kết", "kết quả", "quả bóng", "bóng đá",
    "đá bóng", "bóng rổ", "rổ rá", "ráo riết", "riết róng", "róng rả",
    "rả rích", "rích rắc", "rắc rối", "rối ren", "ren rỉ", "rỉ tai",
    "tai nạn", "nạn nhân", "nhân ái", "ái ngại", "ngại ngùng", "ngùng ngoằng",
    "ngoằng ngoèo", "ngoèo ngoặt", "ngoặt đường", "đường bộ", "bộ đội", "đội nhóm",
    "nhóm lửa", "lửa cháy", "cháy nhà", "nhà bếp", "bếp lửa", "lửa trại",
    "trại hè", "hè thu", "thu hoạch", "hoạch định", "định kỳ", "kỳ hạn",
    "hạn sử dụng", "dụng cụ", "cụm từ", "từ ngữ", "ngữ pháp", "pháp lý",
    "lý do", "do dự", "dự án", "án binh", "binh đoàn", "đoàn tàu", "tàu biển",
    "biển số", "số nhà", "nhà máy", "máy móc", "móc khóa", "khóa cửa",
    "cửa biển", "biển trời", "trời cao", "cao nguyên", "nguyên nhân", "nhân quả",
    "quả thật", "thật sự", "sự thật", "thật thà", "thà rằng", "rằng buộc",
    "buộc dây", "dây điện", "điện lực", "lực điện", "điện năng", "năng suất",
    "suất ăn", "ăn trưa", "trưa hè", "hè nóng", "nóng lạnh", "lạnh giá",
    "giá trị", "trị bệnh", "bệnh tật", "tật nguyền", "nguyền rủa", "rủa xả",
    "xả nước", "nước sạch", "sạch sẽ", "sẽ đến", "đến nơi", "nơi đây",
    "đây đó", "đó đây", "đây này", "này kia", "kia kìa", "kìa bạn", "bạn học",
    "học nhóm", "nhóm trưởng", "trưởng nhóm", "nhóm chat", "chat game", "game online",
    "online shop", "shop hàng", "hàng hiệu", "hiệu quả", "quả nhiên", "nhiên nhiên",
    "nhiên liệu", "liệu trình", "trình độ", "độ khó", "khó khăn", "khăn giấy",
    "giấy bút", "bút chì", "chì màu", "màu xanh", "xanh dương", "dương lịch",
    "lịch sử", "sử dụng", "dụng tâm", "tâm lý", "lý luận", "luận điểm",
    "điểm số", "số liệu", "liệu cơm", "cơm nước", "nước canh", "canh chua",
    "chua ngọt", "ngọt thanh", "thanh mát", "mát mẻ", "mẻ lưới", "lưới cá",
    "cá rô", "rô phi", "phi công", "công an", "an ninh", "ninh bình",
    "bình minh", "minh họa", "họa sĩ", "sĩ diện", "diện mạo", "mạo hiểm",
    "hiểm nguy", "nguy hiểm", "hiểm họa", "họa mi", "mi mắt", "mắt mũi",
    "mũi tên", "tên lửa", "lửa đạn", "đạn dược", "dược phẩm", "phẩm màu",
    "màu đỏ", "đỏ thắm", "thắm thiết", "thiết kế", "kế hoạch", "hoạch toán",
    "toán tử", "tử số", "số học", "học viện", "viện nghiên cứu", "cứu hộ",
    "hộ khẩu", "khẩu vị", "vị giác", "giác mạc", "mạc áo", "áo mưa",
    "mưa xuân", "xuân hè", "hè sang", "sang trọng", "trọng tài", "tài chính",
    "chính sách", "sách giáo khoa", "khoa học", "học thuật", "thuật ngữ", "ngữ nghĩa",
    "nghĩa vụ", "vụ mùa", "mùa màng", "màng nhện", "nhện giăng", "giăng lưới",
    "lưới điện", "điện tử", "tử tế", "tế nhị", "nhịp tim", "tim mạch",
    "mạch nước", "nước suối", "suối nguồn", "nguồn điện", "điện thoại", "thoại văn",
]



def noitu_required_word(phrase: str) -> str:
    parts = phrase.strip().split()
    return parts[-1].lower() if parts else ""


def noitu_find_reply(required: str, used: set[str]) -> str | None:
    required = required.lower().strip()
    candidates = [
        w for w in NOITU_WORDS
        if w.lower().split()[0] == required and w.lower() not in used
    ]
    return random.choice(candidates) if candidates else None


def noitu_embed(title: str, description: str, color=None):
    return discord.Embed(
        title=title,
        description=description,
        color=color or discord.Color.from_rgb(0, 0, 0),
    )


async def noitu_delete_later(message, seconds=10):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def noitu_error(channel, text: str):
    msg = await channel.send(embed=noitu_embed(
        "Nối từ • BirthdayTime",
        f"<a:failed:1548973085741547580>{text}",
    ))
    asyncio.create_task(noitu_delete_later(msg, 10))


async def noitu_finish(channel, game, winner_id: int):
    if game.get("finished"):
        return
    game["finished"] = True
    if game.get("timeout_task"):
        game["timeout_task"].cancel()
    baucua_change_coins(winner_id, 1000)
    embed = noitu_embed(
        "Nối từ • BirthdayTime",
        f"<@{winner_id}> đã chiến thắng đã nhận **1000 coin**<a:coin:1548707654459727964>",
    )
    await channel.send(embed=embed)


async def noitu_schedule_timeout(channel_id: int):
    try:
        await asyncio.sleep(30)
        game = NOITU_GAMES.get(channel_id)
        if not game or game.get("finished") or not game.get("started"):
            return
        if game.get("timeout_token", 0) != game.get("last_activity", 0):
            return
        # Mỗi lần hết 30 giây, bot chỉ được tự nối tối đa 1 lần.
        if game.get("bot_auto_used"):
            return
        required = game.get("required", "")
        bot_reply = noitu_find_reply(required, game["used"])
        if bot_reply is None:
            # Không có từ bot để nối: người chơi gần nhất thắng.
            winner = game.get("last_player_id")
            if winner:
                history = NOITU_WORD_HISTORY.setdefault(game.get("guild_id"), [])
                history.append(set(game.get("used", set())))
                history[:] = history[-10:]
                await noitu_finish(bot.get_channel(channel_id), game, winner)
            return
        game["used"].add(bot_reply.lower())
        game["bot_word"] = bot_reply
        game["required"] = noitu_required_word(bot_reply)
        game["turn_user_id"] = None
        game["last_player_id"] = None
        game["bot_auto_used"] = True
        embed = noitu_embed(
            "Nối từ • BirthdayTime",
            f"**Bot đã nối tiếp với từ:** {bot_reply}\n\n**Bạn hãy nối tiếp với từ:** {game['required']}",
        )
        await bot.get_channel(channel_id).send(embed=embed)
        game["last_activity"] += 1
        game["timeout_token"] = game["last_activity"]
        # Bot chỉ tự nối 1 lần khi timeout; sau đó chờ người chơi.
        game["timeout_task"] = None
    except asyncio.CancelledError:
        return


@bot.tree.command(name="noitu", description="Tạo phòng chơi Nối từ • BirthdayTime")
async def noitu_command(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    game = NOITU_GAMES.get(channel_id)
    if game and not game.get("finished"):
        return await interaction.response.send_message(
            "<a:failed:1548973085741547580> Kênh này đang có một ván Nối từ!",
            ephemeral=True,
        )

    NOITU_GAMES[channel_id] = {
        "guild_id": interaction.guild_id,
        "started": False,
        "finished": False,
        "bot_word": None,
        "required": None,
        "used": set(),
        "turn_user_id": None,
        "last_player_id": None,
        "last_activity": 0,
        "timeout_token": 0,
        "timeout_task": None,
        "bot_auto_used": False,
    }
    embed = noitu_embed(
        "Nối từ • BirthdayTime",
        "Hãy nhập lệnh `!start` để bot ra từ để nối",
    )
    await interaction.response.send_message(embed=embed)


async def noitu_start(channel):
    game = NOITU_GAMES.get(channel.id)
    if not game or game.get("finished"):
        return
    if game.get("started"):
        return
    start = random.choice(NOITU_WORDS)
    game.update({
        "started": True,
        "bot_word": start,
        "required": noitu_required_word(start),
        "used": {start.lower()},
        "turn_user_id": None,
        "last_player_id": None,
        "last_activity": 0,
        "timeout_token": 0,
        "bot_auto_used": False,
    })
    embed = noitu_embed(
        "Nối từ • BirthdayTime",
        f"**Bot đã ra từ nối là:** {start}\n\n**Bạn hãy nối tiếp với từ:** {game['required']}",
    )
    await channel.send(embed=embed)
    game["timeout_task"] = asyncio.create_task(noitu_schedule_timeout(channel.id))


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    game = NOITU_GAMES.get(channel_id)

    # !start: ai cũng có thể bắt đầu ván đã tạo bằng /noitu.
    if message.content.strip().lower() == "!start":
        if not game or game.get("finished"):
            await noitu_error(message.channel, "Hãy dùng `/noitu` trước để tạo ván")
        elif game.get("started"):
            await noitu_error(message.channel, "Ván Nối từ đã bắt đầu rồi")
        else:
            await noitu_start(message.channel)
        return

    # !stop: dừng ván Nối từ hiện tại trong kênh.
    if message.content.strip().lower() == "!stop":
        if not game or game.get("finished"):
            await noitu_error(message.channel, "Không có ván Nối từ nào đang chạy")
        else:
            if game.get("timeout_task"):
                game["timeout_task"].cancel()
            NOITU_GAMES.pop(channel_id, None)
            await message.channel.send(embed=noitu_embed(
                "Nối từ • BirthdayTime",
                "Ván Nối từ đã được dừng.",
            ))
        return

    if game and game.get("started") and not game.get("finished"):
        # Nếu đã có người vừa nối, người đó không được nối tiếp ngay.
        if game.get("turn_user_id") == message.author.id:
            await noitu_error(message.channel, "Bạn chưa tới lượt nối")
            return

        user_word = " ".join(message.content.strip().split()).lower()
        parts = user_word.split()
        required = game["required"].lower()

        if len(parts) < 2 or parts[0] != required:
            await noitu_error(message.channel, "Từ nối không hợp lệ")
            return

        # Lưu lịch sử 10 ván: nếu từ nằm trong lịch sử thì từ chối.
        history = NOITU_WORD_HISTORY.setdefault(message.guild.id, [])
        recent_10_games = history[-10:]
        recent_words = {w for game_words in recent_10_games for w in game_words}
        if user_word in game["used"] or user_word in recent_words:
            await noitu_error(message.channel, "Từ này đã nối từ 10 ván trước")
            return

        game["used"].add(user_word)
        game["last_player_id"] = message.author.id
        game["turn_user_id"] = message.author.id
        game["last_activity"] += 1
        game["timeout_token"] = game["last_activity"]
        game["bot_auto_used"] = False
        if game.get("timeout_task"):
            game["timeout_task"].cancel()

        bot_reply = noitu_find_reply(noitu_required_word(user_word), game["used"])
        if bot_reply is None:
            history.append(set(game["used"]))
            history[:] = history[-10:]
            await noitu_finish(message.channel, game, message.author.id)
            return

        game["used"].add(bot_reply.lower())
        game["bot_word"] = bot_reply
        game["required"] = noitu_required_word(bot_reply)

        embed = noitu_embed(
            "Nối từ • BirthdayTime",
            f"<@{message.author.id}> đã ra từ: **{user_word}**\n\n**Bạn hãy nối tiếp với từ:** {game['required']}",
        )
        await message.channel.send(embed=embed)
        game["timeout_task"] = asyncio.create_task(noitu_schedule_timeout(channel_id))
        return

    await bot.process_commands(message)


# ============================================================
# 🏴‍☠️ ONE PIECE — /onepiece (chỉ giữ 1 lệnh)
# ============================================================
TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
MAX_LEVEL = 5000
FIGHT_COOLDOWN = 3
BOSS_COOLDOWN = 60
PVP_ATTACK_COOLDOWN = 1.5
SELL_REFRESH_SECONDS = 3600
LEADERBOARD_CONFIG_FILE = "leaderboard_config.json"
SELL_CONFIG_FILE = "sell_config.json"

# Dùng chung bot instance đã khai báo ở đầu file.
# Không tạo bot instance thứ hai, nếu không các lệnh cũ sẽ bị mất khỏi tree.
SKILLS = {
    "trái": [{"name": "Gomu Pistol", "xp_req": 0, "damage": 15},
             {"name": "Gomu Bazooka", "xp_req": 15, "damage": 25},
             {"name": "Gear Second", "xp_req": 40, "damage": 45},
             {"name": "Gear Fourth", "xp_req": 80, "damage": 75}],
}

WEAPON_EMOJI = {"trái": "🍎"}
STAT_INFO = {
    "defense": {"name": "Defense", "emoji": "🛡️"},
    "fruit": {"name": "Fruit", "emoji": "🍎"},
}

RARITY_COLORS = {
    "Starter": 0x95A5A6, "Common": 0xBDC3C7, "Uncommon": 0x2ECC71,
    "Rare": 0x3498DB, "Legendary": 0x9B59B6, "Mythical": 0xE74C3C, "King": 0xFFD700,
}
TITLES = {
    "rookie": {"name": "Tân Binh", "emoji": "🌱", "req": 10},
    "pirate": {"name": "Hải Tặc", "emoji": "🏴‍☠️", "req": 100},
    "supernova": {"name": "Siêu Tân Tinh", "emoji": "⭐", "req": 500},
    "warlord": {"name": "Thất Vũ Hải", "emoji": "🦈", "req": 1000},
    "admiral": {"name": "Đô Đốc", "emoji": "⚓", "req": 2000},
    "emperor": {"name": "Tứ Hoàng", "emoji": "👑", "req": 3000},
    "king_pirate": {"name": "Vua Hải Tặc", "emoji": "🏆", "req": 4000},
    "legend": {"name": "Huyền Thoại", "emoji": "🌟", "req": 5000},
}
BOUNTY_RANKS = [
    {"min": 0, "max": 10_000, "name": "Vô Danh", "emoji": "👤", "color": 0x95A5A6},
    {"min": 10_000, "max": 100_000, "name": "Tân Binh", "emoji": "🌱", "color": 0x2ECC71},
    {"min": 100_000, "max": 1_000_000, "name": "Hải Tặc Nhí", "emoji": "🏴‍☠️", "color": 0x3498DB},
    {"min": 1_000_000, "max": 10_000_000, "name": "Hải Tặc Khét Tiếng", "emoji": "⚔️", "color": 0x9B59B6},
    {"min": 10_000_000, "max": 100_000_000, "name": "Siêu Tân Tinh", "emoji": "⭐", "color": 0xE74C3C},
    {"min": 100_000_000, "max": 500_000_000, "name": "Thất Vũ Hải", "emoji": "🦈", "color": 0xE67E22},
    {"min": 500_000_000, "max": 1_000_000_000, "name": "Đô Đốc", "emoji": "⚓", "color": 0xF39C12},
    {"min": 1_000_000_000, "max": 5_000_000_000, "name": "Tứ Hoàng", "emoji": "👑", "color": 0xFFD700},
    {"min": 5_000_000_000, "max": 999_999_999_999, "name": "Vua Hải Tặc", "emoji": "🏆", "color": 0xFF6B35},
]
GACHA_RATES = {"Common": 50.0, "Uncommon": 25.0, "Rare": 15.0, "Legendary": 8.0, "Mythical": 1.9, "King": 0.1}
GACHA_COST = {"single": 100000, "x10": 900000, "x50": 4000000}

def get_gacha_single_cost(player):
    """Giá random x1 tăng 10.000 coin sau mỗi 10 level; giữ mốc gốc 100.000."""
    level = max(1, int(player.get("level", 1)))
    return GACHA_COST["single"] + (level // 10) * 10_000

def get_gacha_cost(player, count):
    if count == 1:
        return get_gacha_single_cost(player)
    if count == 10:
        return get_gacha_single_cost(player) * 9
    if count == 50:
        return get_gacha_single_cost(player) * 40
    raise ValueError("Số lượt random không hợp lệ")

def roll_fruit(sea=1):
    """Random 1 trái theo rarity; hỗ trợ cả LMythical của dữ liệu hiện tại."""
    items = [(k, v) for k, v in SHOP_DATA["fruits"].items() if v.get("sea", 1) <= sea]
    if not items:
        return None
    weighted = []
    for key, item in items:
        rarity = item.get("rarity", "Common")
        if rarity == "LMythical":
            rarity = "Mythical"
        weight = GACHA_RATES.get(rarity, 0.0)
        if weight > 0:
            weighted.append((key, weight))
    if not weighted:
        key, _ = random.choice(items)
        return key
    keys = [k for k, _ in weighted]
    weights = [w for _, w in weighted]
    return random.choices(keys, weights=weights, k=1)[0]

def give_fruits_to_player(player, results):
    inv = player.setdefault("inventory", {}).setdefault("fruits", [])
    new = []
    for key in results:
        if key and key not in inv:
            inv.append(key)
            new.append(key)
    return new

def build_gacha_embed(player):
    single = get_gacha_single_cost(player)
    x10 = single * 9
    x50 = single * 40
    return discord.Embed(
        title="🎲 Random Trái Ác Quỷ",
        description=(
            f"🎯 **Random x1:** `{single:,}` Coin\n"
            f"🎁 **Random x10:** `{x10:,}` Coin\n"
            f"🌟 **Random x50:** `{x50:,}` Coin\n\n"
            f"📊 Level hiện tại: **Lv.{player.get('level', 1)}**\n"
            "💡 **Mỗi 10 level, giá random x1 tăng 10.000 Coin.**"
        ),
        color=0x9B59B6
    )

def build_gacha_result_embed(results, player, new_items=None, is_multi=False, free=False):
    names = []
    for key in results:
        item = SHOP_DATA["fruits"].get(key)
        if item:
            names.append(f"{item['emoji']} **{item['name']}** • {item.get('rarity','Common')}")
    title = "🎁 Random Trái Miễn Phí" if free else ("🎲 Kết Quả Random x10" if is_multi else "🎲 Kết Quả Random")
    desc = "\n".join(names) if names else "❌ Không random được trái nào."
    if free:
        desc = "🎉 **Bạn nhận 1 lượt Random miễn phí khi mới tham gia!**\n\n" + desc
    new_items = new_items or []
    if new_items:
        desc += "\n\n✅ **Trái mới nhận:** " + ", ".join(SHOP_DATA["fruits"][k]["name"] for k in new_items if k in SHOP_DATA["fruits"])
    desc += f"\n\n💰 Coin hiện tại: `{player.get('coin',0):,}`\n📊 Level: `Lv.{player.get('level',1)}`"
    return discord.Embed(title=title, description=desc, color=0x2ECC71)

BATTLE_CONFIG = {"bounty_steal_pct": 0.20, "min_bounty": 100_000, "level_gap": 1000, "cooldown": 1800}
SEA_DATA = {
    1: {
        "name": "First Sea", "emoji": "🌊", "level_range": (1, 1000),
        "islands": {
            "starter_island": {
                "name": "Starter Island", "emoji": "🏝️", "level_req": 1,
                "monsters": [
                    {"name": "Bandit", "hp": 50, "damage": 5, "xp": 15, "coin": 20},
                    {"name": "Trainee", "hp": 60, "damage": 6, "xp": 20, "coin": 25},
                    {"name": "Thief", "hp": 70, "damage": 8, "xp": 25, "coin": 30},
                ],
                "boss": {"name": "Gorilla King", "hp": 500, "damage": 30, "xp": 5000, "coin": 10000},
                "quest_kill": 5,
            },
            "jungle": {
                "name": "Jungle", "emoji": "🌴", "level_req": 10,
                "monsters": [
                    {"name": "Monkey", "hp": 100, "damage": 12, "xp": 40, "coin": 60},
                    {"name": "Gorilla", "hp": 130, "damage": 15, "xp": 55, "coin": 80},
                    {"name": "Wild Boar", "hp": 120, "damage": 14, "xp": 50, "coin": 75},
                ],
                "boss": {"name": "Bobby", "hp": 1200, "damage": 60, "xp": 25000, "coin": 50000},
                "quest_kill": 8,
            },
            "pirate_village": {
                "name": "Pirate Village", "emoji": "🏴‍☠️", "level_req": 30,
                "monsters": [
                    {"name": "Pirate", "hp": 250, "damage": 25, "xp": 100, "coin": 180},
                    {"name": "Brute", "hp": 320, "damage": 35, "xp": 130, "coin": 240},
                    {"name": "Pirate Captain", "hp": 400, "damage": 45, "xp": 170, "coin": 320},
                ],
                "boss": {"name": "Bobby Chef", "hp": 3000, "damage": 120, "xp": 100000, "coin": 200000},
                "quest_kill": 12,
            },
            "desert": {
                "name": "Desert", "emoji": "🏜️", "level_req": 60,
                "monsters": [
                    {"name": "Desert Bandit", "hp": 500, "damage": 60, "xp": 220, "coin": 400},
                    {"name": "Desert Officer", "hp": 650, "damage": 80, "xp": 280, "coin": 550},
                    {"name": "Sand Bandit", "hp": 580, "damage": 70, "xp": 250, "coin": 470},
                ],
                "boss": None, "quest_kill": 15,
            },
            "frozen_village": {
                "name": "Frozen Village", "emoji": "❄️", "level_req": 90,
                "monsters": [
                    {"name": "Snow Bandit", "hp": 800, "damage": 100, "xp": 400, "coin": 700},
                    {"name": "Snowman", "hp": 1000, "damage": 130, "xp": 500, "coin": 900},
                    {"name": "Ice Warrior", "hp": 1200, "damage": 150, "xp": 600, "coin": 1100},
                ],
                "boss": {"name": "Yeti", "hp": 10000, "damage": 350, "xp": 500000, "coin": 1000000},
                "quest_kill": 18,
            },
            "marine_fortress": {
                "name": "Marine Fortress", "emoji": "⚓", "level_req": 120,
                "monsters": [
                    {"name": "Marine Recruit", "hp": 1500, "damage": 180, "xp": 700, "coin": 1200},
                    {"name": "Marine Officer", "hp": 1800, "damage": 220, "xp": 850, "coin": 1500},
                    {"name": "Chief Petty Officer", "hp": 2200, "damage": 260, "xp": 1000, "coin": 1800},
                ],
                "boss": {"name": "Vice Admiral", "hp": 20000, "damage": 600, "xp": 1500000, "coin": 3000000},
                "quest_kill": 20,
            },
            "skylands": {
                "name": "Skylands", "emoji": "☁️", "level_req": 150,
                "monsters": [
                    {"name": "Sky Bandit", "hp": 2600, "damage": 300, "xp": 1200, "coin": 2200},
                    {"name": "Sky Warrior", "hp": 3200, "damage": 360, "xp": 1500, "coin": 2700},
                    {"name": "Dark Master", "hp": 4000, "damage": 420, "xp": 1800, "coin": 3300},
                ],
                "boss": {"name": "Fajita", "hp": 35000, "damage": 900, "xp": 3000000, "coin": 6000000},
                "quest_kill": 22,
            },
            "prison": {
                "name": "Prison", "emoji": "🔒", "level_req": 200,
                "monsters": [
                    {"name": "Prisoner", "hp": 5000, "damage": 500, "xp": 2200, "coin": 4000},
                    {"name": "Dangerous Prisoner", "hp": 6500, "damage": 650, "xp": 2800, "coin": 5000},
                    {"name": "Guard Beast", "hp": 8000, "damage": 800, "xp": 3500, "coin": 6500},
                ],
                "boss": {"name": "Warden", "hp": 60000, "damage": 1500, "xp": 8000000, "coin": 15000000},
                "quest_kill": 25,
            },
            "colosseum": {
                "name": "Colosseum", "emoji": "🏛️", "level_req": 250,
                "monsters": [
                    {"name": "Gladiator", "hp": 9000, "damage": 900, "xp": 4000, "coin": 7500},
                    {"name": "Brute", "hp": 11000, "damage": 1100, "xp": 5000, "coin": 9000},
                    {"name": "Arena Master", "hp": 13000, "damage": 1300, "xp": 6000, "coin": 11000},
                ],
                "boss": {"name": "Diamond", "hp": 100000, "damage": 2500, "xp": 15000000, "coin": 30000000},
                "quest_kill": 28,
            },
            "magma_village": {
                "name": "Magma Village", "emoji": "🌋", "level_req": 300,
                "monsters": [
                    {"name": "Military Soldier", "hp": 15000, "damage": 1500, "xp": 7000, "coin": 13000},
                    {"name": "Magma Trooper", "hp": 18000, "damage": 1800, "xp": 8500, "coin": 16000},
                    {"name": "Magma Spy", "hp": 22000, "damage": 2200, "xp": 10000, "coin": 20000},
                ],
                "boss": {"name": "Magma Admiral", "hp": 180000, "damage": 4000, "xp": 30000000, "coin": 50000000},
                "quest_kill": 30,
            },
            "underwater_city": {
                "name": "Underwater City", "emoji": "🌊", "level_req": 375,
                "monsters": [
                    {"name": "Fishman Warrior", "hp": 25000, "damage": 2500, "xp": 12000, "coin": 22000},
                    {"name": "Fishman Officer", "hp": 30000, "damage": 3000, "xp": 15000, "coin": 28000},
                    {"name": "Fishman Captain", "hp": 38000, "damage": 3800, "xp": 18000, "coin": 35000},
                ],
                "boss": {"name": "Fishman Lord", "hp": 300000, "damage": 7000, "xp": 50000000, "coin": 100000000},
                "quest_kill": 32,
            },
            "fountain_city": {
                "name": "Fountain City", "emoji": "⛲", "level_req": 450,
                "monsters": [
                    {"name": "Galley Pirate", "hp": 45000, "damage": 4500, "xp": 22000, "coin": 40000},
                    {"name": "Galley Officer", "hp": 55000, "damage": 5500, "xp": 27000, "coin": 50000},
                    {"name": "Galley Captain", "hp": 70000, "damage": 7000, "xp": 34000, "coin": 65000},
                ],
                "boss": {"name": "Cyborg", "hp": 500000, "damage": 12000, "xp": 100000000, "coin": 200000000},
                "quest_kill": 35,
            },
            "haunted_ship": {
                "name": "Haunted Ship", "emoji": "👻", "level_req": 600,
                "monsters": [
                    {"name": "Living Zombie", "hp": 80000, "damage": 8000, "xp": 40000, "coin": 75000},
                    {"name": "Demonic Soul", "hp": 100000, "damage": 10000, "xp": 50000, "coin": 95000},
                    {"name": "Cursed Ghost", "hp": 120000, "damage": 12000, "xp": 60000, "coin": 115000},
                ],
                "boss": {"name": "Cursed Captain", "hp": 800000, "damage": 20000, "xp": 200000000, "coin": 400000000},
                "quest_kill": 38,
            },
            "graveyard_island": {
                "name": "Graveyard Island", "emoji": "🪦", "level_req": 750,
                "monsters": [
                    {"name": "Reborn Skeleton", "hp": 150000, "damage": 15000, "xp": 70000, "coin": 130000},
                    {"name": "Zombie Pirate", "hp": 180000, "damage": 18000, "xp": 85000, "coin": 160000},
                    {"name": "Necromancer", "hp": 220000, "damage": 22000, "xp": 100000, "coin": 200000},
                ],
                "boss": {"name": "Necromancer Lord", "hp": 1500000, "damage": 35000, "xp": 400000000, "coin": 800000000},
                "quest_kill": 40,
            },
        }
    },
    2: {
        "name": "Second Sea", "emoji": "🌊🌊", "level_range": (1000, 2500),
        "islands": {
            "kingdom_of_rose": {
                "name": "Kingdom of Rose", "emoji": "🌹", "level_req": 1000,
                "monsters": [
                    {"name": "Raider", "hp": 300000, "damage": 30000, "xp": 130000, "coin": 250000},
                    {"name": "Mercenary", "hp": 380000, "damage": 38000, "xp": 160000, "coin": 300000},
                    {"name": "Rose Knight", "hp": 450000, "damage": 45000, "xp": 190000, "coin": 360000},
                ],
                "boss": {"name": "Diamond (Awakened)", "hp": 2000000, "damage": 60000, "xp": 500000000, "coin": 1000000000},
                "quest_kill": 40,
            },
            "green_zone": {
                "name": "Green Zone", "emoji": "🌳", "level_req": 1100,
                "monsters": [
                    {"name": "Marine Soldier", "hp": 500000, "damage": 50000, "xp": 200000, "coin": 380000},
                    {"name": "Marine Captain", "hp": 650000, "damage": 65000, "xp": 260000, "coin": 500000},
                    {"name": "Marine Commander", "hp": 800000, "damage": 80000, "xp": 320000, "coin": 620000},
                ],
                "boss": {"name": "Cyborg (Awakened)", "hp": 3500000, "damage": 100000, "xp": 1000000000, "coin": 2000000000},
                "quest_kill": 42,
            },
            "snow_mountain": {
                "name": "Snow Mountain", "emoji": "🏔️", "level_req": 1300,
                "monsters": [
                    {"name": "Snow Trooper", "hp": 900000, "damage": 90000, "xp": 350000, "coin": 650000},
                    {"name": "Snow Assassin", "hp": 1100000, "damage": 110000, "xp": 420000, "coin": 800000},
                    {"name": "Ice Giant", "hp": 1400000, "damage": 140000, "xp": 500000, "coin": 950000},
                ],
                "boss": {"name": "Snow Demon", "hp": 5000000, "damage": 150000, "xp": 1500000000, "coin": 3000000000},
                "quest_kill": 45,
            },
            "hot_and_cold": {
                "name": "Hot and Cold", "emoji": "🌡️", "level_req": 1500,
                "monsters": [
                    {"name": "Fire Trooper", "hp": 1500000, "damage": 150000, "xp": 580000, "coin": 1100000},
                    {"name": "Ice Trooper", "hp": 1800000, "damage": 180000, "xp": 680000, "coin": 1300000},
                    {"name": "Magma Soldier", "hp": 2200000, "damage": 220000, "xp": 800000, "coin": 1500000},
                ],
                "boss": {"name": "Fire and Ice Admiral", "hp": 8000000, "damage": 250000, "xp": 2000000000, "coin": 4000000000},
                "quest_kill": 48,
            },
            "cursed_ship": {
                "name": "Cursed Ship", "emoji": "🏴‍☠️", "level_req": 1700,
                "monsters": [
                    {"name": "Cursed Pirate", "hp": 2500000, "damage": 250000, "xp": 950000, "coin": 1800000},
                    {"name": "Soul Reaper", "hp": 3000000, "damage": 300000, "xp": 1100000, "coin": 2100000},
                    {"name": "Cursed Warrior", "hp": 3500000, "damage": 350000, "xp": 1300000, "coin": 2500000},
                ],
                "boss": {"name": "Cursed Captain", "hp": 12000000, "damage": 400000, "xp": 3000000000, "coin": 6000000000},
                "quest_kill": 50,
            },
            "ice_castle": {
                "name": "Ice Castle", "emoji": "🏰", "level_req": 1900,
                "monsters": [
                    {"name": "Arctic Warrior", "hp": 4000000, "damage": 400000, "xp": 1500000, "coin": 2800000},
                    {"name": "Frozen Knight", "hp": 4800000, "damage": 480000, "xp": 1800000, "coin": 3300000},
                    {"name": "Ice Queen Guard", "hp": 5500000, "damage": 550000, "xp": 2100000, "coin": 3800000},
                ],
                "boss": {"name": "Ice Queen", "hp": 18000000, "damage": 600000, "xp": 5000000000, "coin": 10000000000},
                "quest_kill": 52,
            },
        }
    },
    3: {
        "name": "Third Sea", "emoji": "🌊🌊🌊", "level_range": (2500, 5000),
        "islands": {
            "port_town": {
                "name": "Port Town", "emoji": "🏘️", "level_req": 2500,
                "monsters": [
                    {"name": "Pirate Thug", "hp": 20000000, "damage": 2000000, "xp": 7000000, "coin": 13000000},
                    {"name": "Marine Guard", "hp": 24000000, "damage": 2400000, "xp": 8200000, "coin": 15000000},
                    {"name": "Town Bandit", "hp": 28000000, "damage": 2800000, "xp": 9500000, "coin": 17000000},
                ],
                "boss": None, "quest_kill": 50,
            },
            "hydra_island": {
                "name": "Hydra Island", "emoji": "🐉", "level_req": 2700,
                "monsters": [
                    {"name": "Hydra Warrior", "hp": 35000000, "damage": 3500000, "xp": 12000000, "coin": 22000000},
                    {"name": "Beast Hunter", "hp": 42000000, "damage": 4200000, "xp": 14500000, "coin": 26000000},
                    {"name": "Hydra Guardian", "hp": 50000000, "damage": 5000000, "xp": 17000000, "coin": 30000000},
                ],
                "boss": {"name": "Stone", "hp": 80000000, "damage": 3000000, "xp": 25000000000, "coin": 50000000000},
                "quest_kill": 52,
            },
            "great_tree": {
                "name": "Great Tree", "emoji": "🌳", "level_req": 2900,
                "monsters": [
                    {"name": "Forest Guardian", "hp": 60000000, "damage": 6000000, "xp": 20000000, "coin": 36000000},
                    {"name": "Tree Beast", "hp": 72000000, "damage": 7200000, "xp": 24000000, "coin": 43000000},
                    {"name": "Ancient Druid", "hp": 85000000, "damage": 8500000, "xp": 28000000, "coin": 50000000},
                ],
                "boss": {"name": "Island Empress", "hp": 120000000, "damage": 5000000, "xp": 40000000000, "coin": 80000000000},
                "quest_kill": 55,
            },
            "castle_turtle": {
                "name": "Castle on Turtle", "emoji": "🐢", "level_req": 3100,
                "monsters": [
                    {"name": "Turtle Warrior", "hp": 100000000, "damage": 10000000, "xp": 34000000, "coin": 62000000},
                    {"name": "Samurai Guard", "hp": 120000000, "damage": 12000000, "xp": 40000000, "coin": 72000000},
                    {"name": "Shogun Soldier", "hp": 150000000, "damage": 15000000, "xp": 48000000, "coin": 86000000},
                ],
                "boss": {"name": "Cake Queen", "hp": 200000000, "damage": 8000000, "xp": 70000000000, "coin": 140000000000},
                "quest_kill": 58,
            },
            "haunted_castle": {
                "name": "Haunted Castle", "emoji": "🏚️", "level_req": 3400,
                "monsters": [
                    {"name": "Reaper", "hp": 180000000, "damage": 18000000, "xp": 58000000, "coin": 105000000},
                    {"name": "Soul Reaper", "hp": 220000000, "damage": 22000000, "xp": 68000000, "coin": 125000000},
                    {"name": "Death Knight", "hp": 270000000, "damage": 27000000, "xp": 80000000, "coin": 145000000},
                ],
                "boss": {"name": "Soul Reaper (Awakened)", "hp": 350000000, "damage": 12000000, "xp": 120000000000, "coin": 240000000000},
                "quest_kill": 60,
            },
        }
    },
}

SHOP_DATA = {
    "fruits": {
        "rocket": {"name": "Rocket", "price": 5000, "rarity": "Common", "sea": 1, "emoji": "<:Rocket:1552121520686375043>"},
        "spin": {"name": "Spin", "price": 7500, "rarity": "Common", "sea": 1, "emoji": "<:Spin:1552122260259602514>"},
        "chop": {"name": "blade", "price": 30000, "rarity": "Common", "sea": 1, "emoji": "<:Blade:1552122411707797644>"},
        "spring": {"name": "Spring", "price": 60000, "rarity": "Common", "sea": 1, "emoji": "<:Spring:1552122676946935808>"},
        "boom": {"name": "Boom", "price": 80000, "rarity": "Common", "sea": 1, "emoji": "<:Bomb:1552123191248556132>"},
        "smoke": {"name": "Smoke", "price": 100000, "rarity": "Common", "sea": 1, "emoji": "<:Smoke:1552124023989739692>"},
        "spike": {"name": "Spike", "price": 180000, "rarity": "Common", "sea": 1, "emoji": "<:Spike:1552124396607635538>"},
        "flame": {"name": "Flame", "price": 250000, "rarity": "Uncommon", "sea": 1, "emoji": "<:Flame:1552125668362420334>"},
        "ice": {"name": "Ice", "price": 350000, "rarity": "Uncommon", "sea": 1, "emoji": "<:Ice:1552126283268362371>"},
        "sand": {"name": "Sand", "price": 420000, "rarity": "Uncommon", "sea": 1, "emoji": "<:Sand:1552126592061542410>"},
        "dark": {"name": "Dark", "price": 500000, "rarity": "Uncommon", "sea": 1, "emoji": "<:Dark:1552126916838957096>"},
        "eagle": {"name": "Eagle", "price": 550000, "rarity": "Uncommon", "sea": 1, "emoji": "<:Eagle:1552127851434745926>"},
        "diamond": {"name": "Diamond", "price": 600000, "rarity": "Rare", "sea": 1, "emoji": "<:Diamond:1552128142976483389>"},
        "light": {"name": "Light", "price": 650000, "rarity": "Rare", "sea": 1, "emoji": "<:Light:1552128433595883581>"},
        "rubber": {"name": "Rubber", "price": 750000, "rarity": "Rare", "sea": 1, "emoji": "<:Rubber:1552128724059553892>"},
        "ghost": {"name": "Ghost", "price": 940000, "rarity": "Rare", "sea": 1, "emoji": "<:Ghost:1552128805571797013>"},
        "magma": {"name": "Magma", "price": 960000, "rarity": "Rare", "sea": 1, "emoji": "<:Magma:1552129422478417971>"},
        "quake": {"name": "Quake", "price": 1000000, "rarity": "Rare", "sea": 1, "emoji": "<:Quake:1552129917863596174>"},
        "buddha": {"name": "Buddha", "price": 1200000, "rarity": "Rare", "sea": 1, "emoji": "<:Buddha:1552130097111109722>"},
        "love": {"name": "Love", "price": 1300000, "rarity": "Rare", "sea": 1, "emoji": "<:Love:1552130396937003048>"},
        "creation": {"name": "Creation", "price": 1400000, "rarity": "Rare", "sea": 1, "emoji": "<:Creation:1552130835237568604>"},
        "spider": {"name": "Spider", "price": 1500000, "rarity": "Rare", "sea": 1, "emoji": "<:Spider:1552131088153845810>"},
        "sound": {"name": "Sound", "price": 1700000, "rarity": "Rare", "sea": 1, "emoji": "<:Sound:1552131217489657976>"},
        "phoenix": {"name": "Phoenix", "price": 1800000, "rarity": "Rare", "sea": 1, "emoji": "<:Phoenix:1552131345814130771>"},
        "portal": {"name": "Portal", "price": 1900000, "rarity": "Rare", "sea": 1, "emoji": "<:Portal:1552131476676681849>"},
        "lingtning": {"name": "Lightning", "price": 2100000, "rarity": "Legendary", "sea": 1, "emoji": "<:Lightning:1552132636691144724>"},
        "pain": {"name": "Pain", "price": 2300000, "rarity": "Legendary", "sea": 1, "emoji": "<:Pain:1552132667875663972>"},
        "blizzard": {"name": "Blizzard", "price": 2400000, "rarity": "Legendary", "sea": 1, "emoji": "<:Blizzard:1552132766072836137>"},
        "gravity": {"name": "Gravity", "price": 2500000, "rarity": "Mythical", "sea": 1, "emoji": "<:Gravity:1552134040763502692>"},
        "mammoth": {"name": "Mammoth", "price": 2700000, "rarity": "Mythical", "sea": 1, "emoji": "<:Mammoth:1552134659624931388>"},
        "t-rex": {"name": "T-Rex", "price": 2700000, "rarity": "Mythical", "sea": 1, "emoji": "<:TRex:1552135002928713798>"},
        "dough": {"name": "Dough", "price": 2800000, "rarity": "Mythical", "sea": 1, "emoji": "<:Dough:1552135199008231515>"},
        "shadow": {"name": "Shadow", "price": 2900000, "rarity": "Mythical", "sea": 1, "emoji": "<:Shadow:1552135431204900967>"},
        "venom": {"name": "Venom", "price": 3000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Venom:1552135525035671562>"},
        "gas": {"name": "Gas", "price": 3200000, "rarity": "Mythical", "sea": 1, "emoji": "<:Gas:1552136163085525012>"},
        "spirit": {"name": "Spirit", "price": 3400000, "rarity": "Mythical", "sea": 1, "emoji": "<:Spirit:1552136390228181042>"},
        "tiger": {"name": "Tiger", "price": 5000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Tiger:1552136589696704644>"},
        "yeti": {"name": "Yeti", "price": 5000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Yeti:1552136931268366356>"},
        "magnet": {"name": "Magnet", "price": 6000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Magnet:1552137076408057886>"},
        "kitsune": {"name": "Kitsune", "price": 8000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Kitsune:1552137395095339088>"},
        "control": {"name": "Control", "price": 9000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Control:1552138369482362952>"},
        "dragon_east": {"name": "Dragon East", "price": 15000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Dragon_East:1552138428940816444>"},
        "dragon_west": {"name": "Dragon West", "price": 15000000, "rarity": "Mythical", "sea": 1, "emoji": "<:Dragon_West:1552138668263604244>"},

        
    },

}
AWAKENING_SKILLS = {
    "flame": {
        "color": 0xE67E22,
        "skills": {
            "Z": {"fragment": 250, "damage_mult": 1.5, "awakened_name": "Flame Bullet+", "emoji": "🔥"},
            "X": {"fragment": 400, "damage_mult": 1.5, "awakened_name": "Fire Fist+", "emoji": "👊"},
            "C": {"fragment": 500, "damage_mult": 1.6, "awakened_name": "Flame Flight+", "emoji": "🦅"},
            "V": {"fragment": 800, "damage_mult": 1.8, "awakened_name": "Flame Emperor", "emoji": "👑"},
        },
        "full_bonus": {"name": "Flame Awakening", "desc": "Mở khoá sức mạnh tối thượng", "damage_mult": 1.3},
    },
    "ice": {
        "color": 0x3498DB,
        "skills": {
            "Z": {"fragment": 250, "damage_mult": 1.5, "awakened_name": "Ice Spear+", "emoji": "🗡️"},
            "X": {"fragment": 400, "damage_mult": 1.5, "awakened_name": "Ice Ball+", "emoji": "⚪"},
            "C": {"fragment": 500, "damage_mult": 1.6, "awakened_name": "Ice Age+", "emoji": "❄️"},
            "V": {"fragment": 800, "damage_mult": 1.8, "awakened_name": "Ice Time", "emoji": "⏱️"},
        },
        "full_bonus": {"name": "Ice Awakening", "desc": "Đóng băng toàn bộ", "damage_mult": 1.3},
    },
    "dark": {
        "color": 0x2C3E50,
        "skills": {
            "Z": {"fragment": 350, "damage_mult": 1.5, "awakened_name": "Dark Hole+", "emoji": "🕳️"},
            "X": {"fragment": 500, "damage_mult": 1.5, "awakened_name": "Black Hole+", "emoji": "⚫"},
            "C": {"fragment": 650, "damage_mult": 1.6, "awakened_name": "Dark Prison+", "emoji": "🔒"},
            "V": {"fragment": 900, "damage_mult": 1.8, "awakened_name": "Dark Dimension", "emoji": "🌑"},
        },
        "full_bonus": {"name": "Dark Awakening", "desc": "Kéo vào hư không", "damage_mult": 1.35},
    },
    "rubber": {
        "color": 0xE74C3C,
        "skills": {
            "Z": {"fragment": 400, "damage_mult": 1.5, "awakened_name": "Gomu Bazooka+", "emoji": "💥"},
            "X": {"fragment": 600, "damage_mult": 1.5, "awakened_name": "Gomu Rocket+", "emoji": "🚀"},
            "C": {"fragment": 800, "damage_mult": 1.6, "awakened_name": "Gear Second+", "emoji": "💨"},
            "V": {"fragment": 1200, "damage_mult": 2.0, "awakened_name": "Gear Fifth", "emoji": "🎈"},
        },
        "full_bonus": {"name": "Nika Awakening", "desc": "Sức mạnh Nika — biến mọi thứ thành cao su", "damage_mult": 1.4},
    },
    "magma": {
        "color": 0xE74C3C,
        "skills": {
            "Z": {"fragment": 500, "damage_mult": 1.5, "awakened_name": "Magma Bullet+", "emoji": "🔴"},
            "X": {"fragment": 700, "damage_mult": 1.5, "awakened_name": "Magma Rain+", "emoji": "🌧️"},
            "C": {"fragment": 900, "damage_mult": 1.6, "awakened_name": "Magma Fist+", "emoji": "👊"},
            "V": {"fragment": 1500, "damage_mult": 2.0, "awakened_name": "Meteor Volcano", "emoji": "☄️"},
        },
        "full_bonus": {"name": "Magma Awakening", "desc": "Mưa thiên thạch dung nham", "damage_mult": 1.5},
    },
    "quake": {
        "color": 0x7F8C8D,
        "skills": {
            "Z": {"fragment": 500, "damage_mult": 1.5, "awakened_name": "Shockwave+", "emoji": "🌊"},
            "X": {"fragment": 700, "damage_mult": 1.5, "awakened_name": "Quake Bubble+", "emoji": "🫧"},
            "C": {"fragment": 1000, "damage_mult": 1.6, "awakened_name": "Rupture+", "emoji": "💔"},
            "V": {"fragment": 1500, "damage_mult": 2.0, "awakened_name": "World Breaker", "emoji": "🌍"},
        },
        "full_bonus": {"name": "Quake Awakening", "desc": "Rạn nứt không gian", "damage_mult": 1.5},
    },
    "rumble": {
        "color": 0xF1C40F,
        "skills": {
            "Z": {"fragment": 700, "damage_mult": 1.5, "awakened_name": "Lightning Spear+", "emoji": "⚡"},
            "X": {"fragment": 900, "damage_mult": 1.5, "awakened_name": "Thunder Storm+", "emoji": "⛈️"},
            "C": {"fragment": 1200, "damage_mult": 1.6, "awakened_name": "Thunder Bird+", "emoji": "🐦"},
            "V": {"fragment": 1800, "damage_mult": 2.0, "awakened_name": "Thunder God", "emoji": "🌩️"},
        },
        "full_bonus": {"name": "Rumble Awakening", "desc": "Hoá thân thần sấm", "damage_mult": 1.6},
    },
    "buddha": {
        "color": 0xF39C12,
        "skills": {
            "Z": {"fragment": 700, "damage_mult": 1.5, "awakened_name": "Buddha Fist+", "emoji": "👊"},
            "X": {"fragment": 1000, "damage_mult": 1.5, "awakened_name": "Shockwave Palm+", "emoji": "✋"},
            "C": {"fragment": 1300, "damage_mult": 1.6, "awakened_name": "Golden Buddha+", "emoji": "🥇"},
            "V": {"fragment": 2000, "damage_mult": 2.0, "awakened_name": "Thousand Hands", "emoji": "🙏"},
        },
        "full_bonus": {"name": "Buddha Awakening", "desc": "Miễn nhiễm vật lý", "damage_mult": 1.6},
    },
    "venom": {
        "color": 0x27AE60,
        "skills": {
            "Z": {"fragment": 800, "damage_mult": 1.5, "awakened_name": "Venom Shot+", "emoji": "💚"},
            "X": {"fragment": 1100, "damage_mult": 1.5, "awakened_name": "Venom Fang+", "emoji": "🐍"},
            "C": {"fragment": 1400, "damage_mult": 1.6, "awakened_name": "Venom Web+", "emoji": "🕸️"},
            "V": {"fragment": 2200, "damage_mult": 2.0, "awakened_name": "Venom Demon", "emoji": "😈"},
        },
        "full_bonus": {"name": "Venom Awakening", "desc": "Hoá thân quỷ độc", "damage_mult": 1.65},
    },
    "dough": {
        "color": 0xE91E63,
        "skills": {
            "Z": {"fragment": 900, "damage_mult": 1.5, "awakened_name": "Dough Roll+", "emoji": "🥐"},
            "X": {"fragment": 1200, "damage_mult": 1.5, "awakened_name": "Dough Shot+", "emoji": "🎯"},
            "C": {"fragment": 1500, "damage_mult": 1.6, "awakened_name": "Baked Jail+", "emoji": "🍞"},
            "V": {"fragment": 2400, "damage_mult": 2.0, "awakened_name": "Dough Awakening", "emoji": "🍩"},
        },
        "full_bonus": {"name": "Dough Awakening", "desc": "Hồi máu liên tục", "damage_mult": 1.75},
    },
    "dragon": {
        "color": 0x27AE60,
        "skills": {
            "Z": {"fragment": 1000, "damage_mult": 1.5, "awakened_name": "Dragon Breath+", "emoji": "🔥"},
            "X": {"fragment": 1300, "damage_mult": 1.5, "awakened_name": "Dragon Cannon+", "emoji": "💥"},
            "C": {"fragment": 1700, "damage_mult": 1.6, "awakened_name": "Dragon Rush+", "emoji": "🐲"},
            "V": {"fragment": 2600, "damage_mult": 2.0, "awakened_name": "Dragon Transform", "emoji": "🐉"},
        },
        "full_bonus": {"name": "Dragon Awakening", "desc": "Hoá rồng khổng lồ", "damage_mult": 1.8},
    },
    "kitsune": {
        "color": 0xFF6B35,
        "skills": {
            "Z": {"fragment": 1500, "damage_mult": 1.5, "awakened_name": "Fire Fox+", "emoji": "🔥"},
            "X": {"fragment": 2000, "damage_mult": 1.5, "awakened_name": "Fox Illusion+", "emoji": "🌀"},
            "C": {"fragment": 2500, "damage_mult": 1.6, "awakened_name": "Nine Tails+", "emoji": "🦊"},
            "V": {"fragment": 3500, "damage_mult": 2.2, "awakened_name": "Kitsune Mode", "emoji": "🌟"},
        },
        "full_bonus": {"name": "Kitsune Awakening", "desc": "Cáo chín đuôi", "damage_mult": 2.0},
    },
    "leopard": {
        "color": 0xF39C12,
        "skills": {
            "Z": {"fragment": 1200, "damage_mult": 1.5, "awakened_name": "Leopard Dash+", "emoji": "💨"},
            "X": {"fragment": 1600, "damage_mult": 1.5, "awakened_name": "Fang Strike+", "emoji": "🦷"},
            "C": {"fragment": 2000, "damage_mult": 1.6, "awakened_name": "Roar+", "emoji": "📢"},
            "V": {"fragment": 3000, "damage_mult": 2.2, "awakened_name": "Leopard Awakening", "emoji": "🐆"},
        },
        "full_bonus": {"name": "Leopard Awakening", "desc": "Tốc độ ánh sáng", "damage_mult": 1.9},
    },
    "gas": {
        "color": 0x27AE60,
        "skills": {
            "Z": {"fragment": 1700, "damage_mult": 1.5, "awakened_name": "Gas Cloud+", "emoji": "☁️"},
            "X": {"fragment": 2200, "damage_mult": 1.5, "awakened_name": "Toxic Shot+", "emoji": "🧪"},
            "C": {"fragment": 2800, "damage_mult": 1.6, "awakened_name": "Gas Prison+", "emoji": "🔒"},
            "V": {"fragment": 4000, "damage_mult": 2.2, "awakened_name": "Gas Apocalypse", "emoji": "💨"},
        },
        "full_bonus": {"name": "Gas Awakening", "desc": "Khí độc hủy diệt", "damage_mult": 2.05},
    },
    "dough_king": {
        "color": 0xFFD700,
        "skills": {
            "Z": {"fragment": 1800, "damage_mult": 1.6, "awakened_name": "King Roll", "emoji": "🥐"},
            "X": {"fragment": 2300, "damage_mult": 1.6, "awakened_name": "King Shot", "emoji": "👑"},
            "C": {"fragment": 2900, "damage_mult": 1.7, "awakened_name": "King Jail", "emoji": "⛓️"},
            "V": {"fragment": 4500, "damage_mult": 2.5, "awakened_name": "King's Awakening", "emoji": "🌟"},
        },
        "full_bonus": {"name": "King Awakening", "desc": "Bất khả chiến bại", "damage_mult": 2.2},
    },
}

RAID_BOSSES = {
    "raid_bandit": {"name": "Bandit King", "emoji": "🏴‍☠️", "tier": 1, "hp": 3000, "damage": 50, "level_req": 50, "cooldown": 300, "reward_fragment": (20, 40), "reward_coin": (100000, 200000), "reward_xp": (50000, 100000), "color": 0x95A5A6},
    "raid_yeti": {"name": "Yeti", "emoji": "❄️", "tier": 1, "hp": 5000, "damage": 80, "level_req": 100, "cooldown": 300, "reward_fragment": (35, 60), "reward_coin": (200000, 350000), "reward_xp": (100000, 200000), "color": 0x3498DB},
    "raid_dragon": {"name": "Raid Dragon", "emoji": "🐉", "tier": 2, "hp": 15000, "damage": 200, "level_req": 300, "cooldown": 600, "reward_fragment": (80, 150), "reward_coin": (500000, 800000), "reward_xp": (500000, 1000000), "color": 0x27AE60},
    "raid_cyborg": {"name": "Raid Cyborg", "emoji": "🦾", "tier": 2, "hp": 20000, "damage": 250, "level_req": 400, "cooldown": 600, "reward_fragment": (100, 200), "reward_coin": (800000, 1200000), "reward_xp": (800000, 1500000), "color": 0x7F8C8D},
    "raid_dough_king": {"name": "Raid Dough King", "emoji": "👑", "tier": 3, "hp": 50000, "damage": 500, "level_req": 700, "cooldown": 900, "reward_fragment": (200, 400), "reward_coin": (2000000, 3000000), "reward_xp": (3000000, 5000000), "color": 0xE91E63},
    "raid_shadow": {"name": "Raid Shadow", "emoji": "🌑", "tier": 3, "hp": 70000, "damage": 700, "level_req": 900, "cooldown": 900, "reward_fragment": (300, 550), "reward_coin": (3000000, 5000000), "reward_xp": (5000000, 8000000), "color": 0x2C3E50},
    "raid_kitsune": {"name": "Raid Kitsune", "emoji": "🦊", "tier": 4, "hp": 150000, "damage": 1200, "level_req": 1200, "cooldown": 1200, "reward_fragment": (500, 900), "reward_coin": (8000000, 12000000), "reward_xp": (15000000, 25000000), "color": 0xFF6B35},
    "raid_god": {"name": "Raid God", "emoji": "🌟", "tier": 5, "hp": 500000, "damage": 3000, "level_req": 2000, "cooldown": 1800, "reward_fragment": (1500, 3000), "reward_coin": (50000000, 80000000), "reward_xp": (100000000, 200000000), "color": 0xFFD700},
}

RACES = {
    "human": {"name": "Human", "emoji": "🧑", "color": 0x95A5A6, "v1": {"name": "Human V1", "bonus": {"melee": 10, "defense": 10}}},
    "cyborg": {"name": "Cyborg", "emoji": "🦾", "color": 0x7F8C8D, "v1": {"name": "Cyborg V1", "bonus": {"gun": 15, "defense": 10}}},
    "skypiea": {"name": "Skypiea", "emoji": "☁️", "color": 0x3498DB, "v1": {"name": "Skypiea V1", "bonus": {"fruit": 15, "melee": 5}}},
    "fishman": {"name": "Fishman", "emoji": "🐟", "color": 0x1ABC9C, "v1": {"name": "Fishman V1", "bonus": {"melee": 20, "defense": 15}}},
    "ghoul": {"name": "Ghoul", "emoji": "💀", "color": 0x2C3E50, "v1": {"name": "Ghoul V1", "bonus": {"sword": 20, "melee": 10}}},
    "mink": {"name": "Mink", "emoji": "🐾", "color": 0xF39C12, "v1": {"name": "Mink V1", "bonus": {"sword": 15, "gun": 15}}},
}
RACE_V4_COST = {"coin": 10_000_000, "fragments": 5_000, "race_fragments": 500}

def get_race_v4_bonus(race_key):
    race = RACES.get(race_key)
    if not race:
        return {}
    return {k: v * 5 for k, v in race["v1"]["bonus"].items()}

# ══════════════════════════════════════════════════════════════════
# 🎯 AWAKENING HELPERS
# ══════════════════════════════════════════════════════════════════
def is_skill_awakened(player, fruit_key, skill_key):
    awakened = player.get("awakened_skills", {})
    return skill_key in awakened.get(fruit_key, [])

def is_fruit_fully_awakened(player, fruit_key):
    awakened = player.get("awakened_skills", {}).get(fruit_key, [])
    return all(s in awakened for s in ["Z", "X", "C", "V"])

def get_skill_damage_mult(player, fruit_key, skill_key):
    info = AWAKENING_SKILLS.get(fruit_key)
    if not info:
        return 1.0
    sk = info["skills"].get(skill_key)
    if not sk:
        return 1.0
    if is_skill_awakened(player, fruit_key, skill_key):
        return sk["damage_mult"]
    return 1.0

def get_fruit_damage_multiplier(player, fruit_key):
    if not fruit_key:
        return 1.0
    info = AWAKENING_SKILLS.get(fruit_key)
    if not info:
        return 1.0
    awakened = player.get("awakened_skills", {}).get(fruit_key, [])
    if not awakened:
        return 1.0
    if is_fruit_fully_awakened(player, fruit_key):
        return info["full_bonus"]["damage_mult"]
    return 1.0 + 0.1 * len(awakened)
# ══════════════════════════════════════════════════════════════════
# 💾 STORAGE
# ══════════════════════════════════════════════════════════════════
player_data = {}

def normalize_player_loadout(player):
    old_inv = player.get("inventory", {}) or {}
    player["inventory"] = {"fruits": list(old_inv.get("fruits", []))}
    for key in ("equipped_sword", "equipped_gun", "equipped_melee", "equipped_accessory"): player.pop(key, None)
    base=player.get("base_stats",{}) or {}; stats=player.get("stats",{}) or {}
    player["base_stats"]={"defense":base.get("defense",1),"fruit":base.get("fruit",1)}
    player["stats"]={"defense":stats.get("defense",1),"fruit":stats.get("fruit",1)}
    mastery=player.get("mastery",{}) or {}; player["mastery"]={"trái":mastery.get("trái",0)}
    recalc_stats(player); return player

active_battles = {}
user_in_battle = {}
active_raids = {}
battle_cooldowns = {}

def load_leaderboard_config():
    if os.path.exists(LEADERBOARD_CONFIG_FILE):
        try:
            with open(LEADERBOARD_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_leaderboard_config():
    with open(LEADERBOARD_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(leaderboard_config, f, indent=2, ensure_ascii=False)

def load_sell_config():
    if os.path.exists(SELL_CONFIG_FILE):
        try:
            with open(SELL_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_sell_config():
    with open(SELL_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(sell_config, f, indent=2, ensure_ascii=False)

leaderboard_config = load_leaderboard_config()
sell_config = load_sell_config()

# ══════════════════════════════════════════════════════════════════
# 🧮 HELPERS
# ══════════════════════════════════════════════════════════════════
def format_number(n):
    if n >= 1_000_000_000_000: return f"{n / 1_000_000_000_000:.1f}T"
    if n >= 1_000_000_000: return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000: return f"{n / 1_000_000:.1f}M"
    if n >= 1_000: return f"{n / 1_000:.1f}K"
    return str(n)

def format_bounty(b):
    return f"{format_number(b)} Berries"

def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}p{s}s" if m else f"{s}s"

def xp_to_level(level):
    if level <= 1: return 0
    return int(50 * (level ** 2) * (level / 100 + 1))

def calc_level(xp):
    if xp < 0: return 1
    lo, hi = 1, MAX_LEVEL
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if xp_to_level(mid) <= xp: lo = mid
        else: hi = mid - 1
    return lo

def xp_progress_in_level(xp):
    level = calc_level(xp)
    cur = xp_to_level(level)
    nxt = xp_to_level(level + 1)
    return xp - cur, nxt - cur

def calc_max_hp(player):
    return 100 + player["stats"]["defense"] * 20

def get_stat_damage(player, weapon):
    if weapon == "trái": return player["stats"]["fruit"] * 2
    return 0

def get_title_by_level(level):
    for t in reversed(list(TITLES.values())):
        if level >= t["req"]: return f"{t['emoji']} {t['name']}"
    return "🌱 Người Mới"

def get_player_title(player):
    level = player["level"]
    if player.get("pvp_wins", 0) >= 100: return "pvp_king"
    if player.get("raids_cleared", 0) >= 50: return "raid_master"
    for key in ["legend", "king_pirate", "emperor", "admiral", "warlord",
                "supernova", "pirate", "rookie"]:
        if level >= TITLES[key]["req"]: return key
    return None

def get_title_display(player):
    t = get_player_title(player)
    if not t: return ""
    info = TITLES[t]
    return f"{info['emoji']} **{info['name']}**"

def get_bounty_rank(bounty):
    for r in BOUNTY_RANKS:
        if r["min"] <= bounty < r["max"]: return r
    return BOUNTY_RANKS[-1]

def recalc_stats(player):
    player["stats"] = dict(player["base_stats"])
    race_key = player.get("race", "human")
    race_level = player.get("race_level", 1)
    race = RACES.get(race_key)
    if race:
        bonuses = get_race_v4_bonus(race_key) if race_level >= 4 else race["v1"]["bonus"]
        for stat, val in bonuses.items():
            if stat in player["stats"]: player["stats"][stat] += val
    player["current_hp"] = calc_max_hp(player)

def update_stat_points(player):
    cur = min(player["level"], MAX_LEVEL)
    last = player.get("last_level", 1)
    if cur > last:
        gained = (cur - last) * 3
        player["stat_points"] += gained
        player["last_level"] = cur
        player["level"] = cur
        return gained
    return 0

def create_player(faction):
    return {
        "faction": faction, "xp": 0, "coin": 0, "level": 1,
        "free_random_used": False,
        "base_stats": {"defense": 1, "fruit": 1},
        "stats": {"defense": 1, "fruit": 1},
        "stat_points": 0, "last_level": 1, "current_hp": 120,
        "equipped_fruit": None,
        "fragments": 0, "awakened_skills": {},
        "bounty": 0, "bounty_history": [],
        "pvp_wins": 0, "pvp_losses": 0, "battle_wins": 0, "battle_losses": 0,
        "bounty_stolen": 0, "bounty_lost": 0,
        "boss_cooldowns": {}, "bosses_killed": 0, "raid_cooldowns": {}, "raids_cleared": 0,
        "total_kills": 0, "title": None, "bio": "", "created_at": time.time(), "playtime": 0,
        "race": "human", "race_level": 1, "race_fragments": 0,
        "current_sea": 1, "current_island": None, "quest_progress": 0, "quest_weapon": None,
        "last_fight": 0, "unlocked_seas": [1], "mastery": {"trái": 0},
        "inventory": {"fruits": []},
    }

def calc_power_score(player):
    s = player["stats"]
    stat_score = s["defense"]*2 + s["fruit"]*3
    level_score = player["level"] * 10
    awaken_score = sum(len(v) for v in player.get("awakened_skills", {}).values()) * 200
    inv_score = sum(len(v) for v in player.get("inventory", {}).values()) * 20
    pvp_score = player.get("pvp_wins", 0) * 50
    frag_score = player.get("fragments", 0) * 0.1
    return int(stat_score + level_score + awaken_score + inv_score + pvp_score + frag_score)

def get_top_players(limit=10):
    ranked = [(uid, p, calc_power_score(p)) for uid, p in player_data.items()]
    ranked.sort(key=lambda x: x[2], reverse=True)
    return ranked[:limit]

def add_bounty(player, amount, reason="", cap=10_000_000_000):
    old = player.get("bounty", 0)
    new = min(max(0, old + amount), cap)
    actual = new - old
    player["bounty"] = new
    if "bounty_history" not in player: player["bounty_history"] = []
    player["bounty_history"].append({"amount": actual, "reason": reason, "time": time.time()})
    player["bounty_history"] = player["bounty_history"][-20:]
    return actual

# ══════════════════════════════════════════════════════════════════
# ⚔️ COMBAT
# ══════════════════════════════════════════════════════════════════
def simulate_fight(player, sea, island_key, weapon, skill_index=0):
    island = SEA_DATA[sea]["islands"][island_key]
    skill = SKILLS[weapon][skill_index]
    monster = random.choice(island["monsters"])

    stat_dmg = get_stat_damage(player, weapon)
    mastery_bonus = player["mastery"].get(weapon, 0) * 0.3
    player_dmg = skill["damage"] + stat_dmg + mastery_bonus + player["level"] * 2 + random.randint(-5, 10)

    if weapon == "trái":
        equipped = player.get("equipped_fruit")
        if equipped:
            skill_keys = ["M1", "Z", "X", "C", "V"]
            sk_key = skill_keys[skill_index] if skill_index < len(skill_keys) else "M1"
            player_dmg *= get_skill_damage_mult(player, equipped, sk_key)

    win = player_dmg >= monster["hp"]
    result = {"win": win, "monster": monster["name"], "monster_hp": monster["hp"],
              "damage": int(player_dmg), "coin": 0, "xp": 0, "bounty_gain": 0, "stat_points_gained": 0}

    if win:
        result["coin"] = monster["coin"]
        result["xp"] = monster["xp"]
        player["coin"] += monster["coin"]
        player["xp"] += monster["xp"]
        new_level = calc_level(player["xp"])
        if new_level > MAX_LEVEL:
            new_level = MAX_LEVEL
            player["xp"] = xp_to_level(MAX_LEVEL)
        player["level"] = new_level
        result["stat_points_gained"] = update_stat_points(player)
        bounty_gain = max(1, monster["hp"] // 100) * {1: 1, 2: 10, 3: 100}.get(sea, 1)
        result["bounty_gain"] = add_bounty(player, bounty_gain, f"Giết {monster['name']}")
        player["total_kills"] = player.get("total_kills", 0) + 1
        player["quest_progress"] = player.get("quest_progress", 0) + 1
        player["mastery"][weapon] = player["mastery"].get(weapon, 0) + random.randint(1, 3)
    return result

def simulate_boss(player, sea, island_key, weapon="trái", skill_index=4):
    island = SEA_DATA[sea]["islands"][island_key]
    boss = island.get("boss")
    if not boss: return None

    stat_dmg = get_stat_damage(player, weapon)
    mastery_bonus = player["mastery"].get(weapon, 0) * 0.5
    player_dmg = 100 + stat_dmg + mastery_bonus + player["level"] * 5 + random.randint(-10, 30)

    if weapon == "trái":
        equipped = player.get("equipped_fruit")
        if equipped:
            player_dmg *= get_skill_damage_mult(player, equipped, "V")

    win = player_dmg >= boss["hp"]
    result = {"win": win, "boss": boss["name"], "boss_hp": boss["hp"],
              "damage": int(player_dmg), "coin": 0, "xp": 0, "bounty_gain": 0, "stat_points_gained": 0}

    if win:
        result["coin"] = boss["coin"]
        result["xp"] = boss["xp"]
        player["coin"] += boss["coin"]
        player["xp"] += boss["xp"]
        new_level = calc_level(player["xp"])
        if new_level > MAX_LEVEL:
            new_level = MAX_LEVEL
            player["xp"] = xp_to_level(MAX_LEVEL)
        player["level"] = new_level
        result["stat_points_gained"] = update_stat_points(player)
        bounty_gain = max(100, boss["hp"] // 10) * {1: 1, 2: 10, 3: 100}.get(sea, 1)
        result["bounty_gain"] = add_bounty(player, bounty_gain, f"Hạ {boss['name']}")
        player["bosses_killed"] = player.get("bosses_killed", 0) + 1
    return result
# ══════════════════════════════════════════════════════════════════
# 🖼️ EMBEDS CƠ BẢN
# ══════════════════════════════════════════════════════════════════
def get_hourly_fruit_stock(sea=1):
    """Kho trái thay đổi tự động mỗi 60 phút, dùng chung theo từng Sea."""
    items = {k: v for k, v in SHOP_DATA["fruits"].items() if v.get("sea", 1) <= sea}
    if not items:
        return []
    hour_key = int(time.time() // 3600)
    rng = random.Random(hour_key + sea * 1000003)
    keys = list(items.keys())
    count = min(5, len(keys))
    return rng.sample(keys, count)

def build_hourly_dealer_embed(player=None):
    sea = player.get("current_sea", 1) if player else 1
    stock = get_hourly_fruit_stock(sea)
    lines = []
    for key in stock:
        item = SHOP_DATA["fruits"][key]
        owned = player and key in player.get("inventory", {}).get("fruits", [])
        mark = "✅" if owned else "🛒"
        lines.append(f"{mark} {item['emoji']} **{item['name']}** — `{item['price']:,}` 💰 • {item['rarity']}")
    now = int(time.time())
    next_hour = ((now // 3600) + 1) * 3600
    remain = max(0, next_hour - now)
    h, rem = divmod(remain, 3600)
    m, sec = divmod(rem, 60)
    timer = f"{m:02d}:{sec:02d}" if h == 0 else f"{h:02d}:{m:02d}:{sec:02d}"
    coin_line = f"\n💰 Coin: `{player['coin']:,}`" if player else ""
    return discord.Embed(
        title="🍎 Blox Fruits Dealer • Trái Ác Quỷ",
        description=(f"**Kho hiện tại (đổi sau `{timer}`):**{coin_line}\n\n" + "\n".join(lines) +
                     "\n\n🔄 Mỗi **1 giờ** hệ thống random lại 5 trái để bán."),
        color=0xFFD700
    )

def build_onepiece_help_embed():
    return discord.Embed(
        title="📖 One Piece • Hướng Dẫn",
        description=(
            "**Các chức năng trong bảng /onepiece:**\n\n"
            "👤 **Profile** — Xem hồ sơ nhân vật\n"
            "💰 **Bounty** — Xem truy nã và BXH bounty\n"
            "⚔️ **PvP** — Thách đấu người chơi khác\n"
            "🎯 **Battle** — Xem Battle Bounty\n"
            "👹 **Raid** — Đánh boss raid\n"
            "🏆 **BXH** — Xem bảng xếp hạng\n"
            "🍎 **Sell** — Mở Dealer trái, stock đổi mỗi 1 giờ\n"
            "🛒 **Shop** — Mua trái đang được bán\n"
            "🌾 **Farm** — Làm quest và đánh quái\n"
            "🎲 **Random** — Gacha trái\n"
            "✨ **Awakening** — Thức tỉnh trái\n\n"
            "💡 Tất cả thao tác được thực hiện bằng nút, không cần gõ các lệnh phụ."
        ),
        color=0x3498DB
    )

def build_main_embed():
    stock = get_hourly_fruit_stock(1)
    stock_lines = []
    for key in stock:
        item = SHOP_DATA["fruits"][key]
        stock_lines.append(f"{item['emoji']} **{item['name']}** — `{item['price']:,}` 💰")
    return discord.Embed(
        title="🏴‍☠️ One Piece • BirthdayTime",
        description=(
            "Bấm **Tham Gia Game** để bắt đầu.\n\n"
            "**🎮 Chức năng:** Profile • Bounty • PvP • Battle • Raid • BXH • Dealer\n\n"
            "🍎 **Dealer trái hiện tại** *(đổi mỗi 1 giờ)*\n" + "\n".join(stock_lines) +
            "\n\n💡 Các chức năng phụ đều nằm trong bảng này, không cần lệnh riêng.\n\u200b"
        ),
        color=0xFFD700
    )

def build_faction_embed():
    return discord.Embed(
        title="🏴‍☠️ CHỌN PHE CỦA BẠN 🏴‍☠️",
        description="Hãy chọn 1 trong 2 phe dưới đây!\n\n\u200b\n\u200b",
        color=0x1ABC9C
    )

def build_game_embed(faction):
    color = 0xE74C3C if "Hải Tặc" in faction else 0x3498DB
    return discord.Embed(
        title="🏴‍☠️ One Piece • BirthdayTime",
        description=f"Chúc mừng bạn đã chọn phe **{faction}**!\n\n\u200b\n\u200b",
        color=color
    )

def build_farm_embed(player):
    ik = player.get("current_island")
    island_line = ""
    if ik:
        try:
            island = SEA_DATA[player["current_sea"]]["islands"].get(ik)
            if island:
                progress = player.get("quest_progress", 0)
                island_line = f"📍 **Đảo:** {island['emoji']} **{island['name']}** (`{progress}/{island['quest_kill']}`)\n"
        except: pass
    if not island_line:
        island_line = "📍 **Đảo:** *Chưa chọn — nhấn Islands!*\n"

    points = player.get("stat_points", 0)
    point_line = f"\n🔴 **`{points}` điểm Stats chưa dùng!**" if points > 0 else ""

    return discord.Embed(
        title="🌾 Farm • Nhiệm Vụ",
        description=(
            f"Nhấn **Quest**, **Islands** hoặc **Start**!\n\n"
            f"{island_line}"
            f"⭐ **XP:** `{player['xp']}` | 📊 **Level:** `{player['level']}`\n"
            f"💰 **Coin:** `{player['coin']}`"
            f"{point_line}\n\u200b"
        ),
        color=0xFF6B35 if points > 0 else 0x2ECC71
    )

def build_stats_embed(player):
    stats = player["stats"]
    base = player["base_stats"]
    points = player["stat_points"]
    max_hp = calc_max_hp(player)

    lines = []
    for k, info in STAT_INFO.items():
        v = stats[k]
        bonus = v - base[k]
        extra = f" *(+{bonus})*" if bonus > 0 else ""
        lines.append(f"{info['emoji']} **{info['name']}:** `{v}`{extra}")

    return discord.Embed(
        title="💪 Tăng Cường Chỉ Số",
        description=(
            f"📊 **Level:** `{player['level']}`\n"
            f"🎯 **Điểm còn lại:** `{points}`\n"
            f"❤️ **HP tối đa:** `{max_hp}`\n\n"
            "**Chỉ số hiện tại:**\n" + "\n".join(lines) +
            "\n\n⚠️ Mỗi level = **3 điểm**. 1 điểm = +1 chỉ số.\n\u200b"
        ),
        color=0xFF6B35 if points > 0 else 0x95A5A6
    )

# ══════════════════════════════════════════════════════════════════
# 🎮 JOIN GAME VIEW
# ══════════════════════════════════════════════════════════════════
class PvPModal(discord.ui.Modal, title="⚔️ Thách Đấu PvP"):
    target = discord.ui.TextInput(
        label="ID hoặc @mention người chơi",
        placeholder="Ví dụ: 123456789012345678 hoặc @Tên",
        required=True,
        max_length=40
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.target.value).strip().replace("<@", "").replace("<@!", "").replace(">", "")
        try:
            target_id = int(raw)
        except ValueError:
            await interaction.response.send_message("❌ Hãy nhập ID Discord hoặc @mention hợp lệ.", ephemeral=True)
            return
        if target_id == interaction.user.id:
            await interaction.response.send_message("❌ Không thể tự thách đấu chính mình.", ephemeral=True)
            return
        target = bot.get_user(target_id)
        if not target or target_id not in player_data:
            await interaction.response.send_message("❌ Người chơi chưa tham gia One Piece hoặc không tìm thấy.", ephemeral=True)
            return
        if interaction.user.id not in player_data:
            await interaction.response.send_message("❌ Bạn chưa tham gia One Piece. Hãy bấm Tham Gia Game trước.", ephemeral=True)
            return
        await interaction.response.send_message(
            content=target.mention,
            embed=build_battle_invite_embed(interaction.user, target),
            view=PvPInviteView(interaction.user.id, target.id)
        )

class OnePieceHubView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _need_player(self, interaction):
        if interaction.user.id not in player_data:
            await interaction.response.send_message("❌ Bạn chưa tham gia One Piece. Hãy bấm **Tham Gia Game** trước.", ephemeral=True)
            return None
        return player_data[interaction.user.id]

    @discord.ui.button(label="Tham Gia Game", emoji="⚔️", style=discord.ButtonStyle.success, row=0)
    async def join(self, interaction, button):
        if interaction.user.id in player_data:
            p = normalize_player_loadout(player_data[interaction.user.id])
            faction = p.get("faction", "🏴‍☠️ Hải Tặc")
            await interaction.response.send_message(embed=build_game_embed(faction), view=GameMenuView(faction, interaction.user.id), ephemeral=True)
            return
        await interaction.response.send_message(embed=build_faction_embed(), view=ChooseFactionView(self), ephemeral=True)

    @discord.ui.button(label="Profile", emoji="👤", style=discord.ButtonStyle.primary, row=0)
    async def profile_btn(self, interaction, button):
        p = await self._need_player(interaction)
        if p is None: return
        await interaction.response.send_message(embed=build_profile_embed(p, interaction.user), view=ProfileView(interaction.user.id), ephemeral=True)

    @discord.ui.button(label="Bounty", emoji="💰", style=discord.ButtonStyle.primary, row=0)
    async def bounty_btn(self, interaction, button):
        p = await self._need_player(interaction)
        if p is None: return
        await interaction.response.send_message(embed=build_bounty_embed(interaction.user, p), view=BountyView(interaction.user.id), ephemeral=True)

    @discord.ui.button(label="PvP", emoji="⚔️", style=discord.ButtonStyle.danger, row=0)
    async def pvp_btn(self, interaction, button):
        p = await self._need_player(interaction)
        if p is None: return
        await interaction.response.send_modal(PvPModal())

    @discord.ui.button(label="Battle", emoji="🎯", style=discord.ButtonStyle.danger, row=0)
    async def battle_btn(self, interaction, button):
        p = await self._need_player(interaction)
        if p is None: return
        await interaction.response.send_message(embed=build_battle_bounty_embed(p, interaction.user), view=BattleBountyView(interaction.user.id), ephemeral=True)

    @discord.ui.button(label="Raid", emoji="👹", style=discord.ButtonStyle.danger, row=1)
    async def raid_btn(self, interaction, button):
        p = await self._need_player(interaction)
        if p is None: return
        await interaction.response.send_message(embed=build_raid_menu_embed(p), view=RaidView(interaction.user.id), ephemeral=True)

    @discord.ui.button(label="BXH Level", emoji="🏆", style=discord.ButtonStyle.primary, row=1)
    async def lb_btn(self, interaction, button):
        ranked = sorted(player_data.items(), key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)), reverse=True)[:10]
        lines=[]
        for idx,(uid,p) in enumerate(ranked,1):
            u=bot.get_user(uid); name=u.display_name if u else f"User {uid}"
            medal=["🥇","🥈","🥉"][idx-1] if idx<=3 else f"`{idx}.`"
            lines.append(f"{medal} **{name}** — Lv.`{p.get('level',0)}` • XP `{p.get('xp',0):,}`")
        await interaction.response.send_message(embed=discord.Embed(title="🏆 BXH Level",description="\n".join(lines) or "*Chưa có người chơi.*",color=0xFFD700),ephemeral=True)

    @discord.ui.button(label="BXH Bounty", emoji="💎", style=discord.ButtonStyle.primary, row=1)
    async def bounty_lb_btn(self, interaction, button):
        ranked=sorted(player_data.items(), key=lambda x:x[1].get("bounty",0), reverse=True)[:10]
        lines=[]
        for idx,(uid,p) in enumerate(ranked,1):
            u=bot.get_user(uid); name=u.display_name if u else f"User {uid}"
            medal=["🥇","🥈","🥉"][idx-1] if idx<=3 else f"`{idx}.`"
            lines.append(f"{medal} **{name}** — 💰 `{format_bounty(p.get('bounty',0))}`")
        await interaction.response.send_message(embed=discord.Embed(title="💰 BXH Bounty",description="\n".join(lines) or "*Chưa có người chơi.*",color=0xFFD700),ephemeral=True)

    @discord.ui.button(label="Sell", emoji="🍎", style=discord.ButtonStyle.success, row=1)
    async def dealer_btn(self, interaction, button):
        p = await self._need_player(interaction)
        if p is None: return
        await interaction.response.send_message(embed=build_hourly_dealer_embed(p), view=ShopView(interaction.user.id), ephemeral=True)

class JoinGameView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.players = {}

    @discord.ui.button(label="Tham Gia Game", emoji="⚔️", style=discord.ButtonStyle.primary)
    async def join(self, interaction, button):
        # Nếu người chơi đã tham gia, mở lại bảng game thay vì báo lỗi.
        if interaction.user.id in player_data:
            player = normalize_player_loadout(player_data[interaction.user.id])
            faction = player.get("faction", "🏴‍☠️ Hải Tặc")
            self.players[interaction.user.id] = {"user": interaction.user, "faction": faction}
            await interaction.response.send_message(
                embed=build_game_embed(faction),
                view=GameMenuView(faction, interaction.user.id),
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=build_faction_embed(),
            view=ChooseFactionView(self),
            ephemeral=True
        )

class ChooseFactionView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=120)
        self.main_view = main_view

    @discord.ui.button(label="Hải Tặc", emoji="🏴‍☠️", style=discord.ButtonStyle.danger)
    async def pirate(self, i, b): await self._pick(i, "🏴‍☠️ Hải Tặc")

    @discord.ui.button(label="Hải Quân", emoji="⚓", style=discord.ButtonStyle.primary)
    async def marine(self, i, b): await self._pick(i, "⚓ Hải Quân")

    async def _pick(self, interaction, faction):
        user = interaction.user
        # Tránh tạo lại nhân vật nếu người chơi bấm chọn phe nhiều lần.
        if user.id in player_data:
            player = normalize_player_loadout(player_data[user.id])
            faction = player.get("faction", faction)
            self.main_view.players[user.id] = {"user": user, "faction": faction}
            await interaction.response.edit_message(
                embed=build_game_embed(faction),
                view=GameMenuView(faction, user.id)
            )
            return
        player_data[user.id] = create_player(faction)
        self.main_view.players[user.id] = {"user": user, "faction": faction}
        recalc_stats(player_data[user.id])
        player = player_data[user.id]
        # Người chơi mới nhận đúng 1 lượt Random trái miễn phí.
        free_result = roll_fruit(player.get("current_sea", 1))
        free_new = give_fruits_to_player(player, [free_result] if free_result else [])
        player["free_random_used"] = True
        if free_result:
            fruit = SHOP_DATA["fruits"].get(free_result, {})
            free_embed = build_gacha_result_embed([free_result], player, free_new, free=True)
            await interaction.response.edit_message(embed=free_embed, view=GameMenuView(faction, user.id))
        else:
            await interaction.response.edit_message(
                embed=build_game_embed(faction),
                view=GameMenuView(faction, user.id)
            )

# ══════════════════════════════════════════════════════════════════
# 🎮 GAME MENU (4 nút chính)
# ══════════════════════════════════════════════════════════════════
class GameMenuView(discord.ui.View):
    def __init__(self, faction, user_id):
        super().__init__(timeout=None)
        self.faction = faction
        self.user_id = user_id

    @discord.ui.button(label="Farm", emoji="🌾", style=discord.ButtonStyle.success, row=0)
    async def farm(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        player = normalize_player_loadout(player_data.setdefault(self.user_id, create_player(self.faction)))
        await interaction.response.edit_message(
            embed=build_farm_embed(player),
            view=FarmView(self.user_id)
        )

    @discord.ui.button(label="Shop", emoji="🛒", style=discord.ButtonStyle.primary, row=0)
    async def shop(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_shop_embed(player_data[self.user_id], "fruits"),
            view=ShopView(self.user_id, "fruits")
        )

    @discord.ui.button(label="Random", emoji="🎲", style=discord.ButtonStyle.danger, row=0)
    async def random_fruit(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_gacha_embed(player_data[self.user_id]),
            view=GachaView(self.user_id)
        )

    @discord.ui.button(label="Awakening", emoji="✨", style=discord.ButtonStyle.primary, row=0)
    async def awakening(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_awakening_embed(player_data[self.user_id], interaction.user),
            view=AwakeningView(self.user_id)
        )

# ══════════════════════════════════════════════════════════════════
# 🌾 FARM VIEW
# ══════════════════════════════════════════════════════════════════
class FarmView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id

    @discord.ui.button(label="Quest", emoji="📜", style=discord.ButtonStyle.success, row=0)
    async def quest(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        p = player_data[self.user_id]
        ik = p.get("current_island") or list(SEA_DATA[p["current_sea"]]["islands"].keys())[0]
        p["current_island"] = ik
        await interaction.response.edit_message(
            embed=build_island_quest_embed(p, p["current_sea"], ik),
            view=IslandQuestView(self.user_id, p["current_sea"], ik)
        )

    @discord.ui.button(label="Islands", emoji="🏝️", style=discord.ButtonStyle.primary, row=0)
    async def islands(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        p = player_data[self.user_id]
        await interaction.response.edit_message(
            embed=build_island_list_embed(p, p["current_sea"]),
            view=IslandListView(self.user_id, p["current_sea"])
        )

    @discord.ui.button(label="Start", emoji="▶️", style=discord.ButtonStyle.primary, row=0)
    async def start(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_stats_embed(player_data[self.user_id]),
            view=StatsView(self.user_id)
        )

    @discord.ui.button(label="Profile", emoji="👤", style=discord.ButtonStyle.primary, row=0)
    async def profile(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        user = bot.get_user(self.user_id)
        await interaction.response.edit_message(
            embed=build_profile_embed(player_data[self.user_id], user),
            view=ProfileView(self.user_id)
        )

    @discord.ui.button(label="Inventory", emoji="🎒", style=discord.ButtonStyle.primary, row=1)
    async def inventory(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_inventory_embed(player_data[self.user_id], "fruits"),
            view=InventoryView(self.user_id, "fruits")
        )

    @discord.ui.button(label="Raid", emoji="👹", style=discord.ButtonStyle.danger, row=1)
    async def raid(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_raid_menu_embed(player_data[self.user_id]),
            view=RaidView(self.user_id)
        )

    @discord.ui.button(label="Bounty", emoji="💰", style=discord.ButtonStyle.primary, row=1)
    async def bounty(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        user = bot.get_user(self.user_id)
        await interaction.response.edit_message(
            embed=build_bounty_embed(user, player_data[self.user_id]),
            view=BountyView(self.user_id)
        )

    @discord.ui.button(label="Exit", emoji="🚪", style=discord.ButtonStyle.secondary, row=1)
    async def exit(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        for c in self.children: c.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(title="🚪 Đã Thoát Farm", description="Hẹn gặp lại!", color=0x95A5A6),
            view=self
        )

# ══════════════════════════════════════════════════════════════════
# 💪 STATS VIEW
# ══════════════════════════════════════════════════════════════════
class StatsView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180); self.user_id = user_id
    @discord.ui.button(label="Defense +1", emoji="🛡️", style=discord.ButtonStyle.primary, row=0)
    async def d(self, i, b): await self._up(i, "defense")
    @discord.ui.button(label="Fruit +1", emoji="🍎", style=discord.ButtonStyle.success, row=0)
    async def f(self, i, b): await self._up(i, "fruit")
    @discord.ui.button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, i, b):
        if i.user.id != self.user_id: await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]), view=FarmView(self.user_id))
    async def _up(self, interaction, stat):
        if interaction.user.id != self.user_id: await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        p = player_data[self.user_id]
        if p["stat_points"] <= 0: await interaction.response.send_message("❌ Hết điểm! Lên level để nhận thêm.", ephemeral=True); return
        p["base_stats"][stat] += 1; p["stat_points"] -= 1; recalc_stats(p)
        await interaction.response.edit_message(embed=build_stats_embed(p), view=StatsView(self.user_id))

# ══════════════════════════════════════════════════════════════════
# 👤 PROFILE VIEW
# ══════════════════════════════════════════════════════════════════
class ProfileView(discord.ui.View):
    def __init__(self, user_id, viewer_id=None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.viewer_id = viewer_id or user_id

    @discord.ui.button(label="Đổi Bio", emoji="📝", style=discord.ButtonStyle.primary)
    async def bio(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải profile bạn!", ephemeral=True); return
        await interaction.response.send_modal(BioModal(self.user_id))

    @discord.ui.button(label="Tộc V4", emoji="👑", style=discord.ButtonStyle.danger)
    async def race(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ Không phải profile bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_race_embed(player_data[self.user_id]),
            view=RaceView(self.user_id)
        )

    @discord.ui.button(label="BXH Level", emoji="📊", style=discord.ButtonStyle.primary)
    async def lb(self, interaction, button):
        ranked = sorted(player_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, p) in enumerate(ranked, 1):
            u = bot.get_user(uid)
            n = u.display_name if u else f"User {uid}"
            medal = medals[i-1] if i <= 3 else f"`{i}.`"
            lines.append(f"{medal} **{n}** — Lv.`{p['level']}`")
        await interaction.response.send_message(
            embed=discord.Embed(title="🏆 BXH Level", description="\n".join(lines), color=0xFFD700),
            ephemeral=True
        )

    @discord.ui.button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        if interaction.user.id != self.viewer_id:
            await interaction.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await interaction.response.edit_message(
            embed=build_farm_embed(player_data[self.user_id]),
            view=FarmView(self.user_id)
        )

class BioModal(discord.ui.Modal, title="Đổi Tiểu Sử"):
    bio_input = discord.ui.TextInput(
        label="Tiểu sử (tối đa 100 ký tự)",
        style=discord.TextStyle.paragraph,
        max_length=100,
        required=False
    )
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    async def on_submit(self, interaction):
        player_data[self.user_id]["bio"] = self.bio_input.value or ""
        await interaction.response.send_message("✅ Đã cập nhật tiểu sử!", ephemeral=True)

def build_profile_embed(player, user):
    level = player["level"]
    bounty = player.get("bounty", 0)
    rank = get_bounty_rank(bounty)
    title = get_player_title(player)
    title_str = f"{TITLES[title]['emoji']} **{TITLES[title]['name']}**" if title else "*Chưa có*"

    fruit_key = player.get("equipped_fruit")
    fruit_line = "*Không có*"
    if fruit_key:
        f = SHOP_DATA["fruits"].get(fruit_key)
        if f:
            awk = " ✨" if is_fruit_fully_awakened(player, fruit_key) else ""
            fruit_line = f"{f['emoji']} **{f['name']}**{awk}"

    stats = player["stats"]
    base = player["base_stats"]
    hp = calc_max_hp(player)
    race = RACES.get(player.get("race", "human"), RACES["human"])
    r_lvl = player.get("race_level", 1)

    cur_xp, need_xp = xp_progress_in_level(player["xp"])
    pct = (cur_xp / need_xp * 100) if need_xp > 0 else 100
    filled = int(15 * pct / 100) if need_xp > 0 else 15
    bar = "█" * filled + "░" * (15 - filled)

    pvp_w = player.get("pvp_wins", 0)
    pvp_l = player.get("pvp_losses", 0)
    tot = pvp_w + pvp_l
    wr = (pvp_w / tot * 100) if tot > 0 else 0
    pt_h = int(player.get("playtime", 0) // 3600)
    pt_m = int((player.get("playtime", 0) % 3600) // 60)

    embed = discord.Embed(
        title=f"👤 Hồ Sơ • {user.display_name}",
        description=(
            f"🏴 **Phe:** {player.get('faction', '*Không*')}\n"
            f"🏆 **Danh hiệu:** {title_str}\n"
            f"{rank['emoji']} **{rank['name']}**\n"
            f"💰 `{format_bounty(bounty)}`\n\n"
            f"**📊 Level {level}/{MAX_LEVEL}**\n"
            f"`{bar}` `{format_number(player['xp'])}`\n\n"
            f"🍎 **Trái:** {fruit_line}\n"
            f"👑 **Tộc:** {race['emoji']} {race['name']} V{r_lvl}\n"
            f"❤️ **HP:** `{hp:,}`\n\n"
            "**⚔️ Chỉ số:**\n"
            f"🛡️ Defense: `{stats['defense']}`" + (f" *(+{stats['defense']-base['defense']})*" if stats['defense']>base['defense'] else "") + "\n"
            f"🍎 Fruit: `{stats['fruit']}`" + (f" *(+{stats['fruit']-base['fruit']})*" if stats['fruit']>base['fruit'] else "")
        ),
        color=rank["color"]
    )
    embed.add_field(name="💰 Tài Sản", value=f"💰 `{format_number(player['coin'])}`\n💎 `{format_number(player.get('fragments',0))}`", inline=True)
    embed.add_field(name="⚔️ PvP", value=f"🏆 `{pvp_w}`\n💀 `{pvp_l}`\n📊 `{wr:.1f}%`", inline=True)
    embed.add_field(name="📈 Khác", value=f"👹 `{player.get('bosses_killed',0)}`\n💀 `{player.get('total_kills',0):,}`", inline=True)
    if player.get("bio"):
        embed.add_field(name="📝 Tiểu sử", value=f"*{player['bio']}*", inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"⏱️ {pt_h}h{pt_m}m • 🌊 Sea {player.get('current_sea',1)}/3")
    return embed
# ══════════════════════════════════════════════════════════════════
# 🛒 SHOP VIEW
# ══════════════════════════════════════════════════════════════════
def build_shop_embed(player, category="fruits"):
    stock = get_hourly_fruit_stock(player.get("current_sea", 1))
    lines=[]
    for key in stock:
        item=SHOP_DATA["fruits"][key]
        owned=key in player.get("inventory",{}).get("fruits",[])
        mark="✅" if owned else "🛒"
        lines.append(f"{mark} {item['emoji']} **{item['name']}** — `{item['price']:,}` 💰 • {item['rarity']}")
    return build_hourly_dealer_embed(player).set_footer(text="Kho trái random lại mỗi 60 phút")

class ShopView(discord.ui.View):
    def __init__(self,user_id,category="fruits",page=0):
        super().__init__(timeout=180)
        self.user_id=user_id
        self.category="fruits"
        self.page=0
        stock=get_hourly_fruit_stock(player_data[user_id].get("current_sea",1))
        for idx,key in enumerate(stock):
            item=SHOP_DATA["fruits"][key]
            btn=discord.ui.Button(label=item["name"][:12],emoji=item["emoji"],style=discord.ButtonStyle.success,row=0)
            btn.callback=self._buy(key)
            self.add_item(btn)
        back=discord.ui.Button(label="Về Menu",emoji="↩️",style=discord.ButtonStyle.secondary,row=1)
        back.callback=self._back
        self.add_item(back)

    def _buy(self,key):
        async def cb(i):
            if i.user.id!=self.user_id:
                await i.response.send_message("⚠️ Không phải bạn!",ephemeral=True); return
            p=player_data[self.user_id]
            # Stock phải còn thuộc giờ hiện tại; sang giờ mới thì người chơi cần mở lại Dealer.
            if key not in get_hourly_fruit_stock(p.get("current_sea",1)):
                await i.response.send_message("⏰ Kho trái vừa đổi! Hãy mở lại Dealer.",ephemeral=True); return
            item=SHOP_DATA["fruits"][key]
            if p["coin"]<item["price"]:
                await i.response.send_message(f"❌ Không đủ Coin! Cần `{item['price']:,}`.",ephemeral=True); return
            if key in p.setdefault("inventory",{}).setdefault("fruits",[]):
                await i.response.send_message("⚠️ Bạn đã sở hữu trái này!",ephemeral=True); return
            p["coin"]-=item["price"]
            p["inventory"]["fruits"].append(key)
            p["equipped_fruit"]=key
            await i.response.edit_message(embed=build_shop_embed(p),view=ShopView(self.user_id))
            await i.followup.send(f"✅ Mua và trang bị **{item['emoji']} {item['name']}** với `{item['price']:,}` Coin!",ephemeral=True)
        return cb

    async def _back(self,i):
        if i.user.id!=self.user_id: return
        p=player_data[self.user_id]
        await i.response.edit_message(embed=build_game_embed(p.get("faction","🏴‍☠️ Hải Tặc")),view=GameMenuView(p.get("faction","🏴‍☠️ Hải Tặc"),self.user_id))

# ══════════════════════════════════════════════════════════════════
# 🎒 INVENTORY VIEW
# ══════════════════════════════════════════════════════════════════
def build_inventory_embed(player, category="fruits"):
    items=player.get("inventory",{}).get("fruits",[]); equipped=player.get("equipped_fruit"); lines=[]
    if not items: lines.append("*Chưa sở hữu trái nào!*")
    for k in items[:20]:
        item=SHOP_DATA["fruits"].get(k)
        if item: lines.append(f"{'✅' if k==equipped else '  '} {item['emoji']} **{item['name']}** *({item['rarity']})*")
    stats=player["stats"]; base=player["base_stats"]; stat_lines=[]
    for k in ("defense","fruit"):
        info=STAT_INFO[k]; bonus=stats[k]-base[k]; extra=f" *(+{bonus})*" if bonus>0 else ""; stat_lines.append(f"{info['emoji']} **{info['name']}:** `{stats[k]}`{extra}")
    eq_line=""
    if equipped and equipped in SHOP_DATA["fruits"]:
        eq=SHOP_DATA["fruits"][equipped]; eq_line=f"\n🍎 **Đang dùng:** {eq['emoji']} **{eq['name']}**\n"
    return discord.Embed(title="🎒 Inventory • 🍎 Trái",description=f"📦 **Số trái:** `{len(items)}`\n{eq_line}\n**📊 Chỉ số:**\n"+"\n".join(stat_lines)+"\n\n**🎁 Danh sách Trái:**\n"+"\n".join(lines)+"\n\n\u200b",color=0x9B59B6)

class InventoryView(discord.ui.View):
    def __init__(self,user_id,category="fruits",page=0):
        super().__init__(timeout=180); self.user_id=user_id; self.category="fruits"; self.page=page
        items=player_data[user_id].get("inventory",{}).get("fruits",[]); per=10; start=page*per; equipped=player_data[user_id].get("equipped_fruit")
        for i,key in enumerate(items[start:start+per]):
            item=SHOP_DATA["fruits"].get(key)
            if not item: continue
            btn=discord.ui.Button(label=f"{'✅' if key==equipped else ''} {item['name'][:14]}".strip(),emoji=item["emoji"],style=discord.ButtonStyle.success if key==equipped else discord.ButtonStyle.primary,row=i//5); btn.callback=self._equip(key); self.add_item(btn)
        prev=discord.ui.Button(label="◀",emoji="⬅️",style=discord.ButtonStyle.secondary,row=2,disabled=page==0); prev.callback=self._prev; self.add_item(prev)
        nxt=discord.ui.Button(label="▶",emoji="➡️",style=discord.ButtonStyle.secondary,row=2,disabled=(start+per>=len(items))); nxt.callback=self._next; self.add_item(nxt)
        back=discord.ui.Button(label="Về Farm",emoji="↩️",style=discord.ButtonStyle.secondary,row=2); back.callback=self._back; self.add_item(back)
    def _equip(self,key):
        async def cb(i):
            if i.user.id!=self.user_id: await i.response.send_message("⚠️ Không phải bạn!",ephemeral=True); return
            p=player_data[self.user_id]; item=SHOP_DATA["fruits"].get(key)
            if not item:return
            if p.get("equipped_fruit")==key: p["equipped_fruit"]=None; msg=f"🔓 Đã gỡ **{item['name']}**"
            else: p["equipped_fruit"]=key; msg=f"✅ Trang bị **{item['emoji']} {item['name']}**"
            await i.response.edit_message(embed=build_inventory_embed(p),view=InventoryView(self.user_id,"fruits",self.page)); await i.followup.send(msg,ephemeral=True)
        return cb
    async def _prev(self,i):
        if i.user.id!=self.user_id:return
        await i.response.edit_message(embed=build_inventory_embed(player_data[self.user_id]),view=InventoryView(self.user_id,"fruits",self.page-1))
    async def _next(self,i):
        if i.user.id!=self.user_id:return
        await i.response.edit_message(embed=build_inventory_embed(player_data[self.user_id]),view=InventoryView(self.user_id,"fruits",self.page+1))
    async def _back(self,i):
        if i.user.id!=self.user_id: await i.response.send_message("⚠️ Không phải bạn!",ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]),view=FarmView(self.user_id))

# ══════════════════════════════════════════════════════════════════
# 🏝️ ISLAND VIEWS
# ══════════════════════════════════════════════════════════════════
def build_island_list_embed(player, sea=None):
    if sea is None: sea = player.get("current_sea", 1)
    islands = SEA_DATA[sea]["islands"]
    current = player.get("current_island")
    lines = []
    for key, isl in islands.items():
        locked = player["level"] < isl["level_req"]
        st = "📍" if key == current else ("🔒" if locked else "✅")
        boss_info = f" 👹 {isl['boss']['name']}" if isl.get("boss") else ""
        lines.append(f"{st} {isl['emoji']} **{isl['name']}** (Lv.{isl['level_req']}+){boss_info}")
    return discord.Embed(
        title=f"{SEA_DATA[sea]['emoji']} {SEA_DATA[sea]['name']} • Chọn Đảo",
        description=(f"⭐ `{player['xp']}` | 💰 `{player['coin']}` | 📊 Lv.`{player['level']}`\n"
                     f"🌊 Sea `{sea}/3`\n\n" + "\n".join(lines[:12]) + "\n\n\u200b"),
        color=0x3498DB
    )

def build_island_quest_embed(player, sea, island_key):
    isl = SEA_DATA[sea]["islands"][island_key]
    progress = player.get("quest_progress", 0)
    need = isl["quest_kill"]
    boss_line = f"\n👹 Boss: **{isl['boss']['name']}**" if isl.get("boss") else ""
    filled = int(10 * progress / need) if need else 0
    bar = "█" * filled + "░" * (10 - filled)
    return discord.Embed(
        title=f"{isl['emoji']} {isl['name']} • Nhiệm Vụ",
        description=(f"🌊 {SEA_DATA[sea]['name']} • Sea {sea}/3\n\n"
                     f"**Đánh** `{need}` **quái**\n**Tiến độ:** `{progress}/{need}`{boss_line}\n\n"
                     f"⭐ `{player['xp']}` | 💰 `{player['coin']}` | 📊 Lv.`{player['level']}`\n\n"
                     f"📊 `{bar}` {progress}/{need}\n\u200b"),
        color=0xE67E22 if progress < need else 0x2ECC71
    )

def build_weapon_choose_embed():
    return discord.Embed(
        title="🍎 Chọn Trái Ác Quỷ",
        description="Chỉ sử dụng **Trái Ác Quỷ** để chiến đấu.\n\n🍎 **Trái**\n\n\u200b",
        color=0x9B59B6
    )

class IslandListView(discord.ui.View):
    def __init__(self, user_id, sea=None):
        super().__init__(timeout=180)
        self.user_id = user_id
        p = player_data[user_id]
        self.sea = sea if sea is not None else p.get("current_sea", 1)
        islands = SEA_DATA[self.sea]["islands"]
        current = p.get("current_island")
        for i, (key, isl) in enumerate(islands.items()):
            if i >= 12: break
            locked = p["level"] < isl["level_req"]
            is_cur = key == current
            style = discord.ButtonStyle.success if is_cur else (
                discord.ButtonStyle.secondary if locked else discord.ButtonStyle.primary)
            emoji = "📍" if is_cur else ("🔒" if locked else isl["emoji"])
            btn = discord.ui.Button(label=isl["name"][:16], emoji=emoji, style=style,
                custom_id=f"il_{self.sea}_{key}", row=i//3, disabled=locked and not is_cur)
            btn.callback = self._pick(key)
            self.add_item(btn)
        prev = discord.ui.Button(label="◀ Sea", emoji="⬅️", style=discord.ButtonStyle.secondary, row=4, disabled=self.sea<=1)
        prev.callback = self._prev; self.add_item(prev)
        nxt = discord.ui.Button(label="Sea ▶", emoji="➡️", style=discord.ButtonStyle.secondary, row=4,
            disabled=self.sea>=3 or (self.sea+1) not in p["unlocked_seas"])
        nxt.callback = self._next; self.add_item(nxt)
        back = discord.ui.Button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary, row=4)
        back.callback = self._back; self.add_item(back)
    def _pick(self, ik):
        async def cb(i):
            if i.user.id != self.user_id:
                await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
            p = player_data[self.user_id]
            if p.get("current_island") != ik: p["quest_progress"] = 0
            p["current_island"] = ik
            p["current_sea"] = self.sea
            await i.response.edit_message(embed=build_island_quest_embed(p, self.sea, ik),
                view=IslandQuestView(self.user_id, self.sea, ik))
        return cb
    async def _prev(self, i):
        if i.user.id != self.user_id: return
        if self.sea > 1:
            player_data[self.user_id]["current_sea"] = self.sea - 1
            await i.response.edit_message(embed=build_island_list_embed(player_data[self.user_id], self.sea - 1),
                view=IslandListView(self.user_id, self.sea - 1))
    async def _next(self, i):
        if i.user.id != self.user_id: return
        p = player_data[self.user_id]
        if self.sea < 3 and (self.sea + 1) in p["unlocked_seas"]:
            p["current_sea"] = self.sea + 1
            await i.response.edit_message(embed=build_island_list_embed(p, self.sea + 1),
                view=IslandListView(self.user_id, self.sea + 1))
    async def _back(self, i):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]), view=FarmView(self.user_id))

class IslandQuestView(discord.ui.View):
    def __init__(self, user_id, sea, island_key):
        super().__init__(timeout=120)
        self.user_id = user_id; self.sea = sea; self.island_key = island_key
    @discord.ui.button(label="Bắt Đầu Đánh", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def start(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_weapon_choose_embed(),
            view=WeaponChooseView(self.user_id, self.sea, self.island_key))
    @discord.ui.button(label="Đánh Boss", emoji="👹", style=discord.ButtonStyle.success)
    async def boss(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        isl = SEA_DATA[self.sea]["islands"][self.island_key]
        p = player_data[self.user_id]
        if not isl.get("boss"):
            await i.response.send_message("❌ Đảo không có Boss!", ephemeral=True); return
        if p["quest_progress"] < isl["quest_kill"]:
            await i.response.send_message(f"⚠️ Cần đánh đủ `{isl['quest_kill']}` quái!", ephemeral=True); return
        res = simulate_boss(p, self.sea, self.island_key, "trái", 4)
        em = discord.Embed(title=f"👹 {isl['boss']['name']} {'🏆' if res['win'] else '💀'}",
            description=(f"❤️ HP: `{res['boss_hp']:,}`\n💥 Dmg: `{res['damage']:,}`\n\n" +
                (f"💰 +`{res['coin']:,}`\n⭐ +`{res['xp']:,}`\n💰 Bounty +`{res['bounty_gain']:,}`" if res['win'] else "❌ Thất bại!")) ,
            color=0xFFD700 if res['win'] else 0xE74C3C)
        await i.response.edit_message(embed=em, view=IslandQuestView(self.user_id, self.sea, self.island_key))
    @discord.ui.button(label="Quay Lại", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_island_list_embed(player_data[self.user_id], self.sea),
            view=IslandListView(self.user_id, self.sea))

class WeaponChooseView(discord.ui.View):
    def __init__(self, user_id, sea, island_key):
        super().__init__(timeout=120); self.user_id=user_id; self.sea=sea; self.island_key=island_key
    @discord.ui.button(label="Dùng Trái Ác Quỷ", emoji="🍎", style=discord.ButtonStyle.success, row=0)
    async def trai(self, i, b):
        if i.user.id != self.user_id: await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_fight_embed(player_data[self.user_id], "trái"), view=FightView(self.user_id,self.sea,self.island_key,"trái"))
    @discord.ui.button(label="Quay Lại", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, i, b):
        if i.user.id != self.user_id: await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_island_quest_embed(player_data[self.user_id],self.sea,self.island_key), view=IslandQuestView(self.user_id,self.sea,self.island_key))

def build_fight_embed(player, weapon):
    mastery = player["mastery"].get(weapon, 0)
    skill_lines = []
    for idx, sk in enumerate(SKILLS.get(weapon, []), 1):
        skill_lines.append(f"**{idx}. {sk['name']}** — {sk['damage']} DMG • cần {sk['xp_req']} XP")
    return discord.Embed(
        title=f"{WEAPON_EMOJI[weapon]} Chiến Đấu • {weapon.upper()}",
        description=(
            f"🔧 Thông thạo: `{mastery}`\n⭐ XP: `{player['xp']}`\n\n"
            "✨ **Tên chiêu:**\n" + "\n".join(skill_lines) + "\n\nChọn chiêu!\n\u200b"
        ),
        color=0x9B59B6
    )

class FightView(discord.ui.View):
    def __init__(self, user_id, sea, island_key, weapon):
        super().__init__(timeout=120)
        self.user_id = user_id; self.sea = sea; self.island_key = island_key; self.weapon = weapon
        for i, sk in enumerate(SKILLS[weapon]):
            btn = discord.ui.Button(label=sk["name"][:80], emoji="✨", style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._atk(i); self.add_item(btn)
        back = discord.ui.Button(label="Quay Lại", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._back; self.add_item(back)
    def _atk(self, idx):
        async def cb(i):
            if i.user.id != self.user_id:
                await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
            p = player_data[self.user_id]
            now = time.time()
            if now - p.get("last_fight", 0) < FIGHT_COOLDOWN:
                await i.response.send_message(f"⏳ Chờ `{FIGHT_COOLDOWN - int(now - p['last_fight'])}s`!", ephemeral=True); return
            p["last_fight"] = now
            res = simulate_fight(p, self.sea, self.island_key, self.weapon, idx)
            isl = SEA_DATA[self.sea]["islands"][self.island_key]
            skill_name = SKILLS[self.weapon][idx]["name"] if idx < len(SKILLS.get(self.weapon, [])) else f"Chiêu {idx+1}"
            em = discord.Embed(
                title=f"🏆 Thắng {res['monster']}!" if res['win'] else f"💀 Thua {res['monster']}!",
                description=(
                    f"✨ **Chiêu:** **{skill_name}**\n"
                    f"👹 HP: `{res['monster_hp']}`\n💥 Dmg: `{res['damage']}`\n\n" +
                    (f"💰 +`{res['coin']}`\n⭐ +`{res['xp']}`\n💰 Bounty +`{res['bounty_gain']}`\n" if res['win'] else "❌ Không nhận thưởng!") +
                    f"\n📊 Lv.`{p['level']}` | 🎯 `{p['quest_progress']}/{isl['quest_kill']}`"),
                color=0x2ECC71 if res['win'] else 0xE74C3C)
            view = QuestCompleteView(self.user_id, self.sea, self.island_key) if p["quest_progress"] >= isl["quest_kill"] else self
            await i.response.edit_message(embed=em, view=view)
        return cb
    async def _back(self, i):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_weapon_choose_embed(),
            view=WeaponChooseView(self.user_id, self.sea, self.island_key))

class QuestCompleteView(discord.ui.View):
    def __init__(self, user_id, sea, island_key):
        super().__init__(timeout=120)
        self.user_id = user_id; self.sea = sea; self.island_key = island_key
    @discord.ui.button(label="Nhận & Tiếp Tục", emoji="🎁", style=discord.ButtonStyle.success)
    async def claim(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        p = player_data[self.user_id]
        isl = SEA_DATA[self.sea]["islands"][self.island_key]
        p["coin"] += isl["level_req"] * 1000
        p["xp"] += isl["level_req"] * 500
        p["quest_progress"] = 0
        await i.response.edit_message(embed=build_island_list_embed(p, self.sea),
            view=IslandListView(self.user_id, self.sea))
    @discord.ui.button(label="Ở Lại", emoji="🔁", style=discord.ButtonStyle.secondary)
    async def stay(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        p = player_data[self.user_id]
        p["quest_progress"] = 0
        await i.response.edit_message(embed=build_weapon_choose_embed(),
            view=WeaponChooseView(self.user_id, self.sea, self.island_key))

# ══════════════════════════════════════════════════════════════════
# ✨ AWAKENING VIEW
# ══════════════════════════════════════════════════════════════════
def build_awakening_embed(player, user=None):
    eq = player.get("equipped_fruit")
    frag = player.get("fragments", 0)
    if not eq:
        return discord.Embed(title="✨ Awakening",
            description=f"💎 `{frag:,}`\n\n❌ Chưa trang bị trái!", color=0x9B59B6)
    info = AWAKENING_SKILLS.get(eq)
    if not info:
        return discord.Embed(title="✨ Awakening",
            description=f"❌ Trái **{SHOP_DATA['fruits'][eq]['name']}** không thể awaken!", color=0x95A5A6)
    fruit = SHOP_DATA["fruits"][eq]
    awk = player.get("awakened_skills", {}).get(eq, [])
    skill_lines = []
    for sk in ["Z", "X", "C", "V"]:
        si = info["skills"].get(sk)
        if not si: continue
        a = sk in awk
        st = "✨" if a else "🔒"
        nm = si["awakened_name"] if a else sk
        skill_lines.append(f"{st} **{sk}** → {si['emoji']} {nm}\n    💎 `{si['fragment']:,}` • Dmg ×`{si['damage_mult']}`")
    tot = len(info["skills"]); done = len(awk)
    pct = (done / tot * 100) if tot else 0
    filled = int(10 * done / tot) if tot else 0
    bar = "█" * filled + "░" * (10 - filled)
    if done == tot:
        fb = info["full_bonus"]
        full = f"\n🌟 **FULL AWAKENING:** {fb['name']}\n*{fb['desc']}*\nBonus ×`{fb['damage_mult']}`"
    else:
        full = "\n⚠️ Cần awaken **cả 4 chiêu** để mở Full!"
    return discord.Embed(
        title=f"✨ Awakening • {fruit['emoji']} {fruit['name']}",
        description=(f"💎 **Fragment:** `{frag:,}`\n"
                     f"📊 `{bar}` {done}/{tot} ({pct:.0f}%)\n\n"
                     "**📜 Chiêu:**\n" + "\n".join(skill_lines) + f"{full}\n\u200b"),
        color=info["color"]
    )

class AwakeningView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id
        p = player_data[user_id]
        eq = p.get("equipped_fruit")
        if not eq or eq not in AWAKENING_SKILLS:
            btn = discord.ui.Button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary)
            btn.callback = self._back; self.add_item(btn); return
        info = AWAKENING_SKILLS[eq]
        awk = p.get("awakened_skills", {}).get(eq, [])
        for sk in ["Z", "X", "C", "V"]:
            si = info["skills"].get(sk)
            if not si: continue
            a = sk in awk
            can = p.get("fragments", 0) >= si["fragment"]
            btn = discord.ui.Button(
                label=f"{sk} - {si['fragment']:,}💎",
                emoji="✨" if a else ("✅" if can else "🔒"),
                style=discord.ButtonStyle.success if a else (
                    discord.ButtonStyle.primary if can else discord.ButtonStyle.secondary),
                custom_id=f"awk_{sk}", row=0, disabled=a)
            btn.callback = self._awaken(sk, eq); self.add_item(btn)
        fb = discord.ui.Button(label="Full Awaken", emoji="🌟", style=discord.ButtonStyle.danger, row=1)
        fb.callback = self._full(eq); self.add_item(fb)
        rb = discord.ui.Button(label="Raid", emoji="👹", style=discord.ButtonStyle.secondary, row=1)
        rb.callback = self._raid; self.add_item(rb)
        bb = discord.ui.Button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        bb.callback = self._back; self.add_item(bb)
    def _awaken(self, sk, fk):
        async def cb(i):
            if i.user.id != self.user_id:
                await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
            p = player_data[self.user_id]
            info = AWAKENING_SKILLS[fk]; si = info["skills"][sk]
            awk = p.get("awakened_skills", {}).get(fk, [])
            if sk in awk:
                await i.response.send_message("✅ Đã awaken!", ephemeral=True); return
            if p.get("fragments", 0) < si["fragment"]:
                await i.response.send_message(f"❌ Thiếu `{si['fragment']-p['fragments']:,}` Fragment!", ephemeral=True); return
            p["fragments"] -= si["fragment"]
            p.setdefault("awakened_skills", {}).setdefault(fk, []).append(sk)
            full = len(p["awakened_skills"][fk]) == 4
            em = discord.Embed(title="✨ AWAKEN THÀNH CÔNG!",
                description=(f"⚔️ **{sk}** → {si['emoji']} **{si['awakened_name']}**\n"
                             f"💥 Damage ×`{si['damage_mult']}`\n"
                             f"💎 -`{si['fragment']:,}` • Còn `{p['fragments']:,}`"),
                color=info["color"])
            if full:
                fbi = info["full_bonus"]
                em.add_field(name="🌟 FULL AWAKENING!", value=f"**{fbi['name']}**\nBonus ×`{fbi['damage_mult']}`", inline=False)
            await i.response.edit_message(embed=em, view=AwakeningView(self.user_id))
        return cb
    def _full(self, fk):
        async def cb(i):
            if i.user.id != self.user_id:
                await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
            p = player_data[self.user_id]
            info = AWAKENING_SKILLS[fk]
            awk = p.get("awakened_skills", {}).get(fk, [])
            if len(awk) == 4:
                await i.response.send_message("✅ Đã full!", ephemeral=True); return
            cost = sum(info["skills"][sk]["fragment"] for sk in ["Z","X","C","V"] if sk not in awk)
            if p.get("fragments", 0) < cost:
                await i.response.send_message(f"❌ Cần `{cost:,}` Fragment!", ephemeral=True); return
            p["fragments"] -= cost
            p.setdefault("awakened_skills", {})[fk] = ["Z","X","C","V"]
            fbi = info["full_bonus"]
            em = discord.Embed(title="🌟 FULL AWAKENING!",
                description=f"**{fbi['name']}**\n*{fbi['desc']}*\n\n💥 ×`{fbi['damage_mult']}`\n💎 -`{cost:,}` • Còn `{p['fragments']:,}`",
                color=0xFFD700)
            await i.response.edit_message(embed=em, view=AwakeningView(self.user_id))
        return cb
    async def _raid(self, i):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.send_message(embed=build_raid_menu_embed(player_data[self.user_id]),
            view=RaidView(self.user_id), ephemeral=True)
    async def _back(self, i):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]), view=FarmView(self.user_id))

# ══════════════════════════════════════════════════════════════════
# 🎲 GACHA VIEW
# ══════════════════════════════════════════════════════════════════
class GachaView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id
    @discord.ui.button(label="Quay x1", emoji="🎯", style=discord.ButtonStyle.success, row=0)
    async def r1(self, i, b): await self._roll(i, 1, "single")
    @discord.ui.button(label="Quay x10", emoji="🎁", style=discord.ButtonStyle.primary, row=0)
    async def r10(self, i, b): await self._roll(i, 10, "x10")
    @discord.ui.button(label="Quay x50", emoji="🌟", style=discord.ButtonStyle.danger, row=0)
    async def r50(self, i, b): await self._roll(i, 50, "x50")
    @discord.ui.button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]), view=FarmView(self.user_id))
    async def _roll(self, i, count, cost_key):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        p = player_data[self.user_id]
        cost = get_gacha_cost(p, count)
        if p["coin"] < cost:
            await i.response.send_message(f"❌ Cần `{cost:,}` Coin! (Lv.{p.get('level',1)})", ephemeral=True); return
        p["coin"] -= cost
        results = []
        for _ in range(count):
            f = roll_fruit(p.get("current_sea", 1))
            if f: results.append(f)
        new = give_fruits_to_player(p, results)
        em = build_gacha_result_embed(results, p, new, is_multi=(count > 1))
        await i.response.edit_message(embed=em, view=GachaView(self.user_id))

# ══════════════════════════════════════════════════════════════════
# 👹 RAID VIEW
# ══════════════════════════════════════════════════════════════════
class RaidView(discord.ui.View):
    def __init__(self, user_id, page=0):
        super().__init__(timeout=180)
        self.user_id = user_id; self.page = page
        p = player_data[user_id]
        all_b = list(RAID_BOSSES.items())
        per = 3; total = (len(all_b) + per - 1) // per
        for i, (k, boss) in enumerate(all_b[page*per:(page+1)*per]):
            locked = p["level"] < boss["level_req"]
            rem, ok = check_raid_cooldown(p, k)
            if locked:
                lbl = f"{boss['name']} 🔒"; style = discord.ButtonStyle.secondary; dis = True
            elif not ok:
                lbl = f"{boss['name']} ({format_time(rem)})"; style = discord.ButtonStyle.secondary; dis = True
            else:
                lbl = boss["name"]; style = discord.ButtonStyle.danger; dis = False
            btn = discord.ui.Button(label=lbl, emoji=boss["emoji"], style=style,
                custom_id=f"raid_{k}", row=0, disabled=dis)
            btn.callback = self._pick(k); self.add_item(btn)
        prev = discord.ui.Button(label="◀", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1, disabled=page==0)
        prev.callback = self._prev; self.add_item(prev)
        nxt = discord.ui.Button(label="▶", emoji="➡️", style=discord.ButtonStyle.secondary, row=1, disabled=page>=total-1)
        nxt.callback = self._next; self.add_item(nxt)
        back = discord.ui.Button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self._back; self.add_item(back)
    def _pick(self, bk):
        async def cb(i):
            if i.user.id != self.user_id:
                await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
            p = player_data[self.user_id]
            rem, ok = check_raid_cooldown(p, bk)
            if not ok:
                await i.response.send_message(f"⏳ Chờ `{format_time(rem)}`!", ephemeral=True); return
            res = simulate_raid(p, bk)
            boss = RAID_BOSSES[bk]
            em = discord.Embed(
                title=f"{boss['emoji']} {boss['name']} {'🏆' if res['win'] else '💀'}",
                description=(f"❤️ HP: `{res['boss_hp']:,}`\n💥 Dmg: `{res['damage']:,}`\n\n" +
                    (f"💎 +`{res['fragment']:,}`\n💰 +`{res['coin']:,}`\n⭐ +`{res['xp']:,}`" if res['win'] else "❌ Thất bại!")),
                color=0x2ECC71 if res['win'] else 0xE74C3C)
            await i.response.edit_message(embed=em, view=RaidView(self.user_id))
        return cb
    async def _prev(self, i):
        if i.user.id != self.user_id: return
        await i.response.edit_message(embed=build_raid_menu_embed(player_data[self.user_id]),
            view=RaidView(self.user_id, self.page - 1))
    async def _next(self, i):
        if i.user.id != self.user_id: return
        await i.response.edit_message(embed=build_raid_menu_embed(player_data[self.user_id]),
            view=RaidView(self.user_id, self.page + 1))
    async def _back(self, i):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]), view=FarmView(self.user_id))

# ══════════════════════════════════════════════════════════════════
# 💰 BOUNTY VIEW
# ══════════════════════════════════════════════════════════════════
def build_bounty_embed(user, player):
    b = player.get("bounty", 0)
    r = get_bounty_rank(b)
    hist = player.get("bounty_history", [])[-5:]
    hl = []
    for h in reversed(hist):
        sign = "+" if h["amount"] >= 0 else ""
        hl.append(f"`{sign}{format_number(h['amount'])}` — *{h['reason']}*")
    if not hl: hl = ["*Chưa có hoạt động*"]
    return discord.Embed(
        title=f"💰 Truy Nã • {user.display_name}",
        description=(f"{r['emoji']} **{r['name']}**\n\n"
                     f"💰 `{format_bounty(b)}`\n"
                     f"📊 Lv.`{player['level']}`\n"
                     f"⚔️ PvP: `{player.get('pvp_wins',0)}W/{player.get('pvp_losses',0)}L`\n\n"
                     "**📜 Gần đây:**\n" + "\n".join(hl) + "\n\u200b"),
        color=r["color"])

class BountyView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id
    @discord.ui.button(label="BXH Bounty", emoji="🏆", style=discord.ButtonStyle.primary)
    async def lb(self, i, b):
        ranked = sorted(player_data.items(), key=lambda x: x[1].get("bounty", 0), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for idx, (uid, p) in enumerate(ranked, 1):
            u = bot.get_user(uid); n = u.display_name if u else f"User {uid}"
            bb = p.get("bounty", 0); rr = get_bounty_rank(bb)
            m = medals[idx-1] if idx <= 3 else f"`{idx}.`"
            lines.append(f"{m} **{n}** {rr['emoji']} — `{format_bounty(bb)}`")
        await i.response.send_message(embed=discord.Embed(title="🏆 BXH Bounty",
            description="\n".join(lines), color=0xFFD700), ephemeral=True)
    @discord.ui.button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]), view=FarmView(self.user_id))

# ══════════════════════════════════════════════════════════════════
# ⚔️ PVP VIEW
# ══════════════════════════════════════════════════════════════════
def build_battle_invite_embed(inviter, target):
    ip = player_data.get(inviter.id); tp = player_data.get(target.id)
    if not ip or not tp: return discord.Embed(title="❌ Lỗi", color=0xE74C3C)
    return discord.Embed(
        title="⚔️ Lời Mời PvP",
        description=(f"**{inviter.display_name}** thách đấu!\n\n"
                     f"👤 **Đối thủ:** Lv.`{ip['level']}`\n"
                     f"📊 **Bạn:** Lv.`{tp['level']}`\n\n"
                     "⏱️ Hết hạn 60 giây."),
        color=0xE74C3C)

class PvPInviteView(discord.ui.View):
    def __init__(self, inviter_id, target_id):
        super().__init__(timeout=60)
        self.inviter_id = inviter_id; self.target_id = target_id
    @discord.ui.button(label="Chấp Nhận", emoji="✅", style=discord.ButtonStyle.success)
    async def acc(self, i, b):
        if i.user.id != self.target_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=discord.Embed(title="✅ Đã chấp nhận",
            description="Trận PvP sẽ sớm được bắt đầu!", color=0x2ECC71), view=None)
    @discord.ui.button(label="Từ Chối", emoji="❌", style=discord.ButtonStyle.danger)
    async def dec(self, i, b):
        if i.user.id != self.target_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        for c in self.children: c.disabled = True
        await i.response.edit_message(embed=discord.Embed(title="❌ Từ chối",
            description=f"{i.user.display_name} đã từ chối.", color=0x95A5A6), view=self)

# ══════════════════════════════════════════════════════════════════
# 🎯 BATTLE BOUNTY VIEW
# ══════════════════════════════════════════════════════════════════
def build_battle_bounty_embed(player, user):
    b = player.get("bounty", 0)
    r = get_bounty_rank(b)
    return discord.Embed(
        title="🎯 Battle Bounty",
        description=(f"**Bounty:** {r['emoji']} `{format_bounty(b)}`\n\n"
                     "**📜 Luật:**\n"
                     f"• Bounty tối thiểu: `{format_bounty(BATTLE_CONFIG['min_bounty'])}`\n"
                     f"• Cướp `{int(BATTLE_CONFIG['bounty_steal_pct']*100)}%` khi thắng\n"
                     f"• Mất `{int(BATTLE_CONFIG['bounty_steal_pct']*100)}%` khi thua\n\n"
                     "💡 Dùng `/pvp @user` để thách đấu."),
        color=0xE74C3C)

class BattleBountyView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id
    @discord.ui.button(label="DS Top Bounty", emoji="🏆", style=discord.ButtonStyle.primary)
    async def top(self, i, b):
        ranked = sorted(player_data.items(), key=lambda x: x[1].get("bounty", 0), reverse=True)[:10]
        lines = []
        for idx, (uid, p) in enumerate(ranked, 1):
            u = bot.get_user(uid); n = u.display_name if u else f"User {uid}"
            bb = p.get("bounty", 0); rr = get_bounty_rank(bb)
            m = ["🥇","🥈","🥉"][idx-1] if idx <= 3 else f"`{idx}.`"
            lines.append(f"{m} **{n}** {rr['emoji']} — `{format_bounty(bb)}` • Lv.`{p['level']}`")
        await i.response.send_message(embed=discord.Embed(title="💰 Top Bounty",
            description="\n".join(lines), color=0xFFD700), ephemeral=True)
    @discord.ui.button(label="Lịch Sử", emoji="📜", style=discord.ButtonStyle.secondary)
    async def hist(self, i, b):
        p = player_data[self.user_id]
        await i.response.send_message(embed=discord.Embed(title="📜 Lịch Sử Battle",
            description=f"🏆 Thắng: `{p.get('battle_wins',0)}`\n💀 Thua: `{p.get('battle_losses',0)}`\n"
                        f"💰 Cướp: `{format_bounty(p.get('bounty_stolen',0))}`\n"
                        f"🔻 Mất: `{format_bounty(p.get('bounty_lost',0))}`",
            color=0x9B59B6), ephemeral=True)
    @discord.ui.button(label="Về Farm", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_farm_embed(player_data[self.user_id]), view=FarmView(self.user_id))

# ══════════════════════════════════════════════════════════════════
# 🛒 SELL VIEW
# ══════════════════════════════════════════════════════════════════
class SellView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        config = sell_config.get(guild_id, {})
        for key in config.get("fruits", [])[:5]:
            item = SHOP_DATA["fruits"].get(key)
            if not item: continue
            btn = discord.ui.Button(label=item["name"][:15], emoji=item["emoji"],
                style=discord.ButtonStyle.success, custom_id=f"sell_{guild_id}_{key}", row=0)
            btn.callback = self._buy(key)
            self.add_item(btn)
    def _buy(self, fk):
        async def cb(i):
            if i.user.id not in player_data:
                await i.response.send_message("❌ Chưa tham gia! Dùng `/onepiece`", ephemeral=True); return
            p = player_data[i.user.id]
            item = SHOP_DATA["fruits"][fk]
            price = int(item["price"] * 1.5)
            if p["coin"] < price:
                await i.response.send_message(f"❌ Cần `{format_number(price)}` Coin!", ephemeral=True); return
            if fk in p["inventory"]["fruits"]:
                await i.response.send_message(f"⚠️ Đã có **{item['name']}**!", ephemeral=True); return
            p["coin"] -= price
            p["inventory"]["fruits"].append(fk)
            p["equipped_fruit"] = fk
            await i.response.send_message(f"✅ Mua **{item['emoji']} {item['name']}**! (-`{format_number(price)}`)", ephemeral=True)
        return cb

# ══════════════════════════════════════════════════════════════════
# 👑 RACE VIEW
# ══════════════════════════════════════════════════════════════════
def build_race_embed(player):
    rk = player.get("race", "human")
    race = RACES.get(rk, RACES["human"])
    rl = player.get("race_level", 1)
    if rl >= 4:
        bonuses = get_race_v4_bonus(rk)
        title = f"👑 {race['name']} V4"
        color = 0xFFD700
    else:
        bonuses = race["v1"]["bonus"]
        title = f"{race['emoji']} {race['name']} V{rl}"
        color = race["color"]
    bl = [f"• +{v} {k.title()}" for k, v in bonuses.items()]
    v4 = ""
    if rl < 4:
        v4 = (f"\n**🌟 Nâng V4:**\n"
              f"💰 `{format_number(RACE_V4_COST['coin'])}`\n"
              f"💎 `{format_number(RACE_V4_COST['fragments'])}`\n"
              f"🎯 `{RACE_V4_COST['race_fragments']}` Race Frag\n")
    else:
        v4 = "\n✅ **Đã V4 — cấp cao nhất!**\n"
    return discord.Embed(
        title="👑 Hệ Thống Tộc",
        description=(f"{title}\n\n**Bonus:**\n" + "\n".join(bl) + f"\n{v4}\n"
                     f"💰 `{format_number(player['coin'])}`\n"
                     f"💎 `{format_number(player.get('fragments',0))}`\n"
                     f"🎯 `{player.get('race_fragments',0)}`\n\u200b"),
        color=color)

class RaceView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id
    @discord.ui.button(label="Đổi Tộc (1M)", emoji="🔄", style=discord.ButtonStyle.primary)
    async def change(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        await i.response.edit_message(embed=build_race_change_embed(), view=RaceChangeView(self.user_id))
    @discord.ui.button(label="Nâng V4", emoji="👑", style=discord.ButtonStyle.danger)
    async def v4(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        p = player_data[self.user_id]
        if p.get("race_level", 1) >= 4:
            await i.response.send_message("✅ Đã V4!", ephemeral=True); return
        missing = []
        if p["coin"] < RACE_V4_COST["coin"]:
            missing.append(f"💰 thiếu `{format_number(RACE_V4_COST['coin']-p['coin'])}`")
        if p.get("fragments", 0) < RACE_V4_COST["fragments"]:
            missing.append(f"💎 thiếu `{format_number(RACE_V4_COST['fragments']-p.get('fragments',0))}`")
        if p.get("race_fragments", 0) < RACE_V4_COST["race_fragments"]:
            missing.append(f"🎯 thiếu `{RACE_V4_COST['race_fragments']-p.get('race_fragments',0)}`")
        if missing:
            await i.response.send_message("❌ Thiếu:\n" + "\n".join(missing), ephemeral=True); return
        p["coin"] -= RACE_V4_COST["coin"]
        p["fragments"] -= RACE_V4_COST["fragments"]
        p["race_fragments"] -= RACE_V4_COST["race_fragments"]
        p["race_level"] = 4
        recalc_stats(p)
        rk = p.get("race", "human")
        bonuses = get_race_v4_bonus(rk)
        em = discord.Embed(title="👑 NÂNG V4 THÀNH CÔNG!",
            description=("**Bonus mới:**\n" + "\n".join(f"• **+{v}** {k.title()}" for k, v in bonuses.items()) +
                         "\n\n⚡ Sức mạnh tăng vọt!"), color=0xFFD700)
        await i.response.edit_message(embed=em, view=RaceView(self.user_id))
    @discord.ui.button(label="Về Profile", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, i, b):
        if i.user.id != self.user_id:
            await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
        u = bot.get_user(self.user_id)
        await i.response.edit_message(embed=build_profile_embed(player_data[self.user_id], u),
            view=ProfileView(self.user_id))

def build_race_change_embed():
    lines = []
    for k, r in RACES.items():
        b = ", ".join(f"+{v} {sk.title()}" for sk, v in r["v1"]["bonus"].items())
        lines.append(f"{r['emoji']} **{r['name']}** — {b}")
    return discord.Embed(title="🔄 Chọn Tộc",
        description="\n".join(lines) + "\n\n⚠️ Đổi tộc tốn `1,000,000` Coin!\n\u200b", color=0x9B59B6)

class RaceChangeView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id
        for idx, (k, r) in enumerate(RACES.items()):
            btn = discord.ui.Button(label=r["name"], emoji=r["emoji"],
                style=discord.ButtonStyle.primary, custom_id=f"rc_{k}", row=idx // 3)
            btn.callback = self._pick(k); self.add_item(btn)
        back = discord.ui.Button(label="Quay Lại", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
        back.callback = self._back; self.add_item(back)
    def _pick(self, rk):
        async def cb(i):
            if i.user.id != self.user_id:
                await i.response.send_message("⚠️ Không phải bạn!", ephemeral=True); return
            p = player_data[self.user_id]
            if p["coin"] < 1_000_000:
                await i.response.send_message("❌ Cần `1,000,000` Coin!", ephemeral=True); return
            if p.get("race") == rk:
                await i.response.send_message("⚠️ Đang ở tộc này!", ephemeral=True); return
            p["coin"] -= 1_000_000
            p["race"] = rk
            p["race_level"] = 1
            recalc_stats(p)
            race = RACES[rk]
            await i.response.edit_message(embed=discord.Embed(title="✅ Đổi Tộc!",
                description=f"Trở thành {race['emoji']} **{race['name']}**!\n\n" +
                            "\n".join(f"• +{v} {sk.title()}" for sk, v in race["v1"]["bonus"].items()),
                color=race["color"]), view=RaceView(self.user_id))
        return cb
    async def _back(self, i):
        if i.user.id != self.user_id: return
        await i.response.edit_message(embed=build_race_embed(player_data[self.user_id]), view=RaceView(self.user_id))
        # ══════════════════════════════════════════════════════════════════
# 🏆 LEADERBOARD EMBEDS
# ══════════════════════════════════════════════════════════════════
def build_leaderboard_embed(guild):
    top = get_top_players(10)
    if not top:
        return discord.Embed(title="🏆 BXH", description="*Chưa có ai!*", color=0xFFD700)

    medals = ["🥇", "🥈", "🥉"]
    top3 = []
    for i in range(min(3, len(top))):
        uid, p, sc = top[i]
        u = bot.get_user(uid)
        n = u.display_name if u else f"User {uid}"
        t = get_player_title(p)
        ts = f" {TITLES[t]['emoji']} *{TITLES[t]['name']}*" if t else ""
        top3.append(f"{medals[i]} **{n}**{ts}\n   ⚡ `{format_number(sc)}` • Lv.`{p['level']}`")

    rest = []
    for i in range(3, len(top)):
        uid, p, sc = top[i]
        u = bot.get_user(uid)
        n = u.display_name if u else f"User {uid}"
        rest.append(f"`{i+1}.` **{n}** — ⚡ `{format_number(sc)}` • Lv.`{p['level']}`")

    desc = "**🌟 TOP 3:**\n\n" + "\n\n".join(top3)
    if rest:
        desc += "\n\n**📋 Tiếp theo:**\n" + "\n".join(rest)
    desc += f"\n\n━━━━━━━━━━━━━━━\n👥 `{len(player_data)}` người • 🔄 60s"

    embed = discord.Embed(title="🏆 BXH • NGƯỜI MẠNH NHẤT", description=desc,
        color=0xFFD700, timestamp=discord.utils.utcnow())
    if top:
        tu = bot.get_user(top[0][0])
        if tu: embed.set_thumbnail(url=tu.display_avatar.url)
    embed.set_footer(text="⚡ Power = Stats + Level + Awaken + PvP")
    return embed

def build_bounty_leaderboard_embed(guild):
    ranked = sorted(player_data.items(), key=lambda x: x[1].get("bounty", 0), reverse=True)[:10]
    if not ranked:
        return discord.Embed(title="💰 BXH Truy Nã", description="*Chưa có ai!*", color=0xFFD700)

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, p) in enumerate(ranked):
        u = bot.get_user(uid); n = u.display_name if u else f"User {uid}"
        b = p.get("bounty", 0); r = get_bounty_rank(b)
        m = medals[i] if i < 3 else f"`{i+1}.`"
        if i < 3:
            lines.append(f"{m} **{n}** {r['emoji']}\n   💰 `{format_bounty(b)}` • Lv.`{p['level']}`")
        else:
            lines.append(f"{m} **{n}** — 💰 `{format_bounty(b)}`")

    embed = discord.Embed(title="💰 BXH • TRUY NÃ",
        description="\n\n".join(lines) + f"\n\n━━━━━━━━━━━━━━━\n👥 `{len(player_data)}` • 🔄 60s",
        color=0xFFD700, timestamp=discord.utils.utcnow())
    if ranked:
        tu = bot.get_user(ranked[0][0])
        if tu: embed.set_thumbnail(url=tu.display_avatar.url)
    return embed

# ══════════════════════════════════════════════════════════════════
# 🔄 TASKS
# ══════════════════════════════════════════════════════════════════
@tasks.loop(seconds=60)
async def update_leaderboards():
    for guild_id, config in list(leaderboard_config.items()):
        if guild_id == "bounty_channels": continue
        try:
            guild = bot.get_guild(int(guild_id))
            if not guild: continue
            ch = guild.get_channel(config["channel_id"])
            if not ch:
                del leaderboard_config[guild_id]; save_leaderboard_config(); continue
            try:
                msg = await ch.fetch_message(config["message_id"])
            except discord.NotFound:
                nm = await ch.send(embed=build_leaderboard_embed(guild))
                leaderboard_config[guild_id]["message_id"] = nm.id
                save_leaderboard_config(); continue
            ne = build_leaderboard_embed(guild)
            if not msg.embeds or msg.embeds[0].description != ne.description:
                await msg.edit(embed=ne)
        except Exception as e:
            print(f"[LB] {guild_id}: {e}")

    bc = leaderboard_config.get("bounty_channels", {})
    for guild_id, config in list(bc.items()):
        try:
            guild = bot.get_guild(int(guild_id))
            if not guild: continue
            ch = guild.get_channel(config["channel_id"])
            if not ch: continue
            try:
                msg = await ch.fetch_message(config["message_id"])
                ne = build_bounty_leaderboard_embed(guild)
                if not msg.embeds or msg.embeds[0].description != ne.description:
                    await msg.edit(embed=ne)
            except: pass
        except Exception as e:
            print(f"[Bounty LB] {guild_id}: {e}")

@tasks.loop(seconds=60)
async def auto_refresh_sell():
    for guild_id, config in list(sell_config.items()):
        try:
            if time.time() - config["last_refresh"] >= SELL_REFRESH_SECONDS:
                refresh_sell_fruits(guild_id)
                guild = bot.get_guild(int(guild_id))
                if not guild: continue
                ch = guild.get_channel(config["channel_id"])
                if not ch: continue
                try:
                    msg = await ch.fetch_message(config["message_id"])
                    await msg.edit(embed=build_sell_embed(guild_id), view=SellView(guild_id))
                except: pass
        except Exception as e:
            print(f"[Sell] {guild_id}: {e}")

@update_leaderboards.before_loop
async def before_lb(): await bot.wait_until_ready()

@auto_refresh_sell.before_loop
async def before_sell(): await bot.wait_until_ready()

# ══════════════════════════════════════════════════════════════════

@bot.tree.command(name="onepiece", description="🏴‍☠️ Mở bảng điều khiển One Piece")
async def cmd_onepiece(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=build_main_embed(),
        view=OnePieceHubView()
    )

@bot.event
async def on_ready():
    # Đồng bộ slash command chỉ vào server được phép và dọn bản global cũ.
    # Trước đây /onepiece từng được sync global, nên Discord có thể hiển thị
    # đồng thời 1 bản global + 1 bản guild thành 2 /onepiece.
    try:
        guild_obj = discord.Object(id=ALLOWED_GUILD_ID)

        # Giữ lại danh sách command hiện có trong code để có thể dùng lại sau khi
        # dọn registry global cũ trên Discord.
        current_commands = list(bot.tree.get_commands())

        # 1) Xóa toàn bộ global command cũ trên Discord.
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()

        # 2) Khôi phục các command trong code vào local command tree.
        for command in current_commands:
            bot.tree.add_command(command)

        # 3) Chỉ đăng ký các command đó vào guild mục tiêu.
        bot.tree.clear_commands(guild=guild_obj)
        bot.tree.copy_global_to(guild=guild_obj)
        synced_guild = await bot.tree.sync(guild=guild_obj)

        names = [getattr(cmd, "name", "?") for cmd in synced_guild]
        print(f"[BOT] Slash commands trong server {ALLOWED_GUILD_ID}: {names}")
        print(f"[BOT] Đã sync {len(synced_guild)} slash commands vào server.")
    except Exception as e:
        print(f"[BOT] LỖI SYNC SLASH COMMAND: {type(e).__name__}: {e}")

    print(f"[BOT] Đã đăng nhập: {bot.user}")

# ===== KHOI DONG BOT TREN RAILWAY =====
# Dat token Discord trong Railway Variables voi ten: DISCORD_TOKEN
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Chua dat bien moi truong DISCORD_TOKEN tren Railway")

bot.run(TOKEN)
