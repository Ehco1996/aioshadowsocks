def run_server():
    from shadowsocks.app import App

    app = App()
    app.run()


if __name__ == "__main__":
    run_server()
