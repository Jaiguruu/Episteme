<?php
namespace Example\Gen;

use Example\Gen\Base3;
use Example\Gen\Handler3 as H3;

class Base3
{
    protected $name;
}

interface Handler3
{
    public function handle($payload);
}

class Service3 extends Base3 implements Handler3
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

function helper_3($value) {
    return $value;
}
