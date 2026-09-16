#!/usr/bin/env bash
source "./module2.sh"

BASE_3="base"

handle_3() {
  local payload="$1"
  validate_3 "$payload"
  echo "$payload"
}

validate_3() {
  [ -n "$1" ]
}

helper_3() {
  echo "$1"
}
