require_relative "./module5"

module Example
  class Base6
    def initialize(name)
      @name = name
    end
  end

  class Service6 < Base6
    def handle(payload)
      validate(payload)
      true
    end

    def validate(payload)
      !payload.nil?
    end
  end
end

def helper_6(value)
  value
end
