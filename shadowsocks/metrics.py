from aiohttp import web


routes = web.RouteTableDef()
app = web.Application()


@routes.get("/metrics")
async def metrics_handler(request):
    from shadowsocks.mdb.models import UserServer

    active_user_count = len(UserServer.__active_user_ids__)
    total_connection_count = UserServer.get_total_connection_count()
    return web.json_response(
        {
            "active_user_count": active_user_count,
            "total_connection_count": total_connection_count,
        }
    )


async def run_metrics_server():
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 9000)
    await site.start()
