require_relative "./module2"

module Example
  class Base3
    def initialize(name)
      @name = name
    end
  end

  class Service3 < Base3
    def handle(payload)
      validate(payload)
      true
    end

    def validate(payload)
      !payload.nil?
    end
  end
end

def helper_3(value)
  value
end
