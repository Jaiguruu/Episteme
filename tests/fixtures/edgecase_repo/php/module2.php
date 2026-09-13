<?php
namespace Example\Gen;

use Example\Gen\Base2;
use Example\Gen\Handler2 as H2;

class Base2
{
    protected $name;
}

interface Handler2
{
    public function handle($payload);
}

class Service2 extends Base2 implements Handler2
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

function helper_2($value) {
    return $value;
}
