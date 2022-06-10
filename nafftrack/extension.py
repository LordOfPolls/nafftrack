import asyncio
import logging

import prometheus_client
import uvicorn
import naff
from nafftrack.stats import (
    bot_info,
    channels_gauge,
    guilds_gauge,
    latency_gauge,
    members_gauge,
    messages_counter,
    snek_info,
)


class Stats(naff.Extension):
    host = "0.0.0.0"
    port = 8877
    interval = 5

    @naff.listen()
    async def on_startup(self) -> None:
        logging.info("Starting metrics endpoint!")
        app = prometheus_client.make_asgi_app()
        config = uvicorn.Config(app=app, host=self.host, port=self.port, access_log=False)
        server = uvicorn.Server(config)
        loop = asyncio.get_running_loop()
        loop.create_task(server.serve())

        snek_info.info(
            {
                "version": naff.const.__version__,
            }
        )

        guilds_gauge.set(len(self.bot.user._guild_ids))

        stats_task = naff.Task(
            self.collect_stats, naff.triggers.IntervalTrigger(seconds=self.interval)
        )
        stats_task.start()

    @naff.listen()
    async def on_ready(self) -> None:
        bot_info.info(
            {
                "username": self.bot.user.username,
                "discriminator": self.bot.user.discriminator,
                "tag": str(self.bot.user.tag),
            }
        )
        for guild in self.bot.guilds:
            c_gauge = channels_gauge.labels(guild_id=guild.id, guild_name=guild.name)
            m_gauge = members_gauge.labels(guild_id=guild.id, guild_name=guild.name)

            c_gauge.set(len(guild._channel_ids))
            m_gauge.set(guild.member_count)
            if naff.Intents.GUILD_MEMBERS in self.bot.intents:
                m_gauge.set(len(guild._member_ids))

    @naff.listen()
    async def on_message_create(self, event: naff.events.MessageCreate):
        if guild := event.message.guild:
            counter = messages_counter.labels(guild_id=guild.id, guild_name=guild.name, dm=0)
        else:
            counter = messages_counter.labels(guild_id=None, guild_name=None, dm=1)

        counter.inc()

    # @tasks.Task.create(tasks.triggers.IntervalTrigger(seconds=interval))  # TODO wait for polls implementing it
    async def collect_stats(self):
        # Latency stats
        if latency := self.bot.ws.latency:
            latency_gauge.set(latency[-1])

    @naff.listen()
    async def on_guild_join(self, _):
        # ignore guild_join events during bot initialization
        if not self.bot.is_ready:
            return

        guilds_gauge.inc()

    @naff.listen()
    async def on_guild_left(self, _):
        guilds_gauge.dec()

    @naff.listen()
    async def on_member_remove(self, event: naff.events.MemberRemove):
        gauge = members_gauge.labels(guild_id=event.guild.id, guild_name=event.guild.name)
        gauge.dec()

    @naff.listen()
    async def on_member_add(self, event: naff.events.MemberAdd):
        gauge = members_gauge.labels(guild_id=event.guild.id, guild_name=event.guild.name)
        gauge.inc()

    @naff.listen()
    async def on_channel_delete(self, event: naff.events.ChannelDelete):
        gauge = channels_gauge.labels(guild_id=event.guild.id, guild_name=event.guild.name)
        gauge.dec()

    @naff.listen()
    async def on_channel_create(self, event: naff.events.ChannelCreate):
        gauge = channels_gauge.labels(guild_id=event.guild.id, guild_name=event.guild.name)
        gauge.inc()

    # @naff.listen()
    # async def on_guild_unavailable(self, event):
    #     guilds_gauge.set(len(self.bot.user._guild_ids))


def setup(client):
    Stats(client)
