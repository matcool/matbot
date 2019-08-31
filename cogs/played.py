import discord
from discord.ext import commands
from discord.ext import buttons
import sqlite3 as sql
import asyncio
from functools import partial

# Epic mixin so that the pages dont get deleted
async def _teardown(self, *args, **kwargs):
    """Clean the session up."""
    self._session_task.cancel()

    try:
        await self.page.clear_reactions()
    except discord.Forbidden:
        pass
buttons.Session.teardown = _teardown

class PlayedTracker(commands.Cog, name='Played Tracker'):
    def __init__(self, bot):
        self.bot = bot
        self.conn = None
        self.task = asyncio.create_task(self.checkPlaying())
        self.toTrack = []

    def cog_unload(self):
        self.task.cancel()
        self.conn.close()

    async def checkPlaying(self):
        await self.bot.wait_until_ready()
        self.conn = sql.connect('playing.db')
        self.getTrackList()
        while not self.bot.is_closed():
            await asyncio.sleep(60)
            for n in self.toTrack:
                try:
                    mem = self.bot.get_guild(n[1]).get_member(n[0])
                except AttributeError:
                    continue
                if mem is None:
                    continue

                if len(mem.activities) < 1:
                    continue
                act = mem.activities[0]
                self.updateGame(n[0],act.name,act.type.value)
            self.conn.commit()

    def getTrackList(self):
        c = self.conn.cursor()
        try:
            c.execute('CREATE TABLE tracklist (uid int, guildid int)')
        except Exception:
            pass
        self.toTrack = c.execute('SELECT * FROM tracklist').fetchall()

    def track(self,uid,gid):
        self.toTrack.append((uid,gid))
        c = self.conn.cursor()
        c.execute('INSERT INTO tracklist VALUES (?, ?)',(uid,gid))
        self.conn.commit()

    def updateGame(self,uid,game,acttype):
        c = self.conn.cursor()
        uid = 'u'+str(uid)
        try:
            c.execute(f'CREATE TABLE {uid} (game text, time int, acttype tinyint)')
        except Exception:
            pass
        c.execute(f'SELECT * FROM {uid} WHERE game=?', (game,))
        if c.fetchone() == None:
            c.execute(f'INSERT INTO {uid} VALUES (?, ?, ?)', (game,1,acttype))
            return
        time = c.execute(f'SELECT time FROM {uid} WHERE game=?', (game,)).fetchone()[0]
        c.execute(f'UPDATE {uid} SET time=? WHERE game=?',(time+1,game))
        
    def getUserPlayed(self,uid):
        c = self.conn.cursor()
        uid = 'u'+str(uid)
        try:
            c.execute(f'SELECT time FROM {uid}')
        except Exception:
            return
        return c.execute(f'SELECT * FROM {uid}').fetchall()

    def formatTime(self,time,acttype):
        verb = 'played streamed listened watched ????'.split(' ')[acttype]
        hours,minutes = divmod(time,60)
        days,hours = divmod(hours,24)
        time = ''
        time += f'{days}d' if days > 0 else ''
        time += f'{hours}h' if hours > 0 else ''
        time += f'{minutes}m' if minutes > 0 else ''
        return f'{verb} for {time}'

    def stopTracking(self,uid,delete):
        self.toTrack.pop([j for j,i in enumerate(self.toTrack) if i[0] == uid][0])
        c = self.conn.cursor()
        try:
            c.execute('DELETE FROM tracklist WHERE uid=?',(uid,))
        except sql.OperationalError:
            pass
        if delete:
            uid = 'u'+str(uid)
            try:
                c.execute(f'DROP TABLE {uid}')
            except sql.OperationalError:
                pass
        self.conn.commit()

    @commands.command()
    async def played(self,ctx,*args):
        """
        Check played games stats
        Usage:
        {prefix}played [enable|disable|delete|(user)]
        """
        user = ctx.author
        if len(args) > 0 and args[0] not in ('enable', 'disable', 'delete'):
            user = await commands.MemberConverter().convert(ctx, args[0])
            if user and not any(map(lambda x: x[0] == user.id, self.toTrack)):
                await ctx.send('Tagged person does not have played tracking enabled')
                return
        elif not any(map(lambda x: x[0] == user.id, self.toTrack)):
            if ctx.guild is None:
                await ctx.send('You can only enable the played command within a guild')
                return
            elif len(args) == 0 or args[0] != 'enable':
                await ctx.send(f'I\'m currently not tracking your games, do `{self.bot.command_prefix}played enable` to enable')
                return
            else:
                self.track(ctx.author.id,ctx.guild.id)
                await ctx.send(f'Your games will now be tracked forever!!! >:) :smiling_imp:\ndo `{self.bot.command_prefix}played disable` to opt out *or `delete` to disable and delete all data*')
                return

        if len(args) > 0 and args[0] in ('disable','delete'):
            self.stopTracking(ctx.author.id, args[0] == 'delete')
            await ctx.send('Game tracking is now disabled')
            return

        games = self.getUserPlayed(user.id)
        if games is None or len(games) < 1:
            await ctx.send(f'{"You" if user == ctx.author else "They"} haven\'t played any games yet!')
            return

        games.sort(key=lambda x: x[1],reverse=True)
        pages = []
        page = ''
        i = 0
        for game in games:
            page += f'**{game[0]}** - {self.formatTime(game[1], game[2])}\n'
            i += 1
            if i > 10:
                i = 0
                pages.append(page)
                page = ''
        if i != 0: pages.append(page)
        p = buttons.Paginator(title=f'{user.name}\'s played stats', colour=0x61C7C3, embed=True, timeout=10, use_defaults=True,
        entries=pages, length=1)
        await p.start(ctx)

def setup(bot):
    bot.add_cog(PlayedTracker(bot))