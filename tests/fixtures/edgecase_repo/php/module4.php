<?php
namespace Example\Gen;

use Example\Gen\Base4;
use Example\Gen\Handler4 as H4;

class Base4
{
    protected $name;
}

interface Handler4
{
    public function handle($payload);
}

class Service4 extends Base4 implements Handler4
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

function helper_4($value) {
    return $value;
}
