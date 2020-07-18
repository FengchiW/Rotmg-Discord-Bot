import asyncio
import datetime

import discord
from discord.ext import commands

import checks
import embeds
import sql
import utils
from cogs.Raiding.logrun import LogRun
from cogs.Raiding.vc_select import VCSelect


class Logging(commands.Cog):
    """Run Logging"""

    def __init__(self, client):
        self.client = client

    @commands.command(usage="pop <key/event/vial/helm/shield/sword> <member> [number]",
                      description="Log when a member pops something for the server.")
    @commands.guild_only()
    @checks.is_rl_or_higher_check()
    async def pop(self, ctx, type, member: utils.MemberLookupConverter, number: int = 1):
        type = type.lower()
        if type not in ["key", "event", "vial", "helm", "shield", "sword"]:
            embed = discord.Embed(title="Error!", description="Please choose a proper key option!\nUsage: `!pop <key/event/vial/helm/"
                                                              "shield/sword> <@member> {number}`", color=discord.Color.red())
            return await ctx.send(embed=embed)

        col = sql.log_cols.pkey if type == "key" else sql.log_cols.eventkeys if type == "event" else sql.log_cols.vials if type == "vial"\
            else sql.log_cols.helmrunes if type == "helm" else sql.log_cols.shieldrunes if type == "shield" else sql.log_cols.swordrunes
        num = await sql.log_runs(self.client.pool, ctx.guild.id, member.id, col, number)

        if type != 'event':
            await utils.check_pops(self.client, ctx, member, number, num, type=type)
        embed = discord.Embed(title="Key Logged!", description=f"Successfully logged {number} popped {type}(s) for {member.mention}",
                              color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command(usage="logrun [member (leader)] [num_runs]", description="Log a full run (or multiple runs) manually.")
    @commands.guild_only()
    @checks.is_rl_or_higher_check()
    async def logrun(self, ctx, member: utils.MemberLookupConverter=None, number=1):
        if not member:
            member = ctx.author

        setup = VCSelect(self.client, ctx)
        data = await setup.start()
        if isinstance(data, tuple):
            (raidnum, inraiding, invet, inevents, raiderrole, rlrole, hcchannel, vcchannel, setup_msg) = data
        else:
            return

        try:
            await setup_msg.delete()
        except discord.NotFound:
            pass
        r_msg = await ctx.send(embed=embeds.dungeon_select())
        def dungeon_check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        while True:
            try:
                msg = await self.client.wait_for('message', timeout=60, check=dungeon_check)
            except asyncio.TimeoutError:
                embed = discord.Embed(title="Timed out!", description="You didn't choose a dungeon in time!", color=discord.Color.red())
                await r_msg.clear_reactions()
                return await r_msg.edit(embed=embed)

            if msg.content.isdigit():
                if 0 < int(msg.content) < 56:
                    break
            await ctx.send("Please choose a number between 1-55!", delete_after=7)

        await r_msg.delete()
        dungeon_info = utils.dungeon_info(int(msg.content))
        await msg.delete()
        dungeontitle = dungeon_info[0]
        emojis = dungeon_info[1]
        guild_db = self.client.guild_db.get(ctx.guild.id)
        logrun = LogRun(self.client, ctx, emojis, [], dungeontitle, [member.id], guild_db.get(sql.gld_cols.rlroleid), hcchannel,
                        events=inevents, vialreacts=[], helmreacts=[], shieldreacts=[], swordreacts=[], numruns=number, runleader=member)
        await logrun.start()
        
    @commands.command(usage="updateleaderboard", description="Manually updates the leaderboard in this server.")
    @commands.guild_only()
    @checks.is_rl_or_higher_check()
    async def updateleaderboard(self, ctx):
        await ctx.message.delete()
        if ctx.guild.id in self.client.serverwleaderboard:
            embed = discord.Embed(title="Success!", description="The leaderboards are being updated & will be posted soon!",
                                  color=discord.Color.green())
            await ctx.send(embed=embed)
            return await update_leaderboard(self.client, ctx.guild.id)
        return await ctx.send("This server does not have leaderboards enabled! Contact Darkmattr#7321 to enable them.", delete_after=7)
        

def setup(client):
    client.add_cog(Logging(client))


async def update_leaderboards(client):
    while(True):
        startofweek = (datetime.datetime.today() + datetime.timedelta(days=7 - datetime.datetime.today().weekday())).replace(hour=0,
                                                                      minute=0, second=0, microsecond=1)
        await asyncio.sleep((startofweek-datetime.datetime.utcnow()).total_seconds())

        for id in client.serverwleaderboard:
            await update_leaderboard(client, id)
        await asyncio.sleep(10) # Sleep for 10s so don't get repeated messages
  
async def update_leaderboard(client, guild_id):
    guild = client.get_guild(guild_id)
    leaderboardchannel = client.guild_db.get(guild_id)[sql.gld_cols.leaderboardchannel]
    zerorunschannel = client.guild_db.get(guild_id)[sql.gld_cols.zerorunchannel]
    rlrole = client.guild_db.get(guild_id)[sql.gld_cols.rlroleid]

    top_runs = await sql.get_top_10_logs(client.pool, guild_id, sql.log_cols.weeklyruns, False)
    top_runs = clean_rl_data(top_runs, guild, rlrole)
    top_assists = await sql.get_top_10_logs(client.pool, guild_id, sql.log_cols.weeklyassists, False)
    top_assists = clean_rl_data(top_assists, guild, rlrole)
    top_keys = await sql.get_top_10_logs(client.pool, guild_id, sql.log_cols.pkey)

    embed = discord.Embed(title="Top Runs Led This Week", color=discord.Color.gold())
    embed.add_field(name="Runs Led:", value=format_top_data(top_runs, sql.log_cols.weeklyruns)).add_field(name="Runs Assisted:",
                                                                                                          value=format_top_data(top_assists,
                                                                                                                                sql.log_cols.weeklyassists))
    await leaderboardchannel.send(embed=embed)

    embed = discord.Embed(title="Top Keys Popped", color=discord.Color.gold())
    embed.add_field(name="Keys Popped:", value=format_top_data(top_keys, sql.log_cols.pkey))
    await leaderboardchannel.send(embed=embed)

    zero_runs = await sql.get_0_runs(client.pool, guild_id)
    zero_runs = clean_rl_data(zero_runs, guild, rlrole, False)

    if zero_runs:
        desc = "".join("<@" + str(r[0]) + "> - (Assists: " + str(r[sql.log_cols.weeklyassists]) + ")\n" for r in zero_runs)
    else:
        desc = "All rl's completed at least 1 run this week."
    embed = discord.Embed(title="RL's With 0 Runs", description=desc, color=discord.Color.orange())
    await zerorunschannel.send(embed=embed)
            

def clean_rl_data(data, guild, rlrole, truncate=True):
    temp = []
    for i, r in enumerate(data):
        member = guild.get_member(r[0])
        if member:
            if member.top_role >= rlrole:
                temp.append(r)
    if truncate:
        temp = temp[:10]
    return temp


def format_top_data(data, col):
    top = ""
    for i, r in enumerate(data):
        top += f"#{i+1}. <@{r[0]}> - {r[col]}\n"

    return top