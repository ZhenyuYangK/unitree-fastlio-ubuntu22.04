#!/usr/bin/env bash
export G1_NETWORK_INTERFACE=lo
unset CYCLONEDDS_URI
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/setup_common.sh"
