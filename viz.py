from shadowsocks.app import App

if __name__ == "__main__":
    # NOTE 用viztrace看一下到cpu耗时花费在哪里
    app = App()
    app.run_ss_server()
