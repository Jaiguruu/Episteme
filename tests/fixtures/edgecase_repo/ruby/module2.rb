require_relative "./module1"

module Example
  class Base2
    def initialize(name)
      @name = name
    end
  end

  class Service2 < Base2
    def handle(payload)
      validate(payload)
      true
    end

    def validate(payload)
      !payload.nil?
    end
  end
end

def helper_2(value)
  value
end
