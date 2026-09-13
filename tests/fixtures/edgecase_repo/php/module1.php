<?php
namespace Example\Gen;

use Example\Gen\Base1;
use Example\Gen\Handler1 as H1;

class Base1
{
    protected $name;
}

interface Handler1
{
    public function handle($payload);
}

class Service1 extends Base1 implements Handler1
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

function helper_1($value) {
    return $value;
}
