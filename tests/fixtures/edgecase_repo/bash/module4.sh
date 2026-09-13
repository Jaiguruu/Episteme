#!/usr/bin/env bash
source "./module3.sh"

BASE_4="base"

handle_4() {
  local payload="$1"
  validate_4 "$payload"
  echo "$payload"
}

validate_4() {
  [ -n "$1" ]
}

helper_4() {
  echo "$1"
}
