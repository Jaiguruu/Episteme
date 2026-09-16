require_relative "./module4"

module Example
  class Base5
    def initialize(name)
      @name = name
    end
  end

  class Service5 < Base5
    def handle(payload)
      validate(payload)
      true
    end

    def validate(payload)
      !payload.nil?
    end
  end
end

def helper_5(value)
  value
end
