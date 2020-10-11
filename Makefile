.PHONY: setup update proto_compile fmt publish

setup:
	poetry install

update:
	poetry update

proto_compile:
	python3 -m grpc_tools.protoc -I. --python_out=. --python_grpc_out=. shadowsocks/protos/aioshadowsocks.proto

publish:
	poetry build && poetry publish

fmt:
	autoflake --recursive --remove-all-unused-imports --in-place . && isort . && black .
