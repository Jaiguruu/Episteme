#!/usr/bin/env bash
source "./module4.sh"

BASE_5="base"

handle_5() {
  local payload="$1"
  validate_5 "$payload"
  echo "$payload"
}

validate_5() {
  [ -n "$1" ]
}

helper_5() {
  echo "$1"
}
