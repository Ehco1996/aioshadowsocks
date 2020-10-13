.PHONY: setup update proto_compile fmt publish

setup:
	poetry install

update:
	poetry update

proto_compile:
	echo "compile async proto..."

	python3 -m grpc_tools.protoc -I protos --python_out=shadowsocks/gen/async_protos --grpclib_python_out=shadowsocks/gen/async_protos protos/*.proto
	sed -i "" -e 's/import aioshadowsocks_pb2/from . import aioshadowsocks_pb2/g' \
           shadowsocks/gen/async_protos/aioshadowsocks_grpc.py

	echo "compile sync proto..."

	python3 -m grpc_tools.protoc -I protos --python_out=shadowsocks/gen/sync_protos --grpc_python_out=shadowsocks/gen/sync_protos protos/*.proto
	sed -i "" -e 's/import aioshadowsocks_pb2/from . import aioshadowsocks_pb2/g' \
           shadowsocks/gen/sync_protos/aioshadowsocks_pb2_grpc.py
publish:
	poetry build && poetry publish

fmt:
	autoflake --recursive --remove-all-unused-imports --in-place . && isort . && black .
