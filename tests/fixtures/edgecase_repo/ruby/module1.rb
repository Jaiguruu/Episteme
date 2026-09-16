require_relative "./module0"

module Example
  class Base1
    def initialize(name)
      @name = name
    end
  end

  class Service1 < Base1
    def handle(payload)
      validate(payload)
      true
    end

    def validate(payload)
      !payload.nil?
    end
  end
end

def helper_1(value)
  value
end
