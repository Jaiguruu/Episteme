"""Developer tool: dump tree-sitter parse trees for representative snippets.

Not part of the pipeline. Used once, to write the extraction queries against
real node names instead of guessed ones.

Usage:
    python tools/dump_trees.py [language ...]
"""

from __future__ import annotations

import sys

import tree_sitter_language_pack as pack

SAMPLES: dict[str, str] = {
    "python": '''
"""Module docstring."""
import os
from models.payment import Payment as Pay


class PaymentService(Base, Mixin):
    """A service."""

    def process(self, payment):
        self.validate(payment)
        os.path.join("a", "b")

    @staticmethod
    def validate(payment):
        return True
''',
    "javascript": '''
import { Payment } from "./models/payment";
const os = require("os");

class PaymentService extends Base {
  process(payment) {
    this.validate(payment);
    os.join("a", "b");
  }
}

function helper(a) {
  return a;
}
''',
    "typescript": '''
import { Payment } from "./models/payment";

interface Repo {
  save(p: Payment): void;
}

export class PaymentService extends Base implements Repo {
  private repo: string;

  process(payment: Payment): boolean {
    this.validate(payment);
    return true;
  }
}

function helper(a: number): number {
  return a;
}
''',
    "tsx": '''
import React from "react";

export interface Props {
  name: string;
}

export function Widget(props: Props) {
  const handle = () => props.name;
  return <div onClick={handle}>{props.name}</div>;
}

export class Panel extends React.Component {
  render() {
    return <span />;
  }
}
''',
    "java": '''
package com.example.services;

import com.example.models.Payment;

public class PaymentService extends BaseService implements Runnable {
    private final String repo;

    public PaymentService(String repo) {
        this.repo = repo;
    }

    public boolean process(Payment payment) {
        this.validate(payment);
        return true;
    }
}
''',
    "go": '''
package services

import (
    "fmt"
    "example.com/models"
)

type PaymentService struct {
    Repo string
}

type Processor interface {
    Process(p models.Payment) bool
}

func (s *PaymentService) Process(p models.Payment) bool {
    s.validate(p)
    fmt.Println("x")
    return true
}

func helper(a int) int {
    return a
}
''',
    "rust": '''
use crate::models::Payment;

pub struct PaymentService {
    repo: String,
}

pub trait Processor {
    fn process(&self, p: Payment) -> bool;
}

impl Processor for PaymentService {
    fn process(&self, p: Payment) -> bool {
        self.validate(p);
        true
    }
}

pub fn helper(a: i32) -> i32 {
    a
}
''',
    "c": '''
#include <stdio.h>
#include "payment.h"

struct PaymentService {
    int repo;
};

typedef struct PaymentService PaymentService;

int process_payment(Payment *p) {
    validate(p);
    printf("x");
    return 0;
}
''',
    "cpp": '''
#include <string>
#include "payment.hpp"

class PaymentService : public BaseService {
public:
    PaymentService(std::string repo) : repo_(repo) {}

    bool process(Payment& p) {
        this->validate(p);
        return true;
    }

private:
    std::string repo_;
};

int helper(int a) { return a; }
''',
    "csharp": '''
using System;
using Example.Models;

namespace Example.Services
{
    public class PaymentService : BaseService, IProcessor
    {
        private readonly string repo;

        public PaymentService(string repo)
        {
            this.repo = repo;
        }

        public bool Process(Payment p)
        {
            this.Validate(p);
            return true;
        }
    }

    public interface IProcessor
    {
        bool Process(Payment p);
    }
}
''',
    "ruby": '''
require "json"
require_relative "./payment"

module Example
  class PaymentService < BaseService
    include Comparable

    def initialize(repo)
      @repo = repo
    end

    def process(payment)
      validate(payment)
      true
    end
  end
end

def helper(a)
  a
end
''',
    "php": '''
<?php
namespace Example\\Services;

use Example\\Models\\Payment;
use Example\\Models\\Payment as Pay;

class PaymentService extends BaseService implements Processor
{
    private $repo;

    public function __construct($repo)
    {
        $this->repo = $repo;
    }

    public function process(Payment $payment): bool
    {
        $this->validate($payment);
        return true;
    }
}

function helper($a) {
    return $a;
}
''',
    "kotlin": '''
package com.example.services

import com.example.models.Payment

interface Processor {
    fun process(p: Payment): Boolean
}

class PaymentService(private val repo: String) : BaseService(), Processor {
    override fun process(p: Payment): Boolean {
        this.validate(p)
        return true
    }
}

fun helper(a: Int): Int {
    return a
}
''',
    "swift": '''
import Foundation
import ExampleKit

protocol Processor {
    func process(_ p: Payment) -> Bool
}

class PaymentService: BaseService, Processor {
    private let repo: String

    init(repo: String) {
        self.repo = repo
    }

    func process(_ p: Payment) -> Bool {
        self.validate(p)
        return true
    }
}

func helper(_ a: Int) -> Int {
    return a
}
''',
    "scala": '''
package com.example.services

import com.example.models.Payment

trait Processor {
  def process(p: Payment): Boolean
}

class PaymentService(repo: String) extends BaseService with Processor {
  def process(p: Payment): Boolean = {
    this.validate(p)
    true
  }
}

object Main {
  def helper(a: Int): Int = a
}
''',
    "lua": '''
local json = require("json")
local payment = require("models.payment")

local PaymentService = {}
PaymentService.__index = PaymentService

function PaymentService.new(repo)
  local self = setmetatable({}, PaymentService)
  self.repo = repo
  return self
end

function PaymentService:process(p)
  self:validate(p)
  return true
end

local function helper(a)
  return a
end

return PaymentService
''',
    "bash": '''
#!/usr/bin/env bash
source ./lib/common.sh
. ./lib/helpers.sh

function process_payment() {
  local payment="$1"
  validate "$payment"
  echo "done"
}

helper() {
  echo "$1"
}

process_payment "x"
''',
    "dart": '''
import 'dart:async';
import 'package:example/models/payment.dart';

abstract class Processor {
  bool process(Payment p);
}

class PaymentService extends BaseService implements Processor {
  final String repo;

  PaymentService(this.repo);

  @override
  bool process(Payment p) {
    this.validate(p);
    return true;
  }
}

int helper(int a) => a;
''',
}


def main(argv: list[str]) -> int:
    wanted = argv[1:] or sorted(SAMPLES)
    for language in wanted:
        sample = SAMPLES.get(language)
        if sample is None:
            print(f"=== {language}: no sample ===")
            continue
        try:
            parser = pack.get_parser(language)
            tree = parser.parse(sample.encode("utf-8"))
        except Exception as error:  # noqa: BLE001
            print(f"=== {language}: FAILED {error} ===")
            continue
        print(f"=== {language} (has_error={tree.root_node.has_error}) ===")
        print(tree.root_node)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
