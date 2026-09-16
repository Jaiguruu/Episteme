#!/usr/bin/env bash
source "./module1.sh"

BASE_2="base"

handle_2() {
  local payload="$1"
  validate_2 "$payload"
  echo "$payload"
}

validate_2() {
  [ -n "$1" ]
}

helper_2() {
  echo "$1"
}
