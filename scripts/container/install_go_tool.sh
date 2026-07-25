#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -lt 1 ]; then
    echo "usage: install_go_tool.sh PACKAGE@VERSION [MODULE@MINIMUM_VERSION ...]" >&2
    exit 2
fi

tool_spec=$1
shift
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

for dependency_spec in "$@"; do
    case "$dependency_spec" in
        *@*)
            dependency_module=${dependency_spec%@*}
            dependency_version=${dependency_spec##*@}
            ;;
        *)
            echo "Go dependency floor must include an exact module version: $dependency_spec" >&2
            exit 2
            ;;
    esac
    if [ -z "$dependency_module" ] || [ -z "$dependency_version" ] ||
        [ "$dependency_module" = "$dependency_spec" ]; then
        echo "invalid Go dependency floor: $dependency_spec" >&2
        exit 2
    fi
done

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
for dependency_spec in "$@"; do
    go get "$dependency_spec"
done
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

if [ -n "${GO_TOOL_SOURCE_PATCH:-}" ]; then
    if [ ! -f "$GO_TOOL_SOURCE_PATCH" ]; then
        echo "Go tool source patch does not exist: $GO_TOOL_SOURCE_PATCH" >&2
        exit 1
    fi
    module_dir=$(go list -m -f '{{.Dir}}' "$module_path")
    if [ -z "$module_dir" ] || [ ! -d "$module_dir" ]; then
        echo "Go tool module source directory is unavailable: module=$module_path directory=$module_dir" >&2
        exit 1
    fi
    chmod -R u+w "$module_dir"
    git -C "$module_dir" apply --check "$GO_TOOL_SOURCE_PATCH"
    git -C "$module_dir" apply "$GO_TOOL_SOURCE_PATCH"
    patch_sha256=$(sha256sum "$GO_TOOL_SOURCE_PATCH" | awk '{print $1}')
    printf '%s\n' \
        "Applied Go tool source patch package=$package patch=$GO_TOOL_SOURCE_PATCH sha256=$patch_sha256"
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

dependency_summary=
for dependency_spec in "$@"; do
    dependency_module=${dependency_spec%@*}
    dependency_floor=${dependency_spec##*@}
    selected_dependency_version=$(go list -m -f '{{.Version}}' "$dependency_module")
    embedded_dependency_version=$(
        go version -m "$target" |
            awk -v module="$dependency_module" '$1 == "dep" && $2 == module {print $3; exit}'
    )
    if [ -z "$selected_dependency_version" ] ||
        [ "$embedded_dependency_version" != "$selected_dependency_version" ]; then
        echo "Go tool dependency floor mismatch: package=$package dependency=$dependency_module floor=$dependency_floor selected=$selected_dependency_version embedded=$embedded_dependency_version" >&2
        exit 1
    fi
    dependency_summary="${dependency_summary} ${dependency_module}=${embedded_dependency_version}"
done

x_crypto_version=$(go list -m -f '{{.Version}}' golang.org/x/crypto)
printf '%s\n' \
    "Installed Go tool package=$package module=$module_path version=$embedded_version x_crypto=$x_crypto_version${dependency_summary}"
