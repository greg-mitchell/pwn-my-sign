#!/usr/bin/env bash
set -euo pipefail

case "${0##*/}" in
    cmp)
        [ "${FAKE_CMP_ERROR:-0}" = 0 ] || exit 2
        exec "$REAL_CMP" "$@" ;;
    mv)
        [ "${FAKE_MV_ERROR:-0}" = 0 ] || exit 1
        exec "$REAL_MV" "$@" ;;
esac
