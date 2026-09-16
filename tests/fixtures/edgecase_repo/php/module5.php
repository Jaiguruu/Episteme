<?php
namespace Example\Gen;

use Example\Gen\Base5;
use Example\Gen\Handler5 as H5;

class Base5
{
    protected $name;
}

interface Handler5
{
    public function handle($payload);
}

class Service5 extends Base5 implements Handler5
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

function helper_5($value) {
    return $value;
}
