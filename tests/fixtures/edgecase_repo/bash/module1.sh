#!/usr/bin/env bash
source "./module0.sh"

BASE_1="base"

handle_1() {
  local payload="$1"
  validate_1 "$payload"
  echo "$payload"
}

validate_1() {
  [ -n "$1" ]
}

helper_1() {
  echo "$1"
}
