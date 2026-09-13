require_relative "./module3"

module Example
  class Base4
    def initialize(name)
      @name = name
    end
  end

  class Service4 < Base4
    def handle(payload)
      validate(payload)
      true
    end

    def validate(payload)
      !payload.nil?
    end
  end
end

def helper_4(value)
  value
end
