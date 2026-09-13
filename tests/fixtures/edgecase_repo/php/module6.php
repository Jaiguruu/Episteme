<?php
namespace Example\Gen;

use Example\Gen\Base6;
use Example\Gen\Handler6 as H6;

class Base6
{
    protected $name;
}

interface Handler6
{
    public function handle($payload);
}

class Service6 extends Base6 implements Handler6
{
    public function handle($payload): bool
    {
        $this->validate($payload);
        return true;
    }

    private function validate($payload): void
    {
    }
}

function helper_6($value) {
    return $value;
}
