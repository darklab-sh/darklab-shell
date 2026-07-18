#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: install_go_tool.sh PACKAGE@VERSION" >&2
    exit 2
fi

tool_spec=$1
case "$tool_spec" in
    *@*)
        package=${tool_spec%@*}
        ;;
    *)
        echo "Go tool must include an exact module version: $tool_spec" >&2
        exit 2
        ;;
esac

if [ -z "$package" ] || [ "$package" = "$tool_spec" ]; then
    echo "invalid Go tool specification: $tool_spec" >&2
    exit 2
fi

: "${GO_X_CRYPTO_VERSION:?GO_X_CRYPTO_VERSION must be set}"

build_dir=$(mktemp -d)
cleanup() {
    rm -rf "$build_dir"
}
trap cleanup EXIT HUP INT TERM

cd "$build_dir"
go mod init darklab.invalid/tool-install
go get "$tool_spec"
go get "golang.org/x/crypto@${GO_X_CRYPTO_VERSION}"
go install "$package"
