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
        requested_version=${tool_spec##*@}
        ;;
    *)
        echo "Go tool must include an exact module version: $tool_spec" >&2
        exit 2
        ;;
esac

if [ -z "$package" ] || [ -z "$requested_version" ] || [ "$package" = "$tool_spec" ]; then
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

# Establish the reviewed x/crypto release as a floor before selecting the
# requested tool. A tool can raise the dependency when its pinned release
# requires a newer version, but the floor must never downgrade the tool itself.
go get "golang.org/x/crypto@${GO_X_CRYPTO_VERSION}"
go get "$tool_spec"

module_path=$(go list -f '{{if .Module}}{{.Module.Path}}{{end}}' "$package")
if [ -z "$module_path" ]; then
    echo "Go tool package has no owning module: $package" >&2
    exit 1
fi

selected_version=$(go list -m -f '{{.Version}}' "$module_path")
expected_version=$(go list -m -f '{{.Version}}' "${module_path}@${requested_version}")
if [ -z "$selected_version" ] || [ "$selected_version" != "$expected_version" ]; then
    echo "Go tool module version mismatch: package=$package expected=$expected_version selected=$selected_version" >&2
    exit 1
fi

go install "$package"

target=$(go list -f '{{.Target}}' "$package")
if [ -z "$target" ] || [ ! -x "$target" ]; then
    echo "Go tool install did not create an executable: package=$package target=$target" >&2
    exit 1
fi

embedded_version=$(
    go version -m "$target" |
        awk -v module="$module_path" '$1 == "mod" && $2 == module {print $3; exit}'
)
if [ -z "$embedded_version" ] || [ "$embedded_version" != "$expected_version" ]; then
    echo "Go tool embedded module version mismatch: package=$package expected=$expected_version embedded=$embedded_version" >&2
    exit 1
fi

x_crypto_version=$(go list -m -f '{{.Version}}' golang.org/x/crypto)
printf '%s\n' \
    "Installed Go tool package=$package module=$module_path version=$embedded_version x_crypto=$x_crypto_version"
