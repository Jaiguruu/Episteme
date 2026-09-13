local mod1 = require("module1")

local Base2 = {}
Base2.__index = Base2

function Base2.new(name)
  local self = setmetatable({}, Base2)
  self.name = name
  return self
end

local Service2 = setmetatable({}, { __index = Base2 })

function Service2:handle(payload)
  self:validate(payload)
  return true
end

function Service2:validate(payload)
  return payload ~= nil
end

local function helper2(value)
  return value
end

return Service2
