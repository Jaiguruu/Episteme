local mod0 = require("module0")

local Base1 = {}
Base1.__index = Base1

function Base1.new(name)
  local self = setmetatable({}, Base1)
  self.name = name
  return self
end

local Service1 = setmetatable({}, { __index = Base1 })

function Service1:handle(payload)
  self:validate(payload)
  return true
end

function Service1:validate(payload)
  return payload ~= nil
end

local function helper1(value)
  return value
end

return Service1
